"""
Condition registry.

Centralises condition discovery and presentation metadata.
Sole authority for:
- Which conditions exist
- How they are labelled for patients
- What framing text is shown before session start
- Resolving condition_id to ruleset file path

Initialised once at application startup. Immutable after initialisation.
Any validation failure aborts startup.

This module must never:
- Expose questions, encoder definitions, safety rules, or ruleset hashes
- Return raw ruleset JSON
- Be imported by form_logic, encoder_mapping, encoder_stub, or safety_engine

Note: pre_form_information is no longer supported in presentation blocks.
Practice-specific signposting is handled by presentation_service.py using
data from practice_repository.py. Universal safety warnings are defined
as constants in presentation_service.py.
"""

import logging
import os
import json
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

# Limits for search_tags validation. Named constants so they are easy to adjust.
SEARCH_TAGS_MAX_COUNT = 20
SEARCH_TAGS_MAX_TAG_LENGTH = 60


class ConditionNotFound(Exception):
    pass


class RegistryValidationError(Exception):
    pass


class ConditionRegistry:
    """
    Immutable after __init__. Loads all ruleset JSON files from a directory,
    validates presentation blocks, and retains only discovery + presentation data.
    """

    def __init__(self, data_dir: str):
        self._conditions: Dict[str, dict] = {}
        self._load_order: List[str] = []
        self._load_all(data_dir)

    def _load_all(self, data_dir: str) -> None:
        if not os.path.isdir(data_dir):
            raise RegistryValidationError(
                f"Data directory does not exist: {data_dir}"
            )

        json_files = sorted(
            f for f in os.listdir(data_dir) if f.endswith(".json")
        )

        if not json_files:
            raise RegistryValidationError(
                f"No JSON files found in {data_dir}"
            )

        for filename in json_files:
            path = os.path.join(data_dir, filename)
            self._load_one(path)

    def _load_one(self, path: str) -> None:
        with open(path, "r") as f:
            raw = json.load(f)

        # Validate condition_id exists
        condition_id = raw.get("condition_id")
        if not condition_id or not isinstance(condition_id, str):
            raise RegistryValidationError(
                f"Missing or invalid condition_id in {path}"
            )

        # Reject duplicates
        if condition_id in self._conditions:
            raise RegistryValidationError(
                f"Duplicate condition_id '{condition_id}' in {path}"
            )

        # Validate and extract presentation
        presentation = raw.get("presentation")
        search_tags = self._validate_presentation(presentation, condition_id, path)

        # Store only what the registry needs
        self._conditions[condition_id] = {
            "label": presentation["label"],
            "presentation": presentation,
            "search_tags": search_tags,
            "ruleset_path": os.path.abspath(path),
        }
        self._load_order.append(condition_id)

    def _validate_presentation(
        self, presentation: Optional[dict], condition_id: str, path: str
    ) -> List[str]:
        """
        Validate the presentation block.
        Returns the cleaned search_tags list (may be empty).
        Raises RegistryValidationError on any structural or content problem.
        """
        prefix = f"condition '{condition_id}' in {path}"

        if presentation is None:
            raise RegistryValidationError(
                f"Missing presentation block for {prefix}"
            )

        if not isinstance(presentation, dict):
            raise RegistryValidationError(
                f"presentation must be an object for {prefix}"
            )

        # label is required, must be non-empty string
        label = presentation.get("label")
        if not isinstance(label, str) or label.strip() == "":
            raise RegistryValidationError(
                f"presentation.label must be a non-empty string for {prefix}"
            )

        # free_text_prompt is optional, must be string if present
        ftp = presentation.get("free_text_prompt")
        if ftp is not None and not isinstance(ftp, str):
            raise RegistryValidationError(
                f"presentation.free_text_prompt must be a string for {prefix}"
            )

        # search_tags is optional — validate and normalise if present
        search_tags = self._validate_and_normalise_tags(
            presentation.get("search_tags"), condition_id, path
        )

        # No unexpected keys
        allowed_keys = {"label", "free_text_prompt", "search_tags"}
        extra = set(presentation.keys()) - allowed_keys
        if extra:
            raise RegistryValidationError(
                f"Unexpected keys in presentation for {prefix}: {extra}"
            )

        return search_tags

    def _validate_and_normalise_tags(
        self,
        raw_tags,
        condition_id: str,
        path: str,
    ) -> List[str]:
        """
        Validate and normalise search_tags from the presentation block.

        Rules:
        - Absent or None: return empty list (not an error)
        - Must be a list
        - Each item must be a string
        - Each item stripped must be non-empty
        - Each item stripped must not exceed SEARCH_TAGS_MAX_TAG_LENGTH
        - Total count must not exceed SEARCH_TAGS_MAX_COUNT
        - Duplicates (case-insensitive) are silently removed; first occurrence kept
        - Returns the cleaned, stripped list
        """
        prefix = f"condition '{condition_id}' in {path}"

        if raw_tags is None:
            return []

        if not isinstance(raw_tags, list):
            raise RegistryValidationError(
                f"presentation.search_tags must be a list for {prefix}"
            )

        if len(raw_tags) > SEARCH_TAGS_MAX_COUNT:
            raise RegistryValidationError(
                f"presentation.search_tags exceeds maximum of {SEARCH_TAGS_MAX_COUNT} "
                f"tags for {prefix} (found {len(raw_tags)})"
            )

        cleaned: List[str] = []
        seen_lower: set = set()

        for i, item in enumerate(raw_tags):
            if not isinstance(item, str):
                raise RegistryValidationError(
                    f"presentation.search_tags item {i} must be a string for {prefix}"
                )

            stripped = item.strip()

            if not stripped:
                raise RegistryValidationError(
                    f"presentation.search_tags item {i} is empty after stripping "
                    f"for {prefix}"
                )

            if len(stripped) > SEARCH_TAGS_MAX_TAG_LENGTH:
                raise RegistryValidationError(
                    f"presentation.search_tags item {i} exceeds maximum length of "
                    f"{SEARCH_TAGS_MAX_TAG_LENGTH} characters for {prefix}"
                )

            lower = stripped.lower()
            if lower in seen_lower:
                logger.warning(
                    "Duplicate search_tag '%s' removed for condition '%s' in %s",
                    stripped,
                    condition_id,
                    path,
                )
                continue

            seen_lower.add(lower)
            cleaned.append(stripped)

        return cleaned

    # --- Public interface ---

    def list_conditions(self) -> List[dict]:
        """Returns ordered list of {id, label, search_tags} for all conditions."""
        return [
            {
                "id": cid,
                "label": self._conditions[cid]["label"],
                "search_tags": self._conditions[cid]["search_tags"],
            }
            for cid in self._load_order
        ]

    def get_presentation(self, condition_id: str) -> dict:
        """Returns the full presentation block for a condition."""
        entry = self._conditions.get(condition_id)
        if entry is None:
            raise ConditionNotFound(condition_id)
        return entry["presentation"]

    def get_ruleset_path(self, condition_id: str) -> str:
        """Returns the absolute file path to the ruleset JSON."""
        entry = self._conditions.get(condition_id)
        if entry is None:
            raise ConditionNotFound(condition_id)
        return entry["ruleset_path"]

    def has_condition(self, condition_id: str) -> bool:
        return condition_id in self._conditions

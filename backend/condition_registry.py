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
"""

import os
import json
from typing import Dict, List, Optional


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
        self._validate_presentation(presentation, condition_id, path)

        # Store only what the registry needs
        self._conditions[condition_id] = {
            "label": presentation["label"],
            "presentation": presentation,
            "ruleset_path": os.path.abspath(path),
        }
        self._load_order.append(condition_id)

    def _validate_presentation(
        self, presentation: Optional[dict], condition_id: str, path: str
    ) -> None:
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

        # pre_form_information is optional, must be list of strings if present
        pfi = presentation.get("pre_form_information")
        if pfi is not None:
            if not isinstance(pfi, list):
                raise RegistryValidationError(
                    f"presentation.pre_form_information must be an array for {prefix}"
                )
            for i, item in enumerate(pfi):
                if not isinstance(item, str):
                    raise RegistryValidationError(
                        f"presentation.pre_form_information[{i}] must be a string for {prefix}"
                    )

        # No nested objects, no templating, no clinical references
        allowed_keys = {"label", "free_text_prompt", "pre_form_information"}
        extra = set(presentation.keys()) - allowed_keys
        if extra:
            raise RegistryValidationError(
                f"Unexpected keys in presentation for {prefix}: {extra}"
            )

    # --- Public interface ---

    def list_conditions(self) -> List[dict]:
        """Returns ordered list of {id, label} for all conditions."""
        return [
            {"id": cid, "label": self._conditions[cid]["label"]}
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
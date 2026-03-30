"""
Consultation outcome constants.

Single source of truth for consultation outcome values and labels, shared across:
  - consultation_outcomes.json  — canonical data file (this is what you edit)
  - app/core/consultation_outcomes.py  — this file (Python side)
  - frontend/src/types.ts  — ConsultationOutcome union type (must be kept in sync manually)

The JSON file is loaded once at module import time. A missing or malformed
JSON file is a deployment error and will raise immediately at startup.

VALUE STRINGS ARE IMMUTABLE once the system has live data. Adding new entries
is safe. Renaming or removing existing values is a breaking change — old
submissions stored in the database will contain values that no longer exist
in this list.

Do not define outcome values anywhere else in the backend codebase.
"""

import json
import os

_HERE = os.path.dirname(__file__)
_JSON_PATH = os.path.join(_HERE, "consultation_outcomes.json")

with open(_JSON_PATH, "r", encoding="utf-8") as _f:
    CONSULTATION_OUTCOMES: list[dict] = json.load(_f)

# Derived: frozenset of valid value strings, used for O(1) validation.
VALID_OUTCOME_VALUES: frozenset[str] = frozenset(
    entry["value"] for entry in CONSULTATION_OUTCOMES
)

# Derived: mapping from value string to human-readable label, used in PDF rendering.
OUTCOME_LABELS: dict[str, str] = {
    entry["value"]: entry["label"] for entry in CONSULTATION_OUTCOMES
}
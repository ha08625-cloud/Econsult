"""
Consultation outcome constants.

Single source of truth for valid consultation outcome values and their
human-readable labels, shared across:
  - app/core/consultation_outcomes.py  (this file — Python side)
  - frontend/src/screens/OutcomeScreen.tsx (imports consultation_outcomes.json
    directly via resolveJsonModule)

The JSON file lives at app/core/consultation_outcomes.json alongside this
module. The Dockerfile frontend build stage copies it explicitly into the
frontend workdir so that the Vite build can resolve the import.

The value strings are stored in the database (inside the clinical_output_json
JSONB blob) and printed in the PDF. They are IMMUTABLE once deployed:
  - Adding new entries is safe.
  - Renaming or removing existing values is a breaking change.

If a value is added, also update the ConsultationOutcome union type in
frontend/src/types.ts.

Values are loaded once at module import time. A missing or malformed JSON
file is a deployment error and will raise immediately at startup.
"""

import json
import os

_HERE = os.path.dirname(__file__)
_JSON_PATH = os.path.join(_HERE, "consultation_outcomes.json")

with open(_JSON_PATH, "r", encoding="utf-8") as _f:
    _data = json.load(_f)

CONSULTATION_OUTCOMES: list[dict] = _data

VALID_OUTCOME_VALUES: frozenset[str] = frozenset(
    entry["value"] for entry in CONSULTATION_OUTCOMES
)
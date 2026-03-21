from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional


@dataclass(frozen=True)
class PatientDetails:
    patient_for: str          # "me" or "someone_else"
    first_name: str
    last_name: str
    date_of_birth: str        # ISO 8601: "1990-03-15"
    postcode: str
    submitter_name: Optional[str] = field(default=None)
    submitter_relationship: Optional[str] = field(default=None)


@dataclass(frozen=True)
class ClinicalOutput:
    condition_id: str
    free_text: str
    additional_text: Optional[str]
    answers: Dict[str, Any]
    safety_messages: List[dict]
    question_labels: Dict[str, str]  # answer_key -> question text at submission time
    patient_details: PatientDetails
    contact_preferences: Optional[Dict[str, Any]] = field(default=None)


@dataclass(frozen=True)
class AuditOutput:
    runtime_state: Dict[str, Any]
    safety_evaluation: Dict[str, Any]
    ruleset_version: str
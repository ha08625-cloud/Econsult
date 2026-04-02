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

    @classmethod
    def from_dict(cls, data: dict) -> "ClinicalOutput":
        """
        Reconstruct a ClinicalOutput from a plain dict (e.g. as returned by
        psycopg2 when reading clinical_output_json from the database).

        Handles the nested PatientDetails dataclass, which cannot be
        reconstructed by a bare **data unpack. All other fields are scalars
        or plain dicts/lists and pass through unchanged.

        Raises KeyError if required fields are absent, which surfaces the
        schema mismatch as an immediate loud error rather than a silent wrong
        value.
        """
        patient_details_raw = data["patient_details"]
        patient_details = PatientDetails(
            patient_for=patient_details_raw["patient_for"],
            first_name=patient_details_raw["first_name"],
            last_name=patient_details_raw["last_name"],
            date_of_birth=patient_details_raw["date_of_birth"],
            postcode=patient_details_raw["postcode"],
            submitter_name=patient_details_raw.get("submitter_name"),
            submitter_relationship=patient_details_raw.get("submitter_relationship"),
        )
        return cls(
            condition_id=data["condition_id"],
            free_text=data["free_text"],
            additional_text=data.get("additional_text"),
            answers=data["answers"],
            safety_messages=data["safety_messages"],
            question_labels=data["question_labels"],
            patient_details=patient_details,
            contact_preferences=data.get("contact_preferences"),
        )


@dataclass(frozen=True)
class AuditOutput:
    runtime_state: Dict[str, Any]
    safety_evaluation: Dict[str, Any]
    ruleset_version: str
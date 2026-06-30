from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional


@dataclass(frozen=True)
class PatientDetails:
    patient_for: str          # "me" or "someone_else"
    first_name: str
    last_name: str
    date_of_birth: str        # ISO 8601: "1990-03-15"
    postcode: str
    gender: str               # "male" | "female" | "other" | "prefer_not_to_say"
    preferred_name: Optional[str] = field(default=None)
    nhs_number: Optional[str] = field(default=None)
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
    # The form-wide unit system chosen by the patient, or None for a submission
    # with no quantity question. answers[key] always holds the canonical kg
    # string regardless; this records which unit the patient actually used.
    unit_system: Optional[str] = field(default=None)
    # Per quantity answer_key: {"raw_components": {...}, "decimal_places": int}.
    # raw_components is the lossless input ({"kg": "70.5"} or {"st": 11, "lb": 11})
    # and decimal_places is snapshotted so the PDF (which has no ruleset) can
    # format the canonical value. One sidecar dict, mirroring question_labels.
    quantity_answers: Dict[str, Dict[str, Any]] = field(default_factory=dict)

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
        value. unit_system and quantity_answers are read with .get() so records
        predating quantity support deserialise cleanly, same as
        photo_quality_tier on AuditOutput.
        """
        patient_details_raw = data["patient_details"]
        patient_details = PatientDetails(
            patient_for=patient_details_raw["patient_for"],
            first_name=patient_details_raw["first_name"],
            last_name=patient_details_raw["last_name"],
            date_of_birth=patient_details_raw["date_of_birth"],
            postcode=patient_details_raw["postcode"],
            gender=patient_details_raw["gender"],
            preferred_name=patient_details_raw.get("preferred_name"),
            nhs_number=patient_details_raw.get("nhs_number"),
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
            unit_system=data.get("unit_system"),
            quantity_answers=data.get("quantity_answers") or {},
        )


@dataclass(frozen=True)
class AuditOutput:
    runtime_state: Dict[str, Any]
    safety_evaluation: Dict[str, Any]
    ruleset_version: str
    # photo_quality_tier is optional because:
    # - Submissions without photos do not have a meaningful tier value.
    # - The clinical pipeline (pipeline.py / serialisation.py) has no knowledge
    #   of the HTTP submission tier. form_router.py stamps this field after
    #   finish_runtime_state() returns, using dataclasses.replace().
    # - Historical records predating this field will read None when deserialised.
    photo_quality_tier: Optional[str] = field(default=None)
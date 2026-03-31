import re
from datetime import date

from app.core.errors import INVALID_PAYLOAD
from app.core.consultation_outcomes import VALID_OUTCOME_VALUES

VALID_CONTACT_METHODS = {"email", "text", "phone"}
VALID_DOCTOR_PREFERENCES = {"any", "usual"}
VALID_PATIENT_FOR_VALUES = {"me", "someone_else"}

# Validates UK postcode format only.
# Accepts most standard outward + inward code combinations.
# Does NOT verify the postcode exists or is currently in use.
# Examples that pass: SW1A 1AA, M1 1AE, B1 1BB, EC1A 1BB
# An optional space between the two halves is permitted.
_UK_POSTCODE_RE = re.compile(
    r"^[A-Z]{1,2}\d[A-Z\d]?\s*\d[A-Z]{2}$",
    re.IGNORECASE,
)


def require_keys(obj: dict, allowed: set):
    extra = set(obj.keys()) - allowed
    if extra:
        raise INVALID_PAYLOAD(f"Illegal fields present: {extra}")


def validate_init_payload(payload: dict):
    require_keys(payload, {"condition_id", "free_text"})
    if not isinstance(payload["condition_id"], str):
        raise INVALID_PAYLOAD("condition_id must be string")


def validate_update_payload(payload: dict):
    require_keys(payload, {"runtime_id", "base_version", "answers", "additional_text"})

    if not isinstance(payload["runtime_id"], str):
        raise INVALID_PAYLOAD("runtime_id must be string")

    if not isinstance(payload["base_version"], int):
        raise INVALID_PAYLOAD("base_version must be integer")

    if not isinstance(payload["answers"], dict):
        raise INVALID_PAYLOAD("answers must be object")

    if not payload["answers"]:
        raise INVALID_PAYLOAD("answers must be complete and non-empty")

    additional_text = payload.get("additional_text")
    if additional_text is not None and not isinstance(additional_text, str):
        raise INVALID_PAYLOAD("additional_text must be a string or null")


def validate_contact_preferences(cp: dict):
    """Validate the contact_preferences block within a finish payload."""

    if not isinstance(cp, dict):
        raise INVALID_PAYLOAD("contact_preferences must be an object")

    require_keys(
        cp,
        {
            "contact_methods",
            "email_address",
            "phone_number",
            "best_time_to_call",
            "doctor_preference",
            "usual_doctor_name",
            "consultation_outcome",
        },
    )

    # contact_methods
    methods = cp.get("contact_methods")
    if not isinstance(methods, list) or len(methods) == 0:
        raise INVALID_PAYLOAD("contact_methods must be a non-empty list")

    invalid_methods = [m for m in methods if m not in VALID_CONTACT_METHODS]
    if invalid_methods:
        raise INVALID_PAYLOAD(
            f"contact_methods contains invalid values: {invalid_methods}. "
            f"Allowed: {sorted(VALID_CONTACT_METHODS)}"
        )

    methods_set = set(methods)

    # phone_number required if text or phone selected
    if methods_set & {"text", "phone"}:
        if not cp.get("phone_number"):
            raise INVALID_PAYLOAD(
                "phone_number is required when contact_methods includes 'text' or 'phone'"
            )

    # email_address required if email selected
    if "email" in methods_set:
        if not cp.get("email_address"):
            raise INVALID_PAYLOAD(
                "email_address is required when contact_methods includes 'email'"
            )

    # best_time_to_call — optional string, but must not be a non-string type if present
    best_time = cp.get("best_time_to_call")
    if best_time is not None and not isinstance(best_time, str):
        raise INVALID_PAYLOAD("best_time_to_call must be a string or null")

    # doctor_preference
    doctor_pref = cp.get("doctor_preference")
    if doctor_pref not in VALID_DOCTOR_PREFERENCES:
        raise INVALID_PAYLOAD(
            f"doctor_preference must be one of: {sorted(VALID_DOCTOR_PREFERENCES)}"
        )

    # usual_doctor_name required if doctor_preference is "usual"
    if doctor_pref == "usual" and not cp.get("usual_doctor_name"):
        raise INVALID_PAYLOAD(
            "usual_doctor_name is required when doctor_preference is 'usual'"
        )

    # consultation_outcome — required, must be a known value
    outcome = cp.get("consultation_outcome")
    if outcome is None:
        raise INVALID_PAYLOAD("consultation_outcome is required")
    if outcome not in VALID_OUTCOME_VALUES:
        raise INVALID_PAYLOAD(
            f"consultation_outcome must be one of: {sorted(VALID_OUTCOME_VALUES)}"
        )


def validate_patient_details(pd: dict) -> None:
    """Validate the patient_details block within a finish payload."""

    if not isinstance(pd, dict):
        raise INVALID_PAYLOAD("patient_details must be an object")

    require_keys(
        pd,
        {
            "patient_for",
            "first_name",
            "last_name",
            "date_of_birth",
            "postcode",
            "submitter_name",
            "submitter_relationship",
        },
    )

    # patient_for
    patient_for = pd.get("patient_for")
    if patient_for not in VALID_PATIENT_FOR_VALUES:
        raise INVALID_PAYLOAD(
            f"patient_for must be one of: {sorted(VALID_PATIENT_FOR_VALUES)}"
        )

    # Required string fields
    for field_name in ("first_name", "last_name", "postcode"):
        value = pd.get(field_name)
        if not isinstance(value, str) or not value.strip():
            raise INVALID_PAYLOAD(f"{field_name} must be a non-empty string")

    # date_of_birth — must be a dict with exactly day, month, year
    dob = pd.get("date_of_birth")
    if not isinstance(dob, dict):
        raise INVALID_PAYLOAD("date_of_birth must be an object")

    require_keys(dob, {"day", "month", "year"})

    for component in ("day", "month", "year"):
        val = dob.get(component)
        if not isinstance(val, str) or not val.strip():
            raise INVALID_PAYLOAD(
                f"date_of_birth.{component} must be a non-empty string"
            )
        if not val.strip().isdigit():
            raise INVALID_PAYLOAD(
                f"date_of_birth.{component} must contain digits only, got: {val!r}"
            )

    # Assemble and validate as a real calendar date
    try:
        assembled = date(
            int(dob["year"].strip()),
            int(dob["month"].strip()),
            int(dob["day"].strip()),
        )
    except ValueError:
        raise INVALID_PAYLOAD("date_of_birth is not a valid calendar date")

    if assembled > date.today():
        raise INVALID_PAYLOAD("date_of_birth cannot be in the future")

    # Postcode format
    if not _UK_POSTCODE_RE.match(pd["postcode"].strip()):
        raise INVALID_PAYLOAD(
            "postcode does not match a recognised UK postcode format"
        )

    # Submitter fields — required when patient_for is "someone_else"
    if patient_for == "someone_else":
        for field_name in ("submitter_name", "submitter_relationship"):
            value = pd.get(field_name)
            if not isinstance(value, str) or not value.strip():
                raise INVALID_PAYLOAD(
                    f"{field_name} is required when patient_for is 'someone_else'"
                )


def validate_finish_payload(payload: dict):
    require_keys(
        payload,
        {"runtime_id", "version", "contact_preferences", "patient_details"},
    )

    if not isinstance(payload["runtime_id"], str):
        raise INVALID_PAYLOAD("runtime_id must be string")

    if not isinstance(payload["version"], int):
        raise INVALID_PAYLOAD("version must be integer")

    if "contact_preferences" not in payload:
        raise INVALID_PAYLOAD("contact_preferences is required")

    validate_contact_preferences(payload["contact_preferences"])

    if "patient_details" not in payload:
        raise INVALID_PAYLOAD("patient_details is required")

    validate_patient_details(payload["patient_details"])
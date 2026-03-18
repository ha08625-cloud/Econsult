from dataclasses import dataclass


@dataclass
class APIError(Exception):
    code: str
    message: str


INVALID_PAYLOAD = lambda msg="Invalid payload": APIError("INVALID_PAYLOAD", msg)
UNKNOWN_RUNTIME_ID = lambda: APIError("UNKNOWN_RUNTIME_ID", "Unknown runtime_id")
VERSION_CONFLICT = lambda: APIError("VERSION_CONFLICT", "Version conflict")
INCOMPLETE_ANSWERS = lambda: APIError("INCOMPLETE_ANSWERS", "Incomplete answers")
RULESET_VALIDATION_FAILURE = lambda msg: APIError("RULESET_VALIDATION_FAILURE", msg)
SESSION_CLOSED = lambda: APIError("SESSION_CLOSED", "Session already closed")

# Admin-specific errors
CONDITION_NOT_FOUND = lambda cid: APIError("CONDITION_NOT_FOUND", f"Unknown condition: {cid}")
INVALID_DATE_FORMAT = lambda field, value: APIError(
    "INVALID_DATE_FORMAT",
    f"Invalid format for '{field}': '{value}'. Expected ISO format.",
)
INVALID_FIELD_TYPE = lambda field, expected: APIError(
    "INVALID_FIELD_TYPE",
    f"'{field}' must be {expected}",
)

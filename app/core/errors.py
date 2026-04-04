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
INVALID_DATE_FORMAT = lambda field, value: APIError(
    "INVALID_DATE_FORMAT",
    f"Invalid format for '{field}': '{value}'. Expected ISO format.",
)
INVALID_FIELD_TYPE = lambda field, expected: APIError(
    "INVALID_FIELD_TYPE",
    f"'{field}' must be {expected}",
)

# MFA auth errors
#
# INVALID_AUTH_CODE: all verification failures (wrong code, locked out, expired).
# A single generic error is deliberate — it conceals which gate failed.
# Raised as APIError -> HTTP 422 via the existing handler in main.py.
INVALID_AUTH_CODE = lambda: APIError(
    "INVALID_AUTH_CODE",
    "Invalid or expired authentication code.",
)

# SESSION_EXPIRED: session cookie present but session not found or expired.
# NOT raised as APIError. Raise directly as:
#   HTTPException(status_code=401, detail="Session expired or not found.")
# in admin_context.py. Defined here as a constant string so the message
# stays consistent and is easy to find.
SESSION_EXPIRED_MESSAGE = "Session expired or not found."

# RATE_LIMIT_EXCEEDED: code requested within the 60-second cooldown window.
# Must return HTTP 429. The existing APIError handler hardcodes 422, so this
# is a separate exception class with its own handler registered in main.py.
class RateLimitError(Exception):
    pass

RATE_LIMIT_EXCEEDED = lambda: RateLimitError(
    "Code requested too recently. Wait 60 seconds before trying again."
)

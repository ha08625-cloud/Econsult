from dataclasses import dataclass


class ConditionNotFound(Exception):
    pass


@dataclass
class APIError(Exception):
    code: str
    message: str
    status_code: int = 422


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

# SESSION_EXPIRED: 401 is the primary contract for session expiry.
# admin_context.py raises HTTPException(status_code=401, ...) directly.
# No constant is defined here — admin_context.py must never import any
# project module, so a shared constant cannot be used across that boundary.
# All 401 responses are reshaped into the standard error envelope by the
# HTTPException handler registered in main.py.

# RATE_LIMIT_EXCEEDED: code requested within the 60-second cooldown window.
# Must return HTTP 429. The existing APIError handler uses exc.status_code,
# so this is a separate exception class with its own handler registered in
# main.py.
class RateLimitError(Exception):
    pass

RATE_LIMIT_EXCEEDED = lambda: RateLimitError(
    "Code requested too recently. Wait 60 seconds before trying again."
)

# ---------------------------------------------------------------------------
# Password authentication errors
# ---------------------------------------------------------------------------

# INVALID_CREDENTIALS: all password-path failures map to this single error.
# Deliberately generic — does not reveal whether the gate that failed was
# "user not found", "wrong password", "account locked", or "no password set".
# Maps to HTTP 422 (consistent with INVALID_AUTH_CODE).
INVALID_CREDENTIALS = lambda: APIError(
    "INVALID_CREDENTIALS",
    "Invalid email or password.",
)

# INVALID_RESET_TOKEN: the supplied reset/setup token is absent, expired,
# or has already been consumed. Maps to HTTP 422.
INVALID_RESET_TOKEN = lambda: APIError(
    "INVALID_RESET_TOKEN",
    "This link has expired or has already been used. Please request a new one.",
)

# WEAK_PASSWORD: the supplied password did not meet the minimum strength
# requirements enforced by zxcvbn. The message is populated with the
# specific feedback string returned by zxcvbn so the user receives
# actionable guidance rather than a generic rejection.
WEAK_PASSWORD = lambda msg="Password is too weak.": APIError(
    "WEAK_PASSWORD",
    msg,
)

# ---------------------------------------------------------------------------
# User management errors (admin portal)
# ---------------------------------------------------------------------------

USER_ALREADY_EXISTS = lambda: APIError(
    "USER_ALREADY_EXISTS",
    "A user with this email already exists.",
    409,
)

ACTION_NOT_PERMITTED = lambda msg="This action is not permitted.": APIError(
    "ACTION_NOT_PERMITTED",
    msg,
    403,
)

USER_NOT_FOUND = lambda: APIError(
    "USER_NOT_FOUND",
    "User not found.",
    404,
)
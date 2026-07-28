from dataclasses import dataclass

# Naming convention: the UPPER_CASE names below are not constants — they are
# factory functions that construct a fresh exception instance on each call.
# Always call them at the raise site, e.g. `raise INVALID_PAYLOAD()` or
# `raise INVALID_PAYLOAD("custom message")`, never `raise INVALID_PAYLOAD`.
# UPPER_CASE is used here to keep call sites read as named, fixed error
# codes rather than ad-hoc constructor calls.


class ConditionNotFound(Exception):
    pass


@dataclass
class APIError(Exception):
    code: str
    message: str
    status_code: int = 422


def INVALID_PAYLOAD(msg="Invalid payload"):
    return APIError("INVALID_PAYLOAD", msg)


def UNKNOWN_RUNTIME_ID():
    return APIError("UNKNOWN_RUNTIME_ID", "Unknown runtime_id")


def VERSION_CONFLICT():
    return APIError("VERSION_CONFLICT", "Version conflict")


def SESSION_CLOSED():
    return APIError("SESSION_CLOSED", "Session already closed")


def PAYLOAD_TOO_LARGE(msg="Request body too large"):
    return APIError("PAYLOAD_TOO_LARGE", msg, status_code=413)


# Admin-specific errors
def INVALID_DATE_FORMAT(field, value):
    return APIError(
        "INVALID_DATE_FORMAT",
        f"Invalid format for '{field}': '{value}'. Expected ISO format.",
    )


def INVALID_FIELD_TYPE(field, expected):
    return APIError(
        "INVALID_FIELD_TYPE",
        f"'{field}' must be {expected}",
    )


# MFA auth errors
#
# INVALID_AUTH_CODE: all verification failures (wrong code, locked out, expired).
# A single generic error is deliberate — it conceals which gate failed.
# Raised as APIError -> HTTP 422 via the existing handler in main.py.
def INVALID_AUTH_CODE():
    return APIError(
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


def RATE_LIMIT_EXCEEDED():
    return RateLimitError("Code requested too recently. Wait 60 seconds before trying again.")


# ---------------------------------------------------------------------------
# Password authentication errors
# ---------------------------------------------------------------------------


# INVALID_CREDENTIALS: all password-path failures map to this single error.
# Deliberately generic — does not reveal whether the gate that failed was
# "user not found", "wrong password", "account locked", or "no password set".
# Maps to HTTP 422 (consistent with INVALID_AUTH_CODE).
def INVALID_CREDENTIALS():
    return APIError(
        "INVALID_CREDENTIALS",
        "Invalid email or password.",
    )


# INVALID_RESET_TOKEN: the supplied reset/setup token is absent, expired,
# or has already been consumed. Maps to HTTP 422.
def INVALID_RESET_TOKEN():
    return APIError(
        "INVALID_RESET_TOKEN",
        "This link has expired or has already been used. Please request a new one.",
    )


# WEAK_PASSWORD: the supplied password did not meet the minimum strength
# requirements enforced by zxcvbn. The message is populated with the
# specific feedback string returned by zxcvbn so the user receives
# actionable guidance rather than a generic rejection.
def WEAK_PASSWORD(msg="Password is too weak."):
    return APIError(
        "WEAK_PASSWORD",
        msg,
    )


# ---------------------------------------------------------------------------
# User management errors (admin portal)
# ---------------------------------------------------------------------------


def USER_ALREADY_EXISTS():
    return APIError(
        "USER_ALREADY_EXISTS",
        "A user with this email already exists.",
        409,
    )


def ACTION_NOT_PERMITTED(msg="This action is not permitted."):
    return APIError(
        "ACTION_NOT_PERMITTED",
        msg,
        403,
    )


def USER_NOT_FOUND():
    return APIError(
        "USER_NOT_FOUND",
        "User not found.",
        404,
    )

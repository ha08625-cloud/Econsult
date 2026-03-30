"""
Admin API router.

All endpoints require a valid Bearer token via require_admin.
Prefix /admin and tag "admin" are applied when registered in main.py.

This module is responsible for:
- Signposting management per condition
- Admin condition list
- Availability configuration
- Manual override management
- Per-date exception management
- Doctor list management

This module must never import:
- Clinical engine modules (form_logic, safety_engine, encoder_mapping, etc.)
- presentation_service
- serialisation, projection, runtime_state
"""

import datetime
import logging
from datetime import timezone

from fastapi import APIRouter, Request, Depends

from app.core.admin_context import AdminContext, require_admin
from app.repositories.practice_repository import (
    InvalidSignpostingData,
    InvalidEmailError,
    InvalidDoctorListError,
    MAX_SIGNPOSTING_LENGTH,
    MAX_DOCTOR_NAME_LENGTH,
    MAX_DOCTOR_LIST_LENGTH,
)
from app.services.availability_service import (
    validate_availability_config,
    validate_override,
    validate_exception,
    deactivation_clears_override,
)
from app.models.availability_models import AvailabilityException, LONDON_TZ
from app.core.condition_registry import ConditionNotFound
from app.core.errors import (
    INVALID_PAYLOAD,
    INVALID_DATE_FORMAT,
    INVALID_FIELD_TYPE,
)
from app.core.dependencies import get_registry, get_practice_repo, get_availability_repo

logger = logging.getLogger(__name__)

router = APIRouter()


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _normalise_signposting(value) -> str | None:
    """
    Normalise signposting for API responses.

    Returns None if value is None or an empty/whitespace-only string.
    Returns the string unchanged otherwise.

    Uses an explicit isinstance check rather than relying on Python
    truthiness so that the intent is clear and a future type change
    does not produce silent incorrect behaviour.
    """
    if not isinstance(value, str) or not value.strip():
        return None
    return value


def _format_availability_response(config: dict) -> dict:
    """
    Format a raw availability config dict for JSON response.

    Converts time objects to HH:MM strings. Converts override_expires_at
    to ISO format string if present.
    """
    config["open_time"] = config["open_time"].strftime("%H:%M")
    config["close_time"] = config["close_time"].strftime("%H:%M")
    if config.get("override_expires_at") is not None:
        config["override_expires_at"] = config["override_expires_at"].isoformat()
    return config


def _format_exception_response(exc: dict) -> dict:
    """
    Format a raw exception dict for JSON response.

    Converts date to ISO string. Converts time objects to HH:MM strings
    if present.
    """
    result = {
        "exception_date": exc["exception_date"].isoformat(),
        "exception_type": exc["exception_type"],
        "open_time": exc["open_time"].strftime("%H:%M") if exc.get("open_time") else None,
        "close_time": exc["close_time"].strftime("%H:%M") if exc.get("close_time") else None,
        "note": exc.get("note"),
    }
    return result


# ---------------------------------------------------------------------------
# Condition list
# ---------------------------------------------------------------------------

@router.get("/conditions")
async def admin_list_conditions(
    _: AdminContext = Depends(require_admin),
    registry=Depends(get_registry),
):
    """
    Return all condition IDs and labels.
    This is a raw administrative view, separate from the patient-facing endpoint.
    """
    return {"conditions": registry.list_conditions()}


# ---------------------------------------------------------------------------
# Practice
# ---------------------------------------------------------------------------

@router.get("/practice")
async def get_practice(
    admin: AdminContext = Depends(require_admin),
    practice_repo=Depends(get_practice_repo),
):
    """
    Return current practice details.

    Returns {"practice_id": ..., "name": ..., "email": ...}.
    created_at is intentionally omitted — it is an internal field
    with no use in the admin UI.
    """
    practice = practice_repo.get_practice(admin.practice_id)
    return {
        "practice_id": practice["practice_id"],
        "name": practice["name"],
        "email": practice["email"],
    }


@router.put("/practice/email")
async def put_practice_email(
    request: Request,
    admin: AdminContext = Depends(require_admin),
    practice_repo=Depends(get_practice_repo),
):
    """
    Update the practice email address.

    Accepts: {"email": "new@address.com"}

    Validation:
    - email must be present and must be a string
    - email must pass repository format validation

    Catches InvalidEmailError and converts to INVALID_PAYLOAD.
    Does not catch PracticeNotFound — the practice is guaranteed to exist
    at startup. If it does not exist here, the deployment is broken and
    the unhandled exception traceback is the correct diagnostic signal.

    Returns {"practice_id": ..., "name": ..., "email": ...} on success.
    """
    try:
        body = await request.json()
    except Exception:
        raise INVALID_PAYLOAD("Invalid JSON body")

    if not isinstance(body, dict) or "email" not in body:
        raise INVALID_PAYLOAD('Body must be {"email": "..."}')

    email = body["email"]

    if not isinstance(email, str):
        raise INVALID_FIELD_TYPE("email", "a string")

    try:
        practice_repo.update_email(admin.practice_id, email)
    except InvalidEmailError as e:
        raise INVALID_PAYLOAD(str(e))

    practice = practice_repo.get_practice(admin.practice_id)
    return {
        "practice_id": practice["practice_id"],
        "name": practice["name"],
        "email": practice["email"],
    }


# ---------------------------------------------------------------------------
# Signposting
# ---------------------------------------------------------------------------

@router.get("/conditions/{condition_id}/signposting")
async def get_signposting(
    condition_id: str,
    admin: AdminContext = Depends(require_admin),
    registry=Depends(get_registry),
    practice_repo=Depends(get_practice_repo),
):
    """
    Return current signposting for a condition.
    Returns {"condition_id": ..., "signposting": <html string or null>}.
    """
    if not registry.has_condition(condition_id):
        raise ConditionNotFound(condition_id)

    html = practice_repo.get_signposting(admin.practice_id, condition_id)

    return {
        "condition_id": condition_id,
        "signposting": _normalise_signposting(html),
    }


@router.put("/conditions/{condition_id}/signposting")
async def put_signposting(
    condition_id: str,
    request: Request,
    admin: AdminContext = Depends(require_admin),
    registry=Depends(get_registry),
    practice_repo=Depends(get_practice_repo),
):
    """
    Set or clear signposting for a condition.

    Accepts: {"signposting": "<p>html string</p>"}

    The signposting value is always a string. Empty or whitespace-only
    content is treated as an instruction to clear signposting — the
    repository will delete any existing row rather than write empty content.

    Validation (in order):
    1. Body must be valid JSON
    2. signposting key must be present and must be a string
    3. Length must not exceed MAX_SIGNPOSTING_LENGTH characters

    The router catches InvalidSignpostingData from the repository and
    converts it to an INVALID_PAYLOAD error. This should only arise from
    the length check (the sanitiser raises it before nh3 runs). It never
    produces a 500 from sanitisation failures.

    Returns {"condition_id": ..., "signposting": <sanitised html or null>}.
    A null response means the content was empty after sanitisation and no
    row was written.
    """
    if not registry.has_condition(condition_id):
        raise ConditionNotFound(condition_id)

    try:
        body = await request.json()
    except Exception:
        raise INVALID_PAYLOAD("Invalid JSON body")

    if not isinstance(body, dict) or "signposting" not in body:
        raise INVALID_PAYLOAD('Body must be {"signposting": "..."}')

    raw = body["signposting"]

    if not isinstance(raw, str):
        raise INVALID_FIELD_TYPE("signposting", "a string")

    if len(raw) > MAX_SIGNPOSTING_LENGTH:
        raise INVALID_PAYLOAD(f"Signposting must not exceed {MAX_SIGNPOSTING_LENGTH} characters")

    try:
        practice_repo.set_signposting(admin.practice_id, condition_id, raw)
    except InvalidSignpostingData as e:
        raise INVALID_PAYLOAD(str(e))

    saved = practice_repo.get_signposting(admin.practice_id, condition_id)

    return {
        "condition_id": condition_id,
        "signposting": _normalise_signposting(saved),
    }


@router.delete("/conditions/{condition_id}/signposting", status_code=204)
async def delete_signposting(
    condition_id: str,
    admin: AdminContext = Depends(require_admin),
    registry=Depends(get_registry),
    practice_repo=Depends(get_practice_repo),
):
    """
    Remove all signposting for a condition.
    Idempotent: no error if nothing was configured.
    Returns 204 No Content.
    """
    if not registry.has_condition(condition_id):
        raise ConditionNotFound(condition_id)

    practice_repo.delete_signposting(admin.practice_id, condition_id)


# ---------------------------------------------------------------------------
# Doctor list
# ---------------------------------------------------------------------------

@router.get("/doctors")
async def get_doctors(
    admin: AdminContext = Depends(require_admin),
    practice_repo=Depends(get_practice_repo),
):
    """
    Return the doctor list for the practice.

    Returns {"doctors": ["Dr Smith", "Dr Jones", ...]} in display order.
    Returns {"doctors": []} if no doctors are configured.
    """
    doctors = practice_repo.get_doctors(admin.practice_id)
    return {"doctors": doctors}


@router.put("/doctors")
async def put_doctors(
    request: Request,
    admin: AdminContext = Depends(require_admin),
    practice_repo=Depends(get_practice_repo),
):
    """
    Replace the doctor list for the practice.

    Accepts: {"doctors": ["Dr Smith", "Dr Jones", ...]}

    An empty list is valid — it clears the doctor list entirely.

    Validation:
    - doctors key must be present and must be a list
    - each item must be a non-empty string
    - each item must not exceed MAX_DOCTOR_NAME_LENGTH characters
    - list must not exceed MAX_DOCTOR_LIST_LENGTH items

    Catches InvalidDoctorListError and converts to INVALID_PAYLOAD.
    Does not catch PracticeNotFound — the practice is guaranteed to exist
    at startup.

    Returns {"doctors": [...]} reflecting the saved list.
    """
    try:
        body = await request.json()
    except Exception:
        raise INVALID_PAYLOAD("Invalid JSON body")

    if not isinstance(body, dict) or "doctors" not in body:
        raise INVALID_PAYLOAD('Body must be {"doctors": [...]}')

    doctors = body["doctors"]

    if not isinstance(doctors, list):
        raise INVALID_FIELD_TYPE("doctors", "a list")

    try:
        practice_repo.set_doctors(admin.practice_id, doctors)
    except InvalidDoctorListError as e:
        raise INVALID_PAYLOAD(str(e))

    saved = practice_repo.get_doctors(admin.practice_id)
    return {"doctors": saved}


# ---------------------------------------------------------------------------
# Availability
# ---------------------------------------------------------------------------

@router.get("/availability")
async def get_availability(
    admin: AdminContext = Depends(require_admin),
    availability_repo=Depends(get_availability_repo),
):
    """
    Return the raw availability configuration for the practice.

    Returns all columns from practice_availability as a dict.
    Does not call evaluate_availability — this is the admin view of the
    stored config, not the evaluated patient-facing result.
    """
    config = availability_repo.get_availability(admin.practice_id)
    return _format_availability_response(config)


@router.put("/availability")
async def put_availability(
    request: Request,
    admin: AdminContext = Depends(require_admin),
    availability_repo=Depends(get_availability_repo),
):
    """
    Update the availability configuration.

    Accepts:
    {
        "is_active": true,
        "weekly_open_days": ["mon", "tue", "wed", "thu", "fri"],
        "open_time": "08:00",
        "close_time": "18:30",
        "closed_message": "The practice is now closed."
    }

    Validation:
    - All fields are required except closed_message (nullable).
    - weekly_open_days must contain only valid day abbreviations.
    - open_time and close_time must not be equal.

    If is_active is set to false, any existing override is auto-cleared.
    Logs a warning if is_active is true and weekly_open_days is empty.
    Returns the updated config by fetching it back from the repository.
    Returns an error with a descriptive message if validation fails.
    """
    try:
        body = await request.json()
    except Exception:
        raise INVALID_PAYLOAD("Invalid JSON body")

    if not isinstance(body, dict):
        raise INVALID_PAYLOAD("Body must be a JSON object")

    # --- Extract and type-check fields ---

    is_active = body.get("is_active")
    if not isinstance(is_active, bool):
        raise INVALID_FIELD_TYPE("is_active", "a boolean")

    weekly_open_days = body.get("weekly_open_days")
    if not isinstance(weekly_open_days, list):
        raise INVALID_FIELD_TYPE("weekly_open_days", "a list")
    if not all(isinstance(d, str) for d in weekly_open_days):
        raise INVALID_FIELD_TYPE("weekly_open_days", "a list of strings")

    open_time_str = body.get("open_time")
    close_time_str = body.get("close_time")
    if not isinstance(open_time_str, str) or not isinstance(close_time_str, str):
        raise INVALID_FIELD_TYPE("open_time and close_time", "strings in HH:MM format")

    try:
        open_time = datetime.time.fromisoformat(open_time_str)
    except ValueError:
        raise INVALID_DATE_FORMAT("open_time", open_time_str)

    try:
        close_time = datetime.time.fromisoformat(close_time_str)
    except ValueError:
        raise INVALID_DATE_FORMAT("close_time", close_time_str)

    closed_message = body.get("closed_message")
    if closed_message is not None and not isinstance(closed_message, str):
        raise INVALID_FIELD_TYPE("closed_message", "a string or null")

    # --- Validate via service layer ---

    try:
        validate_availability_config(
            weekly_open_days=weekly_open_days,
            open_time=open_time,
            close_time=close_time,
            closed_message=closed_message,
        )
    except ValueError as e:
        raise INVALID_PAYLOAD(str(e))

    # --- Persist ---

    availability_repo.set_availability(
        practice_id=admin.practice_id,
        is_active=is_active,
        weekly_open_days=weekly_open_days,
        open_time=open_time,
        close_time=close_time,
        closed_message=closed_message,
    )

    # --- Auto-clear override on deactivation ---

    if deactivation_clears_override(is_active):
        availability_repo.clear_override(admin.practice_id)

    # --- Log warning for empty-days misconfiguration ---

    if is_active and not weekly_open_days:
        logger.warning(
            "Practice '%s': is_active=true with no weekly_open_days. "
            "The form will be closed to patients every day.",
            admin.practice_id,
        )

    # --- Return updated config ---

    updated = availability_repo.get_availability(admin.practice_id)
    return _format_availability_response(updated)


# ---------------------------------------------------------------------------
# Override
# ---------------------------------------------------------------------------

@router.post("/availability/override")
async def post_override(
    request: Request,
    admin: AdminContext = Depends(require_admin),
    availability_repo=Depends(get_availability_repo),
):
    """
    Set a manual override (force-open or force-closed).

    Accepts:
    {
        "status": "open" | "closed",
        "expires_at": "2025-06-02T18:30:00Z",
        "message": "Optional message for patients" | null
    }

    expires_at must be a timezone-aware ISO datetime string.
    The backend rejects timezone-naive datetimes.
    The valid window is: now < expires_at <= now + 24 hours.

    Returns the updated raw config.
    """
    try:
        body = await request.json()
    except Exception:
        raise INVALID_PAYLOAD("Invalid JSON body")

    if not isinstance(body, dict):
        raise INVALID_PAYLOAD("Body must be a JSON object")

    # --- Extract and type-check fields ---

    status = body.get("status")
    if not isinstance(status, str):
        raise INVALID_FIELD_TYPE("status", "a string ('open' or 'closed')")

    expires_at_str = body.get("expires_at")
    if not isinstance(expires_at_str, str):
        raise INVALID_FIELD_TYPE("expires_at", "an ISO datetime string")

    try:
        expires_at = datetime.datetime.fromisoformat(expires_at_str)
    except ValueError:
        raise INVALID_DATE_FORMAT("expires_at", expires_at_str)

    # Reject timezone-naive datetimes. During BST, a London-local time
    # submitted without an offset would be stored as if it were UTC,
    # causing the override to expire one hour late.
    if expires_at.tzinfo is None:
        raise INVALID_PAYLOAD(
            "expires_at must include a timezone offset (e.g. 'Z' or '+01:00'). "
            "Timezone-naive datetimes are rejected to prevent BST/UTC confusion."
        )

    message = body.get("message")
    if message is not None and not isinstance(message, str):
        raise INVALID_FIELD_TYPE("message", "a string or null")

    # --- Validate via service layer ---

    now_utc = datetime.datetime.now(timezone.utc)
    try:
        validate_override(
            status=status,
            expires_at=expires_at,
            now_utc=now_utc,
        )
    except ValueError as e:
        raise INVALID_PAYLOAD(str(e))

    # --- Persist ---

    availability_repo.set_override(
        practice_id=admin.practice_id,
        override_status=status,
        override_expires_at=expires_at,
        override_message=message,
    )

    # --- Return updated config ---

    updated = availability_repo.get_availability(admin.practice_id)
    return _format_availability_response(updated)


@router.delete("/availability/override")
async def delete_override(
    admin: AdminContext = Depends(require_admin),
    availability_repo=Depends(get_availability_repo),
):
    """
    Clear any active override.

    Idempotent — no error if no override was active.
    Returns the updated raw config.
    """
    availability_repo.clear_override(admin.practice_id)

    updated = availability_repo.get_availability(admin.practice_id)
    return _format_availability_response(updated)


# ---------------------------------------------------------------------------
# Per-date exceptions (Stage 4)
# ---------------------------------------------------------------------------

@router.get("/availability/exceptions")
async def list_exceptions(
    admin: AdminContext = Depends(require_admin),
    availability_repo=Depends(get_availability_repo),
):
    """
    Return all exceptions on or after today (Europe/London time).

    Includes today's exception if one exists — the admin needs to verify
    what is currently active. Ordered by date ascending.
    """
    today_london = datetime.datetime.now(timezone.utc).astimezone(LONDON_TZ).date()
    rows = availability_repo.get_exceptions(admin.practice_id, today_london)
    return {
        "exceptions": [_format_exception_response(r) for r in rows],
    }


@router.put("/availability/exceptions/{date}")
async def put_exception(
    date: str,
    request: Request,
    admin: AdminContext = Depends(require_admin),
    availability_repo=Depends(get_availability_repo),
):
    """
    Create or update an exception for a specific date.

    Accepts:
    {
        "exception_type": "closed" | "custom_hours",
        "open_time": "09:00" | null,
        "close_time": "13:00" | null,
        "note": "Staff training day" | null
    }

    For "closed" exceptions, open_time and close_time must be null.
    For "custom_hours" exceptions, both open_time and close_time are required.

    Returns the exception as stored.
    """
    # --- Parse date from URL path ---
    try:
        exception_date = datetime.date.fromisoformat(date)
    except ValueError:
        raise INVALID_DATE_FORMAT("date", date)

    # --- Parse body ---
    try:
        body = await request.json()
    except Exception:
        raise INVALID_PAYLOAD("Invalid JSON body")

    if not isinstance(body, dict):
        raise INVALID_PAYLOAD("Body must be a JSON object")

    # --- Extract and type-check fields ---

    exception_type = body.get("exception_type")
    if not isinstance(exception_type, str):
        raise INVALID_FIELD_TYPE("exception_type", "a string ('closed' or 'custom_hours')")

    open_time_str = body.get("open_time")
    close_time_str = body.get("close_time")

    open_time = None
    close_time = None

    if open_time_str is not None:
        if not isinstance(open_time_str, str):
            raise INVALID_FIELD_TYPE("open_time", "a string in HH:MM format or null")
        try:
            open_time = datetime.time.fromisoformat(open_time_str)
        except ValueError:
            raise INVALID_DATE_FORMAT("open_time", open_time_str)

    if close_time_str is not None:
        if not isinstance(close_time_str, str):
            raise INVALID_FIELD_TYPE("close_time", "a string in HH:MM format or null")
        try:
            close_time = datetime.time.fromisoformat(close_time_str)
        except ValueError:
            raise INVALID_DATE_FORMAT("close_time", close_time_str)

    note = body.get("note")
    if note is not None and not isinstance(note, str):
        raise INVALID_FIELD_TYPE("note", "a string or null")

    # --- Validate via service layer ---

    try:
        validate_exception(
            exception_type=exception_type,
            open_time=open_time,
            close_time=close_time,
        )
    except ValueError as e:
        raise INVALID_PAYLOAD(str(e))

    # --- Persist ---

    availability_repo.set_exception(
        practice_id=admin.practice_id,
        exception_date=exception_date,
        exception_type=exception_type,
        open_time=open_time,
        close_time=close_time,
        note=note,
    )

    # --- Return the stored exception ---

    return _format_exception_response({
        "exception_date": exception_date,
        "exception_type": exception_type,
        "open_time": open_time,
        "close_time": close_time,
        "note": note,
    })


@router.delete("/availability/exceptions/{date}", status_code=204)
async def delete_exception(
    date: str,
    admin: AdminContext = Depends(require_admin),
    availability_repo=Depends(get_availability_repo),
):
    """
    Delete an exception for a specific date.

    Idempotent — no error if no exception existed for this date.
    Returns 204 No Content.
    """
    try:
        exception_date = datetime.date.fromisoformat(date)
    except ValueError:
        raise INVALID_DATE_FORMAT("date", date)

    availability_repo.delete_exception(admin.practice_id, exception_date)
"""
Admin Availability API router.

Handles weekly opening hours, manual overrides, and per-date exceptions.

All endpoints require a valid session cookie via require_admin.

This module must never import:
- Clinical engine modules (form_logic, safety_engine, encoder_mapping, etc.)
- presentation_service
- serialisation, projection, runtime_state

# ---------------------------------------------------------------------------
# Transaction pattern for mutating endpoints
# ---------------------------------------------------------------------------
#
# Each mutating endpoint wraps both the repository mutation and the
# audit_repo.log_event call in a single database transaction via get_conn.
# If either operation fails, both roll back.
#
# The pattern is:
#   1. Read "before" state outside the transaction (clean read, no lock held).
#   2. Open a shared connection with get_conn.
#   3. Call the repository mutating method with conn=conn.
#   4. Call audit_repo.log_event(conn=conn, ...).
#   5. The get_conn context manager commits on exit.
#
# The caller owns the transaction boundary. Repository methods do not commit
# when conn is supplied — they execute on the cursor and return, leaving
# commit/rollback to the caller.
#
# On any exception inside the with block, psycopg2's context manager rolls
# back, and the endpoint returns HTTP 500.
"""

import datetime
import logging

from fastapi import APIRouter, Depends, HTTPException, Request

from app.core.admin_context import AdminContext, require_admin
from app.core.db import get_conn
from app.core.dependencies import (
    get_audit_repo,
    get_availability_repo,
)
from app.core.errors import (
    INVALID_DATE_FORMAT,
    INVALID_FIELD_TYPE,
    INVALID_PAYLOAD,
)
from app.models.availability_models import LONDON_TZ
from app.services.admin.availability_service import (
    deactivation_clears_override,
    validate_availability_config,
    validate_exception,
    validate_override,
)
from app.utils.http_utils import extract_ip

logger = logging.getLogger(__name__)

router = APIRouter()

# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


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


def _serialise_availability_for_audit(config: dict) -> dict:
    """
    Convert a raw availability config dict to a JSON-serialisable form
    for use in audit log detail fields.

    time objects become HH:MM strings. Datetimes become ISO strings.
    None values are preserved as-is.
    """
    return {
        "is_active": config.get("is_active"),
        "weekly_open_days": config.get("weekly_open_days"),
        "open_time": config["open_time"].strftime("%H:%M") if config.get("open_time") else None,
        "close_time": config["close_time"].strftime("%H:%M") if config.get("close_time") else None,
        "closed_message": config.get("closed_message"),
        "override_status": config.get("override_status"),
        "override_expires_at": config["override_expires_at"].isoformat()
        if config.get("override_expires_at")
        else None,
        "override_message": config.get("override_message"),
    }


def _serialise_exception_for_audit(exc: dict) -> dict:
    """
    Convert a raw exception dict to a JSON-serialisable form for audit
    log detail fields.

    date becomes ISO string. time objects become HH:MM strings.
    None values are preserved as-is.
    """
    return {
        "exception_date": exc["exception_date"].isoformat() if exc.get("exception_date") else None,
        "exception_type": exc.get("exception_type"),
        "open_time": exc["open_time"].strftime("%H:%M") if exc.get("open_time") else None,
        "close_time": exc["close_time"].strftime("%H:%M") if exc.get("close_time") else None,
        "note": exc.get("note"),
    }


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
    audit_repo=Depends(get_audit_repo),
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

    If is_active is set to false, any existing override is auto-cleared
    within the same transaction.
    Logs a warning if is_active is true and weekly_open_days is empty.
    Returns the updated config by fetching it back from the repository.
    Returns an error with a descriptive message if validation fails.

    Audit: availability.config.updated with before/after detail.
    The mutation, optional override clear, and audit log write are all
    atomic in a single transaction.
    """
    try:
        body = await request.json()
    except Exception as e:
        raise INVALID_PAYLOAD("Invalid JSON body") from e

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
    except ValueError as e:
        raise INVALID_DATE_FORMAT("open_time", open_time_str) from e

    try:
        close_time = datetime.time.fromisoformat(close_time_str)
    except ValueError as e:
        raise INVALID_DATE_FORMAT("close_time", close_time_str) from e

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
        raise INVALID_PAYLOAD(str(e)) from e

    # --- Read "before" state outside the transaction ---

    before_config = availability_repo.get_availability(admin.practice_id)

    ip_address = extract_ip(
        request.headers,
        request.client.host if request.client else None,
    )

    # --- Persist (mutation + optional override clear + audit log, all atomic) ---

    try:
        with get_conn(availability_repo.database_url) as conn:
            availability_repo.set_availability(
                practice_id=admin.practice_id,
                is_active=is_active,
                weekly_open_days=weekly_open_days,
                open_time=open_time,
                close_time=close_time,
                closed_message=closed_message,
                conn=conn,
            )

            if deactivation_clears_override(is_active):
                availability_repo.clear_override(admin.practice_id, conn=conn)

            # Build "after" from the validated input values — we cannot
            # read back from the DB inside this transaction because
            # get_availability opens its own connection and will not see
            # uncommitted rows. Using the known inputs is accurate and avoids
            # a second connection.
            after_for_audit = {
                "is_active": is_active,
                "weekly_open_days": weekly_open_days,
                "open_time": open_time,
                "close_time": close_time,
                "closed_message": closed_message,
                # Override fields: preserve from before_config since
                # set_availability does not touch them. If is_active is
                # False, clear_override has nulled them within this
                # transaction, so reflect that explicitly.
                "override_status": None
                if deactivation_clears_override(is_active)
                else before_config.get("override_status"),
                "override_expires_at": None
                if deactivation_clears_override(is_active)
                else before_config.get("override_expires_at"),
                "override_message": None
                if deactivation_clears_override(is_active)
                else before_config.get("override_message"),
            }

            audit_repo.log_event(
                practice_id=admin.practice_id,
                actor_email=admin.actor_email,
                action="availability.config.updated",
                ip_address=ip_address,
                session_id=admin.session_id,
                detail={
                    "before": _serialise_availability_for_audit(before_config),
                    "after": _serialise_availability_for_audit(after_for_audit),
                },
                conn=conn,
            )
    except Exception as e:
        logger.exception("Transaction failed for availability.config.updated")
        raise HTTPException(
            status_code=500,
            detail="Failed to update availability configuration. Please try again.",
        ) from e

    # --- Log warning for empty-days misconfiguration ---

    if is_active and not weekly_open_days:
        logger.warning(
            "Practice '%s': is_active=true with no weekly_open_days. "
            "The form will be closed to patients every day.",
            admin.practice_id,
        )

    # --- Return updated config (read after commit) ---

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
    audit_repo=Depends(get_audit_repo),
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

    Audit: availability.override.updated with before/after detail.
    The mutation and audit log write are atomic in a single transaction.
    """
    try:
        body = await request.json()
    except Exception as e:
        raise INVALID_PAYLOAD("Invalid JSON body") from e

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
    except ValueError as e:
        raise INVALID_DATE_FORMAT("expires_at", expires_at_str) from e

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

    now_utc = datetime.datetime.now(datetime.UTC)
    try:
        validate_override(
            status=status,
            expires_at=expires_at,
            now_utc=now_utc,
        )
    except ValueError as e:
        raise INVALID_PAYLOAD(str(e)) from e

    # --- Read "before" state outside the transaction ---

    before_config = availability_repo.get_availability(admin.practice_id)

    ip_address = extract_ip(
        request.headers,
        request.client.host if request.client else None,
    )

    # --- Persist ---

    try:
        with get_conn(availability_repo.database_url) as conn:
            availability_repo.set_override(
                practice_id=admin.practice_id,
                override_status=status,
                override_expires_at=expires_at,
                override_message=message,
                conn=conn,
            )

            audit_repo.log_event(
                practice_id=admin.practice_id,
                actor_email=admin.actor_email,
                action="availability.override.updated",
                ip_address=ip_address,
                session_id=admin.session_id,
                detail={
                    "before": {
                        "override_status": before_config.get("override_status"),
                        "override_expires_at": before_config["override_expires_at"].isoformat()
                        if before_config.get("override_expires_at")
                        else None,
                        "override_message": before_config.get("override_message"),
                    },
                    "after": {
                        "override_status": status,
                        "override_expires_at": expires_at.isoformat(),
                        "override_message": message,
                    },
                },
                conn=conn,
            )
    except Exception as e:
        logger.exception("Transaction failed for availability.override.updated")
        raise HTTPException(
            status_code=500,
            detail="Failed to set availability override. Please try again.",
        ) from e

    # --- Return updated config (read after commit) ---

    updated = availability_repo.get_availability(admin.practice_id)
    return _format_availability_response(updated)


@router.delete("/availability/override")
async def delete_override(
    request: Request,
    admin: AdminContext = Depends(require_admin),
    availability_repo=Depends(get_availability_repo),
    audit_repo=Depends(get_audit_repo),
):
    """
    Clear any active override.

    Idempotent — no error if no override was active.
    Returns the updated raw config.

    Audit: availability.override.deleted with before detail.
    The mutation and audit log write are atomic in a single transaction.
    """
    # Read "before" state outside the transaction.
    before_config = availability_repo.get_availability(admin.practice_id)

    ip_address = extract_ip(
        request.headers,
        request.client.host if request.client else None,
    )

    try:
        with get_conn(availability_repo.database_url) as conn:
            availability_repo.clear_override(admin.practice_id, conn=conn)
            audit_repo.log_event(
                practice_id=admin.practice_id,
                actor_email=admin.actor_email,
                action="availability.override.deleted",
                ip_address=ip_address,
                session_id=admin.session_id,
                detail={
                    "before": {
                        "override_status": before_config.get("override_status"),
                        "override_expires_at": before_config["override_expires_at"].isoformat()
                        if before_config.get("override_expires_at")
                        else None,
                        "override_message": before_config.get("override_message"),
                    },
                },
                conn=conn,
            )
    except Exception as e:
        logger.exception("Transaction failed for availability.override.deleted")
        raise HTTPException(
            status_code=500,
            detail="Failed to clear availability override. Please try again.",
        ) from e

    updated = availability_repo.get_availability(admin.practice_id)
    return _format_availability_response(updated)


# ---------------------------------------------------------------------------
# Per-date exceptions
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
    today_london = datetime.datetime.now(datetime.UTC).astimezone(LONDON_TZ).date()
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
    audit_repo=Depends(get_audit_repo),
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

    Audit: availability.exception.created if no row existed for this date,
    or availability.exception.updated if one did. Both include before/after
    detail (before is absent for created). The mutation and audit log write
    are atomic in a single transaction.
    """
    # --- Parse date from URL path ---
    try:
        exception_date = datetime.date.fromisoformat(date)
    except ValueError as e:
        raise INVALID_DATE_FORMAT("date", date) from e

    # --- Parse body ---
    try:
        body = await request.json()
    except Exception as e:
        raise INVALID_PAYLOAD("Invalid JSON body") from e

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
        except ValueError as e:
            raise INVALID_DATE_FORMAT("open_time", open_time_str) from e

    if close_time_str is not None:
        if not isinstance(close_time_str, str):
            raise INVALID_FIELD_TYPE("close_time", "a string in HH:MM format or null")
        try:
            close_time = datetime.time.fromisoformat(close_time_str)
        except ValueError as e:
            raise INVALID_DATE_FORMAT("close_time", close_time_str) from e

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
        raise INVALID_PAYLOAD(str(e)) from e

    # --- Read "before" state outside the transaction ---

    before_exc = availability_repo.get_exception(admin.practice_id, exception_date)
    is_create = before_exc is None
    action = "availability.exception.created" if is_create else "availability.exception.updated"

    ip_address = extract_ip(
        request.headers,
        request.client.host if request.client else None,
    )

    after_exc = {
        "exception_date": exception_date,
        "exception_type": exception_type,
        "open_time": open_time,
        "close_time": close_time,
        "note": note,
    }

    # Build detail outside the transaction — no DB reads needed.
    if is_create:
        audit_detail = {"after": _serialise_exception_for_audit(after_exc)}
    else:
        audit_detail = {
            "before": _serialise_exception_for_audit(before_exc),
            "after": _serialise_exception_for_audit(after_exc),
        }

    # --- Persist ---

    try:
        with get_conn(availability_repo.database_url) as conn:
            availability_repo.set_exception(
                practice_id=admin.practice_id,
                exception_date=exception_date,
                exception_type=exception_type,
                open_time=open_time,
                close_time=close_time,
                note=note,
                conn=conn,
            )
            audit_repo.log_event(
                practice_id=admin.practice_id,
                actor_email=admin.actor_email,
                action=action,
                resource=exception_date.isoformat(),
                ip_address=ip_address,
                session_id=admin.session_id,
                detail=audit_detail,
                conn=conn,
            )
    except Exception as e:
        logger.exception("Transaction failed for %s", action)
        raise HTTPException(
            status_code=500,
            detail="Failed to save availability exception. Please try again.",
        ) from e

    # --- Return the stored exception ---

    return _format_exception_response(after_exc)


@router.delete("/availability/exceptions/{date}", status_code=204)
async def delete_exception(
    date: str,
    request: Request,
    admin: AdminContext = Depends(require_admin),
    availability_repo=Depends(get_availability_repo),
    audit_repo=Depends(get_audit_repo),
):
    """
    Delete an exception for a specific date.

    Idempotent — no error if no exception existed for this date.
    Returns 204 No Content.

    Audit: availability.exception.deleted with before detail.
    If no row existed, the audit event is still written — the admin's
    intent is recorded regardless. The mutation and audit log write are
    atomic in a single transaction.
    """
    try:
        exception_date = datetime.date.fromisoformat(date)
    except ValueError as e:
        raise INVALID_DATE_FORMAT("date", date) from e

    # Read "before" state outside the transaction.
    before_exc = availability_repo.get_exception(admin.practice_id, exception_date)

    ip_address = extract_ip(
        request.headers,
        request.client.host if request.client else None,
    )

    try:
        with get_conn(availability_repo.database_url) as conn:
            availability_repo.delete_exception(admin.practice_id, exception_date, conn=conn)
            audit_repo.log_event(
                practice_id=admin.practice_id,
                actor_email=admin.actor_email,
                action="availability.exception.deleted",
                resource=exception_date.isoformat(),
                ip_address=ip_address,
                session_id=admin.session_id,
                detail={
                    "before": _serialise_exception_for_audit(before_exc) if before_exc else None
                },
                conn=conn,
            )
    except Exception as e:
        logger.exception("Transaction failed for availability.exception.deleted")
        raise HTTPException(
            status_code=500,
            detail="Failed to delete availability exception. Please try again.",
        ) from e
        
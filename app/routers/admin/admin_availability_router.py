"""
Admin Availability API router.
Handles weekly hours, manual overrides, and per-date exceptions.
"""
import datetime
import logging
from datetime import timezone

from fastapi import APIRouter, Request, Depends, HTTPException

from app.core.admin_context import AdminContext, require_admin
from app.services.availability_service import (
    validate_availability_config,
    validate_override,
    validate_exception,
    deactivation_clears_override,
)
from app.models.availability_models import LONDON_TZ
from app.core.errors import (
    INVALID_PAYLOAD,
    INVALID_DATE_FORMAT,
    INVALID_FIELD_TYPE,
)
from app.core.dependencies import (
    get_availability_repo,
    get_audit_repo,
)
from app.core.db import get_conn
from app.utils.http_utils import extract_ip

logger = logging.getLogger(__name__)

router = APIRouter()

# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _format_availability_response(config: dict) -> dict:
    config["open_time"] = config["open_time"].strftime("%H:%M")
    config["close_time"] = config["close_time"].strftime("%H:%M")
    if config.get("override_expires_at") is not None:
        config["override_expires_at"] = config["override_expires_at"].isoformat()
    return config

def _format_exception_response(exc: dict) -> dict:
    result = {
        "exception_date": exc["exception_date"].isoformat(),
        "exception_type": exc["exception_type"],
        "open_time": exc["open_time"].strftime("%H:%M") if exc.get("open_time") else None,
        "close_time": exc["close_time"].strftime("%H:%M") if exc.get("close_time") else None,
        "note": exc.get("note"),
    }
    return result

def _serialise_availability_for_audit(config: dict) -> dict:
    return {
        "is_active": config.get("is_active"),
        "weekly_open_days": config.get("weekly_open_days"),
        "open_time": config["open_time"].strftime("%H:%M") if config.get("open_time") else None,
        "close_time": config["close_time"].strftime("%H:%M") if config.get("close_time") else None,
        "closed_message": config.get("closed_message"),
        "override_status": config.get("override_status"),
        "override_expires_at": config["override_expires_at"].isoformat() if config.get("override_expires_at") else None,
        "override_message": config.get("override_message"),
    }

def _serialise_exception_for_audit(exc: dict) -> dict:
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
    config = availability_repo.get_availability(admin.practice_id)
    return _format_availability_response(config)

@router.put("/availability")
async def put_availability(
    request: Request,
    admin: AdminContext = Depends(require_admin),
    availability_repo=Depends(get_availability_repo),
    audit_repo=Depends(get_audit_repo),
):
    try:
        body = await request.json()
    except Exception:
        raise INVALID_PAYLOAD("Invalid JSON body")

    if not isinstance(body, dict):
        raise INVALID_PAYLOAD("Body must be a JSON object")

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

    try:
        validate_availability_config(
            weekly_open_days=weekly_open_days,
            open_time=open_time,
            close_time=close_time,
            closed_message=closed_message,
        )
    except ValueError as e:
        raise INVALID_PAYLOAD(str(e))

    before_config = availability_repo.get_availability(admin.practice_id)
    ip_address = extract_ip(request.headers, request.client.host if request.client else None)

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

            after_for_audit = {
                "is_active": is_active,
                "weekly_open_days": weekly_open_days,
                "open_time": open_time,
                "close_time": close_time,
                "closed_message": closed_message,
                "override_status": None if deactivation_clears_override(is_active) else before_config.get("override_status"),
                "override_expires_at": None if deactivation_clears_override(is_active) else before_config.get("override_expires_at"),
                "override_message": None if deactivation_clears_override(is_active) else before_config.get("override_message"),
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
    except Exception:
        logger.exception("Transaction failed for availability.config.updated")
        raise HTTPException(
            status_code=500,
            detail="Failed to update availability configuration. Please try again.",
        )

    if is_active and not weekly_open_days:
        logger.warning(
            "Practice '%s': is_active=true with no weekly_open_days. "
            "The form will be closed to patients every day.",
            admin.practice_id,
        )

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
    try:
        body = await request.json()
    except Exception:
        raise INVALID_PAYLOAD("Invalid JSON body")

    if not isinstance(body, dict):
        raise INVALID_PAYLOAD("Body must be a JSON object")

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

    if expires_at.tzinfo is None:
        raise INVALID_PAYLOAD(
            "expires_at must include a timezone offset (e.g. 'Z' or '+01:00'). "
            "Timezone-naive datetimes are rejected to prevent BST/UTC confusion."
        )

    message = body.get("message")
    if message is not None and not isinstance(message, str):
        raise INVALID_FIELD_TYPE("message", "a string or null")

    now_utc = datetime.datetime.now(timezone.utc)
    try:
        validate_override(
            status=status,
            expires_at=expires_at,
            now_utc=now_utc,
        )
    except ValueError as e:
        raise INVALID_PAYLOAD(str(e))

    before_config = availability_repo.get_availability(admin.practice_id)
    ip_address = extract_ip(request.headers, request.client.host if request.client else None)

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
                        "override_expires_at": before_config["override_expires_at"].isoformat() if before_config.get("override_expires_at") else None,
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
    except Exception:
        logger.exception("Transaction failed for availability.override.updated")
        raise HTTPException(
            status_code=500,
            detail="Failed to set availability override. Please try again.",
        )

    updated = availability_repo.get_availability(admin.practice_id)
    return _format_availability_response(updated)


@router.delete("/availability/override")
async def delete_override(
    request: Request,
    admin: AdminContext = Depends(require_admin),
    availability_repo=Depends(get_availability_repo),
    audit_repo=Depends(get_audit_repo),
):
    before_config = availability_repo.get_availability(admin.practice_id)
    ip_address = extract_ip(request.headers, request.client.host if request.client else None)

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
                        "override_expires_at": before_config["override_expires_at"].isoformat() if before_config.get("override_expires_at") else None,
                        "override_message": before_config.get("override_message"),
                    },
                },
                conn=conn,
            )
    except Exception:
        logger.exception("Transaction failed for availability.override.deleted")
        raise HTTPException(
            status_code=500,
            detail="Failed to clear availability override. Please try again.",
        )

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
    audit_repo=Depends(get_audit_repo),
):
    try:
        exception_date = datetime.date.fromisoformat(date)
    except ValueError:
        raise INVALID_DATE_FORMAT("date", date)

    try:
        body = await request.json()
    except Exception:
        raise INVALID_PAYLOAD("Invalid JSON body")

    if not isinstance(body, dict):
        raise INVALID_PAYLOAD("Body must be a JSON object")

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

    try:
        validate_exception(
            exception_type=exception_type,
            open_time=open_time,
            close_time=close_time,
        )
    except ValueError as e:
        raise INVALID_PAYLOAD(str(e))

    before_exc = availability_repo.get_exception(admin.practice_id, exception_date)
    is_create = before_exc is None
    action = "availability.exception.created" if is_create else "availability.exception.updated"

    ip_address = extract_ip(request.headers, request.client.host if request.client else None)

    after_exc = {
        "exception_date": exception_date,
        "exception_type": exception_type,
        "open_time": open_time,
        "close_time": close_time,
        "note": note,
    }

    if is_create:
        audit_detail = {"after": _serialise_exception_for_audit(after_exc)}
    else:
        audit_detail = {
            "before": _serialise_exception_for_audit(before_exc),
            "after": _serialise_exception_for_audit(after_exc),
        }

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
    except Exception:
        logger.exception("Transaction failed for %s", action)
        raise HTTPException(
            status_code=500,
            detail="Failed to save availability exception. Please try again.",
        )

    return _format_exception_response(after_exc)


@router.delete("/availability/exceptions/{date}", status_code=204)
async def delete_exception(
    date: str,
    request: Request,
    admin: AdminContext = Depends(require_admin),
    availability_repo=Depends(get_availability_repo),
    audit_repo=Depends(get_audit_repo),
):
    try:
        exception_date = datetime.date.fromisoformat(date)
    except ValueError:
        raise INVALID_DATE_FORMAT("date", date)

    before_exc = availability_repo.get_exception(admin.practice_id, exception_date)
    ip_address = extract_ip(request.headers, request.client.host if request.client else None)

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
                detail={"before": _serialise_exception_for_audit(before_exc) if before_exc else None},
                conn=conn,
            )
    except Exception:
        logger.exception("Transaction failed for availability.exception.deleted")
        raise HTTPException(
            status_code=500,
            detail="Failed to delete availability exception. Please try again.",
        )
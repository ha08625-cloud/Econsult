"""
Admin API router.

All endpoints require a valid session cookie via require_admin, except the
three auth endpoints below which are unauthenticated by design.

Prefix /admin and tag "admin" are applied when registered in main.py.

This module is responsible for:
- MFA authentication (request-code, verify, logout)
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

# ---------------------------------------------------------------------------
# Transaction pattern for mutating endpoints
# ---------------------------------------------------------------------------
#
# Each mutating endpoint (PUT/DELETE that changes state) wraps both the
# repository mutation and the audit_repo.log_event call in a single database
# transaction via get_conn. If either operation fails, both roll back.
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
import os
from datetime import timezone

from fastapi import APIRouter, Request, Depends, HTTPException
from fastapi.responses import JSONResponse, Response

from app.core.admin_context import (
    AdminContext,
    require_admin,
    SESSION_COOKIE_NAME,
    SESSION_COOKIE_MAX_AGE,
    SESSION_TTL_MINUTES,
)
from app.repositories.practice_repository import (
    InvalidSignpostingData,
    InvalidEmailError,
    InvalidDoctorListError,
    MAX_SIGNPOSTING_LENGTH,
    MAX_DOCTOR_NAME_LENGTH,
    MAX_DOCTOR_LIST_LENGTH,
    sanitise_signposting_html,
)
from app.services.availability_service import (
    validate_availability_config,
    validate_override,
    validate_exception,
    deactivation_clears_override,
)
from app.models.availability_models import AvailabilityException, LONDON_TZ
from app.core.errors import (
    APIError,
    INVALID_PAYLOAD,
    INVALID_DATE_FORMAT,
    INVALID_FIELD_TYPE,
    ConditionNotFound,
)
from app.core.dependencies import (
    get_registry,
    get_practice_repo,
    get_availability_repo,
    get_auth_repo,
    get_audit_repo,
    get_admin_delivery_service,
    get_allowed_admin_domains,
    get_practice_id,
)
from app.core.db import get_conn
from app.core.http_utils import extract_ip
from app.services import auth_service

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
        "override_expires_at": config["override_expires_at"].isoformat() if config.get("override_expires_at") else None,
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
# Auth endpoints (unauthenticated)
# ---------------------------------------------------------------------------

@router.post("/auth/request-code", status_code=200)
async def request_mfa_code(
    request: Request,
    auth_repo=Depends(get_auth_repo),
    audit_repo=Depends(get_audit_repo),
    delivery_service=Depends(get_admin_delivery_service),
    allowed_domains: str = Depends(get_allowed_admin_domains),
    practice_id: str = Depends(get_practice_id),
):
    """
    Request an MFA code to be sent to an admin email address.

    Accepts: {"email": "user@domain.com"}

    Always returns 200 regardless of whether the email is registered,
    to prevent user enumeration.

    Returns 422 if the email domain is not in ALLOWED_ADMIN_DOMAINS.
    Returns 429 if a code was requested within the last 60 seconds.

    Audit: logs auth.code_requested for every attempt that passes body
    validation, including attempts for unregistered emails. This is
    intentional — the audit log captures all attempts regardless of
    whether a code was actually sent.
    """
    try:
        body = await request.json()
    except Exception:
        raise INVALID_PAYLOAD("Invalid JSON body")

    if not isinstance(body, dict) or "email" not in body:
        raise INVALID_PAYLOAD('Body must be {"email": "..."}')

    email = body["email"]
    if not isinstance(email, str) or not email.strip():
        raise INVALID_PAYLOAD("email must be a non-empty string")

    email = email.strip().lower()

    auth_service.request_mfa_code(
        email=email,
        auth_repo=auth_repo,
        delivery_service=delivery_service,
        allowed_domains=allowed_domains,
        practice_id=practice_id,
    )

    # Standalone insert — no paired mutation to wrap in a transaction.
    try:
        audit_repo.log_event(
            practice_id=practice_id,
            actor_email=email,
            action="auth.code_requested",
            ip_address=extract_ip(
                request.headers,
                request.client.host if request.client else None,
            ),
            detail={"email": email},
        )
    except Exception:
        logger.exception("Audit log write failed for action auth.code_requested")
        raise HTTPException(
            status_code=500,
            detail="Action succeeded but audit logging failed. Please report this.",
        )

    return {"ok": True}


@router.post("/auth/verify", status_code=200)
async def verify_mfa_code(
    request: Request,
    auth_repo=Depends(get_auth_repo),
    audit_repo=Depends(get_audit_repo),
    practice_id: str = Depends(get_practice_id),
):
    """
    Verify a 6-digit MFA code and issue a session cookie on success.

    Accepts: {"email": "user@domain.com", "code": "047823"}

    On success: returns 200 and sets an HttpOnly session cookie.
    On failure: returns 422 with INVALID_AUTH_CODE for all failure modes.

    The session cookie attributes:
    - HttpOnly: not readable by JavaScript
    - Secure: HTTPS only (set False in DEV_MODE to work over HTTP locally)
    - SameSite=Strict: no cross-site requests
    - Max-Age: SESSION_COOKIE_MAX_AGE seconds

    Audit: logs auth.login.succeeded on success; auth.login.failed on any
    INVALID_AUTH_CODE. The failed event is logged before re-raising so the
    422 response to the client is unchanged.
    """
    try:
        body = await request.json()
    except Exception:
        raise INVALID_PAYLOAD("Invalid JSON body")

    if not isinstance(body, dict):
        raise INVALID_PAYLOAD("Body must be a JSON object")

    email = body.get("email")
    code = body.get("code")

    if not isinstance(email, str) or not email.strip():
        raise INVALID_PAYLOAD("email must be a non-empty string")
    if not isinstance(code, str) or not code.strip():
        raise INVALID_PAYLOAD("code must be a non-empty string")

    email = email.strip().lower()
    code = code.strip()

    # Format validation: code must be exactly 6 digits.
    if not code.isdigit() or len(code) != 6:
        raise INVALID_PAYLOAD("code must be a 6-digit number")

    ip_address = extract_ip(
        request.headers,
        request.client.host if request.client else None,
    )

    try:
        session_id = auth_service.verify_mfa_code(
            email=email,
            code=code,
            auth_repo=auth_repo,
            session_ttl_minutes=SESSION_TTL_MINUTES,
        )
    except APIError as exc:
        if exc.code == "INVALID_AUTH_CODE":
            # Log the failed attempt before re-raising.
            # Standalone insert — no mutation to pair with.
            try:
                audit_repo.log_event(
                    practice_id=practice_id,
                    actor_email=email,
                    action="auth.login.failed",
                    ip_address=ip_address,
                    detail={"email": email, "reason": "verification_failed"},
                )
            except Exception:
                logger.exception("Audit log write failed for action auth.login.failed")
                raise HTTPException(
                    status_code=500,
                    detail="Action succeeded but audit logging failed. Please report this.",
                )
        raise

    # Success path: log before building the response.
    # Standalone insert — session creation already committed inside auth_service.
    try:
        audit_repo.log_event(
            practice_id=practice_id,
            actor_email=email,
            action="auth.login.succeeded",
            ip_address=ip_address,
            session_id=session_id,
            detail={"email": email},
        )
    except Exception:
        logger.exception("Audit log write failed for action auth.login.succeeded")
        raise HTTPException(
            status_code=500,
            detail="Action succeeded but audit logging failed. Please report this.",
        )

    is_dev = os.environ.get("DEV_MODE", "").lower() in ("1", "true")

    response = JSONResponse(content={"ok": True})
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=session_id,
        httponly=True,
        secure=not is_dev,
        samesite="strict",
        max_age=SESSION_COOKIE_MAX_AGE,
    )
    return response


@router.post("/auth/logout", status_code=200)
async def logout(
    request: Request,
    auth_repo=Depends(get_auth_repo),
    audit_repo=Depends(get_audit_repo),
    practice_id: str = Depends(get_practice_id),
):
    """
    Log out by deleting the session and clearing the cookie.

    Does not require require_admin. The client may be calling this after
    a session has already expired, or the cookie may have been cleared
    already. Both cases must succeed cleanly.

    If no session cookie is present, skip the DB call and audit log entirely.
    Always returns an expired cookie to clear any browser state.

    Audit: session_id is captured from the cookie BEFORE delete_session is
    called. This ordering is intentional — once the session is deleted the
    ID is no longer available from the database. actor_email is recorded as
    "unknown" — logout is unauthenticated by design so the caller's identity
    cannot be verified. The session_id in detail is sufficient to correlate
    with the preceding auth.login.succeeded entry.
    """
    # Capture session_id before any DB call so it is available for the audit log.
    session_id = request.cookies.get(SESSION_COOKIE_NAME)

    if session_id:
        auth_repo.delete_session(session_id)

        # Standalone insert — no mutation to wrap in a transaction.
        try:
            audit_repo.log_event(
                practice_id=practice_id,
                actor_email="unknown",
                action="auth.logout",
                ip_address=extract_ip(
                    request.headers,
                    request.client.host if request.client else None,
                ),
                session_id=session_id,
                detail={"session_id": session_id},
            )
        except Exception:
            logger.exception("Audit log write failed for action auth.logout")
            raise HTTPException(
                status_code=500,
                detail="Action succeeded but audit logging failed. Please report this.",
            )

    is_dev = os.environ.get("DEV_MODE", "").lower() in ("1", "true")

    response = JSONResponse(content={"ok": True})
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value="",
        httponly=True,
        secure=not is_dev,
        samesite="strict",
        max_age=0,
    )
    return response


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
    audit_repo=Depends(get_audit_repo),
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

    Audit: practice.email.updated with before/after detail. The mutation
    and audit log write are atomic in a single transaction.
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

    # Validate format before opening a transaction.
    try:
        practice_repo._validate_email(email)
    except InvalidEmailError as e:
        raise INVALID_PAYLOAD(str(e))

    # Read "before" state outside the transaction.
    before_email = practice_repo.get_email(admin.practice_id)

    ip_address = extract_ip(
        request.headers,
        request.client.host if request.client else None,
    )

    try:
        with get_conn(practice_repo.database_url) as conn:
            practice_repo.update_email(admin.practice_id, email, conn=conn)
            audit_repo.log_event(
                practice_id=admin.practice_id,
                actor_email=admin.actor_email,
                action="practice.email.updated",
                ip_address=ip_address,
                session_id=admin.session_id,
                detail={"before": before_email, "after": email},
                conn=conn,
            )
    except InvalidEmailError as e:
        raise INVALID_PAYLOAD(str(e))
    except Exception:
        logger.exception("Transaction failed for practice.email.updated")
        raise HTTPException(
            status_code=500,
            detail="Failed to update practice email. Please try again.",
        )

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
    audit_repo=Depends(get_audit_repo),
):
    """
    Set or replace signposting for a condition.

    Accepts: {"signposting": "<html>..."}

    If content is empty after sanitisation, the row is deleted (same
    as DELETE). The response reflects whatever row was written.

    Validation:
    - condition_id must exist in the registry
    - signposting key must be present and must be a string
    - content must not exceed MAX_SIGNPOSTING_LENGTH characters before
      sanitisation (the repository enforces this too, but checking early
      gives a cleaner error message)

    Returns {"condition_id": ..., "signposting": <html or null>} reflecting
    whatever row was written.

    Audit: conditions.signposting.updated with before/after detail.
    The mutation and audit log write are atomic in a single transaction.
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

    # Read "before" state outside the transaction.
    before_html = practice_repo.get_signposting(admin.practice_id, condition_id)

    ip_address = extract_ip(
        request.headers,
        request.client.host if request.client else None,
    )

    try:
        with get_conn(practice_repo.database_url) as conn:
            practice_repo.set_signposting(admin.practice_id, condition_id, raw, conn=conn)
            # Compute "after" from the input rather than reading back inside
            # the transaction — get_signposting opens its own connection and
            # would not see uncommitted rows. sanitise_signposting_html is
            # deterministic so the result here matches what was written.
            after_html = _normalise_signposting(sanitise_signposting_html(raw))
            audit_repo.log_event(
                practice_id=admin.practice_id,
                actor_email=admin.actor_email,
                action="conditions.signposting.updated",
                resource=condition_id,
                ip_address=ip_address,
                session_id=admin.session_id,
                detail={
                    "before": {"signposting": _normalise_signposting(before_html)},
                    "after": {"signposting": after_html},
                },
                conn=conn,
            )
    except InvalidSignpostingData as e:
        raise INVALID_PAYLOAD(str(e))
    except Exception:
        logger.exception("Transaction failed for conditions.signposting.updated")
        raise HTTPException(
            status_code=500,
            detail="Failed to update signposting. Please try again.",
        )

    saved = practice_repo.get_signposting(admin.practice_id, condition_id)

    return {
        "condition_id": condition_id,
        "signposting": _normalise_signposting(saved),
    }


@router.delete("/conditions/{condition_id}/signposting", status_code=204)
async def delete_signposting(
    condition_id: str,
    request: Request,
    admin: AdminContext = Depends(require_admin),
    registry=Depends(get_registry),
    practice_repo=Depends(get_practice_repo),
    audit_repo=Depends(get_audit_repo),
):
    """
    Remove all signposting for a condition.
    Idempotent: no error if nothing was configured.
    Returns 204 No Content.

    Audit: conditions.signposting.deleted with before detail.
    If nothing was configured (before is null), the audit event is still
    written — the admin's intent is recorded regardless.
    The mutation and audit log write are atomic in a single transaction.
    """
    if not registry.has_condition(condition_id):
        raise ConditionNotFound(condition_id)

    # Read "before" state outside the transaction.
    before_html = practice_repo.get_signposting(admin.practice_id, condition_id)

    ip_address = extract_ip(
        request.headers,
        request.client.host if request.client else None,
    )

    try:
        with get_conn(practice_repo.database_url) as conn:
            practice_repo.delete_signposting(admin.practice_id, condition_id, conn=conn)
            audit_repo.log_event(
                practice_id=admin.practice_id,
                actor_email=admin.actor_email,
                action="conditions.signposting.deleted",
                resource=condition_id,
                ip_address=ip_address,
                session_id=admin.session_id,
                detail={"before": {"signposting": _normalise_signposting(before_html)}},
                conn=conn,
            )
    except Exception:
        logger.exception("Transaction failed for conditions.signposting.deleted")
        raise HTTPException(
            status_code=500,
            detail="Failed to delete signposting. Please try again.",
        )


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
    except Exception:
        logger.exception("Transaction failed for %s", action)
        raise HTTPException(
            status_code=500,
            detail="Failed to save availability exception. Please try again.",
        )

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
    except ValueError:
        raise INVALID_DATE_FORMAT("date", date)

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
                detail={"before": _serialise_exception_for_audit(before_exc) if before_exc else None},
                conn=conn,
            )
    except Exception:
        logger.exception("Transaction failed for availability.exception.deleted")
        raise HTTPException(
            status_code=500,
            detail="Failed to delete availability exception. Please try again.",
        )


# ---------------------------------------------------------------------------
# Doctors
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
    audit_repo=Depends(get_audit_repo),
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

    Audit: doctors.updated with before/after detail.
    The mutation and audit log write are atomic in a single transaction.
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

    # Validate before opening a transaction so format errors return 422,
    # not 500.
    try:
        practice_repo._validate_doctor_list(doctors)
    except InvalidDoctorListError as e:
        raise INVALID_PAYLOAD(str(e))

    # Read "before" state outside the transaction.
    before_doctors = practice_repo.get_doctors(admin.practice_id)

    ip_address = extract_ip(
        request.headers,
        request.client.host if request.client else None,
    )

    try:
        with get_conn(practice_repo.database_url) as conn:
            practice_repo.set_doctors(admin.practice_id, doctors, conn=conn)
            audit_repo.log_event(
                practice_id=admin.practice_id,
                actor_email=admin.actor_email,
                action="doctors.updated",
                ip_address=ip_address,
                session_id=admin.session_id,
                detail={"before": before_doctors, "after": doctors},
                conn=conn,
            )
    except InvalidDoctorListError as e:
        raise INVALID_PAYLOAD(str(e))
    except Exception:
        logger.exception("Transaction failed for doctors.updated")
        raise HTTPException(
            status_code=500,
            detail="Failed to update doctor list. Please try again.",
        )

    saved = practice_repo.get_doctors(admin.practice_id)
    return {"doctors": saved}


# ---------------------------------------------------------------------------
# Audit log
# ---------------------------------------------------------------------------

@router.get("/audit-log")
async def get_audit_log(
    request: Request,
    admin: AdminContext = Depends(require_admin),
    audit_repo=Depends(get_audit_repo),
    cursor: str | None = None,
    from_date: str | None = None,
    to_date: str | None = None,
    actor: str | None = None,
    action: str | None = None,
    limit: int = 50,
):
    """
    Return a paginated list of audit events for this practice.

    Query parameters:
        cursor      Opaque pagination token from a previous response's
                    next_cursor field. Omit to start from the most recent
                    event. Discard when changing any filter.
        from_date   Inclusive start date, YYYY-MM-DD. Applied at 00:00:00 UTC.
        to_date     Inclusive end date, YYYY-MM-DD. Applied at 23:59:59 UTC.
        actor       Exact match on actor_email.
        action      Left-anchored prefix match on action, e.g. "availability"
                    matches "availability.config.updated". Must be lowercase
                    letters, digits, dots, and underscores only.
        limit       Page size. Default 50, max 200. Values outside this
                    range are clamped server-side rather than rejected.

    Response:
        {
            "events": [...],
            "next_cursor": "<opaque string> | null"
        }

    next_cursor is null when the client has reached the end of the result
    set. Pass it back as ?cursor= on the next request to load the next page.

    Each event contains: id, occurred_at (ISO 8601), practice_id,
    actor_email, action, resource, detail, ip_address, session_id.

    Returns 400 if the cursor is malformed or the action prefix is invalid.
    Returns 422 if from_date or to_date cannot be parsed as YYYY-MM-DD.

    All admins may access this endpoint. It is read-only and contains no
    patient-confidential information.
    """
    # Parse date strings. Return 422 on invalid format — same status used
    # for other input validation errors in this router.
    parsed_from_date = None
    if from_date is not None:
        try:
            parsed_from_date = datetime.date.fromisoformat(from_date)
        except ValueError:
            raise INVALID_DATE_FORMAT("from_date", from_date)

    parsed_to_date = None
    if to_date is not None:
        try:
            parsed_to_date = datetime.date.fromisoformat(to_date)
        except ValueError:
            raise INVALID_DATE_FORMAT("to_date", to_date)

    # Clamp limit. Do not reject out-of-range values — just apply the bounds
    # silently. This avoids a class of client breakage if limits drift over time.
    limit = max(1, min(limit, 200))

    try:
        result = audit_repo.list_events(
            practice_id=admin.practice_id,
            cursor=cursor,
            from_date=parsed_from_date,
            to_date=parsed_to_date,
            actor=actor,
            action_prefix=action,
            limit=limit,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    # Serialise datetime fields. psycopg2 returns occurred_at as a Python
    # datetime object; JSON serialisation requires a string.
    events = []
    for row in result["events"]:
        serialised = dict(row)
        if isinstance(serialised.get("occurred_at"), datetime.datetime):
            serialised["occurred_at"] = serialised["occurred_at"].isoformat()
        events.append(serialised)

    return {
        "events": events,
        "next_cursor": result["next_cursor"],
    }
"""
Admin Practice API router.

Handles practice settings, doctor lists, condition lists, and signposting.
All endpoints require a valid admin session via require_admin.

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

import logging

from fastapi import APIRouter, Depends, HTTPException, Request

from app.core.admin_context import AdminContext, require_admin
from app.core.body_capture import BodyCapturingRoute, read_json_body
from app.core.db import get_conn
from app.core.dependencies import (
    get_audit_repo,
    get_practice_repo,
    get_registry,
)
from app.core.errors import (
    INVALID_FIELD_TYPE,
    INVALID_PAYLOAD,
    ConditionNotFound,
)
from app.repositories.practice_repository import (
    MAX_SIGNPOSTING_LENGTH,
    InvalidDoctorListError,
    InvalidEmailError,
    InvalidSignpostingData,
    sanitise_signposting_html,
)
from app.utils.http_utils import extract_ip

logger = logging.getLogger(__name__)

router = APIRouter(route_class=BodyCapturingRoute)


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


# ---------------------------------------------------------------------------
# Condition list
# ---------------------------------------------------------------------------


@router.get("/conditions")
def admin_list_conditions(
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
def get_practice(
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
def put_practice_email(
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
    body = read_json_body(request)

    if not isinstance(body, dict) or "email" not in body:
        raise INVALID_PAYLOAD('Body must be {"email": "..."}')

    email = body["email"]

    if not isinstance(email, str):
        raise INVALID_FIELD_TYPE("email", "a string")

    # Validate format before opening a transaction so format errors return 422,
    # not 500.
    try:
        practice_repo._validate_email(email)
    except InvalidEmailError as e:
        raise INVALID_PAYLOAD(str(e)) from e

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
        raise INVALID_PAYLOAD(str(e)) from e
    except Exception as e:
        logger.exception("Transaction failed for practice.email.updated")
        raise HTTPException(
            status_code=500,
            detail="Failed to update practice email. Please try again.",
        ) from e

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
def get_signposting(
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
def put_signposting(
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

    body = read_json_body(request)

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
        raise INVALID_PAYLOAD(str(e)) from e
    except Exception as e:
        logger.exception("Transaction failed for conditions.signposting.updated")
        raise HTTPException(
            status_code=500,
            detail="Failed to update signposting. Please try again.",
        ) from e

    saved = practice_repo.get_signposting(admin.practice_id, condition_id)

    return {
        "condition_id": condition_id,
        "signposting": _normalise_signposting(saved),
    }


@router.delete("/conditions/{condition_id}/signposting", status_code=204)
def delete_signposting(
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
    except Exception as e:
        logger.exception("Transaction failed for conditions.signposting.deleted")
        raise HTTPException(
            status_code=500,
            detail="Failed to delete signposting. Please try again.",
        ) from e


# ---------------------------------------------------------------------------
# Doctors
# ---------------------------------------------------------------------------


@router.get("/doctors")
def get_doctors(
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
def put_doctors(
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
    body = read_json_body(request)

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
        raise INVALID_PAYLOAD(str(e)) from e

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
        raise INVALID_PAYLOAD(str(e)) from e
    except Exception as e:
        logger.exception("Transaction failed for doctors.updated")
        raise HTTPException(
            status_code=500,
            detail="Failed to update doctor list. Please try again.",
        ) from e

    saved = practice_repo.get_doctors(admin.practice_id)
    return {"doctors": saved}

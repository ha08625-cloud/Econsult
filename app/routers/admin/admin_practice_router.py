"""
Admin Practice API router.
Handles practice settings, doctor lists, condition lists, and signposting.
"""
import logging

from fastapi import APIRouter, Request, Depends, HTTPException

from app.core.admin_context import AdminContext, require_admin
from app.repositories.practice_repository import (
    InvalidSignpostingData,
    InvalidEmailError,
    InvalidDoctorListError,
    MAX_SIGNPOSTING_LENGTH,
    MAX_DOCTOR_LIST_LENGTH,
    sanitise_signposting_html,
)
from app.core.errors import (
    INVALID_PAYLOAD,
    INVALID_FIELD_TYPE,
    ConditionNotFound,
)
from app.core.dependencies import (
    get_registry,
    get_practice_repo,
    get_audit_repo,
)
from app.core.db import get_conn
from app.utils.http_utils import extract_ip

logger = logging.getLogger(__name__)

router = APIRouter()

# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _normalise_signposting(value) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    return value

# ---------------------------------------------------------------------------
# Condition list
# ---------------------------------------------------------------------------

@router.get("/conditions")
async def admin_list_conditions(
    _: AdminContext = Depends(require_admin),
    registry=Depends(get_registry),
):
    return {"conditions": registry.list_conditions()}

# ---------------------------------------------------------------------------
# Practice
# ---------------------------------------------------------------------------

@router.get("/practice")
async def get_practice(
    admin: AdminContext = Depends(require_admin),
    practice_repo=Depends(get_practice_repo),
):
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
        practice_repo._validate_email(email)
    except InvalidEmailError as e:
        raise INVALID_PAYLOAD(str(e))

    before_email = practice_repo.get_email(admin.practice_id)
    ip_address = extract_ip(request.headers, request.client.host if request.client else None)

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

    before_html = practice_repo.get_signposting(admin.practice_id, condition_id)
    ip_address = extract_ip(request.headers, request.client.host if request.client else None)

    try:
        with get_conn(practice_repo.database_url) as conn:
            practice_repo.set_signposting(admin.practice_id, condition_id, raw, conn=conn)
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
    if not registry.has_condition(condition_id):
        raise ConditionNotFound(condition_id)

    before_html = practice_repo.get_signposting(admin.practice_id, condition_id)
    ip_address = extract_ip(request.headers, request.client.host if request.client else None)

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
# Doctors
# ---------------------------------------------------------------------------

@router.get("/doctors")
async def get_doctors(
    admin: AdminContext = Depends(require_admin),
    practice_repo=Depends(get_practice_repo),
):
    doctors = practice_repo.get_doctors(admin.practice_id)
    return {"doctors": doctors}

@router.put("/doctors")
async def put_doctors(
    request: Request,
    admin: AdminContext = Depends(require_admin),
    practice_repo=Depends(get_practice_repo),
    audit_repo=Depends(get_audit_repo),
):
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
        practice_repo._validate_doctor_list(doctors)
    except InvalidDoctorListError as e:
        raise INVALID_PAYLOAD(str(e))

    before_doctors = practice_repo.get_doctors(admin.practice_id)
    ip_address = extract_ip(request.headers, request.client.host if request.client else None)

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
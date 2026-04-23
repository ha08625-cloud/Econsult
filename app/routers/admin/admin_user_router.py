"""
app/routers/admin/admin_user_router.py

Admin user management endpoints.

Endpoints:
  GET    /admin/users                      — list all users for the practice
  POST   /admin/users                      — add a new admin user
  DELETE /admin/users/{id}                 — remove an admin user
  POST   /admin/users/{id}/resend-invitation — resend the invitation email

All endpoints require a valid admin session via require_admin.

# ---------------------------------------------------------------------------
# Transaction pattern
# ---------------------------------------------------------------------------
#
# Mutating endpoints (POST, DELETE) follow the same transaction pattern as
# other admin sub-routers:
#
#   1. Open with get_conn(db_url) as conn:
#   2. Call user_service (which calls repositories with conn=conn).
#   3. Call audit_repo.log_event(conn=conn, ...).
#   4. The context manager commits on clean exit, rolls back on exception.
#
# Email delivery always happens AFTER the with block closes (i.e. after the
# transaction has committed). This means:
#   - If delivery fails, the user was still added/the audit log still written.
#   - The caller receives email_sent: false and can retry via resend-invitation.
#
# resend-invitation is a special case: the service call (a read) happens
# BEFORE the with block, and the with block exists solely to write the
# audit log atomically. Email is sent after the with block.
#
# ---------------------------------------------------------------------------
# datetime serialisation
# ---------------------------------------------------------------------------
#
# psycopg2 returns TIMESTAMPTZ columns as Python datetime objects.
# FastAPI cannot serialise raw datetime objects in plain dict responses.
# All datetime fields (created_at, last_login) must be converted to ISO 8601
# strings before returning. last_login may be None — only call .isoformat()
# when the value is not None.
# ---------------------------------------------------------------------------
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, Request

from app.core.admin_context import AdminContext, require_admin
from app.core.db import get_conn
from app.core.dependencies import (
    get_auth_repo,
    get_practice_repo,
    get_audit_repo,
    get_admin_delivery_service,
    get_allowed_admin_domains,
)
from app.core.errors import INVALID_PAYLOAD
from app.services.admin import user_service
from app.utils.http_utils import extract_ip

logger = logging.getLogger(__name__)

router = APIRouter()


def _serialise_user(user: dict, current_user_id: str) -> dict:
    """
    Convert a raw user dict from the repository into the API response shape.

    - Converts created_at and last_login datetime objects to ISO 8601 strings.
    - Injects is_current_user boolean.
    """
    return {
        "id": user["id"],
        "email": user["email"],
        "created_at": user["created_at"].isoformat() if user["created_at"] is not None else None,
        "last_login": user["last_login"].isoformat() if user["last_login"] is not None else None,
        "is_current_user": user["id"] == current_user_id,
    }


# ---------------------------------------------------------------------------
# GET /admin/users
# ---------------------------------------------------------------------------

@router.get("/users")
async def list_users(
    admin: AdminContext = Depends(require_admin),
    auth_repo=Depends(get_auth_repo),
):
    """
    Return all admin users for the practice, ordered by created_at ASC.

    Each user includes:
      id, email, created_at (ISO 8601), last_login (ISO 8601 or null),
      is_current_user (bool).
    """
    users = auth_repo.get_users_by_practice(admin.practice_id)
    return {
        "users": [_serialise_user(u, admin.user_id) for u in users]
    }


# ---------------------------------------------------------------------------
# POST /admin/users
# ---------------------------------------------------------------------------

@router.post("/users")
async def add_user(
    request: Request,
    admin: AdminContext = Depends(require_admin),
    auth_repo=Depends(get_auth_repo),
    practice_repo=Depends(get_practice_repo),
    audit_repo=Depends(get_audit_repo),
    admin_delivery_service=Depends(get_admin_delivery_service),
    allowed_domains: str = Depends(get_allowed_admin_domains),
):
    """
    Add a new admin user for the practice.

    Accepts: {"email": "user@nhs.net"}

    Returns: {"ok": true, "email_sent": true|false}

    email_sent is false if the invitation email failed to send. The user was
    still created — the caller should use POST /admin/users/{id}/resend-invitation
    to retry delivery.

    Audit: auth.user_added with target_email detail.
    """
    try:
        body = await request.json()
    except Exception:
        raise INVALID_PAYLOAD("Invalid JSON body")

    if not isinstance(body, dict) or "email" not in body:
        raise INVALID_PAYLOAD('Body must be {"email": "..."}')

    email = body["email"]

    if not isinstance(email, str):
        raise INVALID_PAYLOAD("email must be a string")

    # Normalise here so the audit log records the canonical form.
    email = email.strip().lower()

    ip_address = extract_ip(
        request.headers,
        request.client.host if request.client else None,
    )

    try:
        with get_conn(practice_repo.database_url) as conn:
            user_service.add_user(
                email=email,
                allowed_domains=allowed_domains,
                admin_context=admin,
                practice_repo=practice_repo,
                auth_repo=auth_repo,
                conn=conn,
            )
            audit_repo.log_event(
                practice_id=admin.practice_id,
                actor_email=admin.actor_email,
                action="auth.user_added",
                detail={"target_email": email},
                ip_address=ip_address,
                session_id=admin.session_id,
                conn=conn,
            )
    except Exception:
        # Re-raise APIError subclasses (validation, domain policy, duplicate)
        # so FastAPI's exception handler returns the correct status code.
        # Only catch and convert unexpected errors to 500.
        from app.core.errors import APIError as _APIError
        import sys
        exc = sys.exc_info()[1]
        if isinstance(exc, _APIError):
            raise
        logger.exception("Transaction failed for auth.user_added")
        raise HTTPException(
            status_code=500,
            detail="Failed to add user. Please try again.",
        )

    # Transaction committed. Now attempt email delivery.
    email_sent = True
    try:
        admin_delivery_service.send_admin_invitation(email)
    except Exception:
        logger.warning("Invitation email failed to send to %s", email, exc_info=True)
        email_sent = False

    return {"ok": True, "email_sent": email_sent}


# ---------------------------------------------------------------------------
# DELETE /admin/users/{id}
# ---------------------------------------------------------------------------

@router.delete("/users/{user_id}")
async def remove_user(
    user_id: str,
    request: Request,
    admin: AdminContext = Depends(require_admin),
    auth_repo=Depends(get_auth_repo),
    practice_repo=Depends(get_practice_repo),
    audit_repo=Depends(get_audit_repo),
):
    """
    Remove an admin user from the practice.

    Returns 200 {"ok": true} on success.

    Possible error responses (via APIError handler):
      403 ACTION_NOT_PERMITTED — self-delete or last-user delete
      404 USER_NOT_FOUND       — user does not exist in this practice

    Audit: auth.user_deleted with target_user_id detail.
    """
    ip_address = extract_ip(
        request.headers,
        request.client.host if request.client else None,
    )

    try:
        with get_conn(practice_repo.database_url) as conn:
            user_service.remove_user(
                target_user_id=user_id,
                admin_context=admin,
                practice_repo=practice_repo,
                auth_repo=auth_repo,
                conn=conn,
            )
            audit_repo.log_event(
                practice_id=admin.practice_id,
                actor_email=admin.actor_email,
                action="auth.user_deleted",
                detail={"target_user_id": user_id},
                ip_address=ip_address,
                session_id=admin.session_id,
                conn=conn,
            )
    except Exception:
        from app.core.errors import APIError as _APIError
        import sys
        exc = sys.exc_info()[1]
        if isinstance(exc, _APIError):
            raise
        logger.exception("Transaction failed for auth.user_deleted")
        raise HTTPException(
            status_code=500,
            detail="Failed to remove user. Please try again.",
        )

    return {"ok": True}


# ---------------------------------------------------------------------------
# POST /admin/users/{id}/resend-invitation
# ---------------------------------------------------------------------------

@router.post("/users/{user_id}/resend-invitation")
async def resend_invitation(
    user_id: str,
    request: Request,
    admin: AdminContext = Depends(require_admin),
    auth_repo=Depends(get_auth_repo),
    practice_repo=Depends(get_practice_repo),
    audit_repo=Depends(get_audit_repo),
    admin_delivery_service=Depends(get_admin_delivery_service),
):
    """
    Resend the invitation email to an existing admin user.

    The service call (a read) happens before the transaction block.
    The transaction block exists solely to write the audit log atomically.
    Email is sent after the transaction commits.

    Returns: {"ok": true, "email_sent": true|false}

    Possible error responses:
      404 USER_NOT_FOUND — user does not exist in this practice

    Audit: auth.invitation_resent with target_user_id detail.
    """
    # Read outside the transaction — no writes in the service call.
    email = user_service.resend_invitation(
        target_user_id=user_id,
        admin_context=admin,
        auth_repo=auth_repo,
    )

    ip_address = extract_ip(
        request.headers,
        request.client.host if request.client else None,
    )

    try:
        with get_conn(practice_repo.database_url) as conn:
            audit_repo.log_event(
                practice_id=admin.practice_id,
                actor_email=admin.actor_email,
                action="auth.invitation_resent",
                detail={"target_user_id": user_id},
                ip_address=ip_address,
                session_id=admin.session_id,
                conn=conn,
            )
    except Exception:
        logger.exception("Audit log failed for auth.invitation_resent")
        raise HTTPException(
            status_code=500,
            detail="Failed to record audit event. Please try again.",
        )

    # Transaction committed. Now attempt email delivery.
    email_sent = True
    try:
        admin_delivery_service.send_admin_invitation(email)
    except Exception:
        logger.warning(
            "Resend invitation email failed to send to %s", email, exc_info=True
        )
        email_sent = False

    return {"ok": True, "email_sent": email_sent}
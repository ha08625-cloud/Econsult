"""
Admin User Management API router.

Handles listing, adding, deleting, and re-inviting admin users.
All endpoints require a valid admin session via require_admin.

This module must never import:
- Clinical engine modules (form_logic, safety_engine, encoder_mapping, etc.)
- presentation_service
- serialisation, projection, runtime_state

# ---------------------------------------------------------------------------
# Transaction pattern
# ---------------------------------------------------------------------------
#
# POST /users and DELETE /users/{id} both open a shared transaction via
# get_conn. The transaction covers:
#   - The practice row lock (acquired inside user_service)
#   - The user write (insert or delete, inside user_service)
#   - The reset token upsert (inside auth_service.generate_reset_token, for
#     POST /users only — token generation is inside the transaction so it
#     rolls back atomically if the user insert fails)
#   - The audit log write
#
# If any of these fail the entire transaction rolls back.
#
# APIError raised inside user_service (domain validation failures: 409, 403,
# 422, 404) must propagate out of the try/except block uncaught so they reach
# the registered APIError exception handler in main.py. The bare
# `except Exception` catches only genuinely unexpected errors and converts them
# to 500, following the same pattern as admin_practice_router.py.
#
# Email delivery (send_admin_invitation) is intentionally outside the
# transaction. A delivery failure does not roll back the user write — the user
# has been added and can be re-invited via POST /users/{id}/resend-invitation.
# The response includes email_sent: false so the caller is informed.
#
# POST /users/{id}/resend-invitation performs a token upsert (its own
# connection, not part of a larger transaction) then dispatches email.
# The audit log insert uses conn=None (standalone insert, consistent with
# the pattern in admin_auth_router.py for write-free flows).
# ---------------------------------------------------------------------------
"""
import logging
import datetime

from fastapi import APIRouter, Request, Depends, HTTPException

from app.core.admin_context import AdminContext, require_admin
from app.core.dependencies import (
    get_auth_repo,
    get_practice_repo,
    get_audit_repo,
    get_admin_delivery_service,
    get_allowed_admin_domains,
)
from app.core.errors import APIError, INVALID_PAYLOAD
from app.core.db import get_conn
from app.core.rate_limit import limiter
from app.utils.http_utils import extract_ip
from app.services.admin import user_service, auth_service

logger = logging.getLogger(__name__)

router = APIRouter()


# ---------------------------------------------------------------------------
# GET /users
# ---------------------------------------------------------------------------

@router.get("/users")
async def list_users(
    admin: AdminContext = Depends(require_admin),
    auth_repo=Depends(get_auth_repo),
):
    """
    Return all admin users for this practice.

    Plain read — no lock, no transaction. Ordered by created_at ascending.

    Each user object contains:
        id              UUID string
        email           str
        created_at      ISO 8601 string
        last_login      ISO 8601 string or null (null means invitation pending)
        is_current_user bool — true if this user is the authenticated caller

    Returns 401 if the session has expired.
    """
    users = auth_repo.get_users_by_practice(admin.practice_id)

    result = []
    for user in users:
        result.append({
            "id": user["id"],
            "email": user["email"],
            "created_at": (
                user["created_at"].isoformat()
                if isinstance(user["created_at"], datetime.datetime)
                else user["created_at"]
            ),
            "last_login": (
                user["last_login"].isoformat()
                if isinstance(user["last_login"], datetime.datetime)
                else None
            ),
            "is_current_user": user["id"] == admin.user_id,
        })

    return result


# ---------------------------------------------------------------------------
# POST /users
# ---------------------------------------------------------------------------

@router.post("/users", status_code=200)
@limiter.limit("10/minute")
async def add_user(
    request: Request,
    admin: AdminContext = Depends(require_admin),
    auth_repo=Depends(get_auth_repo),
    practice_repo=Depends(get_practice_repo),
    audit_repo=Depends(get_audit_repo),
    delivery_service=Depends(get_admin_delivery_service),
    allowed_domains: str = Depends(get_allowed_admin_domains),
):
    """
    Add a new admin user for this practice and send a setup invitation email.

    Accepts: {"email": "user@domain.com"}

    Validation:
    - email must be a non-empty string
    - email must be a valid format (checked in user_service)
    - email domain must be in ALLOWED_ADMIN_DOMAINS (checked in user_service)
    - email must not already be registered (checked in user_service)

    The user insert, reset token upsert, and audit log are atomic — they
    share a single transaction. If any of these fail, the entire transaction
    rolls back. Email delivery is outside the transaction — a delivery failure
    does not roll back the user insert.

    Returns:
        {"ok": true, "email_sent": true}   — user added, invitation sent
        {"ok": true, "email_sent": false}  — user added, delivery failed

    Returns 409 if the email already exists.
    Returns 403 if the domain is not on the allowlist.
    Returns 422 if the email format is invalid.
    Returns 401 if the session has expired.
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

    # Normalisation is also applied inside user_service.add_user, but strip
    # here so the value used for audit logging and email delivery is consistent
    # with what was stored.
    email = email.strip().lower()

    ip_address = extract_ip(
        request.headers,
        request.client.host if request.client else None,
    )

    raw_token: str = ""

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
            # Retrieve the newly inserted user's id to generate the token.
            # get_user_by_email uses its own connection — inside a shared
            # transaction we must use the conn-accepting path. user_service
            # returns the inserted user for this purpose.
            #
            # Since insert_user does not return the id, we look it up within
            # the same transaction to guarantee consistency.
            new_user = _get_user_by_email_in_conn(auth_repo, email, conn)
            raw_token = auth_service.generate_reset_token(
                new_user["id"], auth_repo, conn=conn
            )
            audit_repo.log_event(
                practice_id=admin.practice_id,
                actor_email=admin.actor_email,
                action="auth.user_added",
                ip_address=ip_address,
                session_id=admin.session_id,
                detail={"target_email": email},
                conn=conn,
            )
    except APIError:
        # Domain validation failure (409, 403, 422) — let it propagate to the
        # registered APIError handler in main.py unchanged.
        raise
    except Exception:
        logger.exception("Transaction failed for auth.user_added")
        raise HTTPException(
            status_code=500,
            detail="Failed to add user. Please try again.",
        )

    # Delivery is outside the transaction. A failure here does not roll back
    # the user insert — the admin can retry via /resend-invitation.
    email_sent = True
    try:
        delivery_service.send_admin_invitation(email, raw_token)
    except Exception:
        logger.warning("Invitation email failed to send to %s", email)
        email_sent = False

    return {"ok": True, "email_sent": email_sent}


def _get_user_by_email_in_conn(auth_repo, email: str, conn) -> dict:
    """
    Look up a user by email within an existing transaction connection.

    get_user_by_email always opens its own connection (it is a read method
    with no conn parameter). To retrieve the newly inserted user's id within
    the same transaction — so the id read is consistent with the uncommitted
    insert — we execute the query directly on the shared conn here.

    This helper is private to admin_user_router and is only called from
    add_user, immediately after insert_user, within the same get_conn block.
    """
    from psycopg2.extras import RealDictCursor
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(
            "SELECT id::text, email FROM admin_users WHERE email = %s",
            (email,),
        )
        row = cur.fetchone()
    if row is None:
        raise RuntimeError(
            f"User '{email}' not found immediately after insert — this should not happen."
        )
    return dict(row)


# ---------------------------------------------------------------------------
# DELETE /users/{user_id}
# ---------------------------------------------------------------------------

@router.delete("/users/{user_id}", status_code=200)
async def remove_user(
    user_id: str,
    request: Request,
    admin: AdminContext = Depends(require_admin),
    auth_repo=Depends(get_auth_repo),
    practice_repo=Depends(get_practice_repo),
    audit_repo=Depends(get_audit_repo),
):
    """
    Delete an admin user from this practice.

    Guards (enforced in user_service):
    - Cannot delete your own account (403)
    - Cannot delete the last user (403)
    - Cannot delete a user not in this practice (404)

    The delete and audit log are atomic. Postgres cascades the delete to
    admin_sessions and admin_password_reset_tokens, so the deleted user's
    sessions and pending tokens are removed automatically.

    Returns {"ok": true} on success.
    Returns 403 if self-deletion or last-user deletion is attempted.
    Returns 404 if the target user is not found in this practice.
    Returns 401 if the session has expired.
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
                ip_address=ip_address,
                session_id=admin.session_id,
                detail={"target_user_id": user_id},
                conn=conn,
            )
    except APIError:
        raise
    except Exception:
        logger.exception("Transaction failed for auth.user_deleted")
        raise HTTPException(
            status_code=500,
            detail="Failed to delete user. Please try again.",
        )

    return {"ok": True}


# ---------------------------------------------------------------------------
# POST /users/{user_id}/resend-invitation
# ---------------------------------------------------------------------------

@router.post("/users/{user_id}/resend-invitation", status_code=200)
@limiter.limit("10/minute")
async def resend_invitation(
    user_id: str,
    request: Request,
    admin: AdminContext = Depends(require_admin),
    auth_repo=Depends(get_auth_repo),
    audit_repo=Depends(get_audit_repo),
    delivery_service=Depends(get_admin_delivery_service),
):
    """
    Re-send the setup invitation email to an existing admin user.

    Generates a fresh reset token (replacing any existing pending token) and
    sends an invitation email with the new setup link. The frontend only
    renders this button when last_login is null, but the endpoint does not
    enforce that constraint — any user can be re-invited regardless of login
    history.

    The audit log uses a standalone insert (conn=None) consistent with the
    pattern in admin_auth_router.py. If the audit write fails the endpoint
    returns 500 — the audit trail is mandatory.

    Returns:
        {"ok": true, "email_sent": true}   — invitation sent
        {"ok": true, "email_sent": false}  — delivery failed

    Returns 404 if the target user is not found in this practice.
    Returns 401 if the session has expired.
    """
    # Raises USER_NOT_FOUND (404) if the user is not in this practice.
    email = user_service.resend_invitation(
        target_user_id=user_id,
        admin_context=admin,
        auth_repo=auth_repo,
    )

    # Generate a fresh token. Uses its own connection (no transaction needed
    # here — this is the only write and it is idempotent via upsert).
    raw_token = auth_service.generate_reset_token(user_id, auth_repo)

    ip_address = extract_ip(
        request.headers,
        request.client.host if request.client else None,
    )

    try:
        audit_repo.log_event(
            practice_id=admin.practice_id,
            actor_email=admin.actor_email,
            action="auth.invitation_resent",
            ip_address=ip_address,
            session_id=admin.session_id,
            detail={"target_user_id": user_id},
        )
    except Exception:
        logger.exception("Audit log write failed for action auth.invitation_resent")
        raise HTTPException(
            status_code=500,
            detail="Action succeeded but audit logging failed. Please report this.",
        )

    email_sent = True
    try:
        delivery_service.send_admin_invitation(email, raw_token)
    except Exception:
        logger.warning("Re-invitation email failed to send to %s", email)
        email_sent = False

    return {"ok": True, "email_sent": email_sent}
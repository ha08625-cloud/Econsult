"""
Admin Auth API router.
Handles MFA requests, verification, and logout.
Unauthenticated by design.
"""
import os
import logging

from fastapi import APIRouter, Request, Depends, HTTPException
from fastapi.responses import JSONResponse

from app.core.admin_context import (
    SESSION_COOKIE_NAME,
    SESSION_COOKIE_MAX_AGE,
    SESSION_TTL_MINUTES,
)
from app.core.errors import APIError, INVALID_PAYLOAD
from app.core.dependencies import (
    get_auth_repo,
    get_audit_repo,
    get_admin_delivery_service,
    get_allowed_admin_domains,
    get_practice_id,
)
from app.utils.http_utils import extract_ip
from app.core.rate_limit import limiter
from app.services import auth_service

logger = logging.getLogger(__name__)

router = APIRouter()

@router.post("/auth/request-code", status_code=200)
@limiter.limit("5/minute")
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
@limiter.limit("5/minute")
async def verify_mfa_code(
    request: Request,
    auth_repo=Depends(get_auth_repo),
    audit_repo=Depends(get_audit_repo),
    practice_id: str = Depends(get_practice_id),
):
    """
    Verify a 6-digit MFA code and issue a session cookie on success.
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
    """
    session_id = request.cookies.get(SESSION_COOKIE_NAME)

    if session_id:
        auth_repo.delete_session(session_id)

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
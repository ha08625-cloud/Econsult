"""
Admin Auth API router.

Handles password+OTP login (two steps), password reset/setup, and logout.
All endpoints except logout are unauthenticated by design — they are the
mechanism by which an admin establishes a session, so they cannot require one.

Transaction pattern: auth endpoints use standalone audit log inserts (no
paired repository mutation to wrap). Each audit_repo.log_event call is
therefore outside a get_conn block. If the audit write fails, the endpoint
returns 500 — the audit trail is considered mandatory for all auth events.

Background task pattern (POST /auth/login):
The OTP is generated and upserted to the database synchronously, before
the 200 response is sent. This guarantees the DB write succeeded before
the client transitions to the OTP screen. The email delivery is then
dispatched as a FastAPI BackgroundTask so that the SMTP/HTTP network delay
does not block the response. If the background delivery fails, the task
catches the exception, logs it to Sentry, and deletes the OTP record from
the database so the user is not left waiting for a code that will never arrive.

Background task pattern (POST /auth/request-reset):
Same reasoning applies to the anti-enumeration fixed delay: any work that
differs between a registered and an unregistered email must not add to
response time, or the delay it is meant to protect is defeated. The reset
token is written to the database synchronously (fast, and required before
the email can reference it), but the email itself — a Mailgun HTTP round
trip — is dispatched as a BackgroundTask after the fixed delay has already
elapsed and the response is on its way out.
"""

import logging
from datetime import UTC, datetime, timedelta

import sentry_sdk
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from fastapi.responses import JSONResponse

from app.core.admin_context import (
    SESSION_COOKIE_MAX_AGE,
    SESSION_COOKIE_NAME,
    SESSION_TTL_MINUTES,
)
from app.core.body_capture import BodyCapturingRoute, read_json_body
from app.core.dependencies import (
    get_admin_delivery_service,
    get_audit_repo,
    get_auth_repo,
    get_practice_id,
)
from app.core.errors import INVALID_PAYLOAD, APIError
from app.core.rate_limit import limiter
from app.services.admin import auth_service
from app.utils.http_utils import extract_ip

# OTP TTL re-used from auth_service constants (10 minutes).
_CODE_TTL_MINUTES = 10

logger = logging.getLogger(__name__)

router = APIRouter(route_class=BodyCapturingRoute)


# ---------------------------------------------------------------------------
# Background task: send MFA code with cleanup on failure
# ---------------------------------------------------------------------------


def _send_mfa_code_background(
    email: str,
    code: str,
    auth_repo,
    delivery_service,
) -> None:
    """
    Background task: deliver the MFA code email.

    Called after the OTP has been synchronously written to the database and
    the 200 response has been returned to the client. If delivery fails:
    - The exception is reported to Sentry for the engineering team.
    - The OTP record is deleted from the database.

    Deleting the OTP record on failure is important: the client has already
    transitioned to the OTP entry screen, but the code was never delivered.
    Leaving the record in place would mean the user could not request a new
    code via a retry (the 60-second cooldown would still be active). Cleaning
    up lets a retry attempt succeed immediately.
    """
    try:
        delivery_service.send_mfa_code(email, code)
        logger.info("auth.login.mfa_code_sent: %s", email)
    except Exception:
        logger.exception("auth.login.mfa_delivery_failed: %s — cleaning up OTP record", email)
        sentry_sdk.capture_exception()
        try:
            auth_repo.delete_auth_code(email)
        except Exception:
            logger.exception(
                "auth.login.otp_cleanup_failed: %s — OTP record may be orphaned",
                email,
            )


# ---------------------------------------------------------------------------
# POST /auth/login  (step 1: password check + OTP dispatch)
# ---------------------------------------------------------------------------


@router.post("/auth/login", status_code=200)
@limiter.limit("5/minute")
def login(
    request: Request,
    background_tasks: BackgroundTasks,
    auth_repo=Depends(get_auth_repo),
    audit_repo=Depends(get_audit_repo),
    delivery_service=Depends(get_admin_delivery_service),
    practice_id: str = Depends(get_practice_id),
):
    """
    Step 1 of 2-factor login: verify email and password.

    Accepts: {"email": "user@domain.com", "password": "..."}

    On success:
    - Synchronously generates an OTP and upserts it to admin_auth_codes.
    - Dispatches email delivery as a background task.
    - Returns 200 {"ok": true}. The client should transition to the OTP
      entry screen.

    On failure:
    - Returns 422 INVALID_CREDENTIALS for any failure (wrong password,
      user not found, account locked, no password set yet, cooldown).
      The generic error deliberately conceals which gate failed.

    Audit:
    - auth.login.step1_failed on any INVALID_CREDENTIALS.
    - auth.login.step1_succeeded on success (OTP generated and queued).
    """
    body = read_json_body(request)

    if not isinstance(body, dict):
        raise INVALID_PAYLOAD("Body must be a JSON object")

    email = body.get("email")
    password = body.get("password")

    if not isinstance(email, str) or not email.strip():
        raise INVALID_PAYLOAD("email must be a non-empty string")
    if not isinstance(password, str) or not password:
        raise INVALID_PAYLOAD("password must be a non-empty string")

    email = email.strip().lower()

    ip_address = extract_ip(
        request.headers,
        request.client.host if request.client else None,
    )

    try:
        auth_service.verify_login_credentials(
            email=email,
            password=password,
            auth_repo=auth_repo,
        )
    except APIError as exc:
        if exc.code == "INVALID_CREDENTIALS":
            try:
                audit_repo.log_event(
                    practice_id=practice_id,
                    actor_email=email,
                    action="auth.login.step1_failed",
                    ip_address=ip_address,
                    detail={"email": email},
                )
            except Exception as err:
                logger.exception("Audit log write failed for auth.login.step1_failed")
                raise HTTPException(
                    status_code=500,
                    detail="Action succeeded but audit logging failed. Please report this.",
                ) from err
        raise

    # Password verified. Generate OTP and upsert synchronously.
    code = auth_service.generate_code()
    hashed = auth_service.hash_code(code)
    now = datetime.now(tz=UTC)
    expires_at = now + timedelta(minutes=_CODE_TTL_MINUTES)

    auth_repo.upsert_auth_code(
        email=email,
        hashed_code=hashed,
        expires_at=expires_at,
        last_requested_at=now,
    )

    # Dispatch email in the background. Failure handling is inside the task.
    background_tasks.add_task(
        _send_mfa_code_background,
        email,
        code,
        auth_repo,
        delivery_service,
    )

    try:
        audit_repo.log_event(
            practice_id=practice_id,
            actor_email=email,
            action="auth.login.step1_succeeded",
            ip_address=ip_address,
            detail={"email": email},
        )
    except Exception as err:
        logger.exception("Audit log write failed for auth.login.step1_succeeded")
        raise HTTPException(
            status_code=500,
            detail="Action succeeded but audit logging failed. Please report this.",
        ) from err

    return {"ok": True}


# ---------------------------------------------------------------------------
# POST /auth/verify  (step 2: OTP check, unchanged)
# ---------------------------------------------------------------------------


@router.post("/auth/verify", status_code=200)
@limiter.limit("5/minute")
def verify_mfa_code(
    request: Request,
    auth_repo=Depends(get_auth_repo),
    audit_repo=Depends(get_audit_repo),
    practice_id: str = Depends(get_practice_id),
):
    """
    Step 2 of 2-factor login: verify the 6-digit OTP and issue a session.

    Accepts: {"email": "user@domain.com", "code": "047823"}

    On success: returns 200 and sets an HttpOnly session cookie.
    On failure: returns 422 with INVALID_AUTH_CODE for all failure modes.

    The session cookie attributes:
    - HttpOnly: not readable by JavaScript
    - Secure: HTTPS only
    - SameSite=Strict: no cross-site requests
    - Max-Age: SESSION_COOKIE_MAX_AGE seconds

    Audit: logs auth.login.succeeded on success; auth.login.failed on any
    INVALID_AUTH_CODE. The failed event is logged before re-raising so the
    422 response to the client is unchanged.
    """
    body = read_json_body(request)

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
            try:
                audit_repo.log_event(
                    practice_id=practice_id,
                    actor_email=email,
                    action="auth.login.failed",
                    ip_address=ip_address,
                    detail={"email": email, "reason": "verification_failed"},
                )
            except Exception as err:
                logger.exception("Audit log write failed for action auth.login.failed")
                raise HTTPException(
                    status_code=500,
                    detail="Action succeeded but audit logging failed. Please report this.",
                ) from err
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
    except Exception as err:
        logger.exception("Audit log write failed for action auth.login.succeeded")
        raise HTTPException(
            status_code=500,
            detail="Action succeeded but audit logging failed. Please report this.",
        ) from err

    response = JSONResponse(content={"ok": True})
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=session_id,
        httponly=True,
        secure=True,
        samesite="strict",
        max_age=SESSION_COOKIE_MAX_AGE,
    )
    return response


def _send_reset_email_background(
    email: str,
    raw_token: str,
    delivery_service,
) -> None:
    """
    Background task: deliver the password reset/setup email.

    Called after the response has already been returned to the client, so
    the Mailgun HTTP round trip cannot introduce a response-time difference
    between registered and unregistered emails. Delivery failure is reported
    to Sentry; no cleanup is needed since the reset token remains valid for
    a later retry regardless of whether this delivery attempt succeeded.
    """
    try:
        delivery_service.send_admin_invitation(email, raw_token)
        logger.info("auth.request_reset.sent: %s", email)
    except Exception:
        logger.exception("auth.request_reset.delivery_failed: %s", email)
        sentry_sdk.capture_exception()


def _process_password_reset(
    email: str,
    auth_repo,
    delivery_service,
    start: float,
    background_tasks: BackgroundTasks,
) -> None:
    """
    Look up the user, apply the fixed delay, and queue the reset email if found.

    Called directly from request_password_reset, which is now a plain `def`
    handler dispatched onto the anyio threadpool — the fixed delay
    (time.sleep()) and the lookup/token generation (blocking psycopg2 calls)
    are off the event loop because the whole handler runs on a worker thread.

    Email delivery is dispatched as a BackgroundTask, exactly as
    POST /auth/login does, so the Mailgun HTTP round trip happens after the
    200 response is sent and cannot be timed by an attacker to distinguish
    a registered address from an unregistered one.
    """
    from app.services.admin.auth_service import _fixed_delay

    user = auth_repo.get_user_by_email(email)

    # Fixed delay applied regardless of whether the user exists, to prevent
    # an attacker from distinguishing DB hit vs miss via response time.
    _fixed_delay(start)

    if user is not None:
        raw_token = auth_service.generate_reset_token(user["id"], auth_repo)
        background_tasks.add_task(
            _send_reset_email_background,
            email,
            raw_token,
            delivery_service,
        )
    else:
        logger.warning("auth.request_reset.unknown_email: %s", email)


# ---------------------------------------------------------------------------
# POST /auth/request-reset
# ---------------------------------------------------------------------------


@router.post("/auth/request-reset", status_code=200)
@limiter.limit("5/minute")
def request_password_reset(
    request: Request,
    background_tasks: BackgroundTasks,
    auth_repo=Depends(get_auth_repo),
    delivery_service=Depends(get_admin_delivery_service),
    practice_id: str = Depends(get_practice_id),
):
    """
    Request a password reset/setup link for an admin email address.

    Accepts: {"email": "user@domain.com"}

    Always returns 200 regardless of whether the email is registered.
    A fixed delay is applied before the user lookup result is acted upon
    to prevent an attacker from distinguishing registered from unregistered
    addresses via DB I/O timing differences.

    If the email is registered, a reset token is generated synchronously
    and the setup email is dispatched as a BackgroundTask (see
    _send_reset_email_background) so the Mailgun HTTP round trip happens
    after the response is sent — otherwise that round trip alone would
    reintroduce the timing leak the fixed delay is meant to prevent. If
    not registered, the request is silently discarded.

    No audit log is written. Writing an audit log here would require
    recording whether the email was found, which would enumerate registered
    addresses in the audit trail — the opposite of the intended behaviour.
    """
    import time

    start = time.monotonic()

    body = read_json_body(request)

    if not isinstance(body, dict) or "email" not in body:
        raise INVALID_PAYLOAD('Body must be {"email": "..."}')

    email = body["email"]
    if not isinstance(email, str) or not email.strip():
        raise INVALID_PAYLOAD("email must be a non-empty string")

    email = email.strip().lower()

    _process_password_reset(email, auth_repo, delivery_service, start, background_tasks)

    return {"ok": True}


# ---------------------------------------------------------------------------
# POST /auth/set-password
# ---------------------------------------------------------------------------


@router.post("/auth/set-password", status_code=200)
@limiter.limit("5/minute")
def set_password(
    request: Request,
    auth_repo=Depends(get_auth_repo),
    practice_id: str = Depends(get_practice_id),
):
    """
    Set a new password using a valid reset/setup token.

    Accepts: {"token": "...", "password": "..."}

    The token is the raw value from the #reset:{token} URL hash fragment.
    It is verified by hashing with SHA-256 and looking up the digest in the
    database. Tokens are single-use and expire after 1 hour.

    Returns 422 INVALID_RESET_TOKEN if the token is absent, expired, or
    already consumed.
    Returns 422 WEAK_PASSWORD if the password does not meet strength
    requirements, with a specific feedback message from zxcvbn.
    Returns 200 {"ok": true} on success.

    No audit log is written for set-password — it is an unauthenticated
    endpoint invoked before the user has a session. The password_changed_at
    column on admin_users provides the compliance audit trail.
    """
    body = read_json_body(request)

    if not isinstance(body, dict):
        raise INVALID_PAYLOAD("Body must be a JSON object")

    token = body.get("token")
    password = body.get("password")

    if not isinstance(token, str) or not token.strip():
        raise INVALID_PAYLOAD("token must be a non-empty string")
    if not isinstance(password, str) or not password:
        raise INVALID_PAYLOAD("password must be a non-empty string")

    token = token.strip()

    user_id = auth_service.verify_reset_token(token, auth_repo)
    auth_service.set_new_password(user_id, password, auth_repo)

    logger.info("auth.set_password.success: user_id=%s", user_id)
    return {"ok": True}


# ---------------------------------------------------------------------------
# POST /auth/logout
# ---------------------------------------------------------------------------


@router.post("/auth/logout", status_code=200)
def logout(
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
        except Exception as err:
            logger.exception("Audit log write failed for action auth.logout")
            raise HTTPException(
                status_code=500,
                detail="Action succeeded but audit logging failed. Please report this.",
            ) from err

    response = JSONResponse(content={"ok": True})
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value="",
        httponly=True,
        secure=True,
        samesite="strict",
        max_age=0,
    )
    return response

"""
Admin authentication boundary.

Defines AdminContext and the require_admin FastAPI dependency.

Authentication is exclusively via session cookie (HttpOnly, initially set
by POST /admin/auth/verify). Session cookie is the only authentication
path.

Sessions use a sliding-window TTL: every successful call through
require_admin extends the session's expiry and re-issues the cookie, so
the cookie set by /auth/verify is not the only place it is written.

Session-based auth rules:
- Reads session_id from the HttpOnly cookie set by POST /admin/auth/verify.
- Calls auth_repo.get_session_context(session_id) to validate and resolve
  practice_id, email, user_id, and session_id.
- Returns HTTP 401 if the cookie is absent or the session is not found
  or has expired.
- On success, best-effort extends the session's expiry in the DB and
  re-issues the Set-Cookie header with a fresh Max-Age, matching the
  cookie attributes set at login.

This module is a security boundary kept to a minimal import surface: it
imports only stdlib, FastAPI, and app.core.state_keys (a leaf module that
itself imports nothing). It deliberately does NOT import the repository or
wiring modules. Instead it depends on the AuthProvider abstraction below
(dependency inversion): require_admin needs only an object that satisfies
get_session_context, not the concrete AuthRepository or the concrete
app/core/wiring construction module.

This is a deliberate design choice, not an oversight that it skips the
app/core/dependencies.get_auth_repo getter. dependencies.py centralises
app.state access at the cost of importing the full repository-and-service
closure at module load. For a boundary that may be imported early in the
startup chain, keeping that closure out is the right tradeoff, and the
AuthProvider Protocol already supplies the type safety the getter would
otherwise provide. The one thing the getter would have unified -- the
app.state attribute name -- is shared via the AUTH_REPO constant in
app/core/state_keys.py so it cannot drift. tests/test_admin_context.py
pins this import surface in a subprocess so a future import of the wiring
closure into this module fails CI.

The AuthProvider Protocol below documents the subset of AuthRepository
used by this module without importing the repository class itself.

require_admin is deliberately a sync `def`, not `async def`. FastAPI runs
sync dependencies in the threadpool rather than on the event loop, and
get_session_context and update_session_expiry are blocking psycopg2 calls
that would otherwise stall the event loop on every authenticated admin
request.
"""

import logging
from typing import Any, Protocol, runtime_checkable

from fastapi import HTTPException, Request, Response

from app.core.state_keys import AUTH_REPO

logger = logging.getLogger(__name__)

# Session cookie name. Must match the name set in POST /admin/auth/verify
# and cleared in POST /admin/auth/logout.
SESSION_COOKIE_NAME = "session_id"

# Session TTL in minutes. Used by verify_mfa_code in auth_service.py and
# by the Set-Cookie Max-Age attribute in the verify endpoint.
#
# Sessions slide: each authenticated request through require_admin extends
# expiry by another SESSION_TTL_MINUTES, so an active admin never hits this
# limit. It only ends a session after SESSION_TTL_MINUTES of inactivity.
# Make this an env-var if different TTLs are ever needed per deployment.
SESSION_TTL_MINUTES = 60

# Cookie Max-Age in seconds (must match SESSION_TTL_MINUTES).
SESSION_COOKIE_MAX_AGE = SESSION_TTL_MINUTES * 60


# ---------------------------------------------------------------------------
# AdminContext
# ---------------------------------------------------------------------------


class AdminContext:
    """
    Resolved authentication context for an admin request.

    practice_id:  the practice this user belongs to.
    user_id:      UUID string of the authenticated admin_users row.
    auth_method:  "session_cookie" — the only supported authentication path.
    actor_email:  email address of the authenticated user, used for audit
                  logging.
    session_id:   the raw session UUID string from the cookie, used for
                  audit logging.
    """

    __slots__ = ("practice_id", "user_id", "auth_method", "actor_email", "session_id")

    def __init__(
        self,
        practice_id: str,
        user_id: str,
        auth_method: str,
        actor_email: str,
        session_id: str,
    ):
        self.practice_id = practice_id
        self.user_id = user_id
        self.auth_method = auth_method
        self.actor_email = actor_email
        self.session_id = session_id


# ---------------------------------------------------------------------------
# AuthProvider Protocol
# ---------------------------------------------------------------------------


@runtime_checkable
class AuthProvider(Protocol):
    """
    Structural protocol for the subset of AuthRepository used here.

    Defined in this module to avoid importing AuthRepository directly,
    which would violate the no-project-module-imports constraint if the
    import graph ever changes. Any object implementing get_session_context
    and update_session_expiry satisfies this protocol.

    get_session_context return value keys (when not None):
        user_id (str), role (str), practice_id (str), email (str),
        session_id (str).
    """

    def get_session_context(self, session_id: str) -> dict[str, Any] | None: ...

    def update_session_expiry(self, session_id: str, ttl_minutes: int) -> None: ...


# ---------------------------------------------------------------------------
# require_admin dependency
# ---------------------------------------------------------------------------


def require_admin(request: Request, response: Response) -> AdminContext:
    """
    FastAPI dependency. Validates session cookie and returns AdminContext.

    1. Read session_id from the HttpOnly cookie.
    2. Call auth_repo.get_session_context(session_id).
    3. If context is None (session not found or expired), raise HTTP 401.
    4. Best-effort: extend the session's expiry and re-issue the cookie
       with a fresh Max-Age, implementing the sliding-window TTL. Failures
       here are logged and swallowed — the request still proceeds, since
       the session was already validated in step 2. A DB outage would have
       failed that validation anyway, so this only covers transient
       refresh failures.
    5. Return AdminContext populated with practice_id, user_id, role,
       actor_email, and session_id from the context dict.

    Raises:
        HTTP 401 if no valid session cookie is present or the session has
        expired.
    """
    auth_repo: AuthProvider = getattr(request.app.state, AUTH_REPO)

    session_id = request.cookies.get(SESSION_COOKIE_NAME)
    if not session_id:
        raise HTTPException(
            status_code=401,
            detail="Authentication required.",
        )

    context = auth_repo.get_session_context(session_id)
    if context is None:
        raise HTTPException(
            status_code=401,
            detail="Session expired or not found.",
        )

    try:
        auth_repo.update_session_expiry(session_id, SESSION_TTL_MINUTES)
        response.set_cookie(
            key=SESSION_COOKIE_NAME,
            value=session_id,
            httponly=True,
            secure=True,
            samesite="strict",
            max_age=SESSION_COOKIE_MAX_AGE,
        )
    except Exception:
        logger.exception("Session expiry refresh failed for session %s", session_id)

    return AdminContext(
        practice_id=context["practice_id"],
        user_id=context["user_id"],
        auth_method="session_cookie",
        actor_email=context["email"],
        session_id=context["session_id"],
    )

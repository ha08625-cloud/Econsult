"""
Admin authentication boundary.

Defines AdminContext and the require_admin FastAPI dependency.

Authentication is exclusively via session cookie (HttpOnly, set by
POST /admin/auth/verify). There is no bearer-token or DEV_MODE fallback
path — the MFA email flow is fast enough for local development.

Session-based auth rules:
- Reads session_id from the HttpOnly cookie set by POST /admin/auth/verify.
- Calls auth_repo.get_session_context(session_id) to validate and resolve
  practice_id, email, user_id, and session_id.
- Returns HTTP 401 if the cookie is absent or the session is not found
  or has expired.

This module must never import any project module other than app.core.db.
Only stdlib, FastAPI, and psycopg2.

The AuthProvider Protocol below documents the subset of AuthRepository
used by this module without importing the repository class itself, which
would create a circular dependency risk if admin_context is ever imported
early in the startup chain.
"""

import logging
from typing import Optional, Dict, Any, Protocol, runtime_checkable

from fastapi import Request, HTTPException

logger = logging.getLogger(__name__)

# Session cookie name. Must match the name set in POST /admin/auth/verify
# and cleared in POST /admin/auth/logout.
SESSION_COOKIE_NAME = "session_id"

# Session TTL in minutes. Used by verify_mfa_code in auth_service.py and
# by the Set-Cookie Max-Age attribute in the verify endpoint.
# 24 hours is appropriate for an infrequently-used admin portal.
# Make this an env-var if different TTLs are ever needed per deployment.
SESSION_TTL_MINUTES = 60 * 24

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
    auth_method:  "session_cookie" | "bearer_token" | "dev_any".
                  bearer_token and dev_any are DEV_MODE fallback paths only.
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
    satisfies this protocol.

    get_session_context return value keys (when not None):
        user_id (str), role (str), practice_id (str), email (str),
        session_id (str).
    """

    def get_session_context(self, session_id: str) -> Optional[Dict[str, Any]]:
        ...


# ---------------------------------------------------------------------------
# require_admin dependency
# ---------------------------------------------------------------------------

async def require_admin(request: Request) -> AdminContext:
    """
    FastAPI dependency. Validates session cookie and returns AdminContext.

    1. Read session_id from the HttpOnly cookie.
    2. Call auth_repo.get_session_context(session_id).
    3. If context is None (session not found or expired), raise HTTP 401.
    4. Return AdminContext populated with practice_id, user_id, role,
       actor_email, and session_id from the context dict.

    Raises:
        HTTP 401 if no valid session cookie is present or the session has
        expired.
    """
    auth_repo: AuthProvider = request.app.state.auth_repo

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

    return AdminContext(
        practice_id=context["practice_id"],
        user_id=context["user_id"],
        auth_method="session_cookie",
        actor_email=context["email"],
        session_id=context["session_id"],
    )
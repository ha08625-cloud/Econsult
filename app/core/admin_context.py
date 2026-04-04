"""
Admin authentication boundary.

Defines AdminContext and the require_admin FastAPI dependency.

Phase 1B: session-cookie MFA. The bearer-token path is retained as a
DEV_MODE fallback so existing tests continue to pass unchanged during
the transition period. It will be removed in a later cleanup pass.

Session-based auth rules:
- Reads session_id from the HttpOnly cookie set by POST /admin/auth/verify.
- Calls auth_repo.get_session_context(session_id) to validate and resolve
  practice_id and role.
- Returns HTTP 401 (SESSION_EXPIRED) if the cookie is absent or the session
  is not found / has expired.

DEV_MODE bearer-token fallback rules:
- Active only when DEV_MODE=1 AND no session cookie is present.
- In DEV_MODE with no ADMIN_TOKEN set: any non-empty bearer token is accepted.
- If ADMIN_TOKEN is set: token must match exactly.

This module must never import any project module other than app.core.db.
Only stdlib, FastAPI, and psycopg2.

The AuthProvider Protocol below documents the subset of AuthRepository
used by this module without importing the repository class itself, which
would create a circular dependency risk if admin_context is ever imported
early in the startup chain.
"""

import os
import logging
from typing import Optional, Dict, Any, Protocol, runtime_checkable

from fastapi import Request, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

logger = logging.getLogger(__name__)

_bearer_scheme = HTTPBearer(auto_error=False)

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

    practice_id: the practice this user belongs to.
    role: "admin" or "staff" (from admin_users.role).
    auth_method: "session_cookie" | "bearer_token" | "dev_any".
                 bearer_token and dev_any are DEV_MODE fallback paths only.
    """
    __slots__ = ("practice_id", "role", "auth_method")

    def __init__(self, practice_id: str, role: str, auth_method: str):
        self.practice_id = practice_id
        self.role = role
        self.auth_method = auth_method


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
        user_id (str), role (str), practice_id (str)
    """

    def get_session_context(self, session_id: str) -> Optional[Dict[str, Any]]:
        ...


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# Intentionally duplicated from main.py. This module must never import
# any project module, so the helper cannot be shared.
def _is_dev_mode() -> bool:
    return os.environ.get("DEV_MODE", "").lower() in ("1", "true")


# ---------------------------------------------------------------------------
# require_admin dependency
# ---------------------------------------------------------------------------

async def require_admin(request: Request) -> AdminContext:
    """
    FastAPI dependency. Validates session cookie and returns AdminContext.

    Primary path (production and DEV_MODE):
    1. Read session_id from the HttpOnly cookie.
    2. Call auth_repo.get_session_context(session_id).
    3. If context is None (session not found or expired), raise HTTP 401.
    4. Return AdminContext with auth_method="session_cookie".

    DEV_MODE fallback (only when no session cookie is present):
    5. Attempt bearer-token auth using ADMIN_TOKEN env var.
    6. If ADMIN_TOKEN is set: require exact match.
    7. If ADMIN_TOKEN is not set in DEV_MODE: accept any non-empty token.
    8. Return AdminContext with auth_method="bearer_token" or "dev_any".

    Raises:
        HTTP 401 if no valid session and no valid DEV_MODE token.
    """
    auth_repo: AuthProvider = request.app.state.auth_repo
    practice_id: str = request.app.state.practice_id

    # --- Primary path: session cookie ---
    session_id = request.cookies.get(SESSION_COOKIE_NAME)
    if session_id:
        context = auth_repo.get_session_context(session_id)
        if context is None:
            raise HTTPException(
                status_code=401,
                detail="Session expired or not found.",
            )
        return AdminContext(
            practice_id=context["practice_id"],
            role=context["role"],
            auth_method="session_cookie",
        )

    # --- DEV_MODE bearer-token fallback ---
    if _is_dev_mode():
        credentials: Optional[HTTPAuthorizationCredentials] = await _bearer_scheme(request)
        if credentials is not None and credentials.credentials.strip():
            token = credentials.credentials
            admin_token = os.environ.get("ADMIN_TOKEN", "")
            if admin_token:
                if token != admin_token:
                    raise HTTPException(status_code=401, detail="Invalid token")
                auth_method = "bearer_token"
            else:
                auth_method = "dev_any"
            # DEV_MODE fallback returns a synthetic role of "admin" because
            # there is no real user record to look up. The practice_id comes
            # from app.state (same as the old implementation).
            return AdminContext(
                practice_id=practice_id,
                role="admin",
                auth_method=auth_method,
            )

    raise HTTPException(
        status_code=401,
        detail="Authentication required.",
    )
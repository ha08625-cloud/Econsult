"""
Admin authentication boundary.

Defines AdminContext and the require_admin FastAPI dependency.

Phase 2: validates a Bearer token against the ADMIN_TOKEN environment variable.
Phase 1B: this file is replaced entirely with session-based MFA. Nothing else changes.

Rules:
- Authorization header is always required, even in DEV_MODE
- In DEV_MODE with no ADMIN_TOKEN set: any non-empty bearer token is accepted
- If ADMIN_TOKEN is set: token must match exactly
- Missing or empty bearer value always returns 401

This module must never import any project module.
Only stdlib and FastAPI.
"""

import os
from dataclasses import dataclass

from fastapi import Request, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials


_bearer_scheme = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class AdminContext:
    practice_id: str
    auth_method: str  # "bearer_token" | "dev_any"


# Intentionally duplicated from main.py. admin_context must never import
# any project module (see arch_admin.md), so this cannot be shared.
def _is_dev_mode() -> bool:
    return os.environ.get("DEV_MODE", "").lower() in ("1", "true")


async def require_admin(request: Request) -> AdminContext:
    """
    FastAPI dependency. Validates the Bearer token and returns an AdminContext.

    Reads practice_id from request.app.state.practice_id.
    Reads ADMIN_TOKEN from environment.

    Raises HTTP 401 if:
    - Authorization header is missing
    - Bearer value is empty
    - Token does not match ADMIN_TOKEN (when ADMIN_TOKEN is set)
    """
    # Use the bearer scheme to parse the header
    credentials: HTTPAuthorizationCredentials | None = await _bearer_scheme(request)

    if credentials is None or not credentials.credentials.strip():
        raise HTTPException(status_code=401, detail="Authorization header required")

    token = credentials.credentials
    admin_token = os.environ.get("ADMIN_TOKEN", "")

    if admin_token:
        # Production path: validate against known token
        if token != admin_token:
            raise HTTPException(status_code=401, detail="Invalid token")
        auth_method = "bearer_token"
    elif _is_dev_mode():
        # Dev path: any non-empty token accepted
        auth_method = "dev_any"
    else:
        # ADMIN_TOKEN not set and not in DEV_MODE — should have been caught at startup
        # Fail closed rather than accidentally granting access
        raise HTTPException(status_code=401, detail="Admin authentication not configured")

    practice_id = request.app.state.practice_id

    return AdminContext(practice_id=practice_id, auth_method=auth_method)

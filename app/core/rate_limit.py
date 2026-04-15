"""
app/core/rate_limit.py

Rate limiter configuration.

Instantiates a single module-level Limiter that is shared across all routers.
Import `limiter` from this module wherever a @limiter.limit() decorator is needed.

Storage:
    Uses limits.storage.MemoryStorage (the slowapi default). This is intentional —
    the deployment is a single web worker processing ~50 forms per day.
    In-memory storage is sufficient and avoids the operational overhead of Redis.
    Rate limit counters reset on process restart, which is acceptable at this scale.

Key function:
    Uses extract_ip from app.core.http_utils rather than slowapi's built-in
    get_remote_address. extract_ip correctly handles X-Forwarded-For and X-Real-IP
    headers for the Railway deployment, where requests arrive via a reverse proxy.
    slowapi's get_remote_address reads only request.client.host, which would always
    resolve to the proxy IP rather than the real client IP.
"""

from starlette.requests import Request

from slowapi import Limiter

from app.core.http_utils import extract_ip


def _ip_key(request: Request) -> str:
    """
    Extract the real client IP from a Starlette Request.

    Wraps extract_ip so it matches the signature slowapi expects:
    a callable that accepts a Request and returns a string.

    Falls back to "unknown" if no IP can be determined, which ensures
    slowapi always receives a valid non-None key string.
    """
    return (
        extract_ip(
            request.headers,
            request.client.host if request.client else None,
        )
        or "unknown"
    )


limiter = Limiter(key_func=_ip_key)
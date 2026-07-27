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
    Uses extract_ip from app.utils.http_utils rather than slowapi's built-in
    get_remote_address. extract_ip correctly handles X-Forwarded-For and X-Real-IP
    headers for the Railway deployment, where requests arrive via a reverse proxy.
    slowapi's get_remote_address reads only request.client.host, which would always
    resolve to the proxy IP rather than the real client IP.
"""

import logging

from slowapi import Limiter
from starlette.requests import Request

from app.utils.http_utils import extract_ip

logger = logging.getLogger(__name__)


# slowapi/extension.py:496 dispatches on inspect.signature(lim.key_func)
# containing a parameter named literally `request`. Ours is named correctly —
# renaming it drops slowapi to calling key_func() with no arguments, which
# raises TypeError.
def _ip_key(request: Request) -> str:
    """
    Extract the real client IP from a Starlette Request.

    Wraps extract_ip so it matches the signature slowapi expects:
    a callable that accepts a Request and returns a string.

    Falls back to "unknown" if no IP can be determined, which ensures
    slowapi always receives a valid non-None key string.
    """
    client_host = request.client.host if request.client else None
    resolved = extract_ip(request.headers, client_host)

    if resolved is not None and resolved == client_host:
        # extract_ip fell all the way back to the direct connection host,
        # which on Railway is the internal proxy — identical for every
        # client. Every caller collapses into one rate-limit bucket, which
        # turns a per-IP limit into a global one.
        logger.error(
            "IP resolution degraded to client_host (%s); rate limiting is "
            "no longer per-client",
            resolved,
        )

    return resolved or "unknown"


limiter = Limiter(key_func=_ip_key)

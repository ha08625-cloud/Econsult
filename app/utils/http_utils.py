"""
app/core/http_utils.py

Shared HTTP utility helpers.

Functions here are used by routers and repositories that need access to
request-level metadata such as client IP addresses.
"""

from typing import Optional


def extract_ip(
    headers,
    client_host: Optional[str],
) -> Optional[str]:
    """
    Extract the real client IP address from request headers.

    Reads X-Forwarded-For first (taking only the first value, which is
    the original client IP before any proxy hops), then X-Real-IP, then
    falls back to the direct connection host.

    headers should be a mapping that supports .get() — pass
    request.headers from FastAPI. client_host should be
    request.client.host or None.

    Returns None if no IP can be determined.
    """
    forwarded_for = headers.get("x-forwarded-for")
    if forwarded_for:
        # X-Forwarded-For may be a comma-separated list: "client, proxy1, proxy2"
        # The first entry is the original client IP.
        return forwarded_for.split(",")[0].strip()

    real_ip = headers.get("x-real-ip")
    if real_ip:
        return real_ip.strip()

    return client_host or None
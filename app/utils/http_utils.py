"""
app/utils/http_utils.py

Shared HTTP utility helpers.

Functions here are used by routers and repositories that need access to
request-level metadata such as client IP addresses.
"""

import ipaddress


def _is_global(candidate: str) -> bool:
    try:
        return ipaddress.ip_address(candidate).is_global
    except ValueError:
        return False


def extract_ip(
    headers,
    client_host: str | None,
) -> str | None:
    """
    Extract the real client IP address from request headers.

    X-Forwarded-For is a list proxies *append* to, so the client's own
    entry is on the left and the most recently added (and therefore most
    trustworthy) hop is on the right. Walking the list right-to-left and
    trusting the first globally-routable entry means we don't need to know
    how many internal proxy hops sit in front of the app: Railway's internal
    proxy addresses are private (10.0.0.0/8, fd00::/8, etc.) and are skipped,
    while a real client arriving over the public internet is globally
    routable. `ipaddress.ip_address(s).is_global` correctly excludes
    private, loopback, link-local, CGNAT (100.64.0.0/10) and documentation
    ranges, so an attacker-supplied entry to the left of the real proxy hop
    can never be mistaken for it — they cannot inject an entry *after* the
    one the proxy adds.

    This breaks if a CDN sits in front of Railway: the CDN's public IP
    would become the rightmost global entry and would be trusted instead
    of the real client.

    If no entry in X-Forwarded-For is globally routable, falls back to
    X-Real-IP (same validity check), then to the direct connection host.

    headers should be a mapping that supports .get() — pass
    request.headers from FastAPI. client_host should be
    request.client.host or None.

    Returns None if no IP can be determined.
    """
    forwarded_for = headers.get("x-forwarded-for")
    if forwarded_for:
        entries = [entry.strip() for entry in forwarded_for.split(",")]
        for entry in reversed(entries):
            if entry and _is_global(entry):
                return entry

    real_ip = headers.get("x-real-ip")
    if real_ip:
        real_ip = real_ip.strip()
        if real_ip and _is_global(real_ip):
            return real_ip

    return client_host or None

"""
Unit tests for app.utils.http_utils.extract_ip.

extract_ip only calls .get() on the headers argument, so plain dicts are
used as fixtures rather than FastAPI/Starlette Headers objects.
"""

import pytest

from app.utils.http_utils import extract_ip

CASES = [
    pytest.param(
        {"x-forwarded-for": "1.2.3.4, 8.8.8.8"},
        None,
        "8.8.8.8",
        id="spoofed-leftmost-entry-ignored",
    ),
    pytest.param(
        {"x-forwarded-for": "10.0.0.1, 8.8.8.8"},
        None,
        "8.8.8.8",
        id="spoofed-private-leftmost-entry-ignored",
    ),
    pytest.param(
        {"x-forwarded-for": "8.8.8.8, 10.0.0.1, 10.0.0.2"},
        None,
        "8.8.8.8",
        id="private-proxy-hops-on-right-skipped",
    ),
    pytest.param(
        {"x-forwarded-for": "8.8.8.8"},
        None,
        "8.8.8.8",
        id="single-global-entry-returned-as-is",
    ),
    pytest.param(
        {"x-forwarded-for": "10.0.0.1, 10.0.0.2", "x-real-ip": "1.1.1.1"},
        None,
        "1.1.1.1",
        id="all-private-falls-through-to-x-real-ip",
    ),
    pytest.param(
        {"x-forwarded-for": "10.0.0.1, 10.0.0.2"},
        "203.0.113.5",
        "203.0.113.5",
        id="all-private-falls-through-to-client-host",
    ),
    pytest.param(
        {"x-forwarded-for": "junk, 8.8.8.8"},
        None,
        "8.8.8.8",
        id="malformed-entry-does-not-raise",
    ),
    pytest.param(
        {"x-forwarded-for": ", , 8.8.8.8,  "},
        None,
        "8.8.8.8",
        id="empty-and-whitespace-entries-do-not-raise",
    ),
    pytest.param(
        {},
        "203.0.113.5",
        "203.0.113.5",
        id="no-headers-at-all-returns-client-host",
    ),
    pytest.param(
        {},
        None,
        None,
        id="nothing-determinable-returns-none",
    ),
]


@pytest.mark.parametrize("headers, client_host, expected", CASES)
def test_extract_ip(headers, client_host, expected):
    assert extract_ip(headers, client_host) == expected

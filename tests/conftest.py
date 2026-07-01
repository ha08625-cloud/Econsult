"""
conftest.py

Pytest configuration and shared fixtures.

Fixtures:
    reset_rate_limiter — autouse fixture that resets slowapi's in-memory
    storage before every test. Without this, the module-level Limiter
    instance retains its counters across test boundaries, causing spurious
    429 failures in tests that simulate legitimate traffic after any test
    that fires multiple requests.

    NOTE: The reset call uses limiter._storage.reset(). This is the correct
    API for slowapi 0.1.x with limits.storage.MemoryStorage. If you upgrade
    either library and see AttributeError here, inspect type(limiter._storage)
    and its available methods to find the replacement.
"""

import pytest

from app.core.rate_limit import limiter


@pytest.fixture(autouse=True)
def reset_rate_limiter():
    """Reset slowapi in-memory counters before every test."""
    limiter._storage.reset()
    yield
    limiter._storage.reset()

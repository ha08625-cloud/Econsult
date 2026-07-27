"""
Integration tests for app/core/db.py — timeouts as the server actually applies them.

Requires TEST_DATABASE_URL in the environment.

tests/test_db.py proves the right parameters are passed to psycopg2. These
prove the server honours them: that the session really carries the timeouts,
and that an over-running statement is really cancelled.

Separate file rather than a section of test_db.py because the guardrail below
and the integration marker are both module-scoped — sharing a file would skip
the unit tests whenever TEST_DATABASE_URL is unset, which is how `make test`
runs.
"""

import os
import time

import pytest

if "TEST_DATABASE_URL" not in os.environ:
    pytest.skip(
        "TEST_DATABASE_URL not set — skipping integration tests to protect production data",
        allow_module_level=True,
    )

os.environ.setdefault("DATABASE_URL", os.environ["TEST_DATABASE_URL"])

import psycopg2  # noqa: E402

from app.core.db import get_conn  # noqa: E402

pytestmark = pytest.mark.integration

DATABASE_URL = os.environ["TEST_DATABASE_URL"]


def _show(conn, setting: str) -> str:
    with conn.cursor() as cur:
        cur.execute(f"SHOW {setting}")
        return cur.fetchone()[0]


# ---------------------------------------------------------------------------
# Session settings
# ---------------------------------------------------------------------------


def test_statement_timeout_is_applied_to_the_session():
    with get_conn(DATABASE_URL) as conn:
        assert _show(conn, "statement_timeout") == "10s"


def test_idle_in_transaction_timeout_is_applied_to_the_session():
    with get_conn(DATABASE_URL) as conn:
        assert _show(conn, "idle_in_transaction_session_timeout") == "30s"


def test_statement_timeout_override_is_applied_to_the_session():
    with get_conn(DATABASE_URL, statement_timeout_ms=120_000) as conn:
        assert _show(conn, "statement_timeout") == "2min"


def test_override_does_not_leak_into_the_next_connection():
    """Each connection is independent — an override is not sticky."""
    with get_conn(DATABASE_URL, statement_timeout_ms=120_000) as conn:
        assert _show(conn, "statement_timeout") == "2min"

    with get_conn(DATABASE_URL) as conn:
        assert _show(conn, "statement_timeout") == "10s"


# ---------------------------------------------------------------------------
# Enforcement
# ---------------------------------------------------------------------------


def test_over_running_statement_is_cancelled():
    """
    A statement past the timeout raises QueryCanceled rather than running on.

    Uses a short override so the test costs a second, not ten.
    """
    started = time.monotonic()

    with (
        pytest.raises(psycopg2.errors.QueryCanceled),
        get_conn(DATABASE_URL, statement_timeout_ms=1_000) as conn,
        conn.cursor() as cur,
    ):
        cur.execute("SELECT pg_sleep(30)")

    elapsed = time.monotonic() - started
    assert elapsed < 15, f"statement ran {elapsed:.1f}s — timeout did not fire"


def test_cancelled_statement_surfaces_query_canceled_not_interface_error():
    """
    The regression this ticket's rollback guard exists for.

    The cancellation leaves the connection in a state where rollback() can
    itself fail. Unguarded, that InterfaceError would replace the
    QueryCanceled and the operator would never learn a timeout occurred.
    """
    with (
        pytest.raises(psycopg2.errors.QueryCanceled) as excinfo,
        get_conn(DATABASE_URL, statement_timeout_ms=1_000) as conn,
        conn.cursor() as cur,
    ):
        cur.execute("SELECT pg_sleep(30)")

    assert "statement timeout" in str(excinfo.value).lower()


def test_connection_still_usable_after_a_normal_query():
    """Sanity check that the options string does not break ordinary use."""
    with get_conn(DATABASE_URL) as conn, conn.cursor() as cur:
        cur.execute("SELECT 1")
        assert cur.fetchone()[0] == 1


# ---------------------------------------------------------------------------
# Connect timeout
# ---------------------------------------------------------------------------


def test_connect_timeout_bounds_an_unreachable_host():
    """
    An unreachable database fails in seconds rather than hanging.

    192.0.2.0/24 is TEST-NET-1 (RFC 5737) and is guaranteed unroutable, so
    the connect attempt blocks until the timeout rather than being refused.
    """
    unreachable = "postgresql://user:password@192.0.2.1:5432/dbname"

    started = time.monotonic()
    with pytest.raises(psycopg2.OperationalError), get_conn(unreachable, connect_timeout_seconds=2):
        pass
    elapsed = time.monotonic() - started

    assert elapsed < 20, f"connect blocked for {elapsed:.1f}s — connect_timeout did not fire"

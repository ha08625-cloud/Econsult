"""
Unit tests for app/core/db.py — connection parameters and error handling.

No database required. psycopg2.connect is monkeypatched inside the db module
and the yielded connection is a stub, so these run under `make test`.

The integration counterpart, which proves the server actually honours the
timeouts, is tests/test_db_integration.py.
"""

import psycopg2
import pytest

from app.core import db


class FakeConn:
    """Minimal psycopg2 connection stub recording the calls made against it."""

    def __init__(self, rollback_error=None, close_error=None, commit_error=None):
        self.rollback_error = rollback_error
        self.close_error = close_error
        self.commit_error = commit_error
        self.committed = False
        self.rolled_back = False
        self.closed = False

    def commit(self):
        self.committed = True
        if self.commit_error is not None:
            raise self.commit_error

    def rollback(self):
        self.rolled_back = True
        if self.rollback_error is not None:
            raise self.rollback_error

    def close(self):
        self.closed = True
        if self.close_error is not None:
            raise self.close_error


@pytest.fixture
def captured_connect(monkeypatch):
    """
    Patch psycopg2.connect inside the db module.

    Returns a dict that fills in with the dsn and kwargs of the single
    connect call, plus the FakeConn that was handed back. Tests wanting a
    connection that misbehaves assign to captured["conn"] before calling
    get_conn.
    """
    captured: dict = {"conn": FakeConn()}

    def fake_connect(dsn, **kwargs):
        captured["dsn"] = dsn
        captured["kwargs"] = kwargs
        return captured["conn"]

    monkeypatch.setattr(db.psycopg2, "connect", fake_connect)
    return captured


DSN = "postgresql://user:password@host/dbname"


# ---------------------------------------------------------------------------
# Connection parameters
# ---------------------------------------------------------------------------


def test_dsn_is_passed_through_unmodified(captured_connect):
    """The DSN is never parsed or rewritten — timeouts ride as kwargs."""
    with db.get_conn(DSN):
        pass

    assert captured_connect["dsn"] == DSN


def test_client_side_timeouts_are_set(captured_connect):
    with db.get_conn(DSN):
        pass

    kwargs = captured_connect["kwargs"]
    assert kwargs["connect_timeout"] == db.CONNECT_TIMEOUT_SECONDS
    assert kwargs["keepalives"] == 1
    assert kwargs["keepalives_idle"] == db.KEEPALIVES_IDLE_SECONDS
    assert kwargs["keepalives_interval"] == db.KEEPALIVES_INTERVAL_SECONDS
    assert kwargs["keepalives_count"] == db.KEEPALIVES_COUNT
    assert kwargs["tcp_user_timeout"] == db.TCP_USER_TIMEOUT_MS


def test_keepalives_are_present_because_statement_timeout_cannot_cover_a_dead_peer(
    captured_connect,
):
    """
    Regression guard for the whole point of this module's timeout block.

    statement_timeout is enforced by the server and so cannot fire when the
    server is what vanished. If someone ever "simplifies" the connect call
    down to the two obvious timeouts, this fails.
    """
    with db.get_conn(DSN):
        pass

    kwargs = captured_connect["kwargs"]
    assert kwargs.get("keepalives") == 1, (
        "TCP keepalives are the only client-side bound on a server that "
        "disappears mid-query; statement_timeout cannot cover that case."
    )


def test_server_side_timeouts_ride_in_options(captured_connect):
    """
    Both server-side timeouts go through `options`, not a post-connect SET.

    Connections are opened per operation, so a SET would cost a round trip on
    every query in the system.
    """
    with db.get_conn(DSN):
        pass

    options = captured_connect["kwargs"]["options"]
    assert f"-c statement_timeout={db.STATEMENT_TIMEOUT_MS}" in options
    assert f"-c idle_in_transaction_session_timeout={db.IDLE_IN_TRANSACTION_TIMEOUT_MS}" in options


def test_defaults_match_the_documented_values(captured_connect):
    """Pin the constants themselves — arch_infrastructure.md quotes these."""
    assert db.CONNECT_TIMEOUT_SECONDS == 5
    assert db.STATEMENT_TIMEOUT_MS == 10_000
    assert db.IDLE_IN_TRANSACTION_TIMEOUT_MS == 30_000
    assert db.TCP_USER_TIMEOUT_MS == 30_000


# ---------------------------------------------------------------------------
# Per-call overrides
# ---------------------------------------------------------------------------


def test_statement_timeout_override_wins(captured_connect):
    """The deletion_job.py path."""
    with db.get_conn(DSN, statement_timeout_ms=120_000):
        pass

    options = captured_connect["kwargs"]["options"]
    assert "-c statement_timeout=120000" in options
    assert f"-c statement_timeout={db.STATEMENT_TIMEOUT_MS} " not in options


def test_overriding_one_timeout_leaves_the_others_at_their_defaults(captured_connect):
    with db.get_conn(DSN, statement_timeout_ms=120_000):
        pass

    kwargs = captured_connect["kwargs"]
    assert kwargs["connect_timeout"] == db.CONNECT_TIMEOUT_SECONDS
    assert (
        f"-c idle_in_transaction_session_timeout={db.IDLE_IN_TRANSACTION_TIMEOUT_MS}"
        in kwargs["options"]
    )


def test_all_timeouts_can_be_overridden_together(captured_connect):
    with db.get_conn(
        DSN,
        statement_timeout_ms=1,
        idle_in_transaction_timeout_ms=2,
        connect_timeout_seconds=3,
    ):
        pass

    kwargs = captured_connect["kwargs"]
    assert kwargs["connect_timeout"] == 3
    assert "-c statement_timeout=1" in kwargs["options"]
    assert "-c idle_in_transaction_session_timeout=2" in kwargs["options"]


def test_timeouts_are_keyword_only(captured_connect):
    """Guards against a positional second argument being read as a timeout."""
    with pytest.raises(TypeError), db.get_conn(DSN, 120_000):
        pass


# ---------------------------------------------------------------------------
# Transaction lifecycle
# ---------------------------------------------------------------------------


def test_commits_and_closes_on_success(captured_connect):
    with db.get_conn(DSN) as conn:
        pass

    assert conn.committed
    assert not conn.rolled_back
    assert conn.closed


def test_rolls_back_and_closes_on_failure(captured_connect):
    with pytest.raises(ValueError), db.get_conn(DSN):
        raise ValueError("body failed")

    conn = captured_connect["conn"]
    assert conn.rolled_back
    assert not conn.committed
    assert conn.closed


# ---------------------------------------------------------------------------
# Error masking
#
# A timeout leaves the connection dead, so rollback() and close() raise too.
# Unguarded, that secondary failure replaces the real one and the operator
# sees "connection already closed" instead of the timeout that caused it.
# ---------------------------------------------------------------------------


def test_failing_rollback_does_not_mask_the_original_error(captured_connect):
    captured_connect["conn"] = FakeConn(
        rollback_error=psycopg2.InterfaceError("connection already closed")
    )

    original = psycopg2.errors.QueryCanceled("canceling statement due to statement timeout")

    with pytest.raises(psycopg2.errors.QueryCanceled) as excinfo, db.get_conn(DSN):
        raise original

    assert excinfo.value is original


def test_failing_close_does_not_mask_the_original_error(captured_connect):
    captured_connect["conn"] = FakeConn(
        close_error=psycopg2.InterfaceError("connection already closed")
    )

    original = psycopg2.errors.QueryCanceled("canceling statement due to statement timeout")

    with pytest.raises(psycopg2.errors.QueryCanceled) as excinfo, db.get_conn(DSN):
        raise original

    assert excinfo.value is original


def test_rollback_and_close_both_failing_still_surfaces_the_original(captured_connect):
    captured_connect["conn"] = FakeConn(
        rollback_error=psycopg2.InterfaceError("connection already closed"),
        close_error=psycopg2.InterfaceError("connection already closed"),
    )

    original = psycopg2.errors.QueryCanceled("canceling statement due to statement timeout")

    with pytest.raises(psycopg2.errors.QueryCanceled) as excinfo, db.get_conn(DSN):
        raise original

    assert excinfo.value is original


def test_failing_close_on_the_success_path_is_swallowed(captured_connect):
    """
    The commit has already returned, so the work is durable. Raising here
    would turn a completed operation into a reported failure.
    """
    captured_connect["conn"] = FakeConn(
        close_error=psycopg2.InterfaceError("connection already closed")
    )

    with db.get_conn(DSN) as conn:
        pass

    assert conn.committed


def test_commit_failure_propagates_and_rolls_back(captured_connect):
    captured_connect["conn"] = FakeConn(
        commit_error=psycopg2.errors.QueryCanceled("canceling statement"),
        rollback_error=psycopg2.InterfaceError("connection already closed"),
    )

    with pytest.raises(psycopg2.errors.QueryCanceled), db.get_conn(DSN):
        pass

    assert captured_connect["conn"].closed


def test_rollback_failure_is_logged(captured_connect, caplog):
    captured_connect["conn"] = FakeConn(
        rollback_error=psycopg2.InterfaceError("connection already closed")
    )

    with (
        caplog.at_level("WARNING", logger=db.__name__),
        pytest.raises(ValueError),
        db.get_conn(DSN),
    ):
        raise ValueError("body failed")

    assert "Rollback failed" in caplog.text


# ---------------------------------------------------------------------------
# options string construction
# ---------------------------------------------------------------------------


def test_build_options_is_accepted_by_libpq():
    """
    Prove the options string and every kwarg parse as real libpq parameters.

    make_dsn validates against libpq's known-parameter list, so this catches
    a malformed options string or a parameter unsupported by the bundled
    libpq (tcp_user_timeout needs >= 12) without needing a live server.
    """
    dsn = psycopg2.extensions.make_dsn(
        DSN,
        connect_timeout=db.CONNECT_TIMEOUT_SECONDS,
        options=db._build_options(db.STATEMENT_TIMEOUT_MS, db.IDLE_IN_TRANSACTION_TIMEOUT_MS),
        keepalives=1,
        keepalives_idle=db.KEEPALIVES_IDLE_SECONDS,
        keepalives_interval=db.KEEPALIVES_INTERVAL_SECONDS,
        keepalives_count=db.KEEPALIVES_COUNT,
        tcp_user_timeout=db.TCP_USER_TIMEOUT_MS,
    )

    assert "tcp_user_timeout=30000" in dsn
    assert "statement_timeout=10000" in dsn

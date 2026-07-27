"""
Shared Postgres connection module.

This is the only file in the codebase that imports psycopg2.

Responsibilities:
- Provide get_conn(database_url): a context manager that opens a psycopg2
  connection, yields it, commits on success, rolls back on failure, closes on exit.
- Provide alembic_upgrade(): runs all pending Alembic migrations at startup.

The context manager yields the connection, not a cursor.
Each repository calls conn.cursor(cursor_factory=RealDictCursor) internally
and manages its own cursor lifecycle.

RealDictCursor returns RealDictRow objects which inherit from dict.
Existing dict(row) calls at all call sites continue to work correctly.
No call site performs isinstance checks against row types.

---------------------------------------------------------------------------
Timeouts
---------------------------------------------------------------------------

Every connection carries four independent bounds. None substitutes for
another, and the fourth is the one that is easy to leave out:

    connect_timeout       Postgres unreachable at connect time  (libpq)
    statement_timeout     slow query, lock wait, runaway scan   (server)
    idle_in_transaction   a transaction stalling while holding  (server)
      _session_timeout    a row lock
    keepalives +          the server or network vanishing       (kernel)
      tcp_user_timeout    mid-query

statement_timeout is enforced by the *server*, so it cannot fire when the
server is the thing that disappeared — the client simply blocks in recv().
TCP keepalives are the only client-side bound on that case, and it is not a
per-request problem here: every route is `async def` and calls these
synchronous psycopg2 functions directly on the event loop thread (see the
note in app/services/admin/auth_service.py), with uvicorn running a single
worker. One connection blocked in recv() therefore stalls every concurrent
request in the process, not just its own.

The two server-side timeouts are passed via the `options` connection
parameter rather than issued as `SET` statements after connect. Connections
are opened per operation — every repository method calls get_conn for
itself — so a `SET` would add a round trip to every query in the system.
`options` is applied by the server at session start at no cost.

These are tuning parameters with safe defaults, not deployment
configuration, so they are module constants rather than settings. get_conn
is called by four processes and two scripts, and only the web service
constructs WebSettings; routing these through settings.py would mean
threading configuration into every call site. Callers needing a different
bound pass it explicitly — deletion_job.py is the only one that does.

statement_timeout is deliberately loose. Every web-facing query is a
single-row lookup, but practice_repository.lock_practice issues a blocking
`SELECT ... FOR UPDATE` (not SKIP LOCKED) that legitimately waits on
contention, and the one genuinely long-running operation in the system —
the nightly bulk delete — overrides it explicitly. Treat 10s as a safety
valve rather than a latency target, and tighten it once there is production
data on real query latency.

Two portability notes:

- psycopg2.connect(dsn, **kwargs) merges kwargs into the DSN via make_dsn,
  with kwargs taking precedence. Nothing here parses or rewrites
  DATABASE_URL. Note the precedence direction: a DATABASE_URL carrying its
  own `options=` would be silently overridden by ours.
- tcp_user_timeout needs libpq >= 12 (psycopg2-binary 2.9.9 bundles 16, so
  it is accepted) and is a no-op on platforms without TCP_USER_TIMEOUT,
  notably macOS. Local macOS development gets keepalives but not the
  tighter bound. This is expected, not a bug.
"""

import logging
import os
from contextlib import contextmanager

import psycopg2
import psycopg2.extras
from alembic.config import Config

from alembic import command

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Alembic path resolution
# ---------------------------------------------------------------------------
# This file lives at app/core/db.py, so two parent steps reach the project root.
# An explicit existence check ensures a misconfigured path fails immediately
# with a clear error rather than an opaque Alembic failure at startup.

_HERE = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.normpath(os.path.join(_HERE, "..", ".."))
_ALEMBIC_INI = os.path.join(_PROJECT_ROOT, "alembic.ini")


def alembic_upgrade() -> None:
    """
    Run all pending Alembic migrations.

    Called once at application startup from main.py.
    If a migration fails, the application will fail to start — this is correct
    behaviour. A failed migration must prevent startup.
    """
    if not os.path.isfile(_ALEMBIC_INI):
        raise RuntimeError(f"alembic.ini not found at expected location: {_ALEMBIC_INI}")
    cfg = Config(_ALEMBIC_INI)
    command.upgrade(cfg, "head")


# ---------------------------------------------------------------------------
# Timeout defaults
# ---------------------------------------------------------------------------
# See the "Timeouts" section of the module docstring for the reasoning behind
# each of these. Callers override per call; there are no environment variables.

# libpq treats any value below 2 as 2.
CONNECT_TIMEOUT_SECONDS = 5

STATEMENT_TIMEOUT_MS = 10_000
IDLE_IN_TRANSACTION_TIMEOUT_MS = 30_000

# Roughly 60s to detect a dead peer (idle + interval * count), with
# tcp_user_timeout as the tighter bound where the platform supports it.
KEEPALIVES_IDLE_SECONDS = 30
KEEPALIVES_INTERVAL_SECONDS = 10
KEEPALIVES_COUNT = 3
TCP_USER_TIMEOUT_MS = 30_000


def _build_options(statement_timeout_ms: int, idle_in_transaction_timeout_ms: int) -> str:
    """Build the libpq `options` string carrying the two server-side timeouts."""
    return (
        f"-c statement_timeout={statement_timeout_ms} "
        f"-c idle_in_transaction_session_timeout={idle_in_transaction_timeout_ms}"
    )


# ---------------------------------------------------------------------------
# Connection context manager
# ---------------------------------------------------------------------------


@contextmanager
def get_conn(
    database_url: str,
    *,
    statement_timeout_ms: int = STATEMENT_TIMEOUT_MS,
    idle_in_transaction_timeout_ms: int = IDLE_IN_TRANSACTION_TIMEOUT_MS,
    connect_timeout_seconds: int = CONNECT_TIMEOUT_SECONDS,
):
    """
    Open a psycopg2 connection, commit on success, roll back on failure.

    Yields the connection. The caller is responsible for creating and
    closing its own cursor.

    Usage:
        with get_conn(database_url) as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(...)

    All timeouts default to the module constants; the keyword arguments exist
    for the rare caller whose work is legitimately long (deletion_job.py).
    A query exceeding statement_timeout raises psycopg2.errors.QueryCanceled
    (SQLSTATE 57014, an OperationalError subclass), which propagates to the
    caller like any other database error.
    """
    conn = psycopg2.connect(
        database_url,
        connect_timeout=connect_timeout_seconds,
        options=_build_options(statement_timeout_ms, idle_in_transaction_timeout_ms),
        keepalives=1,
        keepalives_idle=KEEPALIVES_IDLE_SECONDS,
        keepalives_interval=KEEPALIVES_INTERVAL_SECONDS,
        keepalives_count=KEEPALIVES_COUNT,
        tcp_user_timeout=TCP_USER_TIMEOUT_MS,
    )
    try:
        yield conn
        conn.commit()
    except Exception:
        # rollback() and close() both raise when the connection is already
        # dead — which is precisely the state a timeout leaves it in. Left
        # unguarded, that secondary failure replaces the real one, and the
        # operator sees "connection already closed" instead of the timeout
        # that caused it. Log and swallow so the original error survives.
        _safe_rollback(conn)
        raise
    finally:
        _safe_close(conn)


def _safe_rollback(conn) -> None:
    """Roll back, swallowing any failure so the original exception survives."""
    try:
        conn.rollback()
    except Exception as exc:
        logger.warning("Rollback failed while handling an earlier error: %s", exc)


def _safe_close(conn) -> None:
    """
    Close, swallowing any failure.

    Reached on both the success and failure paths. On the success path the
    commit has already returned, so the work is durable and a close failure
    is cosmetic; raising here would turn a completed operation into a failed
    one. On the failure path, swallowing keeps the original exception intact.
    """
    try:
        conn.close()
    except Exception as exc:
        logger.warning("Connection close failed: %s", exc)

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
"""

import os
from contextlib import contextmanager

import psycopg2
import psycopg2.extras
from alembic.config import Config
from alembic import command

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
        raise RuntimeError(
            f"alembic.ini not found at expected location: {_ALEMBIC_INI}"
        )
    cfg = Config(_ALEMBIC_INI)
    command.upgrade(cfg, "head")


# ---------------------------------------------------------------------------
# Connection context manager
# ---------------------------------------------------------------------------

@contextmanager
def get_conn(database_url: str):
    """
    Open a psycopg2 connection, commit on success, roll back on failure.

    Yields the connection. The caller is responsible for creating and
    closing its own cursor.

    Usage:
        with get_conn(database_url) as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(...)
    """
    conn = psycopg2.connect(database_url)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

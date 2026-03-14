"""
app/core/db.py — Shared Postgres connection module.

This is the only file in the codebase that imports psycopg2.

Responsibilities:
- Provide get_conn(database_url): a context manager that opens a psycopg2
  connection, yields it, commits on success, rolls back on failure, closes on exit.
- Provide init_database(database_url): creates all tables once at startup.

The context manager yields the connection, not a cursor.
Each repository calls conn.cursor(cursor_factory=RealDictCursor) internally
and manages its own cursor lifecycle.

RealDictCursor returns RealDictRow objects which inherit from dict.
Existing dict(row) calls at all call sites continue to work correctly.
No call site performs isinstance checks against row types.

Known gap: init_database() uses CREATE TABLE IF NOT EXISTS and is a
one-time bootstrapper for a fresh database. It does not handle future
schema changes. Alembic is the correct long-term solution and must be
adopted before any schema change is required.

Known gap (testing): tests currently run against the same Railway Postgres
instance as the deployed application. A dedicated test database must be
provisioned before a second developer joins or before any real patient data
is stored.
"""

from contextlib import contextmanager

import psycopg2
import psycopg2.extras


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


def init_database(database_url: str) -> None:
    """
    Create all application tables if they do not already exist.

    Called once at application startup from main.py.
    Safe to call on an already-initialised database — CREATE TABLE IF NOT EXISTS
    is a no-op when the table exists.

    Tables created:
    - runtime_state_versions  (RuntimeStateRepository)
    - practices               (PracticeRepository)
    - practice_signposting    (PracticeRepository)
    - submission_records      (SubmissionRepository)
    """
    with get_conn(database_url) as conn:
        with conn.cursor() as cur:

            # --- RuntimeStateRepository ---
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS runtime_state_versions (
                    runtime_id   TEXT        NOT NULL,
                    version      INTEGER     NOT NULL,
                    ruleset_hash TEXT        NOT NULL,
                    state_json   JSONB       NOT NULL,
                    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    is_closed    BOOLEAN     NOT NULL DEFAULT FALSE,
                    PRIMARY KEY (runtime_id, version)
                )
                """
            )

            # --- PracticeRepository ---
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS practices (
                    practice_id TEXT        PRIMARY KEY,
                    name        TEXT        NOT NULL,
                    email       TEXT        NOT NULL,
                    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
                """
            )

            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS practice_signposting (
                    practice_id      TEXT        NOT NULL REFERENCES practices(practice_id),
                    condition_id     TEXT        NOT NULL,
                    signposting_json TEXT        NOT NULL,
                    updated_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    PRIMARY KEY (practice_id, condition_id)
                )
                """
            )

            # --- SubmissionRepository ---
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS submission_records (
                    submission_id        TEXT        PRIMARY KEY,
                    practice_id          TEXT        NOT NULL,
                    condition_id         TEXT        NOT NULL,
                    clinical_output_json JSONB       NOT NULL,
                    audit_output_json    JSONB       NOT NULL,
                    submitted_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    delivery_status      TEXT        NOT NULL DEFAULT 'pending',
                    delivery_email       TEXT        NOT NULL,
                    delivered_at         TIMESTAMPTZ,
                    delivery_error       TEXT
                )
                """
            )

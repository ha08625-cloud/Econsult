"""
app/repositories/auth_repository.py

Database access for admin MFA authentication.

Handles three tables: admin_users, admin_auth_codes, admin_sessions.

This module must never:
- Contain business logic (cooldown checks, code generation, hashing)
- Import from service modules
- Import from routers

All business logic lives in app/services/auth_service.py.
All transport logic lives in app/services/delivery/admin_delivery_service.py.
Table creation is handled by Alembic migration 0014.
"""

import uuid
from datetime import datetime
from typing import Optional

from psycopg2.extras import RealDictCursor

from app.core.db import get_conn


class AuthRepository:
    def __init__(self, database_url: str):
        self.database_url = database_url

    # ------------------------------------------------------------------
    # admin_users
    # ------------------------------------------------------------------

    def get_user_by_email(self, email: str) -> Optional[dict]:
        """
        Return the admin_users row for the given email as a dict, or None
        if no matching row exists.

        Returned dict keys: id (str), email, practice_id, role, created_at.
        id is cast to str — psycopg2 returns UUID columns as uuid.UUID
        objects; callers expect strings throughout the auth layer.
        """
        with get_conn(self.database_url) as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT id::text, email, practice_id, role, created_at
                    FROM admin_users
                    WHERE email = %s
                    """,
                    (email,),
                )
                row = cur.fetchone()
        return dict(row) if row is not None else None

    def count_users_for_practice(self, practice_id: str) -> int:
        """
        Return the number of rows in admin_users for the given practice_id.

        Used at startup to decide whether to seed the initial admin user.
        Returns 0 if no users exist for the practice.
        """
        with get_conn(self.database_url) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT COUNT(*) FROM admin_users WHERE practice_id = %s",
                    (practice_id,),
                )
                row = cur.fetchone()
        return row[0] if row else 0

    def insert_user(self, email: str, practice_id: str, role: str) -> None:
        """
        Insert a new row into admin_users.

        Does not check for duplicates — the UNIQUE constraint on email will
        raise a psycopg2 IntegrityError if the email already exists.
        The caller (startup validation) is responsible for calling
        count_users_for_practice first to avoid a redundant insert.
        """
        with get_conn(self.database_url) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO admin_users (email, practice_id, role)
                    VALUES (%s, %s, %s)
                    """,
                    (email, practice_id, role),
                )

    # ------------------------------------------------------------------
    # admin_auth_codes
    # ------------------------------------------------------------------

    def upsert_auth_code(
        self,
        email: str,
        hashed_code: str,
        expires_at: datetime,
        last_requested_at: datetime,
    ) -> None:
        """
        Insert or replace the auth code record for the given email.

        Uses INSERT ... ON CONFLICT (email) DO UPDATE so that requesting a
        new code atomically replaces any existing in-flight code.
        attempts_count is reset to 0 on every upsert — a new code starts
        fresh regardless of how many times the old code was attempted.
        """
        with get_conn(self.database_url) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO admin_auth_codes
                        (email, hashed_code, expires_at, attempts_count, last_requested_at)
                    VALUES (%s, %s, %s, 0, %s)
                    ON CONFLICT (email) DO UPDATE SET
                        hashed_code       = EXCLUDED.hashed_code,
                        expires_at        = EXCLUDED.expires_at,
                        attempts_count    = 0,
                        last_requested_at = EXCLUDED.last_requested_at
                    """,
                    (email, hashed_code, expires_at, last_requested_at),
                )

    def get_auth_code_record(self, email: str) -> Optional[dict]:
        """
        Return the admin_auth_codes row for the given email as a dict,
        or None if no row exists.

        Returned dict keys: email, hashed_code, expires_at,
        attempts_count, last_requested_at.
        """
        with get_conn(self.database_url) as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT email, hashed_code, expires_at,
                           attempts_count, last_requested_at
                    FROM admin_auth_codes
                    WHERE email = %s
                    """,
                    (email,),
                )
                row = cur.fetchone()
        return dict(row) if row is not None else None

    def increment_code_attempts(self, email: str) -> None:
        """
        Atomically increment attempts_count for the given email.

        Uses UPDATE ... SET attempts_count = attempts_count + 1 to avoid
        a read-modify-write race. No-ops silently if the row does not exist
        (the code may have been deleted by a concurrent request).
        """
        with get_conn(self.database_url) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE admin_auth_codes
                    SET attempts_count = attempts_count + 1
                    WHERE email = %s
                    """,
                    (email,),
                )

    def delete_auth_code(self, email: str) -> None:
        """
        Delete the auth code record for the given email.

        Idempotent — no-ops silently if the row does not exist.
        Called on successful verification, on lockout (3 failed attempts),
        and on expiry detection.
        """
        with get_conn(self.database_url) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "DELETE FROM admin_auth_codes WHERE email = %s",
                    (email,),
                )

    # ------------------------------------------------------------------
    # admin_sessions
    # ------------------------------------------------------------------

    def create_session(self, user_id: str, expires_at: datetime) -> str:
        """
        Create a new session for the given user and return the session_id
        as a string (UUID).

        Deletes ALL existing sessions for user_id in the same transaction,
        enforcing single-session behaviour — not just expired sessions, but
        valid ones too. Runs as a single transaction so there is no window
        where the user has zero sessions.
        """
        session_id = str(uuid.uuid4())
        with get_conn(self.database_url) as conn:
            with conn.cursor() as cur:
                # Delete all existing sessions for this user (single-session enforcement).
                cur.execute(
                    "DELETE FROM admin_sessions WHERE user_id = %s::uuid",
                    (user_id,),
                )
                # Insert the new session.
                cur.execute(
                    """
                    INSERT INTO admin_sessions (session_id, user_id, expires_at)
                    VALUES (%s::uuid, %s::uuid, %s)
                    """,
                    (session_id, user_id, expires_at),
                )
        return session_id

    def get_session_context(self, session_id: str) -> Optional[dict]:
        """
        Return session context for the given session_id, or None if the
        session does not exist or has expired.

        Joins admin_sessions to admin_users on user_id to resolve
        practice_id and email in a single query. The expiry check is done
        in SQL so there is no clock-skew risk from comparing DB timestamps
        in Python.

        Returned dict keys: user_id (str), practice_id (str),
                            email (str), session_id (str).
        session_id is returned so that the caller (require_admin) can
        populate AdminContext without needing to pass it separately.
        """
        with get_conn(self.database_url) as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT u.id::text AS user_id,
                           u.practice_id,
                           u.email,
                           s.session_id::text
                    FROM admin_sessions s
                    JOIN admin_users u ON s.user_id = u.id
                    WHERE s.session_id = %s::uuid
                      AND s.expires_at > NOW()
                    """,
                    (session_id,),
                )
                row = cur.fetchone()
        return dict(row) if row is not None else None

    def delete_session(self, session_id: str) -> None:
        """
        Delete the session with the given session_id.

        Idempotent — no-ops silently if the session does not exist.
        Called by the logout endpoint.
        """
        with get_conn(self.database_url) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "DELETE FROM admin_sessions WHERE session_id = %s::uuid",
                    (session_id,),
                )
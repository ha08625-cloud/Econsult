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

from datetime import datetime
from typing import Optional

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
        """
        raise NotImplementedError

    def count_users_for_practice(self, practice_id: str) -> int:
        """
        Return the number of rows in admin_users for the given practice_id.

        Used at startup to decide whether to seed the initial admin user.
        Returns 0 if no users exist for the practice.
        """
        raise NotImplementedError

    def insert_user(self, email: str, practice_id: str, role: str) -> None:
        """
        Insert a new row into admin_users.

        Does not check for duplicates — the UNIQUE constraint on email will
        raise a psycopg2 IntegrityError if the email already exists.
        The caller (startup validation) is responsible for calling
        count_users_for_practice first to avoid a redundant insert.
        """
        raise NotImplementedError

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
        raise NotImplementedError

    def get_auth_code_record(self, email: str) -> Optional[dict]:
        """
        Return the admin_auth_codes row for the given email as a dict,
        or None if no row exists.

        Returned dict keys: email, hashed_code, expires_at,
        attempts_count, last_requested_at.
        """
        raise NotImplementedError

    def increment_code_attempts(self, email: str) -> None:
        """
        Atomically increment attempts_count for the given email.

        Uses UPDATE ... SET attempts_count = attempts_count + 1 to avoid
        a read-modify-write race. No-ops silently if the row does not exist
        (the code may have been deleted by a concurrent request).
        """
        raise NotImplementedError

    def delete_auth_code(self, email: str) -> None:
        """
        Delete the auth code record for the given email.

        Idempotent — no-ops silently if the row does not exist.
        Called on successful verification, on lockout (3 failed attempts),
        and on expiry detection.
        """
        raise NotImplementedError

    # ------------------------------------------------------------------
    # admin_sessions
    # ------------------------------------------------------------------

    def create_session(self, user_id: str, expires_at: datetime) -> str:
        """
        Create a new session for the given user and return the session_id
        as a string (UUID).

        Also deletes ALL existing sessions for user_id in the same
        transaction, enforcing single-session behaviour. This ensures only
        one active login exists per user at any time — not just expired
        sessions, but valid ones too.

        The two operations (delete all + insert new) run in a single
        transaction so there is no window where the user has zero sessions.
        """
        raise NotImplementedError

    def get_session_context(self, session_id: str) -> Optional[dict]:
        """
        Return session context for the given session_id, or None if the
        session does not exist or has expired.

        Joins admin_sessions to admin_users on user_id to resolve role
        and practice_id in a single query.

        Returns None if:
          - No row with that session_id exists
          - The row exists but expires_at < NOW()

        Returned dict keys: user_id (str), role (str), practice_id (str).
        """
        raise NotImplementedError

    def delete_session(self, session_id: str) -> None:
        """
        Delete the session with the given session_id.

        Idempotent — no-ops silently if the session does not exist.
        Called by the logout endpoint.
        """
        raise NotImplementedError
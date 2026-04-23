"""
app/repositories/auth_repository.py

Database access for admin authentication, session management, and user management.

Responsibilities:
- User lookups (by email, by id, by practice)
- Auth code lifecycle (upsert, lookup, delete, increment attempts)
- Session lifecycle (create, lookup, delete)
- User lifecycle (insert, delete, count)

# ---------------------------------------------------------------------------
# conn parameter convention
# ---------------------------------------------------------------------------
#
# Several methods accept an optional conn parameter.
#
# When conn is supplied, the method executes on that connection without
# opening a new one and without committing. The caller owns the transaction
# lifecycle. Use this when the operation must be atomic with another write
# (e.g. an audit log insert, or a practice lock) in the same transaction.
#
# When conn is None, the method opens its own connection via get_conn,
# which commits on success and rolls back on failure.
#
# Read methods that are only called outside transactions (get_user_by_email,
# get_auth_code_record, get_session_context, count_users_for_practice,
# get_user_by_id) do not accept conn. The exception is get_users_by_practice,
# which must be callable inside the remove_user transaction to guarantee a
# consistent read while the practice row is locked.
"""

import logging
from typing import Optional

from psycopg2.extras import RealDictCursor

from app.core.db import get_conn

logger = logging.getLogger(__name__)


class AuthRepository:
    def __init__(self, database_url: str) -> None:
        self.database_url = database_url

    # -------------------------------------------------------------------------
    # User reads
    # -------------------------------------------------------------------------

    def get_user_by_email(self, email: str) -> Optional[dict]:
        """
        Return the admin_users row for the given email, or None if not found.

        Returns a dict with keys: id (str), email, practice_id, role.
        """
        with get_conn(self.database_url) as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT id::text, email, practice_id, role
                    FROM admin_users
                    WHERE email = %s
                    """,
                    (email,),
                )
                row = cur.fetchone()
        return dict(row) if row else None

    def get_user_by_id(self, user_id: str, practice_id: str) -> Optional[dict]:
        """
        Return an admin_users row by UUID and practice, or None if not found.

        Returns a dict with keys: id (str), email, created_at, last_login.
        practice_id is enforced to prevent cross-tenant lookups.

        No conn parameter — this is only called from resend_invitation, which
        performs no writes and has no transaction to join.
        """
        with get_conn(self.database_url) as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT id::text, email, created_at, last_login
                    FROM admin_users
                    WHERE id = %s::uuid
                      AND practice_id = %s
                    """,
                    (user_id, practice_id),
                )
                row = cur.fetchone()
        return dict(row) if row else None

    def get_users_by_practice(self, practice_id: str, conn=None) -> list:
        """
        Return all admin_users rows for the given practice, ordered by
        created_at ascending.

        Returns a list of dicts with keys: id (str), email, created_at,
        last_login.

        conn: see module-level convention. conn is accepted here because
        remove_user must read the user list inside the same transaction
        that holds the practice row lock, so the count check is consistent
        with the subsequent delete.
        """
        def _execute(cur):
            cur.execute(
                """
                SELECT id::text, email, created_at, last_login
                FROM admin_users
                WHERE practice_id = %s
                ORDER BY created_at ASC
                """,
                (practice_id,),
            )
            return [dict(row) for row in cur.fetchall()]

        if conn is not None:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                return _execute(cur)
        else:
            with get_conn(self.database_url) as own_conn:
                with own_conn.cursor(cursor_factory=RealDictCursor) as cur:
                    return _execute(cur)

    def count_users_for_practice(self, practice_id: str) -> int:
        """
        Return the count of admin_users rows for the given practice.

        Used by startup validation in main.py to ensure at least one admin
        exists before accepting requests.
        """
        with get_conn(self.database_url) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT COUNT(*) FROM admin_users WHERE practice_id = %s",
                    (practice_id,),
                )
                row = cur.fetchone()
        return row[0]

    # -------------------------------------------------------------------------
    # User writes
    # -------------------------------------------------------------------------

    def insert_user(
        self,
        email: str,
        practice_id: str,
        role: str,
        conn=None,
    ) -> None:
        """
        Insert a new admin_users row.

        email is normalised to lowercase before insertion. This ensures all
        stored emails are consistently lowercase regardless of call site.
        create_admin_user.py continues to work unchanged — it does not pass
        conn, so this method opens its own connection as before, and the
        normalisation now applies there too.

        Raises psycopg2.errors.UniqueViolation if the email already exists.
        The caller (user_service.add_user) catches this and raises USER_ALREADY_EXISTS.

        conn: see module-level convention.
        """
        email = email.lower()

        def _execute(cur) -> None:
            cur.execute(
                """
                INSERT INTO admin_users (email, practice_id, role)
                VALUES (%s, %s, %s)
                """,
                (email, practice_id, role),
            )

        if conn is not None:
            with conn.cursor() as cur:
                _execute(cur)
        else:
            with get_conn(self.database_url) as own_conn:
                with own_conn.cursor() as cur:
                    _execute(cur)

    def delete_user(self, user_id: str, practice_id: str, conn=None) -> None:
        """
        Delete an admin_users row by UUID and practice.

        practice_id is enforced as a tenant boundary — a delete can only
        succeed for a user that belongs to the caller's practice.

        Postgres cascades the delete to admin_sessions via the FK defined
        in migration 0002 (ON DELETE CASCADE), so all sessions for this
        user are removed automatically.

        conn: see module-level convention.
        """
        def _execute(cur) -> None:
            cur.execute(
                """
                DELETE FROM admin_users
                WHERE id = %s::uuid
                  AND practice_id = %s
                """,
                (user_id, practice_id),
            )

        if conn is not None:
            with conn.cursor() as cur:
                _execute(cur)
        else:
            with get_conn(self.database_url) as own_conn:
                with own_conn.cursor() as cur:
                    _execute(cur)

    # -------------------------------------------------------------------------
    # Auth code lifecycle
    # -------------------------------------------------------------------------

    def get_auth_code_record(self, email: str) -> Optional[dict]:
        """
        Return the admin_auth_codes row for the given email, or None.

        Returns a dict with keys: email, hashed_code, expires_at,
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
        return dict(row) if row else None

    def upsert_auth_code(
        self,
        email: str,
        hashed_code: str,
        expires_at,
        last_requested_at,
    ) -> None:
        """
        Insert or replace the auth code record for the given email.

        email is the PK of admin_auth_codes, so an upsert replaces any
        existing in-flight code, enforcing one in-flight code per user.
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

    def increment_code_attempts(self, email: str) -> None:
        """Increment attempts_count for the given email's auth code record."""
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
        """Delete the auth code record for the given email."""
        with get_conn(self.database_url) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "DELETE FROM admin_auth_codes WHERE email = %s",
                    (email,),
                )

    # -------------------------------------------------------------------------
    # Session lifecycle
    # -------------------------------------------------------------------------

    def get_session_context(self, session_id: str) -> Optional[dict]:
        """
        Validate a session and return its context, or None if invalid/expired.

        Returns a dict with keys: user_id (str), role, practice_id, email,
        session_id. Returns None if the session does not exist or has expired.
        Expiry is checked in SQL (expires_at > NOW()) to avoid clock-skew issues.
        """
        with get_conn(self.database_url) as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT
                        u.id::text  AS user_id,
                        u.role,
                        u.practice_id,
                        u.email,
                        s.session_id::text AS session_id
                    FROM admin_sessions s
                    JOIN admin_users u ON u.id = s.user_id
                    WHERE s.session_id = %s::uuid
                      AND s.expires_at > NOW()
                    """,
                    (session_id,),
                )
                row = cur.fetchone()
        return dict(row) if row else None

    def create_session(self, user_id: str, expires_at) -> str:
        """
        Create a new session for the given user and return the session_id.

        Runs three statements atomically in a single transaction:
        1. Delete all existing sessions for this user (single-session enforcement).
        2. Delete all expired sessions across all users (lazy cleanup).
        3. Insert the new session row.
        4. Update admin_users.last_login to NOW() for this user.

        Returns the new session_id as a string.
        """
        import uuid
        session_id = str(uuid.uuid4())

        with get_conn(self.database_url) as conn:
            with conn.cursor() as cur:
                # Invalidate any existing sessions for this user.
                cur.execute(
                    "DELETE FROM admin_sessions WHERE user_id = %s::uuid",
                    (user_id,),
                )
                # Lazy expiry cleanup — remove expired sessions for all users.
                cur.execute(
                    "DELETE FROM admin_sessions WHERE expires_at <= NOW()"
                )
                # Insert the new session.
                cur.execute(
                    """
                    INSERT INTO admin_sessions (session_id, user_id, expires_at)
                    VALUES (%s::uuid, %s::uuid, %s)
                    """,
                    (session_id, user_id, expires_at),
                )
                # Record last login time atomically with session creation.
                cur.execute(
                    """
                    UPDATE admin_users
                    SET last_login = NOW()
                    WHERE id = %s::uuid
                    """,
                    (user_id,),
                )

        return session_id

    def delete_session(self, session_id: str) -> None:
        """Delete a session by session_id (used by logout)."""
        with get_conn(self.database_url) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "DELETE FROM admin_sessions WHERE session_id = %s::uuid",
                    (session_id,),
                )
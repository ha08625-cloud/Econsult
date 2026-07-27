"""
Database access for admin MFA authentication, password authentication,
and user management.

Handles four tables: admin_users, admin_auth_codes, admin_sessions,
admin_password_reset_tokens.

This module must never:
- Contain business logic (cooldown checks, code generation, hashing,
  lockout decisions)
- Import from service modules
- Import from routers

All business logic lives in app/services/auth_service.py.
All transport logic lives in app/services/delivery/admin_delivery_service.py.
Table creation is handled by Alembic migrations.

# ---------------------------------------------------------------------------
# conn parameter convention
# ---------------------------------------------------------------------------
#
# Several mutating methods accept an optional conn parameter.
#
# When conn is supplied, the method executes on that connection without
# opening a new one and without committing. The caller owns the transaction
# lifecycle. Use this when the operation must be atomic with another write
# (e.g. an audit log insert, or a practice row lock) in the same transaction.
#
# When conn is None, the method opens its own connection via get_conn,
# which commits on success and rolls back on failure.
#
# Read methods that are only ever called outside transactions
# (get_user_by_email, get_auth_code_record, get_session_context,
# count_users_for_practice, get_user_by_id) do not accept conn.
# The exception is get_users_by_practice, which must be callable inside
# the remove_user transaction to guarantee a consistent read while the
# practice row lock is held.
"""

import uuid
from datetime import datetime

from psycopg2.extras import RealDictCursor

from app.core.db import get_conn


class AuthRepository:
    def __init__(self, database_url: str):
        self.database_url = database_url

    # ------------------------------------------------------------------
    # admin_users — reads
    # ------------------------------------------------------------------

    def get_user_by_email(self, email: str) -> dict | None:
        """
        Return the admin_users row for the given email as a dict, or None
        if no matching row exists.

        Returned dict keys: id (str), email, practice_id, role, created_at,
        hashed_password, failed_password_attempts, password_locked_until,
        password_changed_at.

        id is cast to str — psycopg2 returns UUID columns as uuid.UUID
        objects; callers expect strings throughout the auth layer.
        """
        with (
            get_conn(self.database_url) as conn,
            conn.cursor(cursor_factory=RealDictCursor) as cur,
        ):
            cur.execute(
                """
                SELECT id::text,
                        email,
                        practice_id,
                        role,
                        created_at,
                        hashed_password,
                        failed_password_attempts,
                        password_locked_until,
                        password_changed_at
                FROM admin_users
                WHERE email = %s
                """,
                (email,),
            )
            row = cur.fetchone()
        return dict(row) if row is not None else None

    def get_user_by_id(self, user_id: str, practice_id: str) -> dict | None:
        """
        Return an admin_users row by UUID and practice, or None if not found.

        Returned dict keys: id (str), email, created_at, last_login.
        practice_id is enforced to prevent cross-tenant lookups.

        No conn parameter — this is only called from resend_invitation, which
        performs no writes and has no transaction to join.
        """
        with (
            get_conn(self.database_url) as conn,
            conn.cursor(cursor_factory=RealDictCursor) as cur,
        ):
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
        return dict(row) if row is not None else None

    def get_users_by_practice(self, practice_id: str, conn=None) -> list:
        """
        Return all admin_users rows for the given practice, ordered by
        created_at ascending.

        Returned list of dicts with keys: id (str), email, created_at,
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
            with (
                get_conn(self.database_url) as own_conn,
                own_conn.cursor(cursor_factory=RealDictCursor) as cur,
            ):
                return _execute(cur)

    def count_users_for_practice(self, practice_id: str) -> int:
        """
        Return the number of rows in admin_users for the given practice_id.

        Used at startup to decide whether to seed the initial admin user.
        Returns 0 if no users exist for the practice.
        """
        with get_conn(self.database_url) as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT COUNT(*) FROM admin_users WHERE practice_id = %s",
                (practice_id,),
            )
            row = cur.fetchone()
        return row[0] if row else 0

    # ------------------------------------------------------------------
    # admin_users — writes
    # ------------------------------------------------------------------

    def insert_user(self, email: str, practice_id: str, role: str, conn=None) -> None:
        """
        Insert a new row into admin_users.

        email is normalised to lowercase before insertion so all stored
        emails are consistently lowercase regardless of call site.
        create_admin_user.py continues to work unchanged — it does not pass
        conn, so this method opens its own connection as before.

        Does not check for duplicates — the UNIQUE constraint on email will
        raise psycopg2.errors.UniqueViolation if the email already exists.
        The caller (user_service.add_user) catches this and raises
        USER_ALREADY_EXISTS.

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
            with get_conn(self.database_url) as own_conn, own_conn.cursor() as cur:
                _execute(cur)

    def delete_user(self, user_id: str, practice_id: str, conn=None) -> None:
        """
        Delete an admin_users row by UUID and practice.

        practice_id is enforced as a tenant boundary — a delete can only
        succeed for a user that belongs to the caller's practice.

        Postgres cascades the delete to admin_sessions and
        admin_password_reset_tokens via the FK constraints defined in
        migrations 0002 and 0004, so all sessions and pending reset tokens
        for this user are removed automatically.

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
            with get_conn(self.database_url) as own_conn, own_conn.cursor() as cur:
                _execute(cur)

    def set_password(self, user_id: str, hashed_password: str, conn=None) -> None:
        """
        Set a new hashed password for the given user.

        Atomically updates hashed_password, sets password_changed_at to NOW(),
        and resets the lockout state (failed_password_attempts = 0,
        password_locked_until = NULL) in a single UPDATE statement.

        This is the only method that should write hashed_password. It is
        called after set_new_password validates strength and hashes the
        plaintext in the service layer.

        conn: see module-level convention.
        """

        def _execute(cur) -> None:
            cur.execute(
                """
                UPDATE admin_users
                SET hashed_password          = %s,
                    password_changed_at      = NOW(),
                    failed_password_attempts = 0,
                    password_locked_until    = NULL
                WHERE id = %s::uuid
                """,
                (hashed_password, user_id),
            )

        if conn is not None:
            with conn.cursor() as cur:
                _execute(cur)
        else:
            with get_conn(self.database_url) as own_conn, own_conn.cursor() as cur:
                _execute(cur)

    def record_failed_password_attempt(
        self,
        user_id: str,
        lock_until: datetime | None = None,
        conn=None,
    ) -> None:
        """
        Atomically increment failed_password_attempts for the given user.

        If lock_until is provided, also sets password_locked_until to that
        timestamp. The service layer decides when to supply lock_until (i.e.
        when the attempt count reaches the threshold). This method does not
        make that decision.

        Uses a single UPDATE to avoid a read-modify-write race. No-ops
        silently if the user does not exist.

        conn: see module-level convention.
        """

        def _execute(cur) -> None:
            if lock_until is not None:
                cur.execute(
                    """
                    UPDATE admin_users
                    SET failed_password_attempts = failed_password_attempts + 1,
                        password_locked_until    = %s
                    WHERE id = %s::uuid
                    """,
                    (lock_until, user_id),
                )
            else:
                cur.execute(
                    """
                    UPDATE admin_users
                    SET failed_password_attempts = failed_password_attempts + 1
                    WHERE id = %s::uuid
                    """,
                    (user_id,),
                )

        if conn is not None:
            with conn.cursor() as cur:
                _execute(cur)
        else:
            with get_conn(self.database_url) as own_conn, own_conn.cursor() as cur:
                _execute(cur)

    def reset_password_attempts(self, user_id: str, conn=None) -> None:
        """
        Reset failed_password_attempts to 0 and clear password_locked_until.

        Called on successful password verification to restore the attempt
        counter without triggering a full set_password (which would update
        password_changed_at, reserved for actual password changes).

        conn: see module-level convention.
        """

        def _execute(cur) -> None:
            cur.execute(
                """
                UPDATE admin_users
                SET failed_password_attempts = 0,
                    password_locked_until    = NULL
                WHERE id = %s::uuid
                """,
                (user_id,),
            )

        if conn is not None:
            with conn.cursor() as cur:
                _execute(cur)
        else:
            with get_conn(self.database_url) as own_conn, own_conn.cursor() as cur:
                _execute(cur)

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
        with get_conn(self.database_url) as conn, conn.cursor() as cur:
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

    def get_auth_code_record(self, email: str) -> dict | None:
        """
        Return the admin_auth_codes row for the given email as a dict,
        or None if no row exists.

        Returned dict keys: email, hashed_code, expires_at,
        attempts_count, last_requested_at.
        """
        with get_conn(self.database_url) as conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
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
        with get_conn(self.database_url) as conn, conn.cursor() as cur:
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
        with get_conn(self.database_url) as conn, conn.cursor() as cur:
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

        Runs four statements atomically in a single transaction:
        1. Delete all existing sessions for this user (single-session enforcement).
        2. Delete all expired sessions across all users (lazy cleanup).
        3. Insert the new session row.
        4. Update admin_users.last_login to NOW() for this user.

        Steps 1 and 4 ensure that on each new login the old session is
        invalidated and the login timestamp is recorded atomically.
        """
        session_id = str(uuid.uuid4())
        with get_conn(self.database_url) as conn, conn.cursor() as cur:
            # Invalidate any existing sessions for this user.
            cur.execute(
                "DELETE FROM admin_sessions WHERE user_id = %s::uuid",
                (user_id,),
            )
            # Lazy expiry cleanup — remove expired sessions for all users.
            cur.execute("DELETE FROM admin_sessions WHERE expires_at <= NOW()")
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

    def get_session_context(self, session_id: str) -> dict | None:
        """
        Return session context for the given session_id, or None if the
        session does not exist or has expired.

        Joins admin_sessions to admin_users on user_id to resolve
        practice_id and email in a single query. The expiry check is done
        in SQL so there is no clock-skew risk from comparing DB timestamps
        in Python.

        Returned dict keys: user_id (str), practice_id (str), role (str),
                            email (str), session_id (str).
        session_id is returned so that the caller (require_admin) can
        populate AdminContext without needing to pass it separately.
        """
        with get_conn(self.database_url) as conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                SELECT u.id::text AS user_id,
                        u.practice_id,
                        u.role,
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

    def update_session_expiry(self, session_id: str, ttl_minutes: int) -> None:
        """
        Extend the session's expires_at to ttl_minutes from now.

        Implements the sliding-window TTL: called by require_admin on every
        authenticated request so an active session never lapses. Time
        arithmetic is done on the DB clock via make_interval, consistent
        with get_session_context's expiry comparison. No conn parameter —
        this is a fire-and-forget refresh that never joins another
        transaction. Idempotent, no-ops silently if the session does not
        exist (e.g. it expired or was deleted between validation and here).
        """
        with get_conn(self.database_url) as conn, conn.cursor() as cur:
            cur.execute(
                """
                UPDATE admin_sessions
                SET expires_at = NOW() + make_interval(mins => %s)
                WHERE session_id = %s::uuid
                """,
                (ttl_minutes, session_id),
            )

    def delete_session(self, session_id: str) -> None:
        """
        Delete the session with the given session_id.

        Idempotent — no-ops silently if the session does not exist.
        Called by the logout endpoint.
        """
        with get_conn(self.database_url) as conn, conn.cursor() as cur:
            cur.execute(
                "DELETE FROM admin_sessions WHERE session_id = %s::uuid",
                (session_id,),
            )

    # ------------------------------------------------------------------
    # admin_password_reset_tokens
    # ------------------------------------------------------------------

    def upsert_reset_token(
        self,
        user_id: str,
        token_hash: str,
        expires_at: datetime,
        conn=None,
    ) -> None:
        """
        Insert or replace the reset token for the given user.

        Uses INSERT ... ON CONFLICT (user_id) DO UPDATE so that generating
        a new token atomically replaces any existing pending token for this
        user. The UNIQUE constraint on user_id is therefore also the
        de-duplication mechanism — there is never a window where two valid
        tokens exist for the same user.

        conn: see module-level convention. conn is accepted so that token
        generation can be part of the same transaction as a user insert
        (POST /users) to ensure the token is only committed if the user
        write succeeds.
        """

        def _execute(cur) -> None:
            cur.execute(
                """
                INSERT INTO admin_password_reset_tokens
                    (token_hash, user_id, expires_at)
                VALUES (%s, %s::uuid, %s)
                ON CONFLICT (user_id) DO UPDATE SET
                    token_hash = EXCLUDED.token_hash,
                    expires_at = EXCLUDED.expires_at
                """,
                (token_hash, user_id, expires_at),
            )

        if conn is not None:
            with conn.cursor() as cur:
                _execute(cur)
        else:
            with get_conn(self.database_url) as own_conn, own_conn.cursor() as cur:
                _execute(cur)

    def get_reset_token_record(self, token_hash: str) -> dict | None:
        """
        Return the admin_password_reset_tokens row for the given token hash,
        or None if no matching row exists.

        Returned dict keys: token_hash, user_id (str), expires_at.
        user_id is cast to str for consistency with the rest of the auth layer.
        """
        with get_conn(self.database_url) as conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                SELECT token_hash, user_id::text, expires_at
                FROM admin_password_reset_tokens
                WHERE token_hash = %s
                """,
                (token_hash,),
            )
            row = cur.fetchone()
        return dict(row) if row is not None else None

    def delete_reset_token(self, token_hash: str, conn=None) -> None:
        """
        Delete the reset token with the given hash.

        Idempotent — no-ops silently if the row does not exist.
        Called by verify_reset_token after a token is consumed, ensuring
        each token can only be used once.

        conn: see module-level convention.
        """

        def _execute(cur) -> None:
            cur.execute(
                "DELETE FROM admin_password_reset_tokens WHERE token_hash = %s",
                (token_hash,),
            )

        if conn is not None:
            with conn.cursor() as cur:
                _execute(cur)
        else:
            with get_conn(self.database_url) as own_conn, own_conn.cursor() as cur:
                _execute(cur)

"""
Database access only. No validation logic. No imports from service modules.

Methods:
- init_availability: insert default row if absent (startup)
- get_availability: return all columns as dict
- set_availability: upsert full config (caller validates first)
- set_override: update the three override columns
- clear_override: set all three override columns to NULL
- get_exceptions: return all exceptions on or after a given date
- set_exception: upsert a single exception row
- delete_exception: delete a single exception row (idempotent)

# ---------------------------------------------------------------------------
# conn parameter convention
# ---------------------------------------------------------------------------
#
# Several mutating methods accept an optional conn parameter.
#
# When conn is supplied, the method executes on that connection without
# opening a new one and without committing. The caller owns the transaction
# lifecycle. Use this when the write must be atomic with another operation
# (e.g. an audit log insert) in the same transaction.
#
# When conn is None, the method opens its own connection via get_conn,
# which commits on success and rolls back on failure. This is the default
# and preserves the original behaviour for callers that do not need a
# shared transaction.
#
# Read methods (get_availability, get_exceptions) never accept conn.
# They are called outside the transaction to read the "before" state,
# and called again after the transaction commits to build the HTTP response.
"""

import datetime

from psycopg2.extras import RealDictCursor

from app.core.db import get_conn


class AvailabilityRepository:
    def __init__(self, database_url: str):
        self.database_url = database_url

    def init_availability(self, practice_id: str) -> None:
        """
        Insert a default availability row if one does not exist.

        Called once at startup after the practice row exists.
        Uses INSERT ... ON CONFLICT DO NOTHING so it is safe to call
        repeatedly.
        """
        with get_conn(self.database_url) as conn, conn.cursor() as cur:
            cur.execute(
                """
                    INSERT INTO practice_availability (practice_id)
                    VALUES (%s)
                    ON CONFLICT DO NOTHING
                    """,
                (practice_id,),
            )

    def get_availability(self, practice_id: str) -> dict:
        """
        Return all columns for the given practice as a dict.

        Raises ValueError if the row does not exist.
        """
        with get_conn(self.database_url) as conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                SELECT practice_id, is_active, weekly_open_days,
                       open_time, close_time, closed_message,
                       override_status, override_expires_at,
                       override_message
                FROM practice_availability
                WHERE practice_id = %s
                """,
                (practice_id,),
            )
            row = cur.fetchone()

        if row is None:
            raise ValueError(f"No availability row found for practice '{practice_id}'")
        return dict(row)

    def set_availability(
        self,
        practice_id: str,
        is_active: bool,
        weekly_open_days: list[str],
        open_time: datetime.time,
        close_time: datetime.time,
        closed_message: str | None,
        conn=None,
    ) -> None:
        """
        Upsert the availability configuration.

        No validation is performed here. The caller is responsible for
        calling validate_availability_config() before calling this method.

        conn: see module-level conn parameter convention.
        """

        def _execute(cur) -> None:
            cur.execute(
                """
                INSERT INTO practice_availability
                    (practice_id, is_active, weekly_open_days,
                     open_time, close_time, closed_message)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (practice_id) DO UPDATE SET
                    is_active = EXCLUDED.is_active,
                    weekly_open_days = EXCLUDED.weekly_open_days,
                    open_time = EXCLUDED.open_time,
                    close_time = EXCLUDED.close_time,
                    closed_message = EXCLUDED.closed_message
                """,
                (
                    practice_id,
                    is_active,
                    weekly_open_days,
                    open_time,
                    close_time,
                    closed_message,
                ),
            )

        if conn is not None:
            with conn.cursor() as cur:
                _execute(cur)
        else:
            with get_conn(self.database_url) as own_conn, own_conn.cursor() as cur:
                _execute(cur)

    def set_override(
        self,
        practice_id: str,
        override_status: str,
        override_expires_at: datetime.datetime,
        override_message: str | None,
        conn=None,
    ) -> None:
        """
        Update the three override columns.

        The caller is responsible for calling validate_override() first.

        conn: see module-level conn parameter convention.
        """

        def _execute(cur) -> None:
            cur.execute(
                """
                UPDATE practice_availability
                SET override_status = %s,
                    override_expires_at = %s,
                    override_message = %s
                WHERE practice_id = %s
                """,
                (override_status, override_expires_at, override_message, practice_id),
            )

        if conn is not None:
            with conn.cursor() as cur:
                _execute(cur)
        else:
            with get_conn(self.database_url) as own_conn, own_conn.cursor() as cur:
                _execute(cur)

    def clear_override(self, practice_id: str, conn=None) -> None:
        """
        Set all three override columns to NULL.

        Idempotent — no error if no override was active.

        conn: see module-level conn parameter convention.
        """

        def _execute(cur) -> None:
            cur.execute(
                """
                UPDATE practice_availability
                SET override_status = NULL,
                    override_expires_at = NULL,
                    override_message = NULL
                WHERE practice_id = %s
                """,
                (practice_id,),
            )

        if conn is not None:
            with conn.cursor() as cur:
                _execute(cur)
        else:
            with get_conn(self.database_url) as own_conn, own_conn.cursor() as cur:
                _execute(cur)

    # ------------------------------------------------------------------
    # Per-date exceptions
    # ------------------------------------------------------------------

    def get_exceptions(self, practice_id: str, from_date: datetime.date) -> list[dict]:
        """
        Return all exceptions on or after from_date, ordered by date ascending.

        Used both by the evaluation path (which checks only today's
        exception) and by GET /admin/availability/exceptions (which
        displays all upcoming exceptions to the admin).
        """
        with get_conn(self.database_url) as conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                SELECT practice_id, exception_date, exception_type,
                       open_time, close_time, note
                FROM practice_availability_exceptions
                WHERE practice_id = %s AND exception_date >= %s
                ORDER BY exception_date ASC
                """,
                (practice_id, from_date),
            )
            rows = cur.fetchall()
        return [dict(r) for r in rows]

    def get_exception(self, practice_id: str, exception_date: datetime.date) -> dict | None:
        """
        Return a single exception row for a specific date, or None if absent.

        Used to read the "before" state for audit logging before a set or
        delete operation.
        """
        with get_conn(self.database_url) as conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                SELECT practice_id, exception_date, exception_type,
                       open_time, close_time, note
                FROM practice_availability_exceptions
                WHERE practice_id = %s AND exception_date = %s
                """,
                (practice_id, exception_date),
            )
            row = cur.fetchone()
        return dict(row) if row is not None else None

    def set_exception(
        self,
        practice_id: str,
        exception_date: datetime.date,
        exception_type: str,
        open_time: datetime.time | None,
        close_time: datetime.time | None,
        note: str | None,
        conn=None,
    ) -> None:
        """
        Upsert a single exception row.

        No validation is performed here. The caller is responsible for
        calling validate_exception() before calling this method.

        conn: see module-level conn parameter convention.
        """

        def _execute(cur) -> None:
            cur.execute(
                """
                INSERT INTO practice_availability_exceptions
                    (practice_id, exception_date, exception_type,
                     open_time, close_time, note)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (practice_id, exception_date) DO UPDATE SET
                    exception_type = EXCLUDED.exception_type,
                    open_time = EXCLUDED.open_time,
                    close_time = EXCLUDED.close_time,
                    note = EXCLUDED.note
                """,
                (
                    practice_id,
                    exception_date,
                    exception_type,
                    open_time,
                    close_time,
                    note,
                ),
            )

        if conn is not None:
            with conn.cursor() as cur:
                _execute(cur)
        else:
            with get_conn(self.database_url) as own_conn, own_conn.cursor() as cur:
                _execute(cur)

    def delete_exception(self, practice_id: str, exception_date: datetime.date, conn=None) -> None:
        """
        Delete a single exception row.

        Idempotent — no error if the row does not exist.

        conn: see module-level conn parameter convention.
        """

        def _execute(cur) -> None:
            cur.execute(
                """
                DELETE FROM practice_availability_exceptions
                WHERE practice_id = %s AND exception_date = %s
                """,
                (practice_id, exception_date),
            )

        if conn is not None:
            with conn.cursor() as cur:
                _execute(cur)
        else:
            with get_conn(self.database_url) as own_conn, own_conn.cursor() as cur:
                _execute(cur)

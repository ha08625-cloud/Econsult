"""
Practice repository.

Database access for practice identity and practice-specific configuration.
Handles the practices, practice_signposting, and practice_doctors tables.

This module is responsible for:
- CRUD operations for practices (including email)
- CRUD operations for practice signposting
- CRUD operations for the doctor list
- HTML sanitisation for signposting content
- Email format validation

Table creation is handled by Alembic migrations at startup.

This module must never:
- Access clinical data (rulesets, RuntimeState, answers)
- Perform composition logic (that belongs in presentation_service)
- Handle authentication (that belongs in practice_context, Phase 1B)

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
# Read methods (get_practice, get_signposting, get_doctors, get_email)
# never accept conn. They are called outside the transaction to read the
# "before" state, and called again after the transaction commits to build
# the HTTP response from the committed state.
"""

import re
from typing import List, Optional

import nh3
import psycopg2.extras
from psycopg2.extras import RealDictCursor

from app.core.db import get_conn


MAX_SIGNPOSTING_LENGTH = 5000
QUILL_EMPTY_OUTPUT = "<p></p>"

MAX_DOCTOR_NAME_LENGTH = 100
MAX_DOCTOR_LIST_LENGTH = 50


class PracticeNotFound(Exception):
    """Raised when a practice_id does not exist."""
    pass


class InvalidSignpostingData(Exception):
    """Raised when signposting HTML is too long or otherwise invalid."""
    pass


class InvalidEmailError(Exception):
    """Raised when an email address fails validation."""
    pass


class InvalidDoctorListError(Exception):
    """Raised when the doctor list fails validation."""
    pass


def sanitise_signposting_html(raw: str) -> str | None:
    """
    Sanitise a raw HTML string from the Quill editor before storage.

    Steps:
    1. Reject input exceeding MAX_SIGNPOSTING_LENGTH characters.
    2. Run nh3.clean() with an explicit allowlist of tags, attributes,
       and URL schemes.
    3. After sanitisation, strip all remaining tags and check whether
       any non-whitespace characters survive. If not, return None.

    Allowed tags : p, strong, em, a, ul, ol, li, br
    Allowed attrs: href, rel, target on <a> only
    Allowed URL schemes on href: http, https

    Returns:
        Sanitised HTML string, or None if content is empty after sanitisation.

    Raises:
        InvalidSignpostingData: if raw exceeds MAX_SIGNPOSTING_LENGTH.
    """
    if len(raw) > MAX_SIGNPOSTING_LENGTH:
        raise InvalidSignpostingData(
            f"Signposting must not exceed {MAX_SIGNPOSTING_LENGTH} characters "
            f"(received {len(raw)})"
        )

    clean = nh3.clean(
        raw,
        tags={"p", "strong", "em", "a", "ul", "ol", "li", "br"},
        attributes={"a": {"href", "target"}},
        url_schemes={"http", "https"},
    )

    text_only = re.sub(r"<[^>]+>", "", clean)
    if not text_only.strip():
        return None

    return clean


class PracticeRepository:
    def __init__(self, database_url: str):
        self.database_url = database_url

    def _validate_email(self, email: str) -> None:
        if not isinstance(email, str):
            raise InvalidEmailError(
                f"Email must be a string, got {type(email).__name__}"
            )
        if email != email.strip():
            raise InvalidEmailError(
                "Email contains leading or trailing whitespace"
            )
        parts = email.split("@")
        if len(parts) != 2 or not parts[0] or not parts[1]:
            raise InvalidEmailError(
                "Email must be in format 'local@domain'"
            )

    def _validate_doctor_list(self, names: List[str]) -> None:
        """
        Validate a list of doctor names.

        Raises InvalidDoctorListError if:
        - names is not a list
        - the list exceeds MAX_DOCTOR_LIST_LENGTH items
        - any item is not a non-empty string
        - any item exceeds MAX_DOCTOR_NAME_LENGTH characters
        """
        if not isinstance(names, list):
            raise InvalidDoctorListError("Doctor list must be a list")
        if len(names) > MAX_DOCTOR_LIST_LENGTH:
            raise InvalidDoctorListError(
                f"Doctor list must not exceed {MAX_DOCTOR_LIST_LENGTH} items "
                f"(received {len(names)})"
            )
        for i, name in enumerate(names):
            if not isinstance(name, str) or not name.strip():
                raise InvalidDoctorListError(
                    f"Doctor name at index {i} must be a non-empty string"
                )
            if len(name) > MAX_DOCTOR_NAME_LENGTH:
                raise InvalidDoctorListError(
                    f"Doctor name at index {i} exceeds {MAX_DOCTOR_NAME_LENGTH} characters"
                )

    # --- Practices ---

    def create_practice(self, practice_id: str, name: str, email: str) -> None:
        """
        Create a new practice.

        Raises InvalidEmailError if email is invalid.
        Raises psycopg2.errors.UniqueViolation if practice_id already exists.
        """
        self._validate_email(email)

        with get_conn(self.database_url) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO practices (practice_id, name, email)
                    VALUES (%s, %s, %s)
                    """,
                    (practice_id, name, email),
                )

    def get_practice(self, practice_id: str) -> Optional[dict]:
        """
        Get practice by ID.
        Returns dict with practice_id, name, email, created_at or None if not found.
        """
        with get_conn(self.database_url) as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT practice_id, name, email, created_at
                    FROM practices
                    WHERE practice_id = %s
                    """,
                    (practice_id,),
                )
                row = cur.fetchone()

        if row is None:
            return None
        return dict(row)

    def get_email(self, practice_id: str) -> str:
        """
        Get the email address for a practice.
        Raises PracticeNotFound if practice does not exist.
        """
        practice = self.get_practice(practice_id)
        if practice is None:
            raise PracticeNotFound(f"Practice not found: {practice_id}")
        return practice["email"]

    def update_email(self, practice_id: str, email: str, conn=None) -> None:
        """
        Update the email address for a practice.

        Raises InvalidEmailError if email is invalid.
        Raises PracticeNotFound if practice does not exist.
        Returns nothing on success.

        conn: see module-level conn parameter convention.
        """
        self._validate_email(email)

        practice = self.get_practice(practice_id)
        if practice is None:
            raise PracticeNotFound(f"Practice not found: {practice_id}")

        def _execute(cur) -> None:
            cur.execute(
                """
                UPDATE practices
                SET email = %s
                WHERE practice_id = %s
                """,
                (email, practice_id),
            )

        if conn is not None:
            with conn.cursor() as cur:
                _execute(cur)
        else:
            with get_conn(self.database_url) as own_conn:
                with own_conn.cursor() as cur:
                    _execute(cur)

    def practice_exists(self, practice_id: str) -> bool:
        return self.get_practice(practice_id) is not None

    def count_practices(self) -> int:
        with get_conn(self.database_url) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) FROM practices")
                row = cur.fetchone()
        return row[0]

    # --- Signposting ---

    def get_signposting(
        self, practice_id: str, condition_id: str
    ) -> Optional[str]:
        """
        Get signposting for a practice and condition.
        Returns None if no row exists, or the HTML string if it does.

        NOTE: despite the column name 'signposting_json', this column
        stores a plain HTML string. The column name is a legacy misnomer.
        """
        with get_conn(self.database_url) as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT signposting_json
                    FROM practice_signposting
                    WHERE practice_id = %s AND condition_id = %s
                    """,
                    (practice_id, condition_id),
                )
                row = cur.fetchone()

        if row is None:
            return None
        return row["signposting_json"]

    def set_signposting(
        self, practice_id: str, condition_id: str, html: str, conn=None
    ) -> None:
        """
        Set signposting for a practice and condition.

        Sanitises HTML before writing. If sanitised result is empty after
        sanitisation, a DELETE is issued instead of an INSERT/UPDATE.

        Raises PracticeNotFound if practice does not exist.
        Raises InvalidSignpostingData if html exceeds MAX_SIGNPOSTING_LENGTH.

        conn: see module-level conn parameter convention. When conn is
        supplied, both the potential DELETE and the INSERT/UPDATE use the
        same connection so the entire operation stays within the caller's
        transaction.
        """
        if not self.practice_exists(practice_id):
            raise PracticeNotFound(f"Practice not found: {practice_id}")

        sanitised = sanitise_signposting_html(html)

        if sanitised is None:
            # Delegate to delete_signposting, forwarding conn so that the
            # delete stays inside the caller's transaction when one is active.
            self.delete_signposting(practice_id, condition_id, conn=conn)
            return

        def _execute(cur) -> None:
            cur.execute(
                """
                INSERT INTO practice_signposting
                    (practice_id, condition_id, signposting_json, updated_at)
                VALUES (%s, %s, %s, NOW())
                ON CONFLICT (practice_id, condition_id)
                DO UPDATE SET
                    signposting_json = EXCLUDED.signposting_json,
                    updated_at       = NOW()
                """,
                (practice_id, condition_id, sanitised),
            )

        if conn is not None:
            with conn.cursor() as cur:
                _execute(cur)
        else:
            with get_conn(self.database_url) as own_conn:
                with own_conn.cursor() as cur:
                    _execute(cur)

    def delete_signposting(
        self, practice_id: str, condition_id: str, conn=None
    ) -> None:
        """
        Delete signposting for a practice and condition. No error if absent.

        conn: see module-level conn parameter convention.
        """
        def _execute(cur) -> None:
            cur.execute(
                """
                DELETE FROM practice_signposting
                WHERE practice_id = %s AND condition_id = %s
                """,
                (practice_id, condition_id),
            )

        if conn is not None:
            with conn.cursor() as cur:
                _execute(cur)
        else:
            with get_conn(self.database_url) as own_conn:
                with own_conn.cursor() as cur:
                    _execute(cur)

    # --- Doctor list ---

    def get_doctors(self, practice_id: str) -> List[str]:
        """
        Return the doctor list for a practice, ordered by display_order.
        Returns an empty list if no doctors are configured.
        """
        with get_conn(self.database_url) as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT name
                    FROM practice_doctors
                    WHERE practice_id = %s
                    ORDER BY display_order ASC
                    """,
                    (practice_id,),
                )
                rows = cur.fetchall()

        return [row["name"] for row in rows]

    def set_doctors(self, practice_id: str, names: List[str], conn=None) -> None:
        """
        Replace the entire doctor list for a practice atomically.

        Deletes all existing rows for the practice and re-inserts with
        sequential display_order values (0-based) in a single transaction.

        An empty list is valid — it clears the doctor list entirely.

        Raises InvalidDoctorListError if validation fails.
        Raises PracticeNotFound if practice does not exist.

        conn: see module-level conn parameter convention.
        """
        self._validate_doctor_list(names)

        if not self.practice_exists(practice_id):
            raise PracticeNotFound(f"Practice not found: {practice_id}")

        def _execute(cur) -> None:
            cur.execute(
                "DELETE FROM practice_doctors WHERE practice_id = %s",
                (practice_id,),
            )
            if names:
                psycopg2.extras.execute_values(
                    cur,
                    """
                    INSERT INTO practice_doctors (practice_id, name, display_order)
                    VALUES %s
                    """,
                    [
                        (practice_id, name.strip(), order)
                        for order, name in enumerate(names)
                    ],
                )

        if conn is not None:
            with conn.cursor() as cur:
                _execute(cur)
        else:
            with get_conn(self.database_url) as own_conn:
                with own_conn.cursor() as cur:
                    _execute(cur)
                    
    def lock_practice(self, practice_id: str, conn) -> None:
        """
        Acquire a row-level lock on the practice row for the current transaction.

        Executes SELECT ... FOR UPDATE, which blocks until any concurrent
        transaction holding a lock on this row commits or rolls back. This
        serialises concurrent user add/remove operations for the same practice,
        preventing two simultaneous requests from both passing the minimum-user
        check and both proceeding to delete.

        conn is required with no default — there is no sensible fallback.
        Calling this without a surrounding transaction would acquire and
        immediately release the lock on a separate connection, making it useless.
        """
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id FROM practices WHERE practice_id = %s FOR UPDATE",
                (practice_id,),
            )
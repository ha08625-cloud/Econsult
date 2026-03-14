"""
Practice repository.

Database access for practice identity and practice-specific configuration.
Handles the practices and practice_signposting tables.

This module is responsible for:
- CRUD operations for practices (including email)
- CRUD operations for practice signposting
- HTML sanitisation for signposting content
- Email format validation

Table creation is handled once at startup by app/core/db.init_database().

This module must never:
- Access clinical data (rulesets, RuntimeState, answers)
- Perform composition logic (that belongs in presentation_service)
- Handle authentication (that belongs in practice_context, Phase 1B)
"""

import re
from typing import List, Optional

import nh3
import psycopg2.extras
from psycopg2.extras import RealDictCursor

from app.core.db import get_conn


MAX_SIGNPOSTING_LENGTH = 5000
QUILL_EMPTY_OUTPUT = "<p></p>"


class PracticeNotFound(Exception):
    """Raised when a practice_id does not exist."""
    pass


class InvalidSignpostingData(Exception):
    """Raised when signposting HTML is too long or otherwise invalid."""
    pass


class InvalidEmailError(Exception):
    """Raised when an email address fails validation."""
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
        self, practice_id: str, condition_id: str, html: str
    ) -> None:
        """
        Set signposting for a practice and condition.

        Sanitises HTML before writing. If sanitised result is None,
        the row is deleted rather than written.

        Raises PracticeNotFound if practice does not exist.
        Raises InvalidSignpostingData if html exceeds MAX_SIGNPOSTING_LENGTH.
        """
        if not self.practice_exists(practice_id):
            raise PracticeNotFound(f"Practice not found: {practice_id}")

        sanitised = sanitise_signposting_html(html)

        if sanitised is None:
            self.delete_signposting(practice_id, condition_id)
            return

        with get_conn(self.database_url) as conn:
            with conn.cursor() as cur:
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

    def delete_signposting(self, practice_id: str, condition_id: str) -> None:
        """Delete signposting for a practice and condition. No error if absent."""
        with get_conn(self.database_url) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    DELETE FROM practice_signposting
                    WHERE practice_id = %s AND condition_id = %s
                    """,
                    (practice_id, condition_id),
                )

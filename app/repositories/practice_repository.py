"""
Practice repository.

Database access for practice identity and practice-specific configuration.
Handles the practices and practice_signposting tables.

This module is responsible for:
- Initialising practice-related tables on startup
- CRUD operations for practices (including email)
- CRUD operations for practice signposting
- HTML sanitisation for signposting content
- Email format validation

This module must never:
- Access clinical data (rulesets, RuntimeState, answers)
- Perform composition logic (that belongs in presentation_service)
- Handle authentication (that belongs in practice_context, Phase 1B)
"""

import re
import sqlite3
import json
from contextlib import contextmanager
from typing import List, Optional

import nh3


# Maximum permitted length for raw signposting HTML before sanitisation.
# Enforced in sanitise_signposting_html before nh3 runs.
MAX_SIGNPOSTING_LENGTH = 5000

# The exact HTML string emitted by Quill 2.0.2 when the editor is empty.
# Used as a sentinel in tests and in the sanitiser's empty-content check.
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
       any non-whitespace characters survive. If not, return None —
       the content is effectively empty and the row should not be stored.

    Allowed tags : p, strong, em, a, ul, ol, li, br
    Allowed attrs: href, rel, target on <a> only
    Allowed URL schemes on href: http, https (blocks javascript: URIs)

    Note on rel/target: Quill 2.0.2 automatically adds
    rel="noopener noreferrer" and target="_blank" to every link it
    produces. These must survive sanitisation. Stripping them would
    silently remove a security attribute.

    Note on bare text: nh3 does not wrap bare text nodes in <p> tags.
    In normal use this does not arise because Quill wraps all content
    in block elements. The sanitiser does not handle bare unwrapped
    text and there is no test case for it.

    Returns:
        Sanitised HTML string, or None if content is empty after
        sanitisation.

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
        # link_rel is intentionally omitted: the default is 'noopener noreferrer',
        # which nh3 injects automatically on every <a> tag.
        # Do NOT add 'rel' to the attributes dict — nh3 reserves it and will panic.
        # DOMPurify in admin.html and App.tsx must still allow 'rel' in ALLOWED_ATTR
        # because the stored HTML will contain rel="noopener noreferrer".
    )

    # Strip all tags from the sanitised output and check whether
    # any non-whitespace content survives. An empty result means
    # the input contained no displayable content.
    text_only = re.sub(r"<[^>]+>", "", clean)
    if not text_only.strip():
        return None

    return clean


class PracticeRepository:
    def __init__(self, db_path: str):
        self.db_path = db_path
        self._init_tables()

    def _init_tables(self):
        with self._conn() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS practices (
                    practice_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    email TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS practice_signposting (
                    practice_id TEXT NOT NULL REFERENCES practices(practice_id),
                    condition_id TEXT NOT NULL,
                    signposting_json TEXT NOT NULL,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

                    PRIMARY KEY (practice_id, condition_id)
                )
                """
            )

    @contextmanager
    def _conn(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    # --- Email validation ---

    def _validate_email(self, email: str) -> None:
        """
        Validate email format.

        Rules:
        - Must be a string
        - Must not have leading or trailing whitespace
        - Must contain exactly one '@'
        - Local part (before '@') must be non-empty
        - Domain part (after '@') must be non-empty
        """
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

        Validates email format before inserting.
        Raises InvalidEmailError if email is invalid.
        Raises sqlite3.IntegrityError if practice_id already exists.
        """
        self._validate_email(email)

        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO practices (practice_id, name, email)
                VALUES (?, ?, ?)
                """,
                (practice_id, name, email),
            )

    def get_practice(self, practice_id: str) -> Optional[dict]:
        """
        Get practice by ID.
        Returns dict with practice_id, name, email, created_at or None if not found.
        """
        with self._conn() as conn:
            row = conn.execute(
                """
                SELECT practice_id, name, email, created_at
                FROM practices
                WHERE practice_id = ?
                """,
                (practice_id,),
            ).fetchone()

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
        """Check if a practice exists."""
        return self.get_practice(practice_id) is not None

    def count_practices(self) -> int:
        """Return total number of practices in the database."""
        with self._conn() as conn:
            row = conn.execute("SELECT COUNT(*) FROM practices").fetchone()
            return row[0]

    # --- Signposting ---

    def get_signposting(
        self, practice_id: str, condition_id: str
    ) -> Optional[str]:
        """
        Get signposting for a practice and condition.

        Returns:
        - None if no signposting is configured (row does not exist)
        - HTML string if configured

        Does not validate that practice_id or condition_id exist.
        This is intentional - allows graceful degradation if practice
        is deleted but signposting query is still made.

        NOTE: despite the column name 'signposting_json', this column
        stores a plain HTML string, not JSON. The column name is a
        legacy misnomer from the original list-of-strings design.
        See architecture.md Section 15.4 for the migration assumption
        that makes this format change safe in the current Railway deployment.
        JSON error handling has been removed because this column no
        longer contains JSON.
        """
        with self._conn() as conn:
            row = conn.execute(
                """
                SELECT signposting_json
                FROM practice_signposting
                WHERE practice_id = ? AND condition_id = ?
                """,
                (practice_id, condition_id),
            ).fetchone()

            if row is None:
                return None

            return row["signposting_json"]

    def set_signposting(
        self, practice_id: str, condition_id: str, html: str
    ) -> None:
        """
        Set signposting for a practice and condition.

        Sanitises the HTML input via sanitise_signposting_html before
        writing. If the sanitised result is None (empty content), the
        row is deleted rather than written — an empty write is treated
        as an instruction to clear signposting.

        Raises:
        - PracticeNotFound if practice does not exist
        - InvalidSignpostingData if html exceeds MAX_SIGNPOSTING_LENGTH

        NOTE: despite the column name 'signposting_json', this column
        stores a plain HTML string, not JSON. See architecture.md
        Section 15.4.
        """
        if not self.practice_exists(practice_id):
            raise PracticeNotFound(f"Practice not found: {practice_id}")

        sanitised = sanitise_signposting_html(html)

        if sanitised is None:
            # Empty content: delete any existing row rather than writing.
            self.delete_signposting(practice_id, condition_id)
            return

        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO practice_signposting (practice_id, condition_id, signposting_json, updated_at)
                VALUES (?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(practice_id, condition_id)
                DO UPDATE SET signposting_json = excluded.signposting_json,
                              updated_at = CURRENT_TIMESTAMP
                """,
                (practice_id, condition_id, sanitised),
            )

    def delete_signposting(self, practice_id: str, condition_id: str) -> None:
        """
        Delete signposting for a practice and condition.
        No error if row does not exist.
        """
        with self._conn() as conn:
            conn.execute(
                """
                DELETE FROM practice_signposting
                WHERE practice_id = ? AND condition_id = ?
                """,
                (practice_id, condition_id),
            )

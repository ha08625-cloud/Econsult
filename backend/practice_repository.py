"""
Practice repository.

Database access for practice identity and practice-specific configuration.
Handles the practices and practice_signposting tables.

This module is responsible for:
- Initialising practice-related tables on startup
- CRUD operations for practices
- CRUD operations for practice signposting
- JSON validation for signposting content

This module must never:
- Access clinical data (rulesets, RuntimeState, answers)
- Perform composition logic (that belongs in presentation_service)
- Handle authentication (that belongs in practice_context, Phase 1B)
"""

import sqlite3
import json
from contextlib import contextmanager
from typing import List, Optional


class PracticeNotFound(Exception):
    """Raised when a practice_id does not exist."""
    pass


class InvalidSignpostingData(Exception):
    """Raised when signposting JSON is malformed or invalid."""
    pass


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

    # --- Practices ---

    def create_practice(self, practice_id: str, name: str) -> None:
        """
        Create a new practice.
        Raises sqlite3.IntegrityError if practice_id already exists.
        """
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO practices (practice_id, name)
                VALUES (?, ?)
                """,
                (practice_id, name),
            )

    def get_practice(self, practice_id: str) -> Optional[dict]:
        """
        Get practice by ID.
        Returns dict with practice_id, name, created_at or None if not found.
        """
        with self._conn() as conn:
            row = conn.execute(
                """
                SELECT practice_id, name, created_at
                FROM practices
                WHERE practice_id = ?
                """,
                (practice_id,),
            ).fetchone()

            if row is None:
                return None

            return dict(row)

    def practice_exists(self, practice_id: str) -> bool:
        """Check if a practice exists."""
        return self.get_practice(practice_id) is not None

    # --- Signposting ---

    def get_signposting(
        self, practice_id: str, condition_id: str
    ) -> Optional[List[str]]:
        """
        Get signposting for a practice and condition.

        Returns:
        - None if no signposting is configured (row does not exist)
        - List of strings if configured (may be empty list)

        Does not validate that practice_id or condition_id exist.
        This is intentional - allows graceful degradation if practice
        is deleted but signposting query is still made.
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

            # Parse JSON - should always be valid if set_signposting was used
            try:
                items = json.loads(row["signposting_json"])
            except json.JSONDecodeError as e:
                # This should not happen if data was written via set_signposting
                # Log error and return None for graceful degradation
                # In production, this would log to a proper logging system
                print(f"WARNING: Malformed signposting JSON for {practice_id}/{condition_id}: {e}")
                return None

            return items

    def set_signposting(
        self, practice_id: str, condition_id: str, items: List[str]
    ) -> None:
        """
        Set signposting for a practice and condition.

        Validates:
        - practice_id exists
        - items is a list
        - each item is a non-empty string

        Raises:
        - PracticeNotFound if practice does not exist
        - InvalidSignpostingData if items fail validation
        """
        # Validate practice exists
        if not self.practice_exists(practice_id):
            raise PracticeNotFound(f"Practice not found: {practice_id}")

        # Validate items
        self._validate_signposting_items(items)

        # Serialize to JSON
        signposting_json = json.dumps(items)

        # Upsert
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO practice_signposting (practice_id, condition_id, signposting_json, updated_at)
                VALUES (?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(practice_id, condition_id) 
                DO UPDATE SET signposting_json = excluded.signposting_json,
                              updated_at = CURRENT_TIMESTAMP
                """,
                (practice_id, condition_id, signposting_json),
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

    def _validate_signposting_items(self, items: List[str]) -> None:
        """
        Validate signposting items.

        Rules:
        - Must be a list
        - Each item must be a string
        - Each item must be non-empty after stripping whitespace
        - Empty list is allowed (explicit "no signposting")
        """
        if not isinstance(items, list):
            raise InvalidSignpostingData(
                f"Signposting must be a list, got {type(items).__name__}"
            )

        for i, item in enumerate(items):
            if not isinstance(item, str):
                raise InvalidSignpostingData(
                    f"Signposting item {i} must be a string, got {type(item).__name__}"
                )
            if item.strip() == "":
                raise InvalidSignpostingData(
                    f"Signposting item {i} must be non-empty"
                )
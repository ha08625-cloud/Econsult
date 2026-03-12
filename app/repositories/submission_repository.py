"""
Submission repository.

Database access for submission records.
Handles the submission_records table.

This module is responsible for:
- Initialising the submission_records table on startup
- Creating submission records at the point of form completion
- Updating delivery status after email send attempt
- Retrieving submissions by ID
- Listing submissions by delivery status (for manual inspection of failures)

This module must never:
- Access clinical engine modules (form_logic, safety_engine, etc.)
- Send emails (that belongs in email_service)
- Make decisions about retry logic (that belongs in the calling layer)
"""

import sqlite3
import json
from contextlib import contextmanager
from datetime import datetime
from typing import Optional

from app.models.serialisation_contracts import ClinicalOutput, AuditOutput


VALID_STATUSES = {"pending", "sent", "failed"}


class SubmissionNotFound(Exception):
    """Raised when a submission_id does not exist."""
    pass


class InvalidDeliveryStatus(Exception):
    """Raised when an unrecognised delivery status is used."""
    pass


class SubmissionRepository:
    def __init__(self, db_path: str):
        self.db_path = db_path
        self._init_tables()

    def _init_tables(self):
        with self._conn() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS submission_records (
                    submission_id TEXT PRIMARY KEY,
                    practice_id TEXT NOT NULL,
                    condition_id TEXT NOT NULL,
                    clinical_output_json TEXT NOT NULL,
                    audit_output_json TEXT NOT NULL,
                    submitted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    delivery_status TEXT NOT NULL DEFAULT 'pending',
                    delivery_email TEXT NOT NULL,
                    delivered_at TIMESTAMP,
                    delivery_error TEXT
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

    def _validate_status(self, status: str) -> None:
        if status not in VALID_STATUSES:
            raise InvalidDeliveryStatus(
                f"Invalid delivery status: {status!r}. "
                f"Must be one of: {sorted(VALID_STATUSES)}"
            )

    def create_submission(
        self,
        submission_id: str,
        practice_id: str,
        condition_id: str,
        clinical_output: ClinicalOutput,
        audit_output: AuditOutput,
        delivery_email: str,
    ) -> None:
        """
        Create a new submission record with delivery_status = 'pending'.

        clinical_output and audit_output are serialised to JSON at write time.
        delivery_email is stored as-is from the practice record at the time
        of submission, so the audit trail reflects where the form was actually sent.

        Raises sqlite3.IntegrityError if submission_id already exists.
        """
        from dataclasses import asdict

        clinical_json = json.dumps(asdict(clinical_output))
        audit_json = json.dumps(asdict(audit_output))

        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO submission_records (
                    submission_id,
                    practice_id,
                    condition_id,
                    clinical_output_json,
                    audit_output_json,
                    delivery_status,
                    delivery_email
                )
                VALUES (?, ?, ?, ?, ?, 'pending', ?)
                """,
                (
                    submission_id,
                    practice_id,
                    condition_id,
                    clinical_json,
                    audit_json,
                    delivery_email,
                ),
            )

    def update_delivery_status(
        self,
        submission_id: str,
        status: str,
        delivered_at: Optional[datetime] = None,
        delivery_error: Optional[str] = None,
    ) -> None:
        """
        Update the delivery status of a submission.

        status must be one of: 'pending', 'sent', 'failed'.
        delivered_at should be set when status is 'sent'.
        delivery_error should be set when status is 'failed'.

        Raises InvalidDeliveryStatus if status is not valid.
        Raises SubmissionNotFound if submission_id does not exist.
        """
        self._validate_status(status)

        delivered_at_str = (
            delivered_at.isoformat() if delivered_at is not None else None
        )

        with self._conn() as conn:
            result = conn.execute(
                """
                UPDATE submission_records
                SET delivery_status = ?,
                    delivered_at = ?,
                    delivery_error = ?
                WHERE submission_id = ?
                """,
                (status, delivered_at_str, delivery_error, submission_id),
            )

            if result.rowcount == 0:
                raise SubmissionNotFound(submission_id)

    def get_submission(self, submission_id: str) -> dict:
        """
        Get a submission record by ID.

        Returns a dict with all columns.
        clinical_output_json and audit_output_json are returned as raw JSON strings,
        not parsed - the caller decides whether to deserialise.

        Raises SubmissionNotFound if submission_id does not exist.
        """
        with self._conn() as conn:
            row = conn.execute(
                """
                SELECT *
                FROM submission_records
                WHERE submission_id = ?
                """,
                (submission_id,),
            ).fetchone()

            if row is None:
                raise SubmissionNotFound(submission_id)

            return dict(row)

    def list_by_status(self, status: str) -> list[dict]:
        """
        List all submission records with the given delivery_status.

        Returns a list of dicts ordered by submitted_at ascending
        (oldest undelivered first, which is the natural inspection order).

        Raises InvalidDeliveryStatus if status is not a recognised value.
        This is intentional: a typo should not silently return an empty list
        when the caller expected to find failed submissions.
        """
        self._validate_status(status)

        with self._conn() as conn:
            rows = conn.execute(
                """
                SELECT *
                FROM submission_records
                WHERE delivery_status = ?
                ORDER BY submitted_at ASC
                """,
                (status,),
            ).fetchall()

            return [dict(row) for row in rows]

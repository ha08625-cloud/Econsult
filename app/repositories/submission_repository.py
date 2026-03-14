"""
Submission repository.

Database access for submission records.
Handles the submission_records table.

This module is responsible for:
- Creating submission records at the point of form completion
- Updating delivery status after email send attempt
- Retrieving submissions by ID
- Listing submissions by delivery status

Table creation is handled once at startup by app/core/db.init_database().

This module must never:
- Access clinical engine modules (form_logic, safety_engine, etc.)
- Send emails (that belongs in email_service)
- Make decisions about retry logic (that belongs in the calling layer)
"""

from dataclasses import asdict
from datetime import datetime
from typing import Optional

from psycopg2.extras import RealDictCursor

from app.core.db import get_conn
from app.models.serialisation_contracts import ClinicalOutput, AuditOutput


VALID_STATUSES = {"pending", "sent", "failed"}


class SubmissionNotFound(Exception):
    """Raised when a submission_id does not exist."""
    pass


class InvalidDeliveryStatus(Exception):
    """Raised when an unrecognised delivery status is used."""
    pass


class SubmissionRepository:
    def __init__(self, database_url: str):
        self.database_url = database_url

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

        clinical_output and audit_output are stored as JSONB. psycopg2 does not
        automatically serialise dataclasses, so we convert to dict with asdict()
        first and pass the dict directly — psycopg2 handles JSON serialisation
        transparently for JSONB columns via Json adapter.

        Raises psycopg2.errors.UniqueViolation if submission_id already exists.
        """
        import psycopg2.extras

        clinical_dict = asdict(clinical_output)
        audit_dict = asdict(audit_output)

        with get_conn(self.database_url) as conn:
            with conn.cursor() as cur:
                cur.execute(
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
                    VALUES (%s, %s, %s, %s, %s, 'pending', %s)
                    """,
                    (
                        submission_id,
                        practice_id,
                        condition_id,
                        psycopg2.extras.Json(clinical_dict),
                        psycopg2.extras.Json(audit_dict),
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
        delivered_at is a datetime object passed directly to psycopg2, which
        handles TIMESTAMPTZ serialisation transparently — no .isoformat() needed.

        Raises InvalidDeliveryStatus if status is not valid.
        Raises SubmissionNotFound if submission_id does not exist.
        """
        self._validate_status(status)

        with get_conn(self.database_url) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE submission_records
                    SET delivery_status = %s,
                        delivered_at    = %s,
                        delivery_error  = %s
                    WHERE submission_id = %s
                    """,
                    (status, delivered_at, delivery_error, submission_id),
                )

                if cur.rowcount == 0:
                    raise SubmissionNotFound(submission_id)

    def get_submission(self, submission_id: str) -> dict:
        """
        Get a submission record by ID.

        Returns a dict with all columns. clinical_output_json and
        audit_output_json are returned as Python dicts (psycopg2 deserialises
        JSONB columns automatically) — callers no longer need to call
        json.loads() on these fields.

        Raises SubmissionNotFound if submission_id does not exist.
        """
        with get_conn(self.database_url) as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT *
                    FROM submission_records
                    WHERE submission_id = %s
                    """,
                    (submission_id,),
                )
                row = cur.fetchone()

        if row is None:
            raise SubmissionNotFound(submission_id)
        return dict(row)

    def list_by_status(self, status: str) -> list[dict]:
        """
        List all submission records with the given delivery_status.

        Returns a list of dicts ordered by submitted_at ascending.

        Raises InvalidDeliveryStatus if status is not a recognised value.
        """
        self._validate_status(status)

        with get_conn(self.database_url) as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT *
                    FROM submission_records
                    WHERE delivery_status = %s
                    ORDER BY submitted_at ASC
                    """,
                    (status,),
                )
                rows = cur.fetchall()

        return [dict(row) for row in rows]

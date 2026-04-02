"""
Delivery repository.

Database access for the delivery_jobs table.

Responsibilities:
- Creating delivery jobs once the PDF attachment has been saved.
- Claiming the next eligible pending job (SKIP LOCKED, single job per call).
- Marking jobs as sent or failed.
- Retrieving individual jobs by ID.

Architecture rules:
- This module must never import clinical engine modules.
- This module must never send emails or generate PDFs.
- Retry policy constants are imported from delivery_constants; this
  module does not define policy.
- All claim operations use SELECT ... FOR UPDATE SKIP LOCKED and
  immediately update next_retry_after within the same transaction.

Ordering invariant (enforced by the PDF worker, documented here):
A delivery_jobs row can only exist after save_attachment has completed
successfully. Therefore get_attachment will always find the attachment
when a delivery job is claimed. Do not break this invariant in the PDF
worker's operation ordering.
"""

from datetime import datetime
from typing import Optional

from psycopg2.extras import RealDictCursor

from app.core.db import get_conn
from app.services.delivery.delivery_constants import MAX_ATTEMPTS, RETRY_BACKOFF_MINUTES


class DeliveryJobNotFound(Exception):
    """Raised when a job_id does not exist in delivery_jobs."""
    pass


class DeliveryRepository:
    def __init__(self, database_url: str):
        self.database_url = database_url

    # ------------------------------------------------------------------
    # Job creation
    # ------------------------------------------------------------------

    def create_job(
        self,
        submission_id: str,
        to_email: str,
        condition_label: str,
        submitted_at: datetime,
    ) -> str:
        """
        Insert a new delivery_jobs row with status = 'pending'.

        The submission_id column has a UNIQUE constraint, so calling this
        twice with the same submission_id is safe: the second call uses
        ON CONFLICT DO NOTHING and the existing row is left untouched.
        This makes the call idempotent and safe across PDF worker retries.

        to_email, condition_label, and submitted_at are denormalised here
        so the delivery worker never needs to read submission_records.

        Returns the job UUID as a string (the existing row's id if the
        conflict path was taken).
        """
        with get_conn(self.database_url) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO delivery_jobs (
                        submission_id,
                        to_email,
                        condition_label,
                        submitted_at
                    )
                    VALUES (
                        %(submission_id)s,
                        %(to_email)s,
                        %(condition_label)s,
                        %(submitted_at)s
                    )
                    ON CONFLICT (submission_id) DO NOTHING
                    RETURNING id
                    """,
                    {
                        "submission_id": submission_id,
                        "to_email": to_email,
                        "condition_label": condition_label,
                        "submitted_at": submitted_at,
                    },
                )
                row = cur.fetchone()

                if row is not None:
                    # Fresh insert: return the new id.
                    return str(row[0])

                # Conflict path: fetch the existing row's id.
                cur.execute(
                    "SELECT id FROM delivery_jobs WHERE submission_id = %s",
                    (submission_id,),
                )
                existing = cur.fetchone()
                return str(existing[0])

    # ------------------------------------------------------------------
    # Job claiming
    # ------------------------------------------------------------------

    def claim_next_pending(self) -> Optional[dict]:
        """
        Claim the next eligible pending delivery_jobs row.

        A job is eligible when:
        - status = 'pending'
        - next_retry_after IS NULL OR next_retry_after <= NOW()

        The claim is performed atomically:
        1. SELECT ... FOR UPDATE SKIP LOCKED finds and locks the row.
        2. An immediate UPDATE pushes next_retry_after 10 minutes into the
           future, moving the row outside the eligible window for any
           concurrent worker.
        Both steps happen inside a single transaction.

        Returns a dict of the claimed row, or None if the queue is empty.
        """
        with get_conn(self.database_url) as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT *
                    FROM delivery_jobs
                    WHERE status = 'pending'
                      AND (next_retry_after IS NULL OR next_retry_after <= NOW())
                    ORDER BY created_at ASC
                    LIMIT 1
                    FOR UPDATE SKIP LOCKED
                    """
                )
                row = cur.fetchone()
                if row is None:
                    return None

                cur.execute(
                    """
                    UPDATE delivery_jobs
                    SET next_retry_after = NOW() + INTERVAL '10 minutes',
                        updated_at       = NOW()
                    WHERE id = %s
                    """,
                    (row["id"],),
                )

        return dict(row)

    # ------------------------------------------------------------------
    # Outcome recording
    # ------------------------------------------------------------------

    def mark_sent(self, job_id: str) -> None:
        """
        Mark a delivery_job as successfully sent.

        Sets status = 'sent' and updated_at. Does not clear last_error
        (historical error context is useful if a job failed before
        eventually succeeding on a later attempt).
        """
        with get_conn(self.database_url) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE delivery_jobs
                    SET status     = 'sent',
                        updated_at = NOW()
                    WHERE id = %s
                    """,
                    (job_id,),
                )

    def mark_failed(
        self,
        job_id: str,
        error: str,
        next_retry_after: Optional[datetime],
    ) -> None:
        """
        Record a failed delivery attempt.

        Increments attempt_count by 1. If the new attempt_count reaches
        MAX_ATTEMPTS, status is set to 'failed' permanently. Otherwise
        status remains 'pending' and next_retry_after is set to the
        supplied value.

        Raises DeliveryJobNotFound if the job_id does not exist.
        """
        with get_conn(self.database_url) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE delivery_jobs
                    SET attempt_count    = attempt_count + 1,
                        last_error       = %(error)s,
                        next_retry_after = %(next_retry_after)s,
                        status           = CASE
                            WHEN attempt_count + 1 >= %(max_attempts)s THEN 'failed'
                            ELSE 'pending'
                        END,
                        updated_at       = NOW()
                    WHERE id = %(job_id)s
                    RETURNING id
                    """,
                    {
                        "job_id": job_id,
                        "error": error,
                        "next_retry_after": next_retry_after,
                        "max_attempts": MAX_ATTEMPTS,
                    },
                )
                result = cur.fetchone()
                if result is None:
                    raise DeliveryJobNotFound(job_id)

    # ------------------------------------------------------------------
    # Lookup
    # ------------------------------------------------------------------

    def get(self, job_id: str) -> dict:
        """
        Return the full delivery_jobs row for job_id.

        Raises DeliveryJobNotFound if absent.
        """
        with get_conn(self.database_url) as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    "SELECT * FROM delivery_jobs WHERE id = %s",
                    (job_id,),
                )
                row = cur.fetchone()

        if row is None:
            raise DeliveryJobNotFound(job_id)

        return dict(row)
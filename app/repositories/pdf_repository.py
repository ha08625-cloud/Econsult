"""
PDF repository.

Database access for the pdf_jobs table.

Responsibilities:
- Creating PDF jobs when a form is submitted.
- Claiming the next eligible pending job (SKIP LOCKED, single job per call).
- Marking jobs as done or failed.
- Detecting orphaned submissions (submitted but never enqueued for PDF).

Architecture rules:
- This module must never import clinical engine modules.
- This module must never send emails or generate PDFs.
- Retry policy constants (MAX_PDF_ATTEMPTS, PDF_RETRY_BACKOFF_MINUTES)
  are imported from pdf_constants; this module does not define policy.
- All claim operations use SELECT ... FOR UPDATE SKIP LOCKED and
  immediately update next_retry_after within the same transaction so
  two concurrent workers cannot claim the same job.
"""

from datetime import datetime, timedelta, timezone
from typing import Optional

from psycopg2.extras import RealDictCursor

from app.core.db import get_conn
from app.services.delivery.pdf_constants import MAX_PDF_ATTEMPTS


class PDFJobNotFound(Exception):
    """Raised when a job_id does not exist in pdf_jobs."""
    pass


class PDFRepository:
    def __init__(self, database_url: str):
        self.database_url = database_url

    # ------------------------------------------------------------------
    # Job creation
    # ------------------------------------------------------------------

    def create_job(
        self,
        submission_id: str,
        attachment_count: int,
        delivery_email: str,
    ) -> str:
        """
        Insert a new pdf_jobs row with status = 'pending'.

        attachment_count and delivery_email are captured here at submission
        time so the PDF worker can read them from the job row without
        touching submission_records. This makes the PDF worker robust to
        Migration D, which drops those columns from submission_records.

        Returns the new job UUID as a string.

        Raises psycopg2.errors.UniqueViolation if a job already exists for
        this submission_id (the FK has no UNIQUE constraint — callers must
        not call this twice for the same submission outside of the retry
        UPSERT path).
        """
        with get_conn(self.database_url) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO pdf_jobs (
                        submission_id,
                        attachment_count,
                        delivery_email
                    )
                    VALUES (%(submission_id)s, %(attachment_count)s, %(delivery_email)s)
                    RETURNING id
                    """,
                    {
                        "submission_id": submission_id,
                        "attachment_count": attachment_count,
                        "delivery_email": delivery_email,
                    },
                )
                row = cur.fetchone()
        return str(row[0])

    # ------------------------------------------------------------------
    # Job claiming
    # ------------------------------------------------------------------

    def claim_next_pending(self) -> Optional[dict]:
        """
        Claim the next eligible pending pdf_jobs row.

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

        The returned dict includes all columns of pdf_jobs.
        """
        with get_conn(self.database_url) as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT *
                    FROM pdf_jobs
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

                # Push next_retry_after to prevent concurrent re-claim
                # while this worker processes the job.
                cur.execute(
                    """
                    UPDATE pdf_jobs
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

    def mark_done(self, job_id: str) -> None:
        """
        Mark a pdf_job as successfully completed.

        Sets status = 'done', clears last_error, and sets updated_at.

        Does not verify that the job existed before — callers must supply
        a valid job_id obtained from claim_next_pending.
        """
        with get_conn(self.database_url) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE pdf_jobs
                    SET status     = 'done',
                        last_error = NULL,
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
    ) -> bool:
        """
        Record a failed PDF generation attempt.

        Increments attempt_count by 1. If the new attempt_count reaches
        MAX_PDF_ATTEMPTS, status is set to 'failed' permanently. Otherwise
        status remains 'pending' and next_retry_after is set to the
        supplied value so the job is not re-claimed before the backoff
        window elapses.

        Returns True if the job has been permanently exhausted (status is
        now 'failed'), False if it remains pending for a future retry.

        next_retry_after must be supplied by the caller (typically the
        PDF worker, which reads PDF_RETRY_BACKOFF_MINUTES). Passing None
        leaves the job immediately eligible for re-claim, which is only
        appropriate for testing.

        Raises PDFJobNotFound if the job_id does not exist.
        """
        with get_conn(self.database_url) as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    UPDATE pdf_jobs
                    SET attempt_count    = attempt_count + 1,
                        last_error       = %(error)s,
                        next_retry_after = %(next_retry_after)s,
                        status           = CASE
                            WHEN attempt_count + 1 >= %(max_attempts)s THEN 'failed'
                            ELSE 'pending'
                        END,
                        updated_at       = NOW()
                    WHERE id = %(job_id)s
                    RETURNING id, status
                    """,
                    {
                        "job_id": job_id,
                        "error": error,
                        "next_retry_after": next_retry_after,
                        "max_attempts": MAX_PDF_ATTEMPTS,
                    },
                )
                result = cur.fetchone()
                if result is None:
                    raise PDFJobNotFound(job_id)
                return result["status"] == "failed"

    # ------------------------------------------------------------------
    # Lookup
    # ------------------------------------------------------------------

    def get(self, job_id: str) -> dict:
        """
        Return the full pdf_jobs row for job_id.

        Raises PDFJobNotFound if absent.
        """
        with get_conn(self.database_url) as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    "SELECT * FROM pdf_jobs WHERE id = %s",
                    (job_id,),
                )
                row = cur.fetchone()

        if row is None:
            raise PDFJobNotFound(job_id)

        return dict(row)

    # ------------------------------------------------------------------
    # Orphan detection
    # ------------------------------------------------------------------

    def list_orphaned_submissions(self, older_than_minutes: int) -> list[str]:
        """
        Return submission IDs that have no corresponding pdf_jobs row.

        An orphan is a submission_records row where:
        - No matching row exists in pdf_jobs (LEFT JOIN, IS NULL)
        - submitted_at < NOW() - older_than_minutes

        This pattern indicates the form router crashed after
        create_submission but before pdf_repo.create_job. The PDF worker
        logs orphans at CRITICAL level; no mutation is performed. Recovery
        requires operator action (see arch_submission.md).

        Returns submission IDs only. Returns an empty list if none found.
        """
        with get_conn(self.database_url) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT sr.submission_id
                    FROM submission_records sr
                    LEFT JOIN pdf_jobs pj ON sr.submission_id = pj.submission_id
                    WHERE pj.submission_id IS NULL
                      AND sr.submitted_at < NOW() - INTERVAL '1 minute' * %(threshold)s
                    ORDER BY sr.submitted_at ASC
                    """,
                    {"threshold": older_than_minutes},
                )
                rows = cur.fetchall()

        return [str(row[0]) for row in rows]
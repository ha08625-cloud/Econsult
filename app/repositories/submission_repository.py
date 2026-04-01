"""
Submission repository.

Database access for submission records.
Handles the submission_records table.

This module is responsible for:
- Creating submission records at the point of form completion
- Updating delivery status after email send attempt
- Retrieving submissions by ID
- Listing submissions by delivery status
- Providing lightweight delivery projections (PendingDelivery)
- Atomically recording delivery attempt outcomes
- Querying submissions eligible for delivery retry
- Detecting orphan submissions (pending with no delivery attempt)

Table creation is handled by Alembic migrations at startup.

This module must never:
- Access clinical engine modules (form_logic, safety_engine, etc.)
- Send emails (that belongs in delivery_service)
- Make decisions about retry logic (that belongs in the orchestration layer)
"""

from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Optional

import psycopg2.extras
from psycopg2.extras import RealDictCursor

from app.core.db import get_conn
from app.models.serialisation_contracts import ClinicalOutput, AuditOutput


VALID_STATUSES = {"pending", "sent", "failed"}

# Explicit column list for SELECT queries against submission_records.
# Must be updated whenever a migration adds or removes a column.
# Do not use SELECT * — new columns would appear silently in returned dicts
# and make schema changes harder to track.
_SUBMISSION_COLUMNS = """
    submission_id,
    practice_id,
    condition_id,
    condition_label,
    clinical_output_json,
    audit_output_json,
    delivery_status,
    delivery_email,
    delivered_at,
    delivery_error,
    submitted_at,
    delivery_attempts,
    last_attempt_at,
    next_retry_after,
    attachment_count
"""


class SubmissionNotFound(Exception):
    """Raised when a submission_id does not exist."""
    pass


class InvalidDeliveryStatus(Exception):
    """Raised when an unrecognised delivery status is used."""
    pass


@dataclass(frozen=True)
class PendingDelivery:
    """
    Lightweight read-only projection of a submission for delivery.

    Contains only the fields the orchestration layer needs to decide
    whether and how to deliver. Does not include clinical_output_json
    or audit_output_json.
    """
    delivery_status: str
    delivery_email: str
    condition_label: str
    submitted_at: datetime
    delivery_attempts: int
    next_retry_after: Optional[datetime]


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
        condition_label: str,
        clinical_output: ClinicalOutput,
        audit_output: AuditOutput,
        delivery_email: str,
        submitted_at: datetime,
        attachment_count: int,
    ) -> None:
        """
        Create a new submission record with delivery_status = 'pending'.

        condition_label is the human-readable condition name at submission time.
        It is stored denormalised for lightweight access during delivery retry
        without loading clinical_output_json. If the condition label is later
        changed in the ruleset, historical records retain the label that was
        active when the patient submitted.

        submitted_at must be supplied by the caller (form_router.py captures it
        immediately before calling this function). The database column has no
        DEFAULT — this is enforced by migration 0005.

        attachment_count records how many photos were submitted. It is an audit
        field only and is not used by the delivery or retry layers. No default
        is provided here — the caller must always supply the value explicitly.
        This ensures a missing argument raises TypeError immediately rather than
        silently writing 0.

        clinical_output and audit_output are stored as JSONB. psycopg2 does not
        automatically serialise dataclasses, so we convert to dict with asdict()
        first and wrap in psycopg2.extras.Json so psycopg2 serialises correctly
        for JSONB columns.

        Named parameters (%(name)s) are used throughout the INSERT rather than
        positional %s placeholders. This makes the column-to-value mapping
        explicit and prevents silent data corruption if columns are reordered.

        Raises psycopg2.errors.UniqueViolation if submission_id already exists.
        """
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
                        condition_label,
                        clinical_output_json,
                        audit_output_json,
                        delivery_status,
                        delivery_email,
                        submitted_at,
                        attachment_count
                    ) VALUES (
                        %(submission_id)s,
                        %(practice_id)s,
                        %(condition_id)s,
                        %(condition_label)s,
                        %(clinical_output_json)s,
                        %(audit_output_json)s,
                        'pending',
                        %(delivery_email)s,
                        %(submitted_at)s,
                        %(attachment_count)s
                    )
                    """,
                    {
                        "submission_id": submission_id,
                        "practice_id": practice_id,
                        "condition_id": condition_id,
                        "condition_label": condition_label,
                        "clinical_output_json": psycopg2.extras.Json(clinical_dict),
                        "audit_output_json": psycopg2.extras.Json(audit_dict),
                        "delivery_email": delivery_email,
                        "submitted_at": submitted_at,
                        "attachment_count": attachment_count,
                    },
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

        NOTE: This method is retained for backward compatibility. The
        orchestration layer uses record_attempt_outcome instead, which
        atomically increments delivery_attempts in the same UPDATE.
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
                    f"""
                    SELECT {_SUBMISSION_COLUMNS}
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
                    f"""
                    SELECT {_SUBMISSION_COLUMNS}
                    FROM submission_records
                    WHERE delivery_status = %s
                    ORDER BY submitted_at ASC
                    """,
                    (status,),
                )
                rows = cur.fetchall()

        return [dict(row) for row in rows]

    def get_pending_delivery(self, submission_id: str) -> PendingDelivery:
        """
        Get lightweight delivery projection for a submission.

        Returns a PendingDelivery dataclass with only the fields needed
        by the orchestration layer. Does not return clinical_output_json
        or audit_output_json.

        Raises SubmissionNotFound if submission_id does not exist.
        """
        with get_conn(self.database_url) as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT delivery_status,
                           delivery_email,
                           condition_label,
                           submitted_at,
                           delivery_attempts,
                           next_retry_after
                    FROM submission_records
                    WHERE submission_id = %s
                    """,
                    (submission_id,),
                )
                row = cur.fetchone()

        if row is None:
            raise SubmissionNotFound(submission_id)

        return PendingDelivery(
            delivery_status=row["delivery_status"],
            delivery_email=row["delivery_email"],
            condition_label=row["condition_label"],
            submitted_at=row["submitted_at"],
            delivery_attempts=row["delivery_attempts"],
            next_retry_after=row["next_retry_after"],
        )

    def list_retryable(self, limit: int = 50) -> list[str]:
        """
        Return submission IDs that are due for a delivery retry.

        A submission is eligible when all three conditions hold:
        - delivery_status = 'failed'  (sent and pending submissions are excluded)
        - next_retry_after IS NOT NULL  (new submissions mid-first-attempt are excluded)
        - next_retry_after <= NOW()  (the backoff window has elapsed)

        Results are ordered by submitted_at ASC so older submissions are
        retried first. The limit parameter caps the number of rows returned
        per call; the background worker calls list_retryable in a loop until
        it returns an empty list.

        Returns submission IDs only. The worker passes each ID directly to
        attempt_delivery, which calls get_pending_delivery internally as its
        first step. This keeps PendingDelivery out of the worker layer and
        avoids bundling a stale projection into the retry call.

        Design note — delivery_status = 'failed' is the tighter filter:
        NOT IN ('sent') would also match pending submissions. A pending
        submission with next_retry_after set should not exist under normal
        operation. If it does, it indicates a bug or manual data corruption.
        The = 'failed' filter ensures the worker only processes submissions
        that have been through at least one attempted delivery. Anomalous
        states are left for operator investigation rather than silently retried.

        Returns an empty list if no submissions are eligible.
        """
        with get_conn(self.database_url) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT submission_id
                    FROM submission_records
                    WHERE delivery_status = 'failed'
                      AND next_retry_after IS NOT NULL
                      AND next_retry_after <= NOW()
                    ORDER BY submitted_at ASC
                    LIMIT %s
                    """,
                    (limit,),
                )
                rows = cur.fetchall()

        return [row[0] for row in rows]

    def list_orphans(self, older_than_minutes: int) -> list[str]:
        """
        Return submission IDs that appear to be stuck in pending state.

        An orphan is a submission where:
        - delivery_status = 'pending'
        - delivery_attempts = 0
        - submitted_at < NOW() - older_than_minutes

        This pattern indicates the router crashed after inserting the row
        but before the first delivery attempt completed. Under normal
        operation no submission should remain pending with zero attempts
        beyond a short window.

        The background worker calls this once per loop iteration and emits
        a CRITICAL log if any are found. No mutation is performed — orphan
        recovery requires operator intervention.

        Known limitation: under high load, genuinely new submissions could
        satisfy these conditions if the router queue is backed up beyond
        older_than_minutes. At current single-surgery scale this is not a
        realistic concern. Document as a known limitation if scale changes.

        Returns submission IDs only. Returns an empty list if none found.
        """
        with get_conn(self.database_url) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT submission_id
                    FROM submission_records
                    WHERE delivery_status = 'pending'
                      AND delivery_attempts = 0
                      AND submitted_at < NOW() - INTERVAL '1 minute' * %s
                    ORDER BY submitted_at ASC
                    """,
                    (older_than_minutes,),
                )
                rows = cur.fetchall()

        return [row[0] for row in rows]

    def record_attempt_outcome(
        self,
        submission_id: str,
        delivery_status: str,
        delivered_at: Optional[datetime] = None,
        delivery_error: Optional[str] = None,
        next_retry_after: Optional[datetime] = None,
    ) -> int:
        """
        Atomically record the outcome of a delivery attempt.

        Performs a single UPDATE that:
        - Increments delivery_attempts by 1
        - Sets last_attempt_at to NOW()
        - Sets delivery_status
        - Sets delivered_at (on success)
        - Sets delivery_error (on failure)
        - Sets next_retry_after (on failure, if retries remain)

        Returns the new delivery_attempts count from the database via
        RETURNING. The caller should use this returned value rather than
        computing it independently — this avoids a TOCTOU race between
        the read in get_pending_delivery and the atomic increment here.

        Raises InvalidDeliveryStatus if delivery_status is not valid.
        Raises SubmissionNotFound if submission_id does not exist.
        """
        self._validate_status(delivery_status)

        with get_conn(self.database_url) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE submission_records
                    SET delivery_attempts = delivery_attempts + 1,
                        last_attempt_at   = NOW(),
                        delivery_status   = %s,
                        delivered_at      = %s,
                        delivery_error    = %s,
                        next_retry_after  = %s
                    WHERE submission_id = %s
                    RETURNING delivery_attempts
                    """,
                    (
                        delivery_status,
                        delivered_at,
                        delivery_error,
                        next_retry_after,
                        submission_id,
                    ),
                )

                result = cur.fetchone()
                if result is None:
                    raise SubmissionNotFound(submission_id)

                return result[0]
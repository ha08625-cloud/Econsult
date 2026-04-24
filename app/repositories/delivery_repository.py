"""
Delivery repository.

Database access for the delivery_jobs table.

Responsibilities:
- Creating delivery jobs once the PDF attachment has been saved.
- Claiming the next eligible pending job (SKIP LOCKED, single job per call).
- Marking jobs as sent or failed (legacy SMTP path).
- Marking jobs as provider_accepted (Mailgun path — worker sets this after
  receiving the provider message ID from send_clinical_output).
- Marking jobs as delivered or failed via webhook signals.
- Appending raw webhook event payloads to the provider_events JSONB column.
- Retrieving individual jobs by ID.

Architecture rules:
- This module must never import clinical engine modules.
- This module must never send emails or generate PDFs.
- Retry policy constants are imported from delivery_constants; this
  module does not define policy.
- All claim operations use SELECT ... FOR UPDATE SKIP LOCKED and
  immediately update next_retry_after within the same transaction.
- JSONB writes must wrap dicts in psycopg2.extras.Json() per the
  infrastructure convention (psycopg2 does not auto-adapt Python dicts).

Ordering invariant (enforced by the PDF worker, documented here):
A delivery_jobs row can only exist after save_attachment has completed
successfully. Therefore get_attachment will always find the attachment
when a delivery job is claimed. Do not break this invariant in the PDF
worker's operation ordering.

Status lifecycle:
  pending -> provider_accepted  (Mailgun path: worker marks after successful send)
  pending -> sent               (SMTP/legacy path: worker marks after successful send)
  provider_accepted -> delivered (webhook router marks on 'delivered' event)
  provider_accepted -> failed    (webhook router marks on 'failed'/'dropped' event)
  pending -> failed              (worker exhausts all retry attempts)

Jobs in provider_accepted status are intentionally excluded from
claim_next_pending. They must not be re-processed by the worker. Transition
out of provider_accepted is exclusively the webhook router's responsibility.
"""

from datetime import datetime
from typing import Optional

import psycopg2.extras
from psycopg2.extras import Json, RealDictCursor

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

        Jobs in provider_accepted, delivered, sent, or failed status are
        intentionally excluded. A provider_accepted job must not be
        re-processed by the worker; its status transitions exclusively via
        the webhook router.

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
    # Outcome recording — worker
    # ------------------------------------------------------------------

    def mark_as_accepted(self, job_id: str, provider_message_id: str) -> None:
        """
        Mark a delivery_job as accepted by the provider (Mailgun path).

        Sets status = 'provider_accepted' and records the provider_message_id
        returned by the Mailgun API. Called by the delivery worker immediately
        after a successful send_clinical_output call.

        The provider_message_id is the lookup key used by the webhook router
        to match incoming delivery signals to this job. It must be committed
        before any webhook can arrive (in practice there is a small window
        where a webhook could arrive first; the router handles this by
        returning 406 to trigger a provider retry).

        Raises DeliveryJobNotFound if the job_id does not exist.
        """
        with get_conn(self.database_url) as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    UPDATE delivery_jobs
                    SET status              = 'provider_accepted',
                        provider_message_id = %(provider_message_id)s,
                        updated_at          = NOW()
                    WHERE id = %(job_id)s
                    RETURNING id
                    """,
                    {
                        "job_id": job_id,
                        "provider_message_id": provider_message_id,
                    },
                )
                if cur.fetchone() is None:
                    raise DeliveryJobNotFound(job_id)

    def mark_sent(self, job_id: str) -> None:
        """
        Mark a delivery_job as successfully sent (legacy SMTP path).

        Sets status = 'sent' and updated_at. Used when the delivery service
        returns None (SMTP or ConsoleDeliveryService), indicating no webhook
        tracking is available. Does not clear last_error (historical error
        context is useful if a job failed before eventually succeeding on a
        later attempt).
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
    ) -> bool:
        """
        Record a failed delivery attempt.

        Increments attempt_count by 1. If the new attempt_count reaches
        MAX_ATTEMPTS, status is set to 'failed' permanently. Otherwise
        status remains 'pending' and next_retry_after is set to the
        supplied value.

        Returns True if the job has been permanently exhausted (status is
        now 'failed'), False if it remains pending for a future retry.

        Raises DeliveryJobNotFound if the job_id does not exist.
        """
        with get_conn(self.database_url) as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
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
                    RETURNING id, status
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
                return result["status"] == "failed"

    # ------------------------------------------------------------------
    # Outcome recording — webhook router
    # ------------------------------------------------------------------

    def mark_delivered(self, provider_message_id: str) -> bool:
        """
        Mark a job as delivered based on a Mailgun 'delivered' webhook event.

        Sets status = 'delivered' and updated_at. Does not append the event
        payload here — call append_provider_event separately to keep the
        JSONB write and the status update decoupled.

        Returns True if a row was found and updated, False if no row exists
        for the given provider_message_id (signals the webhook router to
        return 406 so Mailgun retries later).
        """
        with get_conn(self.database_url) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE delivery_jobs
                    SET status     = 'delivered',
                        updated_at = NOW()
                    WHERE provider_message_id = %s
                    RETURNING id
                    """,
                    (provider_message_id,),
                )
                return cur.fetchone() is not None

    def mark_provider_failed(self, provider_message_id: str) -> bool:
        """
        Mark a job as failed based on a Mailgun 'failed' or 'dropped' webhook.

        Sets status = 'failed' and updated_at. Does not append the event
        payload here — call append_provider_event separately.

        Returns True if a row was found and updated, False if no row exists
        for the given provider_message_id (signals the webhook router to
        return 406 so Mailgun retries later).
        """
        with get_conn(self.database_url) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE delivery_jobs
                    SET status     = 'failed',
                        updated_at = NOW()
                    WHERE provider_message_id = %s
                    RETURNING id
                    """,
                    (provider_message_id,),
                )
                return cur.fetchone() is not None

    def append_provider_event(
        self, provider_message_id: str, event_payload: dict
    ) -> None:
        """
        Append a raw webhook event payload to the provider_events JSONB column.

        Uses jsonb_build_array and the concatenation operator (||) to append
        to the existing array, initialising to an empty array if NULL.
        This keeps the column as an ordered array of event objects.

        Called for all webhook event types, including ones that do not change
        status (e.g. 'opened', 'clicked'). The lossless audit trail is
        maintained regardless of whether the event triggers a status change.

        No-ops silently if the provider_message_id is not found — a missing
        row at this point means the status update (mark_delivered / mark_provider_failed)
        already returned False and the router will return 406. Appending to a
        non-existent row would be a no-op anyway.
        """
        with get_conn(self.database_url) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE delivery_jobs
                    SET provider_events = COALESCE(provider_events, '[]'::jsonb)
                                         || jsonb_build_array(%(payload)s::jsonb),
                        updated_at      = NOW()
                    WHERE provider_message_id = %(provider_message_id)s
                    """,
                    {
                        "provider_message_id": provider_message_id,
                        "payload": Json(event_payload),
                    },
                )

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
"""
MESH repository.

Database access for the mesh_jobs table — the queue between the PDF worker
(producer, via MeshEnqueuer) and the MESH dispatcher (consumer, Phase 3) and
tracking poller (Phase 4).

Responsibilities:
- Creating mesh jobs once the PDF attachment has been saved (idempotent).
- Claiming the next dispatchable job (SKIP LOCKED, single job per call) — Phase 3.
- Recording a successful send and the returned MESH messageID — Phase 3.
- Recording a transient failure with caller-supplied backoff — Phase 3.
- Recording the fallback-to-email transition — Phase 3.
- Recording tracking transitions (provider_accepted, delivered) — Phase 4.

Architecture rules:
- This module must never import clinical engine modules, routers, or services.
- This module must never send MESH messages, build payloads, or open HTTP
  connections — it is persistence only. The dispatcher owns the MeshClient.
- This module does not define retry policy. The number of attempts before
  giving up (MAX_MESH_ATTEMPTS) is the dispatcher's concern; mark_failed only
  records the attempt and returns the new attempt_count so the dispatcher can
  decide whether to retry or fall back. This mirrors how DeliveryRepository
  keeps backoff values out of the repository.

Ordering invariant (enforced by the PDF worker, documented here):
A mesh_jobs row can only exist after save_attachment has completed
successfully. create_job is therefore idempotent (ON CONFLICT DO NOTHING on
submission_id) so the PDF worker's at-least-once enqueue is safe across
retries — identical in shape to DeliveryRepository.create_job.

Status lifecycle (the six CHECK-constrained states):
  pending                  -> sent               (dispatcher: MESH returned 202)
  pending                  -> fallback_triggered (dispatcher: terminal failure
                                                  or transient attempts exhausted)
  sent                     -> provider_accepted  (tracking: Accepted + downloadTimestamp)
  sent | provider_accepted -> delivered          (tracking: Acknowledged + SUCCESS)

The 'failed' state is reserved for a tracking-time terminal signal (Error /
statusSuccess=FAILED) and is set by a Phase 4 tracking method that is added in
that phase. In Phase 2b only create_job is wired (by MeshEnqueuer); the claim
and mark_* methods are built and tested here but not yet called by any worker.

A transient send failure does NOT move the row to 'failed': mark_failed leaves
status as 'pending' and sets next_retry_after, so the dispatcher reclaims the
row when the backoff expires. Giving up after MAX_MESH_ATTEMPTS is an explicit
dispatcher decision that calls mark_fallback_triggered.
"""

from datetime import datetime

from psycopg2.extras import RealDictCursor

from app.core.db import get_conn


class MeshJobNotFound(Exception):
    """Raised when a mesh_job_id does not exist in mesh_jobs."""

    pass


class MeshRepository:
    def __init__(self, database_url: str):
        self.database_url = database_url

    # ------------------------------------------------------------------
    # Job creation (Phase 2b — wired via MeshEnqueuer)
    # ------------------------------------------------------------------

    def create_job(self, *, submission_id: str, recipient_mailbox_id: str) -> str:
        """
        Insert a new mesh_jobs row with status = 'pending'.

        The submission_id column has a UNIQUE constraint, so calling this twice
        with the same submission_id is safe: the second call uses ON CONFLICT
        DO NOTHING and the existing row is left untouched. This makes the call
        idempotent and safe across PDF worker retries, satisfying the worker's
        ordering invariant (see arch_submission.md).

        recipient_mailbox_id is copied onto the row so that a later change to
        the MESH_RECIPIENT_MAILBOX_ID configuration cannot misroute a referral
        that was already queued.

        Returns the row's id as a string (the existing row's id if the conflict
        path was taken).
        """
        with get_conn(self.database_url) as conn, conn.cursor() as cur:
            cur.execute(
                """
                    INSERT INTO mesh_jobs (submission_id, recipient_mailbox_id)
                    VALUES (%(submission_id)s, %(recipient_mailbox_id)s)
                    ON CONFLICT (submission_id) DO NOTHING
                    RETURNING id
                    """,
                {
                    "submission_id": submission_id,
                    "recipient_mailbox_id": recipient_mailbox_id,
                },
            )
            row = cur.fetchone()

            if row is not None:
                # Fresh insert: return the new id.
                return str(row[0])

            # Conflict path: fetch the existing row's id.
            cur.execute(
                "SELECT id FROM mesh_jobs WHERE submission_id = %s",
                (submission_id,),
            )
            existing = cur.fetchone()
            return str(existing[0])

    # ------------------------------------------------------------------
    # Job claiming (Phase 3 — dispatcher)
    # ------------------------------------------------------------------

    def claim_next_pending(self) -> dict | None:
        """
        Claim the next dispatchable mesh_jobs row.

        A job is eligible when:
        - status = 'pending'
        - next_retry_after IS NULL OR next_retry_after <= NOW()

        Rows in any other status are excluded. The claim is atomic:
        1. SELECT ... FOR UPDATE SKIP LOCKED finds and locks the row.
        2. An immediate UPDATE pushes next_retry_after 10 minutes into the
           future, moving the row outside the eligible window for any
           concurrent dispatcher. This is a crash safety net: if the
           dispatcher dies after claiming but before recording an outcome,
           the row becomes eligible again once the 10 minutes elapse.
        Both steps happen inside a single transaction.

        Returns a dict of the claimed row (all columns), or None if the queue
        is empty.
        """
        with get_conn(self.database_url) as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT *
                    FROM mesh_jobs
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
                    UPDATE mesh_jobs
                    SET next_retry_after = NOW() + INTERVAL '10 minutes',
                        updated_at       = NOW()
                    WHERE id = %s
                    """,
                    (row["id"],),
                )

        return dict(row)

    # ------------------------------------------------------------------
    # Outcome recording — dispatcher (Phase 3)
    # ------------------------------------------------------------------

    def mark_sent(self, *, mesh_job_id: str, message_id: str) -> None:
        """
        Mark a mesh_job as sent after MESH returns 202 Accepted.

        Records the MESH messageID verbatim and stamps sent_at. message_id is
        stored exactly as returned (32-char uppercase hex); it must not be
        normalised.

        Raises MeshJobNotFound if the mesh_job_id does not exist.
        """
        with get_conn(self.database_url) as conn, conn.cursor() as cur:
            cur.execute(
                """
                    UPDATE mesh_jobs
                    SET status     = 'sent',
                        message_id = %(message_id)s,
                        sent_at    = NOW(),
                        updated_at = NOW()
                    WHERE id = %(mesh_job_id)s
                    RETURNING id
                    """,
                {"mesh_job_id": mesh_job_id, "message_id": message_id},
            )
            if cur.fetchone() is None:
                raise MeshJobNotFound(mesh_job_id)

    def mark_failed(
        self,
        *,
        mesh_job_id: str,
        error: str,
        error_code: str | None,
        next_retry_after: datetime | None,
    ) -> int:
        """
        Record a transient send failure.

        Increments attempt_count by 1, records the error text and any MESH
        error code, and sets next_retry_after to the caller-supplied backoff.
        Status is left as 'pending' so the dispatcher reclaims the row when the
        backoff expires.

        Returns the new attempt_count so the dispatcher can compare it against
        MAX_MESH_ATTEMPTS and decide whether to keep retrying or to call
        mark_fallback_triggered. This repository intentionally does not own
        that threshold.

        Raises MeshJobNotFound if the mesh_job_id does not exist.
        """
        with get_conn(self.database_url) as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    UPDATE mesh_jobs
                    SET attempt_count    = attempt_count + 1,
                        last_error       = %(error)s,
                        last_error_code  = %(error_code)s,
                        next_retry_after = %(next_retry_after)s,
                        updated_at       = NOW()
                    WHERE id = %(mesh_job_id)s
                    RETURNING attempt_count
                    """,
                    {
                        "mesh_job_id": mesh_job_id,
                        "error": error,
                        "error_code": error_code,
                        "next_retry_after": next_retry_after,
                    },
                )
                result = cur.fetchone()
                if result is None:
                    raise MeshJobNotFound(mesh_job_id)
                return result["attempt_count"]

    def mark_fallback_triggered(self, *, mesh_job_id: str) -> None:
        """
        Mark a mesh_job as having fallen through to the email (Mailgun) path.

        Set by the dispatcher when MESH fails terminally or transient attempts
        are exhausted, immediately before it enqueues the email fallback. The
        dispatcher's ordering invariant (mark_fallback_triggered then
        delivery_repo.create_job(is_fallback=True)) is documented in
        arch_submission.md; this method only performs the status transition.

        Raises MeshJobNotFound if the mesh_job_id does not exist.
        """
        with get_conn(self.database_url) as conn, conn.cursor() as cur:
            cur.execute(
                """
                    UPDATE mesh_jobs
                    SET status     = 'fallback_triggered',
                        updated_at = NOW()
                    WHERE id = %s
                    RETURNING id
                    """,
                (mesh_job_id,),
            )
            if cur.fetchone() is None:
                raise MeshJobNotFound(mesh_job_id)

    # ------------------------------------------------------------------
    # Outcome recording — tracking poller (Phase 4)
    # ------------------------------------------------------------------

    def mark_provider_accepted(self, *, mesh_job_id: str) -> None:
        """
        Mark a mesh_job as downloaded by the recipient's MESH client.

        Set by the tracking poller when the tracking record shows the message
        has been Accepted with a populated downloadTimestamp. This is an
        intermediate state, not proof of clinical receipt — delivery is only
        confirmed on Acknowledged + SUCCESS (mark_delivered).

        Raises MeshJobNotFound if the mesh_job_id does not exist.
        """
        with get_conn(self.database_url) as conn, conn.cursor() as cur:
            cur.execute(
                """
                    UPDATE mesh_jobs
                    SET status               = 'provider_accepted',
                        provider_accepted_at = NOW(),
                        updated_at           = NOW()
                    WHERE id = %s
                    RETURNING id
                    """,
                (mesh_job_id,),
            )
            if cur.fetchone() is None:
                raise MeshJobNotFound(mesh_job_id)

    def mark_delivered(self, *, mesh_job_id: str) -> None:
        """
        Mark a mesh_job as delivered (recipient acknowledgement received).

        Set by the tracking poller when the tracking record shows
        status == 'Acknowledged' AND statusSuccess == 'SUCCESS'. This is the
        authoritative delivery signal; the deletion job (Phase 4) treats it as
        proof of receipt and only then becomes eligible to delete the referral.

        Raises MeshJobNotFound if the mesh_job_id does not exist.
        """
        with get_conn(self.database_url) as conn, conn.cursor() as cur:
            cur.execute(
                """
                    UPDATE mesh_jobs
                    SET status       = 'delivered',
                        delivered_at = NOW(),
                        updated_at   = NOW()
                    WHERE id = %s
                    RETURNING id
                    """,
                (mesh_job_id,),
            )
            if cur.fetchone() is None:
                raise MeshJobNotFound(mesh_job_id)

    # ------------------------------------------------------------------
    # Lookup
    # ------------------------------------------------------------------

    def list_orphaned_fallbacks(self) -> list[dict]:
        """
        Find mesh_jobs rows in 'fallback_triggered' with no matching
        delivery_jobs row.

        These are the crash artefacts of the dispatcher's fallback ordering
        invariant: mark_fallback_triggered committed, but the process died
        before delivery_repo.create_job ran. Without recovery, the
        submission is silently undelivered — fallback_triggered is terminal
        in mesh_jobs and nothing else consumes it.

        Consumed by the dispatcher's recovery sweep (every loop iteration),
        which re-runs the idempotent delivery_repo.create_job for each
        orphan. Returns a list of dicts with 'id' and 'submission_id',
        oldest first; empty list when there are no orphans (the normal
        case — this query is a cheap LEFT JOIN on two indexed columns).
        """
        with get_conn(self.database_url) as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT m.id, m.submission_id
                    FROM mesh_jobs m
                    LEFT JOIN delivery_jobs d
                           ON d.submission_id = m.submission_id
                    WHERE m.status = 'fallback_triggered'
                      AND d.id IS NULL
                    ORDER BY m.created_at ASC
                    """
                )
                rows = cur.fetchall()
        return [dict(row) for row in rows]

    def get(self, mesh_job_id: str) -> dict:
        """
        Return the full mesh_jobs row for mesh_job_id.

        Raises MeshJobNotFound if absent.
        """
        with get_conn(self.database_url) as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    "SELECT * FROM mesh_jobs WHERE id = %s",
                    (mesh_job_id,),
                )
                row = cur.fetchone()

        if row is None:
            raise MeshJobNotFound(mesh_job_id)

        return dict(row)
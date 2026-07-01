"""
MESH dispatcher worker loop.

Claims pending mesh_jobs rows, builds the outbound payload via the
MeshPayloadBuilder seam, POSTs to MESH via MeshClient, and records the
outcome. On terminal MESH failure (or transient exhaustion) it falls back
to the email path by enqueuing a delivery_jobs row with is_fallback=True,
which the existing delivery worker sends via Mailgun unchanged — fallback
emails are identical to email-path emails by design.

Architecture rules:
- This module may import from: mesh_repository, delivery_repository,
  pdf_repository, submission_repository, attachment_repository, the MESH
  client library (app.services.delivery.mesh), mesh_payload, and
  mesh_constants. It must never import the engine directly, import from
  routers, or call SubmissionRepository.get_submission (which returns
  clinical JSON) — fallback metadata comes from the narrow
  get_delivery_metadata method only.
- Retry policy lives here (via mesh_constants), never in the repository.
  MeshRepository.mark_failed records an attempt and returns the new count;
  this module compares against MAX_MESH_ATTEMPTS and decides retry vs
  fallback.

Ordering invariant (fallback):
mark_fallback_triggered commits BEFORE delivery_repo.create_job runs. A
crash between the two therefore fails safe: the submission is undelivered
but detectable (a 'fallback_triggered' mesh_job with no delivery_jobs row),
never double-sent on both channels. The orphaned-fallback recovery sweep at
the top of every loop iteration repairs exactly this state by re-running
the idempotent create_job (ON CONFLICT DO NOTHING on submission_id).

Crash recovery at each step in _process_job:
- Before send_message: retry resends from the stored attachment — safe.
- After Spine accepts (202) but before mark_sent commits: the claim's
  retry-push expires and the job is resent. The GP practice receives two
  copies. This is the documented duplicate-send Accepted Limitation in
  mesh_integration_plan.md; Mex-LocalID is set per job for manual
  correlation via the tracking endpoint.
- After mark_sent: the row is 'sent' and not re-claimed — safe.
- Between mark_fallback_triggered and create_job: repaired by the sweep
  (see above).

Worker behaviour:
- Single-threaded, single process. claim_next_pending uses
  FOR UPDATE SKIP LOCKED, so multiple dispatcher processes are safe if
  ever deployed.
- psycopg2.OperationalError propagates uncaught (from the claim, the sweep,
  or outcome recording) so the process exits and Railway restarts the
  container — consistent with the other workers.
- Unexpected (non-MESH) exceptions in a job are recorded as a failed
  attempt with backoff, so a persistent bug still reaches the email
  fallback once attempts exhaust, rather than wedging the queue.

Sentry alert routing for failed / fallback_triggered states is Phase 5;
this module logs at ERROR/CRITICAL in the meantime.
"""

import logging
import time
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

import psycopg2

from app.repositories.attachment_repository import AttachmentRepository
from app.repositories.delivery_repository import DeliveryRepository
from app.repositories.mesh_repository import MeshRepository
from app.repositories.pdf_repository import PDFRepository
from app.repositories.submission_repository import SubmissionRepository
from app.services.delivery.mesh import (
    MeshClient,
    MeshTerminalError,
    MeshTransientError,
)
from app.services.delivery.mesh_constants import (
    HANDSHAKE_RETRY_DELAYS_SECONDS,
    MAX_MESH_ATTEMPTS,
    MESH_RETRY_BACKOFF_MINUTES,
)
from app.services.delivery.mesh_payload import MeshPayloadBuilder

logger = logging.getLogger(__name__)


def run_worker(
    mesh_repo: MeshRepository,
    attachment_repo: AttachmentRepository,
    pdf_repo: PDFRepository,
    submission_repo: SubmissionRepository,
    delivery_repo: DeliveryRepository,
    mesh_client: MeshClient,
    payload_builder: MeshPayloadBuilder,
    workflow_id: str,
    poll_interval: int,
) -> None:
    """
    Run the MESH dispatcher loop indefinitely.

    Each iteration: recover orphaned fallbacks, then claim and process at
    most one mesh_jobs row. Sleeps only when the queue is empty.

    Arguments:
        mesh_repo       -- MeshRepository instance
        attachment_repo -- AttachmentRepository instance
        pdf_repo        -- PDFRepository instance (delivery_email lookup)
        submission_repo -- SubmissionRepository instance (narrow metadata)
        delivery_repo   -- DeliveryRepository instance (fallback enqueue)
        mesh_client     -- MeshClient instance (handshake already performed
                           by the entry point)
        payload_builder -- MeshPayloadBuilder selected at startup
        workflow_id     -- Mex-WorkflowID for outgoing messages (env-driven;
                           see mesh_payload.py for the coupling note)
        poll_interval   -- seconds to sleep when the queue is empty
    """
    logger.info(
        "MESH dispatcher started: poll_interval=%ds max_attempts=%d workflow_id=%s",
        poll_interval,
        MAX_MESH_ATTEMPTS,
        workflow_id,
    )

    while True:
        _recover_orphaned_fallbacks(
            mesh_repo=mesh_repo,
            pdf_repo=pdf_repo,
            submission_repo=submission_repo,
            delivery_repo=delivery_repo,
        )

        job = mesh_repo.claim_next_pending()

        if job is None:
            logger.debug("MESH dispatcher queue empty — sleeping %ds", poll_interval)
            time.sleep(poll_interval)
            continue

        try:
            _process_job(
                job=job,
                mesh_repo=mesh_repo,
                attachment_repo=attachment_repo,
                pdf_repo=pdf_repo,
                submission_repo=submission_repo,
                delivery_repo=delivery_repo,
                mesh_client=mesh_client,
                payload_builder=payload_builder,
                workflow_id=workflow_id,
            )
        except psycopg2.OperationalError:
            raise
        except Exception as exc:
            # Unexpected (non-MESH) failure: record as a failed attempt so
            # the job retries with backoff and, if the bug persists, still
            # reaches the email fallback on exhaustion.
            logger.critical(
                "MESH dispatcher: unexpected error submission_id=%s mesh_job_id=%s "
                "attempt=%d error=%s",
                job["submission_id"],
                job["id"],
                job["attempt_count"] + 1,
                exc,
                exc_info=True,
            )
            _record_failure_and_maybe_fallback(
                job=job,
                exc=exc,
                mesh_repo=mesh_repo,
                pdf_repo=pdf_repo,
                submission_repo=submission_repo,
                delivery_repo=delivery_repo,
            )


def _process_job(
    job: dict,
    mesh_repo: MeshRepository,
    attachment_repo: AttachmentRepository,
    pdf_repo: PDFRepository,
    submission_repo: SubmissionRepository,
    delivery_repo: DeliveryRepository,
    mesh_client: MeshClient,
    payload_builder: MeshPayloadBuilder,
    workflow_id: str,
) -> None:
    """
    Process a single claimed mesh_jobs row.

    MESH-classified failures are handled here (transient -> backoff or
    exhaustion-fallback; terminal -> immediate fallback). Anything else
    raises to run_worker, which records a failed attempt.
    """
    submission_id = str(job["submission_id"])
    mesh_job_id = str(job["id"])

    pdf_bytes = attachment_repo.get_attachment(submission_id)
    payload = payload_builder.build(pdf_bytes=pdf_bytes)

    try:
        message_id = mesh_client.send_message(
            recipient_mailbox_id=str(job["recipient_mailbox_id"]),
            payload_bytes=payload.payload_bytes,
            workflow_id=workflow_id,
            mex_localid=str(job["mex_localid"]),
            content_type=payload.content_type,
        )
    except MeshTerminalError as exc:
        logger.error(
            "MESH dispatcher: terminal failure submission_id=%s mesh_job_id=%s "
            "error=%s — falling back to email",
            submission_id,
            mesh_job_id,
            exc,
        )
        _trigger_fallback(
            job=job,
            mesh_repo=mesh_repo,
            pdf_repo=pdf_repo,
            submission_repo=submission_repo,
            delivery_repo=delivery_repo,
        )
        return
    except MeshTransientError as exc:
        logger.warning(
            "MESH dispatcher: transient failure submission_id=%s mesh_job_id=%s "
            "attempt=%d error=%s",
            submission_id,
            mesh_job_id,
            job["attempt_count"] + 1,
            exc,
        )
        _record_failure_and_maybe_fallback(
            job=job,
            exc=exc,
            mesh_repo=mesh_repo,
            pdf_repo=pdf_repo,
            submission_repo=submission_repo,
            delivery_repo=delivery_repo,
        )
        return

    mesh_repo.mark_sent(mesh_job_id=mesh_job_id, message_id=message_id)
    logger.info(
        "MESH dispatcher: sent submission_id=%s mesh_job_id=%s message_id=%s",
        submission_id,
        mesh_job_id,
        message_id,
    )


def _record_failure_and_maybe_fallback(
    job: dict,
    exc: Exception,
    mesh_repo: MeshRepository,
    pdf_repo: PDFRepository,
    submission_repo: SubmissionRepository,
    delivery_repo: DeliveryRepository,
) -> None:
    """
    Record a failed attempt with backoff. If attempts are now exhausted
    (MAX_MESH_ATTEMPTS), trigger the email fallback.

    error_code is recorded as None: the MESH exception classes are
    attribute-free by design (their message carries the HTTP status and any
    MESH errorCode). Populating mesh_jobs.last_error_code as a structured
    field is the small additive client change anticipated in
    mesh_integration_plan.md Phase 2a, deferred until something consumes it
    (Phase 5 alerting is the likely customer).
    """
    new_attempt_count = mesh_repo.mark_failed(
        mesh_job_id=str(job["id"]),
        error=str(exc),
        error_code=None,
        next_retry_after=_compute_backoff(job["attempt_count"]),
    )

    if new_attempt_count >= MAX_MESH_ATTEMPTS:
        logger.error(
            "MESH dispatcher: attempts exhausted submission_id=%s mesh_job_id=%s "
            "attempts=%d — falling back to email",
            job["submission_id"],
            job["id"],
            new_attempt_count,
        )
        _trigger_fallback(
            job=job,
            mesh_repo=mesh_repo,
            pdf_repo=pdf_repo,
            submission_repo=submission_repo,
            delivery_repo=delivery_repo,
        )


def _trigger_fallback(
    job: dict,
    mesh_repo: MeshRepository,
    pdf_repo: PDFRepository,
    submission_repo: SubmissionRepository,
    delivery_repo: DeliveryRepository,
) -> None:
    """
    Transition the mesh_job to fallback_triggered, THEN enqueue the email
    delivery. The order is the documented invariant — see the module
    docstring. Do not reorder.
    """
    mesh_repo.mark_fallback_triggered(mesh_job_id=str(job["id"]))
    _enqueue_fallback_delivery(
        submission_id=str(job["submission_id"]),
        pdf_repo=pdf_repo,
        submission_repo=submission_repo,
        delivery_repo=delivery_repo,
    )


def _enqueue_fallback_delivery(
    submission_id: str,
    pdf_repo: PDFRepository,
    submission_repo: SubmissionRepository,
    delivery_repo: DeliveryRepository,
) -> None:
    """
    Create the is_fallback=True delivery_jobs row for a submission.

    Shared by _trigger_fallback and the recovery sweep. Idempotent:
    create_job is ON CONFLICT DO NOTHING on submission_id, so calling this
    for an already-satisfied fallback is a no-op (first write wins).
    """
    to_email = pdf_repo.get_delivery_email(submission_id)
    meta = submission_repo.get_delivery_metadata(submission_id)
    delivery_repo.create_job(
        submission_id=submission_id,
        to_email=to_email,
        condition_label=meta["condition_label"],
        submitted_at=meta["submitted_at"],
        is_fallback=True,
    )


def _recover_orphaned_fallbacks(
    mesh_repo: MeshRepository,
    pdf_repo: PDFRepository,
    submission_repo: SubmissionRepository,
    delivery_repo: DeliveryRepository,
) -> None:
    """
    Repair crash artefacts of the fallback ordering invariant: any
    fallback_triggered mesh_job with no delivery_jobs row gets its email
    delivery enqueued now.

    Runs at the top of every loop iteration (the query is a cheap LEFT
    JOIN; the normal result is an empty list). Each recovery is logged at
    ERROR — it means a crash happened in the invariant window. Per-orphan
    exceptions are contained so one bad row cannot wedge the queue;
    psycopg2.OperationalError still propagates so a dead database exits
    the process.
    """
    for orphan in mesh_repo.list_orphaned_fallbacks():
        submission_id = str(orphan["submission_id"])
        try:
            _enqueue_fallback_delivery(
                submission_id=submission_id,
                pdf_repo=pdf_repo,
                submission_repo=submission_repo,
                delivery_repo=delivery_repo,
            )
            logger.error(
                "MESH dispatcher: recovered orphaned fallback submission_id=%s "
                "mesh_job_id=%s (crash occurred between mark_fallback_triggered "
                "and create_job)",
                submission_id,
                orphan["id"],
            )
        except psycopg2.OperationalError:
            raise
        except Exception as exc:
            logger.critical(
                "MESH dispatcher: orphan recovery failed submission_id=%s mesh_job_id=%s error=%s",
                submission_id,
                orphan["id"],
                exc,
                exc_info=True,
            )


def _compute_backoff(attempt_count: int) -> datetime:
    """
    Backoff timestamp for a job that has already failed attempt_count
    times (0-based at first failure). Indexes into
    MESH_RETRY_BACKOFF_MINUTES, clamped to the final entry — identical in
    shape to the PDF and delivery workers' backoff helpers.
    """
    index = min(attempt_count, len(MESH_RETRY_BACKOFF_MINUTES) - 1)
    minutes = MESH_RETRY_BACKOFF_MINUTES[index]
    return datetime.now(UTC) + timedelta(minutes=minutes)


def _handshake_with_retry(
    mesh_client: MeshClient,
    delays_seconds: list[int] | None = None,
    sleep_fn: Callable[[float], None] = time.sleep,
) -> None:
    """
    Perform the startup handshake with bounded retry on transient failure.

    - MeshTerminalError (e.g. 403 with populated errorCode): re-raised
      immediately — misconfiguration, fail fast.
    - MeshTransientError: retried per delays_seconds (default
      HANDSHAKE_RETRY_DELAYS_SECONDS, ~8.5 minutes of patience), then
      re-raised. The bound is deliberate: a 403 with an EMPTY errorCode
      classifies as transient, so bad credentials can present as transient
      — an unbounded retry would mask a credential error forever.

    sleep_fn is injected for testability.
    """
    if delays_seconds is None:
        delays_seconds = HANDSHAKE_RETRY_DELAYS_SECONDS

    attempt = 1
    for delay in delays_seconds:
        try:
            mesh_client.handshake()
            logger.info("MESH handshake succeeded (attempt %d)", attempt)
            return
        except MeshTransientError as exc:
            logger.warning(
                "MESH handshake transient failure (attempt %d): %s — retrying in %ds",
                attempt,
                exc,
                delay,
            )
            sleep_fn(delay)
            attempt += 1

    # Final attempt after the last delay; failure here propagates.
    mesh_client.handshake()
    logger.info("MESH handshake succeeded (attempt %d)", attempt)

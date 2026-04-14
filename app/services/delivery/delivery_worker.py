"""
Delivery worker.

Background worker loop responsible for draining the delivery_jobs queue and
sending PDFs to the practice via email.

Architecture rules:
- This module may import from: delivery_repository, attachment_repository,
  delivery_service, delivery_constants, sentry_sdk.
- This module must never: implement clinical logic, access the database
  directly, import from routers, or read submission_records.
- All delivery metadata (to_email, condition_label, submitted_at) is read
  from the delivery_jobs row. The delivery worker never reads
  submission_records.

Ordering invariant (enforced by the PDF worker, relied upon here):
A delivery_jobs row can only exist after save_attachment has completed
successfully. Therefore get_attachment will always find the attachment when
a delivery job is claimed. A missing attachment is always a bug — it means
the ordering invariant has been broken — and must propagate loudly.

Concurrency:
- Single-threaded, single process. The claim_next_pending method uses
  SELECT ... FOR UPDATE SKIP LOCKED so multiple delivery worker processes
  could safely run in parallel, but the current deployment is single-process.

Failure handling:
- EmailDeliveryError is caught per-job and recorded via mark_failed.
- mark_failed returns True when the job is permanently exhausted; an
  additional error log is emitted in that case.
- All other exceptions per-job are caught, logged at CRITICAL, and skipped
  so the worker continues processing other jobs.
- psycopg2.OperationalError from claim_next_pending propagates uncaught
  so the process exits and Railway restarts the container.

Duplicate delivery risk:
- A crash after a successful SMTP send but before mark_sent results in a
  re-send on the next retry. Duplicate delivery is safer than silently
  dropping a submission. This is a known and accepted limitation.
"""

import logging
import time
from datetime import datetime, timedelta, timezone
from typing import Optional

import sentry_sdk

from app.repositories.attachment_repository import AttachmentRepository
from app.repositories.delivery_repository import DeliveryRepository
from app.services.delivery.delivery_constants import MAX_ATTEMPTS, RETRY_BACKOFF_MINUTES
from app.services.delivery.delivery_service import DeliveryService, EmailDeliveryError

logger = logging.getLogger(__name__)


def run_worker(
    delivery_repo: DeliveryRepository,
    attachment_repo: AttachmentRepository,
    delivery_service: DeliveryService,
    poll_interval: int,
) -> None:
    """
    Run the delivery worker loop indefinitely.

    Claims one pending delivery_jobs row per iteration, fetches the PDF
    attachment, sends it via email, and marks the job sent. Sleeps only
    when the queue is empty.

    psycopg2.OperationalError from claim_next_pending propagates uncaught
    so the process exits and Railway restarts the container.

    Arguments:
        delivery_repo   -- DeliveryRepository instance
        attachment_repo -- AttachmentRepository instance
        delivery_service -- DeliveryService instance (Email or Console)
        poll_interval   -- seconds to sleep when the queue is empty
    """
    logger.info("Delivery worker started: poll_interval=%ds", poll_interval)

    while True:
        job = delivery_repo.claim_next_pending()

        if job is None:
            logger.debug("Delivery worker queue empty — sleeping %ds", poll_interval)
            time.sleep(poll_interval)
            continue

        job_id = str(job["id"])
        submission_id = str(job["submission_id"])

        with sentry_sdk.new_scope() as scope:
            # Tag every Sentry event from this iteration with the job
            # identifiers. new_scope() inherits process-level tags while
            # isolating breadcrumbs between jobs.
            scope.set_tag("job_id", job_id)
            scope.set_tag("submission_id", submission_id)

            try:
                _process_job(
                    job=job,
                    delivery_repo=delivery_repo,
                    attachment_repo=attachment_repo,
                    delivery_service=delivery_service,
                )
            except EmailDeliveryError as exc:
                next_retry = _compute_backoff(job["attempt_count"])
                is_exhausted = delivery_repo.mark_failed(job_id, str(exc), next_retry_after=next_retry)
                logger.error(
                    "Delivery worker: SMTP failure submission_id=%s job_id=%s "
                    "attempt=%d next_retry_after=%s error=%s",
                    submission_id,
                    job_id,
                    job["attempt_count"] + 1,
                    next_retry.isoformat() if next_retry else "None (exhausted)",
                    exc,
                )
                if is_exhausted:
                    sentry_sdk.capture_message(
                        f"Delivery job permanently failed after {MAX_ATTEMPTS} attempts. "
                        "Operator intervention required.",
                        level="error",
                    )
                    logger.error(
                        "Delivery worker: job permanently failed after %d attempts "
                        "submission_id=%s job_id=%s",
                        MAX_ATTEMPTS,
                        submission_id,
                        job_id,
                    )
            except Exception as exc:
                # Unexpected error (e.g. AttachmentNotFound — ordering invariant broken,
                # or a repository bug). Log at CRITICAL and skip — do not swallow silently.
                logger.critical(
                    "Delivery worker: unhandled exception submission_id=%s job_id=%s "
                    "error=%s",
                    submission_id,
                    job_id,
                    exc,
                    exc_info=True,
                )


def _process_job(
    job: dict,
    delivery_repo: DeliveryRepository,
    attachment_repo: AttachmentRepository,
    delivery_service: DeliveryService,
) -> None:
    """
    Process a single claimed delivery_jobs row.

    Fetches the PDF attachment (guaranteed to exist by the ordering
    invariant), sends the email, and marks the job sent.

    Raises EmailDeliveryError on SMTP failure so the caller can record the
    backoff. Raises any other exception (e.g. AttachmentNotFound) without
    catching so the caller logs at CRITICAL.
    """
    submission_id = str(job["submission_id"])

    pdf_bytes = attachment_repo.get_attachment(submission_id)

    delivery_service.send_clinical_output(
        to_email=job["to_email"],
        condition_label=job["condition_label"],
        pdf_bytes=pdf_bytes,
        submission_id=submission_id,
        submitted_at=job["submitted_at"],
    )

    delivery_repo.mark_sent(str(job["id"]))

    logger.info(
        "Delivery worker: sent submission_id=%s job_id=%s to=%s",
        submission_id,
        job["id"],
        job["to_email"],
    )


def _compute_backoff(attempt_count: int) -> Optional[datetime]:
    """
    Compute next_retry_after for a failed delivery attempt.

    attempt_count is the value on the job row before the current failure.
    The backoff index is therefore attempt_count, not attempt_count - 1.

    Returns None if the job has exhausted all retries, which signals to
    mark_failed that the job should be permanently failed.
    """
    post_increment = attempt_count + 1
    if post_increment >= MAX_ATTEMPTS:
        return None
    backoff_index = attempt_count
    if backoff_index < len(RETRY_BACKOFF_MINUTES):
        minutes = RETRY_BACKOFF_MINUTES[backoff_index]
    else:
        minutes = RETRY_BACKOFF_MINUTES[-1]
    return datetime.now(timezone.utc) + timedelta(minutes=minutes)
"""
PDF worker.

Background worker loop responsible for generating PDFs from queued pdf_jobs
rows and enqueuing the resulting attachment onto a downstream queue.

Architecture rules:
- This module may import from: pdf_repository, photo_repository,
  submission_repository, attachment_repository, downstream_enqueuer,
  pdf_formatter, pdf_constants.
- This module must never: access the database directly (uses repositories),
  import from routers, implement delivery policy, or know which
  downstream queue is active.
- The operation ordering within process_job is an invariant that must not
  be broken. See arch_submission.md.

Operation ordering invariant (must not be reordered):
  1. save_attachment  (UPSERT — safe on retry)
  2. downstream.enqueue  (idempotent — underlying repos use ON CONFLICT DO NOTHING)
  3. pdf_repo.mark_done

A downstream queue row can only exist after save_attachment has completed.
This guarantees the next worker (delivery worker on the email path, or
the PDS worker on the future MESH path) will always find an attachment
when it claims its job.

The active downstream is selected at worker startup by pdf_worker_main.py.
In the email-only configuration (MESH_DELIVERY=0) it is DeliveryEnqueuer.
The worker itself is downstream-agnostic.

Orphan detection:
- Once per loop iteration, list_orphaned_submissions is called on pdf_repo.
  If any are found a CRITICAL log is emitted, rate-limited to one emission
  per ORPHAN_LOG_INTERVAL_SECONDS. No mutation is performed — recovery
  requires operator action. See arch_submission.md.

Crash recovery at each step in process_job:
- Before save_attachment: retry regenerates PDF from stored photos — safe.
- After save_attachment, before enqueue: UPSERT fires, enqueue is
  idempotent, mark_done succeeds — safe.
- After enqueue, before mark_done: UPSERT and the downstream's
  idempotent insert both fire safely, mark_done succeeds — safe.
- After mark_done: job is done and not re-claimed — safe.
There is no crash point that requires operator intervention within a job.

Photo count defensive check:
- The worker compares len(photos) against job["attachment_count"]. A
  mismatch means photos were partially persisted (router crashed mid-save).
  The job is marked failed immediately without generating a PDF.
"""

import logging
import time
from datetime import datetime, timedelta, timezone
from typing import Optional

from app.repositories.attachment_repository import AttachmentRepository
from app.repositories.pdf_repository import PDFRepository
from app.repositories.photo_repository import PhotoRepository
from app.repositories.submission_repository import SubmissionRepository
from app.services.delivery.downstream_enqueuer import DownstreamEnqueuer
from app.services.delivery.pdf_constants import MAX_PDF_ATTEMPTS, PDF_RETRY_BACKOFF_MINUTES
from app.utils.pdf_formatter import generate_pdf
from app.models.serialisation_contracts import ClinicalOutput  # noqa: F401 (used via from_dict)

logger = logging.getLogger(__name__)

# Minimum seconds between CRITICAL orphan log emissions.
ORPHAN_LOG_INTERVAL_SECONDS = 60

# Threshold in minutes before a submission with no pdf_jobs row is considered
# an orphan. Must be long enough that normal submissions are never flagged as
# false positives, but short enough to catch genuinely stuck submissions.
ORPHAN_THRESHOLD_MINUTES = 5


def run_worker(
    pdf_repo: PDFRepository,
    photo_repo: PhotoRepository,
    submission_repo: SubmissionRepository,
    attachment_repo: AttachmentRepository,
    downstream: DownstreamEnqueuer,
    poll_interval: int,
    practice_name: Optional[str],
) -> None:
    """
    Run the PDF worker loop indefinitely.

    Claims one pending pdf_jobs row per iteration, generates the PDF,
    saves the attachment, enqueues the next-stage queue row via the
    downstream adapter, and marks the pdf_job done. Sleeps only when the
    queue is empty.

    psycopg2.OperationalError from claim_next_pending propagates uncaught
    so the process exits and Railway restarts the container.

    Arguments:
        pdf_repo        -- PDFRepository instance
        photo_repo      -- PhotoRepository instance
        submission_repo -- SubmissionRepository instance
        attachment_repo -- AttachmentRepository instance
        downstream      -- DownstreamEnqueuer adapter selected at startup
        poll_interval   -- seconds to sleep when the queue is empty
        practice_name   -- practice name for PDF header; may be None
    """
    logger.info("PDF worker started: poll_interval=%ds", poll_interval)

    last_orphan_log_at: Optional[float] = None

    while True:
        last_orphan_log_at = _check_orphans(
            pdf_repo, last_orphan_log_at, ORPHAN_LOG_INTERVAL_SECONDS
        )

        job = pdf_repo.claim_next_pending()

        if job is None:
            logger.debug("PDF worker queue empty — sleeping %ds", poll_interval)
            time.sleep(poll_interval)
            continue

        submission_id = str(job["submission_id"])
        job_id = str(job["id"])

        try:
            _process_job(
                job=job,
                pdf_repo=pdf_repo,
                photo_repo=photo_repo,
                submission_repo=submission_repo,
                attachment_repo=attachment_repo,
                downstream=downstream,
                practice_name=practice_name,
            )
        except Exception as exc:
            next_retry = _compute_backoff(job["attempt_count"])
            pdf_repo.mark_failed(job_id, str(exc), next_retry_after=next_retry)
            logger.critical(
                "PDF worker: job failed submission_id=%s job_id=%s attempt=%d error=%s",
                submission_id,
                job_id,
                job["attempt_count"] + 1,
                exc,
                exc_info=True,
            )


def _process_job(
    job: dict,
    pdf_repo: PDFRepository,
    photo_repo: PhotoRepository,
    submission_repo: SubmissionRepository,
    attachment_repo: AttachmentRepository,
    downstream: DownstreamEnqueuer,
    practice_name: Optional[str],
) -> None:
    """
    Process a single claimed pdf_jobs row.

    Raises on any error so the caller (run_worker) can mark the job failed
    with the appropriate backoff.

    Operation ordering is an invariant — do not reorder steps 1-3.
    See module docstring and arch_submission.md.
    """
    submission_id = str(job["submission_id"])
    expected_count = job["attachment_count"]

    # --- Defensive photo count check ---
    photos = photo_repo.get_photos(submission_id)
    if len(photos) != expected_count:
        raise ValueError(
            f"Photo count mismatch for submission {submission_id}: "
            f"expected {expected_count}, got {len(photos)}. "
            "Photos may have been partially persisted. "
            "Operator intervention required if this persists after retries."
        )

    # --- Load submission record ---
    submission = submission_repo.get_submission(submission_id)
    clinical_output = ClinicalOutput.from_dict(submission["clinical_output_json"])
    condition_label = submission["condition_label"]
    submitted_at = submission["submitted_at"]

    # --- Generate PDF ---
    pdf_bytes = generate_pdf(
        condition_label=condition_label,
        clinical_output=clinical_output,
        submission_id=submission_id,
        submitted_at=submitted_at,
        practice_name=practice_name,
        photo_bytes=photos if photos else None,
    )

    # --- Step 1: Save attachment (UPSERT — safe on retry) ---
    attachment_repo.save_attachment(submission_id, pdf_bytes)

    # --- Step 2: Enqueue downstream queue row (idempotent in all implementations) ---
    downstream.enqueue(submission_id=submission_id)

    # --- Step 3: Mark pdf_job done ---
    pdf_repo.mark_done(str(job["id"]))

    logger.info(
        "PDF worker: job done submission_id=%s job_id=%s",
        submission_id,
        job["id"],
    )


def _compute_backoff(attempt_count: int) -> Optional[datetime]:
    """
    Compute next_retry_after for a failed attempt.

    attempt_count is the value on the job row before the current failure
    (i.e. the number of attempts already recorded). The backoff index is
    therefore attempt_count, not attempt_count - 1.

    Returns None if the job has exhausted all retries (attempt_count + 1
    >= MAX_PDF_ATTEMPTS), which leaves the job immediately eligible for
    re-claim — but mark_failed will set status = 'failed' permanently at
    that point so it will never be claimed again.
    """
    post_increment = attempt_count + 1
    if post_increment >= MAX_PDF_ATTEMPTS:
        return None
    backoff_index = attempt_count
    if backoff_index < len(PDF_RETRY_BACKOFF_MINUTES):
        minutes = PDF_RETRY_BACKOFF_MINUTES[backoff_index]
    else:
        minutes = PDF_RETRY_BACKOFF_MINUTES[-1]
    return datetime.now(timezone.utc) + timedelta(minutes=minutes)


def _check_orphans(
    pdf_repo: PDFRepository,
    last_log_at: Optional[float],
    interval: int,
) -> Optional[float]:
    """
    Query for orphaned submissions and emit a CRITICAL log if any are found,
    subject to rate limiting. Returns the updated last_log_at timestamp.

    An orphan is a submission_records row with no matching pdf_jobs row that
    is older than ORPHAN_THRESHOLD_MINUTES minutes. This indicates the form
    router crashed after create_submission but before pdf_repo.create_job.

    Rate limiting: if a CRITICAL was emitted within the last `interval`
    seconds, the log is suppressed. The query still runs on every call.

    Returns:
        The current monotonic time if a CRITICAL was just emitted.
        last_log_at unchanged in all other cases.
    """
    now = time.monotonic()
    within_rate_limit = last_log_at is not None and (now - last_log_at) < interval

    try:
        orphan_ids = pdf_repo.list_orphaned_submissions(
            older_than_minutes=ORPHAN_THRESHOLD_MINUTES
        )
    except Exception as exc:
        logger.error("PDF worker: orphan check failed — error=%s", exc)
        return last_log_at

    if orphan_ids and not within_rate_limit:
        logger.critical(
            "PDF worker: orphan submissions detected (no pdf_jobs row, >%d min old). "
            "Inspect submission_photos for each ID to determine recoverability. "
            "Manual insertion of a pdf_jobs row may be possible if photos exist. "
            "submission_ids=%s",
            ORPHAN_THRESHOLD_MINUTES,
            orphan_ids,
        )
        return now

    return last_log_at
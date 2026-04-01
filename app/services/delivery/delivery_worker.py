"""
Delivery worker.

Background worker loop responsible for draining the delivery retry queue.

This module contains a single public function, run_worker, which loops
indefinitely: fetching retryable submission IDs, calling attempt_delivery
for each one, and sleeping only when the queue is empty.

Architecture rules:
- This module may import from: submission_repository, attachment_repository,
  delivery_service, delivery_orchestration.
- This module must never: implement delivery policy, make retry decisions,
  access the database directly, or import clinical engine modules.
- Policy enforcement (guards, backoff, exhaustion) lives exclusively in
  delivery_orchestration.attempt_delivery. The worker calls it blindly.

Concurrency:
- Single-threaded, single process. No parallelism, no locking.
- psycopg2.OperationalError from list_retryable propagates uncaught so the
  process exits and Railway restarts the container. Transient DB blips are
  treated identically to permanent failures — the worker exits and relies
  on Railway restart. See arch_submission.md for the TOCTOU note.

Orphan detection:
- Once per loop iteration, list_orphans is called. If any are found a
  CRITICAL log is emitted. The same orphan IDs will continue to appear
  on every iteration until resolved, so logging is rate-limited to one
  emission per ORPHAN_LOG_INTERVAL_SECONDS to avoid log spam.
- No mutation is performed on orphans — recovery requires operator action.

Per-batch logging:
- After each batch a summary log is emitted: count fetched, count processed,
  elapsed time. This is the primary operational signal that the worker is
  running normally.

Known limitation:
- Under a systemic SMTP outage, a full batch of 50 submissions each timing
  out at 30s means a sweep takes up to 25 minutes. Submissions that become
  retryable during this sweep are not picked up until the next iteration.
  At current single-surgery scale this is acceptable. See arch_submission.md.
"""

import logging
import time
from typing import Optional

from app.repositories.attachment_repository import AttachmentRepository
from app.repositories.submission_repository import SubmissionRepository
from app.services.delivery.delivery_orchestration import attempt_delivery
from app.services.delivery.delivery_service import DeliveryService

logger = logging.getLogger(__name__)

# Minimum seconds between CRITICAL orphan log emissions.
# Prevents a single stuck orphan from flooding the log on every poll cycle.
ORPHAN_LOG_INTERVAL_SECONDS = 60

# Threshold in minutes before a pending submission with 0 attempts is
# considered an orphan. Must be long enough that normal submissions are never
# false-positives, but short enough to catch genuine stuck submissions.
ORPHAN_THRESHOLD_MINUTES = 5


def run_worker(
    submission_repo: SubmissionRepository,
    attachment_repo: AttachmentRepository,
    delivery_service: DeliveryService,
    poll_interval: int,
    batch_limit: int,
) -> None:
    """
    Run the delivery retry worker loop indefinitely.

    Fetches retryable submission IDs from list_retryable, calls
    attempt_delivery for each, and sleeps only when the queue is empty.
    When the queue is non-empty, the next batch is fetched immediately
    after the current one finishes — no sleep between batches.

    Per-item exceptions are caught, logged at CRITICAL, and skipped.
    The worker never terminates due to a per-item failure.

    psycopg2.OperationalError from list_retryable (DB connection failure)
    is not caught. The process exits and Railway restarts the container.

    Arguments:
        submission_repo   -- SubmissionRepository instance
        attachment_repo   -- AttachmentRepository instance
        delivery_service  -- DeliveryService instance (Email or Console)
        poll_interval     -- seconds to sleep when the queue is empty
        batch_limit       -- maximum submissions to fetch per loop iteration
    """
    logger.info(
        "Worker started: poll_interval=%ds batch_limit=%d",
        poll_interval,
        batch_limit,
    )

    last_orphan_log_at: Optional[float] = None

    while True:
        # ------------------------------------------------------------------
        # Orphan detection — once per iteration, rate-limited CRITICAL log.
        # list_orphans failures are caught inside _check_orphans so a DB
        # blip on the orphan check does not abort the loop; only
        # list_retryable failures do.
        # ------------------------------------------------------------------
        last_orphan_log_at = _check_orphans(
            submission_repo, last_orphan_log_at, ORPHAN_LOG_INTERVAL_SECONDS
        )

        # ------------------------------------------------------------------
        # Fetch retryable IDs.
        # psycopg2.OperationalError propagates uncaught — process exits.
        # ------------------------------------------------------------------
        submission_ids = submission_repo.list_retryable(limit=batch_limit)

        if not submission_ids:
            logger.debug("Worker queue empty — sleeping %ds", poll_interval)
            time.sleep(poll_interval)
            continue

        # ------------------------------------------------------------------
        # Process batch.
        # ------------------------------------------------------------------
        batch_start = time.monotonic()
        processed = 0

        for submission_id in submission_ids:
            try:
                attempt_delivery(
                    submission_id,
                    submission_repo,
                    attachment_repo,
                    delivery_service,
                )
                processed += 1
            except Exception as exc:
                logger.critical(
                    "Worker: unhandled exception for submission_id=%s — skipping. "
                    "error=%s",
                    submission_id,
                    exc,
                    exc_info=True,
                )

        elapsed = time.monotonic() - batch_start
        logger.info(
            "Worker batch complete: %d fetched, %d processed in %.1fs",
            len(submission_ids),
            processed,
            elapsed,
        )


def _check_orphans(
    submission_repo: SubmissionRepository,
    last_log_at: Optional[float],
    interval: int,
) -> Optional[float]:
    """
    Query for orphan submissions and emit a CRITICAL log if any are found,
    subject to rate limiting. Returns the updated last_log_at timestamp.

    An orphan is a pending submission with delivery_attempts=0 that is older
    than ORPHAN_THRESHOLD_MINUTES minutes — indicating the router crashed
    before the first delivery attempt completed.

    Rate limiting: if a CRITICAL was emitted within the last `interval`
    seconds, no log is emitted even if orphans exist. This prevents the
    same stuck submission from spamming the log on every poll cycle.
    The query still runs on every call regardless of rate-limit state —
    only the log emission is suppressed.

    Returns:
        The current monotonic time if a CRITICAL was just emitted.
        last_log_at unchanged in all other cases (no orphans, rate-limited,
        or query failed).
    """
    now = time.monotonic()
    within_rate_limit = last_log_at is not None and (now - last_log_at) < interval

    try:
        orphan_ids = submission_repo.list_orphans(
            older_than_minutes=ORPHAN_THRESHOLD_MINUTES
        )
    except Exception as exc:
        logger.error("Worker: orphan check failed — error=%s", exc)
        return last_log_at

    if orphan_ids and not within_rate_limit:
        logger.critical(
            "Worker: orphan submissions detected (pending, 0 attempts, >%d min old). "
            "Manual investigation required. submission_ids=%s",
            ORPHAN_THRESHOLD_MINUTES,
            orphan_ids,
        )
        return now

    return last_log_at
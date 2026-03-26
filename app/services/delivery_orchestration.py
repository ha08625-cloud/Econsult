"""
Delivery orchestration.

Single entry point for all delivery attempts — both the first attempt
from form_router.py and retries from the (deferred) background worker.

This module enforces all delivery policy: guards, send, outcome recording,
and structured logging. The caller never needs to re-implement policy checks.

Architecture rules:
- This module may import from: submission_repository, attachment_repository,
  delivery_service, delivery_constants, delivery_events.
- This module must never: access the database directly (uses repositories),
  import clinical engine modules, or import from routers.
- Exceptions from get_attachment or the repository layer propagate to the
  caller. Only EmailDeliveryError is caught and handled.

Concurrency note (revisit when background worker is added):
There are two TOCTOU sites in attempt_delivery. First, the already-sent
guard checks delivery_status == "sent" at the start; concurrent calls could
both pass this guard before either completes. Second, the exhaustion guard
reads delivery_attempts from get_pending_delivery, but the actual increment
happens atomically inside record_attempt_outcome — using the RETURNING clause
for backoff index calculation closes the data race on the count, but does not
close the guard race. Once a background worker is added, row-level locking
(SELECT ... FOR UPDATE) or an atomic compare-and-swap pattern is required to
close the guard race. Do not add this complexity until the worker ticket.
"""

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Optional

from app.repositories.attachment_repository import AttachmentRepository
from app.repositories.submission_repository import SubmissionRepository
from app.services.delivery_constants import MAX_ATTEMPTS, RETRY_BACKOFF_MINUTES
from app.services.delivery_events import (
    DELIVERY_EXHAUSTED,
    DELIVERY_FAILED,
    DELIVERY_RETRY_TOO_EARLY,
    DELIVERY_SENT,
)
from app.services.delivery_service import DeliveryService, EmailDeliveryError

logger = logging.getLogger(__name__)


class DeliveryOutcomeStatus(Enum):
    """
    All possible outcomes from attempt_delivery.

    SENT and FAILED are delivery outcomes from an actual send attempt.
    ALREADY_SENT, EXHAUSTED, and TOO_EARLY are guard outcomes — the
    function returned without attempting a send.
    """
    SENT = "sent"
    FAILED = "failed"
    ALREADY_SENT = "already_sent"
    EXHAUSTED = "exhausted"
    TOO_EARLY = "too_early"


@dataclass(frozen=True)
class DeliveryOutcome:
    """Result of an attempt_delivery call."""
    status: DeliveryOutcomeStatus
    attempts: int
    next_retry_after: Optional[datetime]
    error: Optional[str]


def attempt_delivery(
    submission_id: str,
    submission_repo: SubmissionRepository,
    attachment_repo: AttachmentRepository,
    delivery_service: DeliveryService,
) -> DeliveryOutcome:
    """
    Attempt to deliver a submission's PDF to the practice.

    Guards are checked in order before any send or attempt increment:
    1. Already sent   — returns ALREADY_SENT immediately, no increment.
    2. Exhaustion     — returns EXHAUSTED immediately, no increment. Logs CRITICAL.
    3. Too early      — returns TOO_EARLY immediately, no increment.

    On success: records "sent" status, clears next_retry_after. Logs DELIVERY_SENT.

    On EmailDeliveryError:
    - Computes expected post-increment count as pending.delivery_attempts + 1.
    - If that count < MAX_ATTEMPTS: sets next_retry_after using the backoff
      schedule. Logs DELIVERY_FAILED.
    - If that count >= MAX_ATTEMPTS: sets next_retry_after=None (exhausted).
      Logs DELIVERY_EXHAUSTED at CRITICAL.
    - Calls record_attempt_outcome once with next_retry_after already computed.
      Uses the RETURNING value as actual_count in DeliveryOutcome to confirm
      the database count matches expectations.

    Exceptions from get_pending_delivery, get_attachment, or
    record_attempt_outcome propagate to the caller. Only EmailDeliveryError
    is caught and handled.

    Returns a DeliveryOutcome with the result. The attempts field uses the
    actual count returned by the database (via RETURNING), not a pre-computed
    value, except for guard returns where no increment occurs.
    """
    now_utc = datetime.now(timezone.utc)

    # Fetch delivery metadata (lightweight — no clinical content).
    pending = submission_repo.get_pending_delivery(submission_id)

    # ------------------------------------------------------------------
    # Guard 1: Already sent
    # ------------------------------------------------------------------
    if pending.delivery_status == "sent":
        return DeliveryOutcome(
            status=DeliveryOutcomeStatus.ALREADY_SENT,
            attempts=pending.delivery_attempts,
            next_retry_after=None,
            error=None,
        )

    # ------------------------------------------------------------------
    # Guard 2: Exhaustion
    # ------------------------------------------------------------------
    if pending.delivery_attempts >= MAX_ATTEMPTS:
        logger.critical(
            "%s submission_id=%s attempts=%d",
            DELIVERY_EXHAUSTED,
            submission_id,
            pending.delivery_attempts,
        )
        return DeliveryOutcome(
            status=DeliveryOutcomeStatus.EXHAUSTED,
            attempts=pending.delivery_attempts,
            next_retry_after=None,
            error=None,
        )

    # ------------------------------------------------------------------
    # Guard 3: Too early
    # ------------------------------------------------------------------
    if pending.next_retry_after is not None and pending.next_retry_after > now_utc:
        logger.debug(
            "%s submission_id=%s next_retry_after=%s",
            DELIVERY_RETRY_TOO_EARLY,
            submission_id,
            pending.next_retry_after.isoformat(),
        )
        return DeliveryOutcome(
            status=DeliveryOutcomeStatus.TOO_EARLY,
            attempts=pending.delivery_attempts,
            next_retry_after=pending.next_retry_after,
            error=None,
        )

    # ------------------------------------------------------------------
    # Guards passed — fetch PDF and attempt send.
    # ------------------------------------------------------------------
    pdf_bytes = attachment_repo.get_attachment(submission_id)

    try:
        delivery_service.send_clinical_output(
            to_email=pending.delivery_email,
            condition_label=pending.condition_label,
            pdf_bytes=pdf_bytes,
            submission_id=submission_id,
            submitted_at=pending.submitted_at,
        )
    except EmailDeliveryError as e:
        # Compute next_retry_after before recording the outcome so we can
        # make exactly one call to record_attempt_outcome.
        #
        # post_increment_count is the delivery_attempts value the database
        # will hold after the UPDATE. We use it to index into the backoff
        # schedule. The RETURNING value from record_attempt_outcome is used
        # as actual_count in the DeliveryOutcome to confirm consistency.
        post_increment_count = pending.delivery_attempts + 1

        if post_increment_count < MAX_ATTEMPTS:
            backoff_index = post_increment_count - 1
            assert backoff_index < len(RETRY_BACKOFF_MINUTES), (
                f"Backoff index {backoff_index} out of range for schedule "
                f"of length {len(RETRY_BACKOFF_MINUTES)}. This indicates "
                f"MAX_ATTEMPTS and RETRY_BACKOFF_MINUTES are out of sync."
            )
            next_retry = now_utc + timedelta(minutes=RETRY_BACKOFF_MINUTES[backoff_index])

            actual_count = submission_repo.record_attempt_outcome(
                submission_id=submission_id,
                delivery_status="failed",
                delivery_error=str(e),
                next_retry_after=next_retry,
            )

            logger.error(
                "%s submission_id=%s attempts=%d next_retry_after=%s error=%s",
                DELIVERY_FAILED,
                submission_id,
                actual_count,
                next_retry.isoformat(),
                str(e),
            )

            return DeliveryOutcome(
                status=DeliveryOutcomeStatus.FAILED,
                attempts=actual_count,
                next_retry_after=next_retry,
                error=str(e),
            )
        else:
            # Exhausted after this attempt.
            actual_count = submission_repo.record_attempt_outcome(
                submission_id=submission_id,
                delivery_status="failed",
                delivery_error=str(e),
                next_retry_after=None,
            )

            logger.critical(
                "%s submission_id=%s attempts=%d error=%s",
                DELIVERY_EXHAUSTED,
                submission_id,
                actual_count,
                str(e),
            )

            return DeliveryOutcome(
                status=DeliveryOutcomeStatus.FAILED,
                attempts=actual_count,
                next_retry_after=None,
                error=str(e),
            )

    # Success path.
    actual_count = submission_repo.record_attempt_outcome(
        submission_id=submission_id,
        delivery_status="sent",
        delivered_at=now_utc,
        next_retry_after=None,
    )

    logger.info(
        "%s submission_id=%s attempts=%d",
        DELIVERY_SENT,
        submission_id,
        actual_count,
    )

    return DeliveryOutcome(
        status=DeliveryOutcomeStatus.SENT,
        attempts=actual_count,
        next_retry_after=None,
        error=None,
    )
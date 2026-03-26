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
"""

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from app.repositories.attachment_repository import AttachmentRepository
from app.repositories.submission_repository import SubmissionRepository
from app.services.delivery_events import (
    DELIVERY_FAILED,
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

    All five values are defined now. The guard statuses (ALREADY_SENT,
    EXHAUSTED, TOO_EARLY) are not returned until retry guards are added
    in Step 2.
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

    At this stage (Step D), no retry guards are implemented. Guards
    (already-sent, exhaustion, too-early) are added in Step 2.

    On success: records "sent" status, clears next_retry_after.
    On EmailDeliveryError: records "failed" status. Does not set
    next_retry_after — that logic is added in Step 2.

    Exceptions from get_pending_delivery, get_attachment, or
    record_attempt_outcome propagate to the caller. Only
    EmailDeliveryError is caught and handled.

    Returns a DeliveryOutcome with the result. The attempts field
    uses the actual count returned by the database (via RETURNING),
    not a pre-computed value.
    """
    now_utc = datetime.now(timezone.utc)

    # Fetch delivery metadata (lightweight — no clinical content).
    pending = submission_repo.get_pending_delivery(submission_id)

    # Fetch PDF bytes.
    pdf_bytes = attachment_repo.get_attachment(submission_id)

    # Attempt the send.
    try:
        delivery_service.send_clinical_output(
            to_email=pending.delivery_email,
            condition_label=pending.condition_label,
            pdf_bytes=pdf_bytes,
            submission_id=submission_id,
            submitted_at=pending.submitted_at,
        )
    except EmailDeliveryError as e:
        # Record failure. next_retry_after is not set at this stage —
        # retry scheduling is added in Step 2.
        actual_count = submission_repo.record_attempt_outcome(
            submission_id=submission_id,
            delivery_status="failed",
            delivery_error=str(e),
        )

        logger.error(
            "%s submission_id=%s attempts=%d error=%s",
            DELIVERY_FAILED,
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
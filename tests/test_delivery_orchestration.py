"""
Unit tests for delivery_orchestration.attempt_delivery (Step D).

These tests use mocks for all three dependencies (submission_repo,
attachment_repo, delivery_service) so no database is required.

At this stage (Step D), retry guards are not yet implemented. These
tests cover the success and failure paths only. Guard tests are added
in Step 2.
"""

import pytest
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from app.services.delivery_orchestration import (
    attempt_delivery,
    DeliveryOutcome,
    DeliveryOutcomeStatus,
)
from app.repositories.submission_repository import (
    PendingDelivery,
    SubmissionNotFound,
)
from app.repositories.attachment_repository import AttachmentNotFound
from app.services.delivery_service import EmailDeliveryError


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_NOW = datetime(2025, 6, 15, 10, 0, 0, tzinfo=timezone.utc)
_SUBMISSION_ID = "test-sub-001"
_DUMMY_PDF = b"%PDF-1.4 test content"


def _make_pending(
    delivery_status="pending",
    delivery_attempts=0,
    next_retry_after=None,
) -> PendingDelivery:
    return PendingDelivery(
        delivery_status=delivery_status,
        delivery_email="practice@example.com",
        condition_label="Urinary Tract Infection",
        submitted_at=_NOW,
        delivery_attempts=delivery_attempts,
        next_retry_after=next_retry_after,
    )


def _make_mocks(
    pending=None,
    pdf_bytes=None,
    send_side_effect=None,
    record_return=1,
):
    """Build mock submission_repo, attachment_repo, and delivery_service."""
    submission_repo = MagicMock()
    submission_repo.get_pending_delivery.return_value = pending or _make_pending()
    submission_repo.record_attempt_outcome.return_value = record_return

    attachment_repo = MagicMock()
    attachment_repo.get_attachment.return_value = pdf_bytes or _DUMMY_PDF

    delivery_service = MagicMock()
    if send_side_effect:
        delivery_service.send_clinical_output.side_effect = send_side_effect

    return submission_repo, attachment_repo, delivery_service


# ---------------------------------------------------------------------------
# Tests: success path
# ---------------------------------------------------------------------------

class TestAttemptDeliverySuccess:
    def test_returns_sent_status(self):
        sub_repo, att_repo, svc = _make_mocks(record_return=1)

        outcome = attempt_delivery(_SUBMISSION_ID, sub_repo, att_repo, svc)

        assert outcome.status == DeliveryOutcomeStatus.SENT
        assert outcome.error is None
        assert outcome.next_retry_after is None

    def test_uses_actual_count_from_database(self):
        """The attempts field comes from RETURNING, not pre-computation."""
        sub_repo, att_repo, svc = _make_mocks(record_return=3)

        outcome = attempt_delivery(_SUBMISSION_ID, sub_repo, att_repo, svc)

        assert outcome.attempts == 3

    def test_calls_send_with_correct_args(self):
        pending = _make_pending()
        sub_repo, att_repo, svc = _make_mocks(pending=pending)

        attempt_delivery(_SUBMISSION_ID, sub_repo, att_repo, svc)

        svc.send_clinical_output.assert_called_once_with(
            to_email="practice@example.com",
            condition_label="Urinary Tract Infection",
            pdf_bytes=_DUMMY_PDF,
            submission_id=_SUBMISSION_ID,
            submitted_at=pending.submitted_at,
        )

    def test_records_sent_outcome(self):
        sub_repo, att_repo, svc = _make_mocks()

        attempt_delivery(_SUBMISSION_ID, sub_repo, att_repo, svc)

        call_kwargs = sub_repo.record_attempt_outcome.call_args
        assert call_kwargs[1]["submission_id"] == _SUBMISSION_ID
        assert call_kwargs[1]["delivery_status"] == "sent"
        assert call_kwargs[1]["next_retry_after"] is None
        assert call_kwargs[1]["delivered_at"] is not None

    def test_clears_next_retry_after_on_success(self):
        sub_repo, att_repo, svc = _make_mocks()

        attempt_delivery(_SUBMISSION_ID, sub_repo, att_repo, svc)

        call_kwargs = sub_repo.record_attempt_outcome.call_args
        assert call_kwargs[1]["next_retry_after"] is None


# ---------------------------------------------------------------------------
# Tests: failure path (EmailDeliveryError)
# ---------------------------------------------------------------------------

class TestAttemptDeliveryFailure:
    def test_returns_failed_status_on_email_error(self):
        sub_repo, att_repo, svc = _make_mocks(
            send_side_effect=EmailDeliveryError("SMTP timeout"),
            record_return=1,
        )

        outcome = attempt_delivery(_SUBMISSION_ID, sub_repo, att_repo, svc)

        assert outcome.status == DeliveryOutcomeStatus.FAILED
        assert outcome.error == "SMTP timeout"

    def test_records_failed_outcome(self):
        sub_repo, att_repo, svc = _make_mocks(
            send_side_effect=EmailDeliveryError("Connection refused"),
        )

        attempt_delivery(_SUBMISSION_ID, sub_repo, att_repo, svc)

        call_kwargs = sub_repo.record_attempt_outcome.call_args
        assert call_kwargs[1]["delivery_status"] == "failed"
        assert call_kwargs[1]["delivery_error"] == "Connection refused"

    def test_does_not_set_next_retry_after_at_step_d(self):
        """Step D does not implement retry scheduling. next_retry_after stays None."""
        sub_repo, att_repo, svc = _make_mocks(
            send_side_effect=EmailDeliveryError("SMTP timeout"),
        )

        outcome = attempt_delivery(_SUBMISSION_ID, sub_repo, att_repo, svc)

        assert outcome.next_retry_after is None
        call_kwargs = sub_repo.record_attempt_outcome.call_args
        # record_attempt_outcome is called without next_retry_after
        # (defaults to None in the function signature)
        assert call_kwargs[1].get("next_retry_after") is None

    def test_uses_actual_count_from_database_on_failure(self):
        sub_repo, att_repo, svc = _make_mocks(
            send_side_effect=EmailDeliveryError("timeout"),
            record_return=2,
        )

        outcome = attempt_delivery(_SUBMISSION_ID, sub_repo, att_repo, svc)

        assert outcome.attempts == 2


# ---------------------------------------------------------------------------
# Tests: propagation of unexpected errors
# ---------------------------------------------------------------------------

class TestAttemptDeliveryPropagation:
    def test_submission_not_found_propagates(self):
        sub_repo = MagicMock()
        sub_repo.get_pending_delivery.side_effect = SubmissionNotFound("missing")
        att_repo = MagicMock()
        svc = MagicMock()

        with pytest.raises(SubmissionNotFound):
            attempt_delivery(_SUBMISSION_ID, sub_repo, att_repo, svc)

    def test_attachment_not_found_propagates(self):
        sub_repo, att_repo, svc = _make_mocks()
        att_repo.get_attachment.side_effect = AttachmentNotFound("missing")

        with pytest.raises(AttachmentNotFound):
            attempt_delivery(_SUBMISSION_ID, sub_repo, att_repo, svc)

    def test_repository_error_on_record_outcome_propagates(self):
        sub_repo, att_repo, svc = _make_mocks()
        sub_repo.record_attempt_outcome.side_effect = RuntimeError("DB gone")

        with pytest.raises(RuntimeError, match="DB gone"):
            attempt_delivery(_SUBMISSION_ID, sub_repo, att_repo, svc)


# ---------------------------------------------------------------------------
# Tests: DeliveryOutcomeStatus enum
# ---------------------------------------------------------------------------

class TestDeliveryOutcomeStatus:
    def test_all_five_values_exist(self):
        assert DeliveryOutcomeStatus.SENT.value == "sent"
        assert DeliveryOutcomeStatus.FAILED.value == "failed"
        assert DeliveryOutcomeStatus.ALREADY_SENT.value == "already_sent"
        assert DeliveryOutcomeStatus.EXHAUSTED.value == "exhausted"
        assert DeliveryOutcomeStatus.TOO_EARLY.value == "too_early"

    def test_enum_member_count(self):
        assert len(DeliveryOutcomeStatus) == 5

    def test_outcome_status_is_enum_not_string(self):
        sub_repo, att_repo, svc = _make_mocks()

        outcome = attempt_delivery(_SUBMISSION_ID, sub_repo, att_repo, svc)

        assert isinstance(outcome.status, DeliveryOutcomeStatus)
        assert not isinstance(outcome.status, str)
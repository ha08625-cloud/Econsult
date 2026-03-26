"""
Unit tests for delivery_orchestration.attempt_delivery.

These tests use mocks for all three dependencies (submission_repo,
attachment_repo, delivery_service) so no database is required.

Covers:
- Success path
- Failure path with retry scheduling
- Failure path when exhausted after this attempt
- Guard: already sent
- Guard: exhaustion (attempts >= MAX_ATTEMPTS before send)
- Guard: too early
- Propagation of unexpected errors
- DeliveryOutcomeStatus enum integrity
"""

import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, call

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
from app.services.delivery_constants import MAX_ATTEMPTS, RETRY_BACKOFF_MINUTES


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_NOW = datetime(2025, 6, 15, 10, 0, 0, tzinfo=timezone.utc)
_SUBMISSION_ID = "test-sub-001"
_DUMMY_PDF = b"%PDF-1.4 test content"

# _FUTURE and _PAST must be relative to real wall-clock time, not the frozen
# _NOW constant. The too-early guard compares against datetime.now(timezone.utc)
# at call time, so a "future" value derived from a fixed 2025 date would already
# be in the past when the test runs.
_FUTURE = datetime.now(timezone.utc) + timedelta(minutes=10)
_PAST = datetime.now(timezone.utc) - timedelta(minutes=2)


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

    def test_record_attempt_outcome_called_once_on_success(self):
        sub_repo, att_repo, svc = _make_mocks()

        attempt_delivery(_SUBMISSION_ID, sub_repo, att_repo, svc)

        sub_repo.record_attempt_outcome.assert_called_once()


# ---------------------------------------------------------------------------
# Tests: failure path — retry scheduling
# ---------------------------------------------------------------------------

class TestAttemptDeliveryFailureWithRetry:
    def test_returns_failed_status_on_email_error(self):
        sub_repo, att_repo, svc = _make_mocks(
            send_side_effect=EmailDeliveryError("SMTP timeout"),
            record_return=1,
        )

        outcome = attempt_delivery(_SUBMISSION_ID, sub_repo, att_repo, svc)

        assert outcome.status == DeliveryOutcomeStatus.FAILED
        assert outcome.error == "SMTP timeout"

    def test_sets_next_retry_after_on_first_failure(self):
        """First failure (attempts goes 0->1) uses RETRY_BACKOFF_MINUTES[0]."""
        pending = _make_pending(delivery_attempts=0)
        sub_repo, att_repo, svc = _make_mocks(
            pending=pending,
            send_side_effect=EmailDeliveryError("timeout"),
            record_return=1,
        )

        outcome = attempt_delivery(_SUBMISSION_ID, sub_repo, att_repo, svc)

        assert outcome.next_retry_after is not None
        expected_minutes = RETRY_BACKOFF_MINUTES[0]
        # Allow a small tolerance for test execution time
        delta = outcome.next_retry_after - datetime.now(timezone.utc)
        assert timedelta(seconds=0) < delta <= timedelta(minutes=expected_minutes + 1)

    def test_sets_next_retry_after_on_second_failure(self):
        """Second failure (attempts goes 1->2) uses RETRY_BACKOFF_MINUTES[1]."""
        pending = _make_pending(delivery_attempts=1, next_retry_after=_PAST)
        sub_repo, att_repo, svc = _make_mocks(
            pending=pending,
            send_side_effect=EmailDeliveryError("timeout"),
            record_return=2,
        )

        outcome = attempt_delivery(_SUBMISSION_ID, sub_repo, att_repo, svc)

        assert outcome.next_retry_after is not None
        expected_minutes = RETRY_BACKOFF_MINUTES[1]
        delta = outcome.next_retry_after - datetime.now(timezone.utc)
        assert timedelta(seconds=0) < delta <= timedelta(minutes=expected_minutes + 1)

    def test_record_attempt_outcome_called_once_on_failure(self):
        """Exactly one call to record_attempt_outcome — not two."""
        sub_repo, att_repo, svc = _make_mocks(
            send_side_effect=EmailDeliveryError("timeout"),
        )

        attempt_delivery(_SUBMISSION_ID, sub_repo, att_repo, svc)

        sub_repo.record_attempt_outcome.assert_called_once()

    def test_records_failed_outcome_with_next_retry_after(self):
        pending = _make_pending(delivery_attempts=0)
        sub_repo, att_repo, svc = _make_mocks(
            pending=pending,
            send_side_effect=EmailDeliveryError("Connection refused"),
        )

        attempt_delivery(_SUBMISSION_ID, sub_repo, att_repo, svc)

        call_kwargs = sub_repo.record_attempt_outcome.call_args[1]
        assert call_kwargs["delivery_status"] == "failed"
        assert call_kwargs["delivery_error"] == "Connection refused"
        assert call_kwargs["next_retry_after"] is not None

    def test_uses_actual_count_from_database_on_failure(self):
        sub_repo, att_repo, svc = _make_mocks(
            send_side_effect=EmailDeliveryError("timeout"),
            record_return=2,
        )

        outcome = attempt_delivery(_SUBMISSION_ID, sub_repo, att_repo, svc)

        assert outcome.attempts == 2

    def test_get_attachment_not_called_before_guards_pass(self):
        """Guards run before get_attachment. Already-sent guard should short-circuit."""
        pending = _make_pending(delivery_status="sent")
        sub_repo, att_repo, svc = _make_mocks(pending=pending)

        attempt_delivery(_SUBMISSION_ID, sub_repo, att_repo, svc)

        att_repo.get_attachment.assert_not_called()


# ---------------------------------------------------------------------------
# Tests: failure path — exhaustion after this attempt
# ---------------------------------------------------------------------------

class TestAttemptDeliveryExhaustion:
    def _make_last_attempt_mocks(self):
        """Set up a submission on its last allowed attempt."""
        # pending.delivery_attempts = MAX_ATTEMPTS - 1 means this is the
        # last allowed send. After failure, post_increment_count = MAX_ATTEMPTS.
        pending = _make_pending(
            delivery_attempts=MAX_ATTEMPTS - 1,
            next_retry_after=_PAST,
        )
        return _make_mocks(
            pending=pending,
            send_side_effect=EmailDeliveryError("final failure"),
            record_return=MAX_ATTEMPTS,
        )

    def test_returns_failed_status_when_exhausted_after_send(self):
        sub_repo, att_repo, svc = self._make_last_attempt_mocks()

        outcome = attempt_delivery(_SUBMISSION_ID, sub_repo, att_repo, svc)

        assert outcome.status == DeliveryOutcomeStatus.FAILED

    def test_next_retry_after_is_none_when_exhausted(self):
        sub_repo, att_repo, svc = self._make_last_attempt_mocks()

        outcome = attempt_delivery(_SUBMISSION_ID, sub_repo, att_repo, svc)

        assert outcome.next_retry_after is None

    def test_records_failed_with_null_next_retry_after_when_exhausted(self):
        sub_repo, att_repo, svc = self._make_last_attempt_mocks()

        attempt_delivery(_SUBMISSION_ID, sub_repo, att_repo, svc)

        call_kwargs = sub_repo.record_attempt_outcome.call_args[1]
        assert call_kwargs["delivery_status"] == "failed"
        assert call_kwargs["next_retry_after"] is None

    def test_record_attempt_outcome_called_once_when_exhausted(self):
        sub_repo, att_repo, svc = self._make_last_attempt_mocks()

        attempt_delivery(_SUBMISSION_ID, sub_repo, att_repo, svc)

        sub_repo.record_attempt_outcome.assert_called_once()


# ---------------------------------------------------------------------------
# Tests: guard — already sent
# ---------------------------------------------------------------------------

class TestGuardAlreadySent:
    def test_returns_already_sent_status(self):
        pending = _make_pending(delivery_status="sent", delivery_attempts=1)
        sub_repo, att_repo, svc = _make_mocks(pending=pending)

        outcome = attempt_delivery(_SUBMISSION_ID, sub_repo, att_repo, svc)

        assert outcome.status == DeliveryOutcomeStatus.ALREADY_SENT

    def test_does_not_increment_attempts(self):
        pending = _make_pending(delivery_status="sent", delivery_attempts=1)
        sub_repo, att_repo, svc = _make_mocks(pending=pending)

        attempt_delivery(_SUBMISSION_ID, sub_repo, att_repo, svc)

        sub_repo.record_attempt_outcome.assert_not_called()

    def test_does_not_send(self):
        pending = _make_pending(delivery_status="sent", delivery_attempts=1)
        sub_repo, att_repo, svc = _make_mocks(pending=pending)

        attempt_delivery(_SUBMISSION_ID, sub_repo, att_repo, svc)

        svc.send_clinical_output.assert_not_called()

    def test_reflects_current_attempt_count(self):
        pending = _make_pending(delivery_status="sent", delivery_attempts=2)
        sub_repo, att_repo, svc = _make_mocks(pending=pending)

        outcome = attempt_delivery(_SUBMISSION_ID, sub_repo, att_repo, svc)

        assert outcome.attempts == 2

    def test_next_retry_after_is_none(self):
        pending = _make_pending(delivery_status="sent", delivery_attempts=1)
        sub_repo, att_repo, svc = _make_mocks(pending=pending)

        outcome = attempt_delivery(_SUBMISSION_ID, sub_repo, att_repo, svc)

        assert outcome.next_retry_after is None
        assert outcome.error is None


# ---------------------------------------------------------------------------
# Tests: guard — exhaustion before send
# ---------------------------------------------------------------------------

class TestGuardExhaustion:
    def test_returns_exhausted_status(self):
        pending = _make_pending(delivery_attempts=MAX_ATTEMPTS)
        sub_repo, att_repo, svc = _make_mocks(pending=pending)

        outcome = attempt_delivery(_SUBMISSION_ID, sub_repo, att_repo, svc)

        assert outcome.status == DeliveryOutcomeStatus.EXHAUSTED

    def test_does_not_increment_attempts(self):
        pending = _make_pending(delivery_attempts=MAX_ATTEMPTS)
        sub_repo, att_repo, svc = _make_mocks(pending=pending)

        attempt_delivery(_SUBMISSION_ID, sub_repo, att_repo, svc)

        sub_repo.record_attempt_outcome.assert_not_called()

    def test_does_not_send(self):
        pending = _make_pending(delivery_attempts=MAX_ATTEMPTS)
        sub_repo, att_repo, svc = _make_mocks(pending=pending)

        attempt_delivery(_SUBMISSION_ID, sub_repo, att_repo, svc)

        svc.send_clinical_output.assert_not_called()

    def test_reflects_current_attempt_count(self):
        pending = _make_pending(delivery_attempts=MAX_ATTEMPTS)
        sub_repo, att_repo, svc = _make_mocks(pending=pending)

        outcome = attempt_delivery(_SUBMISSION_ID, sub_repo, att_repo, svc)

        assert outcome.attempts == MAX_ATTEMPTS

    def test_also_triggers_at_above_max(self):
        """delivery_attempts > MAX_ATTEMPTS (manual data anomaly) also triggers guard."""
        pending = _make_pending(delivery_attempts=MAX_ATTEMPTS + 1)
        sub_repo, att_repo, svc = _make_mocks(pending=pending)

        outcome = attempt_delivery(_SUBMISSION_ID, sub_repo, att_repo, svc)

        assert outcome.status == DeliveryOutcomeStatus.EXHAUSTED
        sub_repo.record_attempt_outcome.assert_not_called()


# ---------------------------------------------------------------------------
# Tests: guard — too early
# ---------------------------------------------------------------------------

class TestGuardTooEarly:
    def test_returns_too_early_status(self):
        pending = _make_pending(
            delivery_status="failed",
            delivery_attempts=1,
            next_retry_after=_FUTURE,
        )
        sub_repo, att_repo, svc = _make_mocks(pending=pending)

        outcome = attempt_delivery(_SUBMISSION_ID, sub_repo, att_repo, svc)

        assert outcome.status == DeliveryOutcomeStatus.TOO_EARLY

    def test_does_not_increment_attempts(self):
        pending = _make_pending(
            delivery_status="failed",
            delivery_attempts=1,
            next_retry_after=_FUTURE,
        )
        sub_repo, att_repo, svc = _make_mocks(pending=pending)

        attempt_delivery(_SUBMISSION_ID, sub_repo, att_repo, svc)

        sub_repo.record_attempt_outcome.assert_not_called()

    def test_does_not_send(self):
        pending = _make_pending(
            delivery_status="failed",
            delivery_attempts=1,
            next_retry_after=_FUTURE,
        )
        sub_repo, att_repo, svc = _make_mocks(pending=pending)

        attempt_delivery(_SUBMISSION_ID, sub_repo, att_repo, svc)

        svc.send_clinical_output.assert_not_called()

    def test_returns_next_retry_after_from_pending(self):
        pending = _make_pending(
            delivery_status="failed",
            delivery_attempts=1,
            next_retry_after=_FUTURE,
        )
        sub_repo, att_repo, svc = _make_mocks(pending=pending)

        outcome = attempt_delivery(_SUBMISSION_ID, sub_repo, att_repo, svc)

        assert outcome.next_retry_after == _FUTURE

    def test_null_next_retry_after_does_not_trigger_guard(self):
        """A pending submission with next_retry_after=None passes this guard."""
        pending = _make_pending(delivery_attempts=0, next_retry_after=None)
        sub_repo, att_repo, svc = _make_mocks(pending=pending)

        outcome = attempt_delivery(_SUBMISSION_ID, sub_repo, att_repo, svc)

        # Should proceed to send, not return TOO_EARLY
        assert outcome.status != DeliveryOutcomeStatus.TOO_EARLY

    def test_past_next_retry_after_does_not_trigger_guard(self):
        """A next_retry_after in the past means the window has elapsed — proceed."""
        pending = _make_pending(
            delivery_status="failed",
            delivery_attempts=1,
            next_retry_after=_PAST,
        )
        sub_repo, att_repo, svc = _make_mocks(pending=pending)

        outcome = attempt_delivery(_SUBMISSION_ID, sub_repo, att_repo, svc)

        assert outcome.status != DeliveryOutcomeStatus.TOO_EARLY


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
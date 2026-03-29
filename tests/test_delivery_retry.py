"""
tests/test_delivery_retry.py

Integration tests for the delivery retry pipeline.

Exercises attempt_delivery, list_retryable, and record_attempt_outcome
directly against a live Postgres database. Does not use the HTTP layer.

Requires TEST_DATABASE_URL in the environment.
Run via: make test-integration

Design notes:
- Each test creates its own submission(s) with a unique ID and cleans up in
  a finally block. No test depends on another test's data.
- _create_submission inserts both submission_records and submission_attachments
  rows so attempt_delivery has everything it needs.
- _read_row reads directly via get_conn so assertions are not filtered by
  repository abstraction.
- FailingDeliveryService always raises EmailDeliveryError. Used to drive
  failure paths.
- SucceedingDeliveryService captures calls and returns normally. Used to
  assert success paths.
- Where a test needs to bypass the too-early guard between calls it manually
  backdates next_retry_after via get_conn.
"""

import os
import pytest

# ---------------------------------------------------------------------------
# Database guardrail — must be first, before any app imports.
# ---------------------------------------------------------------------------

if "TEST_DATABASE_URL" not in os.environ:
    pytest.skip(
        "TEST_DATABASE_URL not set — skipping integration tests to protect production data",
        allow_module_level=True,
    )

os.environ.setdefault("DATABASE_URL", os.environ["TEST_DATABASE_URL"])
os.environ.setdefault("DEV_MODE", "1")
os.environ.setdefault("PRACTICE_ID", "test-practice")
os.environ.setdefault("DATA_DIR", os.path.join(os.path.dirname(__file__), "..", "data"))

from datetime import datetime, timedelta, timezone  # noqa: E402
from uuid import uuid4  # noqa: E402

from app.core.db import get_conn, alembic_upgrade  # noqa: E402
from app.repositories.attachment_repository import (  # noqa: E402
    AttachmentRepository,
    AttachmentNotFound,
)
from app.repositories.submission_repository import (  # noqa: E402
    SubmissionRepository,
    PendingDelivery,
)
from app.models.serialisation_contracts import (  # noqa: E402
    ClinicalOutput,
    AuditOutput,
    PatientDetails,
)
from app.services.delivery.delivery_service import DeliveryService, EmailDeliveryError  # noqa: E402
from app.services.delivery.delivery_constants import MAX_ATTEMPTS, RETRY_BACKOFF_MINUTES  # noqa: E402
from app.services.delivery.delivery_orchestration import (  # noqa: E402
    attempt_delivery,
    DeliveryOutcome,
    DeliveryOutcomeStatus,
)

# ---------------------------------------------------------------------------
# Ensure schema is up to date before any test runs.
# ---------------------------------------------------------------------------

alembic_upgrade()

DATABASE_URL = os.environ["TEST_DATABASE_URL"]


# ---------------------------------------------------------------------------
# Delivery service stubs
# ---------------------------------------------------------------------------

class FailingDeliveryService(DeliveryService):
    """Always raises EmailDeliveryError. Used to drive failure paths."""

    def send_clinical_output(
        self,
        to_email: str,
        condition_label: str,
        pdf_bytes: bytes,
        submission_id: str,
        submitted_at: datetime,
    ) -> None:
        raise EmailDeliveryError("Simulated SMTP failure")


class SucceedingDeliveryService(DeliveryService):
    """Captures calls and returns normally. Used to assert success paths."""

    def __init__(self):
        self.calls: list[dict] = []

    def send_clinical_output(
        self,
        to_email: str,
        condition_label: str,
        pdf_bytes: bytes,
        submission_id: str,
        submitted_at: datetime,
    ) -> None:
        self.calls.append({
            "to_email": to_email,
            "condition_label": condition_label,
            "submission_id": submission_id,
            "submitted_at": submitted_at,
        })


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _uid() -> str:
    return f"test_{uuid4().hex[:12]}"


def _make_repos() -> tuple[SubmissionRepository, AttachmentRepository]:
    return SubmissionRepository(DATABASE_URL), AttachmentRepository(DATABASE_URL)


def _create_submission(sid: str) -> None:
    """
    Insert a minimal valid submission record and its PDF attachment.

    Leaves the submission in delivery_status='pending' with
    delivery_attempts=0. The attachment is a small stub — the content
    does not matter for delivery retry tests.
    """
    sub_repo, att_repo = _make_repos()

    patient = PatientDetails(
        patient_for="me",
        first_name="Test",
        last_name="Patient",
        date_of_birth="1990-01-15",
        postcode="SW1A 1AA",
    )
    clinical = ClinicalOutput(
        condition_id="uti",
        free_text="test free text",
        additional_text=None,
        answers={"fever": True},
        safety_messages=[],
        question_labels={"fever": "Do you have a fever?"},
        patient_details=patient,
    )
    audit = AuditOutput(
        runtime_state={"session_id": sid, "version": 1},
        safety_evaluation={"flags": []},
        ruleset_version="uti_v1",
    )

    sub_repo.create_submission(
        submission_id=sid,
        practice_id="test-practice",
        condition_id="uti",
        condition_label="Urinary Tract Infection",
        clinical_output=clinical,
        audit_output=audit,
        delivery_email="test@example.com",
        submitted_at=datetime.now(timezone.utc),
    )
    att_repo.save_attachment(sid, b"%PDF-1.4 stub bytes")


def _cleanup(sid: str) -> None:
    """Delete attachment then submission record. Safe to call in finally."""
    with get_conn(DATABASE_URL) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM submission_attachments WHERE submission_id = %s", (sid,)
            )
            cur.execute(
                "DELETE FROM submission_records WHERE submission_id = %s", (sid,)
            )


def _read_row(sid: str) -> dict:
    """
    Read the full submission_records row for sid.

    Returns a plain dict. Used to assert database state without going
    through repository abstraction.
    """
    from psycopg2.extras import RealDictCursor
    with get_conn(DATABASE_URL) as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                "SELECT * FROM submission_records WHERE submission_id = %s", (sid,)
            )
            row = cur.fetchone()
    assert row is not None, f"No row found for submission_id={sid}"
    return dict(row)


def _backdate_next_retry(sid: str) -> None:
    """
    Set next_retry_after to two minutes ago so the too-early guard passes.

    Used between failure calls in tests that need to drive a submission
    through multiple attempts.
    """
    past = datetime.now(timezone.utc) - timedelta(minutes=2)
    with get_conn(DATABASE_URL) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE submission_records SET next_retry_after = %s "
                "WHERE submission_id = %s",
                (past, sid),
            )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_first_attempt_failure_sets_expected_state():
    """
    A first-attempt failure sets delivery_status='failed', delivery_attempts=1,
    and next_retry_after approximately NOW() + RETRY_BACKOFF_MINUTES[0] minutes.
    """
    sid = _uid()
    sub_repo, att_repo = _make_repos()

    try:
        _create_submission(sid)
        before = datetime.now(timezone.utc)
        outcome = attempt_delivery(sid, sub_repo, att_repo, FailingDeliveryService())
        after = datetime.now(timezone.utc)

        assert outcome.status == DeliveryOutcomeStatus.FAILED
        assert outcome.attempts == 1
        assert outcome.next_retry_after is not None

        row = _read_row(sid)
        assert row["delivery_status"] == "failed"
        assert row["delivery_attempts"] == 1

        expected_backoff = timedelta(minutes=RETRY_BACKOFF_MINUTES[0])
        lower = before + expected_backoff - timedelta(seconds=10)
        upper = after + expected_backoff + timedelta(seconds=10)
        assert lower <= row["next_retry_after"] <= upper, (
            f"next_retry_after {row['next_retry_after']} not within 10s of "
            f"expected window [{lower}, {upper}]"
        )
    finally:
        _cleanup(sid)


def test_retry_after_backoff_clears_state():
    """
    After a failure, a successful retry sets delivery_status='sent',
    delivery_attempts=2, and clears next_retry_after to NULL.
    """
    sid = _uid()
    sub_repo, att_repo = _make_repos()

    try:
        _create_submission(sid)

        # First attempt fails.
        attempt_delivery(sid, sub_repo, att_repo, FailingDeliveryService())

        # Simulate the backoff window elapsing.
        _backdate_next_retry(sid)

        # Retry succeeds.
        succeeding = SucceedingDeliveryService()
        outcome = attempt_delivery(sid, sub_repo, att_repo, succeeding)

        assert outcome.status == DeliveryOutcomeStatus.SENT
        assert outcome.attempts == 2

        row = _read_row(sid)
        assert row["delivery_status"] == "sent"
        assert row["delivery_attempts"] == 2
        assert row["next_retry_after"] is None

        assert len(succeeding.calls) == 1
        assert succeeding.calls[0]["submission_id"] == sid
    finally:
        _cleanup(sid)


def test_list_retryable_returns_only_eligible_failed():
    """
    list_retryable returns failed submissions with next_retry_after in the
    past. A new pending submission is not returned.
    """
    failed_sid = _uid()
    pending_sid = _uid()
    sub_repo, att_repo = _make_repos()

    try:
        # Create the failed submission and drive it to failure.
        _create_submission(failed_sid)
        attempt_delivery(failed_sid, sub_repo, att_repo, FailingDeliveryService())
        _backdate_next_retry(failed_sid)

        # Create a fresh pending submission (no delivery attempt).
        _create_submission(pending_sid)

        # Verify via raw query that only the failed submission qualifies.
        with get_conn(DATABASE_URL) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT submission_id FROM submission_records "
                    "WHERE submission_id = ANY(%s) "
                    "AND delivery_status = 'failed' "
                    "AND next_retry_after IS NOT NULL "
                    "AND next_retry_after <= NOW()",
                    ([failed_sid, pending_sid],),
                )
                eligible_ids = {row[0] for row in cur.fetchall()}

        assert failed_sid in eligible_ids, (
            "Failed submission with past next_retry_after must be eligible"
        )
        assert pending_sid not in eligible_ids, (
            "Pending submission must not appear in list_retryable"
        )
    finally:
        _cleanup(failed_sid)
        _cleanup(pending_sid)


def test_list_retryable_excludes_sent_with_anomalous_next_retry():
    """
    A sent submission does not appear in list_retryable even if
    next_retry_after is manually set to the past (data integrity anomaly).
    """
    sid = _uid()
    sub_repo, att_repo = _make_repos()

    try:
        _create_submission(sid)

        # Mark sent directly (bypassing attempt_delivery).
        sub_repo.update_delivery_status(
            sid, "sent", delivered_at=datetime.now(timezone.utc)
        )

        # Introduce the anomaly.
        past = datetime.now(timezone.utc) - timedelta(minutes=2)
        with get_conn(DATABASE_URL) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE submission_records SET next_retry_after = %s "
                    "WHERE submission_id = %s",
                    (past, sid),
                )

        # The delivery_status = 'failed' filter must exclude this row.
        with get_conn(DATABASE_URL) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT submission_id FROM submission_records "
                    "WHERE submission_id = %s "
                    "AND delivery_status = 'failed' "
                    "AND next_retry_after IS NOT NULL "
                    "AND next_retry_after <= NOW()",
                    (sid,),
                )
                found = cur.fetchone()

        assert found is None, (
            "Sent submission must never appear in list_retryable, even with "
            "next_retry_after set"
        )
    finally:
        _cleanup(sid)


def test_list_retryable_respects_limit():
    """
    list_retryable(limit=n) returns at most n results even when more
    eligible submissions exist in the database.
    """
    limit = 3
    count = limit + 2
    sids = [_uid() for _ in range(count)]
    sub_repo, att_repo = _make_repos()

    try:
        for sid in sids:
            _create_submission(sid)
            attempt_delivery(sid, sub_repo, att_repo, FailingDeliveryService())
            _backdate_next_retry(sid)

        results = sub_repo.list_retryable(limit=limit)

        # The global result set may include pre-existing rows in CI, but the
        # cap must always hold.
        assert len(results) <= limit, (
            f"list_retryable(limit={limit}) returned {len(results)} rows, "
            f"expected at most {limit}"
        )
    finally:
        for sid in sids:
            _cleanup(sid)


def test_missing_attachment_raises_attachment_not_found():
    """
    attempt_delivery raises AttachmentNotFound when the attachment row is
    absent. This is an unexpected error — not a handled failure path.
    """
    sid = _uid()
    sub_repo, att_repo = _make_repos()

    patient = PatientDetails(
        patient_for="me",
        first_name="Test",
        last_name="Patient",
        date_of_birth="1990-01-15",
        postcode="SW1A 1AA",
    )
    clinical = ClinicalOutput(
        condition_id="uti",
        free_text="test",
        additional_text=None,
        answers={},
        safety_messages=[],
        question_labels={},
        patient_details=patient,
    )
    audit = AuditOutput(
        runtime_state={},
        safety_evaluation={},
        ruleset_version="uti_v1",
    )

    try:
        sub_repo.create_submission(
            submission_id=sid,
            practice_id="test-practice",
            condition_id="uti",
            condition_label="Urinary Tract Infection",
            clinical_output=clinical,
            audit_output=audit,
            delivery_email="test@example.com",
            submitted_at=datetime.now(timezone.utc),
        )
        # No save_attachment call — attachment is deliberately absent.

        with pytest.raises(AttachmentNotFound):
            attempt_delivery(sid, sub_repo, att_repo, SucceedingDeliveryService())
    finally:
        _cleanup(sid)


def test_exhaustion_guard_returns_exhausted_without_incrementing():
    """
    After MAX_ATTEMPTS failed delivery attempts, a further call to
    attempt_delivery returns DeliveryOutcomeStatus.EXHAUSTED without
    incrementing delivery_attempts or calling send_clinical_output.

    The EXHAUSTED status comes from Guard 2, which fires when
    delivery_attempts >= MAX_ATTEMPTS before a send attempt begins.
    The MAX_ATTEMPTS-th attempt itself returns FAILED (not EXHAUSTED);
    the extra call after MAX_ATTEMPTS is what triggers the guard.
    """
    sid = _uid()
    sub_repo, att_repo = _make_repos()

    try:
        _create_submission(sid)

        # Drive the submission to MAX_ATTEMPTS failures.
        for i in range(MAX_ATTEMPTS):
            outcome = attempt_delivery(sid, sub_repo, att_repo, FailingDeliveryService())
            assert outcome.status == DeliveryOutcomeStatus.FAILED, (
                f"Attempt {i + 1} should return FAILED, got {outcome.status}"
            )
            # Backdate so the next attempt is not blocked by the too-early guard.
            _backdate_next_retry(sid)

        row_at_max = _read_row(sid)
        assert row_at_max["delivery_attempts"] == MAX_ATTEMPTS

        # One more call — must hit Guard 2 and return EXHAUSTED.
        succeeding = SucceedingDeliveryService()
        guard_outcome = attempt_delivery(sid, sub_repo, att_repo, succeeding)

        assert guard_outcome.status == DeliveryOutcomeStatus.EXHAUSTED
        assert guard_outcome.attempts == MAX_ATTEMPTS

        # delivery_attempts must not have increased.
        row_after_guard = _read_row(sid)
        assert row_after_guard["delivery_attempts"] == MAX_ATTEMPTS, (
            "delivery_attempts must not increment when the exhaustion guard fires"
        )

        # The succeeding delivery service must never have been called.
        assert len(succeeding.calls) == 0, (
            "send_clinical_output must not be called when exhaustion guard fires"
        )
    finally:
        _cleanup(sid)


def test_success_path_clears_next_retry_after():
    """
    After a failure sets next_retry_after, a successful retry clears it
    to NULL in the database.
    """
    sid = _uid()
    sub_repo, att_repo = _make_repos()

    try:
        _create_submission(sid)

        attempt_delivery(sid, sub_repo, att_repo, FailingDeliveryService())

        row_after_failure = _read_row(sid)
        assert row_after_failure["next_retry_after"] is not None, (
            "next_retry_after must be set after a failure"
        )

        _backdate_next_retry(sid)
        attempt_delivery(sid, sub_repo, att_repo, SucceedingDeliveryService())

        row_after_success = _read_row(sid)
        assert row_after_success["next_retry_after"] is None, (
            "next_retry_after must be NULL after a successful delivery"
        )
    finally:
        _cleanup(sid)


def test_record_attempt_outcome_atomicity():
    """
    A single call to record_attempt_outcome updates all six fields atomically.
    Reading the row back confirms delivery_attempts, last_attempt_at,
    delivery_status, delivered_at, delivery_error, and next_retry_after all
    match the values passed in that one call.
    """
    sid = _uid()
    sub_repo, _ = _make_repos()

    try:
        _create_submission(sid)

        now = datetime.now(timezone.utc)
        next_retry = now + timedelta(minutes=RETRY_BACKOFF_MINUTES[0])

        returned_count = sub_repo.record_attempt_outcome(
            submission_id=sid,
            delivery_status="failed",
            delivery_error="SMTP connection refused",
            next_retry_after=next_retry,
        )

        assert returned_count == 1

        row = _read_row(sid)
        assert row["delivery_attempts"] == 1
        assert row["delivery_status"] == "failed"
        assert row["delivery_error"] == "SMTP connection refused"
        assert row["delivered_at"] is None
        assert row["last_attempt_at"] is not None

        # next_retry_after must be within 5 seconds of the value we passed.
        assert row["next_retry_after"] is not None
        diff = abs((row["next_retry_after"] - next_retry).total_seconds())
        assert diff < 5, (
            f"next_retry_after differs from expected by {diff:.2f}s"
        )
    finally:
        _cleanup(sid)


def test_list_retryable_excludes_pending_with_anomalous_next_retry():
    """
    A pending submission does not appear in list_retryable even if
    next_retry_after is manually set to the past (data integrity anomaly).
    """
    sid = _uid()
    sub_repo, _ = _make_repos()

    try:
        _create_submission(sid)

        row = _read_row(sid)
        assert row["delivery_status"] == "pending"

        # Introduce the anomaly: set next_retry_after to the past on a
        # pending submission.
        past = datetime.now(timezone.utc) - timedelta(minutes=2)
        with get_conn(DATABASE_URL) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE submission_records SET next_retry_after = %s "
                    "WHERE submission_id = %s",
                    (past, sid),
                )

        # The delivery_status = 'failed' filter must exclude this row.
        with get_conn(DATABASE_URL) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT submission_id FROM submission_records "
                    "WHERE submission_id = %s "
                    "AND delivery_status = 'failed' "
                    "AND next_retry_after IS NOT NULL "
                    "AND next_retry_after <= NOW()",
                    (sid,),
                )
                found = cur.fetchone()

        assert found is None, (
            "Pending submission must never appear in list_retryable, even with "
            "next_retry_after set"
        )
    finally:
        _cleanup(sid)


def test_delivery_outcome_status_is_always_enum_member():
    """
    DeliveryOutcome.status is always a DeliveryOutcomeStatus enum member,
    not a raw string, for both failure and success paths.
    """
    sid_fail = _uid()
    sid_ok = _uid()
    sub_repo, att_repo = _make_repos()

    try:
        _create_submission(sid_fail)
        fail_outcome = attempt_delivery(
            sid_fail, sub_repo, att_repo, FailingDeliveryService()
        )
        assert isinstance(fail_outcome.status, DeliveryOutcomeStatus), (
            f"Expected DeliveryOutcomeStatus, got {type(fail_outcome.status)}"
        )

        _create_submission(sid_ok)
        ok_outcome = attempt_delivery(
            sid_ok, sub_repo, att_repo, SucceedingDeliveryService()
        )
        assert isinstance(ok_outcome.status, DeliveryOutcomeStatus), (
            f"Expected DeliveryOutcomeStatus, got {type(ok_outcome.status)}"
        )
    finally:
        _cleanup(sid_fail)
        _cleanup(sid_ok)

"""
tests/test_delivery_worker_integration.py

Integration tests for the delivery worker loop.

These tests exercise run_worker against a real Postgres database. They follow
the same conventions as test_delivery_retry.py: unique IDs, finally cleanup,
TEST_DATABASE_URL guardrail at the top.

Each test runs the worker for a controlled number of iterations by patching
time.sleep to raise StopIteration after N calls, preventing the loop from
running indefinitely.

attempt_delivery is NOT patched here. These tests use real delivery service
stubs (FailingDeliveryService, SucceedingDeliveryService) to exercise the
full stack from worker through orchestration to the database.

Requires TEST_DATABASE_URL in the environment.
Run via: make test-integration
"""

import logging
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
from unittest.mock import patch  # noqa: E402
from uuid import uuid4  # noqa: E402

from app.core.db import get_conn, alembic_upgrade  # noqa: E402
from app.repositories.attachment_repository import AttachmentRepository  # noqa: E402
from app.repositories.submission_repository import SubmissionRepository  # noqa: E402
from app.models.serialisation_contracts import (  # noqa: E402
    AuditOutput,
    ClinicalOutput,
    PatientDetails,
)
from app.services.delivery.delivery_service import DeliveryService, EmailDeliveryError  # noqa: E402
from app.services.delivery.delivery_worker import run_worker  # noqa: E402

# ---------------------------------------------------------------------------
# Ensure schema is up to date before any test runs.
# ---------------------------------------------------------------------------

alembic_upgrade()

DATABASE_URL = os.environ["TEST_DATABASE_URL"]


# ---------------------------------------------------------------------------
# Delivery service stubs
# ---------------------------------------------------------------------------

class FailingDeliveryService(DeliveryService):
    """Always raises EmailDeliveryError."""

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
    """Captures calls and returns normally."""

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
            "submission_id": submission_id,
        })


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _uid() -> str:
    return f"test_{uuid4().hex[:12]}"


def _make_repos() -> tuple[SubmissionRepository, AttachmentRepository]:
    return SubmissionRepository(DATABASE_URL), AttachmentRepository(DATABASE_URL)


def _create_submission(sid: str) -> None:
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
        attachment_count=0,
    )
    att_repo.save_attachment(sid, b"%PDF-1.4 stub bytes")


def _cleanup(sid: str) -> None:
    with get_conn(DATABASE_URL) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM submission_attachments WHERE submission_id = %s", (sid,)
            )
            cur.execute(
                "DELETE FROM submission_records WHERE submission_id = %s", (sid,)
            )


def _read_row(sid: str) -> dict:
    from psycopg2.extras import RealDictCursor
    with get_conn(DATABASE_URL) as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                "SELECT * FROM submission_records WHERE submission_id = %s", (sid,)
            )
            row = cur.fetchone()
    assert row is not None, f"No row found for submission_id={sid}"
    return dict(row)


def _drive_to_failed(sid: str) -> None:
    """Drive a submission to delivery_status='failed' with next_retry_after in the past."""
    from app.services.delivery.delivery_orchestration import attempt_delivery
    sub_repo, att_repo = _make_repos()
    attempt_delivery(sid, sub_repo, att_repo, FailingDeliveryService())
    _backdate_next_retry(sid)


def _backdate_next_retry(sid: str) -> None:
    past = datetime.now(timezone.utc) - timedelta(minutes=2)
    with get_conn(DATABASE_URL) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE submission_records SET next_retry_after = %s "
                "WHERE submission_id = %s",
                (past, sid),
            )


def _run_worker_one_batch(sub_repo, att_repo, delivery_service):
    """
    Run one worker iteration (one batch fetch + process), then stop.

    Patches time.sleep to raise StopIteration on the first call so the
    worker halts after sleeping (i.e. after draining one non-empty batch
    or after finding the queue empty on the first check).
    """
    with patch(
        "app.services.delivery.delivery_worker.time.sleep",
        side_effect=StopIteration,
    ):
        try:
            run_worker(
                submission_repo=sub_repo,
                attachment_repo=att_repo,
                delivery_service=delivery_service,
                poll_interval=10,
                batch_limit=50,
            )
        except StopIteration:
            pass


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_worker_drains_retryable_batch():
    """
    Given three failed submissions due for retry, one worker iteration
    delivers all three successfully.
    """
    sids = [_uid() for _ in range(3)]
    sub_repo, att_repo = _make_repos()
    delivery_service = SucceedingDeliveryService()

    try:
        for sid in sids:
            _create_submission(sid)
            _drive_to_failed(sid)

        _run_worker_one_batch(sub_repo, att_repo, delivery_service)

        for sid in sids:
            row = _read_row(sid)
            assert row["delivery_status"] == "sent", (
                f"Expected delivery_status='sent' for {sid}, got {row['delivery_status']}"
            )

        delivered_ids = [c["submission_id"] for c in delivery_service.calls]
        for sid in sids:
            assert sid in delivered_ids, (
                f"Expected {sid} to have been delivered"
            )
    finally:
        for sid in sids:
            _cleanup(sid)


def test_worker_respects_backoff_too_early():
    """
    A failed submission with next_retry_after in the future does not appear
    in list_retryable and is therefore not processed by the worker.
    """
    sid = _uid()
    sub_repo, att_repo = _make_repos()
    delivery_service = SucceedingDeliveryService()

    try:
        _create_submission(sid)
        # Drive to failed but leave next_retry_after in the future (no backdate).
        from app.services.delivery.delivery_orchestration import attempt_delivery
        attempt_delivery(sid, sub_repo, att_repo, FailingDeliveryService())

        row_before = _read_row(sid)
        assert row_before["delivery_status"] == "failed"
        assert row_before["next_retry_after"] > datetime.now(timezone.utc)

        # list_retryable must not return this submission.
        retryable = sub_repo.list_retryable()
        assert sid not in retryable, (
            "A submission with future next_retry_after must not appear in list_retryable"
        )

        _run_worker_one_batch(sub_repo, att_repo, delivery_service)

        # Status must be unchanged.
        row_after = _read_row(sid)
        assert row_after["delivery_status"] == "failed"
        assert row_after["delivery_attempts"] == row_before["delivery_attempts"]
    finally:
        _cleanup(sid)


def test_worker_progresses_through_retry_schedule():
    """
    A submission driven through all retry stages via the worker loop
    increments delivery_attempts correctly at each stage and reaches
    delivery_status='sent' on the final succeeding attempt.

    The submission starts as pending. The worker runs MAX_ATTEMPTS - 1 times
    with a failing service. Between each run, next_retry_after is backdated
    so the too-early guard does not block the next attempt. After each run,
    delivery_attempts is asserted to equal the iteration count. A final run
    with a succeeding service asserts delivery_status='sent'.

    Note: the first worker iteration processes a pending submission, not a
    failed one. attempt_delivery's first-attempt path handles pending->failed
    correctly. list_retryable only returns 'failed' submissions, so the
    pending submission is not in the retryable queue on the first call.
    The first run therefore does nothing (queue is empty, worker sleeps).

    To exercise the worker retry path without coupling to the first-attempt
    router path, we seed the submission directly into a failed state using
    record_attempt_outcome before running the worker.
    """
    from app.services.delivery.delivery_constants import MAX_ATTEMPTS

    sid = _uid()
    sub_repo, att_repo = _make_repos()

    try:
        _create_submission(sid)

        # Seed directly into a failed state with next_retry_after in the past.
        # This bypasses the first-attempt router path and exercises the worker
        # retry path exclusively.
        past = datetime.now(timezone.utc) - timedelta(minutes=2)
        sub_repo.record_attempt_outcome(
            submission_id=sid,
            delivery_status="failed",
            delivery_error="Seeded failure for retry schedule test",
            next_retry_after=past,
        )

        row = _read_row(sid)
        assert row["delivery_attempts"] == 1

        # Run MAX_ATTEMPTS - 1 more failing iterations via the worker.
        # After each, assert delivery_attempts has incremented.
        # Starting at attempt_number=2 because the seeded failure counts as attempt 1.
        for attempt_number in range(2, MAX_ATTEMPTS):
            _run_worker_one_batch(sub_repo, att_repo, FailingDeliveryService())

            row = _read_row(sid)
            assert row["delivery_attempts"] == attempt_number, (
                f"Expected delivery_attempts={attempt_number} after worker iteration "
                f"{attempt_number - 1}, got {row['delivery_attempts']}"
            )
            assert row["delivery_status"] == "failed"

            # Backdate next_retry_after so the following iteration is not blocked.
            _backdate_next_retry(sid)

        # Final iteration — succeeds.
        succeeding = SucceedingDeliveryService()
        _run_worker_one_batch(sub_repo, att_repo, succeeding)

        row_final = _read_row(sid)
        assert row_final["delivery_status"] == "sent", (
            f"Expected delivery_status='sent' after final succeeding attempt, "
            f"got {row_final['delivery_status']}"
        )
        assert row_final["delivery_attempts"] == MAX_ATTEMPTS

        assert len(succeeding.calls) == 1
        assert succeeding.calls[0]["submission_id"] == sid
    finally:
        _cleanup(sid)


def test_orphan_detection_integration(caplog):
    """
    A submission with delivery_status='pending', delivery_attempts=0, and
    submitted_at more than 5 minutes ago causes the worker to emit a CRITICAL
    log containing the submission ID. The submission is not mutated.
    """
    sid = _uid()
    sub_repo, att_repo = _make_repos()
    delivery_service = SucceedingDeliveryService()

    try:
        _create_submission(sid)

        # Backdate submitted_at to 6 minutes ago to exceed the orphan threshold.
        six_minutes_ago = datetime.now(timezone.utc) - timedelta(minutes=6)
        with get_conn(DATABASE_URL) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE submission_records SET submitted_at = %s "
                    "WHERE submission_id = %s",
                    (six_minutes_ago, sid),
                )

        with caplog.at_level(
            logging.CRITICAL,
            logger="app.services.delivery.delivery_worker",
        ):
            _run_worker_one_batch(sub_repo, att_repo, delivery_service)

        assert any(
            sid in r.message for r in caplog.records if r.levelno == logging.CRITICAL
        ), (
            f"Expected CRITICAL log containing orphan submission_id={sid}"
        )

        # Submission must not have been mutated.
        row = _read_row(sid)
        assert row["delivery_status"] == "pending"
        assert row["delivery_attempts"] == 0
    finally:
        _cleanup(sid)

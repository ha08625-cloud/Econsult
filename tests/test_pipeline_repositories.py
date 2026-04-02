"""
tests/test_pipeline_repositories.py

Integration tests for PDFRepository and DeliveryRepository.

Exercises the pdf_jobs and delivery_jobs tables directly against a live
Postgres database. Does not use the HTTP layer.

Requires TEST_DATABASE_URL in the environment.
Run via: make test-integration

Design notes:
- Each test creates its own submission with a unique ID and cleans up in a
  finally block. No test depends on another test's data.
- _create_submission inserts only a submission_records row. PDFRepository
  and DeliveryRepository tests create their own job rows.
- _cleanup deletes child rows before the parent submission_records row to
  satisfy FK constraints.
- claim_next_pending tests use backdating of next_retry_after via get_conn
  to simulate eligibility without waiting for real time to pass.
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

from datetime import datetime, timedelta, timezone  # noqa: E402
from uuid import uuid4  # noqa: E402

from app.core.db import get_conn, alembic_upgrade  # noqa: E402
from app.repositories.submission_repository import SubmissionRepository  # noqa: E402
from app.repositories.pdf_repository import PDFRepository, PDFJobNotFound  # noqa: E402
from app.repositories.delivery_repository import DeliveryRepository, DeliveryJobNotFound  # noqa: E402
from app.models.serialisation_contracts import (  # noqa: E402
    ClinicalOutput,
    AuditOutput,
    PatientDetails,
)
from app.services.delivery.pdf_constants import MAX_PDF_ATTEMPTS  # noqa: E402
from app.services.delivery.delivery_constants import MAX_ATTEMPTS  # noqa: E402

# ---------------------------------------------------------------------------
# Ensure schema is up to date before any test runs.
# ---------------------------------------------------------------------------

alembic_upgrade()

DATABASE_URL = os.environ["TEST_DATABASE_URL"]


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _uid() -> str:
    return f"test_{uuid4().hex[:12]}"


def _create_submission(sid: str) -> None:
    """
    Insert a minimal valid submission_records row.

    Does not create pdf_jobs or delivery_jobs rows — individual tests do that.
    """
    repo = SubmissionRepository(DATABASE_URL)

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

    repo.create_submission(
        submission_id=sid,
        practice_id="test-practice",
        condition_id="uti",
        condition_label="Urinary Tract Infection",
        clinical_output=clinical,
        audit_output=audit,
        delivery_email="gp@example.com",
        submitted_at=datetime.now(timezone.utc),
        attachment_count=2,
    )


def _cleanup(sid: str) -> None:
    """Delete a submission and all FK child rows in dependency order."""
    with get_conn(DATABASE_URL) as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM delivery_jobs WHERE submission_id = %s", (sid,))
            cur.execute("DELETE FROM pdf_jobs WHERE submission_id = %s", (sid,))
            cur.execute("DELETE FROM submission_attachments WHERE submission_id = %s", (sid,))
            cur.execute("DELETE FROM submission_records WHERE submission_id = %s", (sid,))


def _backdate_pdf_job_retry(job_id: str) -> None:
    """Set next_retry_after to the past so the job is immediately eligible."""
    with get_conn(DATABASE_URL) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE pdf_jobs SET next_retry_after = NOW() - INTERVAL '1 minute' WHERE id = %s",
                (job_id,),
            )


def _backdate_delivery_job_retry(job_id: str) -> None:
    """Set next_retry_after to the past so the job is immediately eligible."""
    with get_conn(DATABASE_URL) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE delivery_jobs SET next_retry_after = NOW() - INTERVAL '1 minute' WHERE id = %s",
                (job_id,),
            )


def _read_pdf_job(job_id: str) -> dict:
    with get_conn(DATABASE_URL) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM pdf_jobs WHERE id = %s", (job_id,))
            row = cur.fetchone()
            cols = [desc[0] for desc in cur.description]
    return dict(zip(cols, row))


def _read_delivery_job(job_id: str) -> dict:
    with get_conn(DATABASE_URL) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM delivery_jobs WHERE id = %s", (job_id,))
            row = cur.fetchone()
            cols = [desc[0] for desc in cur.description]
    return dict(zip(cols, row))


# ===========================================================================
# PDFRepository tests
# ===========================================================================

class TestPDFRepositoryCreateJob:
    def test_create_job_inserts_pending_row(self):
        sid = _uid()
        repo = PDFRepository(DATABASE_URL)
        try:
            _create_submission(sid)
            job_id = repo.create_job(sid, attachment_count=2, delivery_email="gp@example.com")
            row = _read_pdf_job(job_id)
            assert str(row["submission_id"]) == sid
            assert row["status"] == "pending"
            assert row["attempt_count"] == 0
            assert row["attachment_count"] == 2
            assert row["delivery_email"] == "gp@example.com"
            assert row["last_error"] is None
        finally:
            _cleanup(sid)

    def test_create_job_returns_string_id(self):
        sid = _uid()
        repo = PDFRepository(DATABASE_URL)
        try:
            _create_submission(sid)
            job_id = repo.create_job(sid, attachment_count=0, delivery_email="gp@example.com")
            assert isinstance(job_id, str)
            assert len(job_id) > 0
        finally:
            _cleanup(sid)


class TestPDFRepositoryClaimNextPending:
    def test_returns_none_when_queue_is_empty(self):
        repo = PDFRepository(DATABASE_URL)
        # We cannot guarantee the queue is truly empty in a shared DB, but we
        # can verify the call does not raise and returns None or a dict.
        result = repo.claim_next_pending()
        assert result is None or isinstance(result, dict)

    def test_claim_returns_the_pending_row(self):
        sid = _uid()
        repo = PDFRepository(DATABASE_URL)
        try:
            _create_submission(sid)
            job_id = repo.create_job(sid, attachment_count=2, delivery_email="gp@example.com")
            claimed = repo.claim_next_pending()
            assert claimed is not None, "Expected a claimed job, got None"
            assert str(claimed["id"]) == job_id
        finally:
            _cleanup(sid)

    def test_claim_updates_next_retry_after_atomically(self):
        """
        After claiming, next_retry_after should be set to a future time so the
        job is not immediately re-claimed by a concurrent worker.
        """
        sid = _uid()
        repo = PDFRepository(DATABASE_URL)
        try:
            _create_submission(sid)
            job_id = repo.create_job(sid, attachment_count=2, delivery_email="gp@example.com")
            repo.claim_next_pending()
            row = _read_pdf_job(job_id)
            assert row["next_retry_after"] is not None
            assert row["next_retry_after"] > datetime.now(timezone.utc)
        finally:
            _cleanup(sid)

    def test_two_eligible_rows_only_one_claimed(self):
        """
        With two eligible jobs, a single call to claim_next_pending returns
        exactly one row. The second call (after backdating) returns the other.
        """
        sid1, sid2 = _uid(), _uid()
        repo = PDFRepository(DATABASE_URL)
        try:
            _create_submission(sid1)
            _create_submission(sid2)
            job_id1 = repo.create_job(sid1, attachment_count=0, delivery_email="gp@example.com")
            job_id2 = repo.create_job(sid2, attachment_count=0, delivery_email="gp@example.com")

            first = repo.claim_next_pending()
            assert first is not None

            # The second job is now beyond the claim window. Backdate it.
            _backdate_pdf_job_retry(job_id2 if str(first["id"]) == job_id1 else job_id1)
            second = repo.claim_next_pending()
            assert second is not None

            claimed_ids = {str(first["id"]), str(second["id"])}
            assert claimed_ids == {job_id1, job_id2}
        finally:
            _cleanup(sid1)
            _cleanup(sid2)


class TestPDFRepositoryMarkDone:
    def test_mark_done_sets_status(self):
        sid = _uid()
        repo = PDFRepository(DATABASE_URL)
        try:
            _create_submission(sid)
            job_id = repo.create_job(sid, attachment_count=2, delivery_email="gp@example.com")
            repo.mark_done(job_id)
            row = _read_pdf_job(job_id)
            assert row["status"] == "done"
            assert row["last_error"] is None
        finally:
            _cleanup(sid)


class TestPDFRepositoryMarkFailed:
    def test_below_max_attempts_leaves_status_pending(self):
        """A failure below MAX_PDF_ATTEMPTS keeps status = 'pending' for retry."""
        assert MAX_PDF_ATTEMPTS > 1, "Test requires MAX_PDF_ATTEMPTS > 1"
        sid = _uid()
        repo = PDFRepository(DATABASE_URL)
        future = datetime.now(timezone.utc) + timedelta(minutes=5)
        try:
            _create_submission(sid)
            job_id = repo.create_job(sid, attachment_count=2, delivery_email="gp@example.com")
            repo.mark_failed(job_id, "PDF generation failed", next_retry_after=future)
            row = _read_pdf_job(job_id)
            assert row["status"] == "pending"
            assert row["attempt_count"] == 1
            assert row["last_error"] == "PDF generation failed"
            assert row["next_retry_after"] is not None
        finally:
            _cleanup(sid)

    def test_at_max_attempts_sets_status_failed(self):
        """After MAX_PDF_ATTEMPTS failures, status is set to 'failed' permanently."""
        sid = _uid()
        repo = PDFRepository(DATABASE_URL)
        future = datetime.now(timezone.utc) + timedelta(minutes=5)
        try:
            _create_submission(sid)
            job_id = repo.create_job(sid, attachment_count=2, delivery_email="gp@example.com")

            for i in range(MAX_PDF_ATTEMPTS - 1):
                _backdate_pdf_job_retry(job_id)
                repo.mark_failed(job_id, f"failure {i + 1}", next_retry_after=future)
                row = _read_pdf_job(job_id)
                assert row["status"] == "pending", (
                    f"Expected pending after failure {i + 1}, got {row['status']}"
                )

            _backdate_pdf_job_retry(job_id)
            repo.mark_failed(job_id, f"failure {MAX_PDF_ATTEMPTS}", next_retry_after=future)
            row = _read_pdf_job(job_id)
            assert row["status"] == "failed", (
                f"Expected failed after {MAX_PDF_ATTEMPTS} attempts, got {row['status']}"
            )
            assert row["attempt_count"] == MAX_PDF_ATTEMPTS
        finally:
            _cleanup(sid)

    def test_mark_failed_raises_for_unknown_job(self):
        repo = PDFRepository(DATABASE_URL)
        raised = False
        try:
            repo.mark_failed(
                str(uuid4()),
                "error",
                next_retry_after=None,
            )
        except PDFJobNotFound:
            raised = True
        assert raised, "Expected PDFJobNotFound was not raised"


class TestPDFRepositoryGet:
    def test_get_returns_row(self):
        sid = _uid()
        repo = PDFRepository(DATABASE_URL)
        try:
            _create_submission(sid)
            job_id = repo.create_job(sid, attachment_count=2, delivery_email="gp@example.com")
            row = repo.get(job_id)
            assert str(row["id"]) == job_id
            assert row["status"] == "pending"
        finally:
            _cleanup(sid)

    def test_get_raises_for_unknown_job(self):
        repo = PDFRepository(DATABASE_URL)
        raised = False
        try:
            repo.get(str(uuid4()))
        except PDFJobNotFound:
            raised = True
        assert raised, "Expected PDFJobNotFound was not raised"


class TestPDFRepositoryListOrphanedSubmissions:
    def test_returns_submission_with_no_pdf_job(self):
        """
        A submission older than the threshold with no pdf_jobs entry is an orphan.
        """
        sid = _uid()
        try:
            _create_submission(sid)
            # Backdate submitted_at to 6 minutes ago.
            with get_conn(DATABASE_URL) as conn:
                with conn.cursor() as cur:
                    six_ago = datetime.now(timezone.utc) - timedelta(minutes=6)
                    cur.execute(
                        "UPDATE submission_records SET submitted_at = %s WHERE submission_id = %s",
                        (six_ago, sid),
                    )

            repo = PDFRepository(DATABASE_URL)
            orphans = repo.list_orphaned_submissions(older_than_minutes=5)
            assert sid in orphans, f"Expected {sid} in orphan list, got {orphans}"
        finally:
            _cleanup(sid)

    def test_does_not_return_submission_with_pdf_job(self):
        """
        A submission that has a pdf_jobs entry is not an orphan, even if old.
        """
        sid = _uid()
        repo = PDFRepository(DATABASE_URL)
        try:
            _create_submission(sid)
            repo.create_job(sid, attachment_count=2, delivery_email="gp@example.com")
            with get_conn(DATABASE_URL) as conn:
                with conn.cursor() as cur:
                    six_ago = datetime.now(timezone.utc) - timedelta(minutes=6)
                    cur.execute(
                        "UPDATE submission_records SET submitted_at = %s WHERE submission_id = %s",
                        (six_ago, sid),
                    )

            orphans = repo.list_orphaned_submissions(older_than_minutes=5)
            assert sid not in orphans, (
                f"Submission with a pdf_jobs entry should not be an orphan"
            )
        finally:
            _cleanup(sid)

    def test_does_not_return_recent_submission(self):
        """A submission created just now is not an orphan regardless of pdf_jobs."""
        sid = _uid()
        try:
            _create_submission(sid)
            # submitted_at is NOW() by default — within the 5-minute threshold
            repo = PDFRepository(DATABASE_URL)
            orphans = repo.list_orphaned_submissions(older_than_minutes=5)
            assert sid not in orphans, (
                "A freshly created submission should not appear in orphan list"
            )
        finally:
            _cleanup(sid)


# ===========================================================================
# DeliveryRepository tests
# ===========================================================================

class TestDeliveryRepositoryCreateJob:
    def test_create_job_inserts_pending_row(self):
        sid = _uid()
        repo = DeliveryRepository(DATABASE_URL)
        submitted_at = datetime.now(timezone.utc)
        try:
            _create_submission(sid)
            job_id = repo.create_job(
                submission_id=sid,
                to_email="gp@example.com",
                condition_label="Urinary Tract Infection",
                submitted_at=submitted_at,
            )
            row = _read_delivery_job(job_id)
            assert str(row["submission_id"]) == sid
            assert row["status"] == "pending"
            assert row["attempt_count"] == 0
            assert row["to_email"] == "gp@example.com"
            assert row["condition_label"] == "Urinary Tract Infection"
            assert row["last_error"] is None
        finally:
            _cleanup(sid)

    def test_create_job_second_call_same_submission_is_idempotent(self):
        """
        Calling create_job twice with the same submission_id must not raise and
        must not insert a duplicate row.
        """
        sid = _uid()
        repo = DeliveryRepository(DATABASE_URL)
        submitted_at = datetime.now(timezone.utc)
        try:
            _create_submission(sid)
            job_id_1 = repo.create_job(
                submission_id=sid,
                to_email="gp@example.com",
                condition_label="Urinary Tract Infection",
                submitted_at=submitted_at,
            )
            job_id_2 = repo.create_job(
                submission_id=sid,
                to_email="gp@example.com",
                condition_label="Urinary Tract Infection",
                submitted_at=submitted_at,
            )
            # Both calls return the same job id
            assert job_id_1 == job_id_2, (
                f"Expected same job_id on conflict, got {job_id_1} vs {job_id_2}"
            )
            # Only one row exists
            with get_conn(DATABASE_URL) as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "SELECT COUNT(*) FROM delivery_jobs WHERE submission_id = %s",
                        (sid,),
                    )
                    count = cur.fetchone()[0]
            assert count == 1, f"Expected 1 delivery_jobs row, got {count}"
        finally:
            _cleanup(sid)


class TestDeliveryRepositoryClaimNextPending:
    def test_returns_none_when_queue_is_empty(self):
        repo = DeliveryRepository(DATABASE_URL)
        result = repo.claim_next_pending()
        assert result is None or isinstance(result, dict)

    def test_claim_returns_the_pending_row(self):
        sid = _uid()
        repo = DeliveryRepository(DATABASE_URL)
        submitted_at = datetime.now(timezone.utc)
        try:
            _create_submission(sid)
            job_id = repo.create_job(
                submission_id=sid,
                to_email="gp@example.com",
                condition_label="Urinary Tract Infection",
                submitted_at=submitted_at,
            )
            claimed = repo.claim_next_pending()
            assert claimed is not None, "Expected a claimed job, got None"
            assert str(claimed["id"]) == job_id
        finally:
            _cleanup(sid)

    def test_claim_updates_next_retry_after_atomically(self):
        sid = _uid()
        repo = DeliveryRepository(DATABASE_URL)
        submitted_at = datetime.now(timezone.utc)
        try:
            _create_submission(sid)
            job_id = repo.create_job(
                submission_id=sid,
                to_email="gp@example.com",
                condition_label="Urinary Tract Infection",
                submitted_at=submitted_at,
            )
            repo.claim_next_pending()
            row = _read_delivery_job(job_id)
            assert row["next_retry_after"] is not None
            assert row["next_retry_after"] > datetime.now(timezone.utc)
        finally:
            _cleanup(sid)


class TestDeliveryRepositoryMarkSent:
    def test_mark_sent_sets_status(self):
        sid = _uid()
        repo = DeliveryRepository(DATABASE_URL)
        submitted_at = datetime.now(timezone.utc)
        try:
            _create_submission(sid)
            job_id = repo.create_job(
                submission_id=sid,
                to_email="gp@example.com",
                condition_label="Urinary Tract Infection",
                submitted_at=submitted_at,
            )
            repo.mark_sent(job_id)
            row = _read_delivery_job(job_id)
            assert row["status"] == "sent"
        finally:
            _cleanup(sid)


class TestDeliveryRepositoryMarkFailed:
    def test_below_max_attempts_leaves_status_pending(self):
        assert MAX_ATTEMPTS > 1, "Test requires MAX_ATTEMPTS > 1"
        sid = _uid()
        repo = DeliveryRepository(DATABASE_URL)
        submitted_at = datetime.now(timezone.utc)
        future = datetime.now(timezone.utc) + timedelta(minutes=5)
        try:
            _create_submission(sid)
            job_id = repo.create_job(
                submission_id=sid,
                to_email="gp@example.com",
                condition_label="Urinary Tract Infection",
                submitted_at=submitted_at,
            )
            repo.mark_failed(job_id, "SMTP timeout", next_retry_after=future)
            row = _read_delivery_job(job_id)
            assert row["status"] == "pending"
            assert row["attempt_count"] == 1
            assert row["last_error"] == "SMTP timeout"
        finally:
            _cleanup(sid)

    def test_at_max_attempts_sets_status_failed(self):
        sid = _uid()
        repo = DeliveryRepository(DATABASE_URL)
        submitted_at = datetime.now(timezone.utc)
        future = datetime.now(timezone.utc) + timedelta(minutes=5)
        try:
            _create_submission(sid)
            job_id = repo.create_job(
                submission_id=sid,
                to_email="gp@example.com",
                condition_label="Urinary Tract Infection",
                submitted_at=submitted_at,
            )

            for i in range(MAX_ATTEMPTS - 1):
                _backdate_delivery_job_retry(job_id)
                repo.mark_failed(job_id, f"failure {i + 1}", next_retry_after=future)
                row = _read_delivery_job(job_id)
                assert row["status"] == "pending", (
                    f"Expected pending after failure {i + 1}, got {row['status']}"
                )

            _backdate_delivery_job_retry(job_id)
            repo.mark_failed(job_id, f"failure {MAX_ATTEMPTS}", next_retry_after=future)
            row = _read_delivery_job(job_id)
            assert row["status"] == "failed", (
                f"Expected failed after {MAX_ATTEMPTS} attempts, got {row['status']}"
            )
            assert row["attempt_count"] == MAX_ATTEMPTS
        finally:
            _cleanup(sid)

    def test_mark_failed_raises_for_unknown_job(self):
        repo = DeliveryRepository(DATABASE_URL)
        raised = False
        try:
            repo.mark_failed(str(uuid4()), "error", next_retry_after=None)
        except DeliveryJobNotFound:
            raised = True
        assert raised, "Expected DeliveryJobNotFound was not raised"


class TestDeliveryRepositoryGet:
    def test_get_returns_row(self):
        sid = _uid()
        repo = DeliveryRepository(DATABASE_URL)
        submitted_at = datetime.now(timezone.utc)
        try:
            _create_submission(sid)
            job_id = repo.create_job(
                submission_id=sid,
                to_email="gp@example.com",
                condition_label="Urinary Tract Infection",
                submitted_at=submitted_at,
            )
            row = repo.get(job_id)
            assert str(row["id"]) == job_id
            assert row["status"] == "pending"
        finally:
            _cleanup(sid)

    def test_get_raises_for_unknown_job(self):
        repo = DeliveryRepository(DATABASE_URL)
        raised = False
        try:
            repo.get(str(uuid4()))
        except DeliveryJobNotFound:
            raised = True
        assert raised, "Expected DeliveryJobNotFound was not raised"
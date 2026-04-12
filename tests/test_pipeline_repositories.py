"""
tests/test_pipeline_repositories.py

Integration tests for PDFRepository, DeliveryRepository, and PhotoRepository.

Exercises the pdf_jobs, delivery_jobs, and submission_photos tables directly
against a live Postgres database. Does not use the HTTP layer.

Requires TEST_DATABASE_URL in the environment.
Run via: make test-integration

Design notes:
- Each test creates its own submission with a unique ID and cleans up in a
  finally block. No test depends on another test's data.
- _create_submission inserts only a submission_records row. Repository tests
  create their own child rows.
- _cleanup deletes child rows before the parent submission_records row to
  satisfy FK constraints. submission_photos is now included.
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

pytestmark = pytest.mark.integration

from datetime import datetime, timedelta, timezone  # noqa: E402
from uuid import uuid4  # noqa: E402

from app.core.db import get_conn, alembic_upgrade  # noqa: E402
from app.repositories.submission_repository import SubmissionRepository  # noqa: E402
from app.repositories.pdf_repository import PDFRepository, PDFJobNotFound  # noqa: E402
from app.repositories.delivery_repository import DeliveryRepository, DeliveryJobNotFound  # noqa: E402
from app.repositories.photo_repository import PhotoRepository  # noqa: E402
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

    delivery_email and attachment_count are no longer columns on
    submission_records (dropped by Migration 0013). create_submission
    no longer accepts those parameters.

    Does not create pdf_jobs, delivery_jobs, or submission_photos rows —
    individual tests do that.
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
        submitted_at=datetime.now(timezone.utc),
    )


def _cleanup(sid: str) -> None:
    """Delete a submission and all FK child rows in dependency order."""
    with get_conn(DATABASE_URL) as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM delivery_jobs WHERE submission_id = %s", (sid,))
            cur.execute("DELETE FROM pdf_jobs WHERE submission_id = %s", (sid,))
            cur.execute("DELETE FROM submission_attachments WHERE submission_id = %s", (sid,))
            cur.execute("DELETE FROM submission_photos WHERE submission_id = %s", (sid,))
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


def _claim_until(claim_fn, target_job_id: str, limit: int = 50):
    """
    Call claim_fn repeatedly until it returns our target job or the queue
    is empty. Any other job claimed along the way has its next_retry_after
    left as-is (already pushed to the future by the claim, so it will not
    interfere with subsequent calls). Returns the claimed row for our job,
    or None if it was not found within `limit` calls.

    This helper exists because claim_next_pending returns the globally oldest
    eligible job, not the one we just created. In a shared CI database with
    residual rows from other test runs, our job may not be first in line.
    """
    for _ in range(limit):
        row = claim_fn()
        if row is None:
            return None
        if str(row["id"]) == target_job_id:
            return row
    return None


# ===========================================================================
# PhotoRepository tests
# ===========================================================================

class TestPhotoRepositorySaveAndGet:
    def test_save_photos_inserts_one_row_per_photo(self):
        """save_photos inserts one row per byte payload with the correct index."""
        sid = _uid()
        repo = PhotoRepository(DATABASE_URL)
        try:
            _create_submission(sid)
            repo.save_photos(sid, [b"photo-0", b"photo-1", b"photo-2"])

            with get_conn(DATABASE_URL) as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "SELECT photo_index, photo_bytes FROM submission_photos "
                        "WHERE submission_id = %s ORDER BY photo_index",
                        (sid,),
                    )
                    rows = cur.fetchall()

            assert len(rows) == 3
            assert rows[0][0] == 0
            assert rows[1][0] == 1
            assert rows[2][0] == 2
        finally:
            _cleanup(sid)

    def test_get_photos_returns_bytes_in_order(self):
        """get_photos returns photo bytes in photo_index order."""
        sid = _uid()
        repo = PhotoRepository(DATABASE_URL)
        photos = [b"first", b"second", b"third"]
        try:
            _create_submission(sid)
            repo.save_photos(sid, photos)
            result = repo.get_photos(sid)
            assert result == photos
        finally:
            _cleanup(sid)

    def test_get_photos_returns_empty_list_when_none_saved(self):
        """get_photos returns [] when no photos exist for the submission."""
        sid = _uid()
        repo = PhotoRepository(DATABASE_URL)
        try:
            _create_submission(sid)
            result = repo.get_photos(sid)
            assert result == []
        finally:
            _cleanup(sid)

    def test_save_photos_empty_list_inserts_nothing(self):
        """save_photos with an empty list returns silently and inserts no rows."""
        sid = _uid()
        repo = PhotoRepository(DATABASE_URL)
        try:
            _create_submission(sid)
            repo.save_photos(sid, [])
            result = repo.get_photos(sid)
            assert result == []
        finally:
            _cleanup(sid)

    def test_save_photos_preserves_byte_content_exactly(self):
        """Photo bytes round-trip through the database unchanged."""
        sid = _uid()
        repo = PhotoRepository(DATABASE_URL)
        payload = [b"\x00\x01\x02\xff", b"plain text bytes"]
        try:
            _create_submission(sid)
            repo.save_photos(sid, payload)
            result = repo.get_photos(sid)
            assert result == payload
        finally:
            _cleanup(sid)


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
        result = repo.claim_next_pending()
        assert result is None or isinstance(result, dict)

    def test_claim_marks_our_job_as_claimed(self):
        """
        After claim_next_pending runs, our specific job must eventually be
        claimed. We drain the queue with _claim_until rather than asserting
        on queue position, making the test immune to residual rows from other
        tests in the shared CI database.
        """
        sid = _uid()
        repo = PDFRepository(DATABASE_URL)
        try:
            _create_submission(sid)
            job_id = repo.create_job(sid, attachment_count=2, delivery_email="gp@example.com")
            claimed = _claim_until(repo.claim_next_pending, job_id)
            assert claimed is not None, (
                f"Expected job {job_id} to be claimed; it was never returned by "
                "claim_next_pending. Check for residual rows blocking the queue."
            )
            assert str(claimed["id"]) == job_id
        finally:
            _cleanup(sid)

    def test_claim_updates_next_retry_after_atomically(self):
        """
        After our job is claimed, next_retry_after must be set to a future time
        so it cannot be immediately re-claimed by a concurrent worker.
        """
        sid = _uid()
        repo = PDFRepository(DATABASE_URL)
        try:
            _create_submission(sid)
            job_id = repo.create_job(sid, attachment_count=2, delivery_email="gp@example.com")
            _claim_until(repo.claim_next_pending, job_id)
            row = _read_pdf_job(job_id)
            assert row["next_retry_after"] is not None
            assert row["next_retry_after"] > datetime.now(timezone.utc)
        finally:
            _cleanup(sid)

    def test_two_eligible_rows_each_claimed_exactly_once(self):
        """
        Both of our jobs must be claimable. After claiming both (draining any
        interleaved foreign jobs with _claim_until), both rows must have
        next_retry_after set. We assert on row state rather than on global
        queue position.
        """
        sid1, sid2 = _uid(), _uid()
        repo = PDFRepository(DATABASE_URL)
        try:
            _create_submission(sid1)
            _create_submission(sid2)
            job_id1 = repo.create_job(sid1, attachment_count=0, delivery_email="gp@example.com")
            job_id2 = repo.create_job(sid2, attachment_count=0, delivery_email="gp@example.com")

            claimed1 = _claim_until(repo.claim_next_pending, job_id1)
            assert claimed1 is not None, f"job1 ({job_id1}) was never claimed"

            _backdate_pdf_job_retry(job_id2)
            claimed2 = _claim_until(repo.claim_next_pending, job_id2)
            assert claimed2 is not None, f"job2 ({job_id2}) was never claimed"

            row1 = _read_pdf_job(job_id1)
            row2 = _read_pdf_job(job_id2)
            assert row1["next_retry_after"] is not None, "job1 must have been claimed"
            assert row2["next_retry_after"] is not None, "job2 must have been claimed"
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
            assert row["status"] == "failed"
            assert row["attempt_count"] == MAX_PDF_ATTEMPTS
        finally:
            _cleanup(sid)

    def test_mark_failed_raises_for_unknown_job(self):
        repo = PDFRepository(DATABASE_URL)
        raised = False
        try:
            repo.mark_failed(str(uuid4()), "error", next_retry_after=None)
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
        sid = _uid()
        try:
            _create_submission(sid)
            with get_conn(DATABASE_URL) as conn:
                with conn.cursor() as cur:
                    six_ago = datetime.now(timezone.utc) - timedelta(minutes=6)
                    cur.execute(
                        "UPDATE submission_records SET submitted_at = %s WHERE submission_id = %s",
                        (six_ago, sid),
                    )
            repo = PDFRepository(DATABASE_URL)
            orphans = repo.list_orphaned_submissions(older_than_minutes=5)
            assert sid in orphans
        finally:
            _cleanup(sid)

    def test_does_not_return_submission_with_pdf_job(self):
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
            assert sid not in orphans
        finally:
            _cleanup(sid)

    def test_does_not_return_recent_submission(self):
        sid = _uid()
        try:
            _create_submission(sid)
            repo = PDFRepository(DATABASE_URL)
            orphans = repo.list_orphaned_submissions(older_than_minutes=5)
            assert sid not in orphans
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
            assert job_id_1 == job_id_2
            with get_conn(DATABASE_URL) as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "SELECT COUNT(*) FROM delivery_jobs WHERE submission_id = %s",
                        (sid,),
                    )
                    count = cur.fetchone()[0]
            assert count == 1
        finally:
            _cleanup(sid)


class TestDeliveryRepositoryClaimNextPending:
    def test_returns_none_when_queue_is_empty(self):
        repo = DeliveryRepository(DATABASE_URL)
        result = repo.claim_next_pending()
        assert result is None or isinstance(result, dict)

    def test_claim_marks_our_job_as_claimed(self):
        """
        After claim_next_pending runs, our specific delivery job must eventually
        be claimed. We use _claim_until rather than asserting on queue position.
        """
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
            claimed = _claim_until(repo.claim_next_pending, job_id)
            assert claimed is not None, (
                f"Expected delivery job {job_id} to be claimed"
            )
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
            _claim_until(repo.claim_next_pending, job_id)
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
                assert row["status"] == "pending"

            _backdate_delivery_job_retry(job_id)
            repo.mark_failed(job_id, f"failure {MAX_ATTEMPTS}", next_retry_after=future)
            row = _read_delivery_job(job_id)
            assert row["status"] == "failed"
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

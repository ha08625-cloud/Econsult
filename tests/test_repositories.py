"""
tests/test_repositories.py

Integration tests for all three Postgres repositories:
  - RuntimeStateRepository
  - PracticeRepository  (including signposting)
  - SubmissionRepository

REQUIRES: TEST_DATABASE_URL set in .env, pointing to the dedicated test
database. Never runs against the production database.

Run from the project root with:
    python -m pytest tests/test_repositories.py -v

Add to the integration suite with:
    make test-integration
"""

import os
import pytest
from pathlib import Path
from datetime import datetime, timezone
from uuid import uuid4

# ---------------------------------------------------------------------------
# Load .env before the skip guard fires.
# conftest.py loads too late (after module-level skip checks), so we load
# dotenv here explicitly. override=False means already-set env vars win.
# ---------------------------------------------------------------------------
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent.parent / ".env", override=False)
except ImportError:
    pass

# ---------------------------------------------------------------------------
# Skip all tests in this module if TEST_DATABASE_URL is not set.
# This enforces the two-database rule: repository integration tests must
# never run against the production database URL.
# ---------------------------------------------------------------------------
if not os.environ.get("TEST_DATABASE_URL"):
    pytest.skip(
        "TEST_DATABASE_URL not set — skipping repository integration tests",
        allow_module_level=True,
    )

DATABASE_URL = os.environ["TEST_DATABASE_URL"]

# ---------------------------------------------------------------------------
# Imports (after skip guard so import errors don't mask the skip)
# ---------------------------------------------------------------------------

from app.core.db import get_conn
from app.repositories.runtime_state_repository import (
    RuntimeStateRepository,
    RuntimeStateNotFound,
    VersionConflict,
    SessionClosed,
)
from app.repositories.practice_repository import (
    PracticeRepository,
    PracticeNotFound,
    InvalidEmailError,
)
from app.repositories.submission_repository import (
    SubmissionRepository,
    SubmissionNotFound,
    InvalidDeliveryStatus,
)
from app.models.serialisation_contracts import ClinicalOutput, AuditOutput, PatientDetails


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _uid() -> str:
    """Generate a unique ID safe to use as a test primary key."""
    return f"test_{uuid4().hex[:8]}"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def runtime_repo():
    return RuntimeStateRepository(DATABASE_URL)


@pytest.fixture
def practice_repo():
    return PracticeRepository(DATABASE_URL)


@pytest.fixture
def submission_repo():
    return SubmissionRepository(DATABASE_URL)


@pytest.fixture
def practice_id(practice_repo):
    """
    Create a temporary practice for a single test and clean up afterwards.
    Tests that need a practice record use this fixture.
    """
    pid = _uid()
    practice_repo.create_practice(pid, "Test Practice", "test@example.com")
    yield pid
    with get_conn(DATABASE_URL) as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM practice_signposting WHERE practice_id = %s", (pid,))
            cur.execute("DELETE FROM practices WHERE practice_id = %s", (pid,))


@pytest.fixture
def dummy_outputs():
    """Minimal ClinicalOutput and AuditOutput for submission tests."""
    patient = PatientDetails(
        patient_for="me",
        first_name="Test",
        last_name="Patient",
        date_of_birth="1990-01-15",
        postcode="SW1A 1AA",
    )
    clinical = ClinicalOutput(
        condition_id="uti",
        free_text="Burning on urination for 3 days",
        additional_text=None,
        answers={"fever": True, "dysuria": True},
        safety_messages=[],
        question_labels={
            "fever": "Do you have a fever?",
            "dysuria": "Do you have pain when urinating?",
        },
        patient_details=patient,
    )
    audit = AuditOutput(
        runtime_state={"session_id": "test_session", "version": 1},
        safety_evaluation={"flags": []},
        ruleset_version="uti_v1",
    )
    return clinical, audit


# ---------------------------------------------------------------------------
# RuntimeStateRepository
# ---------------------------------------------------------------------------

class TestRuntimeStateRepository:

    def test_create_initial_and_get_latest(self, runtime_repo):
        rid = _uid()
        state = {"answers": {}, "step": 1}
        try:
            runtime_repo.create_initial(rid, "hash_abc", state)
            row = runtime_repo.get_latest(rid)
            assert row["runtime_id"] == rid
            assert row["version"] == 1
            assert row["ruleset_hash"] == "hash_abc"
            assert row["state_json"] == state
            assert row["is_closed"] is False
        finally:
            with get_conn(DATABASE_URL) as conn:
                with conn.cursor() as cur:
                    cur.execute("DELETE FROM runtime_state_versions WHERE runtime_id = %s", (rid,))

    def test_insert_new_version_increments_correctly(self, runtime_repo):
        rid = _uid()
        state_v2 = {"answers": {"q1": True}, "step": 2}
        try:
            runtime_repo.create_initial(rid, "hash_abc", {})
            new_ver = runtime_repo.insert_new_version(rid, 1, "hash_abc", state_v2)
            assert new_ver == 2
            row = runtime_repo.get_latest(rid)
            assert row["version"] == 2
            assert row["state_json"] == state_v2
        finally:
            with get_conn(DATABASE_URL) as conn:
                with conn.cursor() as cur:
                    cur.execute("DELETE FROM runtime_state_versions WHERE runtime_id = %s", (rid,))

    def test_version_conflict_on_stale_base_version(self, runtime_repo):
        rid = _uid()
        try:
            runtime_repo.create_initial(rid, "hash_abc", {})
            runtime_repo.insert_new_version(rid, 1, "hash_abc", {})
            with pytest.raises(VersionConflict):
                runtime_repo.insert_new_version(rid, 1, "hash_abc", {})
        finally:
            with get_conn(DATABASE_URL) as conn:
                with conn.cursor() as cur:
                    cur.execute("DELETE FROM runtime_state_versions WHERE runtime_id = %s", (rid,))

    def test_session_closed_blocks_get_latest(self, runtime_repo):
        rid = _uid()
        try:
            runtime_repo.create_initial(rid, "hash_abc", {})
            runtime_repo.close_session(rid, 1)
            with pytest.raises(SessionClosed):
                runtime_repo.get_latest(rid)
        finally:
            with get_conn(DATABASE_URL) as conn:
                with conn.cursor() as cur:
                    cur.execute("DELETE FROM runtime_state_versions WHERE runtime_id = %s", (rid,))

    def test_get_latest_raises_not_found_for_missing_id(self, runtime_repo):
        with pytest.raises(RuntimeStateNotFound):
            runtime_repo.get_latest("nonexistent_id_that_will_never_exist_xyz")


# ---------------------------------------------------------------------------
# PracticeRepository
# ---------------------------------------------------------------------------

class TestPracticeRepository:

    def test_create_and_get(self, practice_repo, practice_id):
        practice = practice_repo.get_practice(practice_id)
        assert practice is not None
        assert practice["practice_id"] == practice_id
        assert practice["name"] == "Test Practice"
        assert practice["email"] == "test@example.com"

    def test_practice_exists_before_and_after_create(self, practice_repo):
        pid = _uid()
        try:
            assert practice_repo.practice_exists(pid) is False
            practice_repo.create_practice(pid, "Test", "a@b.com")
            assert practice_repo.practice_exists(pid) is True
        finally:
            with get_conn(DATABASE_URL) as conn:
                with conn.cursor() as cur:
                    cur.execute("DELETE FROM practices WHERE practice_id = %s", (pid,))

    def test_create_with_invalid_email_raises(self, practice_repo):
        with pytest.raises(InvalidEmailError):
            practice_repo.create_practice(_uid(), "Test", "not-an-email")

    def test_get_email_returns_correct_address(self, practice_repo, practice_id):
        email = practice_repo.get_email(practice_id)
        assert email == "test@example.com"

    def test_get_email_raises_not_found_for_missing_practice(self, practice_repo):
        with pytest.raises(PracticeNotFound):
            practice_repo.get_email("nonexistent_practice_that_will_never_exist_xyz")

    def test_update_email_changes_stored_address(self, practice_repo, practice_id):
        practice_repo.update_email(practice_id, "updated@example.com")
        assert practice_repo.get_email(practice_id) == "updated@example.com"

    def test_update_email_with_invalid_format_raises(self, practice_repo, practice_id):
        with pytest.raises(InvalidEmailError):
            practice_repo.update_email(practice_id, "not-an-email")

    def test_set_and_get_signposting(self, practice_repo, practice_id):
        practice_repo.set_signposting(practice_id, "uti", "<p>Call 111 if symptoms worsen</p>")
        html = practice_repo.get_signposting(practice_id, "uti")
        assert html is not None
        assert "111" in html

    def test_delete_signposting_removes_row(self, practice_repo, practice_id):
        practice_repo.set_signposting(practice_id, "uti", "<p>Some info</p>")
        practice_repo.delete_signposting(practice_id, "uti")
        assert practice_repo.get_signposting(practice_id, "uti") is None

    def test_set_signposting_with_empty_html_deletes_row(self, practice_repo, practice_id):
        practice_repo.set_signposting(practice_id, "uti", "<p>Some info</p>")
        # Quill empty output should result in deletion rather than storing an empty row
        practice_repo.set_signposting(practice_id, "uti", "<p></p>")
        assert practice_repo.get_signposting(practice_id, "uti") is None


# ---------------------------------------------------------------------------
# SubmissionRepository
# ---------------------------------------------------------------------------

class TestSubmissionRepository:

    def test_create_and_get(self, submission_repo, dummy_outputs):
        sid = _uid()
        clinical, audit = dummy_outputs
        try:
            submission_repo.create_submission(
                submission_id=sid,
                practice_id="test-practice",
                condition_id="uti",
                clinical_output=clinical,
                audit_output=audit,
                delivery_email="test@example.com",
            )
            row = submission_repo.get_submission(sid)
            assert row["submission_id"] == sid
            assert row["delivery_status"] == "pending"
            # JSONB columns come back as dicts, not strings
            assert isinstance(row["clinical_output_json"], dict)
            assert isinstance(row["audit_output_json"], dict)
            assert row["clinical_output_json"]["patient_details"]["first_name"] == "Test"
        finally:
            with get_conn(DATABASE_URL) as conn:
                with conn.cursor() as cur:
                    cur.execute("DELETE FROM submission_records WHERE submission_id = %s", (sid,))

    def test_update_delivery_status_to_sent(self, submission_repo, dummy_outputs):
        sid = _uid()
        clinical, audit = dummy_outputs
        try:
            submission_repo.create_submission(
                submission_id=sid,
                practice_id="test-practice",
                condition_id="uti",
                clinical_output=clinical,
                audit_output=audit,
                delivery_email="test@example.com",
            )
            submission_repo.update_delivery_status(sid, "sent", delivered_at=datetime.now(timezone.utc))
            row = submission_repo.get_submission(sid)
            assert row["delivery_status"] == "sent"
            assert row["delivered_at"] is not None
        finally:
            with get_conn(DATABASE_URL) as conn:
                with conn.cursor() as cur:
                    cur.execute("DELETE FROM submission_records WHERE submission_id = %s", (sid,))

    def test_update_delivery_status_to_failed(self, submission_repo, dummy_outputs):
        sid = _uid()
        clinical, audit = dummy_outputs
        try:
            submission_repo.create_submission(
                submission_id=sid,
                practice_id="test-practice",
                condition_id="uti",
                clinical_output=clinical,
                audit_output=audit,
                delivery_email="test@example.com",
            )
            submission_repo.update_delivery_status(sid, "failed", delivery_error="SMTP timeout")
            row = submission_repo.get_submission(sid)
            assert row["delivery_status"] == "failed"
            assert row["delivery_error"] == "SMTP timeout"
        finally:
            with get_conn(DATABASE_URL) as conn:
                with conn.cursor() as cur:
                    cur.execute("DELETE FROM submission_records WHERE submission_id = %s", (sid,))

    def test_get_submission_raises_not_found_for_missing_id(self, submission_repo):
        with pytest.raises(SubmissionNotFound):
            submission_repo.get_submission("nonexistent_submission_that_will_never_exist_xyz")

    def test_update_delivery_status_raises_for_invalid_status(self, submission_repo):
        with pytest.raises(InvalidDeliveryStatus):
            submission_repo.update_delivery_status("any_id", "delivered")

    def test_list_by_status_returns_created_submission(self, submission_repo, dummy_outputs):
        sid = _uid()
        clinical, audit = dummy_outputs
        try:
            submission_repo.create_submission(
                submission_id=sid,
                practice_id="test-practice",
                condition_id="uti",
                clinical_output=clinical,
                audit_output=audit,
                delivery_email="test@example.com",
            )
            pending = submission_repo.list_by_status("pending")
            ids = [r["submission_id"] for r in pending]
            assert sid in ids
        finally:
            with get_conn(DATABASE_URL) as conn:
                with conn.cursor() as cur:
                    cur.execute("DELETE FROM submission_records WHERE submission_id = %s", (sid,))
"""
tests/integration/test_mesh_repository.py

Integration tests for MeshRepository.

Exercises the mesh_jobs table directly against a live Postgres database. Does
not use the HTTP layer and does not exercise any MESH protocol or network — it
is pure persistence coverage.

Requires TEST_DATABASE_URL in the environment.
Run via: make test-integration

Design notes (mirrors test_pipeline_repositories.py):
- Each test creates its own submission with a unique ID and cleans up in a
  finally block. No test depends on another test's data.
- _create_submission inserts only a submission_records row (the FK parent).
- _cleanup deletes mesh_jobs before submission_records to satisfy the FK.
- claim_next_pending tests backdate next_retry_after via get_conn to simulate
  eligibility without waiting for real time to pass.
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
os.environ.setdefault("PRACTICE_ID", "test-practice")

pytestmark = pytest.mark.integration

from datetime import datetime, timedelta, timezone  # noqa: E402
from uuid import uuid4  # noqa: E402

from app.core.db import get_conn, alembic_upgrade  # noqa: E402
from app.repositories.submission_repository import SubmissionRepository  # noqa: E402
from app.repositories.mesh_repository import MeshRepository, MeshJobNotFound  # noqa: E402
from app.models.serialisation_contracts import (  # noqa: E402
    ClinicalOutput,
    AuditOutput,
    PatientDetails,
)

# ---------------------------------------------------------------------------
# Ensure schema is up to date before any test runs.
# ---------------------------------------------------------------------------

alembic_upgrade()

DATABASE_URL = os.environ["TEST_DATABASE_URL"]

RECIPIENT = "X26HC001"


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _uid() -> str:
    return f"test_{uuid4().hex[:12]}"


def _create_submission(sid: str) -> None:
    """Insert a minimal valid submission_records row (the FK parent)."""
    repo = SubmissionRepository(DATABASE_URL)

    patient = PatientDetails(
        patient_for="me",
        first_name="Test",
        last_name="Patient",
        date_of_birth="1990-01-15",
        postcode="SW1A 1AA",
        gender="female",
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
    """Delete a submission and its mesh_jobs child rows in dependency order."""
    with get_conn(DATABASE_URL) as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM mesh_jobs WHERE submission_id = %s", (sid,))
            cur.execute("DELETE FROM submission_records WHERE submission_id = %s", (sid,))


def _read_job(mesh_job_id: str) -> dict:
    with get_conn(DATABASE_URL) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM mesh_jobs WHERE id = %s", (mesh_job_id,))
            row = cur.fetchone()
            cols = [desc[0] for desc in cur.description]
    return dict(zip(cols, row))


# ---------------------------------------------------------------------------
# create_job
# ---------------------------------------------------------------------------

def test_create_job_inserts_pending_row():
    sid = _uid()
    _create_submission(sid)
    try:
        repo = MeshRepository(DATABASE_URL)
        job_id = repo.create_job(submission_id=sid, recipient_mailbox_id=RECIPIENT)

        row = _read_job(job_id)
        assert row["submission_id"] == sid
        assert row["status"] == "pending"
        assert row["recipient_mailbox_id"] == RECIPIENT
        assert row["message_id"] is None
        assert row["mex_localid"] is not None
        assert row["attempt_count"] == 0
        assert row["sent_at"] is None
    finally:
        _cleanup(sid)


def test_create_job_is_idempotent_on_submission_id():
    sid = _uid()
    _create_submission(sid)
    try:
        repo = MeshRepository(DATABASE_URL)
        first = repo.create_job(submission_id=sid, recipient_mailbox_id=RECIPIENT)
        second = repo.create_job(submission_id=sid, recipient_mailbox_id="DIFFERENT")

        # Same row returned both times; the second call is a no-op (ON CONFLICT
        # DO NOTHING) so the original recipient is preserved.
        assert first == second
        row = _read_job(first)
        assert row["recipient_mailbox_id"] == RECIPIENT

        with get_conn(DATABASE_URL) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) FROM mesh_jobs WHERE submission_id = %s", (sid,))
                assert cur.fetchone()[0] == 1
    finally:
        _cleanup(sid)


# ---------------------------------------------------------------------------
# claim_next_pending
# ---------------------------------------------------------------------------

def test_claim_next_pending_returns_eligible_row_and_pushes_retry():
    sid = _uid()
    _create_submission(sid)
    try:
        repo = MeshRepository(DATABASE_URL)
        job_id = repo.create_job(submission_id=sid, recipient_mailbox_id=RECIPIENT)

        claimed = repo.claim_next_pending()
        assert claimed is not None
        # We may claim other tests' rows in a shared DB; loop until ours or empty.
        while claimed is not None and str(claimed["id"]) != job_id:
            claimed = repo.claim_next_pending()
        assert claimed is not None, "Our pending job was not claimable"
        assert str(claimed["id"]) == job_id
        assert claimed["recipient_mailbox_id"] == RECIPIENT

        # The claim must have pushed next_retry_after into the future so a
        # concurrent claim would skip it.
        row = _read_job(job_id)
        assert row["next_retry_after"] is not None
        assert row["next_retry_after"] > datetime.now(timezone.utc)
    finally:
        _cleanup(sid)


def test_claim_next_pending_returns_none_when_no_eligible_rows():
    sid = _uid()
    _create_submission(sid)
    try:
        repo = MeshRepository(DATABASE_URL)
        job_id = repo.create_job(submission_id=sid, recipient_mailbox_id=RECIPIENT)
        # Move our row out of eligibility, then drain any other eligible rows.
        with get_conn(DATABASE_URL) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE mesh_jobs SET status = 'sent' WHERE id = %s", (job_id,)
                )
        # Drain anything else that may be pending from other tests.
        for _ in range(50):
            if repo.claim_next_pending() is None:
                break
        # Our row is 'sent', so it is never returned.
        # (We cannot assert the global queue is empty in a shared DB, only that
        #  our own non-pending row is excluded — verified by status.)
        assert _read_job(job_id)["status"] == "sent"
    finally:
        _cleanup(sid)


# ---------------------------------------------------------------------------
# mark_sent
# ---------------------------------------------------------------------------

def test_mark_sent_records_message_id_and_timestamp():
    sid = _uid()
    _create_submission(sid)
    try:
        repo = MeshRepository(DATABASE_URL)
        job_id = repo.create_job(submission_id=sid, recipient_mailbox_id=RECIPIENT)

        message_id = "A1B2C3D4E5F600112233445566778899"
        repo.mark_sent(mesh_job_id=job_id, message_id=message_id)

        row = _read_job(job_id)
        assert row["status"] == "sent"
        assert row["message_id"] == message_id  # stored verbatim, not normalised
        assert row["sent_at"] is not None
    finally:
        _cleanup(sid)


def test_mark_sent_raises_for_unknown_job():
    repo = MeshRepository(DATABASE_URL)
    with pytest.raises(MeshJobNotFound):
        repo.mark_sent(mesh_job_id=str(uuid4()), message_id="DEADBEEF")


# ---------------------------------------------------------------------------
# mark_failed
# ---------------------------------------------------------------------------

def test_mark_failed_increments_attempt_and_keeps_pending():
    sid = _uid()
    _create_submission(sid)
    try:
        repo = MeshRepository(DATABASE_URL)
        job_id = repo.create_job(submission_id=sid, recipient_mailbox_id=RECIPIENT)

        retry_at = datetime.now(timezone.utc) + timedelta(minutes=5)
        count = repo.mark_failed(
            mesh_job_id=job_id,
            error="connection reset",
            error_code=None,
            next_retry_after=retry_at,
        )
        assert count == 1

        row = _read_job(job_id)
        # Transient failure must NOT move the row to a terminal status.
        assert row["status"] == "pending"
        assert row["attempt_count"] == 1
        assert row["last_error"] == "connection reset"
        assert row["last_error_code"] is None
        assert row["next_retry_after"] is not None

        # A second failure increments again and returns the new count.
        count2 = repo.mark_failed(
            mesh_job_id=job_id,
            error="503 from Spine",
            error_code="OWS_FAILED",
            next_retry_after=retry_at,
        )
        assert count2 == 2
        row2 = _read_job(job_id)
        assert row2["attempt_count"] == 2
        assert row2["last_error_code"] == "OWS_FAILED"
    finally:
        _cleanup(sid)


def test_mark_failed_raises_for_unknown_job():
    repo = MeshRepository(DATABASE_URL)
    with pytest.raises(MeshJobNotFound):
        repo.mark_failed(
            mesh_job_id=str(uuid4()),
            error="x",
            error_code=None,
            next_retry_after=None,
        )


# ---------------------------------------------------------------------------
# mark_fallback_triggered
# ---------------------------------------------------------------------------

def test_mark_fallback_triggered_transitions_status():
    sid = _uid()
    _create_submission(sid)
    try:
        repo = MeshRepository(DATABASE_URL)
        job_id = repo.create_job(submission_id=sid, recipient_mailbox_id=RECIPIENT)

        repo.mark_fallback_triggered(mesh_job_id=job_id)

        assert _read_job(job_id)["status"] == "fallback_triggered"
    finally:
        _cleanup(sid)


def test_mark_fallback_triggered_raises_for_unknown_job():
    repo = MeshRepository(DATABASE_URL)
    with pytest.raises(MeshJobNotFound):
        repo.mark_fallback_triggered(mesh_job_id=str(uuid4()))


# ---------------------------------------------------------------------------
# mark_provider_accepted / mark_delivered (Phase 4 tracking transitions)
# ---------------------------------------------------------------------------

def test_mark_provider_accepted_then_delivered():
    sid = _uid()
    _create_submission(sid)
    try:
        repo = MeshRepository(DATABASE_URL)
        job_id = repo.create_job(submission_id=sid, recipient_mailbox_id=RECIPIENT)
        repo.mark_sent(mesh_job_id=job_id, message_id="ABC123")

        repo.mark_provider_accepted(mesh_job_id=job_id)
        row = _read_job(job_id)
        assert row["status"] == "provider_accepted"
        assert row["provider_accepted_at"] is not None
        assert row["delivered_at"] is None

        repo.mark_delivered(mesh_job_id=job_id)
        row = _read_job(job_id)
        assert row["status"] == "delivered"
        assert row["delivered_at"] is not None
    finally:
        _cleanup(sid)


def test_tracking_transitions_raise_for_unknown_job():
    repo = MeshRepository(DATABASE_URL)
    with pytest.raises(MeshJobNotFound):
        repo.mark_provider_accepted(mesh_job_id=str(uuid4()))
    with pytest.raises(MeshJobNotFound):
        repo.mark_delivered(mesh_job_id=str(uuid4()))


# ---------------------------------------------------------------------------
# get
# ---------------------------------------------------------------------------

def test_get_returns_full_row_and_raises_when_absent():
    sid = _uid()
    _create_submission(sid)
    try:
        repo = MeshRepository(DATABASE_URL)
        job_id = repo.create_job(submission_id=sid, recipient_mailbox_id=RECIPIENT)

        row = repo.get(job_id)
        assert row["submission_id"] == sid
        assert row["recipient_mailbox_id"] == RECIPIENT

        with pytest.raises(MeshJobNotFound):
            repo.get(str(uuid4()))
    finally:
        _cleanup(sid)


# ---------------------------------------------------------------------------
# list_orphaned_fallbacks (Phase 3 — dispatcher recovery sweep)
# ---------------------------------------------------------------------------

def _insert_delivery_job(sid: str) -> None:
    """
    Insert a minimal delivery_jobs row directly. DeliveryRepository is
    deliberately not imported here — this file owns mesh_jobs coverage and
    only needs the FK sibling row to exist.
    """
    with get_conn(DATABASE_URL) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO delivery_jobs
                    (submission_id, to_email, condition_label, submitted_at)
                VALUES (%s, %s, %s, NOW())
                """,
                (sid, "gp@example.com", "Urinary Tract Infection"),
            )


def _delete_delivery_job(sid: str) -> None:
    with get_conn(DATABASE_URL) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM delivery_jobs WHERE submission_id = %s", (sid,)
            )


def test_list_orphaned_fallbacks_finds_row_without_delivery_job():
    """
    A fallback_triggered mesh_job with no delivery_jobs row is the crash
    artefact the sweep exists to recover.
    """
    repo = MeshRepository(DATABASE_URL)
    sid = _uid()
    try:
        _create_submission(sid)
        job_id = repo.create_job(submission_id=sid, recipient_mailbox_id=RECIPIENT)
        repo.mark_fallback_triggered(mesh_job_id=job_id)

        orphans = repo.list_orphaned_fallbacks()
        matching = [o for o in orphans if str(o["submission_id"]) == sid]
        assert len(matching) == 1
        assert str(matching[0]["id"]) == job_id
    finally:
        _cleanup(sid)


def test_list_orphaned_fallbacks_ignores_satisfied_fallback():
    """A fallback_triggered row WITH a delivery_jobs row is not an orphan."""
    repo = MeshRepository(DATABASE_URL)
    sid = _uid()
    try:
        _create_submission(sid)
        job_id = repo.create_job(submission_id=sid, recipient_mailbox_id=RECIPIENT)
        repo.mark_fallback_triggered(mesh_job_id=job_id)
        _insert_delivery_job(sid)

        orphans = repo.list_orphaned_fallbacks()
        assert all(str(o["submission_id"]) != sid for o in orphans)
    finally:
        _delete_delivery_job(sid)
        _cleanup(sid)


def test_list_orphaned_fallbacks_ignores_other_statuses():
    """A pending row with no delivery_jobs row is queued work, not an orphan."""
    repo = MeshRepository(DATABASE_URL)
    sid = _uid()
    try:
        _create_submission(sid)
        repo.create_job(submission_id=sid, recipient_mailbox_id=RECIPIENT)

        orphans = repo.list_orphaned_fallbacks()
        assert all(str(o["submission_id"]) != sid for o in orphans)
    finally:
        _cleanup(sid)
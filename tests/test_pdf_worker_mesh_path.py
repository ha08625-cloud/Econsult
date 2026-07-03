"""
tests/integration/test_pdf_worker_mesh_path.py

Integration test for the PDF worker on the MESH downstream path.

Proves that when the PDF worker is wired with a MeshEnqueuer (as
pdf_worker_main.py does for MESH_DELIVERY=1), processing a pdf_jobs row writes
a mesh_jobs row — not a delivery_jobs row — while preserving the worker's
ordering invariant (attachment saved, downstream enqueued, pdf_job marked done).

No dispatcher runs here; nothing consumes the mesh_jobs row. That is Phase 3.

This calls pdf_worker._process_job directly rather than the indefinite
run_worker loop, exercising the same ordering against a live database.

Requires TEST_DATABASE_URL in the environment.
Run via: make test-integration
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

from datetime import UTC, datetime  # noqa: E402
from uuid import uuid4  # noqa: E402

from app.core.db import alembic_upgrade, get_conn  # noqa: E402
from app.models.serialisation_contracts import (  # noqa: E402
    AuditOutput,
    ClinicalOutput,
    PatientDetails,
)
from app.repositories.attachment_repository import AttachmentRepository  # noqa: E402
from app.repositories.mesh_repository import MeshRepository  # noqa: E402
from app.repositories.pdf_repository import PDFRepository  # noqa: E402
from app.repositories.photo_repository import PhotoRepository  # noqa: E402
from app.repositories.submission_repository import SubmissionRepository  # noqa: E402
from app.services.delivery import pdf_worker  # noqa: E402
from app.services.delivery.mesh_enqueuer import MeshEnqueuer  # noqa: E402

alembic_upgrade()

DATABASE_URL = os.environ["TEST_DATABASE_URL"]

RECIPIENT = "X26HC042"


def _uid() -> str:
    return f"test_{uuid4().hex[:12]}"


def _create_submission(sid: str) -> None:
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
        submitted_at=datetime.now(UTC),
    )


def _cleanup(sid: str) -> None:
    with get_conn(DATABASE_URL) as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM mesh_jobs WHERE submission_id = %s", (sid,))
        cur.execute("DELETE FROM delivery_jobs WHERE submission_id = %s", (sid,))
        cur.execute("DELETE FROM pdf_jobs WHERE submission_id = %s", (sid,))
        cur.execute("DELETE FROM submission_attachments WHERE submission_id = %s", (sid,))
        cur.execute("DELETE FROM submission_photos WHERE submission_id = %s", (sid,))
        cur.execute("DELETE FROM submission_records WHERE submission_id = %s", (sid,))


def _read_pdf_job(job_id: str) -> dict:
    with get_conn(DATABASE_URL) as conn, conn.cursor() as cur:
        cur.execute("SELECT * FROM pdf_jobs WHERE id = %s", (job_id,))
        row = cur.fetchone()
        cols = [desc[0] for desc in cur.description]
    return dict(zip(cols, row, strict=True))


def _count(table: str, sid: str) -> int:
    with get_conn(DATABASE_URL) as conn, conn.cursor() as cur:
        cur.execute(f"SELECT COUNT(*) FROM {table} WHERE submission_id = %s", (sid,))
        return cur.fetchone()[0]


def test_pdf_worker_mesh_path_writes_mesh_job_not_delivery_job():
    sid = _uid()
    _create_submission(sid)
    try:
        pdf_repo = PDFRepository(DATABASE_URL)
        photo_repo = PhotoRepository(DATABASE_URL)
        submission_repo = SubmissionRepository(DATABASE_URL)
        attachment_repo = AttachmentRepository(DATABASE_URL)
        mesh_repo = MeshRepository(DATABASE_URL)

        # Zero attachments so no photos need saving; generate_pdf runs with no
        # embedded images and the defensive photo-count check passes (0 == 0).
        job_id = pdf_repo.create_job(
            submission_id=sid,
            attachment_count=0,
            delivery_email="gp@example.com",
        )
        job = _read_pdf_job(job_id)

        downstream = MeshEnqueuer(mesh_repo=mesh_repo, recipient_mailbox_id=RECIPIENT)

        pdf_worker._process_job(
            job=job,
            pdf_repo=pdf_repo,
            photo_repo=photo_repo,
            submission_repo=submission_repo,
            attachment_repo=attachment_repo,
            downstream=downstream,
            practice_name="Test Practice",
        )

        # A mesh_jobs row exists with the configured recipient and pending status.
        assert _count("mesh_jobs", sid) == 1
        with get_conn(DATABASE_URL) as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT status, recipient_mailbox_id FROM mesh_jobs WHERE submission_id = %s",
                (sid,),
            )
            status, recipient = cur.fetchone()
        assert status == "pending"
        assert recipient == RECIPIENT

        # The email path was NOT used.
        assert _count("delivery_jobs", sid) == 0

        # Ordering invariant held: attachment saved, pdf_job marked done.
        assert _count("submission_attachments", sid) == 1
        assert _read_pdf_job(job_id)["status"] == "done"
    finally:
        _cleanup(sid)


def test_pdf_worker_mesh_path_enqueue_is_idempotent_on_retry():
    """
    Re-processing the same job (simulating a crash after enqueue, before
    mark_done) must not create a second mesh_jobs row.
    """
    sid = _uid()
    _create_submission(sid)
    try:
        pdf_repo = PDFRepository(DATABASE_URL)
        photo_repo = PhotoRepository(DATABASE_URL)
        submission_repo = SubmissionRepository(DATABASE_URL)
        attachment_repo = AttachmentRepository(DATABASE_URL)
        mesh_repo = MeshRepository(DATABASE_URL)

        job_id = pdf_repo.create_job(
            submission_id=sid, attachment_count=0, delivery_email="gp@example.com"
        )
        job = _read_pdf_job(job_id)
        downstream = MeshEnqueuer(mesh_repo=mesh_repo, recipient_mailbox_id=RECIPIENT)

        pdf_worker._process_job(
            job=job,
            pdf_repo=pdf_repo,
            photo_repo=photo_repo,
            submission_repo=submission_repo,
            attachment_repo=attachment_repo,
            downstream=downstream,
            practice_name=None,
        )
        # Process the same job row again (idempotent UPSERT + ON CONFLICT).
        pdf_worker._process_job(
            job=job,
            pdf_repo=pdf_repo,
            photo_repo=photo_repo,
            submission_repo=submission_repo,
            attachment_repo=attachment_repo,
            downstream=downstream,
            practice_name=None,
        )

        assert _count("mesh_jobs", sid) == 1
    finally:
        _cleanup(sid)

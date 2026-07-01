"""
tests/integration/test_mesh_worker_db.py

DB-backed integration tests for the MESH dispatcher's fallback path and
orphaned-fallback recovery sweep. The MeshClient is mocked (no network, no
sandbox) — the point here is that the real repositories, against a real
Postgres, produce the correct cross-table state. Sandbox coverage of the
happy send path lives in tests/integration/test_mesh_worker_sandbox.py.

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
from unittest.mock import MagicMock  # noqa: E402
from uuid import uuid4  # noqa: E402

from app.core.db import alembic_upgrade, get_conn  # noqa: E402
from app.models.serialisation_contracts import (  # noqa: E402
    AuditOutput,
    ClinicalOutput,
    PatientDetails,
)
from app.repositories.attachment_repository import AttachmentRepository  # noqa: E402
from app.repositories.delivery_repository import DeliveryRepository  # noqa: E402
from app.repositories.mesh_repository import MeshRepository  # noqa: E402
from app.repositories.pdf_repository import PDFRepository  # noqa: E402
from app.repositories.submission_repository import SubmissionRepository  # noqa: E402
from app.services.delivery.mesh import MeshTerminalError  # noqa: E402
from app.services.delivery.mesh_payload import RawPdfPayloadBuilder  # noqa: E402
from app.services.delivery.mesh_worker import (  # noqa: E402
    _process_job,
    _recover_orphaned_fallbacks,
)

alembic_upgrade()

DATABASE_URL = os.environ["TEST_DATABASE_URL"]

RECIPIENT = "X26HC001"
DELIVERY_EMAIL = "gp@example.com"
PDF_BYTES = b"%PDF-1.7 dispatcher integration test"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _uid() -> str:
    return f"test_{uuid4().hex[:12]}"


def _create_submission_with_pdf_artifacts(sid: str) -> None:
    """
    Insert the full FK lineage the dispatcher reads: a submission_records
    row, a pdf_jobs row (delivery_email source), and the PDF attachment.
    """
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
    SubmissionRepository(DATABASE_URL).create_submission(
        submission_id=sid,
        practice_id="test-practice",
        condition_id="uti",
        condition_label="Urinary Tract Infection",
        clinical_output=clinical,
        audit_output=audit,
        submitted_at=datetime.now(UTC),
    )
    PDFRepository(DATABASE_URL).create_job(
        submission_id=sid,
        attachment_count=0,
        delivery_email=DELIVERY_EMAIL,
    )
    AttachmentRepository(DATABASE_URL).save_attachment(sid, PDF_BYTES)


def _cleanup(sid: str) -> None:
    """Delete all FK child rows before the parent submission_records row."""
    with get_conn(DATABASE_URL) as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM delivery_jobs WHERE submission_id = %s", (sid,))
        cur.execute("DELETE FROM mesh_jobs WHERE submission_id = %s", (sid,))
        cur.execute("DELETE FROM pdf_jobs WHERE submission_id = %s", (sid,))
        cur.execute("DELETE FROM submission_attachments WHERE submission_id = %s", (sid,))
        cur.execute("DELETE FROM submission_records WHERE submission_id = %s", (sid,))


def _read_delivery_job(sid: str) -> dict:
    with get_conn(DATABASE_URL) as conn, conn.cursor() as cur:
        cur.execute("SELECT * FROM delivery_jobs WHERE submission_id = %s", (sid,))
        row = cur.fetchone()
        assert row is not None, f"expected a delivery_jobs row for {sid}"
        cols = [desc[0] for desc in cur.description]
    return dict(zip(cols, row))


# ---------------------------------------------------------------------------
# Terminal failure -> fallback delivery_jobs row
# ---------------------------------------------------------------------------


def test_terminal_failure_creates_fallback_delivery_job_with_real_metadata():
    """
    End-to-end across real tables: a terminal MESH failure must leave the
    mesh_job in fallback_triggered and create a delivery_jobs row with
    is_fallback=TRUE whose denormalised fields come from pdf_jobs
    (to_email) and submission_records (condition_label, submitted_at).
    """
    sid = _uid()
    mesh_repo = MeshRepository(DATABASE_URL)
    try:
        _create_submission_with_pdf_artifacts(sid)
        mesh_repo.create_job(submission_id=sid, recipient_mailbox_id=RECIPIENT)
        job = mesh_repo.claim_next_pending()
        # SKIP LOCKED claim can race with other test rows; claim until ours.
        attempts = 0
        while job is not None and str(job["submission_id"]) != sid and attempts < 50:
            job = mesh_repo.claim_next_pending()
            attempts += 1
        assert job is not None and str(job["submission_id"]) == sid

        failing_client = MagicMock()
        failing_client.send_message.side_effect = MeshTerminalError("417 unregistered recipient")

        _process_job(
            job=job,
            mesh_repo=mesh_repo,
            attachment_repo=AttachmentRepository(DATABASE_URL),
            pdf_repo=PDFRepository(DATABASE_URL),
            submission_repo=SubmissionRepository(DATABASE_URL),
            delivery_repo=DeliveryRepository(DATABASE_URL),
            mesh_client=failing_client,
            payload_builder=RawPdfPayloadBuilder(),
            workflow_id="TEST_WORKFLOW",
        )

        mesh_row = mesh_repo.get(str(job["id"]))
        assert mesh_row["status"] == "fallback_triggered"

        delivery_row = _read_delivery_job(sid)
        assert delivery_row["is_fallback"] is True
        assert delivery_row["status"] == "pending"
        assert delivery_row["to_email"] == DELIVERY_EMAIL
        assert delivery_row["condition_label"] == "Urinary Tract Infection"
        assert delivery_row["submitted_at"] is not None
    finally:
        _cleanup(sid)


# ---------------------------------------------------------------------------
# Orphaned-fallback recovery sweep
# ---------------------------------------------------------------------------


def test_sweep_recovers_manufactured_orphan():
    """
    Manufacture the crash artefact (fallback_triggered with no
    delivery_jobs row) and assert one sweep pass repairs it.
    """
    sid = _uid()
    mesh_repo = MeshRepository(DATABASE_URL)
    try:
        _create_submission_with_pdf_artifacts(sid)
        job_id = mesh_repo.create_job(submission_id=sid, recipient_mailbox_id=RECIPIENT)
        mesh_repo.mark_fallback_triggered(mesh_job_id=job_id)

        _recover_orphaned_fallbacks(
            mesh_repo=mesh_repo,
            pdf_repo=PDFRepository(DATABASE_URL),
            submission_repo=SubmissionRepository(DATABASE_URL),
            delivery_repo=DeliveryRepository(DATABASE_URL),
        )

        delivery_row = _read_delivery_job(sid)
        assert delivery_row["is_fallback"] is True
        assert delivery_row["to_email"] == DELIVERY_EMAIL

        # The orphan is now satisfied: a second sweep must be a no-op
        # (idempotent create_job; no duplicate rows possible under the
        # UNIQUE constraint, and the orphan query no longer matches).
        _recover_orphaned_fallbacks(
            mesh_repo=mesh_repo,
            pdf_repo=PDFRepository(DATABASE_URL),
            submission_repo=SubmissionRepository(DATABASE_URL),
            delivery_repo=DeliveryRepository(DATABASE_URL),
        )
        with get_conn(DATABASE_URL) as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT COUNT(*) FROM delivery_jobs WHERE submission_id = %s",
                (sid,),
            )
            assert cur.fetchone()[0] == 1
    finally:
        _cleanup(sid)

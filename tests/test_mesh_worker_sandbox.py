"""
tests/integration/test_mesh_worker_sandbox.py

HYBRID integration test: real Postgres AND the local MESH sandbox (behind
its nginx mTLS proxy). This is the dispatch-tick proof: a real mesh_jobs
row, the real MeshClient, and the real repositories, end to end.

This file is the first member of the hybrid test category documented in
docs/arch_testing.md: it carries the `integration` marker, the
TEST_DATABASE_URL guardrail (it writes to Postgres), AND the MESH_BASE_URL
module-level skip (it talks to the sandbox). The remaining MESH env vars
are read with direct subscripts so a half-configured .env.sandbox fails
loudly — the same convention as tests/test_mesh_client_integration.py.

NOTE: this file requires MESH_WORKFLOW_ID in .env.sandbox (new in Phase 3).
A KeyError here means the sandbox env file needs updating.

Run via: make test-integration (with the sandbox up: make sandbox-up)
"""

import os

import pytest

# ---------------------------------------------------------------------------
# Guardrail 1: database — must be first, before any app imports.
# ---------------------------------------------------------------------------

if "TEST_DATABASE_URL" not in os.environ:
    pytest.skip(
        "TEST_DATABASE_URL not set — skipping integration tests to protect production data",
        allow_module_level=True,
    )

os.environ.setdefault("DATABASE_URL", os.environ["TEST_DATABASE_URL"])
os.environ.setdefault("PRACTICE_ID", "test-practice")

# ---------------------------------------------------------------------------
# Guardrail 2: sandbox availability.
# ---------------------------------------------------------------------------

if "MESH_BASE_URL" not in os.environ:
    pytest.skip(
        "MESH_BASE_URL not set — skipping MESH sandbox integration tests",
        allow_module_level=True,
    )

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
from app.repositories.delivery_repository import DeliveryRepository  # noqa: E402
from app.repositories.mesh_repository import MeshRepository  # noqa: E402
from app.repositories.pdf_repository import PDFRepository  # noqa: E402
from app.repositories.submission_repository import SubmissionRepository  # noqa: E402
from app.services.delivery.mesh import MeshClient  # noqa: E402
from app.services.delivery.mesh_payload import RawPdfPayloadBuilder  # noqa: E402
from app.services.delivery.mesh_worker import _process_job  # noqa: E402

alembic_upgrade()

DATABASE_URL = os.environ["TEST_DATABASE_URL"]

# Direct subscripts: a half-configured .env.sandbox must fail loudly.
_BASE_URL = os.environ["MESH_BASE_URL"]
_MAILBOX_ID = os.environ["MESH_MAILBOX_ID"]
_MAILBOX_PASSWORD = os.environ["MESH_MAILBOX_PASSWORD"]
_SHARED_KEY = os.environ["MESH_SHARED_KEY"]
_CA_CERT_PATH = os.environ["MESH_CA_CERT_PATH"]
_CLIENT_CERT_PATH = os.environ["MESH_CLIENT_CERT_PATH"]
_CLIENT_KEY_PATH = os.environ["MESH_CLIENT_KEY_PATH"]
_WORKFLOW_ID = os.environ["MESH_WORKFLOW_ID"]

# Pre-provisioned sandbox recipient — see sandbox/mailboxes.jsonl.
_RECIPIENT_MAILBOX_ID = "TARGET_MAILBOX"

PDF_BYTES = b"%PDF-1.7 sandbox dispatch-tick test"


def _uid() -> str:
    return f"test_{uuid4().hex[:12]}"


def _make_client() -> MeshClient:
    return MeshClient(
        base_url=_BASE_URL,
        mailbox_id=_MAILBOX_ID,
        mailbox_password=_MAILBOX_PASSWORD,
        shared_key=_SHARED_KEY,
        ca_cert_path=_CA_CERT_PATH,
        client_cert_path=_CLIENT_CERT_PATH,
        client_key_path=_CLIENT_KEY_PATH,
    )


def _create_submission_with_pdf_artifacts(sid: str) -> None:
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
        delivery_email="gp@example.com",
    )
    AttachmentRepository(DATABASE_URL).save_attachment(sid, PDF_BYTES)


def _cleanup(sid: str) -> None:
    with get_conn(DATABASE_URL) as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM delivery_jobs WHERE submission_id = %s", (sid,))
        cur.execute("DELETE FROM mesh_jobs WHERE submission_id = %s", (sid,))
        cur.execute("DELETE FROM pdf_jobs WHERE submission_id = %s", (sid,))
        cur.execute("DELETE FROM submission_attachments WHERE submission_id = %s", (sid,))
        cur.execute("DELETE FROM submission_records WHERE submission_id = %s", (sid,))


def test_dispatch_tick_sends_to_sandbox_and_marks_sent():
    """
    The full dispatch tick: enqueue a real mesh_jobs row (stamped with the
    sandbox recipient), claim it, process it with the real MeshClient
    against the sandbox, and assert the row transitions to 'sent' with the
    MESH messageID stored verbatim (32-char hex, never normalised — see
    MeshClient.send_message docstring).
    """
    sid = _uid()
    mesh_repo = MeshRepository(DATABASE_URL)
    client = _make_client()
    client.handshake()

    try:
        _create_submission_with_pdf_artifacts(sid)
        mesh_repo.create_job(submission_id=sid, recipient_mailbox_id=_RECIPIENT_MAILBOX_ID)
        job = mesh_repo.claim_next_pending()
        attempts = 0
        while job is not None and str(job["submission_id"]) != sid and attempts < 50:
            job = mesh_repo.claim_next_pending()
            attempts += 1
        assert job is not None and str(job["submission_id"]) == sid

        _process_job(
            job=job,
            mesh_repo=mesh_repo,
            attachment_repo=AttachmentRepository(DATABASE_URL),
            pdf_repo=PDFRepository(DATABASE_URL),
            submission_repo=SubmissionRepository(DATABASE_URL),
            delivery_repo=DeliveryRepository(DATABASE_URL),
            mesh_client=client,
            payload_builder=RawPdfPayloadBuilder(),
            workflow_id=_WORKFLOW_ID,
        )

        row = mesh_repo.get(str(job["id"]))
        assert row["status"] == "sent"
        assert row["sent_at"] is not None
        message_id = row["message_id"]
        assert isinstance(message_id, str)
        assert len(message_id) == 32
        # Stored verbatim: hex characters only, no hyphens, case preserved.
        assert all(c in "0123456789ABCDEFabcdef" for c in message_id)
        assert "-" not in message_id

        # The send must not have touched the email path.
        with get_conn(DATABASE_URL) as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT COUNT(*) FROM delivery_jobs WHERE submission_id = %s",
                (sid,),
            )
            assert cur.fetchone()[0] == 0
    finally:
        _cleanup(sid)

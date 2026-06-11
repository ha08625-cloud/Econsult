"""
tests/test_repositories.py

Integration tests for RuntimeStateRepository, PracticeRepository,
SubmissionRepository, and AttachmentRepository.

Requires TEST_DATABASE_URL in the environment.
Run via: make test-integration

Each test generates a unique ID and cleans up its own rows in a finally
block. No test depends on another test's data.
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

from uuid import uuid4  # noqa: E402
from datetime import datetime, timezone  # noqa: E402

from app.core.db import get_conn  # noqa: E402
from app.repositories.runtime_state_repository import (  # noqa: E402
    RuntimeStateRepository,
    RuntimeStateNotFound,
    VersionConflict,
    SessionClosed,
)
from app.repositories.practice_repository import (  # noqa: E402
    PracticeRepository,
    PracticeNotFound,
    InvalidEmailError,
    InvalidSignpostingData,
    InvalidDoctorListError,
)
from app.repositories.submission_repository import (  # noqa: E402
    SubmissionRepository,
    SubmissionNotFound,
)
from app.repositories.attachment_repository import (  # noqa: E402
    AttachmentRepository,
    AttachmentNotFound,
)
from app.models.serialisation_contracts import ClinicalOutput, AuditOutput, PatientDetails  # noqa: E402

DATABASE_URL = os.environ["TEST_DATABASE_URL"]


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _uid() -> str:
    return f"test_{uuid4().hex[:8]}"


# ---------------------------------------------------------------------------
# RuntimeStateRepository
# ---------------------------------------------------------------------------

def _make_state_repo() -> RuntimeStateRepository:
    return RuntimeStateRepository(DATABASE_URL)


def _cleanup_runtime(rid: str) -> None:
    with get_conn(DATABASE_URL) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM runtime_state_versions WHERE runtime_id = %s", (rid,)
            )


def test_runtime_create_and_get():
    repo = _make_state_repo()
    rid = _uid()
    state = {"answers": {}, "step": 1}

    try:
        repo.create_initial(rid, "hash_abc", state)
        row = repo.get_latest(rid)
        assert row["runtime_id"] == rid
        assert row["version"] == 1
        assert row["ruleset_hash"] == "hash_abc"
        assert row["state_json"] == state
        assert row["is_closed"] is False
    finally:
        _cleanup_runtime(rid)


def test_runtime_insert_new_version():
    repo = _make_state_repo()
    rid = _uid()
    state_v2 = {"answers": {"q1": True}, "step": 2}

    try:
        repo.create_initial(rid, "hash_abc", {})
        new_ver = repo.insert_new_version(rid, 1, "hash_abc", state_v2)
        assert new_ver == 2
        row = repo.get_latest(rid)
        assert row["version"] == 2
        assert row["state_json"] == state_v2
    finally:
        _cleanup_runtime(rid)


def test_runtime_version_conflict():
    repo = _make_state_repo()
    rid = _uid()

    try:
        repo.create_initial(rid, "hash_abc", {})
        repo.insert_new_version(rid, 1, "hash_abc", {})
        with pytest.raises(VersionConflict):
            repo.insert_new_version(rid, 1, "hash_abc", {})
    finally:
        _cleanup_runtime(rid)


def test_runtime_session_closed():
    repo = _make_state_repo()
    rid = _uid()

    try:
        repo.create_initial(rid, "hash_abc", {})
        repo.close_session(rid, 1)
        with pytest.raises(SessionClosed):
            repo.get_latest(rid)
    finally:
        _cleanup_runtime(rid)


def test_runtime_not_found():
    repo = _make_state_repo()
    with pytest.raises(RuntimeStateNotFound):
        repo.get_latest("nonexistent_id_that_will_never_exist_xyz")


# ---------------------------------------------------------------------------
# PracticeRepository
# ---------------------------------------------------------------------------

def _make_practice_repo() -> PracticeRepository:
    return PracticeRepository(DATABASE_URL)


def _cleanup_practice(pid: str) -> None:
    with get_conn(DATABASE_URL) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM practice_doctors WHERE practice_id = %s", (pid,)
            )
            cur.execute(
                "DELETE FROM practice_signposting WHERE practice_id = %s", (pid,)
            )
            cur.execute("DELETE FROM practices WHERE practice_id = %s", (pid,))


def test_practice_create_and_get():
    repo = _make_practice_repo()
    pid = _uid()

    try:
        repo.create_practice(pid, "Test Practice", "test@example.com")
        practice = repo.get_practice(pid)
        assert practice is not None
        assert practice["practice_id"] == pid
        assert practice["name"] == "Test Practice"
        assert practice["email"] == "test@example.com"
    finally:
        _cleanup_practice(pid)


def test_practice_exists():
    repo = _make_practice_repo()
    pid = _uid()

    try:
        assert repo.practice_exists(pid) is False
        repo.create_practice(pid, "Test", "a@b.com")
        assert repo.practice_exists(pid) is True
    finally:
        _cleanup_practice(pid)


def test_practice_invalid_email():
    repo = _make_practice_repo()
    with pytest.raises(InvalidEmailError):
        repo.create_practice(_uid(), "Test", "not-an-email")


def test_practice_get_email():
    repo = _make_practice_repo()
    pid = _uid()

    try:
        repo.create_practice(pid, "Test", "addr@example.com")
        assert repo.get_email(pid) == "addr@example.com"
    finally:
        _cleanup_practice(pid)


def test_practice_not_found():
    repo = _make_practice_repo()
    with pytest.raises(PracticeNotFound):
        repo.get_email("nonexistent_practice_that_will_never_exist_xyz")


def test_practice_update_email():
    repo = _make_practice_repo()
    pid = _uid()

    try:
        repo.create_practice(pid, "Test", "original@example.com")
        repo.update_email(pid, "updated@example.com")
        assert repo.get_email(pid) == "updated@example.com"
    finally:
        _cleanup_practice(pid)


def test_practice_update_email_invalid_format():
    repo = _make_practice_repo()
    pid = _uid()

    try:
        repo.create_practice(pid, "Test", "valid@example.com")
        with pytest.raises(InvalidEmailError):
            repo.update_email(pid, "not-an-email")
    finally:
        _cleanup_practice(pid)


def test_signposting_set_and_get():
    repo = _make_practice_repo()
    pid = _uid()

    try:
        repo.create_practice(pid, "Test", "a@b.com")
        repo.set_signposting(pid, "uti", "<p>Call 111 if symptoms worsen</p>")
        html = repo.get_signposting(pid, "uti")
        assert html is not None
        assert "111" in html
    finally:
        _cleanup_practice(pid)


def test_signposting_delete():
    repo = _make_practice_repo()
    pid = _uid()

    try:
        repo.create_practice(pid, "Test", "a@b.com")
        repo.set_signposting(pid, "uti", "<p>Some info</p>")
        repo.delete_signposting(pid, "uti")
        assert repo.get_signposting(pid, "uti") is None
    finally:
        _cleanup_practice(pid)


def test_signposting_empty_html_deletes_row():
    repo = _make_practice_repo()
    pid = _uid()

    try:
        repo.create_practice(pid, "Test", "a@b.com")
        repo.set_signposting(pid, "uti", "<p>Some info</p>")
        repo.set_signposting(pid, "uti", "<p></p>")
        assert repo.get_signposting(pid, "uti") is None
    finally:
        _cleanup_practice(pid)


# ---------------------------------------------------------------------------
# PracticeRepository — doctor list
# ---------------------------------------------------------------------------

def test_doctors_get_returns_empty_list_when_none_configured():
    repo = _make_practice_repo()
    pid = _uid()

    try:
        repo.create_practice(pid, "Test", "a@b.com")
        assert repo.get_doctors(pid) == []
    finally:
        _cleanup_practice(pid)


def test_doctors_set_and_get_round_trip():
    repo = _make_practice_repo()
    pid = _uid()
    names = ["Dr Smith", "Dr Jones", "Dr Patel"]

    try:
        repo.create_practice(pid, "Test", "a@b.com")
        repo.set_doctors(pid, names)
        assert repo.get_doctors(pid) == names
    finally:
        _cleanup_practice(pid)


def test_doctors_set_replaces_existing_list():
    repo = _make_practice_repo()
    pid = _uid()

    try:
        repo.create_practice(pid, "Test", "a@b.com")
        repo.set_doctors(pid, ["Dr Smith", "Dr Jones"])
        repo.set_doctors(pid, ["Dr Brown"])
        assert repo.get_doctors(pid) == ["Dr Brown"]
    finally:
        _cleanup_practice(pid)


def test_doctors_set_empty_list_clears_doctors():
    repo = _make_practice_repo()
    pid = _uid()

    try:
        repo.create_practice(pid, "Test", "a@b.com")
        repo.set_doctors(pid, ["Dr Smith", "Dr Jones"])
        repo.set_doctors(pid, [])
        assert repo.get_doctors(pid) == []
    finally:
        _cleanup_practice(pid)


def test_doctors_order_is_preserved():
    repo = _make_practice_repo()
    pid = _uid()
    # Deliberately non-alphabetical to confirm ordering is by display_order,
    # not alphabetical sort.
    names = ["Dr Zebra", "Dr Apple", "Dr Mango"]

    try:
        repo.create_practice(pid, "Test", "a@b.com")
        repo.set_doctors(pid, names)
        assert repo.get_doctors(pid) == names
    finally:
        _cleanup_practice(pid)


def test_doctors_set_raises_for_missing_practice():
    repo = _make_practice_repo()
    with pytest.raises(PracticeNotFound):
        repo.set_doctors("nonexistent_practice_that_will_never_exist_xyz", ["Dr Smith"])


def test_doctors_set_raises_for_empty_name():
    repo = _make_practice_repo()
    pid = _uid()

    try:
        repo.create_practice(pid, "Test", "a@b.com")
        with pytest.raises(InvalidDoctorListError):
            repo.set_doctors(pid, ["Dr Smith", "  ", "Dr Jones"])
    finally:
        _cleanup_practice(pid)


def test_doctors_set_raises_for_name_too_long():
    repo = _make_practice_repo()
    pid = _uid()

    try:
        repo.create_practice(pid, "Test", "a@b.com")
        long_name = "Dr " + "A" * 100  # 103 chars, over limit of 100
        with pytest.raises(InvalidDoctorListError):
            repo.set_doctors(pid, [long_name])
    finally:
        _cleanup_practice(pid)


def test_doctors_set_raises_for_list_too_long():
    repo = _make_practice_repo()
    pid = _uid()

    try:
        repo.create_practice(pid, "Test", "a@b.com")
        too_many = [f"Dr Doctor{i}" for i in range(51)]  # 51 items, over limit of 50
        with pytest.raises(InvalidDoctorListError):
            repo.set_doctors(pid, too_many)
    finally:
        _cleanup_practice(pid)


# ---------------------------------------------------------------------------
# SubmissionRepository
# ---------------------------------------------------------------------------

def _make_submission_repo() -> SubmissionRepository:
    return SubmissionRepository(DATABASE_URL)


def _make_dummy_patient_details() -> PatientDetails:
    return PatientDetails(
        patient_for="me",
        first_name="Test",
        last_name="Patient",
        gender="Female",
        date_of_birth="1990-01-15",
        postcode="SW1A 1AA",
    )


def _make_dummy_outputs():
    clinical = ClinicalOutput(
        condition_id="uti",
        free_text="I have had burning on urination for 3 days",
        additional_text=None,
        answers={"fever": True, "dysuria": True},
        safety_messages=[],
        question_labels={
            "fever": "Do you have a fever?",
            "dysuria": "Do you have pain when urinating?",
        },
        patient_details=_make_dummy_patient_details(),
    )
    audit = AuditOutput(
        runtime_state={"session_id": "test_session", "version": 1},
        safety_evaluation={"flags": []},
        ruleset_version="uti_v1",
    )
    return clinical, audit


def _cleanup_submission(sid: str) -> None:
    with get_conn(DATABASE_URL) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM delivery_jobs WHERE submission_id = %s", (sid,)
            )
            cur.execute(
                "DELETE FROM pdf_jobs WHERE submission_id = %s", (sid,)
            )
            cur.execute(
                "DELETE FROM submission_attachments WHERE submission_id = %s", (sid,)
            )
            cur.execute(
                "DELETE FROM submission_records WHERE submission_id = %s", (sid,)
            )


def _create_test_submission(repo: SubmissionRepository, sid: str) -> None:
    clinical, audit = _make_dummy_outputs()
    repo.create_submission(
        submission_id=sid,
        practice_id="test-practice",
        condition_id="uti",
        condition_label="Urinary Tract Infection",
        clinical_output=clinical,
        audit_output=audit,
        submitted_at=datetime.now(timezone.utc),
    )


def test_submission_create_and_get():
    repo = _make_submission_repo()
    sid = _uid()

    try:
        _create_test_submission(repo, sid)
        row = repo.get_submission(sid)
        assert row["submission_id"] == sid
        assert row["condition_id"] == "uti"
        assert row["condition_label"] == "Urinary Tract Infection"
        # JSONB columns come back as dicts, not strings
        assert isinstance(row["clinical_output_json"], dict)
        assert isinstance(row["audit_output_json"], dict)
        assert row["clinical_output_json"]["patient_details"]["first_name"] == "Test"
    finally:
        _cleanup_submission(sid)


def test_submission_not_found():
    repo = _make_submission_repo()
    with pytest.raises(SubmissionNotFound):
        repo.get_submission("nonexistent_submission_that_will_never_exist_xyz")


# ---------------------------------------------------------------------------
# AttachmentRepository
# ---------------------------------------------------------------------------

def _make_attachment_repo() -> AttachmentRepository:
    return AttachmentRepository(DATABASE_URL)


_DUMMY_PDF_BYTES = b"%PDF-1.4 fake pdf content for testing"


def test_attachment_save_and_get():
    sub_repo = _make_submission_repo()
    att_repo = _make_attachment_repo()
    sid = _uid()

    try:
        _create_test_submission(sub_repo, sid)
        att_repo.save_attachment(sid, _DUMMY_PDF_BYTES)
        assert att_repo.get_attachment(sid) == _DUMMY_PDF_BYTES
    finally:
        _cleanup_submission(sid)


def test_attachment_get_missing_raises():
    att_repo = _make_attachment_repo()
    with pytest.raises(AttachmentNotFound):
        att_repo.get_attachment("nonexistent_submission_that_will_never_exist_xyz")


def test_attachment_delete():
    sub_repo = _make_submission_repo()
    att_repo = _make_attachment_repo()
    sid = _uid()

    try:
        _create_test_submission(sub_repo, sid)
        att_repo.save_attachment(sid, _DUMMY_PDF_BYTES)
        att_repo.delete_attachment(sid)
        with pytest.raises(AttachmentNotFound):
            att_repo.get_attachment(sid)
    finally:
        _cleanup_submission(sid)


def test_attachment_delete_idempotent():
    sub_repo = _make_submission_repo()
    att_repo = _make_attachment_repo()
    sid = _uid()

    try:
        _create_test_submission(sub_repo, sid)
        att_repo.save_attachment(sid, _DUMMY_PDF_BYTES)
        att_repo.delete_attachment(sid)
        att_repo.delete_attachment(sid)  # must not raise
    finally:
        _cleanup_submission(sid)


# ---------------------------------------------------------------------------
# SubmissionRepository.get_delivery_metadata (Phase 3 — MESH fallback path)
# ---------------------------------------------------------------------------

def test_get_delivery_metadata_returns_only_the_two_fields():
    """
    The MESH dispatcher uses this narrow method when falling back to email.
    It must return exactly condition_label and submitted_at — nothing else,
    and in particular no clinical JSON (the dispatcher must never hold
    clinical content for a fallback enqueue).
    """
    repo = _make_submission_repo()
    sid = _uid()
    try:
        _create_test_submission(repo, sid)
        meta = repo.get_delivery_metadata(sid)
        assert set(meta.keys()) == {"condition_label", "submitted_at"}
        assert meta["condition_label"] == "Urinary Tract Infection"
        assert meta["submitted_at"] is not None
    finally:
        _cleanup_submission(sid)


def test_get_delivery_metadata_raises_for_unknown_submission():
    repo = _make_submission_repo()
    with pytest.raises(SubmissionNotFound):
        repo.get_delivery_metadata("nonexistent_submission_xyz")
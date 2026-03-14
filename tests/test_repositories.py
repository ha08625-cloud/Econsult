"""
tests/test_repositories.py

Integration tests for all three Postgres repositories.

Requires TEST_DATABASE_URL in the environment (pointing to the Railway
Postgres instance via DATABASE_PUBLIC_URL).

WARNING: These tests run against the same Postgres instance as the deployed
application. There is no dedicated test database. Each test generates unique
IDs and cleans up in a finally block. This is acceptable for a single-developer
project at this stage but must be resolved before any real patient data is
stored. See architecture.md Section 15.4.

Run from project root:
    python -m tests.test_repositories
"""

import os
import sys
import traceback
from uuid import uuid4
from datetime import datetime, timezone

# ---------------------------------------------------------------------------
# Minimal test harness (no pytest on server)
# ---------------------------------------------------------------------------

_passed = 0
_failed = 0
_errors = []


def run_test(name: str, fn):
    global _passed, _failed
    try:
        fn()
        print(f"  PASS  {name}")
        _passed += 1
    except AssertionError as e:
        print(f"  FAIL  {name}: {e}")
        _failed += 1
        _errors.append((name, traceback.format_exc()))
    except Exception as e:
        print(f"  ERROR {name}: {e}")
        _failed += 1
        _errors.append((name, traceback.format_exc()))


def _uid() -> str:
    return f"test_{uuid4().hex[:8]}"


# ---------------------------------------------------------------------------
# Load DATABASE_URL
# ---------------------------------------------------------------------------

DATABASE_URL = os.environ.get("TEST_DATABASE_URL") or os.environ.get("DATABASE_URL")
if not DATABASE_URL:
    print("ERROR: TEST_DATABASE_URL or DATABASE_URL must be set to run these tests.")
    sys.exit(1)

# ---------------------------------------------------------------------------
# Ensure tables exist
# ---------------------------------------------------------------------------

from app.core.db import init_database, get_conn
init_database(DATABASE_URL)

# ---------------------------------------------------------------------------
# Repository imports
# ---------------------------------------------------------------------------

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
    InvalidSignpostingData,
)
from app.repositories.submission_repository import (
    SubmissionRepository,
    SubmissionNotFound,
    InvalidDeliveryStatus,
)
from app.models.serialisation_contracts import ClinicalOutput, AuditOutput


# ---------------------------------------------------------------------------
# RuntimeStateRepository tests
# ---------------------------------------------------------------------------

def _make_state_repo() -> RuntimeStateRepository:
    return RuntimeStateRepository(DATABASE_URL)


def _cleanup_runtime(rid: str):
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
        raised = False
        try:
            repo.insert_new_version(rid, 1, "hash_abc", {})
        except VersionConflict:
            raised = True
        assert raised, "Expected VersionConflict was not raised"
    finally:
        _cleanup_runtime(rid)


def test_runtime_session_closed():
    repo = _make_state_repo()
    rid = _uid()

    try:
        repo.create_initial(rid, "hash_abc", {})
        repo.close_session(rid, 1)
        raised = False
        try:
            repo.get_latest(rid)
        except SessionClosed:
            raised = True
        assert raised, "Expected SessionClosed was not raised"
    finally:
        _cleanup_runtime(rid)


def test_runtime_not_found():
    repo = _make_state_repo()
    raised = False
    try:
        repo.get_latest("nonexistent_id_that_will_never_exist_xyz")
    except RuntimeStateNotFound:
        raised = True
    assert raised, "Expected RuntimeStateNotFound was not raised"


# ---------------------------------------------------------------------------
# PracticeRepository tests
# ---------------------------------------------------------------------------

def _make_practice_repo() -> PracticeRepository:
    return PracticeRepository(DATABASE_URL)


def _cleanup_practice(pid: str):
    with get_conn(DATABASE_URL) as conn:
        with conn.cursor() as cur:
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
    raised = False
    try:
        repo.create_practice(_uid(), "Test", "not-an-email")
    except InvalidEmailError:
        raised = True
    assert raised, "Expected InvalidEmailError was not raised"


def test_practice_get_email():
    repo = _make_practice_repo()
    pid = _uid()

    try:
        repo.create_practice(pid, "Test", "addr@example.com")
        email = repo.get_email(pid)
        assert email == "addr@example.com"
    finally:
        _cleanup_practice(pid)


def test_practice_not_found():
    repo = _make_practice_repo()
    raised = False
    try:
        repo.get_email("nonexistent_practice_that_will_never_exist_xyz")
    except PracticeNotFound:
        raised = True
    assert raised, "Expected PracticeNotFound was not raised"


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
        result = repo.get_signposting(pid, "uti")
        assert result is None
    finally:
        _cleanup_practice(pid)


def test_signposting_empty_html_deletes_row():
    repo = _make_practice_repo()
    pid = _uid()

    try:
        repo.create_practice(pid, "Test", "a@b.com")
        repo.set_signposting(pid, "uti", "<p>Some info</p>")
        # Quill empty output should result in deletion
        repo.set_signposting(pid, "uti", "<p></p>")
        result = repo.get_signposting(pid, "uti")
        assert result is None
    finally:
        _cleanup_practice(pid)


# ---------------------------------------------------------------------------
# SubmissionRepository tests
# ---------------------------------------------------------------------------

def _make_submission_repo() -> SubmissionRepository:
    return SubmissionRepository(DATABASE_URL)


def _make_dummy_outputs():
    clinical = ClinicalOutput(
        condition_id="uti",
        free_text="I have had burning on urination for 3 days",
        additional_text=None,
        answers={"fever": True, "dysuria": True},
        safety_messages=[],
        question_labels={"fever": "Do you have a fever?", "dysuria": "Do you have pain when urinating?"},
    )
    audit = AuditOutput(
        runtime_state={"session_id": "test_session", "version": 1},
        safety_evaluation={"flags": []},
        ruleset_version="uti_v1",
    )
    return clinical, audit


def _cleanup_submission(sid: str):
    with get_conn(DATABASE_URL) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM submission_records WHERE submission_id = %s", (sid,)
            )


def test_submission_create_and_get():
    repo = _make_submission_repo()
    sid = _uid()

    try:
        clinical, audit = _make_dummy_outputs()
        repo.create_submission(
            submission_id=sid,
            practice_id="test_practice",
            condition_id="uti",
            clinical_output=clinical,
            audit_output=audit,
            delivery_email="test@example.com",
        )
        row = repo.get_submission(sid)
        assert row["submission_id"] == sid
        assert row["delivery_status"] == "pending"
        # JSONB columns come back as dicts, not strings
        assert isinstance(row["clinical_output_json"], dict)
        assert isinstance(row["audit_output_json"], dict)
    finally:
        _cleanup_submission(sid)


def test_submission_update_to_sent():
    repo = _make_submission_repo()
    sid = _uid()

    try:
        clinical, audit = _make_dummy_outputs()
        repo.create_submission(
            submission_id=sid,
            practice_id="test_practice",
            condition_id="uti",
            clinical_output=clinical,
            audit_output=audit,
            delivery_email="test@example.com",
        )
        now = datetime.now(timezone.utc)
        repo.update_delivery_status(sid, "sent", delivered_at=now)
        row = repo.get_submission(sid)
        assert row["delivery_status"] == "sent"
        assert row["delivered_at"] is not None
    finally:
        _cleanup_submission(sid)


def test_submission_update_to_failed():
    repo = _make_submission_repo()
    sid = _uid()

    try:
        clinical, audit = _make_dummy_outputs()
        repo.create_submission(
            submission_id=sid,
            practice_id="test_practice",
            condition_id="uti",
            clinical_output=clinical,
            audit_output=audit,
            delivery_email="test@example.com",
        )
        repo.update_delivery_status(sid, "failed", delivery_error="SMTP timeout")
        row = repo.get_submission(sid)
        assert row["delivery_status"] == "failed"
        assert row["delivery_error"] == "SMTP timeout"
    finally:
        _cleanup_submission(sid)


def test_submission_not_found():
    repo = _make_submission_repo()
    raised = False
    try:
        repo.get_submission("nonexistent_submission_that_will_never_exist_xyz")
    except SubmissionNotFound:
        raised = True
    assert raised, "Expected SubmissionNotFound was not raised"


def test_submission_invalid_status():
    repo = _make_submission_repo()
    raised = False
    try:
        repo.update_delivery_status("any_id", "delivered")
    except InvalidDeliveryStatus:
        raised = True
    assert raised, "Expected InvalidDeliveryStatus was not raised"


def test_submission_list_by_status():
    repo = _make_submission_repo()
    sid = _uid()

    try:
        clinical, audit = _make_dummy_outputs()
        repo.create_submission(
            submission_id=sid,
            practice_id="test_practice",
            condition_id="uti",
            clinical_output=clinical,
            audit_output=audit,
            delivery_email="test@example.com",
        )
        pending = repo.list_by_status("pending")
        ids = [r["submission_id"] for r in pending]
        assert sid in ids
    finally:
        _cleanup_submission(sid)


# ---------------------------------------------------------------------------
# Run all tests
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("\n--- RuntimeStateRepository ---")
    run_test("create_initial and get_latest", test_runtime_create_and_get)
    run_test("insert_new_version increments correctly", test_runtime_insert_new_version)
    run_test("version_conflict on stale base_version", test_runtime_version_conflict)
    run_test("session_closed blocks get_latest", test_runtime_session_closed)
    run_test("get_latest raises RuntimeStateNotFound for missing id", test_runtime_not_found)

    print("\n--- PracticeRepository ---")
    run_test("create_practice and get_practice", test_practice_create_and_get)
    run_test("practice_exists before and after create", test_practice_exists)
    run_test("invalid_email raises InvalidEmailError", test_practice_invalid_email)
    run_test("get_email returns correct address", test_practice_get_email)
    run_test("get_email raises PracticeNotFound for missing practice", test_practice_not_found)
    run_test("set_signposting and get_signposting", test_signposting_set_and_get)
    run_test("delete_signposting removes row", test_signposting_delete)
    run_test("set_signposting with empty html deletes row", test_signposting_empty_html_deletes_row)

    print("\n--- SubmissionRepository ---")
    run_test("create_submission and get_submission", test_submission_create_and_get)
    run_test("update_delivery_status to sent", test_submission_update_to_sent)
    run_test("update_delivery_status to failed with error message", test_submission_update_to_failed)
    run_test("get_submission raises SubmissionNotFound for missing id", test_submission_not_found)
    run_test("update_delivery_status raises InvalidDeliveryStatus for bad status", test_submission_invalid_status)
    run_test("list_by_status returns pending submissions", test_submission_list_by_status)

    print(f"\n{'='*40}")
    print(f"Results: {_passed} passed, {_failed} failed")

    if _errors:
        print("\nFailed test details:")
        for name, tb in _errors:
            print(f"\n--- {name} ---")
            print(tb)

    sys.exit(0 if _failed == 0 else 1)
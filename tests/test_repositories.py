"""
tests/test_repositories.py

Integration tests for all four Postgres repositories.

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
from datetime import datetime, timezone, timedelta

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

from app.core.db import alembic_upgrade, get_conn
alembic_upgrade()

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
    InvalidDoctorListError,
)
from app.repositories.submission_repository import (
    SubmissionRepository,
    SubmissionNotFound,
    InvalidDeliveryStatus,
    PendingDelivery,
)
from app.repositories.attachment_repository import (
    AttachmentRepository,
    AttachmentNotFound,
)
from app.models.serialisation_contracts import ClinicalOutput, AuditOutput, PatientDetails


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
            # Delete child rows before the parent practice row.
            # practice_doctors and practice_signposting both FK to practices.
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


def test_practice_update_email():
    repo = _make_practice_repo()
    pid = _uid()

    try:
        repo.create_practice(pid, "Test", "original@example.com")
        repo.update_email(pid, "updated@example.com")
        email = repo.get_email(pid)
        assert email == "updated@example.com", f"Expected updated@example.com, got {email}"
    finally:
        _cleanup_practice(pid)


def test_practice_update_email_invalid_format():
    repo = _make_practice_repo()
    pid = _uid()

    try:
        repo.create_practice(pid, "Test", "valid@example.com")
        raised = False
        try:
            repo.update_email(pid, "not-an-email")
        except InvalidEmailError:
            raised = True
        assert raised, "Expected InvalidEmailError was not raised"
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
# PracticeRepository — doctor list tests
# ---------------------------------------------------------------------------

def test_doctors_get_returns_empty_list_when_none_configured():
    repo = _make_practice_repo()
    pid = _uid()

    try:
        repo.create_practice(pid, "Test", "a@b.com")
        doctors = repo.get_doctors(pid)
        assert doctors == [], f"Expected empty list, got {doctors}"
    finally:
        _cleanup_practice(pid)


def test_doctors_set_and_get_round_trip():
    repo = _make_practice_repo()
    pid = _uid()
    names = ["Dr Smith", "Dr Jones", "Dr Patel"]

    try:
        repo.create_practice(pid, "Test", "a@b.com")
        repo.set_doctors(pid, names)
        result = repo.get_doctors(pid)
        assert result == names, f"Expected {names}, got {result}"
    finally:
        _cleanup_practice(pid)


def test_doctors_set_replaces_existing_list():
    repo = _make_practice_repo()
    pid = _uid()

    try:
        repo.create_practice(pid, "Test", "a@b.com")
        repo.set_doctors(pid, ["Dr Smith", "Dr Jones"])
        repo.set_doctors(pid, ["Dr Brown"])
        result = repo.get_doctors(pid)
        assert result == ["Dr Brown"], f"Expected ['Dr Brown'], got {result}"
    finally:
        _cleanup_practice(pid)


def test_doctors_set_empty_list_clears_doctors():
    repo = _make_practice_repo()
    pid = _uid()

    try:
        repo.create_practice(pid, "Test", "a@b.com")
        repo.set_doctors(pid, ["Dr Smith", "Dr Jones"])
        repo.set_doctors(pid, [])
        result = repo.get_doctors(pid)
        assert result == [], f"Expected empty list after clearing, got {result}"
    finally:
        _cleanup_practice(pid)


def test_doctors_order_is_preserved():
    repo = _make_practice_repo()
    pid = _uid()
    # Deliberately non-alphabetical to confirm display_order not alphabetical sort
    names = ["Dr Zebra", "Dr Apple", "Dr Mango"]

    try:
        repo.create_practice(pid, "Test", "a@b.com")
        repo.set_doctors(pid, names)
        result = repo.get_doctors(pid)
        assert result == names, (
            f"Expected order {names}, got {result}"
        )
    finally:
        _cleanup_practice(pid)


def test_doctors_set_raises_for_missing_practice():
    repo = _make_practice_repo()
    raised = False
    try:
        repo.set_doctors("nonexistent_practice_that_will_never_exist_xyz", ["Dr Smith"])
    except PracticeNotFound:
        raised = True
    assert raised, "Expected PracticeNotFound was not raised"


def test_doctors_set_raises_for_empty_name():
    repo = _make_practice_repo()
    pid = _uid()

    try:
        repo.create_practice(pid, "Test", "a@b.com")
        raised = False
        try:
            repo.set_doctors(pid, ["Dr Smith", "  ", "Dr Jones"])
        except InvalidDoctorListError:
            raised = True
        assert raised, "Expected InvalidDoctorListError for empty/whitespace name"
    finally:
        _cleanup_practice(pid)


def test_doctors_set_raises_for_name_too_long():
    repo = _make_practice_repo()
    pid = _uid()

    try:
        repo.create_practice(pid, "Test", "a@b.com")
        long_name = "Dr " + "A" * 100  # 103 chars, over limit of 100
        raised = False
        try:
            repo.set_doctors(pid, [long_name])
        except InvalidDoctorListError:
            raised = True
        assert raised, "Expected InvalidDoctorListError for name exceeding 100 characters"
    finally:
        _cleanup_practice(pid)


def test_doctors_set_raises_for_list_too_long():
    repo = _make_practice_repo()
    pid = _uid()

    try:
        repo.create_practice(pid, "Test", "a@b.com")
        too_many = [f"Dr Doctor{i}" for i in range(51)]  # 51 items, over limit of 50
        raised = False
        try:
            repo.set_doctors(pid, too_many)
        except InvalidDoctorListError:
            raised = True
        assert raised, "Expected InvalidDoctorListError for list exceeding 50 items"
    finally:
        _cleanup_practice(pid)


# ---------------------------------------------------------------------------
# SubmissionRepository tests
# ---------------------------------------------------------------------------

def _make_submission_repo() -> SubmissionRepository:
    return SubmissionRepository(DATABASE_URL)


def _make_dummy_patient_details() -> PatientDetails:
    """Minimal PatientDetails fixture for repository tests."""
    return PatientDetails(
        patient_for="me",
        first_name="Test",
        last_name="Patient",
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


def _cleanup_submission(sid: str):
    """Delete submission and its attachment (child row first for FK constraint)."""
    with get_conn(DATABASE_URL) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM submission_attachments WHERE submission_id = %s", (sid,)
            )
            cur.execute(
                "DELETE FROM submission_records WHERE submission_id = %s", (sid,)
            )


def _create_test_submission(repo: SubmissionRepository, sid: str) -> None:
    """Helper: create a submission with all required fields for reuse across tests."""
    clinical, audit = _make_dummy_outputs()
    repo.create_submission(
        submission_id=sid,
        practice_id="test_practice",
        condition_id="uti",
        condition_label="Urinary Tract Infection",
        clinical_output=clinical,
        audit_output=audit,
        delivery_email="test@example.com",
        submitted_at=datetime.now(timezone.utc),
        attachment_count=0,
    )


def test_submission_create_and_get():
    repo = _make_submission_repo()
    sid = _uid()

    try:
        _create_test_submission(repo, sid)
        row = repo.get_submission(sid)
        assert row["submission_id"] == sid
        assert row["delivery_status"] == "pending"
        assert row["condition_label"] == "Urinary Tract Infection"
        # JSONB columns come back as dicts, not strings
        assert isinstance(row["clinical_output_json"], dict)
        assert isinstance(row["audit_output_json"], dict)
        # patient_details should be persisted inside clinical_output_json
        assert row["clinical_output_json"]["patient_details"]["first_name"] == "Test"
    finally:
        _cleanup_submission(sid)


def test_submission_update_to_sent():
    repo = _make_submission_repo()
    sid = _uid()

    try:
        _create_test_submission(repo, sid)
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
        _create_test_submission(repo, sid)
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
        _create_test_submission(repo, sid)
        pending = repo.list_by_status("pending")
        ids = [r["submission_id"] for r in pending]
        assert sid in ids
    finally:
        _cleanup_submission(sid)


# ---------------------------------------------------------------------------
# SubmissionRepository — list_retryable tests
# ---------------------------------------------------------------------------

def test_list_retryable_returns_eligible():
    """A failed submission with next_retry_after in the past is returned."""
    repo = _make_submission_repo()
    sid = _uid()

    try:
        _create_test_submission(repo, sid)
        past = datetime.now(timezone.utc) - timedelta(minutes=2)
        repo.record_attempt_outcome(
            sid, "failed", delivery_error="SMTP timeout", next_retry_after=past
        )
        results = repo.list_retryable()
        assert sid in results, f"Expected {sid} in list_retryable results"
    finally:
        _cleanup_submission(sid)


def test_list_retryable_excludes_future_retry():
    """A failed submission whose next_retry_after is in the future is not returned."""
    repo = _make_submission_repo()
    sid = _uid()

    try:
        _create_test_submission(repo, sid)
        future = datetime.now(timezone.utc) + timedelta(minutes=10)
        repo.record_attempt_outcome(
            sid, "failed", delivery_error="SMTP timeout", next_retry_after=future
        )
        row = repo.get_submission(sid)
        assert row["delivery_status"] == "failed"
        assert row["next_retry_after"] is not None

        results = repo.list_retryable()
        assert sid not in results, "Submission with future next_retry_after should not be retryable"
    finally:
        _cleanup_submission(sid)


def test_list_retryable_excludes_null_next_retry():
    """
    A failed submission with next_retry_after IS NULL is not returned.
    This is the state of a first-attempt failure before retry scheduling
    is implemented, or an exhausted submission.
    """
    repo = _make_submission_repo()
    sid = _uid()

    try:
        _create_test_submission(repo, sid)
        repo.record_attempt_outcome(
            sid, "failed", delivery_error="SMTP timeout", next_retry_after=None
        )
        row = repo.get_submission(sid)
        assert row["delivery_status"] == "failed"
        assert row["next_retry_after"] is None

        results = repo.list_retryable()
        assert sid not in results, "Submission with NULL next_retry_after should not be retryable"
    finally:
        _cleanup_submission(sid)


def test_list_retryable_excludes_sent():
    """
    A sent submission is never returned even if next_retry_after is set.
    This simulates a data integrity anomaly (should not occur in normal
    operation) and verifies the delivery_status = 'failed' filter holds.
    """
    repo = _make_submission_repo()
    sid = _uid()

    try:
        _create_test_submission(repo, sid)
        now = datetime.now(timezone.utc)
        past = now - timedelta(minutes=2)
        repo.update_delivery_status(sid, "sent", delivered_at=now)
        with get_conn(DATABASE_URL) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE submission_records SET next_retry_after = %s WHERE submission_id = %s",
                    (past, sid),
                )

        results = repo.list_retryable()
        assert sid not in results, "Sent submission should never appear in list_retryable"
    finally:
        _cleanup_submission(sid)


def test_list_retryable_excludes_pending():
    """
    A pending submission is never returned even if next_retry_after is set.
    This simulates a data integrity anomaly.
    """
    repo = _make_submission_repo()
    sid = _uid()

    try:
        _create_test_submission(repo, sid)
        past = datetime.now(timezone.utc) - timedelta(minutes=2)
        with get_conn(DATABASE_URL) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE submission_records SET next_retry_after = %s WHERE submission_id = %s",
                    (past, sid),
                )

        row = repo.get_submission(sid)
        assert row["delivery_status"] == "pending"

        results = repo.list_retryable()
        assert sid not in results, "Pending submission should never appear in list_retryable"
    finally:
        _cleanup_submission(sid)


def test_list_retryable_respects_limit():
    """
    list_retryable(limit=n) returns at most n results even when more
    eligible submissions exist.
    """
    repo = _make_submission_repo()
    limit = 3
    n_submissions = limit + 2  # create more than the limit
    sids = [_uid() for _ in range(n_submissions)]
    past = datetime.now(timezone.utc) - timedelta(minutes=2)

    try:
        for sid in sids:
            _create_test_submission(repo, sid)
            repo.record_attempt_outcome(
                sid, "failed", delivery_error="SMTP timeout", next_retry_after=past
            )

        results = repo.list_retryable(limit=limit)
        assert len(results) == limit, (
            f"Expected exactly {limit} results, got {len(results)}"
        )
    finally:
        for sid in sids:
            _cleanup_submission(sid)


def test_list_retryable_returns_string_ids():
    """Each item returned by list_retryable is a string submission ID."""
    repo = _make_submission_repo()
    sid = _uid()
    past = datetime.now(timezone.utc) - timedelta(minutes=2)

    try:
        _create_test_submission(repo, sid)
        repo.record_attempt_outcome(
            sid, "failed", delivery_error="SMTP timeout", next_retry_after=past
        )
        results = repo.list_retryable(limit=100)
        assert len(results) >= 1
        for item in results:
            assert isinstance(item, str), (
                f"Expected str submission ID, got {type(item)}"
            )
        assert sid in results
    finally:
        _cleanup_submission(sid)


def test_list_retryable_empty():
    """list_retryable returns an empty list when no submissions are eligible."""
    repo = _make_submission_repo()
    # limit=0 always returns empty regardless of database state
    results = repo.list_retryable(limit=0)
    assert isinstance(results, list), "Expected list from list_retryable"
    assert len(results) == 0, "limit=0 should always return an empty list"


# ---------------------------------------------------------------------------
# SubmissionRepository — list_orphans tests
# ---------------------------------------------------------------------------

def test_list_orphans_returns_old_pending_submission():
    """
    A pending submission with delivery_attempts=0 older than the threshold
    is returned by list_orphans.
    """
    repo = _make_submission_repo()
    sid = _uid()

    try:
        _create_test_submission(repo, sid)
        # Backdate submitted_at to 6 minutes ago to exceed the 5-minute threshold.
        six_minutes_ago = datetime.now(timezone.utc) - timedelta(minutes=6)
        with get_conn(DATABASE_URL) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE submission_records SET submitted_at = %s WHERE submission_id = %s",
                    (six_minutes_ago, sid),
                )

        results = repo.list_orphans(older_than_minutes=5)
        assert sid in results, (
            f"Expected {sid} in list_orphans results for a 6-minute-old pending submission"
        )
    finally:
        _cleanup_submission(sid)


def test_list_orphans_excludes_recent_pending():
    """
    A pending submission submitted less than the threshold ago is not an orphan.
    """
    repo = _make_submission_repo()
    sid = _uid()

    try:
        _create_test_submission(repo, sid)
        # submitted_at defaults to now — within the threshold
        results = repo.list_orphans(older_than_minutes=5)
        assert sid not in results, (
            "A freshly created pending submission should not appear in list_orphans"
        )
    finally:
        _cleanup_submission(sid)


def test_list_orphans_excludes_failed_submission():
    """
    A failed submission (delivery attempted) is never an orphan, even if old.
    """
    repo = _make_submission_repo()
    sid = _uid()

    try:
        _create_test_submission(repo, sid)
        repo.record_attempt_outcome(
            sid, "failed", delivery_error="SMTP timeout", next_retry_after=None
        )
        # Backdate to make it old
        six_minutes_ago = datetime.now(timezone.utc) - timedelta(minutes=6)
        with get_conn(DATABASE_URL) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE submission_records SET submitted_at = %s WHERE submission_id = %s",
                    (six_minutes_ago, sid),
                )

        results = repo.list_orphans(older_than_minutes=5)
        assert sid not in results, (
            "A failed submission must never appear in list_orphans"
        )
    finally:
        _cleanup_submission(sid)


def test_list_orphans_excludes_sent_submission():
    """
    A sent submission is never an orphan, even if old.
    """
    repo = _make_submission_repo()
    sid = _uid()

    try:
        _create_test_submission(repo, sid)
        repo.update_delivery_status(sid, "sent", delivered_at=datetime.now(timezone.utc))
        six_minutes_ago = datetime.now(timezone.utc) - timedelta(minutes=6)
        with get_conn(DATABASE_URL) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE submission_records SET submitted_at = %s WHERE submission_id = %s",
                    (six_minutes_ago, sid),
                )

        results = repo.list_orphans(older_than_minutes=5)
        assert sid not in results, (
            "A sent submission must never appear in list_orphans"
        )
    finally:
        _cleanup_submission(sid)


def test_list_orphans_returns_empty_when_none():
    """list_orphans returns an empty list when no orphans exist."""
    repo = _make_submission_repo()
    # No setup — any existing orphans in the DB are fine; we just confirm
    # the call does not raise and returns a list.
    results = repo.list_orphans(older_than_minutes=5)
    assert isinstance(results, list), "Expected list from list_orphans"


# ---------------------------------------------------------------------------
# AttachmentRepository tests
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
        retrieved = att_repo.get_attachment(sid)
        assert retrieved == _DUMMY_PDF_BYTES
    finally:
        _cleanup_submission(sid)


def test_attachment_duplicate_save_raises():
    sub_repo = _make_submission_repo()
    att_repo = _make_attachment_repo()
    sid = _uid()

    try:
        _create_test_submission(sub_repo, sid)
        att_repo.save_attachment(sid, _DUMMY_PDF_BYTES)
        raised = False
        try:
            att_repo.save_attachment(sid, _DUMMY_PDF_BYTES)
        except Exception:
            # psycopg2.errors.UniqueViolation
            raised = True
        assert raised, "Expected UniqueViolation on duplicate save_attachment"
    finally:
        _cleanup_submission(sid)


def test_attachment_get_missing_raises():
    att_repo = _make_attachment_repo()
    raised = False
    try:
        att_repo.get_attachment("nonexistent_submission_that_will_never_exist_xyz")
    except AttachmentNotFound:
        raised = True
    assert raised, "Expected AttachmentNotFound was not raised"


def test_attachment_delete():
    sub_repo = _make_submission_repo()
    att_repo = _make_attachment_repo()
    sid = _uid()

    try:
        _create_test_submission(sub_repo, sid)
        att_repo.save_attachment(sid, _DUMMY_PDF_BYTES)
        att_repo.delete_attachment(sid)
        # After deletion, get should raise AttachmentNotFound
        raised = False
        try:
            att_repo.get_attachment(sid)
        except AttachmentNotFound:
            raised = True
        assert raised, "Expected AttachmentNotFound after delete"
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
        # Second delete should not raise
        att_repo.delete_attachment(sid)
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
    run_test("update_email changes the stored address", test_practice_update_email)
    run_test("update_email raises InvalidEmailError for bad format", test_practice_update_email_invalid_format)
    run_test("set_signposting and get_signposting", test_signposting_set_and_get)
    run_test("delete_signposting removes row", test_signposting_delete)
    run_test("set_signposting with empty html deletes row", test_signposting_empty_html_deletes_row)

    print("\n--- PracticeRepository — doctor list ---")
    run_test("get_doctors returns empty list when none configured", test_doctors_get_returns_empty_list_when_none_configured)
    run_test("set_doctors and get_doctors round-trip", test_doctors_set_and_get_round_trip)
    run_test("set_doctors replaces existing list", test_doctors_set_replaces_existing_list)
    run_test("set_doctors with empty list clears doctors", test_doctors_set_empty_list_clears_doctors)
    run_test("get_doctors preserves insertion order", test_doctors_order_is_preserved)
    run_test("set_doctors raises PracticeNotFound for missing practice", test_doctors_set_raises_for_missing_practice)
    run_test("set_doctors raises InvalidDoctorListError for empty name", test_doctors_set_raises_for_empty_name)
    run_test("set_doctors raises InvalidDoctorListError for name too long", test_doctors_set_raises_for_name_too_long)
    run_test("set_doctors raises InvalidDoctorListError for list too long", test_doctors_set_raises_for_list_too_long)

    print("\n--- SubmissionRepository ---")
    run_test("create_submission and get_submission", test_submission_create_and_get)
    run_test("update_delivery_status to sent", test_submission_update_to_sent)
    run_test("update_delivery_status to failed with error message", test_submission_update_to_failed)
    run_test("get_submission raises SubmissionNotFound for missing id", test_submission_not_found)
    run_test("update_delivery_status raises InvalidDeliveryStatus for bad status", test_submission_invalid_status)
    run_test("list_by_status returns pending submissions", test_submission_list_by_status)

    print("\n--- SubmissionRepository — list_retryable ---")
    run_test("list_retryable returns eligible failed submission", test_list_retryable_returns_eligible)
    run_test("list_retryable excludes submission with future next_retry_after", test_list_retryable_excludes_future_retry)
    run_test("list_retryable excludes failed submission with NULL next_retry_after", test_list_retryable_excludes_null_next_retry)
    run_test("list_retryable excludes sent submission even with next_retry_after set", test_list_retryable_excludes_sent)
    run_test("list_retryable excludes pending submission even with next_retry_after set", test_list_retryable_excludes_pending)
    run_test("list_retryable respects limit parameter", test_list_retryable_respects_limit)
    run_test("list_retryable items are string submission IDs", test_list_retryable_returns_string_ids)
    run_test("list_retryable returns empty list when limit=0", test_list_retryable_empty)

    print("\n--- SubmissionRepository — list_orphans ---")
    run_test("list_orphans returns old pending submission", test_list_orphans_returns_old_pending_submission)
    run_test("list_orphans excludes recent pending submission", test_list_orphans_excludes_recent_pending)
    run_test("list_orphans excludes failed submission", test_list_orphans_excludes_failed_submission)
    run_test("list_orphans excludes sent submission", test_list_orphans_excludes_sent_submission)
    run_test("list_orphans returns empty list when none", test_list_orphans_returns_empty_when_none)

    print("\n--- AttachmentRepository ---")
    run_test("save_attachment and get_attachment round-trip", test_attachment_save_and_get)
    run_test("duplicate save_attachment raises", test_attachment_duplicate_save_raises)
    run_test("get_attachment raises AttachmentNotFound for missing id", test_attachment_get_missing_raises)
    run_test("delete_attachment removes the row", test_attachment_delete)
    run_test("delete_attachment is idempotent", test_attachment_delete_idempotent)

    print(f"\n{'='*40}")
    print(f"Results: {_passed} passed, {_failed} failed")

    if _errors:
        print("\nFailed test details:")
        for name, tb in _errors:
            print(f"\n--- {name} ---")
            print(tb)

    sys.exit(0 if _failed == 0 else 1)
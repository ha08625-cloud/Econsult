"""
tests/test_mesh_worker.py

Unit tests for the MESH dispatcher worker (app/services/delivery/mesh_worker.py).

No database, no network, no real sleeping. All repositories and the MESH
client are MagicMocks; the payload builder is the real RawPdfPayloadBuilder
(pure function). run_worker's infinite loop is not exercised here — the
processing helpers it delegates to are tested directly. Integration
coverage (real DB, real sandbox) lives in
tests/integration/test_mesh_worker_db.py and
tests/integration/test_mesh_worker_sandbox.py.
"""

import logging
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest

from app.services.delivery.mesh import MeshTerminalError, MeshTransientError
from app.services.delivery.mesh_constants import (
    MAX_MESH_ATTEMPTS,
    MESH_RETRY_BACKOFF_MINUTES,
)
from app.services.delivery.mesh_payload import RawPdfPayloadBuilder
from app.services.delivery.mesh_worker import (
    _compute_backoff,
    _enqueue_fallback_delivery,
    _handshake_with_retry,
    _process_job,
    _record_failure_and_maybe_fallback,
    _recover_orphaned_fallbacks,
    _trigger_fallback,
)

WORKFLOW_ID = "TEST_WORKFLOW"
PDF_BYTES = b"%PDF-1.7 test bytes"
MESSAGE_ID = "20260611000000000000_A1B2C3"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _job_row(attempt_count: int = 0) -> dict:
    """A claimed mesh_jobs row as claim_next_pending returns it."""
    return {
        "id": uuid.uuid4(),
        "submission_id": "sub_test_123",
        "status": "pending",
        "message_id": None,
        "mex_localid": uuid.uuid4(),  # Postgres UUID type -> uuid.UUID
        "recipient_mailbox_id": "X26HC001",
        "attempt_count": attempt_count,
        "last_error": None,
        "last_error_code": None,
        "next_retry_after": None,
    }


def _deps():
    """All mocked dependencies, with sensible fallback-metadata returns."""
    deps = {
        "mesh_repo": MagicMock(),
        "attachment_repo": MagicMock(),
        "pdf_repo": MagicMock(),
        "submission_repo": MagicMock(),
        "delivery_repo": MagicMock(),
        "mesh_client": MagicMock(),
    }
    deps["attachment_repo"].get_attachment.return_value = PDF_BYTES
    deps["mesh_client"].send_message.return_value = MESSAGE_ID
    deps["pdf_repo"].get_delivery_email.return_value = "gp@example.com"
    deps["submission_repo"].get_delivery_metadata.return_value = {
        "condition_label": "Urinary Tract Infection",
        "submitted_at": datetime(2026, 6, 11, 9, 0, tzinfo=timezone.utc),
    }
    return deps


def _run_process_job(job, deps):
    _process_job(
        job=job,
        mesh_repo=deps["mesh_repo"],
        attachment_repo=deps["attachment_repo"],
        pdf_repo=deps["pdf_repo"],
        submission_repo=deps["submission_repo"],
        delivery_repo=deps["delivery_repo"],
        mesh_client=deps["mesh_client"],
        payload_builder=RawPdfPayloadBuilder(),
        workflow_id=WORKFLOW_ID,
    )


def _fallback_kwargs(deps):
    return {
        "mesh_repo": deps["mesh_repo"],
        "pdf_repo": deps["pdf_repo"],
        "submission_repo": deps["submission_repo"],
        "delivery_repo": deps["delivery_repo"],
    }


# ---------------------------------------------------------------------------
# Success path
# ---------------------------------------------------------------------------

def test_success_sends_payload_and_marks_sent():
    deps = _deps()
    job = _job_row()

    _run_process_job(job, deps)

    send_kwargs = deps["mesh_client"].send_message.call_args.kwargs
    assert send_kwargs["recipient_mailbox_id"] == "X26HC001"
    assert send_kwargs["payload_bytes"] == PDF_BYTES
    assert send_kwargs["workflow_id"] == WORKFLOW_ID
    assert send_kwargs["content_type"] == "application/pdf"
    deps["mesh_repo"].mark_sent.assert_called_once_with(
        mesh_job_id=str(job["id"]), message_id=MESSAGE_ID
    )
    deps["mesh_repo"].mark_failed.assert_not_called()
    deps["mesh_repo"].mark_fallback_triggered.assert_not_called()
    deps["delivery_repo"].create_job.assert_not_called()


def test_mex_localid_is_stringified():
    """The DB column is a Postgres UUID; MeshClient takes a str."""
    deps = _deps()
    job = _job_row()

    _run_process_job(job, deps)

    sent = deps["mesh_client"].send_message.call_args.kwargs["mex_localid"]
    assert isinstance(sent, str)
    assert sent == str(job["mex_localid"])


# ---------------------------------------------------------------------------
# Transient failure: retry with backoff
# ---------------------------------------------------------------------------

def test_transient_below_max_records_failure_without_fallback():
    deps = _deps()
    deps["mesh_client"].send_message.side_effect = MeshTransientError("503")
    deps["mesh_repo"].mark_failed.return_value = 1  # below MAX
    job = _job_row(attempt_count=0)

    _run_process_job(job, deps)

    failed_kwargs = deps["mesh_repo"].mark_failed.call_args.kwargs
    assert failed_kwargs["mesh_job_id"] == str(job["id"])
    assert "503" in failed_kwargs["error"]
    assert failed_kwargs["error_code"] is None
    expected = datetime.now(timezone.utc) + timedelta(
        minutes=MESH_RETRY_BACKOFF_MINUTES[0]
    )
    assert abs((failed_kwargs["next_retry_after"] - expected).total_seconds()) < 5
    deps["mesh_repo"].mark_sent.assert_not_called()
    deps["mesh_repo"].mark_fallback_triggered.assert_not_called()
    deps["delivery_repo"].create_job.assert_not_called()


@pytest.mark.parametrize(
    "attempt_count,expected_minutes",
    [
        (0, MESH_RETRY_BACKOFF_MINUTES[0]),
        (1, MESH_RETRY_BACKOFF_MINUTES[1]),
        (2, MESH_RETRY_BACKOFF_MINUTES[2]),
        (5, MESH_RETRY_BACKOFF_MINUTES[-1]),  # clamped past the schedule end
    ],
)
def test_compute_backoff_indexes_and_clamps(attempt_count, expected_minutes):
    expected = datetime.now(timezone.utc) + timedelta(minutes=expected_minutes)
    assert abs((_compute_backoff(attempt_count) - expected).total_seconds()) < 5


def test_transient_exhaustion_triggers_fallback():
    deps = _deps()
    deps["mesh_client"].send_message.side_effect = MeshTransientError("503")
    deps["mesh_repo"].mark_failed.return_value = MAX_MESH_ATTEMPTS
    job = _job_row(attempt_count=MAX_MESH_ATTEMPTS - 1)

    _run_process_job(job, deps)

    deps["mesh_repo"].mark_failed.assert_called_once()
    deps["mesh_repo"].mark_fallback_triggered.assert_called_once_with(
        mesh_job_id=str(job["id"])
    )
    deps["delivery_repo"].create_job.assert_called_once()
    deps["mesh_repo"].mark_sent.assert_not_called()


# ---------------------------------------------------------------------------
# Terminal failure: immediate fallback
# ---------------------------------------------------------------------------

def test_terminal_failure_falls_back_immediately_without_mark_failed():
    deps = _deps()
    deps["mesh_client"].send_message.side_effect = MeshTerminalError(
        "417 unregistered recipient"
    )
    job = _job_row()

    _run_process_job(job, deps)

    deps["mesh_repo"].mark_failed.assert_not_called()
    deps["mesh_repo"].mark_fallback_triggered.assert_called_once_with(
        mesh_job_id=str(job["id"])
    )
    deps["delivery_repo"].create_job.assert_called_once()
    deps["mesh_repo"].mark_sent.assert_not_called()


# ---------------------------------------------------------------------------
# Fallback mechanics
# ---------------------------------------------------------------------------

def test_fallback_ordering_invariant_mark_before_create():
    """
    mark_fallback_triggered must commit BEFORE create_job runs. A crash
    between the two fails safe (undelivered-but-detectable, recovered by
    the sweep); the reverse order would risk double-channel delivery.
    """
    deps = _deps()
    order = MagicMock()
    order.attach_mock(deps["mesh_repo"].mark_fallback_triggered, "mark")
    order.attach_mock(deps["delivery_repo"].create_job, "create")

    _trigger_fallback(job=_job_row(), **_fallback_kwargs(deps))

    names = [call[0] for call in order.mock_calls]
    assert names.index("mark") < names.index("create")


def test_fallback_enqueue_uses_narrow_metadata_and_sets_flag():
    """
    to_email comes from pdf_jobs (get_delivery_email); condition_label and
    submitted_at from the narrow get_delivery_metadata. get_submission
    (full clinical row) must never be called.
    """
    deps = _deps()

    _enqueue_fallback_delivery(
        submission_id="sub_test_123",
        pdf_repo=deps["pdf_repo"],
        submission_repo=deps["submission_repo"],
        delivery_repo=deps["delivery_repo"],
    )

    deps["pdf_repo"].get_delivery_email.assert_called_once_with("sub_test_123")
    deps["submission_repo"].get_delivery_metadata.assert_called_once_with(
        "sub_test_123"
    )
    deps["submission_repo"].get_submission.assert_not_called()
    create_kwargs = deps["delivery_repo"].create_job.call_args.kwargs
    assert create_kwargs["submission_id"] == "sub_test_123"
    assert create_kwargs["to_email"] == "gp@example.com"
    assert create_kwargs["condition_label"] == "Urinary Tract Infection"
    assert create_kwargs["is_fallback"] is True


# ---------------------------------------------------------------------------
# Unexpected-exception path (run_worker delegates here)
# ---------------------------------------------------------------------------

def test_unexpected_failure_records_attempt_and_falls_back_on_exhaustion():
    deps = _deps()
    deps["mesh_repo"].mark_failed.return_value = MAX_MESH_ATTEMPTS
    job = _job_row(attempt_count=MAX_MESH_ATTEMPTS - 1)

    _record_failure_and_maybe_fallback(
        job=job, exc=RuntimeError("attachment corrupt"), **_fallback_kwargs(deps)
    )

    assert "attachment corrupt" in deps["mesh_repo"].mark_failed.call_args.kwargs["error"]
    deps["mesh_repo"].mark_fallback_triggered.assert_called_once()
    deps["delivery_repo"].create_job.assert_called_once()


# ---------------------------------------------------------------------------
# Orphaned-fallback recovery sweep
# ---------------------------------------------------------------------------

def test_sweep_recovers_each_orphan_and_logs_error(caplog):
    deps = _deps()
    deps["mesh_repo"].list_orphaned_fallbacks.return_value = [
        {"id": uuid.uuid4(), "submission_id": "sub_orphan_1"},
        {"id": uuid.uuid4(), "submission_id": "sub_orphan_2"},
    ]

    with caplog.at_level(logging.ERROR, logger="app.services.delivery.mesh_worker"):
        _recover_orphaned_fallbacks(**_fallback_kwargs(deps))

    assert deps["delivery_repo"].create_job.call_count == 2
    for call in deps["delivery_repo"].create_job.call_args_list:
        assert call.kwargs["is_fallback"] is True
    recovered = [r for r in caplog.records if "recovered orphaned fallback" in r.message]
    assert len(recovered) == 2


def test_sweep_is_noop_when_no_orphans():
    deps = _deps()
    deps["mesh_repo"].list_orphaned_fallbacks.return_value = []

    _recover_orphaned_fallbacks(**_fallback_kwargs(deps))

    deps["delivery_repo"].create_job.assert_not_called()


def test_sweep_contains_per_orphan_failure_and_continues():
    """One unrecoverable orphan must not block recovery of the others."""
    deps = _deps()
    deps["mesh_repo"].list_orphaned_fallbacks.return_value = [
        {"id": uuid.uuid4(), "submission_id": "sub_bad"},
        {"id": uuid.uuid4(), "submission_id": "sub_good"},
    ]
    deps["pdf_repo"].get_delivery_email.side_effect = [
        RuntimeError("no pdf_jobs row"),
        "gp@example.com",
    ]

    _recover_orphaned_fallbacks(**_fallback_kwargs(deps))

    assert deps["delivery_repo"].create_job.call_count == 1
    assert (
        deps["delivery_repo"].create_job.call_args.kwargs["submission_id"]
        == "sub_good"
    )


# ---------------------------------------------------------------------------
# Startup handshake with bounded retry
# ---------------------------------------------------------------------------

def test_handshake_terminal_error_aborts_immediately_without_sleeping():
    client = MagicMock()
    client.handshake.side_effect = MeshTerminalError("403 INVALID_AUTH")
    sleep_fn = MagicMock()

    with pytest.raises(MeshTerminalError):
        _handshake_with_retry(client, delays_seconds=[1, 2, 3], sleep_fn=sleep_fn)

    assert client.handshake.call_count == 1
    sleep_fn.assert_not_called()


def test_handshake_transient_then_success_retries_once():
    client = MagicMock()
    client.handshake.side_effect = [MeshTransientError("timeout"), None]
    sleep_fn = MagicMock()

    _handshake_with_retry(client, delays_seconds=[7, 11], sleep_fn=sleep_fn)

    assert client.handshake.call_count == 2
    sleep_fn.assert_called_once_with(7)


def test_handshake_persistent_transient_exhausts_bound_and_raises():
    """
    The bound exists because empty-errorCode 403s classify as transient,
    so bad credentials must eventually abort rather than retry forever.
    Attempts = len(delays) + 1 final attempt.
    """
    client = MagicMock()
    client.handshake.side_effect = MeshTransientError("timeout")
    sleep_fn = MagicMock()
    delays = [1, 2, 3]

    with pytest.raises(MeshTransientError):
        _handshake_with_retry(client, delays_seconds=delays, sleep_fn=sleep_fn)

    assert client.handshake.call_count == len(delays) + 1
    assert [c.args[0] for c in sleep_fn.call_args_list] == delays


def test_handshake_default_delays_come_from_constants():
    """Passing no schedule must use HANDSHAKE_RETRY_DELAYS_SECONDS."""
    client = MagicMock()
    client.handshake.side_effect = MeshTransientError("timeout")
    sleep_fn = MagicMock()

    with pytest.raises(MeshTransientError):
        _handshake_with_retry(client, sleep_fn=sleep_fn)

    from app.services.delivery.mesh_constants import HANDSHAKE_RETRY_DELAYS_SECONDS

    assert [c.args[0] for c in sleep_fn.call_args_list] == HANDSHAKE_RETRY_DELAYS_SECONDS
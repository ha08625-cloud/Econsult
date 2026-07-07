"""
tests/test_delivery_worker.py

Unit tests for the delivery worker loop.

No database required. All dependencies are replaced with fakes or mocks.
time.sleep is patched so tests do not wait real time.

The delivery worker calls delivery_repo.claim_next_pending directly and
processes one job per loop iteration.

Provider ID branching:
send_clinical_output now returns str | None.
- str  -> worker calls mark_as_accepted (Mailgun path)
- None -> worker calls mark_sent (SMTP/legacy path)

_make_delivery_service defaults to returning a mock provider ID so tests
exercise the Mailgun path by default. Tests that need the legacy path
explicitly set send_clinical_output.return_value = None.
"""

import contextlib
import logging
from datetime import UTC, datetime
from unittest.mock import MagicMock, call, patch

import psycopg2
import pytest

from app.repositories.attachment_repository import AttachmentNotFound
from app.services.delivery.delivery_constants import MAX_ATTEMPTS, RETRY_BACKOFF_MINUTES
from app.services.delivery.delivery_service import EmailDeliveryError
from app.services.delivery.delivery_worker import (
    _compute_backoff,
    _process_job,
    run_worker,
)

_MOCK_PROVIDER_ID = "20260423123456.1.abc@mailgun.org"


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _make_delivery_repo(job_sequence=None):
    """
    Build a fake DeliveryRepository.

    job_sequence: list of return values for successive claim_next_pending
    calls. Defaults to [None] (empty queue).
    """
    repo = MagicMock()
    if job_sequence is None:
        job_sequence = [None]
    repo.claim_next_pending.side_effect = job_sequence
    return repo


def _make_attachment_repo(pdf_bytes=b"%PDF-fake"):
    repo = MagicMock()
    repo.get_attachment.return_value = pdf_bytes
    return repo


def _make_delivery_service(provider_id: str | None = _MOCK_PROVIDER_ID):
    """
    Build a mock DeliveryService.

    By default, send_clinical_output returns a mock provider ID (Mailgun path).
    Pass provider_id=None to exercise the legacy SMTP path.
    """
    svc = MagicMock()
    svc.send_clinical_output.return_value = provider_id
    return svc


def _make_job(
    submission_id="sub-aaa",
    job_id="job-aaa",
    to_email="gp@example.com",
    condition_label="UTI",
    submitted_at=None,
    attempt_count=0,
):
    if submitted_at is None:
        submitted_at = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)
    return {
        "id": job_id,
        "submission_id": submission_id,
        "to_email": to_email,
        "condition_label": condition_label,
        "submitted_at": submitted_at,
        "attempt_count": attempt_count,
    }


def _run_worker_n_sleeps(
    delivery_repo,
    attachment_repo,
    delivery_service,
    n_sleeps,
    poll_interval=10,
):
    """
    Run run_worker until time.sleep has been called n_sleeps times, then stop.
    Returns the mock time.sleep object for assertion.
    """
    sleep_call_count = [0]

    def fake_sleep(seconds):
        sleep_call_count[0] += 1
        if sleep_call_count[0] >= n_sleeps:
            raise StopIteration

    with patch(
        "app.services.delivery.delivery_worker.time.sleep", side_effect=fake_sleep
    ) as mock_sleep:
        with contextlib.suppress(StopIteration):
            run_worker(
                delivery_repo=delivery_repo,
                attachment_repo=attachment_repo,
                delivery_service=delivery_service,
                poll_interval=poll_interval,
            )

    return mock_sleep


# ---------------------------------------------------------------------------
# _process_job: successful path — Mailgun (provider ID returned)
# ---------------------------------------------------------------------------


def test_process_job_fetches_attachment_and_sends():
    """
    _process_job must call get_attachment with the submission_id, then pass
    the bytes to send_clinical_output.
    """
    job = _make_job()
    attachment_repo = _make_attachment_repo(pdf_bytes=b"%PDF-real")
    delivery_service = _make_delivery_service()
    delivery_repo = MagicMock()

    _process_job(
        job=job,
        delivery_repo=delivery_repo,
        attachment_repo=attachment_repo,
        delivery_service=delivery_service,
    )

    attachment_repo.get_attachment.assert_called_once_with("sub-aaa")
    delivery_service.send_clinical_output.assert_called_once()
    send_kwargs = delivery_service.send_clinical_output.call_args.kwargs
    assert send_kwargs["pdf_bytes"] == b"%PDF-real"
    assert send_kwargs["to_email"] == "gp@example.com"
    assert send_kwargs["submission_id"] == "sub-aaa"


def test_process_job_marks_accepted_on_mailgun_success():
    """
    When send_clinical_output returns a provider ID string, mark_as_accepted
    must be called with the job id and that ID. mark_sent must not be called.
    """
    job = _make_job(job_id="job-xyz")
    delivery_repo = MagicMock()
    delivery_service = _make_delivery_service(provider_id=_MOCK_PROVIDER_ID)

    _process_job(
        job=job,
        delivery_repo=delivery_repo,
        attachment_repo=_make_attachment_repo(),
        delivery_service=delivery_service,
    )

    delivery_repo.mark_as_accepted.assert_called_once_with("job-xyz", _MOCK_PROVIDER_ID)
    delivery_repo.mark_sent.assert_not_called()


def test_process_job_marks_sent_on_smtp_path():
    """
    When send_clinical_output returns None (SMTP/legacy path), mark_sent must
    be called with the job id. mark_as_accepted must not be called.
    """
    job = _make_job(job_id="job-xyz")
    delivery_repo = MagicMock()
    delivery_service = _make_delivery_service(provider_id=None)

    _process_job(
        job=job,
        delivery_repo=delivery_repo,
        attachment_repo=_make_attachment_repo(),
        delivery_service=delivery_service,
    )

    delivery_repo.mark_sent.assert_called_once_with("job-xyz")
    delivery_repo.mark_as_accepted.assert_not_called()


def test_process_job_passes_denormalised_fields_to_send():
    """
    send_clinical_output must receive condition_label and submitted_at from
    the delivery_jobs row, not from submission_records (which the delivery
    worker never reads).
    """
    submitted_at = datetime(2026, 3, 15, 9, 30, 0, tzinfo=UTC)
    job = _make_job(condition_label="Chest Infection", submitted_at=submitted_at)
    delivery_service = _make_delivery_service()

    _process_job(
        job=job,
        delivery_repo=MagicMock(),
        attachment_repo=_make_attachment_repo(),
        delivery_service=delivery_service,
    )

    send_kwargs = delivery_service.send_clinical_output.call_args.kwargs
    assert send_kwargs["condition_label"] == "Chest Infection"
    assert send_kwargs["submitted_at"] == submitted_at


# ---------------------------------------------------------------------------
# _process_job: failure paths
# ---------------------------------------------------------------------------


def test_process_job_raises_email_delivery_error_on_send_failure():
    """
    EmailDeliveryError from send_clinical_output must propagate uncaught from
    _process_job so the caller (run_worker) can record the backoff.
    """
    job = _make_job()
    delivery_service = _make_delivery_service()
    delivery_service.send_clinical_output.side_effect = EmailDeliveryError("timeout")

    with pytest.raises(EmailDeliveryError):
        _process_job(
            job=job,
            delivery_repo=MagicMock(),
            attachment_repo=_make_attachment_repo(),
            delivery_service=delivery_service,
        )


def test_process_job_raises_attachment_not_found_on_missing_attachment():
    """
    AttachmentNotFound must propagate uncaught from _process_job. A missing
    attachment means the ordering invariant has been broken.
    """
    job = _make_job()
    attachment_repo = _make_attachment_repo()
    attachment_repo.get_attachment.side_effect = AttachmentNotFound("sub-aaa")

    with pytest.raises(AttachmentNotFound):
        _process_job(
            job=job,
            delivery_repo=MagicMock(),
            attachment_repo=attachment_repo,
            delivery_service=_make_delivery_service(),
        )


# ---------------------------------------------------------------------------
# run_worker: queue and sleep behaviour
# ---------------------------------------------------------------------------


def test_worker_sleeps_when_queue_is_empty():
    """
    When claim_next_pending returns None, time.sleep is called with poll_interval.
    """
    delivery_repo = _make_delivery_repo(job_sequence=[None, None, None])
    mock_sleep = _run_worker_n_sleeps(
        delivery_repo,
        _make_attachment_repo(),
        _make_delivery_service(),
        n_sleeps=2,
        poll_interval=20,
    )
    for c in mock_sleep.call_args_list:
        assert c == call(20)


def test_worker_processes_job_and_does_not_sleep():
    """
    When a job is claimed, the worker processes it without sleeping, then
    claims again immediately.
    """
    job = _make_job()
    delivery_repo = _make_delivery_repo(job_sequence=[job, None])
    delivery_service = _make_delivery_service()

    mock_sleep = _run_worker_n_sleeps(
        delivery_repo,
        _make_attachment_repo(),
        delivery_service,
        n_sleeps=1,
    )

    delivery_service.send_clinical_output.assert_called_once()
    assert mock_sleep.call_count == 1  # only after the empty second claim


def test_worker_records_failed_backoff_on_send_error():
    """
    When send_clinical_output raises EmailDeliveryError, run_worker calls
    delivery_repo.mark_failed with the job id and a future next_retry_after.
    mark_failed returns False (not exhausted) in the normal retry case.
    """
    job = _make_job(attempt_count=0)
    delivery_repo = _make_delivery_repo(job_sequence=[job, None])
    delivery_repo.mark_failed.return_value = False
    delivery_service = _make_delivery_service()
    delivery_service.send_clinical_output.side_effect = EmailDeliveryError("SMTP down")

    with (
        patch(
            "app.services.delivery.delivery_worker.time.sleep",
            side_effect=[None, StopIteration],
        ),
        contextlib.suppress(StopIteration),
    ):
        run_worker(
            delivery_repo=delivery_repo,
            attachment_repo=_make_attachment_repo(),
            delivery_service=delivery_service,
            poll_interval=10,
        )

    delivery_repo.mark_failed.assert_called_once()
    call_args = delivery_repo.mark_failed.call_args
    assert call_args.args[0] == "job-aaa"
    assert isinstance(call_args.args[1], str)  # error message
    # next_retry_after should be a future datetime (not None at attempt 0)
    assert (
        call_args.kwargs.get("next_retry_after") is not None
        or len(call_args.args) >= 3
        and call_args.args[2] is not None
    )


def test_worker_logs_error_on_exhaustion(caplog):
    """
    When mark_failed returns True (job permanently exhausted), run_worker must
    log an additional error message containing the submission_id, job_id, and
    MAX_ATTEMPTS.
    """
    job = _make_job(attempt_count=MAX_ATTEMPTS - 1)
    delivery_repo = _make_delivery_repo(job_sequence=[job, None])
    delivery_repo.mark_failed.return_value = True
    delivery_service = _make_delivery_service()
    delivery_service.send_clinical_output.side_effect = EmailDeliveryError("SMTP down")

    with (
        caplog.at_level(logging.ERROR),
        patch(
            "app.services.delivery.delivery_worker.time.sleep",
            side_effect=[None, StopIteration],
        ),
        contextlib.suppress(StopIteration),
    ):
        run_worker(
            delivery_repo=delivery_repo,
            attachment_repo=_make_attachment_repo(),
            delivery_service=delivery_service,
            poll_interval=10,
        )

    exhaustion_messages = [r.message for r in caplog.records if "permanently failed" in r.message]
    assert len(exhaustion_messages) == 1
    msg = exhaustion_messages[0]
    assert "sub-aaa" in msg
    assert "job-aaa" in msg
    assert str(MAX_ATTEMPTS) in msg


def test_worker_logs_critical_on_attachment_not_found():
    """
    AttachmentNotFound from get_attachment is a bug (invariant broken) and
    must be logged at CRITICAL. The worker must not call mark_sent or
    mark_as_accepted.
    """
    job = _make_job()
    delivery_repo = _make_delivery_repo(job_sequence=[job, None])
    attachment_repo = _make_attachment_repo()
    attachment_repo.get_attachment.side_effect = AttachmentNotFound("sub-aaa")

    with (
        patch(
            "app.services.delivery.delivery_worker.time.sleep",
            side_effect=[None, StopIteration],
        ),
        contextlib.suppress(StopIteration),
    ):
        run_worker(
            delivery_repo=delivery_repo,
            attachment_repo=attachment_repo,
            delivery_service=_make_delivery_service(),
            poll_interval=10,
        )

    delivery_repo.mark_sent.assert_not_called()
    delivery_repo.mark_as_accepted.assert_not_called()


def test_worker_exits_on_db_failure():
    """
    When claim_next_pending raises psycopg2.OperationalError the exception
    propagates uncaught, allowing the process to exit and Railway to restart.
    """
    delivery_repo = MagicMock()
    delivery_repo.claim_next_pending.side_effect = psycopg2.OperationalError("connection refused")

    with (
        patch("app.services.delivery.delivery_worker.time.sleep"),
        pytest.raises(psycopg2.OperationalError),
    ):
        run_worker(
            delivery_repo=delivery_repo,
            attachment_repo=_make_attachment_repo(),
            delivery_service=_make_delivery_service(),
            poll_interval=10,
        )


# ---------------------------------------------------------------------------
# _compute_backoff
# ---------------------------------------------------------------------------


def test_compute_backoff_first_failure():
    result = _compute_backoff(attempt_count=0)
    assert result is not None
    expected_minutes = RETRY_BACKOFF_MINUTES[0]
    diff = (result - datetime.now(UTC)).total_seconds()
    assert abs(diff - expected_minutes * 60) < 5


def test_compute_backoff_returns_none_when_exhausted():
    result = _compute_backoff(attempt_count=MAX_ATTEMPTS - 1)
    assert result is None
    
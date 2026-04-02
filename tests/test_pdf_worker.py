"""
tests/test_pdf_worker.py

Unit tests for the PDF worker loop and job processing logic.

No database required. All dependencies are replaced with fakes or mocks.
time.sleep is patched so tests do not wait real time.

Test coverage:
- Successful job: photos fetched, count verified, PDF generated,
  attachment saved (UPSERT), delivery job created, job marked done.
- Photo count mismatch: job marked failed immediately, no PDF generated,
  no delivery job created.
- UPSERT safety: save_attachment called once per process (idempotency
  is a DB-level guarantee, not tested here; we verify the call is made).
- Idempotent delivery job creation: create_job called once per process
  (DO NOTHING is a DB-level guarantee; we verify the call is made).
- Failed generation: job marked failed with backoff, delivery job not created.
- Empty queue: worker sleeps for the configured interval.
- Orphan detection: CRITICAL logged when orphans exist, rate-limited.
"""

import logging
import time
from datetime import datetime, timezone
from unittest.mock import MagicMock, call, patch

import pytest

from app.services.delivery.pdf_worker import (
    ORPHAN_LOG_INTERVAL_SECONDS,
    ORPHAN_THRESHOLD_MINUTES,
    _check_orphans,
    _compute_backoff,
    _process_job,
    run_worker,
)
from app.services.delivery.pdf_constants import MAX_PDF_ATTEMPTS, PDF_RETRY_BACKOFF_MINUTES


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _make_pdf_repo(job_sequence=None, orphan_sequence=None):
    """
    Build a fake PDFRepository.

    job_sequence: list of return values for successive claim_next_pending
    calls. Each element is a dict or None. Defaults to [None].

    orphan_sequence: list of return values for successive
    list_orphaned_submissions calls. Defaults to [[]] (no orphans).
    """
    repo = MagicMock()

    if job_sequence is None:
        job_sequence = [None]
    repo.claim_next_pending.side_effect = job_sequence

    if orphan_sequence is None:
        orphan_sequence = [[]] * 20
    repo.list_orphaned_submissions.side_effect = orphan_sequence

    return repo


def _make_job(
    submission_id="sub-aaa",
    job_id="job-aaa",
    attachment_count=1,
    delivery_email="gp@example.com",
    attempt_count=0,
):
    return {
        "id": job_id,
        "submission_id": submission_id,
        "attachment_count": attachment_count,
        "delivery_email": delivery_email,
        "attempt_count": attempt_count,
    }


def _make_photo_repo(photos=None):
    repo = MagicMock()
    repo.get_photos.return_value = photos if photos is not None else [b"fake-photo"]
    return repo


def _make_submission_repo(condition_label="UTI", submitted_at=None):
    repo = MagicMock()
    if submitted_at is None:
        submitted_at = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    repo.get_submission.return_value = {
        "condition_label": condition_label,
        "submitted_at": submitted_at,
        "clinical_output_json": {
            "condition_id": "uti",
            "free_text": "test",
            "additional_text": None,
            "answers": {},
            "safety_messages": [],
            "question_labels": {},
            "patient_details": {
                "patient_for": "me",
                "first_name": "Jane",
                "last_name": "Smith",
                "date_of_birth": "1990-01-01",
                "postcode": "SW1A 1AA",
                "submitter_name": None,
                "submitter_relationship": None,
            },
            "contact_preferences": None,
        },
    }
    return repo


def _make_attachment_repo():
    return MagicMock()


def _make_delivery_repo():
    return MagicMock()


def _run_worker_n_sleeps(
    pdf_repo,
    photo_repo,
    submission_repo,
    attachment_repo,
    delivery_repo,
    n_sleeps,
    poll_interval=10,
    practice_name=None,
):
    """
    Run run_worker until time.sleep has been called n_sleeps times, then stop.

    Patches time.sleep and generate_pdf to prevent real work and control
    execution. Returns the mock objects for time.sleep and generate_pdf.
    """
    sleep_call_count = [0]

    def fake_sleep(seconds):
        sleep_call_count[0] += 1
        if sleep_call_count[0] >= n_sleeps:
            raise StopIteration

    with patch(
        "app.services.delivery.pdf_worker.time.sleep", side_effect=fake_sleep
    ) as mock_sleep, patch(
        "app.services.delivery.pdf_worker.generate_pdf", return_value=b"%PDF-fake"
    ) as mock_generate:
        try:
            run_worker(
                pdf_repo=pdf_repo,
                photo_repo=photo_repo,
                submission_repo=submission_repo,
                attachment_repo=attachment_repo,
                delivery_repo=delivery_repo,
                poll_interval=poll_interval,
                practice_name=practice_name,
            )
        except StopIteration:
            pass

    return mock_sleep, mock_generate


# ---------------------------------------------------------------------------
# _process_job: successful path
# ---------------------------------------------------------------------------

def test_process_job_fetches_photos_and_generates_pdf():
    """
    _process_job must call get_photos, generate_pdf with the photos, and
    save the result via save_attachment.
    """
    job = _make_job(attachment_count=1)
    photo_repo = _make_photo_repo(photos=[b"img"])
    submission_repo = _make_submission_repo()
    attachment_repo = _make_attachment_repo()
    delivery_repo = _make_delivery_repo()

    with patch(
        "app.services.delivery.pdf_worker.generate_pdf", return_value=b"%PDF-fake"
    ) as mock_gen:
        _process_job(
            job=job,
            pdf_repo=MagicMock(),
            photo_repo=photo_repo,
            submission_repo=submission_repo,
            attachment_repo=attachment_repo,
            delivery_repo=delivery_repo,
            practice_name="Test Practice",
        )

    photo_repo.get_photos.assert_called_once_with("sub-aaa")
    assert mock_gen.call_count == 1
    call_kwargs = mock_gen.call_args.kwargs
    assert call_kwargs["photo_bytes"] == [b"img"]
    attachment_repo.save_attachment.assert_called_once_with("sub-aaa", b"%PDF-fake")


def test_process_job_creates_delivery_job_after_save_attachment():
    """
    delivery_repo.create_job must be called after save_attachment, never before.
    The ordering invariant: a delivery_jobs row can only exist after
    save_attachment has completed.
    """
    call_order = []
    job = _make_job(attachment_count=1)
    attachment_repo = _make_attachment_repo()
    attachment_repo.save_attachment.side_effect = lambda *a, **kw: call_order.append("save")
    delivery_repo = _make_delivery_repo()
    delivery_repo.create_job.side_effect = lambda *a, **kw: call_order.append("create_job")
    pdf_repo = MagicMock()
    pdf_repo.mark_done.side_effect = lambda *a, **kw: call_order.append("mark_done")

    with patch("app.services.delivery.pdf_worker.generate_pdf", return_value=b"%PDF"):
        _process_job(
            job=job,
            pdf_repo=pdf_repo,
            photo_repo=_make_photo_repo(),
            submission_repo=_make_submission_repo(),
            attachment_repo=attachment_repo,
            delivery_repo=delivery_repo,
            practice_name=None,
        )

    assert call_order == ["save", "create_job", "mark_done"], (
        f"Operations out of order: {call_order}. "
        "The ordering invariant (save -> create_job -> mark_done) must not be broken."
    )


def test_process_job_marks_pdf_job_done_on_success():
    """
    pdf_repo.mark_done must be called with the job id after successful processing.
    """
    job = _make_job(job_id="job-xyz", attachment_count=1)
    pdf_repo = MagicMock()

    with patch("app.services.delivery.pdf_worker.generate_pdf", return_value=b"%PDF"):
        _process_job(
            job=job,
            pdf_repo=pdf_repo,
            photo_repo=_make_photo_repo(),
            submission_repo=_make_submission_repo(),
            attachment_repo=_make_attachment_repo(),
            delivery_repo=_make_delivery_repo(),
            practice_name=None,
        )

    pdf_repo.mark_done.assert_called_once_with("job-xyz")


def test_process_job_passes_delivery_email_to_create_job():
    """
    delivery_repo.create_job must receive the delivery_email from the job row,
    not from submission_records.
    """
    job = _make_job(delivery_email="practice@nhs.net", attachment_count=1)
    delivery_repo = _make_delivery_repo()

    with patch("app.services.delivery.pdf_worker.generate_pdf", return_value=b"%PDF"):
        _process_job(
            job=job,
            pdf_repo=MagicMock(),
            photo_repo=_make_photo_repo(),
            submission_repo=_make_submission_repo(),
            attachment_repo=_make_attachment_repo(),
            delivery_repo=delivery_repo,
            practice_name=None,
        )

    call_kwargs = delivery_repo.create_job.call_args.kwargs
    assert call_kwargs["to_email"] == "practice@nhs.net"


# ---------------------------------------------------------------------------
# _process_job: photo count mismatch
# ---------------------------------------------------------------------------

def test_process_job_fails_immediately_on_photo_count_mismatch():
    """
    When len(photos) != job.attachment_count, _process_job must raise ValueError
    without calling generate_pdf or creating a delivery job.
    """
    job = _make_job(attachment_count=2)
    photo_repo = _make_photo_repo(photos=[b"only-one"])  # 1 photo, expected 2
    delivery_repo = _make_delivery_repo()

    with patch(
        "app.services.delivery.pdf_worker.generate_pdf"
    ) as mock_gen:
        with pytest.raises(ValueError, match="Photo count mismatch"):
            _process_job(
                job=job,
                pdf_repo=MagicMock(),
                photo_repo=photo_repo,
                submission_repo=_make_submission_repo(),
                attachment_repo=_make_attachment_repo(),
                delivery_repo=delivery_repo,
                practice_name=None,
            )

    mock_gen.assert_not_called()
    delivery_repo.create_job.assert_not_called()


# ---------------------------------------------------------------------------
# _process_job: no photos (attachment_count=0)
# ---------------------------------------------------------------------------

def test_process_job_succeeds_with_zero_photos():
    """
    A submission with attachment_count=0 must succeed when get_photos returns [].
    generate_pdf should be called with photo_bytes=None (empty list maps to None).
    """
    job = _make_job(attachment_count=0)
    photo_repo = _make_photo_repo(photos=[])

    with patch(
        "app.services.delivery.pdf_worker.generate_pdf", return_value=b"%PDF"
    ) as mock_gen:
        _process_job(
            job=job,
            pdf_repo=MagicMock(),
            photo_repo=photo_repo,
            submission_repo=_make_submission_repo(),
            attachment_repo=_make_attachment_repo(),
            delivery_repo=_make_delivery_repo(),
            practice_name=None,
        )

    call_kwargs = mock_gen.call_args.kwargs
    assert call_kwargs["photo_bytes"] is None


# ---------------------------------------------------------------------------
# run_worker: queue and sleep behaviour
# ---------------------------------------------------------------------------

def test_worker_sleeps_when_queue_is_empty():
    """
    When claim_next_pending returns None, time.sleep is called with poll_interval.
    """
    pdf_repo = _make_pdf_repo(job_sequence=[None, None, None])
    mock_sleep, _ = _run_worker_n_sleeps(
        pdf_repo,
        _make_photo_repo(),
        _make_submission_repo(),
        _make_attachment_repo(),
        _make_delivery_repo(),
        n_sleeps=2,
        poll_interval=15,
    )
    for c in mock_sleep.call_args_list:
        assert c == call(15)


def test_worker_processes_job_and_continues():
    """
    When a job is claimed successfully, the worker processes it and then
    continues to the next loop iteration without sleeping.
    """
    job = _make_job(attachment_count=0)
    pdf_repo = _make_pdf_repo(job_sequence=[job, None])

    mock_sleep, mock_gen = _run_worker_n_sleeps(
        pdf_repo,
        _make_photo_repo(photos=[]),
        _make_submission_repo(),
        _make_attachment_repo(),
        _make_delivery_repo(),
        n_sleeps=1,
    )

    assert mock_gen.call_count == 1
    assert mock_sleep.call_count == 1  # only after the empty queue


def test_worker_marks_job_failed_on_exception():
    """
    When _process_job raises, run_worker calls pdf_repo.mark_failed with
    the job id and a next_retry_after value.
    """
    job = _make_job(attachment_count=1, attempt_count=0)
    pdf_repo = _make_pdf_repo(job_sequence=[job, None])

    with patch(
        "app.services.delivery.pdf_worker.generate_pdf",
        side_effect=RuntimeError("PDF library crash"),
    ), patch(
        "app.services.delivery.pdf_worker.time.sleep", side_effect=[None, StopIteration]
    ):
        try:
            run_worker(
                pdf_repo=pdf_repo,
                photo_repo=_make_photo_repo(),
                submission_repo=_make_submission_repo(),
                attachment_repo=_make_attachment_repo(),
                delivery_repo=_make_delivery_repo(),
                poll_interval=10,
                practice_name=None,
            )
        except StopIteration:
            pass

    pdf_repo.mark_failed.assert_called_once()
    call_args = pdf_repo.mark_failed.call_args
    assert call_args.args[0] == "job-aaa"
    assert isinstance(call_args.args[1], str)  # error message


def test_worker_does_not_create_delivery_job_on_failed_generation():
    """
    If generate_pdf raises, no delivery job must be created.
    """
    job = _make_job(attachment_count=1)
    pdf_repo = _make_pdf_repo(job_sequence=[job, None])
    delivery_repo = _make_delivery_repo()

    with patch(
        "app.services.delivery.pdf_worker.generate_pdf",
        side_effect=RuntimeError("crash"),
    ), patch(
        "app.services.delivery.pdf_worker.time.sleep", side_effect=[None, StopIteration]
    ):
        try:
            run_worker(
                pdf_repo=pdf_repo,
                photo_repo=_make_photo_repo(),
                submission_repo=_make_submission_repo(),
                attachment_repo=_make_attachment_repo(),
                delivery_repo=delivery_repo,
                poll_interval=10,
                practice_name=None,
            )
        except StopIteration:
            pass

    delivery_repo.create_job.assert_not_called()


# ---------------------------------------------------------------------------
# _compute_backoff
# ---------------------------------------------------------------------------

def test_compute_backoff_first_failure_uses_first_schedule_entry():
    result = _compute_backoff(attempt_count=0)
    assert result is not None
    expected_minutes = PDF_RETRY_BACKOFF_MINUTES[0]
    diff = (result - datetime.now(timezone.utc)).total_seconds()
    # Allow a 5-second window for test execution time.
    assert abs(diff - expected_minutes * 60) < 5


def test_compute_backoff_second_failure_uses_second_schedule_entry():
    result = _compute_backoff(attempt_count=1)
    assert result is not None
    expected_minutes = PDF_RETRY_BACKOFF_MINUTES[1]
    diff = (result - datetime.now(timezone.utc)).total_seconds()
    assert abs(diff - expected_minutes * 60) < 5


def test_compute_backoff_returns_none_when_exhausted():
    """
    When attempt_count + 1 >= MAX_PDF_ATTEMPTS, returns None (job will be
    permanently failed by mark_failed).
    """
    result = _compute_backoff(attempt_count=MAX_PDF_ATTEMPTS - 1)
    assert result is None


# ---------------------------------------------------------------------------
# Orphan detection
# ---------------------------------------------------------------------------

def test_orphan_detection_logs_critical_when_orphans_found(caplog):
    pdf_repo = MagicMock()
    pdf_repo.list_orphaned_submissions.return_value = ["orphan-aaa", "orphan-bbb"]

    with caplog.at_level(logging.CRITICAL, logger="app.services.delivery.pdf_worker"):
        _check_orphans(pdf_repo, last_log_at=None, interval=ORPHAN_LOG_INTERVAL_SECONDS)

    assert any("orphan-aaa" in r.message for r in caplog.records)
    assert any(r.levelno == logging.CRITICAL for r in caplog.records)


def test_orphan_detection_does_not_log_when_no_orphans(caplog):
    pdf_repo = MagicMock()
    pdf_repo.list_orphaned_submissions.return_value = []

    with caplog.at_level(logging.CRITICAL, logger="app.services.delivery.pdf_worker"):
        _check_orphans(pdf_repo, last_log_at=None, interval=ORPHAN_LOG_INTERVAL_SECONDS)

    critical = [r for r in caplog.records if r.levelno == logging.CRITICAL]
    assert len(critical) == 0


def test_orphan_detection_rate_limits_critical_log(caplog):
    pdf_repo = MagicMock()
    pdf_repo.list_orphaned_submissions.return_value = ["orphan-aaa"]

    last_log_at = _check_orphans(
        pdf_repo, last_log_at=None, interval=ORPHAN_LOG_INTERVAL_SECONDS
    )
    assert last_log_at is not None

    caplog.clear()

    with caplog.at_level(logging.CRITICAL, logger="app.services.delivery.pdf_worker"):
        _check_orphans(pdf_repo, last_log_at=last_log_at, interval=ORPHAN_LOG_INTERVAL_SECONDS)

    critical = [r for r in caplog.records if r.levelno == logging.CRITICAL]
    assert len(critical) == 0, "CRITICAL must be suppressed within the rate-limit window"


def test_orphan_detection_emits_again_after_interval(caplog):
    pdf_repo = MagicMock()
    pdf_repo.list_orphaned_submissions.return_value = ["orphan-aaa"]

    expired_log_at = time.monotonic() - ORPHAN_LOG_INTERVAL_SECONDS - 1

    with caplog.at_level(logging.CRITICAL, logger="app.services.delivery.pdf_worker"):
        _check_orphans(
            pdf_repo, last_log_at=expired_log_at, interval=ORPHAN_LOG_INTERVAL_SECONDS
        )

    assert any(r.levelno == logging.CRITICAL for r in caplog.records)
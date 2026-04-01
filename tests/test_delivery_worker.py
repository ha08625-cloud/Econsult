"""
tests/test_delivery_worker.py

Unit tests for the delivery worker loop.

No database required. All dependencies are replaced with fakes or mocks.
time.sleep is patched so tests do not wait real time and assertions on
sleep call count are reliable.

Why attempt_delivery is patched at app.services.delivery.delivery_worker
rather than at app.services.delivery.delivery_orchestration:

    When delivery_worker.py imports attempt_delivery at the top of the file,
    Python binds the name 'attempt_delivery' in delivery_worker's module
    namespace. Patching the original source location
    (delivery_orchestration.attempt_delivery) replaces the object in
    delivery_orchestration but delivery_worker still holds the original
    reference. To intercept calls made by the worker, we must patch the
    name in the module that uses it — delivery_worker.attempt_delivery.
    This is standard Python mock patching behaviour.
"""

import logging
import time
from unittest.mock import MagicMock, call, patch

import psycopg2
import pytest

from app.services.delivery.delivery_worker import (
    ORPHAN_LOG_INTERVAL_SECONDS,
    ORPHAN_THRESHOLD_MINUTES,
    _check_orphans,
    run_worker,
)


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _make_repos(retryable_sequence=None, orphan_sequence=None):
    """
    Build a fake SubmissionRepository.

    retryable_sequence: list of return values for successive list_retryable
    calls. Each element is a list[str]. Defaults to [[]] (empty on first call).

    orphan_sequence: list of return values for successive list_orphans calls.
    Defaults to [[]] (no orphans).
    """
    repo = MagicMock()

    if retryable_sequence is None:
        retryable_sequence = [[]]
    repo.list_retryable.side_effect = retryable_sequence

    if orphan_sequence is None:
        orphan_sequence = [[]] * 20  # enough for any test
    repo.list_orphans.side_effect = orphan_sequence

    return repo


def _make_attachment_repo():
    return MagicMock()


def _make_delivery_service():
    return MagicMock()


def _run_worker_n_sleeps(repo, attachment_repo, delivery_service, n_sleeps,
                          poll_interval=10, batch_limit=50):
    """
    Run run_worker until time.sleep has been called n_sleeps times, then stop.

    Patches both time.sleep (to prevent real waiting and count calls) and
    attempt_delivery (to prevent real DB/SMTP calls).

    Returns the mock objects for time.sleep and attempt_delivery so callers
    can assert on calls.
    """
    sleep_call_count = [0]

    def fake_sleep(seconds):
        sleep_call_count[0] += 1
        if sleep_call_count[0] >= n_sleeps:
            raise StopIteration

    with patch("app.services.delivery.delivery_worker.time.sleep", side_effect=fake_sleep) as mock_sleep, \
         patch("app.services.delivery.delivery_worker.attempt_delivery") as mock_attempt:
        try:
            run_worker(
                submission_repo=repo,
                attachment_repo=attachment_repo,
                delivery_service=delivery_service,
                poll_interval=poll_interval,
                batch_limit=batch_limit,
            )
        except StopIteration:
            pass

    return mock_sleep, mock_attempt


# ---------------------------------------------------------------------------
# Worker loop behaviour
# ---------------------------------------------------------------------------

def test_worker_calls_attempt_delivery_for_each_item():
    """
    Given list_retryable returns two IDs on the first call then empty,
    attempt_delivery is called once per ID and sleep is called once (for
    the empty batch).
    """
    ids = ["sub_aaa", "sub_bbb"]
    repo = _make_repos(retryable_sequence=[ids, []])
    attachment_repo = _make_attachment_repo()
    delivery_service = _make_delivery_service()

    mock_sleep, mock_attempt = _run_worker_n_sleeps(
        repo, attachment_repo, delivery_service, n_sleeps=1
    )

    assert mock_attempt.call_count == 2
    called_ids = [c.args[0] for c in mock_attempt.call_args_list]
    assert called_ids == ids

    assert mock_sleep.call_count == 1


def test_worker_continues_after_per_item_exception():
    """
    If attempt_delivery raises an unexpected exception for one submission,
    the worker continues and processes the next submission.
    """
    ids = ["sub_fail", "sub_ok"]
    repo = _make_repos(retryable_sequence=[ids, []])
    attachment_repo = _make_attachment_repo()
    delivery_service = _make_delivery_service()

    call_count = [0]

    def fake_attempt(submission_id, *args, **kwargs):
        call_count[0] += 1
        if submission_id == "sub_fail":
            raise RuntimeError("Unexpected error")

    with patch("app.services.delivery.delivery_worker.time.sleep",
               side_effect=[None, StopIteration]), \
         patch("app.services.delivery.delivery_worker.attempt_delivery",
               side_effect=fake_attempt):
        try:
            run_worker(
                submission_repo=repo,
                attachment_repo=attachment_repo,
                delivery_service=delivery_service,
                poll_interval=10,
                batch_limit=50,
            )
        except StopIteration:
            pass

    assert call_count[0] == 2, (
        "attempt_delivery must be called for both submissions even when "
        "the first raises an exception"
    )


def test_worker_sleeps_when_queue_is_empty():
    """
    When list_retryable returns empty, time.sleep is called with the
    configured poll interval.
    """
    repo = _make_repos(retryable_sequence=[[], [], []])
    attachment_repo = _make_attachment_repo()
    delivery_service = _make_delivery_service()

    mock_sleep, _ = _run_worker_n_sleeps(
        repo, attachment_repo, delivery_service, n_sleeps=2, poll_interval=10
    )

    for c in mock_sleep.call_args_list:
        assert c == call(10), (
            f"sleep must be called with poll_interval=10, got {c}"
        )


def test_worker_does_not_sleep_between_non_empty_batches():
    """
    When two consecutive batches are non-empty, sleep is not called between
    them. Sleep is only called after the first empty batch.
    """
    batch1 = ["sub_aaa"]
    batch2 = ["sub_bbb"]
    repo = _make_repos(retryable_sequence=[batch1, batch2, []])
    attachment_repo = _make_attachment_repo()
    delivery_service = _make_delivery_service()

    mock_sleep, mock_attempt = _run_worker_n_sleeps(
        repo, attachment_repo, delivery_service, n_sleeps=1
    )

    # Two IDs processed, one sleep total (after the empty batch).
    assert mock_attempt.call_count == 2
    assert mock_sleep.call_count == 1


def test_worker_exits_on_db_failure():
    """
    When list_retryable raises psycopg2.OperationalError the exception
    propagates uncaught, allowing the process to exit and Railway to restart.
    """
    repo = MagicMock()
    repo.list_retryable.side_effect = psycopg2.OperationalError("connection refused")
    repo.list_orphans.return_value = []

    attachment_repo = _make_attachment_repo()
    delivery_service = _make_delivery_service()

    with patch("app.services.delivery.delivery_worker.time.sleep"), \
         patch("app.services.delivery.delivery_worker.attempt_delivery"):
        with pytest.raises(psycopg2.OperationalError):
            run_worker(
                submission_repo=repo,
                attachment_repo=attachment_repo,
                delivery_service=delivery_service,
                poll_interval=10,
                batch_limit=50,
            )


# ---------------------------------------------------------------------------
# Orphan detection
# ---------------------------------------------------------------------------

def test_orphan_detection_logs_critical_when_orphans_found(caplog):
    """
    When list_orphans returns submission IDs and the rate-limit window has
    elapsed, a CRITICAL log is emitted containing the IDs.
    """
    orphan_ids = ["orphan_aaa", "orphan_bbb"]
    repo = MagicMock()
    repo.list_orphans.return_value = orphan_ids

    with caplog.at_level(logging.CRITICAL, logger="app.services.delivery.delivery_worker"):
        _check_orphans(repo, last_log_at=None, interval=ORPHAN_LOG_INTERVAL_SECONDS)

    assert any("orphan_aaa" in r.message for r in caplog.records), (
        "CRITICAL log must contain the orphan submission IDs"
    )
    assert any(r.levelno == logging.CRITICAL for r in caplog.records)


def test_orphan_detection_does_not_log_when_no_orphans(caplog):
    """
    When list_orphans returns empty, no CRITICAL log is emitted.
    """
    repo = MagicMock()
    repo.list_orphans.return_value = []

    with caplog.at_level(logging.CRITICAL, logger="app.services.delivery.delivery_worker"):
        _check_orphans(repo, last_log_at=None, interval=ORPHAN_LOG_INTERVAL_SECONDS)

    critical_records = [r for r in caplog.records if r.levelno == logging.CRITICAL]
    assert len(critical_records) == 0, (
        "No CRITICAL log must be emitted when there are no orphans"
    )


def test_orphan_detection_rate_limits_critical_log(caplog):
    """
    When a CRITICAL was emitted recently (within interval), a second call
    with orphans present does not emit another CRITICAL log.
    """
    orphan_ids = ["orphan_aaa"]
    repo = MagicMock()
    repo.list_orphans.return_value = orphan_ids

    # First call — no prior log, should emit.
    last_log_at = _check_orphans(
        repo, last_log_at=None, interval=ORPHAN_LOG_INTERVAL_SECONDS
    )
    assert last_log_at is not None, "First call with orphans must update last_log_at"

    caplog.clear()

    # Second call immediately after — within rate-limit window, must not emit.
    with caplog.at_level(logging.CRITICAL, logger="app.services.delivery.delivery_worker"):
        _check_orphans(repo, last_log_at=last_log_at, interval=ORPHAN_LOG_INTERVAL_SECONDS)

    critical_records = [r for r in caplog.records if r.levelno == logging.CRITICAL]
    assert len(critical_records) == 0, (
        "CRITICAL log must be suppressed within the rate-limit window"
    )


def test_orphan_detection_emits_again_after_interval(caplog):
    """
    When the rate-limit window has elapsed, a subsequent call with orphans
    emits a new CRITICAL log.
    """
    orphan_ids = ["orphan_aaa"]
    repo = MagicMock()
    repo.list_orphans.return_value = orphan_ids

    # Simulate a last_log_at that is older than the interval.
    expired_log_at = time.monotonic() - ORPHAN_LOG_INTERVAL_SECONDS - 1

    with caplog.at_level(logging.CRITICAL, logger="app.services.delivery.delivery_worker"):
        _check_orphans(
            repo, last_log_at=expired_log_at, interval=ORPHAN_LOG_INTERVAL_SECONDS
        )

    assert any(r.levelno == logging.CRITICAL for r in caplog.records), (
        "CRITICAL log must be emitted once the rate-limit window has elapsed"
    )


def test_orphan_check_returns_updated_timestamp_on_log():
    """
    _check_orphans returns a fresh monotonic timestamp when a CRITICAL is emitted.
    """
    repo = MagicMock()
    repo.list_orphans.return_value = ["orphan_aaa"]

    before = time.monotonic()
    new_ts = _check_orphans(repo, last_log_at=None, interval=ORPHAN_LOG_INTERVAL_SECONDS)
    after = time.monotonic()

    assert new_ts is not None
    assert before <= new_ts <= after


def test_orphan_check_returns_unchanged_timestamp_when_no_orphans():
    """
    _check_orphans returns last_log_at unchanged when no orphans are found.
    """
    repo = MagicMock()
    repo.list_orphans.return_value = []

    sentinel = 123.456
    result = _check_orphans(repo, last_log_at=sentinel, interval=ORPHAN_LOG_INTERVAL_SECONDS)
    assert result == sentinel
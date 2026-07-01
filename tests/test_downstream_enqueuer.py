"""
tests/test_downstream_enqueuer.py

Unit tests for the DownstreamEnqueuer Protocol and its concrete
DeliveryEnqueuer implementation.

No database required. All repository dependencies are MagicMock. The
adapter is a pure forwarder so all coverage is achievable at the unit
level. The underlying repositories are integration-tested separately in
test_pipeline_repositories.py.
"""

from datetime import UTC, datetime
from unittest.mock import MagicMock

from app.services.delivery.downstream_enqueuer import (
    DeliveryEnqueuer,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_pdf_repo(delivery_email: str = "gp@example.com"):
    repo = MagicMock()
    repo.get_delivery_email.return_value = delivery_email
    return repo


def _make_submission_repo(
    condition_label: str = "Urinary Tract Infection",
    submitted_at: datetime | None = None,
):
    repo = MagicMock()
    if submitted_at is None:
        submitted_at = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)
    repo.get_submission.return_value = {
        "condition_label": condition_label,
        "submitted_at": submitted_at,
    }
    return repo


def _make_delivery_repo():
    return MagicMock()


def _make_enqueuer(
    pdf_repo=None,
    submission_repo=None,
    delivery_repo=None,
) -> DeliveryEnqueuer:
    return DeliveryEnqueuer(
        pdf_repo=pdf_repo or _make_pdf_repo(),
        submission_repo=submission_repo or _make_submission_repo(),
        delivery_repo=delivery_repo or _make_delivery_repo(),
    )


# ---------------------------------------------------------------------------
# Protocol structural compliance
# ---------------------------------------------------------------------------


def test_delivery_enqueuer_has_protocol_shape():
    """
    DeliveryEnqueuer must satisfy the structural shape of DownstreamEnqueuer:
    a callable `enqueue` method accepting a keyword-only `submission_id`
    argument.

    DownstreamEnqueuer is a Protocol — isinstance is not used at runtime
    (the Protocol is not @runtime_checkable). This test asserts the
    method exists and is callable. If the Protocol signature changes,
    this test should still pass; the typechecker is the primary enforcer.
    """
    enqueuer = _make_enqueuer()
    assert callable(getattr(enqueuer, "enqueue", None))
    # Confirm the method accepts the expected keyword argument by calling it.
    enqueuer.enqueue(submission_id="sub-aaa")


# ---------------------------------------------------------------------------
# DeliveryEnqueuer behaviour
# ---------------------------------------------------------------------------


def test_delivery_enqueuer_reads_email_from_pdf_repo():
    """
    enqueue must look up the delivery email from pdf_repo, not from
    submission_repo or anywhere else.
    """
    pdf_repo = _make_pdf_repo(delivery_email="practice@nhs.net")
    enqueuer = _make_enqueuer(pdf_repo=pdf_repo)

    enqueuer.enqueue(submission_id="sub-aaa")

    pdf_repo.get_delivery_email.assert_called_once_with("sub-aaa")


def test_delivery_enqueuer_reads_condition_and_submitted_at_from_submission_repo():
    """
    enqueue must look up condition_label and submitted_at from
    submission_repo.
    """
    submission_repo = _make_submission_repo()
    enqueuer = _make_enqueuer(submission_repo=submission_repo)

    enqueuer.enqueue(submission_id="sub-bbb")

    submission_repo.get_submission.assert_called_once_with("sub-bbb")


def test_delivery_enqueuer_forwards_to_delivery_repo_create_job():
    """
    enqueue must call delivery_repo.create_job with the submission_id and
    the values fetched from the other two repos.
    """
    submitted_at = datetime(2026, 3, 15, 9, 30, 0, tzinfo=UTC)
    pdf_repo = _make_pdf_repo(delivery_email="practice@nhs.net")
    submission_repo = _make_submission_repo(
        condition_label="Sore throat",
        submitted_at=submitted_at,
    )
    delivery_repo = _make_delivery_repo()
    enqueuer = _make_enqueuer(
        pdf_repo=pdf_repo,
        submission_repo=submission_repo,
        delivery_repo=delivery_repo,
    )

    enqueuer.enqueue(submission_id="sub-ccc")

    delivery_repo.create_job.assert_called_once_with(
        submission_id="sub-ccc",
        to_email="practice@nhs.net",
        condition_label="Sore throat",
        submitted_at=submitted_at,
    )


def test_delivery_enqueuer_returns_none():
    """
    enqueue must return None. The Protocol contract is a fire-and-forget
    write; callers do not rely on a return value.
    """
    enqueuer = _make_enqueuer()
    result = enqueuer.enqueue(submission_id="sub-ddd")
    assert result is None


def test_delivery_enqueuer_propagates_pdf_repo_error():
    """
    Errors from pdf_repo.get_delivery_email must propagate. The PDF
    worker treats any exception from enqueue as job failure and triggers
    its backoff/retry logic. The adapter must not swallow.
    """
    pdf_repo = _make_pdf_repo()
    pdf_repo.get_delivery_email.side_effect = RuntimeError("pdf_jobs row missing")
    enqueuer = _make_enqueuer(pdf_repo=pdf_repo)

    try:
        enqueuer.enqueue(submission_id="sub-eee")
    except RuntimeError as exc:
        assert "pdf_jobs row missing" in str(exc)
    else:
        raise AssertionError("RuntimeError was not propagated")


def test_delivery_enqueuer_propagates_submission_repo_error():
    """
    Errors from submission_repo.get_submission must propagate.
    """
    submission_repo = _make_submission_repo()
    submission_repo.get_submission.side_effect = RuntimeError("submission missing")
    enqueuer = _make_enqueuer(submission_repo=submission_repo)

    try:
        enqueuer.enqueue(submission_id="sub-fff")
    except RuntimeError as exc:
        assert "submission missing" in str(exc)
    else:
        raise AssertionError("RuntimeError was not propagated")


def test_delivery_enqueuer_propagates_delivery_repo_error():
    """
    Errors from delivery_repo.create_job must propagate.
    """
    delivery_repo = _make_delivery_repo()
    delivery_repo.create_job.side_effect = RuntimeError("DB unavailable")
    enqueuer = _make_enqueuer(delivery_repo=delivery_repo)

    try:
        enqueuer.enqueue(submission_id="sub-ggg")
    except RuntimeError as exc:
        assert "DB unavailable" in str(exc)
    else:
        raise AssertionError("RuntimeError was not propagated")


def test_delivery_enqueuer_call_order_reads_before_writes():
    """
    Both reads must complete before delivery_repo.create_job is called.
    If create_job fired before the reads resolved, a failure on the
    write would leave us unable to retry cleanly (the worker's idempotent
    retry depends on the underlying ON CONFLICT DO NOTHING; this still
    works, but the ordering reflects the natural data dependency).
    """
    call_order = []
    pdf_repo = _make_pdf_repo()
    pdf_repo.get_delivery_email.side_effect = lambda *a, **kw: (
        call_order.append("get_delivery_email") or "gp@example.com"
    )
    submission_repo = _make_submission_repo()
    submission_repo.get_submission.side_effect = lambda *a, **kw: (
        call_order.append("get_submission")
        or {
            "condition_label": "X",
            "submitted_at": datetime.now(UTC),
        }
    )
    delivery_repo = _make_delivery_repo()
    delivery_repo.create_job.side_effect = lambda *a, **kw: call_order.append("create_job")

    enqueuer = _make_enqueuer(
        pdf_repo=pdf_repo,
        submission_repo=submission_repo,
        delivery_repo=delivery_repo,
    )
    enqueuer.enqueue(submission_id="sub-hhh")

    assert call_order == ["get_delivery_email", "get_submission", "create_job"], (
        f"Unexpected call order: {call_order}"
    )

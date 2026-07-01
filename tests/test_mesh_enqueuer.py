"""
tests/test_mesh_enqueuer.py

Unit tests for the MeshEnqueuer implementation of the DownstreamEnqueuer
Protocol.

No database required. The MeshRepository dependency is a MagicMock. The
adapter is a pure forwarder so all coverage is achievable at the unit level.
MeshRepository itself is integration-tested separately in
tests/integration/test_mesh_repository.py.
"""

from unittest.mock import MagicMock

from app.services.delivery.mesh_enqueuer import MeshEnqueuer

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_enqueuer(
    mesh_repo=None,
    recipient_mailbox_id: str = "X26HC001",
) -> MeshEnqueuer:
    return MeshEnqueuer(
        mesh_repo=mesh_repo or MagicMock(),
        recipient_mailbox_id=recipient_mailbox_id,
    )


# ---------------------------------------------------------------------------
# Protocol structural compliance
# ---------------------------------------------------------------------------


def test_mesh_enqueuer_has_protocol_shape():
    """
    MeshEnqueuer must satisfy the structural shape of DownstreamEnqueuer: a
    callable `enqueue` method accepting a keyword-only `submission_id`
    argument. DownstreamEnqueuer is a Protocol (not @runtime_checkable), so
    this asserts the method exists and is callable by invoking it.
    """
    enqueuer = _make_enqueuer()
    assert callable(getattr(enqueuer, "enqueue", None))
    enqueuer.enqueue(submission_id="sub-aaa")


# ---------------------------------------------------------------------------
# Behaviour
# ---------------------------------------------------------------------------


def test_mesh_enqueuer_forwards_to_create_job():
    """
    enqueue must call mesh_repo.create_job with the submission_id and the
    recipient mailbox supplied to the constructor.
    """
    mesh_repo = MagicMock()
    enqueuer = _make_enqueuer(
        mesh_repo=mesh_repo,
        recipient_mailbox_id="X26HC999",
    )

    enqueuer.enqueue(submission_id="sub-bbb")

    mesh_repo.create_job.assert_called_once_with(
        submission_id="sub-bbb",
        recipient_mailbox_id="X26HC999",
    )


def test_mesh_enqueuer_uses_constructor_recipient_not_a_default():
    """
    The recipient must come from the constructor, not a hardcoded value. Two
    enqueuers configured with different recipients must forward different
    values for the same submission_id.
    """
    repo_a = MagicMock()
    repo_b = MagicMock()
    _make_enqueuer(mesh_repo=repo_a, recipient_mailbox_id="AAA").enqueue(submission_id="sub-ccc")
    _make_enqueuer(mesh_repo=repo_b, recipient_mailbox_id="BBB").enqueue(submission_id="sub-ccc")

    assert repo_a.create_job.call_args.kwargs["recipient_mailbox_id"] == "AAA"
    assert repo_b.create_job.call_args.kwargs["recipient_mailbox_id"] == "BBB"


def test_mesh_enqueuer_returns_none():
    """
    enqueue must return None. The Protocol contract is a fire-and-forget write;
    callers do not rely on a return value (and create_job's returned id is
    intentionally discarded).
    """
    mesh_repo = MagicMock()
    mesh_repo.create_job.return_value = "some-uuid"
    enqueuer = _make_enqueuer(mesh_repo=mesh_repo)

    result = enqueuer.enqueue(submission_id="sub-ddd")

    assert result is None


def test_mesh_enqueuer_propagates_repo_error():
    """
    Errors from mesh_repo.create_job must propagate. The PDF worker treats any
    exception from enqueue as job failure and triggers its backoff/retry logic.
    The adapter must not swallow.
    """
    mesh_repo = MagicMock()
    mesh_repo.create_job.side_effect = RuntimeError("DB unavailable")
    enqueuer = _make_enqueuer(mesh_repo=mesh_repo)

    try:
        enqueuer.enqueue(submission_id="sub-eee")
    except RuntimeError as exc:
        assert "DB unavailable" in str(exc)
    else:
        raise AssertionError("RuntimeError was not propagated")

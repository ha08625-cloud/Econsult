"""
Integration tests for ``MeshClient`` against the local MESH sandbox.

DB-FREE INTEGRATION TEST. Unlike the Postgres integration tests described in
docs/arch_testing.md, this module never touches a database -- it exercises the
``MeshClient`` mTLS + HMAC code path against the local mesh-sandbox running
behind its nginx mTLS proxy (see sandbox/README.md). It therefore deliberately
does NOT carry the ``TEST_DATABASE_URL`` guardrail that every Postgres
integration module carries. This is the one documented exception to that
convention; the rationale is recorded in docs/arch_testing.md.

It is guarded solely on ``MESH_BASE_URL``: if the sandbox is not configured the
whole module is skipped. CI never runs the sandbox, so ``MESH_BASE_URL`` is
unset there and these tests skip. The remaining MESH env vars are read with a
direct subscript (no defaults): if ``MESH_BASE_URL`` is set but another var is
missing, that is a misconfigured ``.env.sandbox`` and a ``KeyError`` is the
correct, loud signal.

Run locally with the sandbox up::

    make sandbox-up
    make test-integration   # with .env.sandbox sourced into the environment
"""

import os
import re

import pytest

pytestmark = pytest.mark.integration

if not os.environ.get("MESH_BASE_URL"):
    pytest.skip(
        "MESH sandbox not configured (MESH_BASE_URL unset); skipping DB-free "
        "MESH integration tests.",
        allow_module_level=True,
    )

# Imports and config reads happen AFTER the skip guard so that an unconfigured
# environment (e.g. CI) skips cleanly without importing application code or
# raising on missing vars. E402 here is intentional and matches the
# guardrail-then-imports pattern used by the Postgres integration modules.
import uuid  # noqa: E402

from app.services.delivery.mesh import (  # noqa: E402
    MeshClient,
    MeshTransientError,
)

# Direct subscript, no .get(), no defaults: a missing var is a hard failure.
_BASE_URL = os.environ["MESH_BASE_URL"]
_MAILBOX_ID = os.environ["MESH_MAILBOX_ID"]
_MAILBOX_PASSWORD = os.environ["MESH_MAILBOX_PASSWORD"]
_SHARED_KEY = os.environ["MESH_SHARED_KEY"]
_CA_CERT_PATH = os.environ["MESH_CA_CERT_PATH"]
_CLIENT_CERT_PATH = os.environ["MESH_CLIENT_CERT_PATH"]
_CLIENT_KEY_PATH = os.environ["MESH_CLIENT_KEY_PATH"]

# The mock GP practice mailbox pre-created in the sandbox fixture
# (mailbox_id "TARGET_MAILBOX", ODS A99999). See sandbox/mailboxes.jsonl.
_RECIPIENT_MAILBOX_ID = "TARGET_MAILBOX"

_HEX_32 = re.compile(r"[0-9A-Fa-f]{32}")


def _make_client(**overrides) -> MeshClient:
    kwargs = dict(
        base_url=_BASE_URL,
        mailbox_id=_MAILBOX_ID,
        mailbox_password=_MAILBOX_PASSWORD,
        shared_key=_SHARED_KEY,
        ca_cert_path=_CA_CERT_PATH,
        client_cert_path=_CLIENT_CERT_PATH,
        client_key_path=_CLIENT_KEY_PATH,
    )
    kwargs.update(overrides)
    return MeshClient(**kwargs)


def _send_one(client: MeshClient) -> str:
    return client.send_message(
        recipient_mailbox_id=_RECIPIENT_MAILBOX_ID,
        payload_bytes=b"%PDF-1.4 integration-test payload",
        workflow_id="TEST_WORKFLOW",
        mex_localid=str(uuid.uuid4()),
        content_type="application/pdf",
    )


def test_handshake_succeeds():
    """The startup handshake against our sender mailbox completes cleanly."""
    _make_client().handshake()  # raises on failure


def test_send_returns_hex_message_id():
    message_id = _send_one(_make_client())
    assert _HEX_32.fullmatch(message_id), message_id


def test_wrong_shared_key_is_transient():
    """A bad signature is a 403 with empty errorCode -> retryable."""
    client = _make_client(shared_key="DEFINITELY-WRONG-KEY")
    with pytest.raises(MeshTransientError):
        client.handshake()


def test_get_message_status_returns_expected_fields():
    client = _make_client()
    message_id = _send_one(client)
    record = client.get_message_status(message_id=message_id)
    assert isinstance(record, dict)
    # Load-bearing tracking fields per docs/nhs_integration_reference.md.
    for field in ("messageId", "status", "statusSuccess"):
        assert field in record, f"missing tracking field: {field}"


def test_nonexistent_client_cert_is_transient():
    """A missing client cert file surfaces as a transport error -> transient.

    requests raises OSError from its cert-file check; the client classifies
    transport-layer failures as transient. (The authoritative protection
    against a missing cert file is the Phase 3 worker startup fail-fast.)
    """
    client = _make_client(client_cert_path="/no/such/client.pem")
    with pytest.raises(MeshTransientError):
        client.handshake()
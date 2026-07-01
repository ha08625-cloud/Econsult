"""
Unit tests for ``MeshClient`` (Phase 2a).

No marker -> these run in the fast ``make test`` suite and in CI. No database,
no network: ``requests`` is mocked. Sandbox-backed checks live in
``tests/test_mesh_client_integration.py``.

The golden auth-header value below is computed independently (HMAC-SHA256 of
the documented canonical string) and pinned as a literal. If a refactor changes
the header construction, this test fails -- which is the point.
"""

import uuid
from unittest.mock import MagicMock

import pytest
import requests

from app.services.delivery.mesh import (
    MeshClient,
    MeshTerminalError,
    MeshTransientError,
)

# --- fixed inputs for deterministic assertions -----------------------------

_BASE_URL = "https://mesh.example.test:8700"
_MAILBOX_ID = "SENDER_MAILBOX"
_MAILBOX_PASSWORD = "password"
_SHARED_KEY = "TestKey"
_CA_CERT_PATH = "/certs/ca.pem"
_CLIENT_CERT_PATH = "/certs/client.pem"
_CLIENT_KEY_PATH = "/certs/client.key"

_FIXED_NONCE = "11111111-1111-1111-1111-111111111111"
_FIXED_TIMESTAMP = "202405311200"

# HMAC-SHA256("TestKey",
#   "SENDER_MAILBOX:1111...1111:1:password:202405311200") hex digest.
_GOLDEN_HEADER = (
    "NHSMESH SENDER_MAILBOX:11111111-1111-1111-1111-111111111111:1:"
    "202405311200:"
    "f822e3c00b3c80af4e295c26bc4f720cd7906048bf8364b76798007f3f63e6c7"
)

_HEX_MESSAGE_ID = "093D3376E61747D7BC1E077C8E5F1043"


# --- test doubles ----------------------------------------------------------

_UNSET = object()


class _FakeResponse:
    """Minimal stand-in for ``requests.Response``.

    ``json()`` raises ``ValueError`` (as the real one does on a non-JSON body)
    when no ``json_body`` was supplied.
    """

    def __init__(self, status_code, *, json_body=_UNSET, text=""):
        self.status_code = status_code
        self._json_body = json_body
        self.text = text

    def json(self):
        if self._json_body is _UNSET:
            raise ValueError("No JSON body")
        return self._json_body


def _make_client():
    return MeshClient(
        base_url=_BASE_URL,
        mailbox_id=_MAILBOX_ID,
        mailbox_password=_MAILBOX_PASSWORD,
        shared_key=_SHARED_KEY,
        ca_cert_path=_CA_CERT_PATH,
        client_cert_path=_CLIENT_CERT_PATH,
        client_key_path=_CLIENT_KEY_PATH,
    )


def _client_with_mock_session():
    """Return ``(client, mock_session)`` with the transport mocked out."""
    client = _make_client()
    mock_session = MagicMock()
    client._session = mock_session
    return client, mock_session


# --- construction / TLS configuration --------------------------------------


def test_session_built_with_cert_and_verify():
    """The Session must present our client cert and verify the server cert."""
    client = _make_client()
    assert client._session.cert == (_CLIENT_CERT_PATH, _CLIENT_KEY_PATH)
    assert client._session.verify == _CA_CERT_PATH


def test_construction_does_not_touch_the_filesystem():
    """Constructing with non-existent cert paths must not raise.

    The files are opened lazily by ``requests`` on first use; validating they
    exist is the Phase 3 worker entry point's job.
    """
    MeshClient(
        base_url=_BASE_URL,
        mailbox_id=_MAILBOX_ID,
        mailbox_password=_MAILBOX_PASSWORD,
        shared_key=_SHARED_KEY,
        ca_cert_path="/no/such/ca.pem",
        client_cert_path="/no/such/client.pem",
        client_key_path="/no/such/client.key",
    )


# --- auth header (golden) ---------------------------------------------------


def test_auth_header_golden():
    client = _make_client()
    header = client._build_auth_header(nonce=_FIXED_NONCE, timestamp=_FIXED_TIMESTAMP)
    assert header == _GOLDEN_HEADER


def test_auth_header_regenerated_per_call():
    """Two calls with generated (not injected) inputs differ via the nonce."""
    client = _make_client()
    first = client._build_auth_header()
    second = client._build_auth_header()
    assert first != second


def test_auth_header_excludes_password_but_signs_it():
    client = _make_client()
    header = client._build_auth_header(nonce=_FIXED_NONCE, timestamp=_FIXED_TIMESTAMP)
    # The header value must not leak the password...
    assert _MAILBOX_PASSWORD not in header
    # ...but the signature depends on it: a different password -> different hmac.
    other = MeshClient(
        base_url=_BASE_URL,
        mailbox_id=_MAILBOX_ID,
        mailbox_password="different-password",
        shared_key=_SHARED_KEY,
        ca_cert_path=_CA_CERT_PATH,
        client_cert_path=_CLIENT_CERT_PATH,
        client_key_path=_CLIENT_KEY_PATH,
    )
    assert other._build_auth_header(nonce=_FIXED_NONCE, timestamp=_FIXED_TIMESTAMP) != header


# --- send_message: success --------------------------------------------------


def test_send_message_returns_hex_message_id():
    client, session = _client_with_mock_session()
    session.request.return_value = _FakeResponse(202, json_body={"messageID": _HEX_MESSAGE_ID})

    result = client.send_message(
        recipient_mailbox_id="TARGET_MAILBOX",
        payload_bytes=b"%PDF-1.4 ...",
        workflow_id="REFERRAL_LETTER",
        mex_localid=str(uuid.uuid4()),
        content_type="application/pdf",
    )

    assert result == _HEX_MESSAGE_ID
    # The id is opaque text and must be returned byte-for-byte. It happens to
    # be parseable by uuid.UUID(), but parsing NORMALISES it (lowercases and
    # inserts hyphens), which is exactly why it is stored as TEXT, not UUID:
    # a normalised value would no longer match what MESH echoes back via the
    # tracking endpoint.
    assert result.isupper()
    assert len(result) == 32
    assert "-" not in result
    assert str(uuid.UUID(result)) != result  # normalisation would corrupt it


def test_send_message_targets_outbox_with_expected_headers():
    client, session = _client_with_mock_session()
    session.request.return_value = _FakeResponse(202, json_body={"messageID": _HEX_MESSAGE_ID})

    client.send_message(
        recipient_mailbox_id="TARGET_MAILBOX",
        payload_bytes=b"data",
        workflow_id="REFERRAL_LETTER",
        mex_localid="local-123",
        content_type="application/pdf",
    )

    args, kwargs = session.request.call_args
    method, url = args
    assert method == "POST"
    assert url == f"{_BASE_URL}/messageexchange/{_MAILBOX_ID}/outbox"
    headers = kwargs["headers"]
    assert headers["Mex-From"] == _MAILBOX_ID
    assert headers["Mex-To"] == "TARGET_MAILBOX"
    assert headers["Mex-WorkflowID"] == "REFERRAL_LETTER"
    assert headers["Mex-LocalID"] == "local-123"
    assert headers["Content-Type"] == "application/pdf"
    assert headers["Authorization"].startswith("NHSMESH ")
    assert kwargs["data"] == b"data"


# --- send_message: malformed success body -> terminal -----------------------


def test_send_message_malformed_202_body_is_terminal():
    client, session = _client_with_mock_session()
    session.request.return_value = _FakeResponse(202, text="not json")
    with pytest.raises(MeshTerminalError):
        client.send_message(
            recipient_mailbox_id="TARGET_MAILBOX",
            payload_bytes=b"data",
            workflow_id="WF",
            mex_localid="x",
            content_type="application/pdf",
        )


def test_send_message_202_without_message_id_is_terminal():
    client, session = _client_with_mock_session()
    session.request.return_value = _FakeResponse(202, json_body={"unexpected": 1})
    with pytest.raises(MeshTerminalError):
        client.send_message(
            recipient_mailbox_id="TARGET_MAILBOX",
            payload_bytes=b"data",
            workflow_id="WF",
            mex_localid="x",
            content_type="application/pdf",
        )


# --- error classification ---------------------------------------------------


def _send(client):
    return client.send_message(
        recipient_mailbox_id="TARGET_MAILBOX",
        payload_bytes=b"data",
        workflow_id="WF",
        mex_localid="x",
        content_type="application/pdf",
    )


def test_network_error_is_transient():
    client, session = _client_with_mock_session()
    session.request.side_effect = requests.ConnectionError("boom")
    with pytest.raises(MeshTransientError):
        _send(client)


def test_missing_cert_file_oserror_is_transient():
    """requests raises OSError on a missing cert file; classify it transient."""
    client, session = _client_with_mock_session()
    session.request.side_effect = OSError("Could not find the TLS certificate file")
    with pytest.raises(MeshTransientError):
        _send(client)


def test_5xx_is_transient():
    client, session = _client_with_mock_session()
    session.request.return_value = _FakeResponse(503, text="Service Unavailable")
    with pytest.raises(MeshTransientError):
        _send(client)


def test_403_empty_error_code_is_transient():
    """Auth/clock failure: empty errorCode -> retryable."""
    client, session = _client_with_mock_session()
    session.request.return_value = _FakeResponse(
        403,
        json_body={
            "errorEvent": "",
            "errorCode": "",
            "errorDescription": "Invalid Authentication Token",
        },
    )
    with pytest.raises(MeshTransientError):
        _send(client)


def test_403_populated_error_code_is_terminal():
    """A 403 carrying a business errorCode is a real denial -> terminal."""
    client, session = _client_with_mock_session()
    session.request.return_value = _FakeResponse(
        403,
        json_body={
            "errorEvent": "SEND",
            "errorCode": "07",
            "errorDescription": "Authorisation denied",
        },
    )
    with pytest.raises(MeshTerminalError):
        _send(client)


def test_417_unregistered_recipient_is_terminal():
    client, session = _client_with_mock_session()
    session.request.return_value = _FakeResponse(
        417,
        json_body={
            "errorEvent": "SEND",
            "errorCode": "12",
            "errorDescription": "Unregistered to address",
        },
    )
    with pytest.raises(MeshTerminalError):
        _send(client)


def test_other_4xx_is_terminal():
    client, session = _client_with_mock_session()
    session.request.return_value = _FakeResponse(400, text="Bad Request")
    with pytest.raises(MeshTerminalError):
        _send(client)


# --- get_message_status -----------------------------------------------------


def test_get_message_status_uses_query_string_and_returns_dict():
    client, session = _client_with_mock_session()
    tracking = {
        "messageId": _HEX_MESSAGE_ID,
        "status": "Acknowledged",
        "statusSuccess": "SUCCESS",
    }
    session.request.return_value = _FakeResponse(200, json_body=tracking)

    result = client.get_message_status(message_id=_HEX_MESSAGE_ID)

    assert result == tracking
    args, kwargs = session.request.call_args
    method, url = args
    assert method == "GET"
    # Query-string form: the message id is in params, not the path.
    assert url == (f"{_BASE_URL}/messageexchange/{_MAILBOX_ID}/outbox/tracking")
    assert kwargs["params"] == {"messageID": _HEX_MESSAGE_ID}


def test_get_message_status_404_is_terminal():
    client, session = _client_with_mock_session()
    session.request.return_value = _FakeResponse(404, text="Not Found")
    with pytest.raises(MeshTerminalError):
        client.get_message_status(message_id="does-not-exist")


def test_get_message_status_unparseable_body_is_terminal():
    client, session = _client_with_mock_session()
    session.request.return_value = _FakeResponse(200, text="<html>nope</html>")
    with pytest.raises(MeshTerminalError):
        client.get_message_status(message_id=_HEX_MESSAGE_ID)


# --- handshake --------------------------------------------------------------


def test_handshake_success_does_not_raise():
    client, session = _client_with_mock_session()
    session.request.return_value = _FakeResponse(200, json_body={"mailboxId": _MAILBOX_ID})
    client.handshake()  # no exception
    args, _ = session.request.call_args
    method, url = args
    assert method == "POST"
    assert url == f"{_BASE_URL}/messageexchange/{_MAILBOX_ID}"


def test_handshake_auth_failure_is_transient():
    client, session = _client_with_mock_session()
    session.request.return_value = _FakeResponse(
        403, json_body={"errorCode": "", "errorDescription": "bad token"}
    )
    with pytest.raises(MeshTransientError):
        client.handshake()

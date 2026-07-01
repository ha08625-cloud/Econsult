"""
MESH client library (Phase 2a).

A thin, synchronous HTTP client for the NHS MESH API. Responsibilities:

  - present a client certificate and verify the server certificate on every
    request (mutual TLS), with no environment-driven bypass;
  - construct the per-request ``NHSMESH`` HMAC authorization header;
  - perform the startup handshake, send a message, and read a message's
    tracking status;
  - classify failures into ``MeshTransientError`` (retryable) and
    ``MeshTerminalError`` (not retryable).

What this module does NOT do (by design, see docs/mesh_integration_plan.md):

  - It does not read environment variables. The constructor takes explicit
    values; the worker entry point (Phase 3) reads the environment and owns the
    fail-fast checks.
  - It does not touch the filesystem at construction time. The three cert paths
    are handed to a ``requests.Session`` and are only opened when the first
    request is made. Validating that the files exist is the worker entry
    point's job (Phase 3), per docs/arch_security.md section 8.
  - It does not build payloads, talk to the database, or decide retry policy.
    The dispatcher (Phase 3) owns those.

Protocol facts (auth header layout, endpoint paths, response shapes, error
classification) are recorded in docs/nhs_integration_reference.md, which is the
authoritative source. Where the integration plan's prose and that reference
differ, the reference wins.
"""

import hashlib
import hmac
import logging
import uuid
from datetime import UTC, datetime

import requests

from app.services.delivery.mesh.errors import (
    MeshTerminalError,
    MeshTransientError,
)

logger = logging.getLogger(__name__)

# Matches the outbound-HTTP timeout used by the email delivery service.
_DEFAULT_TIMEOUT_SECONDS = 30

# nonce_count exists in the MESH auth scheme for replay-prevention designs that
# increment it per nonce. We send a fresh nonce on every request, so a constant
# "1" is correct for our usage. See docs/nhs_integration_reference.md.
_NONCE_COUNT = "1"

# MESH timestamps are UTC at minute granularity: YYYYMMDDHHmm (no seconds).
_TIMESTAMP_FORMAT = "%Y%m%d%H%M"


class MeshClient:
    """Synchronous MESH API client.

    All three cert paths are mandatory ``str`` values. There is no toggle to
    disable verification and no ``None`` path: a misconfiguration cannot
    silently degrade to one-way TLS or plain HTTPS (docs/arch_security.md
    section 8). The same mTLS code path runs against the local sandbox (behind
    its nginx mTLS proxy) and against production; only the *contents* of the
    cert files differ.

    Constructor arguments are keyword-only so the several same-typed string
    inputs cannot be transposed by accident (e.g. swapping the cert and key
    paths).
    """

    def __init__(
        self,
        *,
        base_url: str,
        mailbox_id: str,
        mailbox_password: str,
        shared_key: str,
        ca_cert_path: str,
        client_cert_path: str,
        client_key_path: str,
        timeout: float = _DEFAULT_TIMEOUT_SECONDS,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._mailbox_id = mailbox_id
        self._mailbox_password = mailbox_password
        self._shared_key = shared_key
        self._ca_cert_path = ca_cert_path
        self._client_cert_path = client_cert_path
        self._client_key_path = client_key_path
        self._timeout = timeout

        # Build the session once. Assigning cert/verify does NOT open the files;
        # requests reads them lazily on the first request. So construction stays
        # filesystem-free, as required.
        self._session = requests.Session()
        self._session.cert = (client_cert_path, client_key_path)
        self._session.verify = ca_cert_path

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def handshake(self) -> None:
        """Perform the mandatory startup handshake.

        ``POST /messageexchange/<mailbox_id>``. A 2xx response (200 in the
        sandbox, body ``{"mailboxId": ...}``) means the credentials and
        connectivity are good. Any non-2xx is classified and raised. Intended
        to be called once per process at startup, before any send, so
        credential/mailbox/connectivity problems surface immediately rather
        than on the first patient submission.
        """
        url = f"{self._base_url}/messageexchange/{self._mailbox_id}"
        self._request("POST", url, context="handshake")

    def send_message(
        self,
        *,
        recipient_mailbox_id: str,
        payload_bytes: bytes,
        workflow_id: str,
        mex_localid: str,
        content_type: str,
    ) -> str:
        """Send a message and return the MESH ``messageID``.

        ``POST /messageexchange/<mailbox_id>/outbox``. The path mailbox is our
        own (sender) mailbox; the recipient travels in the ``Mex-To`` header.

        Returns the ``messageID`` from the 202 body verbatim. Per the
        integration reference this is a 32-character (uppercase) hex string,
        NOT a hyphenated UUID -- it is returned and must be stored as opaque
        text. Case is preserved; the value is never normalised or parsed.

        Raises ``MeshTransientError`` on retryable failures and
        ``MeshTerminalError`` on permanent failures, including a 2xx with an
        unparseable or messageID-less body.
        """
        url = f"{self._base_url}/messageexchange/{self._mailbox_id}/outbox"
        extra_headers = {
            "Mex-From": self._mailbox_id,
            "Mex-To": recipient_mailbox_id,
            "Mex-WorkflowID": workflow_id,
            # Diagnostic correlation id. MESH persists it in the tracking record
            # but does NOT use it to deduplicate; it does not prevent duplicate
            # sends. See docs/nhs_integration_reference.md ("Idempotency").
            "Mex-LocalID": mex_localid,
            "Content-Type": content_type,
        }
        response = self._request(
            "POST",
            url,
            context="send_message",
            headers=extra_headers,
            data=payload_bytes,
        )
        return self._extract_message_id(response)

    def get_message_status(self, *, message_id: str) -> dict:
        """Return the tracking record for a sent message as a parsed dict.

        ``GET /messageexchange/<mailbox_id>/outbox/tracking?messageID=<id>``.
        Tracking is query-string only: the path-style
        ``.../tracking/<message_id>`` form returns 404
        (docs/nhs_integration_reference.md). ``params=`` produces the
        query-string form.

        Raises the same error types as the other methods; a 2xx with an
        unparseable body is terminal.
        """
        url = f"{self._base_url}/messageexchange/{self._mailbox_id}/outbox/tracking"
        response = self._request(
            "GET",
            url,
            context="get_message_status",
            params={"messageID": message_id},
        )
        try:
            return response.json()
        except ValueError as exc:
            raise MeshTerminalError(
                f"MESH get_message_status returned an unparseable body: {response.text[:200]!r}"
            ) from exc

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _build_auth_header(
        self,
        *,
        nonce: str | None = None,
        timestamp: str | None = None,
    ) -> str:
        """Construct the ``Authorization: NHSMESH ...`` header value.

        Two distinct colon-joined strings are involved (see
        docs/nhs_integration_reference.md, "Auth model"):

          - the HMAC *input* (signed with the shared key) includes the mailbox
            password::

                <mailbox_id>:<nonce>:<nonce_count>:<password>:<timestamp>

          - the header *value* after ``NHSMESH`` excludes the password and
            appends the hex HMAC, with the timestamp before it::

                <mailbox_id>:<nonce>:<nonce_count>:<timestamp>:<hmac>

        ``nonce`` and ``timestamp`` are injectable solely so the unit test can
        pin a deterministic golden value; in normal use a fresh UUID nonce and
        the current UTC minute are generated on every call (the header must be
        regenerated per request because of the minute-granularity timestamp).
        """
        if nonce is None:
            nonce = str(uuid.uuid4())
        if timestamp is None:
            timestamp = datetime.now(UTC).strftime(_TIMESTAMP_FORMAT)

        hmac_input = ":".join(
            [
                self._mailbox_id,
                nonce,
                _NONCE_COUNT,
                self._mailbox_password,
                timestamp,
            ]
        )
        digest = hmac.new(
            self._shared_key.encode("utf-8"),
            hmac_input.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

        token = ":".join([self._mailbox_id, nonce, _NONCE_COUNT, timestamp, digest])
        return f"NHSMESH {token}"

    def _request(
        self,
        method: str,
        url: str,
        *,
        context: str,
        headers: dict | None = None,
        **kwargs,
    ) -> requests.Response:
        """Issue a request with a freshly built auth header, then classify.

        A fresh ``Authorization`` header is built on every call, guaranteeing
        per-request regeneration. Transport-layer failures -- including a
        missing/unreadable client cert file, which ``requests`` raises as
        ``OSError`` from its cert check -- are classified transient. (The
        authoritative protection against a missing cert file is the Phase 3
        worker startup fail-fast, not this client.)
        """
        request_headers = {"Authorization": self._build_auth_header()}
        if headers:
            request_headers.update(headers)
        try:
            response = self._session.request(
                method,
                url,
                headers=request_headers,
                timeout=self._timeout,
                **kwargs,
            )
        except (requests.RequestException, OSError) as exc:
            raise MeshTransientError(f"MESH {context} transport error: {exc}") from exc
        self._raise_for_status(response, context=context)
        return response

    @staticmethod
    def _extract_message_id(response: requests.Response) -> str:
        """Pull the ``messageID`` string out of a successful send response."""
        try:
            body = response.json()
            message_id = body["messageID"]
        except (ValueError, KeyError, TypeError) as exc:
            raise MeshTerminalError(
                f"MESH send returned an unparseable or messageID-less body: {response.text[:200]!r}"
            ) from exc
        if not isinstance(message_id, str) or not message_id:
            raise MeshTerminalError(
                f"MESH send returned an empty or non-string messageID: {message_id!r}"
            )
        return message_id

    @staticmethod
    def _raise_for_status(response: requests.Response, *, context: str) -> None:
        """Classify a non-2xx response into transient vs terminal.

        Rules (docs/mesh_integration_plan.md 2a, docs/nhs_integration_reference.md):

          - 2xx                       -> success (no raise)
          - 5xx                       -> transient
          - 403, empty errorCode      -> transient (auth/clock failure, retry)
          - 403, populated errorCode  -> terminal (a real authorization denial)
          - any other 4xx             -> terminal (incl. 417 unregistered
                                         recipient, 404 message-not-found)
          - anything else non-2xx     -> terminal
        """
        status = response.status_code
        if 200 <= status < 300:
            return

        error_code = ""
        error_description = ""
        try:
            body = response.json()
            if isinstance(body, dict):
                error_code = (body.get("errorCode") or "").strip()
                error_description = (body.get("errorDescription") or "").strip()
        except ValueError:
            pass

        detail = error_description or response.text[:200]
        message = (
            f"MESH {context} failed: HTTP {status} "
            f"errorCode={error_code or '(empty)'} detail={detail!r}"
        )

        if status >= 500:
            raise MeshTransientError(message)
        if status == 403:
            if error_code:
                raise MeshTerminalError(message)
            raise MeshTransientError(message)
        # All remaining client errors (and any unexpected non-2xx) are terminal.
        raise MeshTerminalError(message)

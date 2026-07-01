"""
MESH dispatcher entry point.

Standalone Python process for the background MESH dispatcher worker.
Has no connection to the FastAPI application lifecycle.

Responsibilities:
- Validate required environment variables (fail-fast, no defaulting).
- Validate that the three mTLS certificate files exist on disk before
  constructing MeshClient (fail-fast per docs/arch_security.md section 8 —
  MeshClient itself deliberately never touches the filesystem).
- Instantiate MeshClient, repositories, and the payload builder.
- Perform the startup handshake with bounded transient retry
  (mesh_worker._handshake_with_retry): MeshTerminalError aborts
  immediately; MeshTransientError retries per
  HANDSHAKE_RETRY_DELAYS_SECONDS then aborts. mesh_jobs rows are durable
  throughout, so a handshake-abort/restart cycle delays delivery but
  loses nothing.
- Call run_worker (which loops indefinitely).

Does not run Alembic migrations. The FastAPI web service handles migrations
at deployment time; if Railway starts this worker first, it fails querying
mesh_jobs, exits, restarts, and eventually succeeds — same documented race
as the other workers.

Does not serve HTTP. Does not seed data.

Payload note: the only builder wired here is RawPdfPayloadBuilder, which is
PROVISIONAL (see app/services/delivery/mesh_payload.py and
mesh_integration_plan.md "Payload status: provisional"). Production
enablement of MESH_DELIVERY=1 is gated — see "Production enablement gates"
in mesh_integration_plan.md.

Environment variables:
    DATABASE_URL                      -- Postgres connection string (required)
    MESH_WORKER_POLL_INTERVAL_SECONDS -- seconds to sleep when queue is empty
                                         (required, positive integer)
    MESH_BASE_URL                     -- MESH API base URL (required)
    MESH_MAILBOX_ID                   -- our (sender) mailbox ID (required)
    MESH_MAILBOX_PASSWORD             -- auth input (required)
    MESH_SHARED_KEY                   -- HMAC secret (required)
    MESH_CA_CERT_PATH                 -- CA bundle path; file must exist (required)
    MESH_CLIENT_CERT_PATH             -- client cert path; file must exist (required)
    MESH_CLIENT_KEY_PATH              -- client key path; file must exist (required)
    MESH_WORKFLOW_ID                  -- Mex-WorkflowID for outgoing messages
                                         (required; production value is gated —
                                         see mesh_integration_plan.md)

MESH_RECIPIENT_MAILBOX_ID is deliberately NOT read here: the recipient was
stamped onto each mesh_jobs row at enqueue time by the PDF worker, so a
config change between enqueue and dispatch cannot misroute a queued
referral.
"""

import logging
import os
import sys

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)

from app.core.telemetry import init_telemetry  # noqa: E402

init_telemetry("mesh-dispatcher")

logger = logging.getLogger(__name__)


def _require_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        logger.critical("Required environment variable not set: %s", name)
        sys.exit(1)
    return value


def _require_file(path: str, env_name: str) -> None:
    """
    Abort startup if a configured certificate file does not exist on disk.

    MeshClient never touches the filesystem at construction by design, so
    this entry point owns the cert-file fail-fast (arch_security.md §8). A
    missing file would otherwise surface as an opaque TLS error on the
    first request.
    """
    if not os.path.exists(path):
        logger.critical("Certificate file configured in %s does not exist: %s", env_name, path)
        sys.exit(1)


def main() -> None:
    database_url = _require_env("DATABASE_URL")
    poll_interval_raw = _require_env("MESH_WORKER_POLL_INTERVAL_SECONDS")

    try:
        poll_interval = int(poll_interval_raw)
    except ValueError:
        logger.critical(
            "MESH_WORKER_POLL_INTERVAL_SECONDS must be an integer, got: %r",
            poll_interval_raw,
        )
        sys.exit(1)

    if poll_interval <= 0:
        logger.critical(
            "MESH_WORKER_POLL_INTERVAL_SECONDS must be a positive integer, got: %d",
            poll_interval,
        )
        sys.exit(1)

    base_url = _require_env("MESH_BASE_URL")
    mailbox_id = _require_env("MESH_MAILBOX_ID")
    mailbox_password = _require_env("MESH_MAILBOX_PASSWORD")
    shared_key = _require_env("MESH_SHARED_KEY")
    ca_cert_path = _require_env("MESH_CA_CERT_PATH")
    client_cert_path = _require_env("MESH_CLIENT_CERT_PATH")
    client_key_path = _require_env("MESH_CLIENT_KEY_PATH")
    workflow_id = _require_env("MESH_WORKFLOW_ID")

    _require_file(ca_cert_path, "MESH_CA_CERT_PATH")
    _require_file(client_cert_path, "MESH_CLIENT_CERT_PATH")
    _require_file(client_key_path, "MESH_CLIENT_KEY_PATH")

    # Import application modules after env validation so import errors are not
    # confused with missing configuration.
    import sentry_sdk

    from app.repositories.attachment_repository import AttachmentRepository
    from app.repositories.delivery_repository import DeliveryRepository
    from app.repositories.mesh_repository import MeshRepository
    from app.repositories.pdf_repository import PDFRepository
    from app.repositories.submission_repository import SubmissionRepository
    from app.services.delivery.mesh import MeshClient, MeshError
    from app.services.delivery.mesh_payload import RawPdfPayloadBuilder
    from app.services.delivery.mesh_worker import (
        _handshake_with_retry,
        run_worker,
    )

    sentry_sdk.set_tag("worker", "mesh_dispatcher")

    mesh_client = MeshClient(
        base_url=base_url,
        mailbox_id=mailbox_id,
        mailbox_password=mailbox_password,
        shared_key=shared_key,
        ca_cert_path=ca_cert_path,
        client_cert_path=client_cert_path,
        client_key_path=client_key_path,
    )

    mesh_repo = MeshRepository(database_url)
    attachment_repo = AttachmentRepository(database_url)
    pdf_repo = PDFRepository(database_url)
    submission_repo = SubmissionRepository(database_url)
    delivery_repo = DeliveryRepository(database_url)
    payload_builder = RawPdfPayloadBuilder()

    logger.info(
        "MESH dispatcher configuration: poll_interval=%ds base_url=%s "
        "mailbox_id=%s workflow_id=%s payload_builder=%s",
        poll_interval,
        base_url,
        mailbox_id,
        workflow_id,
        type(payload_builder).__name__,
    )

    try:
        _handshake_with_retry(mesh_client)
    except MeshError as exc:
        logger.critical(
            "MESH dispatcher: startup handshake failed after bounded retry — aborting. error=%s",
            exc,
        )
        sys.exit(1)

    run_worker(
        mesh_repo=mesh_repo,
        attachment_repo=attachment_repo,
        pdf_repo=pdf_repo,
        submission_repo=submission_repo,
        delivery_repo=delivery_repo,
        mesh_client=mesh_client,
        payload_builder=payload_builder,
        workflow_id=workflow_id,
        poll_interval=poll_interval,
    )


if __name__ == "__main__":
    main()

"""
PDF worker entry point.

Standalone Python process for the background PDF generation worker.
Has no connection to the FastAPI application lifecycle.

Responsibilities:
- Validate required environment variables.
- Select the downstream queue (email vs MESH) based on MESH_DELIVERY.
- Instantiate repositories.
- Look up the practice name from the database for use in PDF headers.
- Log startup configuration.
- Call run_worker (which loops indefinitely).

Does not run Alembic migrations. The FastAPI web service handles migrations
at deployment time. If Railway starts this worker before the web service
completes its migration run, the worker will fail querying pdf_jobs, exit,
be restarted by Railway, and eventually succeed. This is documented and
acceptable — Railway's restart behaviour is the sole recovery mechanism
for this race.

Does not serve HTTP. Does not seed data.

Environment variables:
    DATABASE_URL                     -- Postgres connection string (required)
    PDF_WORKER_POLL_INTERVAL_SECONDS -- seconds to sleep when queue is empty (required)
    MESH_DELIVERY                    -- "0" or "1" (required). "0" selects the
                                        email path (DeliveryEnqueuer). "1"
                                        selects the MESH path (MeshEnqueuer).
                                        No defaulting.
    MESH_RECIPIENT_MAILBOX_ID        -- required only when MESH_DELIVERY=1. The
                                        destination practice mailbox, a
                                        deployment-wide value copied onto each
                                        mesh_jobs row at enqueue time. A wrong
                                        value misroutes referrals silently, so
                                        it is deployment-controlled and
                                        fail-fast, never set via the admin UI.
    PRACTICE_ID                      -- optional. Used only to look up the
                                        practice name for PDF headers; the MESH
                                        path does not depend on it.
"""

import logging
import os
import sys

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)

from app.core.telemetry import init_telemetry  # noqa: E402

init_telemetry("pdf-worker")

logger = logging.getLogger(__name__)


def _require_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        logger.critical("Required environment variable not set: %s", name)
        sys.exit(1)
    return value


def _validate_mesh_delivery() -> str:
    """
    Validate the MESH_DELIVERY environment variable.

    Must be present and exactly "0" or "1". No defaulting is permitted —
    a misconfigured deployment must abort at startup per the Fail-Fast
    Configuration project invariant (see architecture.md).

    "0" selects the email path; "1" selects the MESH path. The MESH path's
    own required configuration (MESH_RECIPIENT_MAILBOX_ID) is validated in
    main() at the point of use, alongside the rest of the MESH wiring.

    Returns the validated value as a string. Exits the process on any
    invalid value.
    """
    value = os.environ.get("MESH_DELIVERY")
    if value is None:
        logger.critical(
            "Required environment variable not set: MESH_DELIVERY. "
            "Must be exactly '0' or '1'. No default is permitted."
        )
        sys.exit(1)
    if value not in ("0", "1"):
        logger.critical(
            "MESH_DELIVERY must be exactly '0' or '1', got: %r. "
            "No other values (including truthy strings) are accepted.",
            value,
        )
        sys.exit(1)
    return value


def main() -> None:
    database_url = _require_env("DATABASE_URL")
    poll_interval_raw = _require_env("PDF_WORKER_POLL_INTERVAL_SECONDS")
    mesh_delivery = _validate_mesh_delivery()  # exits on invalid; "0" or "1" reached here

    try:
        poll_interval = int(poll_interval_raw)
    except ValueError:
        logger.critical(
            "PDF_WORKER_POLL_INTERVAL_SECONDS must be an integer, got: %r",
            poll_interval_raw,
        )
        sys.exit(1)

    if poll_interval <= 0:
        logger.critical(
            "PDF_WORKER_POLL_INTERVAL_SECONDS must be a positive integer, got: %d",
            poll_interval,
        )
        sys.exit(1)

    # Import application modules after env validation so import errors are not
    # confused with missing configuration.
    import sentry_sdk
    from app.repositories.pdf_repository import PDFRepository
    from app.repositories.photo_repository import PhotoRepository
    from app.repositories.submission_repository import SubmissionRepository
    from app.repositories.attachment_repository import AttachmentRepository
    from app.repositories.delivery_repository import DeliveryRepository
    from app.repositories.practice_repository import PracticeRepository
    from app.repositories.mesh_repository import MeshRepository
    from app.services.delivery.downstream_enqueuer import DeliveryEnqueuer
    from app.services.delivery.mesh_enqueuer import MeshEnqueuer
    from app.services.delivery.pdf_worker import run_worker

    pdf_repo = PDFRepository(database_url)
    photo_repo = PhotoRepository(database_url)
    submission_repo = SubmissionRepository(database_url)
    attachment_repo = AttachmentRepository(database_url)
    delivery_repo = DeliveryRepository(database_url)
    practice_repo = PracticeRepository(database_url)

    # Look up practice name for PDF headers. Failures here are non-fatal —
    # the worker will run without a practice name in the PDF header rather
    # than refuse to start over a cosmetic field. This is independent of the
    # delivery path: the MESH recipient is configured via env, not PRACTICE_ID.
    practice_name = None
    practice_id = os.environ.get("PRACTICE_ID")
    if practice_id:
        try:
            practice = practice_repo.get_practice(practice_id)
            practice_name = practice.get("name") if practice else None
        except Exception as exc:
            logger.warning(
                "PDF worker: could not load practice name — PDFs will omit it. error=%s",
                exc,
            )
    else:
        logger.warning(
            "PDF worker: PRACTICE_ID not set — PDFs will omit the practice name."
        )

    # --- Downstream selection ---
    # The PDF worker is downstream-agnostic; the adapter is chosen here based on
    # MESH_DELIVERY. On the MESH path the recipient mailbox is a required,
    # deployment-controlled env var (fail-fast); a missing value aborts startup.
    if mesh_delivery == "1":
        recipient_mailbox_id = _require_env("MESH_RECIPIENT_MAILBOX_ID")
        mesh_repo = MeshRepository(database_url)
        downstream = MeshEnqueuer(
            mesh_repo=mesh_repo,
            recipient_mailbox_id=recipient_mailbox_id,
        )
        downstream_mode = "mesh"
    else:
        downstream = DeliveryEnqueuer(
            pdf_repo=pdf_repo,
            submission_repo=submission_repo,
            delivery_repo=delivery_repo,
        )
        downstream_mode = "email"

    sentry_sdk.set_tag("downstream_mode", downstream_mode)

    logger.info(
        "PDF worker configuration: poll_interval=%ds practice_name=%r "
        "mesh_delivery=%s downstream_mode=%s",
        poll_interval,
        practice_name,
        mesh_delivery,
        downstream_mode,
    )

    run_worker(
        pdf_repo=pdf_repo,
        photo_repo=photo_repo,
        submission_repo=submission_repo,
        attachment_repo=attachment_repo,
        downstream=downstream,
        poll_interval=poll_interval,
        practice_name=practice_name,
    )


if __name__ == "__main__":
    main()
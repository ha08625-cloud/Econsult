"""
PDF worker entry point.

Standalone Python process for the background PDF generation worker.
Has no connection to the FastAPI application lifecycle.

Responsibilities:
- Validate required environment variables.
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
    DATABASE_URL                    -- Postgres connection string (required)
    PDF_WORKER_POLL_INTERVAL_SECONDS -- seconds to sleep when queue is empty (required)
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


def main() -> None:
    database_url = _require_env("DATABASE_URL")
    poll_interval_raw = _require_env("PDF_WORKER_POLL_INTERVAL_SECONDS")

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
    from app.repositories.pdf_repository import PDFRepository
    from app.repositories.photo_repository import PhotoRepository
    from app.repositories.submission_repository import SubmissionRepository
    from app.repositories.attachment_repository import AttachmentRepository
    from app.repositories.delivery_repository import DeliveryRepository
    from app.repositories.practice_repository import PracticeRepository
    from app.services.delivery.pdf_worker import run_worker

    pdf_repo = PDFRepository(database_url)
    photo_repo = PhotoRepository(database_url)
    submission_repo = SubmissionRepository(database_url)
    attachment_repo = AttachmentRepository(database_url)
    delivery_repo = DeliveryRepository(database_url)
    practice_repo = PracticeRepository(database_url)

    # Look up practice name for PDF headers. Failures here are non-fatal —
    # the worker will run without a practice name in the PDF header rather
    # than refuse to start over a cosmetic field.
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

    logger.info(
        "PDF worker configuration: poll_interval=%ds practice_name=%r",
        poll_interval,
        practice_name,
    )

    run_worker(
        pdf_repo=pdf_repo,
        photo_repo=photo_repo,
        submission_repo=submission_repo,
        attachment_repo=attachment_repo,
        delivery_repo=delivery_repo,
        poll_interval=poll_interval,
        practice_name=practice_name,
    )


if __name__ == "__main__":
    main()
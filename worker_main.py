"""
Worker entry point.

Standalone Python process for the background delivery worker.
Has no connection to the FastAPI application lifecycle.

Responsibilities:
- Validate required environment variables (DATABASE_URL,
  WORKER_POLL_INTERVAL_SECONDS, WORKER_BATCH_LIMIT).
- Instantiate repositories and the delivery service.
- Log startup configuration.
- Call run_worker (which loops indefinitely).

Does not run Alembic migrations. The FastAPI app handles migrations at
deployment time. The worker assumes the schema is already up to date.

Does not serve HTTP. Does not seed data.

Environment variables:
    DATABASE_URL                   -- Postgres connection string (required)
    WORKER_POLL_INTERVAL_SECONDS   -- seconds to sleep when queue is empty (required)
    WORKER_BATCH_LIMIT             -- max submissions per loop iteration (required)
    DEV_MODE                       -- set to "1" or "true" for ConsoleDeliveryService
"""

import logging
import os
import sys

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)

logger = logging.getLogger(__name__)


def _require_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        logger.critical("Required environment variable not set: %s", name)
        sys.exit(1)
    return value


def _is_dev_mode() -> bool:
    return os.environ.get("DEV_MODE", "").lower() in ("1", "true")


def main() -> None:
    database_url = _require_env("DATABASE_URL")
    poll_interval_raw = _require_env("WORKER_POLL_INTERVAL_SECONDS")
    batch_limit_raw = _require_env("WORKER_BATCH_LIMIT")

    try:
        poll_interval = int(poll_interval_raw)
    except ValueError:
        logger.critical(
            "WORKER_POLL_INTERVAL_SECONDS must be an integer, got: %r",
            poll_interval_raw,
        )
        sys.exit(1)

    try:
        batch_limit = int(batch_limit_raw)
    except ValueError:
        logger.critical(
            "WORKER_BATCH_LIMIT must be an integer, got: %r",
            batch_limit_raw,
        )
        sys.exit(1)

    if poll_interval <= 0:
        logger.critical(
            "WORKER_POLL_INTERVAL_SECONDS must be a positive integer, got: %d",
            poll_interval,
        )
        sys.exit(1)

    if batch_limit <= 0:
        logger.critical(
            "WORKER_BATCH_LIMIT must be a positive integer, got: %d",
            batch_limit,
        )
        sys.exit(1)

    # Import application modules after env validation so import errors are not
    # confused with missing configuration.
    from app.repositories.submission_repository import SubmissionRepository
    from app.repositories.attachment_repository import AttachmentRepository
    from app.services.delivery.delivery_service import (
        ConsoleDeliveryService,
        EmailDeliveryService,
    )
    from app.services.delivery.delivery_worker import run_worker

    submission_repo = SubmissionRepository(database_url)
    attachment_repo = AttachmentRepository(database_url)

    if _is_dev_mode():
        delivery_service = ConsoleDeliveryService()
        logger.info("Worker running in DEV_MODE — email delivery disabled")
    else:
        delivery_service = EmailDeliveryService()

    logger.info(
        "Worker configuration: poll_interval=%ds batch_limit=%d dev_mode=%s",
        poll_interval,
        batch_limit,
        _is_dev_mode(),
    )

    run_worker(
        submission_repo=submission_repo,
        attachment_repo=attachment_repo,
        delivery_service=delivery_service,
        poll_interval=poll_interval,
        batch_limit=batch_limit,
    )


if __name__ == "__main__":
    main()
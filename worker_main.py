"""
Delivery worker entry point.

Standalone Python process for the background delivery worker.
Has no connection to the FastAPI application lifecycle.

Responsibilities:
- Validate required environment variables (DATABASE_URL,
  WORKER_POLL_INTERVAL_SECONDS).
- Instantiate repositories and the delivery service.
- Log startup configuration.
- Call run_worker (which loops indefinitely).

Does not run Alembic migrations. The FastAPI app handles migrations at
deployment time. The worker assumes the schema is already up to date.

Does not serve HTTP. Does not seed data.

Environment variables:
    DATABASE_URL                   -- Postgres connection string (required)
    WORKER_POLL_INTERVAL_SECONDS   -- seconds to sleep when queue is empty (required)
    MAILGUN_API_KEY                -- Mailgun HTTP delivery; only takes effect together
                                       with MAILGUN_DOMAIN -- see "Service selection" below
    MAILGUN_DOMAIN                 -- Mailgun HTTP delivery; only takes effect together
                                       with MAILGUN_API_KEY
    EMAIL_FROM                     -- required in production

Service selection:
    Delegates to app.core.email_mode.select_email_delivery_mode -- the same
    predicate the web service uses via app/core/settings.py.EmailSettings.
    Mailgun is selected only when BOTH MAILGUN_API_KEY and MAILGUN_DOMAIN
    are set (non-blank); otherwise SMTP is selected. A partial Mailgun
    configuration (one set, not both) logs a warning and falls through to
    SMTP, matching the web's behaviour, rather than attempting Mailgun and
    failing inside MailgunHttpDeliveryService.__init__.
"""

import logging
import os
import sys

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)

from app.core.telemetry import init_telemetry  # noqa: E402

init_telemetry("delivery-worker")

logger = logging.getLogger(__name__)


def _require_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        logger.critical("Required environment variable not set: %s", name)
        sys.exit(1)
    return value


def main() -> None:
    database_url = _require_env("DATABASE_URL")
    poll_interval_raw = _require_env("WORKER_POLL_INTERVAL_SECONDS")

    try:
        poll_interval = int(poll_interval_raw)
    except ValueError:
        logger.critical(
            "WORKER_POLL_INTERVAL_SECONDS must be an integer, got: %r",
            poll_interval_raw,
        )
        sys.exit(1)

    if poll_interval <= 0:
        logger.critical(
            "WORKER_POLL_INTERVAL_SECONDS must be a positive integer, got: %d",
            poll_interval,
        )
        sys.exit(1)

    # Import application modules after env validation so import errors are not
    # confused with missing configuration.
    from app.core.email_mode import has_partial_mailgun, select_email_delivery_mode
    from app.repositories.attachment_repository import AttachmentRepository
    from app.repositories.delivery_repository import DeliveryRepository
    from app.services.delivery.delivery_service import (
        EmailDeliveryService,
        MailgunHttpDeliveryService,
    )
    from app.services.delivery.delivery_worker import run_worker

    delivery_repo = DeliveryRepository(database_url)
    attachment_repo = AttachmentRepository(database_url)

    mailgun_api_key = os.environ.get("MAILGUN_API_KEY")
    mailgun_domain = os.environ.get("MAILGUN_DOMAIN")

    if select_email_delivery_mode(mailgun_api_key, mailgun_domain) == "mailgun":
        delivery_service = MailgunHttpDeliveryService()
        logger.info("Delivery worker: Mailgun HTTP API selected")
    else:
        if has_partial_mailgun(mailgun_api_key, mailgun_domain):
            # Deliberate fall-through to SMTP, but never silently: a typo in
            # MAILGUN_DOMAIN must not invisibly demote this worker to SMTP
            # without an operator-visible signal. Mirrors the warning logged
            # by app/core/settings.py on the web side.
            logger.warning(
                "Partial Mailgun configuration detected (one of MAILGUN_API_KEY / "
                "MAILGUN_DOMAIN is set, but not both). Falling through to SMTP "
                "delivery. If Mailgun was intended, set both variables."
            )
        delivery_service = EmailDeliveryService()
        logger.info("Delivery worker: SMTP selected")

    logger.info(
        "Delivery worker configuration: poll_interval=%ds",
        poll_interval,
    )

    run_worker(
        delivery_repo=delivery_repo,
        attachment_repo=attachment_repo,
        delivery_service=delivery_service,
        poll_interval=poll_interval,
    )


if __name__ == "__main__":
    main()

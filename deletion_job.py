"""
Nightly deletion job.

One-shot script executed by Railway cron at midnight. Deletes raw photo bytes
and generated PDF attachments for submissions that have been confirmed delivered.

What is deleted:
- submission_photos rows where the corresponding delivery_jobs.status = 'delivered'
- submission_attachments rows where the corresponding delivery_jobs.status = 'delivered'

What is never deleted:
- submission_records rows (permanent clinical record)
- pdf_jobs rows (operational audit trail)
- delivery_jobs rows (operational audit trail)
- Any rows where delivery_jobs.status is 'pending', 'provider_accepted',
  'sent', or 'failed'

Note on 'sent' status (SMTP/legacy path):
Jobs delivered via SMTP reach 'sent' status, not 'delivered'. Photos and
attachments for SMTP-delivered submissions are therefore NOT deleted by this
job. This is a known limitation while the system transitions to webhook-tracked
delivery. It will be addressed when the backup delivery service and notification
architecture are implemented.

Note on 'provider_accepted' status:
Jobs where Mailgun accepted the message but no 'delivered' webhook was received
remain in 'provider_accepted' status. Photos and attachments for these submissions
are not deleted until a 'delivered' webhook arrives. If the webhook never arrives
(provider outage, permanent delivery failure without a 'failed' event), data
retention is not bounded. This is an accepted known limitation until the backup
delivery and notification architecture is implemented.

Retention window (delivered webhook path):
- Minimum: ~5.25 hours (submission at 6:45pm, delivered webhook + midnight deletion)
- Maximum: ~24 hours (submission at practice open, delivered webhook next midnight)

This script exits with code 0 on success and code 1 on any database error.
Railway cron treats a non-zero exit code as a failure and will log it.

Environment variables:
    DATABASE_URL  -- Postgres connection string (required)
"""

import logging
import os
import sys

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)

from app.core.telemetry import init_telemetry  # noqa: E402

init_telemetry("deletion-cron")

logger = logging.getLogger(__name__)


def _require_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        logger.critical("Required environment variable not set: %s", name)
        sys.exit(1)
    return value


def run_deletion(database_url: str) -> None:
    """
    Delete photos and attachments for confirmed-delivered submissions.

    Uses a single database connection for both DELETE statements so they
    run within the same implicit transaction. Both statements identify
    their target rows by joining against delivery_jobs on submission_id
    and filtering on status = 'delivered'.

    Logs the number of rows deleted from each table. Raises on any
    database error so the caller can exit with a non-zero code.
    """
    # Import here so missing DATABASE_URL is caught before any app import.
    from app.core.db import get_conn

    with get_conn(database_url) as conn, conn.cursor() as cur:
        cur.execute(
            """
                DELETE FROM submission_photos
                WHERE submission_id IN (
                    SELECT submission_id
                    FROM delivery_jobs
                    WHERE status = 'delivered'
                )
                """
        )
        photos_deleted = cur.rowcount

        cur.execute(
            """
                DELETE FROM submission_attachments
                WHERE submission_id IN (
                    SELECT submission_id
                    FROM delivery_jobs
                    WHERE status = 'delivered'
                )
                """
        )
        attachments_deleted = cur.rowcount

    logger.info(
        "Deletion job complete: photos_deleted=%d attachments_deleted=%d",
        photos_deleted,
        attachments_deleted,
    )


def main() -> None:
    database_url = _require_env("DATABASE_URL")

    try:
        run_deletion(database_url)
    except Exception as exc:
        logger.critical("Deletion job failed: %s", exc, exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()

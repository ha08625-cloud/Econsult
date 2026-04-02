"""0013 — drop delivery columns from submission_records (Migration D)

Removes the delivery-tracking columns that have moved to the pdf_jobs and
delivery_jobs tables as part of the async pipeline refactor.

Columns dropped:
- delivery_status
- delivery_email
- delivered_at
- delivery_error
- delivery_attempts
- last_attempt_at
- next_retry_after
- attachment_count

These values now live as follows:
- delivery_email, attachment_count: captured on pdf_jobs at job creation time
  by the form router (written before this migration runs).
- delivery_status, delivered_at, delivery_error, delivery_attempts,
  last_attempt_at, next_retry_after: owned entirely by delivery_jobs.

Point of no return: the old synchronous delivery path in form_router.py is
permanently unavailable after this migration runs. Commit 2 must be fully
deployed before this migration executes.

Edge case: if this migration runs while a PDF job is mid-flight (claimed but
not yet past the create_job step), the PDF worker's get_submission call will
not fail because delivery_email is read from pdf_jobs, not submission_records.
The value was captured at job creation time by the form router and is immune
to this migration. See arch_submission.md for detail.

Revision ID: 0013
Revises: 0012
"""

from alembic import op

# revision identifiers, used by Alembic.
revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE submission_records
            DROP COLUMN IF EXISTS delivery_status,
            DROP COLUMN IF EXISTS delivery_email,
            DROP COLUMN IF EXISTS delivered_at,
            DROP COLUMN IF EXISTS delivery_error,
            DROP COLUMN IF EXISTS delivery_attempts,
            DROP COLUMN IF EXISTS last_attempt_at,
            DROP COLUMN IF EXISTS next_retry_after,
            DROP COLUMN IF EXISTS attachment_count
        """
    )


def downgrade() -> None:
    # Restores schema shape only. Data is not recoverable.
    op.execute(
        """
        ALTER TABLE submission_records
            ADD COLUMN IF NOT EXISTS delivery_status   TEXT    NOT NULL DEFAULT 'pending',
            ADD COLUMN IF NOT EXISTS delivery_email    TEXT,
            ADD COLUMN IF NOT EXISTS delivered_at      TIMESTAMPTZ,
            ADD COLUMN IF NOT EXISTS delivery_error    TEXT,
            ADD COLUMN IF NOT EXISTS delivery_attempts INTEGER NOT NULL DEFAULT 0,
            ADD COLUMN IF NOT EXISTS last_attempt_at   TIMESTAMPTZ,
            ADD COLUMN IF NOT EXISTS next_retry_after  TIMESTAMPTZ,
            ADD COLUMN IF NOT EXISTS attachment_count  INTEGER NOT NULL DEFAULT 0
        """
    )
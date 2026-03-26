"""0007 — add delivery retry columns to submission_records

Adds three columns to support delivery retry orchestration:

- delivery_attempts: tracks how many delivery attempts have had their
  outcome recorded. Starts at 0. Incremented atomically by
  record_attempt_outcome. Does not count physical SMTP connections —
  a crash during send leaves it un-incremented.

- last_attempt_at: timestamp of the most recent delivery attempt whose
  outcome was recorded. NULL until the first attempt completes.

- next_retry_after: the earliest time at which the next retry should be
  attempted. Set on failure according to the backoff schedule. Cleared
  (set to NULL) on success or when retries are exhausted. Used by
  list_retryable to find submissions eligible for retry.

Existing rows get delivery_attempts = 0 (database default) and NULL
for the timestamp columns. This is correct: existing rows with
delivery_status = 'sent' will never be retried (the already-sent guard
catches them), and existing rows with delivery_status = 'failed' will
not be picked up by list_retryable (which requires next_retry_after
IS NOT NULL).

Revision ID: 0007
Revises: 0006
"""

from alembic import op

# revision identifiers, used by Alembic.
revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE submission_records
        ADD COLUMN delivery_attempts INTEGER NOT NULL DEFAULT 0
        """
    )
    op.execute(
        """
        ALTER TABLE submission_records
        ADD COLUMN last_attempt_at TIMESTAMPTZ
        """
    )
    op.execute(
        """
        ALTER TABLE submission_records
        ADD COLUMN next_retry_after TIMESTAMPTZ
        """
    )


def downgrade() -> None:
    op.execute("ALTER TABLE submission_records DROP COLUMN IF EXISTS next_retry_after")
    op.execute("ALTER TABLE submission_records DROP COLUMN IF EXISTS last_attempt_at")
    op.execute("ALTER TABLE submission_records DROP COLUMN IF EXISTS delivery_attempts")
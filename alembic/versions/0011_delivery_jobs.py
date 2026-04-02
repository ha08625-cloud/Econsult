"""0011 — delivery_jobs table

Adds the delivery_jobs table, which queues email delivery work for each
form submission. The delivery worker polls this table after the PDF worker
has generated the attachment.

Columns:
- id:               UUID primary key
- submission_id:    FK to submission_records; UNIQUE constraint enforces
                    exactly one delivery job per submission and makes
                    the create_job INSERT idempotent via ON CONFLICT DO NOTHING
- status:           'pending' | 'sent' | 'failed'
- attempt_count:    incremented on each delivery attempt
- last_error:       populated on failure; cleared on success
- next_retry_after: the earliest time this job may be re-claimed after
                    a failure; NULL means immediately eligible
- to_email:         denormalised from submission_records at creation time;
                    kept here so the delivery worker never needs to read
                    submission_records
- condition_label:  denormalised for the same reason
- submitted_at:     denormalised for the same reason
- created_at / updated_at: audit timestamps

Index on (status, next_retry_after) supports the claim_next_pending query.

Ordering invariant: a delivery_jobs row is only created after
save_attachment has completed. This guarantees the delivery worker will
always find an attachment when it claims a job. Do not break this
invariant.

This migration adds new tables only. No existing tables are modified.
The application runs entirely on the old delivery path until Commit 2
completes.

Revision ID: 0011
Revises: 0010
"""

from alembic import op

# revision identifiers, used by Alembic.
revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE delivery_jobs (
            id               UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
            submission_id    UUID        NOT NULL REFERENCES submission_records(submission_id),
            status           TEXT        NOT NULL DEFAULT 'pending'
                                         CHECK (status IN ('pending', 'sent', 'failed')),
            attempt_count    INTEGER     NOT NULL DEFAULT 0,
            last_error       TEXT,
            next_retry_after TIMESTAMPTZ,
            to_email         TEXT        NOT NULL,
            condition_label  TEXT        NOT NULL,
            submitted_at     TIMESTAMPTZ NOT NULL,
            created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE (submission_id)
        )
        """
    )
    op.execute(
        """
        CREATE INDEX idx_delivery_jobs_status_retry
            ON delivery_jobs (status, next_retry_after)
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_delivery_jobs_status_retry")
    op.execute("DROP TABLE IF EXISTS delivery_jobs")
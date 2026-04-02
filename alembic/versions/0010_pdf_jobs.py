"""0010 — pdf_jobs table

Adds the pdf_jobs table, which queues PDF generation work for each
form submission. The PDF worker polls this table and processes pending
jobs independently of the web request.

Columns:
- id:               UUID primary key
- submission_id:    FK to submission_records; one PDF job per submission
- status:           'pending' | 'done' | 'failed'
- attempt_count:    incremented on each processing attempt
- last_error:       populated on failure; cleared on success
- next_retry_after: the earliest time this job may be re-claimed after
                    a failure; NULL means immediately eligible
- attachment_count: number of photos expected for this submission;
                    captured at job creation time so the PDF worker can
                    perform a defensive photo count check without reading
                    submission_records (which drops this column in migration
                    0012 / Migration D)
- delivery_email:   the practice email address to deliver to; captured
                    at job creation time for the same reason as attachment_count
- created_at / updated_at: audit timestamps

Index on (status, next_retry_after) supports the claim_next_pending query.

This migration adds new tables only. No existing tables are modified.
The application runs entirely on the old delivery path until Commit 2
completes.

Revision ID: 0010
Revises: 0009
"""

from alembic import op

# revision identifiers, used by Alembic.
revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE pdf_jobs (
            id               UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
            submission_id    TEXT        NOT NULL REFERENCES submission_records(submission_id),
            status           TEXT        NOT NULL DEFAULT 'pending'
                                         CHECK (status IN ('pending', 'done', 'failed')),
            attempt_count    INTEGER     NOT NULL DEFAULT 0,
            last_error       TEXT,
            next_retry_after TIMESTAMPTZ,
            attachment_count INTEGER     NOT NULL,
            delivery_email   TEXT        NOT NULL,
            created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    op.execute(
        """
        CREATE INDEX idx_pdf_jobs_status_retry
            ON pdf_jobs (status, next_retry_after)
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_pdf_jobs_status_retry")
    op.execute("DROP TABLE IF EXISTS pdf_jobs")
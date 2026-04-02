"""0012 — submission_photos table

Adds the submission_photos table, which stores raw photo bytes uploaded by
patients at form submission time. The PDF worker reads these bytes to
generate the PDF attachment.

Columns:
- submission_id:  FK to submission_records; part of the composite PK
- photo_index:    0-based integer preserving upload order; part of the composite PK
- photo_bytes:    raw image bytes as BYTEA

The primary key is (submission_id, photo_index) — no surrogate id needed.
The PDF worker reads rows ordered by photo_index to reconstruct the original
upload order when embedding images in the PDF.

Rows are deleted by the nightly deletion cron job (deletion_job.py) for
submissions where delivery_jobs.status = 'sent'. pdf_jobs and
delivery_jobs rows are never deleted — they accumulate as an operational
audit trail.

This migration adds a new table only. No existing tables are modified.

Revision ID: 0012
Revises: 0011
"""

from alembic import op

# revision identifiers, used by Alembic.
revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE submission_photos (
            submission_id  TEXT    NOT NULL REFERENCES submission_records(submission_id),
            photo_index    INTEGER NOT NULL,
            photo_bytes    BYTEA   NOT NULL,
            PRIMARY KEY (submission_id, photo_index)
        )
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS submission_photos")
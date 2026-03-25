"""0006 — store PDF bytes and condition_label at submission time

Adds condition_label to submission_records for lightweight access during
delivery retry without loading clinical_output_json.

Creates submission_attachments as a separate table so that blob data
(PDF bytes, and later photo attachments) is never loaded by queries
against submission_records.

Design decision: The PDF stored in submission_attachments is the canonical
delivery artifact. It must never be regenerated at retry time. Whatever was
in the PDF at submission time is what gets sent on every retry.

condition_label uses DEFAULT '' for existing rows only. The application
always supplies the value explicitly on new submissions.

Revision ID: 0006
Revises: 0005
"""

from alembic import op

# revision identifiers, used by Alembic.
revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add condition_label to submission_records.
    # DEFAULT '' handles existing rows; the application always supplies
    # the value explicitly on INSERT.
    op.execute(
        """
        ALTER TABLE submission_records
        ADD COLUMN condition_label TEXT NOT NULL DEFAULT ''
        """
    )

    # Separate table for blob storage. Keeps submission_records queries
    # lightweight. submission_id is both PK and FK.
    op.execute(
        """
        CREATE TABLE submission_attachments (
            submission_id TEXT PRIMARY KEY
                REFERENCES submission_records(submission_id),
            pdf_bytes     BYTEA NOT NULL
        )
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS submission_attachments")
    op.execute(
        """
        ALTER TABLE submission_records
        DROP COLUMN IF EXISTS condition_label
        """
    )
"""0008 — add attachment_count to submission_records

Adds one column:

- attachment_count: the number of photos submitted alongside the form.
  Stored as an audit field only. Not used by delivery or retry logic.
  DEFAULT 0 handles rows inserted before this migration. New submissions
  always supply an explicit value from the router — the default is not
  relied upon in new code.

Revision ID: 0008
Revises: 0007
"""

from alembic import op

# revision identifiers, used by Alembic.
revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE submission_records
        ADD COLUMN attachment_count INTEGER NOT NULL DEFAULT 0
        """
    )


def downgrade() -> None:
    op.execute("ALTER TABLE submission_records DROP COLUMN IF EXISTS attachment_count")
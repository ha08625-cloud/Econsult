"""0003 — availability override columns

Adds override_status, override_expires_at, and override_message columns
to practice_availability for manual force-open/force-closed overrides.

All three columns are nullable. A null override_status means no override
is active.

Revision ID: 0003
Revises: 0002
"""

from alembic import op

# revision identifiers, used by Alembic.
revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE practice_availability
            ADD COLUMN override_status TEXT CHECK (override_status IN ('open', 'closed')),
            ADD COLUMN override_expires_at TIMESTAMPTZ,
            ADD COLUMN override_message TEXT
        """
    )


def downgrade() -> None:
    op.execute("ALTER TABLE practice_availability DROP COLUMN override_message")
    op.execute("ALTER TABLE practice_availability DROP COLUMN override_expires_at")
    op.execute("ALTER TABLE practice_availability DROP COLUMN override_status")

"""0002 — practice_availability table

Adds the practice_availability table for weekly schedule,
closed message, and after-hours notice configuration.

No IF NOT EXISTS — this is a proper Alembic migration.

Revision ID: 0002
Revises: 0001
"""

from alembic import op

# revision identifiers, used by Alembic.
revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE practice_availability (
            practice_id      TEXT PRIMARY KEY REFERENCES practices(practice_id),
            is_active        BOOLEAN NOT NULL DEFAULT false,
            weekly_open_days TEXT[]  NOT NULL DEFAULT '{}',
            open_time        TIME   NOT NULL DEFAULT '08:00',
            close_time       TIME   NOT NULL DEFAULT '18:30',
            closed_message   TEXT,
            CONSTRAINT weekly_open_days_valid CHECK (
                weekly_open_days <@ ARRAY['mon','tue','wed','thu','fri','sat','sun']::TEXT[]
            )
        )
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS practice_availability")

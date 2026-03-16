"""0004 — availability exceptions table

Creates practice_availability_exceptions for per-date schedule overrides.
Supports two exception types: 'closed' (full day closure) and
'custom_hours' (different open/close times for that date).

Composite primary key (practice_id, exception_date) ensures one exception
per practice per date.

Revision ID: 0004
Revises: 0003
"""

from alembic import op

# revision identifiers, used by Alembic.
revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE practice_availability_exceptions (
            practice_id     TEXT NOT NULL REFERENCES practices(practice_id),
            exception_date  DATE NOT NULL,
            exception_type  TEXT NOT NULL CHECK (exception_type IN ('closed', 'custom_hours')),
            open_time       TIME,
            close_time      TIME,
            note            TEXT,
            PRIMARY KEY (practice_id, exception_date)
        )
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE practice_availability_exceptions")

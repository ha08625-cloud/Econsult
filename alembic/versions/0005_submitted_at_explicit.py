"""0005 — remove DEFAULT NOW() from submitted_at

Makes submitted_at explicitly required in application code.
The column remains NOT NULL — the application must always supply the value.

Rationale: prevents any possibility of the DB generating a timestamp that
diverges from the one the application captures and passes to the delivery
service. A single authoritative timestamp is captured in form_router.py
immediately before create_submission is called.

Revision ID: 0005
Revises: 0004
"""

from alembic import op

# revision identifiers, used by Alembic.
revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE submission_records
        ALTER COLUMN submitted_at DROP DEFAULT
        """
    )


def downgrade() -> None:
    op.execute(
        """
        ALTER TABLE submission_records
        ALTER COLUMN submitted_at SET DEFAULT NOW()
        """
    )

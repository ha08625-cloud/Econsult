"""0006 — DB backstop constraints for availability time invariants

Revision ID: 0006
Revises: 0005
Branch labels: None
Depends on: None

These are backstops for the application-layer validation already performed
by validate_exception() and validate_availability_config() in
availability_service.py. That validation is the primary defence and runs on
every admin write; these constraints exist only to make a bypass of that
layer (a bad direct SQL write, a bug in a future code path, a manual data
fix) fail loudly at the database rather than silently produce a malformed
row. This mirrors the intent of the existing weekly_open_days_valid
constraint on practice_availability, which serves the same backstop role
for the weekly_open_days array.

Two constraints are added:

1. practice_availability_exceptions.exception_times_valid — exception_type
   is already restricted to 'closed' or 'custom_hours' by the table's
   existing CHECK, so the two-branch OR below is exhaustive:
     - 'closed' rows must have both open_time and close_time NULL.
     - 'custom_hours' rows must have both open_time and close_time set,
       with open_time strictly before close_time.

2. practice_availability.availability_times_valid — open_time and
   close_time are both NOT NULL on this table already, so this constraint
   only needs to enforce open_time < close_time.

No backfill or data-cleaning step is included here deliberately. If a
violating row already exists, this migration must fail rather than paper
over it. See deployment_checklist.md for the pre-deploy queries that
should be run against production before applying this migration.

Both tables are small (one config row per practice for
practice_availability, a handful of exception rows for
practice_availability_exceptions), so the brief ACCESS EXCLUSIVE lock
taken by ADD CONSTRAINT is negligible.
"""

from alembic import op


revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # -------------------------------------------------------------------------
    # practice_availability_exceptions: exception_times_valid
    # -------------------------------------------------------------------------
    op.execute(
        """
        ALTER TABLE practice_availability_exceptions
            ADD CONSTRAINT exception_times_valid CHECK (
                (exception_type = 'closed'
                    AND open_time IS NULL AND close_time IS NULL)
                OR
                (exception_type = 'custom_hours'
                    AND open_time IS NOT NULL AND close_time IS NOT NULL
                    AND open_time < close_time)
            )
        """
    )

    # -------------------------------------------------------------------------
    # practice_availability: availability_times_valid
    # -------------------------------------------------------------------------
    op.execute(
        """
        ALTER TABLE practice_availability
            ADD CONSTRAINT availability_times_valid CHECK (
                open_time < close_time
            )
        """
    )


def downgrade() -> None:
    # Reverse order relative to upgrade().
    op.execute(
        """
        ALTER TABLE practice_availability
            DROP CONSTRAINT IF EXISTS availability_times_valid
        """
    )
    op.execute(
        """
        ALTER TABLE practice_availability_exceptions
            DROP CONSTRAINT IF EXISTS exception_times_valid
        """
    )

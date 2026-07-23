"""0006 — CHECK constraint backstops for availability time invariants

Revision ID: 0006
Revises: 0005
Branch labels: None
Depends on: None

Two independent CHECK constraints, both closing gaps where an invariant
was previously enforced only in the application layer
(app/services/admin/availability_service.py: validate_exception and
validate_availability_config), with no database-level backstop. Both
mirror an existing pattern already in this schema — the
weekly_open_days_valid CHECK on practice_availability (0001) — which the
architecture doc cites as the precedent for "validation belongs in the
DB too, not just the app".

1. practice_availability_exceptions — add
   availability_exceptions_time_invariant, requiring:
     - exception_type = 'closed'       -> open_time AND close_time IS NULL
     - exception_type = 'custom_hours' -> open_time AND close_time IS NOT
       NULL, and open_time < close_time (overnight hours unsupported,
       matching validate_exception exactly)

   Without this, a row written outside the application (manual DB edit,
   bad backfill, future bug) with exception_type='custom_hours' and a NULL
   time raises TypeError inside evaluate_availability when the time
   comparison runs. That TypeError is swallowed by the fail-open wrapper
   around POST /form/init and /form/finish (silently disabling the
   schedule gate for patients) and separately surfaces as an unhandled
   HTTP 500 on GET /availability, which has no such wrapper. A defensive
   None-guard was also added to evaluate_availability itself in this same
   change (see availability_service.py) as belt-and-braces, but the CHECK
   constraint is the actual backstop: it prevents the bad row from ever
   being persisted, regardless of which code path (or absence of one)
   writes it.

2. practice_availability — add availability_time_invariant, requiring
   open_time < close_time. The same overnight-hours rule as
   validate_availability_config has applied at the application layer
   since 0001, but the column itself was never backed by a CHECK the way
   weekly_open_days was. Existing default values (08:00 / 18:30) already
   satisfy this constraint, so no data migration is needed here either.

Deploy note: ALTER TABLE ... ADD CONSTRAINT validates all existing rows.
alembic_upgrade() in db.py runs at web service startup, so a single
violating row in either table will fail this migration and prevent the
app from starting until the row is fixed — this is the same fail-fast
behaviour as every other startup validation in this codebase, not a new
risk, but see deployment_checklist.md for the pre-deploy row check this
migration's entry recommends.

No backfill step: no violating rows are expected in either table. If the
migration fails on deploy, that failure is itself the signal that a bad
row exists and needs manual attention before proceeding — exactly the
outcome we want instead of a silent TypeError or 500 in production.
"""

from alembic import op


revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # -------------------------------------------------------------------------
    # practice_availability_exceptions: time invariant tied to exception_type
    # -------------------------------------------------------------------------
    op.execute(
        """
        ALTER TABLE practice_availability_exceptions
            ADD CONSTRAINT availability_exceptions_time_invariant CHECK (
                (exception_type = 'closed'
                    AND open_time IS NULL
                    AND close_time IS NULL)
                OR
                (exception_type = 'custom_hours'
                    AND open_time IS NOT NULL
                    AND close_time IS NOT NULL
                    AND open_time < close_time)
            )
        """
    )

    # -------------------------------------------------------------------------
    # practice_availability: open_time < close_time backstop
    # -------------------------------------------------------------------------
    op.execute(
        """
        ALTER TABLE practice_availability
            ADD CONSTRAINT availability_time_invariant CHECK (
                open_time < close_time
            )
        """
    )


def downgrade() -> None:
    op.execute(
        """
        ALTER TABLE practice_availability
            DROP CONSTRAINT IF EXISTS availability_time_invariant
        """
    )
    op.execute(
        """
        ALTER TABLE practice_availability_exceptions
            DROP CONSTRAINT IF EXISTS availability_exceptions_time_invariant
        """
    )

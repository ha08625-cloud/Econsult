"""0002 — user management: cascade delete on admin_sessions and last_login on admin_users

Adds two schema changes required for admin user management:

1. admin_sessions.user_id foreign key:
   The initial FK was created inline without an explicit name, so Postgres
   generated one. We query pg_constraint at migration time to find the exact
   name, drop it, and recreate it with ON DELETE CASCADE so that deleting an
   admin_users row automatically removes all their sessions.

2. admin_users.last_login:
   A nullable TIMESTAMPTZ column. Set to NOW() by AuthRepository.create_session
   each time a user successfully authenticates. Null means the user has never
   logged in (i.e. the invitation has been sent but not yet acted on).

Revision ID: 0002
Revises: 0001
"""

from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # -------------------------------------------------------------------------
    # Step 1: Recreate admin_sessions.user_id FK with ON DELETE CASCADE.
    #
    # The FK was created inline in migration 0001 without an explicit name,
    # so Postgres assigned an auto-generated name. We use a PL/pgSQL DO block
    # to look up the exact constraint name from pg_constraint at runtime, drop
    # it, then recreate it with ondelete=CASCADE.
    #
    # This approach is safe to run multiple times: if the inline FK has already
    # been dropped (e.g. in a dev environment where the migration was applied
    # manually), the DO block will find no matching constraint and skip the DROP.
    # -------------------------------------------------------------------------
    op.execute(
        """
        DO $$
        DECLARE
            _constraint_name TEXT;
        BEGIN
            SELECT conname INTO _constraint_name
            FROM pg_constraint
            WHERE conrelid = 'admin_sessions'::regclass
              AND confrelid = 'admin_users'::regclass
              AND contype   = 'f';

            IF _constraint_name IS NOT NULL THEN
                EXECUTE format(
                    'ALTER TABLE admin_sessions DROP CONSTRAINT %I',
                    _constraint_name
                );
            END IF;
        END;
        $$;
        """
    )

    op.create_foreign_key(
        constraint_name="fk_admin_sessions_user_id",
        source_table="admin_sessions",
        referent_table="admin_users",
        local_cols=["user_id"],
        remote_cols=["id"],
        ondelete="CASCADE",
    )

    # -------------------------------------------------------------------------
    # Step 2: Add last_login column to admin_users.
    #
    # Nullable with no default — existing rows correctly represent users who
    # have never logged in. Set to NOW() by create_session on each login.
    # -------------------------------------------------------------------------
    op.execute(
        "ALTER TABLE admin_users ADD COLUMN last_login TIMESTAMPTZ"
    )


def downgrade() -> None:
    # Remove last_login column.
    op.execute(
        "ALTER TABLE admin_users DROP COLUMN IF EXISTS last_login"
    )

    # Drop the explicitly-named FK and restore the inline (unnamed) one.
    op.drop_constraint(
        constraint_name="fk_admin_sessions_user_id",
        table_name="admin_sessions",
        type_="foreignkey",
    )
    op.create_foreign_key(
        constraint_name=None,
        source_table="admin_sessions",
        referent_table="admin_users",
        local_cols=["user_id"],
        remote_cols=["id"],
    )
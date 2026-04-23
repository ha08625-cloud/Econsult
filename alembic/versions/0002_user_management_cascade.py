"""0002 — user management: cascade FK on admin_sessions, last_login on admin_users

Revision ID: 0002
Revises: 0001
Branch labels: None
Depends on: None

Two schema changes shipped as a single version:

1. admin_sessions.user_id FK — replace the anonymous FK created in 0001 with a
   named FK that carries ON DELETE CASCADE. When an admin_users row is deleted,
   all of that user's sessions are removed automatically by Postgres. This is
   safer than relying on the application layer to clean up sessions before
   deleting a user — if the application ever fails mid-operation the database
   is left consistent.

   The FK created in 0001 was defined inline (no explicit name), so Postgres
   assigned it an auto-generated name. A PL/pgSQL DO block queries pg_constraint
   to discover that name at migration time, then drops it. If the constraint is
   missing for any reason the DO block raises an explicit exception and the
   migration aborts rather than proceeding silently.

2. admin_users.last_login — nullable TIMESTAMPTZ column, no default. Populated
   by AuthRepository.create_session whenever a user logs in. NULL means the user
   has never completed a login (i.e. an invitation has been sent but MFA has
   not been verified yet). The frontend displays NULL as "Pending".
"""

from alembic import op
import sqlalchemy as sa


revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # -------------------------------------------------------------------------
    # Step 1: Drop the anonymous FK on admin_sessions.user_id.
    #
    # Postgres auto-names FKs defined inline. We query pg_constraint to find
    # the exact name rather than hardcoding it (which would be fragile across
    # different Postgres versions or environments). The block raises an explicit
    # error if no matching constraint is found so the migration aborts loudly
    # rather than silently half-applying.
    # -------------------------------------------------------------------------
    op.execute(
        """
        DO $$
        DECLARE
            v_constraint_name TEXT;
        BEGIN
            SELECT conname INTO v_constraint_name
            FROM pg_constraint
            WHERE conrelid = 'admin_sessions'::regclass
              AND contype = 'f'
              AND conkey = ARRAY(
                  SELECT attnum
                  FROM pg_attribute
                  WHERE attrelid = 'admin_sessions'::regclass
                    AND attname = 'user_id'
              );

            IF v_constraint_name IS NULL THEN
                RAISE EXCEPTION
                    'Could not find foreign key on admin_sessions.user_id — '
                    'migration cannot proceed safely';
            END IF;

            EXECUTE 'ALTER TABLE admin_sessions DROP CONSTRAINT '
                    || quote_ident(v_constraint_name);
        END
        $$;
        """
    )

    # -------------------------------------------------------------------------
    # Step 2: Re-add the FK with ON DELETE CASCADE and an explicit name.
    #
    # op.create_foreign_key generates:
    #   ALTER TABLE admin_sessions
    #     ADD CONSTRAINT fk_admin_sessions_user_id
    #     FOREIGN KEY (user_id) REFERENCES admin_users (id)
    #     ON DELETE CASCADE;
    # -------------------------------------------------------------------------
    op.create_foreign_key(
        constraint_name="fk_admin_sessions_user_id",
        source_table="admin_sessions",
        referent_table="admin_users",
        local_cols=["user_id"],
        remote_cols=["id"],
        ondelete="CASCADE",
    )

    # -------------------------------------------------------------------------
    # Step 3: Add last_login to admin_users.
    #
    # Nullable with no default — NULL means the user has never logged in
    # (invitation sent but MFA not yet verified). AuthRepository.create_session
    # sets this to NOW() atomically when a session is created.
    # -------------------------------------------------------------------------
    op.add_column(
        "admin_users",
        sa.Column(
            "last_login",
            sa.TIMESTAMP(timezone=True),
            nullable=True,
        ),
    )


def downgrade() -> None:
    # -------------------------------------------------------------------------
    # Reverse in the opposite order to upgrade.
    # -------------------------------------------------------------------------

    # Remove last_login column.
    op.drop_column("admin_users", "last_login")

    # Drop the named cascade FK.
    op.drop_constraint(
        "fk_admin_sessions_user_id",
        "admin_sessions",
        type_="foreignkey",
    )

    # Restore the original anonymous FK (no cascade, matching 0001 state).
    # We cannot restore the original auto-generated name, so we use an explicit
    # name here. This is only relevant if downgrade is ever run — in practice
    # this migration is not expected to be reversed in production.
    op.create_foreign_key(
        constraint_name="fk_admin_sessions_user_id_nocascade",
        source_table="admin_sessions",
        referent_table="admin_users",
        local_cols=["user_id"],
        remote_cols=["id"],
        ondelete=None,
    )
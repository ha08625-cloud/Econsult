"""0014 — admin auth tables

Creates three tables for MFA-based admin authentication:

  admin_users       — registered admin/staff accounts linked to a practice
  admin_auth_codes  — in-flight MFA codes (one per user at a time)
  admin_sessions    — active sessions created after successful MFA verification

Revision ID: 0014
Revises: 0013
"""

from alembic import op

revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # admin_users — one row per registered admin or staff account.
    # practice_id is a FK to practices so a user is always scoped to a practice.
    # role is stored as free text — enforced at application layer (admin/staff).
    op.execute(
        """
        CREATE TABLE admin_users (
            id          UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
            email       TEXT        NOT NULL UNIQUE,
            practice_id TEXT        NOT NULL REFERENCES practices(practice_id),
            role        TEXT        NOT NULL,
            created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    op.execute("CREATE INDEX admin_users_email_idx ON admin_users (email)")

    # admin_auth_codes — one in-flight code per user at a time.
    # email is the PK so an upsert naturally replaces any existing code.
    # last_requested_at enforces the 60-second cooldown in the service layer.
    # attempts_count is reset to 0 on every upsert (new code request).
    op.execute(
        """
        CREATE TABLE admin_auth_codes (
            email             TEXT        PRIMARY KEY,
            hashed_code       TEXT        NOT NULL,
            expires_at        TIMESTAMPTZ NOT NULL,
            attempts_count    INTEGER     NOT NULL DEFAULT 0,
            last_requested_at TIMESTAMPTZ NOT NULL
        )
        """
    )

    # admin_sessions — active sessions after successful MFA verification.
    # user_id FK to admin_users. Expired sessions are cleaned up lazily
    # inside AuthRepository.create_session (per-user, not global).
    op.execute(
        """
        CREATE TABLE admin_sessions (
            session_id UUID        PRIMARY KEY,
            user_id    UUID        NOT NULL REFERENCES admin_users(id),
            expires_at TIMESTAMPTZ NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )


def downgrade() -> None:
    # Drop in reverse dependency order.
    # admin_sessions references admin_users, so it must be dropped first.
    # admin_auth_codes has no FK dependencies.
    op.execute("DROP TABLE IF EXISTS admin_sessions")
    op.execute("DROP TABLE IF EXISTS admin_auth_codes")
    op.execute("DROP TABLE IF EXISTS admin_users")
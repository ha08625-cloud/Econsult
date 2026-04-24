"""0004 — password authentication: password fields on admin_users and reset tokens table

Revision ID: 0004
Revises: 0003
Branch labels: None
Depends on: None

Two schema changes:

1. admin_users — four new columns:
   - hashed_password (TEXT, nullable): NULL indicates the account has not
     yet had a password set (pending invitation/setup). Populated by the
     set-password flow after the user follows their setup link.
   - failed_password_attempts (INTEGER, NOT NULL, DEFAULT 0): incremented
     atomically on each wrong password. Reset to 0 on successful auth or
     when a new password is set.
   - password_locked_until (TIMESTAMPTZ, nullable): set to NOW() + 15
     minutes when failed_password_attempts reaches 3. NULL means not locked.
   - password_changed_at (TIMESTAMPTZ, nullable): set to NOW() whenever a
     new password is stored. Required for Cyber Essentials Plus compliance
     auditing.

2. admin_password_reset_tokens — new table for password setup and reset links:
   - token_hash (TEXT, PRIMARY KEY): SHA-256 hex digest of the raw token
     sent in the email. Raw tokens are never stored.
   - user_id (UUID, NOT NULL, FK -> admin_users.id ON DELETE CASCADE):
     the user this token was issued for.
   - UNIQUE (user_id): structurally enforces one active token per user.
     The upsert (ON CONFLICT DO UPDATE) replaces any existing token when a
     new one is generated, so the constraint is also the de-duplication
     mechanism.
   - expires_at (TIMESTAMPTZ, NOT NULL): token is considered invalid after
     this timestamp, checked in the service layer.
"""

from alembic import op


revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # -------------------------------------------------------------------------
    # admin_users: add password-related columns
    # -------------------------------------------------------------------------
    op.execute(
        """
        ALTER TABLE admin_users
            ADD COLUMN hashed_password         TEXT,
            ADD COLUMN failed_password_attempts INTEGER     NOT NULL DEFAULT 0,
            ADD COLUMN password_locked_until    TIMESTAMPTZ,
            ADD COLUMN password_changed_at      TIMESTAMPTZ
        """
    )

    # -------------------------------------------------------------------------
    # admin_password_reset_tokens: new table
    # -------------------------------------------------------------------------
    op.execute(
        """
        CREATE TABLE admin_password_reset_tokens (
            token_hash TEXT        PRIMARY KEY,
            user_id    UUID        NOT NULL
                           REFERENCES admin_users(id) ON DELETE CASCADE,
            expires_at TIMESTAMPTZ NOT NULL,
            CONSTRAINT admin_password_reset_tokens_user_id_unique UNIQUE (user_id)
        )
        """
    )


def downgrade() -> None:
    # Drop the reset tokens table first (FK dependency on admin_users).
    op.execute("DROP TABLE IF EXISTS admin_password_reset_tokens")

    # Remove the four password columns from admin_users.
    op.execute(
        """
        ALTER TABLE admin_users
            DROP COLUMN IF EXISTS hashed_password,
            DROP COLUMN IF EXISTS failed_password_attempts,
            DROP COLUMN IF EXISTS password_locked_until,
            DROP COLUMN IF EXISTS password_changed_at
        """
    )
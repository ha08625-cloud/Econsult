"""0001 — initial schema

Captures the four tables that already exist in the production database.
Uses CREATE TABLE IF NOT EXISTS as a one-time concession because the
database predates Alembic. Future migrations must NOT use IF NOT EXISTS.

Revision ID: 0001
Revises: (none)
"""

from alembic import op

# revision identifiers, used by Alembic.
revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # --- practices (referenced by other tables) ---
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS practices (
            practice_id TEXT        PRIMARY KEY,
            name        TEXT        NOT NULL,
            email       TEXT        NOT NULL,
            created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )

    # --- runtime_state_versions ---
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS runtime_state_versions (
            runtime_id   TEXT        NOT NULL,
            version      INTEGER     NOT NULL,
            ruleset_hash TEXT        NOT NULL,
            state_json   JSONB       NOT NULL,
            created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            is_closed    BOOLEAN     NOT NULL DEFAULT FALSE,
            PRIMARY KEY (runtime_id, version)
        )
        """
    )

    # --- practice_signposting (references practices) ---
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS practice_signposting (
            practice_id      TEXT        NOT NULL REFERENCES practices(practice_id),
            condition_id     TEXT        NOT NULL,
            signposting_json TEXT        NOT NULL,
            updated_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            PRIMARY KEY (practice_id, condition_id)
        )
        """
    )

    # --- submission_records ---
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS submission_records (
            submission_id        TEXT        PRIMARY KEY,
            practice_id          TEXT        NOT NULL,
            condition_id         TEXT        NOT NULL,
            clinical_output_json JSONB       NOT NULL,
            audit_output_json    JSONB       NOT NULL,
            submitted_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            delivery_status      TEXT        NOT NULL DEFAULT 'pending',
            delivery_email       TEXT        NOT NULL,
            delivered_at         TIMESTAMPTZ,
            delivery_error       TEXT
        )
        """
    )


def downgrade() -> None:
    # Drop in reverse foreign-key dependency order.
    # practice_signposting references practices, so it must be dropped first.
    op.execute("DROP TABLE IF EXISTS practice_signposting")
    op.execute("DROP TABLE IF EXISTS submission_records")
    op.execute("DROP TABLE IF EXISTS runtime_state_versions")
    op.execute("DROP TABLE IF EXISTS practices")

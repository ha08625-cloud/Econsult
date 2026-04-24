"""0003 — webhook tracking: provider message IDs, event log, and replay protection

Revision ID: 0003
Revises: 0002
Branch labels: None
Depends on: None

Three schema changes:

1. delivery_jobs — add provider_message_id (VARCHAR 255, nullable, indexed).
   Populated by the delivery worker immediately after a successful Mailgun API
   call. The webhook router uses this to look up the job when a delivery signal
   arrives.

2. delivery_jobs — add provider_events (JSONB, nullable).
   Append-only log of raw webhook payloads received from Mailgun. Consistent
   with the system's lossless audit trail design. Written by the webhook router.

3. delivery_jobs — extend status check constraint to include 'provider_accepted'
   and 'delivered'.
   - provider_accepted: Mailgun has accepted the message (HTTP 200 from their
     API). Set by the delivery worker on the Mailgun path.
   - delivered: Mailgun has confirmed delivery to the recipient mail server.
     Set by the webhook router on receipt of a 'delivered' event.
   Existing values 'pending', 'sent', 'failed' are preserved unchanged.
   'sent' remains valid for the legacy SMTP path (no webhook tracking).

   Altering an inline check constraint requires dropping and recreating it.
   A PL/pgSQL DO block discovers the auto-generated constraint name from
   pg_constraint, drops it, then adds the new named constraint. If the
   constraint is unexpectedly absent the block raises an explicit exception
   so the migration aborts rather than proceeding silently.

4. webhook_tokens — new table for replay attack prevention.
   Stores the unique token from each Mailgun webhook. The webhook router
   attempts INSERT ... ON CONFLICT DO NOTHING; if no row is inserted, the
   token was already seen and the request is a replay. Expired tokens
   (older than 15 minutes) are deleted at the start of each webhook request
   to keep the table bounded without a separate cron job.
"""

from alembic import op


revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # -------------------------------------------------------------------------
    # delivery_jobs: add provider_message_id
    # -------------------------------------------------------------------------
    op.execute(
        """
        ALTER TABLE delivery_jobs
            ADD COLUMN provider_message_id VARCHAR(255)
        """
    )
    op.execute(
        """
        CREATE INDEX idx_delivery_jobs_provider_message_id
            ON delivery_jobs (provider_message_id)
            WHERE provider_message_id IS NOT NULL
        """
    )

    # -------------------------------------------------------------------------
    # delivery_jobs: add provider_events JSONB
    # -------------------------------------------------------------------------
    op.execute(
        """
        ALTER TABLE delivery_jobs
            ADD COLUMN provider_events JSONB
        """
    )

    # -------------------------------------------------------------------------
    # delivery_jobs: extend status check constraint
    #
    # The original constraint was defined inline with no explicit name, so
    # Postgres assigned an auto-generated name. A PL/pgSQL DO block discovers
    # the name via pg_constraint and drops it before adding the new named
    # constraint. If the constraint is absent the block raises an explicit
    # error so the migration aborts cleanly.
    # -------------------------------------------------------------------------
    op.execute(
        """
        DO $$
        DECLARE
            v_constraint_name TEXT;
        BEGIN
            SELECT conname INTO v_constraint_name
            FROM pg_constraint
            WHERE conrelid = 'delivery_jobs'::regclass
              AND contype = 'c'
              AND pg_get_constraintdef(oid) LIKE '%pending%sent%failed%';

            IF v_constraint_name IS NULL THEN
                RAISE EXCEPTION
                    'Could not locate status check constraint on delivery_jobs. '
                    'Migration cannot proceed safely.';
            END IF;

            EXECUTE 'ALTER TABLE delivery_jobs DROP CONSTRAINT ' ||
                    quote_ident(v_constraint_name);
        END;
        $$
        """
    )
    op.execute(
        """
        ALTER TABLE delivery_jobs
            ADD CONSTRAINT delivery_jobs_status_check
            CHECK (status IN (
                'pending',
                'provider_accepted',
                'delivered',
                'sent',
                'failed'
            ))
        """
    )

    # -------------------------------------------------------------------------
    # webhook_tokens: replay protection table
    # -------------------------------------------------------------------------
    op.execute(
        """
        CREATE TABLE webhook_tokens (
            token       TEXT        PRIMARY KEY,
            received_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )


def downgrade() -> None:
    # Remove webhook_tokens
    op.execute("DROP TABLE IF EXISTS webhook_tokens")

    # Restore original status check constraint on delivery_jobs
    op.execute(
        """
        ALTER TABLE delivery_jobs
            DROP CONSTRAINT IF EXISTS delivery_jobs_status_check
        """
    )
    op.execute(
        """
        ALTER TABLE delivery_jobs
            ADD CHECK (status IN ('pending', 'sent', 'failed'))
        """
    )

    # Remove provider_events and provider_message_id columns
    op.execute(
        "DROP INDEX IF EXISTS idx_delivery_jobs_provider_message_id"
    )
    op.execute(
        """
        ALTER TABLE delivery_jobs
            DROP COLUMN IF EXISTS provider_events,
            DROP COLUMN IF EXISTS provider_message_id
        """
    )
"""0005 — MESH delivery queue: mesh_jobs table and delivery_jobs.is_fallback

Revision ID: 0005
Revises: 0004
Branch labels: None
Depends on: None

Two schema changes in one migration (Alembic wraps each migration in a single
transaction on Postgres, so both apply atomically):

1. mesh_jobs — new table. One row per MESH-enabled submission. Created by the
   PDF worker via MeshEnqueuer (Phase 2b). Consumed by the MESH dispatcher
   (Phase 3) and the tracking poller (Phase 4). Mirrors the pdf_jobs /
   delivery_jobs queue shape: UUID PK, a UNIQUE submission_id for idempotent
   enqueue, a named status CHECK constraint, attempt/error bookkeeping, and a
   (status, next_retry_after) claim index.

   - message_id holds the 32-char uppercase hex MESH messageID verbatim as
     TEXT. It must never be parsed as a UUID (that would lowercase and
     hyphenate it and no longer match what the tracking endpoint echoes back).
     It is UNIQUE; Postgres permits many NULLs under a UNIQUE constraint, which
     is the intended state for not-yet-sent rows.
   - mex_localid is generated at row creation for crash-trail correlation. The
     dispatcher (Phase 3) sends it as the per-message Mex-LocalID header.
   - recipient_mailbox_id is copied onto the row at enqueue time (from the
     MESH_RECIPIENT_MAILBOX_ID env value) so that a configuration change
     between enqueue and dispatch cannot misroute an already-queued referral.

2. delivery_jobs — add is_fallback BOOLEAN NOT NULL DEFAULT FALSE. Set TRUE only
   by the MESH dispatcher (Phase 3) when it abandons MESH and falls through to
   the Mailgun email path. The PDF worker email path leaves it FALSE.
"""

from alembic import op


revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # -------------------------------------------------------------------------
    # mesh_jobs: outbound MESH delivery queue
    # -------------------------------------------------------------------------
    op.execute(
        """
        CREATE TABLE mesh_jobs (
            id                   UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
            submission_id        TEXT        NOT NULL UNIQUE
                                             REFERENCES submission_records(submission_id),
            status               TEXT        NOT NULL DEFAULT 'pending',
            message_id           TEXT        UNIQUE,
            mex_localid          UUID        NOT NULL DEFAULT gen_random_uuid(),
            recipient_mailbox_id TEXT        NOT NULL,
            attempt_count        INTEGER     NOT NULL DEFAULT 0,
            last_error           TEXT,
            last_error_code      TEXT,
            created_at           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            next_retry_after     TIMESTAMPTZ,
            sent_at              TIMESTAMPTZ,
            provider_accepted_at TIMESTAMPTZ,
            delivered_at         TIMESTAMPTZ,
            CONSTRAINT mesh_jobs_status_check CHECK (status IN (
                'pending',
                'sent',
                'provider_accepted',
                'delivered',
                'failed',
                'fallback_triggered'
            ))
        )
        """
    )
    op.execute(
        """
        CREATE INDEX idx_mesh_jobs_status_retry
            ON mesh_jobs (status, next_retry_after)
        """
    )

    # -------------------------------------------------------------------------
    # delivery_jobs: add is_fallback flag
    # -------------------------------------------------------------------------
    op.execute(
        """
        ALTER TABLE delivery_jobs
            ADD COLUMN is_fallback BOOLEAN NOT NULL DEFAULT FALSE
        """
    )


def downgrade() -> None:
    # Reverse order: drop the column first, then the table.
    op.execute(
        """
        ALTER TABLE delivery_jobs
            DROP COLUMN IF EXISTS is_fallback
        """
    )
    op.execute("DROP TABLE IF EXISTS mesh_jobs")
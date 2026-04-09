"""0015 — admin audit log

Creates the admin_audit_log table for recording all mutating admin actions
and authentication events.

Design decisions:
- No foreign keys. The log is append-only and must remain readable even
  if a user or practice record is later deleted.
- BIGSERIAL primary key. Sequential IDs are sufficient for this use case
  and simplify cursor-based pagination.
- detail column is JSONB. Shape is freeform and documented per action type
  in AuditRepository. No enforced envelope.
- ip_address and session_id are nullable. Auth events that precede session
  creation (e.g. auth.code_requested) have no session_id. ip_address may
  be absent in test/dev environments.

Indexes:
- (occurred_at DESC)              — primary sort for the audit log view
- (actor_email)                   — filter by actor
- (practice_id, occurred_at DESC) — multi-tenant filtering
- (action)                        — prefix-match filtering (WHERE action LIKE 'x%')
                                    btree supports left-anchored LIKE queries

Revision ID: 0015
Revises: 0014
"""

from alembic import op

revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE admin_audit_log (
            id           BIGSERIAL    PRIMARY KEY,
            occurred_at  TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
            practice_id  TEXT         NOT NULL,
            actor_email  TEXT         NOT NULL,
            action       TEXT         NOT NULL,
            resource     TEXT,
            detail       JSONB,
            ip_address   TEXT,
            session_id   TEXT
        )
        """
    )

    op.execute(
        "CREATE INDEX ix_admin_audit_log_occurred_at "
        "ON admin_audit_log (occurred_at DESC)"
    )
    op.execute(
        "CREATE INDEX ix_admin_audit_log_actor_email "
        "ON admin_audit_log (actor_email)"
    )
    op.execute(
        "CREATE INDEX ix_admin_audit_log_practice_id "
        "ON admin_audit_log (practice_id, occurred_at DESC)"
    )
    op.execute(
        "CREATE INDEX ix_admin_audit_log_action "
        "ON admin_audit_log (action)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS admin_audit_log")
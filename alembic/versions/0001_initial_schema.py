"""0001 — complete initial schema

Single migration that creates all tables from scratch.
"""

from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # -------------------------------------------------------------------------
    # practices
    # Referenced by all practice-scoped tables; must be created first.
    # -------------------------------------------------------------------------
    op.execute(
        """
        CREATE TABLE practices (
            practice_id TEXT        PRIMARY KEY,
            name        TEXT        NOT NULL,
            email       TEXT        NOT NULL,
            created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )

    # -------------------------------------------------------------------------
    # runtime_state_versions
    # Stores versioned form-engine state snapshots. No FK to practices —
    # runtime_id is app-generated and scoped by convention.
    # -------------------------------------------------------------------------
    op.execute(
        """
        CREATE TABLE runtime_state_versions (
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

    # -------------------------------------------------------------------------
    # practice_signposting
    # Per-practice, per-condition signposting content configured in the admin UI.
    # -------------------------------------------------------------------------
    op.execute(
        """
        CREATE TABLE practice_signposting (
            practice_id      TEXT        NOT NULL REFERENCES practices(practice_id),
            condition_id     TEXT        NOT NULL,
            signposting_json TEXT        NOT NULL,
            updated_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            PRIMARY KEY (practice_id, condition_id)
        )
        """
    )

    # -------------------------------------------------------------------------
    # submission_records
    # One row per completed patient form submission.
    # Note: submitted_at has no DEFAULT — the application must supply the value
    # explicitly to ensure a single authoritative timestamp (see form_router.py).
    # -------------------------------------------------------------------------
    op.execute(
        """
        CREATE TABLE submission_records (
            submission_id        TEXT        PRIMARY KEY,
            practice_id          TEXT        NOT NULL,
            condition_id         TEXT        NOT NULL,
            clinical_output_json JSONB       NOT NULL,
            audit_output_json    JSONB       NOT NULL,
            submitted_at         TIMESTAMPTZ NOT NULL,
            condition_label      TEXT        NOT NULL DEFAULT ''
        )
        """
    )

    # -------------------------------------------------------------------------
    # submission_attachments
    # Stores the generated PDF bytes separately from submission_records so that
    # blob data is never loaded by queries against the main submissions table.
    # -------------------------------------------------------------------------
    op.execute(
        """
        CREATE TABLE submission_attachments (
            submission_id TEXT PRIMARY KEY
                REFERENCES submission_records(submission_id),
            pdf_bytes     BYTEA NOT NULL
        )
        """
    )

    # -------------------------------------------------------------------------
    # submission_photos
    # Raw photo bytes uploaded by patients. Read by the PDF worker to embed
    # images in the generated PDF. Deleted by the nightly deletion job once
    # delivery is confirmed (delivery_jobs.status = 'sent').
    # -------------------------------------------------------------------------
    op.execute(
        """
        CREATE TABLE submission_photos (
            submission_id  TEXT    NOT NULL REFERENCES submission_records(submission_id),
            photo_index    INTEGER NOT NULL,
            photo_bytes    BYTEA   NOT NULL,
            PRIMARY KEY (submission_id, photo_index)
        )
        """
    )

    # -------------------------------------------------------------------------
    # practice_availability
    # Weekly schedule and override configuration for the availability gate.
    # -------------------------------------------------------------------------
    op.execute(
        """
        CREATE TABLE practice_availability (
            practice_id        TEXT     PRIMARY KEY REFERENCES practices(practice_id),
            is_active          BOOLEAN  NOT NULL DEFAULT false,
            weekly_open_days   TEXT[]   NOT NULL DEFAULT '{}',
            open_time          TIME     NOT NULL DEFAULT '08:00',
            close_time         TIME     NOT NULL DEFAULT '18:30',
            closed_message     TEXT,
            override_status    TEXT     CHECK (override_status IN ('open', 'closed')),
            override_expires_at TIMESTAMPTZ,
            override_message   TEXT,
            CONSTRAINT weekly_open_days_valid CHECK (
                weekly_open_days <@ ARRAY['mon','tue','wed','thu','fri','sat','sun']::TEXT[]
            )
        )
        """
    )

    # -------------------------------------------------------------------------
    # practice_availability_exceptions
    # Per-date schedule overrides (closures or custom hours).
    # -------------------------------------------------------------------------
    op.execute(
        """
        CREATE TABLE practice_availability_exceptions (
            practice_id     TEXT NOT NULL REFERENCES practices(practice_id),
            exception_date  DATE NOT NULL,
            exception_type  TEXT NOT NULL CHECK (exception_type IN ('closed', 'custom_hours')),
            open_time       TIME,
            close_time      TIME,
            note            TEXT,
            PRIMARY KEY (practice_id, exception_date)
        )
        """
    )

    # -------------------------------------------------------------------------
    # practice_doctors
    # Ordered list of doctor names per practice for the patient Contact screen.
    # -------------------------------------------------------------------------
    op.execute(
        """
        CREATE TABLE practice_doctors (
            id            SERIAL  PRIMARY KEY,
            practice_id   TEXT    NOT NULL REFERENCES practices(practice_id),
            name          TEXT    NOT NULL,
            display_order INTEGER NOT NULL
        )
        """
    )

    # -------------------------------------------------------------------------
    # pdf_jobs
    # Queues PDF generation work for the async PDF worker.
    # One job per submission. The PDF worker claims and processes pending jobs.
    # -------------------------------------------------------------------------
    op.execute(
        """
        CREATE TABLE pdf_jobs (
            id               UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
            submission_id    TEXT        NOT NULL REFERENCES submission_records(submission_id),
            status           TEXT        NOT NULL DEFAULT 'pending'
                                         CHECK (status IN ('pending', 'done', 'failed')),
            attempt_count    INTEGER     NOT NULL DEFAULT 0,
            last_error       TEXT,
            next_retry_after TIMESTAMPTZ,
            attachment_count INTEGER     NOT NULL,
            delivery_email   TEXT        NOT NULL,
            created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    op.execute(
        """
        CREATE INDEX idx_pdf_jobs_status_retry
            ON pdf_jobs (status, next_retry_after)
        """
    )

    # -------------------------------------------------------------------------
    # delivery_jobs
    # Queues email delivery work for the async delivery worker.
    # One job per submission (enforced by UNIQUE constraint).
    # Ordering invariant: a delivery_jobs row is only created after
    # save_attachment has completed.
    # -------------------------------------------------------------------------
    op.execute(
        """
        CREATE TABLE delivery_jobs (
            id               UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
            submission_id    TEXT        NOT NULL REFERENCES submission_records(submission_id),
            status           TEXT        NOT NULL DEFAULT 'pending'
                                         CHECK (status IN ('pending', 'sent', 'failed')),
            attempt_count    INTEGER     NOT NULL DEFAULT 0,
            last_error       TEXT,
            next_retry_after TIMESTAMPTZ,
            to_email         TEXT        NOT NULL,
            condition_label  TEXT        NOT NULL,
            submitted_at     TIMESTAMPTZ NOT NULL,
            created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE (submission_id)
        )
        """
    )
    op.execute(
        """
        CREATE INDEX idx_delivery_jobs_status_retry
            ON delivery_jobs (status, next_retry_after)
        """
    )

    # -------------------------------------------------------------------------
    # admin_users
    # Registered admin/staff accounts, scoped to a practice.
    # Role is enforced at the application layer (admin/staff).
    # -------------------------------------------------------------------------
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

    # -------------------------------------------------------------------------
    # admin_auth_codes
    # In-flight MFA codes. Email is the PK so an upsert replaces any existing
    # code, enforcing one in-flight code per user at a time.
    # -------------------------------------------------------------------------
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

    # -------------------------------------------------------------------------
    # admin_sessions
    # Active sessions created after successful MFA verification.
    # Expired sessions are cleaned up lazily inside AuthRepository.create_session.
    # -------------------------------------------------------------------------
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

    # -------------------------------------------------------------------------
    # admin_audit_log
    # Append-only log of all mutating admin actions and authentication events.
    # No foreign keys — the log must remain readable even if a user or practice
    # record is later deleted.
    # -------------------------------------------------------------------------
    op.execute(
        """
        CREATE TABLE admin_audit_log (
            id          BIGSERIAL   PRIMARY KEY,
            occurred_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            practice_id TEXT        NOT NULL,
            actor_email TEXT        NOT NULL,
            action      TEXT        NOT NULL,
            resource    TEXT,
            detail      JSONB,
            ip_address  TEXT,
            session_id  TEXT
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
    # Drop in reverse foreign-key dependency order.
    op.execute("DROP TABLE IF EXISTS admin_audit_log")
    op.execute("DROP TABLE IF EXISTS admin_sessions")
    op.execute("DROP TABLE IF EXISTS admin_auth_codes")
    op.execute("DROP TABLE IF EXISTS admin_users")
    op.execute("DROP TABLE IF EXISTS delivery_jobs")
    op.execute("DROP TABLE IF EXISTS pdf_jobs")
    op.execute("DROP TABLE IF EXISTS practice_doctors")
    op.execute("DROP TABLE IF EXISTS practice_availability_exceptions")
    op.execute("DROP TABLE IF EXISTS practice_availability")
    op.execute("DROP TABLE IF EXISTS submission_photos")
    op.execute("DROP TABLE IF EXISTS submission_attachments")
    op.execute("DROP TABLE IF EXISTS submission_records")
    op.execute("DROP TABLE IF EXISTS practice_signposting")
    op.execute("DROP TABLE IF EXISTS runtime_state_versions")
    op.execute("DROP TABLE IF EXISTS practices")

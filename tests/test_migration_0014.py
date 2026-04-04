"""
tests/test_migration_0014.py

Integration test for Alembic migration 0014 (admin auth tables).

Verifies:
- upgrade() produces all three tables with the expected columns
- downgrade() removes all three tables cleanly

This test is destructive: it runs downgrade() and then upgrade() against
the test database. It must only run against TEST_DATABASE_URL, never
against the production DATABASE_URL.

Run via:
    make test-integration
or directly:
    TEST_DATABASE_URL=... python -m pytest tests/test_migration_0014.py -v
"""

import os
import pytest

# ---------------------------------------------------------------------------
# Database guardrail — must be first, before any app imports.
# ---------------------------------------------------------------------------

if "TEST_DATABASE_URL" not in os.environ:
    pytest.skip(
        "TEST_DATABASE_URL not set — skipping migration test to protect production data",
        allow_module_level=True,
    )

os.environ.setdefault("DATABASE_URL", os.environ["TEST_DATABASE_URL"])
os.environ.setdefault("DEV_MODE", "1")
os.environ.setdefault("PRACTICE_ID", "test-practice")

from alembic.config import Config  # noqa: E402
from alembic import command  # noqa: E402
from app.core.db import get_conn  # noqa: E402

DATABASE_URL = os.environ["TEST_DATABASE_URL"]

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_alembic_cfg() -> Config:
    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", DATABASE_URL)
    return cfg


def _table_columns(table_name: str) -> set[str]:
    """Return the set of column names for a table, or empty set if absent."""
    with get_conn(DATABASE_URL) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT column_name
                FROM information_schema.columns
                WHERE table_schema = 'public'
                  AND table_name = %s
                """,
                (table_name,),
            )
            rows = cur.fetchall()
    return {row[0] for row in rows}


def _table_exists(table_name: str) -> bool:
    return len(_table_columns(table_name)) > 0


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_upgrade_creates_admin_users_with_expected_columns():
    cfg = _make_alembic_cfg()
    command.upgrade(cfg, "0014")

    cols = _table_columns("admin_users")
    assert "id" in cols
    assert "email" in cols
    assert "practice_id" in cols
    assert "role" in cols
    assert "created_at" in cols


def test_upgrade_creates_admin_auth_codes_with_expected_columns():
    cols = _table_columns("admin_auth_codes")
    assert "email" in cols
    assert "hashed_code" in cols
    assert "expires_at" in cols
    assert "attempts_count" in cols
    assert "last_requested_at" in cols


def test_upgrade_creates_admin_sessions_with_expected_columns():
    cols = _table_columns("admin_sessions")
    assert "session_id" in cols
    assert "user_id" in cols
    assert "expires_at" in cols
    assert "created_at" in cols


def test_downgrade_removes_all_three_tables():
    cfg = _make_alembic_cfg()
    command.downgrade(cfg, "0013")

    assert not _table_exists("admin_sessions"), "admin_sessions should not exist after downgrade"
    assert not _table_exists("admin_auth_codes"), "admin_auth_codes should not exist after downgrade"
    assert not _table_exists("admin_users"), "admin_users should not exist after downgrade"


def test_upgrade_again_after_downgrade_succeeds():
    """Verify the migration is re-runnable — important for CI."""
    cfg = _make_alembic_cfg()
    command.upgrade(cfg, "0014")

    assert _table_exists("admin_users")
    assert _table_exists("admin_auth_codes")
    assert _table_exists("admin_sessions")
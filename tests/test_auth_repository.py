"""
Integration tests for AuthRepository.update_session_expiry.

Requires TEST_DATABASE_URL in the environment.
Run via: make test-integration

Each test creates its own practice/user/session rows and cleans them up in
a finally block, following the pattern in tests/test_repositories.py.
"""

import os

import pytest

if "TEST_DATABASE_URL" not in os.environ:
    pytest.skip(
        "TEST_DATABASE_URL not set — skipping integration tests to protect production data",
        allow_module_level=True,
    )

os.environ.setdefault("DATABASE_URL", os.environ["TEST_DATABASE_URL"])
os.environ.setdefault("PRACTICE_ID", "test-practice")

pytestmark = pytest.mark.integration

from datetime import UTC, datetime, timedelta  # noqa: E402
from uuid import uuid4  # noqa: E402

from app.core.db import get_conn  # noqa: E402
from app.repositories.auth_repository import AuthRepository  # noqa: E402

DATABASE_URL = os.environ["TEST_DATABASE_URL"]


def _uid() -> str:
    return f"test_{uuid4().hex[:8]}"


def _make_repo() -> AuthRepository:
    return AuthRepository(DATABASE_URL)


def _setup_session(practice_id: str, email: str, session_id: str, expires_at: datetime) -> None:
    with get_conn(DATABASE_URL) as conn, conn.cursor() as cur:
        cur.execute(
            "INSERT INTO practices (practice_id, name, email) VALUES (%s, %s, %s)",
            (practice_id, "Test Practice", "practice@example.com"),
        )
        cur.execute(
            "INSERT INTO admin_users (email, practice_id, role) "
            "VALUES (%s, %s, %s) RETURNING id::text",
            (email, practice_id, "admin"),
        )
        user_id = cur.fetchone()[0]
        cur.execute(
            "INSERT INTO admin_sessions (session_id, user_id, expires_at) "
            "VALUES (%s::uuid, %s::uuid, %s)",
            (session_id, user_id, expires_at),
        )


def _get_expires_at(session_id: str) -> datetime:
    with get_conn(DATABASE_URL) as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT expires_at FROM admin_sessions WHERE session_id = %s::uuid",
            (session_id,),
        )
        row = cur.fetchone()
    return row[0]


def _cleanup(practice_id: str) -> None:
    with get_conn(DATABASE_URL) as conn, conn.cursor() as cur:
        cur.execute(
            "DELETE FROM admin_sessions WHERE user_id IN "
            "(SELECT id FROM admin_users WHERE practice_id = %s)",
            (practice_id,),
        )
        cur.execute("DELETE FROM admin_users WHERE practice_id = %s", (practice_id,))
        cur.execute("DELETE FROM practices WHERE practice_id = %s", (practice_id,))


def test_update_session_expiry_extends_expiry():
    repo = _make_repo()
    practice_id = _uid()
    session_id = str(uuid4())
    original_expiry = datetime.now(UTC) + timedelta(minutes=1)

    try:
        _setup_session(practice_id, "admin@example.com", session_id, original_expiry)

        repo.update_session_expiry(session_id, ttl_minutes=60)

        new_expiry = _get_expires_at(session_id)
        assert new_expiry > original_expiry
        assert new_expiry > datetime.now(UTC) + timedelta(minutes=50)
    finally:
        _cleanup(practice_id)


def test_update_session_expiry_noops_on_unknown_session():
    repo = _make_repo()
    unknown_session_id = str(uuid4())

    # Should not raise even though no row matches.
    repo.update_session_expiry(unknown_session_id, ttl_minutes=60)

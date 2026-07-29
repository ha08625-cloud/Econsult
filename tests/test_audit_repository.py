"""
tests/test_audit_repository.py

Integration tests for AuditRepository against a live Postgres database.

All prior AuditRepository coverage (tests/routers/test_admin_audit_router.py)
stubs the repository or mocks psycopg2's connection to inspect the SQL
parameters built for date boundaries. None of it exercises admin_audit_log
itself, so cursor round-tripping, tuple-comparison pagination across
timestamp ties, real date-boundary filtering, and the prefix filter have
never run against a real database. This file closes that gap.

Requires TEST_DATABASE_URL in the environment.
Run via: make test-integration

Design notes:
- admin_audit_log has no foreign keys, so cleanup is a single DELETE keyed
  on practice_id. Each test uses a unique practice_id and cleans up in a
  finally block, matching test_repositories.py.
- log_event always stamps occurred_at via the database's NOW() default, so
  it cannot be used to build fixtures with controlled timestamps. Tests that
  need specific timestamps (ties, boundaries) insert directly via SQL with
  an explicit occurred_at, mirroring the backdating helpers in
  test_mesh_repository.py.
"""

import os

import pytest

# ---------------------------------------------------------------------------
# Database guardrail — must be first, before any app imports.
# ---------------------------------------------------------------------------

if "TEST_DATABASE_URL" not in os.environ:
    pytest.skip(
        "TEST_DATABASE_URL not set — skipping integration tests to protect production data",
        allow_module_level=True,
    )

os.environ.setdefault("DATABASE_URL", os.environ["TEST_DATABASE_URL"])
os.environ.setdefault("PRACTICE_ID", "test-practice")

pytestmark = pytest.mark.integration

from datetime import UTC, date, datetime, timedelta  # noqa: E402
from uuid import uuid4  # noqa: E402

import psycopg2.extras  # noqa: E402

from app.core.db import get_conn  # noqa: E402
from app.repositories.audit_repository import AuditRepository  # noqa: E402

DATABASE_URL = os.environ["TEST_DATABASE_URL"]


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _uid() -> str:
    return f"test_{uuid4().hex[:8]}"


def _make_repo() -> AuditRepository:
    return AuditRepository(DATABASE_URL)


def _insert_event(
    practice_id: str,
    occurred_at: datetime,
    *,
    actor_email: str = "actor@example.com",
    action: str = "test.action",
    resource: str | None = None,
    detail: dict | None = None,
    ip_address: str | None = None,
    session_id: str | None = None,
) -> int:
    """
    Insert a row directly via SQL with an explicit occurred_at.

    log_event always relies on the column's NOW() default, so it cannot
    produce rows with controlled or tied timestamps. Returns the new id.
    """
    detail_value = psycopg2.extras.Json(detail) if detail is not None else None
    with get_conn(DATABASE_URL) as conn, conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO admin_audit_log
                (occurred_at, practice_id, actor_email, action,
                 resource, detail, ip_address, session_id)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
            """,
            (
                occurred_at,
                practice_id,
                actor_email,
                action,
                resource,
                detail_value,
                ip_address,
                session_id,
            ),
        )
        return cur.fetchone()[0]


def _cleanup(practice_id: str) -> None:
    with get_conn(DATABASE_URL) as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM admin_audit_log WHERE practice_id = %s", (practice_id,))


# ---------------------------------------------------------------------------
# log_event
# ---------------------------------------------------------------------------


def test_log_event_round_trips_through_list_events():
    repo = _make_repo()
    pid = _uid()
    try:
        repo.log_event(
            practice_id=pid,
            actor_email="admin@example.com",
            action="practice.email.updated",
            resource="practice",
            detail={"before": "old@example.com", "after": "new@example.com"},
            ip_address="203.0.113.5",
            session_id="live-session-token",
        )

        page = repo.list_events(practice_id=pid)
        assert len(page["events"]) == 1
        event = page["events"][0]
        assert event["actor_email"] == "admin@example.com"
        assert event["action"] == "practice.email.updated"
        assert event["resource"] == "practice"
        assert event["detail"] == {"before": "old@example.com", "after": "new@example.com"}
        assert event["ip_address"] == "203.0.113.5"
        # session_id is never selected, even though it was written.
        assert "session_id" not in event
    finally:
        _cleanup(pid)


def test_log_event_with_conn_does_not_commit_independently():
    """
    When a connection is supplied, log_event must not commit on its own —
    the caller owns the transaction. A rollback on the caller's connection
    must discard the insert.
    """
    repo = _make_repo()
    pid = _uid()
    try:
        with get_conn(DATABASE_URL) as conn:
            repo.log_event(
                practice_id=pid,
                actor_email="admin@example.com",
                action="test.rolled_back",
                conn=conn,
            )
            conn.rollback()

        page = repo.list_events(practice_id=pid)
        assert page["events"] == []
    finally:
        _cleanup(pid)


# ---------------------------------------------------------------------------
# Cursor round-trip
# ---------------------------------------------------------------------------


def test_cursor_round_trip_covers_every_row_without_gap_or_duplicate():
    repo = _make_repo()
    pid = _uid()
    base = datetime(2024, 3, 1, 12, 0, 0, tzinfo=UTC)
    try:
        ids = [
            _insert_event(pid, base + timedelta(minutes=i), action=f"test.event_{i}")
            for i in range(5)
        ]

        seen_ids: list[int] = []
        cursor = None
        pages = 0
        while True:
            page = repo.list_events(practice_id=pid, cursor=cursor, limit=2)
            seen_ids.extend(e["id"] for e in page["events"])
            pages += 1
            cursor = page["next_cursor"]
            if cursor is None:
                break
            assert pages < 10, "pagination did not terminate"

        # Newest-first pages, reassembled, must equal the full inserted set
        # with no gaps or duplicates — this is what the cursor round-trip
        # guarantees.
        assert sorted(seen_ids) == sorted(ids)
        assert len(seen_ids) == len(set(seen_ids))
        assert pages == 3  # 5 rows at limit=2 -> 2, 2, 1
    finally:
        _cleanup(pid)


def test_cursor_from_last_page_is_none():
    repo = _make_repo()
    pid = _uid()
    base = datetime(2024, 3, 2, 9, 0, 0, tzinfo=UTC)
    try:
        _insert_event(pid, base, action="test.only_event")

        page = repo.list_events(practice_id=pid, limit=50)
        assert len(page["events"]) == 1
        assert page["next_cursor"] is None
    finally:
        _cleanup(pid)


# ---------------------------------------------------------------------------
# Tuple pagination across timestamp ties
# ---------------------------------------------------------------------------


def test_pagination_breaks_ties_on_id_with_no_gap_or_duplicate():
    """
    Several rows sharing the exact same occurred_at must still paginate
    cleanly. A cursor built from occurred_at alone would either skip or
    repeat tied rows; the (occurred_at, id) tuple comparison must not.
    """
    repo = _make_repo()
    pid = _uid()
    tied_at = datetime(2024, 3, 3, 15, 0, 0, tzinfo=UTC)
    try:
        ids = [_insert_event(pid, tied_at, action=f"test.tied_{i}") for i in range(4)]

        page1 = repo.list_events(practice_id=pid, limit=2)
        assert [e["id"] for e in page1["events"]] == sorted(ids, reverse=True)[:2]
        assert page1["next_cursor"] is not None

        page2 = repo.list_events(practice_id=pid, cursor=page1["next_cursor"], limit=2)
        assert [e["id"] for e in page2["events"]] == sorted(ids, reverse=True)[2:]
        assert page2["next_cursor"] is None

        all_ids = [e["id"] for e in page1["events"]] + [e["id"] for e in page2["events"]]
        assert sorted(all_ids) == sorted(ids)
        assert len(all_ids) == len(set(all_ids))
    finally:
        _cleanup(pid)


# ---------------------------------------------------------------------------
# Date boundaries
# ---------------------------------------------------------------------------


def test_from_date_and_to_date_are_inclusive_at_utc_midnight_boundaries():
    repo = _make_repo()
    pid = _uid()
    try:
        just_before = _insert_event(
            pid, datetime(2024, 5, 31, 23, 59, 59, tzinfo=UTC), action="test.just_before"
        )
        at_from_boundary = _insert_event(
            pid, datetime(2024, 6, 1, 0, 0, 0, tzinfo=UTC), action="test.at_from_boundary"
        )
        at_to_boundary = _insert_event(
            pid,
            datetime(2024, 6, 1, 23, 59, 59, 999999, tzinfo=UTC),
            action="test.at_to_boundary",
        )
        just_after = _insert_event(
            pid, datetime(2024, 6, 2, 0, 0, 0, tzinfo=UTC), action="test.just_after"
        )

        page = repo.list_events(
            practice_id=pid, from_date=date(2024, 6, 1), to_date=date(2024, 6, 1), limit=50
        )
        returned_ids = {e["id"] for e in page["events"]}

        assert returned_ids == {at_from_boundary, at_to_boundary}
        assert just_before not in returned_ids
        assert just_after not in returned_ids
    finally:
        _cleanup(pid)


def test_from_date_only_excludes_earlier_rows():
    repo = _make_repo()
    pid = _uid()
    try:
        earlier = _insert_event(
            pid, datetime(2024, 7, 1, 10, 0, 0, tzinfo=UTC), action="test.earlier"
        )
        later = _insert_event(pid, datetime(2024, 7, 5, 10, 0, 0, tzinfo=UTC), action="test.later")

        page = repo.list_events(practice_id=pid, from_date=date(2024, 7, 3), limit=50)
        returned_ids = {e["id"] for e in page["events"]}

        assert returned_ids == {later}
        assert earlier not in returned_ids
    finally:
        _cleanup(pid)


# ---------------------------------------------------------------------------
# action_prefix filter
# ---------------------------------------------------------------------------


def test_action_prefix_matches_only_left_anchored_rows():
    repo = _make_repo()
    pid = _uid()
    base = datetime(2024, 8, 1, tzinfo=UTC)
    try:
        matching_1 = _insert_event(pid, base, action="availability.config.updated")
        matching_2 = _insert_event(
            pid, base + timedelta(seconds=1), action="availability.override.updated"
        )
        non_matching = _insert_event(
            pid, base + timedelta(seconds=2), action="practice.email.updated"
        )
        # Must not match as a substring — the prefix is left-anchored only.
        substring_only = _insert_event(
            pid, base + timedelta(seconds=3), action="user.availability.other"
        )

        page = repo.list_events(practice_id=pid, action_prefix="availability", limit=50)
        returned_ids = {e["id"] for e in page["events"]}

        assert returned_ids == {matching_1, matching_2}
        assert non_matching not in returned_ids
        assert substring_only not in returned_ids
    finally:
        _cleanup(pid)


def test_action_prefix_raises_for_invalid_characters():
    repo = _make_repo()
    with pytest.raises(ValueError):
        repo.list_events(practice_id=_uid(), action_prefix="UPPERCASE_INVALID")

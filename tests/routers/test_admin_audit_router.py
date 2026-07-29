"""
tests/test_admin_audit_router.py

Tests for the admin audit log endpoint (GET /admin/audit-log).
"""

import unittest
from datetime import UTC, date, datetime

from fastapi.testclient import TestClient

from tests.helpers.admin_test_helpers import TEST_SESSION_COOKIE, StubAuditRepo, make_test_app

# ---------------------------------------------------------------------------
# Specialized Audit Stubs
# ---------------------------------------------------------------------------


class ConfigurableAuditRepo(StubAuditRepo):
    """
    Audit repo stub whose list_events return value can be configured
    per test. Also records the kwargs list_events was called with.
    """

    def __init__(self, return_value=None):
        super().__init__()
        self._return_value = return_value or {"events": [], "next_cursor": None}
        self.list_calls = []

    def list_events(
        self,
        *,
        practice_id,
        cursor=None,
        from_date=None,
        to_date=None,
        actor=None,
        action_prefix=None,
        limit=50,
    ):
        self.list_calls.append(
            {
                "practice_id": practice_id,
                "cursor": cursor,
                "from_date": from_date,
                "to_date": to_date,
                "actor": actor,
                "action_prefix": action_prefix,
                "limit": limit,
            }
        )
        return self._return_value


class RaisingAuditRepo(StubAuditRepo):
    """Audit repo stub whose list_events raises a given exception."""

    def __init__(self, exc):
        super().__init__()
        self._exc = exc

    def list_events(self, **kwargs):
        raise self._exc


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestAuditLogEndpoint(unittest.TestCase):
    """Tests for GET /admin/audit-log."""

    def _make_client(self, audit_repo=None):
        app = make_test_app(audit_repo=audit_repo)
        return TestClient(app, raise_server_exceptions=False)

    # ------------------------------------------------------------------
    # Auth
    # ------------------------------------------------------------------

    def test_unauthenticated_returns_401(self):
        client = self._make_client()
        res = client.get("/admin/audit-log")
        self.assertEqual(res.status_code, 401)

    # ------------------------------------------------------------------
    # Happy path
    # ------------------------------------------------------------------

    def test_authenticated_no_filters_returns_200(self):
        client = self._make_client()
        res = client.get("/admin/audit-log", cookies=TEST_SESSION_COOKIE)
        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertIn("events", body)
        self.assertIn("next_cursor", body)

    def test_empty_result_returns_empty_events_and_null_cursor(self):
        client = self._make_client()
        res = client.get("/admin/audit-log", cookies=TEST_SESSION_COOKIE)
        body = res.json()
        self.assertEqual(body["events"], [])
        self.assertIsNone(body["next_cursor"])

    def test_events_and_cursor_reflected_from_repo(self):
        repo = ConfigurableAuditRepo(
            return_value={
                "events": [
                    {
                        "id": 1,
                        "actor_email": "a@b.com",
                        "action": "auth.login.succeeded",
                        "occurred_at": None,
                        "practice_id": "test_practice",
                        "resource": None,
                        "detail": None,
                        "ip_address": None,
                        "session_id": None,
                    }
                ],
                "next_cursor": "abc123",
            }
        )
        client = self._make_client(audit_repo=repo)
        res = client.get("/admin/audit-log", cookies=TEST_SESSION_COOKIE)
        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertEqual(len(body["events"]), 1)
        self.assertEqual(body["next_cursor"], "abc123")

    def test_datetime_occurred_at_is_serialised_to_string(self):
        repo = ConfigurableAuditRepo(
            return_value={
                "events": [
                    {
                        "id": 1,
                        "actor_email": "a@b.com",
                        "action": "auth.login.succeeded",
                        "occurred_at": datetime(2024, 6, 1, 12, 0, 0, tzinfo=UTC),
                        "practice_id": "test_practice",
                        "resource": None,
                        "detail": None,
                        "ip_address": None,
                        "session_id": None,
                    }
                ],
                "next_cursor": None,
            }
        )
        client = self._make_client(audit_repo=repo)
        res = client.get("/admin/audit-log", cookies=TEST_SESSION_COOKIE)
        self.assertEqual(res.status_code, 200)
        occurred_at = res.json()["events"][0]["occurred_at"]
        self.assertIsInstance(occurred_at, str)
        self.assertIn("2024-06-01", occurred_at)

    # ------------------------------------------------------------------
    # Session token must never leave via this endpoint
    # ------------------------------------------------------------------

    def test_session_id_column_is_stripped_from_response(self):
        """The stored session_id is the live session cookie. Even if a
        repository hands one back, the endpoint must not return it."""
        repo = ConfigurableAuditRepo(
            return_value={
                "events": [
                    {
                        "id": 1,
                        "actor_email": "a@b.com",
                        "action": "auth.login.succeeded",
                        "occurred_at": None,
                        "practice_id": "test_practice",
                        "resource": None,
                        "detail": {"email": "a@b.com"},
                        "ip_address": None,
                        "session_id": "33333333-3333-3333-3333-333333333333",
                    }
                ],
                "next_cursor": None,
            }
        )
        client = self._make_client(audit_repo=repo)
        res = client.get("/admin/audit-log", cookies=TEST_SESSION_COOKIE)
        self.assertEqual(res.status_code, 200)
        self.assertNotIn("session_id", res.json()["events"][0])
        self.assertNotIn("33333333-3333-3333-3333-333333333333", res.text)

    def test_session_id_inside_detail_is_stripped_from_response(self):
        """Legacy rows may carry a raw session id in the detail JSON."""
        repo = ConfigurableAuditRepo(
            return_value={
                "events": [
                    {
                        "id": 1,
                        "actor_email": "unknown",
                        "action": "auth.logout",
                        "occurred_at": None,
                        "practice_id": "test_practice",
                        "resource": None,
                        "detail": {
                            "session_id": "33333333-3333-3333-3333-333333333333",
                            "email": "a@b.com",
                        },
                        "ip_address": None,
                    }
                ],
                "next_cursor": None,
            }
        )
        client = self._make_client(audit_repo=repo)
        res = client.get("/admin/audit-log", cookies=TEST_SESSION_COOKIE)
        self.assertEqual(res.status_code, 200)
        detail = res.json()["events"][0]["detail"]
        self.assertNotIn("session_id", detail)
        self.assertEqual(detail, {"email": "a@b.com"})

    # ------------------------------------------------------------------
    # Query parameter forwarding
    # ------------------------------------------------------------------

    def test_query_params_forwarded_to_repo(self):
        repo = ConfigurableAuditRepo()
        client = self._make_client(audit_repo=repo)
        client.get(
            "/admin/audit-log",
            cookies=TEST_SESSION_COOKIE,
            params={
                "from_date": "2024-01-01",
                "to_date": "2024-12-31",
                "actor": "admin@nhs.net",
                "action": "availability",
                "limit": "10",
            },
        )
        self.assertEqual(len(repo.list_calls), 1)
        call = repo.list_calls[0]
        self.assertEqual(call["from_date"], date(2024, 1, 1))
        self.assertEqual(call["to_date"], date(2024, 12, 31))
        self.assertEqual(call["actor"], "admin@nhs.net")
        self.assertEqual(call["action_prefix"], "availability")
        self.assertEqual(call["limit"], 10)

    def test_cursor_forwarded_to_repo(self):
        repo = ConfigurableAuditRepo()
        client = self._make_client(audit_repo=repo)
        client.get(
            "/admin/audit-log",
            cookies=TEST_SESSION_COOKIE,
            params={"cursor": "opaque-token"},
        )
        self.assertEqual(repo.list_calls[0]["cursor"], "opaque-token")

    # ------------------------------------------------------------------
    # Limit clamping
    # ------------------------------------------------------------------

    def test_limit_above_200_is_clamped_to_200(self):
        repo = ConfigurableAuditRepo()
        client = self._make_client(audit_repo=repo)
        res = client.get("/admin/audit-log", cookies=TEST_SESSION_COOKIE, params={"limit": "999"})
        self.assertEqual(res.status_code, 200)
        self.assertEqual(repo.list_calls[0]["limit"], 200)

    def test_limit_below_1_is_clamped_to_1(self):
        repo = ConfigurableAuditRepo()
        client = self._make_client(audit_repo=repo)
        res = client.get("/admin/audit-log", cookies=TEST_SESSION_COOKIE, params={"limit": "0"})
        self.assertEqual(res.status_code, 200)
        self.assertEqual(repo.list_calls[0]["limit"], 1)

    # ------------------------------------------------------------------
    # Input validation errors
    # ------------------------------------------------------------------

    def test_invalid_from_date_format_returns_422(self):
        client = self._make_client()
        res = client.get(
            "/admin/audit-log",
            cookies=TEST_SESSION_COOKIE,
            params={"from_date": "not-a-date"},
        )
        self.assertEqual(res.status_code, 422)

    def test_invalid_to_date_format_returns_422(self):
        client = self._make_client()
        res = client.get(
            "/admin/audit-log",
            cookies=TEST_SESSION_COOKIE,
            params={"to_date": "31/12/2024"},
        )
        self.assertEqual(res.status_code, 422)

    def test_malformed_cursor_returns_400(self):
        repo = RaisingAuditRepo(ValueError("Invalid pagination cursor: bad data"))
        client = self._make_client(audit_repo=repo)
        res = client.get(
            "/admin/audit-log",
            cookies=TEST_SESSION_COOKIE,
            params={"cursor": "not-valid-base64-cursor"},
        )
        self.assertEqual(res.status_code, 400)

    def test_invalid_action_prefix_returns_400(self):
        repo = RaisingAuditRepo(ValueError("action_prefix must match ^[a-z0-9_.]+$"))
        client = self._make_client(audit_repo=repo)
        res = client.get(
            "/admin/audit-log",
            cookies=TEST_SESSION_COOKIE,
            params={"action": "UPPERCASE_INVALID"},
        )
        self.assertEqual(res.status_code, 400)


# ---------------------------------------------------------------------------
# AuditRepository.list_events — SQL parameter construction
# ---------------------------------------------------------------------------


class _RecordingCursor:
    """Minimal psycopg2 cursor stand-in that captures execute() arguments."""

    def __init__(self, sink):
        self._sink = sink

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def execute(self, query, params):
        self._sink["query"] = query
        self._sink["params"] = params

    def fetchall(self):
        return []


class _RecordingConn:
    def __init__(self, sink):
        self._sink = sink

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def cursor(self, **kwargs):
        return _RecordingCursor(self._sink)


class TestListEventsDateBoundaries(unittest.TestCase):
    """
    occurred_at is TIMESTAMPTZ. Naive boundary datetimes would be interpreted
    by Postgres in the session timezone, so the documented "midnight UTC"
    window would silently depend on database configuration.
    """

    def _run(self, **kwargs):
        from unittest.mock import patch

        from app.repositories.audit_repository import AuditRepository

        sink = {}
        with patch(
            "app.repositories.audit_repository.get_conn",
            return_value=_RecordingConn(sink),
        ):
            AuditRepository("postgresql://unused").list_events(practice_id="practice-1", **kwargs)
        return sink["params"]

    def test_from_date_boundary_is_utc_aware(self):
        params = self._run(from_date=date(2024, 6, 1))
        self.assertEqual(params["from_date"], datetime(2024, 6, 1, 0, 0, 0, tzinfo=UTC))
        self.assertIsNotNone(params["from_date"].tzinfo)

    def test_to_date_boundary_is_utc_aware(self):
        params = self._run(to_date=date(2024, 6, 1))
        self.assertEqual(params["to_date"], datetime(2024, 6, 1, 23, 59, 59, 999999, tzinfo=UTC))
        self.assertIsNotNone(params["to_date"].tzinfo)


if __name__ == "__main__":
    unittest.main(verbosity=2)

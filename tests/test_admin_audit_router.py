"""
tests/test_admin_audit_router.py

Tests for the admin audit log endpoint (GET /admin/audit-log).
"""
import os
import unittest
from datetime import datetime, timezone, date

from fastapi.testclient import TestClient

from tests.helpers.admin_test_helpers import make_test_app, StubAuditRepo


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

    def list_events(self, *, practice_id, cursor=None, from_date=None,
                    to_date=None, actor=None, action_prefix=None, limit=50):
        self.list_calls.append({
            "practice_id": practice_id,
            "cursor": cursor,
            "from_date": from_date,
            "to_date": to_date,
            "actor": actor,
            "action_prefix": action_prefix,
            "limit": limit,
        })
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

    _AUTH_HEADERS = {"Authorization": "Bearer dev-token"}

    def _make_client(self, audit_repo=None):
        os.environ["DEV_MODE"] = "1"
        app = make_test_app(audit_repo=audit_repo)
        return TestClient(app, raise_server_exceptions=False)

    def tearDown(self):
        os.environ.pop("DEV_MODE", None)

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
        res = client.get("/admin/audit-log", headers=self._AUTH_HEADERS)
        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertIn("events", body)
        self.assertIn("next_cursor", body)

    def test_empty_result_returns_empty_events_and_null_cursor(self):
        client = self._make_client()
        res = client.get("/admin/audit-log", headers=self._AUTH_HEADERS)
        body = res.json()
        self.assertEqual(body["events"], [])
        self.assertIsNone(body["next_cursor"])

    def test_events_and_cursor_reflected_from_repo(self):
        repo = ConfigurableAuditRepo(return_value={
            "events": [{"id": 1, "actor_email": "a@b.com", "action": "auth.login.succeeded",
                        "occurred_at": None, "practice_id": "test_practice",
                        "resource": None, "detail": None, "ip_address": None, "session_id": None}],
            "next_cursor": "abc123",
        })
        client = self._make_client(audit_repo=repo)
        res = client.get("/admin/audit-log", headers=self._AUTH_HEADERS)
        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertEqual(len(body["events"]), 1)
        self.assertEqual(body["next_cursor"], "abc123")

    def test_datetime_occurred_at_is_serialised_to_string(self):
        repo = ConfigurableAuditRepo(return_value={
            "events": [{"id": 1, "actor_email": "a@b.com", "action": "auth.login.succeeded",
                        "occurred_at": datetime(2024, 6, 1, 12, 0, 0, tzinfo=timezone.utc),
                        "practice_id": "test_practice", "resource": None, "detail": None,
                        "ip_address": None, "session_id": None}],
            "next_cursor": None,
        })
        client = self._make_client(audit_repo=repo)
        res = client.get("/admin/audit-log", headers=self._AUTH_HEADERS)
        self.assertEqual(res.status_code, 200)
        occurred_at = res.json()["events"][0]["occurred_at"]
        self.assertIsInstance(occurred_at, str)
        self.assertIn("2024-06-01", occurred_at)

    # ------------------------------------------------------------------
    # Query parameter forwarding
    # ------------------------------------------------------------------

    def test_query_params_forwarded_to_repo(self):
        repo = ConfigurableAuditRepo()
        client = self._make_client(audit_repo=repo)
        client.get(
            "/admin/audit-log",
            headers=self._AUTH_HEADERS,
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
            headers=self._AUTH_HEADERS,
            params={"cursor": "opaque-token"},
        )
        self.assertEqual(repo.list_calls[0]["cursor"], "opaque-token")

    # ------------------------------------------------------------------
    # Limit clamping
    # ------------------------------------------------------------------

    def test_limit_above_200_is_clamped_to_200(self):
        repo = ConfigurableAuditRepo()
        client = self._make_client(audit_repo=repo)
        res = client.get("/admin/audit-log", headers=self._AUTH_HEADERS, params={"limit": "999"})
        self.assertEqual(res.status_code, 200)
        self.assertEqual(repo.list_calls[0]["limit"], 200)

    def test_limit_below_1_is_clamped_to_1(self):
        repo = ConfigurableAuditRepo()
        client = self._make_client(audit_repo=repo)
        res = client.get("/admin/audit-log", headers=self._AUTH_HEADERS, params={"limit": "0"})
        self.assertEqual(res.status_code, 200)
        self.assertEqual(repo.list_calls[0]["limit"], 1)

    # ------------------------------------------------------------------
    # Input validation errors
    # ------------------------------------------------------------------

    def test_invalid_from_date_format_returns_422(self):
        client = self._make_client()
        res = client.get(
            "/admin/audit-log",
            headers=self._AUTH_HEADERS,
            params={"from_date": "not-a-date"},
        )
        self.assertEqual(res.status_code, 422)

    def test_invalid_to_date_format_returns_422(self):
        client = self._make_client()
        res = client.get(
            "/admin/audit-log",
            headers=self._AUTH_HEADERS,
            params={"to_date": "31/12/2024"},
        )
        self.assertEqual(res.status_code, 422)

    def test_malformed_cursor_returns_400(self):
        repo = RaisingAuditRepo(ValueError("Invalid pagination cursor: bad data"))
        client = self._make_client(audit_repo=repo)
        res = client.get(
            "/admin/audit-log",
            headers=self._AUTH_HEADERS,
            params={"cursor": "not-valid-base64-cursor"},
        )
        self.assertEqual(res.status_code, 400)

    def test_invalid_action_prefix_returns_400(self):
        repo = RaisingAuditRepo(ValueError("action_prefix must match ^[a-z0-9_.]+$"))
        client = self._make_client(audit_repo=repo)
        res = client.get(
            "/admin/audit-log",
            headers=self._AUTH_HEADERS,
            params={"action": "UPPERCASE_INVALID"},
        )
        self.assertEqual(res.status_code, 400)


if __name__ == "__main__":
    unittest.main(verbosity=2)

"""
Tests for admin_user_router.py.

This module previously had no test coverage at all — no test in the suite
hit /users or imported admin_user_router. Covers POST /users (add_user) and
POST /users/{user_id}/resend-invitation.
"""

import unittest
import uuid
from contextlib import contextmanager
from unittest.mock import patch

import psycopg2.errors
from fastapi.testclient import TestClient

from tests.helpers.admin_test_helpers import (
    TEST_SESSION_COOKIE,
    StubAuditRepo,
    StubAuthRepo,
    dummy_conn,
    make_test_app,
)


class _FakeCursor:
    """
    Stands in for a psycopg2 RealDictCursor for the one raw-SQL lookup in
    add_user (_get_user_by_email_in_conn). Returns a synthetic id derived
    from the queried email — good enough for generate_reset_token, which
    only needs an opaque id to hand to the (no-op) stub auth_repo.
    """

    def __init__(self):
        self._email = None

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return False

    def execute(self, _query, params):
        self._email = params[0]

    def fetchone(self):
        return {"id": str(uuid.uuid5(uuid.NAMESPACE_DNS, self._email)), "email": self._email}


class _FakeUserLookupConn:
    def cursor(self, cursor_factory=None):
        return _FakeCursor()


@contextmanager
def user_lookup_conn(_database_url):
    """
    Stand-in for get_conn that supports the raw conn.cursor() call
    add_user makes to look up the newly inserted user's id, unlike
    dummy_conn (a bare sentinel string with no cursor() method).
    """
    yield _FakeUserLookupConn()


class DuplicateEmailAuthRepo(StubAuthRepo):
    """insert_user raises UniqueViolation for a pre-registered email."""

    def __init__(self, existing_email):
        super().__init__()
        self._existing_email = existing_email

    def insert_user(self, email, practice_id, role, conn=None):
        if email == self._existing_email:
            raise psycopg2.errors.UniqueViolation()
        super().insert_user(email, practice_id, role, conn=conn)


class FailingAuditRepo(StubAuditRepo):
    """log_event always raises, simulating an audit write failure."""

    def log_event(self, **kwargs):
        raise RuntimeError("Simulated audit log failure")


class TestAddUser(unittest.TestCase):
    def setUp(self):
        self._conn_patcher = patch("app.routers.admin.admin_user_router.get_conn", user_lookup_conn)
        self._conn_patcher.start()

    def tearDown(self):
        self._conn_patcher.stop()

    def _client(self, **make_app_kwargs):
        app = make_test_app(**make_app_kwargs)
        return TestClient(app, raise_server_exceptions=True)

    def test_add_user_200_email_sent_true(self):
        client = self._client()
        res = client.post(
            "/admin/users",
            json={"email": "new.admin@nhs.net"},
            cookies=TEST_SESSION_COOKIE,
        )
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json(), {"ok": True, "email_sent": True})

    def test_add_user_200_email_sent_false_when_delivery_fails(self):
        from tests.helpers.admin_test_helpers import StubAdminDeliveryService

        client = self._client(delivery_service=StubAdminDeliveryService(invitation_raises=True))
        res = client.post(
            "/admin/users",
            json={"email": "new.admin@nhs.net"},
            cookies=TEST_SESSION_COOKIE,
        )
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json(), {"ok": True, "email_sent": False})

    def test_add_user_409_duplicate_email(self):
        auth_repo = DuplicateEmailAuthRepo(existing_email="taken@nhs.net")
        client = self._client(auth_repo=auth_repo)
        res = client.post(
            "/admin/users",
            json={"email": "taken@nhs.net"},
            cookies=TEST_SESSION_COOKIE,
        )
        self.assertEqual(res.status_code, 409)
        self.assertEqual(res.json()["error"]["code"], "USER_ALREADY_EXISTS")

    def test_add_user_403_disallowed_domain(self):
        client = self._client()
        res = client.post(
            "/admin/users",
            json={"email": "someone@othertrust.net"},
            cookies=TEST_SESSION_COOKIE,
        )
        self.assertEqual(res.status_code, 403)
        self.assertEqual(res.json()["error"]["code"], "ACTION_NOT_PERMITTED")

    def test_add_user_422_invalid_email_format(self):
        client = self._client()
        res = client.post(
            "/admin/users",
            json={"email": "not-an-email"},
            cookies=TEST_SESSION_COOKIE,
        )
        self.assertEqual(res.status_code, 422)
        self.assertEqual(res.json()["error"]["code"], "INVALID_PAYLOAD")

    def test_add_user_401_expired_session(self):
        client = self._client()
        res = client.post(
            "/admin/users",
            json={"email": "new.admin@nhs.net"},
            cookies={"session_id": "expired-or-unknown"},
        )
        self.assertEqual(res.status_code, 401)

    def test_add_user_malformed_json_body(self):
        client = self._client()
        res = client.post(
            "/admin/users",
            content=b"{not valid json",
            headers={"content-type": "application/json"},
            cookies=TEST_SESSION_COOKIE,
        )
        self.assertEqual(res.status_code, 422)
        self.assertEqual(res.json()["error"]["code"], "INVALID_PAYLOAD")

    def test_add_user_audit_failure_returns_500(self):
        client = self._client(audit_repo=FailingAuditRepo())
        res = client.post(
            "/admin/users",
            json={"email": "new.admin@nhs.net"},
            cookies=TEST_SESSION_COOKIE,
        )
        self.assertEqual(res.status_code, 500)


class TestResendInvitation(unittest.TestCase):
    def setUp(self):
        self._conn_patcher = patch("app.routers.admin.admin_user_router.get_conn", dummy_conn)
        self._conn_patcher.start()

    def tearDown(self):
        self._conn_patcher.stop()

    def _client(self, **make_app_kwargs):
        app = make_test_app(**make_app_kwargs)
        return TestClient(app, raise_server_exceptions=True)

    def test_resend_invitation_200_email_sent_true(self):
        client = self._client()
        res = client.post(
            "/admin/users/00000000-0000-0000-0000-000000000001/resend-invitation",
            cookies=TEST_SESSION_COOKIE,
        )
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json(), {"ok": True, "email_sent": True})

    def test_resend_invitation_200_email_sent_false_when_delivery_fails(self):
        from tests.helpers.admin_test_helpers import StubAdminDeliveryService

        client = self._client(delivery_service=StubAdminDeliveryService(invitation_raises=True))
        res = client.post(
            "/admin/users/00000000-0000-0000-0000-000000000001/resend-invitation",
            cookies=TEST_SESSION_COOKIE,
        )
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json(), {"ok": True, "email_sent": False})

    def test_resend_invitation_404_unknown_user(self):
        client = self._client()
        res = client.post(
            "/admin/users/00000000-0000-0000-0000-000000000099/resend-invitation",
            cookies=TEST_SESSION_COOKIE,
        )
        self.assertEqual(res.status_code, 404)
        self.assertEqual(res.json()["error"]["code"], "USER_NOT_FOUND")

    def test_resend_invitation_401_expired_session(self):
        client = self._client()
        res = client.post(
            "/admin/users/00000000-0000-0000-0000-000000000001/resend-invitation",
            cookies={"session_id": "expired-or-unknown"},
        )
        self.assertEqual(res.status_code, 401)

    def test_resend_invitation_audit_failure_returns_500(self):
        client = self._client(audit_repo=FailingAuditRepo())
        res = client.post(
            "/admin/users/00000000-0000-0000-0000-000000000001/resend-invitation",
            cookies=TEST_SESSION_COOKIE,
        )
        self.assertEqual(res.status_code, 500)


if __name__ == "__main__":
    unittest.main()

"""
tests/test_admin_auth_router.py

Tests for admin_context.py and admin_auth_router.py.

Covers:
1. General Auth Behaviour (testing session vs DEV_MODE token)
2. MFA Request Code Endpoint
3. MFA Verify Endpoint
4. Logout Endpoint
5. SlowAPI Rate Limiting on MFA Endpoints

Run from project root:
    python -m pytest tests/test_admin_auth_router.py
"""

import os
import unittest
from unittest.mock import patch

from tests.helpers.admin_test_helpers import (
    make_test_app,
    StubAuthRepo,
    StubAdminDeliveryService,
)


# ---------------------------------------------------------------------------
# Section 1: Auth behaviour (admin_context.py)
# ---------------------------------------------------------------------------
# We test this against GET /admin/conditions, which is a protected route.
# Even though the route lives in the practice router, it serves as the perfect
# test bed for the require_admin dependency.

class TestAuthBehaviour(unittest.TestCase):

    def setUp(self):
        from fastapi.testclient import TestClient
        self.app = make_test_app()
        self.client = TestClient(self.app, raise_server_exceptions=True)

    def _get(self, headers=None):
        return self.client.get("/admin/conditions", headers=headers or {})

    def test_missing_authorization_header_returns_401(self):
        res = self._get()
        self.assertEqual(res.status_code, 401)

    def test_empty_bearer_value_returns_401(self):
        # HTTPBearer with auto_error=False returns None for malformed header;
        # our code then raises 401
        res = self._get(headers={"Authorization": "Bearer "})
        self.assertEqual(res.status_code, 401)

    def test_wrong_token_when_admin_token_set_returns_401(self):
        os.environ["ADMIN_TOKEN"] = "correct-token"
        os.environ["DEV_MODE"] = "1"
        try:
            res = self._get(headers={"Authorization": "Bearer wrong-token"})
            self.assertEqual(res.status_code, 401)
        finally:
            del os.environ["ADMIN_TOKEN"]
            del os.environ["DEV_MODE"]

    def test_correct_token_when_admin_token_set_returns_200(self):
        os.environ["ADMIN_TOKEN"] = "correct-token"
        os.environ["DEV_MODE"] = "1"
        try:
            res = self._get(headers={"Authorization": "Bearer correct-token"})
            self.assertEqual(res.status_code, 200)
        finally:
            del os.environ["ADMIN_TOKEN"]
            del os.environ["DEV_MODE"]

    def test_any_nonempty_token_accepted_in_dev_mode_without_admin_token(self):
        os.environ["DEV_MODE"] = "1"
        os.environ.pop("ADMIN_TOKEN", None)
        try:
            res = self._get(headers={"Authorization": "Bearer anything"})
            self.assertEqual(res.status_code, 200)
        finally:
            del os.environ["DEV_MODE"]


# ---------------------------------------------------------------------------
# Stub specific for Auth tests
# ---------------------------------------------------------------------------

class SpyAuthRepo(StubAuthRepo):
    """
    Extends StubAuthRepo with configurable return values and call recording.
    Allows individual tests to control what the repo returns without
    building a full database-backed repo.
    """

    def __init__(
        self,
        user=None,
        auth_code_record=None,
        session_context=None,
    ):
        self._user = user
        self._auth_code_record = auth_code_record
        self._session_context = session_context
        self.upserted = []
        self.deleted_codes = []
        self.deleted_sessions = []
        self.incremented = []
        self.created_sessions = []

    def get_user_by_email(self, email):
        return self._user

    def get_auth_code_record(self, email):
        return self._auth_code_record

    def get_session_context(self, session_id):
        return self._session_context

    def upsert_auth_code(self, email, hashed_code, expires_at, last_requested_at):
        self.upserted.append(email)

    def delete_auth_code(self, email):
        self.deleted_codes.append(email)

    def increment_code_attempts(self, email):
        self.incremented.append(email)

    def create_session(self, user_id, expires_at):
        self.created_sessions.append(user_id)
        return "test-session-id"

    def delete_session(self, session_id):
        self.deleted_sessions.append(session_id)


# ---------------------------------------------------------------------------
# Section 2: MFA Request Code Endpoint
# ---------------------------------------------------------------------------

class TestRequestMfaCode(unittest.TestCase):

    def _make_client(self, auth_repo=None, delivery_service=None):
        from fastapi.testclient import TestClient
        os.environ["DEV_MODE"] = "1"
        app = make_test_app(auth_repo=auth_repo, delivery_service=delivery_service)
        return TestClient(app, raise_server_exceptions=False)

    def tearDown(self):
        os.environ.pop("DEV_MODE", None)

    def test_unknown_domain_returns_422(self):
        client = self._make_client()
        res = client.post(
            "/admin/auth/request-code",
            json={"email": "user@notallowed.com"},
        )
        self.assertEqual(res.status_code, 422)

    def test_unregistered_email_with_valid_domain_returns_200(self):
        # Silent return — must not reveal the email is unregistered.
        repo = SpyAuthRepo(user=None)
        client = self._make_client(auth_repo=repo)
        res = client.post(
            "/admin/auth/request-code",
            json={"email": "unknown@nhs.net"},
        )
        self.assertEqual(res.status_code, 200)
        # No code upserted and no email sent.
        self.assertEqual(len(repo.upserted), 0)

    def test_registered_email_sends_code_and_returns_200(self):
        user = {"id": "user-uuid", "email": "admin@nhs.net",
                "practice_id": "test_practice", "role": "admin"}
        repo = SpyAuthRepo(user=user)
        delivery = StubAdminDeliveryService()
        client = self._make_client(auth_repo=repo, delivery_service=delivery)
        res = client.post(
            "/admin/auth/request-code",
            json={"email": "admin@nhs.net"},
        )
        self.assertEqual(res.status_code, 200)
        self.assertEqual(len(repo.upserted), 1)
        self.assertEqual(len(delivery.calls), 1)
        self.assertEqual(delivery.calls[0]["email"], "admin@nhs.net")

    def test_missing_email_field_returns_422(self):
        client = self._make_client()
        res = client.post("/admin/auth/request-code", json={})
        self.assertEqual(res.status_code, 422)

    def test_email_normalised_to_lowercase(self):
        user = {"id": "user-uuid", "email": "admin@nhs.net",
                "practice_id": "test_practice", "role": "admin"}
        repo = SpyAuthRepo(user=user)
        delivery = StubAdminDeliveryService()
        client = self._make_client(auth_repo=repo, delivery_service=delivery)
        res = client.post(
            "/admin/auth/request-code",
            json={"email": "ADMIN@NHS.NET"},
        )
        self.assertEqual(res.status_code, 200)
        self.assertEqual(delivery.calls[0]["email"], "admin@nhs.net")


# ---------------------------------------------------------------------------
# Section 3: MFA Verify Endpoint
# ---------------------------------------------------------------------------

class TestVerifyMfaCode(unittest.TestCase):

    def _make_client(self, auth_repo=None):
        from fastapi.testclient import TestClient
        os.environ["DEV_MODE"] = "1"
        app = make_test_app(auth_repo=auth_repo)
        return TestClient(app, raise_server_exceptions=False)

    def tearDown(self):
        os.environ.pop("DEV_MODE", None)

    def _valid_code_repo(self):
        """
        Return a SpyAuthRepo configured with a user and a valid (unexpired,
        unhashed) code record. Uses a known plaintext code "123456" with
        a real bcrypt hash so verify_code passes.
        """
        import bcrypt
        from datetime import datetime, timezone, timedelta

        code = "123456"
        hashed = bcrypt.hashpw(code.encode(), bcrypt.gensalt()).decode()
        user = {"id": "user-uuid", "email": "admin@nhs.net",
                "practice_id": "test_practice", "role": "admin"}
        record = {
            "email": "admin@nhs.net",
            "hashed_code": hashed,
            "expires_at": datetime.now(tz=timezone.utc) + timedelta(minutes=5),
            "attempts_count": 0,
            "last_requested_at": datetime.now(tz=timezone.utc),
        }
        return SpyAuthRepo(user=user, auth_code_record=record), code

    def test_correct_code_returns_200_and_sets_cookie(self):
        repo, code = self._valid_code_repo()
        client = self._make_client(auth_repo=repo)
        res = client.post(
            "/admin/auth/verify",
            json={"email": "admin@nhs.net", "code": code},
        )
        self.assertEqual(res.status_code, 200)
        self.assertIn("session_id", res.cookies)

    def test_wrong_code_returns_422(self):
        repo, _ = self._valid_code_repo()
        client = self._make_client(auth_repo=repo)
        res = client.post(
            "/admin/auth/verify",
            json={"email": "admin@nhs.net", "code": "000000"},
        )
        self.assertEqual(res.status_code, 422)
        self.assertEqual(res.json()["error"]["code"], "INVALID_AUTH_CODE")

    def test_non_digit_code_returns_422(self):
        client = self._make_client()
        res = client.post(
            "/admin/auth/verify",
            json={"email": "admin@nhs.net", "code": "abcdef"},
        )
        self.assertEqual(res.status_code, 422)

    def test_short_code_returns_422(self):
        client = self._make_client()
        res = client.post(
            "/admin/auth/verify",
            json={"email": "admin@nhs.net", "code": "123"},
        )
        self.assertEqual(res.status_code, 422)

    def test_no_user_returns_422(self):
        repo = SpyAuthRepo(user=None)
        client = self._make_client(auth_repo=repo)
        res = client.post(
            "/admin/auth/verify",
            json={"email": "nobody@nhs.net", "code": "123456"},
        )
        self.assertEqual(res.status_code, 422)
        self.assertEqual(res.json()["error"]["code"], "INVALID_AUTH_CODE")

    def test_no_code_record_returns_422(self):
        user = {"id": "user-uuid", "email": "admin@nhs.net",
                "practice_id": "test_practice", "role": "admin"}
        repo = SpyAuthRepo(user=user, auth_code_record=None)
        client = self._make_client(auth_repo=repo)
        res = client.post(
            "/admin/auth/verify",
            json={"email": "admin@nhs.net", "code": "123456"},
        )
        self.assertEqual(res.status_code, 422)

    def test_expired_code_returns_422(self):
        import bcrypt
        from datetime import datetime, timezone, timedelta

        code = "123456"
        hashed = bcrypt.hashpw(code.encode(), bcrypt.gensalt()).decode()
        user = {"id": "user-uuid", "email": "admin@nhs.net",
                "practice_id": "test_practice", "role": "admin"}
        # expires_at in the past
        record = {
            "email": "admin@nhs.net",
            "hashed_code": hashed,
            "expires_at": datetime.now(tz=timezone.utc) - timedelta(minutes=1),
            "attempts_count": 0,
            "last_requested_at": datetime.now(tz=timezone.utc),
        }
        repo = SpyAuthRepo(user=user, auth_code_record=record)
        client = self._make_client(auth_repo=repo)
        res = client.post(
            "/admin/auth/verify",
            json={"email": "admin@nhs.net", "code": code},
        )
        self.assertEqual(res.status_code, 422)

    def test_locked_out_after_max_attempts_returns_422(self):
        import bcrypt
        from datetime import datetime, timezone, timedelta

        code = "123456"
        hashed = bcrypt.hashpw(code.encode(), bcrypt.gensalt()).decode()
        user = {"id": "user-uuid", "email": "admin@nhs.net",
                "practice_id": "test_practice", "role": "admin"}
        # attempts_count at maximum
        record = {
            "email": "admin@nhs.net",
            "hashed_code": hashed,
            "expires_at": datetime.now(tz=timezone.utc) + timedelta(minutes=5),
            "attempts_count": 3,
            "last_requested_at": datetime.now(tz=timezone.utc),
        }
        repo = SpyAuthRepo(user=user, auth_code_record=record)
        client = self._make_client(auth_repo=repo)
        res = client.post(
            "/admin/auth/verify",
            json={"email": "admin@nhs.net", "code": code},
        )
        self.assertEqual(res.status_code, 422)
        # Code should have been deleted on lockout.
        self.assertIn("admin@nhs.net", repo.deleted_codes)


# ---------------------------------------------------------------------------
# Section 4: Logout Endpoint
# ---------------------------------------------------------------------------

class TestLogout(unittest.TestCase):

    def _make_client(self, auth_repo=None):
        from fastapi.testclient import TestClient
        os.environ["DEV_MODE"] = "1"
        app = make_test_app(auth_repo=auth_repo)
        return TestClient(app, raise_server_exceptions=False)

    def tearDown(self):
        os.environ.pop("DEV_MODE", None)

    def test_logout_without_cookie_returns_200(self):
        repo = SpyAuthRepo()
        client = self._make_client(auth_repo=repo)
        res = client.post("/admin/auth/logout")
        self.assertEqual(res.status_code, 200)
        # No session_id cookie present, so delete_session must not be called.
        self.assertEqual(len(repo.deleted_sessions), 0)

    def test_logout_with_cookie_deletes_session_and_returns_200(self):
        repo = SpyAuthRepo()
        client = self._make_client(auth_repo=repo)
        client.cookies.set("session_id", "some-session-id")
        res = client.post("/admin/auth/logout")
        self.assertEqual(res.status_code, 200)
        self.assertIn("some-session-id", repo.deleted_sessions)

    def test_logout_clears_cookie(self):
        repo = SpyAuthRepo()
        client = self._make_client(auth_repo=repo)
        client.cookies.set("session_id", "some-session-id")
        res = client.post("/admin/auth/logout")
        # Cookie should be cleared (Max-Age=0 sets an expired cookie).
        # TestClient reflects the Set-Cookie header in res.headers.
        set_cookie = res.headers.get("set-cookie", "")
        self.assertIn("session_id", set_cookie)
        self.assertIn("Max-Age=0", set_cookie)

    def test_logout_cookie_not_secure_in_dev_mode(self):
        # In DEV_MODE the clearing cookie must not have Secure set, so it
        # works over plain HTTP in local development. _make_client sets DEV_MODE=1.
        repo = SpyAuthRepo()
        client = self._make_client(auth_repo=repo)
        client.cookies.set("session_id", "some-session-id")
        res = client.post("/admin/auth/logout")
        set_cookie = res.headers.get("set-cookie", "").lower()
        self.assertNotIn("secure", set_cookie)

    def test_logout_cookie_secure_outside_dev_mode(self):
        # Outside DEV_MODE the clearing cookie must carry the Secure attribute.
        from fastapi.testclient import TestClient
        os.environ.pop("DEV_MODE", None)
        app = make_test_app(auth_repo=SpyAuthRepo())
        client = TestClient(app, raise_server_exceptions=False)
        client.cookies.set("session_id", "some-session-id")
        res = client.post("/admin/auth/logout")
        set_cookie = res.headers.get("set-cookie", "").lower()
        self.assertIn("secure", set_cookie)


# ---------------------------------------------------------------------------
# Section 5: SlowAPI rate limiting
# ---------------------------------------------------------------------------

class TestMFARateLimiting(unittest.TestCase):
    """
    Integration tests for the @limiter.limit("5/minute") decorators on the
    two unauthenticated MFA endpoints.

    These tests use with_rate_limiting=True on make_test_app, which wires
    SlowAPIMiddleware and the RateLimitExceeded handler to mirror production.

    The limiter storage is automatically reset by the `reset_rate_limiter`
    fixture in conftest.py if run via pytest.
    """

    def setUp(self):
        from app.core.rate_limit import limiter
        limiter._storage.reset()
        os.environ["DEV_MODE"] = "1"

    def tearDown(self):
        from app.core.rate_limit import limiter
        limiter._storage.reset()
        os.environ.pop("DEV_MODE", None)

    def _make_client(self):
        from fastapi.testclient import TestClient
        app = make_test_app(with_rate_limiting=True)
        # raise_server_exceptions=False so that slowapi's 429 is returned as
        # a response rather than re-raised as an exception in the test process.
        return TestClient(app, raise_server_exceptions=False)

    def test_request_code_blocked_after_five_requests(self):
        client = self._make_client()
        payload = {"email": "admin@nhs.net"}

        with patch("app.services.admin.auth_service.request_mfa_code"):
            for i in range(5):
                res = client.post("/admin/auth/request-code", json=payload)
                self.assertNotEqual(
                    res.status_code, 429,
                    msg=f"Request {i + 1} was unexpectedly rate-limited before the 6th call",
                )

            res = client.post("/admin/auth/request-code", json=payload)

        self.assertEqual(res.status_code, 429)
        body = res.json()
        self.assertEqual(body["error"]["code"], "RATE_LIMIT_EXCEEDED")
        self.assertEqual(
            body["error"]["message"],
            "Too many requests. Please try again later.",
        )

    def test_verify_blocked_after_five_requests(self):
        client = self._make_client()
        payload = {"email": "admin@nhs.net", "code": "123456"}

        with patch(
            "app.services.admin.auth_service.verify_mfa_code",
            return_value="stub-session-id",
        ):
            for i in range(5):
                res = client.post("/admin/auth/verify", json=payload)
                self.assertNotEqual(
                    res.status_code, 429,
                    msg=f"Request {i + 1} was unexpectedly rate-limited before the 6th call",
                )

            res = client.post("/admin/auth/verify", json=payload)

        self.assertEqual(res.status_code, 429)
        body = res.json()
        self.assertEqual(body["error"]["code"], "RATE_LIMIT_EXCEEDED")
        self.assertEqual(
            body["error"]["message"],
            "Too many requests. Please try again later.",
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)

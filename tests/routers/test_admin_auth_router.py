"""
tests/test_admin_auth_router.py

Tests for admin_context.py and admin_auth_router.py.

Covers:
1. General Auth Behaviour (session cookie path)
2. POST /auth/login (step 1: password check)
3. POST /auth/verify (step 2: OTP check, unchanged)
4. POST /auth/request-reset
5. POST /auth/set-password
6. POST /auth/logout
7. SlowAPI Rate Limiting on auth endpoints

Run from project root:
    python -m pytest tests/test_admin_auth_router.py
"""

import unittest
from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import bcrypt

from tests.helpers.admin_test_helpers import (
    TEST_SESSION_COOKIE,
    TEST_SESSION_ID,
    StubAdminDeliveryService,
    StubAuditRepo,
    StubAuthRepo,
    make_test_app,
)


class RaisingAuditRepo(StubAuditRepo):
    """Audit repo stub whose log_event always raises, for D8 500 tests."""

    def log_event(self, *args, **kwargs):
        raise RuntimeError("Simulated audit log failure")


# ---------------------------------------------------------------------------
# Shared SpyAuthRepo for auth router tests
# ---------------------------------------------------------------------------


class SpyAuthRepo(StubAuthRepo):
    """
    Extends StubAuthRepo with configurable return values and call recording.
    """

    def __init__(
        self,
        user=None,
        auth_code_record=None,
        session_context=None,
        reset_token_record=None,
    ):
        self._user = user
        self._auth_code_record = auth_code_record
        self._session_context = session_context
        self._reset_token_record = reset_token_record
        self.upserted_codes = []
        self.deleted_codes = []
        self.deleted_sessions = []
        self.incremented = []
        self.created_sessions = []
        self.failed_attempts_recorded = []
        self.attempts_reset = []
        self.upserted_tokens = []
        self.deleted_tokens = []
        self.passwords_set = []

    def get_user_by_email(self, email):
        return self._user

    def get_auth_code_record(self, email):
        return self._auth_code_record

    def get_session_context(self, session_id):
        if self._session_context is not None:
            return self._session_context
        # Fall back to the default test session.
        if session_id == TEST_SESSION_ID:
            return {
                "user_id": "00000000-0000-0000-0000-000000000001",
                "role": "admin",
                "practice_id": "test_practice",
                "email": "admin@nhs.net",
                "session_id": TEST_SESSION_ID,
            }
        return None

    def upsert_auth_code(self, email, hashed_code, expires_at, last_requested_at):
        self.upserted_codes.append(email)

    def delete_auth_code(self, email):
        self.deleted_codes.append(email)

    def increment_code_attempts(self, email):
        self.incremented.append(email)

    def create_session(self, user_id, expires_at):
        self.created_sessions.append(user_id)
        return "test-session-id"

    def delete_session(self, session_id):
        self.deleted_sessions.append(session_id)

    def record_failed_password_attempt(self, user_id, lock_until=None, conn=None):
        self.failed_attempts_recorded.append({"user_id": user_id, "lock_until": lock_until})

    def reset_password_attempts(self, user_id, conn=None):
        self.attempts_reset.append(user_id)

    def upsert_reset_token(self, user_id, token_hash, expires_at, conn=None):
        self.upserted_tokens.append({"user_id": user_id, "token_hash": token_hash})

    def get_reset_token_record(self, token_hash):
        return self._reset_token_record

    def delete_reset_token(self, token_hash, conn=None):
        self.deleted_tokens.append(token_hash)

    def set_password(self, user_id, hashed_password, conn=None):
        self.passwords_set.append({"user_id": user_id, "hashed_password": hashed_password})


def _make_user(hashed_password=None, failed_attempts=0, locked_until=None):
    """Helper: return a minimal user dict with password auth fields."""
    return {
        "id": "user-uuid",
        "email": "admin@nhs.net",
        "practice_id": "test_practice",
        "role": "admin",
        "created_at": datetime(2024, 1, 1, tzinfo=UTC),
        "hashed_password": hashed_password,
        "failed_password_attempts": failed_attempts,
        "password_locked_until": locked_until,
        "password_changed_at": None,
    }


# ---------------------------------------------------------------------------
# Section 1: Auth behaviour (admin_context.py)
# ---------------------------------------------------------------------------


class TestAuthBehaviour(unittest.TestCase):
    def setUp(self):
        from fastapi.testclient import TestClient

        self.app = make_test_app()
        self.client = TestClient(self.app, raise_server_exceptions=True)

    def _get(self, cookies=None):
        return self.client.get("/admin/conditions", cookies=cookies or {})

    def test_no_session_cookie_returns_401(self):
        res = self._get()
        self.assertEqual(res.status_code, 401)

    def test_malformed_session_cookie_returns_401(self):
        """Non-UUID cookie value must 401 without ever reaching the
        repository — get_session_context casts with %s::uuid, so a
        malformed value would otherwise raise a 500."""
        res = self._get(cookies={"session_id": "not-a-real-session"})
        self.assertEqual(res.status_code, 401)

    def test_wellformed_but_unknown_session_cookie_returns_401(self):
        """A syntactically valid UUID that has no matching session row."""
        res = self._get(cookies={"session_id": "99999999-9999-9999-9999-999999999999"})
        self.assertEqual(res.status_code, 401)

    def test_valid_session_cookie_returns_200(self):
        res = self._get(cookies=TEST_SESSION_COOKIE)
        self.assertEqual(res.status_code, 200)


# ---------------------------------------------------------------------------
# Section 2: POST /auth/login (step 1)
# ---------------------------------------------------------------------------


class TestLogin(unittest.TestCase):
    def _make_client(self, auth_repo=None, delivery_service=None, audit_repo=None):
        from fastapi.testclient import TestClient

        app = make_test_app(
            auth_repo=auth_repo, delivery_service=delivery_service, audit_repo=audit_repo
        )
        return TestClient(app, raise_server_exceptions=False)

    def tearDown(self):
        pass

    def _valid_user_repo(self):
        """Return a SpyAuthRepo with a user who has a known bcrypt password."""
        password = "CorrectHorseBatteryStaple1!"
        hashed = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
        user = _make_user(hashed_password=hashed)
        return SpyAuthRepo(user=user), password

    def test_correct_credentials_return_200(self):
        repo, password = self._valid_user_repo()
        client = self._make_client(auth_repo=repo)
        res = client.post(
            "/admin/auth/login",
            json={"email": "admin@nhs.net", "password": password},
        )
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json(), {"ok": True})

    def test_correct_credentials_upsert_otp(self):
        repo, password = self._valid_user_repo()
        client = self._make_client(auth_repo=repo)
        client.post(
            "/admin/auth/login",
            json={"email": "admin@nhs.net", "password": password},
        )
        # OTP must be upserted synchronously before 200 is returned.
        self.assertIn("admin@nhs.net", repo.upserted_codes)

    def test_wrong_password_returns_422(self):
        repo, _ = self._valid_user_repo()
        client = self._make_client(auth_repo=repo)
        res = client.post(
            "/admin/auth/login",
            json={"email": "admin@nhs.net", "password": "WrongPassword123!"},
        )
        self.assertEqual(res.status_code, 422)
        self.assertEqual(res.json()["error"]["code"], "INVALID_CREDENTIALS")

    def test_wrong_password_records_failed_attempt(self):
        repo, _ = self._valid_user_repo()
        client = self._make_client(auth_repo=repo)
        client.post(
            "/admin/auth/login",
            json={"email": "admin@nhs.net", "password": "WrongPassword123!"},
        )
        self.assertEqual(len(repo.failed_attempts_recorded), 1)

    def test_wrong_password_at_threshold_sets_lockout(self):
        """Third failed attempt must set lock_until."""
        password = "CorrectHorseBatteryStaple1!"
        hashed = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
        # failed_password_attempts=2, so next failure is the 3rd.
        user = _make_user(hashed_password=hashed, failed_attempts=2)
        repo = SpyAuthRepo(user=user)
        client = self._make_client(auth_repo=repo)
        client.post(
            "/admin/auth/login",
            json={"email": "admin@nhs.net", "password": "WrongPassword123!"},
        )
        self.assertEqual(len(repo.failed_attempts_recorded), 1)
        self.assertIsNotNone(repo.failed_attempts_recorded[0]["lock_until"])

    def test_user_not_found_returns_422_with_generic_error(self):
        repo = SpyAuthRepo(user=None)
        client = self._make_client(auth_repo=repo)
        res = client.post(
            "/admin/auth/login",
            json={"email": "nobody@nhs.net", "password": "SomePassword1!"},
        )
        self.assertEqual(res.status_code, 422)
        self.assertEqual(res.json()["error"]["code"], "INVALID_CREDENTIALS")

    def test_locked_account_returns_422_with_generic_error(self):
        password = "CorrectHorseBatteryStaple1!"
        hashed = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
        locked_until = datetime.now(tz=UTC) + timedelta(minutes=15)
        user = _make_user(hashed_password=hashed, locked_until=locked_until)
        repo = SpyAuthRepo(user=user)
        client = self._make_client(auth_repo=repo)
        res = client.post(
            "/admin/auth/login",
            json={"email": "admin@nhs.net", "password": password},
        )
        self.assertEqual(res.status_code, 422)
        self.assertEqual(res.json()["error"]["code"], "INVALID_CREDENTIALS")

    def test_no_password_set_returns_422_with_generic_error(self):
        """User exists but hashed_password is None (invitation not yet accepted)."""
        user = _make_user(hashed_password=None)
        repo = SpyAuthRepo(user=user)
        client = self._make_client(auth_repo=repo)
        res = client.post(
            "/admin/auth/login",
            json={"email": "admin@nhs.net", "password": "SomePassword1!"},
        )
        self.assertEqual(res.status_code, 422)
        self.assertEqual(res.json()["error"]["code"], "INVALID_CREDENTIALS")

    def test_missing_password_field_returns_422(self):
        client = self._make_client()
        res = client.post("/admin/auth/login", json={"email": "admin@nhs.net"})
        self.assertEqual(res.status_code, 422)

    def test_missing_email_field_returns_422(self):
        client = self._make_client()
        res = client.post("/admin/auth/login", json={"password": "SomePassword1!"})
        self.assertEqual(res.status_code, 422)

    def test_email_normalised_to_lowercase(self):
        password = "CorrectHorseBatteryStaple1!"
        hashed = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
        user = _make_user(hashed_password=hashed)
        repo = SpyAuthRepo(user=user)
        client = self._make_client(auth_repo=repo)
        res = client.post(
            "/admin/auth/login",
            json={"email": "ADMIN@NHS.NET", "password": password},
        )
        self.assertEqual(res.status_code, 200)

    def test_audit_log_failure_returns_500(self):
        """D8: if audit_repo.log_event raises, the endpoint returns 500 with
        the standard 'audit logging failed' message, not a silent 200."""
        repo, password = self._valid_user_repo()
        client = self._make_client(auth_repo=repo, audit_repo=RaisingAuditRepo())
        res = client.post(
            "/admin/auth/login",
            json={"email": "admin@nhs.net", "password": password},
        )
        self.assertEqual(res.status_code, 500)
        self.assertEqual(
            res.json()["detail"],
            "Action succeeded but audit logging failed. Please report this.",
        )


# ---------------------------------------------------------------------------
# Section 3: POST /auth/verify (step 2, unchanged)
# ---------------------------------------------------------------------------


class TestVerifyMfaCode(unittest.TestCase):
    def _make_client(self, auth_repo=None):
        from fastapi.testclient import TestClient

        app = make_test_app(auth_repo=auth_repo)
        return TestClient(app, raise_server_exceptions=False)

    def tearDown(self):
        pass

    def _valid_code_repo(self):
        code = "123456"
        hashed = bcrypt.hashpw(code.encode(), bcrypt.gensalt()).decode()
        user = _make_user()
        record = {
            "email": "admin@nhs.net",
            "hashed_code": hashed,
            "expires_at": datetime.now(tz=UTC) + timedelta(minutes=5),
            "attempts_count": 0,
            "last_requested_at": datetime.now(tz=UTC),
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

    def test_expired_code_returns_422(self):
        code = "123456"
        hashed = bcrypt.hashpw(code.encode(), bcrypt.gensalt()).decode()
        user = _make_user()
        record = {
            "email": "admin@nhs.net",
            "hashed_code": hashed,
            "expires_at": datetime.now(tz=UTC) - timedelta(minutes=1),
            "attempts_count": 0,
            "last_requested_at": datetime.now(tz=UTC),
        }
        repo = SpyAuthRepo(user=user, auth_code_record=record)
        client = self._make_client(auth_repo=repo)
        res = client.post(
            "/admin/auth/verify",
            json={"email": "admin@nhs.net", "code": code},
        )
        self.assertEqual(res.status_code, 422)

    def test_locked_out_after_max_attempts_returns_422(self):
        code = "123456"
        hashed = bcrypt.hashpw(code.encode(), bcrypt.gensalt()).decode()
        user = _make_user()
        record = {
            "email": "admin@nhs.net",
            "hashed_code": hashed,
            "expires_at": datetime.now(tz=UTC) + timedelta(minutes=5),
            "attempts_count": 3,
            "last_requested_at": datetime.now(tz=UTC),
        }
        repo = SpyAuthRepo(user=user, auth_code_record=record)
        client = self._make_client(auth_repo=repo)
        res = client.post(
            "/admin/auth/verify",
            json={"email": "admin@nhs.net", "code": code},
        )
        self.assertEqual(res.status_code, 422)
        self.assertIn("admin@nhs.net", repo.deleted_codes)


# ---------------------------------------------------------------------------
# Section 4: POST /auth/request-reset
# ---------------------------------------------------------------------------


class TestRequestReset(unittest.TestCase):
    def _make_client(self, auth_repo=None, delivery_service=None):
        from fastapi.testclient import TestClient

        app = make_test_app(auth_repo=auth_repo, delivery_service=delivery_service)
        return TestClient(app, raise_server_exceptions=False)

    def tearDown(self):
        pass

    def test_registered_email_returns_200(self):
        user = _make_user()
        repo = SpyAuthRepo(user=user)
        delivery = StubAdminDeliveryService()
        client = self._make_client(auth_repo=repo, delivery_service=delivery)
        res = client.post(
            "/admin/auth/request-reset",
            json={"email": "admin@nhs.net"},
        )
        self.assertEqual(res.status_code, 200)

    def test_registered_email_upserts_token_and_sends_email(self):
        user = _make_user()
        repo = SpyAuthRepo(user=user)
        delivery = StubAdminDeliveryService()
        client = self._make_client(auth_repo=repo, delivery_service=delivery)
        client.post(
            "/admin/auth/request-reset",
            json={"email": "admin@nhs.net"},
        )
        self.assertEqual(len(repo.upserted_tokens), 1)
        self.assertEqual(len(delivery.invitation_calls), 1)

    def test_unregistered_email_returns_200_silently(self):
        """Must not reveal whether the email is registered."""
        repo = SpyAuthRepo(user=None)
        delivery = StubAdminDeliveryService()
        client = self._make_client(auth_repo=repo, delivery_service=delivery)
        res = client.post(
            "/admin/auth/request-reset",
            json={"email": "nobody@nhs.net"},
        )
        self.assertEqual(res.status_code, 200)
        # No token upserted and no email sent.
        self.assertEqual(len(repo.upserted_tokens), 0)
        self.assertEqual(len(delivery.invitation_calls), 0)

    def test_missing_email_returns_422(self):
        client = self._make_client()
        res = client.post("/admin/auth/request-reset", json={})
        self.assertEqual(res.status_code, 422)


# ---------------------------------------------------------------------------
# Section 5: POST /auth/set-password
# ---------------------------------------------------------------------------


class TestSetPassword(unittest.TestCase):
    def _make_client(self, auth_repo=None):
        from fastapi.testclient import TestClient

        app = make_test_app(auth_repo=auth_repo)
        return TestClient(app, raise_server_exceptions=False)

    def tearDown(self):
        pass

    def _valid_token_repo(self):
        """Return a SpyAuthRepo with a valid unexpired reset token."""
        import hashlib
        import secrets as sec

        raw_token = sec.token_urlsafe(32)
        token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
        record = {
            "token_hash": token_hash,
            "user_id": "user-uuid",
            "expires_at": datetime.now(tz=UTC) + timedelta(hours=1),
        }
        repo = SpyAuthRepo(reset_token_record=record)
        return repo, raw_token

    def test_valid_token_and_strong_password_returns_200(self):
        repo, raw_token = self._valid_token_repo()
        client = self._make_client(auth_repo=repo)
        res = client.post(
            "/admin/auth/set-password",
            json={"token": raw_token, "password": "CorrectHorseBatteryStaple1!"},
        )
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json(), {"ok": True})

    def test_valid_token_calls_set_password_on_repo(self):
        repo, raw_token = self._valid_token_repo()
        client = self._make_client(auth_repo=repo)
        client.post(
            "/admin/auth/set-password",
            json={"token": raw_token, "password": "CorrectHorseBatteryStaple1!"},
        )
        self.assertEqual(len(repo.passwords_set), 1)
        self.assertEqual(repo.passwords_set[0]["user_id"], "user-uuid")

    def test_expired_token_returns_422(self):
        import hashlib
        import secrets as sec

        raw_token = sec.token_urlsafe(32)
        token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
        record = {
            "token_hash": token_hash,
            "user_id": "user-uuid",
            "expires_at": datetime.now(tz=UTC) - timedelta(hours=1),
        }
        repo = SpyAuthRepo(reset_token_record=record)
        client = self._make_client(auth_repo=repo)
        res = client.post(
            "/admin/auth/set-password",
            json={"token": raw_token, "password": "CorrectHorseBatteryStaple1!"},
        )
        self.assertEqual(res.status_code, 422)
        self.assertEqual(res.json()["error"]["code"], "INVALID_RESET_TOKEN")

    def test_unknown_token_returns_422(self):
        repo = SpyAuthRepo(reset_token_record=None)
        client = self._make_client(auth_repo=repo)
        res = client.post(
            "/admin/auth/set-password",
            json={"token": "not-a-real-token", "password": "CorrectHorseBatteryStaple1!"},
        )
        self.assertEqual(res.status_code, 422)
        self.assertEqual(res.json()["error"]["code"], "INVALID_RESET_TOKEN")

    def test_weak_password_returns_422(self):
        repo, raw_token = self._valid_token_repo()
        client = self._make_client(auth_repo=repo)
        res = client.post(
            "/admin/auth/set-password",
            # "password" is in every dictionary wordlist — zxcvbn will score it 0.
            json={"token": raw_token, "password": "password123456"},
        )
        self.assertEqual(res.status_code, 422)
        self.assertEqual(res.json()["error"]["code"], "WEAK_PASSWORD")

    def test_short_password_returns_422(self):
        repo, raw_token = self._valid_token_repo()
        client = self._make_client(auth_repo=repo)
        res = client.post(
            "/admin/auth/set-password",
            json={"token": raw_token, "password": "short"},
        )
        self.assertEqual(res.status_code, 422)

    def test_whitespace_is_not_stripped_before_hashing(self):
        """
        Regression test for the whitespace-strip asymmetry bug.

        verify_login_credentials does not strip the typed password at
        login, so set_new_password must not strip it either. If it did,
        a password containing leading/trailing whitespace would be stored
        as the stripped version but checked against the raw typed version
        at login, permanently locking the user out.
        """
        repo, raw_token = self._valid_token_repo()
        client = self._make_client(auth_repo=repo)
        submitted_password = "  CorrectHorseBatteryStaple1!  "

        res = client.post(
            "/admin/auth/set-password",
            json={"token": raw_token, "password": submitted_password},
        )

        self.assertEqual(res.status_code, 200)
        self.assertEqual(len(repo.passwords_set), 1)
        stored_hash = repo.passwords_set[0]["hashed_password"]

        # The stored hash must verify against the password exactly as typed.
        self.assertTrue(bcrypt.checkpw(submitted_password.encode(), stored_hash.encode()))
        # It must NOT verify against a stripped version — proving the
        # service no longer normalises the password before hashing.
        self.assertFalse(bcrypt.checkpw(submitted_password.strip().encode(), stored_hash.encode()))

    def test_missing_token_returns_422(self):
        client = self._make_client()
        res = client.post(
            "/admin/auth/set-password",
            json={"password": "CorrectHorseBatteryStaple1!"},
        )
        self.assertEqual(res.status_code, 422)

    def test_token_consumed_on_success(self):
        """Token must be deleted after successful use."""
        repo, raw_token = self._valid_token_repo()
        client = self._make_client(auth_repo=repo)
        client.post(
            "/admin/auth/set-password",
            json={"token": raw_token, "password": "CorrectHorseBatteryStaple1!"},
        )
        self.assertEqual(len(repo.deleted_tokens), 1)

    def test_token_consumed_even_on_expiry(self):
        """Expired token must also be deleted (consumed on lookup)."""
        import hashlib
        import secrets as sec

        raw_token = sec.token_urlsafe(32)
        token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
        record = {
            "token_hash": token_hash,
            "user_id": "user-uuid",
            "expires_at": datetime.now(tz=UTC) - timedelta(hours=1),
        }
        repo = SpyAuthRepo(reset_token_record=record)
        client = self._make_client(auth_repo=repo)
        client.post(
            "/admin/auth/set-password",
            json={"token": raw_token, "password": "CorrectHorseBatteryStaple1!"},
        )
        self.assertEqual(len(repo.deleted_tokens), 1)


# ---------------------------------------------------------------------------
# Section 6: POST /auth/logout
# ---------------------------------------------------------------------------


class TestLogout(unittest.TestCase):
    def _make_client(self, auth_repo=None, audit_repo=None):
        from fastapi.testclient import TestClient

        app = make_test_app(auth_repo=auth_repo, audit_repo=audit_repo)
        return TestClient(app, raise_server_exceptions=False)

    def tearDown(self):
        pass

    def test_logout_without_cookie_returns_200(self):
        repo = SpyAuthRepo()
        client = self._make_client(auth_repo=repo)
        res = client.post("/admin/auth/logout")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(len(repo.deleted_sessions), 0)

    def test_logout_with_cookie_deletes_session_and_returns_200(self):
        repo = SpyAuthRepo()
        client = self._make_client(auth_repo=repo)
        client.cookies.set("session_id", "33333333-3333-3333-3333-333333333333")
        res = client.post("/admin/auth/logout")
        self.assertEqual(res.status_code, 200)
        self.assertIn("33333333-3333-3333-3333-333333333333", repo.deleted_sessions)

    def test_logout_with_malformed_cookie_skips_delete_and_returns_200(self):
        """A non-UUID cookie value must not reach delete_session (which casts
        with %s::uuid) — logout should still succeed and clear the cookie."""
        repo = SpyAuthRepo()
        client = self._make_client(auth_repo=repo)
        client.cookies.set("session_id", "not-a-real-session")
        res = client.post("/admin/auth/logout")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(len(repo.deleted_sessions), 0)

    def test_logout_clears_cookie(self):
        repo = SpyAuthRepo()
        client = self._make_client(auth_repo=repo)
        client.cookies.set("session_id", "33333333-3333-3333-3333-333333333333")
        res = client.post("/admin/auth/logout")
        set_cookie = res.headers.get("set-cookie", "")
        self.assertIn("session_id", set_cookie)
        self.assertIn("Max-Age=0", set_cookie)

    def test_logout_audit_keeps_session_id_out_of_detail(self):
        """The session id belongs in the session_id column only. detail is
        returned verbatim by GET /admin/audit-log, so a raw token there
        would be readable by every other admin in the practice."""
        audit_repo = StubAuditRepo()
        client = self._make_client(auth_repo=SpyAuthRepo(), audit_repo=audit_repo)
        client.cookies.set("session_id", "33333333-3333-3333-3333-333333333333")
        client.post("/admin/auth/logout")

        logout_events = [e for e in audit_repo.logged if e["action"] == "auth.logout"]
        self.assertEqual(len(logout_events), 1)
        event = logout_events[0]
        self.assertEqual(event["session_id"], "33333333-3333-3333-3333-333333333333")
        self.assertIsNone(event["detail"])

    def test_logout_cookie_is_always_secure(self):
        repo = SpyAuthRepo()
        client = self._make_client(auth_repo=repo)
        client.cookies.set("session_id", "33333333-3333-3333-3333-333333333333")
        res = client.post("/admin/auth/logout")
        set_cookie = res.headers.get("set-cookie", "").lower()
        self.assertIn("secure", set_cookie)


# ---------------------------------------------------------------------------
# Section 7: SlowAPI rate limiting
# ---------------------------------------------------------------------------


class TestAuthRateLimiting(unittest.TestCase):
    def setUp(self):
        from app.core.rate_limit import limiter

        limiter._storage.reset()

    def tearDown(self):
        from app.core.rate_limit import limiter

        limiter._storage.reset()

    def _make_client(self):
        from fastapi.testclient import TestClient

        app = make_test_app(with_rate_limiting=True)
        return TestClient(app, raise_server_exceptions=False)

    def test_login_blocked_after_five_requests(self):
        client = self._make_client()
        payload = {"email": "admin@nhs.net", "password": "SomePassword1!"}

        with patch("app.services.admin.auth_service.verify_login_credentials"):
            for i in range(5):
                res = client.post("/admin/auth/login", json=payload)
                self.assertNotEqual(
                    res.status_code, 429, msg=f"Request {i + 1} was unexpectedly rate-limited"
                )

            res = client.post("/admin/auth/login", json=payload)

        self.assertEqual(res.status_code, 429)
        self.assertEqual(res.json()["error"]["code"], "RATE_LIMIT_EXCEEDED")

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
                    res.status_code, 429, msg=f"Request {i + 1} was unexpectedly rate-limited"
                )

            res = client.post("/admin/auth/verify", json=payload)

        self.assertEqual(res.status_code, 429)
        self.assertEqual(res.json()["error"]["code"], "RATE_LIMIT_EXCEEDED")

    def test_request_reset_blocked_after_five_requests(self):
        client = self._make_client()
        payload = {"email": "admin@nhs.net"}

        for i in range(5):
            res = client.post("/admin/auth/request-reset", json=payload)
            self.assertNotEqual(
                res.status_code, 429, msg=f"Request {i + 1} was unexpectedly rate-limited"
            )

        res = client.post("/admin/auth/request-reset", json=payload)
        self.assertEqual(res.status_code, 429)
        self.assertEqual(res.json()["error"]["code"], "RATE_LIMIT_EXCEEDED")

    def test_set_password_blocked_after_five_requests(self):
        client = self._make_client()
        payload = {"token": "sometoken", "password": "SomePassword1!"}

        for i in range(5):
            res = client.post("/admin/auth/set-password", json=payload)
            self.assertNotEqual(
                res.status_code, 429, msg=f"Request {i + 1} was unexpectedly rate-limited"
            )

        res = client.post("/admin/auth/set-password", json=payload)
        self.assertEqual(res.status_code, 429)
        self.assertEqual(res.json()["error"]["code"], "RATE_LIMIT_EXCEEDED")


if __name__ == "__main__":
    unittest.main(verbosity=2)

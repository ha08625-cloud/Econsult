"""
Tests for admin_context.py and admin_router.py.

Four sections:
1. Auth behaviour — tested against GET /admin/conditions
2. Endpoint behaviour — assumes valid auth throughout
3. Signposting sanitisation — unit tests for sanitise_signposting_html
4. MFA auth endpoints — request-code, verify, logout

Test setup uses a bare FastAPI app with app.state populated manually,
bypassing the normal startup sequence in main.py.

Section 2 uses a StubPracticeRepo that calls the real sanitise_signposting_html
function so that sanitisation side-effects (javascript: stripping, <p></p>
treated as empty, overlength rejection) are exercised through the router.

Run from project root:
    python -m pytest tests/test_admin_router.py

"""

import os
import unittest
from contextlib import contextmanager
from unittest.mock import patch

from app.repositories.practice_repository import (
    MAX_SIGNPOSTING_LENGTH,
    sanitise_signposting_html,
    InvalidSignpostingData,
)


# ---------------------------------------------------------------------------
# Minimal stubs
# ---------------------------------------------------------------------------

class StubRegistry:
    def __init__(self, condition_ids):
        self._conditions = {
            cid: {"id": cid, "label": cid.replace("_", " ").title()}
            for cid in condition_ids
        }

    def list_conditions(self):
        return list(self._conditions.values())

    def has_condition(self, condition_id):
        return condition_id in self._conditions


class StubPracticeRepo:
    """
    In-memory practice repo stub.

    Calls the real sanitise_signposting_html so that sanitisation
    side-effects (stripping unsafe content, treating empty HTML as None,
    rejecting overlength input) are exercised through the router in tests.

    database_url is present because the router accesses
    practice_repo.database_url when opening a shared transaction via
    get_conn. In unit tests get_conn is patched (see _dummy_conn below)
    so this value is never used to open a real connection.

    Mutating methods accept conn=None to match the real repository
    signatures after Step 5 added optional conn parameters. The conn
    value is ignored — the stub operates on in-memory state only.
    """
    def __init__(self):
        self.database_url = "stub://not-a-real-db"
        self._store = {}  # (practice_id, condition_id) -> str | None

    def get_signposting(self, practice_id, condition_id):
        return self._store.get((practice_id, condition_id))

    def set_signposting(self, practice_id, condition_id, value: str, conn=None):
        sanitised = sanitise_signposting_html(value)
        if sanitised is not None:
            self._store[(practice_id, condition_id)] = sanitised
        else:
            self._store.pop((practice_id, condition_id), None)

    def delete_signposting(self, practice_id, condition_id, conn=None):
        self._store.pop((practice_id, condition_id), None)


class StubAuthRepo:
    """
    In-memory auth repo stub for unit tests.

    No sessions are valid by default — session lookups always return None,
    which causes require_admin to fall through to the DEV_MODE bearer-token
    fallback. This preserves backward compatibility with the existing auth
    behaviour tests.

    MFA endpoint tests inject a more capable stub via make_test_app().
    """
    def get_session_context(self, session_id):
        return None

    def get_user_by_email(self, email):
        return None

    def get_auth_code_record(self, email):
        return None

    def upsert_auth_code(self, email, hashed_code, expires_at, last_requested_at):
        pass

    def increment_code_attempts(self, email):
        pass

    def delete_auth_code(self, email):
        pass

    def create_session(self, user_id, expires_at):
        return "stub-session-id"

    def delete_session(self, session_id):
        pass

    def count_users_for_practice(self, practice_id):
        return 0

    def insert_user(self, email, practice_id, role):
        pass


class StubAuditRepo:
    """
    No-op audit repo stub for unit tests.

    Records calls to log_event so tests can assert it was called if needed,
    but never touches the database. The conn parameter is accepted and
    ignored to match the real AuditRepository.log_event signature.
    """
    def __init__(self):
        self.logged = []

    def log_event(self, *, practice_id, actor_email, action, resource=None,
                  detail=None, ip_address=None, session_id=None, conn=None):
        self.logged.append({
            "practice_id": practice_id,
            "actor_email": actor_email,
            "action": action,
            "resource": resource,
            "detail": detail,
            "ip_address": ip_address,
            "session_id": session_id,
        })

    def list_events(self, *, practice_id, cursor=None, from_date=None,
                    to_date=None, actor=None, action_prefix=None, limit=50):
        return {"events": [], "next_cursor": None}


class StubAdminDeliveryService:
    """Captures send_mfa_code calls without sending email."""
    def __init__(self):
        self.calls = []

    def send_mfa_code(self, email, code):
        self.calls.append({"email": email, "code": code})


# ---------------------------------------------------------------------------
# App factory for tests
# ---------------------------------------------------------------------------

def make_test_app(condition_ids=None, auth_repo=None, delivery_service=None,
                  audit_repo=None):
    """
    Build a bare FastAPI app with the admin router registered and
    app.state populated. Does not run the normal startup validation.

    Registers the same exception handlers as main.py:
      - ConditionNotFound  → 404
      - APIError           → 422
      - RateLimitError     → 429
    All three are required so that error-path tests reflect production behaviour.
    """
    from fastapi import FastAPI
    from fastapi.responses import JSONResponse
    from app.routers.admin_router import router as admin_router
    from app.core.errors import APIError, RateLimitError, ConditionNotFound

    app = FastAPI()
    app.include_router(admin_router, prefix="/admin", tags=["admin"])

    app.state.practice_id = "test_practice"
    app.state.registry = StubRegistry(condition_ids or ["urinary_symptoms"])
    app.state.practice_repo = StubPracticeRepo()
    app.state.auth_repo = auth_repo or StubAuthRepo()
    app.state.audit_repo = audit_repo or StubAuditRepo()
    app.state.allowed_admin_domains = "nhs.net"
    app.state.admin_delivery_service = delivery_service or StubAdminDeliveryService()

    @app.exception_handler(ConditionNotFound)
    async def condition_not_found_handler(_, exc: ConditionNotFound):
        return JSONResponse(
            status_code=404,
            content={"error": {"code": "CONDITION_NOT_FOUND", "message": f"Unknown condition: {exc}"}},
        )

    @app.exception_handler(APIError)
    async def api_error_handler(_, exc: APIError):
        return JSONResponse(
            status_code=422,
            content={"error": {"code": exc.code, "message": exc.message}},
        )

    @app.exception_handler(RateLimitError)
    async def rate_limit_handler(_, exc: RateLimitError):
        return JSONResponse(
            status_code=429,
            content={"error": {"code": "RATE_LIMIT_EXCEEDED", "message": str(exc)}},
        )

    return app


# ---------------------------------------------------------------------------
# Section 1: Auth behaviour
# ---------------------------------------------------------------------------

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
# Section 2: Endpoint behaviour
# (DEV_MODE=1, no ADMIN_TOKEN — any token passes)
# ---------------------------------------------------------------------------

VALID_AUTH = {"Authorization": "Bearer testtoken"}


@contextmanager
def _dummy_conn(_database_url):
    """
    Stand-in for app.core.db.get_conn in unit tests.

    Yields a sentinel string instead of a real psycopg2 connection.
    The stub repositories accept conn=None and ignore it, so the
    sentinel is never used for actual database operations. It only
    needs to exist so that the ``with get_conn(...) as conn:`` block
    in the router succeeds without opening a real Postgres connection.
    """
    yield "stub-conn"


class TestEndpointBehaviour(unittest.TestCase):

    def setUp(self):
        os.environ["DEV_MODE"] = "1"
        os.environ.pop("ADMIN_TOKEN", None)
        from fastapi.testclient import TestClient
        # Patch get_conn where the router imports it so that the shared-
        # transaction blocks in mutating endpoints do not attempt to open
        # a real Postgres connection.
        self._conn_patcher = patch(
            "app.routers.admin_router.get_conn", _dummy_conn
        )
        self._conn_patcher.start()
        self.app = make_test_app(condition_ids=["urinary_symptoms"])
        self.client = TestClient(self.app, raise_server_exceptions=True)
        self.practice_id = "test_practice"
        self.condition_id = "urinary_symptoms"
        self.unknown_id = "nonexistent_condition"

    def tearDown(self):
        self._conn_patcher.stop()
        os.environ.pop("DEV_MODE", None)

    # --- GET /admin/conditions ---

    def test_list_conditions_returns_condition_list(self):
        res = self.client.get("/admin/conditions", headers=VALID_AUTH)
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIn("conditions", data)
        ids = [c["id"] for c in data["conditions"]]
        self.assertIn("urinary_symptoms", ids)

    # --- GET signposting ---

    def test_get_signposting_unknown_condition_returns_404(self):
        res = self.client.get(
            f"/admin/conditions/{self.unknown_id}/signposting",
            headers=VALID_AUTH,
        )
        self.assertEqual(res.status_code, 404)

    def test_get_signposting_when_none_configured_returns_null(self):
        res = self.client.get(
            f"/admin/conditions/{self.condition_id}/signposting",
            headers=VALID_AUTH,
        )
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIsNone(data["signposting"])

    # --- PUT signposting ---

    def test_put_signposting_stores_and_returns_string(self):
        body = {"signposting": "<p>Call physio: 0800 123 456</p>"}
        res = self.client.put(
            f"/admin/conditions/{self.condition_id}/signposting",
            json=body,
            headers=VALID_AUTH,
        )
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIsNotNone(data["signposting"])
        self.assertIn("Call physio", data["signposting"])

    def test_put_empty_string_clears_signposting_and_returns_null(self):
        self.client.put(
            f"/admin/conditions/{self.condition_id}/signposting",
            json={"signposting": "<p>something</p>"},
            headers=VALID_AUTH,
        )
        res = self.client.put(
            f"/admin/conditions/{self.condition_id}/signposting",
            json={"signposting": ""},
            headers=VALID_AUTH,
        )
        self.assertEqual(res.status_code, 200)
        self.assertIsNone(res.json()["signposting"])
        get_res = self.client.get(
            f"/admin/conditions/{self.condition_id}/signposting",
            headers=VALID_AUTH,
        )
        self.assertIsNone(get_res.json()["signposting"])

    def test_put_whitespace_only_string_is_treated_as_clear_and_returns_null(self):
        res = self.client.put(
            f"/admin/conditions/{self.condition_id}/signposting",
            json={"signposting": "   "},
            headers=VALID_AUTH,
        )
        self.assertEqual(res.status_code, 200)
        self.assertIsNone(res.json()["signposting"])

    def test_put_quill_empty_output_clears_signposting(self):
        self.client.put(
            f"/admin/conditions/{self.condition_id}/signposting",
            json={"signposting": "<p>existing content</p>"},
            headers=VALID_AUTH,
        )
        res = self.client.put(
            f"/admin/conditions/{self.condition_id}/signposting",
            json={"signposting": "<p></p>"},
            headers=VALID_AUTH,
        )
        self.assertEqual(res.status_code, 200)
        self.assertIsNone(res.json()["signposting"])

    def test_put_response_reflects_sanitised_content_not_raw_input(self):
        res = self.client.put(
            f"/admin/conditions/{self.condition_id}/signposting",
            json={"signposting": '<p><a href="javascript:alert(1)">click me</a></p>'},
            headers=VALID_AUTH,
        )
        self.assertEqual(res.status_code, 200)
        saved = res.json()["signposting"]
        if saved is not None:
            self.assertNotIn("javascript:", saved)

    def test_put_overlength_returns_422(self):
        res = self.client.put(
            f"/admin/conditions/{self.condition_id}/signposting",
            json={"signposting": "a" * (MAX_SIGNPOSTING_LENGTH + 1)},
            headers=VALID_AUTH,
        )
        self.assertEqual(res.status_code, 422)
        self.assertIn(str(MAX_SIGNPOSTING_LENGTH), res.json()["error"]["message"])

    def test_put_exactly_max_length_returns_200(self):
        inner = "a" * (MAX_SIGNPOSTING_LENGTH - len("<p></p>"))
        raw = f"<p>{inner}</p>"
        raw = raw[:MAX_SIGNPOSTING_LENGTH]
        res = self.client.put(
            f"/admin/conditions/{self.condition_id}/signposting",
            json={"signposting": raw},
            headers=VALID_AUTH,
        )
        self.assertEqual(res.status_code, 200)

    def test_put_rejects_non_string_value_with_422(self):
        res = self.client.put(
            f"/admin/conditions/{self.condition_id}/signposting",
            json={"signposting": ["item"]},
            headers=VALID_AUTH,
        )
        self.assertEqual(res.status_code, 422)

    def test_put_rejects_numeric_value_with_422(self):
        res = self.client.put(
            f"/admin/conditions/{self.condition_id}/signposting",
            json={"signposting": 123},
            headers=VALID_AUTH,
        )
        self.assertEqual(res.status_code, 422)

    def test_put_missing_signposting_key_returns_422(self):
        res = self.client.put(
            f"/admin/conditions/{self.condition_id}/signposting",
            json={"wrong_key": "value"},
            headers=VALID_AUTH,
        )
        self.assertEqual(res.status_code, 422)

    def test_put_unknown_condition_returns_404(self):
        res = self.client.put(
            f"/admin/conditions/{self.unknown_id}/signposting",
            json={"signposting": "<p>item</p>"},
            headers=VALID_AUTH,
        )
        self.assertEqual(res.status_code, 404)

    # --- DELETE signposting ---

    def test_delete_removes_signposting_and_subsequent_get_returns_null(self):
        self.client.put(
            f"/admin/conditions/{self.condition_id}/signposting",
            json={"signposting": "<p>item</p>"},
            headers=VALID_AUTH,
        )
        res = self.client.delete(
            f"/admin/conditions/{self.condition_id}/signposting",
            headers=VALID_AUTH,
        )
        self.assertEqual(res.status_code, 204)
        get_res = self.client.get(
            f"/admin/conditions/{self.condition_id}/signposting",
            headers=VALID_AUTH,
        )
        self.assertIsNone(get_res.json()["signposting"])

    def test_delete_idempotent_when_no_signposting_configured(self):
        res = self.client.delete(
            f"/admin/conditions/{self.condition_id}/signposting",
            headers=VALID_AUTH,
        )
        self.assertEqual(res.status_code, 204)

    def test_delete_unknown_condition_returns_404(self):
        res = self.client.delete(
            f"/admin/conditions/{self.unknown_id}/signposting",
            headers=VALID_AUTH,
        )
        self.assertEqual(res.status_code, 404)


# ---------------------------------------------------------------------------
# Section 3: Signposting sanitisation — unit tests for sanitise_signposting_html
# ---------------------------------------------------------------------------

class TestSignpostingSanitisation(unittest.TestCase):

    def test_valid_html_returned_with_content_intact(self):
        result = sanitise_signposting_html("<p>Call us on <strong>0800 123 456</strong>.</p>")
        self.assertIsNotNone(result)
        self.assertIn("Call us on", result)

    def test_empty_string_returns_none(self):
        self.assertIsNone(sanitise_signposting_html(""))

    def test_whitespace_only_returns_none(self):
        self.assertIsNone(sanitise_signposting_html("   "))

    def test_quill_empty_paragraph_returns_none(self):
        self.assertIsNone(sanitise_signposting_html("<p></p>"))

    def test_javascript_href_is_stripped(self):
        result = sanitise_signposting_html('<p><a href="javascript:alert(1)">click</a></p>')
        if result is not None:
            self.assertNotIn("javascript:", result)

    def test_http_href_is_preserved(self):
        result = sanitise_signposting_html('<p><a href="https://example.com">link</a></p>')
        self.assertIsNotNone(result)
        self.assertIn("https://example.com", result)

    def test_overlength_raises_invalid_signposting_data(self):
        with self.assertRaises(InvalidSignpostingData):
            sanitise_signposting_html("a" * (MAX_SIGNPOSTING_LENGTH + 1))

    def test_exactly_max_length_does_not_raise(self):
        inner = "a" * (MAX_SIGNPOSTING_LENGTH - len("<p></p>"))
        raw = f"<p>{inner}</p>"
        raw = raw[:MAX_SIGNPOSTING_LENGTH]
        sanitise_signposting_html(raw)  # must not raise

    def test_disallowed_tag_is_stripped(self):
        result = sanitise_signposting_html("<p>text</p><script>alert(1)</script>")
        self.assertIsNotNone(result)
        self.assertNotIn("<script>", result)
        self.assertIn("text", result)


# ---------------------------------------------------------------------------
# Section 4: MFA auth endpoints
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


class TestRequestMfaCode(unittest.TestCase):
    """Tests for POST /admin/auth/request-code."""

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


class TestVerifyMfaCode(unittest.TestCase):
    """Tests for POST /admin/auth/verify."""

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


class TestLogout(unittest.TestCase):
    """Tests for POST /admin/auth/logout."""

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
# Section 5: Audit log endpoint
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


class TestAuditLogEndpoint(unittest.TestCase):
    """Tests for GET /admin/audit-log."""

    _AUTH_HEADERS = {"Authorization": "Bearer dev-token"}

    def _make_client(self, audit_repo=None):
        from fastapi.testclient import TestClient
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
        from datetime import datetime, timezone
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
        from datetime import date
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


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    unittest.main(verbosity=2)
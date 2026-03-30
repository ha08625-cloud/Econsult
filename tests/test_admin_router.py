"""
Tests for admin_context.py and admin_router.py.

Four sections:
1. Auth behaviour — tested against GET /admin/conditions
2. Endpoint behaviour — assumes valid auth throughout
3. Doctor list endpoints — GET and PUT /admin/doctors
4. Signposting sanitisation — unit tests for sanitise_signposting_html

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

from app.repositories.practice_repository import (
    MAX_SIGNPOSTING_LENGTH,
    MAX_DOCTOR_NAME_LENGTH,
    MAX_DOCTOR_LIST_LENGTH,
    sanitise_signposting_html,
    InvalidSignpostingData,
    InvalidDoctorListError,
)


# ---------------------------------------------------------------------------
# Minimal stubs for registry and practice_repo
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

    Doctor list methods delegate to the real _validate_doctor_list logic
    by importing and calling it directly, so validation errors surface
    correctly through the router.
    """
    def __init__(self):
        self._store = {}        # (practice_id, condition_id) -> str | None
        self._doctors = {}      # practice_id -> list[str]

    def get_practice(self, practice_id):
        return {
            "practice_id": practice_id,
            "name": "Test Practice",
            "email": "test@example.com",
        }

    def update_email(self, practice_id, email):
        pass

    def get_signposting(self, practice_id, condition_id):
        return self._store.get((practice_id, condition_id))

    def set_signposting(self, practice_id, condition_id, value: str):
        sanitised = sanitise_signposting_html(value)
        if sanitised is not None:
            self._store[(practice_id, condition_id)] = sanitised
        else:
            self._store.pop((practice_id, condition_id), None)

    def delete_signposting(self, practice_id, condition_id):
        self._store.pop((practice_id, condition_id), None)

    def get_doctors(self, practice_id):
        return list(self._doctors.get(practice_id, []))

    def set_doctors(self, practice_id, names):
        # Delegate to the real validation so errors surface through the router
        from app.repositories.practice_repository import PracticeRepository
        # Instantiate a throwaway repo just to run _validate_doctor_list.
        # We pass a dummy URL because we never connect to the database.
        repo = PracticeRepository.__new__(PracticeRepository)
        repo._validate_doctor_list(names)
        self._doctors[practice_id] = [name.strip() for name in names]


# ---------------------------------------------------------------------------
# App factory for tests
# ---------------------------------------------------------------------------

def make_test_app(condition_ids=None):
    """
    Build a bare FastAPI app with the admin router registered and
    app.state populated. Does not run the normal startup validation.

    Registers the same two exception handlers as main.py:
      - ConditionNotFound  → 404
      - APIError           → 422
    Both are required so that error-path tests reflect production behaviour.
    """
    from fastapi import FastAPI
    from fastapi.responses import JSONResponse
    from app.routers.admin_router import router as admin_router
    from app.core.errors import APIError
    from app.core.condition_registry import ConditionNotFound

    app = FastAPI()
    app.include_router(admin_router, prefix="/admin", tags=["admin"])

    app.state.practice_id = "test_practice"
    app.state.registry = StubRegistry(condition_ids or ["urinary_symptoms"])
    app.state.practice_repo = StubPracticeRepo()

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
        os.environ.pop("DEV_MODE", None)
        try:
            res = self._get(headers={"Authorization": "Bearer wrong-token"})
            self.assertEqual(res.status_code, 401)
        finally:
            del os.environ["ADMIN_TOKEN"]

    def test_correct_token_when_admin_token_set_returns_200(self):
        os.environ["ADMIN_TOKEN"] = "correct-token"
        os.environ.pop("DEV_MODE", None)
        try:
            res = self._get(headers={"Authorization": "Bearer correct-token"})
            self.assertEqual(res.status_code, 200)
        finally:
            del os.environ["ADMIN_TOKEN"]

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


class TestEndpointBehaviour(unittest.TestCase):

    def setUp(self):
        os.environ["DEV_MODE"] = "1"
        os.environ.pop("ADMIN_TOKEN", None)
        from fastapi.testclient import TestClient
        self.app = make_test_app(condition_ids=["urinary_symptoms"])
        self.client = TestClient(self.app, raise_server_exceptions=True)
        self.practice_id = "test_practice"
        self.condition_id = "urinary_symptoms"
        self.unknown_id = "nonexistent_condition"

    def tearDown(self):
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
        # Step 1: store something first
        self.client.put(
            f"/admin/conditions/{self.condition_id}/signposting",
            json={"signposting": "<p>something</p>"},
            headers=VALID_AUTH,
        )
        # Step 2: PUT with empty string — this is a clear, not an error
        res = self.client.put(
            f"/admin/conditions/{self.condition_id}/signposting",
            json={"signposting": ""},
            headers=VALID_AUTH,
        )
        self.assertEqual(res.status_code, 200)
        self.assertIsNone(res.json()["signposting"])
        # Step 3: subsequent GET also returns null
        get_res = self.client.get(
            f"/admin/conditions/{self.condition_id}/signposting",
            headers=VALID_AUTH,
        )
        self.assertIsNone(get_res.json()["signposting"])

    def test_put_whitespace_only_string_is_treated_as_clear_and_returns_null(self):
        # Whitespace-only content is never stored — treated as a clear instruction
        res = self.client.put(
            f"/admin/conditions/{self.condition_id}/signposting",
            json={"signposting": "   "},
            headers=VALID_AUTH,
        )
        self.assertEqual(res.status_code, 200)
        self.assertIsNone(res.json()["signposting"])

    def test_put_quill_empty_output_clears_signposting(self):
        # <p></p> is what the Quill editor emits when the user clears the field.
        # It must be treated as empty and return null, not stored as a blank paragraph.
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
        # A javascript: href must be stripped by nh3 before storage.
        # The PUT response must reflect what was stored, not the raw input.
        res = self.client.put(
            f"/admin/conditions/{self.condition_id}/signposting",
            json={"signposting": '<p><a href="javascript:alert(1)">click me</a></p>'},
            headers=VALID_AUTH,
        )
        self.assertEqual(res.status_code, 200)
        saved = res.json()["signposting"]
        # After nh3 strips the unsafe href, the link text survives but the
        # javascript: attribute is gone. The result is non-null (text remains).
        if saved is not None:
            self.assertNotIn("javascript:", saved)

    def test_put_overlength_returns_422(self):
        # Content exceeding MAX_SIGNPOSTING_LENGTH is rejected before sanitisation.
        res = self.client.put(
            f"/admin/conditions/{self.condition_id}/signposting",
            json={"signposting": "a" * (MAX_SIGNPOSTING_LENGTH + 1)},
            headers=VALID_AUTH,
        )
        self.assertEqual(res.status_code, 422)
        self.assertIn(str(MAX_SIGNPOSTING_LENGTH), res.json()["error"]["message"])

    def test_put_exactly_max_length_returns_200(self):
        # Exactly MAX_SIGNPOSTING_LENGTH characters must be accepted.
        # Build a string that contains real content so nh3 does not strip
        # it to empty. Wrap in a <p> tag and pad to the limit.
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
        # signposting must be a string; a list is the wrong type
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
        # Set up signposting first
        self.client.put(
            f"/admin/conditions/{self.condition_id}/signposting",
            json={"signposting": "<p>item</p>"},
            headers=VALID_AUTH,
        )
        # Delete
        res = self.client.delete(
            f"/admin/conditions/{self.condition_id}/signposting",
            headers=VALID_AUTH,
        )
        self.assertEqual(res.status_code, 204)
        # Subsequent GET returns null
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
# Section 3: Doctor list endpoints
# ---------------------------------------------------------------------------

class TestDoctorListEndpoints(unittest.TestCase):

    def setUp(self):
        os.environ["DEV_MODE"] = "1"
        os.environ.pop("ADMIN_TOKEN", None)
        from fastapi.testclient import TestClient
        self.app = make_test_app()
        self.client = TestClient(self.app, raise_server_exceptions=True)

    def tearDown(self):
        os.environ.pop("DEV_MODE", None)

    # --- GET /admin/doctors ---

    def test_get_doctors_returns_empty_list_when_none_configured(self):
        res = self.client.get("/admin/doctors", headers=VALID_AUTH)
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIn("doctors", data)
        self.assertEqual(data["doctors"], [])

    def test_get_doctors_returns_list_after_put(self):
        names = ["Dr Smith", "Dr Jones"]
        self.client.put("/admin/doctors", json={"doctors": names}, headers=VALID_AUTH)
        res = self.client.get("/admin/doctors", headers=VALID_AUTH)
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["doctors"], names)

    # --- PUT /admin/doctors ---

    def test_put_doctors_returns_saved_list(self):
        names = ["Dr Smith", "Dr Jones", "Dr Patel"]
        res = self.client.put("/admin/doctors", json={"doctors": names}, headers=VALID_AUTH)
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["doctors"], names)

    def test_put_doctors_replaces_existing_list(self):
        self.client.put(
            "/admin/doctors",
            json={"doctors": ["Dr Smith", "Dr Jones"]},
            headers=VALID_AUTH,
        )
        res = self.client.put(
            "/admin/doctors",
            json={"doctors": ["Dr Brown"]},
            headers=VALID_AUTH,
        )
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["doctors"], ["Dr Brown"])

    def test_put_doctors_with_empty_list_clears_doctors(self):
        self.client.put(
            "/admin/doctors",
            json={"doctors": ["Dr Smith"]},
            headers=VALID_AUTH,
        )
        res = self.client.put("/admin/doctors", json={"doctors": []}, headers=VALID_AUTH)
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["doctors"], [])

    def test_put_doctors_preserves_order(self):
        # Non-alphabetical order to confirm storage order is respected
        names = ["Dr Zebra", "Dr Apple", "Dr Mango"]
        res = self.client.put("/admin/doctors", json={"doctors": names}, headers=VALID_AUTH)
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["doctors"], names)

    def test_put_doctors_missing_key_returns_422(self):
        res = self.client.put(
            "/admin/doctors",
            json={"wrong_key": ["Dr Smith"]},
            headers=VALID_AUTH,
        )
        self.assertEqual(res.status_code, 422)

    def test_put_doctors_non_list_value_returns_422(self):
        res = self.client.put(
            "/admin/doctors",
            json={"doctors": "Dr Smith"},
            headers=VALID_AUTH,
        )
        self.assertEqual(res.status_code, 422)

    def test_put_doctors_empty_name_in_list_returns_422(self):
        res = self.client.put(
            "/admin/doctors",
            json={"doctors": ["Dr Smith", "  ", "Dr Jones"]},
            headers=VALID_AUTH,
        )
        self.assertEqual(res.status_code, 422)

    def test_put_doctors_name_too_long_returns_422(self):
        long_name = "Dr " + "A" * 100  # 103 chars, over limit
        res = self.client.put(
            "/admin/doctors",
            json={"doctors": [long_name]},
            headers=VALID_AUTH,
        )
        self.assertEqual(res.status_code, 422)

    def test_put_doctors_list_too_long_returns_422(self):
        too_many = [f"Dr Doctor{i}" for i in range(MAX_DOCTOR_LIST_LENGTH + 1)]
        res = self.client.put(
            "/admin/doctors",
            json={"doctors": too_many},
            headers=VALID_AUTH,
        )
        self.assertEqual(res.status_code, 422)

    def test_get_doctors_requires_auth(self):
        res = self.client.get("/admin/doctors")
        self.assertEqual(res.status_code, 401)

    def test_put_doctors_requires_auth(self):
        res = self.client.put("/admin/doctors", json={"doctors": []})
        self.assertEqual(res.status_code, 401)


# ---------------------------------------------------------------------------
# Section 4: Signposting sanitisation — unit tests for sanitise_signposting_html
#
# These tests call the sanitiser directly because the behaviour being tested
# is in the repository layer, not the HTTP layer. Testing via the router
# would require inspecting side effects rather than return values.
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
        # The length check fires before nh3 runs, so a string at exactly the
        # limit must not raise even if nh3 strips most of it.
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
# Runner
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    unittest.main(verbosity=2)
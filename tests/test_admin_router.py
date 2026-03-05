"""
Tests for admin_context.py and admin_router.py.

Two sections:
1. Auth behaviour — tested against GET /admin/conditions
2. Endpoint behaviour — assumes valid auth throughout

Test setup uses a bare FastAPI app with app.state populated manually,
bypassing the normal startup sequence in main.py.

Run from project root:
    python -m tests.test_admin_router
"""

import os
import sys
import unittest

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
    def __init__(self):
        self._store = {}  # (practice_id, condition_id) -> list[str] | sentinel

    def get_signposting(self, practice_id, condition_id):
        return self._store.get((practice_id, condition_id))

    def set_signposting(self, practice_id, condition_id, items):
        self._store[(practice_id, condition_id)] = items

    def delete_signposting(self, practice_id, condition_id):
        self._store.pop((practice_id, condition_id), None)


# ---------------------------------------------------------------------------
# App factory for tests
# ---------------------------------------------------------------------------

def make_test_app(condition_ids=None):
    """
    Build a bare FastAPI app with the admin router registered and
    app.state populated. Does not run the normal startup validation.
    """
    from fastapi import FastAPI
    from admin_router import router as admin_router

    app = FastAPI()
    app.include_router(admin_router, prefix="/admin", tags=["admin"])

    app.state.practice_id = "test_practice"
    app.state.registry = StubRegistry(condition_ids or ["urinary_symptoms"])
    app.state.practice_repo = StubPracticeRepo()

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

    def test_put_signposting_stores_and_returns_items(self):
        body = {"signposting": ["Call physio: 0800 123 456"]}
        res = self.client.put(
            f"/admin/conditions/{self.condition_id}/signposting",
            json=body,
            headers=VALID_AUTH,
        )
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["signposting"], ["Call physio: 0800 123 456"])

    def test_put_empty_list_stores_and_returns_null(self):
        # Step 1: store a non-empty list first so we know something exists
        self.client.put(
            f"/admin/conditions/{self.condition_id}/signposting",
            json={"signposting": ["something"]},
            headers=VALID_AUTH,
        )
        # Step 2: PUT with empty list
        res = self.client.put(
            f"/admin/conditions/{self.condition_id}/signposting",
            json={"signposting": []},
            headers=VALID_AUTH,
        )
        self.assertEqual(res.status_code, 200)
        # Response normalises to null
        self.assertIsNone(res.json()["signposting"])
        # Step 3: subsequent GET also returns null
        get_res = self.client.get(
            f"/admin/conditions/{self.condition_id}/signposting",
            headers=VALID_AUTH,
        )
        self.assertIsNone(get_res.json()["signposting"])

    def test_put_strips_whitespace_from_items(self):
        body = {"signposting": ["  Call physio  ", " 0800 123 456 "]}
        res = self.client.put(
            f"/admin/conditions/{self.condition_id}/signposting",
            json=body,
            headers=VALID_AUTH,
        )
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["signposting"], ["Call physio", "0800 123 456"])

    def test_put_rejects_empty_string_items_after_stripping(self):
        res = self.client.put(
            f"/admin/conditions/{self.condition_id}/signposting",
            json={"signposting": ["   "]},
            headers=VALID_AUTH,
        )
        self.assertEqual(res.status_code, 400)

    def test_put_rejects_non_string_items(self):
        res = self.client.put(
            f"/admin/conditions/{self.condition_id}/signposting",
            json={"signposting": [123]},
            headers=VALID_AUTH,
        )
        self.assertEqual(res.status_code, 400)

    def test_put_missing_signposting_key_returns_400(self):
        res = self.client.put(
            f"/admin/conditions/{self.condition_id}/signposting",
            json={"wrong_key": []},
            headers=VALID_AUTH,
        )
        self.assertEqual(res.status_code, 400)

    def test_put_unknown_condition_returns_404(self):
        res = self.client.put(
            f"/admin/conditions/{self.unknown_id}/signposting",
            json={"signposting": ["item"]},
            headers=VALID_AUTH,
        )
        self.assertEqual(res.status_code, 404)

    # --- DELETE signposting ---

    def test_delete_removes_signposting_and_subsequent_get_returns_null(self):
        # Set up signposting first
        self.client.put(
            f"/admin/conditions/{self.condition_id}/signposting",
            json={"signposting": ["item"]},
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
# Runner
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    unittest.main(verbosity=2)

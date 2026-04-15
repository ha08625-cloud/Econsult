"""
Tests for admin_practice_router.py

Covers:
1. Practice endpoints (conditions, signposting)
2. Signposting HTML sanitisation rules
"""

import os
import unittest
from unittest.mock import patch
from fastapi.testclient import TestClient

from app.repositories.practice_repository import (
    MAX_SIGNPOSTING_LENGTH,
    sanitise_signposting_html,
    InvalidSignpostingData,
)
from tests.helpers.admin_test_helpers import make_test_app, dummy_conn

VALID_AUTH = {"Authorization": "Bearer testtoken"}

# ---------------------------------------------------------------------------
# Section 1: Endpoint behaviour
# ---------------------------------------------------------------------------

class TestPracticeEndpointBehaviour(unittest.TestCase):

    def setUp(self):
        os.environ["DEV_MODE"] = "1"
        os.environ.pop("ADMIN_TOKEN", None)
        
        # FIXED PATCH TARGET: Points to the new sub-router where get_conn is actually used
        self._conn_patcher = patch(
            "app.routers.admin.admin_practice_router.get_conn", dummy_conn
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
# Section 2: Signposting sanitisation logic
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

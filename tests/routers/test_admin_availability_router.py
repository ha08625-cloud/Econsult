"""
Tests for admin_availability_router.py.

Exercises the availability configuration, overrides, and exceptions endpoints.
Authenticates via session cookie using TEST_SESSION_COOKIE from admin_test_helpers.

Coverage:
  GET  /availability
  PUT  /availability
  POST /availability/override
  DELETE /availability/override
  GET  /availability/exceptions
  PUT  /availability/exceptions/{date}
  DELETE /availability/exceptions/{date}
"""

import unittest
import datetime
from datetime import timezone
from unittest.mock import patch

from fastapi.testclient import TestClient

from tests.helpers.admin_test_helpers import make_test_app, dummy_conn, TEST_SESSION_COOKIE


class TestAdminAvailabilityRouter(unittest.TestCase):

    def setUp(self):
        self._conn_patcher = patch(
            "app.routers.admin.admin_availability_router.get_conn", dummy_conn
        )
        self._conn_patcher.start()

        self.app = make_test_app()
        self.availability_repo = self.app.state.availability_repo
        self.client = TestClient(self.app, raise_server_exceptions=True)

        # A timezone-aware datetime 2 hours from now. Used for override tests.
        # Chosen to be safely within the validate_override window of
        # (now_utc, now_utc + 24h].
        self.override_expires = (
            datetime.datetime.now(timezone.utc) + datetime.timedelta(hours=2)
        )

        # A future date used for exception tests.
        self.future_date = (
            datetime.datetime.now(timezone.utc) + datetime.timedelta(days=1)
        ).date()

    def tearDown(self):
        self._conn_patcher.stop()

    # ---------------------------------------------------------------------------
    # GET /availability
    # ---------------------------------------------------------------------------

    def test_get_availability_returns_formatted_config(self):
        res = self.client.get("/admin/availability", cookies=TEST_SESSION_COOKIE)
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["is_active"], True)
        self.assertEqual(data["open_time"], "08:00")
        self.assertEqual(data["close_time"], "18:30")
        self.assertIsNone(data["override_status"])

    def test_get_availability_requires_auth(self):
        res = self.client.get("/admin/availability")
        self.assertEqual(res.status_code, 401)

    # ---------------------------------------------------------------------------
    # PUT /availability
    # ---------------------------------------------------------------------------

    def test_put_availability_updates_config(self):
        body = {
            "is_active": True,
            "weekly_open_days": ["mon", "wed", "fri"],
            "open_time": "09:00",
            "close_time": "17:00",
            "closed_message": "Closed for lunch",
        }
        res = self.client.put("/admin/availability", json=body, cookies=TEST_SESSION_COOKIE)
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["weekly_open_days"], ["mon", "wed", "fri"])
        self.assertEqual(data["open_time"], "09:00")
        self.assertEqual(data["closed_message"], "Closed for lunch")

    def test_put_availability_accepts_null_closed_message(self):
        body = {
            "is_active": True,
            "weekly_open_days": ["mon"],
            "open_time": "08:00",
            "close_time": "18:00",
            "closed_message": None,
        }
        res = self.client.put("/admin/availability", json=body, cookies=TEST_SESSION_COOKIE)
        self.assertEqual(res.status_code, 200)
        self.assertIsNone(res.json()["closed_message"])

    def test_put_availability_active_with_empty_open_days_returns_200(self):
        # Empty weekly_open_days with is_active=True is a misconfiguration but
        # not a validation error — the router logs a warning and proceeds.
        body = {
            "is_active": True,
            "weekly_open_days": [],
            "open_time": "08:00",
            "close_time": "18:00",
            "closed_message": None,
        }
        res = self.client.put("/admin/availability", json=body, cookies=TEST_SESSION_COOKIE)
        self.assertEqual(res.status_code, 200)

    def test_put_availability_auto_clears_override_when_deactivated(self):
        # Set an override first.
        self.availability_repo.set_override(
            "test_practice", "open", self.override_expires, "test override"
        )
        body = {
            "is_active": False,
            "weekly_open_days": ["mon"],
            "open_time": "08:00",
            "close_time": "18:00",
            "closed_message": None,
        }
        res = self.client.put("/admin/availability", json=body, cookies=TEST_SESSION_COOKIE)
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertFalse(data["is_active"])
        self.assertIsNone(data["override_status"])
        self.assertIsNone(data["override_expires_at"])

    def test_put_availability_invalid_time_format_returns_422(self):
        body = {
            "is_active": True,
            "weekly_open_days": ["mon"],
            "open_time": "9 AM",
            "close_time": "18:00",
            "closed_message": None,
        }
        res = self.client.put("/admin/availability", json=body, cookies=TEST_SESSION_COOKIE)
        self.assertEqual(res.status_code, 422)

    def test_put_availability_invalid_day_returns_422(self):
        body = {
            "is_active": True,
            "weekly_open_days": ["monday"],  # must be "mon"
            "open_time": "08:00",
            "close_time": "18:00",
            "closed_message": None,
        }
        res = self.client.put("/admin/availability", json=body, cookies=TEST_SESSION_COOKIE)
        self.assertEqual(res.status_code, 422)

    def test_put_availability_equal_open_close_time_returns_422(self):
        body = {
            "is_active": True,
            "weekly_open_days": ["mon"],
            "open_time": "09:00",
            "close_time": "09:00",
            "closed_message": None,
        }
        res = self.client.put("/admin/availability", json=body, cookies=TEST_SESSION_COOKIE)
        self.assertEqual(res.status_code, 422)

    def test_put_availability_close_before_open_returns_422(self):
        body = {
            "is_active": True,
            "weekly_open_days": ["mon"],
            "open_time": "18:00",
            "close_time": "08:00",
            "closed_message": None,
        }
        res = self.client.put("/admin/availability", json=body, cookies=TEST_SESSION_COOKIE)
        self.assertEqual(res.status_code, 422)

    def test_put_availability_missing_is_active_returns_422(self):
        body = {
            "weekly_open_days": ["mon"],
            "open_time": "08:00",
            "close_time": "18:00",
        }
        res = self.client.put("/admin/availability", json=body, cookies=TEST_SESSION_COOKIE)
        self.assertEqual(res.status_code, 422)

    # ---------------------------------------------------------------------------
    # POST /availability/override
    # ---------------------------------------------------------------------------

    def test_post_override_sets_override(self):
        expires_at_str = self.override_expires.isoformat()
        body = {
            "status": "closed",
            "expires_at": expires_at_str,
            "message": "Emergency closure",
        }
        res = self.client.post(
            "/admin/availability/override", json=body, cookies=TEST_SESSION_COOKIE
        )
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["override_status"], "closed")
        self.assertEqual(data["override_expires_at"], expires_at_str)
        self.assertEqual(data["override_message"], "Emergency closure")

    def test_post_override_accepts_null_message(self):
        body = {
            "status": "open",
            "expires_at": self.override_expires.isoformat(),
            "message": None,
        }
        res = self.client.post(
            "/admin/availability/override", json=body, cookies=TEST_SESSION_COOKIE
        )
        self.assertEqual(res.status_code, 200)
        self.assertIsNone(res.json()["override_message"])

    def test_post_override_rejects_timezone_naive_datetime(self):
        naive = self.override_expires.replace(tzinfo=None).isoformat()
        body = {"status": "closed", "expires_at": naive, "message": None}
        res = self.client.post(
            "/admin/availability/override", json=body, cookies=TEST_SESSION_COOKIE
        )
        self.assertEqual(res.status_code, 422)
        self.assertIn("timezone offset", res.json()["error"]["message"])

    def test_post_override_invalid_status_returns_422(self):
        body = {
            "status": "maybe_open",
            "expires_at": self.override_expires.isoformat(),
            "message": None,
        }
        res = self.client.post(
            "/admin/availability/override", json=body, cookies=TEST_SESSION_COOKIE
        )
        self.assertEqual(res.status_code, 422)

    def test_post_override_expires_at_in_past_returns_422(self):
        past = (
            datetime.datetime.now(timezone.utc) - datetime.timedelta(hours=1)
        ).isoformat()
        body = {"status": "closed", "expires_at": past, "message": None}
        res = self.client.post(
            "/admin/availability/override", json=body, cookies=TEST_SESSION_COOKIE
        )
        self.assertEqual(res.status_code, 422)

    def test_post_override_expires_at_beyond_24h_returns_422(self):
        too_far = (
            datetime.datetime.now(timezone.utc) + datetime.timedelta(hours=25)
        ).isoformat()
        body = {"status": "closed", "expires_at": too_far, "message": None}
        res = self.client.post(
            "/admin/availability/override", json=body, cookies=TEST_SESSION_COOKIE
        )
        self.assertEqual(res.status_code, 422)

    # ---------------------------------------------------------------------------
    # DELETE /availability/override
    # ---------------------------------------------------------------------------

    def test_delete_override_clears_active_override(self):
        self.availability_repo.set_override(
            "test_practice", "closed", self.override_expires, "test"
        )
        res = self.client.delete(
            "/admin/availability/override", cookies=TEST_SESSION_COOKIE
        )
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIsNone(data["override_status"])
        self.assertIsNone(data["override_expires_at"])

    def test_delete_override_idempotent_when_no_override_active(self):
        # No override set — should still return 200 cleanly.
        res = self.client.delete(
            "/admin/availability/override", cookies=TEST_SESSION_COOKIE
        )
        self.assertEqual(res.status_code, 200)
        self.assertIsNone(res.json()["override_status"])

    # ---------------------------------------------------------------------------
    # GET /availability/exceptions
    # ---------------------------------------------------------------------------

    def test_get_exceptions_returns_empty_list_when_none_configured(self):
        res = self.client.get("/admin/availability/exceptions", cookies=TEST_SESSION_COOKIE)
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIn("exceptions", data)
        self.assertEqual(data["exceptions"], [])

    def test_get_exceptions_returns_configured_exceptions(self):
        self.availability_repo.set_exception(
            "test_practice", self.future_date, "closed", None, None, "Holiday"
        )
        res = self.client.get("/admin/availability/exceptions", cookies=TEST_SESSION_COOKIE)
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(len(data["exceptions"]), 1)
        self.assertEqual(
            data["exceptions"][0]["exception_date"], self.future_date.isoformat()
        )

    # ---------------------------------------------------------------------------
    # PUT /availability/exceptions/{date}
    # ---------------------------------------------------------------------------

    def test_put_exception_creates_closed_exception(self):
        date_str = self.future_date.isoformat()
        body = {
            "exception_type": "closed",
            "open_time": None,
            "close_time": None,
            "note": "Bank holiday",
        }
        res = self.client.put(
            f"/admin/availability/exceptions/{date_str}",
            json=body,
            cookies=TEST_SESSION_COOKIE,
        )
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["exception_date"], date_str)
        self.assertEqual(data["exception_type"], "closed")
        self.assertIsNone(data["open_time"])
        self.assertEqual(data["note"], "Bank holiday")

    def test_put_exception_creates_custom_hours_exception(self):
        date_str = self.future_date.isoformat()
        body = {
            "exception_type": "custom_hours",
            "open_time": "09:00",
            "close_time": "12:00",
            "note": "Half day",
        }
        res = self.client.put(
            f"/admin/availability/exceptions/{date_str}",
            json=body,
            cookies=TEST_SESSION_COOKIE,
        )
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["exception_type"], "custom_hours")
        self.assertEqual(data["open_time"], "09:00")
        self.assertEqual(data["close_time"], "12:00")

    def test_put_exception_updates_existing_exception(self):
        # Create initially as closed.
        self.availability_repo.set_exception(
            "test_practice", self.future_date, "closed", None, None, "Original"
        )
        date_str = self.future_date.isoformat()
        body = {
            "exception_type": "custom_hours",
            "open_time": "10:00",
            "close_time": "14:00",
            "note": "Updated",
        }
        res = self.client.put(
            f"/admin/availability/exceptions/{date_str}",
            json=body,
            cookies=TEST_SESSION_COOKIE,
        )
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["exception_type"], "custom_hours")
        self.assertEqual(data["note"], "Updated")

    def test_put_exception_custom_hours_missing_times_returns_422(self):
        # custom_hours requires both open_time and close_time.
        date_str = self.future_date.isoformat()
        body = {
            "exception_type": "custom_hours",
            "open_time": None,
            "close_time": None,
            "note": None,
        }
        res = self.client.put(
            f"/admin/availability/exceptions/{date_str}",
            json=body,
            cookies=TEST_SESSION_COOKIE,
        )
        self.assertEqual(res.status_code, 422)

    def test_put_exception_closed_with_times_returns_422(self):
        # closed type must not have open_time or close_time.
        date_str = self.future_date.isoformat()
        body = {
            "exception_type": "closed",
            "open_time": "09:00",
            "close_time": "12:00",
            "note": None,
        }
        res = self.client.put(
            f"/admin/availability/exceptions/{date_str}",
            json=body,
            cookies=TEST_SESSION_COOKIE,
        )
        self.assertEqual(res.status_code, 422)

    def test_put_exception_invalid_date_format_returns_422(self):
        body = {
            "exception_type": "closed",
            "open_time": None,
            "close_time": None,
            "note": None,
        }
        res = self.client.put(
            "/admin/availability/exceptions/not-a-date",
            json=body,
            cookies=TEST_SESSION_COOKIE,
        )
        self.assertEqual(res.status_code, 422)

    def test_put_exception_invalid_exception_type_returns_422(self):
        date_str = self.future_date.isoformat()
        body = {
            "exception_type": "half_day",  # not a valid type
            "open_time": None,
            "close_time": None,
            "note": None,
        }
        res = self.client.put(
            f"/admin/availability/exceptions/{date_str}",
            json=body,
            cookies=TEST_SESSION_COOKIE,
        )
        self.assertEqual(res.status_code, 422)

    # ---------------------------------------------------------------------------
    # DELETE /availability/exceptions/{date}
    # ---------------------------------------------------------------------------

    def test_delete_exception_removes_exception(self):
        self.availability_repo.set_exception(
            "test_practice", self.future_date, "closed", None, None, "Holiday"
        )
        date_str = self.future_date.isoformat()
        res = self.client.delete(
            f"/admin/availability/exceptions/{date_str}", cookies=TEST_SESSION_COOKIE
        )
        self.assertEqual(res.status_code, 204)
        self.assertIsNone(
            self.availability_repo.get_exception("test_practice", self.future_date)
        )

    def test_delete_exception_idempotent_when_no_exception_exists(self):
        date_str = self.future_date.isoformat()
        res = self.client.delete(
            f"/admin/availability/exceptions/{date_str}", cookies=TEST_SESSION_COOKIE
        )
        self.assertEqual(res.status_code, 204)

    def test_delete_exception_invalid_date_format_returns_422(self):
        res = self.client.delete(
            "/admin/availability/exceptions/not-a-date", cookies=TEST_SESSION_COOKIE
        )
        self.assertEqual(res.status_code, 422)


if __name__ == "__main__":
    unittest.main(verbosity=2)
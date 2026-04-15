"""
Tests for admin_availability_router.py.

Exercises the availability configuration, overrides, and exceptions endpoints.
Relies on DEV_MODE=1 bearer token fallback for authentication.
"""

import os
import unittest
import datetime
from datetime import timezone
from unittest.mock import patch

from fastapi.testclient import TestClient

from tests.helpers.admin_test_helpers import make_test_app, dummy_conn

VALID_AUTH = {"Authorization": "Bearer testtoken"}   

class TestAdminAvailabilityRouter(unittest.TestCase):
    def setUp(self):
        os.environ["DEV_MODE"] = "1"
        os.environ.pop("ADMIN_TOKEN", None)
        
        self._conn_patcher = patch(
            "app.routers.admin.admin_availability_router.get_conn", dummy_conn
        )
        self._conn_patcher.start()
        
        self.app = make_test_app()
        # Grab the reference created by the helper
        self.availability_repo = self.app.state.availability_repo
        
        self.client = TestClient(self.app, raise_server_exceptions=True)

    def tearDown(self):
        self._conn_patcher.stop()
        os.environ.pop("DEV_MODE", None)

    # ---------------------------------------------------------------------------
    # GET /availability
    # ---------------------------------------------------------------------------

    def test_get_availability_returns_formatted_config(self):
        res = self.client.get("/admin/availability", headers=VALID_AUTH)
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["is_active"], True)
        self.assertEqual(data["open_time"], "08:00")
        self.assertEqual(data["close_time"], "18:30")
        self.assertIsNone(data["override_status"])

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
        res = self.client.put("/admin/availability", json=body, headers=VALID_AUTH)
        self.assertEqual(res.status_code, 200)
        
        data = res.json()
        self.assertEqual(data["weekly_open_days"], ["mon", "wed", "fri"])
        self.assertEqual(data["open_time"], "09:00")
        self.assertEqual(data["closed_message"], "Closed for lunch")

    def test_put_availability_auto_clears_override_when_deactivated(self):
        # Set an override first
        self.availability_repo.set_override("test_practice", "open", self.tomorrow, "test override")
        
        # Deactivate practice
        body = {
            "is_active": False,
            "weekly_open_days": ["mon"],
            "open_time": "08:00",
            "close_time": "18:00",
            "closed_message": None,
        }
        res = self.client.put("/admin/availability", json=body, headers=VALID_AUTH)
        self.assertEqual(res.status_code, 200)
        
        data = res.json()
        self.assertFalse(data["is_active"])
        self.assertIsNone(data["override_status"])
        self.assertIsNone(data["override_expires_at"])

    def test_put_availability_invalid_time_format_returns_422(self):
        body = {
            "is_active": True,
            "weekly_open_days": ["mon"],
            "open_time": "9 AM", # Invalid format
            "close_time": "18:00",
            "closed_message": None,
        }
        res = self.client.put("/admin/availability", json=body, headers=VALID_AUTH)
        self.assertEqual(res.status_code, 422)

    # ---------------------------------------------------------------------------
    # POST /availability/override
    # ---------------------------------------------------------------------------

    def test_post_override_sets_override_with_timezone_aware_datetime(self):
        expires_at = self.tomorrow.isoformat()
        body = {
            "status": "closed",
            "expires_at": expires_at,
            "message": "Emergency closure"
        }
        res = self.client.post("/admin/availability/override", json=body, headers=VALID_AUTH)
        self.assertEqual(res.status_code, 200)
        
        data = res.json()
        self.assertEqual(data["override_status"], "closed")
        self.assertEqual(data["override_expires_at"], expires_at)
        self.assertEqual(data["override_message"], "Emergency closure")

    def test_post_override_rejects_timezone_naive_datetime_with_422(self):
        # Strip timezone info
        naive_expires_at = self.tomorrow.replace(tzinfo=None).isoformat()
        body = {
            "status": "closed",
            "expires_at": naive_expires_at,
            "message": None
        }
        res = self.client.post("/admin/availability/override", json=body, headers=VALID_AUTH)
        self.assertEqual(res.status_code, 422)
        self.assertIn("timezone offset", res.json()["error"]["message"])

    def test_post_override_invalid_status_returns_422(self):
        body = {
            "status": "maybe_open",
            "expires_at": self.tomorrow.isoformat(),
            "message": None
        }
        # Assuming validate_override in the service throws ValueError on invalid status
        res = self.client.post("/admin/availability/override", json=body, headers=VALID_AUTH)
        self.assertEqual(res.status_code, 422)

    # ---------------------------------------------------------------------------
    # DELETE /availability/override
    # ---------------------------------------------------------------------------

    def test_delete_override_clears_override(self):
        self.availability_repo.set_override("test_practice", "closed", self.tomorrow, "test")
        
        res = self.client.delete("/admin/availability/override", headers=VALID_AUTH)
        self.assertEqual(res.status_code, 200)
        
        data = res.json()
        self.assertIsNone(data["override_status"])
        self.assertIsNone(data["override_expires_at"])

    # ---------------------------------------------------------------------------
    # Exceptions (GET, PUT, DELETE)
    # ---------------------------------------------------------------------------

    def test_put_exception_creates_closed_exception(self):
        date_str = self.tomorrow.date().isoformat()
        body = {
            "exception_type": "closed",
            "open_time": None,
            "close_time": None,
            "note": "Bank holiday"
        }
        res = self.client.put(f"/admin/availability/exceptions/{date_str}", json=body, headers=VALID_AUTH)
        self.assertEqual(res.status_code, 200)
        
        data = res.json()
        self.assertEqual(data["exception_date"], date_str)
        self.assertEqual(data["exception_type"], "closed")
        self.assertIsNone(data["open_time"])
        self.assertEqual(data["note"], "Bank holiday")

    def test_put_exception_creates_custom_hours_exception(self):
        date_str = self.tomorrow.date().isoformat()
        body = {
            "exception_type": "custom_hours",
            "open_time": "09:00",
            "close_time": "12:00",
            "note": "Half day"
        }
        res = self.client.put(f"/admin/availability/exceptions/{date_str}", json=body, headers=VALID_AUTH)
        self.assertEqual(res.status_code, 200)
        
        data = res.json()
        self.assertEqual(data["exception_date"], date_str)
        self.assertEqual(data["exception_type"], "custom_hours")
        self.assertEqual(data["open_time"], "09:00")
        self.assertEqual(data["close_time"], "12:00")

    def test_put_exception_invalid_date_format_returns_422(self):
        body = {
            "exception_type": "closed",
            "open_time": None,
            "close_time": None,
            "note": None
        }
        res = self.client.put("/admin/availability/exceptions/not-a-date", json=body, headers=VALID_AUTH)
        self.assertEqual(res.status_code, 422)

    def test_get_exceptions_returns_list_of_exceptions(self):
        date_str = self.tomorrow.date().isoformat()
        self.availability_repo.set_exception(
            "test_practice", self.tomorrow.date(), "closed", None, None, "Holiday"
        )
        
        res = self.client.get("/admin/availability/exceptions", headers=VALID_AUTH)
        self.assertEqual(res.status_code, 200)
        
        data = res.json()
        self.assertIn("exceptions", data)
        self.assertEqual(len(data["exceptions"]), 1)
        self.assertEqual(data["exceptions"][0]["exception_date"], date_str)

    def test_delete_exception_removes_exception(self):
        exc_date = self.tomorrow.date()
        date_str = exc_date.isoformat()
        self.availability_repo.set_exception(
            "test_practice", exc_date, "closed", None, None, "Holiday"
        )
        
        res = self.client.delete(f"/admin/availability/exceptions/{date_str}", headers=VALID_AUTH)
        self.assertEqual(res.status_code, 204)
        
        # Verify it was removed
        self.assertIsNone(self.availability_repo.get_exception("test_practice", exc_date))

if __name__ == "__main__":
    unittest.main(verbosity=2)

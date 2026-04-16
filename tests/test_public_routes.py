"""
Integration tests for public (unauthenticated) HTTP endpoints.

REQUIRES: A running Postgres database with DATABASE_URL set in the environment,
the schema migrated, and at least one practice and one condition seeded.

These tests use FastAPI's TestClient against the real application stack.
They are not mocked — they test the full path from HTTP to database.
"""

import os
import pytest
from pathlib import Path
from fastapi.testclient import TestClient

# ---------------------------------------------------------------------------
# Load .env before the skip guard runs.
# conftest.py loads too late (after module-level skip checks fire), so we
# load dotenv here explicitly. override=False means already-set env vars win.
# ---------------------------------------------------------------------------
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent.parent / ".env", override=False)
except ImportError:
    pass

# ---------------------------------------------------------------------------
# Skip all tests in this module if no database is configured.
# This prevents CI failures on machines without a database.
# ---------------------------------------------------------------------------
if not os.environ.get("DATABASE_URL"):
    pytest.skip(
        "DATABASE_URL not set — skipping integration tests",
        allow_module_level=True,
    )

from main import app  # noqa: E402 — import after skip guard

pytestmark = pytest.mark.integration

client = TestClient(app, raise_server_exceptions=True)

# ---------------------------------------------------------------------------
# GET /conditions
# ---------------------------------------------------------------------------

def test_list_conditions_returns_200():
    response = client.get("/conditions")
    assert response.status_code == 200

def test_list_conditions_returns_conditions_list():
    response = client.get("/conditions")
    body = response.json()
    assert "conditions" in body
    assert isinstance(body["conditions"], list)
    assert len(body["conditions"]) > 0

def test_list_conditions_items_have_expected_keys():
    response = client.get("/conditions")
    first = response.json()["conditions"][0]
    assert "id" in first
    assert "label" in first

# ---------------------------------------------------------------------------
# GET /conditions/{condition_id}/presentation
# ---------------------------------------------------------------------------

def _get_first_condition_id() -> str:
    response = client.get("/conditions")
    return response.json()["conditions"][0]["id"]

def test_get_presentation_known_condition_returns_200():
    condition_id = _get_first_condition_id()
    response = client.get(f"/conditions/{condition_id}/presentation")
    assert response.status_code == 200

def test_get_presentation_known_condition_has_expected_keys():
    condition_id = _get_first_condition_id()
    response = client.get(f"/conditions/{condition_id}/presentation")
    body = response.json()
    assert "label" in body
    assert "free_text_prompt" in body
    assert "universal_safety_warning" in body
    assert "practice_signposting" in body

def test_get_presentation_unknown_condition_returns_404():
    response = client.get("/conditions/nonexistent_condition_xyz/presentation")
    assert response.status_code == 404

def test_get_presentation_unknown_condition_has_error_body():
    response = client.get("/conditions/nonexistent_condition_xyz/presentation")
    body = response.json()
    assert "error" in body
    assert body["error"]["code"] == "CONDITION_NOT_FOUND"

# ---------------------------------------------------------------------------
# GET /availability
# ---------------------------------------------------------------------------

def test_get_availability_returns_200():
    response = client.get("/availability")
    assert response.status_code == 200

def test_get_availability_has_expected_keys():
    response = client.get("/availability")
    body = response.json()
    assert "is_open" in body
    assert "closed_message" in body
    assert "after_hours_notice" in body

def test_get_availability_is_open_is_bool():
    response = client.get("/availability")
    body = response.json()
    assert isinstance(body["is_open"], bool)

# ---------------------------------------------------------------------------
# GET /safety-warning
# ---------------------------------------------------------------------------

def test_get_safety_warning_returns_200():
    response = client.get("/safety-warning")
    assert response.status_code == 200

def test_get_safety_warning_has_expected_key():
    response = client.get("/safety-warning")
    body = response.json()
    assert "universal_safety_warning" in body

def test_get_safety_warning_is_non_empty_string():
    response = client.get("/safety-warning")
    body = response.json()
    assert isinstance(body["universal_safety_warning"], str)
    assert len(body["universal_safety_warning"]) > 0

# ---------------------------------------------------------------------------
# GET /doctors
# ---------------------------------------------------------------------------

def test_get_doctors_returns_200():
    response = client.get("/doctors")
    assert response.status_code == 200

def test_get_doctors_returns_doctors_key():
    response = client.get("/doctors")
    body = response.json()
    assert "doctors" in body

def test_get_doctors_value_is_a_list():
    response = client.get("/doctors")
    body = response.json()
    assert isinstance(body["doctors"], list)

def test_get_doctors_items_are_strings_when_list_is_non_empty():
    # Only asserts type if the list is non-empty.
    # An empty list is a valid response when no doctors are configured.
    response = client.get("/doctors")
    doctors = response.json()["doctors"]
    for item in doctors:
        assert isinstance(item, str), f"Expected string, got {type(item)}: {item}"

def test_get_doctors_requires_no_authentication():
    # Confirm the endpoint is genuinely unauthenticated — no Authorization header.
    response = client.get("/doctors")
    assert response.status_code == 200
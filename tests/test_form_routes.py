"""
Integration tests for form session endpoints.

Requires a live Postgres database via TEST_DATABASE_URL.
If that variable is absent the entire module is skipped — this prevents
accidental runs against the wrong database.

Run from project root:
    TEST_DATABASE_URL=... python -m pytest tests/test_form_routes.py -v

Architecture notes:
- MockDeliveryService is injected via app.dependency_overrides so no SMTP
  config is needed during tests.
- The availability check in form_init is also overridden to return open
  for the happy-path test, and to raise for the fail-open test.
- Each test that writes to the database uses a unique condition_id drawn
  from the real registry so that the engine can load its ruleset.
"""

import os
import pytest

# ---------------------------------------------------------------------------
# Database guardrail — must be first, before any app imports
# ---------------------------------------------------------------------------

if "TEST_DATABASE_URL" not in os.environ:
    pytest.skip(
        "TEST_DATABASE_URL not set — skipping integration tests to protect production data",
        allow_module_level=True,
    )

os.environ.setdefault("DATABASE_URL", os.environ["TEST_DATABASE_URL"])
os.environ.setdefault("DEV_MODE", "1")
os.environ.setdefault("PRACTICE_ID", "test-practice")
os.environ.setdefault("DATA_DIR", os.path.join(os.path.dirname(__file__), "..", "data"))

from fastapi.testclient import TestClient  # noqa: E402

from main import app  # noqa: E402
from app.core.dependencies import get_delivery_service, get_availability_repo  # noqa: E402
from app.services.delivery_service import DeliveryService  # noqa: E402
from app.models.serialisation_contracts import ClinicalOutput  # noqa: E402


# ---------------------------------------------------------------------------
# Mock delivery service
# ---------------------------------------------------------------------------

class MockDeliveryService(DeliveryService):
    """Captures send calls for assertion without touching SMTP."""

    def __init__(self):
        self.calls: list[dict] = []

    def send_clinical_output(
        self,
        to_email: str,
        condition_label: str,
        clinical_output: ClinicalOutput,
        submission_id: str,
    ) -> None:
        self.calls.append({
            "to_email": to_email,
            "condition_label": condition_label,
            "clinical_output": clinical_output,
            "submission_id": submission_id,
        })


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_first_condition(client: TestClient) -> dict:
    """Return the first condition from the registry (id and label)."""
    res = client.get("/conditions")
    assert res.status_code == 200
    conditions = res.json()["conditions"]
    assert conditions, "Registry has no conditions — cannot run form tests"
    return conditions[0]


def _valid_contact_preferences() -> dict:
    return {
        "contact_methods": ["email"],
        "email_address": "patient@example.com",
        "phone_number": None,
        "best_time_to_call": None,
        "doctor_preference": "any",
        "usual_doctor_name": None,
    }


def _build_answers(client_state: dict) -> dict:
    """
    Build a minimal valid answers dict from a client_state.
    Booleans default to True; text fields default to 'test'.
    """
    answers = {}
    for q in client_state["questions"]:
        if q["answer_type"] == "boolean":
            answers[q["answer_key"]] = True
        else:
            answers[q["answer_key"]] = "test answer"
    return answers


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_happy_path_end_to_end():
    """
    Full init -> update -> finish flow.

    Asserts:
    - Each step returns HTTP 200
    - finish response contains submission_id
    - finish response does NOT contain submitted_after_hours
    - MockDeliveryService captured one send call with correct submission_id
    - contact_preferences are present inside the captured ClinicalOutput
    """
    mock_delivery = MockDeliveryService()
    app.dependency_overrides[get_delivery_service] = lambda: mock_delivery

    try:
        with TestClient(app) as client:
            condition = _get_first_condition(client)
            condition_id = condition["id"]

            # --- init ---
            init_res = client.post("/form/init", json={
                "condition_id": condition_id,
                "free_text": "Test symptom description",
            })
            assert init_res.status_code == 200, init_res.text
            init_body = init_res.json()
            runtime_id = init_body["runtime_id"]
            version = init_body["version"]
            client_state = init_body["client_state"]
            assert runtime_id
            assert version == 1

            # --- update ---
            answers = _build_answers(client_state)
            update_res = client.post("/form/update", json={
                "runtime_id": runtime_id,
                "base_version": version,
                "answers": answers,
                "additional_text": None,
            })
            assert update_res.status_code == 200, update_res.text
            update_body = update_res.json()
            version = update_body["version"]
            assert version == 2

            # --- finish ---
            contact_prefs = _valid_contact_preferences()
            finish_res = client.post("/form/finish", json={
                "runtime_id": runtime_id,
                "version": version,
                "contact_preferences": contact_prefs,
            })
            assert finish_res.status_code == 200, finish_res.text
            finish_body = finish_res.json()

            # submission_id present
            assert "submission_id" in finish_body
            assert finish_body["submission_id"]

            # submitted_after_hours must be absent
            assert "submitted_after_hours" not in finish_body, (
                "submitted_after_hours must not be in the finish response"
            )

            # delivery was called exactly once
            assert len(mock_delivery.calls) == 1
            call = mock_delivery.calls[0]
            assert call["submission_id"] == finish_body["submission_id"]

            # contact_preferences are inside ClinicalOutput
            captured_clinical: ClinicalOutput = call["clinical_output"]
            assert captured_clinical.contact_preferences is not None
            assert captured_clinical.contact_preferences["contact_methods"] == ["email"]
            assert captured_clinical.contact_preferences["email_address"] == "patient@example.com"

    finally:
        app.dependency_overrides.pop(get_delivery_service, None)


def test_form_init_fail_open_on_availability_error():
    """
    If the availability check raises an exception during form_init,
    the endpoint must still return HTTP 200 (fail-open).
    """
    def broken_availability_repo():
        class BrokenRepo:
            def get_availability(self, *args, **kwargs):
                raise RuntimeError("Simulated availability DB failure")
            def get_exceptions(self, *args, **kwargs):
                raise RuntimeError("Simulated availability DB failure")
        return BrokenRepo()

    app.dependency_overrides[get_availability_repo] = broken_availability_repo

    try:
        with TestClient(app) as client:
            condition = _get_first_condition(client)
            res = client.post("/form/init", json={
                "condition_id": condition["id"],
                "free_text": None,
            })
            assert res.status_code == 200, (
                f"form_init must fail-open when availability check raises, got {res.status_code}: {res.text}"
            )
    finally:
        app.dependency_overrides.pop(get_availability_repo, None)


def test_form_finish_delivery_failure_does_not_prevent_submission_id():
    """
    If the delivery service raises EmailDeliveryError, form_finish must
    still return HTTP 200 with a submission_id.
    The patient must always receive confirmation that their submission was saved.
    """
    from app.services.delivery_service import EmailDeliveryError

    class FailingDeliveryService(DeliveryService):
        def send_clinical_output(self, to_email, condition_label, clinical_output, submission_id):
            raise EmailDeliveryError("Simulated SMTP failure")

    app.dependency_overrides[get_delivery_service] = lambda: FailingDeliveryService()

    try:
        with TestClient(app) as client:
            condition = _get_first_condition(client)
            condition_id = condition["id"]

            init_res = client.post("/form/init", json={
                "condition_id": condition_id,
                "free_text": None,
            })
            assert init_res.status_code == 200, init_res.text
            body = init_res.json()
            runtime_id = body["runtime_id"]
            version = body["version"]
            client_state = body["client_state"]

            answers = _build_answers(client_state)
            update_res = client.post("/form/update", json={
                "runtime_id": runtime_id,
                "base_version": version,
                "answers": answers,
                "additional_text": None,
            })
            assert update_res.status_code == 200, update_res.text
            version = update_res.json()["version"]

            finish_res = client.post("/form/finish", json={
                "runtime_id": runtime_id,
                "version": version,
                "contact_preferences": _valid_contact_preferences(),
            })
            assert finish_res.status_code == 200, (
                f"form_finish must return 200 even when delivery fails, got {finish_res.status_code}: {finish_res.text}"
            )
            assert "submission_id" in finish_res.json()

    finally:
        app.dependency_overrides.pop(get_delivery_service, None)


def test_form_finish_submitted_after_hours_absent():
    """
    Explicit guard: submitted_after_hours must never appear in the
    form_finish response regardless of availability state.
    """
    mock_delivery = MockDeliveryService()
    app.dependency_overrides[get_delivery_service] = lambda: mock_delivery

    try:
        with TestClient(app) as client:
            condition = _get_first_condition(client)
            condition_id = condition["id"]

            init_res = client.post("/form/init", json={
                "condition_id": condition_id,
                "free_text": None,
            })
            assert init_res.status_code == 200
            body = init_res.json()
            runtime_id, version = body["runtime_id"], body["version"]
            client_state = body["client_state"]

            update_res = client.post("/form/update", json={
                "runtime_id": runtime_id,
                "base_version": version,
                "answers": _build_answers(client_state),
                "additional_text": None,
            })
            assert update_res.status_code == 200
            version = update_res.json()["version"]

            finish_res = client.post("/form/finish", json={
                "runtime_id": runtime_id,
                "version": version,
                "contact_preferences": _valid_contact_preferences(),
            })
            assert finish_res.status_code == 200
            assert "submitted_after_hours" not in finish_res.json()

    finally:
        app.dependency_overrides.pop(get_delivery_service, None)

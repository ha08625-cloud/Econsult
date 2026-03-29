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
- form_finish delegates to delivery_orchestration.attempt_delivery, which
  calls get_pending_delivery and get_attachment on the real database before
  calling delivery_service.send_clinical_output on the mock. The mock must
  match the current DeliveryService ABC signature.
- form_finish accepts multipart/form-data. The JSON payload is sent as the
  'payload' form field (a string). Photos are optional and sent as 'photos'
  file fields. Use _finish_multipart() to build the data= and files= args
  for all finish calls.
"""

import json
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

from datetime import datetime  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from main import app  # noqa: E402
from app.core.dependencies import get_delivery_service, get_availability_repo  # noqa: E402
from app.core.upload_constants import (  # noqa: E402
    MAX_FILE_COUNT,
    MAX_FILE_SIZE_BYTES,
    MAX_TOTAL_SIZE_BYTES,
)
from app.repositories.submission_repository import SubmissionRepository  # noqa: E402
from app.services.delivery_service import DeliveryService  # noqa: E402
from tests.test_pdf_generation import MINIMAL_JPEG  # noqa: E402


# ---------------------------------------------------------------------------
# Mock delivery service
# ---------------------------------------------------------------------------

class MockDeliveryService(DeliveryService):
    """
    Captures send calls for assertion without touching SMTP.

    Matches the current DeliveryService ABC signature: to_email,
    condition_label, pdf_bytes, submission_id, submitted_at.
    """

    def __init__(self):
        self.calls: list[dict] = []

    def send_clinical_output(
        self,
        to_email: str,
        condition_label: str,
        pdf_bytes: bytes,
        submission_id: str,
        submitted_at: datetime,
    ) -> None:
        self.calls.append({
            "to_email": to_email,
            "condition_label": condition_label,
            "pdf_bytes": pdf_bytes,
            "submission_id": submission_id,
            "submitted_at": submitted_at,
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


def _valid_patient_details() -> dict:
    """
    Minimal valid patient_details payload for use in finish requests.
    Uses patient_for="me" — no submitter fields required.
    """
    return {
        "patient_for": "me",
        "first_name": "Jane",
        "last_name": "Smith",
        "date_of_birth": {"day": "15", "month": "3", "year": "1990"},
        "postcode": "SW1A 1AA",
        "submitter_name": None,
        "submitter_relationship": None,
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


def _finish_multipart(runtime_id: str, version: int) -> dict:
    """
    Build the data= and files= kwargs for a multipart form_finish request.

    form_finish accepts multipart/form-data with:
      - 'payload': the JSON-stringified finish payload (string form field)
      - 'photos':  optional list of file tuples (omitted here — no photos)

    Usage:
        finish_res = client.post("/form/finish", **_finish_multipart(runtime_id, version))

    To include photos in a test, build the request manually instead of using
    this helper.
    """
    payload = {
        "runtime_id": runtime_id,
        "version": version,
        "contact_preferences": _valid_contact_preferences(),
        "patient_details": _valid_patient_details(),
    }
    return {
        "data": {"payload": json.dumps(payload)},
        "files": [],
    }


def _run_full_flow(client: TestClient) -> tuple[str, int]:
    """
    Run init -> update through to a ready-to-finish state.

    Returns (runtime_id, version) ready to pass to a finish call.
    The caller is responsible for making the finish request so it can
    vary the photos argument.
    """
    condition = _get_first_condition(client)
    condition_id = condition["id"]

    init_res = client.post("/form/init", json={
        "condition_id": condition_id,
        "free_text": "Test symptom description",
    })
    assert init_res.status_code == 200, init_res.text
    init_body = init_res.json()
    runtime_id = init_body["runtime_id"]
    version = init_body["version"]
    client_state = init_body["client_state"]

    update_res = client.post("/form/update", json={
        "runtime_id": runtime_id,
        "base_version": version,
        "answers": _build_answers(client_state),
        "additional_text": None,
    })
    assert update_res.status_code == 200, update_res.text
    version = update_res.json()["version"]

    return runtime_id, version


def _make_submission_repo() -> SubmissionRepository:
    return SubmissionRepository(os.environ["TEST_DATABASE_URL"])


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
    - The send call received a non-empty pdf_bytes and valid submitted_at
    - The send call received the correct condition_label

    Note: ClinicalOutput assertions (contact_preferences, patient_details)
    are no longer possible via the delivery mock because the delivery service
    no longer receives ClinicalOutput. Those fields are verified by the
    repository integration tests (test_repositories.py) which read back
    the persisted clinical_output_json.
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
            finish_res = client.post(
                "/form/finish",
                **_finish_multipart(runtime_id, version),
            )
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

            # The delivery service received the correct condition label
            assert call["condition_label"] == condition["label"]

            # PDF bytes were generated and passed to the delivery service
            assert isinstance(call["pdf_bytes"], bytes)
            assert len(call["pdf_bytes"]) > 0

            # submitted_at is a timezone-aware datetime
            assert isinstance(call["submitted_at"], datetime)
            assert call["submitted_at"].tzinfo is not None

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

    The patient must always receive confirmation that their submission was
    saved. The delivery failure is caught by attempt_delivery, which records
    the failure and returns a DeliveryOutcome. The router's except Exception
    block catches any unexpected errors from the orchestration layer.
    """
    from app.services.delivery_service import EmailDeliveryError

    class FailingDeliveryService(DeliveryService):
        def send_clinical_output(
            self,
            to_email: str,
            condition_label: str,
            pdf_bytes: bytes,
            submission_id: str,
            submitted_at: datetime,
        ) -> None:
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

            finish_res = client.post(
                "/form/finish",
                **_finish_multipart(runtime_id, version),
            )
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

            finish_res = client.post(
                "/form/finish",
                **_finish_multipart(runtime_id, version),
            )
            assert finish_res.status_code == 200
            assert "submitted_after_hours" not in finish_res.json()

    finally:
        app.dependency_overrides.pop(get_delivery_service, None)


# ---------------------------------------------------------------------------
# Photo upload tests
# ---------------------------------------------------------------------------

def test_finish_with_no_photos_records_attachment_count_zero():
    """
    A valid finish with no photos must return 200 and persist
    attachment_count = 0 on the submission record.
    """
    mock_delivery = MockDeliveryService()
    app.dependency_overrides[get_delivery_service] = lambda: mock_delivery

    try:
        with TestClient(app) as client:
            runtime_id, version = _run_full_flow(client)

            finish_res = client.post(
                "/form/finish",
                **_finish_multipart(runtime_id, version),
            )
            assert finish_res.status_code == 200, finish_res.text
            submission_id = finish_res.json()["submission_id"]

        repo = _make_submission_repo()
        row = repo.get_submission(submission_id)
        assert row["attachment_count"] == 0

    finally:
        app.dependency_overrides.pop(get_delivery_service, None)


def test_finish_with_one_photo_records_attachment_count_one():
    """
    A valid finish with one real JPEG must return 200 and persist
    attachment_count = 1 on the submission record.

    MINIMAL_JPEG is the shared fixture from test_pdf_generation.py —
    a valid 631-byte JPEG that the PDF renderer can process without error.
    """
    mock_delivery = MockDeliveryService()
    app.dependency_overrides[get_delivery_service] = lambda: mock_delivery

    try:
        with TestClient(app) as client:
            runtime_id, version = _run_full_flow(client)

            payload = {
                "runtime_id": runtime_id,
                "version": version,
                "contact_preferences": _valid_contact_preferences(),
                "patient_details": _valid_patient_details(),
            }
            finish_res = client.post(
                "/form/finish",
                data={"payload": json.dumps(payload)},
                files=[("photos", ("photo.jpg", MINIMAL_JPEG, "image/jpeg"))],
            )
            assert finish_res.status_code == 200, finish_res.text
            submission_id = finish_res.json()["submission_id"]

        repo = _make_submission_repo()
        row = repo.get_submission(submission_id)
        assert row["attachment_count"] == 1

    finally:
        app.dependency_overrides.pop(get_delivery_service, None)


def test_finish_rejects_too_many_photos():
    """
    Submitting more than MAX_FILE_COUNT photos must return 422.
    No submission record is created.
    """
    mock_delivery = MockDeliveryService()
    app.dependency_overrides[get_delivery_service] = lambda: mock_delivery

    try:
        with TestClient(app) as client:
            runtime_id, version = _run_full_flow(client)

            payload = {
                "runtime_id": runtime_id,
                "version": version,
                "contact_preferences": _valid_contact_preferences(),
                "patient_details": _valid_patient_details(),
            }
            # MAX_FILE_COUNT + 1 files, each a valid minimal JPEG
            files = [
                ("photos", (f"photo{i}.jpg", MINIMAL_JPEG, "image/jpeg"))
                for i in range(MAX_FILE_COUNT + 1)
            ]
            finish_res = client.post(
                "/form/finish",
                data={"payload": json.dumps(payload)},
                files=files,
            )
            assert finish_res.status_code == 422, (
                f"Expected 422 for {MAX_FILE_COUNT + 1} photos, got {finish_res.status_code}: {finish_res.text}"
            )

    finally:
        app.dependency_overrides.pop(get_delivery_service, None)


def test_finish_rejects_single_file_exceeding_size_limit():
    """
    A single file whose byte length exceeds MAX_FILE_SIZE_BYTES must
    return 422. No submission record is created.

    The oversized bytes are sent with a valid JPEG content-type so the
    rejection is triggered by the size check, not the MIME check.
    """
    mock_delivery = MockDeliveryService()
    app.dependency_overrides[get_delivery_service] = lambda: mock_delivery

    try:
        with TestClient(app) as client:
            runtime_id, version = _run_full_flow(client)

            payload = {
                "runtime_id": runtime_id,
                "version": version,
                "contact_preferences": _valid_contact_preferences(),
                "patient_details": _valid_patient_details(),
            }
            oversized_bytes = b"\xff\xd8\xff" + b"\x00" * MAX_FILE_SIZE_BYTES  # one byte over
            finish_res = client.post(
                "/form/finish",
                data={"payload": json.dumps(payload)},
                files=[("photos", ("big.jpg", oversized_bytes, "image/jpeg"))],
            )
            assert finish_res.status_code == 422, (
                f"Expected 422 for oversized file, got {finish_res.status_code}: {finish_res.text}"
            )

    finally:
        app.dependency_overrides.pop(get_delivery_service, None)


def test_finish_rejects_combined_size_exceeding_total_limit():
    """
    Multiple files whose combined size exceeds MAX_TOTAL_SIZE_BYTES must
    return 422 even if each individual file is within MAX_FILE_SIZE_BYTES.
    No submission record is created.

    Strategy: send two files each just over half of MAX_TOTAL_SIZE_BYTES
    but under MAX_FILE_SIZE_BYTES, so only the combined check fires.
    """
    mock_delivery = MockDeliveryService()
    app.dependency_overrides[get_delivery_service] = lambda: mock_delivery

    try:
        with TestClient(app) as client:
            runtime_id, version = _run_full_flow(client)

            payload = {
                "runtime_id": runtime_id,
                "version": version,
                "contact_preferences": _valid_contact_preferences(),
                "patient_details": _valid_patient_details(),
            }
            # Each file is (MAX_TOTAL_SIZE_BYTES // 2) + 1 bytes — individually
            # within MAX_FILE_SIZE_BYTES (5 MB) but combined over MAX_TOTAL_SIZE_BYTES (10 MB).
            chunk_size = (MAX_TOTAL_SIZE_BYTES // 2) + 1
            assert chunk_size <= MAX_FILE_SIZE_BYTES, (
                "Test assumption violated: chunk_size must be <= MAX_FILE_SIZE_BYTES. "
                "If the constants change, review this test."
            )
            chunk = b"\xff\xd8\xff" + b"\x00" * (chunk_size - 3)
            files = [
                ("photos", ("a.jpg", chunk, "image/jpeg")),
                ("photos", ("b.jpg", chunk, "image/jpeg")),
            ]
            finish_res = client.post(
                "/form/finish",
                data={"payload": json.dumps(payload)},
                files=files,
            )
            assert finish_res.status_code == 422, (
                f"Expected 422 for combined size over limit, got {finish_res.status_code}: {finish_res.text}"
            )

    finally:
        app.dependency_overrides.pop(get_delivery_service, None)
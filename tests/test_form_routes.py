"""
Integration tests for form session endpoints.

Requires a live Postgres database via TEST_DATABASE_URL.
If that variable is absent the entire module is skipped — this prevents
accidental runs against the wrong database.

Run from project root:
    TEST_DATABASE_URL=... python -m pytest tests/test_form_routes.py -v

Architecture notes:
- form_finish no longer calls the delivery service synchronously. It persists
  the submission and photos, enqueues a pdf_jobs row, and returns immediately.
  MockDeliveryService is retained for tests that inject it via other paths,
  but form_finish tests no longer assert on delivery service calls.
- Tests that previously checked attachment_count on submission_records now
  check pdf_jobs.attachment_count and submission_photos row count instead,
  since those columns were moved in Migration 0013.
- The availability check in form_init is overridden to return open for
  happy-path tests, and to raise for the fail-open test.
- Each test that writes to the database uses a unique condition_id drawn
  from the real registry so that the engine can load its ruleset.
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
from app.core.db import get_conn  # noqa: E402
from app.core.dependencies import get_availability_repo  # noqa: E402
from app.core.upload_constants import (  # noqa: E402
    MAX_FILE_COUNT,
    MAX_FILE_SIZE_BYTES,
    MAX_TOTAL_SIZE_BYTES,
)
from app.services.delivery.delivery_service import DeliveryService  # noqa: E402
from tests.test_pdf_generation import MINIMAL_JPEG  # noqa: E402

DATABASE_URL = os.environ["TEST_DATABASE_URL"]


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
        "consultation_outcome": "not_sure",
    }


def _valid_patient_details() -> dict:
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
    answers = {}
    for q in client_state["questions"]:
        if q["answer_type"] == "boolean":
            answers[q["answer_key"]] = True
        else:
            answers[q["answer_key"]] = "test answer"
    return answers


def _finish_multipart(runtime_id: str, version: int) -> dict:
    """
    Build the data= and files= kwargs for a multipart form_finish request
    with no photos.
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


def _count_pdf_jobs(submission_id: str) -> int:
    with get_conn(DATABASE_URL) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT COUNT(*) FROM pdf_jobs WHERE submission_id = %s",
                (submission_id,),
            )
            return cur.fetchone()[0]


def _read_pdf_job(submission_id: str) -> dict | None:
    with get_conn(DATABASE_URL) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT * FROM pdf_jobs WHERE submission_id = %s",
                (submission_id,),
            )
            row = cur.fetchone()
            if row is None:
                return None
            cols = [desc[0] for desc in cur.description]
    return dict(zip(cols, row))


def _count_submission_photos(submission_id: str) -> int:
    with get_conn(DATABASE_URL) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT COUNT(*) FROM submission_photos WHERE submission_id = %s",
                (submission_id,),
            )
            return cur.fetchone()[0]


# ---------------------------------------------------------------------------
# Core flow tests
# ---------------------------------------------------------------------------

def test_happy_path_end_to_end():
    """
    Full init -> update -> finish flow.

    Asserts:
    - Each step returns HTTP 200.
    - finish response contains submission_id.
    - finish response does NOT contain submitted_after_hours.
    - A pdf_jobs row is created with status = 'pending'.
    - No delivery_jobs row is created (delivery happens asynchronously).
    - No direct delivery call is made by the web request.
    """
    try:
        with TestClient(app) as client:
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
            assert runtime_id
            assert version == 1

            answers = _build_answers(client_state)
            update_res = client.post("/form/update", json={
                "runtime_id": runtime_id,
                "base_version": version,
                "answers": answers,
                "additional_text": None,
            })
            assert update_res.status_code == 200, update_res.text
            version = update_res.json()["version"]
            assert version == 2

            finish_res = client.post(
                "/form/finish",
                **_finish_multipart(runtime_id, version),
            )
            assert finish_res.status_code == 200, finish_res.text
            finish_body = finish_res.json()

            assert "submission_id" in finish_body
            assert finish_body["submission_id"]
            assert "submitted_after_hours" not in finish_body

            submission_id = finish_body["submission_id"]

            # Pipeline state: pdf_jobs row exists, pending.
            assert _count_pdf_jobs(submission_id) == 1
            pdf_job = _read_pdf_job(submission_id)
            assert pdf_job["status"] == "pending"

            # No photos submitted: no submission_photos rows.
            assert _count_submission_photos(submission_id) == 0

            # No delivery_jobs row yet (delivery is async).
            with get_conn(DATABASE_URL) as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "SELECT COUNT(*) FROM delivery_jobs WHERE submission_id = %s",
                        (submission_id,),
                    )
                    delivery_count = cur.fetchone()[0]
            assert delivery_count == 0

    finally:
        pass  # No dependency overrides to clean up.


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
                f"form_init must fail-open when availability check raises, "
                f"got {res.status_code}: {res.text}"
            )
    finally:
        app.dependency_overrides.pop(get_availability_repo, None)


def test_form_finish_always_returns_submission_id():
    """
    form_finish must return HTTP 200 with a submission_id. This test
    verifies the guarantee holds under normal conditions on the new
    pipeline path (no delivery service is invoked synchronously).
    """
    with TestClient(app) as client:
        runtime_id, version = _run_full_flow(client)
        finish_res = client.post("/form/finish", **_finish_multipart(runtime_id, version))
        assert finish_res.status_code == 200, finish_res.text
        assert "submission_id" in finish_res.json()


def test_form_finish_submitted_after_hours_absent():
    """
    submitted_after_hours must never appear in the form_finish response.
    """
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


# ---------------------------------------------------------------------------
# Photo upload tests
# ---------------------------------------------------------------------------

def test_finish_with_no_photos_creates_pdf_job_with_attachment_count_zero():
    """
    A valid finish with no photos must return 200, create a pdf_jobs row
    with attachment_count = 0, and create no submission_photos rows.
    """
    with TestClient(app) as client:
        runtime_id, version = _run_full_flow(client)
        finish_res = client.post("/form/finish", **_finish_multipart(runtime_id, version))
        assert finish_res.status_code == 200, finish_res.text
        submission_id = finish_res.json()["submission_id"]

    pdf_job = _read_pdf_job(submission_id)
    assert pdf_job is not None, "pdf_jobs row must exist after form_finish"
    assert pdf_job["attachment_count"] == 0
    assert _count_submission_photos(submission_id) == 0


def test_finish_with_one_photo_creates_pdf_job_and_photo_row():
    """
    A valid finish with one real JPEG must return 200, create a pdf_jobs
    row with attachment_count = 1, and create one submission_photos row.
    """
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

    pdf_job = _read_pdf_job(submission_id)
    assert pdf_job is not None
    assert pdf_job["attachment_count"] == 1
    assert _count_submission_photos(submission_id) == 1


def test_finish_with_multiple_photos_creates_correct_photo_rows():
    """
    A finish with two photos must persist two submission_photos rows and
    record attachment_count = 2 on the pdf_jobs row.
    """
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
            files=[
                ("photos", ("a.jpg", MINIMAL_JPEG, "image/jpeg")),
                ("photos", ("b.jpg", MINIMAL_JPEG, "image/jpeg")),
            ],
        )
        assert finish_res.status_code == 200, finish_res.text
        submission_id = finish_res.json()["submission_id"]

    pdf_job = _read_pdf_job(submission_id)
    assert pdf_job is not None
    assert pdf_job["attachment_count"] == 2
    assert _count_submission_photos(submission_id) == 2


def test_finish_no_delivery_call_is_made():
    """
    form_finish must not invoke the delivery service synchronously.
    After form_finish, delivery_jobs must have no row for the submission.
    """
    with TestClient(app) as client:
        runtime_id, version = _run_full_flow(client)
        finish_res = client.post("/form/finish", **_finish_multipart(runtime_id, version))
        assert finish_res.status_code == 200, finish_res.text
        submission_id = finish_res.json()["submission_id"]

    with get_conn(DATABASE_URL) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT COUNT(*) FROM delivery_jobs WHERE submission_id = %s",
                (submission_id,),
            )
            count = cur.fetchone()[0]
    assert count == 0, (
        "delivery_jobs must have no row after form_finish — "
        "delivery is enqueued asynchronously by the PDF worker"
    )


def test_finish_rejects_too_many_photos():
    """
    Submitting more than MAX_FILE_COUNT photos must return 422.
    No submission record is created.
    """
    with TestClient(app) as client:
        runtime_id, version = _run_full_flow(client)

        payload = {
            "runtime_id": runtime_id,
            "version": version,
            "contact_preferences": _valid_contact_preferences(),
            "patient_details": _valid_patient_details(),
        }
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
            f"Expected 422 for {MAX_FILE_COUNT + 1} photos, "
            f"got {finish_res.status_code}: {finish_res.text}"
        )


def test_finish_rejects_single_file_exceeding_size_limit():
    """
    A single file whose byte length exceeds MAX_FILE_SIZE_BYTES must
    return 422. No submission record is created.
    """
    with TestClient(app) as client:
        runtime_id, version = _run_full_flow(client)

        payload = {
            "runtime_id": runtime_id,
            "version": version,
            "contact_preferences": _valid_contact_preferences(),
            "patient_details": _valid_patient_details(),
        }
        oversized_bytes = b"\xff\xd8\xff" + b"\x00" * MAX_FILE_SIZE_BYTES
        finish_res = client.post(
            "/form/finish",
            data={"payload": json.dumps(payload)},
            files=[("photos", ("big.jpg", oversized_bytes, "image/jpeg"))],
        )
        assert finish_res.status_code == 422, (
            f"Expected 422 for oversized file, got {finish_res.status_code}: {finish_res.text}"
        )


def test_finish_rejects_combined_size_exceeding_total_limit():
    """
    Multiple files whose combined size exceeds MAX_TOTAL_SIZE_BYTES must
    return 422 even if each individual file is within MAX_FILE_SIZE_BYTES.
    """
    with TestClient(app) as client:
        runtime_id, version = _run_full_flow(client)

        payload = {
            "runtime_id": runtime_id,
            "version": version,
            "contact_preferences": _valid_contact_preferences(),
            "patient_details": _valid_patient_details(),
        }
        chunk_size = (MAX_TOTAL_SIZE_BYTES // 3) + 1
        assert chunk_size <= MAX_FILE_SIZE_BYTES, (
            "Test assumption violated: chunk_size must be <= MAX_FILE_SIZE_BYTES."
        )
        assert chunk_size * 3 > MAX_TOTAL_SIZE_BYTES, (
            "Test assumption violated: three chunks must exceed MAX_TOTAL_SIZE_BYTES."
        )
        chunk = b"\xff\xd8\xff" + b"\x00" * (chunk_size - 3)
        files = [
            ("photos", ("a.jpg", chunk, "image/jpeg")),
            ("photos", ("b.jpg", chunk, "image/jpeg")),
            ("photos", ("c.jpg", chunk, "image/jpeg")),
        ]
        finish_res = client.post(
            "/form/finish",
            data={"payload": json.dumps(payload)},
            files=files,
        )
        assert finish_res.status_code == 422, (
            f"Expected 422 for combined size over limit, "
            f"got {finish_res.status_code}: {finish_res.text}"
        )


def test_finish_rejects_invalid_image_header():
    """
    A file that fails Pillow header validation must return 422.
    The bytes have a valid JPEG start marker but are otherwise corrupt.
    """
    with TestClient(app) as client:
        runtime_id, version = _run_full_flow(client)

        payload = {
            "runtime_id": runtime_id,
            "version": version,
            "contact_preferences": _valid_contact_preferences(),
            "patient_details": _valid_patient_details(),
        }
        # Valid JPEG start marker, but the rest is junk — verify() will reject it.
        corrupt_bytes = b"\xff\xd8\xff" + b"\x00" * 50
        finish_res = client.post(
            "/form/finish",
            data={"payload": json.dumps(payload)},
            files=[("photos", ("corrupt.jpg", corrupt_bytes, "image/jpeg"))],
        )
        assert finish_res.status_code == 422, (
            f"Expected 422 for corrupt image, got {finish_res.status_code}: {finish_res.text}"
        )
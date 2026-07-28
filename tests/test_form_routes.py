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
- The availability check in form_init is overridden to return open for
  happy-path tests, and to raise for the fail-open test.
- Each test that writes to the database uses a unique condition_id drawn
  from the real registry so that the engine can load its ruleset.
- form_finish accepts multipart/form-data. The JSON payload is sent as the
  'payload' form field (a string). Photos are optional and sent as 'photos'
  file fields. Use _finish_multipart() to build the data= and files= args
  for all finish calls.
"""

import io
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
os.environ.setdefault("PRACTICE_ID", "test-practice")
os.environ.setdefault("DATA_DIR", os.path.join(os.path.dirname(__file__), "..", "data"))
# Startup validation in main.py requires email config and ALLOWED_ADMIN_DOMAINS.
# These are stub values — the delivery service is overridden at the route level
# in tests that exercise submission, so no real email is ever sent.
os.environ.setdefault("MAILGUN_API_KEY", "test-key")
os.environ.setdefault("MAILGUN_DOMAIN", "test.mailgun.org")
os.environ.setdefault("EMAIL_FROM", "test@example.com")
os.environ.setdefault("MAILGUN_SIGNING_KEY", "test-signing-key")
os.environ.setdefault("ALLOWED_ADMIN_DOMAINS", "example.com")

pytestmark = pytest.mark.integration

from fastapi.testclient import TestClient  # noqa: E402
from PIL import Image  # noqa: E402

from app.core.db import get_conn  # noqa: E402
from app.core.dependencies import get_availability_repo  # noqa: E402
from app.core.upload_constants import (  # noqa: E402
    MAX_FILE_COUNT,
    MAX_FILE_SIZE_BYTES,
    MAX_FINISH_REQUEST_BYTES,
    MAX_TOTAL_SIZE_BYTES,
)
from main import app  # noqa: E402
from tests.test_pdf_formatter import MINIMAL_JPEG  # noqa: E402

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
        "gender": "female",
        "submitter_name": None,
        "submitter_relationship": None,
        "preferred_name": None,
        "nhs_number": None,
    }


def _build_answers(client_state: dict) -> dict:
    answers = {}
    for q in client_state["questions"]:
        if q["answer_type"] == "boolean":
            answers[q["answer_key"]] = True
        elif q["answer_type"] == "number":
            # An integer always satisfies the question's precision; choose one
            # near the middle of the allowed range so the generic flow tests do
            # not trip an out-of-range warning. Sent as a JSON number.
            lo = q.get("min")
            hi = q.get("max")
            answers[q["answer_key"]] = (
                int(round((lo + hi) / 2)) if lo is not None and hi is not None else 1
            )
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

    init_res = client.post(
        "/form/init",
        json={
            "condition_id": condition_id,
            "free_text": "Test symptom description",
        },
    )
    assert init_res.status_code == 200, init_res.text
    init_body = init_res.json()
    runtime_id = init_body["runtime_id"]
    version = init_body["version"]
    client_state = init_body["client_state"]

    update_res = client.post(
        "/form/update",
        json={
            "runtime_id": runtime_id,
            "base_version": version,
            "answers": _build_answers(client_state),
            "additional_text": None,
        },
    )
    assert update_res.status_code == 200, update_res.text
    version = update_res.json()["version"]

    return runtime_id, version


def _count_pdf_jobs(submission_id: str) -> int:
    with get_conn(DATABASE_URL) as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT COUNT(*) FROM pdf_jobs WHERE submission_id = %s",
            (submission_id,),
        )
        return cur.fetchone()[0]


def _read_pdf_job(submission_id: str) -> dict | None:
    with get_conn(DATABASE_URL) as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT * FROM pdf_jobs WHERE submission_id = %s",
            (submission_id,),
        )
        row = cur.fetchone()
        if row is None:
            return None
        cols = [desc[0] for desc in cur.description]
    return dict(zip(cols, row, strict=True))


def _count_submission_photos(submission_id: str) -> int:
    with get_conn(DATABASE_URL) as conn, conn.cursor() as cur:
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

            init_res = client.post(
                "/form/init",
                json={
                    "condition_id": condition_id,
                    "free_text": "Test symptom description",
                },
            )
            assert init_res.status_code == 200, init_res.text
            init_body = init_res.json()
            runtime_id = init_body["runtime_id"]
            version = init_body["version"]
            client_state = init_body["client_state"]
            assert runtime_id
            assert version == 1

            answers = _build_answers(client_state)
            update_res = client.post(
                "/form/update",
                json={
                    "runtime_id": runtime_id,
                    "base_version": version,
                    "answers": answers,
                    "additional_text": None,
                },
            )
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
            with get_conn(DATABASE_URL) as conn, conn.cursor() as cur:
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
            res = client.post(
                "/form/init",
                json={
                    "condition_id": condition["id"],
                    "free_text": None,
                },
            )
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

        init_res = client.post(
            "/form/init",
            json={
                "condition_id": condition_id,
                "free_text": None,
            },
        )
        assert init_res.status_code == 200
        body = init_res.json()
        runtime_id, version = body["runtime_id"], body["version"]
        client_state = body["client_state"]

        update_res = client.post(
            "/form/update",
            json={
                "runtime_id": runtime_id,
                "base_version": version,
                "answers": _build_answers(client_state),
                "additional_text": None,
            },
        )
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
            "photo_quality_tier": "standard",
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
            "photo_quality_tier": "standard",
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

    with get_conn(DATABASE_URL) as conn, conn.cursor() as cur:
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


def test_finish_rejects_oversized_content_length_before_reading_body():
    """
    A request whose Content-Length exceeds MAX_FINISH_REQUEST_BYTES must be
    rejected with 413 by MaxBodySizeRoute (app/core/max_body_size_route.py),
    which runs before FastAPI parses the multipart body.

    Uses a bogus, nonexistent runtime_id/version to prove the rejection
    happens ahead of any payload/runtime lookup — those would otherwise
    fail with a different error before the byte-count checks ever ran.
    """
    with TestClient(app) as client:
        payload = {
            "runtime_id": "does-not-exist",
            "version": 1,
            "contact_preferences": _valid_contact_preferences(),
            "patient_details": _valid_patient_details(),
        }
        oversized = b"\xff\xd8\xff" + b"\x00" * (MAX_FINISH_REQUEST_BYTES - 2)
        finish_res = client.post(
            "/form/finish",
            data={"payload": json.dumps(payload)},
            files=[("photos", ("big.jpg", oversized, "image/jpeg"))],
        )
        assert finish_res.status_code == 413, (
            f"Expected 413 for oversized Content-Length, "
            f"got {finish_res.status_code}: {finish_res.text}"
        )
        assert finish_res.json()["error"]["code"] == "PAYLOAD_TOO_LARGE"


def test_finish_rejects_truncated_jpeg():
    """
    A truncated JPEG — valid SOI header bytes, abrupt end — must return 422.

    This is the CE+ regression test for CDR.
    """
    with TestClient(app) as client:
        runtime_id, version = _run_full_flow(client)

        payload = {
            "runtime_id": runtime_id,
            "version": version,
            "contact_preferences": _valid_contact_preferences(),
            "patient_details": _valid_patient_details(),
            "photo_quality_tier": "standard",
        }
        truncated = b"\xff\xd8\xff" + b"\x00" * 50
        finish_res = client.post(
            "/form/finish",
            data={"payload": json.dumps(payload)},
            files=[("photos", ("truncated.jpg", truncated, "image/jpeg"))],
        )
        assert finish_res.status_code == 422, (
            f"Expected 422 for truncated JPEG, got {finish_res.status_code}: {finish_res.text}"
        )


def test_finish_sanitizes_png_to_jpeg():
    """
    A valid PNG must be accepted, sanitized to JPEG, and result in a 200
    response with a pdf_jobs row and one submission_photos row.

    """
    png_img = Image.new("RGB", (1, 1), color=(0, 128, 0))
    buf = io.BytesIO()
    png_img.save(buf, format="PNG")
    png_bytes = buf.getvalue()

    with TestClient(app) as client:
        runtime_id, version = _run_full_flow(client)

        payload = {
            "runtime_id": runtime_id,
            "version": version,
            "contact_preferences": _valid_contact_preferences(),
            "patient_details": _valid_patient_details(),
            "photo_quality_tier": "standard",
        }
        finish_res = client.post(
            "/form/finish",
            data={"payload": json.dumps(payload)},
            files=[("photos", ("photo.png", png_bytes, "image/png"))],
        )
        assert finish_res.status_code == 200, (
            f"Expected 200 for valid PNG upload, got {finish_res.status_code}: {finish_res.text}"
        )
        submission_id = finish_res.json()["submission_id"]

    pdf_job = _read_pdf_job(submission_id)
    assert pdf_job is not None
    assert pdf_job["attachment_count"] == 1
    assert _count_submission_photos(submission_id) == 1


# ---------------------------------------------------------------------------
# Tier validation tests
# ---------------------------------------------------------------------------


def test_finish_with_photo_and_high_tier_returns_200():
    """
    Submitting a photo with photo_quality_tier "high" must return 200.
    The high-tier CDR path is exercised; the result is a valid submission.
    """
    with TestClient(app) as client:
        runtime_id, version = _run_full_flow(client)

        payload = {
            "runtime_id": runtime_id,
            "version": version,
            "contact_preferences": _valid_contact_preferences(),
            "patient_details": _valid_patient_details(),
            "photo_quality_tier": "high",
        }
        finish_res = client.post(
            "/form/finish",
            data={"payload": json.dumps(payload)},
            files=[("photos", ("photo.jpg", MINIMAL_JPEG, "image/jpeg"))],
        )
        assert finish_res.status_code == 200, (
            f"Expected 200 for high-tier photo submission, "
            f"got {finish_res.status_code}: {finish_res.text}"
        )
        assert "submission_id" in finish_res.json()


def test_finish_with_photo_and_invalid_tier_returns_422():
    """
    Submitting a photo with an unrecognised photo_quality_tier value must
    return 422. No database writes occur.
    """
    with TestClient(app) as client:
        runtime_id, version = _run_full_flow(client)

        payload = {
            "runtime_id": runtime_id,
            "version": version,
            "contact_preferences": _valid_contact_preferences(),
            "patient_details": _valid_patient_details(),
            "photo_quality_tier": "ultra",
        }
        finish_res = client.post(
            "/form/finish",
            data={"payload": json.dumps(payload)},
            files=[("photos", ("photo.jpg", MINIMAL_JPEG, "image/jpeg"))],
        )
        assert finish_res.status_code == 422, (
            f"Expected 422 for invalid tier value, got {finish_res.status_code}: {finish_res.text}"
        )


def test_finish_with_photo_and_no_tier_returns_422():
    """
    Submitting photos without a photo_quality_tier field must return 422.
    The tier field is required when photos are present.
    """
    with TestClient(app) as client:
        runtime_id, version = _run_full_flow(client)

        payload = {
            "runtime_id": runtime_id,
            "version": version,
            "contact_preferences": _valid_contact_preferences(),
            "patient_details": _valid_patient_details(),
            # photo_quality_tier intentionally absent
        }
        finish_res = client.post(
            "/form/finish",
            data={"payload": json.dumps(payload)},
            files=[("photos", ("photo.jpg", MINIMAL_JPEG, "image/jpeg"))],
        )
        assert finish_res.status_code == 422, (
            f"Expected 422 when photos present but tier absent, "
            f"got {finish_res.status_code}: {finish_res.text}"
        )


def test_finish_without_photos_and_no_tier_returns_200():
    """
    Submitting no photos without a photo_quality_tier field must return 200.
    The tier field is only required when photos are present; text-only
    submissions must not be rejected for omitting it.
    """
    with TestClient(app) as client:
        runtime_id, version = _run_full_flow(client)
        # _finish_multipart sends no photos and no photo_quality_tier.
        finish_res = client.post("/form/finish", **_finish_multipart(runtime_id, version))
        assert finish_res.status_code == 200, (
            f"Expected 200 for text-only submission with no tier field, "
            f"got {finish_res.status_code}: {finish_res.text}"
        )


def test_finish_without_photos_and_invalid_tier_returns_422():
    """
    A tampered client can submit no photos but still include a garbage
    photo_quality_tier value. Previously this was accepted verbatim (the
    tier check only ran when photos were present) and stamped straight onto
    the audit record. It must now return 422 regardless of photo presence.
    """
    with TestClient(app) as client:
        runtime_id, version = _run_full_flow(client)

        payload = {
            "runtime_id": runtime_id,
            "version": version,
            "contact_preferences": _valid_contact_preferences(),
            "patient_details": _valid_patient_details(),
            "photo_quality_tier": "ultra",
        }
        finish_res = client.post(
            "/form/finish",
            data={"payload": json.dumps(payload)},
            files=[],
        )
        assert finish_res.status_code == 422, (
            f"Expected 422 for invalid tier with no photos, "
            f"got {finish_res.status_code}: {finish_res.text}"
        )


def test_finish_without_photos_and_unhashable_tier_returns_422():
    """
    An unhashable photo_quality_tier (e.g. a JSON object) must return 422,
    not an unhandled 500 from `tier in _VALID_TIERS` raising TypeError.
    """
    with TestClient(app) as client:
        runtime_id, version = _run_full_flow(client)

        payload = {
            "runtime_id": runtime_id,
            "version": version,
            "contact_preferences": _valid_contact_preferences(),
            "patient_details": _valid_patient_details(),
            "photo_quality_tier": {"nested": "object"},
        }
        finish_res = client.post(
            "/form/finish",
            data={"payload": json.dumps(payload)},
            files=[],
        )
        assert finish_res.status_code == 422, (
            f"Expected 422 for unhashable tier, got {finish_res.status_code}: {finish_res.text}"
        )


def test_finish_with_high_tier_and_multiple_photos_returns_422():
    """
    "high" tier is limited to a single photo (the frontend enforces this in
    EditScreen.tsx). A tampered client sending tier=high with several photos
    must be rejected server-side, before the expensive per-photo 4K CDR pass
    runs for each one.
    """
    with TestClient(app) as client:
        runtime_id, version = _run_full_flow(client)

        payload = {
            "runtime_id": runtime_id,
            "version": version,
            "contact_preferences": _valid_contact_preferences(),
            "patient_details": _valid_patient_details(),
            "photo_quality_tier": "high",
        }
        finish_res = client.post(
            "/form/finish",
            data={"payload": json.dumps(payload)},
            files=[
                ("photos", ("photo1.jpg", MINIMAL_JPEG, "image/jpeg")),
                ("photos", ("photo2.jpg", MINIMAL_JPEG, "image/jpeg")),
            ],
        )
        assert finish_res.status_code == 422, (
            f"Expected 422 for high-tier submission with multiple photos, "
            f"got {finish_res.status_code}: {finish_res.text}"
        )


def test_finish_with_malformed_json_payload_returns_422():
    """
    A payload field that isn't valid JSON must return 422, not an unhandled
    500 from json.loads raising JSONDecodeError.
    """
    with TestClient(app) as client:
        finish_res = client.post(
            "/form/finish",
            data={"payload": "{not valid json"},
            files=[],
        )
        assert finish_res.status_code == 422, (
            f"Expected 422 for malformed JSON payload, "
            f"got {finish_res.status_code}: {finish_res.text}"
        )


def test_finish_with_non_object_json_payload_returns_422():
    """
    A payload field that parses as valid JSON but isn't a JSON object (e.g.
    a bare list) must return 422, not an unhandled 500 from require_keys
    calling .keys() on a non-dict.
    """
    with TestClient(app) as client:
        finish_res = client.post(
            "/form/finish",
            data={"payload": json.dumps(["not", "an", "object"])},
            files=[],
        )
        assert finish_res.status_code == 422, (
            f"Expected 422 for non-object JSON payload, "
            f"got {finish_res.status_code}: {finish_res.text}"
        )


# ---------------------------------------------------------------------------
# Quantity (unit-toggle) Number answer — boundary behaviour at /form/update
#
# These target the numeric_capability_demo condition: a single quantity Number
# question (patient_weight_kg, decimal_places=1, metric+imperial). The patient
# submits {"system", "components"}; the server converts to a canonical kg value.
# They exercise real precision rejection (metric), imperial conversion/rounding,
# and the shape/system guards, end to end through the raw-body parse_float=Decimal
# path. (They predate Step E's response serialisation, so they assert status and
# version only, not the response current_value shape.)
# ---------------------------------------------------------------------------

NUMERIC_DEMO_CONDITION_ID = "numeric_capability_demo"
NUMERIC_DEMO_ANSWER_KEY = "patient_weight_kg"


def _init_numeric_demo(client: TestClient) -> tuple[str, int]:
    """Init the demo condition directly by id (works regardless of search_tags)."""
    res = client.post(
        "/form/init",
        json={
            "condition_id": NUMERIC_DEMO_CONDITION_ID,
            "free_text": "Numeric capability demo",
        },
    )
    assert res.status_code == 200, res.text
    body = res.json()
    return body["runtime_id"], body["version"]


def _metric(kg):
    return {"system": "metric", "components": {"kg": kg}}


def _imperial(st, lb):
    return {"system": "imperial", "components": {"st": st, "lb": lb}}


def _update_weight(client, runtime_id, version, value):
    return client.post(
        "/form/update",
        json={
            "runtime_id": runtime_id,
            "base_version": version,
            "answers": {NUMERIC_DEMO_ANSWER_KEY: value},
            "additional_text": None,
        },
    )


def test_update_rejects_number_with_too_many_decimals():
    """
    A metric value finer than the question's decimal_places is rejected at the
    boundary as 422 INVALID_PAYLOAD. Also exercises the raw-body
    parse_float=Decimal path: the nested 70.55 must be read exactly (as Decimal),
    so the precision check sees two decimal places rather than a lossy float.
    """
    with TestClient(app) as client:
        runtime_id, version = _init_numeric_demo(client)
        res = _update_weight(client, runtime_id, version, _metric(70.55))
        assert res.status_code == 422, res.text
        assert res.json()["error"]["code"] == "INVALID_PAYLOAD"


def test_update_accepts_number_at_allowed_precision():
    """A metric value at exactly decimal_places is accepted and the session advances."""
    with TestClient(app) as client:
        runtime_id, version = _init_numeric_demo(client)
        res = _update_weight(client, runtime_id, version, _metric(70.5))
        assert res.status_code == 200, res.text
        assert res.json()["version"] == version + 1


def test_update_accepts_whole_number_for_number_question():
    """A whole metric kg carries no fractional part and is always within precision."""
    with TestClient(app) as client:
        runtime_id, version = _init_numeric_demo(client)
        res = _update_weight(client, runtime_id, version, _metric(70))
        assert res.status_code == 200, res.text


def test_update_rejects_bare_number_for_quantity_question():
    """
    The pre-toggle payload shape (a bare JSON number) is no longer valid for a
    quantity question: the server requires {system, components}.
    """
    with TestClient(app) as client:
        runtime_id, version = _init_numeric_demo(client)
        res = _update_weight(client, runtime_id, version, 70.5)
        assert res.status_code == 422, res.text
        assert res.json()["error"]["code"] == "INVALID_PAYLOAD"


def test_update_accepts_imperial_components():
    """Imperial stones/pounds are accepted, converted, and the session advances."""
    with TestClient(app) as client:
        runtime_id, version = _init_numeric_demo(client)
        res = _update_weight(client, runtime_id, version, _imperial(11, 11))
        assert res.status_code == 200, res.text
        assert res.json()["version"] == version + 1


def test_update_rejects_imperial_fractional_pounds():
    """Stones/pounds must be whole numbers; a fractional pound is rejected as 422."""
    with TestClient(app) as client:
        runtime_id, version = _init_numeric_demo(client)
        res = _update_weight(client, runtime_id, version, _imperial(11, 11.5))
        assert res.status_code == 422, res.text
        assert res.json()["error"]["code"] == "INVALID_PAYLOAD"


def test_update_rejects_unknown_unit_system():
    """A system outside the question's allowed_systems is rejected as 422."""
    with TestClient(app) as client:
        runtime_id, version = _init_numeric_demo(client)
        res = _update_weight(
            client,
            runtime_id,
            version,
            {"system": "nautical", "components": {"kg": 70}},
        )
        assert res.status_code == 422, res.text
        assert res.json()["error"]["code"] == "INVALID_PAYLOAD"

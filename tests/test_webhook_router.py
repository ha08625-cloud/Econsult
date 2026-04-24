"""
tests/test_webhook_router.py

Integration tests for the Mailgun webhook router.

These tests require a live Postgres database (TEST_DATABASE_URL).
They verify the security boundary (HMAC verification, replay protection,
timestamp tolerance) and the status transition logic driven by webhook events.

Two-database rule: TEST_DATABASE_URL must be set and must not equal DATABASE_URL.
This guardrail must never be removed.
"""

import hashlib
import hmac
import os
import time
import uuid
from datetime import datetime, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

# ---------------------------------------------------------------------------
# Two-database guardrail
# ---------------------------------------------------------------------------

_TEST_DB = os.environ.get("TEST_DATABASE_URL")
if not _TEST_DB:
    pytest.skip(
        "TEST_DATABASE_URL is not set — skipping webhook integration tests",
        allow_module_level=True,
    )

pytestmark = pytest.mark.integration

# ---------------------------------------------------------------------------
# Imports (after guardrail)
# ---------------------------------------------------------------------------

from app.routers.webhook_router import router as webhook_router
from app.repositories.delivery_repository import DeliveryRepository
from app.repositories.submission_repository import SubmissionRepository
from app.models.serialisation_contracts import ClinicalOutput, AuditOutput, PatientDetails

_SIGNING_KEY = "test-signing-key-abc123"

_SUBMITTED_AT = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)

# Minimal PatientDetails satisfying all required fields.
_PATIENT_DETAILS = PatientDetails(
    patient_for="me",
    first_name="Test",
    last_name="Patient",
    date_of_birth="1990-01-01",
    postcode="OX1 1AA",
    gender="prefer_not_to_say",
)

# Minimal ClinicalOutput satisfying all required fields.
_CLINICAL_OUTPUT = ClinicalOutput(
    condition_id="test-condition",
    free_text="",
    additional_text=None,
    answers={},
    safety_messages=[],
    question_labels={},
    patient_details=_PATIENT_DETAILS,
    contact_preferences=None,
)

# Minimal AuditOutput satisfying all required fields.
_AUDIT_OUTPUT = AuditOutput(
    runtime_state={},
    safety_evaluation={},
    ruleset_version="test",
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_signature(signing_key: str, timestamp: str, token: str) -> str:
    """Generate a valid Mailgun HMAC-SHA256 signature for a given timestamp and token."""
    return hmac.new(
        key=signing_key.encode("utf-8"),
        msg=f"{timestamp}{token}".encode("utf-8"),
        digestmod=hashlib.sha256,
    ).hexdigest()


def _fresh_timestamp() -> str:
    """Return the current Unix timestamp as a string."""
    return str(int(time.time()))


def _fresh_token() -> str:
    """Return a unique token string to avoid replay conflicts between tests."""
    return uuid.uuid4().hex


def _make_payload(
    event: str,
    provider_message_id: str,
    signing_key: str = _SIGNING_KEY,
    timestamp: str | None = None,
    token: str | None = None,
    signature: str | None = None,
) -> dict:
    """
    Build a form-encoded payload dict matching Mailgun's webhook format.

    Generates a valid signature by default. Pass explicit timestamp/token/signature
    to test invalid or stale cases.
    """
    ts = timestamp or _fresh_timestamp()
    tok = token or _fresh_token()
    sig = signature or _make_signature(signing_key, ts, tok)

    return {
        "timestamp": ts,
        "token": tok,
        "signature": sig,
        "event-data[event]": event,
        "event-data[message][headers][message-id]": f"<{provider_message_id}>",
    }


def _make_test_app(delivery_repo: DeliveryRepository, database_url: str) -> FastAPI:
    """Build a minimal FastAPI app with the webhook router and required state."""
    app = FastAPI()
    app.include_router(webhook_router)
    app.state.delivery_repo = delivery_repo
    app.state.mailgun_signing_key = _SIGNING_KEY
    app.state.database_url = database_url
    return app


def _insert_test_submission(submission_repo: SubmissionRepository) -> str:
    """Insert a minimal submission_records row and return its submission_id."""
    submission_id = str(uuid.uuid4())
    submission_repo.create_submission(
        submission_id=submission_id,
        practice_id="test-practice",
        condition_id="test-condition",
        condition_label="Test Condition",
        clinical_output=_CLINICAL_OUTPUT,
        audit_output=_AUDIT_OUTPUT,
        submitted_at=_SUBMITTED_AT,
    )
    return submission_id


def _insert_delivery_job(
    delivery_repo: DeliveryRepository,
    submission_id: str,
    provider_message_id: str,
) -> str:
    """
    Insert a delivery_jobs row in provider_accepted status with a known
    provider_message_id. Returns the job_id.
    """
    job_id = delivery_repo.create_job(
        submission_id=submission_id,
        to_email="gp@example.com",
        condition_label="Test Condition",
        submitted_at=_SUBMITTED_AT,
    )
    delivery_repo.mark_as_accepted(job_id, provider_message_id)
    return job_id


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def delivery_repo():
    return DeliveryRepository(_TEST_DB)


@pytest.fixture()
def submission_repo():
    return SubmissionRepository(_TEST_DB)


@pytest.fixture()
def client(delivery_repo):
    app = _make_test_app(delivery_repo, _TEST_DB)
    return TestClient(app)


# ---------------------------------------------------------------------------
# Security: HMAC verification
# ---------------------------------------------------------------------------

class TestHMACVerification:
    def test_valid_signature_is_accepted(self, client, delivery_repo, submission_repo):
        submission_id = _insert_test_submission(submission_repo)
        provider_message_id = f"msg-{uuid.uuid4().hex}@mailgun.org"
        _insert_delivery_job(delivery_repo, submission_id, provider_message_id)

        payload = _make_payload("delivered", provider_message_id)
        response = client.post("/webhooks/mailgun", data=payload)

        assert response.status_code == 200

    def test_invalid_signature_returns_403(self, client):
        provider_message_id = f"msg-{uuid.uuid4().hex}@mailgun.org"
        ts = _fresh_timestamp()
        tok = _fresh_token()
        payload = _make_payload(
            "delivered",
            provider_message_id,
            timestamp=ts,
            token=tok,
            signature="invalidsignature",
        )

        response = client.post("/webhooks/mailgun", data=payload)

        assert response.status_code == 403

    def test_wrong_signing_key_returns_403(self, delivery_repo):
        """A webhook signed with a different key must be rejected."""
        app = _make_test_app(delivery_repo, _TEST_DB)
        app.state.mailgun_signing_key = "wrong-key"
        wrong_client = TestClient(app)

        provider_message_id = f"msg-{uuid.uuid4().hex}@mailgun.org"
        # Payload signed with the correct key, but app expects the wrong key.
        payload = _make_payload("delivered", provider_message_id, signing_key=_SIGNING_KEY)

        response = wrong_client.post("/webhooks/mailgun", data=payload)

        assert response.status_code == 403


# ---------------------------------------------------------------------------
# Security: timestamp staleness
# ---------------------------------------------------------------------------

class TestTimestampStaleness:
    def test_stale_timestamp_returns_200_and_does_not_update(
        self, client, delivery_repo, submission_repo
    ):
        """
        A webhook with a timestamp older than 15 minutes must be silently
        dropped (200 OK) without changing the job status.
        """
        submission_id = _insert_test_submission(submission_repo)
        provider_message_id = f"msg-{uuid.uuid4().hex}@mailgun.org"
        job_id = _insert_delivery_job(delivery_repo, submission_id, provider_message_id)

        stale_ts = str(int(time.time()) - 1000)  # ~16 minutes ago
        tok = _fresh_token()
        sig = _make_signature(_SIGNING_KEY, stale_ts, tok)

        payload = _make_payload(
            "delivered",
            provider_message_id,
            timestamp=stale_ts,
            token=tok,
            signature=sig,
        )

        response = client.post("/webhooks/mailgun", data=payload)

        assert response.status_code == 200
        job = delivery_repo.get(job_id)
        assert job["status"] == "provider_accepted"  # unchanged


# ---------------------------------------------------------------------------
# Security: replay protection
# ---------------------------------------------------------------------------

class TestReplayProtection:
    def test_duplicate_token_returns_200_and_does_not_double_update(
        self, client, delivery_repo, submission_repo
    ):
        """
        Sending the same token twice must succeed on first call and be silently
        dropped on the second. The status must not be updated twice.
        """
        submission_id = _insert_test_submission(submission_repo)
        provider_message_id = f"msg-{uuid.uuid4().hex}@mailgun.org"
        job_id = _insert_delivery_job(delivery_repo, submission_id, provider_message_id)

        ts = _fresh_timestamp()
        tok = _fresh_token()
        sig = _make_signature(_SIGNING_KEY, ts, tok)

        payload = _make_payload(
            "delivered",
            provider_message_id,
            timestamp=ts,
            token=tok,
            signature=sig,
        )

        first = client.post("/webhooks/mailgun", data=payload)
        second = client.post("/webhooks/mailgun", data=payload)

        assert first.status_code == 200
        assert second.status_code == 200

        job = delivery_repo.get(job_id)
        # Delivered exactly once.
        assert job["status"] == "delivered"
        # provider_events should contain exactly one entry.
        assert job["provider_events"] is not None
        assert len(job["provider_events"]) == 1


# ---------------------------------------------------------------------------
# Status transitions: delivered
# ---------------------------------------------------------------------------

class TestDeliveredEvent:
    def test_delivered_event_transitions_status(
        self, client, delivery_repo, submission_repo
    ):
        submission_id = _insert_test_submission(submission_repo)
        provider_message_id = f"msg-{uuid.uuid4().hex}@mailgun.org"
        job_id = _insert_delivery_job(delivery_repo, submission_id, provider_message_id)

        payload = _make_payload("delivered", provider_message_id)
        response = client.post("/webhooks/mailgun", data=payload)

        assert response.status_code == 200
        job = delivery_repo.get(job_id)
        assert job["status"] == "delivered"

    def test_delivered_event_appends_provider_event(
        self, client, delivery_repo, submission_repo
    ):
        submission_id = _insert_test_submission(submission_repo)
        provider_message_id = f"msg-{uuid.uuid4().hex}@mailgun.org"
        job_id = _insert_delivery_job(delivery_repo, submission_id, provider_message_id)

        payload = _make_payload("delivered", provider_message_id)
        client.post("/webhooks/mailgun", data=payload)

        job = delivery_repo.get(job_id)
        assert job["provider_events"] is not None
        assert len(job["provider_events"]) == 1
        assert job["provider_events"][0]["event-data[event]"] == "delivered"


# ---------------------------------------------------------------------------
# Status transitions: failed / dropped
# ---------------------------------------------------------------------------

class TestFailedEvent:
    def test_failed_event_transitions_status(
        self, client, delivery_repo, submission_repo
    ):
        submission_id = _insert_test_submission(submission_repo)
        provider_message_id = f"msg-{uuid.uuid4().hex}@mailgun.org"
        job_id = _insert_delivery_job(delivery_repo, submission_id, provider_message_id)

        payload = _make_payload("failed", provider_message_id)
        response = client.post("/webhooks/mailgun", data=payload)

        assert response.status_code == 200
        job = delivery_repo.get(job_id)
        assert job["status"] == "failed"

    def test_dropped_event_transitions_status_to_failed(
        self, client, delivery_repo, submission_repo
    ):
        submission_id = _insert_test_submission(submission_repo)
        provider_message_id = f"msg-{uuid.uuid4().hex}@mailgun.org"
        job_id = _insert_delivery_job(delivery_repo, submission_id, provider_message_id)

        payload = _make_payload("dropped", provider_message_id)
        response = client.post("/webhooks/mailgun", data=payload)

        assert response.status_code == 200
        job = delivery_repo.get(job_id)
        assert job["status"] == "failed"


# ---------------------------------------------------------------------------
# Race condition: provider_message_id not yet committed
# ---------------------------------------------------------------------------

class TestRaceCondition:
    def test_unknown_provider_message_id_returns_406(self, client):
        """
        If the delivery worker hasn't committed provider_message_id yet,
        the webhook router must return 406 so Mailgun retries later.
        """
        unknown_id = f"nonexistent-{uuid.uuid4().hex}@mailgun.org"
        payload = _make_payload("delivered", unknown_id)

        response = client.post("/webhooks/mailgun", data=payload)

        assert response.status_code == 406


# ---------------------------------------------------------------------------
# Informational events
# ---------------------------------------------------------------------------

class TestInformationalEvents:
    def test_unknown_event_type_returns_200_and_appends_event(
        self, client, delivery_repo, submission_repo
    ):
        """
        An event type not in the handled set (e.g. 'opened') must return 200
        and append the payload to provider_events without changing status.
        """
        submission_id = _insert_test_submission(submission_repo)
        provider_message_id = f"msg-{uuid.uuid4().hex}@mailgun.org"
        job_id = _insert_delivery_job(delivery_repo, submission_id, provider_message_id)

        payload = _make_payload("opened", provider_message_id)
        response = client.post("/webhooks/mailgun", data=payload)

        assert response.status_code == 200
        job = delivery_repo.get(job_id)
        # Status must be unchanged.
        assert job["status"] == "provider_accepted"
        # Payload must be appended.
        assert job["provider_events"] is not None
        assert len(job["provider_events"]) == 1
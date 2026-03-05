"""
HTTP layer.

Thin wrapper over engine_adapters. No clinical logic.
Imports: engine_adapters, persistence, condition_registry, request_validation, errors.

Single-tenant deployment:
- PRACTICE_ID environment variable is required at startup
- The practice must exist in the database with a valid email
- The database must contain exactly one practice
- SMTP configuration is required unless DEV_MODE is set
- ADMIN_TOKEN is required unless DEV_MODE is set
"""

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
import uuid
import os
import logging
from datetime import datetime, timezone

from persistence import (
    RuntimeStateRepository,
    RuntimeStateNotFound,
    VersionConflict,
    SessionClosed,
)
from contracts.runtime_state import RuntimeState
from condition_registry import ConditionRegistry, ConditionNotFound
from practice_repository import PracticeRepository
from presentation_service import PresentationService
from submission_repository import SubmissionRepository
from request_validation import (
    validate_init_payload,
    validate_update_payload,
    validate_finish_payload,
)
from errors import APIError, INVALID_PAYLOAD, UNKNOWN_RUNTIME_ID, VERSION_CONFLICT, SESSION_CLOSED
from engine_adapters import (
    init_runtime_state,
    apply_update_and_evaluate,
    finish_runtime_state,
)
from email_service import send_clinical_output, EmailDeliveryError
from admin_router import router as admin_router

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Startup helpers
# ---------------------------------------------------------------------------

def _require_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"Required environment variable not set: {name}")
    return value


def _is_dev_mode() -> bool:
    return os.environ.get("DEV_MODE", "").lower() in ("1", "true")


def _validate_startup(practice_repo: PracticeRepository) -> str:
    practice_id = _require_env("PRACTICE_ID")

    count = practice_repo.count_practices()
    if count > 1:
        raise RuntimeError(
            f"Database contains {count} practices. "
            "This is a single-tenant deployment. "
            "Multiple practices is a clinically unsafe configuration. "
            "Aborting startup."
        )

    practice = practice_repo.get_practice(practice_id)
    if practice is None:
        raise RuntimeError(
            f"PRACTICE_ID '{practice_id}' not found in database. "
            "Create the practice record before starting the application."
        )

    if not practice.get("email", "").strip():
        raise RuntimeError(
            f"Practice '{practice_id}' has no email address configured. "
            "Update the practice record with a valid email before starting."
        )

    if not _is_dev_mode():
        for var in ("SMTP_HOST", "SMTP_USER", "SMTP_PASSWORD", "EMAIL_FROM"):
            if not os.environ.get(var):
                raise RuntimeError(
                    f"Required SMTP environment variable not set: {var}. "
                    "Set DEV_MODE=1 to skip email sending during development."
                )

    if not _is_dev_mode():
        if not os.environ.get("ADMIN_TOKEN"):
            raise RuntimeError(
                "Required environment variable not set: ADMIN_TOKEN. "
                "Set DEV_MODE=1 to skip this check during development."
            )
    else:
        if not os.environ.get("ADMIN_TOKEN"):
            logger.warning(
                "ADMIN_TOKEN is not set. In DEV_MODE any non-empty bearer token "
                "will be accepted by admin endpoints. Do not expose this server publicly."
            )

    return practice_id


# ---------------------------------------------------------------------------
# Application factory
# ---------------------------------------------------------------------------

DATA_DIR = os.environ.get("DATA_DIR", "data")
DB_PATH = os.environ.get("DB_PATH", "runtime.db")

app = FastAPI()

repo = RuntimeStateRepository(DB_PATH)
registry = ConditionRegistry(DATA_DIR)
practice_repo = PracticeRepository(DB_PATH)
submission_repo = SubmissionRepository(DB_PATH)
presentation_service = PresentationService(registry, practice_repo)

# Startup validation -- runs at import time (when FastAPI loads the module).
# Any failure here prevents the application from starting.
app.state.practice_id = _validate_startup(practice_repo)
app.state.registry = registry
app.state.practice_repo = practice_repo

# Admin router -- prefix and tag applied here so admin_router.py stays decoupled
app.include_router(admin_router, prefix="/admin", tags=["admin"])


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------

@app.exception_handler(APIError)
async def api_error_handler(_, exc: APIError):
    return JSONResponse(
        status_code=422,
        content={"error": {"code": exc.code, "message": exc.message}},
    )


# ---------------------------------------------------------------------------
# Condition discovery (pre-session, no state)
# ---------------------------------------------------------------------------

@app.get("/conditions")
async def list_conditions():
    return {"conditions": registry.list_conditions()}


@app.get("/conditions/{condition_id}/presentation")
async def get_presentation(condition_id: str):
    try:
        return presentation_service.get_patient_presentation(
            condition_id,
            app.state.practice_id,
        )
    except ConditionNotFound:
        return JSONResponse(
            status_code=404,
            content={
                "error": {
                    "code": "CONDITION_NOT_FOUND",
                    "message": f"Unknown condition: {condition_id}",
                }
            },
        )


# ---------------------------------------------------------------------------
# Form session endpoints
# ---------------------------------------------------------------------------

@app.post("/form/init")
async def form_init(request: Request):
    payload = await request.json()
    validate_init_payload(payload)

    condition_id = payload["condition_id"]
    free_text = payload.get("free_text")

    try:
        ruleset_path = registry.get_ruleset_path(condition_id)
        condition_label = registry.get_presentation(condition_id)["label"]
    except ConditionNotFound:
        raise INVALID_PAYLOAD(f"Unknown condition_id: {condition_id}")

    runtime_id = str(uuid.uuid4())

    runtime_state, rh, client_state = init_runtime_state(
        condition_id=condition_id,
        free_text=free_text,
        ruleset_path=ruleset_path,
        condition_label=condition_label,
    )

    repo.create_initial(
        runtime_id=runtime_id,
        ruleset_hash=rh,
        state_dict=runtime_state.to_dict(),
    )

    return {
        "runtime_id": runtime_id,
        "version": 1,
        "client_state": client_state,
    }


@app.post("/form/update")
async def form_update(request: Request):
    payload = await request.json()
    validate_update_payload(payload)

    runtime_id = payload["runtime_id"]
    base_version = payload["base_version"]
    answers = payload["answers"]

    try:
        row = repo.get_latest(runtime_id)
    except RuntimeStateNotFound:
        raise UNKNOWN_RUNTIME_ID()
    except SessionClosed:
        raise SESSION_CLOSED()

    runtime_state = RuntimeState.from_dict(row["state_json"])
    current_ruleset_hash = row["ruleset_hash"]

    try:
        ruleset_path = registry.get_ruleset_path(runtime_state.condition_id)
        condition_label = registry.get_presentation(runtime_state.condition_id)["label"]
    except ConditionNotFound:
        raise INVALID_PAYLOAD(f"Unknown condition_id: {runtime_state.condition_id}")

    new_state, new_client_state, safety_messages = apply_update_and_evaluate(
        runtime_state=runtime_state,
        answers=answers,
        ruleset_path=ruleset_path,
        condition_label=condition_label,
    )

    try:
        new_version = repo.insert_new_version(
            runtime_id=runtime_id,
            base_version=base_version,
            ruleset_hash=current_ruleset_hash,
            state_dict=new_state.to_dict(),
        )
    except VersionConflict:
        raise VERSION_CONFLICT()

    return {
        "runtime_id": runtime_id,
        "version": new_version,
        "client_state": new_client_state,
        "safety_messages": [
            {"rule_id": m.rule_id, "message": m.message}
            for m in safety_messages
        ],
    }


@app.post("/form/finish")
async def form_finish(request: Request):
    payload = await request.json()
    validate_finish_payload(payload)

    runtime_id = payload["runtime_id"]
    version = payload["version"]

    try:
        row = repo.get_latest(runtime_id)
    except RuntimeStateNotFound:
        raise UNKNOWN_RUNTIME_ID()
    except SessionClosed:
        raise SESSION_CLOSED()

    if row["version"] != version:
        raise VERSION_CONFLICT()

    runtime_state = RuntimeState.from_dict(row["state_json"])

    try:
        ruleset_path = registry.get_ruleset_path(runtime_state.condition_id)
        condition_label = registry.get_presentation(runtime_state.condition_id)["label"]
    except ConditionNotFound:
        raise INVALID_PAYLOAD(f"Unknown condition_id: {runtime_state.condition_id}")

    clinical, audit = finish_runtime_state(runtime_state, ruleset_path)

    delivery_email = practice_repo.get_email(app.state.practice_id)
    submission_id = str(uuid.uuid4())

    submission_repo.create_submission(
        submission_id=submission_id,
        practice_id=app.state.practice_id,
        condition_id=runtime_state.condition_id,
        clinical_output=clinical,
        audit_output=audit,
        delivery_email=delivery_email,
    )

    try:
        send_clinical_output(
            to_email=delivery_email,
            condition_label=condition_label,
            clinical_output=clinical,
            submission_id=submission_id,
        )
        submission_repo.update_delivery_status(
            submission_id=submission_id,
            status="sent",
            delivered_at=datetime.now(timezone.utc),
        )
    except EmailDeliveryError as e:
        logger.error(
            "Email delivery failed for submission %s: %s",
            submission_id,
            str(e),
        )
        submission_repo.update_delivery_status(
            submission_id=submission_id,
            status="failed",
            delivery_error=str(e),
        )

    repo.close_session(runtime_id, version)

    return {"submission_id": submission_id}

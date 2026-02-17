"""
HTTP layer.

Thin wrapper over engine_adapters. No clinical logic.
Imports: engine_adapters, persistence, condition_registry, request_validation, errors.
"""

from fastapi import FastAPI, Request, Query
from fastapi.responses import JSONResponse
import uuid
import os
from typing import Optional

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

# --- Startup wiring ---

DATA_DIR = os.environ.get("DATA_DIR", "data")
DB_PATH = os.environ.get("DB_PATH", "runtime.db")

app = FastAPI()
repo = RuntimeStateRepository(DB_PATH)
registry = ConditionRegistry(DATA_DIR)
practice_repo = PracticeRepository(DB_PATH)
presentation_service = PresentationService(registry, practice_repo)


# --- Error handling ---

@app.exception_handler(APIError)
async def api_error_handler(_, exc: APIError):
    return JSONResponse(
        status_code=422,
        content={"error": {"code": exc.code, "message": exc.message}},
    )


# --- Condition discovery (pre-session, no state) ---

@app.get("/conditions")
async def list_conditions():
    return {"conditions": registry.list_conditions()}


@app.get("/conditions/{condition_id}/presentation")
async def get_presentation(
    condition_id: str,
    practice: Optional[str] = Query(default=None),
):
    """
    Get patient-facing presentation for a condition.
    
    Optional query parameter:
        practice: Practice ID for practice-specific signposting
    """
    try:
        return presentation_service.get_patient_presentation(condition_id, practice)
    except ConditionNotFound:
        return JSONResponse(
            status_code=404,
            content={"error": {"code": "CONDITION_NOT_FOUND", "message": f"Unknown condition: {condition_id}"}},
        )


# --- Form session endpoints ---

@app.post("/form/init")
async def form_init(request: Request):
    payload = await request.json()
    validate_init_payload(payload)

    condition_id = payload["condition_id"]
    free_text = payload.get("free_text")

    # Validate condition exists and get its metadata
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
    ruleset_hash = row["ruleset_hash"]

    # Resolve ruleset path and label from the condition_id stored in RuntimeState
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
            ruleset_hash=ruleset_hash,
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

    # Resolve ruleset path from the condition_id stored in RuntimeState
    try:
        ruleset_path = registry.get_ruleset_path(runtime_state.condition_id)
    except ConditionNotFound:
        raise INVALID_PAYLOAD(f"Unknown condition_id: {runtime_state.condition_id}")

    submission_id = finish_runtime_state(runtime_state, ruleset_path)

    repo.close_session(runtime_id, version)

    return {"submission_id": submission_id}
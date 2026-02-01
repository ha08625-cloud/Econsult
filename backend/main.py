from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
import uuid

from persistence import (
    RuntimeStateRepository,
    RuntimeStateNotFound,
    VersionConflict,
    SessionClosed,
)
from errors import *
from api_models import *

# ---- wiring points (existing engine) ----
from engine import (
    init_runtime_state,
    apply_update_and_evaluate,
    finish_runtime_state,
)

app = FastAPI()
repo = RuntimeStateRepository("runtime.db")


@app.exception_handler(APIError)
async def api_error_handler(_, exc: APIError):
    return JSONResponse(
        status_code=422,
        content={"error": {"code": exc.code, "message": exc.message}},
    )


@app.post("/form/init")
async def form_init(req: InitRequest):
    runtime_id = str(uuid.uuid4())

    runtime_state, ruleset_hash, client_state = init_runtime_state(
        condition_id=req.condition_id,
        free_text=req.free_text,
    )

    repo.create_initial(
        runtime_id=runtime_id,
        ruleset_hash=ruleset_hash,
        state_dict=runtime_state.to_dict(),
    )

    return InitResponse(
        runtime_id=runtime_id,
        version=1,
        client_state=client_state,
    )


@app.post("/form/update")
async def form_update(req: UpdateRequest):
    try:
        row = repo.get_latest(req.runtime_id)
    except RuntimeStateNotFound:
        raise UNKNOWN_RUNTIME_ID()
    except SessionClosed:
        raise SESSION_CLOSED()

    runtime_state = RuntimeState.from_dict(row["state_json"])
    ruleset_hash = row["ruleset_hash"]

    (
        new_state,
        new_client_state,
        safety_messages,
    ) = apply_update_and_evaluate(
        runtime_state=runtime_state,
        answers=req.answers,
    )

    try:
        new_version = repo.insert_new_version(
            runtime_id=req.runtime_id,
            base_version=req.base_version,
            ruleset_hash=ruleset_hash,
            state_dict=new_state.to_dict(),
        )
    except VersionConflict:
        raise VERSION_CONFLICT()

    return UpdateResponse(
        runtime_id=req.runtime_id,
        version=new_version,
        client_state=new_client_state,
        safety_messages=safety_messages,
    )


@app.post("/form/finish")
async def form_finish(req: FinishRequest):
    try:
        row = repo.get_latest(req.runtime_id)
    except RuntimeStateNotFound:
        raise UNKNOWN_RUNTIME_ID()
    except SessionClosed:
        raise SESSION_CLOSED()

    if row["version"] != req.version:
        raise VERSION_CONFLICT()

    runtime_state = RuntimeState.from_dict(row["state_json"])

    submission_id = finish_runtime_state(runtime_state)

    repo.close_session(req.runtime_id, req.version)

    return FinishResponse(submission_id=submission_id)

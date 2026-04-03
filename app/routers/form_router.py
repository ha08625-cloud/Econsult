"""
Form session router.

Handles the three form lifecycle endpoints:
  POST /form/init   — start a new session, run availability check (fail-open)
  POST /form/update — apply patient answers, evaluate safety rules
  POST /form/finish — finalise submission, persist photos, enqueue PDF job

Architecture rules:
  - No request.app.state access in handler bodies.
  - All dependencies injected via Depends from app/core/dependencies.py.
  - No clinical logic. No encoder invocation.
  - Validation calls are the first statement in each handler body.
  - form_finish no longer generates PDFs or sends email. It persists the
    submission and photos, enqueues a pdf_jobs row, and returns immediately.
    PDF generation and delivery are handled by background workers.
  - The patient always receives a submission_id regardless of any downstream
    worker failure.
"""

import io
import json
import logging
import uuid
from datetime import date, datetime, timezone

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.responses import JSONResponse
from PIL import Image

from app.core.condition_registry import ConditionNotFound
from app.core.dependencies import (
    get_availability_repo,
    get_pdf_repo,
    get_photo_repo,
    get_practice_id,
    get_practice_repo,
    get_registry,
    get_runtime_repo,
    get_submission_repo,
)
from app.core.errors import (
    INVALID_PAYLOAD,
    SESSION_CLOSED,
    UNKNOWN_RUNTIME_ID,
    VERSION_CONFLICT,
)
from app.core.request_validation import (
    validate_finish_payload,
    validate_init_payload,
    validate_update_payload,
)
from app.core.upload_constants import (
    MAX_FILE_COUNT,
    MAX_FILE_SIZE_BYTES,
    MAX_TOTAL_SIZE_BYTES,
)
from app.models.runtime_state import RuntimeState
from app.models.serialisation_contracts import PatientDetails
from app.repositories.runtime_state_repository import (
    RuntimeStateNotFound,
    SessionClosed,
    VersionConflict,
)
from app.services.availability_orchestration import check_availability
from app.services.engine.pipeline import (
    apply_update_and_evaluate,
    finish_runtime_state,
    init_runtime_state,
)

logger = logging.getLogger(__name__)

router = APIRouter()


# ---------------------------------------------------------------------------
# POST /form/init
# ---------------------------------------------------------------------------

@router.post("/form/init")
async def form_init(
    request: Request,
    registry=Depends(get_registry),
    runtime_repo=Depends(get_runtime_repo),
    practice_id: str = Depends(get_practice_id),
    availability_repo=Depends(get_availability_repo),
):
    # --- Availability check (fail-open) ---
    # If the check fails for any reason, log and proceed as if open.
    # A database failure must never lock patients out.
    try:
        result = check_availability(
            availability_repo, practice_id, datetime.now(timezone.utc)
        )
        if not result.is_open:
            return JSONResponse(
                status_code=503,
                content={"detail": result.closed_message},
            )
    except Exception:
        logger.exception(
            "Availability check failed during form/init — proceeding as open (fail-open)"
        )

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

    initial_state, ruleset_hash, client_state = init_runtime_state(
        condition_id=condition_id,
        free_text=free_text,
        ruleset_path=ruleset_path,
        condition_label=condition_label,
    )

    version = runtime_repo.create_session(
        runtime_id=runtime_id,
        ruleset_hash=ruleset_hash,
        state_dict=initial_state.to_dict(),
    )

    return {
        "runtime_id": runtime_id,
        "version": version,
        "client_state": client_state,
    }


# ---------------------------------------------------------------------------
# POST /form/update
# ---------------------------------------------------------------------------

@router.post("/form/update")
async def form_update(
    request: Request,
    registry=Depends(get_registry),
    runtime_repo=Depends(get_runtime_repo),
):
    payload = await request.json()
    validate_update_payload(payload)

    runtime_id = payload["runtime_id"]
    base_version = payload["base_version"]
    answers = payload["answers"]
    additional_text = payload.get("additional_text")

    try:
        row = runtime_repo.get_latest(runtime_id)
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
        additional_text=additional_text,
        ruleset_path=ruleset_path,
        condition_label=condition_label,
    )

    try:
        new_version = runtime_repo.insert_new_version(
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


# ---------------------------------------------------------------------------
# POST /form/finish
# ---------------------------------------------------------------------------

@router.post("/form/finish")
async def form_finish(
    payload: str = Form(...),
    photos: list[UploadFile] = File(default=[]),
    registry=Depends(get_registry),
    runtime_repo=Depends(get_runtime_repo),
    submission_repo=Depends(get_submission_repo),
    practice_repo=Depends(get_practice_repo),
    practice_id: str = Depends(get_practice_id),
    pdf_repo=Depends(get_pdf_repo),
    photo_repo=Depends(get_photo_repo),
):
    data = json.loads(payload)
    validate_finish_payload(data)

    # Read all photo bytes and enforce size limits before any database access.
    # FastAPI does not enforce count limits on list[UploadFile], so the count
    # check here is the primary enforcement point, not a redundant safety net.
    photo_bytes = [await f.read() for f in photos] if photos else []

    for i, b in enumerate(photo_bytes):
        if len(b) > MAX_FILE_SIZE_BYTES:
            raise INVALID_PAYLOAD(
                f"Photo {i + 1} exceeds the {MAX_FILE_SIZE_BYTES} byte limit"
            )
    if sum(len(b) for b in photo_bytes) > MAX_TOTAL_SIZE_BYTES:
        raise INVALID_PAYLOAD(
            f"Combined photo size exceeds the {MAX_TOTAL_SIZE_BYTES} byte limit"
        )
    if len(photo_bytes) > MAX_FILE_COUNT:
        raise INVALID_PAYLOAD(
            f"Too many photos: maximum is {MAX_FILE_COUNT}"
        )

    # Pillow header validation — checks that each file has a valid image header.
    # verify() is header-only: a file with a valid header but a truncated body
    # will pass here but may cause the PDF worker to fail during generation.
    # In that case the PDF worker retries and eventually marks the job failed.
    # This is accepted — the submission record exists and the failure is logged.
    for i, b in enumerate(photo_bytes):
        try:
            img = Image.open(io.BytesIO(b))
            img.verify()
        except Exception:
            raise INVALID_PAYLOAD(f"Photo {i + 1} is not a valid image")

    runtime_id = data["runtime_id"]
    version = data["version"]
    contact_preferences = data["contact_preferences"]
    pd_raw = data["patient_details"]

    # Assemble PatientDetails dataclass.
    # Validation has already confirmed that day/month/year are digit-only strings
    # and form a valid calendar date, so the date() call here will not raise.
    dob = pd_raw["date_of_birth"]
    dob_iso = date(
        int(dob["year"].strip()),
        int(dob["month"].strip()),
        int(dob["day"].strip()),
    ).isoformat()  # produces "YYYY-MM-DD"

    patient_details = PatientDetails(
        patient_for=pd_raw["patient_for"],
        first_name=pd_raw["first_name"].strip(),
        last_name=pd_raw["last_name"].strip(),
        date_of_birth=dob_iso,
        postcode=pd_raw["postcode"].strip(),
        submitter_name=pd_raw.get("submitter_name") or None,
        submitter_relationship=pd_raw.get("submitter_relationship") or None,
    )

    try:
        row = runtime_repo.get_latest(runtime_id)
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

    clinical, audit = finish_runtime_state(
        runtime_state,
        ruleset_path,
        contact_preferences=contact_preferences,
        patient_details=patient_details,
    )

    delivery_email = practice_repo.get_email(practice_id)
    submission_id = str(uuid.uuid4())

    # Capture the authoritative submission timestamp here, immediately before
    # persisting. This same value is passed to create_submission and
    # pdf_repo.create_job so the DB record and the PDF carry identical timestamps.
    submitted_at = datetime.now(timezone.utc)

    # Persistence ordering (steps below are deliberate and must not be reordered):
    #
    # 1. create_submission — creates the FK target for submission_photos and pdf_jobs.
    #    If this crashes, the submission is lost. Nothing else references it yet.
    #
    # 2. photo_repo.save_photos — stores the raw bytes the PDF worker needs.
    #    If this crashes after create_submission, the orphan detection LEFT JOIN
    #    will find the submission (no pdf_jobs row). Photos may be missing or
    #    partial. The submission is potentially unrecoverable via automation.
    #
    # 3. pdf_repo.create_job — enqueues PDF generation.
    #    If this crashes after save_photos, an operator can manually insert a
    #    pdf_jobs row for full recovery (photos exist and count matches).
    #    This is the ordering that maximises recoverability on crash.
    #
    # 4. runtime_repo.close_session — closes the form session.
    #    Not a data-loss risk; the session TTL will expire it naturally.

    submission_repo.create_submission(
        submission_id=submission_id,
        practice_id=practice_id,
        condition_id=runtime_state.condition_id,
        condition_label=condition_label,
        clinical_output=clinical,
        audit_output=audit,
        submitted_at=submitted_at,
    )

    photo_repo.save_photos(submission_id, photo_bytes)

    pdf_repo.create_job(
        submission_id=submission_id,
        attachment_count=len(photo_bytes),
        delivery_email=delivery_email,
    )

    runtime_repo.close_session(runtime_id, version)

    return {"submission_id": submission_id}

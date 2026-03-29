"""
Form session router.

Handles the three form lifecycle endpoints:
  POST /form/init   — start a new session, run availability check (fail-open)
  POST /form/update — apply patient answers, evaluate safety rules
  POST /form/finish — finalise submission, persist, deliver

Architecture rules:
  - No request.app.state access in handler bodies.
  - All dependencies injected via Depends from app/core/dependencies.py.
  - No clinical logic. No encoder invocation.
  - Validation calls are the first statement in each handler body.
  - Delivery is delegated to delivery_orchestration.attempt_delivery.
    Any exception from attempt_delivery is caught, logged at CRITICAL,
    and swallowed — the patient always receives their submission_id.
"""

import json
import logging
import uuid
from datetime import date, datetime, timezone

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.responses import JSONResponse

from app.core.condition_registry import ConditionNotFound
from app.core.dependencies import (
    get_availability_repo,
    get_attachment_repo,
    get_delivery_service,
    get_practice_id,
    get_practice_name,
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
from app.services.delivery.delivery_orchestration import attempt_delivery
from app.services.engine.pipeline import (
    apply_update_and_evaluate,
    finish_runtime_state,
    init_runtime_state,
)
from app.utils.pdf_formatter import generate_pdf

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
    except ConditionNotFound:
        raise INVALID_PAYLOAD(f"Unknown condition_id: {condition_id}")

    runtime_id = str(uuid.uuid4())

    initial_state, client_state = init_runtime_state(
        condition_id=condition_id,
        free_text=free_text,
        ruleset_path=ruleset_path,
    )

    ruleset_hash = registry.get_ruleset_hash(condition_id)

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
    attachment_repo=Depends(get_attachment_repo),
    practice_repo=Depends(get_practice_repo),
    practice_id: str = Depends(get_practice_id),
    practice_name: str = Depends(get_practice_name),
    delivery_service=Depends(get_delivery_service),
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

    runtime_id = data["runtime_id"]
    version = data["version"]
    contact_preferences = data["contact_preferences"]
    pd_raw = data["patient_details"]

    # Assemble PatientDetails dataclass.
    # Validation has already confirmed that day/month/year are digit-only strings
    # and form a valid calendar date, so the date() call here will not raise.
    # The router's responsibility is assembly into the domain type; date formatting
    # for human display happens later in delivery_service.py.
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
    # persisting. This same value is passed to both create_submission and
    # send_clinical_output so the DB record and the delivered output are
    # guaranteed to carry identical timestamps.
    submitted_at = datetime.now(timezone.utc)

    submission_repo.create_submission(
        submission_id=submission_id,
        practice_id=practice_id,
        condition_id=runtime_state.condition_id,
        condition_label=condition_label,
        clinical_output=clinical,
        audit_output=audit,
        delivery_email=delivery_email,
        submitted_at=submitted_at,
        attachment_count=len(photo_bytes),
    )

    # Generate PDF once at submission time. This is the canonical delivery
    # artifact — it is stored in submission_attachments and sent as-is on
    # every delivery attempt (including retries). It must never be regenerated.
    # photo_bytes will be passed here in Step 3 when pdf_formatter is updated.
    pdf_bytes = generate_pdf(
        condition_label=condition_label,
        clinical_output=clinical,
        submission_id=submission_id,
        submitted_at=submitted_at,
        practice_name=practice_name,
    )
    attachment_repo.save_attachment(submission_id, pdf_bytes)

    # Delivery is delegated to the orchestration layer. Any exception —
    # whether from SMTP failure, attachment retrieval, or a repository bug —
    # is caught and logged at CRITICAL. The patient always receives their
    # submission_id. The submission and attachment are already persisted.
    try:
        attempt_delivery(
            submission_id=submission_id,
            submission_repo=submission_repo,
            attachment_repo=attachment_repo,
            delivery_service=delivery_service,
        )
    except Exception:
        logger.critical(
            "Delivery orchestration failed for submission %s. "
            "The submission is persisted but delivery status may be inconsistent. "
            "Investigate immediately.",
            submission_id,
            exc_info=True,
        )

    runtime_repo.close_session(runtime_id, version)

    return {"submission_id": submission_id}
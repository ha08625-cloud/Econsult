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

import json
import logging
import uuid
from dataclasses import replace
from datetime import UTC, date, datetime
from decimal import Decimal

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.responses import JSONResponse

from app.core.body_capture import BodyCapturingRoute, read_json_body
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
    ConditionNotFound,
)
from app.core.max_body_size_route import MaxBodySizeRoute
from app.core.rate_limit import limiter
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
from app.services.admin.availability_orchestration import check_availability
from app.services.engine.form_logic import AnswerValidationError
from app.services.engine.pipeline import (
    apply_update_and_evaluate,
    finish_runtime_state,
    init_runtime_state,
)
from app.utils.image_sanitizer import ImageTooLargeError, sanitize_image

logger = logging.getLogger(__name__)

# form_init and form_update read a JSON body via read_json_body(request), which
# requires route_class=BodyCapturingRoute. form_finish is exempt (D9): capturing
# the raw body of a multipart upload would double-buffer up to ~6.3 MB of photo
# data alongside FastAPI's own parsed Form/File data. It instead uses
# MaxBodySizeRoute (a Content-Length pre-check, not a body-capturing one) and
# is mounted into `router` below so main.py's single `include_router(form_router)`
# still picks up all three routes.
router = APIRouter(route_class=MaxBodySizeRoute)
_body_capturing_router = APIRouter(route_class=BodyCapturingRoute)

_VALID_TIERS = {"high", "standard"}


def _sanitize_photos(photo_bytes: list[bytes], tier: str) -> list[bytes]:
    """
    Sanitize each photo via sanitize_image, translating failures to HTTPException.

    Called directly from form_finish, itself a plain `def` dispatched onto the
    anyio threadpool — the CDR passes (up to three full decode/resize/re-encode
    cycles per photo at the "high" tier) are CPU-bound and can take seconds. It
    deliberately raises HTTPException despite looking otherwise pure: this is
    safe because exceptions raised on a threadpool worker propagate back to the
    caller unchanged.
    """
    sanitized = []
    for i, b in enumerate(photo_bytes):
        try:
            sanitized.append(sanitize_image(b, tier=tier))
        except ImageTooLargeError as exc:
            raise INVALID_PAYLOAD(str(exc)) from None
        except ValueError:
            raise INVALID_PAYLOAD(f"Photo {i + 1} is not a valid image") from None
    return sanitized


# ---------------------------------------------------------------------------
# POST /form/init
# ---------------------------------------------------------------------------


@_body_capturing_router.post("/form/init")
@limiter.limit("30/minute")
def form_init(
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
        result = check_availability(availability_repo, practice_id, datetime.now(UTC))
        if not result.is_open:
            return JSONResponse(
                status_code=503,
                content={"detail": result.closed_message},
            )
    except Exception:
        logger.exception(
            "Availability check failed during form/init — proceeding as open (fail-open)"
        )

    payload = read_json_body(request)
    validate_init_payload(payload)

    condition_id = payload["condition_id"]
    free_text = payload.get("free_text")

    try:
        ruleset_path = registry.get_ruleset_path(condition_id)
        condition_label = registry.get_presentation(condition_id)["label"]
    except ConditionNotFound:
        raise INVALID_PAYLOAD(f"Unknown condition_id: {condition_id}") from None

    runtime_id = str(uuid.uuid4())

    initial_state, ruleset_hash, client_state = init_runtime_state(
        condition_id=condition_id,
        free_text=free_text,
        ruleset_path=ruleset_path,
        condition_label=condition_label,
    )

    runtime_repo.create_initial(
        runtime_id=runtime_id,
        ruleset_hash=ruleset_hash,
        state_dict=initial_state.to_dict(),
    )
    version = 1

    return {
        "runtime_id": runtime_id,
        "version": version,
        "client_state": client_state,
    }


# ---------------------------------------------------------------------------
# POST /form/update
# ---------------------------------------------------------------------------


@_body_capturing_router.post("/form/update")
@limiter.limit("30/minute")
def form_update(
    request: Request,
    registry=Depends(get_registry),
    runtime_repo=Depends(get_runtime_repo),
):
    # Parse with parse_float=Decimal (json.loads(..., parse_float=...) has no
    # equivalent via request.json()) so Number answers arrive as exact Decimals
    # rather than lossy floats. The only float-bearing field in this payload is
    # "answers"; runtime_id and additional_text are strings and base_version is
    # an integer token.
    payload = read_json_body(request, parse_float=Decimal)
    validate_update_payload(payload)

    runtime_id = payload["runtime_id"]
    base_version = payload["base_version"]
    answers = payload["answers"]
    additional_text = payload.get("additional_text")

    try:
        row = runtime_repo.get_latest(runtime_id)
    except RuntimeStateNotFound:
        raise UNKNOWN_RUNTIME_ID() from None
    except SessionClosed:
        raise SESSION_CLOSED() from None

    runtime_state = RuntimeState.from_dict(row["state_json"])
    current_ruleset_hash = row["ruleset_hash"]

    try:
        ruleset_path = registry.get_ruleset_path(runtime_state.condition_id)
        condition_label = registry.get_presentation(runtime_state.condition_id)["label"]
    except ConditionNotFound:
        raise INVALID_PAYLOAD(f"Unknown condition_id: {runtime_state.condition_id}") from None

    try:
        new_state, new_client_state, safety_messages = apply_update_and_evaluate(
            runtime_state=runtime_state,
            answers=answers,
            additional_text=additional_text,
            ruleset_path=ruleset_path,
            condition_label=condition_label,
        )
    except AnswerValidationError as exc:
        # A submitted answer failed type/precision validation. Translate the
        # core exception to a 422 here at the boundary. Catching the subclass
        # specifically means a plain ValueError raised deeper in the pipeline
        # (e.g. load_ruleset) still surfaces as a logged 500, not a 422.
        raise INVALID_PAYLOAD(str(exc)) from None

    try:
        new_version = runtime_repo.insert_new_version(
            runtime_id=runtime_id,
            base_version=base_version,
            ruleset_hash=current_ruleset_hash,
            state_dict=new_state.to_dict(),
        )
    except VersionConflict:
        raise VERSION_CONFLICT() from None

    return {
        "runtime_id": runtime_id,
        "version": new_version,
        "client_state": new_client_state,
        "safety_messages": [{"rule_id": m.rule_id, "message": m.message} for m in safety_messages],
    }


# ---------------------------------------------------------------------------
# POST /form/finish
# ---------------------------------------------------------------------------


@router.post("/form/finish")
@limiter.limit("30/minute")
def form_finish(
    request: Request,
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

    # Count check runs before any bytes are read. FastAPI does not enforce
    # count limits on list[UploadFile], and reading N files into memory only
    # to reject the request on count afterwards defeats the point of a count
    # limit -- this is the primary enforcement point, not a redundant safety net.
    if len(photos) > MAX_FILE_COUNT:
        raise INVALID_PAYLOAD(f"Too many photos: maximum is {MAX_FILE_COUNT}")

    # Read all photo bytes and enforce size limits before any database access.
    photo_bytes = [f.file.read() for f in photos] if photos else []

    for i, b in enumerate(photo_bytes):
        if len(b) > MAX_FILE_SIZE_BYTES:
            raise INVALID_PAYLOAD(f"Photo {i + 1} exceeds the {MAX_FILE_SIZE_BYTES} byte limit")
    if sum(len(b) for b in photo_bytes) > MAX_TOTAL_SIZE_BYTES:
        raise INVALID_PAYLOAD(f"Combined photo size exceeds the {MAX_TOTAL_SIZE_BYTES} byte limit")

    # Tier validation.
    #
    # photo_quality_tier is validated here rather than in validate_finish_payload
    # because the conditional requirement — tier is required when photos are
    # present — spans both the JSON payload and the multipart file list.
    # validate_finish_payload only sees the JSON; this handler sees both.
    #
    # When no photos are submitted, tier is accepted as None or absent and
    # ignored. When photos are present, tier must be one of the valid values.
    tier = data.get("photo_quality_tier")
    if photo_bytes and tier not in _VALID_TIERS:
        raise INVALID_PAYLOAD(
            f"photo_quality_tier must be one of {sorted(_VALID_TIERS)} when photos are included"
        )

    # Image CDR (Content Disarm and Reconstruction).
    #
    # Each uploaded image is fully decoded by Pillow and re-encoded as a clean
    # JPEG. The tier parameter controls the resize bounds and encode quality:
    #
    # - "high":     long edge 3840px (4K), quality 85, with a fallback
    #               iteration sequence if the initial encode exceeds 5 MB.
    # - "standard": long edge 1920px (1080p), quality 80. A single encode
    #               step — this combination reliably stays within 5 MB.
    #
    # CDR guarantees:
    # - Full decode: truncated or corrupt image bodies are rejected here rather
    #   than deferred to the PDF worker.
    # - Metadata stripping: EXIF, ICC profiles, and all other metadata are
    #   discarded. The output buffer is written from scratch.
    # - Format normalisation: output is always JPEG regardless of whether the
    #   input was JPEG or PNG.
    # - Structural polyglot defence: any payload embedded in regions Pillow
    #   ignores (e.g. appended after the JPEG EOI marker) is discarded during
    #   re-encoding.
    # - 5 MB output guarantee: the sanitizer either returns bytes within the
    #   EMIS limit or raises ImageTooLargeError with a user-facing message.
    #
    # The post-sanitization size checks below remain as defensive guards.
    # Re-encoding an already-compressed JPEG can marginally increase its size
    # in edge cases; these checks ensure the stored bytes invariant holds.
    effective_tier = tier if tier in _VALID_TIERS else "standard"
    photo_bytes = _sanitize_photos(photo_bytes, effective_tier)

    for i, b in enumerate(photo_bytes):
        if len(b) > MAX_FILE_SIZE_BYTES:
            raise INVALID_PAYLOAD(
                f"Photo {i + 1} exceeds the {MAX_FILE_SIZE_BYTES} byte limit after processing"
            )
    if sum(len(b) for b in photo_bytes) > MAX_TOTAL_SIZE_BYTES:
        raise INVALID_PAYLOAD(
            f"Combined photo size exceeds the {MAX_TOTAL_SIZE_BYTES} byte limit after processing"
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
        gender=pd_raw["gender"],
        preferred_name=pd_raw.get("preferred_name") or None,
        nhs_number=pd_raw.get("nhs_number") or None,
        submitter_name=pd_raw.get("submitter_name") or None,
        submitter_relationship=pd_raw.get("submitter_relationship") or None,
    )

    try:
        row = runtime_repo.get_latest(runtime_id)
    except RuntimeStateNotFound:
        raise UNKNOWN_RUNTIME_ID() from None
    except SessionClosed:
        raise SESSION_CLOSED() from None

    if row["version"] != version:
        raise VERSION_CONFLICT()

    runtime_state = RuntimeState.from_dict(row["state_json"])

    try:
        ruleset_path = registry.get_ruleset_path(runtime_state.condition_id)
        condition_label = registry.get_presentation(runtime_state.condition_id)["label"]
    except ConditionNotFound:
        raise INVALID_PAYLOAD(f"Unknown condition_id: {runtime_state.condition_id}") from None

    clinical, audit = finish_runtime_state(
        runtime_state,
        ruleset_path,
        contact_preferences=contact_preferences,
        patient_details=patient_details,
    )

    # Stamp the submission-level photo tier onto the audit record.
    #
    # finish_runtime_state() has no knowledge of the HTTP submission tier —
    # tier is a transport concern, not a clinical engine concern. We use
    # dataclasses.replace() to produce an augmented AuditOutput without
    # mutating the value returned by the pipeline.
    #
    # tier is None when no photos were submitted, which is the correct value
    # for a text-only submission.
    audit = replace(audit, photo_quality_tier=tier)

    delivery_email = practice_repo.get_email(practice_id)
    submission_id = str(uuid.uuid4())

    # Capture the authoritative submission timestamp here, immediately before
    # persisting. This same value is passed to create_submission and
    # pdf_repo.create_job so the DB record and the PDF carry identical timestamps.
    submitted_at = datetime.now(UTC)

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


router.include_router(_body_capturing_router)

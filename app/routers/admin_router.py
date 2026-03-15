"""
Admin API router.

All endpoints require a valid Bearer token via require_admin.
Prefix /admin and tag "admin" are applied when registered in main.py.

This module is responsible for:
- Signposting management per condition
- Admin condition list
- Availability configuration

This module must never import:
- Clinical engine modules (form_logic, safety_engine, encoder_mapping, etc.)
- presentation_service
- serialisation, projection, runtime_state
"""

import datetime
import logging

from fastapi import APIRouter, Request, Depends, HTTPException
from fastapi.responses import JSONResponse

from app.core.admin_context import AdminContext, require_admin
from app.core.condition_registry import ConditionNotFound
from app.repositories.practice_repository import InvalidSignpostingData, MAX_SIGNPOSTING_LENGTH
from app.services.availability_service import validate_availability_config

logger = logging.getLogger(__name__)

router = APIRouter()


def _normalise_signposting(value) -> str | None:
    """
    Normalise signposting for API responses.

    Returns None if value is None or an empty/whitespace-only string.
    Returns the string unchanged otherwise.

    Uses an explicit isinstance check rather than relying on Python
    truthiness so that the intent is clear and a future type change
    does not produce silent incorrect behaviour.
    """
    if not isinstance(value, str) or not value.strip():
        return None
    return value


# ---------------------------------------------------------------------------
# Condition list
# ---------------------------------------------------------------------------

@router.get("/conditions")
async def admin_list_conditions(
    request: Request,
    _: AdminContext = Depends(require_admin),
):
    """
    Return all condition IDs and labels.
    This is a raw administrative view, separate from the patient-facing endpoint.
    """
    registry = request.app.state.registry
    return {"conditions": registry.list_conditions()}


# ---------------------------------------------------------------------------
# Signposting
# ---------------------------------------------------------------------------

@router.get("/conditions/{condition_id}/signposting")
async def get_signposting(
    condition_id: str,
    request: Request,
    admin: AdminContext = Depends(require_admin),
):
    """
    Return current signposting for a condition.
    Returns {"condition_id": ..., "signposting": <html string or null>}.
    """
    registry = request.app.state.registry
    practice_repo = request.app.state.practice_repo

    if not registry.has_condition(condition_id):
        raise HTTPException(status_code=404, detail=f"Unknown condition: {condition_id}")

    html = practice_repo.get_signposting(admin.practice_id, condition_id)

    return {
        "condition_id": condition_id,
        "signposting": _normalise_signposting(html),
    }


@router.put("/conditions/{condition_id}/signposting")
async def put_signposting(
    condition_id: str,
    request: Request,
    admin: AdminContext = Depends(require_admin),
):
    """
    Set or clear signposting for a condition.

    Accepts: {"signposting": "<p>html string</p>"}

    The signposting value is always a string. Empty or whitespace-only
    content is treated as an instruction to clear signposting — the
    repository will delete any existing row rather than write empty content.

    Validation (in order):
    1. Body must be valid JSON
    2. signposting key must be present and must be a string
    3. Length must not exceed MAX_SIGNPOSTING_LENGTH characters

    The router catches InvalidSignpostingData from the repository and
    converts it to HTTP 400. This should only arise from the length check
    (the sanitiser raises it before nh3 runs). It never produces a 500
    from sanitisation failures.

    Returns {"condition_id": ..., "signposting": <sanitised html or null>}.
    A null response means the content was empty after sanitisation and no
    row was written.
    """
    registry = request.app.state.registry
    practice_repo = request.app.state.practice_repo

    if not registry.has_condition(condition_id):
        raise HTTPException(status_code=404, detail=f"Unknown condition: {condition_id}")

    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON body")

    if not isinstance(body, dict) or "signposting" not in body:
        raise HTTPException(
            status_code=400,
            detail='Body must be {"signposting": "..."}',
        )

    raw = body["signposting"]

    if not isinstance(raw, str):
        raise HTTPException(
            status_code=400,
            detail=f"signposting must be a string, got {type(raw).__name__}",
        )

    if len(raw) > MAX_SIGNPOSTING_LENGTH:
        raise HTTPException(
            status_code=400,
            detail=f"Signposting must not exceed {MAX_SIGNPOSTING_LENGTH} characters",
        )

    try:
        practice_repo.set_signposting(admin.practice_id, condition_id, raw)
    except InvalidSignpostingData as e:
        raise HTTPException(status_code=400, detail=str(e))

    saved = practice_repo.get_signposting(admin.practice_id, condition_id)

    return {
        "condition_id": condition_id,
        "signposting": _normalise_signposting(saved),
    }


@router.delete("/conditions/{condition_id}/signposting", status_code=204)
async def delete_signposting(
    condition_id: str,
    request: Request,
    admin: AdminContext = Depends(require_admin),
):
    """
    Remove all signposting for a condition.
    Idempotent: no error if nothing was configured.
    Returns 204 No Content.
    """
    registry = request.app.state.registry
    practice_repo = request.app.state.practice_repo

    if not registry.has_condition(condition_id):
        raise HTTPException(status_code=404, detail=f"Unknown condition: {condition_id}")

    practice_repo.delete_signposting(admin.practice_id, condition_id)


# ---------------------------------------------------------------------------
# Availability
# ---------------------------------------------------------------------------

@router.get("/availability")
async def get_availability(
    request: Request,
    admin: AdminContext = Depends(require_admin),
):
    """
    Return the raw availability configuration for the practice.

    Returns all columns from practice_availability as a dict.
    Does not call evaluate_availability — this is the admin view of the
    stored config, not the evaluated patient-facing result.
    """
    availability_repo = request.app.state.availability_repo
    config = availability_repo.get_availability(admin.practice_id)

    # Convert time objects to strings for JSON serialisation.
    config["open_time"] = config["open_time"].strftime("%H:%M")
    config["close_time"] = config["close_time"].strftime("%H:%M")

    return config


@router.put("/availability")
async def put_availability(
    request: Request,
    admin: AdminContext = Depends(require_admin),
):
    """
    Update the availability configuration.

    Accepts:
    {
        "is_active": true,
        "weekly_open_days": ["mon", "tue", "wed", "thu", "fri"],
        "open_time": "08:00",
        "close_time": "18:30",
        "closed_message": "The practice is now closed."
    }

    Validation:
    - All fields are required except closed_message (nullable).
    - weekly_open_days must contain only valid day abbreviations.
    - open_time and close_time must not be equal.

    Logs a warning if is_active is true and weekly_open_days is empty.
    Returns the updated config by fetching it back from the repository.
    """
    availability_repo = request.app.state.availability_repo

    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON body")

    if not isinstance(body, dict):
        raise HTTPException(status_code=400, detail="Body must be a JSON object")

    # --- Extract and type-check fields ---

    is_active = body.get("is_active")
    if not isinstance(is_active, bool):
        raise HTTPException(
            status_code=400,
            detail="is_active must be a boolean",
        )

    weekly_open_days = body.get("weekly_open_days")
    if not isinstance(weekly_open_days, list):
        raise HTTPException(
            status_code=400,
            detail="weekly_open_days must be a list",
        )
    if not all(isinstance(d, str) for d in weekly_open_days):
        raise HTTPException(
            status_code=400,
            detail="weekly_open_days must contain only strings",
        )

    open_time_str = body.get("open_time")
    close_time_str = body.get("close_time")
    if not isinstance(open_time_str, str) or not isinstance(close_time_str, str):
        raise HTTPException(
            status_code=400,
            detail="open_time and close_time must be strings in HH:MM format",
        )

    try:
        open_time = datetime.time.fromisoformat(open_time_str)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid open_time format: '{open_time_str}'. Expected HH:MM.",
        )

    try:
        close_time = datetime.time.fromisoformat(close_time_str)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid close_time format: '{close_time_str}'. Expected HH:MM.",
        )

    closed_message = body.get("closed_message")
    if closed_message is not None and not isinstance(closed_message, str):
        raise HTTPException(
            status_code=400,
            detail="closed_message must be a string or null",
        )

    # --- Validate via service layer ---

    try:
        validate_availability_config(
            weekly_open_days=weekly_open_days,
            open_time=open_time,
            close_time=close_time,
            closed_message=closed_message,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # --- Persist ---

    availability_repo.set_availability(
        practice_id=admin.practice_id,
        is_active=is_active,
        weekly_open_days=weekly_open_days,
        open_time=open_time,
        close_time=close_time,
        closed_message=closed_message,
    )

    # --- Log warning for empty-days misconfiguration ---

    if is_active and not weekly_open_days:
        logger.warning(
            "Practice '%s': is_active=true with no weekly_open_days. "
            "The form will be closed to patients every day.",
            admin.practice_id,
        )

    # --- Return updated config ---

    updated = availability_repo.get_availability(admin.practice_id)
    updated["open_time"] = updated["open_time"].strftime("%H:%M")
    updated["close_time"] = updated["close_time"].strftime("%H:%M")

    return updated

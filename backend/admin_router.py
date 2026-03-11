"""
Admin API router.

All endpoints require a valid Bearer token via require_admin.
Prefix /admin and tag "admin" are applied when registered in main.py.

This module is responsible for:
- Signposting management per condition
- Admin condition list

This module must never import:
- Clinical engine modules (form_logic, safety_engine, encoder_mapping, etc.)
- presentation_service
- serialisation, projection, runtime_state
"""

from fastapi import APIRouter, Request, Depends, HTTPException
from fastapi.responses import JSONResponse

from admin_context import AdminContext, require_admin
from condition_registry import ConditionNotFound
from practice_repository import InvalidSignpostingData, MAX_SIGNPOSTING_LENGTH

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
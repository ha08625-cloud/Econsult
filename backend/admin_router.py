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

router = APIRouter()


def _normalise_signposting(items) -> list | None:
    """
    Normalise signposting for API responses.
    Empty list and None both become None — nothing to display.
    """
    if not items:
        return None
    return items


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
    Returns signposting: null if nothing is configured or list is empty.
    """
    registry = request.app.state.registry
    practice_repo = request.app.state.practice_repo

    if not registry.has_condition(condition_id):
        raise HTTPException(status_code=404, detail=f"Unknown condition: {condition_id}")

    items = practice_repo.get_signposting(admin.practice_id, condition_id)

    return {
        "condition_id": condition_id,
        "signposting": _normalise_signposting(items),
    }


@router.put("/conditions/{condition_id}/signposting")
async def put_signposting(
    condition_id: str,
    request: Request,
    admin: AdminContext = Depends(require_admin),
):
    """
    Replace the signposting list for a condition.

    Accepts: {"signposting": ["item 1", "item 2"]}

    Validation:
    - signposting key must be present and a list
    - each item must be a string
    - each item must be non-empty after stripping whitespace
    - empty list is valid (explicit "no signposting")

    Strips whitespace from each item before writing.
    Stores the stripped list (including empty list) in the database.
    Normalises empty list to null only in the response.
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
        raise HTTPException(status_code=400, detail="Body must be {\"signposting\": [...]}")

    raw_items = body["signposting"]

    if not isinstance(raw_items, list):
        raise HTTPException(status_code=400, detail="signposting must be a list")

    stripped = []
    for i, item in enumerate(raw_items):
        if not isinstance(item, str):
            raise HTTPException(
                status_code=400,
                detail=f"Item {i} must be a string, got {type(item).__name__}",
            )
        clean = item.strip()
        if not clean:
            raise HTTPException(
                status_code=400,
                detail=f"Item {i} is empty or whitespace-only after stripping",
            )
        stripped.append(clean)

    practice_repo.set_signposting(admin.practice_id, condition_id, stripped)

    return {
        "condition_id": condition_id,
        "signposting": _normalise_signposting(stripped),
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

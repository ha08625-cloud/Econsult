"""
Public HTTP router.

Unauthenticated, read-only endpoints served before a form session begins.
No clinical logic. No session state.

Endpoints:
- GET /conditions
- GET /conditions/{condition_id}/presentation
- GET /availability
- GET /safety-warning

All dependencies are injected via Depends from app.core.dependencies.
No handler body accesses request.app.state directly.

Error handling:
- ConditionNotFound propagates to the exception handler registered in main.py,
  which returns HTTP 404. The inline JSONResponse construction previously in
  main.py has been removed.
- Any availability repository exception propagates and FastAPI returns HTTP 500.
  The frontend treats any non-200 availability response as fail-open.

This router is registered with no prefix in main.py so all routes sit at root.
"""

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends

from app.core.condition_registry import ConditionNotFound
from app.core.dependencies import (
    get_availability_repo,
    get_practice_id,
    get_presentation_service,
    get_registry,
)
from app.services.availability_orchestration import check_availability

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/safety-warning")
async def get_safety_warning(
    presentation_service=Depends(get_presentation_service),
):
    return {"universal_safety_warning": presentation_service.get_universal_safety_warning()}


@router.get("/conditions")
async def list_conditions(
    registry=Depends(get_registry),
):
    return {"conditions": registry.list_conditions()}


@router.get("/conditions/{condition_id}/presentation")
async def get_presentation(
    condition_id: str,
    presentation_service=Depends(get_presentation_service),
    practice_id: str = Depends(get_practice_id),
):
    # ConditionNotFound propagates to the handler registered in main.py -> 404.
    return presentation_service.get_patient_presentation(condition_id, practice_id)


@router.get("/availability")
async def get_availability(
    availability_repo=Depends(get_availability_repo),
    practice_id: str = Depends(get_practice_id),
):
    """
    Evaluate and return current availability for patients.

    Returns {"is_open": bool, "closed_message": str|null, "after_hours_notice": str|null}.

    If the database raises an exception, the exception propagates and FastAPI
    returns HTTP 500. The frontend treats any non-200 as fail-open.
    """
    result = check_availability(availability_repo, practice_id, datetime.now(timezone.utc))
    return {
        "is_open": result.is_open,
        "closed_message": result.closed_message,
        "after_hours_notice": result.after_hours_notice,
    }
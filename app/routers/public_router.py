"""
Public HTTP router.

Unauthenticated, read-only endpoints served before a form session begins.
No clinical logic. No session state.

Endpoints:
- GET /conditions
- GET /conditions/{condition_id}/presentation
- GET /availability
- GET /safety-warning
- GET /practice
- GET /doctors

All dependencies are injected via Depends from app.core.dependencies.
No handler body accesses request.app.state directly.

Error handling:
- ConditionNotFound propagates to the exception handler registered in main.py,
  which returns HTTP 404. The inline JSONResponse construction previously in
  main.py has been removed.
- Any availability repository exception propagates and FastAPI returns HTTP 500.
  The frontend treats any non-200 availability response as fail-open.
- GET /practice returns HTTP 500 if the practice record is not found. This should
  never happen in a correctly configured deployment — startup validation seeds and
  validates the practice record before any request is served.
- GET /doctors never returns an error for a missing or empty list. An empty list
  is the correct response when no doctors are configured. The frontend treats an
  empty list as "no list configured" and falls back to free text entry.

This router is registered with no prefix in main.py so all routes sit at root.
"""

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request

from app.core.errors import ConditionNotFound
from app.core.dependencies import (
    get_availability_repo,
    get_practice_id,
    get_practice_repo,
    get_presentation_service,
    get_registry,
)
from app.core.rate_limit import limiter
from app.services.admin.availability_orchestration import check_availability

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/safety-warning")
@limiter.limit("30/minute")
async def get_safety_warning(
    request: Request,
    presentation_service=Depends(get_presentation_service),
):
    return {"universal_safety_warning": presentation_service.get_universal_safety_warning()}


@router.get("/conditions")
@limiter.limit("30/minute")
async def list_conditions(
    request: Request,
    registry=Depends(get_registry),
):
    return {"conditions": registry.list_conditions()}


@router.get("/conditions/{condition_id}/presentation")
@limiter.limit("30/minute")
async def get_presentation(
    request: Request,
    condition_id: str,
    presentation_service=Depends(get_presentation_service),
    practice_id: str = Depends(get_practice_id),
):
    # ConditionNotFound propagates to the handler registered in main.py -> 404.
    return presentation_service.get_patient_presentation(condition_id, practice_id)


@router.get("/availability")
@limiter.limit("30/minute")
async def get_availability(
    request: Request,
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


@router.get("/practice")
@limiter.limit("30/minute")
async def get_practice(
    request: Request,
    practice_repo=Depends(get_practice_repo),
    practice_id: str = Depends(get_practice_id),
):
    """
    Return the practice name for the current deployment.

    Used by the frontend to display the practice name in the page header.
    Returns {"practice_name": str}.

    Returns HTTP 500 if the practice record is not found. A missing practice at
    request time is a server misconfiguration — startup validation guarantees the
    record exists before the server accepts traffic.
    """
    practice = practice_repo.get_practice(practice_id)
    if practice is None:
        logger.error("Practice not found at request time: %s", practice_id)
        raise HTTPException(status_code=500, detail="Practice record not found")
    return {"practice_name": practice["name"]}


@router.get("/doctors")
@limiter.limit("30/minute")
async def get_doctors(
    request: Request,
    practice_repo=Depends(get_practice_repo),
    practice_id: str = Depends(get_practice_id),
):
    """
    Return the doctor list for the practice.

    Used by the patient Contact screen to populate the doctor dropdown.
    Returns {"doctors": ["Dr Smith", "Dr Jones", ...]} in display order.
    Returns {"doctors": []} if no doctors are configured — never an error.

    The frontend treats an empty list as "no list configured" and falls back
    to a free text field. Any exception from the repository propagates and
    FastAPI returns HTTP 500; the frontend must treat any non-200 as an empty
    list and fall back to free text without showing an error to the patient.
    """
    doctors = practice_repo.get_doctors(practice_id)
    return {"doctors": doctors}
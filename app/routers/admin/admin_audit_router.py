"""
Admin Audit Log API router.

Exposes a single paginated read-only endpoint for querying the audit trail.
All mutating admin actions and auth events are written to this log by the
other sub-routers; this router only reads.

All endpoints require a valid session cookie via require_admin.
"""

import datetime

from fastapi import APIRouter, Depends, HTTPException, Request

from app.core.admin_context import AdminContext, require_admin
from app.core.dependencies import get_audit_repo
from app.core.errors import INVALID_DATE_FORMAT

router = APIRouter()


@router.get("/audit-log")
async def get_audit_log(
    request: Request,
    admin: AdminContext = Depends(require_admin),
    audit_repo=Depends(get_audit_repo),
    cursor: str | None = None,
    from_date: str | None = None,
    to_date: str | None = None,
    actor: str | None = None,
    action: str | None = None,
    limit: int = 50,
):
    """
    Return a paginated list of audit events for this practice.

    Query parameters:
        cursor      Opaque pagination token from a previous response's
                    next_cursor field. Omit to start from the most recent
                    event. Discard when changing any filter.
        from_date   Inclusive start date, YYYY-MM-DD. Applied at 00:00:00 UTC.
        to_date     Inclusive end date, YYYY-MM-DD. Applied at 23:59:59 UTC.
        actor       Exact match on actor_email.
        action      Left-anchored prefix match on action, e.g. "availability"
                    matches "availability.config.updated". Must be lowercase
                    letters, digits, dots, and underscores only.
        limit       Page size. Default 50, max 200. Values outside this
                    range are clamped server-side rather than rejected.

    Response:
        {
            "events": [...],
            "next_cursor": "<opaque string> | null"
        }

    next_cursor is null when the client has reached the end of the result
    set. Pass it back as ?cursor= on the next request to load the next page.

    Each event contains: id, occurred_at (ISO 8601), practice_id,
    actor_email, action, resource, detail, ip_address, session_id.

    Returns 400 if the cursor is malformed or the action prefix is invalid.
    Returns 422 if from_date or to_date cannot be parsed as YYYY-MM-DD.

    All admins may access this endpoint. It is read-only and contains no
    patient-confidential information.
    """
    # Parse date strings. Return 422 on invalid format — same status used
    # for other input validation errors in this router.
    parsed_from_date = None
    if from_date is not None:
        try:
            parsed_from_date = datetime.date.fromisoformat(from_date)
        except ValueError:
            raise INVALID_DATE_FORMAT("from_date", from_date) from None

    parsed_to_date = None
    if to_date is not None:
        try:
            parsed_to_date = datetime.date.fromisoformat(to_date)
        except ValueError:
            raise INVALID_DATE_FORMAT("to_date", to_date) from None

    # Clamp limit. Do not reject out-of-range values — just apply the bounds
    # silently. This avoids a class of client breakage if limits drift over time.
    limit = max(1, min(limit, 200))

    try:
        result = audit_repo.list_events(
            practice_id=admin.practice_id,
            cursor=cursor,
            from_date=parsed_from_date,
            to_date=parsed_to_date,
            actor=actor,
            action_prefix=action,
            limit=limit,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    # Serialise datetime fields. psycopg2 returns occurred_at as a Python
    # datetime object; JSON serialisation requires a string.
    events = []
    for row in result["events"]:
        serialised = dict(row)
        if isinstance(serialised.get("occurred_at"), datetime.datetime):
            serialised["occurred_at"] = serialised["occurred_at"].isoformat()
        events.append(serialised)

    return {
        "events": events,
        "next_cursor": result["next_cursor"],
    }

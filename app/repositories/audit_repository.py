"""
app/repositories/audit_repository.py

Database access for the admin audit log.

Handles the admin_audit_log table created by migration 0015.

This module must never:
- Contain business logic or validation
- Import from service modules or routers
- Be called from the patient-facing request path

Two methods:
- log_event: insert a single audit event. Accepts an optional open
  psycopg2 connection so the caller can include the insert in an
  existing transaction. When conn is None, opens its own connection
  (standalone insert, appropriate for auth-only events with no
  paired mutation).
- list_events: paginated read for the GET /admin/audit-log endpoint.

# ---------------------------------------------------------------------------
# Action types and their detail shapes
# ---------------------------------------------------------------------------
#
# auth.code_requested
#   detail: { "email": str }
#
# auth.login.succeeded
#   detail: { "email": str }
#
# auth.login.failed
#   detail: { "email": str, "reason": str }
#
# auth.logout
#   detail: { "session_id": str }
#
# practice.email.updated
#   detail: { "before": str, "after": str }
#
# conditions.signposting.updated
#   detail: { "before": dict | None, "after": dict }
#
# conditions.signposting.deleted
#   detail: { "before": dict }
#
# doctors.updated
#   detail: { "before": list, "after": list }
#
# availability.config.updated
#   detail: { "before": dict, "after": dict }
#
# availability.override.updated
#   detail: { "before": dict | None, "after": dict }
#
# availability.override.deleted
#   detail: { "before": dict }
#
# availability.exception.created
#   detail: { "after": dict }
#
# availability.exception.updated
#   detail: { "before": dict, "after": dict }
#
# availability.exception.deleted
#   detail: { "before": dict }
#
# ---------------------------------------------------------------------------
# Cursor pagination
# ---------------------------------------------------------------------------
#
# list_events uses an opaque base64-encoded cursor that encodes both
# last_id and last_occurred_at. The WHERE clause uses a tuple comparison:
#
#   WHERE (occurred_at, id) < (:last_occurred_at, :last_id)
#
# This handles ties on timestamp correctly using id as a tiebreaker and
# remains stable if rows are inserted mid-pagination.
#
# The cursor and filter parameters are independent. The cursor says
# "start after this point"; filters say "only show matching rows".
# When the user changes a filter, the caller discards the cursor and
# issues a fresh query with cursor=None.
#
# ---------------------------------------------------------------------------
# IP address extraction
# ---------------------------------------------------------------------------
#
# _extract_ip reads X-Forwarded-For first (first hop only, to get the
# real client IP behind a proxy), then X-Real-IP, then falls back to
# request.client.host. Returns None if none of these are available.
# Callers pass request.headers and request.client to avoid importing
# FastAPI Request here.
"""

import base64
import json
import logging
import re
from datetime import date, datetime
from typing import Any, Optional

import psycopg2.extras
from psycopg2.extras import RealDictCursor

from app.core.db import get_conn

logger = logging.getLogger(__name__)

# Validates the action_prefix query parameter before building a LIKE clause.
# Permits only lowercase letters, digits, dots, and underscores.
_ACTION_PREFIX_RE = re.compile(r"^[a-z0-9_.]+$")

# Default and maximum page sizes for list_events.
_DEFAULT_LIMIT = 50
_MAX_LIMIT = 200


def _extract_ip(
    headers: dict,
    client_host: Optional[str],
) -> Optional[str]:
    """
    Extract the real client IP address from request headers.

    Reads X-Forwarded-For first (taking only the first value, which is
    the original client IP before any proxy hops), then X-Real-IP, then
    falls back to the direct connection host.

    headers should be a mapping that supports .get() — pass
    request.headers from FastAPI. client_host should be
    request.client.host or None.

    Returns None if no IP can be determined.
    """
    forwarded_for = headers.get("x-forwarded-for")
    if forwarded_for:
        # X-Forwarded-For may be a comma-separated list: "client, proxy1, proxy2"
        # The first entry is the original client IP.
        return forwarded_for.split(",")[0].strip()

    real_ip = headers.get("x-real-ip")
    if real_ip:
        return real_ip.strip()

    return client_host or None


def _encode_cursor(last_id: int, last_occurred_at: datetime) -> str:
    """
    Encode pagination state as an opaque base64 string.

    Encodes last_id (int) and last_occurred_at (ISO 8601 string with
    timezone) so the client can pass it back as ?cursor=<string>.
    The client must treat this value as opaque and never construct it
    manually.
    """
    payload = {
        "last_id": last_id,
        "last_occurred_at": last_occurred_at.isoformat(),
    }
    return base64.urlsafe_b64encode(json.dumps(payload).encode()).decode()


def _decode_cursor(cursor: str) -> tuple[int, datetime]:
    """
    Decode a cursor string returned by _encode_cursor.

    Returns (last_id, last_occurred_at).

    Raises ValueError if the cursor is malformed or missing required keys.
    This is treated as a bad request by the endpoint, not an internal error.
    """
    try:
        payload = json.loads(base64.urlsafe_b64decode(cursor.encode()))
        last_id = int(payload["last_id"])
        last_occurred_at = datetime.fromisoformat(payload["last_occurred_at"])
        return last_id, last_occurred_at
    except Exception as exc:
        raise ValueError(f"Invalid pagination cursor: {exc}") from exc


class AuditRepository:
    def __init__(self, database_url: str):
        self.database_url = database_url

    def log_event(
        self,
        *,
        practice_id: str,
        actor_email: str,
        action: str,
        resource: Optional[str] = None,
        detail: Optional[dict[str, Any]] = None,
        ip_address: Optional[str] = None,
        session_id: Optional[str] = None,
        conn=None,
    ) -> None:
        """
        Insert a single audit event into admin_audit_log.

        All parameters are keyword-only to prevent accidental positional
        mismatches at call sites.

        conn:
            If supplied, the INSERT is executed on that connection without
            opening a new one and without committing. The caller owns the
            transaction lifecycle. Use this when the audit write must be
            atomic with a mutation (Steps 5+).

            If None, this method opens its own connection via get_conn,
            which commits on success and rolls back on failure. Use this
            for auth-only events (Step 4) where there is no paired mutation.

        detail:
            A plain dict. Shape is freeform and documented per action type
            at the top of this module. Wrapped in psycopg2.extras.Json
            before insertion — do not pre-serialise.

        Raises:
            Any psycopg2 exception on database failure. The caller is
            responsible for handling this (log + re-raise as HTTP 500).
        """
        detail_value = psycopg2.extras.Json(detail) if detail is not None else None

        def _execute(cur) -> None:
            cur.execute(
                """
                INSERT INTO admin_audit_log
                    (practice_id, actor_email, action, resource,
                     detail, ip_address, session_id)
                VALUES
                    (%(practice_id)s, %(actor_email)s, %(action)s, %(resource)s,
                     %(detail)s, %(ip_address)s, %(session_id)s)
                """,
                {
                    "practice_id": practice_id,
                    "actor_email": actor_email,
                    "action": action,
                    "resource": resource,
                    "detail": detail_value,
                    "ip_address": ip_address,
                    "session_id": session_id,
                },
            )

        if conn is not None:
            # Caller owns the transaction — use the supplied connection directly.
            with conn.cursor() as cur:
                _execute(cur)
        else:
            # Standalone insert — open, commit, close.
            with get_conn(self.database_url) as own_conn:
                with own_conn.cursor() as cur:
                    _execute(cur)

    def list_events(
        self,
        *,
        practice_id: str,
        cursor: Optional[str] = None,
        from_date: Optional[date] = None,
        to_date: Optional[date] = None,
        actor: Optional[str] = None,
        action_prefix: Optional[str] = None,
        limit: int = _DEFAULT_LIMIT,
    ) -> dict[str, Any]:
        """
        Return a paginated page of audit events for the given practice.

        All parameters are keyword-only.

        cursor:
            Opaque base64 string returned as next_cursor from a previous
            call. When supplied, results start after the encoded position.
            When None, results start from the most recent event.

        from_date / to_date:
            Inclusive date-range filters on occurred_at. Date boundaries
            are applied at midnight UTC (from_date 00:00:00, to_date
            23:59:59.999999). Pass date objects, not datetimes.

        actor:
            Exact match on actor_email. Case-sensitive.

        action_prefix:
            Left-anchored prefix match: "availability" matches
            "availability.config.updated" etc. Must match ^[a-z0-9_.]+$
            — raises ValueError if it does not. This prevents SQL
            wildcard injection via the LIKE clause.

        limit:
            Page size. Clamped to [1, _MAX_LIMIT]. Defaults to
            _DEFAULT_LIMIT (50).

        Returns a dict with two keys:
            "events":      list of row dicts, newest first.
            "next_cursor": opaque cursor string if more rows exist,
                           None if this is the last page.

        Each event dict keys: id, occurred_at, practice_id, actor_email,
        action, resource, detail, ip_address, session_id.

        Raises:
            ValueError if cursor is malformed or action_prefix is invalid.
        """
        # Validate and clamp limit.
        limit = max(1, min(limit, _MAX_LIMIT))

        # Validate action_prefix before interpolating into a LIKE clause.
        if action_prefix is not None:
            if not _ACTION_PREFIX_RE.match(action_prefix):
                raise ValueError(
                    f"action_prefix must match ^[a-z0-9_.]+$, got: {action_prefix!r}"
                )

        # Decode cursor if present.
        last_id: Optional[int] = None
        last_occurred_at: Optional[datetime] = None
        if cursor is not None:
            last_id, last_occurred_at = _decode_cursor(cursor)

        # Build WHERE clauses and params incrementally.
        conditions: list[str] = ["practice_id = %(practice_id)s"]
        params: dict[str, Any] = {"practice_id": practice_id}

        if last_id is not None and last_occurred_at is not None:
            conditions.append(
                "(occurred_at, id) < (%(last_occurred_at)s, %(last_id)s)"
            )
            params["last_occurred_at"] = last_occurred_at
            params["last_id"] = last_id

        if from_date is not None:
            conditions.append("occurred_at >= %(from_date)s")
            params["from_date"] = datetime(
                from_date.year, from_date.month, from_date.day, 0, 0, 0
            )

        if to_date is not None:
            conditions.append("occurred_at <= %(to_date)s")
            params["to_date"] = datetime(
                to_date.year, to_date.month, to_date.day, 23, 59, 59, 999999
            )

        if actor is not None:
            conditions.append("actor_email = %(actor)s")
            params["actor"] = actor

        if action_prefix is not None:
            # Safe: action_prefix validated against ^[a-z0-9_.]+$ above,
            # so no LIKE wildcard characters can appear in it.
            conditions.append("action LIKE %(action_prefix)s")
            params["action_prefix"] = action_prefix + "%"

        where_clause = " AND ".join(conditions)

        # Fetch limit + 1 rows. If we get limit + 1 back, there is a next
        # page — return only limit rows and encode a cursor from the last
        # of those rows.
        fetch_limit = limit + 1
        params["fetch_limit"] = fetch_limit

        query = f"""
            SELECT id, occurred_at, practice_id, actor_email,
                   action, resource, detail, ip_address, session_id
            FROM admin_audit_log
            WHERE {where_clause}
            ORDER BY occurred_at DESC, id DESC
            LIMIT %(fetch_limit)s
        """

        with get_conn(self.database_url) as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(query, params)
                rows = cur.fetchall()

        rows = [dict(r) for r in rows]

        has_more = len(rows) > limit
        if has_more:
            rows = rows[:limit]

        next_cursor: Optional[str] = None
        if has_more:
            last_row = rows[-1]
            next_cursor = _encode_cursor(last_row["id"], last_row["occurred_at"])

        return {
            "events": rows,
            "next_cursor": next_cursor,
        }
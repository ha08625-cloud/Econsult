"""
tests/helpers/admin_test_helpers.py

Shared stubs and app factory for admin router tests.
"""
import os
import datetime
from datetime import timezone
from contextlib import contextmanager
from fastapi import FastAPI
from fastapi.responses import JSONResponse

from app.routers.admin_router import router as admin_router
from app.core.errors import APIError, RateLimitError, ConditionNotFound
from app.repositories.practice_repository import (
    sanitise_signposting_html,
    InvalidDoctorListError,
    MAX_DOCTOR_NAME_LENGTH,
    MAX_DOCTOR_LIST_LENGTH,
)


# ---------------------------------------------------------------------------
# Minimal stubs
# ---------------------------------------------------------------------------

TEST_SESSION_COOKIE = {"session_id": "test-session-id"}

class StubRegistry:
    def __init__(self, condition_ids):
        self._conditions = {
            cid: {"id": cid, "label": cid.replace("_", " ").title()}
            for cid in condition_ids
        }

    def list_conditions(self):
        return list(self._conditions.values())

    def has_condition(self, condition_id):
        return condition_id in self._conditions


class StubPracticeRepo:
    """
    In-memory practice repo stub.

    Calls the real sanitise_signposting_html so that sanitisation
    side-effects (stripping unsafe content, treating empty HTML as None,
    rejecting overlength input) are exercised through the router in tests.

    database_url is present because the router accesses
    practice_repo.database_url when opening a shared transaction via
    get_conn. In unit tests get_conn is patched (see dummy_conn below)
    so this value is never used to open a real connection.

    Mutating methods accept conn=None to match the real repository
    signatures. The conn value is ignored — the stub operates on
    in-memory state only.
    """
    def __init__(self):
        self.database_url = "stub://not-a-real-db"
        self._signposting = {}   # (practice_id, condition_id) -> str | None
        self._practice = {
            "practice_id": "test_practice",
            "name": "Test Practice",
            "email": "test@nhs.net",
        }
        self._doctors = []       # list of str, in display order

    # --- Practice ---

    def get_practice(self, practice_id):
        return dict(self._practice)

    def get_email(self, practice_id):
        return self._practice["email"]

    def update_email(self, practice_id, email, conn=None):
        self._validate_email(email)
        self._practice["email"] = email

    def _validate_email(self, email):
        from app.repositories.practice_repository import InvalidEmailError
        if not isinstance(email, str):
            raise InvalidEmailError(f"Email must be a string, got {type(email).__name__}")
        if email != email.strip():
            raise InvalidEmailError("Email contains leading or trailing whitespace")
        parts = email.split("@")
        if len(parts) != 2 or not parts[0] or not parts[1]:
            raise InvalidEmailError("Email must be in format 'local@domain'")

    # --- Signposting ---

    def get_signposting(self, practice_id, condition_id):
        return self._signposting.get((practice_id, condition_id))

    def set_signposting(self, practice_id, condition_id, value: str, conn=None):
        sanitised = sanitise_signposting_html(value)
        if sanitised is not None:
            self._signposting[(practice_id, condition_id)] = sanitised
        else:
            self._signposting.pop((practice_id, condition_id), None)

    def delete_signposting(self, practice_id, condition_id, conn=None):
        self._signposting.pop((practice_id, condition_id), None)

    # --- Doctors ---

    def get_doctors(self, practice_id):
        return list(self._doctors)

    def set_doctors(self, practice_id, names, conn=None):
        self._validate_doctor_list(names)
        self._doctors = list(names)

    def _validate_doctor_list(self, names):
        if not isinstance(names, list):
            raise InvalidDoctorListError("Doctor list must be a list")
        if len(names) > MAX_DOCTOR_LIST_LENGTH:
            raise InvalidDoctorListError(
                f"Doctor list must not exceed {MAX_DOCTOR_LIST_LENGTH} items "
                f"(received {len(names)})"
            )
        for i, name in enumerate(names):
            if not isinstance(name, str) or not name.strip():
                raise InvalidDoctorListError(
                    f"Doctor name at index {i} must be a non-empty string"
                )
            if len(name) > MAX_DOCTOR_NAME_LENGTH:
                raise InvalidDoctorListError(
                    f"Doctor name at index {i} exceeds {MAX_DOCTOR_NAME_LENGTH} characters"
                )


class StubAvailabilityRepo:
    """
    In-memory stub for availability repository.
    Mimics database behavior for config, overrides, and exceptions.
    """
    def __init__(self):
        self.database_url = "stub://not-a-real-db"
        self._config = {
            "practice_id": "test_practice",
            "is_active": True,
            "weekly_open_days": ["mon", "tue", "wed", "thu", "fri"],
            "open_time": datetime.time(8, 0),
            "close_time": datetime.time(18, 30),
            "closed_message": None,
            "override_status": None,
            "override_expires_at": None,
            "override_message": None,
        }
        self._exceptions = {}  # date -> dict

    def get_availability(self, practice_id):
        return dict(self._config)

    def set_availability(self, practice_id, is_active, weekly_open_days,
                         open_time, close_time, closed_message, conn=None):
        self._config.update({
            "is_active": is_active,
            "weekly_open_days": weekly_open_days,
            "open_time": open_time,
            "close_time": close_time,
            "closed_message": closed_message,
        })

    def set_override(self, practice_id, override_status, override_expires_at,
                     override_message, conn=None):
        self._config.update({
            "override_status": override_status,
            "override_expires_at": override_expires_at,
            "override_message": override_message,
        })

    def clear_override(self, practice_id, conn=None):
        self._config.update({
            "override_status": None,
            "override_expires_at": None,
            "override_message": None,
        })

    def get_exceptions(self, practice_id, from_date):
        return [exc for date, exc in sorted(self._exceptions.items()) if date >= from_date]

    def get_exception(self, practice_id, exception_date):
        return self._exceptions.get(exception_date)

    def set_exception(self, practice_id, exception_date, exception_type,
                      open_time, close_time, note, conn=None):
        self._exceptions[exception_date] = {
            "exception_date": exception_date,
            "exception_type": exception_type,
            "open_time": open_time,
            "close_time": close_time,
            "note": note,
        }

    def delete_exception(self, practice_id, exception_date, conn=None):
        self._exceptions.pop(exception_date, None)


class StubAuthRepo:
    """
    In-memory auth repo stub for unit tests.

    No sessions are valid by default — session lookups always return None,
    which causes require_admin to fall through to the DEV_MODE bearer-token
    fallback.
    """
    def get_session_context(self, session_id):
        if session_id == "test-session-id":
            return {
                "user_id": "00000000-0000-0000-0000-000000000001",
                "role": "admin",
                "practice_id": "test_practice",
                "email": "admin@nhs.net",
                "session_id": "test-session-id",
            }
        return None
    def get_user_by_email(self, email): return None
    def get_auth_code_record(self, email): return None
    def upsert_auth_code(self, email, hashed_code, expires_at, last_requested_at): pass
    def increment_code_attempts(self, email): pass
    def delete_auth_code(self, email): pass
    def create_session(self, user_id, expires_at): return "stub-session-id"
    def delete_session(self, session_id): pass
    def count_users_for_practice(self, practice_id): return 0
    def insert_user(self, email, practice_id, role): pass


class StubAuditRepo:
    """
    No-op audit repo stub. Records calls to log_event so tests can assert
    it was called if needed, but never touches the database.
    """
    def __init__(self):
        self.logged = []

    def log_event(self, *, practice_id, actor_email, action, resource=None,
                  detail=None, ip_address=None, session_id=None, conn=None):
        self.logged.append({
            "practice_id": practice_id, "actor_email": actor_email, "action": action,
            "resource": resource, "detail": detail, "ip_address": ip_address,
            "session_id": session_id,
        })

    def list_events(self, *, practice_id, cursor=None, from_date=None,
                    to_date=None, actor=None, action_prefix=None, limit=50):
        return {"events": [], "next_cursor": None}


class StubAdminDeliveryService:
    """Captures send_mfa_code and send_admin_invitation calls without sending email."""
    def __init__(self):
        self.calls = []
        self.invitation_calls = []

    def send_mfa_code(self, email, code):
        self.calls.append({"email": email, "code": code})

    def send_admin_invitation(self, email):
        self.invitation_calls.append({"email": email})


# ---------------------------------------------------------------------------
# App factory & dummy connection
# ---------------------------------------------------------------------------

@contextmanager
def dummy_conn(_database_url):
    """
    Stand-in for app.core.db.get_conn in unit tests.

    Yields a sentinel string instead of a real psycopg2 connection.
    The stub repositories accept conn=None and ignore it, so the
    sentinel is never used for actual database operations. It only
    needs to exist so that the `with get_conn(...) as conn:` block
    in the router succeeds without opening a real Postgres connection.
    """
    yield "stub-conn"


def make_test_app(condition_ids=None, auth_repo=None, delivery_service=None,
                  audit_repo=None, availability_repo=None, with_rate_limiting=False):
    """
    Build a bare FastAPI app with the admin router registered and
    app.state populated. Does not run the normal startup validation.

    Registers the same exception handlers as main.py:
      - ConditionNotFound  -> 404
      - APIError           -> 422
      - RateLimitError     -> 429

    with_rate_limiting=True additionally wires SlowAPIMiddleware and the
    RateLimitExceeded handler, mirroring the production main.py setup.
    Pass this flag only in tests that specifically exercise slowapi limits.
    """
    app = FastAPI()

    if with_rate_limiting:
        from slowapi.errors import RateLimitExceeded
        from slowapi.middleware import SlowAPIMiddleware
        from app.core.rate_limit import limiter
        app.state.limiter = limiter
        app.add_middleware(SlowAPIMiddleware)

    app.include_router(admin_router, prefix="/admin", tags=["admin"])

    app.state.practice_id = "test_practice"
    app.state.registry = StubRegistry(condition_ids or ["urinary_symptoms"])
    app.state.practice_repo = StubPracticeRepo()
    app.state.auth_repo = auth_repo or StubAuthRepo()
    app.state.audit_repo = audit_repo or StubAuditRepo()
    app.state.availability_repo = availability_repo or StubAvailabilityRepo()
    app.state.allowed_admin_domains = "nhs.net"
    app.state.admin_delivery_service = delivery_service or StubAdminDeliveryService()

    @app.exception_handler(ConditionNotFound)
    async def condition_not_found_handler(_, exc: ConditionNotFound):
        return JSONResponse(
            status_code=404,
            content={"error": {"code": "CONDITION_NOT_FOUND", "message": f"Unknown condition: {exc}"}},
        )

    @app.exception_handler(APIError)
    async def api_error_handler(_, exc: APIError):
        return JSONResponse(
            status_code=422,
            content={"error": {"code": exc.code, "message": exc.message}},
        )

    @app.exception_handler(RateLimitError)
    async def rate_limit_handler(_, exc: RateLimitError):
        return JSONResponse(
            status_code=429,
            content={"error": {"code": "RATE_LIMIT_EXCEEDED", "message": str(exc)}},
        )

    if with_rate_limiting:
        from slowapi.errors import RateLimitExceeded

        @app.exception_handler(RateLimitExceeded)
        async def slowapi_rate_limit_handler(_, exc: RateLimitExceeded):
            return JSONResponse(
                status_code=429,
                content={"error": {"code": "RATE_LIMIT_EXCEEDED", "message": "Too many requests. Please try again later."}},
            )

    return app
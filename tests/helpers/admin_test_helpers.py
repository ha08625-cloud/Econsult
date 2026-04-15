"""
tests/helpers/admin_test_helpers.py

Shared stubs and app factory for admin router tests.
"""
import os
from contextlib import contextmanager
from fastapi import FastAPI
from fastapi.responses import JSONResponse

from app.routers.admin_router import router as admin_router
from app.core.errors import APIError, RateLimitError, ConditionNotFound
from app.repositories.practice_repository import sanitise_signposting_html

# ---------------------------------------------------------------------------
# Minimal stubs
# ---------------------------------------------------------------------------

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
    def __init__(self):
        self.database_url = "stub://not-a-real-db"
        self._store = {} 

    def get_signposting(self, practice_id, condition_id):
        return self._store.get((practice_id, condition_id))

    def set_signposting(self, practice_id, condition_id, value: str, conn=None):
        sanitised = sanitise_signposting_html(value)
        if sanitised is not None:
            self._store[(practice_id, condition_id)] = sanitised
        else:
            self._store.pop((practice_id, condition_id), None)

    def delete_signposting(self, practice_id, condition_id, conn=None):
        self._store.pop((practice_id, condition_id), None)

class StubAuthRepo:
    def get_session_context(self, session_id): return None
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
    def __init__(self):
        self.logged = []

    def log_event(self, *, practice_id, actor_email, action, resource=None,
                  detail=None, ip_address=None, session_id=None, conn=None):
        self.logged.append({
            "practice_id": practice_id, "actor_email": actor_email, "action": action,
            "resource": resource, "detail": detail, "ip_address": ip_address, "session_id": session_id,
        })

    def list_events(self, *, practice_id, cursor=None, from_date=None,
                    to_date=None, actor=None, action_prefix=None, limit=50):
        return {"events": [], "next_cursor": None}

class StubAdminDeliveryService:
    def __init__(self):
        self.calls = []
    def send_mfa_code(self, email, code):
        self.calls.append({"email": email, "code": code})

# ---------------------------------------------------------------------------
# App factory & dummy connection
# ---------------------------------------------------------------------------

@contextmanager
def dummy_conn(_database_url):
    """Stand-in for app.core.db.get_conn in unit tests."""
    yield "stub-conn"

def make_test_app(condition_ids=None, auth_repo=None, delivery_service=None,
                  audit_repo=None, with_rate_limiting=False):
    app = FastAPI()

    if with_rate_limiting:
        from slowapi.errors import RateLimitExceeded
        from slowapi.middleware import SlowAPIMiddleware
        from app.core.rate_limit import limiter
        app.state.limiter = limiter
        app.add_middleware(SlowAPIMiddleware)

    # Mounts the master admin_router which now delegates to the 4 sub-routers
    app.include_router(admin_router, prefix="/admin", tags=["admin"])

    app.state.practice_id = "test_practice"
    app.state.registry = StubRegistry(condition_ids or ["urinary_symptoms"])
    app.state.practice_repo = StubPracticeRepo()
    app.state.auth_repo = auth_repo or StubAuthRepo()
    app.state.audit_repo = audit_repo or StubAuditRepo()
    app.state.allowed_admin_domains = "nhs.net"
    app.state.admin_delivery_service = delivery_service or StubAdminDeliveryService()

    @app.exception_handler(ConditionNotFound)
    async def condition_not_found_handler(_, exc: ConditionNotFound):
        return JSONResponse(status_code=404, content={"error": {"code": "CONDITION_NOT_FOUND", "message": f"Unknown condition: {exc}"}})

    @app.exception_handler(APIError)
    async def api_error_handler(_, exc: APIError):
        return JSONResponse(status_code=422, content={"error": {"code": exc.code, "message": exc.message}})

    @app.exception_handler(RateLimitError)
    async def rate_limit_handler(_, exc: RateLimitError):
        return JSONResponse(status_code=429, content={"error": {"code": "RATE_LIMIT_EXCEEDED", "message": str(exc)}})

    if with_rate_limiting:
        @app.exception_handler(RateLimitExceeded)
        async def slowapi_rate_limit_handler(_, exc: RateLimitExceeded):
            return JSONResponse(status_code=429, content={"error": {"code": "RATE_LIMIT_EXCEEDED", "message": "Too many requests. Please try again later."}})

    return app

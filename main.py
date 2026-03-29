"""
HTTP layer/imperative shell

Application factory, startup validation, router registration, error handling,
and static file serving. No clinical logic, no form session handling.

Single-tenant deployment:
- PRACTICE_ID environment variable is required at startup
- The practice must exist in the database with a valid email
- The database must contain exactly one practice
- SMTP configuration is required unless DEV_MODE is set
- ADMIN_TOKEN is required unless DEV_MODE is set
"""

from fastapi import FastAPI
from fastapi.responses import JSONResponse
import os
import logging

from app.core.db import alembic_upgrade
from app.core.condition_registry import ConditionRegistry, ConditionNotFound
from app.repositories.practice_repository import PracticeRepository
from app.repositories.availability_repository import AvailabilityRepository
from app.repositories.runtime_state_repository import RuntimeStateRepository
from app.repositories.submission_repository import SubmissionRepository
from app.repositories.attachment_repository import AttachmentRepository
from app.services.presentation_service import PresentationService
from app.core.errors import APIError
from app.services.delivery.delivery_service import ConsoleDeliveryService, EmailDeliveryService
from app.routers.admin_router import router as admin_router
from app.routers.public_router import router as public_router
from app.routers.form_router import router as form_router
from starlette.staticfiles import StaticFiles

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Startup helpers
# ---------------------------------------------------------------------------

def _require_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"Required environment variable not set: {name}")
    return value


# Intentionally duplicated in admin_context.py. That module must never
# import any project module (see arch_admin.md), so this cannot be shared.
def _is_dev_mode() -> bool:
    return os.environ.get("DEV_MODE", "").lower() in ("1", "true")


def _validate_startup(practice_repo: PracticeRepository) -> str:
    practice_id = _require_env("PRACTICE_ID")

    # Seed the practice record if it does not exist.
    # Handles cloud deployments where the database starts empty on every
    # container restart. Safe to run on every startup - skips if already present.
    if not practice_repo.practice_exists(practice_id):
        practice_name = os.environ.get("PRACTICE_NAME", practice_id)
        practice_email = os.environ.get("PRACTICE_EMAIL", "demo@demo.net")
        logger.info("Practice '%s' not found - seeding record now", practice_id)
        practice_repo.create_practice(
            practice_id=practice_id,
            name=practice_name,
            email=practice_email,
        )

    count = practice_repo.count_practices()
    if count > 1:
        raise RuntimeError(
            f"Database contains {count} practices. "
            "This is a single-tenant deployment. "
            "Multiple practices is a clinically unsafe configuration. "
            "Aborting startup."
        )

    practice = practice_repo.get_practice(practice_id)
    if practice is None:
        raise RuntimeError(
            f"PRACTICE_ID '{practice_id}' not found in database. "
            "Create the practice record before starting the application."
        )

    if not practice.get("email", "").strip():
        raise RuntimeError(
            f"Practice '{practice_id}' has no email address configured. "
            "Update the practice record with a valid email before starting."
        )

    if not _is_dev_mode():
        for var in ("SMTP_HOST", "SMTP_USER", "SMTP_PASSWORD", "EMAIL_FROM"):
            if not os.environ.get(var):
                raise RuntimeError(
                    f"Required SMTP environment variable not set: {var}. "
                    "Set DEV_MODE=1 to skip email sending during development."
                )

    if not _is_dev_mode():
        if not os.environ.get("ADMIN_TOKEN"):
            raise RuntimeError(
                "Required environment variable not set: ADMIN_TOKEN. "
                "Set DEV_MODE=1 to skip this check during development."
            )
    else:
        if not os.environ.get("ADMIN_TOKEN"):
            logger.warning(
                "ADMIN_TOKEN is not set. In DEV_MODE any non-empty bearer token "
                "will be accepted by admin endpoints. Do not expose this server publicly."
            )

    return practice_id


# ---------------------------------------------------------------------------
# Application factory
# ---------------------------------------------------------------------------

# Resolve paths relative to the project root.
_PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.environ.get("DATA_DIR") or os.path.join(_PROJECT_ROOT, "data")

DATABASE_URL = os.environ.get("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError("Required environment variable not set: DATABASE_URL")

app = FastAPI()

# Run all pending Alembic migrations at startup.
# If a migration fails, the application will fail to start — this is correct
# behaviour. A failed migration must prevent startup.
# See architecture.md for migration workflow and rollback procedures.
alembic_upgrade()

repo = RuntimeStateRepository(DATABASE_URL)
registry = ConditionRegistry(DATA_DIR)
practice_repo = PracticeRepository(DATABASE_URL)
submission_repo = SubmissionRepository(DATABASE_URL)
attachment_repo = AttachmentRepository(DATABASE_URL)
availability_repo = AvailabilityRepository(DATABASE_URL)
presentation_service = PresentationService(registry, practice_repo)

# Startup validation -- runs at import time (when FastAPI loads the module).
# Any failure here prevents the application from starting.
# Also seeds the practice record if it does not already exist.
app.state.practice_id = _validate_startup(practice_repo)
app.state.registry = registry
app.state.practice_repo = practice_repo
app.state.availability_repo = availability_repo
app.state.presentation_service = presentation_service
app.state.runtime_repo = repo
app.state.submission_repo = submission_repo
app.state.attachment_repo = attachment_repo

# Look up practice name for use in generated PDFs.
# Captured once at startup. If the practice name is changed via the admin
# interface, the running server will use the old name until the next restart.
_practice_record = practice_repo.get_practice(app.state.practice_id)
_practice_name = _practice_record.get("name") if _practice_record else None
app.state.practice_name = _practice_name

if _is_dev_mode():
    app.state.delivery_service = ConsoleDeliveryService()
else:
    app.state.delivery_service = EmailDeliveryService()

# Insert default availability row if absent.
# Must run after _validate_startup ensures the practice row exists.
availability_repo.init_availability(app.state.practice_id)

# ---------------------------------------------------------------------------
# Router registration
# All API routes must be registered before the static file mount block.
# ---------------------------------------------------------------------------

# Admin router -- prefix and tag applied here so admin_router.py stays decoupled
app.include_router(admin_router, prefix="/admin", tags=["admin"])

# Public router -- no prefix, routes sit at root level
app.include_router(public_router)

# Form session router -- no prefix, routes sit at root level
app.include_router(form_router)

# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------

@app.exception_handler(APIError)
async def api_error_handler(_, exc: APIError):
    return JSONResponse(
        status_code=422,
        content={"error": {"code": exc.code, "message": exc.message}},
    )


@app.exception_handler(ConditionNotFound)
async def condition_not_found_handler(_, exc: ConditionNotFound):
    return JSONResponse(
        status_code=404,
        content={"error": {"code": "CONDITION_NOT_FOUND", "message": f"Unknown condition: {exc}"}},
    )


# ---------------------------------------------------------------------------
# Utility endpoints
# ---------------------------------------------------------------------------

@app.get("/healthz")
async def health():
    return {"ok": True}


# ---------------------------------------------------------------------------
# Static file serving
# All API routes must be registered before this block.
# Served whenever frontend/dist exists - i.e. on Railway after the build step.
# Skipped automatically in local dev because Vite has not built dist/ there.
# DEV_MODE does not control this - it only controls email and auth behaviour.
# The catch-all route must come last so it never intercepts API requests.
# ---------------------------------------------------------------------------

_FRONTEND_DIST = os.path.join(_PROJECT_ROOT, "frontend", "dist")

if os.path.isdir(_FRONTEND_DIST):
    logger.info("Frontend dist found - mounting static files")
    app.mount(
        "/",
        StaticFiles(directory=_FRONTEND_DIST, html=True),
        name="frontend",
    )
else:
    logger.info("Frontend dist not found - static file serving disabled (local dev mode)")
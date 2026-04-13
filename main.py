"""
HTTP layer/imperative shell

Application factory, startup validation, router registration, error handling,
and static file serving. No clinical logic, no form session handling.

Single-tenant deployment:
- PRACTICE_ID environment variable is required at startup
- The practice must exist in the database with a valid email
- The database must contain exactly one practice
- In production, either MAILGUN_API_KEY or all four SMTP variables must be set
- ADMIN_TOKEN is now optional; MFA replaces it. If ADMIN_TOKEN is set in
  production alongside MFA, a warning is logged (both auth methods active).
- INITIAL_ADMIN_EMAIL and ALLOWED_ADMIN_DOMAINS are required in production.

Delivery service selection:
- DEV_MODE=1: ConsoleDeliveryService / ConsoleAdminDeliveryService (no email sent)
- MAILGUN_API_KEY set: MailgunHttpDeliveryService / MailgunHttpAdminDeliveryService
- Otherwise: EmailDeliveryService / AdminDeliveryService (SMTP)
"""

from fastapi import FastAPI, HTTPException
from fastapi.exception_handlers import http_exception_handler as _default_http_handler
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
from app.repositories.pdf_repository import PDFRepository
from app.repositories.photo_repository import PhotoRepository
from app.repositories.delivery_repository import DeliveryRepository
from app.repositories.auth_repository import AuthRepository
from app.repositories.audit_repository import AuditRepository
from app.services.presentation_service import PresentationService
from app.core.errors import APIError, RateLimitError
from app.services.delivery.delivery_service import (
    ConsoleDeliveryService,
    EmailDeliveryService,
    MailgunHttpDeliveryService,
)
from app.services.delivery.admin_delivery_service import (
    AdminDeliveryService,
    ConsoleAdminDeliveryService,
    MailgunHttpAdminDeliveryService,
)
from app.services.auth_service import validate_admin_domain
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


def _validate_startup(
    practice_repo: PracticeRepository,
    auth_repo: AuthRepository,
) -> str:
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
        _validate_email_config()

    # --- ADMIN_TOKEN: optional with MFA, warn if both are active ---
    if not _is_dev_mode():
        if os.environ.get("ADMIN_TOKEN"):
            logger.warning(
                "ADMIN_TOKEN is set alongside MFA authentication. "
                "Both auth methods are active. Consider removing ADMIN_TOKEN "
                "once MFA is fully deployed."
            )
    else:
        if not os.environ.get("ADMIN_TOKEN"):
            logger.warning(
                "ADMIN_TOKEN is not set. In DEV_MODE any non-empty bearer token "
                "will be accepted by admin endpoints. Do not expose this server publicly."
            )

    # --- INITIAL_ADMIN_EMAIL and ALLOWED_ADMIN_DOMAINS ---
    # Required in production. In DEV_MODE, absence is allowed but logged.
    initial_admin_email = os.environ.get("INITIAL_ADMIN_EMAIL", "").strip()
    allowed_admin_domains = os.environ.get("ALLOWED_ADMIN_DOMAINS", "").strip()

    if not _is_dev_mode():
        if not initial_admin_email:
            raise RuntimeError(
                "Required environment variable not set: INITIAL_ADMIN_EMAIL. "
                "Set this to the email address of the first admin user."
            )
        if not allowed_admin_domains:
            raise RuntimeError(
                "Required environment variable not set: ALLOWED_ADMIN_DOMAINS. "
                "Set this to a comma-separated list of permitted admin email domains "
                "(e.g. 'nhs.net,gov.uk')."
            )

    # Validate that the seed email's domain is in the allowed list.
    # Runs on every startup to catch the case where domains are changed
    # without updating the seed email.
    if initial_admin_email and allowed_admin_domains:
        if not validate_admin_domain(initial_admin_email, allowed_admin_domains):
            raise RuntimeError(
                f"INITIAL_ADMIN_EMAIL domain is not in ALLOWED_ADMIN_DOMAINS. "
                f"Email: '{initial_admin_email}', "
                f"Allowed domains: '{allowed_admin_domains}'. "
                "Update one of these environment variables before starting."
            )

        # Seed the initial admin user if no users exist for this practice.
        user_count = auth_repo.count_users_for_practice(practice_id)
        if user_count == 0:
            logger.info(
                "No admin users found for practice '%s' — seeding initial admin: %s",
                practice_id,
                initial_admin_email,
            )
            auth_repo.insert_user(
                email=initial_admin_email,
                practice_id=practice_id,
                role="admin",
            )

    return practice_id


def _validate_email_config() -> None:
    """
    Validate that a complete email delivery configuration is present.

    Accepts either:
      - Mailgun HTTP: MAILGUN_API_KEY + MAILGUN_DOMAIN + EMAIL_FROM
      - SMTP: SMTP_HOST + SMTP_USER + SMTP_PASSWORD + EMAIL_FROM

    Raises RuntimeError if neither complete configuration is present.
    EMAIL_FROM is required in both cases.
    """
    if not os.environ.get("EMAIL_FROM"):
        raise RuntimeError(
            "Required environment variable not set: EMAIL_FROM. "
            "Set DEV_MODE=1 to skip email sending during development."
        )

    if os.environ.get("MAILGUN_API_KEY"):
        # Mailgun HTTP path — check the Mailgun-specific variable.
        if not os.environ.get("MAILGUN_DOMAIN"):
            raise RuntimeError(
                "MAILGUN_API_KEY is set but MAILGUN_DOMAIN is missing. "
                "Both are required for Mailgun HTTP delivery."
            )
        logger.info("Email delivery: Mailgun HTTP API selected.")
    else:
        # SMTP path — check all four SMTP variables.
        for var in ("SMTP_HOST", "SMTP_USER", "SMTP_PASSWORD"):
            if not os.environ.get(var):
                raise RuntimeError(
                    f"Required email environment variable not set: {var}. "
                    "Either set MAILGUN_API_KEY + MAILGUN_DOMAIN for Mailgun HTTP, "
                    "or set SMTP_HOST + SMTP_USER + SMTP_PASSWORD for SMTP. "
                    "Set DEV_MODE=1 to skip email sending during development."
                )
        logger.info("Email delivery: SMTP selected.")


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
pdf_repo = PDFRepository(DATABASE_URL)
photo_repo = PhotoRepository(DATABASE_URL)
delivery_repo = DeliveryRepository(DATABASE_URL)
availability_repo = AvailabilityRepository(DATABASE_URL)
auth_repo = AuthRepository(DATABASE_URL)
audit_repo = AuditRepository(DATABASE_URL)
presentation_service = PresentationService(registry, practice_repo)

# Startup validation -- runs at import time (when FastAPI loads the module).
# Any failure here prevents the application from starting.
# Also seeds the practice record and initial admin user if they do not exist.
app.state.practice_id = _validate_startup(practice_repo, auth_repo)
app.state.registry = registry
app.state.practice_repo = practice_repo
app.state.availability_repo = availability_repo
app.state.presentation_service = presentation_service
app.state.runtime_repo = repo
app.state.submission_repo = submission_repo
app.state.attachment_repo = attachment_repo
app.state.pdf_repo = pdf_repo
app.state.photo_repo = photo_repo
app.state.delivery_repo = delivery_repo
app.state.auth_repo = auth_repo
app.state.audit_repo = audit_repo

# Store allowed domains in app.state so the router can read it without
# importing os directly (keeps handler signatures self-documenting).
app.state.allowed_admin_domains = os.environ.get("ALLOWED_ADMIN_DOMAINS", "")

# Look up practice name for use in generated PDFs.
# Captured once at startup. If the practice name is changed via the admin
# interface, the running server will use the old name until the next restart.
_practice_record = practice_repo.get_practice(app.state.practice_id)
_practice_name = _practice_record.get("name") if _practice_record else None
app.state.practice_name = _practice_name

# ---------------------------------------------------------------------------
# Delivery service selection
# DEV_MODE=1       -> Console (no email sent)
# MAILGUN_API_KEY  -> Mailgun HTTP API
# otherwise        -> SMTP
# ---------------------------------------------------------------------------

if _is_dev_mode():
    app.state.delivery_service = ConsoleDeliveryService()
    app.state.admin_delivery_service = ConsoleAdminDeliveryService()
elif os.environ.get("MAILGUN_API_KEY"):
    app.state.delivery_service = MailgunHttpDeliveryService()
    app.state.admin_delivery_service = MailgunHttpAdminDeliveryService()
else:
    app.state.delivery_service = EmailDeliveryService()
    app.state.admin_delivery_service = AdminDeliveryService()

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


@app.exception_handler(RateLimitError)
async def rate_limit_handler(_, exc: RateLimitError):
    return JSONResponse(
        status_code=429,
        content={"error": {"code": "RATE_LIMIT_EXCEEDED", "message": str(exc)}},
    )


@app.exception_handler(HTTPException)
async def http_exception_envelope_handler(request, exc: HTTPException):
    # Reshape 401 responses into the standard error envelope so the frontend
    # has a consistent body shape across all error types. The HTTP status code
    # is the primary contract for session expiry — this handler is the single
    # place that enforces the secondary (body) contract for 401s.
    # All other HTTP exceptions pass through to FastAPI's default handler
    # unchanged — we do not want to interfere with 404s, 422s from Pydantic, etc.
    if exc.status_code == 401:
        return JSONResponse(
            status_code=401,
            content={"error": {"code": "UNAUTHORIZED", "message": exc.detail}},
        )
    return await _default_http_handler(request, exc)


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
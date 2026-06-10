"""
HTTP layer/imperative shell

Application factory, startup validation, router registration, error handling,
and static file serving. No clinical logic, no form session handling.

Single-tenant deployment:
- PRACTICE_ID environment variable is required at startup
- The practice must exist in the database with a valid email
- The database must contain exactly one practice
- The database must contain at least one admin user for the practice
- Either MAILGUN_API_KEY or all four SMTP variables must be set
- ALLOWED_ADMIN_DOMAINS is required

Delivery service selection:
- MAILGUN_API_KEY set: MailgunHttpDeliveryService / MailgunHttpAdminDeliveryService
- Otherwise: EmailDeliveryService / AdminDeliveryService (SMTP)
"""

import os
import logging

from app.core.telemetry import init_telemetry

# Initialise Sentry before any other internal import. This ensures that
# exceptions raised during module-level startup (e.g. a failed Alembic
# migration in db.py) are captured by Sentry's default sys.excepthook.
init_telemetry("http-api")

from fastapi import FastAPI, HTTPException  # noqa: E402
from fastapi.exception_handlers import http_exception_handler as _default_http_handler  # noqa: E402
from fastapi.responses import JSONResponse  # noqa: E402
from slowapi.errors import RateLimitExceeded  # noqa: E402
from slowapi.middleware import SlowAPIMiddleware  # noqa: E402
from app.core.rate_limit import limiter  # noqa: E402

from app.core.db import alembic_upgrade  # noqa: E402
from app.core.condition_registry import ConditionRegistry  # noqa: E402
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
from app.core.errors import APIError, RateLimitError, ConditionNotFound
from app.services.delivery.delivery_service import (
    EmailDeliveryService,
    MailgunHttpDeliveryService,
)
from app.services.delivery.admin_delivery_service import (
    AdminDeliveryService,
    MailgunHttpAdminDeliveryService,
)
from app.routers.admin_router import router as admin_router
from app.routers.public_router import router as public_router
from app.routers.form_router import router as form_router
from app.routers.webhook_router import router as webhook_router
from starlette.staticfiles import StaticFiles

import sentry_sdk  # noqa: E402 — safe: no-op if Sentry not initialised

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Startup helpers
# ---------------------------------------------------------------------------

def _require_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"Required environment variable not set: {name}")
    return value


def _validate_startup(
    practice_repo: PracticeRepository,
    auth_repo: AuthRepository,
) -> str:
    practice_id = _require_env("PRACTICE_ID")

    # --- Practice existence check ---
    # The practice record must be inserted before the application starts.
    # See docs/deployment_checklist.md and scripts/create_admin_user.py.
    practice = practice_repo.get_practice(practice_id)
    if practice is None:
        raise RuntimeError(
            f"Practice '{practice_id}' not found in database. "
            "Insert the practice record before starting the application. "
            "See docs/deployment_checklist.md."
        )

    if not practice.get("email", "").strip():
        raise RuntimeError(
            f"Practice '{practice_id}' has no email address configured. "
            "Update the practice record with a valid email before starting."
        )

    # --- Single-tenant guard ---
    count = practice_repo.count_practices()
    if count > 1:
        raise RuntimeError(
            f"Database contains {count} practices. "
            "This is a single-tenant deployment. "
            "Multiple practices is a clinically unsafe configuration. "
            "Aborting startup."
        )

    # --- Email delivery config ---
    _validate_email_config()

    # --- MESH delivery mode ---
    _validate_mesh_delivery()

    # --- Admin domain config ---
    allowed_admin_domains = os.environ.get("ALLOWED_ADMIN_DOMAINS", "").strip()
    if not allowed_admin_domains:
        raise RuntimeError(
            "Required environment variable not set: ALLOWED_ADMIN_DOMAINS. "
            "Set this to a comma-separated list of permitted admin email domains "
            "(e.g. 'nhs.net,gov.uk')."
        )

    # --- Admin user existence check ---
    # At least one admin user must exist before the application starts.
    # Use scripts/create_admin_user.py to insert the first user.
    user_count = auth_repo.count_users_for_practice(practice_id)
    if user_count == 0:
        raise RuntimeError(
            f"No admin users found for practice '{practice_id}'. "
            "Use scripts/create_admin_user.py to add an admin user before starting. "
            "See docs/deployment_checklist.md."
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
            "Set this to the sender address for outgoing emails."
        )

    has_mailgun = bool(
        os.environ.get("MAILGUN_API_KEY") and os.environ.get("MAILGUN_DOMAIN")
    )
    has_smtp = bool(
        os.environ.get("SMTP_HOST")
        and os.environ.get("SMTP_USER")
        and os.environ.get("SMTP_PASSWORD")
    )

    if not has_mailgun and not has_smtp:
        raise RuntimeError(
            "No email delivery configuration found. "
            "Set either MAILGUN_API_KEY + MAILGUN_DOMAIN (Mailgun HTTP) "
            "or SMTP_HOST + SMTP_USER + SMTP_PASSWORD (SMTP)."
        )
    
    if has_mailgun and not os.environ.get("MAILGUN_SIGNING_KEY"):
        raise RuntimeError(
            "Required environment variable not set: MAILGUN_SIGNING_KEY. "
            "Set this to the Mailgun webhook signing key to enable webhook "
            "signature verification."
        )


def _validate_mesh_delivery() -> None:
    """
    Validate the MESH_DELIVERY environment variable.

    Must be present and exactly "0" or "1". No defaulting is permitted —
    a misconfigured deployment must abort at startup per the Fail-Fast
    Configuration project invariant.

    In Phase 1a only "0" (email path) is implemented. "1" is reserved
    for Phase 1b onwards and causes startup to abort with a clear
    message.

    Raises RuntimeError on any invalid value. The same validation is
    duplicated in every *_worker_main.py; the deployment_checklist.md
    mandates that all processes share the same MESH_DELIVERY value.
    """
    value = os.environ.get("MESH_DELIVERY")
    if value is None:
        raise RuntimeError(
            "Required environment variable not set: MESH_DELIVERY. "
            "Must be exactly '0' or '1'. No default is permitted."
        )
    if value not in ("0", "1"):
        raise RuntimeError(
            f"MESH_DELIVERY must be exactly '0' or '1', got: {value!r}. "
            "No other values (including truthy strings) are accepted."
        )


# ---------------------------------------------------------------------------

# Resolve paths relative to the project root.
_PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.environ.get("DATA_DIR") or os.path.join(_PROJECT_ROOT, "data")

DATABASE_URL = os.environ.get("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError("Required environment variable not set: DATABASE_URL")

app = FastAPI()

# Rate limiting — must be attached before any requests are handled.
# SlowAPIMiddleware reads app.state.limiter to locate the Limiter instance.
app.state.limiter = limiter
app.add_middleware(SlowAPIMiddleware)

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
# The "startup" tag is set unconditionally — sentry_sdk.set_tag is a no-op
# when Sentry is not initialised, so no guard is needed.
sentry_sdk.set_tag("phase", "startup")
app.state.practice_id = _validate_startup(practice_repo, auth_repo)
sentry_sdk.set_tag("phase", "running")
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
app.state.mailgun_signing_key = os.environ.get("MAILGUN_SIGNING_KEY")
app.state.database_url = DATABASE_URL

# Look up practice name for use in generated PDFs.
# Captured once at startup. If the practice name is changed via the admin
# interface, the running server will use the old name until the next restart.
_practice_record = practice_repo.get_practice(app.state.practice_id)
_practice_name = _practice_record.get("name") if _practice_record else None
app.state.practice_name = _practice_name

# ---------------------------------------------------------------------------
# Delivery service selection
# MAILGUN_API_KEY  -> Mailgun HTTP API
# otherwise        -> SMTP
# ---------------------------------------------------------------------------

if os.environ.get("MAILGUN_API_KEY"):
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

app.include_router(webhook_router)

# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------

@app.exception_handler(APIError)
async def api_error_handler(_, exc: APIError):
    return JSONResponse(
        status_code=exc.status_code,
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


@app.exception_handler(RateLimitExceeded)
async def slowapi_rate_limit_handler(_, exc: RateLimitExceeded):
    # Catches requests rejected by @limiter.limit() decorators (slowapi).
    # Returns the same error envelope as the service-layer RateLimitError handler
    # above so the frontend always receives a consistent 429 response shape.
    return JSONResponse(
        status_code=429,
        content={
            "error": {
                "code": "RATE_LIMIT_EXCEEDED",
                "message": "Too many requests. Please try again later.",
            }
        },
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
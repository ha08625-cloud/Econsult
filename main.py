"""
HTTP layer/imperative shell

Application entry point: settings loading, migrations, container
construction, router registration, error handling, and static file
serving. No clinical logic, no form session handling.

Configuration and construction are delegated:
- app/core/settings.py validates every environment variable and owns
  EmailSettings.delivery_mode, the single definition of which email path
  is configured (Mailgun only when MAILGUN_API_KEY + MAILGUN_DOMAIN are
  both set; otherwise SMTP).
- app/core/wiring.py constructs the AppContainer (registry, repositories,
  services, startup-derived scalars), runs the DB-backed deployment
  checks, and unpacks the container onto app.state, where the getters in
  app/core/dependencies.py read it.

Single-tenant deployment invariants (enforced in settings.py and
wiring.run_deployment_checks):
- PRACTICE_ID, DATABASE_URL, ALLOWED_ADMIN_DOMAINS, EMAIL_FROM required
- A complete Mailgun or SMTP configuration required
- MESH_DELIVERY must be exactly "0" (Phase 1a)
- The practice must exist in the database with a valid email
- The database must contain exactly one practice
- At least one admin user must exist for the practice

Everything runs at module import time so that the deployment dry-run
(python -c "from main import app") and the integration tests
(test_public_routes.py, test_form_routes.py) exercise the full startup
sequence.
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
from starlette.staticfiles import StaticFiles  # noqa: E402

from app.core.rate_limit import limiter  # noqa: E402
from app.core.db import alembic_upgrade  # noqa: E402
from app.core.settings import load_web_settings  # noqa: E402
from app.core.wiring import build_container, unpack_container  # noqa: E402
from app.core.errors import APIError, RateLimitError, ConditionNotFound  # noqa: E402
from app.routers.admin_router import router as admin_router  # noqa: E402
from app.routers.public_router import router as public_router  # noqa: E402
from app.routers.form_router import router as form_router  # noqa: E402
from app.routers.webhook_router import router as webhook_router  # noqa: E402

import sentry_sdk  # noqa: E402 — safe: no-op if Sentry not initialised

logger = logging.getLogger(__name__)

_PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))

# ---------------------------------------------------------------------------
# Startup sequence -- runs at import time. Order is load-bearing:
# settings -> limiter -> migrations -> container (repos, DB checks,
# services) -> app.state -> default availability row -> routers ->
# handlers -> static mount.
# ---------------------------------------------------------------------------

# Environment validation first: a misconfigured deployment must abort
# before touching the database. Raises RuntimeError with the same
# operator-facing messages as the legacy inline checks.
settings = load_web_settings()

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

# Construct everything. build_container runs the DB-backed deployment
# checks (practice exists, email present, single tenant, admin user
# exists) between repository and service construction, preserving the
# legacy startup error precedence. Constructing the frozen AppContainer
# is the startup-time completeness check.
# The "startup" tag is set unconditionally — sentry_sdk.set_tag is a no-op
# when Sentry is not initialised, so no guard is needed.
sentry_sdk.set_tag("phase", "startup")
container = build_container(settings)
sentry_sdk.set_tag("phase", "running")

# Expose every container field as a flat app.state attribute, which is
# where app/core/dependencies.py getters (and, until Stage 4, the webhook
# router and admin_context) read them. tests/test_wiring.py pins the
# getter <-> field contract.
unpack_container(app, container)

# Insert default availability row if absent.
# Must run after the deployment checks confirm the practice row exists.
container.availability_repo.init_availability(container.practice_id)

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

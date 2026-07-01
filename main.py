"""
HTTP layer / imperative shell.

Application entry point: settings loading, migrations, container
construction, router registration, error handling, and static file
serving. No clinical logic, no form session handling.

Configuration is delegated to app/core/settings.py and construction to
app/core/wiring.py. For the full startup sequence, the single-tenant
deployment invariants, and the environment variable rules enforced
across both modules, see docs/arch_infrastructure.md -- this docstring
is intentionally not a second copy of that document.

Everything below runs at module import time so that the deployment
dry-run (python -c "from main import app") and the integration tests
(test_public_routes.py, test_form_routes.py) exercise the full startup
sequence.
"""

import logging
import os

from app.core.telemetry import init_telemetry

# Initialise Sentry before any other internal import. This ensures that
# exceptions raised during module-level startup (e.g. a failed Alembic
# migration in db.py) are captured by Sentry's default sys.excepthook.
init_telemetry("http-api")

import sentry_sdk  # noqa: E402 — safe: no-op if Sentry not initialised
from fastapi import FastAPI  # noqa: E402
from slowapi.middleware import SlowAPIMiddleware  # noqa: E402
from starlette.staticfiles import StaticFiles  # noqa: E402

from app.core.db import alembic_upgrade  # noqa: E402
from app.core.error_handlers import register_error_handlers  # noqa: E402
from app.core.rate_limit import limiter  # noqa: E402
from app.core.settings import load_web_settings  # noqa: E402
from app.core.wiring import build_container, unpack_container  # noqa: E402
from app.routers.admin_router import router as admin_router  # noqa: E402
from app.routers.form_router import router as form_router  # noqa: E402
from app.routers.public_router import router as public_router  # noqa: E402
from app.routers.webhook_router import router as webhook_router  # noqa: E402

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

# Expose every container field as a flat app.state attribute. Most
# consumers read it via the app/core/dependencies.py getters; the
# webhook router and admin_context are documented exceptions that read
# app.state directly (see docs/arch_http_boundary.md).
# tests/test_wiring.py pins the getter <-> field contract.
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

register_error_handlers(app)


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

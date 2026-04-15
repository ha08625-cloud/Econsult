# HTTP Boundary & Orchestration

**LLM INSTRUCTIONS:** This document covers design decisions and strict boundaries for `main.py`, `request_validation.py`, and the three routers. Read the source files directly for endpoint signatures, payload field names, and exact validation rules.

---

## Scope

The FastAPI application entry point, startup validation, resource initialisation, router registration, error handling, and static file serving.

**Key files:** `main.py`, `request_validation.py`, `app/routers/public_router.py`, `app/routers/admin_router.py`, `app/routers/admin/` (sub-package), `app/routers/form_router.py`, `app/core/dependencies.py`, `app/services/delivery/delivery_service.py`

---

## Architectural Rules (Strictly Enforced)

- `main.py` is the **imperative shell only**. It contains no route handlers except `/healthz`. Its responsibilities are: environment guards, repository and registry instantiation, startup validation, router registration, error handler registration, and static file serving.
- Clinical presentation metadata (e.g. `condition_label`) is resolved from the registry in the router handler and passed explicitly to engine adapters. It never enters the core engine.
- Repositories and registries are initialised **once at startup** and stored in `app.state`. Routers access them exclusively via dependency provider functions in `app/core/dependencies.py` — never via direct `request.app.state` access inside handler bodies, and never via direct imports from `main.py`. This prevents circular imports and keeps handler signatures self-documenting.
- The `/admin` prefix and `"admin"` tag are applied when the admin router is registered in `main.py`, not inside `admin_router.py`. This keeps the router decoupled from its mount point.
- `admin_router.py` is a thin orchestrator only. It registers four sub-routers from `app/routers/admin/` and contains no route handlers itself. Per-domain tags (`admin-auth`, `admin-practice`, `admin-availability`, `admin-audit`) are applied at include time.
- **All API routes must be registered before the static file mount block.** The catch-all static mount must come last or it will intercept API requests.

---

## Startup Validation (Fail-Fast)

Any failure in startup validation raises a `RuntimeError` and aborts. A misconfigured deployment must never silently degrade.

**Startup sequence:**
1. `import os`, `import logging`, and `init_telemetry("http-api")` execute — Sentry is initialised before any other internal import so that module-load failures (e.g. a failed Alembic migration) are captured by Sentry's default `sys.excepthook`
2. `DATABASE_URL` checked at module load time — failure prevents the app object from being created
3. Alembic migrations run (`alembic_upgrade()`) — a failed migration aborts startup
4. `_validate_startup()` runs and stores `practice_id` in `app.state` — wrapped in `sentry_sdk.set_tag("phase", "startup")` / `"running"` so any `RuntimeError` raised here is tagged in Sentry
5. `availability_repo.init_availability()` seeds a default availability row if absent — must run after step 4 so the practice row exists

**Validation rules enforced by `_validate_startup()`:**
- `PRACTICE_ID` env var must be set.
- If the practice record does not exist, it is **seeded automatically** from `PRACTICE_NAME` and `PRACTICE_EMAIL` env vars. This handles cloud deployments where the DB starts empty on container restart. It is safe to run on every startup — skips if the row already exists.
- The database must contain **exactly one practice**. Multiple practices is a clinically unsafe configuration (cross-contamination risk) and aborts startup.
- The practice must have a non-empty email address.
- Unless DEV_MODE=1: either MAILGUN_API_KEY+MAILGUN_DOMAIN(Mailgun HTTP) orSMTP_HOST+SMTP_USER+SMTP_PASSWORD(SMTP) must be set, plusEMAIL_FROMin both cases. Validation is handled by_validate_email_config().
- Unless `DEV_MODE=1`: `INITIAL_ADMIN_EMAIL` and `ALLOWED_ADMIN_DOMAINS` must be set.
- `INITIAL_ADMIN_EMAIL` domain is validated against `ALLOWED_ADMIN_DOMAINS` on **every startup** (not just first run). If the domain is not in the allowed list, startup aborts. This catches the case where domains are changed without updating the seed email.
- If `admin_users` is empty for the practice, `INITIAL_ADMIN_EMAIL` is inserted as the first admin user with `role="admin"`. This seeding is idempotent — if the user already exists (unique constraint on email), the startup would crash; the count check guards against this.
- `ADMIN_TOKEN` is **no longer required** in production — MFA replaces it. If `ADMIN_TOKEN` is set alongside MFA in production, a warning is logged (both auth methods active). In `DEV_MODE` without `ADMIN_TOKEN`, a warning is logged and any non-empty bearer token is accepted by admin endpoints via the DEV_MODE fallback in `require_admin`.

**`app.state` values set by startup:**

| Key | Type | Description |
|---|---|---|
| `practice_id` | str | The configured practice identifier |
| `registry` | ConditionRegistry | Condition rulesets, immutable after load |
| `practice_repo` | PracticeRepository | Practice record access |
| `availability_repo` | AvailabilityRepository | Availability config access |
| `presentation_service` | PresentationService | Read-only composition for patient frontend |
| `runtime_repo` | RuntimeStateRepository | Form session state |
| `submission_repo` | SubmissionRepository | Submission records |
| `attachment_repo` | AttachmentRepository | PDF attachment storage |
| `pdf_repo` | PDFRepository | PDF job queue |
| `photo_repo` | PhotoRepository | Patient photo storage |
| `delivery_repo` | DeliveryRepository | Delivery job queue |
| `auth_repo` | AuthRepository | Admin MFA auth — users, codes, sessions |
| delivery_service | DeliveryService | Clinical email delivery (Console, Mailgun HTTP, or SMTP) |
| admin_delivery_service | AdminDeliveryService | MFA code email delivery (Console, Mailgun HTTP, or SMTP) |
| `practice_name` | str \| None | Captured once for PDF generation |
| `allowed_admin_domains` | str | Comma-separated permitted admin email domains |

---

## Delivery Service Instantiation

`main.py` instantiates two delivery services at startup:

**Clinical delivery** (`app.state.delivery_service`):
- `DEV_MODE=1`: `ConsoleDeliveryService` — logs the email body to stdout, never sends.
- `MAILGUN_API_KEY` set: `MailgunHttpDeliveryService` — sends via Mailgun EU HTTP API.
- Otherwise: `EmailDeliveryService` — sends via SMTP.

**Admin MFA delivery** (`app.state.admin_delivery_service`):
- `DEV_MODE=1`: `ConsoleAdminDeliveryService` — logs the MFA code to stdout, never sends.
- `MAILGUN_API_KEY` set: `MailgunHttpAdminDeliveryService` — sends via Mailgun EU HTTP API.
- Otherwise: `AdminDeliveryService` — sends via SMTP, separate connection from clinical path.

Both console implementations raise `RuntimeError` at instantiation if `DEV_MODE` is not set, preventing accidental production use. Selection logic is mirrored in `worker_main.py` for the delivery worker process.

Both console implementations raise `RuntimeError` at instantiation if `DEV_MODE` is not set, preventing accidental production use.

---

## Error Handlers

Three exception handlers are registered in `main.py`:

| Exception | HTTP status | Response body |
|---|---|---|
| `APIError` | 422 | `{"error": {"code": "...", "message": "..."}}` |
| `ConditionNotFound` | 404 | `{"error": {"code": "CONDITION_NOT_FOUND", "message": "..."}}` |
| `RateLimitError` | 429 | `{"error": {"code": "RATE_LIMIT_EXCEEDED", "message": "..."}}` |

`RateLimitError` is a separate exception class (not an `APIError` subclass) because the `APIError` handler hardcodes status 422. `SESSION_EXPIRED` is raised directly as `HTTPException(status_code=401)` in `admin_context.py` and does not require a registered handler.

`ConditionNotFound` is defined in `app/core/errors.py` (not `condition_registry.py`). This separation is required so `telemetry.py` can reference it in `ignore_errors` without importing `condition_registry`, which has transitive service dependencies.

`APIError`, `ConditionNotFound`, and `RateLimitError` are all passed to Sentry's `ignore_errors` list in `telemetry.py`. This prevents expected 4xx responses from generating false-positive alerts while still allowing unhandled 5xx exceptions to reach Sentry via FastAPI's default exception hook.

The test factory in `test_admin_router.py` registers the same three handlers so that error-path tests reflect production behaviour.

---

## Availability Orchestration

`check_availability()` in `app/services/availability_orchestration.py` wires `AvailabilityRepository` and `availability_service` together. It does not belong in `availability_service.py` because the service layer has no database access.

**Fail-open rule:** Any exception during an availability check (database, network, logic) must be caught and execution must continue as if the practice is open. Patients must never be locked out due to system errors.

---

## Submission Ordering (form/finish)

`POST /form/finish` accepts `multipart/form-data`. The JSON payload is sent as a string in the `payload` form field. Photos are sent as optional `photos` file fields. Do not set `Content-Type` manually when calling this endpoint — the browser (or httpx in tests) sets it automatically with the correct boundary when a `FormData` object is used.

The handler body executes in this order: validate payload, read photo bytes, assemble `PatientDetails`, load runtime state, run engine, `create_submission`, `save_photos`, `create_job`, `close_session`, return `submission_id`. See `arch_submission.md` for full detail.

---

## Request Validation (`request_validation.py`)

Validates HTTP input for the three form endpoints before any engine call. Raises `INVALID_PAYLOAD` on failure. Extra/unexpected fields in the payload are rejected — the validator uses an allowlist, not a blocklist. See the source file for exact field rules.

---

## Static File Serving

The built Vite frontend is served from `frontend/dist/` via a `StaticFiles` mount. This mount is only activated if the `dist/` directory exists. In local development, Vite serves the frontend directly, so `dist/` is absent and the mount is skipped automatically. `DEV_MODE` does not control this — it only controls email and auth behaviour.

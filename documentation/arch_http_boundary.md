# HTTP Boundary & Orchestration

**LLM INSTRUCTIONS:** This document covers design decisions and strict boundaries for `main.py`, `request_validation.py`, and the three routers. Read the source files directly for endpoint signatures, payload field names, and exact validation rules.

---

## Scope

The FastAPI application entry point, startup validation, resource initialisation, router registration, error handling, and static file serving.

**Key files:** `main.py`, `app/core/settings.py`, `app/core/wiring.py`, `app/core/error_handlers.py`, `request_validation.py`, `app/routers/public_router.py`, `app/routers/admin_router.py`, `app/routers/form_router.py`, `app/core/dependencies.py`, `app/core/state_keys.py`, `app/services/delivery/delivery_service.py`

---

## Architectural Rules (Strictly Enforced)

- `main.py` is the **imperative shell only**. It contains no route handlers except `/healthz`. It delegates configuration to `app/core/settings.py` (environment-variable validation) and construction to `app/core/wiring.py` (the `AppContainer`: registry, repositories, services, startup-derived scalars, plus the DB-backed deployment checks). `main.py`'s own responsibilities are limited to ordering the startup sequence: telemetry, settings load, rate-limit middleware, migrations, container build, unpacking the container onto `app.state`, default-availability seeding, router registration, error handler registration, and static file serving.
- Clinical presentation metadata (e.g. `condition_label`) is resolved from the registry in the router handler and passed explicitly to engine adapters. It never enters the core engine.
- Repositories and registries are constructed **once at startup** inside `build_container` and exposed on `app.state` by `unpack_container`, which iterates `dataclasses.fields(AppContainer)` so the `app.state` key for each field cannot drift from the container. Routers access them exclusively via dependency provider functions in `app/core/dependencies.py` — never via direct `request.app.state` access inside handler bodies, and never via direct imports from `main.py`.
- **Documented exception:** `app/core/admin_context.py` reads `app.state.auth_repo` directly (via the shared `AUTH_REPO` constant) rather than through the `get_auth_repo` provider. This is deliberate dependency inversion, not an oversight: `admin_context` is a security boundary kept to a minimal import surface and depends on the `AuthProvider` Protocol rather than the repository/wiring closure that `dependencies.py` imports at module load. The shared attribute name lives in the leaf module `app/core/state_keys.py` so it cannot drift, and `tests/test_admin_context.py` pins the minimal import surface in a subprocess.
- The `/admin` prefix and `"admin"` tag are applied when the admin router is registered in `main.py`, not inside `admin_router.py`.
- **All API routes must be registered before the static file mount block.** The catch-all static mount must come last or it will intercept API requests.

---

## Startup Validation (Fail-Fast)

Any failure in startup validation raises a `RuntimeError` and aborts. A misconfigured deployment must never silently degrade. Validation is split by what it needs: `app/core/settings.py` owns everything checkable from environment variables alone; `app/core/wiring.py` owns the checks that require a database connection.

**Startup sequence (`main.py`, module level):**
1. `init_telemetry("http-api")` executes before any other internal import, so Sentry captures exceptions raised during module-level startup
2. `load_web_settings()` validates all environment variables and converts pydantic `ValidationError` into a `RuntimeError` with the operator-facing messages
3. Rate-limit limiter attached and `SlowAPIMiddleware` added
4. Alembic migrations run (`alembic_upgrade()`)
5. `build_container(settings)` constructs repositories, runs the DB-backed deployment checks, captures `practice_name`, and selects the delivery services; constructing the frozen `AppContainer` is itself the completeness check
6. `unpack_container(app, container)` exposes every field on `app.state`
7. `availability_repo.init_availability()` seeds a default availability row if absent

**Environment-variable rules (`app/core/settings.py`):**
- `PRACTICE_ID`, `DATABASE_URL`, `ALLOWED_ADMIN_DOMAINS` must be set.
- `EMAIL_FROM` must be set, plus a complete email path: either `MAILGUN_API_KEY` + `MAILGUN_DOMAIN` (Mailgun) or `SMTP_HOST` + `SMTP_USER` + `SMTP_PASSWORD` (SMTP).
- `MAILGUN_SIGNING_KEY` is required only when the Mailgun path is selected (see `EmailSettings.delivery_mode`).
- `MESH_DELIVERY` must be exactly `"0"` or `"1"`; `"1"` is rejected in Phase 1a.
- A partial Mailgun configuration (one of `MAILGUN_API_KEY` / `MAILGUN_DOMAIN` but not both) falls through to SMTP if SMTP is complete, logging a warning so the demotion is visible; if SMTP is incomplete, startup aborts.
- `DATA_DIR` is optional, defaulting to `<project root>/data`.

**Database-backed rules (`wiring.run_deployment_checks`):**
- The practice record must exist in the database.
- The practice must have a non-empty email address.
- The database must contain **exactly one practice**.
- At least one admin user must exist for the practice.

**`app.state` values set by startup (one per `AppContainer` field):**

| Key | Type | Description |
|---|---|---|
| `registry` | ConditionRegistry | Condition rulesets, immutable after load |
| `practice_repo` | PracticeRepository | Practice record access |
| `availability_repo` | AvailabilityRepository | Availability config access |
| `runtime_repo` | RuntimeStateRepository | Form session state |
| `submission_repo` | SubmissionRepository | Submission records |
| `attachment_repo` | AttachmentRepository | PDF attachment storage |
| `pdf_repo` | PDFRepository | PDF job queue |
| `photo_repo` | PhotoRepository | Patient photo storage |
| `delivery_repo` | DeliveryRepository | Delivery job queue |
| `auth_repo` | AuthRepository | Admin auth — users, codes, sessions, reset tokens |
| `audit_repo` | AuditRepository | Admin audit log |
| `presentation_service` | PresentationService | Read-only composition for patient frontend |
| `delivery_service` | DeliveryService | Clinical email delivery |
| `admin_delivery_service` | AdminDeliveryService | Admin MFA code and invitation email delivery |
| `practice_id` | str | The configured practice identifier |
| `practice_name` | str \| None | Captured once for PDF generation |
| `allowed_admin_domains` | str | Comma-separated permitted admin email domains |
| `mailgun_signing_key` | str \| None | Webhook HMAC key; `None` on the SMTP path |
| `database_url` | str | Connection string, used by the webhook replay-protection path |

---

## Delivery Service Instantiation

`build_container` selects both delivery services from a single predicate, `settings.email.delivery_mode`, which returns `"mailgun"` only when a **complete** Mailgun configuration is present (`MAILGUN_API_KEY` + `MAILGUN_DOMAIN`) and `"smtp"` otherwise. This replaced two inconsistent legacy predicates (a startup check requiring key + domain, and a service-selection branch checking the key alone).

**Clinical delivery** (`app.state.delivery_service`):
- `delivery_mode == "mailgun"`: `MailgunHttpDeliveryService`
- Otherwise: `EmailDeliveryService`

**Admin delivery** (`app.state.admin_delivery_service`):
- `delivery_mode == "mailgun"`: `MailgunHttpAdminDeliveryService`
- Otherwise: `AdminDeliveryService`

The service constructors read their own additional environment variables (e.g. `ADMIN_URL`, SMTP port/timeout); those are not validated by `settings.py`. Construction happens after the DB-backed deployment checks, preserving the legacy startup error precedence.

---

## Error Handlers

Five exception handlers are defined in `app/core/error_handlers.py` and attached by `register_error_handlers(app)`, which `main.py` calls during startup. The relocation from `main.py` is a pure refactor; behaviour, status codes, and response envelopes are unchanged.

| Exception | HTTP status | Response body |
|---|---|---|
| `APIError` | `exc.status_code` (default 422) | `{"error": {"code": "...", "message": "..."}}` |
| `ConditionNotFound` | 404 | `{"error": {"code": "CONDITION_NOT_FOUND", "message": "..."}}` |
| `RateLimitError` | 429 | `{"error": {"code": "RATE_LIMIT_EXCEEDED", "message": "..."}}` |
| `RateLimitExceeded` (slowapi) | 429 | `{"error": {"code": "RATE_LIMIT_EXCEEDED", "message": "Too many requests. Please try again later."}}` |
| `HTTPException` (401) | 401 | `{"error": {"code": "UNAUTHORIZED", "message": "..."}}` |

`RateLimitExceeded` is raised by slowapi when a `@limiter.limit()` decorator rejects a request; its handler returns the same envelope shape as the service-layer `RateLimitError` handler so the frontend sees a consistent 429.

`RateLimitError` is a separate exception class (not an `APIError` subclass) because the `APIError` handler uses `exc.status_code` rather than hardcoding 422. The 401s raised by `admin_context.py` (absent cookie or expired/missing session) are plain `HTTPException(status_code=401)` with a detail string; the `HTTPException` handler reshapes them into the `UNAUTHORIZED` envelope.

`APIError`, `ConditionNotFound`, and `RateLimitError` are passed to Sentry's `ignore_errors` list to suppress expected 4xx responses.

The test factory `make_test_app` in `admin_test_helpers.py` registers the same handlers so error-path tests reflect production behaviour.

**Password auth error codes** (all `APIError` subclasses, HTTP 422 unless noted):

| Code | Raised by | Meaning |
|---|---|---|
| `INVALID_CREDENTIALS` | `verify_login_credentials` | Generic failure for all password-step gates — wrong password, user not found, locked, no password set, OTP cooldown active. Deliberately generic to prevent gate enumeration. |
| `INVALID_RESET_TOKEN` | `verify_reset_token` | Token absent, expired, or already consumed. |
| `WEAK_PASSWORD` | `set_new_password` | zxcvbn score below threshold. Message contains specific feedback. |

---

## Admin Auth Endpoints (`/admin/auth/*`)

All four auth endpoints are unauthenticated. They are the mechanism by which an admin establishes a session and cannot require one.

| Method | Path | Rate limit | Description |
|---|---|---|---|
| `POST` | `/admin/auth/login` | 5/min | Step 1: verify password. On success, synchronously upserts OTP to `admin_auth_codes`, then dispatches email delivery as a `BackgroundTask`. Returns 200. |
| `POST` | `/admin/auth/verify` | 5/min | Step 2: verify OTP. On success, creates session and sets `session_id` HttpOnly cookie. |
| `POST` | `/admin/auth/request-reset` | 5/min | Request a password setup/reset link. Always returns 200 (anti-enumeration). |
| `POST` | `/admin/auth/set-password` | 5/min | Set a new password using a reset token from the URL hash. |
| `POST` | `/admin/auth/logout` | none | Delete session and clear cookie. Unauthenticated. |

**`BackgroundTasks` usage in `POST /admin/auth/login`:**
FastAPI injects `BackgroundTasks` automatically when it appears in the handler signature (no `Depends()` needed). The OTP DB upsert is synchronous — it happens before the 200 response is returned. Only the network call to the delivery service is backgrounded. If the background task fails, it catches the exception, reports to Sentry, and deletes the OTP record from the database to allow an immediate retry.

---

## Availability Orchestration

`check_availability()` in `app/services/availability_orchestration.py` wires `AvailabilityRepository` and `availability_service` together.

**Fail-open rule:** Any exception during an availability check must be caught and execution must continue as if the practice is open.

---

## Submission Ordering (form/finish)

`POST /form/finish` accepts `multipart/form-data`. The JSON payload is sent as a string in the `payload` form field. See `arch_submission.md` for full detail.

---

## Request Validation (`request_validation.py`)

Validates HTTP input for the three form endpoints before any engine call. Raises `INVALID_PAYLOAD` on failure. Extra/unexpected fields are rejected.

---

## Static File Serving

The built Vite frontend is served from `frontend/dist/` via a `StaticFiles` mount, activated only if the `dist/` directory exists. In local development where Vite has not run a build, the directory is absent and static serving is silently skipped.
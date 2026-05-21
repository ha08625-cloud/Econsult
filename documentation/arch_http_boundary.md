# HTTP Boundary & Orchestration

**LLM INSTRUCTIONS:** This document covers design decisions and strict boundaries for `main.py`, `request_validation.py`, and the three routers. Read the source files directly for endpoint signatures, payload field names, and exact validation rules.

---

## Scope

The FastAPI application entry point, startup validation, resource initialisation, router registration, error handling, and static file serving.

**Key files:** `main.py`, `request_validation.py`, `app/routers/public_router.py`, `app/routers/admin_router.py`, `app/routers/form_router.py`, `app/core/dependencies.py`, `app/services/delivery/delivery_service.py`

---

## Architectural Rules (Strictly Enforced)

- `main.py` is the **imperative shell only**. It contains no route handlers except `/healthz`. Its responsibilities are: environment guards, repository and registry instantiation, startup validation, router registration, error handler registration, and static file serving.
- Clinical presentation metadata (e.g. `condition_label`) is resolved from the registry in the router handler and passed explicitly to engine adapters. It never enters the core engine.
- Repositories and registries are initialised **once at startup** and stored in `app.state`. Routers access them exclusively via dependency provider functions in `app/core/dependencies.py` — never via direct `request.app.state` access inside handler bodies, and never via direct imports from `main.py`.
- The `/admin` prefix and `"admin"` tag are applied when the admin router is registered in `main.py`, not inside `admin_router.py`.
- **All API routes must be registered before the static file mount block.** The catch-all static mount must come last or it will intercept API requests.

---

## Startup Validation (Fail-Fast)

Any failure in startup validation raises a `RuntimeError` and aborts. A misconfigured deployment must never silently degrade.

**Startup sequence:**
1. `import os`, `import logging`, and `init_telemetry("http-api")` execute — Sentry is initialised before any other internal import
2. `DATABASE_URL` checked at module load time
3. Alembic migrations run (`alembic_upgrade()`)
4. `_validate_startup()` runs and stores `practice_id` in `app.state`
5. `availability_repo.init_availability()` seeds a default availability row if absent

**Validation rules enforced by `_validate_startup()`:**
- `PRACTICE_ID` env var must be set.
- The practice record must exist in the database.
- The practice must have a non-empty email address.
- The database must contain **exactly one practice**.
- Either `MAILGUN_API_KEY` + `MAILGUN_DOMAIN` or `SMTP_HOST` + `SMTP_USER` + `SMTP_PASSWORD` must be set, plus `EMAIL_FROM`.
- `ALLOWED_ADMIN_DOMAINS` must be set.
- At least one admin user must exist for the practice.

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
| `auth_repo` | AuthRepository | Admin auth — users, codes, sessions, reset tokens |
| `delivery_service` | DeliveryService | Clinical email delivery |
| `admin_delivery_service` | AdminDeliveryService | Admin MFA code and invitation email delivery |
| `practice_name` | str \| None | Captured once for PDF generation |
| `allowed_admin_domains` | str | Comma-separated permitted admin email domains |

---

## Delivery Service Instantiation

`main.py` instantiates two delivery services at startup:

**Clinical delivery** (`app.state.delivery_service`):
- `MAILGUN_API_KEY` set: `MailgunHttpDeliveryService`
- Otherwise: `EmailDeliveryService`

**Admin delivery** (`app.state.admin_delivery_service`):
- `MAILGUN_API_KEY` set: `MailgunHttpAdminDeliveryService`
- Otherwise: `AdminDeliveryService`

---

## Error Handlers

Four exception handlers are registered in `main.py`:

| Exception | HTTP status | Response body |
|---|---|---|
| `APIError` | `exc.status_code` (default 422) | `{"error": {"code": "...", "message": "..."}}` |
| `ConditionNotFound` | 404 | `{"error": {"code": "CONDITION_NOT_FOUND", "message": "..."}}` |
| `RateLimitError` | 429 | `{"error": {"code": "RATE_LIMIT_EXCEEDED", "message": "..."}}` |
| `HTTPException` (401) | 401 | `{"error": {"code": "UNAUTHORIZED", "message": "..."}}` |

`RateLimitError` is a separate exception class (not an `APIError` subclass) because the `APIError` handler uses `exc.status_code` rather than hardcoding 422. `SESSION_EXPIRED` is raised directly as `HTTPException(status_code=401)` in `admin_context.py` and reshaped by the `HTTPException` handler.

`APIError`, `ConditionNotFound`, and `RateLimitError` are passed to Sentry's `ignore_errors` list to suppress expected 4xx responses.

The test factory in `test_admin_router.py` registers the same handlers so error-path tests reflect production behaviour.

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
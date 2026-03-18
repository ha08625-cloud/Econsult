# HTTP Boundary & Orchestration

**LLM INSTRUCTIONS:** This document covers design decisions and strict boundaries for `main.py` and `request_validation.py`. Read the source files directly for endpoint signatures, payload field names, and exact validation rules.

---

## Scope

The FastAPI application entry point, startup validation, resource initialisation, HTTP-to-engine orchestration, and static file serving.

**Key files:** `main.py`, `request_validation.py`, `errors.py`

---

## Architectural Rules (Strictly Enforced)

- `main.py` is the **imperative shell only**. It MUST NOT contain clinical logic, safety rule evaluation, or encoder invocation. It translates HTTP requests into engine entry point calls.
- Clinical presentation metadata (e.g. `condition_label`) is resolved from the registry in `main.py` and passed explicitly to engine adapters. It never enters the core engine.
- Repositories and registries are initialised **once at startup** and stored in `app.state`. Routers access them via FastAPI `Depends` dependency provider functions, never via direct imports from `main.py`. This prevents circular imports.
- The `/admin` prefix and `"admin"` tag are applied when the admin router is registered in `main.py`, not inside `admin_router.py`. This keeps the router decoupled from its mount point.
- **All API routes must be registered before the static file mount block.** The catch-all static mount must come last or it will intercept API requests.

---

## Error Handling

The `api_error_handler` is registered on `app` in `main.py`. It catches `APIError` exceptions raised anywhere in the application (including routers) and returns:

```json
{"error": {"code": "...", "message": "..."}}
```

with HTTP 422. All named error constructors live in `errors.py`. The admin frontend reads both `body.detail` (legacy) and `body.error.message` (current) — see `arch_admin.md`.

`HTTPException` is used only for the 401 auth failure in `admin_context.py`. All other error paths use `APIError`.

---

## Startup Validation (Fail-Fast)

Any failure in startup validation raises a `RuntimeError` and aborts. A misconfigured deployment must never silently degrade.

**Startup sequence:**
1. `DATABASE_URL` checked at module load time — failure prevents the app object from being created
2. Alembic migrations run (`alembic_upgrade()`) — a failed migration aborts startup
3. `_validate_startup()` runs and stores `practice_id` in `app.state`
4. `availability_repo.init_availability()` seeds a default availability row if absent — must run after step 3 so the practice row exists

**Validation rules enforced by `_validate_startup()`:**
- `PRACTICE_ID` env var must be set
- If the practice record does not exist, it is **seeded automatically** from `PRACTICE_NAME` and `PRACTICE_EMAIL` env vars. This handles cloud deployments where the DB starts empty on container restart. It is safe to run on every startup — skips if the row already exists.
- The database must contain **exactly one practice**. Multiple practices is a clinically unsafe configuration (cross-contamination risk) and aborts startup.
- The practice must have a non-empty email address.
- Unless `DEV_MODE=1`: `SMTP_HOST`, `SMTP_USER`, `SMTP_PASSWORD`, `EMAIL_FROM`, and `ADMIN_TOKEN` must all be set.
- In `DEV_MODE` without `ADMIN_TOKEN`: a warning is logged but startup proceeds. Any non-empty bearer token is accepted by admin endpoints.

---

## Availability Orchestration

`check_availability()` in `main.py` wires `AvailabilityRepository` and `availability_service` together. It does not belong in `availability_service.py` because the service layer has no database access. This follows the same pattern as `engine_adapters.py`: services contain pure logic; orchestration lives in the calling layer.

**Fail-open rule:** Any exception during an availability check (database, network, logic) must be caught and execution must continue as if the practice is open. Patients must never be locked out due to system errors.

This applies in both `POST /form/init` (blocks entry if closed) and `POST /form/finish` (sets `submitted_after_hours` flag). In `form/finish`, the default on failure is `submitted_after_hours = false` — uncertainty must not alarm the patient.

---

## Submission Ordering (form/finish)

The submission record is created in the database with `delivery_status = "pending"` **before** the email send is attempted. This ensures the record is not lost if the SMTP connection fails. The status is updated to `"sent"` or `"failed"` after the attempt. The session is closed last, after both the DB write and the email attempt.

---

## Request Validation (`request_validation.py`)

Validates HTTP input for the three form endpoints before any engine call. Raises `INVALID_PAYLOAD` on failure. Extra/unexpected fields in the payload are rejected — the validator uses an allowlist, not a blocklist. See the source file for exact field rules.

---

## Static File Serving

The built Vite frontend is served from `frontend/dist/` via a `StaticFiles` mount. This mount is only activated if the `dist/` directory exists. In local development, Vite serves the frontend directly, so `dist/` is absent and the mount is skipped automatically. `DEV_MODE` does not control this — it only controls email and auth behaviour.

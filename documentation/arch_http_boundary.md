# HTTP Boundary & Orchestration

**LLM INSTRUCTIONS:** This document covers design decisions and strict boundaries for `main.py`, `request_validation.py`, and the three routers. Read the source files directly for endpoint signatures, payload field names, and exact validation rules.

---

## Scope

The FastAPI application entry point, startup validation, resource initialisation, router registration, error handling, and static file serving.

**Key files:** `main.py`, `request_validation.py`, `app/routers/public_router.py`, `app/routers/admin_router.py`, `app/routers/form_router.py`, `app/core/dependencies.py`, `app/services/delivery_service.py`

---

## Architectural Rules (Strictly Enforced)

- `main.py` is the **imperative shell only**. It contains no route handlers except `/healthz`. Its responsibilities are: environment guards, repository and registry instantiation, startup validation, router registration, error handler registration, and static file serving.
- Clinical presentation metadata (e.g. `condition_label`) is resolved from the registry in the router handler and passed explicitly to engine adapters. It never enters the core engine.
- Repositories and registries are initialised **once at startup** and stored in `app.state`. Routers access them exclusively via dependency provider functions in `app/core/dependencies.py` — never via direct `request.app.state` access inside handler bodies, and never via direct imports from `main.py`. This prevents circular imports and keeps handler signatures self-documenting.
- The `/admin` prefix and `"admin"` tag are applied when the admin router is registered in `main.py`, not inside `admin_router.py`. This keeps the router decoupled from its mount point.
- **All API routes must be registered before the static file mount block.** The catch-all static mount must come last or it will intercept API requests.

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

## Delivery Service Instantiation

`main.py` instantiates the delivery service conditionally at startup and stores it in `app.state.delivery_service`:

- `DEV_MODE=1`: `ConsoleDeliveryService` — logs the email body to stdout, never sends. Raises `RuntimeError` at instantiation if `DEV_MODE` is not set, preventing accidental production use.
- Production: `EmailDeliveryService` — reads SMTP config from environment variables at instantiation time. A missing variable raises `RuntimeError` at startup, not silently at send time.

Neither constructor takes `practice_name`. PDF generation has moved to `form_router.py`, where `practice_name` is injected via `get_practice_name` dependency. `app.state.practice_name` is captured once at startup from the practice record.

Form handlers access the delivery service via `get_delivery_service` from `dependencies.py`. The abstract base class `DeliveryService` is defined in `app/services/delivery_service.py`. `email_service.py` no longer exists — it was replaced by `delivery_service.py` in Phase 3.

---

## Availability Orchestration

`check_availability()` in `app/services/availability_orchestration.py` wires `AvailabilityRepository` and `availability_service` together. It does not belong in `availability_service.py` because the service layer has no database access. This follows the same pattern as `engine_adapters.py`: services contain pure logic; orchestration lives in the calling layer.

**Fail-open rule:** Any exception during an availability check (database, network, logic) must be caught and execution must continue as if the practice is open. Patients must never be locked out due to system errors.

This applies in `POST /form/init`, which blocks entry if the practice is closed. The `POST /form/finish` endpoint does **not** perform an availability check. Whether the practice was open is determined from the availability fetch that occurred at Screen 0 (session start) and is held in frontend state — it is not re-checked at submission time.

---

## Submission Ordering (form/finish)

The submission record is created in the database with `delivery_status = "pending"` **before** any delivery is attempted. This ensures the record is not lost if the SMTP connection fails.

After `create_submission`, `form_finish` generates the PDF via `generate_pdf()` and stores the bytes via `attachment_repo.save_attachment()`. Both the submission record and the attachment are persisted before the delivery attempt begins. The PDF bytes are then passed to `delivery_service.send_clinical_output()` — the delivery service does not generate the PDF.

The status is updated to `"sent"` or `"failed"` after the delivery attempt. The session is closed last, after both the DB write and the email attempt.

`EmailDeliveryError` is caught in `form_finish` and must never propagate as an HTTP error. The patient must always receive their `submission_id` regardless of delivery outcome.

---

## Request Validation (`request_validation.py`)

Validates HTTP input for the three form endpoints before any engine call. Raises `INVALID_PAYLOAD` on failure. Extra/unexpected fields in the payload are rejected — the validator uses an allowlist, not a blocklist. See the source file for exact field rules.

`contact_preferences` is validated by `validate_finish_payload` and then extracted by the `form_finish` handler, which passes it to `finish_runtime_state()`. It is stored inside `ClinicalOutput` and included in the delivery payload.

---

## Static File Serving

The built Vite frontend is served from `frontend/dist/` via a `StaticFiles` mount. This mount is only activated if the `dist/` directory exists. In local development, Vite serves the frontend directly, so `dist/` is absent and the mount is skipped automatically. `DEV_MODE` does not control this — it only controls email and auth behaviour.

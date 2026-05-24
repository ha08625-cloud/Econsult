# FILE_STRUCTURE.md
# LLM reference: actual local directory layout, structural purpose, and import mapping
# Last updated: 2026-04-24

---

## 1. Top-level layout

- `main.py` — FastAPI entry point. HTTP layer only.
- `worker_main.py` — Delivery worker entry point. No HTTP server, no migrations.
- `pdf_worker_main.py` — PDF worker entry point. No HTTP server, no migrations.
- `deletion_job.py` — Nightly cron one-shot script.
- `.env` — Local environment variables, not committed.
- `Dockerfile` — Container build definition (Vite + Python).
- `build.sh` — Build script used by the container.
- `railway.toml` — Railway deployment config.
- `requirements.txt` — Python dependencies.
- `alembic.ini` — Alembic configuration.
- `app/` — All Python application code.
- `alembic/` — Alembic migration scripts.
- `frontend/` — Patient-facing React app and Admin UI.
- `data/` — Condition ruleset JSON files.
- `scripts/` — One-time management commands for deployment and administration.
  - `create_admin_user.py` — Inserts an admin user before first boot. Generates a one-time password setup token and prints the setup URL. Accepts `--create-practice` flag for CI use.
- `docs/` — Architecture documents and operational guides.
  - `deployment_checklist.md` — Step-by-step checklist for deploying to a new environment.

---

## 2. Python application code (`app/`)

### 2.1 `app/models/`
Data structures only. No business logic, no IO, no imports from non-model modules.

- `api_models.py` — HTTP-layer data shapes.
- `encoder_contracts.py` — Encoder definitions.
- `explicit_answers.py` — Frozen, immutable projected answers.
- `runtime_state.py` — Form session state representations.
- `serialisation_contracts.py` — Output formatting contracts.
- `availability_models.py` — Availability definitions.

### 2.2 `app/services/`
Business logic and orchestration. 

**`app/services/engine/`** (Pure clinical logic. Deterministic, side-effect free except for pipeline.py)
- `form_logic.py` — Deterministic functional core. *Imports: RuntimeState, AnswerState, SafetyEvaluation.*
- `ruleset.py` — Condition ruleset JSON loader/validator. *Imports: standalone; no service imports.*
- `projection.py` — State projection boundary. *Imports: RuntimeState, ExplicitAnswers.*
- `safety_engine.py` — Safety rule evaluation. *Imports: ExplicitAnswers, SafetyEvaluation.*
- `serialisation.py` — State and output serialisation. *Imports: RuntimeState, ClinicalOutput, AuditOutput.*
- `encoder_mapping.py` — Encoder output mapping. *Imports: RuntimeState, EncoderOutput, EncoderSignalDefinition.*
- `encoder_stub.py` — Placeholder encoder. *Imports: standalone; no service imports.*
- `pipeline.py` — Engine orchestration. *Imports: may import all engine services above.*

**`app/services/delivery/`** (IO-touching delivery concerns)
- `delivery_service.py` — Email delivery implementations. *Imports: no clinical contract imports. Receives pre-rendered PDF bytes.*
- `admin_delivery_service.py` — Admin MFA and invitation delivery. Implements `send_mfa_code(email, code)` and `send_admin_invitation(email, token)`. The token is embedded in the setup URL as `#reset:{token}`. *Imports: stdlib only.*
- `delivery_constants.py` — Retry thresholds. *Imports: standalone; no application modules.*
- `pdf_constants.py` — PDF retry thresholds. *Imports: standalone; no application modules.*
- `delivery_worker.py` — Delivery worker loop. *Imports: delivery_repository, attachment_repository, delivery_service, delivery_constants, sentry_sdk only.*
- `pdf_worker.py` — PDF generation worker loop. *Imports: pdf_repository, photo_repository, submission_repository, attachment_repository, downstream_enqueuer, pdf_formatter, pdf_constants, sentry_sdk only.*
- `downstream_enqueuer.py` — Polymorphic seam between the PDF worker and its next-stage queue. Defines `DownstreamEnqueuer` Protocol and `DeliveryEnqueuer` (email path) implementation. Selected at worker startup based on `MESH_DELIVERY`. *Imports: pdf_repository, submission_repository, delivery_repository only.*

**`app/services/admin/`** (admin portal concerns - mirrors app/routers/admin/ subfolder)
- `auth_service.py` — MFA and password authentication business logic. Implements: `request_mfa_code`, `verify_mfa_code`, `verify_login_credentials` (timing-safe password check with dummy-hash path), `generate_reset_token`, `verify_reset_token`, `set_new_password` (zxcvbn strength enforcement, score >= 3). *Imports: bcrypt, zxcvbn, hashlib, secrets, time, datetime, errors. DB/delivery via interfaces only.*
- `user_service.py` — Admin user management business logic (add, remove, resend invitation). *Imports: errors, auth_service.validate_admin_domain, email_utils. Receives repositories and conn as arguments — no direct DB access.*
- `availability_orchestration.py` — Wires repository and service.
- `availability_service.py` — Availability business logic.

**`app/services/` (flat)**
- `presentation_service.py` — Patient-facing presentation assembler. *Imports: condition_registry, practice_repository.*

### 2.3 `app/repositories/`
Database access for persistent records. No business logic.

- `attachment_repository.py` — Owns `submission_attachments`. *Imports: db only.*
- `audit_repository.py` — Owns `admin_audit_log`. *Imports: db, psycopg2, base64, json, re, datetime only.*
- `auth_repository.py` — Owns `admin_users`, `admin_auth_codes`, `admin_sessions`, `admin_password_reset_tokens`. User management methods: `insert_user`, `get_users_by_practice` (accepts conn), `get_user_by_id`, `delete_user` (accepts conn), `create_session` (sets `last_login = NOW()` atomically). Password auth methods: `set_password` (sets hashed_password, password_changed_at, resets lockout atomically), `record_failed_password_attempt` (atomic increment; accepts optional lock_until), `reset_password_attempts`. Reset token methods: `upsert_reset_token` (ON CONFLICT DO UPDATE; accepts conn), `get_reset_token_record`, `delete_reset_token`. *Imports: db, psycopg2, uuid, datetime only.*
- `availability_repository.py` — Owns availability and exception tables.
- `delivery_repository.py` — Owns `delivery_jobs`. *Imports: db, delivery_constants only.*
- `pdf_repository.py` — Owns `pdf_jobs`. *Imports: db, pdf_constants only.*
- `photo_repository.py` — Owns `submission_photos`. *Imports: db only.*
- `practice_repository.py` — Owns practice records. Includes `lock_practice(practice_id, conn)` which executes `SELECT ... FOR UPDATE` to serialise concurrent user management operations. `conn` is required with no default. *Imports: no service modules.*
- `runtime_state_repository.py` — Owns session state versions.
- `submission_repository.py` — Owns `submission_records`. *Imports: db, serialisation_contracts only.*

### 2.4 `app/core/`
Infrastructure concerns only. No clinical logic.

- `admin_context.py` — Admin authentication context/dependencies. *Imports: stdlib and FastAPI only.*
- `condition_registry.py` — Ruleset indexer.
- `consultation_outcomes.py` — Python interface for outcome constants. *Imports: json and os only.*
- `db.py` — Shared Postgres connection module.
- `dependencies.py` — Shared FastAPI dependency provider functions.
- `errors.py` — Shared API, rate limit, and condition-not-found errors. `APIError` carries `status_code: int = 422`. User management errors: `USER_ALREADY_EXISTS` (409), `ACTION_NOT_PERMITTED` (403), `USER_NOT_FOUND` (404). Password auth errors: `INVALID_CREDENTIALS` (422, generic — does not reveal which gate failed), `INVALID_RESET_TOKEN` (422), `WEAK_PASSWORD` (422, message populated from zxcvbn feedback).
- `rate_limit.py` — SlowAPI Limiter instantiation. *Imports: slowapi, app.utils.http_utils only.*
- `request_validation.py` — HTTP payload validation.
- `telemetry.py` — Sentry initialisation. Called once at the top of each process entry point. *Imports: stdlib only at module level; sentry_sdk and app.core.errors imported lazily inside the function body. Must NOT import repositories, registries, or db.*
- `consultation_outcomes.json` — Canonical source for outcome values.
- `upload_constants.json` — Canonical source for photo upload limits.
- `upload_constants.py` — Python interface for upload constants.

### 2.5 `app/utils/`
Pure utility functions. No IO, no database access.

- `http_utils.py` — HTTP utility helpers (IP extraction). *Imports: stdlib only.*
- `email_utils.py` — Email format validation (`is_valid_email_format`). *Imports: stdlib only. Does NOT perform domain allowlist checks — that belongs in auth_service.*
- `pdf_formatter.py` — Pure PDF generation function. *Imports: ClinicalOutput and consultation_outcomes.*
- `image_sanitizer.py` — Content Disarm and Reconstruction (CDR) logic. *Imports: Pillow (PIL.Image) and io only.*

### 2.6 `app/routers/`
HTTP route handlers. No business logic; orchestration only.

- `public_router.py` — Patient-facing public endpoints (conditions list, availability check).
- `form_router.py` — Patient form session endpoints (start, answer, finish).
- `admin_router.py` — Thin orchestrator. Registers the five admin sub-routers. Contains no route handlers.
- `webhook_router.py` — Mailgun delivery webhook endpoint (`POST /webhooks/mailgun`). Enforces HMAC signature verification, timestamp staleness, and token-based replay protection. Reads `app.state.mailgun_signing_key` and `app.state.database_url`. *Imports: delivery_repository, db, fastapi, hmac, hashlib, time only.*

**`app/routers/admin/`** (Admin sub-router package)
- `__init__.py` — Package marker.
- `admin_auth_router.py` — Password login (step 1), OTP verify (step 2), password reset request, set-password, logout. Unauthenticated by design. `POST /auth/login` dispatches OTP email via FastAPI BackgroundTask; on delivery failure the background task deletes the OTP record and reports to Sentry.
- `admin_practice_router.py` — Conditions list, practice settings, signposting, doctor list.
- `admin_availability_router.py` — Weekly config, manual overrides, per-date exceptions.
- `admin_audit_router.py` — Audit log read endpoint.
- `admin_user_router.py` — List, add, delete, and resend-invitation for admin users. POST /users generates a reset token inside the user-insert transaction. POST /users/{id}/resend-invitation generates a fresh reset token before sending the invitation email. Rate-limits POST /users and POST /users/{id}/resend-invitation at 10/minute.

---

## 3. Alembic migrations (`alembic/`)
Schema migration scripts. See code files directly for exact table definitions.

- `alembic/env.py` — Alembic environment configuration.
- `alembic/versions/0001_initial_schema.py` — Creates the complete baseline schema.
- `alembic/versions/0002_user_management_cascade.py` — Adds `ON DELETE CASCADE` to `admin_sessions.user_id` FK; adds `admin_users.last_login` (nullable TIMESTAMPTZ).
- `alembic/versions/0003_webhook_tracking.py` — Adds `provider_message_id` (VARCHAR 255, indexed) and `provider_events` (JSONB) to `delivery_jobs`; extends status check constraint to include `provider_accepted` and `delivered`; creates `webhook_tokens` replay protection table.
- `alembic/versions/0004_password_auth.py` — Adds `hashed_password` (TEXT nullable), `failed_password_attempts` (INTEGER NOT NULL DEFAULT 0), `password_locked_until` (TIMESTAMPTZ nullable), `password_changed_at` (TIMESTAMPTZ nullable) to `admin_users`; creates `admin_password_reset_tokens` table (token_hash PK, user_id FK with ON DELETE CASCADE, UNIQUE(user_id) enforcing one active token per user, expires_at).

---

## 4. Frontend (`frontend/`)

**Patient UI (`frontend/src/`)**
- `App.tsx` — Root React component; session state owner.
- `ConditionCombobox.tsx` — Search and selection.
- `api.ts` — Typed HTTP clients.
- `constants.ts` & `upload_constants.ts` — Shared constants.
- `helpers.ts` — Pure helper functions.
- `layout.tsx` — Structural wrappers.
- `main.tsx` — React entry point.
- `search.ts` — Condition filtering.
- `types.ts` (wire contracts) & `uiTypes.ts` (UI-only types).
- `screens/` — Patient flow views (`SafetyWarningScreen`, `PatientDetailsScreen`, `OutcomeScreen`, `SelectConditionScreen`, `FreeTextScreen`, `EditScreen`, `ReviewScreen`, `ContactScreen`) and corresponding test files e.g. SafetyWarningScreen.test.tsx

**Admin UI (`frontend/admin-ui/src/`)**
- `App.tsx` — Admin root component. AuthState = `"checking" | "login" | "editor" | "set_password"`. On mount, checks `window.location.hash` for `#reset:{token}` before probing the session — if matched, routes directly to `set_password` state without an API call.
- `api.ts` — Admin API clients (cookie-auth based). Auth functions: `login(email, password)`, `verifyMfaCode(email, code)`, `requestPasswordReset(email)` (always resolves, never throws), `setPassword(token, password)`. User management functions: `fetchUsers`, `addUser`, `removeUser`, `resendInvitation`.
- `main.tsx` — React entry point.
- `types.ts` — Admin-specific contracts. Includes `AdminUser` and `AddUserResponse` interfaces.
- `screens/` — Admin views and corresponding test files:
  - `LoginView` — Two-step login: step 1 accepts email + password (calls `POST /auth/login`), step 2 accepts 6-digit OTP (calls `POST /auth/verify`). Includes "Forgot / Set up password?" link that calls `requestPasswordReset`.
  - `SetPasswordView` — Password setup/reset screen. Rendered when `authState === "set_password"`. Extracts and clears the `#reset:{token}` hash on mount. Includes zxcvbn real-time strength meter (score >= 3 required to submit). Handles `INVALID_RESET_TOKEN` and `WEAK_PASSWORD` server errors.
  - `EditorView`, `SignpostingEditor`, `AvailabilityEditor`, `PracticeSettingsTab`, `AuditLogTab`, `UsersTab`

---

## 5. Tests (`tests/`)

**Shared fixtures**
- `conftest.py` — Autouse pytest fixture that resets the SlowAPI in-memory rate limit storage before and after every test. Prevents counter state leaking across test boundaries.
- `helpers/admin_test_helpers.py` — Shared helpers for the admin sub-router tests. Provides `make_test_app`, `dummy_conn`, and stubs: `StubAuthRepo` (includes no-op password auth methods: `set_password`, `record_failed_password_attempt`, `reset_password_attempts`, `upsert_reset_token`, `get_reset_token_record`, `delete_reset_token`), `StubPracticeRepo` (includes `lock_practice`), `StubAvailabilityRepo`, `StubAuditRepo`, `StubAdminDeliveryService` (tracks `send_mfa_code` calls and `send_admin_invitation(email, token)` calls separately), `StubRegistry`.

**Unit tests (Mocked/In-memory)**
- `test_delivery_service.py`, `test_delivery_worker.py`, `test_pdf_worker.py`, `test_downstream_enqueuer.py`, `test_pdf_generation.py`, `test_image_sanitizer.py`, `test_practice_endpoint.py`, `test_request_validation.py`, `test_upload_constants.py`, `test_sanitise_signposting.py`.

**Admin Sub-Router unit tests (placed in tests/routers/ subfolder)**
- `test_admin_auth_router.py` — Covers: general auth behaviour, `POST /auth/login` (correct credentials, wrong password, lockout, no password set, missing fields), `POST /auth/verify` (OTP check, unchanged), `POST /auth/request-reset` (registered and unregistered emails), `POST /auth/set-password` (valid token, expired token, unknown token, weak password, token consumed on use), `POST /auth/logout`, SlowAPI rate limiting on all four unauthenticated auth endpoints.
- `test_admin_availability_router.py`, `test_admin_practice_router.py`, `test_admin_audit_router.py`, `test_admin_user_router.py`

**Frontend component tests (placed in frontend/admin-ui/src/screens/)**
- `LoginView_test.tsx` — Covers step 1 rendering (email + password inputs, Sign in button disabled until both filled, forgot link), step 1 behaviour (login() called with normalised credentials, advances to step 2, error handling), forgot/set-up link (calls requestPasswordReset, shows confirmation, prompts for email if blank), step 2 rendering and behaviour (unchanged from OTP flow), navigation between steps.
- `EditorView_test.tsx`, `SignpostingEditor_test.tsx` (if present), `AvailabilityEditor_test.tsx`, `PracticeSettingsTab_test.tsx`, `AuditLogTab_test.tsx`, `UsersTab_test.tsx`

**Integration tests (Live `TEST_DATABASE_URL`, placed in tests/integration/ subfolder)**
- `test_form_routes.py`, `test_public_routes.py`, `test_repositories.py`, `test_pipeline_repositories.py`, `test_webhook_router.py`.

---

## 6. Banned imports (Design failures if violated)

These structural boundaries MUST NOT be crossed:

* `engine/form_logic`, `engine/encoder_mapping`, `engine/encoder_stub`, `engine/safety_engine` **must NOT** import `condition_registry`, `practice_repository`, or `presentation_service`.
* `engine/safety_engine` **must NOT** import `RuntimeState`, `AnswerState`, or `encoder_contracts`.
* `engine/serialisation` **must NOT** mutate `RuntimeState`.
* `practice_repository` **must NOT** import any service module.
* `presentation_service` **must NOT** import `RuntimeState`, `safety_engine`, `encoder_*`, or `form_logic`.
* Any file in `app/routers/admin/` **must NOT** import engine modules, `presentation_service`, `serialisation`, `projection`, or `runtime_state`.
* `admin_router.py` (orchestrator) **must NOT** import anything other than FastAPI and the five admin sub-routers.
* `admin_context.py` **must NOT** import any project module other than stdlib and FastAPI.
* `auth_service.py` **must NOT** access any repository or database module directly.
* `auth_repository.py` **must NOT** import `auth_service`, `admin_delivery_service`, or any service module.
* `user_service.py` **must NOT** access the database directly or handle email delivery.
* `admin_delivery_service.py` **must NOT** import any repository, `auth_service`, or clinical module.
* `email_utils.py` **must NOT** import any application module.
* `delivery/delivery_service` **must NOT** import engine modules, repositories, `condition_registry`, or `pdf_formatter`.
* `delivery/delivery_worker` **must NOT** import clinical engine modules, routers, `condition_registry`, `pdf_formatter`, `serialisation`, or `submission_repository`.
* `delivery/pdf_worker` **must NOT** import any admin router, `form_router`, `public_router`, or any admin/presentation module.
* `delivery/delivery_constants` and `pdf/pdf_constants` **must NOT** import any application module.
* `audit_repository` **must NOT** import from service modules, routers, or the patient-facing request path.
* `http_utils` **must NOT** import any application module.
* `pdf_formatter` **must NOT** import delivery modules, repositories, routers, or any engine module.
* `image_sanitizer` **must NOT** import any service, repository, router, engine, or core module.
* `consultation_outcomes.py` **must NOT** import any application module.
* `photo_repository` **must NOT** implement a delete method (handled strictly by `deletion_job.py`).
* `telemetry.py` **must NOT** import any repository, registry, database module, or service module at module level. Only `app.core.errors` is permitted, and only as a deferred import inside `init_telemetry()`.
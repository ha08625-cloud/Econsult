# Econsult System Architecture (Hub)

**LLM INSTRUCTIONS:** This is the master map of the system. Do NOT assume architectural details. Use this document to understand the global invariants and locate the specific domain documentation (Spokes). Read the codebase files directly for implementation details (function signatures, schemas, etc.).  All codebase files exist in Claude's project files and are directly accessible.  Claude project files mostly have flat file names for simplicity - full paths are used only if there is ambiguity e.g. frontend/index.html vs frontend/admin-ui/index.html.  See file_structure.md for the definitive file structure

## 1. Project-Level Invariants (Strictly Enforced)

These rules apply universally and MUST NOT be violated by any new feature or refactor:

* **Declarative Clinical Meaning:** Clinical meaning lives *only* in declarative JSON rulesets, never in code.
* **Deterministic Core:** The engine interprets rulesets deterministically (functional core).
* **Imperative Shell:** The UI renders engine output statelessly; it contains no clinical logic.
* **Encoder Boundaries:** Encoder models output signals; they do *not* make decisions. Encoder-filled answers must NEVER overwrite patient answers.
* **Safety Isolation:** Safety netting advice comes exclusively from deterministically coded rules in the ruleset using simple IF/AND/OR logic. Safety logic never mutates state.
* **Fail-Open Availability:** Any failure in the availability check (database, network, logic) MUST fail-open and allow the patient to proceed.
* **State & Session Constraints:** The system is session-backed and server-owned. There is NO conversational memory, NO cross-session state, and NO per-user identity. State is never round-tripped through the client or mutated in place.
* **Fail-Fast Configuration:** A misconfigured deployment (missing env vars, invalid rulesets, database state violations) MUST abort at startup. It must never silently degrade into a state where forms are sent to the wrong destination or safety rules are skipped.
* **Test Maintenance Obligation:** Whenever a test file is created or modified, prompt the user to: (1) add `pytestmark = pytest.mark.integration` if it is an integration test, (2) verify `arch_testing.md` is up to date. No changes to `ci.yml` or `Makefile` are needed if the marker is present — pytest discovers integration tests automatically via the marker.

## 2. High-Level Data Flow

The system is a server-owned, session-backed pipeline composed of strictly separated modules. No module other than the pipeline is aware of execution order.

**Request Pipeline:**
`HTTP Boundary (validation)` -> `Pipeline (ordering)` -> `Form Logic (deterministic core)` -> `Serialization (views)` -> `Persistence (lossless RuntimeState)`

## 3. Capability Index (Domain Routing)

When modifying or adding features, locate the relevant capability below to identify the associated Domain Architecture Document and key files.

### 3.1 Core Engine & Clinical Logic
* **Scope:** Contains core data flows for form initialization and submission, ruleset loading, applying patient answers, projecting state. 
* **Domain Doc:** `docs/arch_core_engine.md`
* **Key Files:** `form_logic.py`, `runtime_state.py`, `ruleset.py`, `condition_registry.py`, `engine_adapters.py`

### 3.2 Clinical Safety & Projection
* **Scope:** Evaluating explicit patient answers against safety rules, blocking submissions.
* **Domain Doc:** `docs/arch_safety.md`
* **Key Files:** `safety_engine.py`, `projection.py`, `explicit_answers.py`

### 3.3 Encoder & ML Boundary
* **Scope:** Prompting encoders, mapping ML signals to answers, enforcing provenance.
* **Domain Doc:** `docs/arch_encoder.md`
* **Key Files:** `encoder_mapping.py`, `encoder_stub.py`, `encoder_contracts.py`

### 3.4 Practice Availability & Scheduling
* **Scope:** Weekly opening hours, per-date exceptions, manual overrides, fail-open logic.
* **Domain Doc:** `docs/arch_availability.md`
* **Key Files:** `availability_service.py`, `availability_repository.py`, `availability_models.py`

### 3.5 Submission, Serialization & Delivery
* **Scope:** Finalizing forms, auditing, persisting submission records, PDF generation, attachment storage, sending emails.
* **Domain Doc:** `docs/arch_submission.md`
* **Key Files:** `serialisation.py`, `serialisation_contracts.py`, `submission_repository.py`, `attachment_repository.py`, `delivery_service.py`, `pdf_formatter.py`

### 3.6 Frontend (Patient UI & Search)
* **Scope:** Stateless React rendering, condition search, combobox, fetching APIs.
* **Domain Doc:** `docs/arch_frontend.md`
* **Key Files:** `App.tsx`, `api.ts`, `types.ts`, `search.ts`, `ConditionCombobox.tsx`

### 3.7 Admin Portal & Configuration
* **Scope:** Admin authentication, editing signposting, configuring availability, managing practice settings, and the admin audit trail (recording all mutating admin actions and auth events).
* **Domain Doc:** `docs/arch_admin.md`
* **Key Files:** `admin_router.py`, `admin_context.py`, `practice_repository.py`, `audit_repository.py`, `http_utils.py`, `frontend/admin-ui/src/*`

### 3.8 HTTP Orchestration & App Entry
* **Scope:** FastAPI application, startup fail-fast validation, routing, error translation, rate limiting middleware.
* **Domain Doc:** Domain Doc: docs/arch_http_boundary.md
* **Key Files:** `main.py`, `request_validation.py`, `public_router.py`, `admin_router.py`, `form_router.py`, `dependencies.py`, `rate_limit.py`

### 3.9 API Boundary & Presentation
* **Scope:** Composing pre-session presentation data.
* **Domain Doc:** docs/arch_presentation.md
* **Key Files:** presentation_service.py

### 3.10 Clinical Ruleset Schema
* **Scope:** Layout and constraints for the clinical ruleset schemas
* **Domain Doc:** Domain Doc: docs/arch_ruleset_schema.md
* **Key Files:** Found in /data/ directory

### 3.11 Infrastructure, Database & Deployment
* **Scope:** Railway deployment configurations, the Dockerfile multi-stage build (Vite + Python), static file serving logic, Alembic database migrations, required environment variables, and Postgres/JSONB data quirks.
* **Domain Doc:** `docs/arch_infrastructure.md`
* **Key Files:** `Dockerfile`, `app/core/db.py` (Alembic initialization), `alembic/env.py`, `main.py` (for static serving mounts).

### 3.12 Testing Strategy
* **Scope:** Test categories (unit vs integration), two-database rule, migration obligations, Makefile targets.
* **Domain Doc:** `docs/arch_testing.md`
* **Key Files:** `tests/test_form_routes.py`, `tests/test_admin_router.py`, `Makefile`

### 3.13 Security & Compliance
* **Scope:** Access control, MFA, fail-fast configuration boundaries, data retention, file upload security (CDR), input sanitization, rate limiting, and dependency patching. Maps technical controls to Cyber Essentials Plus audit requirements.
* **Domain Doc:** `docs/arch_security.md`
* **Key Files:** `dependencies.py`, `admin_router.py`, `auth_repository.py`, `auth_service.py`, `deletion_job.py`, `request_validation.py`, `image_sanitizer.py`, `form_router.py`, `rate_limit.py`

# FILE_STRUCTURE.md
# LLM reference: actual local directory layout, structural purpose, and import mapping
# Last updated: 2026-04-23

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
  - `create_admin_user.py` — Inserts an admin user before first boot. Accepts `--create-practice` flag for CI use.
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
- `admin_delivery_service.py` — Admin MFA and invitation delivery. Implements `send_mfa_code` and `send_admin_invitation`. *Imports: stdlib only.*
- `delivery_constants.py` — Retry thresholds. *Imports: standalone; no application modules.*
- `pdf_constants.py` — PDF retry thresholds. *Imports: standalone; no application modules.*
- `delivery_worker.py` — Delivery worker loop. *Imports: delivery_repository, attachment_repository, delivery_service, delivery_constants, sentry_sdk only.*
- `pdf_worker.py` — PDF generation worker loop. *Imports: pdf_repository, photo_repository, submission_repository, attachment_repository, delivery_repository, pdf_formatter, pdf_constants, sentry_sdk only.*

**`app/services/admin/`** (admin portal concerns - mirrors app/routers/admin/ subfolder)
- `auth_service.py` — MFA auth business logic. *Imports: bcrypt, secrets, time, datetime, errors. DB/delivery via interfaces only.*
- `user_service.py` — Admin user management business logic (add, remove, resend invitation). *Imports: errors, auth_service.validate_admin_domain, email_utils. Receives repositories and conn as arguments — no direct DB access.*
- `availability_orchestration.py` — Wires repository and service.
- `availability_service.py` — Availability business logic.

**`app/services/` (flat)**
- `presentation_service.py` — Patient-facing presentation assembler. *Imports: condition_registry, practice_repository.*

### 2.3 `app/repositories/`
Database access for persistent records. No business logic.

- `attachment_repository.py` — Owns `submission_attachments`. *Imports: db only.*
- `audit_repository.py` — Owns `admin_audit_log`. *Imports: db, psycopg2, base64, json, re, datetime only.*
- `auth_repository.py` — Owns `admin_users`, `admin_auth_codes`, `admin_sessions`. Includes user management methods: `insert_user` (normalises email to lowercase, accepts conn), `get_users_by_practice` (accepts conn for lock-consistent reads), `get_user_by_id`, `delete_user` (accepts conn), `create_session` (sets `last_login = NOW()` atomically). *Imports: db, psycopg2, uuid, datetime only.*
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
- `errors.py` — Shared API, rate limit, and condition-not-found errors. `APIError` carries `status_code: int = 422`. User management adds: `USER_ALREADY_EXISTS` (409), `ACTION_NOT_PERMITTED` (403, accepts optional message), `USER_NOT_FOUND` (404).
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
- `admin_auth_router.py` — MFA request, verify, logout. Unauthenticated by design.
- `admin_practice_router.py` — Conditions list, practice settings, signposting, doctor list.
- `admin_availability_router.py` — Weekly config, manual overrides, per-date exceptions.
- `admin_audit_router.py` — Audit log read endpoint.
- `admin_user_router.py` — List, add, delete, and resend-invitation for admin users. Rate-limits POST /users and POST /users/{id}/resend-invitation at 10/minute.

---

## 3. Alembic migrations (`alembic/`)
Schema migration scripts. See code files directly for exact table definitions.

- `alembic/env.py` — Alembic environment configuration.
- `alembic/versions/0001_initial_schema.py` — Creates the complete baseline schema.
- `alembic/versions/0002_user_management_cascade.py` — Adds `ON DELETE CASCADE` to `admin_sessions.user_id` FK; adds `admin_users.last_login` (nullable TIMESTAMPTZ).
- `alembic/versions/0003_webhook_tracking.py` — Adds `provider_message_id` (VARCHAR 255, indexed) and `provider_events` (JSONB) to `delivery_jobs`; extends status check constraint to include `provider_accepted` and `delivered`; creates `webhook_tokens` replay protection table.

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
- `App.tsx` — Admin root component and routing.
- `api.ts` — Admin API clients (cookie-auth based). Includes user management functions: `fetchUsers`, `addUser`, `removeUser`, `resendInvitation`.
- `main.tsx` — React entry point.
- `types.ts` — Admin-specific contracts. Includes `AdminUser` and `AddUserResponse` interfaces.
- `screens/` — Admin views (`LoginView`, `EditorView`, `SignpostingEditor`, `AvailabilityEditor`, `PracticeSettingsTab`, `AuditLogTab`, `UsersTab`) and corresponding test files e.g. LoginView.test.tsx

---

## 5. Tests (`tests/`)

**Shared fixtures**
- `conftest.py` — Autouse pytest fixture that resets the SlowAPI in-memory rate limit storage before and after every test. Prevents counter state leaking across test boundaries.
- `helpers/admin_test_helpers.py` — Shared helpers for the admin sub-router tests. Provides `make_test_app`, `dummy_conn`, and stubs: `StubAuthRepo`, `StubPracticeRepo` (includes `lock_practice`), `StubAvailabilityRepo`, `StubAuditRepo`, `StubAdminDeliveryService` (tracks `mfa_calls` and `invitation_calls` separately), `StubRegistry`.

**Unit tests (Mocked/In-memory)**
- `test_delivery_service.py`, `test_delivery_worker.py`, `test_pdf_worker.py`, `test_pdf_generation.py`, `test_image_sanitizer.py`, `test_practice_endpoint.py`, `test_request_validation.py`, `test_upload_constants.py`, `test_sanitise_signposting.py`.

**Admin Sub-Router unit tests (placed in tests/routers/ subfolder)**
- `test_admin_auth_router.py`, `test_admin_availability_router.py`, `test_admin_practice_router.py`, `test_admin_audit_router.py`, `test_admin_user_router.py`

**Frontend component tests (placed in frontend/admin-ui/src/screens/)**
- `LoginView_test.tsx`, `EditorView_test.tsx`, `SignpostingEditor_test.tsx` (if present), `AvailabilityEditor_test.tsx`, `PracticeSettingsTab_test.tsx`, `AuditLogTab_test.tsx`, `UsersTab_test.tsx`

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

# Admin Portal & Configuration

**LLM INSTRUCTIONS:** This document covers design decisions and strict boundaries for the admin domain. Read the actual source files for function signatures, field names, and endpoint details.

---

## Scope

Admin authentication, editing per-condition signposting, configuring availability (schedule, overrides, per-date exceptions), managing practice email and doctor list, managing admin users, and the admin-portal frontend.

**Key files:** `app/routers/admin_router.py` (orchestrator), `app/routers/admin/admin_auth_router.py`, `app/routers/admin/admin_practice_router.py`, `app/routers/admin/admin_availability_router.py`, `app/routers/admin/admin_audit_router.py`, `app/routers/admin/admin_user_router.py`, `admin_context.py`, `app/services/admin/auth_service.py`, `app/services/admin/user_service.py`, `app/repositories/auth_repository.py`, `app/repositories/audit_repository.py`, `app/repositories/practice_repository.py`, `app/services/delivery/admin_delivery_service.py`, `availability_repository.py`, `availability_service.py`, `app/utils/http_utils.py`, `app/utils/email_utils.py`, `frontend/admin-ui/src/*`

---

## Design Decisions & Invariants

### Router Structure

The admin domain uses a thin orchestrator (`admin_router.py`) that registers five sub-routers from the `app/routers/admin/` package. Each sub-router owns a single domain boundary and mirrors its corresponding repository or service:

- `admin_auth_router.py` — MFA request, verify, logout (all unauthenticated)
- `admin_practice_router.py` — conditions list, practice settings, signposting, doctor list
- `admin_availability_router.py` — weekly config, manual overrides, per-date exceptions
- `admin_audit_router.py` — audit log read endpoint
- `admin_user_router.py` — list, add, delete, and resend-invitation for admin users

The `require_admin` dependency is applied within each sub-router's route definitions, not in the orchestrator. Auth endpoints are deliberately excluded.

The domain boundary invariant applies to all sub-routers: **no sub-router may import clinical engine modules, `presentation_service`, `serialisation`, `projection`, or `runtime_state`.**

---

### Authentication (`admin_context.py`, `auth_service.py`, `auth_repository.py`)

Authentication is exclusively email-based MFA using time-limited one-time codes and HttpOnly session cookies. There is no bearer-token fallback — the MFA email flow is fast enough for local development.

**MFA flow:**
1. `POST /admin/auth/request-code` — validates email domain, looks up the user, checks the 60-second rate-limit cooldown, generates a 6-digit cryptographic code, hashes it with bcrypt, upserts it to `admin_auth_codes`, and sends it via `AdminDeliveryService`. If the email is not registered, returns 200 silently to prevent user enumeration. Email is normalised to lowercase before the domain check.
2. `POST /admin/auth/verify` — runs the verification pipeline: user lookup, code record lookup, lockout check (3 attempts), expiry check (10 minutes), bcrypt comparison. On success: deletes the code, creates a session, sets an HttpOnly session cookie (`session_id`), and updates `admin_users.last_login` to `NOW()` atomically within the same transaction. All failure paths raise `INVALID_AUTH_CODE` (HTTP 422) regardless of which gate failed — a single generic error deliberately conceals which check failed.
3. `POST /admin/auth/logout` — deletes the session if a cookie is present, clears the cookie with `Max-Age=0`. No auth required — logout must succeed even for expired sessions.

**Session behaviour:**
- Session TTL is 24 hours (`SESSION_TTL_MINUTES = 60 * 24` in `admin_context.py`).
- Single-session enforcement: `AuthRepository.create_session` deletes all existing sessions for the user before inserting the new one, in a single transaction. This means a new login invalidates any existing session from another browser.
- `require_admin` reads the session cookie, calls `auth_repo.get_session_context(session_id)`, and raises HTTP 401 if the cookie is absent, not found, or expired. The expiry check is done in SQL (`expires_at > NOW()`) to avoid clock-skew.

**`admin_context.py` constraints:**
- `require_admin` is the **sole authentication boundary** for all admin endpoints. Every admin endpoint that requires auth declares `Depends(require_admin)`. The three auth endpoints (`request-code`, `verify`, `logout`) are deliberately unauthenticated.
- **This module must never import any project module other than `app.core.db`.** Only stdlib, FastAPI, and psycopg2. The `AuthProvider` Protocol in this module documents the subset of `AuthRepository` used here without importing it directly.

**`AdminContext` fields:** `practice_id`, `user_id`, `role`, `actor_email`, and `session_id` are all populated by `require_admin` from the session record. `user_id` is the UUID string of the `admin_users` row and is used for identity checks (e.g. self-deletion guards in `user_service`). All fields are always present — there is no fallback path that leaves them as `None`.

**Timing attack mitigation:**
`verify_mfa_code` in `auth_service.py` uses `_fixed_delay()` to ensure every verification attempt takes at least 300ms regardless of outcome. This prevents an attacker from learning which gate failed from response time. Uses `time.sleep` (not `asyncio.sleep`) because all repository calls are synchronous psycopg2. Revisit with `run_in_executor` if concurrent load ever becomes a concern.

**Domain validation:**
`ALLOWED_ADMIN_DOMAINS` is a comma-separated list of permitted email domains (e.g. `nhs.net,gov.uk`). Validation uses exact domain match — `endswith` is not used. Email must have exactly one `@`. Set at startup and stored in `app.state.allowed_admin_domains`. The same domain check applies when adding a new admin user via `POST /admin/users`.

**Email normalisation:**
All email addresses are normalised to lowercase at two points: in `auth_service.request_mfa_code` (before domain check and user lookup) and in `user_service.add_user` / `auth_repository.insert_user` (before storage). This belt-and-braces approach ensures stored emails and lookup emails always match regardless of call site.

**`last_login` field:**
`admin_users.last_login` is a nullable `TIMESTAMPTZ` column added in migration `0002`. It is `NULL` until the user first completes MFA verification — the frontend displays `NULL` as "Pending". It is set to `NOW()` atomically inside `AuthRepository.create_session` alongside the session insert.

**Session expiry mid-session:**
If a session expires while an admin is mid-edit, the next mutating API request returns 401. The frontend detects `AuthError` and redirects to `LoginView`. Any unsaved data is lost. This is acceptable given the 24-hour TTL and infrequent use pattern. No re-auth modal is provided — complexity is not justified.

**401 response contract (HTTP-first):**
HTTP `401 Unauthorized` is the primary contract for session expiry. The JSON body is secondary. This separation exists because `admin_context.py` cannot import project modules, so no Python constant can be shared across that boundary. The design is:
- `admin_context.py` raises `HTTPException(status_code=401, detail="...")` with a plain human-readable detail string.
- `main.py` registers an `HTTPException` handler that reshapes any 401 into the standard envelope: `{"error": {"code": "UNAUTHORIZED", "message": "..."}}`. This is the single place the secondary contract is enforced.
- `api.ts` throws `AuthError` on `res.status === 401`. Callers catch `AuthError` to trigger a login redirect. The JSON body is not inspected for 401 responses.
- No `SESSION_EXPIRED` constant exists in `errors.py` — the HTTP status code makes it unnecessary.

---

### Signposting (`admin_practice_router.py`, `practice_repository.py`)

- The admin `GET /admin/conditions` endpoint is a **raw administrative view** deliberately separate from the patient-facing `GET /conditions`. A change to one cannot accidentally affect the other.
- `GET /admin/conditions/{id}/signposting` returns `null` (not 404) when no signposting is configured. Absence of signposting is a valid configured state, not an error.
- `PUT` with empty/whitespace content is treated as "clear" — the repository deletes the row. `DELETE` also deletes the row. Both are semantically distinct at the database level (preserves audit distinctions) but both return `null` to current consumers via the normalisation rule.
- **Validation responsibility split:** The router validates HTTP input (types, whitespace, empty strings, condition ID existence). The repository acts as a backstop only. The condition registry is authoritative for valid condition IDs; the repository has no knowledge of them.
- `condition_id` is validated against the registry before any database operation. The registry is immutable after startup — new condition JSON files require a server restart to be visible in admin endpoints. This is intentional.
- HTML sanitisation of signposting content is performed by `practice_repository.py` via `nh3`. The router does not sanitise; it delegates entirely.
- `practice_repository.py` must never: access clinical data (rulesets, RuntimeState, answers), perform composition logic (belongs in `presentation_service`), or handle authentication.

---

### Availability (`admin_availability_router.py`, `availability_service.py`, `availability_repository.py`)

- `GET /admin/availability` returns the raw config. It does **not** call `evaluate_availability` — that is the patient-facing logic. Admin reads and writes raw config only.
- Setting `is_active = false` auto-clears any existing override. This is handled in the router before persisting.
- Availability and exception validation (equal times, override expiry window, exception type constraints) is delegated to the service layer, not the router.
- Override expiry must be timezone-aware. Timezone-naive `expires_at` is rejected with HTTP 400.

---

### Audit Trail (`admin_audit_router.py`, `audit_repository.py`, `http_utils.py`)

Every mutating admin action and all authentication events are recorded in the `admin_audit_log` table (created by migration 0001). The audit log is append-only and has no foreign keys — it remains readable even if a user or practice record is later deleted.

**What is recorded:**
- Auth events: `auth.code_requested`, `auth.login.succeeded`, `auth.login.failed`, `auth.logout`
- Mutating admin endpoints: practice email, signposting (per condition), doctor list, availability config, override, and per-date exceptions
- User management events: `auth.user_added`, `auth.user_deleted`, `auth.invitation_resent`

Each event records: `practice_id`, `actor_email`, `action`, `resource` (optional), `detail` (JSONB, action-specific shape), `ip_address`, `session_id`, `occurred_at`. The per-action `detail` shapes are documented in `audit_repository.py`.

**Transaction pattern for mutating endpoints:**
Each mutating endpoint reads the "before" state, then wraps both the repository mutation and the `audit_repo.log_event` call in a single shared `get_conn` transaction. If either operation fails, both roll back. The before state is read outside the transaction (clean read, no lock held). This pattern applies uniformly across all sub-routers.

For user management specifically, the practice row lock (`lock_practice`) is also acquired inside the same transaction. See the User Management section below.

**Auth events** (which have no paired mutation) use standalone inserts — `log_event` opens and commits its own connection when `conn=None`. `POST /admin/users/{id}/resend-invitation` also uses a standalone audit insert because it performs no user record mutations.

**IP address extraction** is centralised in `app/utils/http_utils.py` (`extract_ip`). It reads `X-Forwarded-For` first (taking the first value, the original client), then `X-Real-IP`, then `request.client.host`. This logic lives in one place only — not repeated at each call site.

**Read endpoint:** `GET /admin/audit-log` accepts query parameters `cursor`, `from_date`, `to_date`, `actor`, `action` (prefix match), `limit` (default 50, max 200). Pagination uses an opaque base64 cursor encoding `last_id` and `last_occurred_at`. The cursor and filters are independent — discarding the cursor and re-querying when a filter changes is correct behaviour.

**`AuditRepository` design decisions:**
- `list_events` fetches `limit + 1` rows to detect whether a next page exists, avoiding a separate `COUNT(*)` query.
- The `action_prefix` parameter is validated against `^[a-z0-9_.]+$` before building the `LIKE` clause — this prevents wildcard injection.
- Date boundaries are converted to midnight-start and end-of-day datetimes in Python before being passed to the query, making the boundary logic explicit and testable.
- Cursor decoding raises `ValueError` on malformed input; the endpoint converts this to HTTP 400.

---

### User Management (`admin_user_router.py`, `user_service.py`, `auth_repository.py`, `practice_repository.py`)

Admin users are managed per-practice. Each practice is an isolated tenant — no operation can affect users belonging to another practice.

**Endpoints:**
- `GET /admin/users` — plain read, no lock. Returns all users for the practice ordered by `created_at` ascending. Each row includes `is_current_user: bool` set by comparing `user["id"] == admin_context.user_id`.
- `POST /admin/users` — add a new admin user. Rate-limited to 10/minute.
- `DELETE /admin/users/{id}` — delete an admin user.
- `POST /admin/users/{id}/resend-invitation` — resend the invitation email. Rate-limited to 10/minute.

**Service layer (`user_service.py`):**
Business logic lives in `user_service`, not the router. The router opens the transaction and calls the service; the service validates, locks, and writes; the router appends the audit log write inside the same transaction.

`add_user` steps: normalise email → validate format (via `email_utils.is_valid_email_format`) → validate domain (via `auth_service.validate_admin_domain`) → acquire practice lock → insert user → catch `UniqueViolation` and raise `USER_ALREADY_EXISTS`.

`remove_user` steps: reject self-deletion → acquire practice lock → read all users for practice **inside the same transaction** (the read must be consistent with the lock to prevent two concurrent deletes both passing the minimum-user check) → verify target exists → reject if only one user remains → delete user. Postgres cascades the delete to `admin_sessions` via the `ON DELETE CASCADE` FK added in migration `0002`.

`resend_invitation`: look up user by id and practice, return email. No writes, no conn parameter.

**Concurrency and locking:**
`practice_repository.lock_practice` executes `SELECT ... FOR UPDATE` on the practice row. `conn` is a required parameter with no default — acquiring the lock and immediately releasing it on a separate connection would make it useless. The lock serialises concurrent add/remove operations for the same practice. The `get_users_by_practice` read that follows also receives the same `conn` so it runs inside the lock.

**Transaction boundary:**
`POST /admin/users` and `DELETE /admin/users/{id}` both open a `get_conn` transaction in the router. Inside that transaction: practice lock + user write (in `user_service`) + audit log write (in the router). Email delivery (`send_admin_invitation`) is deliberately outside the transaction — a delivery failure does not roll back the user write. The response includes `email_sent: false` so the caller is informed and can retry via resend-invitation.

**Error codes and HTTP status mapping:**
`APIError` carries an optional `status_code` field (default 422). The `APIError` handler in `main.py` uses `exc.status_code`. User management introduces three new error factories:
- `USER_ALREADY_EXISTS` → HTTP 409
- `ACTION_NOT_PERMITTED` → HTTP 403 (accepts an optional message parameter for the three distinct call sites)
- `USER_NOT_FOUND` → HTTP 404

**Invitation email:**
`AdminDeliveryService.send_admin_invitation` sends a plain-text email directing the new user to the admin portal URL (read from `ADMIN_PORTAL_URL` env var at call time, with a sensible fallback). No activation links are used — the existing MFA flow is the login mechanism. There is no `admin_auth_codes` FK to `admin_users.email`, preserving the anti-enumeration design of `request_mfa_code`.

---

### Admin Frontend (`frontend/admin-ui/src/`)

The admin UI is a Vite + React app (TypeScript). It is **not** the no-build CDN/Babel frontend — see `frontend/admin-ui/index.html` for the entry point.

**Component structure:**
- `App.tsx` — root; probes session on mount by calling `GET /admin/conditions`; shows `LoginView` on 401, `EditorView` on success. No token state. Owns `conditions` state and `handleAuthError` callback.
- `LoginView.tsx` — two-step MFA login: step 1 email input calls `POST /admin/auth/request-code`; step 2 code input calls `POST /admin/auth/verify`. On success calls `onSuccess()` so App re-fetches conditions and transitions to `EditorView`.
- `EditorView.tsx` — five-tab container (Signposting, Availability, Practice settings, Audit log, Manage users); owns unsaved-change tracking via refs; passes `onAuthError` down to all children. `AvailabilityEditor` is always mounted (display:none when inactive) to preserve state. All other tabs are conditionally rendered and perform a fresh fetch on mount. `UsersTab` has no unsaved state and requires no ref.
- `SignpostingEditor.tsx` — rich text editor for one condition; calls `onAuthError` on `AuthError`.
- `AvailabilityEditor.tsx` — schedule, override, and exceptions card; calls `onAuthError` on `AuthError`.
- `PracticeSettingsTab.tsx` — practice email and doctor list; calls `onAuthError` on `AuthError`.
- `AuditLogTab.tsx` — read-only audit event viewer. Filter inputs (date range, actor, action prefix) with 400ms debounce on text fields. Paginated table with "Load more" cursor-based pagination. Each row has a collapsible detail cell. Values rendered as plain text — HTML is never rendered.
- `UsersTab.tsx` — admin user management. Lists all users with last login status, add-user form, per-row remove and resend-invite actions. "Resend Invite" is only rendered when `last_login` is null. Remove is disabled for `is_current_user`. Inline messages cover success, warning (email delivery failure), and error states. Re-fetches the user list after any successful add or remove.
- `TokenView.tsx` — **deleted**. Replaced by `LoginView.tsx`.

**Key boundaries:**
- No token is held in React state or any browser storage. Authentication is entirely cookie-based — the browser attaches the `session_id` HttpOnly cookie automatically.
- `api.ts` adds `X-Requested-With: XMLHttpRequest` and `credentials: "same-origin"` to every request. This satisfies the CSRF requirement given a strict same-origin CORS policy.
- `AuthError` is thrown by `apiFetch` on any 401 response. Child components catch it and call `onAuthError()`, which transitions App back to `LoginView`. Unsaved data is lost on session expiry — no modal, no retry queue.
- All fetch calls are wrapped in try/catch; network errors produce inline messages, not browser error dialogs.
- The frontend makes requests to `/admin/*` endpoints only.
- The frontend contains no clinical logic or safety rule evaluation.

**Unsaved change tracking:** `SignpostingEditor` and `AvailabilityEditor` report unsaved state to `EditorView` via `onUnsavedChange` callbacks. `EditorView` stores these in refs so `confirm()` dialogs can read them synchronously. `UsersTab` has no unsaved state — no ref is needed and `handleTabChange` does not guard transitions to or from the users tab.

**Types and API functions:** See `frontend/admin-ui/src/types.ts` and `frontend/admin-ui/src/api.ts` directly.

---

## What Admin Must Never Do

- `admin_context.py`: import any project module other than `app.core.db`
- Any admin sub-router: import clinical engine modules, `presentation_service`, `serialisation`, `projection`, or `runtime_state`
- `auth_service.py`: access the database directly — all DB access goes through `AuthRepository`
- `auth_repository.py`: contain business logic (cooldown checks, code generation, hashing)
- `user_service.py`: touch the database directly — all DB access goes through the repository arguments passed in; handle email delivery (belongs in the router)
- `admin_delivery_service.py`: check cooldowns or access any repository — it is a pure transport layer
- `practice_repository.py`: access clinical data, perform composition logic, or handle authentication
- `audit_repository.py`: contain business logic or validation; import from service modules or routers; be called from the patient-facing request path
- `http_utils.py`: import any application module — stdlib only
- `email_utils.py`: import any application module — stdlib only; perform domain allowlist checks (that belongs in `auth_service.py`)
- Admin frontend: store session data in `localStorage` or `sessionStorage`; contain clinical logic; call non-`/admin/*` endpoints; bypass `onAuthError` on 401; render HTML content from `detail` fields

# Security & Compliance Architecture

**LLM INSTRUCTIONS:** This document defines the security boundaries, access controls, and compliance mechanisms of the Econsult system. It maps technical implementations to standard security audit requirements (such as Cyber Essentials Plus). Read this document to understand data lifecycle, authentication, and boundary defenses.

---

## Scope

User access control, multi-factor authentication, rate limiting, input sanitization, malware mitigation, data retention, and secure configuration enforcement.

**Key files:** `dependencies.py`, `admin_router.py`, `auth_repository.py`, `auth_service.py`, `deletion_job.py`, `request_validation.py`, `image_sanitizer.py`, `form_router.py`, `rate_limit.py`, `webhook_router.py`

---

## 1. User Access Control & Authentication (Admin Portal)

The patient-facing form is intentionally unauthenticated to ensure accessibility. The Admin Portal enforces strict access controls.

- **MFA by Default.** The admin portal is protected by Multi-Factor Authentication. Staff must request a login code and authenticate using a time-limited secure code sent to their registered email address.
- **Isolated MFA Delivery Pipeline.** Admin MFA code delivery uses a completely separate service instance from the clinical delivery path, ensuring operational isolation between authentication traffic and patient data. In production this is MailgunHttpAdminDeliveryService; the SMTP equivalent AdminDeliveryService is available for deployments where SMTP is not blocked.
- **Domain Allowlisting.** The system enforces an `ALLOWED_ADMIN_DOMAINS` environment variable. The domain of the authenticating admin email is validated against this list on every login attempt. The application also validates this configuration at startup and aborts if it is absent or malformed.
- **No Default Passwords.** The system does not use passwords. The legacy `ADMIN_TOKEN` has been replaced by MFA in production.
- **Single-Tenant Isolation.** The application enforces a strict single-tenant architecture. Startup validation explicitly checks that exactly one practice exists in the database, preventing cross-contamination of patient data if the database is misconfigured.
- **Manual Admin User Provisioning.** The first admin user must be inserted before the application starts using `scripts/create_admin_user.py`. The application will refuse to start if no admin users exist for the practice. This replaces the previous `INITIAL_ADMIN_EMAIL` seeding mechanism, which has been removed. Additional users can be added via the admin UI once the system is running.

---

## 2. Secure Configuration & Fail-Fast Boundaries

The system refuses to run in an insecure or partially configured state.

- **Startup Validation.** The application entry point (`main.py`) validates the presence of all required security, database, and email environment variables before accepting any HTTP requests. Missing critical variables cause the process to abort rather than silently degrade.
- **Webhook Signing Key Enforcement.** When `MAILGUN_API_KEY` is set (i.e. Mailgun is the delivery provider), `MAILGUN_SIGNING_KEY` is also required at startup. Absent this key the webhook endpoint cannot verify HMAC signatures, which would allow any party to forge delivery events. The application aborts startup if `MAILGUN_API_KEY` is present but `MAILGUN_SIGNING_KEY` is not.
- **The Two-Database Rule.** Testing is strictly fenced from production. A hardcoded guardrail at the top of every integration test module prevents tests from running unless a dedicated `TEST_DATABASE_URL` environment variable is set. This structurally prevents accidental test data writes or deletions against the production patient database.
- **Network Boundaries.** The application is a single-container deployment hosted on Railway. The database is isolated within the cloud provider's internal network and is not directly exposed to the public internet.
- **Third-Party Observability (Sentry) — PII Lockdown.** Sentry is an external service. Its initialisation enforces strict data minimisation controls to prevent clinical data from leaving the system boundary:
  - **Backend (`telemetry.py`):** `send_default_pii=False`, `request_bodies="never"`, `with_locals=False`. The `request_bodies="never"` setting is the critical control — it drops multipart payloads containing raw clinical JSON and patient photos at the ASGI layer before Sentry can capture them. Worker processes additionally set `traces_sample_rate=0.0` to prevent infinite worker loops from being instrumented as transactions.
  - **Frontend (`main.tsx`):** Performance tracing is disabled (`tracesSampleRate: 0`). The `BrowserTracing`, `Breadcrumbs`, `GlobalHandlers`, `LinkedErrors`, `HttpContext`, and `Dedupe` integrations are explicitly removed from the SDK defaults, preventing DOM interaction tracking, SPA navigation recording, and URL parameter capture. A `beforeBreadcrumb` hook drops the request body size field for POST requests to `/form/update` and `/form/finish`. The `ErrorBoundary`'s `beforeCapture` hook strips React component props and state from error events, preventing patient answers held in transient UI state from being serialised and transmitted.
  - **Test isolation.** Sentry initialisation is bypassed entirely in all test environments (pytest presence, `TEST_DATABASE_URL` set, `DEV_MODE=1` on the backend; `import.meta.env.DEV` or `MODE === 'test'` on the frontend). This prevents test suite HTTP requests to Sentry's ingestion endpoints and eliminates the possibility of test data reaching Sentry's servers.
  - **Safety isolation invariant.** Triggered safety rules are successful, deterministic clinical operations. They are explicitly excluded from Sentry reporting. The backend `ignore_errors` list includes `APIError`, `ConditionNotFound`, `RateLimitError`, and `slowapi.errors.RateLimitExceeded` to suppress expected 4xx responses. Both rate limit exception types must be present: `RateLimitError` covers the service-layer per-email cooldown; `RateLimitExceeded` covers requests rejected by the SlowAPI IP-based limiter. The frontend `triggerFatalError` function must never be called from safety message handling paths.

---

## 3. Data Protection & Retention

Patient data is minimised, protected against concurrency flaws, and aggressively purged to reduce the impact of any potential breach.

- **Append-Only State & Concurrency Control.** In-flight `RuntimeState` is strictly append-only in the database. Each API request creates a new version row, protected by optimistic concurrency control (version consistency validation). This prevents race conditions, state overwrites, or session hijacking if multiple browser tabs are used.
- **Immutable Delivery Artifacts.** Once a patient clicks submit, the finalised PDF is rendered immutable. It is stored once and used as-is for all delivery retries, guaranteeing the clinical record cannot be altered post-submission.
- **Ephemeral Storage & Nightly Deletion.** Raw patient photos (`submission_photos`) and the finalised delivery artifact (`submission_attachments`) are retained only long enough to ensure delivery. A scheduled cron job (`deletion_job.py`) runs at midnight to permanently delete all photos and PDF attachments for submissions where `delivery_jobs.status = 'delivered'`. Maximum retention is strictly bounded to approximately 24 hours for the Mailgun webhook path. See `arch_submission.md` Known Limitations for the SMTP path and `provider_accepted` edge cases.
- **No Cross-Session Memory.** The clinical engine operates entirely on a session-backed basis. There is no conversational memory, no cross-session state, and no persistent per-user identity for patients.

---

## 4. Malware Mitigation & File Upload Security

Because the system accepts files and free text from the public, strict validation and sanitization occurs at multiple layers.

- **Independent Server-Side Enforcement.** The frontend checks file sizes, file counts, and MIME types as a usability guard only. The backend server enforces all limits independently as a strict security boundary, including a server-side count check that is the primary enforcement point (FastAPI does not enforce count limits on `list[UploadFile]`).

- **Image Content Disarm and Reconstruction (CDR).** Before any uploaded photo is written to the database, the server applies CDR via `app/utils/image_sanitizer.py`. Every image is fully decoded by Pillow and re-encoded from scratch as a JPEG. This provides the following guarantees:

  - **Full-decode validation.** The previous approach used `Image.open(...).verify()`, which checks the file header only. A file with a valid header but a corrupt or truncated body would pass that check but then fail during PDF generation, leaving the submission in a degraded state. CDR performs a full decode, catching corrupt bodies at the router before any database write occurs.
  - **Metadata stripping.** EXIF data, ICC profiles, and all other metadata are discarded. The output buffer is written entirely from the decoded pixel values.
  - **Format normalisation.** Output is always JPEG regardless of whether the input was JPEG or PNG. All bytes stored in `submission_photos` are sanitized JPEG.
  - **Structural polyglot defence.** A polyglot file embeds a second payload (such as executable code) in regions Pillow ignores — for example, bytes appended after the JPEG end-of-image marker. Because CDR re-encodes from the decoded pixel buffer rather than forwarding the original bytes, any such payload is discarded and never reaches the database or the PDF worker.

- **Post-Sanitization Size Re-Validation.** After CDR, the router re-validates each image against the per-file and combined size limits. This is necessary because re-encoding an already-compressed JPEG can marginally increase its size. The invariant that stored bytes are within declared limits is maintained.

- **Defensive Photo Count Check (PDF Worker).** The PDF worker validates the raw photo count fetched from the database against the declared `attachment_count` on the `pdf_jobs` row. A mismatch (for example, caused by a dropped connection mid-upload) causes the job to fail immediately rather than process a truncated payload.

- **Input Sanitization (XSS).** The XSS surface has two distinct paths, each handled differently:

  - **Signposting (admin-authored HTML).** This is the only path where content is rendered as HTML in the browser. Admin-provided signposting text is sanitized using `nh3` on the backend before storage, with a strict tag and attribute allowlist (`p`, `strong`, `em`, `a`, `ul`, `ol`, `li`, `br`; `href`, `rel`, `target` on `<a>` only; `http`/`https` URL schemes only). On the frontend, `DOMPurify.sanitize()` with `SIGNPOSTING_PURIFY_CONFIG` is applied again before rendering via `dangerouslySetInnerHTML`. The two allowlists are kept explicitly synchronised. `nh3` automatically injects `rel="noopener noreferrer"` on `<a>` tags; the `DOMPurify` config must preserve `rel` to avoid stripping this on render.
  - **Patient free text.** The patient free text field (`FreeTextScreen`) uses React's standard controlled `textarea` (value/onChange). React escapes all content as plain text — it never renders free text as HTML. There is no `dangerouslySetInnerHTML` involved in this path. No additional sanitization is applied or required, as the data is stored and rendered as plain text throughout (including in the PDF output).

- **PDF Output — Injection Risk.** The PDF formatter (`pdf_formatter.py`) uses `fpdf2`. Patient-supplied strings are passed directly to `cell()`, `multi_cell()`, and `body_text()` calls. This is safe: PDF is a binary format, not a markup language, and `fpdf2` does not use its optional HTML rendering mode anywhere in the codebase. There is no mechanism by which text content in a PDF cell can execute code. XSS sanitization is not applicable to this output path. The relevant threat model for PDFs (embedded JavaScript via interactive form fields or PDF actions) does not apply here as no such features are used.

- **Webhook Endpoint Security.** The Mailgun webhook endpoint (`POST /webhooks/mailgun`) is a public-facing endpoint. It is secured by three independent controls: timestamp staleness check (>15 minutes dropped), HMAC-SHA256 signature verification using `MAILGUN_SIGNING_KEY`, and token-based replay protection backed by the `webhook_tokens` database table. See `arch_submission.md` for the full webhook security model.

---

## 5. Rate Limiting

Brute-force and enumeration attacks are mitigated at the HTTP boundary using SlowAPI (`app/core/rate_limit.py`), wired into the application via `SlowAPIMiddleware` in `main.py`.

**Key file:** `rate_limit.py`

### Admin MFA endpoints — 5 requests/minute per IP

`POST /admin/auth/request-code` and `POST /admin/auth/verify` are both decorated with `@limiter.limit("5/minute")`. These are the only unauthenticated endpoints that interact with credentials, making them the primary brute-force surface.

The IP limit is one layer of a defence-in-depth stack. Two independent service-layer controls also apply:

- `auth_service.request_mfa_code` enforces a **60-second per-email cooldown** backed by the database (`last_requested_at`). This survives process restarts and fires before the slowapi counter is relevant for single-machine attacks.
- `auth_service.verify_mfa_code` enforces a **3-attempt per-email lockout** backed by the database (`attempts_count`). Exceeding this deletes the code and requires a fresh request cycle.

The IP limit adds protection against a distributed attack cycling through different email addresses faster than the per-email cooldowns can engage.

**Audit evasion accepted:** SlowAPI rejects excess requests before they reach the `audit_repo.log_event` call. This is intentional — the database audit log is for clinical admin staff monitoring business actions. Brute-force traffic is visible in stdout logs and Sentry for the technical team.

### Patient-facing endpoints — 30 requests/minute per IP

All endpoints in `public_router.py` and `form_router.py` are decorated with `@limiter.limit("30/minute")`. This provides baseline protection against automated scraping or submission flooding. The limit is intentionally generous to accommodate scenarios where multiple patients share a single NAT IP (care home, public library) without violating the Fail-Open Availability invariant.

### Webhook endpoint

The webhook endpoint (`POST /webhooks/mailgun`) is covered by the SlowAPI middleware. No dedicated rate limit decorator is applied — the middleware provides baseline protection and the HMAC security boundary is the primary control against illegitimate traffic.

### IP extraction

The limiter uses `extract_ip` from `app/core/http_utils.py` as its key function rather than SlowAPI's built-in `get_remote_address`. This is necessary because Railway sits behind a reverse proxy — `request.client.host` always resolves to the proxy IP. `extract_ip` correctly reads `X-Forwarded-For` and `X-Real-IP` headers to obtain the real client IP.

### Storage

In-memory storage (`limits.storage.MemoryStorage`) is used deliberately. The deployment is a single web worker. Redis would add operational overhead with no benefit at this scale. Counters reset on process restart, which is acceptable — a restart clears a brief window of protection, but the service-layer database-backed controls remain active throughout.

### Error envelope

When SlowAPI rejects a request it raises `slowapi.errors.RateLimitExceeded`. A custom handler in `main.py` catches this and returns the standard error envelope: `{"error": {"code": "RATE_LIMIT_EXCEEDED", "message": "Too many requests. Please try again later."}}` with HTTP 429. This is consistent with the existing `RateLimitError` handler so the frontend always receives the same shape regardless of which layer fired the limit.

---

## 6. Security Update Management

Vulnerability patching is automated and enforced via CI/CD pipelines.

- **Dependency Automation.** Dependabot is configured to automatically scan and propose updates for Docker base images, Python (`pip`) dependencies, Node/npm dependencies, and GitHub Actions on a weekly schedule.
- **Synchronised Security Libraries.** Critical security libraries (`nh3` and `DOMPurify`) are explicitly pinned. Version changes require deliberate synchronisation between the frontend and backend allowlists.

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
- Repositories and registries are initialised **once at startup** and stored in `app.state`. Routers access them exclusively via dependency provider functions in `app/core/dependencies.py` — never via direct `request.app.state` access inside handler bodies, and never via direct imports from `main.py`. This prevents circular imports and keeps handler signatures self-documenting.
- The `/admin` prefix and `"admin"` tag are applied when the admin router is registered in `main.py`, not inside `admin_router.py`. This keeps the router decoupled from its mount point.
- **All API routes must be registered before the static file mount block.** The catch-all static mount must come last or it will intercept API requests.

---

## Startup Validation (Fail-Fast)

Any failure in startup validation raises a `RuntimeError` and aborts. A misconfigured deployment must never silently degrade.

The application does not seed or create database records at startup. All required records (practice, admin users) must be inserted before the application starts. See `docs/deployment_checklist.md`.

**Startup sequence:**
1. `import os`, `import logging`, and `init_telemetry("http-api")` execute — Sentry is initialised before any other internal import so that module-load failures (e.g. a failed Alembic migration) are captured by Sentry's default `sys.excepthook`
2. `DATABASE_URL` checked at module load time — failure prevents the app object from being created
3. Alembic migrations run (`alembic_upgrade()`) — a failed migration aborts startup
4. `_validate_startup()` runs and stores `practice_id` in `app.state` — wrapped in `sentry_sdk.set_tag("phase", "startup")` / `"running"` so any `RuntimeError` raised here is tagged in Sentry
5. `availability_repo.init_availability()` seeds a default availability row if absent — must run after step 4 so the practice row exists

**Validation rules enforced by `_validate_startup()`:**
- `PRACTICE_ID` env var must be set.
- The practice record must exist in the database. If absent, startup aborts with instructions to run the deployment checklist.
- The practice must have a non-empty email address.
- The database must contain **exactly one practice**. Multiple practices is a clinically unsafe configuration (cross-contamination risk) and aborts startup.
- Unless `DEV_MODE=1`: either `MAILGUN_API_KEY` + `MAILGUN_DOMAIN` (Mailgun HTTP) or `SMTP_HOST` + `SMTP_USER` + `SMTP_PASSWORD` (SMTP) must be set, plus `EMAIL_FROM` in both cases. Validation is handled by `_validate_email_config()`.
- Unless `DEV_MODE=1`: `ALLOWED_ADMIN_DOMAINS` must be set.
- At least one admin user must exist for the practice. If none are found, startup aborts with instructions to run `scripts/create_admin_user.py`.

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
| `delivery_service` | DeliveryService | Clinical email delivery (Console, Mailgun HTTP, or SMTP) |
| `admin_delivery_service` | AdminDeliveryService | MFA code email delivery (Console, Mailgun HTTP, or SMTP) |
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
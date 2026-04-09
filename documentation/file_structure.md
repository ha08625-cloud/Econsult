# FILE_STRUCTURE.md
# LLM reference: actual local directory layout and import mapping
# Last updated: 2026-04-09

---

## 1. Top-level layout

The project root contains the following items:

- main.py — FastAPI entry point. HTTP layer only.
- worker_main.py — Delivery worker entry point. Validates env vars, instantiates DeliveryRepository, AttachmentRepository, and delivery service, calls run_worker. No HTTP server, no migrations.
- pdf_worker_main.py — PDF worker entry point. Validates env vars, instantiates repositories, looks up practice name from the database, calls run_worker. No HTTP server, no migrations.
- deletion_job.py — Nightly cron one-shot script. Deletes submission_photos and submission_attachments rows for fully delivered submissions. Invoked by Railway cron at midnight. No HTTP server, no migrations.
- seed_db.py — database seed script, safe to run multiple times.
- .env — local environment variables, not committed.
- Dockerfile — container build definition.
- build.sh — build script used by the container.
- railway.toml — Railway deployment config. Contains only `builder = "DOCKERFILE"`.
- requirements.txt — Python dependencies. Includes bcrypt for MFA code hashing.
- alembic.ini — Alembic configuration. Placeholder database URL; the real URL is injected at runtime from DATABASE_URL. No secrets; safe to commit.
- consultation_outcomes.json — canonical source of truth for consultation outcome values and labels. Read by consultation_outcomes.py at import time and imported directly by OutcomeScreen.tsx via resolveJsonModule. Value strings are immutable once deployed.
- upload_constants.json — canonical source of truth for photo upload limits. Read by upload_constants.py at import time.
- app/ — all Python application code.
- alembic/ — Alembic migration scripts.
- frontend/ — patient-facing React app.
- data/ — condition ruleset JSON files.

---

## 2. Python application code (app/)

The app/ directory is a Python package. It contains five sub-packages.

### 2.1 app/models/

Data structures only. No business logic, no IO, no imports from non-model modules.
Imported by service modules; never imports service modules.

Files:
- app/models/api_models.py — SafetyMessage and other HTTP-layer data shapes.
- app/models/encoder_contracts.py — EncoderSignalDefinition, EncoderOutput.
- app/models/explicit_answers.py — ExplicitAnswers (frozen, immutable projected answers for safety engine).
- app/models/runtime_state.py — RuntimeState, AnswerState, SafetyEvaluation.
- app/models/serialisation_contracts.py — PatientDetails, ClinicalOutput (with from_dict classmethod for DB round-trip reconstruction), AuditOutput.
- app/models/availability_models.py

### 2.2 app/services/

Business logic and orchestration. Divided into two sub-packages by concern, plus flat files.

#### app/services/engine/

Pure clinical logic. No IO, no database access, no delivery concerns. All modules are
deterministic and side-effect free except pipeline.py which wires them together.

Files:
- app/services/engine/form_logic.py — deterministic functional core; no IO.
- app/services/engine/ruleset.py — loads and validates condition ruleset JSON.
- app/services/engine/projection.py — projects RuntimeState to ExplicitAnswers.
- app/services/engine/safety_engine.py — evaluates safety rules; consumes ExplicitAnswers only.
- app/services/engine/serialisation.py — produces ClientStateView, ClinicalOutput, AuditOutput.
- app/services/engine/encoder_mapping.py — containment layer; applies encoder output to RuntimeState.
- app/services/engine/encoder_stub.py — placeholder encoder, expected to be replaced; returns plain dict.
- app/services/engine/pipeline.py — orchestration layer; wires all engine services together.

#### app/services/delivery/

IO-touching delivery concerns. Handles SMTP, PDF generation worker, retry scheduling,
and the nightly deletion cron.

Files:
- app/services/delivery/delivery_service.py — DeliveryService abstract base class; EmailDeliveryService (production SMTP with PDF attachment); ConsoleDeliveryService (dev only). Receives pre-rendered PDF bytes from caller; does not generate PDFs.
- app/services/delivery/admin_delivery_service.py — AdminDeliveryService (production SMTP for MFA codes); ConsoleAdminDeliveryService (dev only, logs code to stdout). Pure transport layer — no auth logic, no repository access, no cooldown checks. Uses the same SMTP environment variables as EmailDeliveryService but opens a separate SMTP connection. Instantiated at startup in main.py and stored in app.state.admin_delivery_service.
- app/services/delivery/delivery_constants.py — retry backoff schedule (RETRY_BACKOFF_MINUTES) and MAX_ATTEMPTS. No application-module imports. Single canonical source for the exhaustion threshold.
- app/services/delivery/pdf_constants.py — PDF job retry schedule (PDF_RETRY_BACKOFF_MINUTES) and MAX_PDF_ATTEMPTS. No application-module imports.
- app/services/delivery/delivery_worker.py — rewritten delivery worker loop. Calls delivery_repo.claim_next_pending directly (no delivery_orchestration dependency). Processes one job per iteration: fetches attachment, sends email, marks sent. EmailDeliveryError is caught per-job with backoff recorded. All other exceptions logged at CRITICAL. psycopg2.OperationalError propagates uncaught so Railway can restart. Imports from delivery_repository, attachment_repository, delivery_service, delivery_constants only.
- app/services/delivery/pdf_worker.py — PDF generation worker loop. Calls pdf_repo.claim_next_pending, validates photo count, generates PDF, saves attachment (UPSERT), creates delivery job (idempotent), marks pdf_job done. Operation ordering is an invariant: save_attachment -> create_job -> mark_done. Orphan detection runs once per loop iteration with CRITICAL log rate-limited to 60 seconds. Imports from pdf_repository, photo_repository, submission_repository, attachment_repository, delivery_repository, pdf_formatter, pdf_constants.

#### app/services/ (flat)

- app/services/auth_service.py — MFA auth business logic. Domain validation (validate_admin_domain), code generation (generate_code, hash_code, verify_code using bcrypt), request_mfa_code flow (domain check, user lookup, cooldown check, upsert, send), verify_mfa_code flow (full verification pipeline with fixed-delay timing attack mitigation via _fixed_delay). All DB access delegated to AuthRepository. Must never access the database directly.
- app/services/availability_orchestration.py — orchestration layer; wires AvailabilityRepository and availability_service together.
- app/services/availability_service.py
- app/services/presentation_service.py — assembles patient-facing presentation data.

### 2.3 app/repositories/

Database access for persistent records. No business logic.

Files:
- app/repositories/attachment_repository.py — PDF attachment storage. Owns the submission_attachments table. save_attachment is a UPSERT (ON CONFLICT DO UPDATE) — safe on PDF worker retry. get_attachment raises AttachmentNotFound if absent (always an error — ordering invariant guarantees presence under normal operation). delete_attachment is idempotent; called exclusively by deletion_job.py.
- app/repositories/auth_repository.py — admin MFA auth. Handles three tables: admin_users, admin_auth_codes, admin_sessions. Methods: get_user_by_email, count_users_for_practice, insert_user, upsert_auth_code (resets attempts_count on upsert — ON CONFLICT DO UPDATE), get_auth_code_record, increment_code_attempts (atomic UPDATE, no read-modify-write), delete_auth_code (idempotent), create_session (deletes ALL existing sessions for user_id in the same transaction — single-session enforcement), get_session_context (JOIN to admin_users, expiry checked in SQL via expires_at > NOW()), delete_session (idempotent). UUID columns cast to str on read via ::text. Must never contain business logic.
- app/repositories/availability_repository.py — weekly hours, overrides, and per-date exceptions.
- app/repositories/delivery_repository.py — owns the delivery_jobs table. create_job uses ON CONFLICT DO NOTHING (idempotent). claim_next_pending uses SELECT ... FOR UPDATE SKIP LOCKED. mark_sent, mark_failed (with attempt_count increment and permanent failure at MAX_ATTEMPTS).
- app/repositories/pdf_repository.py — owns the pdf_jobs table. create_job, claim_next_pending (SKIP LOCKED), mark_done, mark_failed, get, list_orphaned_submissions (LEFT JOIN against submission_records).
- app/repositories/photo_repository.py — owns the submission_photos table. save_photos inserts one row per photo with photo_index from enumeration. get_photos returns bytes ordered by photo_index. No delete method — deletion is exclusively deletion_job.py's responsibility.
- app/repositories/practice_repository.py — practice record CRUD including update_email.
- app/repositories/runtime_state_repository.py — session state read/write. Registered in app.state as runtime_repo.
- app/repositories/submission_repository.py — owns the submission_records table. Provides create_submission and get_submission only. create_submission no longer accepts delivery_email or attachment_count (those live on pdf_jobs). _SUBMISSION_COLUMNS does not include the delivery columns dropped by Migration 0013.

### 2.4 app/core/

Infrastructure concerns only. No clinical logic.

Files:
- app/core/admin_context.py — admin authentication context and FastAPI dependency. Implements session-cookie MFA auth (primary path) with DEV_MODE bearer-token fallback. Defines AdminContext class, AuthProvider Protocol (structural — avoids direct AuthRepository import), SESSION_COOKIE_NAME, SESSION_TTL_MINUTES, SESSION_COOKIE_MAX_AGE. Must never import any project module other than stdlib and FastAPI.
- app/core/condition_registry.py — loads and indexes condition rulesets at startup; immutable after init.
- app/core/consultation_outcomes.py — exposes CONSULTATION_OUTCOMES and VALID_OUTCOME_VALUES loaded from consultation_outcomes.json at import time.
- app/core/db.py — shared Postgres connection module. Provides get_conn() context manager and alembic_upgrade().
- app/core/dependencies.py — shared FastAPI dependency provider functions. Provides get_auth_repo (returns app.state.auth_repo) in addition to all pre-existing providers.
- app/core/errors.py — APIError, named error constants. Also defines: INVALID_AUTH_CODE (APIError -> 422, single generic error for all MFA verification failures), SESSION_EXPIRED_MESSAGE (string constant for HTTPException(401) raised in admin_context.py), RateLimitError (separate Exception subclass -> 429 via dedicated handler in main.py, cannot be APIError because that hardcodes 422), RATE_LIMIT_EXCEEDED (lambda returning RateLimitError).
- app/core/request_validation.py — validates incoming HTTP payloads.
- app/core/upload_constants.py — exposes named constants loaded from upload_constants.json.

### 2.5 app/utils/

Pure utility functions. No IO, no database access, no imports from routers or repositories.

Files:
- app/utils/pdf_formatter.py — generate_pdf() pure function. Takes ClinicalOutput, submission metadata, optional practice_name, and optional photo_bytes; returns raw PDF bytes via fpdf2.
- app/utils/image_sanitizer.py — sanitize_image(raw_bytes) -> bytes. Performs Content Disarm and Reconstruction (CDR) on a single uploaded image: full Pillow decode via convert("RGB"), re-encode as JPEG at quality 85. Strips all metadata including EXIF. Returns clean JPEG bytes. Raises ValueError on any decode failure. No IO, no database access, no logging. Called by form_router.py before any database write.

---

## 3. Alembic migrations (alembic/)

Schema migration scripts managed by Alembic. alembic/env.py reads DATABASE_URL
from the environment and runs migrations. alembic_upgrade() in app/core/db.py
calls `alembic upgrade head` at application startup.

Files:
- alembic/env.py — Alembic environment configuration. Reads DATABASE_URL; no ORM metadata.
- alembic/versions/ — migration scripts, ordered by revision chain.
- alembic/versions/0001_initial_schema.py — four existing tables (practices, runtime_state_versions, practice_signposting, submission_records).
- alembic/versions/0002_availability_table.py
- alembic/versions/0003_availability_override.py
- alembic/versions/0004_availability_exceptions.py
- alembic/versions/0005_submitted_at_explicit.py — removes DEFAULT NOW() from submission_records.submitted_at.
- alembic/versions/0006_attachment_storage.py — adds condition_label to submission_records; creates submission_attachments table.
- alembic/versions/0007_delivery_retry_columns.py — adds delivery retry columns to submission_records (superseded by 0013).
- alembic/versions/0008_attachment_count.py — adds attachment_count to submission_records (superseded by 0013).
- alembic/versions/0009_doctor_list.py
- alembic/versions/0010_pdf_jobs.py — creates pdf_jobs table with attachment_count and delivery_email columns.
- alembic/versions/0011_delivery_jobs.py — creates delivery_jobs table with UNIQUE constraint on submission_id.
- alembic/versions/0012_submission_photos.py — creates submission_photos table with composite PK (submission_id, photo_index).
- alembic/versions/0013_drop_delivery_columns.py — drops delivery_status, delivery_email, delivered_at, delivery_error, delivery_attempts, last_attempt_at, next_retry_after, attachment_count from submission_records. Point of no return for the pipeline migration.
- alembic/versions/0014_admin_auth_tables.py — creates admin_users (UUID PK gen_random_uuid(), email UNIQUE, practice_id FK to practices, role TEXT, created_at), admin_auth_codes (email PK, hashed_code, expires_at, attempts_count DEFAULT 0, last_requested_at), admin_sessions (session_id UUID PK, user_id FK to admin_users, expires_at, created_at). Revises 0013.

---

## 4. Frontend (frontend/)

Patient-facing React app built with Vite.

Source files (frontend/src/):
- frontend/src/App.tsx — root component. Owns all screen state, useEffect data fetches, and screen transitions.
- frontend/src/ConditionCombobox.tsx — condition search and selection component.
- frontend/src/api.ts — typed HTTP client functions. No business logic.
- frontend/src/constants.ts — shared frontend constants.
- frontend/src/helpers.ts — pure functions with no React dependency.
- frontend/src/index.css — global styles.
- frontend/src/layout.tsx — structural React wrappers (PageShell, InlineError).
- frontend/src/main.tsx — React entry point.
- frontend/src/search.ts — condition filtering logic.
- frontend/src/types.ts — frontend-visible contracts only. No logic.
- frontend/src/test-setup.ts — Vitest setup file.
- frontend/src/upload_constants.ts — hand-written mirror of upload_constants.json. Must be kept in sync manually.
- frontend/src/uitypes — UI-only types that are never serialised.

Screen components (frontend/src/screens/):
- frontend/src/screens/DoneScreen.tsx
- frontend/src/screens/DoneScreen.test.tsx
- frontend/src/screens/SafetyWarningScreen.tsx
- frontend/src/screens/SafetyWarningScreen.test.tsx
- frontend/src/screens/PatientDetailsScreen.tsx
- frontend/src/screens/PatientDetailsScreen.test.tsx
- frontend/src/screens/OutcomeScreen.tsx
- frontend/src/screens/SelectConditionScreen.tsx
- frontend/src/screens/SelectConditionScreen.test.tsx
- frontend/src/screens/FreeTextScreen.tsx
- frontend/src/screens/FreeTextScreen.test.tsx
- frontend/src/screens/EditScreen.tsx
- frontend/src/screens/EditScreen.test.tsx
- frontend/src/screens/ReviewScreen.tsx
- frontend/src/screens/ReviewScreen.test.tsx
- frontend/src/screens/ContactScreen.tsx
- frontend/src/screens/ContactScreen.test.tsx

Config files (frontend/):
- frontend/index.html — patient form entry point.
- frontend/vite.config.ts
- frontend/vitest.config.ts
- frontend/tsconfig.json, tsconfig.app.json, tsconfig.node.json
- frontend/package.json, package-lock.json
- frontend/eslint.config.js

Admin UI source files (frontend/admin-ui/src/):
- frontend/admin-ui/src/App.tsx — root; probes session on mount by calling GET /admin/conditions; routes to LoginView (401) or EditorView (success). No token state.
- frontend/admin-ui/src/LoginView.tsx — two-step MFA login component. Step 1: email input, calls POST /admin/auth/request-code. Step 2: 6-digit code input, calls POST /admin/auth/verify. On success calls onSuccess() so App re-fetches conditions and transitions to EditorView.
- frontend/admin-ui/src/EditorView.tsx — condition selector + tab container; owns unsaved-change tracking via refs; passes onAuthError down to all children. No token prop.
- frontend/admin-ui/src/SignpostingEditor.tsx — Quill-based rich text editor for one condition; calls onAuthError on AuthError. No token prop.
- frontend/admin-ui/src/AvailabilityEditor.tsx — schedule, override, and exceptions card; calls onAuthError on AuthError. No token prop.
- frontend/admin-ui/src/PracticeSettingsTab.tsx — practice email and doctor list editor; calls onAuthError on AuthError. No token prop.
- frontend/admin-ui/src/api.ts — admin API helpers. No token parameter on any function — cookie-based auth. Exports AuthError class (thrown by apiFetch on any 401). Adds X-Requested-With: XMLHttpRequest and credentials: same-origin to all requests. Exports requestMfaCode, verifyMfaCode, logout alongside all existing admin API functions.
- frontend/admin-ui/src/main.tsx — React entry point.
- frontend/admin-ui/src/types.ts — admin portal type definitions.
- frontend/admin-ui/src/index.css — admin portal styles.
- frontend/admin-ui/index.html — admin UI entry point.

Note: frontend/admin-ui/src/TokenView.tsx has been deleted. It was replaced by LoginView.tsx.

Vite builds two entry points served by the StaticFiles mount at / in main.py:
- frontend/dist/index.html — patient form.
- frontend/dist/admin-ui/index.html — admin portal.

---

## 5. Tests (tests/)

Python test suite. For test categories, run commands, and the two-database rule,
see arch_testing.md. This section covers file locations only.

Unit tests (no database required):
- tests/test_admin_router.py — router and auth behaviour for admin endpoints. Includes Section 4: MFA endpoint tests (TestRequestMfaCode, TestVerifyMfaCode, TestLogout) using SpyAuthRepo with configurable return values and call recording. make_test_app now populates app.state.auth_repo, app.state.allowed_admin_domains, app.state.admin_delivery_service, and registers the RateLimitError handler alongside the existing APIError and ConditionNotFound handlers.
- tests/test_delivery_service.py
- tests/test_delivery_worker.py — unit tests for the rewritten delivery worker loop. Patches delivery_repo.claim_next_pending, time.sleep, and the delivery service via MagicMock. Covers: successful path, SMTP failure with backoff, AttachmentNotFound propagation, DB failure exit, sleep-only-on-empty-queue.
- tests/test_pdf_worker.py — unit tests for the PDF worker loop. Patches pdf_repo.claim_next_pending, generate_pdf, and time.sleep. Covers: successful path and ordering invariant, photo count mismatch failure, empty queue sleep, backoff computation, orphan detection CRITICAL log with rate limiting.
- tests/test_pdf_generation.py — tests for generate_pdf including photo embedding and consultation_outcome label rendering. Contains MINIMAL_JPEG shared fixture.
- tests/test_image_sanitizer.py — unit tests for sanitize_image(). Covers: valid JPEG passthrough, PNG-to-JPEG format normalisation, EXIF stripping, truncated JPEG raises ValueError, corrupt bytes raises ValueError. No database required.
- tests/test_practice_endpoint.py — GET /practice endpoint with stub practice repo.
- tests/test_request_validation.py — validate_patient_details and validate_contact_preferences.
- tests/test_upload_constants.py — verifies upload_constants.py loads the JSON correctly.

Integration tests (require TEST_DATABASE_URL):
- tests/test_form_routes.py — full form pipeline via TestClient against live database. Includes CDR integration tests: test_finish_rejects_truncated_jpeg (CE+ regression — proves full decode rather than header-only check) and test_finish_sanitizes_png_to_jpeg (confirms valid PNG survives CDR).
- tests/test_public_routes.py — public endpoint tests via TestClient.
- tests/test_repositories.py — legacy repository layer tests.
- tests/test_pipeline_repositories.py — integration tests for PDFRepository, DeliveryRepository, and PhotoRepository.
- tests/test_delivery_retry.py — delivery retry integration tests against the database.
- tests/test_delivery_worker_integration.py — worker loop integration tests against a live database.
- tests/test_migration_0014.py — migration integration test for 0014. Verifies upgrade() produces admin_users, admin_auth_codes, admin_sessions with expected columns; downgrade() removes all three; re-upgrade succeeds. Requires TEST_DATABASE_URL. Run via make test-integration.

---

## 6. CI workflow (.github/)

- .github/workflows/tests.yml — GitHub Actions workflow. Runs unit tests (Python + Vitest)
  and integration tests (Python + ephemeral Postgres) in parallel on every push.

---

## 7. Service module dependency rules

Each service module lists which other modules it is permitted to import.

- app/services/engine/ruleset.py: standalone; no service imports.
- app/services/engine/encoder_stub.py: standalone; no service imports; returns plain dict.
- app/services/engine/encoder_mapping.py: imports RuntimeState, EncoderOutput, EncoderSignalDefinition.
- app/services/engine/form_logic.py: imports RuntimeState, AnswerState, SafetyEvaluation.
- app/services/engine/projection.py: imports RuntimeState, ExplicitAnswers.
- app/services/engine/safety_engine.py: imports ExplicitAnswers, SafetyEvaluation.
- app/services/engine/serialisation.py: imports RuntimeState, ClinicalOutput, AuditOutput.
- app/services/delivery/delivery_service.py: no clinical contract imports. Receives pre-rendered PDF bytes from caller. Must not import any engine, repository, clinical module, or pdf_formatter.
- app/services/delivery/admin_delivery_service.py: imports stdlib only (smtplib, os, logging, email.message). Must not import any repository, auth_service, or clinical module.
- app/services/delivery/delivery_constants.py: standalone; no application-module imports.
- app/services/delivery/pdf_constants.py: standalone; no application-module imports.
- app/services/delivery/delivery_worker.py: imports delivery_repository, attachment_repository, delivery_service, delivery_constants only.
- app/services/delivery/pdf_worker.py: imports pdf_repository, photo_repository, submission_repository, attachment_repository, delivery_repository, pdf_formatter, pdf_constants only.
- app/services/auth_service.py: imports bcrypt, secrets, time, datetime, errors. Imports AuthRepository and AdminDeliveryService via TYPE_CHECKING only (avoids circular imports at runtime). Must never access the database directly.
- app/services/engine/pipeline.py: orchestration layer; may import all engine services above.
- app/services/presentation_service.py: imports condition_registry, practice_repository.
- app/utils/pdf_formatter.py: imports ClinicalOutput and consultation_outcomes. Must not import any service, repository, router, or engine module.
- app/utils/image_sanitizer.py: imports Pillow (PIL.Image) and io only. Must not import any service, repository, router, engine, or core module.
- app/core/consultation_outcomes.py: standalone; imports json and os only.
- app/core/admin_context.py: imports stdlib and FastAPI only. Must not import any project module.
- app/repositories/auth_repository.py: imports db, psycopg2, uuid, datetime only. Must not contain business logic.
- app/repositories/photo_repository.py: imports db only. No delete method.
- app/repositories/pdf_repository.py: imports db, pdf_constants only.
- app/repositories/delivery_repository.py: imports db, delivery_constants only.
- app/repositories/attachment_repository.py: imports db only.
- app/repositories/submission_repository.py: imports db, serialisation_contracts only.

---

## 8. Banned imports (design failures if violated)

The following imports must never appear in the codebase:

- engine/form_logic, engine/encoder_mapping, engine/encoder_stub, engine/safety_engine must NOT import condition_registry.
- engine/safety_engine must NOT import RuntimeState, AnswerState, or encoder_contracts.
- engine/serialisation must NOT mutate RuntimeState.
- practice_repository must NOT import any service module.
- presentation_service must NOT import RuntimeState, safety_engine, encoder_*, or form_logic.
- engine/form_logic, engine/encoder_mapping, engine/encoder_stub, engine/safety_engine must NOT import practice_repository or presentation_service.
- admin_router must NOT import engine modules, presentation_service, serialisation, projection, or runtime_state.
- admin_context must NOT import any project module other than stdlib and FastAPI.
- auth_service must NOT access any repository or database module directly — only via AuthRepository and AdminDeliveryService interfaces.
- auth_repository must NOT import auth_service, admin_delivery_service, or any service module.
- admin_delivery_service must NOT import any repository, auth_service, or clinical module.
- delivery/delivery_service must NOT import engine modules, repositories, condition_registry, or pdf_formatter.
- delivery/delivery_worker must NOT import clinical engine modules, routers, condition_registry, pdf_formatter, serialisation, or submission_repository.
- delivery/pdf_worker must NOT import admin_router, form_router, public_router, or any admin/presentation module.
- delivery/delivery_constants and pdf/pdf_constants must NOT import any application module.
- pdf_formatter must NOT import delivery modules, repositories, routers, or any engine module.
- image_sanitizer must NOT import any service, repository, router, engine, or core module.
- consultation_outcomes.py must NOT import any application module.
- photo_repository must NOT implement a delete method. Photo deletion belongs exclusively to deletion_job.py.
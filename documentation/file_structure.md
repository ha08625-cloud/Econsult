# FILE_STRUCTURE.md
# LLM reference: actual local directory layout and import mapping
# Last updated: 2026-03-31

---

## 1. Top-level layout

The project root contains the following items:

- main.py — FastAPI entry point. HTTP layer only.
- worker_main.py — Background worker entry point. Validates env vars, instantiates repositories and delivery service, calls run_worker. No HTTP server, no migrations.
- seed_db.py — database seed script, safe to run multiple times.
- .env — local environment variables, not committed.
- Dockerfile — container build definition.
- build.sh — build script used by the container.
- railway.toml — Railway deployment config. Contains only `builder = "DOCKERFILE"`.
- requirements.txt — Python dependencies.
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
- app/models/serialisation_contracts.py — PatientDetails, ClinicalOutput, AuditOutput.
- app/models/availability_models.py

### 2.2 app/services/

Business logic and orchestration. Divided into two sub-packages by concern, plus two
flat files that do not belong exclusively to either.

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
- app/services/engine/pipeline.py — orchestration layer; wires all engine services together. Formerly engine_adapters.py.

#### app/services/delivery/

IO-touching delivery concerns. Handles SMTP, retry scheduling, and structured logging
of delivery lifecycle events.

Files:
- app/services/delivery/delivery_service.py — DeliveryService abstract base class; EmailDeliveryService (production SMTP with PDF attachment); ConsoleDeliveryService (dev only, raises if DEV_MODE not set). Receives pre-rendered PDF bytes from caller; does not generate PDFs.
- app/services/delivery/delivery_orchestration.py — single entry point for all delivery attempts (first attempt and retries). Contains DeliveryOutcomeStatus enum, DeliveryOutcome dataclass, and attempt_delivery function. Imports from submission_repository, attachment_repository, delivery_service, delivery_constants, delivery_events.
- app/services/delivery/delivery_constants.py — retry backoff schedule (RETRY_BACKOFF_MINUTES) and MAX_ATTEMPTS. No application-module imports. Single canonical source for the exhaustion threshold.
- app/services/delivery/delivery_events.py — four string constants for structured logging of delivery lifecycle (DELIVERY_SENT, DELIVERY_FAILED, DELIVERY_EXHAUSTED, DELIVERY_RETRY_TOO_EARLY). No application-module imports.
- app/services/delivery/delivery_worker.py — background worker loop. run_worker fetches retryable submission IDs via list_retryable, calls attempt_delivery per ID, and sleeps only when the queue is empty. Per-item exceptions are caught and logged at CRITICAL; psycopg2.OperationalError from list_retryable propagates uncaught so the process exits and Railway restarts. Orphan detection runs once per loop iteration with CRITICAL log emission rate-limited to once per 60 seconds. Imports from submission_repository, attachment_repository, delivery_service, delivery_orchestration only.

#### app/services/ (flat)

- app/services/availability_orchestration.py — orchestration layer; wires AvailabilityRepository and availability_service together. No HTTP logic. Called by public_router.py and main.py.
- app/services/availability_service.py
- app/services/presentation_service.py — assembles patient-facing presentation data.

### 2.3 app/repositories/

Database access for persistent records. No business logic.

Files:
- app/repositories/attachment_repository.py — PDF attachment storage for delivery retry. Owns the submission_attachments table.
- app/repositories/availability_repository.py — weekly hours, overrides, and per-date exceptions.
- app/repositories/practice_repository.py — practice record CRUD including update_email.
- app/repositories/runtime_state_repository.py — session state read/write. Registered in app.state as runtime_repo.
- app/repositories/submission_repository.py — submission record creation, delivery status tracking, and delivery retry support. Contains PendingDelivery dataclass (lightweight read-only projection for the orchestration layer), get_pending_delivery, and record_attempt_outcome (atomic UPDATE with RETURNING). list_retryable returns list[str] (submission IDs only, not PendingDelivery objects) so the worker can pass IDs directly to attempt_delivery without carrying a stale projection. list_orphans returns submission IDs for pending submissions with delivery_attempts=0 older than a given threshold.

### 2.4 app/core/

Infrastructure concerns only. No clinical logic.

Files:
- app/core/admin_context.py — admin authentication context and FastAPI dependency.
- app/core/condition_registry.py — loads and indexes condition rulesets at startup; immutable after init.
- app/core/consultation_outcomes.json — see top-level layout; file lives at project root, not inside app/core/.
- app/core/consultation_outcomes.py — exposes CONSULTATION_OUTCOMES (list[dict]) and VALID_OUTCOME_VALUES (frozenset[str]) loaded from consultation_outcomes.json at import time. Used by request_validation.py (value validation) and pdf_formatter.py (label lookup). Fails fast at startup if JSON is missing or malformed. Must not be changed without also updating the ConsultationOutcome union type in frontend/src/types.ts.
- app/core/db.py — shared Postgres connection module. Provides get_conn() context manager and alembic_upgrade() for running migrations at startup.
- app/core/dependencies.py — shared FastAPI dependency provider functions. All routers import from here to access app.state values via Depends rather than direct request.app.state access.
- app/core/errors.py — APIError and named error constants.
- app/core/request_validation.py — validates incoming HTTP payloads. Imports VALID_OUTCOME_VALUES from consultation_outcomes.py to validate the consultation_outcome field in contact_preferences.
- app/core/upload_constants.json — canonical source of truth for photo upload limits (allowed MIME types, per-file size, total size, file count). Read by upload_constants.py at import time.
- app/core/upload_constants.py — exposes named constants loaded from upload_constants.json. Used by validate_photo_guards in request_validation.py (step 5). Must not be changed without also updating frontend/src/upload_constants.ts.

### 2.5 app/utils/

Pure utility functions. No IO, no database access, no imports from routers or repositories.

Files:
- app/utils/pdf_formatter.py — generate_pdf() pure function. Takes ClinicalOutput, submission metadata, and optional practice_name; returns raw PDF bytes via fpdf2. Sections mirror the plain-text email body. Imports CONSULTATION_OUTCOMES from consultation_outcomes.py to derive the outcome label lookup dict at module load time.

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
- alembic/versions/0005_submitted_at_explicit.py — removes DEFAULT NOW() from submission_records.submitted_at. Application must supply the value explicitly.
- alembic/versions/0006_attachment_storage.py — adds condition_label to submission_records; creates submission_attachments table for PDF blob storage.
- alembic/versions/0007_delivery_retry_columns.py — adds delivery_attempts (INTEGER NOT NULL DEFAULT 0), last_attempt_at (TIMESTAMPTZ), and next_retry_after (TIMESTAMPTZ) to submission_records. Supports delivery retry orchestration.

---

## 4. Frontend (frontend/)

Patient-facing React app built with Vite.

Source files (frontend/src/):
- frontend/src/App.tsx — root component. Owns all screen state, useEffect data fetches, and screen transitions. Renders the active screen component. No inline JSX for individual screens that have been extracted to frontend/src/screens/.
- frontend/src/ConditionCombobox.tsx — condition search and selection component.
- frontend/src/api.ts — typed HTTP client functions. No business logic.
- frontend/src/constants.ts — shared frontend constants.
- frontend/src/helpers.ts — pure functions with no React dependency: state initialisers (initialiseEditableAnswers, initialiseContactPreferences) and client-side validation (isValidUkPhone).
- frontend/src/index.css — global styles.
- frontend/src/layout.tsx — structural React wrappers (PageShell, InlineError). No application state knowledge. Must not import from api.ts, helpers.ts, or any screen component.
- frontend/src/main.tsx — React entry point.
- frontend/src/search.ts — condition filtering logic (substring, tag, and Levenshtein fuzzy match).
- frontend/src/types.ts — frontend-visible contracts only. No logic. Contains the ConsultationOutcome union type, which must be kept in sync with consultation_outcomes.json manually — see sync obligation note in arch_frontend.md.
- frontend/src/test-setup.ts — Vitest setup file. Configures jsdom environment before test runs.
- frontend/src/upload_constants.ts — hand-written mirror of upload_constants.json. Values are written explicitly. Must be kept in sync with the JSON file manually.
- frontend/src/uitypes — UI-only types that are never serialised. Kept separate from types.ts, which contains wire-format contracts only.

Screen components (frontend/src/screens/):
Screen components are extracted from App.tsx during Phase 2. Each screen component
owns only its own UI state. Session state (runtimeId, version, clientState, etc.)
remains in App.tsx and is passed down as props.

- frontend/src/screens/DoneScreen.tsx — DONE screen. Props: { practiceWasClosed: boolean }. No state, no API calls.
- frontend/src/screens/DoneScreen.test.tsx — component tests for DoneScreen.
- frontend/src/screens/SafetyWarningScreen.tsx — Safety warning screen.
- frontend/src/screens/SafetyWarningScreen.test.tsx
- frontend/src/screens/PatientDetailsScreen.tsx — Patient details screen. Captures patient identity before condition selection.
- frontend/src/screens/PatientDetailsScreen.test.tsx
- frontend/src/screens/OutcomeScreen.tsx — Consultation outcome screen. Patient selects their desired outcome before condition selection. Imports consultation_outcomes.json directly via resolveJsonModule. No API call; local state only.
- frontend/src/screens/SelectConditionScreen.tsx — Condition selection screen. Includes a back button navigating to OUTCOME.
- frontend/src/screens/SelectConditionScreen.test.tsx
- frontend/src/screens/FreeTextScreen.tsx — Free text screen.
- frontend/src/screens/FreeTextScreen.test.tsx
- frontend/src/screens/EditScreen.tsx — Edit screen.
- frontend/src/screens/EditScreen.test.tsx
- frontend/src/screens/ReviewScreen.tsx — Review screen.
- frontend/src/screens/ReviewScreen.test.tsx
- frontend/src/screens/ContactScreen.tsx — Contact screen. Accepts consultationOutcome as a required prop and includes it in the finish payload.
- frontend/src/screens/ContactScreen.test.tsx

Config files (frontend/):
- frontend/index.html — patient form entry point.
- frontend/vite.config.ts — Vite build config. No test configuration; that lives in vitest.config.ts.
- frontend/vitest.config.ts — Vitest test runner config (jsdom environment, setup file). Separated from vite.config.ts to avoid breaking the production Docker build.
- frontend/tsconfig.json, tsconfig.app.json, tsconfig.node.json — test files explicitly excluded from tsconfig.json; excludes *.test.ts from build. resolveJsonModule is enabled in tsconfig.app.json to allow OutcomeScreen.tsx to import consultation_outcomes.json directly.
- frontend/package.json, package-lock.json
- frontend/eslint.config.js

Admin UI source files (frontend/admin-ui/src/):
- frontend/admin-ui/src/App.tsx
- frontend/admin-ui/src/EditorView.tsx — three-tab layout; conditionally renders SignpostingEditor and PracticeSettingsTab; always mounts AvailabilityEditor
- frontend/admin-ui/src/SignpostingEditor.tsx
- frontend/admin-ui/src/AvailabilityEditor.tsx
- frontend/admin-ui/src/PracticeSettingsTab.tsx — practice email editor; fetches on mount
- frontend/admin-ui/src/TokenView.tsx
- frontend/admin-ui/src/api.ts — includes PracticeDetails interface, getPractice, updatePracticeEmail
- frontend/admin-ui/src/main.tsx
- frontend/admin-ui/src/types.ts
- frontend/admin-ui/src/index.css
- frontend/admin-ui/index.html — admin UI entry point.

Vite builds two entry points:
- frontend/dist/index.html — patient form.
- frontend/dist/admin-ui/index.html — admin portal.

Both are served by the StaticFiles mount at / in main.py.

---

## 5. Tests (tests/)

Python test suite. For test categories, run commands, and the two-database rule,
see arch_testing.md. This section covers file locations only.

Unit tests (no database required):
- tests/test_admin_router.py — router and auth behaviour for admin endpoints; signposting sanitisation.
- tests/test_delivery_orchestration.py — unit tests for attempt_delivery with mocked dependencies. Covers success path, failure path, error propagation, DeliveryOutcomeStatus enum, and PendingDelivery immutability.
- tests/test_delivery_service.py
- tests/test_delivery_worker.py — unit tests for the worker loop. No database required. Patches attempt_delivery at delivery_worker (not delivery_orchestration — see comment in file), time.sleep, and list_retryable/list_orphans via MagicMock. Covers: per-item processing, exception resilience, sleep-only-on-empty-queue, no-sleep-between-batches, DB failure exit, and orphan detection CRITICAL log with rate limiting.
- tests/test_pdf_generation.py — tests for generate_pdf including photo embedding and consultation_outcome label rendering.
- tests/test_practice_endpoint.py — GET /practice endpoint with stub practice repo.
- tests/test_request_validation.py — validate_patient_details and validate_contact_preferences including consultation_outcome validation.
- tests/test_sanitise_signposting.py — sanitise_signposting_html unit tests.
- tests/test_upload_constants.py — verifies upload_constants.py loads the JSON correctly and exposes the expected types and values.

Integration tests (require DATABASE_URL):
- tests/test_form_routes.py — full form pipeline via TestClient against live database. MockDeliveryService and FailingDeliveryService match the current DeliveryService ABC signature (pdf_bytes, submitted_at; no ClinicalOutput).
- tests/test_public_routes.py — public endpoint tests via TestClient; imports main.py directly.
- tests/test_repositories.py — repository layer tests; must be run directly, not via pytest.
- tests/test_delivery_retry.py — delivery retry pipeline integration tests. Exercises attempt_delivery, list_retryable, and record_attempt_outcome directly against the database. Requires TEST_DATABASE_URL.
- tests/test_delivery_worker_integration.py — worker loop integration tests. Exercises run_worker against a live database using real delivery service stubs. Patches time.sleep via StopIteration to halt the loop after one iteration. Covers batch drain, backoff-too-early enforcement, full retry schedule progression, and orphan detection CRITICAL log. Requires TEST_DATABASE_URL.

---

## 6. CI workflow (.github/)

- .github/workflows/tests.yml — GitHub Actions workflow. Runs unit tests (Python + Vitest)
  and integration tests (Python + ephemeral Postgres) in parallel on every push.
  Does not use the Makefile or .env. See arch_testing.md for design decisions.

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
- app/services/delivery/delivery_service.py: No clinical contract imports. Receives pre-rendered PDF bytes from caller. Must not import any engine, repository, clinical module, or pdf_formatter.
- app/services/delivery/delivery_constants.py: standalone; no application-module imports.
- app/services/delivery/delivery_events.py: standalone; no application-module imports.
- app/services/delivery/delivery_orchestration.py: imports submission_repository, attachment_repository, delivery_service, delivery_constants, delivery_events. Must not import clinical engine modules, routers, or access the database directly.
- app/services/delivery/delivery_worker.py: imports submission_repository, attachment_repository, delivery_service, delivery_orchestration. Must not import clinical engine modules, routers, or access the database directly. Must not implement delivery policy — all policy lives in delivery_orchestration.
- app/services/engine/pipeline.py: orchestration layer; may import all services above.
- app/services/presentation_service.py: imports condition_registry, practice_repository.
- app/utils/pdf_formatter.py: imports ClinicalOutput and consultation_outcomes. Must not import any service, repository, router, or engine module.
- app/core/consultation_outcomes.py: standalone; imports json and os only. No application-module imports.

---

## 8. Banned imports (design failures if violated)

The following imports must never appear in the codebase:

- engine/form_logic, engine/encoder_mapping, engine/encoder_stub, engine/safety_engine must NOT import condition_registry.
- engine/safety_engine must NOT import RuntimeState, AnswerState, or encoder_contracts.
- engine/serialisation must NOT mutate RuntimeState.
- practice_repository must NOT import any service module.
- presentation_service must NOT import RuntimeState, safety_engine, encoder_*, or form_logic.
- engine/form_logic, engine/encoder_mapping, engine/encoder_stub, engine/safety_engine must NOT import practice_repository or presentation_service (the clinical engine has no awareness of practice identity).
- admin_router must NOT import engine modules, presentation_service, serialisation, projection, or runtime_state.
- delivery/delivery_service must NOT import engine modules, repositories, condition_registry, or pdf_formatter.
- delivery/delivery_orchestration must NOT import engine modules, routers, condition_registry, pdf_formatter, or serialisation. It interacts with clinical data only through repository projections (PendingDelivery) and pre-rendered PDF bytes.
- delivery/delivery_constants and delivery/delivery_events must NOT import any application module.
- delivery/delivery_worker must NOT import clinical engine modules, routers, condition_registry, pdf_formatter, or serialisation. It must NOT implement retry policy or make decisions about delivery outcomes — those belong in delivery_orchestration.
- pdf_formatter must NOT import delivery modules, repositories, routers, or any engine module.
- consultation_outcomes.py must NOT import any application module.

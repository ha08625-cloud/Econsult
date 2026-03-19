# FILE_STRUCTURE.md
# LLM reference: actual local directory layout and import mapping
# Last updated: 2026-03-19

---

## 1. Top-level layout

The project root contains the following items:

- main.py — FastAPI entry point. HTTP layer only.
- seed_db.py — database seed script, safe to run multiple times.
- .env — local environment variables, not committed.
- Dockerfile — container build definition.
- build.sh — build script used by the container.
- railway.toml — Railway deployment config. Contains only `builder = "DOCKERFILE"`.
- requirements.txt — Python dependencies.
- alembic.ini — Alembic configuration. Placeholder database URL; the real URL is injected at runtime from DATABASE_URL. No secrets; safe to commit.
- app/ — all Python application code.
- alembic/ — Alembic migration scripts.
- frontend/ — patient-facing React app.
- data/ — condition ruleset JSON files.

---

## 2. Python application code (app/)

The app/ directory is a Python package. It contains four sub-packages.

### 2.1 app/models/

Data structures only. No business logic, no IO, no imports from non-model modules.
Imported by service modules; never imports service modules.

Files:
- app/models/api_models.py — SafetyMessage and other HTTP-layer data shapes.
- app/models/encoder_contracts.py — EncoderSignalDefinition, EncoderOutput.
- app/models/explicit_answers.py — ExplicitAnswers (frozen, immutable projected answers for safety engine).
- app/models/runtime_state.py — RuntimeState, AnswerState, SafetyEvaluation.
- app/models/serialisation_contracts.py — ClinicalOutput, AuditOutput.
- app/models/availability_models.py

### 2.2 app/services/

Business logic and orchestration. May import models; must not import each other's
internal state except via defined interfaces.

Files:
- app/services/email_service.py
- app/services/encoder_mapping.py — containment layer; applies encoder output to RuntimeState.
- app/services/encoder_stub.py — placeholder encoder, expected to be replaced; returns plain dict.
- app/services/engine_adapters.py — orchestration layer; wires all services together.
- app/services/form_logic.py — deterministic functional core; no IO.
- app/services/presentation_service.py — assembles patient-facing presentation data.
- app/services/projection.py — projects RuntimeState to ExplicitAnswers.
- app/services/ruleset.py — loads and validates condition ruleset JSON.
- app/services/safety_engine.py — evaluates safety rules; consumes ExplicitAnswers only.
- app/services/serialisation.py — produces ClientStateView, ClinicalOutput, AuditOutput.

### 2.3 app/repositories/

Database access for persistent records. No business logic.

Files:
- app/repositories/practice_repository.py — practice record CRUD.
- app/repositories/submission_repository.py — submission record creation and delivery status tracking
- app/repositories/availability_repository.py

### 2.4 app/core/

Infrastructure concerns only. No clinical logic.

Files:
- app/core/admin_context.py — admin authentication context and FastAPI dependency.
- app/core/condition_registry.py — loads and indexes condition rulesets at startup; immutable after init.
- app/core/db.py — app/core/db.py — shared Postgres connection module. Only file that imports psycopg2. Provides get_conn() context manager and alembic_upgrade() for running migrations at startup
- app/core/errors.py — APIError and named error constants.
- app/core/persistence.py — RuntimeStateRepository; database read/write for session state.
- app/core/request_validation.py — validates incoming HTTP payloads.

### 2.5 app/routers/

HTTP routing only. No business logic.

Files:
- app/routers/admin_router.py

---

## 3. Alembic migrations (alembic/)

Schema migration scripts managed by Alembic. alembic/env.py reads DATABASE_URL
from the environment and runs migrations. alembic_upgrade() in app/core/db.py
calls `alembic upgrade head` at application startup.

Advisory lock is enabled by default and must not be disabled. See architecture.md
for the concurrent startup limitation.

Files:
- alembic/env.py — Alembic environment configuration. Reads DATABASE_URL; no ORM metadata.
- alembic/versions/ — migration scripts, ordered by revision chain.
- alembic/versions/0001_initial_schema.py — four existing tables (practices, runtime_state_versions, practice_signposting, submission_records). Uses IF NOT EXISTS as a one-time concession. Future migrations must not use IF NOT EXISTS.
- alembic/versions/0002_availability_table.py
- alembic/versions/0003_availability_override.py
- alembic/versions/0004_availability_exceptions.py

---

## 4. Frontend (frontend/)

Patient-facing React app built with Vite.

Source files (frontend/src/):
- frontend/src/App.tsx — root component. Owns all screen state, useEffect data fetches, and screen transitions. Renders the active screen component. No inline JSX for individual screens that have been extracted to frontend/src/screens/.
- frontend/src/ConditionCombobox.tsx — condition search and selection component.
- frontend/src/api.ts — typed HTTP client functions. No business logic.
- frontend/src/constants.ts — shared frontend constants.
- frontend/src/helpers.ts — pure functions with no React dependency: state initialisers (initialiseEditableAnswers, initialiseContactPreferences) and client-side validation (isValidUkPhone). No side effects, no API calls. Only imports from types.ts.
- frontend/src/index.css — global styles.
- frontend/src/layout.tsx — structural React wrappers (PageShell, InlineError). No application state knowledge. Must not import from api.ts, helpers.ts, or any screen component.
- frontend/src/main.tsx — React entry point.
- frontend/src/search.ts — condition filtering logic (substring, tag, and Levenshtein fuzzy match).
- frontend/src/types.ts — frontend-visible contracts only. No logic.
- frontend/src/test-setup.ts — Vitest setup file. Configures jsdom environment before test runs.

Screen components (frontend/src/screens/):
Screen components are extracted from App.tsx during Phase 2. Each screen component
owns only its own UI state. Session state (runtimeId, version, clientState, etc.)
remains in App.tsx and is passed down as props.

- frontend/src/screens/DoneScreen.tsx — DONE screen. Props: { submittedAfterHours: boolean }. No state, no API calls.
- frontend/src/screens/DoneScreen.test.tsx — component tests for DoneScreen.
- frontend/src/screens/SafetyWarningScreen.tsx - Safety warning screen
- frontend/src/screens/SafetyWarningScreen.test.tsx
- frontend/src/screens/SelectConditionScreen.tsx - Condition Selection Screen
- frontend/src/screens/SelectConditionScreen.test.tsx
- frontend/src/screens/ReviewScreen.tsx - Review Screen
- frontend/src/screens/ReviewScreen.test.tsx
- frontend/src/screens/EditScreen.tsx - Done Screen
- frontend/src/screens/EditScreen.test.tsx

Config files (frontend/):
- frontend/index.html — patient form entry point.
- frontend/vite.config.ts — Vite build config. No test configuration; that lives in vitest.config.ts.
- frontend/vitest.config.ts — Vitest test runner config (jsdom environment, setup file). Separated from vite.config.ts to avoid breaking the production Docker build.
- frontend/tsconfig.json, tsconfig.app.json, tsconfig.node.json - test files explicitly excluded from tsconfig.json, excludes *.test.ts from build
- frontend/package.json, package-lock.json
- frontend/eslint.config.js

Admin UI source files (frontend/admin-ui/src/):
- frontend/admin-ui/src/App.tsx
- frontend/admin-ui/src/EditorView.tsx
- frontend/admin-ui/src/SignpostingEditor.tsx
- frontend/admin-ui/src/TokenView.tsx
- frontend/admin-ui/src/api.ts
- frontend/admin-ui/src/main.tsx
- frontend/admin-ui/src/types.ts
- frontend/admin-ui/src/index.css
- frontend/admin-ui/src/AvailabilityEditor.tsx
- frontend/admin-ui/index.html — admin UI entry point.

Vite builds two entry points:
- frontend/dist/index.html — patient form.
- frontend/dist/admin-ui/index.html — admin portal.

Both are served by the StaticFiles mount at / in main.py.

---

## 5. Data files (data/)

Condition ruleset JSON files. Clinical content only; no code.

- data/uti1.json — urinary symptoms ruleset (MVP condition).
- data/general.json — general condition ruleset.
- Future condition rulesets go in this directory.

---

## 6. Import conventions

All imports use the full package path from the project root.

Examples:
  from app.models.runtime_state import RuntimeState
  from app.models.encoder_contracts import EncoderOutput
  from app.models.explicit_answers import ExplicitAnswers
  from app.services.form_logic import initialise_runtime_state
  from app.services.engine_adapters import init_runtime_state
  from app.core.persistence import RuntimeStateRepository
  from app.core.db import alembic_upgrade
  from app.core.errors import APIError
  from app.repositories.practice_repository import PracticeRepository

---

## 7. Service module dependency rules

Each service module lists which other modules it is permitted to import.

- app/services/ruleset.py: standalone; no service imports.
- app/services/encoder_stub.py: standalone; no service imports; returns plain dict.
- app/services/encoder_mapping.py: imports RuntimeState, EncoderOutput, EncoderSignalDefinition.
- app/services/form_logic.py: imports RuntimeState, AnswerState, SafetyEvaluation.
- app/services/projection.py: imports RuntimeState, ExplicitAnswers.
- app/services/safety_engine.py: imports ExplicitAnswers, SafetyEvaluation.
- app/services/serialisation.py: imports RuntimeState, ClinicalOutput, AuditOutput.
- app/services/engine_adapters.py: orchestration layer; may import all services above.
- app/services/presentation_service.py: imports condition_registry, practice_repository.

---

## 8. Banned imports (design failures if violated)

The following imports must never appear in the codebase:

- form_logic, encoder_mapping, encoder_stub, safety_engine must NOT import condition_registry.
- safety_engine must NOT import RuntimeState, AnswerState, or encoder_contracts.
- serialisation must NOT mutate RuntimeState.
- practice_repository must NOT import any service module.
- presentation_service must NOT import RuntimeState, safety_engine, encoder_*, or form_logic.
- form_logic, encoder_mapping, encoder_stub, safety_engine must NOT import practice_repository
  or presentation_service (the clinical engine has no awareness of practice identity).
- admin_router must NOT import clinical engine modules, presentation_service, serialisation,
  projection, or runtime_state.

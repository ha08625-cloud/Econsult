# FILE_STRUCTURE.md
# LLM reference: actual local directory layout, structural purpose, and import mapping
# Last updated: 2026-04-10

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
- `admin_delivery_service.py` — Admin MFA delivery. *Imports: stdlib only.*
- `delivery_constants.py` — Retry thresholds. *Imports: standalone; no application modules.*
- `pdf_constants.py` — PDF retry thresholds. *Imports: standalone; no application modules.*
- `delivery_worker.py` — Delivery worker loop. *Imports: delivery_repository, attachment_repository, delivery_service, delivery_constants only.*
- `pdf_worker.py` — PDF generation worker loop. *Imports: pdf_repository, photo_repository, submission_repository, attachment_repository, delivery_repository, pdf_formatter, pdf_constants only.*

**`app/services/` (flat)**
- `auth_service.py` — MFA auth business logic. *Imports: bcrypt, secrets, time, datetime, errors. DB/delivery via interfaces only.*
- `availability_orchestration.py` — Wires repository and service.
- `availability_service.py` — Availability business logic.
- `presentation_service.py` — Patient-facing presentation assembler. *Imports: condition_registry, practice_repository.*

### 2.3 `app/repositories/`
Database access for persistent records. No business logic.

- `attachment_repository.py` — Owns `submission_attachments`. *Imports: db only.*
- `audit_repository.py` — Owns `admin_audit_log`. *Imports: db, psycopg2, base64, json, re, datetime only.*
- `auth_repository.py` — Owns `admin_users`, `admin_auth_codes`, `admin_sessions`. *Imports: db, psycopg2, uuid, datetime only.*
- `availability_repository.py` — Owns availability and exception tables.
- `delivery_repository.py` — Owns `delivery_jobs`. *Imports: db, delivery_constants only.*
- `pdf_repository.py` — Owns `pdf_jobs`. *Imports: db, pdf_constants only.*
- `photo_repository.py` — Owns `submission_photos`. *Imports: db only.*
- `practice_repository.py` — Owns practice records.
- `runtime_state_repository.py` — Owns session state versions.
- `submission_repository.py` — Owns `submission_records`. *Imports: db, serialisation_contracts only.*

### 2.4 `app/core/`
Infrastructure concerns only. No clinical logic.

- `admin_context.py` — Admin authentication context/dependencies. *Imports: stdlib and FastAPI only.*
- `condition_registry.py` — Ruleset indexer.
- `consultation_outcomes.py` — Python interface for outcome constants. *Imports: json and os only.*
- `db.py` — Shared Postgres connection module.
- `dependencies.py` — Shared FastAPI dependency provider functions.
- `errors.py` — Shared API and rate limit errors.
- `http_utils.py` — HTTP utility helpers (IP extraction). *Imports: stdlib only.*
- `request_validation.py` — HTTP payload validation.
- `consultation_outcomes.json` — Canonical source for outcome values.
- `upload_constants.json` — Canonical source for photo upload limits.
- `upload_constants.py` — Python interface for upload constants.

### 2.5 `app/utils/`
Pure utility functions. No IO, no database access.

- `pdf_formatter.py` — Pure PDF generation function. *Imports: ClinicalOutput and consultation_outcomes.*
- `image_sanitizer.py` — Content Disarm and Reconstruction (CDR) logic. *Imports: Pillow (PIL.Image) and io only.*

---

## 3. Alembic migrations (`alembic/`)
Schema migration scripts. See code files directly for exact table definitions.

- `alembic/env.py` — Alembic environment configuration.
- `alembic/versions/0001_initial_schema.py` — Single migration that creates the complete schema from scratch.

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
- `screens/` — Patient flow views (`SafetyWarningScreen`, `PatientDetailsScreen`, `OutcomeScreen`, `SelectConditionScreen`, `FreeTextScreen`, `EditScreen`, `ReviewScreen`, `ContactScreen`).

**Admin UI (`frontend/admin-ui/src/`)**
- `App.tsx` — Admin root component and routing.
- `api.ts` — Admin API clients (cookie-auth based).
- `main.tsx` — React entry point.
- `types.ts` — Admin-specific contracts.
- `screens/` — Admin views (`LoginView`, `EditorView`, `SignpostingEditor`, `AvailabilityEditor`, `PracticeSettingsTab`, `AuditLogTab`).

---

## 5. Tests (`tests/`)

**Unit tests (Mocked/In-memory)**
- `test_admin_router.py`, `test_delivery_service.py`, `test_delivery_worker.py`, `test_pdf_worker.py`, `test_pdf_generation.py`, `test_image_sanitizer.py`, `test_practice_endpoint.py`, `test_request_validation.py`, `test_upload_constants.py`.

**Integration tests (Live `TEST_DATABASE_URL`)**
- `test_form_routes.py`, `test_public_routes.py`, `test_repositories.py`, `test_pipeline_repositories.py`, `test_delivery_retry.py`, `test_delivery_worker_integration.py`.

---

## 6. Banned imports (Design failures if violated)

These structural boundaries MUST NOT be crossed:

* `engine/form_logic`, `engine/encoder_mapping`, `engine/encoder_stub`, `engine/safety_engine` **must NOT** import `condition_registry`, `practice_repository`, or `presentation_service`.
* `engine/safety_engine` **must NOT** import `RuntimeState`, `AnswerState`, or `encoder_contracts`.
* `engine/serialisation` **must NOT** mutate `RuntimeState`.
* `practice_repository` **must NOT** import any service module.
* `presentation_service` **must NOT** import `RuntimeState`, `safety_engine`, `encoder_*`, or `form_logic`.
* `admin_router` **must NOT** import engine modules, `presentation_service`, `serialisation`, `projection`, or `runtime_state`.
* `admin_context` **must NOT** import any project module other than stdlib and FastAPI.
* `auth_service` **must NOT** access any repository or database module directly.
* `auth_repository` **must NOT** import `auth_service`, `admin_delivery_service`, or any service module.
* `admin_delivery_service` **must NOT** import any repository, `auth_service`, or clinical module.
* `delivery/delivery_service` **must NOT** import engine modules, repositories, `condition_registry`, or `pdf_formatter`.
* `delivery/delivery_worker` **must NOT** import clinical engine modules, routers, `condition_registry`, `pdf_formatter`, `serialisation`, or `submission_repository`.
* `delivery/pdf_worker` **must NOT** import `admin_router`, `form_router`, `public_router`, or any admin/presentation module.
* `delivery/delivery_constants` and `pdf/pdf_constants` **must NOT** import any application module.
* `audit_repository` **must NOT** import from service modules, routers, or the patient-facing request path.
* `http_utils` **must NOT** import any application module.
* `pdf_formatter` **must NOT** import delivery modules, repositories, routers, or any engine module.
* `image_sanitizer` **must NOT** import any service, repository, router, engine, or core module.
* `consultation_outcomes.py` **must NOT** import any application module.
* `photo_repository` **must NOT** implement a delete method (handled strictly by `deletion_job.py`).
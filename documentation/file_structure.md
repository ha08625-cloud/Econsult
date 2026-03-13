# FILE_STRUCTURE.md
# LLM reference: actual local directory layout and import mapping
# Last updated: 2026-03-13

## Local directory layout

```
project_root/
├── app/
│   ├── __init__.py
│   │
│   ├── models/                         # Data shapes only. No logic, no IO.
│   │   ├── __init__.py
│   │   ├── api_models.py               # SafetyMessage and other HTTP-layer data shapes
│   │   ├── encoder_contracts.py        # EncoderSignalDefinition, EncoderOutput
│   │   ├── explicit_answers.py         # ExplicitAnswers (immutable, safety engine input)
│   │   ├── runtime_state.py            # RuntimeState, AnswerState, SafetyEvaluation
│   │   └── serialisation_contracts.py  # ClinicalOutput, AuditOutput
│   │
│   ├── routers/                        # HTTP routing only. No business logic.
│   │   ├── __init__.py
│   │   └── admin_router.py
│   │
│   ├── services/                       # Business logic and orchestration.
│   │   ├── __init__.py
│   │   ├── email_service.py
│   │   ├── encoder_mapping.py
│   │   ├── encoder_stub.py             # Placeholder encoder. Expected to be replaced.
│   │   ├── engine_adapters.py          # Orchestration layer. Wires all services together.
│   │   ├── form_logic.py               # Deterministic functional core. No IO.
│   │   ├── presentation_service.py
│   │   ├── projection.py
│   │   ├── ruleset.py
│   │   ├── safety_engine.py            # Isolated. Consumes ExplicitAnswers only.
│   │   └── serialisation.py
│   │
│   ├── repositories/                   # Database access only. No business logic.
│   │   ├── __init__.py
│   │   ├── practice_repository.py
│   │   └── submission_repository.py
│   │
│   └── core/                           # Infrastructure: database, errors, validation.
│       ├── __init__.py
│       ├── admin_context.py
│       ├── condition_registry.py
│       ├── errors.py
│       ├── persistence.py
│       └── request_validation.py
│
├── frontend/                           # All frontend code. Single Vite build pipeline.
│   │
│   ├── src/                            # Patient-facing React app.
│   │   ├── App.tsx
│   │   ├── ConditionCombobox.tsx
│   │   ├── api.ts
│   │   ├── constants.ts                # Shared constants (patient form + admin portal)
│   │   ├── index.css
│   │   ├── main.tsx
│   │   ├── search.ts
│   │   └── types.ts
│   │
│   ├── admin-ui/                       # Admin portal React app. Separate Vite entry point.
│   │   ├── index.html                  # Vite entry point for admin portal
│   │   └── src/
│   │       ├── App.tsx
│   │       ├── EditorView.tsx
│   │       ├── SignpostingEditor.tsx
│   │       ├── TokenView.tsx
│   │       ├── api.ts
│   │       ├── index.css
│   │       ├── main.tsx
│   │       └── types.ts
│   │
│   ├── eslint.config.js
│   ├── index.html                      # Vite entry point for patient form
│   ├── package-lock.json
│   ├── package.json
│   ├── tsconfig.app.json
│   ├── tsconfig.json
│   ├── tsconfig.node.json
│   └── vite.config.ts                  # Two entry points: index.html + admin-ui/index.html
│
├── data/                               # Condition rulesets (JSON). Clinical content only.
│   ├── uti1.json
│   └── general.json
│
├── main.py                             # FastAPI entry point. HTTP layer only.
├── seed_db.py
├── .env
├── Dockerfile
├── build.sh
├── railway.toml
├── requirements.txt
└── runtime.db
```

## Import conventions

All imports use the full package path from the project root.

Examples:
  from app.models.runtime_state import RuntimeState
  from app.models.encoder_contracts import EncoderOutput
  from app.models.explicit_answers import ExplicitAnswers
  from app.services.form_logic import initialise_runtime_state
  from app.services.engine_adapters import init_runtime_state
  from app.core.persistence import RuntimeStateRepository
  from app.core.errors import APIError
  from app.repositories.practice_repository import PracticeRepository

## Model files (app/models/)

These files define data structures only. They contain NO business logic, NO IO,
and NO imports from non-model modules. They are imported by service modules but
never import service modules.

- api_models.py: SafetyMessage and other HTTP-layer data shapes
- encoder_contracts.py: EncoderSignalDefinition, EncoderOutput
- explicit_answers.py: ExplicitAnswers (frozen, immutable projected answers for safety engine)
- runtime_state.py: RuntimeState, AnswerState, SafetyEvaluation
- serialisation_contracts.py: ClinicalOutput, AuditOutput

## Service modules (app/services/)

These contain business logic. They may import models but must not import
each other's internal state except via defined interfaces.

Dependency rules:
- ruleset.py: standalone, no service imports
- encoder_stub.py: standalone, no service imports, returns plain dict
- encoder_mapping.py: imports RuntimeState, EncoderOutput, EncoderSignalDefinition
- form_logic.py: imports RuntimeState, AnswerState, SafetyEvaluation
- projection.py: imports RuntimeState, ExplicitAnswers
- safety_engine.py: imports ExplicitAnswers, SafetyEvaluation
- serialisation.py: imports RuntimeState, ClinicalOutput, AuditOutput
- engine_adapters.py: orchestration layer, may import all services above
- presentation_service.py: imports condition_registry, practice_repository

## Banned imports (design failures if violated)

- form_logic, encoder_mapping, encoder_stub, safety_engine must NOT import condition_registry
- safety_engine must NOT import RuntimeState, AnswerState, encoder_contracts
- serialisation must NOT mutate RuntimeState
- practice_repository must NOT import any service modules
- presentation_service must NOT import RuntimeState, safety_engine, encoder_*, form_logic
- form_logic, encoder_mapping, encoder_stub, safety_engine must NOT import
  practice_repository or presentation_service (clinical engine has no awareness
  of practice identity)
- admin_router must NOT import clinical engine modules, presentation_service,
  serialisation, projection, or runtime_state

## Core modules (app/core/)

Infrastructure concerns only. No clinical logic.

- persistence.py: RuntimeStateRepository, database read/write for session state
- errors.py: APIError and named error constants
- request_validation.py: validates incoming HTTP payloads
- condition_registry.py: loads and indexes condition rulesets at startup
- admin_context.py: admin authentication context

## Repository modules (app/repositories/)

Database access for persistent records. No business logic.

- practice_repository.py: practice record CRUD
- submission_repository.py: submission record creation and delivery status tracking

## Data files (data/)

- uti1.json: urinary symptoms ruleset (MVP condition)
- general.json: general condition ruleset
- Future condition rulesets go here

## Frontend: patient form (frontend/src/)

- types.ts: frontend-visible contracts only. No logic.
- api.ts: typed HTTP client functions. No business logic.
- App.tsx: React UI, stateless renderer. All intelligence lives on the server.
- ConditionCombobox.tsx: condition search and selection component
- constants.ts: shared constants used by both the patient form and the admin
  portal. Includes GENERAL_CONSULTATION_ID and SIGNPOSTING_PURIFY_CONFIG.
- search.ts: search utility

## Frontend: admin portal (frontend/admin-ui/src/)

Separate Vite entry point. Built alongside the patient form into frontend/dist/.
Served at /admin-ui/ in production by the same StaticFiles mount as the patient form.

- types.ts: admin-facing types (ConditionSummary, SaveStatus)
- api.ts: fetchConditions, fetchSignposting, putSignposting. All requests include
  a Bearer token header. No business logic.
- TokenView.tsx: token input form. Calls fetchConditions to validate the token.
- SignpostingEditor.tsx: Quill 2.0.2 rich text editor. Loads, saves, and tracks
  unsaved changes for a single condition's signposting content.
- EditorView.tsx: condition selector shell. Renders SignpostingEditor with
  key={selectedId} to force a clean remount on every condition switch.
- App.tsx: token gate. Renders TokenView until a valid token is held, then
  EditorView.
- main.tsx: entry point. Mounts App into #root.
- index.css: admin portal styles, extracted from the previous CDN-based
  admin/index.html.

## Shared frontend constants

SIGNPOSTING_PURIFY_CONFIG lives in frontend/src/constants.ts and is imported
by both frontend/src/App.tsx and frontend/admin-ui/src/SignpostingEditor.tsx.
It must match the nh3 allowlist in practice_repository.py exactly. If the
allowlist changes, update both locations:
  1. app/repositories/practice_repository.py  — nh3.clean() call
  2. frontend/src/constants.ts                — SIGNPOSTING_PURIFY_CONFIG

## Build output

The Vite build produces frontend/dist/ with two entry points:
  - frontend/dist/index.html          patient form
  - frontend/dist/admin-ui/index.html admin portal

Both are served by the StaticFiles mount at / in main.py. No separate backend
route is needed for the admin portal. Admin API endpoints remain at /admin/.

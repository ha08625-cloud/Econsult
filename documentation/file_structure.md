# FILE_STRUCTURE.md
# LLM reference: actual local directory layout and import mapping
# Last updated: 2026-03-05

## Local directory layout

```
project_root/
├── backend/
│   ├── contracts/
│   │   ├── __init__.py
│   │   ├── encoder_contracts.py    # EncoderSignalDefinition, EncoderOutput
│   │   ├── explicit_answers.py     # ExplicitAnswers
│   │   ├── runtime_state.py        # RuntimeState, AnswerState, SafetyEvaluation
│   │   └── serialisation_contracts.py  # ClinicalOutput, AuditOutput
│   │
│   ├── admin_context.py
│   ├── admin_router.py
│   ├── api_models.py
│   ├── condition_registry.py
│   ├── email_service.py
│   ├── encoder_mapping.py
│   ├── encoder_stub.py
│   ├── engine_adapters.py
│   ├── errors.py
│   ├── form_logic.py
│   ├── main.py
│   ├── persistence.py
│   ├── practice_repository.py
│   ├── presentation_service.py
│   ├── projection.py
│   ├── request_validation.py
│   ├── ruleset.py
│   ├── safety_engine.py
│   ├── serialisation.py
│   └── submission_repository.py
│
├── frontend/
│   ├── admin/
│   │   └── admin.html
│   ├── api.ts
│   ├── app.jsx
│   └── types.ts
│
├── data/
│   └── uti1.json
│
└── migrate_phase1a1.py     # one-shot migration script, run from project root
```

## Import mapping: Claude server (flat) vs local

When working in Claude's server, all files are flat in /home/claude/.
On the user's local machine, imports use the directory structure above.

Examples:
  Claude server:  from encoder_contracts import EncoderOutput
  Local machine:  from contracts.encoder_contracts import EncoderOutput

  Claude server:  from runtime_state import RuntimeState
  Local machine:  from contracts.runtime_state import RuntimeState

  Claude server:  from explicit_answers import ExplicitAnswers
  Local machine:  from contracts.explicit_answers import ExplicitAnswers

## Contract files (backend/contracts/)

These files define data structures only. They contain NO business logic, NO IO,
NO imports from non-contract modules. They are imported by engine modules but
never import engine modules.

- encoder_contracts.py: EncoderSignalDefinition, EncoderOutput
- explicit_answers.py: ExplicitAnswers (frozen, immutable projected answers for safety engine)
- runtime_state.py: RuntimeState, AnswerState, SafetyEvaluation
- serialisation_contracts.py: ClinicalOutput, AuditOutput

## Engine modules (backend/)

These contain business logic. They may import contracts but not each other's
internal state (except via defined interfaces).

Dependency rules:
- condition_registry.py may import ruleset.py utilities only (planned, not yet built)
- ruleset.py: standalone, no engine imports
- encoder_stub.py: standalone, no engine imports, returns plain dict
- encoder_mapping.py: imports RuntimeState, EncoderOutput, EncoderSignalDefinition
- form_logic.py: imports RuntimeState, AnswerState, SafetyEvaluation, ruleset_hash
- projection.py: imports RuntimeState, ExplicitAnswers
- safety_engine.py: imports ExplicitAnswers, SafetyEvaluation
- serialisation.py: imports RuntimeState, ClinicalOutput, AuditOutput
- engine_adapters.py: orchestration layer, may import all above
- main.py: HTTP layer, imports engine_adapters + persistence + api_models + errors
- practice_repository.py: standalone, no engine imports, database access only
- presentation_service.py: imports condition_registry, practice_repository
- main.py: HTTP layer, imports engine_adapters + persistence + api_models + errors + condition_registry + practice_repository + presentation_service

Banned imports (design failures if violated):
- form_logic, encoder_mapping, encoder_stub, safety_engine must NOT import condition_registry
- safety_engine must NOT import RuntimeState, AnswerState, encoder_contracts
- serialisation must NOT mutate RuntimeState
- practice_repository must NOT import any engine modules
- presentation_service must NOT import RuntimeState, safety_engine, encoder_*, form_logic
- form_logic, encoder_mapping, encoder_stub, safety_engine must NOT import practice_repository or presentation_service (clinical engine has no awareness of practice identity)

## Data files (data/)

- uti1.json: urinary symptoms ruleset (MVP condition)
- Future condition rulesets go here

## Frontend files (frontend/)

- types.ts: frontend-visible contracts only
- api.ts: HTTP client functions
- app.jsx: React UI, stateless renderer

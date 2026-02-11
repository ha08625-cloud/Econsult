# FILE_STRUCTURE.md
# LLM reference: actual local directory layout and import mapping
# Last updated: 2026-02-11

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
│   ├── api_models.py
│   ├── encoder_mapping.py
│   ├── encoder_stub.py
│   ├── engine_adapters.py
│   ├── errors.py
│   ├── form_logic.py
│   ├── main.py
│   ├── persistence.py
│   ├── pipeline.py
│   ├── projection.py
│   ├── request_validation.py
│   ├── ruleset.py
│   ├── safety_engine.py
│   └── serialisation.py
│
├── frontend/
│   ├── api.ts
│   ├── app.jsx
│   └── types.ts
│
└── data/
    └── uti1.json
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
- pipeline.py / engine_adapters.py: orchestration layer, may import all above
- main.py: HTTP layer, imports engine_adapters + persistence + api_models + errors

Banned imports (design failures if violated):
- form_logic, encoder_mapping, encoder_stub, safety_engine must NOT import condition_registry
- safety_engine must NOT import RuntimeState, AnswerState, encoder_contracts
- serialisation must NOT mutate RuntimeState

## Data files (data/)

- uti1.json: urinary symptoms ruleset (MVP condition)
- Future condition rulesets go here

## Frontend files (frontend/)

- types.ts: frontend-visible contracts only
- api.ts: HTTP client functions
- app.jsx: React UI, stateless renderer

## Files NOT yet in Claude project files

The following exist locally but have not been uploaded to Claude project files:
- backend/contracts/encoder_contracts.py (uploaded in chat on 2026-02-11)
- backend/contracts/explicit_answers.py
- backend/contracts/runtime_state.py
- backend/contracts/serialisation_contracts.py
# Core Engine

**LLM INSTRUCTIONS:** This document covers design decisions, invariants, and module boundaries for the core engine. Read the actual source files for function signatures, field names, and validation rule details.

---

## Scope

Ruleset loading, RuntimeState lifecycle, applying patient answers, orchestrating the engine pipeline. This is the deterministic functional core of the system.

**Key files:** `form_logic.py`, `runtime_state.py`, `ruleset.py`, `condition_registry.py`, `engine_adapters.py`

---

## Design Decisions & Invariants

### RuntimeState

- RuntimeState is the **full, lossless, versioned** representation of in-flight form state. It is an engineering and safety artefact, not a medical record.
- It is **append-only / versioned**. It must never be mutated in place.
- On final submission it is serialised into `ClinicalOutput` (lossy) and `AuditOutput` (lossless). Once closed, the session is read-only. Neither output contract may re-enter the engine.

### Form Initialisation Flow

Load ruleset → Initialise RuntimeState → Extract encoder definitions → Run encoder (if free text present) → Apply encoder mapping → Return canonical RuntimeState

### Form Submission Flow

Load latest RuntimeState version → Validate version consistency (optimistic concurrency) → Apply patient updates → Normalise encoder provenance → Validate completeness of required answers → Project RuntimeState → ExplicitAnswers → Evaluate safety rules → If safety triggered: block submission, return safety messages → Persist new versioned RuntimeState → Generate ClientStateView projection

Each submission produces **exactly one** new RuntimeState version and **exactly one** safety evaluation.

### Fail-Fast Validation (startup aborts)

Ruleset schema violations, duplicate `condition_id` across rulesets, missing or invalid presentation blocks, and unexpected presentation keys all abort startup. See `condition_registry.py` and `ruleset.py` for the full list. Version mismatch and submission-after-closure are runtime errors, not startup errors.

---

## Module Boundaries

### `form_logic.py` — Deterministic functional core

The pure inner core. Contains no encoder access, no IO, no serialisation, no sequencing. Can be fully unit tested in isolation. Functions initialise, hydrate, and mutate RuntimeState (patient answers and encoder provenance) and validate required-answer completeness before submission.

### `runtime_state.py` — Data contracts for in-flight state

Defines `RuntimeState`, `AnswerState`, `SafetyEvaluation`, and `AnswerSource` literals. Contains no business logic, no IO, no encoder awareness, no safety logic. Defines what state can exist, not how it is used.

### `ruleset.py` — Clinical definitions

Loads rulesets from JSON, validates schema and invariants, computes the ruleset hash, and extracts encoder definitions (answer_key + encoder_prompt pairs). Rulesets are the authoritative source; all mappings are explicit and precomputed.

### `engine_adapters.py` — Orchestration layer

The only module permitted to coordinate across engine boundaries. Defines three entry points matching the three API phases: `init_runtime_state`, `apply_update_and_evaluate`, `finish_runtime_state`.

**Critical boundary:** This module must never import `condition_registry` or any presentation metadata. The `condition_label` needed for `ClientStateView` is passed in explicitly by the HTTP layer. The clinical engine must operate as if presentation metadata does not exist.

It may import all engine modules. It must not contain clinical logic or persistence logic — those are delegated to `form_logic`/`safety_engine` and the repository layer respectively.

### `condition_registry.py` — Condition discovery

Loads all ruleset JSON files from the data directory at startup. Immutable after initialisation — no hot reload. Provides the HTTP layer with condition IDs, labels, presentation blocks, search tags, and ruleset file paths.

**What it must never expose:** questions, encoder definitions, safety rules, ruleset hashes, or raw ruleset JSON.

**Must never be imported by:** `form_logic`, `encoder_mapping`, `encoder_stub`, `safety_engine`, `projection`, or `serialisation`. If a clinical module imports `condition_registry`, that is a design failure.

The registry is the sole authority for which conditions exist. New condition JSON files require a server restart — no lazy loading.

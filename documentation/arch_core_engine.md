# Core Engine

**LLM INSTRUCTIONS:** This document covers design decisions, invariants, and module boundaries for the core engine. Read the actual source files for function signatures, field names, and validation rule details.

---

## Scope

Ruleset loading, RuntimeState lifecycle, applying patient answers, orchestrating the engine pipeline. This is the deterministic functional core of the system.

**Key files:** `form_logic.py`, `runtime_state.py`, `ruleset.py`, `condition_registry.py`, `pipeline.py`, `unit_conversion.py`

---

## Design Decisions & Invariants

### RuntimeState

- RuntimeState is the **full, lossless, versioned** representation of in-flight form state. It is an engineering and safety artefact, not a medical record.
- It is append-only / versioned at the persistence layer. Each API request loads a fresh copy from the database, mutates the in-memory working copy, then persists it as a new version row. The database history is append-only; previous versions are never overwritten. The in-memory object must not survive beyond a single request boundary.
- On final submission it is serialised into `ClinicalOutput` (lossy) and `AuditOutput` (lossless). Once closed, the session is read-only. Neither output contract may re-enter the engine.

### Form Initialisation Flow

Load ruleset → Initialise RuntimeState → Extract encoder definitions → Run encoder (if free text present) → Apply encoder mapping → Return canonical RuntimeState

### Form Submission Flow

Load latest RuntimeState version → Validate version consistency (optimistic concurrency) → Apply patient updates → Resolve quantity (unit-toggle) answers to canonical kg → Normalise encoder provenance → Validate completeness of required answers → Project RuntimeState → ExplicitAnswers → Evaluate safety rules → If safety triggered: block submission, return safety messages → Persist new versioned RuntimeState → Generate ClientStateView projection

Each submission produces **exactly one** new RuntimeState version and **exactly one** safety evaluation.

### Fail-Fast Validation (startup aborts)

Ruleset schema violations, duplicate `condition_id` across rulesets, missing or invalid presentation blocks, and unexpected presentation keys all abort startup. See `condition_registry.py` and `ruleset.py` for the full list. Version mismatch and submission-after-closure are runtime errors, not startup errors.

### Quantity answers (unit toggle)

A quantity question (`quantity: true` in the ruleset — see `arch_ruleset_schema.md`) lets the patient enter a value in metric or imperial. The core resolves both to a single canonical unit, **kilograms**, so nothing downstream (safety, projection, clinical output, delivery) has to know a unit was ever chosen.

- **Canonical value vs. lossless raw input.** `convert_unit_answers` writes the canonical kg value to `AnswerState.value` and preserves the patient's exact input in `AnswerState.raw_components` (kg as a string, or whole stones/pounds as ints). The canonical value therefore does not need to be lossless — `raw_components` is the audit-grade record — which is what lets imperial be rounded (see below) without losing information. The chosen system is recorded once per form in `RuntimeState.unit_system`.
- **Metric rejects, imperial rounds.** For metric the patient typed kilograms directly, so over-precision is a genuine input error and is rejected via the shared number-acceptance ladder. For imperial the exact conversion (stones+pounds → kg) is a long artifact, so it is rounded HALF_UP to the question's `decimal_places`. Consequence: the canonical value is always already at `decimal_places` for both systems, so `validate_required_answers` needs no unit-specific branch, and the PDF's displayed kg matches the stored/structured kg (no divergence).
- **Pipeline placement.** `convert_unit_answers` runs after `apply_patient_answers` (which places the transient client `{system, components}` dict in `value`) and before both `validate_required_answers` (which would otherwise reject a dict) and `normalise_number_answers` (which stringifies the Decimal it leaves). It never touches encoder provenance: a Number question is never `send_to_encoder`.
- **Deferred.** Cross-question unit consistency and a second quantity kind are out of scope until a second quantity question exists; the client toggle is form-wide and seeds from the first quantity question.

---

## Module Boundaries

### `form_logic.py` — Deterministic functional core

The pure inner core. Contains no encoder access, no IO, no serialisation, no sequencing. Can be fully unit tested in isolation. Functions initialise and mutate RuntimeState (patient answers and encoder provenance) and validate required-answer completeness before submission.

### `runtime_state.py` — Data contracts for in-flight state

Defines `RuntimeState`, `AnswerState`, `SafetyEvaluation`, and `AnswerSource` literals. Contains no business logic, no IO, no encoder awareness, no safety logic. Defines what state can exist, not how it is used.

### `unit_conversion.py` — Pure unit arithmetic

Stones/pounds → kilograms conversion only. Knows nothing about RuntimeState, rulesets, or the domain's `AnswerValidationError`; it raises plain `ValueError` on invalid components and does no rounding. Callers (`form_logic.convert_unit_answers`) translate its errors and apply rounding. Fully unit-testable in isolation.

### `ruleset.py` — Clinical definitions

Loads rulesets from JSON, validates schema and invariants, computes the ruleset hash, and extracts encoder definitions (answer_key + encoder_prompt pairs). Rulesets are the authoritative source; all mappings are explicit and precomputed.

### `pipeline.py` — Orchestration layer

The only module permitted to coordinate across engine boundaries. Defines three entry points matching the three API phases: `init_runtime_state`, `apply_update_and_evaluate`, `finish_runtime_state`.

**Critical boundary:** This module must never import `condition_registry` or any presentation metadata. The `condition_label` needed for `ClientStateView` is passed in explicitly by the HTTP layer. The clinical engine must operate as if presentation metadata does not exist.

It may import all engine modules. It must not contain clinical logic or persistence logic — those are delegated to `form_logic`/`safety_engine` and the repository layer respectively.

### `condition_registry.py` — Condition discovery

Loads all ruleset JSON files from the data directory at startup. Immutable after initialisation — no hot reload. Provides the HTTP layer with condition IDs, labels, presentation blocks, search tags, and ruleset file paths.

**What it must never expose:** questions, encoder definitions, safety rules, ruleset hashes, or raw ruleset JSON.

**Must never be imported by:** `form_logic`, `encoder_mapping`, `encoder_stub`, `safety_engine`, `projection`, or `serialisation`. If a clinical module imports `condition_registry`, that is a design failure.

The registry is the sole authority for which conditions exist. New condition JSON files require a server restart — no lazy loading.
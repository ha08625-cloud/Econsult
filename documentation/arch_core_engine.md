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

A quantity question (`quantity: true` in the ruleset — see `arch_ruleset_schema.md`) lets the patient enter a value in one of several unit systems, chosen from that question's `quantity_kind`. The core resolves the patient's input to that kind's own canonical unit — **kilograms for weight**, not universally kilograms — so nothing downstream (safety, projection, clinical output, delivery) has to know which system was chosen or which kind was involved.

- **Canonical value vs. lossless raw input.** `convert_unit_answers` writes the canonical value to `AnswerState.value` and preserves the patient's exact input in `AnswerState.raw_components` (the canonical unit as a string, or the non-canonical system's whole components as ints). The canonical value therefore does not need to be lossless — `raw_components` is the audit-grade record — which is what lets a non-canonical system be rounded (see below) without losing information. The chosen system is recorded **per answer**, in `AnswerState.unit_system`, not once per form. This is a deliberate change from an earlier design that used a form-level `RuntimeState.unit_system`: the system is a property of an individual answer, and the inbound wire shape (`QuantityAnswerPayload`) was already per-answer, so storage now matches the contract that already existed at the boundary.
- **Canonical system rejects, non-canonical systems round.** When the patient's chosen system is the kind's canonical system, they typed the canonical unit directly, so over-precision is a genuine input error and is rejected via the shared number-acceptance ladder. For a non-canonical system, the exact conversion (e.g. stones+pounds → kg) is a long artifact, so it is rounded HALF_UP to the question's `decimal_places`. Consequence: the canonical value is always already at `decimal_places` regardless of which system was used, so `validate_required_answers` needs no unit-specific branch, and the PDF's displayed canonical value matches the stored/structured value (no divergence).
- **Pipeline placement.** `convert_unit_answers` runs after `apply_patient_answers` (which places the transient client `{system, components}` dict in `value`) and before both `validate_required_answers` (which would otherwise reject a dict) and `normalise_number_answers` (which stringifies the Decimal it leaves). It never touches encoder provenance: a Number question is never `send_to_encoder`.
- **Cross-question unit consistency is deliberately not enforced at runtime.** Because the system lives on the answer rather than the form, there is no runtime check that two quantity answers on the same submission used the same system. A mixed-unit submission from a direct API client (not the patient-facing form, which only ever offers one shared system per the ruleset's shared-toggle authoring check — see `arch_ruleset_schema.md`) converts each answer correctly against its own `quantity_kind` and system, records accurately, and renders faithfully on the PDF. It is a readability oddity for that specific submission, not a defect, and this is an accepted consequence rather than a gap to close.
- **Extension seam.** Adding a new quantity kind means adding it to `ruleset.QUANTITY_KINDS` (canonical system, ordered component keys per system) with a matching entry in `form_logic._NON_CANONICAL_CONVERTERS` and `pdf_formatter._QUANTITY_FORMATTERS`. `test_wiring.py` asserts these three tables agree — see `arch_testing.md`. Compound quantity kinds (e.g. blood pressure, which needs more than one canonical component and per-component bounds) do not fit this seam: `AnswerState.value` holds a single scalar, so a compound kind needs a separate mechanism, not a registry entry.

---

## Module Boundaries

### `form_logic.py` — Deterministic functional core

The pure inner core. Contains no encoder access, no IO, no serialisation, no sequencing. Can be fully unit tested in isolation. Functions initialise and mutate RuntimeState (patient answers and encoder provenance) and validate required-answer completeness before submission.

### `runtime_state.py` — Data contracts for in-flight state

Defines `RuntimeState`, `AnswerState`, `SafetyEvaluation`, and `AnswerSource` literals. Contains no business logic, no IO, no encoder awareness, no safety logic. Defines what state can exist, not how it is used.

### `unit_conversion.py` — Pure unit arithmetic

Holds only the arithmetic for converting a non-canonical system's components to a kind's canonical unit (today: stones/pounds → kilograms). Knows nothing about RuntimeState, rulesets, or the domain's `AnswerValidationError`; it raises plain `ValueError` on invalid components and does no rounding. Per-`quantity_kind` dispatch lives in `form_logic._NON_CANONICAL_CONVERTERS`, keyed by `(quantity_kind, system)`; this module is not kind-aware itself. Callers (`form_logic.convert_unit_answers`) translate its errors and apply rounding. Fully unit-testable in isolation. A new quantity kind adds its conversion function(s) here and registers them in `form_logic`'s dispatch table.

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
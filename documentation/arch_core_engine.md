# Core Data Flows

## Form Initialisation Flow:
* Load ruleset
* Initialise RuntimeState
* Extract encoder definitions and mappings
* Run encoder (if free text present)
* Apply encoder mapping
* Return canonical RuntimeState

## Form Submission Flow:
* Load the latest RuntimeState version for the session
* Validate version consistency (optimistic concurrency)
* Apply patient updates
* Normalise encoder provenance
* Validate completeness of required answers
* Project RuntimeState → ExplicitAnswers
* Evaluate safety rules using the safety engine
* If any safety rules are triggered: Submission is blocked, and Safety messages are returned.
* Persist a new, versioned RuntimeState
* Generate ClientStateView projection
* Constraint: Each submission produces exactly one new RuntimeState version and exactly one safety evaluation.

# Modules:

## form_logic.py — Deterministic functional core

Responsibilities:
* Initialise runtime state (including answer_type from ruleset)
* Hydrate runtime state on return
* Apply patient answers (dict of answer_key → value)
* Normalise encoder provenance on submit
* Validate required answers are complete before submission

Rules:
* No encoder access
* No IO
* No serialization
* No sequencing

Function names:
* initialise_runtime_state(ruleset, free_text) → RuntimeState
* hydrate_runtime_state(incoming, ruleset) → RuntimeState
* apply_patient_answers(runtime, answers_dict) → None (mutates)
* normalise_encoder_provenance(runtime) → None (mutates)
* validate_required_answers(runtime) → None (raises ValueError)

## runtime_state.py — Canonical runtime data contracts

Defines the shape of all in‑flight state.

Contains:
* RuntimeState
* AnswerState
* SafetyEvaluation
* AnswerSource literals

Properties:
* No business logic
* No IO
* No encoder awareness
* No safety logic

This module defines what state can exist, not how it is used.

## ruleset.py — Clinical definitions and extraction metadata

Responsibilities:
* Load rulesets from JSON
* Validate schema and invariants
* Compute ruleset hash
* Extracts encoder definitions (encoder-facing contract): answer_key + encoder_prompt pairs

Rules:
* Rulesets are authoritative
* Encoder metadata lives in the ruleset
* All mappings are explicit and precomputed

## engine_adapters.py — Orchestration layer

Responsibilities:
* Wire together: ruleset loading, encoder, form logic, projection,
  safety evaluation, and serialisation
* Define three entry points matching the API endpoints:
  * init_runtime_state — form initialisation + encoder
  * apply_update_and_evaluate — patient answers + safety
  * finish_runtime_state — clinical/audit output + submission ID
* Coordinate safety evaluation and submission blocking based on safety output

Rules:
* No clinical logic (delegates to form_logic, safety_engine)
* No persistence logic (delegated to main.py + repository layer)
* No condition discovery (condition_label passed in by HTTP layer)
* May import all engine modules
* Must not import condition_registry

Architectural guarantee:
This module never imports or accesses condition_registry or presentation
metadata. The condition_label needed for ClientStateView is passed in
explicitly by the HTTP layer. The clinical engine operates exactly as
if presentation metadata never existed.

## condition_registry.py — Condition discovery and presentation

Responsibilities:
* Load all ruleset JSON files from the data directory at startup
* Validate presence and correctness of presentation blocks
* Extract and retain: condition_id, presentation.label, full presentation block,
  search_tags, and absolute ruleset file path
* Provide lookup methods for the HTTP layer

Public interface:
* list_conditions() → list of {id, label, search_tags}
* get_presentation(condition_id) → presentation dict
* get_ruleset_path(condition_id) → absolute file path
* has_condition(condition_id) → bool

Properties:
* Initialised once at application startup
* Immutable after initialisation
* Any validation failure aborts startup (fail-fast)
* No hot reload, no lazy loading
* Only imports stdlib (os, json, typing, logging)

This module must never:
* Expose questions, encoder definitions, safety rules, or ruleset hashes
* Return raw ruleset JSON
* Be imported by form_logic, encoder_mapping, encoder_stub, safety_engine,
  projection, or serialisation

If a clinical module imports condition_registry, that is a design failure.

Validation rules (fail-fast at startup):
* presentation block must exist
* presentation.label must be a non-empty string
* presentation.free_text_prompt must be a string if present
* presentation.search_tags must be a list if present
* Each search tag must be a non-empty string after stripping whitespace
* Each search tag must not exceed SEARCH_TAGS_MAX_TAG_LENGTH (60) characters
* Total search tags must not exceed SEARCH_TAGS_MAX_COUNT (20) per condition
* Case-insensitive duplicate tags are silently removed with a logged warning;
  first occurrence is kept
* No unexpected keys in presentation (allow-list: label, free_text_prompt,
  search_tags)
* No duplicate condition_id across rulesets
* Data directory must exist and contain at least one JSON file

Constants (named, not magic numbers):
* SEARCH_TAGS_MAX_COUNT = 20
* SEARCH_TAGS_MAX_TAG_LENGTH = 60

Note: pre_form_information is no longer supported in presentation blocks.
Practice-specific signposting is handled by presentation_service.py using
data from practice_repository.py. Universal safety warnings are defined
as constants in presentation_service.py.

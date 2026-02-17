# Architecture Decisions – Stage 1 (Form Engine MVP)

## Purpose

This document captures the architectural decisions for the initial stage of the Econsult project. Its goal is to lock constraints, responsibilities, and data boundaries early, so that later additions (encoders, more conditions, UX refinement) do not destabilise safety, auditability, or correctness.

Stage 1 aims to deliver a **server-driven, schema-defined form engine** with no ML dependency.

---

## 1. Project level invariants

* Clinical meaning lives only in declarative rulesets (JSON data files, not code)
* The engine interprets rulesets deterministically (functional core)
* The UI renders engine output (imperative shell)
* Encoder models output signals, they do not make decisions
* Safety netting advice comes from determinstically coded rules in the ruleset (simple IF/AND/OR logic)
* Patient answers can over-write encoder-filled answers, encoder-filled answers must never over-write patient answers

This keeps responsibility separate and well defined
Clinical rules are plug-and-play: easily changed without writing new code

---

## 2. High-Level Architecture
The system is structured as a server-owned, session-backed pipeline composed of strictly separated modules.
Request
↓
HTTP Boundary (validation + versioning)
↓
Pipeline (ordering only)
↓
Form Logic (deterministic core)
↓
Serialization (clinical / audit views)
↓
Persistence (versioned RuntimeState)
No module other than the pipeline is aware of execution order.
No module other than the persistence layer is aware of storage.
The RuntimeState is canonical, backend-owned, lossless, and versioned.
Clients interact only via constrained projections and intent-only inputs.

---

## 3. Module responsibilities

### 3.1 runtime_state.py — Canonical runtime data contracts

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

### 3.2 ruleset.py — Clinical definitions and extraction metadata

Responsibilities:
* Load rulesets from JSON
* Validate schema and invariants
* Compute ruleset hash
* Extracts encoder definitions (encoder-facing contract): answer_key + encoder_prompt pairs

Rules:
* Rulesets are authoritative
* Encoder metadata lives in the ruleset
* All mappings are explicit and precomputed

### 3.3 encoder_stub.py — Replaceable encoder façade

Responsibilities:
* Accept free text + encoder definitions
* Emit {answer_key: true | false | null}

Constraints:
* Encoder never sees rules, questions or answers, RuntimeState
* Encoder output is non‑authoritative
* Stub logic is intentionally naive
* This module is expected to be deleted and replaced by a real encoder without impacting any other module.

### 3.4 encoder_mapping.py — Encoder containment layer

Responsibilities:
* Apply encoder output to RuntimeState
* Enforce provenance rules
* Preserve raw encoder output for audit

Rules:

* Encoder never overwrites patient input
* Encoder only populates unanswered fields
* Mapping failures are fatal
* Encoder influence is fully contained in this module

This is the regulatory boundary between inference and clinical data.

### 3.5 form_logic.py — Deterministic functional core

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

### 3.6 serialization.py — Output views

Responsibilities:
* Produce ClientStateView (for frontend rendering)
* Produce ClinicalOutput (lossy, portable)
* Produce AuditOutput (lossless, for debugging and regulation)

Functions:
* serialize_client_state(runtime, ruleset, condition_label) → dict
* clinical_output(runtime) → ClinicalOutput
* audit_output(runtime) → AuditOutput

Dependencies:
* runtime_state.py (RuntimeState)
* serialisation_contracts.py (ClinicalOutput, AuditOutput)

Rules:
* Serialisation never mutates state
* Clinical output excludes encoder internals
* condition_label is passed in explicitly by the calling layer;
  this function never accesses presentation metadata from the ruleset
* RuntimeState must never be mutated or destroyed by serialisation,
  only read and projected

Architectural guarantee:
This module never accesses presentation metadata directly.
The condition_label for ClientStateView is passed in explicitly
by the calling layer. The ruleset parameter is used only for
question text and answer_type, never for presentation data.

### 3.7 engine_adapters.py — Orchestration layer

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

### 3.8 explicit_answers.py — Safety-critical answer projection

Responsibilities:
* Define the only data structure that safety and other post-submit rule engines may consume
* Enforce immutability of projected answers
* Remove all provenance, encoder metadata, and RuntimeState access

Properties:
* Input is a projection of RuntimeState, not RuntimeState itself
* Answers are immutable (frozen dataclass)
* Answer values may be True, False, or None
* None represents unknown, not False

### 3.9 projection.py — Explicit answer projection boundary

Responsibilities:
* Project RuntimeState → ExplicitAnswers
* Apply strict allow-list provenance rules
* Act as the single choke point where encoder influence is excluded from safety

Rules:
* Only answers with source ∈ {patient, encoder_confirmed} are included
* All other answers are treated as unanswered (None), even if a value exists
* Projection is deterministic and total (all answer_keys always present)

### 3.10 safety_engine.py

Responsibilities:
* Evaluate safety-critical clinical rules defined in the ruleset
* Consume explicit answers only (post-projection)
* Return structured safety outcomes (rule IDs + message text)

Inputs:
* ExplicitAnswers (immutable, projected view)
* Safety rule definitions from the ruleset

Outputs:
* SafetyEvaluation containing:
* Triggered rule IDs
* Corresponding safety message payloads

Properties:
* Pure function: no mutation, no IO, no side effects
* Deterministic and fully inspectable
* Unit-testable in complete isolation

Has no access to:
* RuntimeState
* AnswerState
* Answer provenance
* Encoder output or metadata
* Submission or blocking logic

Rules:
* None represents unknown and never satisfies a condition
* Safety rules are evaluated using explicit boolean logic only
* The safety engine never blocks submission directly
* Blocking decisions are enforced exclusively by the pipeline based on safety output

Non-goals:
* No advisory or informational guidance
* No UI behaviour
* No conditional workflows
* No mutation of answers or state

### 3.11 serialisation_contracts.py

Defines the explicit, immutable data structures that may leave the core
form engine as serialized outputs.

These contracts enforce a hard boundary between:
* Internal runtime state (lossless, mutable, provenance-aware)
* External outputs (lossy or lossless, immutable, purpose-specific)
* This module contains *no logic* and *no knowledge* of RuntimeState internals.
* It exists to make output schemas explicit, inspectable, and enforceable.

Key principles:
* ClinicalOutput is lossy by design and safe for clinical and patient use
* AuditOutput is lossless and intended for debugging, safety review, and regulation
* Neither contract may be used as an input back into the engine

### 3.12 condition_registry.py — Condition discovery and presentation

Responsibilities:
* Load all ruleset JSON files from the data directory at startup
* Validate presence and correctness of presentation blocks
* Extract and retain: condition_id, presentation.label, full presentation block,
  and absolute ruleset file path
* Provide lookup methods for the HTTP layer

Public interface:
* list_conditions() → list of {id, label}
* get_presentation(condition_id) → presentation dict
* get_ruleset_path(condition_id) → absolute file path
* has_condition(condition_id) → bool

Properties:
* Initialised once at application startup
* Immutable after initialisation
* Any validation failure aborts startup (fail-fast)
* No hot reload, no lazy loading
* Only imports stdlib (os, json, typing)

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
* No unexpected keys in presentation (allow-list: label, free_text_prompt)
* No duplicate condition_id across rulesets
* Data directory must exist and contain at least one JSON file

Note: pre_form_information is no longer supported in presentation blocks.
Practice-specific signposting is handled by presentation_service.py using
data from practice_repository.py. Universal safety warnings are defined
as constants in presentation_service.py.

---

## 3.13 main.py — HTTP layer

Responsibilities:
* Provide the FastAPI application and endpoint definitions
* Wire together: condition_registry, engine_adapters, persistence, request_validation,
  practice_repository, presentation_service
* Translate between HTTP requests and engine entry points
* Map condition_id to ruleset_path and condition_label via the registry

Endpoints:
* GET /conditions — list all conditions (from registry)
* GET /conditions/{condition_id}/presentation — patient-facing presentation
  (from presentation_service, accepts optional ?practice= query parameter)
* POST /form/init — create session (validates condition, calls engine_adapters.init_runtime_state)
* POST /form/update — apply patient answers (calls engine_adapters.apply_update_and_evaluate)
* POST /form/finish — close session (calls engine_adapters.finish_runtime_state)

Rules:
* No clinical logic
* No safety rule evaluation
* No encoder invocation
* Request validation via request_validation.py (not Pydantic models)
* Uses Request.json() for payload parsing
* condition_label is resolved from the registry and passed explicitly to
  engine_adapters; presentation metadata never enters the engine

Startup:
* Initialises ConditionRegistry from DATA_DIR environment variable (default: "data")
* Initialises RuntimeStateRepository (SQLite)
* Initialises PracticeRepository (same SQLite database)
* Initialises PresentationService (composes registry + practice data)
* All must succeed or the process fails to start

---

## 3.14 encoder_contracts.py — Encoder boundary contracts

Defines the only data structures permitted to cross the boundary between
an encoder implementation (stub or ML-backed) and the rest of the form engine.

Contains:
* EncoderSignalDefinition (frozen dataclass): answer_key + encoder_prompt
* EncoderOutput (frozen dataclass): model_name, model_version, ruleset_hash,
  signals dict {answer_key: True | False | None}

EncoderOutput.validate_against(definitions):
* Validates that output keys exactly match the provided definitions
* Validates that all values are True, False, or None
* Raises ValueError/TypeError on mismatch

Properties:
* Both dataclasses are frozen (immutable)
* No business logic beyond validation
* No imports from engine modules
* Imported by encoder_mapping.py and engine_adapters.py only

---

## Section 3.15 practice_repository.py — Practice data access

Database access for practice identity and practice-specific configuration.
Handles the practices and practice_signposting tables.

Responsibilities:
* Initialise practice-related tables on startup
* CRUD operations for practices
* CRUD operations for practice signposting
* JSON validation for signposting content

Public interface:
* create_practice(practice_id, name) → None
* get_practice(practice_id) → dict | None
* practice_exists(practice_id) → bool
* get_signposting(practice_id, condition_id) → list[str] | None
* set_signposting(practice_id, condition_id, items) → None
* delete_signposting(practice_id, condition_id) → None

Database schema:
* practices: practice_id (PK), name, created_at
* practice_signposting: practice_id + condition_id (composite PK), signposting_json, updated_at

Validation rules:
* signposting_json must be a valid JSON array
* Each item must be a non-empty string
* Empty array is allowed (explicit "no signposting")

Behaviour:
* get_signposting returns None if no row exists (not configured)
* get_signposting returns [] if row exists with empty array
* get_signposting gracefully handles malformed JSON (logs warning, returns None)

This module must never:
* Access clinical data (rulesets, RuntimeState, answers)
* Perform composition logic (that belongs in presentation_service)
* Handle authentication (that belongs in practice_context, Phase 1B)

---

## Section 3.16 presentation_service.py — Patient-facing presentation composition

Composes patient-facing presentation from multiple sources:
* Universal safety warning (constant)
* Practice-specific signposting (database)
* Condition-specific presentation (condition_registry)

Responsibilities:
* Define the universal safety warning constant
* Compose the complete patient-facing presentation
* Provide a single access point for all presentation data

Public interface:
* UNIVERSAL_SAFETY_WARNING: str (module-level constant)
* PresentationService.get_patient_presentation(condition_id, practice_id=None) → dict

Return structure:
```python
{
    "label": str,                           # From condition_registry
    "free_text_prompt": str | None,         # From condition_registry  
    "universal_safety_warning": str,        # Constant
    "practice_signposting": list[str] | None,  # From practice_repository
}
```

Behaviour:
* If practice_id is None, practice_signposting is None
* If practice_id is provided but no signposting configured, practice_signposting is None
* If signposting is configured, practice_signposting is the list of strings
* Empty list from database is returned as None (nothing to display)
* Raises ConditionNotFound if condition_id does not exist (passthrough from registry)

Architectural note:
This module performs COMPOSITION, not MERGING. Each data source populates a
distinct field in the output. There is no field-level override logic — practice
data and condition data occupy separate slots.

This module must never:
* Access clinical data (rulesets, RuntimeState, answers, safety rules)
* Modify any data (read-only composition)
* Handle authentication (that belongs in practice_context, Phase 1B)

## 3.17 Frontend modules

The frontend is a stateless renderer. It contains no clinical logic,
no branching decisions, and no safety evaluation. All intelligence
lives on the server.

### 3.17.1 types.ts — Frontend-visible contracts

Defines TypeScript interfaces for all data the frontend may receive or send.

Contains:
* ClientQuestion — individual question with current value and suggested flag
* ClientStateView — full form state for rendering
* ClientAnswerReturn — payload sent back on update (runtime_id, base_version, answers)
* SafetyMessage — rule_id + message text
* ConditionSummary — id + label for condition list
* ConditionPresentation — label, free_text_prompt, universal_safety_warning, practice_signposting

Rules:
* No clinical logic
* No encoder awareness
* No safety evaluation
* These types are projections of server-side state, not mirrors of it

### 3.17.2 api.ts — HTTP client

Provides typed fetch wrappers for all backend endpoints.

Functions:
* getConditions() — GET /conditions
* getConditionPresentation(conditionId) — GET /conditions/{id}/presentation
* initForm(conditionId, freeText) — POST /form/init
* updateForm(payload) — POST /form/update
* finishForm(runtimeId, version) — POST /form/finish

Rules:
* No business logic
* No data transformation beyond JSON serialisation
* Payload field names must match backend expectations exactly
  (e.g. condition_id, free_text, runtime_id, base_version)

### 3.17.3 app.jsx — React UI

Stateless renderer implementing a five-screen flow:

* Screen 0 (SELECT_CONDITION): fetches GET /conditions, renders dropdown
* Screen 1 (FREE_TEXT): fetches GET /conditions/{id}/presentation,
  renders framing text + free text input, submits to POST /form/init
* Screen 2 (EDIT): renders questions from ClientStateView, collects answers,
  submits to POST /form/update
* Screen 3 (REVIEW): displays answers + safety messages,
  submits to POST /form/finish or returns to EDIT
* Screen 4 (DONE): confirmation

Rules:
* No clinical logic
* No branching based on answer values
* No hidden questions
* No local safety evaluation
* All rendering driven by server-provided ClientStateView
* Session begins at POST /form/init (Screen 1 → Screen 2 transition)
* Screens 0 and 1 are pre-session (no runtime_id exists)
* Fatal errors reset all state and return to Screen 0

State management:
* Pre-session state: selectedConditionId, presentation, freeText
* Session state: runtimeId, version, clientState, editableAnswers, safetyMessages
* Pre-session state is discarded after /form/init succeeds
* Session state is never round-tripped back to pre-session screens

## 4. Data flow

### 4.1 Form initialisation

Load ruleset
Initialise RuntimeState
Extract encoder definitions and mappings
Run encoder (if free text present)
Apply encoder mapping
Return canonical RuntimeState

### 4.2 Form submission
Load the latest RuntimeState version for the session
Validate version consistency (optimistic concurrency)
Apply patient updates
Normalise encoder provenance
Validate completeness of required answers
Project RuntimeState → ExplicitAnswers
Evaluate safety rules using the safety engine
If any safety rules are triggered:
Submission is blocked
Safety messages are returned
Persist a new, versioned RuntimeState
Generate ClientStateView projection
Each submission produces exactly one new RuntimeState version and exactly one safety evaluation.

## 5. Encoder logic

Encoders:
* Run once on initial free text
* Output partial {answer_key: true|false|null} map
* Do not see questions
* Use `encoder_prompt` as a clinical definition, not an instruction

Encoder output:
* Is clearly marked as suggested
* Can be overridden
* Are advisory and non-authoritative
* Are frozen at extraction time and may be confirmed or corrected by the patient
* On submission, any remaining encoder-derived values are treated as explicitly confirmed or explicitly corrected
* Encoder provenance is retained for audit and debugging only and is never exposed to safety logic or clinical outputs

Allowed answer sources:
unanswered
encoder
encoder_confirmed
encoder_corrected
patient

Allowed transitions:
From	To	Allowed
unanswered	encoder	yes
unanswered	patient	yes
encoder	encoder_confirmed	yes
encoder	encoder_corrected	yes
encoder_confirmed	encoder_corrected	yes
patient	encoder	no
patient	encoder_confirmed	no

Encoders may only ever produce encoder.

## 6. Safety architecture (blocking, isolated)

Safety rules live in the ruleset.
Safety evaluation is performed by a dedicated safety engine that:
Consumes explicit answers only
Never sees RuntimeState, AnswerState, provenance, or encoder output
Operates on an immutable input structure
Is deterministic, inspectable, and unit-testable in isolation

### 6.1 Explicit answer semantics

Safety consumes an ExplicitAnswers structure with the following semantics:
True / False → explicitly answered
None → unknown / unanswered
(None is never treated as False)
Encoder-derived answers (encoder) are never visible to safety.
Encoder-confirmed answers (encoder_confirmed) are treated as explicit only after submission normalisation.

### 6.2 Safety engine responsibilities

The safety engine:
* Evaluates safety rules against explicit answers
* Returns structured safety outcomes (rule IDs + message text)
* Does not decide whether submission is allowed
* Blocking behaviour is enforced only by the pipeline, based on safety output.

### 6.3 Blocking semantics

For the MVP:
* Any triggered safety rule blocks form submission
* The patient is prevented from submitting until answers are changed
* Blocking is explicit and transparent to the patient
* This is a medically defensible design choice and prevents unsafe overnight submissions.

## 7. State

It is a session-backed, server-owned system with RuntimeState persistence.
There is:
No conversational memory
No cross-session state
No per-user identity
No hidden workflow
A session is defined as a server-owned, versioned RuntimeState identified by a runtime_id.

### 7.1 Canonical RuntimeState (lossless, backend-owned)
Purpose:
Represent the full, lossless state of a form at a specific point in time
Support auditability, safety review, and deterministic replay
Enable strict versioned updates and conflict detection
Properties:
Backend-owned
Append-only or versioned
Never round-tripped through the client
Never mutated in place
Short-lived and retention-limited
Engineering and safety artefact, not a medical record
RuntimeState is persisted server-side for the lifetime of the session and is collapsed into outputs on final submission.

### 7.2 Output states (post-submission)
On successful final submission:
RuntimeState is serialized into:
ClinicalOutput (lossy, portable)
AuditOutput (lossless, inspectable)
The session is closed and becomes read-only
No further RuntimeState access is required
ClinicalOutput:
Intended for clinician and patient use
Excludes encoder internals, provenance, and rule traces
AuditOutput:
Retains full provenance and evaluation history
Intended for debugging, safety review, and regulation
Never re-enters the engine

## 8. Clinical ruleset structure

{
"question_id": "urinary_symptoms_1",    # unique identifier
"question": "Are you experiencing pain when passing urine?",    # patient-facing question
"answer_key": "dysuria_present",    # unique label used only for condition logic (could use question_id but more brittle if someone re-orders questions)
"answer_type": "Boolean",    # for encoder must be true, false, or unanswered
"send_to_encoder": true,
"encoder_prompt": "Does the response indicate there is pain when passing urine?"    # prompt for encoder
},
{
"question_id": "urinary_symptoms_2",
"question": "Have you felt like you have had a fever during this episode?",
"answer_key": "fever_present",
"answer_type": "Boolean",
"send_to_encoder": true,
"encoder_prompt": "Does the response indicate there is fever in this episode?"
},
{
"question_id": "urinary_symptoms_3",
"question": "When did the symptoms start?",
"answer_key": "symptom_onset_text",
"answer_type": "text",
"send_to_encoder": false,    # can only be answered by patient not pre-filled by encoder
"encoder_prompt": null
}

**Key decisions**
* This is a form filling engine, not an AI conversation agent
* Some questions can't be extracted easily by encoders e.g. When did the symptoms start?
* More than one question to a signal invites complexities around contradiction detection and resolution
* The only source of information is the patient - signals can be derived from encoders reading free text or direct input from the patient.  Information from other sources, e.g. EHRs, is not within the scope of this project
* Therefore there is no reason to have a signal_id separate from a question_id - the encoder is a helper to speed up a certain subset of questions, not its own class of information
* The question and the encoder prompt are different wordings of the SAME clinical concept optimised for different consumers (one human, one ML) - if one changes, the other MUST be reviewed or they may diverge dangerously

---

## 9. Validation and Failure Semantics

Rulesets are validated at load time.
Fail‑fast, fail-loud conditions include:
* Safety rule referencing absent or invalid answer_key
* Duplicate or unstable IDs
* Duplicate or unstable answer_keys
* Invalid rule expressions
* If send_to_encoder = true, then encoder_prompt must not be null and answer_type must be Boolean
* Safety engine receiving anything other than ExplicitAnswers
* Safety evaluation attempted before projection
* Projection omitting any answer_key
* Safety rules referencing keys absent from projected answers
* Client submission of any RuntimeState or projection data
* Version mismatch on update or finish
* Submission attempt after session closure
* Ruleset hash mismatch between session and current ruleset
* Incomplete required answers on submission
* Missing or invalid presentation block in ruleset → startup abort
* Duplicate condition_id across rulesets → startup abort
* Presentation containing unexpected keys → startup abort

---

## 10. Visibility Semantics

* All questions are shown after free text and encoder run
* No questions are suppressed or hidden

However:
* Visibility rules are still part of the engine design
* Future versions may activate them without refactor
* Explicit answers persist even if visibility changes later.

---

## 11. Scope of current stage

* Multi-condition support via condition_registry
* All questions visible
* One safety message (fever=true => speak to doctor immediately) which is evaluated after submission only
* Safety message blocks final submission
* No ML dependency
* Practice-specific signposting via presentation_service (Phase 1A complete)
* Practice identity via practice_repository (Phase 1A complete)
* Practice authentication deferred to Phase 1B


## Section 12 — Practice Configuration Architecture

### 12.1 Design principles

* Composition, not merging — Practice-specific content occupies a distinct slot,
  never overwrites or merges with clinical content
* Clinical engine untouched — All practice configuration is handled in the
  presentation layer; form_logic, safety_engine, encoder_mapping etc. remain
  unaware of practice identity
* Condition registry remains immutable — Practice-specific data is fetched at
  request time from the database, not baked into startup state
* Graceful degradation — Missing signposting means "show nothing", not "crash"
* Narrow scope — Practices can only configure signposting, not safety warnings,
  labels, or clinical content

### 12.2 Information architecture

Three distinct types of pre-form information, each with clear ownership:

| Type | Example | Ownership | Storage |
|------|---------|-----------|---------|
| Universal Safety Warning | "Call 999 if chest pain..." | Centralised, immutable | Config constant |
| Practice Signposting | "Self-refer to physio: 0800..." | Practice-specific, editable | Database |
| Form Context | "Tell us about your symptoms" | Centralised, per-condition | Ruleset JSON |

### 12.3 Data flow

1. Patient accesses form with optional ?practice= parameter
2. GET /conditions/{id}/presentation called
3. presentation_service composes response:
   a. Fetches condition presentation from registry (immutable, in-memory)
   b. Fetches practice signposting from database (if practice_id provided)
   c. Adds universal safety warning constant
   d. Returns composed dict
4. Frontend renders all three information types in distinct UI sections

### 12.4 Future phases

Phase 1B — Practice authentication:
* practice_tokens table
* practice_context.py for token validation
* Token-based access to admin endpoints

Phase 2 — Admin endpoints:
* CRUD endpoints for practice signposting
* JSON validation for signposting content

Phase 3 — Admin frontend:
* Login page (token-based for MVP)
* Signposting editor per condition

Phase 4 — Audit trail:
* Audit log table
* Automatic logging of signposting changes

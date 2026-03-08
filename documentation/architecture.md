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
- Internal runtime state (lossless, mutable, provenance-aware)
- External outputs (lossy or lossless, immutable, purpose-specific)

This module contains no logic and no knowledge of RuntimeState internals.
It exists to make output schemas explicit, inspectable, and enforceable.

Key principles:
- ClinicalOutput is lossy by design and safe for clinical and patient use
- AuditOutput is lossless and intended for debugging, safety review, and regulation
- Neither contract may be used as an input back into the engine

ClinicalOutput fields:
- condition_id: str
- free_text: str
- answers: Dict[str, Any] — answer values only, no provenance
- safety_messages: List[dict]
- question_labels: Dict[str, str] — answer_key to question text at submission time

question_labels is populated by serialisation.py from the ruleset at submission
time. Storing it in ClinicalOutput means the record is self-contained: a future
reader can interpret answers without reloading the ruleset. If the question text
ever changes, historical submissions still reflect the wording that was shown to
the patient.

### 3.12 condition_registry.py — Condition discovery and presentation

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

---

### 3.13 main.py — HTTP layer

Responsibilities:
- Provide the FastAPI application and endpoint definitions
- Wire together: condition_registry, engine_adapters, persistence,
  practice_repository, submission_repository, email_service, request_validation
- Translate between HTTP requests and engine entry points
- Map condition_id to ruleset_path and condition_label via the registry
- Resolve practice_id from app.state (set once at startup)
- Orchestrate the submission flow: generate outputs, persist record, send email
- registry and practice_repo stored in app.state.registry and app.state.practice_repo so the admin router can access them via request.app.state without importing from main.py

Endpoints:
- GET /conditions — list all conditions (from registry)
- GET /conditions/{condition_id}/presentation — presentation metadata
  (no ?practice= parameter; practice_id resolved from app.state)
- POST /form/init — create session
- POST /form/update — apply patient answers
- POST /form/finish — close session, persist submission, send email

Rules:
- No clinical logic
- No safety rule evaluation
- No encoder invocation
- Request validation via request_validation.py (not Pydantic models)
- Uses Request.json() for payload parsing
- condition_label is resolved from the registry and passed explicitly to
  engine_adapters; presentation metadata never enters the engine

Startup validation (fail-fast, in order):
1. PRACTICE_ID environment variable must be set
2. Database must contain exactly one practice (more is a safety violation —
   multiple practices implies cross-contamination of clinical data)
3. That practice must match PRACTICE_ID
4. The practice must have a non-empty email address
5. SMTP environment variables must be set (unless DEV_MODE=1)
6. ADMIN_TOKEN environment variable must be set (unless DEV_MODE=1); if DEV_MODE=1 and ADMIN_TOKEN is absent, a warning is logged and any non-empty bearer token will be accepted by admin endpoints
7. practice_id stored in app.state.practice_id

Any failure in startup validation raises RuntimeError and prevents the
application from starting. This is intentional: a misconfigured deployment
must not silently degrade into sending forms to the wrong destination.

form/finish flow:
1. Validate payload and load runtime state
2. Call finish_runtime_state → (ClinicalOutput, AuditOutput)
3. Get delivery_email from practice_repo (captured at submission time for audit)
4. Generate submission_id
5. Create submission record with delivery_status = "pending"
6. Attempt email send
7. On success: update delivery_status = "sent"
8. On EmailDeliveryError: update delivery_status = "failed", log error
   (do not re-raise — the patient has completed the form)
9. Close the session
10. Return submission_id
11. Static file serving:
- StaticFiles from starlette.staticfiles is mounted at /admin-portal,
  serving files from frontend/admin/ with html=True
- html=True means a bare request to /admin-portal/ serves admin.html automatically
- The mount must be registered after app.include_router(admin_router) to avoid
  the catch-all StaticFiles handler intercepting admin API routes
- The directory path is relative to the working directory at uvicorn startup,
  which is expected to be project_root/

---

### 3.14 encoder_contracts.py — Encoder boundary contracts

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

### 3.15 practice_repository.py — Practice database access

Responsibilities:
- Initialise practices and practice_signposting tables on startup
- CRUD operations for practices (practice_id, name, email)
- CRUD operations for practice-specific signposting per condition
- Email format validation

Public interface:
- create_practice(practice_id, name, email) → None
- get_practice(practice_id) → dict | None
- get_email(practice_id) → str (raises PracticeNotFound if absent)
- practice_exists(practice_id) → bool
- count_practices() → int
- get_signposting(practice_id, condition_id) → list[str] | None
- set_signposting(practice_id, condition_id, items) → None
- delete_signposting(practice_id, condition_id) → None

Email validation rules:
- Must be a string
- Must not have leading or trailing whitespace
- Must contain exactly one '@' with non-empty parts either side

This module must never:
- Access clinical data (rulesets, RuntimeState, answers)
- Perform composition logic (that belongs in presentation_service)
- Handle authentication (Phase 1B)


### 3.16 submission_repository.py — Submission record database access

Responsibilities:
- Initialise submission_records table on startup
- Create submission records at form completion
- Update delivery status after email send attempt
- Retrieve and list submission records for manual inspection

Public interface:
- create_submission(submission_id, practice_id, condition_id,
  clinical_output, audit_output, delivery_email) → None
- update_delivery_status(submission_id, status,
  delivered_at=None, delivery_error=None) → None
- get_submission(submission_id) → dict
- list_by_status(status) → list[dict]

delivery_status values: "pending", "sent", "failed"
list_by_status raises InvalidDeliveryStatus on unrecognised values — a typo
must not silently return an empty list when the caller expected failures.

delivery_email is stored at submission time from the practice record, not
looked up later. This means the audit trail reflects where the form was
actually sent, even if the practice email is updated afterwards.

This module must never:
- Send emails (that belongs in email_service)
- Import engine modules
- Make retry decisions (that belongs in the calling layer)


### 3.17 email_service.py — Clinical output email delivery

Responsibilities:
- Format clinical output as a plain text email body
- Send via SMTP in production mode
- Log to stdout in DEV_MODE without sending

Configuration via environment variables:
- SMTP_HOST, SMTP_PORT (default 587), SMTP_USER, SMTP_PASSWORD, EMAIL_FROM
- SMTP_TIMEOUT (default 30 seconds)
- DEV_MODE=1: skips sending, logs full email content to stdout

Public interface:
- send_clinical_output(to_email, condition_label, clinical_output,
  submission_id) → None

Raises EmailDeliveryError on any SMTP failure. The error message is
suitable for storage in submission_records.delivery_error.

Email body uses clinical_output.question_labels for human-readable answer
labels. Falls back to the raw answer_key if a label is missing.

This module must never:
- Access the database
- Update delivery status (that belongs in submission_repository)
- Import engine modules or condition_registry
- Retry on failure


### 3.18 presentation_service.py — Patient-facing presentation composition

Responsibilities:
- Compose patient-facing presentation from three sources:
  1. Universal safety warning (hardcoded constant, not editable)
  2. Practice-specific signposting (from practice_repository)
  3. Condition presentation (label, free_text_prompt from condition_registry)
- Provide a single access point for all pre-form presentation data

Public interface:
- get_patient_presentation(condition_id, practice_id) → dict

practice_id is always required. This service is deployed in a single-tenant
context; there is no concept of a missing practice.

Output keys:
- label: str
- free_text_prompt: str | None
- universal_safety_warning: str
- practice_signposting: list[str] | None (None if not configured or empty)

This module performs COMPOSITION, not MERGING. Each source populates a
distinct field. There is no field-level override logic.

This module must never:
- Access clinical data
- Modify any data
- Handle authentication (Phase 1B)

## 3.19 Frontend modules

The frontend is a stateless renderer. It contains no clinical logic,
no branching decisions, and no safety evaluation. All intelligence
lives on the server.

### 3.19.1 types.ts — Frontend-visible contracts

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

### 3.19.2 api.ts — HTTP client

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
* All type imports must use `import type` syntax. TypeScript interfaces
  do not exist at runtime; using a plain import causes bundler errors
  when verbatimModuleSyntax is enabled in tsconfig

### 3.19.3 App.tsx — React UI

Stateless renderer implementing a five-screen flow.

File is App.tsx (TypeScript + JSX). An earlier version was App.jsx but was
renamed when TypeScript generic syntax caused Vite/Babel parse errors in a
.jsx file.

* Screen 0 (SELECT_CONDITION): fetches GET /conditions, renders dropdown
* Screen 1 (FREE_TEXT): fetches GET /conditions/{id}/presentation,
  renders framing text + free text input, submits to POST /form/init
* Screen 2 (EDIT): renders questions from ClientStateView, collects answers, additionalText state is added to the EDIT screen, included in the ClientAnswerReturn payload, and shown on the REVIEW screen only when non-empty
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
* All type imports must use `import type` syntax (same reason as api.ts)

State management:
* Pre-session state: selectedConditionId, presentation, freeText
* Session state: runtimeId, version, clientState, editableAnswers, safetyMessages
* Pre-session state is discarded after /form/init succeeds
* Session state is never round-tripped back to pre-session screens

Development:
* Served via Vite dev server on port 5173 during development
* Vite proxy forwards /conditions and /form requests to FastAPI on port 8000
* For production, run npm run build and serve the dist/ output as StaticFiles
* Start command from project root:
    cd frontend && npm run dev
  FastAPI must also be running on port 8000 in a separate terminal

Here is the new architecture section. This slots in after section 3.19.3 (App.tsx) and before whatever follows it.

### 3.19.4 search.ts — Condition search and filtering
A single-purpose frontend module containing all condition filtering logic for the combobox. Nothing else in the frontend contains matching logic.

Location: frontend/search.ts

Exported functions:
* normalise(text): string — lowercases and trims a string. Applied to both query and all strings being compared.
* matchesQuery(condition, query): boolean — returns true if the condition should appear for a given query string.
* filterConditions(conditions, query): ConditionSummary[] — filters a canonical condition list by query. Always filters from the full list passed in, never incrementally from a previous result.

Three-layer matching strategy (applied in order):
* Layer 1 — substring match on the condition label. Case-insensitive. Handles the common case of a patient typing part of a plain English label.
* Layer 2 — substring match on any search_tags entry. Case-insensitive. Handles synonyms, abbreviations, and medical terms that differ from the label (e.g. "UTI" finding "Urinary symptoms").
* Layer 3 — Levenshtein (edit distance) fuzzy match on individual tokens of each tag. The tag is split on whitespace into tokens. The query is kept as a single string and compared against each token. Handles common misspellings (e.g. "cistitis" finding "cystitis").
* Layer 3 only runs if layers 1 and 2 both return false. This avoids unnecessary computation and prevents short correct queries from triggering fuzzy noise.

Fuzzy matching thresholds:
* Query lengthBehaviourLess than 4Fuzzy disabled entirely4 to 5Threshold 1 (one edit)6 or moreThreshold 2 (two edits)
* Short queries disable fuzzy matching to prevent false positives. For example, "ut" would otherwise match almost everything.
* Fallback behaviour:
* filterConditions returns the full canonical list when the query is empty or when no conditions match. It never returns an empty list.  The caller (ConditionCombobox) is responsible for detecting the no-match fallback and showing the appropriate message.

Constants (named, not magic numbers):
* FUZZY_MIN_QUERY_LENGTH = 4
* FUZZY_THRESHOLD_SHORT = 1
* FUZZY_THRESHOLD_LONG = 2

Dependencies: types.ts (ConditionSummary type only). No backend dependency. No external library.
Tests: tests/test_search.mjs. Run with node tests/test_search.mjs. Covers all three matching layers, threshold boundary conditions, fallback behaviour, and case insensitivity.

### 3.19.5 ConditionCombobox.tsx — Condition selection combobox
A self-contained React component that replaces the separate search input and select dropdown on Screen 0. Renders a text input that shows a floating suggestion list, filtered in real time as the patient types.
Location: frontend/ConditionCombobox.tsx
Props:
typescriptinterface ConditionComboboxProps {
  conditions: ConditionSummary[];   // full canonical list, never mutated
  selectedId: string | null;        // currently selected condition id
  onChange: (id: string | null) => void;
}
Internal state:
* inputValue: string — text currently shown in the input
* isOpen: boolean — whether the suggestion list is visible
* activeIndex: number | null — which suggestion is keyboard-highlighted

filteredConditions is a derived value computed on every render from filterConditions(conditions, inputValue). It is never stored in state, which guarantees filtering is always from the canonical list and never incremental.
Behaviour:
* On focus: opens the suggestion list showing all conditions (input is empty, full list returned).
* On typing: updates inputValue, reopens the list, clears activeIndex, and calls onChange(null) to invalidate any previous selection.
* On suggestion click: sets inputValue to the condition label, closes the list, calls onChange(condition.id).
* On selection via keyboard Enter: same outcome as click.
* On blur: closes the list after a 150ms delay. The delay is necessary because mousedown on a suggestion fires the input blur event before the click registers. Without the delay the list closes before the selection is applied. The blur timeout is cancelled if the user refocuses the input or clicks a suggestion.
* Escape closes the list without clearing the input or selection. Tab closes the list and allows natural focus movement.

Keyboard navigation:
* ArrowDown — moves highlight down, wraps from last to first
* ArrowUp — moves highlight up, wraps from first to last
* Enter — selects the highlighted condition if one exists
* Escape — closes the list
* Tab — closes the list, does not prevent default

Suggestion list:
* Rendered as an absolutely-positioned <ul> below the input. position: relative on the container ensures correct positioning. max-height: 300px with overflow-y: auto prevents the list extending off screen. z-index: 100 ensures it overlays subsequent page content.
* When the filtered list is shorter than the full list, a count label is shown at the top of the list: "Showing X of Y conditions."
* When inputValue is non-empty but no tags or labels matched and filterConditions fell back to the full list, a message is shown instead of the count: "No matching conditions — try different words, or scroll below."

ARIA:
* Follows the ARIA combobox pattern. The input has role="combobox", aria-expanded, aria-autocomplete="list", aria-controls pointing to the listbox, and aria-activedescendant pointing to the active option when keyboard-highlighted. The list has role="listbox". Each item has role="option" and aria-selected. IDs are generated with useId() to prevent collisions.
Dependencies: search.ts (filterConditions), types.ts (ConditionSummary). No external library.

Condition search_tags — ruleset schema
search_tags is an optional field in the presentation block of each ruleset JSON file. It provides synonyms, abbreviations, and colloquial terms that patients might type when searching for a condition.
Location in ruleset: inside presentation, alongside label and free_text_prompt.
Example:
json"presentation": {
  "label": "Urinary symptoms",
  "free_text_prompt": "Tell us about your symptoms and when they started.",
  "search_tags": ["UTI", "cystitis", "bladder infection", "burning urine"]
}


**Design rationale:** search tags are presentation-layer metadata, not clinical content. Placing them inside the `presentation` block keeps clinical schema (questions, safety rules, encoder definitions) free of search concerns. Tags are written and maintained by whoever edits the ruleset JSON — there is no automatic synonym generation.

**Validation** (enforced by `condition_registry.py` at startup — any failure aborts startup):

- `search_tags` is optional. Absent means empty list, not an error.
- If present, must be a list.
- Each item must be a non-empty string after stripping whitespace.
- Each item must not exceed `SEARCH_TAGS_MAX_TAG_LENGTH` (60) characters.
- Total count must not exceed `SEARCH_TAGS_MAX_COUNT` (20) tags.
- Case-insensitive duplicates are silently removed with a logged warning. First occurrence is kept.
- `search_tags` is added to the presentation allow-list in `condition_registry.py`. Any other unexpected key in `presentation` still aborts startup.

**Exposure:** `condition_registry.list_conditions()` returns `search_tags` alongside `id` and `label`. Search tags are never exposed in the clinical engine, safety engine, or any backend module other than the registry.

**Maintenance note:** tags are the only mechanism for synonym matching. There is no automatic or ML-based synonym expansion. If a condition is renamed or new colloquial terms become common, the JSON file must be updated manually.

### 3.19.6 constants.ts — Frontend application constants
Single file for frontend-wide constants that must be kept in one place.
Contains:

GENERAL_CONSULTATION_ID: string — the condition_id of the general consultation
(blank form) ruleset. Must match the condition_id field in general.json exactly.
Used in App.tsx to filter this condition from the combobox and to set
selectedConditionId when the blank form button is clicked.

If the general consultation ruleset is ever renamed, update this constant and
this constant only. Do not hardcode the string elsewhere in the frontend.

---

### 3.20 admin_context.py — Admin authentication boundary
Responsibilities:
* Define the AdminContext frozen dataclass
* Provide the require_admin FastAPI dependency, which is the sole authentication boundary for all admin endpoints

AdminContext fields:

practice_id: str — resolved from request.app.state.practice_id
auth_method: str — "bearer_token" when validated against ADMIN_TOKEN; "dev_any" in DEV_MODE without a set token

Authentication rules:
* Authorization header is always required, even in DEV_MODE
* Missing or empty bearer value → 401
* If ADMIN_TOKEN is set: token must match exactly → 401 on mismatch
* If DEV_MODE=1 and ADMIN_TOKEN is not set: any non-empty bearer token is accepted
* If neither condition holds (production mode, no ADMIN_TOKEN): 401 always — fail closed

The reason the header is required even in DEV_MODE is that omitting it entirely would mean the auth code path is never exercised in development or tests. A broken auth check could be shipped without being noticed. Requiring a header but accepting any value keeps the code path live.
This module is designed to be replaced in its entirety in Phase 1B when session-based MFA is introduced. Nothing else changes when it is replaced. auth_method is a string rather than an enum so Phase 1B can introduce new values without modifying the dataclass.
This module must never import any project module. Only stdlib and FastAPI.

---

### 3.21 admin_router.py — Admin API endpoints
Responsibilities:
* Provide all admin HTTP endpoints as a FastAPI APIRouter
* Validate condition_id against the condition registry before any database operation
* Validate and sanitise signposting input before calling the repository
* Normalise empty signposting lists to null in all responses

The router is registered in main.py with prefix /admin and tag admin. The prefix and tag are not defined in this module so that the router stays decoupled from its mount point.
All endpoints declare Depends(require_admin) and receive an AdminContext. Resources (registry, practice_repo) are read from request.app.state — never imported from main.py.
Endpoints:
* GET /admin/conditions — returns all condition IDs and labels from the registry. This is a raw administrative view separate from the patient-facing GET /conditions, which composes full presentation data. Keeping them separate means a change to either cannot accidentally affect the other.
* GET /admin/conditions/{condition_id}/signposting — returns current signposting or null. Returns null (not 404) when no signposting is configured; absence of signposting is a valid configured state, not an error.
* PUT /admin/conditions/{condition_id}/signposting — replaces the full signposting list. Always sends the complete desired state; no partial update or append. Input validation (performed in the router before calling the repository): body must be {"signposting": [...]}, each item must be a string, each item is stripped of whitespace, each item must be non-empty after stripping, empty list is valid. The stripped list is written to the database as-is (including empty list). The response normalises empty list to null.
* DELETE /admin/conditions/{condition_id}/signposting — removes the database row entirely. Idempotent. Returns 204 no body. Semantically distinct from PUT []: the row is deleted rather than updated, which preserves the distinction at the database level and in any future audit log, even though GET normalises both to null for current consumers.

Response normalisation rule: empty list and null are both returned as null in all responses. This is consistent with how presentation_service.py behaves and means GET does not expose whether signposting was explicitly cleared or never set. That distinction is preserved at the database level only.
Validation responsibility split:

The router is the primary validation layer for HTTP input (types, whitespace, empty strings)
The repository's own validation acts as a backstop but the router validates first
condition_id is validated against the registry in the router; the repository has no knowledge of valid condition IDs and does not raise on unknown ones

Known limitation: the condition registry is immutable after startup. A new condition JSON file added to data/ while the server is running will return 404 from admin endpoints until the server is restarted. This is intentional.
This module must never import: clinical engine modules, presentation_service, serialisation, projection, runtime_state.

---

### 3.22 frontend/admin/admin.html — Admin frontend

A single self-contained HTML file serving the practice admin UI.
No build step. React 18 and JSX loaded via CDN. Babel-standalone
performs in-browser JSX transpilation at load time.

Babel-standalone is approximately 800KB. This is acceptable for an
internal tool on a local network. It would not be acceptable for a
patient-facing or high-traffic interface.

Served at /admin-portal/ via StaticFiles mount in main.py.

Component structure:
- App: root component, owns token and conditions state, switches between views
- TokenView: token entry form, calls GET /admin/conditions as connectivity
  and auth check, stores valid token in React state (never localStorage)
- EditorView: condition dropdown and editor container, owns unsaved-change
  tracking via a ref updated by a callback prop from the editor
- SignpostingEditorWithRef: manages the full list editor for one condition —
  load, add, delete, reorder, per-item validation, save, status messages

State ownership:
- token and conditions: App
- selectedConditionId: EditorView
- items, savedItems, isSaving, saveStatus, validationError: SignpostingEditorWithRef

Unsaved change tracking:
SignpostingEditorWithRef reports its unsaved state to EditorView via an
onUnsavedChange callback prop. EditorView stores this in a ref (not state)
so the value is readable synchronously inside the confirm() dialog handler
without triggering a re-render. When the condition dropdown changes and
unsaved changes exist, window.confirm() is shown before the switch proceeds.

Key behaviours:
- Token entry calls GET /admin/conditions; 200 means valid, 401 shows error
- Condition switch with unsaved changes triggers a confirm() dialog
- Each item is validated as non-empty (after trim) before save is permitted
- Save always sends the full list via PUT (no partial update)
- Empty list save sends [] which the backend stores; subsequent GET returns null;
  UI shows an empty editor
- Try/catch on all fetch calls; network errors produce inline error messages,
  not browser error dialogs
- Saving spinner and "Saved" / "Save failed: ..." status messages inline

Authentication note:
The token field is a temporary placeholder. It will be replaced entirely in
Phase 5 when session-based MFA is introduced. The token is never written to
localStorage or any persistent browser storage — it exists only in React
component state for the duration of the browser session.

This module must never:
- Store the admin token in localStorage or sessionStorage
- Contain clinical logic or safety rule evaluation
- Make requests to any endpoint other than /admin/*

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
Encoder-corrected answers (encoder_corrected) are always treated as explicit — the patient actively overrode an encoder suggestion, which is the strongest possible signal of explicit intent.

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

### 7.3 Submission records (post-session, delivery tracking)

On form/finish, a submission_record is created before the email is sent.
This ensures the record exists even if the process crashes during delivery.

Lifecycle:
1. submission_record created with delivery_status = "pending"
2. Email send attempted
3. On success: delivery_status = "sent", delivered_at = now
4. On failure: delivery_status = "failed", delivery_error = exception message

A "failed" record is the recovery mechanism for email delivery failures.
Manual inspection of failed records (via list_by_status("failed")) is the
supported recovery path for MVP. No automatic retry is implemented.

The patient receives a submission_id regardless of delivery outcome. Email
failure is not surfaced to the patient — it is an operational concern, not
a clinical one. The patient is shown a message on Screen 4 advising them
to contact the practice directly if they do not receive a response within
48 hours.

delivery_email is stored at submission time from the practice record.
If the practice email is updated after submission, historical records
still reflect the address that was actually used.

## 8.1 Clinical ruleset structure

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


### 8.2 search_tags — Presentation-layer synonym metadata

An optional field in the presentation block of each ruleset JSON.
Provides synonyms, abbreviations, and colloquial terms that patients may type
when searching for a condition in the combobox.

Example:
```json
"presentation": {
  "label": "Urinary symptoms",
  "free_text_prompt": "Tell us about your symptoms and when they started.",
  "search_tags": ["UTI", "cystitis", "bladder infection", "burning urine"]
}
```

Design rationale: tags are presentation-layer metadata, not clinical content.
They belong inside the presentation block alongside label and free_text_prompt.
Clinical schema (questions, safety rules, encoder definitions) is unaffected.

Tags are maintained manually in the JSON by whoever edits the ruleset.
There is no automatic or ML-based synonym expansion.

Validation is enforced by condition_registry.py at startup. See section 3.12.

### 8.3 general.json — Generic fallback condition

A standard ruleset processed identically to all other conditions by the backend.
It is the target of the "Use blank form" button on Screen 0.

condition_id: "general_consultation" — this value is also stored in
constants.ts as GENERAL_CONSULTATION_ID. If it changes, both must be updated.

Questions: three open-ended text questions (problem_onset, problem_impact,
problem_tried). All are answer_type "text", send_to_encoder false.

Safety rules: empty. The universal safety warning shown on Screen 1 provides
the only safety netting for this pathway.

This condition is registered in the registry and appears in GET /conditions
like any other condition. The frontend filters it from the combobox using
GENERAL_CONSULTATION_ID. It is never displayed in search results.

No search_tags are defined — this condition is unreachable via the combobox.

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
* PRACTICE_ID environment variable not set → startup abort
* Database contains more than one practice → startup abort
* PRACTICE_ID does not match any practice in database → startup abort
* Practice has no email address → startup abort
* SMTP environment variables not set in production mode → startup abort
* submission_repository.list_by_status called with unrecognised status → ValueError

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
* Single-tenant deployment: one practice per deployment, enforced at startup
* Submission records persisted with delivery status tracking
* Email delivery of clinical output to practice on form completion
* DEV_MODE for local development without SMTP configuration
* question_labels stored in ClinicalOutput for self-contained audit records
Patient-facing frontend running via Vite dev server (port 5173) with API
  proxy to FastAPI (port 8000)
* Admin frontend served as static file at /admin-portal/admin.html


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

1. Patient accesses the form via the practice's website
2. GET /conditions/{id}/presentation called
3. presentation_service composes response:
   a. Fetches condition presentation from registry (immutable, in-memory)
   b. Fetches practice signposting from database using practice_id from app.state
   c. Adds universal safety warning constant
   d. Returns composed dict
4. Frontend renders all three information types in distinct UI sections

### 12.4 Plan
Phase 1A — Practice-specific signposting: COMPLETE
- practices and practice_signposting database tables
- practice_repository.py: CRUD for practices and signposting, email validation
- presentation_service.py: composes universal safety warning + practice signposting
  + condition presentation
- condition_registry.py: pre_form_information removed; presentation block limited
  to label and free_text_prompt
- main.py: presentation endpoint updated to use PresentationService
- types.ts: ConditionPresentation updated to reflect new structure

Phase 1A.1 — Single-tenant deployment configuration: COMPLETE
- practices table: email column added (required, no default)
- practice_repository.py: email support, get_email(), count_practices(),
  InvalidEmailError
- submission_repository.py: new module, submission_records table, delivery
  status tracking
- email_service.py: new module, plain text clinical output email, DEV_MODE
  support, EmailDeliveryError
- serialisation_contracts.py: question_labels added to ClinicalOutput
- serialisation.py: clinical_output() now takes ruleset parameter, builds
  question_labels
- engine_adapters.py: finish_runtime_state returns (ClinicalOutput, AuditOutput)
  tuple
- presentation_service.py: practice_id now required (single-tenant contract)
- main.py: startup validation (PRACTICE_ID, single practice, email, SMTP);
  form/finish creates submission record and sends email; ?practice= query
  parameter removed
- app.jsx: Screen 4 patient guidance message added
- migrate_phase1a1.py: one-shot migration script for dev environments

Phase 2 — Admin endpoints: COMPLETE
- admin_context.py: AdminContext dataclass, require_admin dependency
- admin_router.py: GET/PUT/DELETE /admin/conditions/{id}/signposting,
  GET /admin/conditions
- main.py: register admin router, add app.state.registry/practice_repo,
  ADMIN_TOKEN startup check
- tests/test_admin_router.py: auth and endpoint behaviour tests
- API contracts:
    GET /admin/conditions → { conditions: [{ id, label }] }
    GET /admin/conditions/{id}/signposting → { condition_id, signposting: [] | null }
    PUT /admin/conditions/{id}/signposting → same shape as GET
    DELETE /admin/conditions/{id}/signposting → 204 no body
- Authentication: Bearer token required on all admin endpoints. Token must match
  ADMIN_TOKEN env var in production. In DEV_MODE with no ADMIN_TOKEN set, any
  non-empty token is accepted.
- types.ts has no admin types. admin.html is self-contained and does not use
  types.ts.

Phase 3 — Admin frontend: COMPLETE
- frontend/admin/admin.html: single self-contained file, React 18 + JSX via
  Babel-standalone CDN, no build step
- TokenView: token entry with connectivity check against GET /admin/conditions;
  token stored in React state only, never in localStorage
- EditorView: condition dropdown with unsaved-change detection via ref + callback
  prop pattern; confirm() dialog on condition switch with pending changes
- SignpostingEditorWithRef: full list editor per condition — load, add, delete,
  reorder, per-item blank validation, save with spinner, inline status messages
- Try/catch on all fetch calls; network errors produce inline messages, not
  browser error dialogs
- Served at /admin-portal/ via StaticFiles mount in main.py (registered after
  admin router to avoid route shadowing)
- Note: token field is a temporary placeholder, replaced entirely in Phase 5

Phase 4 — Audit trail: DEFERRED
Deferred until the product is closer to production readiness. Currently system is being used by one practice, one admin
Scope: log all signposting changes made via the admin interface for inspection
and future regulatory purposes.

Expected new artefacts:
- signposting_audit_log table with columns:
    event_id TEXT PRIMARY KEY
    practice_id TEXT NOT NULL
    condition_id TEXT NOT NULL
    action TEXT NOT NULL          -- "put" | "delete"
    token_identity TEXT           -- hash of bearer token, not raw value
    previous_value TEXT           -- JSON array or null (null on first put)
    new_value TEXT                -- JSON array or null (on delete)
    changed_at TIMESTAMP NOT NULL
- audit_repository.py: write-only append log, no update or delete operations
- admin_router.py: call audit_repository.log_event() after every successful
  PUT or DELETE (on failure the signposting change is still committed —
  a logging failure must not roll back a valid admin action)
- GET /admin/conditions/{id}/signposting/audit or similar read endpoint
  (exact shape TBD in Phase 4)

What Phase 3 intentionally does not provide for Phase 4:
- The bearer token is available in AdminContext but its raw value should not
  be logged. Phase 4 should store a hash (e.g. SHA-256 truncated) or a stable
  token alias. The identity field exists to detect "which admin session made
  this change", not to recover the token itself.
- No previous_value is captured today. Phase 4 must fetch the existing
  signposting before overwriting it in order to record the diff. The
  GET-then-PUT pattern in admin_router.py will need to become a
  GET-then-log-then-PUT sequence.

Phase 5 — Practice authentication: DEFERRED
Deferred until the product is closer to production readiness. All other
features should be complete before authentication is introduced.

Planned deliverables:
- practice_tokens table
- practice_context.py for token validation
- admin_context.py replaced in its entirety with session-based MFA
- Token-based access to admin endpoints
- auth_method field in AdminContext is a string rather than an enum
  specifically to allow Phase 5 to introduce new values without modifying
  the dataclass

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
- POST /form/init — create session. Availability check at the top of the handler, before any existing logic.
Wrapped in try/except: if any exception is raised during the check,
it is logged and the request proceeds as if open (fail-open). If the
check completes and is_open is false, returns HTTP 503 with
{"detail": closed_message}. A database failure must never lock
patients out.
- POST /form/update — apply patient answers
- POST /form/finish — close session, persist submission, send email
- POST /form/finish — now requires contact_preferences block in payload.
  See request_validation.py for validation rules. contact_preferences is
  passed through to email_service only; it is not stored in the database
  and has no effect on clinical output or audit records.
- GET /availability — public, no auth. Evaluates current availability
and returns {is_open, closed_message, after_hours_notice}. If the
database raises an exception, FastAPI returns HTTP 500. The frontend
treats any non-200 response as fail-open.

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
8. availability_repo.init_availability(practice_id) — inserts default
availability row if absent. Must run after _validate_startup ensures
the practice row exists.

Any failure in startup validation raises RuntimeError and prevents the
application from starting. This is intentional: a misconfigured deployment
must not silently degrade into sending forms to the wrong destination.

form/finish flow:
1. Validate payload and load runtime state
2. Extract contact_preferences from validated payload
3. Call finish_runtime_state → (ClinicalOutput, AuditOutput)
4. Get delivery_email from practice_repo (captured at submission time for audit)
5. Generate submission_id
6. Create submission record with delivery_status = "pending"
7. Attempt email send
8. On success: update delivery_status = "sent"
9. On EmailDeliveryError: update delivery_status = "failed", log error
   (do not re-raise — the patient has completed the form)
10. Close the session
11. Return submission_id

Static file serving:
- StaticFiles from starlette.staticfiles is mounted at /admin-portal,
  serving files from admin/ with html=True
- html=True means a bare request to /admin-portal/ serves index.html automatically
- The mount must be registered after app.include_router(admin_router) to avoid
  the catch-all StaticFiles handler intercepting admin API routes
- The directory path is relative to the working directory at uvicorn startup,
  which is expected to be project_root/

availability_repo = AvailabilityRepository(DATABASE_URL)
availability_repo stored in app.state.availability_repo so the admin
router can access it via request.app.state

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
- HTML sanitisation for signposting content via nh3

Public interface:
- create_practice(practice_id, name, email) → None
- get_practice(practice_id) → dict | None
- get_email(practice_id) → str (raises PracticeNotFound if absent)
- practice_exists(practice_id) → bool
- count_practices() → int
- get_signposting(practice_id, condition_id) → str | None
- set_signposting(practice_id, condition_id, html) → None
- sanitise_signposting_html(raw) → str | None  (module-level function)
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
  submission_id, contact_preferences=None) → None

contact_preferences is an optional dict passed through from the finish
payload. When present, a CONTACT PREFERENCES section is appended to the
email body after the clinical content. When absent or None, the section
is omitted entirely. Null optional fields within the block (phone_number,
best_time_to_call, usual_doctor_name) are omitted line-by-line rather
than printed as "None".

contact_preferences is accepted as a plain dict, not a typed dataclass.
It is presentation-only data with no clinical significance and no need
for engine-level typing. The email service is not responsible for
validating it — that is done upstream in request_validation.py.

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
- practice_signposting: str | None  (sanitised HTML string, or None if not configured)

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
* ConditionPresentation — label, free_text_prompt, universal_safety_warning, practice_signposting (string | undefined — sanitised HTML rendered via DOMPurify)
*  ContactMethod — union type: "email" | "text" | "phone"
* DoctorPreference — union type: "any" | "usual"
* ContactPreferences — contact method selection, contact details,
  and doctor preference collected on Screen 5 (CONTACT)
* AvailabilityResult — is_open (boolean), closed_message (string | null),
after_hours_notice (string | null). Used by Screen 0 availability fetch.

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
* finishForm(runtimeId, version, contactPreferences) — POST /form/finish
  Accepts a ContactPreferences object and includes it as contact_preferences
  in the POST body.
* getSafetyWarning() — GET /safety-warning (already existed, document here for completeness alongside availability)
* getAvailability() — GET /availability. Returns AvailabilityResult
* ApiError now carries a detail field. postJson extracts detail from 503 responses. friendlyErrorMessage returns the server's closed message for 503 errors.

Rules:
* No business logic
* No data transformation beyond JSON serialisation
* Payload field names must match backend expectations exactly
  (e.g. condition_id, free_text, runtime_id, base_version)
* All type imports must use `import type` syntax. TypeScript interfaces
  do not exist at runtime; using a plain import causes bundler errors
  when verbatimModuleSyntax is enabled in tsconfig

### 3.19.3 App.tsx — React UI

Stateless renderer implementing a six-screen flow.

* Screen 0 (SAFETY_WARNING): displays universal safety warning, requires
  confirmation before continuing
* Screen 1 (SELECT_CONDITION): fetches GET /conditions, renders combobox
* Screen 2 (FREE_TEXT): fetches GET /conditions/{id}/presentation,
  renders framing text + free text input, submits to POST /form/init
* Screen 3 (EDIT): renders questions from ClientStateView, collects answers.
  additionalText state is collected here, included in the ClientAnswerReturn
  payload, and shown on the REVIEW screen only when non-empty.
  Submits to POST /form/update.
* Screen 4 (REVIEW): displays answers + safety messages.
  Submit button transitions to Screen 5 (CONTACT) rather than calling
  the API directly. Returns to EDIT via Back.
* Screen 5 (CONTACT): collects contact preferences (method, contact details,
  doctor preference). Submits to POST /form/finish with the complete
  ContactPreferences payload. Returns to REVIEW via Back without losing
  REVIEW state.
* Screen 6 (DONE): confirmation

Contact screen behaviour:
* At least one contact method must be selected before submission
* Phone number field is shown when "text" or "phone" is selected
* Email address field is shown when "email" is selected
* Best time to call field is shown when "phone" is selected
* Doctor name field is shown when "usual doctor" is selected in the dropdown
* UK phone validation: strips spaces, checks for 07 or +44 prefix,
  enforces length 10–13 digits. International numbers are rejected.
* Validation fires on Submit with inline per-field error messages.
  No alert boxes.
* contactPreferences state is reset to defaults each time the patient
  enters the CONTACT screen from REVIEW.

State management:
* Pre-session state: selectedConditionId, presentation, freeText
* Session state: runtimeId, version, clientState, editableAnswers,
  safetyMessages, additionalText
* Contact state: contactPreferences, contactErrors
* Pre-session state is discarded after /form/init succeeds
* Session state is never round-tripped back to pre-session screens
* contactPreferences is not persisted to the server until final submission

Development:
* Served via Vite dev server on port 5173 during development
* Vite proxy forwards /conditions and /form requests to FastAPI on port 8000
* For production, run npm run build and serve the dist/ output as StaticFiles
* Start command from project root:
    cd frontend && npm run dev
  FastAPI must also be running on port 8000 in a separate terminal

Screen 0 (SAFETY_WARNING) now fetches GET /availability alongside the
safety warning. Three new state variables: practiceIsOpen,
availabilityClosedMessage, afterHoursNotice.
Availability fetch behaviour:

Runs in a separate useEffect, parallel to the safety warning fetch.
If the fetch fails for any reason (network error, any non-200 response),
fails open: practiceIsOpen is set to true. No closed message banner,
no after-hours notice. A fetch failure must never lock patients out.

Screen 0 rendering changes:

When practice is closed (practiceIsOpen === false): a yellow warning
banner appears above the safety warning text. The safety warning remains
visible — a patient arriving out of hours must still see emergency safety
information. The Continue button is disabled.
When practice is open and afterHoursNotice is non-null: an informational
blue notice appears below the safety warning, above the checkbox.

initForm 503 handling:

If POST /form/init returns 503 (practice closed between availability
check and form submission), the detail field from the response body is
displayed as the screen error on Screen 2 (FREE_TEXT). This is handled
transparently via the updated friendlyErrorMessage in api.ts.

### 3.19.4 search.ts — Condition search and filtering
A single-purpose frontend module containing all condition filtering logic for the combobox. Nothing else in the frontend contains matching logic.

Location: frontend/src/search.ts

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

### 3.19.5 ConditionCombobox.tsx — Condition selection combobox
A self-contained React component that replaces the separate search input and select dropdown on Screen 0. Renders a text input that shows a floating suggestion list, filtered in real time as the patient types.
Location: frontend/src/ConditionCombobox.tsx
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

### 3.19.6 Admin portal — AvailabilityEditor.tsx
Location: frontend/admin-ui/src/AvailabilityEditor.tsx
A self-contained React component rendered as a card above the signposting
editor in EditorView.tsx.
Fetches GET /admin/availability on mount. Displays:

Enable/disable checkbox (is_active). When unchecked, schedule fields
are hidden and a description reads "The form is available at all times."
When active: day toggle buttons (Mon–Sun), open/close time inputs
(HTML type="time"), closed message textarea.
Save button calling PUT /admin/availability.

Empty-days confirmation:
If is_active is true and no days are selected when Save is clicked, a
window.confirm dialog is shown: "No days are selected. Saving this
configuration will close the form to patients on every day of the week.
Are you sure?" The admin must confirm before the request is sent.
Validation errors from the API are displayed inline via the SaveStatus
pattern used by SignpostingEditor.
After a successful save, form state is synced to the server's response
to ensure the UI reflects exactly what was stored.
Admin api.ts additions:

fetchAvailability(token) → AvailabilityConfig
putAvailability(token, config) → AvailabilityConfig

Admin types.ts additions:

AvailabilityConfig interface (practice_id, is_active, weekly_open_days,
open_time, close_time, closed_message)

EditorView.tsx changes:

Imports and renders AvailabilityEditor above the signposting card.
Component renders a fragment (<>) instead of a single card div to
accommodate both cards.

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
* PUT /admin/conditions/{condition_id}/signposting — sets signposting for a condition. Body must be {"signposting": "..."} where the value is a string. Empty or whitespace-only content is treated as an instruction to clear — the repository deletes the row and returns {"signposting": null}. Length is pre-checked against MAX_SIGNPOSTING_LENGTH before the repository call. InvalidSignpostingData from the repository is caught and converted to HTTP 400.
* DELETE /admin/conditions/{condition_id}/signposting — removes the database row entirely. Idempotent. Returns 204 no body. Semantically distinct from PUT []: the row is deleted rather than updated, which preserves the distinction at the database level and in any future audit log, even though GET normalises both to null for current consumers.

Response normalisation rule: None and empty/whitespace-only strings are both returned as null in all responses.

Validation responsibility split:
* The router is the primary validation layer for HTTP input (types, whitespace, empty strings)
* The repository's own validation acts as a backstop but the router validates first
* condition_id is validated against the registry in the router; the repository has no knowledge of valid condition IDs and does not raise on unknown ones

Known limitation: the condition registry is immutable after startup. A new condition JSON file added to data/ while the server is running will return 404 from admin endpoints until the server is restarted. This is intentional.
This module must never import: clinical engine modules, presentation_service, serialisation, projection, runtime_state.

---

### 3.22 frontend/admin-ui/src/index.html — Admin frontend

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

### 3.23 availability_models.py — Availability data shapes
Location: app/models/availability_models.py
Data shapes only. No logic, no IO. No imports from service modules.
Contains:

AvailabilityConfig — represents the stored configuration from the
practice_availability table. Fields: practice_id, is_active,
weekly_open_days, open_time, close_time, closed_message.
Provides from_row(dict) class method for construction from a
database row. Extended in Stage 3 with override fields.
AvailabilityResult — return type of evaluate_availability(). Fields:
is_open, closed_message, after_hours_notice. Consumed by
GET /availability and the availability check inside POST /form/init.


### 3.24 availability_repository.py — Availability database access
Location: app/repositories/availability_repository.py
Database access only. No validation logic. No imports from service modules.
Public interface:

init_availability(practice_id) → None
Inserts a default row using INSERT ... ON CONFLICT DO NOTHING.
Called once at startup after the practice row exists.
get_availability(practice_id) → dict
Returns all columns. Raises ValueError if the row does not exist.
set_availability(practice_id, is_active, weekly_open_days, open_time,
close_time, closed_message) → None
Upsert via ON CONFLICT DO UPDATE. No validation — the caller must
call validate_availability_config() before calling this method.

This module must never:

Validate input (validation lives in availability_service.py)
Import service modules


### 3.25 availability_service.py — Availability evaluation logic
Location: app/services/availability_service.py
Pure logic. No database access. No IO. No imports from any project module
except app.models.availability_models. Fully testable without a database.
Public interface:

validate_availability_config(weekly_open_days, open_time, close_time,
closed_message) → None
Raises ValueError if weekly_open_days contains invalid values or
open_time == close_time. Does not validate open_time < close_time
(domain constraint, not validation rule). Does not validate empty
weekly_open_days (UI concern only).
evaluate_availability(config, now_utc) → AvailabilityResult
Takes an AvailabilityConfig and the current UTC datetime. Converts
to Europe/London time using zoneinfo. Returns AvailabilityResult.

Evaluation order (Stage 2):

If is_active is false: return open, no messages.
Convert now_utc to Europe/London.
Check day is in weekly_open_days.
Check time is >= open_time and < close_time (strictly less-than at
close_time — at exactly close_time the practice is closed).
If both pass: open, with after-hours notice constructed from close_time.
Otherwise: closed, with closed_message from config.

After-hours notice format: "Please note: forms submitted after {HH:MM}
will be reviewed on the next working day." Close time is formatted in
24-hour time (UK NHS convention).
Fail-open principle: this service is pure logic and never fails. The
fail-open behaviour is enforced by the callers in main.py, which wrap
the entire availability check (repository + service) in try/except and
proceed as open on any exception.
This module must never:

Access the database
Import repository modules
Make HTTP requests

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
* Patient-facing frontend served as built static files from frontend/dist/ in production, or via Vite dev server (port 5173) with API proxy to FastAPI (port 8000) in local development
* Admin frontend served as static file at /admin-portal/index.html


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

### 12.3 Data flow

The universal safety warning is fetched separately from condition presentation,
before condition selection, so it can be shown on the first screen the patient
sees. The two fetches serve different purposes and are deliberately kept apart.

**Pre-session safety gate (Screen 0):**
1. Patient accesses the form via the practice's website
2. GET /safety-warning called — returns the universal safety warning constant
3. Frontend renders the warning and requires checkbox confirmation before proceeding
4. Patient cannot continue until they confirm the warning does not apply to them

**Condition presentation (Screen 2):**
1. Patient selects a condition on Screen 1
2. GET /conditions/{id}/presentation called
3. presentation_service composes response:
   a. Fetches condition presentation from registry (immutable, in-memory)
   b. Fetches practice signposting from database using practice_id from app.state
   c. Returns composed dict (universal_safety_warning field still present for
      API backwards compatibility but is not displayed by the frontend here)
4. Frontend renders condition label, free_text_prompt, and practice_signposting

### 12.3 Data flow

1. Patient accesses the form via the practice's website
2. GET /conditions/{id}/presentation called
3. presentation_service composes response:
   a. Fetches condition presentation from registry (immutable, in-memory)
   b. Fetches practice signposting from database using practice_id from app.state
   c. Adds universal safety warning constant
   d. Returns composed dict
4. Frontend renders all three information types in distinct UI sections

## Section 13 — Frontend Error Handling

### 13.1 Design principles

* Patient input is never destroyed by a recoverable error
* Error classification happens at the API boundary, not in component logic
* Only genuinely unrecoverable situations escalate to a fatal screen
* Error messages are written for patients, not developers

### 13.2 Error classification

Two error states exist in the frontend:

**fatalError** — replaces the current screen entirely. Reserved for:
- Condition list fails to load on first visit (the form cannot be shown at all without this)
- Invalid internal state (e.g. EDIT screen reached without a runtime_id — should never occur in normal use)

**screenError** — displays an inline message on the current screen without disturbing any state. Used for all recoverable failures: network errors, 5xx responses, and 4xx responses on form submission endpoints. The patient can read the message and try again with their answers intact.

`screenError` is cleared automatically on every screen transition and cleared immediately when the patient begins editing after a failure.

### 13.3 ApiError class (api.ts)

All fetch calls are wrapped to throw `ApiError` rather than a plain `Error`. `ApiError` carries:
- `message` — the HTTP status string or "Network failure"
- `status: number | null` — the HTTP status code, or null for network-level failures where no response was received

This allows `friendlyErrorMessage(e)` to branch on status code and produce specific patient-facing text.

### 13.4 Error messages by status

| Condition | Message shown to patient |
|---|---|
| 409 | "Please check you do not have this form open in another tab. If you do, close the other tab and try again." |
| 5xx | "The server encountered a problem. Please try again in a moment." |
| Network failure (status null) | "Could not reach the server. Please check your internet connection and try again." |
| Any other error | "Something went wrong. Please try again." |

A 409 on a form endpoint means a session version conflict. The most likely cause in a single-patient deployment is the form being open in multiple tabs simultaneously.

### 13.5 What is and is not recoverable

| Screen | Failure point | Recovery |
|---|---|---|
| Screen 0 — loading safety warning | Fetch fails | Inline error with Try again button; no state to lose |
| Screen 1 — loading conditions | Fetch fails | Fatal — form cannot be shown without condition list |
| Screen 2 — loading presentation | Fetch fails | Inline error with Back and Try again buttons; condition selection preserved |
| Screen 2 — submitting free text | initForm fails | Inline error; free text preserved in state |
| Screen 3 — submitting answers | updateForm fails | Inline error; all answers preserved in editableAnswers |
| Screen 4 — final submit | finishForm fails | Inline error; review screen intact, patient can retry |

## Section 14 — Safety Gate

### 14.1 Purpose

Existing online consultation systems display a universal safety warning on
the first page the patient sees, before they have selected a condition or
begun filling in any form. This is the established NHS pattern and exists
for a clear reason: a patient experiencing a medical emergency should be
redirected to 999 or A&E before they have invested time filling in a form.

Displaying the warning after condition selection, as this system originally
did, is the wrong order. The patient has already spent time on the form.
Moving it to the first screen ensures no patient in an emergency proceeds
further than the first page.

### 14.2 Implementation

**New endpoint:** `GET /safety-warning`
- No authentication required
- No condition ID required
- No session required
- Returns `{"universal_safety_warning": "..."}` from the
  `UNIVERSAL_SAFETY_WARNING` constant in `presentation_service.py`
- The constant remains in exactly one place; this endpoint exposes it
  without duplicating it

**Frontend gate (Screen 0 — SAFETY_WARNING):**
- Warning text is fetched on mount via `getSafetyWarning()`
- A checkbox labelled "I confirm that none of the above apply to me" must
  be ticked before the Continue button is enabled
- While the checkbox is unticked, a red hint message reads:
  "If any of the above apply to you, please call 999 or go to A&E
  immediately. Do not use this form."
- Fetch failures show an inline error with a Try again button; no state
  is lost because no session exists yet at this point

### 14.3 Safety principle

The Continue button being disabled — rather than showing a warning and
allowing the patient to proceed anyway — is deliberate. A patient having
a heart attack should have no path to submitting an online form. The gate
is a hard block, not an advisory.

The checkbox confirmation creates a moment of active acknowledgement. The
patient must read the warning and make a positive declaration before the
form is accessible. This matches the pattern used by established NHS online
consultation platforms.

### 14.4 What did not change

- `UNIVERSAL_SAFETY_WARNING` constant location: still in `presentation_service.py`
- `GET /conditions/{id}/presentation` still returns `universal_safety_warning`
  in its response for API backwards compatibility, but the frontend no longer
  displays it there
- No changes to any clinical engine module
- No database changes

## Section 15 — Deployment

### 15.1 Platform

The application is deployed on Railway (railway.app). Railway provides a
single-server cloud environment that clones the GitHub repository, runs the
build script, and starts the server process. Deployments are triggered
automatically on every push to the main branch.

The original Nixpacks builder was replaced with a Dockerfile in March 2026
after Railway migrated to Railpack (their Nixpacks successor). Railpack
failed to generate a build plan for this project's mixed Python/Node
structure without a clear error message. A Dockerfile was the recommended
solution and gives complete control over the build environment.

railway.toml now contains only `builder = "DOCKERFILE"`. The Nixpacks
phase configuration it previously contained is no longer valid and has
been removed.

### 15.2 Build process

Stage 1 (frontend-build): Node 22 image. Installs npm dependencies from
frontend/package.json and runs npm run build, producing frontend/dist/.

Stage 2 (runtime): Python 3.12-slim image. Installs Python dependencies
from requirements.txt, copies app/, data/, and the built frontend/dist/
from stage 1. Starts uvicorn via the Dockerfile CMD.

The Vite build produces two entry points:
- dist/index.html — patient-facing form
- dist/admin-ui/index.html — admin portal

Both are served by the existing StaticFiles mount at / in main.py.
The previous admin/ directory (CDN-based standalone page) has been deleted.

### 15.3 Static file serving

In production, FastAPI serves the built frontend directly. On startup,
`main.py` checks whether `frontend/dist/assets` exists on disk. If it does,
it mounts the assets directory and registers a catch-all route that returns
`index.html` for all unmatched paths. This allows the React app to handle
its own client-side routing.

This check is filesystem-based, not DEV_MODE-based. In local development,
`frontend/dist` does not exist (the developer runs Vite separately), so
static file serving is automatically skipped. No code change is required
when switching between local and production environments.

The admin portal (backend/admin/index.html) is a standalone CDN-based page served 
by FastAPI's StaticFiles at /admin-portal. It is not part of the Vite build pipeline 
and must not be placed inside the frontend/ directory, which Vite processes on build.

The admin portal (admin-ui) is built by Vite as a second entry point and
output to dist/admin-ui/. It is served at /admin-ui/ by the same
StaticFiles mount as the patient form. The previous standalone
admin/index.html served at /admin-portal has been removed.

### 15.4 Database

The database is Postgres, managed by Railway as an add-on service.
The connection string is injected into the application as `DATABASE_URL`.
The previous SQLite approach (`runtime.db`, `DB_PATH`) has been removed.

All four repositories (RuntimeStateRepository, PracticeRepository, SubmissionRepository, AvailabilityRepository) accept database_url: str in their constructors.

#### Schema migrations (Alembic)

Schema migrations are managed by Alembic. `alembic_upgrade()` in
`app/core/db.py` runs `alembic upgrade head` at application startup,
applying any pending migrations before the application serves requests.
If a migration fails, the application fails to start. This is correct
behaviour — a failed migration must prevent startup.

Configuration:
- `alembic.ini` at the project root contains no secrets. The database URL
  is injected at runtime by `alembic/env.py` reading `DATABASE_URL` from
  the environment.
- `alembic/env.py` sets `target_metadata = None` (no SQLAlchemy ORM models).
  The advisory lock is enabled by default and must not be disabled.
- Migration files live in `alembic/versions/`. Each file contains
  `upgrade()` and `downgrade()` functions.

Migration workflow:
1. Write a new migration file in `alembic/versions/`.
2. Run `alembic upgrade head` locally against a test database to verify.
3. Push to main. Railway deployment runs migrations automatically at startup.

Rollback procedure:
To roll back a migration in production, run `alembic downgrade -1` (or to
a specific revision) manually against the live database, then redeploy the
older code version. There is no automated rollback mechanism. The
`downgrade()` functions in each migration file exist for this purpose.

Concurrent startup limitation:
Running migrations at application startup works for a single-developer,
single-instance deployment. If two Railway instances start simultaneously
(e.g. during a deployment overlap), concurrent migration attempts could
conflict. Alembic's default advisory lock mitigates this, but the behaviour
under contention is not well-documented for all Postgres configurations.
This is acceptable for now and must be revisited before scaling.

The initial migration (`0001_initial_schema.py`) uses `CREATE TABLE IF NOT
EXISTS` as a one-time concession because the database predates Alembic.
Future migrations must not use `IF NOT EXISTS`.

The previous `init_database()` function has been replaced by
`alembic_upgrade()`. `init_database()` is retained as deprecated in
`app/core/db.py` until `alembic_upgrade()` is confirmed working on Railway,
then it will be deleted.

JSONB columns: `state_json` (runtime_state_versions),
`clinical_output_json`, and `audit_output_json` (submission_records)
are stored as JSONB. psycopg2 does not automatically adapt plain Python
dicts to JSONB — all write paths wrap dicts in `psycopg2.extras.Json()`
explicitly. Read paths receive Python dicts directly from psycopg2 — no
`json.loads()` call is needed or correct.

### 15.4.1 signposting_json column format

The signposting_json column in practice_signposting stores a plain HTML
string. The column name is a legacy misnomer from the original
list-of-strings design. Do not assume the column contains JSON.

nh3 API constraint: the rel attribute on <a> tags is reserved by nh3
and injected automatically (default: 'noopener noreferrer'). Do not pass
rel through the attributes dict — nh3 will panic at runtime. The correct
call is:

    nh3.clean(
        raw,
        tags={...},
        attributes={"a": {"href", "target"}},
        url_schemes={"http", "https"},
    )

DOMPurify allowlist: SIGNPOSTING_PURIFY_CONFIG is defined once in
frontend/src/constants.ts and imported by both App.tsx and the admin
portal (admin-ui/src/SignpostingEditor.tsx). It must match the nh3
allowlist in practice_repository.py exactly. If the allowlist changes,
update both constants.ts and practice_repository.py.

### 15.4.2 Test database

Known gap: the repository integration tests (`tests/test_repositories.py`)
run against the same Railway Postgres instance as the deployed application.
There is no dedicated test database. Each test generates unique IDs and
cleans up rows in a finally block, but a buggy test could corrupt or delete
live data.

This is acceptable for a single-developer project at this stage. A
dedicated test database must be provisioned before a second developer joins
or before any real patient data is stored.

To run the tests locally, set `TEST_DATABASE_URL` in your `.env` file to
the `DATABASE_PUBLIC_URL` value from the Railway Postgres service dashboard
(the external-facing URL, not the internal `DATABASE_URL`). This file must
not be committed to version control.

    python -m tests.test_repositories

Migration 0002 (0002_availability_table.py):
Creates the practice_availability table with columns: practice_id (PK,
references practices), is_active (boolean, default false),
weekly_open_days (TEXT[], default '{}'), open_time (TIME, default '08:00'),
close_time (TIME, default '18:30'), closed_message (TEXT, nullable).
Includes a CHECK constraint on weekly_open_days using the Postgres <@
(contained by) operator to assert that every element is one of the seven
valid day abbreviations. This makes the database self-defending against
invalid values regardless of how the data is written. Application-layer
validation in availability_service.py still runs first and produces a
better error message for the caller; the constraint is the backstop.

### 15.5 Environment variables

The following environment variables must be set in the Railway dashboard:

| Variable        | Purpose                                                                  |
|-----------------|--------------------------------------------------------------------------|
| PRACTICE_ID     | Practice identifier, must match seeded record                            |
| DATABASE_URL    | Postgres connection string, injected automatically by Railway            |
| DEV_MODE        | Set to 1 to skip SMTP and ADMIN_TOKEN checks                             |
| DATA_DIR        | Path to condition JSON directory (data)                                  |
| PORT            | Injected by Railway. uvicorn binds to this port. Do not hardcode 8000.   |

DB_PATH has been removed. It was the SQLite file path and is no longer used.

PRACTICE_NAME and PRACTICE_EMAIL are optional. If not set, PRACTICE_NAME
defaults to the value of PRACTICE_ID and PRACTICE_EMAIL defaults to
demo@demo.net.

Local development requires a `.env` file (not committed to version control)
containing `TEST_DATABASE_URL` for running repository integration tests.

### 15.6 Current deployment mode

The hosted demo runs with DEV_MODE=1. This means:
- No emails are sent on form submission
- Admin endpoints accept any non-empty bearer token
- SMTP environment variables are not required

This is intentional for a demonstration deployment. DEV_MODE must be
removed and SMTP variables configured before the app is used for any
real clinical submissions.

## Section 16 — Availability enforcement

### 16.1 Overview

The availability system controls when the patient-facing form is open or
closed. It evaluates the current time against the practice's configured
schedule and returns a result that the frontend and form init endpoint
both consume.

The system is designed around a single principle: a failure in the
availability system must never prevent a patient from accessing the form.
Every failure path defaults to open.

### 16.2 Module responsibilities

#### availability_models.py (app/models/)

Data shapes only. No logic, no IO.

AvailabilityConfig: represents the stored row from practice_availability.
Constructed via `from_row(dict)` from the repository output. Includes
three optional override fields (override_status, override_expires_at,
override_message) added in Stage 3, all defaulting to None.

AvailabilityResult: the return type of `evaluate_availability()`. Contains
`is_open`, `closed_message`, and `after_hours_notice`. Both `GET /availability`
and the availability check inside `POST /form/init` consume this type.

`AvailabilityException`: represents a single row from the
`practice_availability_exceptions` table. Fields: `practice_id`,
`exception_date` (date), `exception_type` ("closed" or "custom_hours"),
`open_time` (optional time), `close_time` (optional time), `note`
(optional string). Has a `from_row(dict)` classmethod for construction
from a database row.

#### availability_repository.py (app/repositories/)

Database access only. No validation logic. No imports from service modules.

Methods:
- `init_availability(practice_id)`: inserts a default row using
  `INSERT ... ON CONFLICT DO NOTHING`. Called once at startup after the
  practice row exists.
- `get_availability(practice_id)`: returns all columns (including
  override columns) as a dict. Raises `ValueError` if the row does not
  exist.
- `set_availability(...)`: upserts the schedule config. No validation —
  the caller is responsible for calling `validate_availability_config()`
  first.
- `set_override(practice_id, override_status, override_expires_at,
  override_message)`: updates the three override columns. The caller
  is responsible for calling `validate_override()` first.
- `clear_override(practice_id)`: sets all three override columns to
  NULL. Idempotent — no error if no override was active.

- `get_exceptions(practice_id, from_date)`: returns all exception rows
  on or after `from_date`, ordered by date ascending. Used both by the
  evaluation path (which checks only today's exception) and by
  `GET /admin/availability/exceptions` (which displays all upcoming
  exceptions to the admin).
- `set_exception(practice_id, exception_date, exception_type, open_time,
  close_time, note)`: upserts a single exception row. No validation —
  the caller is responsible for calling `validate_exception()` first.
- `delete_exception(practice_id, exception_date)`: deletes a single
  exception row. Idempotent — no error if the row does not exist.

#### availability_service.py (app/services/)

Pure logic. No database access. No imports from any project module except
`app.models.availability_models`. Fully testable without a database.

`validate_availability_config()`: raises `ValueError` if `weekly_open_days`
contains invalid values or `open_time == close_time`. Does not validate
`open_time < close_time` (reversed times are a self-evident data entry
error given the domain constraint against overnight hours). Does not
validate empty `weekly_open_days` (that is a UI concern only).

`validate_override(status, expires_at, now_utc)`: raises `ValueError` if
status is not "open"/"closed", expires_at is null or timezone-naive,
expires_at is not in the future, or expires_at exceeds 24 hours from now.
The valid window is: now_utc < expires_at <= now_utc + 24 hours.

`deactivation_clears_override(is_active)`: returns True when is_active
is false, signalling that overrides should be cleared on deactivation.
The admin router calls this after PUT /admin/availability and, if true,
calls clear_override on the repository.

`validate_exception(exception_type, open_time, close_time)`: raises
`ValueError` if exception_type is not "closed"/"custom_hours"; if
custom_hours and either time is null; if closed and either time is not
null; if open_time == close_time; or if open_time >= close_time
(overnight hours are not supported — a reversed range would silently
never match any time in the evaluation logic, so this is rejected
explicitly).

`evaluate_availability(config, now_utc, exceptions=None)`: the
`exceptions` parameter defaults to `None`. Inside the function body,
`None` is replaced with an empty list. This avoids the mutable default
argument trap. The signature is backwards-compatible — existing callers
from Stage 3 continue to work without modification. Evaluation order is:
(1) is_active false: return open with no messages.
(2) Active override (override_status not null and expires_at > now_utc):
force-open returns open with after-hours notice; force-closed returns
closed with override_message (falling back to closed_message via
explicit is-not-None check).
(3) Per-date exception for today (Europe/London date): if exception_type
is "closed", return closed with config closed_message; if "custom_hours",
evaluate exception open_time/close_time against current London time.
After-hours notice is constructed from the exception's close_time for
custom_hours, or null for closed exceptions.
(4) Weekly schedule: converts UTC to Europe/London, checks day and time.

Dependency rules:
- availability_service must NOT import any repository module
- availability_service must NOT import any clinical engine module
- availability_service must NOT perform any IO

### 16.3 Fail-open design

The fail-open principle applies at every boundary:

`GET /availability`: if the database raises an exception, the exception
propagates and FastAPI returns HTTP 500. The frontend treats any non-200
response as fail-open and shows the form as normal.

`POST /form/init`: the availability check is wrapped in a try/except. If
any exception is raised during the check, it is logged and the request
proceeds as if the practice is open. If the check succeeds and the
practice is closed, the endpoint returns HTTP 503 with the closed message.

`POST /form/update` and `POST /form/finish`: these do not check
availability. Once a patient has been granted a session via `POST /form/init`,
they can complete and submit the form regardless of whether the practice
has since closed. This is the humane choice — a patient halfway through
a form should not have their work discarded.

`POST /form/finish` now returns a `submitted_after_hours` boolean. After
the existing finish logic completes, `check_availability` is called in a
try/except. If the result's `is_open` is false, `submitted_after_hours`
is true. If the check fails or the result is open,
`submitted_after_hours` is false. Uncertainty must not alarm the patient.
The response shape is: `{"submission_id": "...", "submitted_after_hours": true|false}`.

Frontend availability fetch failure: if `GET /availability` fails for any
reason (network error, any non-200 response including 500), the frontend
shows the form as normal with no closed message banner and no after-hours
notice.

### 16.4 is_active = false behaviour

When `is_active` is false, the practice has not opted in to schedule
enforcement. `GET /availability` returns `is_open: true` with null
messages. The form behaves as if availability does not exist. This is the
default state after `init_availability()` inserts the default row.

### 16.5 After-hours notice

When the practice is open and `is_active` is true, the service constructs
a notice string from the config's `close_time`: "Please note: forms
submitted after [HH:MM] will be reviewed on the next working day." The
time is formatted in 24-hour notation, the standard convention for UK
NHS systems. When the practice is closed, `is_active` is false, or there
is no meaningful close time to reference, `after_hours_notice` is null.

When a per-date exception with custom_hours is active and the practice
is open, the after-hours notice is constructed from the exception's
close_time, not the config's close_time. This reflects the actual
closing time for that day. When a per-date exception with type "closed"
is active, after_hours_notice is null (the practice is closed all day).

### 16.6 Timezone handling

All availability evaluation converts UTC to Europe/London time using
`zoneinfo.ZoneInfo("Europe/London")`. This correctly handles GMT/BST
transitions. The `tzdata` package is in `requirements.txt` to ensure
reliable timezone data on the Railway container.

`open_time` and `close_time` are stored as TIME columns in Postgres.
psycopg2 maps these to `datetime.time` objects automatically on read.
These times are always interpreted in Europe/London local time.

Overnight opening hours are not supported. An overnight service (where
`open_time > close_time`) is by definition an urgent or out-of-hours
service with different clinical logic. The evaluation assumes
`open_time < close_time` and this is an intentional domain constraint.

### 16.7 Database schema

Table `practice_availability` (created by migration 0002, extended by
migration 0003):

    practice_id          TEXT PRIMARY KEY REFERENCES practices(practice_id)
    is_active            BOOLEAN NOT NULL DEFAULT false
    weekly_open_days     TEXT[]  NOT NULL DEFAULT '{}'
    open_time            TIME   NOT NULL DEFAULT '08:00'
    close_time           TIME   NOT NULL DEFAULT '18:30'
    closed_message       TEXT
    override_status      TEXT CHECK (override_status IN ('open', 'closed'))
    override_expires_at  TIMESTAMPTZ
    override_message     TEXT

The three override columns (added by migration 0003) are all nullable.
A null override_status means no override is active.

The `weekly_open_days` column has a CHECK constraint using the Postgres
`<@` operator to assert that every element is one of the seven valid day
abbreviations (mon, tue, wed, thu, fri, sat, sun). Application-layer
validation in `availability_service.py` runs first and produces a better
error message; the database constraint is the backstop.

Table `practice_availability_exceptions` (created by migration 0004):
 
    practice_id     TEXT NOT NULL REFERENCES practices(practice_id)
    exception_date  DATE NOT NULL
    exception_type  TEXT NOT NULL CHECK (exception_type IN ('closed', 'custom_hours'))
    open_time       TIME
    close_time      TIME
    note            TEXT
    PRIMARY KEY (practice_id, exception_date)
 
The composite primary key ensures one exception per practice per date.
`open_time` and `close_time` are nullable — they are required for
custom_hours exceptions and must be null for closed exceptions.
Application-layer validation in `availability_service.py` enforces this;
the database does not have a cross-column constraint.

### 16.8 Startup sequence

The startup sequence in `main.py` is:

1. `alembic_upgrade()` — runs pending migrations (creates the table if
   migration 0002 has not yet run)
2. `_validate_startup(practice_repo)` — seeds the practice row if absent
3. `availability_repo.init_availability(practice_id)` — inserts the
   default availability row if absent

There is never a state where the availability row does not exist after
startup.

`GET /admin/availability/exceptions`: returns all exceptions on or after
today's date (Europe/London time), ordered by date ascending. This
includes today's exception if one exists — the admin needs to verify
what is currently active. The `from_date` passed to the repository is
today in Europe/London time, the same as the evaluation path. Requires
admin auth.
 
`PUT /admin/availability/exceptions/{date}`: creates or updates an
exception for the given date (YYYY-MM-DD format in the URL path).
Accepts `exception_type` ("closed" or "custom_hours"), `open_time` and
`close_time` (HH:MM strings or null), and `note` (string or null).
Validates via `validate_exception` in the service layer. Returns the
stored exception. Returns HTTP 400 if validation fails or the date
format is invalid.
 
`DELETE /admin/availability/exceptions/{date}`: deletes the exception
for the given date. Idempotent — no error if no exception existed.
Returns 204 No Content.

### 16.9 Admin endpoints

`GET /admin/availability`: returns the raw config dict with times
formatted as HH:MM strings and override_expires_at as ISO string.
Requires admin auth. Does not call `evaluate_availability`.

`PUT /admin/availability`: accepts the schedule config, validates via
the service layer, persists via the repository, and returns the updated
config. Logs a warning if `is_active` is true and `weekly_open_days` is
empty. If `is_active` is set to false, auto-clears any existing override
(sets all three override columns to NULL). Returns HTTP 400 if
validation fails.

`POST /admin/availability/override`: sets a manual force-open or
force-closed override. Accepts `status` ("open" or "closed"),
`expires_at` (timezone-aware ISO datetime string), and `message`
(string or null). Validates via `validate_override` in the service
layer. Rejects timezone-naive expires_at with HTTP 400. Returns the
updated raw config.

`DELETE /admin/availability/override`: clears any active override by
setting all three override columns to NULL. Idempotent — no error if
no override was active. Returns the updated raw config.

### 16.10 Banned imports

The following import rules apply to the availability modules:

- availability_service must NOT import any repository or IO module
- availability_repository must NOT import availability_service
- availability_models must NOT import any service or repository module
- admin_router may import availability_service for validation only
- Clinical engine modules (form_logic, safety_engine, encoder_mapping,
  encoder_stub, projection, serialisation) must NOT import any
  availability module — the clinical engine has no awareness of
  practice scheduling

### 16.11 Testing

Unit tests for `availability_service.py` live in
`tests/test_availability_service.py`. They test the pure logic with no
database. All tests construct `AvailabilityConfig` directly and pass
controlled UTC datetimes.

Tests 1-7 cover Stage 2: schedule evaluation, config validation, and
the fail-open pattern.

Tests 8-15 cover Stage 3: force-open override, force-closed with
override message, null message fallback to closed_message, empty string
message preserved (not fallback), expired override fallthrough to
schedule, timezone-naive expires_at rejection, is_active=false ignoring
force-closed override, and auto-clear on deactivation.

Additional boundary tests cover: exact open/close time boundaries, BST
offset effects, and override expiry edge cases.

Run with: `python -m tests.test_availability_service`

### 16.12 Manual override design
 
The override system allows an admin to temporarily force the form open or
closed regardless of the weekly schedule. This is designed for emergency
closures, staff training days, or extending access outside normal hours.
 
#### Override expiry
 
`override_expires_at` is always required when setting an override. Null is
not permitted. The valid window is `now_utc < override_expires_at <=
now_utc + 24 hours`. A non-null `override_expires_at` that has passed is
treated as no override — the evaluation falls through to the weekly
schedule. Expiry is strictly less-than: at exactly `override_expires_at`,
the override is no longer active.
 
#### Timezone requirement for expires_at
 
The admin UI submits `expires_at` as a UTC ISO string. The backend rejects
timezone-naive datetime strings with a clear error message. During BST, a
London-local time submitted without an offset would be stored as if it
were UTC, causing the override to expire one hour late.
 
#### Auto-clear on deactivation
 
When `PUT /admin/availability` sets `is_active` to false, any existing
override is cleared (all three override columns set to NULL). This
prevents stale override data from silently taking effect if the admin
later re-enables `is_active`. The logic is split: the service layer
function `deactivation_clears_override` returns a boolean, and the admin
router calls `clear_override` on the repository when true. The repository
writes only what it is told.
 
#### Override message fallback chain
 
When an override is active and `override_status` is `"closed"`:
(1) If `override_message is not None` (including empty string `""`): use
`override_message`. (2) If `override_message is None`: use
`closed_message`. (3) If both are None: return None. The explicit
`is None` check ensures that an empty string configured as the override
message is treated as an intentional choice, not as absent.
 
#### Admin portal override display
 
Active override is determined in JavaScript:
`override_status !== null && new Date(override_expires_at) > new Date()`.
`Date.now()` is UTC-safe. Local time must not be used for this comparison.
 
When displaying `override_expires_at` to the admin, the timestamp is
formatted in Europe/London local time using `Intl.DateTimeFormat` with
`timeZone: "Europe/London"`. This ensures correctness during BST.
 
#### Force-open after-hours notice
 
When a force-open override is active, the after-hours notice is still
constructed from the config's `close_time`. The override is temporary and
the patient should still be aware of the normal schedule.
 
### 16.13 Migration history
 
| Migration | Description |
|---|---|
| 0001 | Initial schema: four existing tables with IF NOT EXISTS |
| 0002 | availability table |
| 0003 | availability override |
| 0004 | practice_availability_exceptions table (per-date exceptions) |

### 16.14 Per-date exceptions design
 
The exception system allows an admin to define per-date schedule
overrides for specific dates — either closing the practice entirely or
running custom hours. This is designed for bank holidays, staff training
days, or one-off extended hours.
 
#### Exception types
 
`closed`: the practice is closed all day. `open_time` and `close_time`
must be null. The service returns `closed_message` from the config (not
from the exception — exceptions do not carry their own closed message).
 
`custom_hours`: the practice is open during different hours than the
weekly schedule. Both `open_time` and `close_time` are required.
Overnight hours are not supported (same domain constraint as the weekly
schedule). The after-hours notice is constructed from the exception's
close_time, not the config's close_time.
 
#### Evaluation priority
 
The evaluation order is: override > exception > weekly schedule. An
active override always takes priority over an exception on the same day.
This is intentional — if an admin sets a force-open override during a
bank holiday exception, the override wins.
 
#### Exception date lookup
 
`get_exceptions()` is called with today's date in Europe/London time,
not UTC. Using the UTC date would miss exceptions that begin at midnight
London time on days not yet reached in UTC. The same repository method
is used both by the evaluation path and by the admin GET endpoint. The
evaluation logic takes the first matching entry for today and ignores
the rest.
 
#### check_availability orchestration function
 
`check_availability(availability_repo, practice_id, now_utc)` is
defined in `main.py`. It owns the full evaluation pipeline: fetch
config, compute today's London date, fetch exceptions, call
`evaluate_availability`. This function does not belong in
`availability_service.py` because the service layer has no database
access. Both `GET /availability` and the availability check inside
`POST /form/init` call `check_availability`. The fail-open try/except
wrapping lives in `main.py` around the call to `check_availability`.
 
#### Submitted-after-hours flag
 
`POST /form/finish` returns `submitted_after_hours` (boolean). After
the existing finish logic, `check_availability` is called in a
try/except. If the result's `is_open` is false, the flag is true. If
the check fails or the result is open, the flag is false. The frontend
uses this flag to display an appropriate confirmation message on the
submission screen. Uncertainty defaults to false — must not alarm the
patient.
 
#### Note field
 
Each exception has an optional `note` field (free text). This is for
admin reference only (e.g. "Bank holiday", "Staff training afternoon").
The note is not shown to patients and is not used in evaluation logic.
| 0002 | practice_availability table (weekly schedule, closed message) |
| 0003 | Three override columns on practice_availability |

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


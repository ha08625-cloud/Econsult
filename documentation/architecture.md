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

## 2. High‑Level Architecture

The system is structured as a linear pipeline composed of strictly separated modules.

Request
  ↓
Pipeline (ordering only)
  ↓
Form Logic (deterministic core)
  ↓
Serialization (clinical / audit views)

No module other than the pipeline is aware of execution order.

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
* Extracts encoder definitions (encoder‑facing contract), signal → answer_key mappings

Rules:
* Rulesets are authoritative
* Encoder metadata lives in the ruleset
* All mappings are explicit and precomputed

### 3.3 encoder_stub.py — Replaceable encoder façade

Responsibilities:
* Accept free text + encoder definitions
* Emit {signal_id: true | false | null}

Constraints:
* Encoder never sees rules, questions or answers, RuntimeState
* Encoder output is non‑authoritative
* Stub logic is intentionally naive
* This module is expected to be deleted and replaced by a real encoder without impacting any other module.

### 3.4 encoder_mapping.py — Encoder containment layer

Responsibilities:
Apply encoder output to RuntimeState
Enforce provenance rules
Preserve raw encoder output for audit

Rules:

Encoder never overwrites patient input
Encoder only populates unanswered fields
Mapping failures are fatal
Encoder influence is fully contained in this module

This is the regulatory boundary between inference and clinical data.

### 3.5 form_logic.py — Deterministic functional core

Responsibilities:
Initialise runtime state
Hydrate runtime state on submission
Apply patient updates
Normalise provenance on submit
Evaluate safety rules

Rules:
No encoder access
No IO
No serialization
No sequencing

This module can be fully unit tested without the pipeline or encoder.

### 3.6 serialization.py — Output views

Responsibilities:
Produce clinical output (lossy)
Produce audit/debug output (lossless, later)

Rules:

Serialization never mutates state
Clinical output excludes encoder internals

### 3.7 pipeline.py — Thin coordinator

Responsibilities:
Define execution order only
Wire modules together
Provide entry points for API / UI

Rules:
No business logic
No clinical decisions
No state persistence

Linear flow only


## 4. Data flow

### 4.1 Form initialisation

Load ruleset
Initialise RuntimeState
Extract encoder definitions and mappings
Run encoder (if free text present)
Apply encoder mapping
Return canonical RuntimeState

### 4.2 Form submission

Hydrate and validate RuntimeState
Normalise encoder provenance
Evaluate safety rules (explicit answers only)
Serialize clinical output

## 5. Encoder logic

Encoders:
* Run once on initial free text
* Output partial `{signal_id: true|false|unknown}` map
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

## 6. Safety architecture

Safety rules live in the ruleset
Safety consumes explicit answers only
Encoder output is ignored by safety
Safety logic is deterministic and inspectable
This guarantees encoder failure cannot cause unsafe advice.

## 7. State and statelessness

* No server‑side session storage
* No per‑user memory
* State exists only:
* In memory during a request
* In client‑supplied canonical RuntimeState

### 7.1 Canonical runtime state (lossless, backend)

Purpose:
* The system operates on a canonical RuntimeState object that represents the full, lossless state of a form at a point in time
* For the MVP, this state may be round-tripped via the client. In later versions it will be server-owned and versioned
* RuntimeState supports multiple submit events over time, each producing an independent safety evaluation for debugging, model evaluation, audit trail and safety incident investigation

Contains:
* free text input
* encoder raw outputs
* encoder → answer mappings
* answer values
* answer sources (encoder vs patient)
* rule evaluation results
* timestamps
* ruleset version

Properties:
* backend-owned
* append-only or versioned
* restricted access, retention-limited (30 days default) and de-identified
* This is an engineering and safety artefact, not a medical record.

### 7.2 Clinical output state (lossy, portable)

Purpose:
* clinician review
* patient copy
* EHR ingestion

Contains:
* final answers only
* free text (verbatim)
* safety message text shown

Excludes:
* encoder signals
* answer provenance
* rule evaluation traces
* internal metadata

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

Log warning but don't fail loudly
* If source if direct_answer, then signal_id, encoder_prompt and signal_type must be null (incorrect but not dangerous)

---

## 10. Visibility Semantics

* All questions are shown after free text and encoder run
* No questions are suppressed or hidden

However:
* Visibility rules are still part of the engine design
* Future versions may activate them without refactor
* Explicit answers persist even if visibility changes later.

---

## 11. Scope of Stage 1 MVP

* One condition (urinary symptoms), three answer fields: dysuria (boolean), fever (boolean), onset (free text)
* All questions visible
* One safety message (fever=true => speak to doctor immediately)
* No ML dependency

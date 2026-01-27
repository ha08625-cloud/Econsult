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

### Backend

* Condition definition loader (JSON)
* Deterministic form rules engine
* Safety net evaluation engine
* Stateless API: submit answers → return form state
* Audit logging

### Frontend

* Generic renderer driven entirely by server response
* Displays suggested vs explicit answers distinctly
* Allows all suggestions to be overridden by user
* Does not evaluate clinical logic

---

## 3. Data flow

**UI phase 1**
* Patient selects condition
* Patient enters optional free text
* No questions yet

**Engine initialisation**
* Engine loads condition definition
* Engine runs encoder once, using: patient's free text input, encoder-related metadata from ruleset

**Prefill phase**
* Encoder outputs suggested values
* Engine maps suggestions → answer fields
* Answer state now contains: suggested answers, unanswered fields

**UI phase 2**
* Full form rendered
* Suggested answers visibly marked
* Patient edits or confirms
* Submission
* Only answers are submitted
* Encoder output is not re-used (output is for debugging and quality control only)

**Safety evaluation**
* Engine evaluates safety rules using answers only
* Safety messages rendered in UI

## 4. Clinical ruleset structure

{
  "question_id": "urinary_symptoms_1",    # unique identifier
  "question": "Are you experiencing pain when passing urine?",    #the question that is shown on the patient-facing UI
  "send_to_encoder": "true",    # Is this question suitable for encoder extraction
  "encoder_prompt": "Does the response indicate there is pain when passing urine?",    # the prompt that is fed to the encoder
  "answer_field": "empty",    # The end answer
  "answer_source": "empty",    # Initially empty, then filled with encoder or direct answer depending on source
  "answer_type": "Boolean"    # Tri-state output: Encoder extracts true/false/empty
},
{
  "question_id": "urinary_symptoms_2", 
  "question": "When did the symptoms start?",
  "send_to_encoder": "false",    # This question is not suitable for encoder extraction - patient directly answers only
  "encoder_prompt": "null",
  "signal_type": "null",
  "answer_field": "empty",
  "answer_type": "text"    # Patients can answer in text, encoders can only answer Booleans
}

**Key decisions**
* One question_id can map onto 0 or 1 signal_id - some questions can't be extracted easily by encoders e.g. When did the symptoms start?
* One signal_id can only map onto one question_id - this is not classical NLP, this is a simple form filling accelerator. More than one question to a signal invites complexities around contradiction detection and resolution
* The only source of information is the patient - signals can be derived from encoders reading free text or direct input from the patient.  Information from other sources, e.g. EHRs, is not within the scope of this project
* Signals should never exist without Questions
* The question and the encoder prompt are different wordings of the SAME clinical concept optimised for different consumers (one human, one ML) - if one changes, the other MUST be reviewed or they may diverge dangerously

---

## 5. Validation and Failure Semantics

Rulesets are validated at load time.
Fail‑fast, fail-loud conditions include:
* Safety rule referencing absent or invalid answer_field
* Duplicate or unstable IDs
* Invalid rule expressions
* If send_to_encoder = true, then encoder_prompt must not be null and answer_type must be Boolean

Log warning but don't fail loudly
* If source if direct_answer, then signal_id, encoder_prompt and signal_type must be null (incorrect but not dangerous)

---

## 6. Visibility Semantics

* All questions are shown after free text and encoder run
* No questions are suppressed or hidden

However:

* Visibility rules are still part of the engine design
* Future versions may activate them without refactor

Explicit answers persist even if visibility changes later.

---

## 7. Encoder Integration (Deferred Logic)

Encoders:

* Run once on initial free text
* Output partial `{signal_id: true|false|unknown}` map
* Do not see questions
* Use `encoder_prompt` as a clinical definition, not an instruction

Encoder output:

* Is clearly marked as suggested
* Can be overridden
* Is never authoritative

---

## 8. State (information storage)

Two state views: canonical runtime state and clinical output state

Runtime state exists only in memory:
* On the server during a single request
* It is never written as a “runtime object”
* At submission time, you generate two outputs:
* clinical output (lossy)
* debugging / audit output (lossless)

8.1 Canonical runtime state (lossless, backend)

Purpose:
* debugging and model evaluation
* audit trail and safety incident investigation

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
* not used for clinical care
* restricted access
* retention-limited (30 days default)
* De-identified (to reduce data protection issues)
* This is an engineering and safety artefact, not a medical record.

2.2 Clinical output state (lossy, portable)

Purpose:
* clinician review
* patient copy
* EHR ingestion

Contains:
* final answers only
* free text (verbatim)
* safety message text shown

Explicitly excludes:
* encoder signals
* answer provenance
* rule evaluation traces
* internal metadata
* This is the clinical artefact.

---

## 9. Backend Technology Choice

Python is chosen for MVP because:

* Strong JSON handling
* Clear, testable rules evaluation
* Fast iteration

Rules evaluation:

* Declarative
* Boolean‑only
* No general‑purpose DSL
* No dynamic code execution

---

## 10. Scope of Stage 1 MVP

* One condition (urinary symptoms), three answer fields: dysuria (boolean), fever (boolean), onset (free text)
* All questions visible
* One safety message (fever=true => speak to doctor immediately)
* No ML dependency

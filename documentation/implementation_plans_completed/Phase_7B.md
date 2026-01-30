## Phase 7 — Provisional Plan: Minimal Frontend Renderer

### Phase intent

Build a **server-driven, stateless UI renderer** that:

* Renders backend-provided form state verbatim
* Collects explicit patient intent
* Submits intent back to the server
* Displays blocking feedback
* Never owns truth

No optimisation. No abstraction. No anticipatory logic.

---

## 1. Scope definition

### In scope

* Four screens exactly, mapped 1:1 to backend semantics
* Rendering of `ClientStateView` only
* Submission of `ClientAnswerReturn` only
* Display of safety messages as blocking artefacts
* Version handling for optimistic concurrency (UX only)

### Explicitly out of scope

* Any derivation, inference, or state reconciliation
* Any local validation beyond “required answered”
* Any client-side branching or conditional display
* Any persistence beyond in-memory session data
* Any interpretation of safety rules

This is a renderer, not a form engine.

---

## 2. Screen flow (fixed)

### Screen 1 — Session initialisation

**Purpose**

* Collect presenting condition
* Collect free-text description

**Action**

* POST `/form/init`

**Constraints**

* Callable once
* Free text sent verbatim
* No preview, no validation, no retries

**Output consumed**

* `ClientStateView`
* `runtime_id`
* `version`

---

### Screen 2 — Editable question entry

**Purpose**

* Collect explicit answers

**Input**

* `ClientStateView`

**UI behaviour**

* Render questions in order
* Render current values
* Visually mark suggested answers
* Allow editing of all answers
* Remove “suggested” marker locally on edit

**Local enforcement**

* All required questions must be answered before submit (UX only)

**Action**

* POST `/form/update` with `ClientAnswerReturn`

**Repeatable**

* Yes

---

### Screen 3 — Review + safety gate

**Purpose**

* Read-only review
* Safety enforcement

**Input**

* `ClientStateView`
* `safety_messages` (if any)

**UI behaviour**

* No editing
* Display safety messages verbatim
* If safety present: block final submission

**Actions**

* Back → Screen 2
* Submit → POST `/form/finish` (only if no safety)

---

### Screen 4 — Terminal

**Purpose**

* End session

**Behaviour**

* No actions
* No navigation
* No retries

---

## 3. Data contracts (frontend truth boundaries)

### 3.1 ClientStateView (read-only render contract)

Frontend treats this as **opaque, authoritative, immutable**.

Responsibilities:

* Render all questions
* Respect ordering
* Respect `required`
* Display `suggested` markers
* Never infer meaning from values

No caching. No diffing. No mutation.

---

### 3.2 ClientAnswerReturn (intent-only submission)

Frontend submits **only what the user explicitly asserts**.

Rules enforced client-side:

* All required present
* Types correct
* No extra keys

Rules not enforced client-side:

* Clinical validity
* Safety
* Completeness beyond required

---

### 3.3 Safety messages

Frontend treats safety messages as:

* Blocking
* Read-only
* Non-negotiable

No explanation. No mitigation. No UI cleverness.

---

## 4. State handling model (minimal)

Frontend may store, in memory only:

* `runtime_id`
* `version`

Used exclusively for:

* Submission payloads
* Detecting fatal 409

On version conflict:

* Show fatal error
* Restart entire flow

No retry logic. No reconciliation.

---

## 5. Architectural constraints (non-negotiable)

* Frontend is stateless relative to clinical meaning
* Backend is the single source of truth
* ClientStateView is never reconstructed client-side
* No form library that assumes local ownership of state
* No speculative UI behaviour

Violating any of these collapses Phase 6 guarantees.

---

## 6. Deliverables for Phase 7 (planning level)

### Required artefacts

1. Screen flow diagram (4 screens, fixed)
2. Endpoint ↔ screen mapping table
3. ClientStateView JSON schema + concrete example
4. ClientAnswerReturn JSON schema + concrete example
5. Safety message example payload
6. Version conflict example payload

No design system. No styling system. No component abstraction yet.

---

## 7. Known risks to call out early

* React form libraries that assume bidirectional state ownership
* “Helpful” local diffing of answers
* Attempting to cache ClientStateView
* Treating suggested answers as defaults rather than advisory

All of these are regressions.

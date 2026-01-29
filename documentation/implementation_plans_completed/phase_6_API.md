# Phase 6 — API Wrapper with Canonical Server-Side State

## Purpose

Expose the deterministic form engine over HTTP while preserving canonical RuntimeState integrity, auditability, and clinical safety.
Earlier plans assumed a stateless API. This was rejected due to audit, security, and validation risks. Phase 6 therefore introduces **server-side RuntimeState persistence in the MVP** to avoid later architectural refactors.
RuntimeState is server-owned, versioned, and authoritative. Clients interact only through constrained, render-safe and intent-only data structures.

---

## Architectural stance

* RuntimeState is **canonical, backend-owned, and lossless**
* The client never invents, mutates, signs, or round-trips RuntimeState
* The server is the sole authority for:
  * runtime identity
  * versioning
  * provenance transitions
  * safety evaluation
* Persistence is minimal, append-only or versioned
* No conversational memory
* No hidden workflow
* No cross-user or cross-request behavioural state
This is a **stateful system**, but not a session- or conversation-driven one. It is a deterministic engine with durable inputs.

---

## RuntimeState persistence model

Each RuntimeState instance is stored server-side with:

* `runtime_id` (UUID, server-generated, unguessable)
* `ruleset_hash`
* `version` (monotonic integer)
* `created_at`
* `last_modified_at`
* full RuntimeState payload (lossless)

Rules:

* RuntimeState is never mutated in place
* Each update creates a new version
* Previous versions remain accessible for audit/debug
* No update or evaluation deletes or invalidates state

This enables:

* safe back-navigation
* hard failure on conflicts
* auditability
* future model and safety evaluation

RuntimeState is an **engineering and safety artefact**, not a medical record. Production retention (30 days) is deferred to later stages.

---

## Client-facing data contracts

### ClientStateView (server → client)

A render-only projection of RuntimeState.
Purpose:

* Render questions and answers
* Indicate which values were suggested
* Drive frontend completeness checks

Properties:

* Derived from RuntimeState
* Lossy by design
* Structurally incapable of being used as input
* Never accepted by any endpoint

Contains (illustrative):

* question text
* answer_key
* current value
* required flag
* suggested flag

Explicitly excludes:

* provenance enums
* encoder internals
* raw signals
* safety logic
* internal metadata

---

### ClientAnswerReturn (client → server)

An intent-only structure representing **explicit patient input**.

Purpose:

* Express user intent unambiguously
* Avoid inference via diffing or state comparison

Properties:

* Contains only keys the patient explicitly answered or changed
* Absence of a key means “no change”
* Every provided value is treated as `source=patient`

Contains:

* `answer_key → value`

Never contains:

* provenance
* full state
* encoder information
* free text

---

## API Endpoints

### POST /form/init

**Purpose**
Create a new RuntimeState (version 1) for a selected condition.

**Inputs**

```json
{
  "condition_id": "string",
  "free_text": "string | null"
}
```

**Behaviour**

* Load and validate ruleset
* Initialise RuntimeState with all answer_keys present
* Run encoder once (if free_text present)
* Apply encoder mapping
* Persist RuntimeState (version = 1)
* Generate ClientStateView

**Outputs**

```json
{
  "runtime_id": "string",
  "version": 1,
  "client_state": ClientStateView
}
```

**Invariants**

* Encoder runs exactly once
* Encoder output is frozen permanently
* `free_text` exists only at init
* `/form/update` schema must not allow free_text
* Changing free text requires a new runtime_id

---

### POST /form/update

**Purpose**
Apply patient answer changes, normalise provenance, and automatically evaluate safety.

**Inputs**

```json
{
  "runtime_id": "string",
  "base_version": number,
  "answers": ClientAnswerReturn
}
```

**Behaviour**

* Load latest RuntimeState for runtime_id
* Reject if `base_version != latest_version` (409 Conflict)
* Validate ruleset hash
* Apply patient answers (`source=patient`)
* Normalise encoder provenance:

  * remaining encoder → encoder_confirmed
  * overwritten encoder → encoder_corrected
* Validate that all required questions are answered
* Create new RuntimeState version
* Persist
* Project → ExplicitAnswers
* Run safety engine
* Generate ClientStateView

**Outputs**

```json
{
  "runtime_id": "string",
  "version": number,
  "client_state": ClientStateView,
  "safety_messages": [...]
}
```

**Notes**

* This endpoint is safety-critical
* Partial or incomplete states are rejected
* Auto-merge is forbidden
* Safety is never optional or deferrable

---

### POST /form/finish

**Purpose**
Final, irreversible submission after safety has been shown to the patient.

**Inputs**

```json
{
  "runtime_id": "string",
  "version": number
}
```

**Behaviour**

* Load RuntimeState
* Reject if version is not latest
* Optionally re-run safety defensively
* Serialize clinical output
* Hand off to downstream system (out of scope)

**Outputs**

```json
{
  "clinical_output": ...
}
```

This endpoint marks the end of Phase 6 responsibility.

---

## Failure semantics

Fail loud and early on:

* invalid runtime_id
* missing or invalid version
* ruleset_hash mismatch
* illegal provenance transitions
* malformed ClientAnswerReturn
* incomplete required answers
* concurrent modification conflicts

UX expectation:

* user is notified
* form may need to restart
* no silent recovery

Clinical ambiguity is never auto-resolved.

---

## UI flow (informative, non-binding)

1. **Screen 1 — Init**

   * condition + free text
   * `/form/init`
2. **Screen 2 — Edit**

   * all questions required
   * `/form/update`
   * safety evaluated automatically
3. **Screen 3 — Review**

   * read-only answers
   * safety messages always visible
4. **Final submit**

   * `/form/finish`

---

## Explicit non-goals (Phase 6)

* Authentication or authorisation
* Session management
* UI implementation
* Ruleset migration
* Multi-condition support
* Retention enforcement
* EHR integration

---

## Implementation goals (Phase 6 deliverables)

* HTTP API exposing the existing engine
* Server-side RuntimeState persistence
* ClientStateView projection
* ClientAnswerReturn ingestion
* Safety evaluated automatically on update
* Explicit invariants enforced in code

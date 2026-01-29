# Phase 6A — API Semantics and workflow invariants (architecture only, not implementation)

## Purpose

Expose the deterministic form engine over HTTP while preserving canonical RuntimeState integrity, auditability, and clinical safety.

Earlier plans assumed a stateless API. This was rejected due to auditability, safety, and validation risks. Phase 6 therefore **introduces server-side RuntimeState persistence into the MVP** to avoid later architectural refactors.

RuntimeState is server-owned, versioned, and authoritative. Clients interact only through constrained, render-only projections and intent-only input structures.

---

## Architectural stance

* RuntimeState is **canonical, backend-owned, and lossless**
* The client never invents, mutates, signs, or round-trips RuntimeState
* The server is the sole authority for:

  * session identity (`runtime_id`)
  * versioning and conflict detection
  * provenance transitions
  * safety and advisory evaluation
* Persistence is append-only or versioned
* No conversational memory
* No hidden workflow
* No cross-user behavioural state

This is a **session-backed system**.

A *session* is defined as a server-owned, versioned workflow instance identified by `runtime_id`. It is unauthenticated, single-user, short-lived, and deterministic. The absence of authentication does not make the system stateless.

---

## RuntimeState persistence model

Each session (RuntimeState instance) is stored server-side with:

* `runtime_id` — UUID, server-generated, unguessable
* `ruleset_hash`
* `version` — monotonic integer **per runtime_id**
* `created_at`
* `last_modified_at`
* full RuntimeState payload (lossless)

### Rules

* RuntimeState is never mutated in place
* Each successful update creates a new version
* Version numbers are monotonic per `runtime_id`
* The latest version is defined as the highest version number for that `runtime_id`
* Previous versions remain accessible for audit and debugging
* Updates are **intentionally non-idempotent**
* No update or evaluation deletes or invalidates state

Clients must not retry `/form/update` automatically. A version conflict (409) is terminal for that session.

RuntimeState is an **engineering and safety artefact**, not a medical record. Retention policy (e.g. 30 days) is deferred to later phases.

---

## Client-facing data contracts

### ClientStateView (server → client)

A render-only projection of RuntimeState.

**Purpose**

* Render questions and answers
* Indicate which values were suggested
* Drive frontend completeness checks

**Properties**

* Derived from RuntimeState
* Lossy by design
* Read-only projection, not a data transfer object
* Never accepted by any API endpoint

**Contains (illustrative)**

* question text
* answer_key
* current value
* required flag
* suggested flag

**Explicitly excludes**

* provenance enums
* encoder internals or raw signals
* safety or advisory logic
* internal metadata

Any request payload containing fields from ClientStateView is rejected.

---

### ClientAnswerReturn (client → server)

An intent-only structure representing **explicit patient input**.

**Purpose**

* Express user intent unambiguously
* Avoid inference via diffing or state comparison

**Properties**

* Contains only keys the patient explicitly answered or changed
* Absence of a key means “no change”
* Every provided value is treated as `source = patient`

**Contains**

* `answer_key → value`

**Never contains**

* provenance
* full state or projections
* encoder information
* free text

---

## Safety and advisory evaluation

Two distinct rule categories are supported:

1. **Blocking safety rules**

   * Represent clinical risk
   * Evaluated on submission
   * Any trigger blocks submission

2. **Advisory notices**

   * Non-blocking procedural or informational messages
   * Do not prevent submission
   * Intended for guidance (e.g. referral requirements)

Both consume projected ExplicitAnswers, but are typed and enforced separately.

---

## API Endpoints

### POST /form/init

**Purpose**
Create a new session and initialise RuntimeState (version = 1).

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
* Run encoder exactly once (if free_text present)
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
* `/form/update` must not accept free_text
* Changing free text requires a new session (`runtime_id`)

---

### POST /form/update

**Purpose**
Submit a complete form, normalise provenance, and evaluate safety and advisory rules.

This endpoint is semantically a **submit operation**, not a draft or partial update.

**Inputs**

```json
{
  "runtime_id": "string",
  "base_version": number,
  "answers": ClientAnswerReturn
}
```

**Behaviour**

* Load latest RuntimeState for `runtime_id`
* Reject if `base_version != latest_version` (409 Conflict)
* Validate ruleset hash
* Apply patient answers (`source = patient`)
* Normalise encoder provenance:

  * unchanged encoder answers → `encoder_confirmed`
  * overwritten encoder answers → `encoder_corrected`
* Validate that all required questions are answered
* Create new RuntimeState version
* Persist
* Project RuntimeState → ExplicitAnswers
* Evaluate blocking safety rules
* Evaluate advisory notices (out of scope for MVP)
* Generate ClientStateView

**Outputs**

```json
{
  "runtime_id": "string",
  "version": number,
  "client_state": ClientStateView,
  "safety_messages": [...],
  "advisory_messages": [...]
}
```

**Notes**

* This endpoint is safety-critical
* Partial or incomplete states are rejected
* Auto-merge is forbidden
* Safety evaluation is mandatory and occurs exactly once per submission

---

### POST /form/finish

**Purpose**
Terminal session closure and hand-off to downstream systems.

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
* Mark session as closed (read-only)
* Serialize clinical output (lossy)
* Persist audit output (lossless RuntimeState)
* Hand off to downstream system (out of scope)

**Outputs**

```json
{
  "clinical_output": ...
}
```

After `/form/finish`, the session rejects all further updates. The front end merely shows a "this session has ended screen". Any new interaction requires a new `runtime_id`.

---

## Failure semantics

Fail loud and early on:

* invalid `runtime_id`
* missing or invalid version
* ruleset hash mismatch
* illegal provenance transitions
* malformed ClientAnswerReturn
* incomplete required answers
* concurrent modification conflicts

UX expectations:

* the user is notified
* the form may need to restart
* no silent recovery

Clinical ambiguity is never auto-resolved.

---

## UI flow (informative, non-binding)

1. **Screen 1 — Init**

   * condition + free text
   * `/form/init`

2. **Screen 2 — Edit / Submit**

   * all questions required
   * `/form/update`
   * safety and advisory rules evaluated

3. **Screen 3 — Review**

   * read-only answers
   * safety and advisory messages visible

4. **Final submit**

   * `/form/finish`

---

## Explicit non-goals (Phase 6)

* Authentication or authorisation
* Multi-session recovery
* UI implementation
* Ruleset migration
* Multi-condition support
* Retention enforcement
* EHR integration
## Phase 6 — API Wrapper with Canonical Server-Side State (Revised)

### Purpose

Expose the deterministic form engine over HTTP while preserving canonical RuntimeState integrity, auditability, and safety.

The API is **stateless in interaction semantics** (no conversational flow, no per-user logic), but **RuntimeState is server-owned and persisted**. This removes hostile-client risks, simplifies validation, and aligns with future audit and safety requirements.

---

## Architectural stance

* RuntimeState is **canonical, backend-owned, and lossless**
* The client never invents, mutates, or signs RuntimeState
* The server is the sole authority for:

  * state identity
  * versioning
  * provenance transitions
  * safety evaluation
* Persistence is minimal, append-only or versioned
* No conversational memory, no hidden workflow, no cross-user state

This is not a session-based system. It is a deterministic engine with durable inputs.

---

## RuntimeState persistence model

Each RuntimeState instance is stored server-side with:

* `runtime_id` (UUID, server-generated)
* `ruleset_hash`
* `version` (monotonic integer)
* `created_at`
* `last_modified_at`
* full RuntimeState payload (lossless)

Rules:

* RuntimeState is never mutated in place
* Each update creates a new version
* Previous versions remain accessible for audit/debug
* Submission/evaluation never deletes or invalidates state

This enables:

* safe re-submission
* patient back-navigation
* audit trails
* future model evaluation

---

## API Endpoints

### POST /form/init

**Purpose**
Create a new RuntimeState (version 1) for a given condition.

**Inputs**

```
{
  condition_id: string,
  free_text: string | null
}
```

**Behaviour**

* Load and validate ruleset
* Initialise canonical RuntimeState (all answer_keys present)
* Run encoder once (if free text present)
* Apply encoder mapping
* Persist RuntimeState (version = 1)

**Outputs**

```
{
  runtime_id: string,
  version: number,
  state: RuntimeState
}
```

Encoder output is frozen at this point and can never be re-run.

---

### POST /form/update

**Purpose**
Apply patient answer changes to an existing RuntimeState and produce a new version.

**Inputs**

```
{
  runtime_id: string,
  base_version: number,
  answer_updates: {
    answer_key: value
  }
}
```

**Behaviour**

* Load latest RuntimeState for runtime_id
* Reject if base_version != latest_version (409 Conflict)
* Validate ruleset hash
* Apply updates using form logic
* Enforce allowed provenance transitions
* Increment version
* Update last_modified_at
* Persist new RuntimeState version

**Outputs**

```
{
  runtime_id: string,
  version: number,
  state: RuntimeState
}
```

The client never sends a full RuntimeState for mutation. Auto-merge is explicitly forbidden.

---

### POST /form/evaluate

**Purpose**
Evaluate a specific RuntimeState snapshot and emit derived outputs.

This endpoint is **pure**: it must not mutate, normalise, advance, or persist state.

**Inputs**

```
{
  runtime_id: string,
  version: number
}
```

**Behaviour**

* Load RuntimeState(runtime_id, version)
* Validate ruleset hash
* Project RuntimeState → ExplicitAnswers
* Evaluate safety rules
* Generate clinical and safety outputs

**Critical invariants**

* Must NOT advance version
* Must NOT normalise provenance permanently
* Must NOT persist any changes
* May be called on any historical version

**Outputs**

```
{
  clinical_output,
  safety_messages
}
```

Evaluation output is a read-only artefact. The frontend must continue rendering the last known RuntimeState.

**Behaviour**
* Load RuntimeState
* Normalise encoder provenance
* Project RuntimeState → ExplicitAnswers
* Evaluate safety rules
* Generate clinical and safety outputs

**Outputs**
```

{
clinical_output,
safety_messages
}

```

Evaluation does not mutate or advance RuntimeState.

---

## Statelessness guarantees

* No conversational flow
* No hidden per-user logic
* Each request is explicit and self-contained
* Server persistence does not imply behavioural state

The API remains deterministic and replayable.

---

## Failure semantics

Fail loud and early on:
* invalid runtime_id or version
* ruleset_hash mismatch
* illegal provenance transitions
* malformed updates

Expected UX behaviour on failure:
* notify user
* restart form if necessary

---

## Explicit non-goals (Phase 6)

* No session management
* No authentication model
* No long-term data retention policy
* No ruleset migration support

These are deferred intentionally.

---

## Rationale

Introducing minimal server-side storage at this phase:
* reduces security risk
* simplifies validation
* preserves functional purity
* aligns with regulatory and audit needs

This is a deliberate architectural choice, not a compromise.

```

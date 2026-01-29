### Provisional plan for MVP

### Locked invariants for MVP

Server is stateless per request
No ML dependency
All clinical meaning lives in JSON rulesets
UI is a pure renderer
Safety logic consumes explicit answers only

---

### Phase 1 — Define the ruleset schema COMPLETE
### Phase 2 — Build the deterministic form engine COMPLETE
### Phase 3 — Encoder stub (non-ML) COMPLETE
### Phase 4 — Safety engine COMPLETE
### Phase 5 — Clinical output vs audit output split

Deliverables
Two serializers:
Clinical output (lossy)
Audit/debug output (lossless)

Concrete actions
1. Define exact field inclusion/exclusion
2. Ensure encoder-related fields are excluded from clinical output
3. Add ruleset version + timestamps to audit output

This enforces regulatory boundaries early instead of retrofitting later.

---

### Phase 6 — Stateless API wrapper

Purpose
* Expose the deterministic engine over HTTP without introducing server-side session state or conversational memory
* The API is stateless **per request**, but operates on a **canonical RuntimeState** that may be round-tripped by the client

Deliverables
* Minimal HTTP API with two endpoints operating exclusively on canonical RuntimeState objects.

Endpoints
#### `POST /form/init`

Purpose
Create a new canonical RuntimeState and (optionally) apply the encoder.

**Inputs (fresh initialisation only)**

```
{
  condition_id: string,
  free_text: string | null
}
```

Forbidden
* answers
* encoder_value
* source
* safety_evaluation
* partial RuntimeState objects

Behaviour
* Load and validate ruleset
* Construct canonical RuntimeState (all answer_keys present)
* Run encoder if eligible
* Return full RuntimeState

Outputs
```
RuntimeState
```

---

#### `POST /form/submit`

Purpose
Validate, normalise, evaluate safety, and emit clinical output.

Inputs (canonical hydration only)

```
RuntimeState
```

Forbidden
* partial payloads
* clinical (lossy) output
* reconstructed or inferred fields

Behaviour
* Validate RuntimeState against ruleset hash
* Enforce invariants (answer keys, immutability, provenance)
* Normalise sources (`encoder → encoder_confirmed`)
* Evaluate safety using projected answers only
* Generate:
  * clinical output (lossy)
  * safety messages

Outputs

```
{
  clinical_output,
  safety_messages
}
```

Statelessness guarantees

* No server-side session storage
* No per-user memory
* No cross-request mutation
* Every request is fully self-describing

State exists only:

* in memory during request execution
* in client-supplied canonical RuntimeState payloads

---

### Phase 7 — Minimal frontend renderer

Deliverables
Dumb UI capable of:
Rendering questions
Showing suggested vs explicit answers
Allowing overrides
Submitting answers

Constraints
No clinical logic
No branching
No hidden questions

---

### Phase 8 — End-to-end validation
Deliverables
One full happy-path test
One safety-trigger test
One override test (encoder suggestion overridden by user)

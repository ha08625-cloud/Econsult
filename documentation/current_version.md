### Provisional plan for MVP

### Locked invariants for MVP

Server is stateless per request
No ML dependency
All clinical meaning lives in JSON rulesets
UI is a pure renderer
Safety logic consumes explicit answers only

---

### Phase 1 — Define the ruleset schema COMPLETE

Deliverables
* JSON schema - see uti1.json for MVP schema
* Schema validator (rules decided but validator not built)

---

### Phase 2 — Build the deterministic form engine COMPLETE

See form_engine_proposal.md for implementation plan and engine.py for actual code

---

### Phase 3 — Encoder stub (non-ML)

Deliverables: Fake encoder implementation

Concrete actions
1. Hard-code deterministic outputs based on keywords
2. Populate suggested answers
3. Mark source = encoder

---

### Phase 4 — Safety engine (separate, explicit)

Deliverables

Independent safety evaluator:
input: explicit answers only
output: safety messages

Concrete actions
1. Parse safety rules from ruleset
2. Evaluate against answers
3. Return message IDs + text

Why Safety must be inspectable, testable, and impossible to trigger via encoder paths.

---

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
Deliverables
Minimal HTTP API (single endpoint is sufficient)

Concrete actions
1. POST /form/init
inputs: condition_id, free_text
outputs: form state

2. POST /form/submit
inputs: 
{
  condition_id,
  ruleset_version,
  free_text,
  answers
}
outputs: clinical output + safety messages

3. No session storage
4. No per-user memory

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

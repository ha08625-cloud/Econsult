Provisional plan for MVP

Phase 0 — Lock invariants (do not write code yet)

Deliverables
Written confirmation (README / comment) of the following invariants:
Server is stateless per request
No ML dependency
All clinical meaning lives in JSON rulesets
UI is a pure renderer
Safety logic consumes explicit answers only

---

Phase 1 — Define the ruleset schema COMPLETE

Deliverables

JSON schema for:
Condition
Questions
Answer fields
Safety rules

Schema validator

---

Phase 2 — Build the deterministic form engine (core logic)

Deliverables

Pure function:
input: ruleset + current answers
output: form state
No HTTP, no UI, no persistence

Concrete actions
1. Load ruleset
2. Initialise answer state:
empty values
source = unanswered

3. Return:
ordered question list
answer fields
answer sources
metadata needed by UI

This is the functional core.
Everything else is an adapter.

---

Phase 3 — Safety engine (separate, explicit)

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

Phase 4 — Clinical output vs audit output split

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

Phase 5 — Stateless API wrapper
Deliverables
Minimal HTTP API (single endpoint is sufficient)

Concrete actions

1. POST /form/init
inputs: condition_id, free_text
outputs: form state

2. POST /form/submit
inputs: answers only
outputs: clinical output + safety messages

3. No session storage
4. No per-user memory

Why Prevents accidental conversational state from creeping in.

---

Phase 6 — Minimal frontend renderer

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

Why Any logic here will later diverge from server truth.

---

Phase 7 — Encoder stub (non-ML)

Deliverables

Fake encoder implementation

Concrete actions

1. Hard-code deterministic outputs based on keywords

2. Populate suggested answers

3. Mark source = encoder

This tests the entire integration path without introducing ML uncertainty.

---

Phase 8 — End-to-end validation
Deliverables
One full happy-path test
One safety-trigger test
One override test (encoder suggestion overridden by user)
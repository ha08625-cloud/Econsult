## This document contains the module descriptions for `safety_engine.py`, `projection.py`, `explicit_answers.py`

### safety_engine.py

Responsibilities:
* Evaluate safety-critical clinical rules defined in the ruleset
* Consume explicit answers only (post-projection)
* Return structured safety outcomes (rule IDs + message text)

Inputs:
* ExplicitAnswers (immutable, projected view)
* Safety rule definitions from the ruleset

Outputs:
* SafetyEvaluation containing:
* Triggered rule IDs
* Corresponding safety message payloads

Properties:
* Pure function: no mutation, no IO, no side effects
* Deterministic and fully inspectable
* Unit-testable in complete isolation

Has no access to:
* RuntimeState
* AnswerState
* Answer provenance
* Encoder output or metadata
* Submission or blocking logic

Rules:
* None represents unknown and never satisfies a condition
* Safety rules are evaluated using explicit boolean logic only
* The safety engine never blocks submission directly
* Blocking decisions are enforced exclusively by the pipeline based on safety output

Non-goals:
* No advisory or informational guidance
* No UI behaviour
* No conditional workflows
* No mutation of answers or state

### projection.py — Explicit answer projection boundary

Responsibilities:
* Project RuntimeState → ExplicitAnswers
* Apply strict allow-list provenance rules
* Act as the single choke point where encoder influence is excluded from safety

Rules:
* Only answers with source ∈ {patient, encoder_confirmed} are included
* All other answers are treated as unanswered (None), even if a value exists
* Projection is deterministic and total (all answer_keys always present)

### explicit_answers.py — Safety-critical answer projection

Responsibilities:
* Define the only data structure that safety and other post-submit rule engines may consume
* Enforce immutability of projected answers
* Remove all provenance, encoder metadata, and RuntimeState access

Properties:
* Input is a projection of RuntimeState, not RuntimeState itself
* Answers are immutable (frozen dataclass)
* Answer values may be True, False, or None
* None represents unknown, not False


1. REQUIRED for Phase 7 (frontend renderer)

1.1 Endpoint list + semantics (black-box)

Frontend must know only:

Endpoint	When called	Meaning

POST /form/init	Once, at start	Create a new session
POST /form/update	On submit	Submit a complete form
POST /form/finish	Final action	Finalise and hand off

The frontend does not manage state.
It reacts to server responses only.

1.2 ClientStateView (render contract)

Frontend must be given a stable, documented ClientStateView shape, including:

Per question:
answer_key (string, stable identifier)
question_text (string)
current_value (typed: bool / string / null)
required (boolean)
suggested (boolean)

Global:
Questions are complete and ordered
All required questions are present
No hidden logic or conditional branching in Phase 7

Frontend responsibilities:
Render all questions
Visually mark suggested = true
Enforce “all required answered” locally for UX only
Treat ClientStateView as read-only
This is the only structure Phase 7 renders.


---

1.3 ClientAnswerReturn (submission contract)

Frontend must submit:

{
  "runtime_id": "...",
  "base_version": N,
  "answers": {
    "answer_key": value
  }
}

Rules frontend must obey:
Every required question must be present
Values must match declared answer type
No extra keys
No provenance
No copying of client_state
Frontend does not diff state.
It sends explicit intent only.

1.4 Safety messages (blocking feedback)

Frontend must handle:

"safety_messages": [
  { "rule_id": "...", "message": "..." }
]

Rules:
Any safety message blocks progress
Messages are read-only
No interpretation, no rewording
User must change answers and re-submit
Frontend does not “resolve” safety.

1.5 Version handling (UX only)

Frontend must:
Store runtime_id
Store version
Send base_version on submit

On 409:
Show fatal error
Restart flow

No retry. No merge. No background refresh.

2. EXPLICITLY NOT HANDED OVER (must be hidden)

Frontend must never know about:
RuntimeState
Answer provenance
Encoder outputs
Rulesets
Safety logic
Ruleset hash
Session persistence
Audit output
Version history
“Why” a safety rule fired

If Phase 7 asks for any of this, that is a design regression.

3. Minimal frontend mental model (handover summary)

You should give the Phase 7 implementer this exact framing:

> “This is a server-driven form renderer.
The backend owns state, logic, safety, and validation.
The frontend renders questions, collects explicit answers, submits them, and displays messages.
There is no local truth.”

If they violate this, Phase 6 invariants will leak.

4. Strong recommendations (avoid Phase 7 mistakes)

4.1 Freeze ClientStateView early

Write a concrete JSON example
Treat it as a contract
Evolve only additively
This avoids frontend/back-end churn.

4.2 Do NOT add client-side branching

All branching:
belongs in rulesets
belongs in Phase 8+
Phase 7 is a dumb renderer by design.

4.3 Do NOT reuse form libraries that assume local state ownership
Many React form libs fight this model.
Prefer:
simple controlled inputs
explicit submit button
explicit error display

5. What you should hand over as artefacts

Minimum package for Phase 7:
1. Endpoint summary (1 page)
2. ClientStateView schema + example JSON
3. ClientAnswerReturn schema + example JSON
4. Safety message example
5. Version conflict example
# Provisional Plan A — "Not sure" as a Boolean answer value

**Status:** provisional. Written for review (workflow step 2), not for
implementation. Nothing here is decided.

**Relationship to Plan B:** A is a prerequisite for B and is independently
valuable. B (`not_sure_B_encoder_class.md`) must not start until A has shipped
and been used. A can ship and stay useful even if B is never done.

---

## Scope

Today a Boolean question has exactly two answerable values. `EditScreen.tsx`
renders two radio cards (Yes / No), `serialisation.py:56` marks every question
required in the MVP, and `validate_required_answers` rejects a boolean whose
value is `None`. A patient who genuinely does not know whether they have a fever
must pick one, and the record cannot distinguish that coerced answer from a
confident one.

This plan adds a third selectable value, per question, opt-in from the ruleset.

**Out of scope:** anything about the encoder. The encoder keeps emitting
`true | false | null` throughout this plan. Hedged free text continues to produce
`null`, the question is left unprefilled, and the patient answers it — possibly
with the new value. That is the whole point: the clinical fact is captured with
no retraining.

---

## The problem this solves, stated as the failure it prevents

A patient writes "I've been shivery, I don't know if that's a temperature". The
encoder correctly returns `null`. The form asks "Do you have a fever?" and offers
Yes and No. The patient guesses. Whatever they press is recorded with the same
weight as a confident answer, is projected into safety evaluation as an explicit
`True` or `False`, and reaches the clinician on the PDF as "Yes" or "No" with no
indication that it was a guess.

The system currently has no way to represent "the patient does not know", even
though `ExplicitAnswers` already has exactly the right semantic for it
(`None` = unknown, satisfies neither `is_true` nor `is_false`) and
`arch_safety.md` already documents that semantic as load-bearing.

---

## Design decisions to make in review

These are the decisions that change the shape of the work. Each is written with
a recommendation and the argument against it, because two of them are genuinely
close.

### DD-A1. How "not sure" is represented in `AnswerState` — the biggest decision

Three options. `None` is not available: it already means *unanswered*, and
`validate_required_answers` rejects it.

**Option 1 (recommended): a third value in `AnswerState.value`.**
`value: bool | Literal["not_sure"] | None`, persisted as the JSON string
`"not_sure"`.

- *For:* one field holds the answer, which is what every consumer already
  assumes. Consumers that must treat it as unknown say so explicitly at their
  own boundary, which is visible in a diff and testable.
- *Against:* the widest blast radius. Every consumer of `value` has to be
  visited (see the file list below), and `apply_patient_answers` currently does
  `a.value = value` with **no type validation at all** — a boolean question will
  today accept any JSON scalar off the wire. Option 1 makes that pre-existing
  gap load-bearing, so it must be closed as part of this work rather than left.

**Option 2: a separate `AnswerState.unsure: bool` flag, `value` stays `None`.**

- *For:* smallest diff. `projection.py` needs no change at all — an answer with
  `value is None` already projects to `None`, which is the correct safety
  semantic.
- *Against:* that "no change needed" is the reason to be suspicious of it. The
  meaning of the projection changed and nothing in the safety boundary records
  that it did. It also gives `value is None` two distinct meanings (unanswered,
  and answered-as-unsure), so every consumer needs to read two fields to know
  which, and the ones that forget fail silently rather than loudly.

**Option 3: a sentinel string with no type change.** Rejected — this is Option 1
with the type lie left in place.

**Recommendation: Option 1.** The argument is the same one `arch_encoder.md`
makes about `source` persistence and `arch_training.md` makes about manifest
discovery: prefer the failure that is visible in a diff. But this is the
decision most worth arguing with, and it should be settled before any file is
touched, because it determines every task boundary below.

### DD-A2. Which questions may offer it

**Recommendation:** a new optional ruleset field `allow_unsure: bool`, default
`false`, valid only on `answer_type: "Boolean"`. Non-Boolean questions must omit
it or set it false, validated at startup alongside the existing
`send_to_encoder` / `encoder_prompt` checks in `ruleset.py`.

Rationale for opt-in rather than global: "not sure" is right for a subjective
symptom ("do you have a fever?") and wrong for a question of fact the patient
necessarily knows ("are you pregnant?" is arguable; "have you taken the tablets?"
is not). Making it per-question also means the safety interaction (DD-A3) is
decidable per question rather than globally.

### DD-A3. The safety interaction — the decision with clinical weight

`arch_safety.md` already names the exposure: an unknown answer makes an
enclosing `all` group unsatisfied, silently, with no signal to patient or
clinician. Today that only happens for a question the patient never reached.
After this change a patient could **choose** it.

Two defensible positions:

- **Conservative (recommended for MVP):** a question referenced by any safety
  rule leaf (at any nesting depth — the existing declared-key check already
  recurses) may **not** set `allow_unsure: true`. Fail fast at startup, same
  posture as every other ruleset invariant. Red-flag questions keep forcing a
  Yes/No.
- **Permissive:** allow it, and treat "not sure" on a red-flag question as
  `True` for safety purposes (fail-safe), so uncertainty escalates rather than
  silently disarming an `all` group.

The argument for permissive is real and should not be dismissed: forcing a
guess on a red-flag question does not produce safety, it produces fabricated
data that safety then trusts. The argument for conservative is that fail-safe
escalation on an opt-out button is a trivially discoverable way to trigger every
warning screen, and that this is a decision to make with a clinician rather than
in an implementation plan.

**Recommendation: ship conservative, record permissive as the open question, and
put it to a clinician before relaxing it.** Whichever is chosen, it must be a
startup-validated invariant, not a convention.

### DD-A4. What safety sees

**Recommendation:** `project_explicit_answers` maps `"not_sure"` to `None`
explicitly, with a comment naming the decision, and `ExplicitAnswers.values`
keeps its `dict[str, bool | None]` type. The safety engine does not learn the
new value exists, and `safety_engine.py` is not touched.

Under DD-A3-conservative this mapping can never fire for a safety-referenced
key, so it is defence in depth rather than the mechanism. Write it anyway and
test it — it is what makes DD-A3-permissive a one-line change later instead of a
re-audit.

### DD-A5. Provenance and `change_count`

`arch_encoder.md` states a parity invariant: *even `change_count` ⟺ value equals
`encoder_value` ⟺ `encoder_correct`*, proved on the grounds that "every
increment on a boolean is a flip between `true` and `false`". **A third value
breaks that proof.** `true → not_sure → false` is two increments and does not
equal `encoder_value`.

**Recommendation:** downgrade it to the surviving one-way implication
(`encoder_correct` ⟹ even) and update `arch_encoder.md` in the same commit as
the code. The `source` computation itself needs no change — it is already
`value == encoder_value` and that comparison is still correct with a third
value. What must not happen is the doc keeping a claim the code no longer
supports.

### DD-A6. Wire and client representation

**Recommendation:** the string `"not_sure"` on the wire, in both directions,
matching the existing `not_sure` option on the OUTCOME screen
(`arch_frontend.md:29`) so the codebase has one spelling for this concept.
`ClientStateView` gains `allow_unsure` per question so the client knows whether
to render the third card.

### DD-A7. How it reads to the clinician

`pdf_formatter._format_answer` currently returns `"Yes"`, `"No"`, or
`"(not answered)"`. **Recommendation:** `"Not sure"` — and deliberately *not*
`"(not answered)"`, because the two are different facts and the whole value of
this change is that the clinician can tell them apart. The CLINICAL SUMMARY
block (`pdf_labels`) needs the same treatment and should be checked separately;
it is a different render path.

---

## Provisional task breakdown

Ordering is dependency-driven. Task 1 settles the representation and everything
else follows from it.

**Task 1 — Data model and ruleset schema.** `app/models/runtime_state.py`
(`AnswerState.value` type + docstring, `from_dict`/`to_dict` round-trip),
`app/services/engine/ruleset.py` (`allow_unsure` parsing, the Boolean-only
check, the DD-A3 safety-reference check), `documentation/arch_ruleset_schema.md`.
Deliverable: a ruleset carrying `allow_unsure` loads, an invalid one aborts
startup, and a `"not_sure"` value survives a persistence round-trip.

**Task 2 — Engine.** `form_logic.py`: accept `"not_sure"` in
`apply_patient_answers` **only** for a question whose `allow_unsure` is true and
reject every other non-boolean scalar (closing the untyped-assignment gap named
in DD-A1); `validate_required_answers` treats it as answered.
`projection.py`: the DD-A4 mapping. `safety_engine.py` unchanged, and a test
asserting it is unchanged in behaviour.

**Task 3 — Encoder boundary.** `encoder_mapping.py` must be checked, not
assumed: it only populates `unanswered` fields and the encoder still emits
`true | false | null`, so the expected finding is that no change is needed. The
deliverable is a test pinning that, because Plan B changes exactly this.

**Task 4 — Serialisation and delivery.** `serialisation.py` (`ClientStateView`
gains `allow_unsure`; `ClinicalOutput.answers` carries the value),
`app/utils/pdf_formatter.py` (DD-A7, both render paths), and the mesh payload
builder in `app/services/delivery/`. Each of these is a place a `bool` is
assumed; find them by type rather than by grep for `True`.

**Task 5 — Frontend.** `frontend/src/types.ts`, `screens/EditScreen.tsx` (third
selection card, gated on `allow_unsure`), `screens/ReviewScreen.tsx` (how it
displays in review). Existing component tests cover the two-card case and must
keep passing unchanged for questions that do not opt in.

**Task 6 — Ruleset content and docs.** Decide per question in the UTI ruleset
which get `allow_unsure`, and update `arch_core_engine.md`, `arch_safety.md`,
`arch_encoder.md` (DD-A5), `arch_frontend.md`.

---

## What this plan deliberately does not do

- **It does not change the encoder or any training data.** That is Plan B, and
  it is a separate decision taken after this has been used.
- **It does not make "not sure" a default or a skip button.** It is a
  deliberate answer, rendered as a third equal option, not an escape from the
  form.
- **It does not add tri-state logic to safety.** `is_true` / `is_false` against
  `None` is the existing semantic and it is the correct one; nothing in
  `safety_engine.py` should move.

---

## Open questions for review

1. DD-A3 permissive vs conservative — needs a clinician, not an engineer.
2. Should the Review screen visually flag "not sure" answers as needing a second
   look before submission, or treat them as settled? Leaning settled: nagging
   turns a considered answer into a coerced one, which is the failure this plan
   exists to prevent.
3. Does the "not sure" count belong in the audit record as a form-level figure,
   alongside `change_count`? Cheap to add now, and it is the measurement that
   tells you whether the option is used at all.
4. Is there a question in the current UTI ruleset where this is clearly right?
   If the honest answer is no, that is evidence the plan is premature and should
   be said out loud rather than worked around.

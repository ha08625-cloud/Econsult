# Clinical Safety & Projection

**LLM INSTRUCTIONS:** This document covers design decisions and strict invariants for the safety domain. Read the actual source files for function signatures and implementation details.

---

## Scope

Evaluating explicit patient answers against safety rules, projecting `RuntimeState` to the `ExplicitAnswers` boundary, and blocking unsafe submissions.

**Key files:** `safety_engine.py`, `projection.py`, `explicit_answers.py`

---

## Design Decisions & Invariants

### Safety is isolated and input-restricted

The safety engine consumes `ExplicitAnswers` only — a projected, immutable view of `RuntimeState`. It never sees `RuntimeState` directly, answer provenance, or encoder output. This is a hard boundary: the safety engine has no import path to `RuntimeState`, `AnswerState`, or encoder modules.

This isolation is intentional: safety evaluation must be deterministic, inspectable, and unit-testable in complete isolation from the rest of the pipeline.

### The projection boundary (`projection.py`)

`project_explicit_answers` is the single choke point that enforces which answers are allowed to influence safety. The allow-list is `EXPLICIT_SOURCES`:

- `patient` — directly entered by the patient
- `encoder_correct` — an encoder suggestion exists and the current answer matches it
- `encoder_incorrect` — an encoder suggestion exists and the current answer differs from it

All other sources (i.e. raw `encoder` answers) are projected as `None` regardless of their value. An encoder answer that has not been confirmed or corrected by the patient is treated as unknown for safety purposes.

### `None` semantics

`None` means unknown, never `False`. A safety rule clause requiring `is_true` or `is_false` for a key that is `None` is not satisfied by either. This is not an edge case — it is a core semantic: absence of an answer must never accidentally satisfy a safety condition, in either direction. An unconfirmed encoder guess of "No" projects to `None` under the boundary above, so it cannot satisfy an `is_false` clause; only a patient-explicit `False` can.

**An unknown answer makes an enclosing `all` group unsatisfied.** This follows directly from the rule above — an unsatisfied leaf is an unsatisfied leaf, and there is no tri-state logic — but it is worth stating plainly, because it is where the semantic bites hardest. `{"all": [{"is_true": "fever"}, {"is_true": "flank_pain"}]}` with `fever` answered True and `flank_pain` unanswered does **not** fire.

The exposure is worth naming: `all` groups are precisely the rules an unanswered question can silently defeat. An OR rule needs only one answered red flag to fire, so an unknown elsewhere costs nothing; an AND rule needs every leaf answered, so a single unknown turns it off with no signal to the patient or the clinician. An author adding an `all` group must be confident every question it depends on is actually reachable and asked, otherwise the rule is weaker in practice than it looks on the page.

### Safety rules use ANY logic at the top level, with recursive clauses beneath

A safety rule fires if **any** clause in its top-level `any` list is satisfied (OR semantics). See the ruleset schema for the clause grammar and its constraints.

A clause is either a **leaf** (`is_true` / `is_false`, comparing one Boolean answer) or a **group** (`any` / `all`, holding a list of further clauses), evaluated recursively. This is what lets a rule express "fever AND flank pain" rather than only "fever OR flank pain".

`all` is not permitted at the top level of a rule; a whole-rule AND is authored as `{"any": [{"all": [...]}]}`. This is a deliberate restriction, not a leftover typo check. A rule is a list of independent triggers, and OR is the clinically correct default for a red-flag list — any one red flag should fire it. Requiring the nesting means an author who wants AND has to write it explicitly, at the point of authoring, and every rule stays readable the same way: scan the top-level list, and each entry is one independent reason the rule fires.

### Blocking is enforced by the pipeline, not the safety engine

The safety engine returns a `SafetyEvaluation` (triggered rule IDs + message payloads). It does not decide whether submission is allowed. The pipeline makes the blocking decision based on that output.

For the MVP: any triggered safety rule blocks submission. The patient cannot submit until their answers change. This is a deliberate, medically defensible choice to prevent unsafe overnight submissions.

### Safety never mutates state

The safety engine is a pure function — no mutation, no IO, no side effects. It does not write to `RuntimeState`, answers, or any other structure.

---

## What Safety Must Never Do

- `safety_engine.py`: import or access `RuntimeState`, `AnswerState`, encoder modules, or submission logic
- `projection.py`: include raw encoder answers (source `"encoder"`) in `ExplicitAnswers`
- `explicit_answers.py`: be made mutable (it must remain a frozen dataclass)
- Any safety module: block submission directly — that is the pipeline's responsibility
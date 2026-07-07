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

### Safety rules use ANY logic

A safety rule fires if **any** of its conditions is satisfied (OR semantics). See the ruleset schema for rule structure. The engine does not support AND-only rules at the top level.

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
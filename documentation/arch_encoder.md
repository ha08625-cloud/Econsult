# Encoder & ML Boundary

**LLM INSTRUCTIONS:** This document covers design decisions and strict boundaries for the encoder domain. Read the actual source files for dataclass fields, function signatures, and implementation details.

---

## Scope

Prompting encoders, mapping ML signals to answers, enforcing provenance.

**Key files:** `encoder_mapping.py`, `encoder_stub.py`, `encoder_contracts.py`

---

## What the Encoder Is and Is Not

The encoder runs **once**, on initial free text, before the patient sees any questions. It outputs a partial signal map (`answer_key → true | false | null`). It is:

- **Advisory only.** Encoder output is non-authoritative. It surfaces suggestions to the patient; the patient confirms or corrects them.
- **Blind.** The encoder never sees rules, questions, existing answers, or `RuntimeState`. It receives only free text and `EncoderSignalDefinition` objects (answer key + clinical prompt string). The `encoder_prompt` is a clinical definition, not an instruction.
- **Frozen at extraction time.** Encoder-derived values are fixed when applied. On submission, any remaining raw encoder values are promoted to `encoder_correct` (see Provenance Model below).
- **Audit-only provenance.** Encoder provenance is retained in `runtime.metadata["audit"]` for debugging only. It is never exposed to safety logic or clinical outputs.

---

## Provenance Model

`source` is a **pure function of `(value, encoder_value)`**, recomputed on every
`apply_patient_answers` call. It is therefore idempotent — re-applying the same
value yields the same source — which is what lets the client round-trip the
entire answers map on every update without provenance drifting.

| Condition | `source` |
|---|---|
| `encoder_value is None` | `patient` |
| `value == encoder_value` | `encoder_correct` |
| `value != encoder_value` | `encoder_incorrect` |

On submission, `normalise_encoder_provenance` promotes any still-raw `encoder`
answer (one the patient never touched) to `encoder_correct`; its value still
equals `encoder_value` by construction, so this is consistent with the rule above.

Because source is recomputed each call, there is no transition table to enforce.
The **one surviving invariant** is:

> An answer with `encoder_value is None` (patient-owned) can never become
> encoder-derived.

This holds for a single reason: `encoder_value` is written **once**, in
`encoder_mapping.apply_encoder_output`, and is never mutated afterwards.
`apply_patient_answers` must never write it. The hard rule that **encoder output
must never overwrite a patient answer** remains enforced in `encoder_mapping.py`
(it only populates `unanswered` fields).

**Persistence note:** `source` is persisted verbatim inside the `state_json`
JSONB blob and is not validated against the `AnswerSource` Literal on read. The
rename from `encoder_confirmed`/`encoder_corrected` is therefore **not**
backward-compatible with already-persisted sessions: an old value would fall
outside `EXPLICIT_SOURCES` and be silently dropped from safety projection. This
is accepted because the system is pre-live with no durable sessions. **If the
system goes live, a read-time compatibility shim in `AnswerState.from_dict` (or a
session drain on deploy) becomes mandatory.**

---

## Change Auditing

`AnswerState.change_count` records how much a **single encoder-suggested answer
churned** over the life of a session. It complements `source` rather than
duplicating it: `source` says where the answer *ended up* (agreeing with the
encoder or not); `change_count` says how many times it *moved* to get there.

**What increments it.** Inside `apply_patient_answers`, before the value is
overwritten, an answer increments by one when **both** hold:

- `encoder_value is not None` (the answer was encoder-suggested — always a
  boolean), and
- the submitted value differs from the currently committed value.

Number and text answers (`encoder_value is None`) and encoder-null booleans are
out of scope and never increment. The read-before-write is structural: the
increment sits one line ahead of the value assignment in the same loop iteration,
so it cannot be defeated by reordering elsewhere in the pipeline.

**Granularity.** One `/form/update` is one commit. The counter measures
**committed deltas across review cycles**, not in-screen toggling — the server
never sees intermediate UI state, only the value committed at each Edit → Review
transition. A no-op submit (value unchanged) adds nothing, so the same-value
idempotency of `apply_patient_answers` extends to `change_count`.

**Baseline.** The encoder prefill is the baseline (count starts at 0); applying
the encoder's own value is not a patient change.

**Parity invariant.** Because every increment on a boolean is a flip between
`true` and `false`, and a required boolean can never be persisted as `None`,
parity is exact for any tracked answer:

> even `change_count` ⟺ value equals `encoder_value` ⟺ `encoder_correct`
> odd `change_count` ⟺ value differs from `encoder_value` ⟺ `encoder_incorrect`

A consequence worth stating for anyone reading the audit: a **high count does not
mean disagreement**. An answer overridden and then reverted ends at the encoder's
value (`encoder_correct`) with `change_count = 2`. `change_count` must therefore
be read **together with** `source`, never alone.

**Persistence and exposure.** `change_count` rides in the `state_json` JSONB blob
(no migration; `from_dict` defaults a missing key to 0 so pre-existing states
deserialise cleanly). It surfaces **only** in the lossless `AuditOutput` (via
`runtime.to_dict()`); it is deliberately absent from `ClientStateView` and
`ClinicalOutput`. It is captured now for the audit record; no consumer renders it
yet.

---

## Module Responsibilities & Boundaries

### `encoder_contracts.py` — Boundary contracts

Defines the **only** data structures permitted to cross the boundary between an encoder implementation and the rest of the engine: `EncoderSignalDefinition` and `EncoderOutput`. Both are frozen dataclasses.

- No business logic beyond output validation.
- No imports from any engine module.
- Imported by `encoder_mapping.py` and `pipeline.py` only.

### `encoder_stub.py` — Replaceable encoder facade

Accepts free text and encoder definitions, emits an `EncoderOutput`. The stub logic is intentionally naive — it exists as a placeholder. **This module is expected to be deleted and replaced by a real encoder without touching any other module.** That is the test of whether the boundary is clean.

### `encoder_mapping.py` — Containment layer

Applies a validated `EncoderOutput` to `RuntimeState`. This is the **regulatory boundary** between probabilistic inference and clinical state. All encoder influence is fully contained here — no other module applies encoder output.

Rules enforced here:
- Output is validated against definitions before any mutation occurs.
- Only `unanswered` fields are populated.
- Mapping failures are fatal (no partial application).
- Raw encoder output is stored in `runtime.metadata["audit"]` for the audit trail.

---

## Ruleset Constraint

If `send_to_encoder = true` on a question, then `encoder_prompt` must not be null and `answer_type` must be Boolean. This is validated at ruleset load time.
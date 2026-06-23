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
- **Frozen at extraction time.** Encoder-derived values are fixed when applied. On submission, any remaining encoder-derived values are treated as explicitly confirmed or corrected.
- **Audit-only provenance.** Encoder provenance is retained in `runtime.metadata["audit"]` for debugging only. It is never exposed to safety logic or clinical outputs.

---

## Provenance State Machine

An answer's `source` field must follow these transitions. Any other transition is a violation.

| From | To | Allowed |
|---|---|---|
| `unanswered` | `encoder` | yes |
| `unanswered` | `patient` | yes |
| `encoder` | `encoder_confirmed` | yes |
| `encoder` | `encoder_corrected` | yes |
| `encoder_confirmed` | `encoder_corrected` | yes |
| `patient` | `encoder` | **no** |
| `patient` | `encoder_confirmed` | **no** |

The hard rule: **encoder output must never overwrite a patient answer.** This is enforced in `encoder_mapping.py`.

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

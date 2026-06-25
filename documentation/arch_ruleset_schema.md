# Clinical Ruleset Schema

**LLM INSTRUCTIONS:** This document describes the JSON schema for condition rulesets, the design constraints that govern it, and validation rules. Rulesets live in the `/data/` directory. Read `ruleset.py` and `condition_registry.py` for the authoritative parsing and validation logic.

---

## Scope

The shape and constraints of the JSON ruleset files that define clinical behaviour for each condition. This is the **only** place clinical meaning lives — never in code.

---

## Schema Shape

```
{
  "condition_id": "<string>",          // unique identifier, matches filename convention

  "presentation": {
    "label": "<string>",               // patient-facing condition name
    "free_text_prompt": "<string>",    // prompt shown on the free-text entry screen
    "search_tags": ["<string>", ...]   // optional; omit for general_consultation
  },

  "questions": [
    {
      "question_id": "<string>",       // unique within ruleset
      "question": "<string>",          // human-facing question text
      "answer_key": "<string>",        // unique identifier; used everywhere (answers, safety rules, encoder)
      "answer_type": "Boolean" | "text" | "Number",
      "send_to_encoder": true | false,
      "encoder_prompt": "<string>" | null,  // required if send_to_encoder; null otherwise

      // Number questions only (omit these four for Boolean and text):
      "decimal_places": <non-negative integer>,  // 0 = whole numbers only
      "min": <number>,                            // advisory lower bound
      "max": <number>,                            // advisory upper bound; min < max
      "range_warning_text": "<string>" | null     // optional; shown when value is outside min/max
    }
  ],

  "safety": {
    "rules": {
      "<rule_id>": {
        "any": [
          { "is_true": "<answer_key>" }   // or "is_false"
        ],
        "message": "<string>"
      }
    }
  }
}
```

---

## Design Constraints (Strictly Enforced)

**Form engine, not conversational agent.** This is a form-filling engine. Do not architect for EHR integrations or dynamic branching based on prior answers.

**`answer_key` is the universal identifier.** There is no separate `signal_id`. The same `answer_key` identifies a question, its patient answer, and its encoder signal. Do not map multiple questions to a single `answer_key` — contradiction resolution is not supported.

**Coupled wording.** `question` (human-facing) and `encoder_prompt` (ML-facing) are different wordings of the same clinical concept. They must stay in sync when either is edited.

**Encoder questions must be Boolean.** `send_to_encoder: true` requires `answer_type: "Boolean"` and a non-null `encoder_prompt`. Non-Boolean questions must have `send_to_encoder: false` and `encoder_prompt: null`. This is validated at startup by `ruleset.py`.

**Answer types are a closed set.** `answer_type` must be present and one of `"Boolean"`, `"text"`, or `"Number"`. An unknown or missing type aborts startup. (Runtime state lowercases the type, so the client view reports `"number"`.)

**Number questions carry their own precision and bounds.** A `"Number"` question requires `decimal_places` (a non-negative integer; `0` means whole numbers only) and numeric `min`/`max` with `min < max`. Neither bound may have more decimal places than `decimal_places`. `range_warning_text` is optional (string or null). The two constraints behave differently: `decimal_places` is a **hard** submission constraint — a value with more decimal places is rejected at `/form/update` with `INVALID_PAYLOAD` — whereas `min`/`max` are **advisory**, driving only a non-blocking, client-side out-of-range notice (rendered when `range_warning_text` is authored and the value falls outside the bounds) and never blocking submission. Number values are transported on the wire as JSON numbers, parsed with decimal precision at the request boundary, and stored as exact canonical strings (e.g. `"70.5"`). Validated at startup by `ruleset.py`.

**Safety rules use `"any"` (OR) semantics.** A rule fires if **any** clause in its `"any"` list is satisfied. This is the correct clinical behaviour: a single red flag answer should trigger the rule. The key must be `"any"`, not `"all"` — both the validator in `ruleset.py` and the engine in `safety_engine.py` read this key.

**Safety rules reference only declared `answer_key`s.** Every key used in a safety rule's `any` clause must exist in the `questions` list. Validated at startup.

**`answer_key`s must be unique within a ruleset.** Duplicate keys are rejected at startup.

---

## `search_tags` Rules

- Tags belong in the `presentation` block — they are presentation-layer metadata, not clinical schema.
- Synonym expansion is strictly manual. No automated or ML-based tag generation.
- Max 20 tags per condition; max 60 characters per tag. Validated fail-fast at startup by `condition_registry.py`.
- `general_consultation` defines no `search_tags` — it is excluded from combobox search and accessed only via the "Use blank form" button.

---

## The General Fallback (`general.json`)

- `condition_id` is `"general_consultation"`. This value **must exactly match** `GENERAL_CONSULTATION_ID` in `frontend/src/constants.ts`. These are coupled — changing one without the other breaks the "Use blank form" flow.
- Has no condition-specific safety rules (`"rules": {}`). Relies entirely on the universal safety warning shown on Screen 1.
- Has no `search_tags` in the presentation block.

---

## Validation

All validation is performed by `ruleset.py` (`validate_ruleset`) and `condition_registry.py` at application startup. A validation failure aborts startup (fail-fast). There is no runtime re-validation after startup.
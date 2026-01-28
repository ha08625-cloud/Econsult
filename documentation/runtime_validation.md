## Phase 1 — Ruleset Validation Checklist (fail-fast)

### 1. Top-level structure

* `condition_id` **must exist** and be a non-empty string
* `questions` **must exist** and be a non-empty array
* `safety` is optional, but if present:

  * `safety.rules` **must exist** and be an object

---

### 2. Question integrity

For each question:

* `question_id`

  * required
  * unique within the ruleset
* `question`

  * required
  * non-empty string
* `answer_key`

  * required
  * unique within the ruleset
  * must match `[a-z0-9_]+`
* `answer_type`

  * required
  * allowed values: `Boolean`, `text`
* `send_to_encoder`

  * required
  * boolean

---

### 3. Encoder constraints

If `send_to_encoder = true`:

* `answer_type` **must be** `Boolean`
* `encoder_prompt` **must exist** and be non-null

If `send_to_encoder = false`:

* `encoder_prompt` **must be null**

Failure of any rule above → hard failure at load time.

---

### 4. Semantic key invariants

* `answer_key` is treated as a **semantic identifier**
* Validation must enforce:

  * no duplicates
  * no empty strings
* Engine must assume:

  * keys are immutable once released
  * keys are the only join point for logic

(This is enforced socially + via code review, not runtime, but validation must assume it.)

---

### 5. Safety rule validation

For each safety rule:

* Rule ID:

  * unique within `safety.rules`
* Rule expression:

  * may reference **only** `answer_key`
  * every referenced `answer_key` **must exist** in questions
* Logical operators:

  * only `all`, `any`, `is_true`, `is_false`
* `message`

  * required
  * non-empty string

Any reference to:

* `question_id`
* encoder output
* unknown keys

→ hard failure.

---

### 6. Forbidden configuration (explicit)

Ruleset **must not** contain:

* runtime answer values
* answer provenance / source
* UI state
* ordering logic
* persistence hints

If found → hard failure.

---

### 7. Forward-compatibility guardrails

Validation should **warn (not fail)** if:

* `safety` block is missing entirely
* no encoder-enabled questions exist

This allows early MVPs without weakening correctness.

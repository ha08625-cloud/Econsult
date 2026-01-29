Here is a **concrete proposal** for the Phase 2 canonical runtime state.

This object exists **only in memory**, during a single request lifecycle.

```
RuntimeState
├─ condition_id
├─ ruleset_version
├─ free_text
├─ answers
│  └─ { answer_key → AnswerState }
├─ safety_evaluation
└─ metadata
```

### AnswerState (per answer_key)

```
AnswerState
├─ value              // true | false | string | null
├─ source             // "unanswered" | "encoder" | "encoder_confirmed" | "encoder_corrected" | "patient"
├─ encoder_value      // true | false | null
```

---

## Concrete shape (JSON-like)

```
{
  "condition_id": "urinary_symptoms",
  "ruleset_version": "2026-01-27",
  "free_text": "Burning when peeing and feel hot",
  "answers": {
    "dysuria_present": {
      "value": true,
      "source": "encoder",
      "encoder_value": true
    },
    "fever_present": {
      "value": true,
      "source": "encoder",
      "encoder_value": true
    },
    "symptom_onset_text": {
      "value": null,
      "source": "unanswered",
      "encoder_value": null
    }
  },
  "safety_evaluation": {
    "triggered_rules": [],
    "messages": []
  },
  "metadata": {
    "engine_version": "0.1",
    "timestamp": "2026-01-27T10:14:00Z"
  }
}
```

---

### 1. `answer_key` is the sole join point

* Questions → answers
* Encoder output → answers
* Safety rules → answers

---

### 2. Encoder output is not authoritative until the patient confirms or corrects

* `encoder_value` is frozen
* on submit, the patient implicitly confirms the encoder_value is correct and the `source` changes to `encoder_confirmed`
* overwriting the suggested encoder value explicitly confirms the answer `value`, and flips `source` to `encoder_corrected`
* writing an answer that was previously empty/unanswered flips source to `patient`
* encoder output remains for audit/debug only
* once the patient has checked and submitted the form, no `source` can remain `encoder` - they must be flipped to either `encoder_confirmed` or `encoder_corrected`

---

### 3. Safety is evaluated against this state

* Safety engine receives:

  ```
  { answer_key → value }
  ```
* It never sees:

  * `encoder_value`
  * `source`
  * free text

---

### 4. No question-level state

There is:

* no per-question visibility
* no UI ordering
* no branching flags

Those belong to:

* the ruleset (static)
* or a later visibility engine

---

### 5. Output generation is trivial

From this state you can derive:

**Clinical output**

* `free_text`
* `{ answer_key → value }`
* safety messages

**Audit output**

* entire object
* plus encoder raw outputs
* plus ruleset hash

---

## Hard invariants to enforce in Phase 2

These should be assertions, not comments:

1. `answers` contains **exactly one entry per question answer_key**
2. encoder_value is immutable within a single Runtime state lineage. ruleset_version mismatch → hard failure
3. `value` may change only via explicit patient input
4. Safety engine consumes a projected view, not RuntimeState directly

---

Below is a **full lifecycle walkthrough** using the proposed Phase 2 runtime state

---

## Step 0 — Engine initialisation (canonical hydration, no encoder)
Purpose
* Construct a complete, lossless RuntimeState as the sole entry point into the engine.

Inputs (one of two mutually exclusive modes)

**Mode A — Fresh initialisation**
Used when the form is first opened.

Required
* condition_id
* free_text (may be empty)

Forbidden
* answers
* encoder_value
* source

**Mode B — Canonical re-entry (round-trip)**

Used for:
* validation failures
* review/edit flows
* multi-page navigation

Required
* full canonical RuntimeState payload from frontend:
* condition_id
* ruleset_version
* free_text
* answers (including value, source, encoder_value)
* safety_evaluation (may be empty)

Forbidden
* partial answers
* clinical (lossy) payloads
* If this distinction is violated → hard failure.

**Step 0A — Ruleset load and validation**

* Load ruleset for condition_id
* Validate ruleset schema
* Resolve ruleset_version (hash or version string)
* Failure → abort request.

**Step 0B — RuntimeState construction**
Case 1: Fresh initialisation

For each answer_key in the ruleset:

answers[answer_key] = {
  value: null,
  source: "unanswered",
  encoder_value: null
}


Construct:

RuntimeState = {
  condition_id,
  ruleset_version,
  free_text,
  answers,
  safety_evaluation: {
    triggered_rules: [],
    messages: []
  }
}

**Case 2: Canonical hydration (round-trip)**

Accept RuntimeState from request

Validate:
* condition_id matches ruleset
* every ruleset answer_key exists exactly once in answers
* no extra or missing keys
* source ∈ {unanswered, encoder, encoder_confirmed, encoder_corrected, patient}
* encoder_value is immutable (cannot be changed client-side after first set)
* On submission: encoder → encoder_confirmed or encoder_corrected. This must be an assertion, not a convention.

Reject any attempt to:
* reconstruct provenance
* infer missing data
* coerce partial payloads

Then:
RuntimeState = request.RuntimeState

No mutation occurs in Step 0.

**Step 0C — Encoder eligibility pre-check (no execution)**

Compute and store (not act on):

encoder_eligible = (
  free_text is non-empty
  AND exists answer_key where:
       send_to_encoder == true
       AND source == "unanswered"
       AND encoder_value == null
)

---

## Step 1 — Encoder pass (single-shot)

Encoder runs once using:

* free text
* encoder prompts from ruleset
* ONLY if encoder_eligible = true
* if encoder_eligible = false, skip step 1 entirely

**Encoder output (example)**

```
{
  dysuria_present: true,
  fever_present: true
}
```

**State mutation rules**

* Populate `encoder_value`
* Populate `value` ONLY if encoder_value = null AND source = unanswered
* Set `source = encoder`

**Runtime state after encoder**

```
answers: {
  dysuria_present: {
    value: true,
    source: "encoder",
    encoder_value: true
  },
  fever_present: {
    value: true,
    source: "encoder",
    encoder_value: true
  },
  symptom_onset_text: {
    value: null,
    source: "unanswered",
    encoder_value: null
  }
}
```

**Invariant check**

* Encoder never overwrites patient data
* Encoder never runs twice for the same key
* Encoder output is retained separately and immutably
* Skipped encoder produces identical state

---

## Step 2 — UI render

UI receives:

* question text
* current `value`
* `source` flag

Rendering of answers by source:
* source == encoder → render as “suggested”
* source == encoder_corrected or encoder_confirmed → render as “confirmed”
* source == unanswered → render as empty
* BUT all answers can be changed at any time by user - just because something is confirmed, doesnt mean the user cannot change their mind later

No logic occurs here.

---

## Step 3 — Patient overrides one answer

Patient changes:

* `fever_present = false`

**Mutation rules**

* Set `value = false`
* Set `source = encoder_corrected`
* Leave `encoder_value` untouched

**Runtime state**

```
fever_present: {
  value: false,
  source: "encoder_corrected",
  encoder_value: true
}
```

---

## Step 4 — Patient completes text field

Patient answers:

* `symptom_onset_text = "2 days ago"`

**Runtime state**

```
symptom_onset_text: {
  value: "2 days ago",
  source: "patient",
  encoder_value: null
}
```

---

## Step 5 — Submission and safety evaluation

Clicks submit
* all source: encoder fields flipped to encoder_confirmed or encoder_corrected
* Projection fed into safety engine**

```
{
  dysuria_present: true,
  fever_present: false,
  symptom_onset_text: "2 days ago"
}
```

* Encoder provenance is invisible here.

**Safety rule**

```
IF fever_present == true
```

**Result**

* Rule not triggered
* No safety message

**State update**

```
safety_evaluation: {
  triggered_rules: [],
  messages: []
}
```

---

## Step 6 — Clinical output generation (lossy)

```
{
  condition_id: "urinary_symptoms",
  free_text: "Burning when peeing and feel hot",
  answers: {
    dysuria_present: true,
    fever_present: false,
    symptom_onset_text: "2 days ago"
  },
  safety_messages: []
}
```

**Explicitly excluded**

* encoder_value
* source
* rule traces

---

## Step 7 — Audit / debug output (lossless)

Entire runtime state +:

* raw encoder outputs
* ruleset hash
* timestamps

Retention-limited, access-controlled.

## 0. Clarify the training target

 We are training:
* A frozen text encoder (likely transformer)
* Plus **N independent binary heads**, one per `answer_key`
* Each head learns:
  `free_text → {true | false | null}`

Implications:

* Training data must be **labelled per-head**, not per-condition
* Cross-signal co-occurrence is noise unless intentionally modelled
* The encoder must explicitly learn absence as well as presence of true and false

## 1. Define a signal-centric ontology

### 1.1 Source of truth
Clinical meaning is defined only in the clinical ruleset.
answer_key is the sole identifier shared between:
ruleset
encoder heads
training data
No semantic reinterpretation exists outside the ruleset.

### 1.2 Global extraction invariants (apply to all signals)
These rules are universal and non-negotiable:
The label space is {True, False, None} for every signal
None means unknown or unmentioned, never absence
False is assigned only on explicit negation
Ambiguous language maps to None, never to True or False
Absence of any mention of a symptom is always None
No signal may be inferred implicitly from other signals
At most one decisive mention (positive or negative) per signal per example
Contradictory mentions within a single signal are forbidden
These rules define the meaning of labels during training and must never vary by signal.

### 1.3 Minimal SignalSpec (constraint-only)

SignalSpec exists only to impose additional mechanical constraints when required by linguistic structure. It never defines meaning.

SignalSpec {
  answer_key: "fever_present"
  max_mentions: 1              # default = 1
  disallowed_fragment_types: []  # optional
  notes: "free-text extractor constraints only"
}


Properties:
answer_key must exist in the clinical ruleset
SignalSpec is optional; most signals may not need one
SignalSpec must never:
redefine semantics
alter label meaning
encode safety importance
introduce alternative label behavior
If no extra constraints are needed, SignalSpec is omitted.

### 1.4 Label assignment (training-time)

Every generated example must carry an explicit label for every signal
Labels are assigned before text assembly
Labels are never inferred from assembled text
None is treated as a first-class outcome and must dominate the dataset
Label distributions are managed globally, not per signal.

### 1.5 Consequences of this design

The ruleset remains the single clinical authority
Extraction behavior is consistent across all signals
Null semantics are universal and auditable
Per-signal differences are constrained, not expressive
Training logic cannot accidentally encode importance or safety

## 2. Atomic symptom fragment generation

For each signal, we generate atomic text fragments

Example buckets for `fever_present`:

1. **Positive fragments** that map to true
Including clear signals:
   * “I’ve had a fever for two days”
   * “I’ve been feeling hot and shivery”
   * “High temperature overnight”

But also confounding signals:
   * "I didn't really think that I'd had a fever but when I checked my temperature it was up at 38.0"
   
2. **Negative fragments** that map to false

Clear signals
   * “No fever at all”
   * “I haven’t felt feverish”
   * “Temperature has been normal"

Confounding signals:
   * "I felt very hot and cold all day but the thermometer has been reading normal"

3. **Ambiguous / weak fragments** that map to null

   * “Felt a bit off”
   * “Had chills but not sure”
   * “Maybe slightly warm”

Confounders that map to null
   * “Night sweats”
   * “Hot flushes”
   * “After exercise I felt hot”

You should **over-generate** here (e.g. 200–500 per bucket) because these fragments will be reused combinatorially.

Do **not** ask the LLM to label these. Label by construction.

---

## 3. Other symptom fragment library

Create a similar library of fragments for all other signals that map to that condition
For example for urinary symptoms
* fever_present
* dysuria_present
* urinary_frequency_present
* flank_pain_present
* nocturia_present

---

## 4. Non-signal filler fragment library

Create a large library of fragments that mention **other things**:

* Administrative noise
* Patient's ideas about diagnosis
* Irrelevant context and life details
* Patient's expectations about treatments

Purpose:

* Teach the encoder that *not everything is relevant*
* Prevent shortcut learning (“medical-sounding text → positive”)

This library should be **larger** than any single signal’s library.

---

## 5. Controlled recombination engine (your Python script)

For first run, we will recombine only 2 fragments for one signal fever_present

### 5.1 Decide labels first (top-down)

For each signal independently:

* Sample target label from a predefined distribution
  e.g.

  * null: 60%
  * false: 25%
  * true: 15%

This prevents label leakage.

### 5.2 Materialise fragments to satisfy labels

For each signal:

* `true` → include exactly 1 positive fragment
* `false` → include exactly 1 negative fragment
* `null` → include either **zero** fragments from that signal’s library or include ambiguous / weak fragments that map to null
* Never include both positive and negative fragments for the same signal
* Never include positive and negative fragments in addition to an ambiguous / weak fragment that maps to null

### 5.3 Add distractors and shuffle

Add a randomly chosen fragment from:
* other signal libraries e.g. dysuria_present
* filler libraries
Then shuffle order

### 5.4 Expansion

Once the concept has been proven, we can:
* Expand to larger numbers of fragments using the same overall structure
* Add intros and outros
* Add the occasional irrelevant signal from signal libraries from other conditions (e.g. include a headache fragment in a urinary symptoms consultation blurb)
* Add surface level variations: temporal variation, spelling variation, disfluences

End goal
* Variation in length of total blurb - some very short, some very long and everything in between
* True and false fragments can be at the beginning, the middle or the end

---

## 6. Dataset partitioning strategy

Split by **fragment**, not by example.

If the same atomic fragment appears in both train and validation:

* You are leaking lexical shortcuts
* Validation accuracy becomes meaningless

Rule:

* Fragment libraries are split first
* Recombination happens independently per split

---

## 7. Training-time safeguards

During training:

* Train heads independently or with masked loss per head
* Penalise confident predictions on null
* Track:

  * False positives on null
  * Confusion between false vs null

Good. Before touching code, there are **three distinct layers of data structures** you must design, and they serve different purposes. Confusing them is the fastest way to poison training.

I’ll structure this as:

1. What must be decided
2. The concrete data structures
3. Design rules and recommendations
4. Common traps to avoid

No implementation yet.

---

## 1. What must be decided up front

You need to lock decisions in five areas:

1. **Signal definition granularity**
2. **Fragment taxonomy**
3. **Label semantics (true / false / null)**
4. **Recombination contract**
5. **Dataset output schema (training-facing)**

If any of these remain vague, the Python structures will drift and become unmaintainable.

---

## 2. Core data structures (conceptual, not code yet)

### 2.1 SignalSpec (one per encoder head)

This mirrors your ruleset `answer_key`. It must align **exactly** with production.

Fields you need to decide:

* `answer_key` (string, canonical)
* `description` (human-readable, internal)
* `allowed_labels` = {True, False, None}
* `target_distribution` (probabilities for sampling)
* `requires_negative_examples` (bool)

Recommendation:

* Store this as a **pure config object**
* No text here, no fragments

This is your contract between training and runtime.

---

### 2.2 FragmentLibrary (per signal, per split)

Fragments are **atomic**, reusable, and labelled by construction.

You need **four fragment types**, minimum:

* `positive`
* `negative`
* `ambiguous`
* `confounder`

Each fragment entry needs:

* `fragment_id` (stable)
* `text`
* `signal_key` (or `None` for filler)
* `fragment_type`
* `metadata` (optional: tone, length, formality)

Important:

* Ambiguous fragments are **never** used to generate `true` or `false`
* Confounders belong to a signal but should usually label as `null`

Recommendation:

* Fragment libraries are **immutable after generation**
* Split them into train/val/test at the fragment level

---

### 2.3 FillerLibrary (global, signal-agnostic)

This is not optional.

Fields:

* `fragment_id`
* `text`
* `category` (symptom_other, admin, temporal, irrelevant)

These fragments **must never imply any target signal**.

They exist to:

* Break lexical shortcuts
* Increase entropy
* Teach absence

---

### 2.4 ExampleSpec (pre-text, label-first)

This structure exists **before text assembly**.

Fields:

* `example_id`
* `labels: Dict[answer_key, True | False | None]`
* `included_signals: Set[answer_key]`
* `length_class` (short / medium / long)
* `style_flags` (optional, later use)

This enforces:

* Labels are sampled independently
* Text is subordinate to labels

If you skip this layer, leakage is guaranteed.

---

### 2.5 AssembledExample (training output)

This is what hits disk.

Fields:

* `text`
* `labels: Dict[answer_key, 0/1/None]`
* `metadata`

  * fragment_ids_used
  * generation_seed
  * split

Recommendation:

* JSONL
* One row = one text blob
* Labels stored per-head, not flattened

This aligns cleanly with multi-head encoder training.

---

## 3. Design rules you should enforce

These are non-negotiable if you want clean training.

### Rule 1: Label-first generation only

Never infer labels from text.
Ever.

### Rule 2: One signal, one decisive fragment

For a given signal in an example:

* At most one positive OR one negative fragment
* Never both
* Never multiple positives

### Rule 3: Null means structural absence

Null examples must include:

* No signal fragments
* Or ambiguous/confounding fragments only

### Rule 4: Fragment reuse is allowed, fragment leakage is not

* Same fragment can appear in many examples
* Same fragment must not cross train/val/test

### Rule 5: Signals are independent by default

Co-occurrence is noise unless explicitly modelled.
Do not encode clinical correlations yet.

---

## 4. Recommendations (hard-earned)

### 4.1 Start smaller than you think

For MVP encoder training:

* 3 signals
* ~200 fragments per signal
* ~10k recombined examples

You will learn more from errors than scale.

---

### 4.2 Track null performance explicitly

Add evaluation metrics for:

* False positive on null
* Confidence calibration on null

If null collapses, your safety boundary breaks.

---

### 4.3 Keep production alignment sacred

Every `answer_key`:

* Must exist in ruleset
* Must exist in training labels
* Must have identical semantics

No experimental keys.

---

### 4.4 Expect to regenerate everything

Design structures so you can:

* Regenerate datasets deterministically
* Add new fragment types
* Rebalance label distributions

If regeneration is painful, the design is wrong.

---

## 5. Common traps to avoid

* Generating “realistic” narratives too early
* Letting LLMs invent negatives
* Overusing ambiguous fragments
* Encoding clinical logic into generation
* Treating null as false during training

---

## Next step (recommended)

Before writing code, the next concrete step should be:

1. Write **SignalSpec objects** for your 3 MVP signals
2. Define **exact label distributions**
3. Decide **fragment taxonomy and counts per signal**

Only after that should we sketch Python dataclasses and file layouts.

If you want, next we can:

* Draft the exact dataclass definitions
* Or walk through one signal end-to-end (e.g. fever) as a worked example

# Provisional plan: the urinary frequency / nocturia labelling question

**Status: provisional (step 1). Not built from.** This is the discussion-stage
output. It needs the step-2 review pass before it becomes tasks, and it carries
two open decisions (section 4) that change what gets written.

Read first: `arch_training.md` sections 4, 5, 7, 8, 12.3, 12.5, 12.9;
`reports/encoder_training/2026-08-19.md` sections 5, 6 and 8;
`data/synthetic/manifest.json` for the `nocturia_present` and
`urinary_frequency_present` libraries.

---

## 1. The problem this exists to solve

The 2026-08-19 companion run fixed the invented-symptom failure across the board
(191 asserted-but-unmentioned answers down to 35) and paid for it almost entirely
on one signal: `urinary_frequency` real-text recall fell from 71.5% to 41.5%,
roughly 8 of its 26 decisive cells. That is the only detection loss in the run
backed by more than a couple of submissions, and section 8 of the report makes
fixing it the first item of follow-on work.

Two candidate causes were on the table at the start of this discussion:

* **Intrinsic difficulty.** An encoder cannot know what a normal voiding
  frequency is, so "six times a day" is unjudgeable in a way that "there was
  blood in my urine" is not.
* **Labelling.** All nocturia is urinary frequency; not all urinary frequency is
  nocturia. The libraries do not encode that, and the two signals are being asked
  to separate something they overlap on.

The first is real but narrower than it looks, and the second is the larger lever.
Both readings are set out below with what was checked.

## 2. What was checked, and what it showed

### 2.1 The question already carries the comparative

`data/uti1.json`, question `urinary_symptoms_2`, asks *"Are you needing to pass
urine more frequently than usual?"* and its `encoder_prompt` is *"Does the
response indicate the patient is passing urine more frequently than usual?"*.

The model is therefore not being asked to judge absolute normality. It is being
asked to detect a claim of **increase against the patient's own baseline**, and
roughly 40 of the 46 lines in `urinary_frequency_true.txt` state one explicitly
("more than usual", "normally three or four and it's more like fifteen now",
"which isn't like me at all").

The residual gap is the **bare-quantity** statement — "It's every hour on the
hour", "Hourly at least", "I'm going every twenty minutes" — where a rate is
given and no comparison is made. That is a narrow, fixable coverage gap. It is
also the thing open decision A has to settle before any fragment is written,
because the two answers produce different libraries and different gold.

### 2.2 The 14 undeclared pairs are a loss mask, not a shrug

`arch_training.md` section 4 records 16 deliberately undeclared `null_on` pairs,
**14 of which are the nocturia / urinary-frequency pair in both directions**.
Follow that through the training path — `recombine.build_pools`,
`recombine.label_vector`, then `dataset.py` around line 486 and `mask_vector` —
and the consequence is stronger than "a smaller companion pool":

* A missing signal key is a **loss mask**, not a `null` label.
* So in the joint six-head model, the `urinary_frequency` head has **never seen a
  single training example containing night-time voiding language, at any label**.
  Every nocturia example is masked for it, and vice versa.
* And because companion eligibility is gated on `null_on`, nocturia's ~300 lines
  are the one large pool `urinary_frequency` could not draw companions from.
  Companions were where the whole 08-19 gain came from, and this is a plausible
  reason `urinary_frequency` was the signal with the least of it (+18.5 points
  against 49–80 elsewhere).

This is the mechanism the plan is built around. It is a strong hypothesis and it
is not yet confirmed against the actual misses — see task 0.

### 2.3 The subsumption rule is library-level, not per-line

`arch_training.md` 12.5 records that cross-signal `true`/`false` is
inexpressible: `null_on` only carries "null on every line", `Fragment.signal_key`
is singular, and `label_vector` raises if two fragments assert the same signal.
Section 4 files the nocturia pair under "per-line facts a library-level field
cannot state", and points at per-line label vectors (12.3) as the fix.

**Under the subsumption rule that stops being true.** If all nocturia is urinary
frequency, then every line of `nocturia_true` asserts urinary frequency, because
every line of `nocturia_true` asserts nocturia. That is a property of the whole
library, so it needs a library-level field and not the JSONL-per-line rebuild.
This is materially smaller than 12.3 and is the main reason this plan is worth
running now rather than after 12.3.

### 2.4 What the rule does to the 67-submission gold

Cross-tab of `data/realistic/uti1_holdout.labels.tsv`:

| | nocturia `null` | nocturia `true` |
|---|---|---|
| **UF `null`** | 36 | **5** |
| **UF `true`** | 22 | 4 |

Adopting subsumption flips exactly **five cells**: the UF `true` slice goes 26 →
31 and the `null` slice 41 → 36. Four are clean night-only frequency claims
(`holdout-0003` "up all night peeing", `holdout-0012` "get up three times during
the night", `holdout-0024` "4 to 5 times during the night, which is new for me",
`holdout-0054` "four or five times a night"). One is marginal: `holdout-0059`
describes a single night waking, and reading that as "passing urine more
frequently than usual" is a stretch.

Two things follow, and the second is the important one:

* **Relabelling the gold will not fix the score.** Five cells of 67 cannot turn
  41.5% recall into a usable number. The gain has to come from the training data.
* **The existing gold is internally consistent.** This was checked specifically,
  in case the labeller had already been applying the rule unevenly. It had not:
  `holdout-0035`, `-0039`, `-0048` and `-0067` are UF `true` because each carries
  a general or daytime frequency claim, not only a night one. There is no
  labelling bug to find here — this is a definition change, and it has to be
  argued and pre-registered as one.

### 2.5 The 22 cells that have to survive

`UF true / nocturia null` holds **22 of the 67** — the overactive-bladder shape,
frequency without night waking. It is the clinical discriminator the whole
proposal rests on being able to keep, and it is well supplied. That is what makes
the collapse risk in section 3 measurable rather than theoretical.

## 3. What could go wrong, stated before the run

**The heads collapse into each other.** If `nocturia_true` becomes a
`urinary_frequency` positive, the two heads see near-identical positive text and
may learn to predict the same thing. That would destroy exactly the
OAB-versus-UTI discrimination the proposal is motivated by, while the headline
number improved. **This has to be a declared criterion before the run, per the
house rule that a ceiling asserted after a disappointing number is an excuse:**

> The `UF true / nocturia not-true` cell must not empty, and head agreement on
> the synthetic test set must not exceed the pre-declared bound.

**Over-correcting on the 08-19 trade.** The encoder is advisory: it runs once on
free text and the patient then confirms or corrects (`arch_encoder.md`). A miss
degrades to "the patient answers the question themselves". An invention puts a
claim the patient never made in front of them, which they may accept passively.
41.5% recall is bad and worth fixing; it is not as bad as the report's framing
implies, and the 191 → 35 movement should not be traded back to recover it.

**Holdout contamination.** Changing gold labels after seeing a disappointing
number is the failure this project has already written rules against. The
definition has to be settled and written down first, and both arms scored against
both rubrics with both published.

**Non-comparability.** Expanding a library and changing the manifest both move
generated data, so DD16 applies: nothing here is comparable to any number on file,
including 08-19's. Every arm in this plan is regenerated.

## 4. Open decisions

These are the user's to make and they change what gets written. They are recorded
unresolved rather than assumed.

**A. Bare quantity with no comparative.** Is *"I go every hour"* / *"eight times a
day"*, with no comparison to the patient's own baseline, `true` or `null` for
`urinary_frequency_present`? This changes the fragment libraries, the
`encoder_prompt`, and possibly the gold. It is the single highest-value
clarification in the plan.

**B. The contrapositive.** If all nocturia is urinary frequency, then
`urinary_frequency_false` ("I'm going the same as always") entails nocturia
`false`. That is logically forced by the rule and would give the nocturia head 46
free negatives — it has **no** `false` examples anywhere in the 67, which the
08-19 report lists as blocking a real reading of three of six signals. The
recommendation here is to **hold it out of the first run**: it is the riskiest
inference in the set, and it can be added as a clean single-variable change
afterwards. Clinical call, not a technical one.

## 5. Design decisions proposed

**DD-A. The definition is written into the ruleset, not only into the labels.**
`urinary_symptoms_2`'s `encoder_prompt` currently says "more frequently than
usual" and is silent on whether night-time voiding counts. If subsumption is
adopted, the prompt says so explicitly. The prompt is what a future re-labeller
or a future LLM encoder reads; leaving it disagreeing with the labels is how the
decision gets silently reversed later.

**DD-B. Only `nocturia_true` asserts, and it asserts only `true`.** The
asymmetry is the whole clinical claim and the plan must not round it off:

| library | on `urinary_frequency_present` | basis |
|---|---|---|
| `nocturia_true` | **`true`** | new cross-signal assertion |
| `nocturia_false` | `null` | `policy` — denying night waking says nothing about daytime |
| `nocturia_null_*` (5 libraries) | `null` | `policy` |
| `urinary_frequency_true` | `null` on nocturia | `policy` — going often does not imply going at night |
| `urinary_frequency_null_*` (5 libraries) | `null` on nocturia | `policy` |
| `urinary_frequency_false` | *(open decision B)* | — |

Every one of these is `policy`, not `absent`: both libraries talk about the other
signal's territory and no lexicon can check them. That means notes on all of
them and `POLICY_PAIRS` growing by ~13, which is deliberate and reviewable.

**DD-C. Two arms in one comparison, not two sequential runs.** Same seed, counts,
fold triple and salt; differing in one thing, exactly the design that made the
08-19 report readable:

* **Arm A** — expanded `urinary_frequency` libraries, pairs still undeclared.
  Controls for "was it only ever a thin library".
* **Arm B** — the same expanded libraries plus all 14 pairs declared, including
  the subsumption assertion.

Sequential runs against a moving baseline would not be comparable to each other
(DD16), which is the whole reason for pairing them.

**DD-D. Expansion targets what is missing, not more of what is there.** The
library is already good at comparatives; more comparatives buy little. The gaps
worth writing into are bare-quantity claims (subject to decision A), indirect and
consequence phrasing ("planning journeys around toilets", "can't leave the
house"), urgency-adjacent wording, and deliberately more **UF-true-with-no-night-
mention**, which is what keeps the two signals separable under Arm B.

## 6. Sketched task breakdown

To be corrected and expanded in the step-2 pass. Task 0 comes first and is free.

**Task 0 — diagnose before spending a GPU.** Pull the ~8 `urinary_frequency`
submissions Arm P newly misses relative to Arm 0 and read them. If they are
night-flavoured, section 2.2's mechanism is confirmed and the rest of this plan
is justified. If they are bare-quantity or vague daytime, it is a coverage or
threshold problem and the relabelling will not touch it — in which case decision
A carries the ticket and DD-B can wait. **This decides the plan and costs an
afternoon.**

**Task 1 — settle and record the definition.** Decisions A and B; update
`urinary_symptoms_2`'s `encoder_prompt` per DD-A; write the rule into
`arch_training.md` beside the `null_on` table.

**Task 2 — relabel the five gold cells and pre-register.** Before any scoring.
Publish the criteria from section 3, including the collapse bound, and score both
arms against both rubrics.

**Task 3 — manifest and generator: library-level cross-signal assertion.** A
field alongside `null_on` (`also_asserts` or similar); `build_pools.signal_pool`
picks up an asserting foreign library as a `positive` for the target signal;
`label_vector`'s `asserted` map accepts a fragment asserting more than one
signal, with the existing two-fragments-one-signal guard intact. Companion
eligibility is unchanged: an asserting library is not `null_on` and so is not
drawn as a companion.

**Task 4 — write the fragments** per DD-D.

**Task 5 — declare the 13-or-14 pairs** per DD-B, with `policy` notes and
`POLICY_PAIRS` updated.

**Task 6 — generate, train and score the two arms** per DD-C, and write the run
up in `reports/encoder_training/`.

# Provisional Plan B — `not_sure` as a fourth encoder class

**Status:** provisional. Written for review (workflow step 2), not for
implementation. Nothing here is decided, and the first task is explicitly a
decision point that can end the plan.

**Prerequisite:** Plan A (`not_sure_A_answer_value.md`) must have shipped and
been in use. Without it the encoder has nowhere to put a fourth class — an
advisory `not_sure` prefill would collapse back to "leave blank" at
`encoder_mapping`, producing an identical patient experience and an identical
clinical output at the cost of a full retrain.

---

## Scope

The encoder head is `Linear(768, 3)` per signal (`scripts/encoder_training/model.py:20`),
over `CLASS_NAMES = ("false", "true", "null")` (`dataset.py:45`). This plan
splits `null` into `null` and `not_sure`, where `not_sure` means *the text says
the patient does not know*, and `null` keeps its existing meaning: the text does
not settle the question, including by being silent about it.

Everything here is offline tooling plus the encoder boundary contract. It
touches `scripts/synthetic_data/`, `data/synthetic/`, `scripts/encoder_training/`,
`data/realistic/`, and `app/models/encoder_contracts.py` +
`app/services/engine/encoder_mapping.py`. It touches no other part of `app/`.

---

## What is actually being claimed

The current libraries treat six axes of displacement as one label. `hedged`
displaces *certainty*; `thirdparty` displaces *person*; `historical` displaces
*time*; `metaphor`, *meaning*; `attribution`, *cause*; `adjacent`, *referent*
(`arch_training.md` §3). All six currently produce `null`.

The claim behind this plan is that the first of those six is different in kind:
the patient's own stated uncertainty is a fact worth reporting to a clinician,
where "the text is about someone else" or "the word was a metaphor" is not.

**That claim is about `hedged` only.** The other five stay `null`. Any version
of this plan that quietly promotes more than `hedged` is a different plan and
should be rejected in review.

---

## The cost, stated before the work rather than after

**Not the class count.** `Linear(768, 3)` → `Linear(768, 4)` is 2,307 → 3,076
parameters against a ~440MB base encoder. Capacity, training time and inference
cost are all unchanged to within noise.

**The costs that are real:**

1. **No new data arrives.** The fourth class is carved out of `null`, not added
   to the dataset. `hedged` is roughly 5–7% of generated examples, but the
   number that governs generalisation is effective n in *clusters*
   (`arch_training.md` §10) — order 40–50 fragments per signal, ~30 after the
   70/15/15 split, single digits in validation. The new class rests on that and
   nothing else. This is the binding constraint; everything else on this list is
   downstream of it.
2. **Macro-F1 stops being comparable.** Four classes at 1/4 weight each, with
   the new class the hardest, means the headline number falls with an
   identically-good model underneath. Every report in `reports/encoder_training/`
   becomes history rather than a comparator — the same status §10 already
   assigns to pre-2026-08-19 runs, and it must be recorded the same way.
3. **Errors currently free become visible.** A hedged text predicted as
   structural `null` is correct today. After the split it is an error. Measured
   accuracy falls with no model change. Some of this runs the other way and in
   our favour: `true` → `not_sure` is a much less harmful error than
   `true` → `null`, and it becomes visible for the first time.

**Where the cost concentrates.** Two new boundaries, and they are not alike.
`not_sure` vs structural `null` is easy — signal vocabulary present or absent.
`not_sure` vs `true` is the expensive one: same topic, same person, same tense,
separated only by whether the patient volunteered doubt. Essentially all the new
error mass lands there. Which is why Task 2 below is not optional overhead — it
is the thing that decides whether this costs two points or fifteen.

---

## The argument in favour, which is not the ML one

`arch_training.md` §9 records that a high score on the `true`/`null` boundary is
**bad** news: "a model at 95% has learned to detect volunteered doubt — a
discourse cue, not a clinical one — and will carry that into real submissions,
where the cue and the fact come apart."

If `not_sure` becomes a class the system deliberately reports, that objection
**inverts**. Detecting volunteered doubt is then exactly the specified job, and
a high score there is good news rather than a warning. That is the strongest
argument for this plan and it should be the one it is judged on.

It only works because Plan A gave the output somewhere to go. "Four classes
train better than three" is not an argument and is probably false here.

---

## Design decisions to make in review

### DD-B1. `hedged` and only `hedged`

Stated above. The five other axes keep `null`. Worth writing into the manifest
as an explicit per-library class rather than inferring it from the filename —
`arch_training.md` §4 already makes the case that meaning lives in the manifest
and never in a path.

### DD-B2. The `true` / `not_sure` boundary is a policy, and it is written down first

`arch_training.md` §9 already records this seam as broken:

- The fever policy is *unhedged first-person present subjective heat counts as
  `true`*. The `true`/`null` boundary is **already** decided by volunteered
  doubt, so promoting doubt to its own class moves that line and puts every
  `_true` library in scope for re-reading.
- "im pretty sure ive got a fever now" is recorded as **split across `true` and
  `hedged` today**, explicitly flagged as an undeclared policy.
- `recent_uti` rules 3 and 6 ("I had one last year", "I'm prone to them") live
  on the certainty axis but are not the patient being unsure *of the fact* —
  they are the text not settling the 30-day window. Those stay `null` and the
  files they live in do not map cleanly onto the new class.

**Recommendation:** the policy is written per signal, in the manifest or beside
it, and committed **before** the run that measures it. §9's own standard: "an
expected ceiling below the general target is declared per library, in writing,
before the run that measures it. A ceiling asserted after a disappointing report
is not a ceiling, it is an excuse."

### DD-B3. The gating constraint in DD9

`decision.py` chooses the margin maximising macro-F1 subject to a `null → true`
rate no worse than argmax's — the cell that invents a symptom into a patient's
form. With four classes, `not_sure → true` is **equally** symptom invention.

**Recommendation:** the constraint becomes both cells, and it is stated in
`decision.py`'s module docstring rather than left to be inferred from the code.
`not_sure → null` and `null → not_sure` are *not* gated: neither invents
anything.

### DD-B4. The real-text holdout must be relabelled, and it is the honest bottleneck

`data/realistic/` holds 67 hand-labelled submissions and
`arch_encoder_training.md` §11 already distinguishes `null` (a claim) from blank
(unjudgeable), with `holdout.py` refusing to merge them. A fourth class needs a
third distinction added by hand across 67 × 6 cells.

That is a day of careful work by one person, and §11 already bounds what the
result is worth: one voice, wide per-signal intervals, "a validity instrument,
not a precision one". **It cannot rank two models.** It can tell you whether the
new class exists in real text at all — which, for this plan, is the question
that matters most.

### DD-B5. `encoder_mapping` must drop `not_sure` where the question does not allow it

Plan A makes `allow_unsure` per question. The encoder is blind to the ruleset by
design (`arch_encoder.md`) and cannot know. So the containment layer must map a
`not_sure` prediction to "leave unanswered" for any question whose
`allow_unsure` is false. This is exactly the kind of rule `encoder_mapping.py`
exists to hold, and it must be a hard rule with a test, not a defaulting
behaviour.

---

## Provisional task breakdown

**Task 0 — the experiment that can end this plan. Do this first.**

Train four-class, then **collapse predictions back to three** (`not_sure` →
`null`) and score against the existing three-class test set. Same examples, so
it is paired, so the McNemar machinery already in the Arm B package applies
unchanged.

This answers the only question that matters up front: *did adding the class
damage the decisions we already make today?* If the collapsed four-class model
matches the three-class model, the fourth class is close to free and everything
below is bookkeeping. If it is materially worse, that has been measured before a
single fragment was rewritten.

`--test-dir` / `dataset.swap_test_split` (§4f) is the nearest existing
machinery and its id-and-fragment equality checks are the right model for what
the collapse must assert.

**Task 0 is a gate. If it fails, this plan stops and Plan A stands alone.**

**Task 1 — Label space.** `dataset.py` (`CLASS_NAMES`, `CLASS_*`, the
fragment-type → class mapping around `dataset.py:291`), `model.py`
(`N_CLASSES`), and the manifest field from DD-B1. Every module in
`scripts/encoder_training/` importing `CLASS_NAMES` — `metrics.py`,
`decision.py`, `report.py`, `holdout.py`, `baselines.py`, `train.py` — must be
checked for a hardcoded 3 rather than assumed generic.

**Task 2 — The policy pass (DD-B2).** The largest task by hand-effort and the
one that decides the outcome. Per signal: write the `true` / `not_sure` policy,
then re-read every `_true` and `_null_hedged` line against it. Expect to move
lines in both directions. `documentation/encoder_plans/fragment_authoring_prompts.md`
is the existing authoring reference and needs the new boundary added.

**Task 3 — Generator and lint.** `scripts/synthetic_data/`: the label mix now
has four classes (what replaces `15/25/60`?), `null_ambiguous` splits by axis,
and the companion `null_on` declarations need re-reading — a library declared
`null` on a foreign signal may now be `not_sure` on it, and §4's declarations
are the multi-symptom safety mechanism. The stats sidecar reports per-label
figures and gains a class.

**Task 4 — Decision rule.** DD-B3 in `decision.py` and `metrics.py`.

**Task 5 — Real-text holdout.** DD-B4: relabel `data/realistic/`, update its
README, update `holdout.py`.

**Task 6 — Encoder boundary.** `app/models/encoder_contracts.py` (`EncoderOutput`
validation admits the fourth value) and `app/services/engine/encoder_mapping.py`
(DD-B5). This is the only part of the plan inside `app/`.

**Task 7 — Retrain, rescore, write up.** Fold runs, the threshold criteria in
`thresholds.py` re-declared for four classes **before** the run, and
`arch_training.md` §10 updated to record that every prior measurement is now
history rather than a comparator.

---

## What would make me argue against this plan

Recorded now so it is not rationalised away later:

- **Task 0 shows a material loss on the collapsed comparison.** The fourth class
  is then costing accuracy on decisions that already reach patients, to gain a
  distinction Plan A already captures from the patient directly.
- **The relabelled holdout (DD-B4) shows `not_sure` is rare in real
  submissions.** §9 found patients volunteer explicit denials far more than
  expected; it may equally find they rarely volunteer uncertainty in writing, in
  which case the class is a training-set artefact.
- **Plan A ships and nobody presses the button.** DD-A3's open question 3 (log
  the usage) exists precisely so this is answerable with data rather than
  argued. If patients do not use the option when offered it directly, an encoder
  that predicts it is solving a problem nobody has.

Any one of those three is sufficient reason to stop, and stopping leaves Plan A
delivering the clinical value on its own.

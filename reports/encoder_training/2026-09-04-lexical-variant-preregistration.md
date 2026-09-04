# Lexical variant expansion — pre-registration — 2026-09-04

Task 6 of `documentation/encoder_plans/lexical_variant_expansion_implementation.md`.
**This document is written and committed before the first training run.** Its
bounds are what the result is read against; a bound chosen after seeing a number
is not a bound, and §12.9's "declare a bound before you train" is the precedent.

The run is one button: `lexical-expansion-2x2` in the training console
(`scripts/training_gui/runs.json`). Its steps, its paths and its rate are
literals in that entry, so what was run is recoverable from the repository
rather than from a shell history.

---

## What is being measured

Whether a head trained on a lexically expanded tree changes its answer less
often, when only the words change, than a head trained on the clean one — and
whether it pays for that with accuracy.

Four cells, `train tree × test tree`, each a separate five-fold `finetune`:

| | clean test | expanded test |
|---|---|---|
| **clean-trained** | the baseline | the diagnostic cell — *does the fault exist?* |
| **expanded-trained** | the guard cell | the robustness cell |

**Twenty trainings, not ten.** `--test-dir` is a single `Path`, not a repeatable
one, so an arm scored against both test trees needs two invocations and each
trains its own five folds. Four cells × five folds = twenty. At roughly ten
minutes a cell this is about **forty minutes of GPU**. The estimate is written
down here because a plan that budgets half the GPU time it needs is how a
measurement gets cut short.

### The operating point

`--rate 0.4 --clean-share 0.25`, giving p = (1 − clean_share) × rate = **0.30**.

This is the point `reports/synthetic_data/2026-09-04-fever-expansion-rules.md`
recommends from the library statistics, and it is a recommendation rather than a
tuned result. It matters because **1.0 is wrong**: applying every rule at every
site does not flatten `temperature`'s decisive-minus-displaced gap, it *inverts*
it (+0.140 at p = 0, through zero at p ≈ 0.30, to −0.298 at p = 1). A rule set
has an operating point, not a switch.

### The pilot signal

`fever_present`. Task 1 ranked it top for token–label skew and Task 5 authored
its rules. Nothing else is expanded until this reads out.

---

## The pre-registered bounds

### 1. Primary — the paired flip rate

The share of **changed** pairs whose predicted class differs between an arm's
clean-test and expanded-test scorings, computed by
`python -m scripts.encoder_training paired-flip-rate`.

* Unchanged pairs are excluded from the denominator. An example the pass left
  alone is byte-identical on both sides and cannot flip; counting it would lower
  every arm's rate by exactly the unchanged share, which is a fact about
  `--clean-share` and not about a model.
* The resampling unit is the **decisive fragment's cluster**, not the example.
  Ten thousand test examples sit on a few hundred clusters, and resampling
  examples would report an interval several times too narrow (§10).

**Success is the expanded-trained arm's flip rate falling by at least 5
percentage points against the clean-trained arm's, on the same pairs.** That is
deliberately a modest bound. Task 2 measured 15.4% flips on real text with an
interval of [2.6%, 33.3%]; nothing in this experiment has the resolution to
support a claim finer than "it moved" or "it did not".

**A rise in the flip rate is a result, and it is a bad one.** It would mean the
expanded arm learned the *new* vocabulary distribution as a shortcut rather than
learning to ignore vocabulary. Write it down as that.

### 2. Guard — decisive-cell accuracy, on the clean test tree, both arms

**The expanded-trained arm's pooled decisive-cell accuracy on the clean test
tree must not fall more than 0.02 below the clean-trained arm's.**

A head that answers `null` to everything has a flip rate of zero. Two thirds of
the test tree is `null`, so overall accuracy would not catch that and decisive
accuracy is the number that refuses to be gamed — §10 records the companion run
needing exactly this for exactly this reason. The comparison is against the point
estimate, not against separated intervals: the intervals overlap at any effect
this experiment could plausibly produce, and a guard that only fires on a
separated interval never fires.

The guard is scored inside the same `paired-flip-rate` invocation as the flip
rate, and that command exits non-zero when it fails. The two numbers only mean
anything together.

### 3. The negative control — what is expected to move on the synthetic test set

**Nothing.**

The clean synthetic test set is drawn from the same libraries under the same
vocabulary as the training split, so it **cannot contain** the failure this
ticket targets. This is the negative control 2026-08-19 described: "a large
synthetic gain would have meant a new shortcut rather than a removed one."

So:

* Clean-trained vs expanded-trained on the **clean** test tree: expected to be
  indistinguishable. That is the guard cell, and "no change" is it passing.
* A **large gain** there is a warning, not a result. It would mean the expansion
  manufactured a new shortcut — the DD5-adjacent hazard the rules report already
  found once, where a first draft of the rule set opened a 0.218 true/false
  vocabulary gap in `declarative_v1` where the library had 0.014.
* The cell that is *expected* to move is the diagnostic one: clean-trained,
  expanded test. If that cell is not worse than clean-trained on clean test, the
  fault this ticket targets does not reach the model and the pass has nothing to
  remove.

### 4. Effective sample size — pre-registered as unchanged

The expanded tree holds **exactly as many examples** as the clean one, paired
`example_id` for `example_id`. Expansion creates no fragments and no clusters, so
effective sample size is identical in every cell. No number in the result report
may be quoted as growth, and a gain can only mean robustness to paraphrase —
never better coverage.

### 5. The realistic set — a validity check, and nothing else

Both arms are scored against the 67 real submissions. At ±12 points overall and
±25 per signal (`holdout.py`) **that set cannot rank the arms**, and it is not
used to. It is there to catch the large failure — an arm that fell over on real
text — and reporting it as a tiebreak would spend the holdout's validity on a
comparison it cannot make.

---

## What a `stop` here would look like

If the diagnostic cell shows no degradation under paraphrase, the honest reading
is that the measured library skew does not reach the trained head at this rate,
and the pass should not be adopted for the remaining six signals (Task 7 does not
happen). That outcome costs forty minutes of GPU and is worth having written
down: it is the same shape as Task 2's gate, which was also built to be allowed
to fail.

## What this cannot establish

* **That the invariants are right.** Thirty-six hand-written rule invariants are
  the residual risk of the whole pass and no test reads one. A label flipped by a
  rule would show up here as *worse* accuracy in the expanded-trained arm, which
  the guard would catch — but only if it were large.
* **That real consultations improve.** Nothing in this experiment touches real
  text except the validity check, and that check cannot rank.
* **That the rate is right.** 0.4 at clean share 0.25 is one point on a curve
  read off library statistics. Sweeping it is a separate measurement and is not
  budgeted here.

## Results

*Empty on purpose.* Filled in by
`reports/encoder_training/<date>-lexical-variant.md` after the run described
above, item by item against the bounds in this document — **including the items
that failed.**

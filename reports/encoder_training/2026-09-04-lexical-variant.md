# Lexical variant expansion — the 2x2 — 2026-09-04

Task 6 of `documentation/encoder_plans/lexical_variant_expansion_implementation.md`,
read against `2026-09-04-lexical-variant-preregistration.md` item by item,
**including the items that failed.**

Run `20260904-204346-lexical-expansion-2x2`, all nine steps green, twenty
trainings, `roberta-base`, five folds, `--rate 0.4 --clean-share 0.25`
(p = 0.30), rules `31cc5290…`. The authoritative numbers are
`lexical/paired_flip_rate.json` and the four
`lexical/*/fever_present.arm_b_finetune.json`; where this document and one of
those disagree, the JSON is right.
`2026-09-04-lexical-variant-plain-english.md` is the same result in plain
language, for a reader who has not read `arch_training.md`.

---

## The one-paragraph answer

**The mechanism is real and the pass removes it. The pre-registered bound was
unattainable and is not met. The guard held on synthetic text and would not have
held on real text.** The clean-trained head flips on 1.9% of the pairs the pass
changed; the expanded-trained head flips on 0.8%, and 46 of the clean arm's 74
flips are `null → true` — displaced fever language being read as decisive once
the word changes, which is precisely the fault §8 and Task 1 describe. But the
flip rate was never anywhere near the 15.4% Task 2 measured on real text, so the
"falls by ≥ 5 points" bound could not be met arithmetically, and the diagnostic
cell shows the fault costs the clean head **0.2 accuracy points** on synthetic
text. Meanwhile the expanded arm's real-text profile moved a long way: `null`
recall +14 points, `true` recall −18, `null → true` rate 0.237 → 0.090. That is
a head that has become **more conservative**, which the synthetic guard scored as
an improvement and the real-text decisive slice scored as a loss.

---

## 1. Primary — the paired flip rate. **Bound not met.**

Pre-registered: the expanded-trained arm's flip rate falls by **≥ 5 percentage
points**.

| arm | flip rate | 95% CI | flips / changed pairs |
|---|---|---|---|
| clean-trained | **1.89%** | [0.95%, 3.39%] | 74 / 3910 |
| expanded-trained | **0.84%** | [0.31%, 1.92%] | 33 / 3910 |

**Fall: 1.05 points.** The bound is not met, and it was **not meetable**: a
baseline of 1.89% cannot fall by five. I wrote that bound anchored on Task 2's
15.4% flip rate over real submissions, and did not ask whether the *synthetic*
test split could produce a rate of that size. It cannot — the synthetic test set
is drawn from the same libraries as the training split, which is the same
observation DD8 makes about accuracy, applied to the flip rate and missed there.
**The pre-registration was wrong, not the result.** The correct bound would have
been relative, and on that reading the fall is 55%; but a bound rewritten after
seeing the number is not a bound, so the recorded outcome is *not met*.

Denominator: **3910 of 10,000** examples were changed (39.1%), over **417
clusters**. 6090 could not flip and are excluded. Both arms are scored on the
identical pair set.

### Direction — the finding the scalar hides

| transition | clean-trained | expanded-trained |
|---|---|---|
| `null → true` | **46** | 10 |
| `null → false` | 13 | 6 |
| `true → null` | 7 | 1 |
| `false → null` | 2 | 11 |
| `false → true` | 3 | 4 |
| `true → false` | 3 | 1 |

**62% of the clean arm's flips are `null → true`.** Rewrite `fever` as
`temperature` on a hedged, historical or third-party line and the clean head
starts calling it decisive. That is the exact shortcut Task 1 measured in the
libraries (`fever` on 41 of 45 `fever_null_historical` lines, 0 of 50
`fever_null_attribution` ones) and the exact reason the direction matrix is a
first-class output rather than something reconstructed later. The expanded arm
cuts it from 46 to 10.

### By label mode

| label mode | clean-trained | expanded-trained |
|---|---|---|
| `true` | 4.38% (25/571) | **0.53%** (3/571) |
| `null_ambiguous` | 2.76% (34/1231) | **0.89%** (11/1231) |
| `false` | 1.44% (15/1041) | 1.83% (19/1041) |
| `null_structural` | 0.00% (0/1067) | 0.00% (0/1067) |

The movement is concentrated exactly where fever vocabulary lives — `true` and
`null_ambiguous` — and the expanded arm is *slightly worse* on `false`, with
intervals that overlap. `null_structural` never flips in either arm on 1067
changed pairs, which is the sanity check the whole measurement needed: those
examples carry no signal language, only Tier A contractions were rewritten in
them, and neither head moved. A non-zero number there would have meant a rule
was changing meaning.

---

## 2. Guard — decisive-cell accuracy on the clean test tree. **Held.**

Pre-registered: a drop of no more than **0.02**.

| arm | decisive accuracy (clean test) | 95% CI |
|---|---|---|
| clean-trained | 0.9329 | [0.9119, 0.9527] |
| expanded-trained | 0.9449 | [0.9236, 0.9633] |

**Drop: −0.0120** — the expanded arm is 1.2 points *better*. The guard held with
room, and `paired-flip-rate` exited 0.

**Read this cautiously.** It held in the sense that the expanded arm did not buy
its flip rate by refusing to commit *on the synthetic tree*. Section 5 shows it
did buy something on real text, and this guard did not see it.

---

## 3. Negative control (DD8) — expected movement on the clean synthetic test set: **nothing.** Roughly held.

| cell | overall | decisive | macro-F1 | `null → true` |
|---|---|---|---|---|
| clean-trained, clean test | 0.9528 | 0.9329 | 0.9372 | 0.0242 |
| clean-trained, **expanded** test | 0.9513 | 0.9308 | 0.9355 | 0.0285 |
| **expanded**-trained, clean test | 0.9611 | 0.9449 | 0.9474 | 0.0174 |
| **expanded**-trained, expanded test | 0.9598 | 0.9430 | 0.9459 | 0.0184 |

Every 95% interval on those decisive figures spans roughly ±2 points and all four
overlap heavily. **No pair of cells here is separated**, and — because the four
cells live in four separate reports — there is no paired McNemar between them:
`--test-dir` produces one report per invocation, so the arms are compared through
unpaired intervals only. That is a real limitation of the measurement as built,
not a property of the data.

The 1.2-point gain on the clean tree is in the direction DD8 warns about. At this
size, against these intervals, the honest reading is **noise, or mild
augmentation benefit** — more surface variety in training generalising slightly
better — rather than a manufactured shortcut. Two things argue against the
shortcut reading: the gain is the same size on *both* test trees (+1.2 clean,
+1.2 expanded), which is what augmentation looks like and not what a
vocabulary-specific shortcut looks like; and `--dry-run-lint` passed with zero
lexicon hits introduced across all 36 rules over 3506 library lines.

### The diagnostic cell — does the fault reach the model?

Clean-trained loses **0.21 decisive points** moving from the clean test tree to
the expanded one (0.9329 → 0.9308). On accuracy, the fault barely reaches the
model at all.

This is the result that most changes what the ticket is worth. The flip rate says
the head's *decisions* move on 1.9% of rewritten examples and move in a
systematic direction; the accuracy says those movements very nearly cancel —
`null → true` errors introduced are offset by cases the rewrite happens to fix.
A pass that removes a systematic error which costs 0.2 points of accuracy is
removing something real and small.

---

## 4. Effective sample size — pre-registered as unchanged. **Held, mechanically.**

Both trees hold 10,000 test examples over the same clusters; the flip denominator
resamples **417 clusters**, identical in both arms. Expansion creates no
fragments and no clusters. **No number in this report is growth.** One line
written twelve ways is one idea.

DD5 telemetry — realised substitution density per 100 words, by label, on the
training split: `true` 1.12, `false` 1.49, `null` 1.32, largest gap **0.38**.
The pass is label-blind by construction, so a gap is a statement about the
libraries: `false` lines contain more matchable phrasing than `true` ones. It is
in the same direction as, and smaller than, the `declarative_v1` imbalance the
rule-authoring report found and added `any fever → any temperature` to hold down.

---

## 5. The realistic set — a validity check. **It caught something, and it is not a ranking.**

67 submissions, ±12 points overall and ±25 per signal. **This set cannot rank the
arms and is not used to.** It is here to catch the large failure, and it did.

| | clean-trained | expanded-trained |
|---|---|---|
| overall accuracy (mean of 5 folds) | 0.737 (sd 0.091) | **0.812** (sd 0.044) |
| decisive accuracy | **0.767** (sd 0.173) | 0.656 (sd 0.107) |
| `null` recall | 0.727 | **0.869** |
| `true` recall | **0.600** | 0.422 |
| `false` recall | **0.933** | 0.889 |
| `null → true` rate | 0.237 | **0.090** |

**The expanded arm became more conservative on real text.** Overall accuracy rose
7.5 points because 49 of the 67 submissions are `null` and the arm calls `null`
more often. Decisive accuracy fell 11 points, driven by `true` recall dropping
from 0.600 to 0.422 — on **nine** `true` submissions per fold, so that difference
is under two submissions and sd is 0.24–0.37. Nothing here is separated.

Two observations that are worth more than the point estimates:

* **The `null → true` rate fell in four of five folds** (0.531→0.020, 0.224→0.082,
  0.204→0.102, 0.122→0.082, 0.102→**0.163**). Over-calling `true` on `null`
  submissions is a failure mode this project has tracked since 2026-08-09, and
  this is the largest single movement in the run.
* **It is not the margin.** The expanded arm selected *lower* margins on three of
  five folds (0.25/0.40/0.00/0.80/0.00 against 0.55/0.55/0.00/0.45/0.10), and a
  lower margin makes `true` *easier* to reach. The head itself became less willing
  to say `true`, against the direction its own decision rule moved.

**What this means for the guard.** DD7 put the guard on synthetic decisive
accuracy specifically to catch an arm that lowers its flip rate by answering
`null` more often. On synthetic text that arm's decisive accuracy went *up*, so
the guard held; on real text its decisive accuracy went *down* by 11 points. **The
synthetic decisive-cell guard did not proxy for the thing it was designed to
detect.** That is the most important methodological finding in this run, and it
is a fault in the pre-registration rather than in the code.

---

## What was learned about the measurement itself

* **Twenty trainings produced ten distinct models**, and the run proves it: the
  two cells of each arm report byte-identical holdout figures, because they train
  on the same tree with the same seeds and differ only in what they are scored
  against. The predicted ~20 minutes of redundant GPU was spent as predicted.
  Making `--test-dir` repeatable would recover it and would also make the arms
  comparable by McNemar, which section 3 records as the measurement's main gap.
* **`changed_share` recorded `null` in all four reports.** The header read a
  `changed_share` key; the sidecar has `changed_examples.share`. Fixed in this
  PR with a regression test that asserts the value rather than its presence. The
  number itself was never lost — it is in the sidecars and in the run log
  (0.3896 over the whole tree, 0.391 on the test splits).
* **The rule dry run is worth its seconds.** 36 rules over 3506 library lines,
  1968 rewritten, zero lexicon hits introduced or removed.

---

## Was the pass adopted?

**Not yet, and not on this evidence alone.** The recommendation is:

1. **Do not extend to the other six signals (Task 7) on these numbers.** The
   accuracy case is 0.2 points on synthetic text and unmeasurable on real text.
   Rolling a pass out across six signals on an unseparated 1.2-point gain is how
   a project acquires machinery it cannot later evaluate.
2. **The direction result is worth keeping and worth re-testing.** `null → true`
   falling 46 → 10 under paraphrase, and the real-text `null → true` rate falling
   0.237 → 0.090, are the same finding seen through two instruments. If the next
   ticket wants one thing from this, it is that.
3. **The next measurement should be powered on real text, not synthetic.** Every
   bound in this pre-registration was written against a synthetic tree that, by
   DD8's own argument, cannot contain the failure. The instrument that saw
   something was the 67 submissions, and it cannot rank. That is the gap to close
   before spending more GPU here.

## What this does not establish

* **That the invariants are right.** Thirty-six hand-written rule invariants
  remain the residual risk and no test reads one. A label flipped by a rule would
  appear as worse accuracy in the expanded arm; none is visible, but "none
  visible at ±2 points" is the whole of the assurance.
* **That the rate is right.** 0.4 at clean share 0.25 is one point on a curve read
  off library statistics. No sweep was run.
* **That real consultations improve.** The only real-text numbers here are a
  validity check that cannot rank, and its decisive slice moved the wrong way.

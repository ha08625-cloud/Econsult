# Swap class expansion — pre-registration — 2026-09-05

Task 8 of `documentation/encoder_plans/lexical_variant_expansion_v2_implementation.md`.
**This document is written and committed before the first training run.** Its
bounds are what the result is read against; a bound chosen after seeing a number
is not a bound. `2026-09-04-lexical-variant-preregistration.md` is the precedent
and the cautionary tale — its primary bound was arithmetically unattainable
before a model was trained, and §4.1 below is written to not repeat that.

Read first: the plan's DD5 (the arms), DD7 (the metric), DD10 as amended (affect
is its own arm), and the v1 result `2026-09-04-lexical-variant.md`, whose 1.89%
is the anchor for everything here.

---

## 0. What is already verified, on CPU, before any GPU time

All four checks below were run on 2026-09-05 against this commit. They are
recorded because each one is a way the night could be wasted, and each costs
seconds.

| check | command | result |
|---|---|---|
| the clean tree still reproduces | `generate-folds --folds 5 --signal fever_present` | fold0 counts identical to the 2026-09-04 run log (train true=1493 false=2471 null=6036 rejections=80) |
| **the v1 arm still reproduces** | `expand --rate 0.4 --clean-share 0.25 --seed 42 --rules signal` | `substitutions/100 words=1.375, largest by-label gap=0.3016, changed examples=27274 (0.3896)` — **identical to the 2026-09-04 log line**, and the test-split denominator is **3,910**, the same number that report's flip rate is computed over |
| the ruleset is unchanged | `hash_ruleset_file('data/uti1.json')` | `325b3306…`, as recorded in the v1 run's header |
| the libraries are unchanged | `git log --since=2026-09-04 -- data/synthetic` | empty |

The second row is the load-bearing one. DD6a and DD12 both weaken or change
behaviour that a hand-written rule file also passes through, and both were
specified as **gated to class-generated rules** precisely so that the v1 arm
stays the 2026-09-04 anchor. That gating is now checked rather than asserted: the
v1 arm is byte-identical after Tasks 2–5. A v1 arm that did not reproduce would
not be an anchor, and the batch would have to be read against nothing.

---

## 1. The five arms, and which one decides

DD5's arms, with the invocation each one is, and the changed-pair denominator
each one will produce on the 10,000-example test split. **The denominators are
measured, not projected** — the four expansions were run on CPU at the operating
point below and their sidecars read.

| arm | expansion invocation | subs/100 words | changed test pairs | share |
|---|---|---|---|---|
| `clean` | none | — | — | — |
| `v1` | `--rules signal` | 1.375 | **3,910** | 39.1% |
| `classes` | `--rules classes --class-groups referent,calendar,setting` | 0.583 | **1,983** | 19.8% |
| `combined` | `--rules both --class-groups referent,calendar,setting` | 1.944 | **4,873** | 48.7% |
| `affect` | `--rules classes --class-groups affect` | 0.200 | **729** | 7.3% |

All four at `--rate 0.4 --clean-share 0.25 --seed 42` (p = 0.30).

**The decision arm is `combined`. The other four are exploratory and are named as
such here, before the night.** §13 says this discipline is what replaces gating,
and with five arms and seven read-outs apiece a winner appears by noise if the
arm is picked afterwards. A positive result in an exploratory arm alone is a
hypothesis for another night, not a finding.

### What the `classes` arm actually contains

Substitutions on the test split, by group: **referent 1,818 (79.5%)**, calendar
255 (11.1%), setting 215 (9.4%). So the `classes` arm is readable as a referent
measurement with that caveat stated, and §4.2's bound is written against the
bundle rather than against referents alone. A referent-only sixth arm was
considered and rejected: it would buy an 80% → 100% attribution improvement for
another two invocations and another multiple comparison, and the two small groups
are declared no-ops on the same grounds as the referent classes.

---

## 2. The batch, and what it costs

`--test-dir` is a single `Path`, so an arm scored against two test trees needs
two invocations and each trains its own five folds. The clean-trained arm is the
paired baseline for every expanded arm, so it is scored against all five trees.

| trained on | scored on | invocations |
|---|---|---|
| clean | clean, exp-v1, exp-classes, exp-combined, exp-affect | 5 |
| exp-v1 | clean, exp-v1 | 2 |
| exp-classes | clean, exp-classes | 2 |
| exp-combined | clean, exp-combined | 2 |
| exp-affect | clean, exp-affect | 2 |
| | | **13** |

**13 × 5 = 65 fold-trainings, ≈ 130 minutes of GPU** at the 2 min/fold §13
budgets. A night holds about 240, so this fits with room. Four
`paired-flip-rate` invocations follow, one per expanded arm, each with the
clean-trained arm as its baseline.

The batch **opens** with `smoke-cuda`, the reproduce check (§5) and
`--dry-run-lint` over every rule and class file. A wasted night should fail in
minute five, not hour eight.

**25 of the 65 trainings are redundant** — the five clean-trained invocations
differ only in `--test-dir` and their output paths, so they train the identical
model five times. That is a limitation of the CLI as built, not a design choice,
and it is worth its 50 minutes because it also buys the determinism cross-check
in §5.2.

---

## 3. The safety posture, written down because it changed

**After DD6a, no class in this ticket is protected per-rule by either mechanical
layer.** Layer 2 is vacuous for calendar, setting and affect, and after the
person-class normalisation it is only a floor for referents; layer 3 passes
trivially because not one of the 71 members appears in any of the seven
`SIGNAL_LEXICONS`. The **declared class invariants, `--dry-run-lint`, and the
committed-file tests are the entire safety argument** for all sixteen classes.

That is a change of posture from v1, where 36 hand-written invariants sat behind
two layers that could still refuse a bad rule. It is why Task 6 read the dry run
as text rather than as an exit code, and why its 12 accepted degraded sites and
the in-law shadowing are recorded there rather than discovered later.

The residual risk this leaves is stated plainly: **a wrong class invariant is
wrong dozens of times.** No bound below tests an invariant. A label moved by a
bad class would surface here as worse accuracy in that arm, which §4.4's guard
would catch only if it were large.

---

## 4. The pre-registered bounds

Every flip rate is `python -m scripts.encoder_training paired-flip-rate`:
changed pairs only, resampled over the **417 fragment clusters** rather than over
examples, 95% intervals.

### 4.1 Primary — the `combined` arm's paired flip rate. **Absolute.**

**The combined-trained arm's flip rate on the 4,873 changed pairs must be at or
below 1.00%.**

Stated as a level, not as a fall, and the level is chosen against the *observed*
1.89% synthetic baseline rather than against Task 2's 15.4% on real text. That
substitution is the whole of DD8 and the single most reusable thing the v1 run
produced.

The bound is attainable and it is falsifiable, which is the pair of properties
the v1 bound lacked: v1's expanded arm reached **0.84%** on its own pairs, and
the combined arm trains on strictly more variation than v1 did, so 1.00% is
reachable — but the combined arm's pair set is 25% larger and includes 1,983
class pairs whose behaviour nothing has measured, so it is not guaranteed.

**A rise above the clean-trained arm's rate on the same pairs is a result, and it
is a bad one.** It would mean the arm learned the new vocabulary distribution as
a shortcut rather than learning to ignore vocabulary.

### 4.2 The `classes` arm — at or near zero, and the headline number is the *clean* arm's

Two read-outs, and the second matters more than the first.

**(a) The classes-trained arm's flip rate must be at or below 0.50%.** DD7 allows
an absolute near-zero bound here and nowhere else: there is no defensible reason
for a model's answer to change when `sister` becomes `brother`, so unlike
`fever → temperature` a flip is unambiguously the model reading noise. 0.50% of
1,983 pairs is about 10 flips over 417 clusters, which is close to this
instrument's floor; a result in 0.50–1.00% is recorded as *not met* and read as
"reduced but not removed", not quietly reinterpreted.

**(b) The clean-trained arm's flip rate on those same 1,983 pairs is the finding
this ticket exists to produce, and no bound is placed on it.** It is a direct
measurement of surface overfitting with no register confound. Its value is
pre-registered as *unknown*, and both directions are written down now:

* **Above ~1%** — the fault §1 names reaches the trained head, referent swaps
  move it, and the classes are worth rolling out to the other six signals.
* **At or below ~0.5% with an upper interval below 1%** — the fault does not
  reach the head on referent vocabulary at this rate. That is the **stop
  condition** for open question 5, and it costs one night. The honest reading
  would be that 757 occurrences over 20% of library lines are not enough to
  matter to a 110M-parameter encoder, and the classes should not be extended.

### 4.3 The `affect` arm — no near-zero bound, deliberately

**The affect-trained arm's flip rate must not exceed the clean-trained arm's on
the same 729 pairs.** That is the whole bound, and it is a direction rather than
a level.

No absolute level is pre-registered because DD10 is right that affect is not the
same kind of thing: `worried → concerned` is a register swap of exactly v1's
kind, a reader can argue that the register genuinely differs, and so *some* flips
are defensible in a way that no referent flip is. Writing "at or near zero" here
would import the referent argument into a class that does not earn it.

**729 changed pairs cannot resolve much.** At v1's rate this arm's interval is
roughly twice as wide as v1's was; it is exploratory, it is reported separately
from the referent classes exactly as DD10 requires, and it will not be used to
support or oppose adopting the referent classes.

### 4.4 Guard — decisive-cell accuracy on the clean test tree, every arm

**No expanded-trained arm's pooled decisive-cell accuracy on the clean test tree
may fall more than 0.02 below the clean-trained arm's.** Four guards, one per
arm, scored inside each `paired-flip-rate` invocation with `--guard-bound 0.02`,
which exits non-zero on failure. The flip rate and the guard only mean anything
together: a head that answers `null` to everything has a flip rate of zero, and
two thirds of the test tree is `null`, so overall accuracy cannot see that and
decisive accuracy is the number that refuses to be gamed.

**One honest limit, carried forward from the v1 report's §2.** This guard held in
v1, and nothing in v1 tested whether it *would* catch the failure it is built
for, because no arm in that run is known to have refused to commit. It is
unchanged here and it is still untested in that sense.

### 4.5 Negative control — expected movement on the clean synthetic test set: **nothing**

The clean synthetic test set is drawn from the same libraries under the same
vocabulary as the training split, so it cannot contain the failure this ticket
targets. Clean-trained and each expanded-trained arm should be indistinguishable
on it.

**The reading rule for a gain is pre-registered now**, because v1 saw +1.2 points
here and had to decide what it meant after the fact:

* a gain of **the same size on both test trees** is augmentation benefit — more
  surface variety generalising slightly better;
* a gain **only on that arm's expanded tree** is a manufactured shortcut, and is
  a reason not to adopt the arm however good its flip rate looks;
* either way a gain above 0.02 is a warning to be investigated, not a win to be
  reported.

### 4.6 Effective sample size — pre-registered as unchanged

Every expanded tree holds exactly as many examples as the clean one, paired
`example_id` for `example_id`, over the same 417 clusters. Expansion creates no
fragments and no clusters. **No number in the result report may be quoted as
growth**, and a gain can only mean robustness to paraphrase, never better
coverage.

### 4.7 The realistic set — a validity check, and it will not rank the arms

Every arm is scored against the 67 real submissions. At ±12 points overall and
±25 per signal that set cannot rank five arms and **is not used to**. This is
pre-registered explicitly because v1's §5 shows how strong the temptation is:
that report first read an 11-point real-text decisive drop as a harm the guard
had missed, and the corrected reading — set beside §12.6, where a known-harmless
arm fell 12.3 points on the same slice — is that the slice cannot establish a
difference of that size in either direction. It is here to catch an arm that fell
over on real text, and nothing else.

### 4.8 Expansion telemetry — pre-registered from the CPU run

The night's sidecars must match these, which were measured on the test splits on
2026-09-05. A mismatch means the expansion did not run as configured.

| arm | sites found | applied | memoised repeats | skipped: memo | skipped: rate coin | skipped: class collision |
|---|---|---|---|---|---|---|
| `v1` | 12,969 | 5,214 | 0 | 0 | 7,755 | 0 |
| `classes` | 5,589 | 2,288 | 62 | 36 | 3,265 | 0 |
| `combined` | 18,558 | 7,417 | 62 | 33 | 11,108 | 0 |
| `affect` | 1,845 | 756 | 41 | 25 | 1,064 | 0 |

DD12 asked for the memo-firing rate because it is the size of the bug the memo
prevents. **It is 98 of 5,589 sites in the `classes` arm, 1.8%** — 62 second
occurrences forced to follow the first substitution, 36 forced to follow the
first *non*-substitution. Small, and not zero: without the memo those 98 sites
are where *"my sister … my wife"* would have been written. The v1 arm's zeroes
are the gating working, and are a second check on §0's reproduction claim.

`class_collision` is **0** across all four arms on the test splits. Injectivity
is doing nothing measurable here, which is worth recording as a fact about these
libraries rather than as evidence the guard is unnecessary — 55 library lines
carry two referents, so the collision it prevents is reachable.

---

## 5. The canary, and its condition

### 5.1 The value

**`0.9329`** — the clean-trained arm's pooled decisive-cell accuracy on the clean
test tree, 95% CI **[0.9119, 0.9527]**, from
`reports/encoder_training/lexical/clean-trained-clean-test/fever_present.arm_b_finetune.json`
(run `20260904-204346-lexical-expansion-2x2`).

The batch's cell 1 is the identical configuration on the identical tree, so it
must reproduce this value. **It is a trained-model measurement, not a generation
digest**, and that is the condition F10 asks to be stated:

* bit-exact reproduction needs `--determinism strict` (the default) **and** an
  unchanged GPU, driver and torch build;
* the environment the value was produced on, from the run log:

  | | |
  |---|---|
  | torch | `2.13.0+cu130` |
  | torch CUDA | `13.0` |
  | device | `NVIDIA GeForce RTX 5070` |
  | compute capability | `[12, 0]` (sm_120) |
  | `CUBLAS_WORKSPACE_CONFIG` | `:4096:8` |
  | determinism | `strict` |

`smoke-cuda` prints `torch_version` and `device_name` as its first two fields, so
step 1 of the batch records the comparison automatically.

**A mismatch stops the night for investigation, and an environment change is the
first thing to rule out** — a driver update, a torch wheel change, or a different
card explains a miss without anything in this ticket being wrong. Only once the
environment is shown unchanged does a miss implicate Tasks 2–5. The data side of
the canary is already cleared by §0: the tree, the ruleset and the libraries all
reproduce today.

### 5.2 The free determinism cross-check

The five clean-trained invocations train the identical model on the identical
data with the identical seed. Their per-fold validation-selected margins and
validation macro-F1 (`models[0].margins[*]`) **must be identical across all
five**. That is five independent trainings of one configuration, and it is a
stronger statement about this machine's determinism than a single canary value —
it costs nothing, because the CLI forces those five trainings anyway.

**A disagreement between them stops the night**, and it means `--determinism
strict` is not holding, which invalidates every paired comparison in the batch.

---

## 6. Every arm's read-out, written before the night

| arm | what a pass means | what a fail means |
|---|---|---|
| `combined` **(decision)** | flip rate ≤ 1.00% and the guard held: swap classes plus the v1 rules reduce surface overfitting without buying it with commitment. Adopt, and roll the classes to the other six signals. | above 1.00%: the pass did not reach the bound. Report as not met and do not roll out on the strength of an exploratory arm that did. |
| `classes` | ≤ 0.50%: referent, weekday and clinician vocabulary no longer moves the answer. | 0.50–1.00%: reduced, not removed. Above the clean arm's rate: the arm learned the new vocabulary as a shortcut — do not adopt. |
| `classes`, **clean-trained side** | *this is the measurement, not a bound.* Above ~1% the fault reaches the head and the ticket is worth its cost; at or below ~0.5% with an upper interval below 1% it does not, and that is the **stop** for question 5. | — |
| `v1` | reproduces 2026-09-04 within interval (1.89% → 0.84%): the anchor holds and the batch is comparable to it. | a different number on identical inputs means the environment or the gating changed, and §0/§5 say which to check first. |
| `affect` | does not exceed the clean-trained arm: a register swap at this scale costs nothing. | exceeds it: affect words carry label work the class invariant did not capture, exactly as DD10's two library lines warn. Drop the class. |
| every arm | clean-test decisive accuracy within 0.02 of clean-trained; nothing separated on the clean tree; ESS identical. | a gain above 0.02 on the expanded tree only is a manufactured shortcut, and outranks a good flip rate. |

---

## 7. The open questions this document settles

**The rate is not swept, and stays at `--rate 0.4 --clean-share 0.25`.**
(Question 6.) The class site density is genuinely different from fever's — 0.583
substitutions per 100 words against 1.375 at the same rate — so matching v1's
realised density would need a class rate near 0.95, which is the setting the
rule-authoring report measured *inverting* the vocabulary bias. The night has GPU
room for a sweep, and it is still the wrong thing to spend it on: a rate
dimension across five arms is the multiple-comparisons hazard §13 names, and a
rate is only worth tuning once something is known to move. **If the `classes` arm
moves, the sweep is the obvious next night.** Holding the rate also keeps the v1
arm's comparability to 2026-09-04, which is the batch's only external anchor.

**`setting` stays in, folded into `classes` and `combined`.** (Task 6's item 2.)
It is 3 members, 6 pairs, 215 test-split substitutions and +1.1% on the 4-gram
ceiling. It costs nothing to carry and cannot be attributed separately, and §1
records that limitation rather than pretending the `classes` arm is a pure
referent measurement.

**The `mother-in law` library typo is not fixed here.** (Task 6's item 3.) It is a
`data/synthetic/` edit, this ticket does not touch the libraries, and fixing it
now would change the tree and void §0's reproduction and §5's canary in the same
stroke. It is one degraded site of 637 rewritten lines and it belongs to a ticket
that is allowed to edit libraries.

**Multi-signal training stays out.** The classes are signal-agnostic and
`--dry-run-lint` runs over all seven signals, but the batch stays on
`fever_present`, which is where the anchor is.

---

## 8. What this cannot establish

* **That the class invariants are right.** Sixteen of them, each wrong dozens of
  times if wrong at all, and no bound above reads one. §3 is the honest statement
  of that risk.
* **That the 12 accepted degraded sites cost nothing.** Task 6 judged them
  fluency costs rather than label changes. That judgement is not tested here; it
  would show up, if wrong, as worse accuracy in the `classes` arm.
* **That real consultations improve.** Nothing here touches real text except a
  validity check that cannot rank.
* **That the operating point is right for classes.** §7 explains why it is held
  rather than tuned, which is a decision and not a measurement.
* **Whether a referent-only arm would read differently** from the 79.5%-referent
  bundle in §1.

## Results

*To be written against these bounds, item by item and including the items that
fail, in `2026-09-05-swap-class-expansion.md` (Task 10).*

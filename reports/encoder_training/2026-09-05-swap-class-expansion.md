# Swap class expansion — the five-arm batch — 2026-09-05

Task 10 of `documentation/encoder_plans/lexical_variant_expansion_v2_implementation.md`,
read against `2026-09-05-swap-class-preregistration.md` item by item,
**including the items that fail and the one that lands between its own two
readings.**

Run `20260905-202749-swap-class-batch`, commit `18e03a99`, all 24 steps green,
19:27:49 → 21:54:40 UTC (2 h 27 m). Thirteen `finetune` invocations, 65
fold-trainings, `roberta-base`, five folds, `--rate 0.4 --clean-share 0.25`
(p = 0.30), ruleset `325b3306…`. The authoritative numbers are the four
`swapclass/paired_flip_rate_*.json` and the thirteen
`swapclass/*/fever_present.arm_b_finetune.json`; where this document and one of
those disagree, the JSON is right.
`2026-09-05-swap-class-plain-english.md` is the same result in plain language.

---

## The one-paragraph answer

**Every pre-registered bound was met, the batch reproduces the v1 run digit for
digit, and the measurement the ticket was built to make came back
indeterminate.** The combined arm — the decision arm, named before the night —
flips on 0.76% of its changed pairs against a 1.00% bound, and the guard held in
all four arms. But §4.2(b), the clean-trained head's flip rate on the 1,983
referent/calendar/setting pairs, is **0.71% with a 95% interval of [0.21%,
1.68%]**, which is neither the "above ~1%" that would have said the fault reaches
the head nor the "≤0.5% with an upper interval below 1%" that was pre-registered
as the **stop** for open question 5. Fourteen flips is what the whole question
rests on. Two further things weaken the positive reading rather than support it:
the arm carrying *both* rule sets gains **least** on the clean test tree (+0.10
points, against +1.20 for v1 alone and +0.94 for the classes alone), which is the
signature of noise rather than of two additive effects; and no arm-versus-arm
comparison is computable from this batch at all, because each arm's flip rate is
measured over its own pair set. The night bought a clean reproduction, four met
bounds and no answer to the question it was run to settle.

**The classes are adopted anyway** — `referent` and `setting` on by default,
`calendar` opt-in, `affect` not at all — on the ground the pre-registration never
modelled: applying a signal-agnostic class to the next condition costs nothing,
so the decision rule that actually applies is "does it harm?" rather than "does
it help?", and this run answers that one. §10 is the argument, and it is recorded
as an **override** of a pre-registered stop rather than as a reading of the
result.

---

## 0. Verification before any result

Three things had to be true before a single number below means anything. All
three are.

### 0.1 The canary (§5.1). **Reproduced exactly.**

| | pre-registered | measured |
|---|---|---|
| clean-trained, clean test, pooled decisive | `0.9329` | **`0.9329250925662205`** |
| 95% CI | [0.9119, 0.9527] | [0.91187, 0.95266] |

The environment matches the condition F10 asked to be stated, field for field:
torch `2.13.0+cu130`, torch CUDA `13.0`, `NVIDIA GeForce RTX 5070`, compute
capability `[12, 0]`, `CUBLAS_WORKSPACE_CONFIG=:4096:8`, `--determinism strict`.
Nothing had to be ruled out.

### 0.2 The determinism cross-check (§5.2). **Held.**

The five clean-trained invocations differ only in `--test-dir`, so they train the
identical model five times. All five report identical per-fold selected margins
`(0.55, 0.55, 0.0, 0.45, 0.1)` and identical validation macro-F1 to six decimal
places on every fold. That is five independent trainings of one configuration
agreeing exactly, which is a stronger statement about this machine than the
canary alone, and it cost nothing.

### 0.3 The v1 anchor. **Byte-identical to 2026-09-04.**

| | 2026-09-04 | this run |
|---|---|---|
| expansion line | `1.375 / 0.3016 / 27274 (0.3896)` | identical |
| clean-trained flip rate | 1.89%, 74 / 3910 | 1.89%, 74 / 3910 |
| expanded-trained flip rate | 0.84%, 33 / 3910 | 0.84%, 33 / 3910 |
| guard drop | −0.0120 | −0.0120 |
| expanded-trained, expanded test | 0.9430 | 0.9430 |

DD6a and DD12 both changed behaviour that a hand-written rule file also passes
through, and both were specified as gated to class-generated rules so that the v1
arm stays the anchor. That gating is now demonstrated, not asserted. Every
comparison below is therefore on the same footing as the v1 report.

The dry-run lint (step 2) applied all **356 rules** — 36 hand-written plus 320
class-generated — to all 3,506 library lines, rewrote 2,357 of them, and
introduced no lexicon hit and removed none. It is the whole of the mechanical
safety argument after DD6a, and it passed.

---

## 1. Primary — the `combined` arm's paired flip rate. **Bound met.**

Pre-registered (§4.1): **at or below 1.00%**, absolute, anchored on the observed
1.89% synthetic baseline.

| arm | flip rate | 95% CI | flips / changed pairs |
|---|---|---|---|
| clean-trained | 1.72% | [0.89%, 3.12%] | 84 / 4873 |
| **combined-trained** | **0.76%** | [0.37%, 1.47%] | 37 / 4873 |

Met, and met the right way round: §4.1 named a *rise* above the clean-trained arm
as a bad result — the arm learning the new vocabulary distribution as a shortcut
— and the rate fell by more than half instead.

Two honest qualifications:

* The bound was picked knowing v1 reached 0.84% on its own pairs. 0.76% on a pair
  set 25% larger is a slightly better number in a slightly harder setting, but it
  is not a surprising one, and the two intervals overlap almost completely. The
  bound was attainable, which is the property the v1 bound lacked; it was not
  demanding.
* **The bound does not test what adoption depends on.** See §10.

### Direction

| transition | clean-trained | combined-trained |
|---|---|---|
| `null → true` | 47 | 8 |
| `null → false` | 14 | 9 |
| `true → null` | 13 | 9 |
| `false → true` | 4 | 5 |
| `true → false` | 4 | 1 |
| `false → null` | 2 | 5 |

The clean head's flips are dominated by `null → true` — displaced or third-party
fever language read as decisive once a word changes — exactly as the v1 report
found (46 of 74 there, 47 of 84 here). The combined-trained head's residual flips
have no such concentration.

### By label mode

| slice | pairs | clean-trained | combined-trained |
|---|---|---|---|
| `true` | 697 | 3.59% | 1.29% |
| `null_ambiguous` | 1479 | 2.97% | 0.74% |
| `false` | 1279 | 1.17% | 1.25% |
| `null_structural` | 1418 | 0.00% | 0.07% |

The movement is entirely in `true` and `null_ambiguous`, which are the slices the
whole encoder programme is about. The `false` slice does not improve and is
marginally worse; on 1,279 pairs and 98 clusters that difference is one flip.

---

## 2. The `classes` arm

### 2.1 The bound (§4.2a). **Met.**

Pre-registered: **at or below 0.50%**.

| arm | flip rate | 95% CI | flips / changed pairs |
|---|---|---|---|
| clean-trained | 0.71% | [0.21%, 1.68%] | 14 / 1983 |
| **classes-trained** | **0.35%** | [0.08%, 0.85%] | 7 / 1983 |

Met on the number. **It should not be reported as a reduction.** Fourteen flips
against seven, over 363 clusters, with intervals that overlap across most of
their length. The pre-registration itself said 0.50% of 1,983 pairs is about ten
flips and "close to this instrument's floor"; the measured difference is three
flips above that floor. Anyone quoting "halved" from this table is quoting noise.

The slice breakdown makes the point sharper, because the movement is not in one
direction:

| slice | pairs | clean-trained | classes-trained |
|---|---|---|---|
| `null_ambiguous` | 580 | 1.38% (8) | 0.34% (2) |
| `false` | 510 | 0.78% (4) | 0.20% (1) |
| `true` | 285 | 0.70% (2) | **1.40% (4)** |
| `null_structural` | 608 | 0.00% | 0.00% |

The `true` slice got *worse* — two flips to four. On 80 clusters that is not a
finding either, but it is the reason the arm's headline should not be described
as a uniform improvement.

### 2.2 The measurement (§4.2b). **Indeterminate — and this is the result.**

This is what the ticket exists to produce: the **clean-trained** head's flip rate
on pairs that differ only by a referent, weekday or clinician noun. No bound was
placed on it. Two readings were written down in advance:

* **above ~1%** → the fault reaches the trained head; roll the classes out to the
  other six signals;
* **at or below ~0.5%, with an upper interval below 1%** → it does not; **stop**,
  and open question 5 is closed.

**Measured: 0.71%, 95% CI [0.21%, 1.68%], 14 flips of 1,983 pairs over 363
clusters.**

The point estimate sits between the two thresholds and the interval spans both.
Neither pre-registered reading is available. The correct report is that **the
night did not answer the question**, and the pre-registration is at fault for
leaving a gap between its two branches rather than the run for landing in it.

What can be said, weakly, without leaving the data:

* The fault is not *absent*. Fourteen paired flips on vocabulary that carries no
  clinical meaning is a real, if small, sensitivity, and 8 of the 14 are on the
  `null_ambiguous` slice — the same slice the signal-word rules move most.
* The fault is *smaller* on class vocabulary than on signal vocabulary. The same
  head flips at 1.89% on the v1 pairs and 0.71% on the class pairs. Different
  pair sets, so this is a comparison of two rates rather than a test, but the
  direction is consistent with referent nouns mattering less to the head than
  `fever`/`temperature` does — which is what one would expect, and is the least
  interesting of the possible outcomes.
* **On accuracy the fault is invisible.** The clean head scores 0.9329 on the
  clean test tree and 0.9336 on the class-expanded tree. Swapping `sister` for
  `brother` across a fifth of the test set moves pooled decisive accuracy by
  +0.07 points, i.e. not at all.

That last line is the one to carry forward. The flip rate finds something the
accuracy cannot see, and both are true at once: a handful of individual answers
change, and the model is no worse.

---

## 3. The `affect` arm (§4.3). **Bound met, and the number is not usable.**

Pre-registered: the affect-trained arm must not exceed the clean-trained arm on
the same 729 pairs. A direction, not a level — DD10 was right that `worried →
concerned` is a register swap of v1's kind and cannot borrow the referent
argument.

| arm | flip rate | flips / changed pairs |
|---|---|---|
| clean-trained | 0.55% | 4 / 729 |
| affect-trained | 0.00% | 0 / 729 |

Met. Then reported honestly, it says almost nothing: the comparison is four flips
against zero on 274 clusters.

**The `[0.000, 0.000]` interval printed for the affect-trained arm is a bootstrap
artefact and must not be quoted as a 95% CI.** Zero events resample to zero every
time. The defensible ceiling is the rule of three: with no flips over 274
resampling units, the upper bound is roughly **1.1%**, which is above the
clean-trained arm's point estimate. This arm is consistent with no change at all.

DD10 asked for affect to be reported separately from the referent classes so it
could not be used to support them. It is, and it does not.

---

## 4. Guard — decisive-cell accuracy on the clean test tree (§4.4). **Held, four times.**

Bound: no expanded-trained arm may fall more than 0.02 below the clean-trained
arm. Both sides read off the clean test tree, so the two arms are compared on
identical text.

| arm | decisive accuracy, clean test | drop | passed |
|---|---|---|---|
| clean-trained (baseline) | 0.9329 | — | — |
| v1-trained | 0.9449 | −0.0120 | yes |
| classes-trained | 0.9423 | −0.0094 | yes |
| combined-trained | 0.9339 | −0.0010 | yes |
| affect-trained | 0.9345 | −0.0016 | yes |

Every arm is *better* than the baseline, so nothing was bought by refusing to
commit. The guard's purpose — catching a head that lowers its flip rate by
answering `null` more — is not triggered.

**The mechanism is visible even though the guard passed, and it should be
recorded.** Every expanded arm reduces the `null → true` rate on the clean test
tree, some of them sharply:

| arm | `null → true` count | rate (null support 6040) |
|---|---|---|
| clean-trained | 146 | 0.0242 |
| v1-trained | 105 | 0.0174 |
| combined-trained | 86 | 0.0142 |
| classes-trained | 84 | 0.0139 |
| affect-trained | 76 | 0.0126 |

That is the direction which mechanically lowers a flip rate, and DD7's guard
measures accuracy rather than commitment rate. Here the two coexist — the arms
became both more conservative *and* more accurate on decisive cells, which is a
real improvement and not the gamed one. But an arm that moved further along the
same axis could lower its flip rate without the guard noticing until decisive
accuracy finally broke, and this batch does not establish where that point is.

**The honest limit carried forward from v1 §2 is unchanged:** the guard held
again, and again nothing in this run tests whether it *would* catch the failure
it is built for, because no arm refused to commit.

---

## 5. Negative control (§4.5) — and the reason to disbelieve the gains

Pre-registered: expected movement on the clean synthetic test set is **nothing**,
with three reading rules fixed in advance — a gain of the same size on both trees
is augmentation benefit; a gain only on that arm's expanded tree is a
manufactured shortcut; either way a gain above 0.02 is a warning.

| arm | on the clean tree | on its own expanded tree | gain vs clean-trained |
|---|---|---|---|
| clean-trained | 0.9329 | — | — |
| v1-trained | 0.9449 | 0.9430 | +0.0120 |
| classes-trained | 0.9423 | 0.9422 | +0.0094 |
| combined-trained | 0.9339 | 0.9342 | +0.0010 |
| affect-trained | 0.9345 | 0.9345 | +0.0016 |

No arm gains only on its own expanded tree, so the manufactured-shortcut reading
is ruled out. No gain exceeds 0.02, so no warning is triggered. By the letter of
§4.5 the remaining reading is "augmentation benefit".

**That reading should not be taken, and the pre-registration's third option is
missing.** The arm trained on *both* rule sets gains **least**. If v1's +1.20 and
the classes' +0.94 were real and even partly additive, the combined arm should be
the strongest; it is +0.10, effectively zero, and the affect arm — the smallest
intervention in the batch, 0.2 substitutions per 100 words — matches it at +0.16.
The gains do not order by intervention size, they do not add, and every one of
them sits inside a ±2-point interval. The parsimonious reading is that all four
are fold-level noise plus the discrete margin selection described in §9, and that
the pre-registered expectation of **nothing** was correct in the first place.

This is also a correction to how the v1 report read its own +1.2 points. That
report treated the gain as at least potentially real. With four arms instead of
one it is visible that the +1.2 is the largest of four gains that should have
ordered themselves and did not.

---

## 6. Effective sample size (§4.6). **Held, mechanically.**

Every expanded tree holds exactly 10,000 test examples, paired `example_id` for
`example_id` with the clean tree, over the same 417 fragment clusters. Expansion
creates no fragments and no clusters. The smaller pair sets resample over fewer
clusters only because fewer clusters contain a substitutable site — 363 for the
classes arm, 274 for affect — which narrows nothing.

**No number in this report is growth.** A gain could only ever mean robustness to
paraphrase, never better coverage, and per §5 there is no gain to explain.

---

## 7. The realistic set (§4.7). **A validity check. It ranks nothing, as pre-registered.**

All five arms were scored against the 67 real submissions. Worst-case 95%
half-widths: **±12.0 points** overall, **±23.1 points** on the 18 decisive cells.

| arm | overall | decisive | between-fold SD (overall) |
|---|---|---|---|
| clean-trained | 73.7% | 76.7% | 9.1 |
| v1-trained | 81.2% | 65.6% | 4.4 |
| classes-trained | 69.9% | 76.7% | 11.0 |
| combined-trained | 80.3% | 73.3% | 11.8 |
| affect-trained | 75.8% | 71.1% | 11.9 |

The full spread between arms is 11.3 points overall — smaller than the
half-width, and comparable to the spread *within* single arms across folds (the
classes arm runs from 55.2% on fold 1 to 85.1% on fold 0). Nothing here separates
anything, which is what §4.7 said before the night and what v1 §5's correction
established the hard way. **No arm is recommended, dropped or ranked on the
strength of this table**, including the v1 arm's 65.6% decisive, which reproduces
the same 11-point drop that the v1 report first misread as harm.

The set does what it is for: no arm fell over on real text.

---

## 8. Expansion telemetry and the memo rate (§4.8, DD12). **Matches, and re-derived.**

The night's sidecars live in `data/synthetic/generated/`, which is git-ignored, so
they are not recoverable from a branch. The four expansions were therefore re-run
on CPU from this commit and their test-split sidecars aggregated; the regenerated
clean tree reproduces the run log's fold counts exactly, and all four expansion
summary lines reproduce character for character.

| arm | sites found | applied | memoised repeats | skipped: memo | skipped: rate coin | skipped: class collision |
|---|---|---|---|---|---|---|
| `v1` | 12,969 | 5,214 | 0 | 0 | 7,755 | 0 |
| `classes` | 5,589 | 2,288 | 62 | 36 | 3,265 | 0 |
| `combined` | 18,558 | 7,417 | 62 | 33 | 11,108 | 0 |
| `affect` | 1,845 | 756 | 41 | 25 | 1,064 | 0 |

Every cell matches the pre-registered table. The changed-pair denominators match
too: 3,910 / 1,983 / 4,873 / 729.

**The memo fires on 98 of 5,589 sites in the `classes` arm — 1.8%.** DD12 asked
for this because it is the size of the bug the memo prevents: 62 second
occurrences forced to follow the first substitution, 36 forced to follow the
first non-substitution. Those 98 sites are where *"my sister … my wife"* would
otherwise have been written into a single example. Small, and not zero. The v1
arm's zeroes are the DD12 gating working and are a second confirmation of §0.3.

**`class_collision` is 0 in all four arms.** Injectivity did nothing measurable
here. That is a fact about these libraries — 55 library lines carry two referents,
so the collision it prevents is reachable — and not evidence that the guard is
unnecessary.

---

## 9. What was learned about the measurement itself

**The margin selection is a confound nobody had named.** Each arm selects a
decision margin per fold on validation macro-F1, and the five arms chose wildly
different ones:

| arm | selected margins, folds 0–4 |
|---|---|
| clean-trained | 0.55, 0.55, 0.00, 0.45, 0.10 |
| v1-trained | 0.25, 0.40, 0.00, 0.80, 0.00 |
| classes-trained | 0.00, 0.90, 0.00, 0.25, 0.00 |
| combined-trained | 0.00, 0.65, 0.30, 0.00, 0.00 |
| affect-trained | 0.85, 0.90, 0.00, 0.90, 0.00 |

Flip rates and decisive accuracy are both computed after gating, so part of every
between-arm difference in this report is a discrete margin choice made on a
sibling split, not a difference in what the encoder learned. Nothing here
separates the two, and the batch was not designed to. It is the most plausible
mechanical explanation for §5's non-ordering gains, and it belongs in the design
of the next comparison.

**A flip rate over its own pair set cannot compare two arms.** Each arm's rate is
computed over the pairs that arm's rules changed — 3,910, 1,983, 4,873, 729 — so
"v1 reached 0.84% and combined reached 0.76%" is two measurements on two
different populations, not a comparison. Nothing in this batch tests whether
adding the classes to the v1 rules improved anything, and no such test was
pre-registered. That is a design gap, not a result, and §10 is where it bites.

**Fourteen flips.** The classes arm's entire contribution to the ticket's central
question is 14 events, and the affect arm's is four. The instrument's resolution
at these pair-set sizes is roughly one flip in 200 clusters. Any future run that
wants a *difference* rather than a level needs either far more changed pairs or a
paired test across arms inside one invocation.

---
## 10. Was the pass adopted? **Yes — on cost asymmetry, not on evidence of benefit.**

**This is an override of the pre-registration's decision rule, and it is recorded
as one.** §4.2(b) named "≤0.5% with an upper interval below 1%" as the **stop**
for open question 5, and the measured 0.71% [0.21%, 1.68%] is not a pass by that
rule — it is not anything by that rule. The classes are being adopted anyway, on
a ground the pre-registration never modelled.

### The ground

The pre-registration asked *"does this help?"* and treated a "no" as "abandon".
That is the right structure when a technique costs something to apply. These
classes do not. They are signal-agnostic by construction: sixteen lists written
once, expanded by the loader into 320 ordered pairs that mention no signal, and
applying them to a new condition's libraries is passing `--class-groups` on a
generation run. There is no per-condition authoring, no per-symptom tuning and no
per-library review implied by the mechanism itself.

The system is heading for roughly fifty conditions, ~200 symptoms and five or six
fragment libraries each. Hand-written fragments are the expensive resource in that
plan and always will be; anything that widens the surface those fragments cover
without more of them being written is worth keeping unless it is shown to hurt.

So the decision rule that actually applies is **"does it harm?"**, and this run
answers that as well as one run can:

* the swaps do not perturb the model at all on accuracy — the clean-trained head
  scores 0.9329 on the clean tree and 0.9336 after a fifth of the test set has
  had its referents swapped;
* all four guards passed, every arm at or above the baseline on the clean test
  tree;
* no arm gained only on its own expanded tree, so nothing was manufactured;
* the dry-run lint finds no rule that creates medical language the libraries do
  not already contain;
* 14 paired flips out of 1,983, all of them cases where the model was reading
  vocabulary it should not have been.

**Adopted, therefore, on a cost/harm argument. Nothing in this report is evidence
that the classes improve anything**, and §5 explains why the apparent clean-tree
gains should not be read as benefit. That distinction has to survive into
whatever cites this report: a later run that finds something odd must not be read
against a benefit nobody measured.

### What is adopted, and what is not

| group | decision |
|---|---|
| `referent` | **default on** for future generation |
| `setting` | **default on** |
| `calendar` | **opt-in per condition** — see below |
| `affect` | **not adopted.** §3 is consistent with nothing having happened, and DD10 already bars it from supporting the referent case. |

`calendar` is held back for a reason specific to the rollout rather than to this
run. A weekday swap is safe when nothing labels on time, which is true of fever.
For a symptom whose label depends on onset or duration, a weekday changed in one
fragment can contradict a duration phrase in another — and that contradiction is
*cross-fragment*, so the memo cannot see it (it forces consistency only for
repeats of the same token) and neither can any of the three load-time layers. It
is 68 occurrences over 2.6% of library lines and it buys +4.5% on the 4-gram
ceiling. Not worth carrying by default into conditions where onset is the answer.

### The real risk is the rollout, not the fever data

The `referent.adult_female` invariant, in the committed file, says:

> *"the line stays a third-party attribution under every swap, because only which
> woman it is changes and **the libraries never label on that**."*

That final clause is a claim about **this corpus**. It is true of UTI. It is the
thing that stops being automatically true at fifty conditions, and the class lists
make the exposure concrete: `referent.adult_female` holds *mum, mother, wife,
missus, sister, aunt, auntie, girlfriend* in one interchangeable list, so
`my wife → my sister` is a legal swap. Nothing labels on that for fever. For
sexual health, contact tracing, obstetrics or safeguarding, the *relationship* is
clinically material and that swap moves real information.

**The mechanism that handles this already exists, is stricter for classes than
for hand-written rules, and now has a test.** Layer 3 requires a class-generated
rule to leave the matched terms unchanged for **every** signal in
`SIGNAL_LEXICONS` — there is no "own lexicon" to swap inside. So a condition
where `sister` or `partner` is load-bearing declares it in that condition's
lexicon, and every pair touching the word stops loading. The per-condition
clinical judgement becomes "write the lexicon properly", which is already part of
adding a condition.

Until this ticket that guard had never fired: none of the 71 members appears in
any of the seven UTI lexicons, so layer 3 passed **vacuously** on every committed
class rule, and the rollout would have been resting on a check nobody had watched
work. `tests/test_synthetic_expand.py::test_a_class_member_entering_a_signal_lexicon_refuses_the_whole_group`
now adds a signal whose lexicon names `sister` and asserts the refusal, and
`test_the_committed_members_are_absent_from_every_signal_lexicon` records why the
check is vacuous today rather than leaving it assumed.

**It fails closed and coarsely**, which is worth knowing before it happens: the
refusal is raised during `load_classes`, so one collision refuses the whole
`referent` group everywhere rather than dropping the offending pairs. Loud and
safe, and it means the first condition that collides is a small piece of work
(split the list, or narrow the lexicon), not a silent degradation.

### Conditions on the adoption

1. **Run `--dry-run-lint` per new condition** and read its accepted-degraded-sites
   output once. It is already in CI. "Signal-agnostic" means the rules name no
   signal — not that they have been checked against every one.
2. **`referent.adult_female` and `referent.adult_male` are known debt.** They mix
   relationship-bearing members (`wife`, `girlfriend`, `husband`) with
   kinship-only ones (`mum`, `sister`, `dad`, `brother`). The first condition
   where relationship is clinically material needs them split. Named here so it
   is not rediscovered by accident.
3. **The sixteen invariants are still the whole safety argument** for anything
   layer 3 does not catch, and they were written against fever libraries.
4. **Nothing here licenses `affect`.**

### What is no longer urgent

The rate sweep proposed as the way to close question 5 drops in priority. Its
value was deciding whether to keep the classes; that decision is now made on other
grounds. Whether the classes *help* is a question the real-text holdout will
answer better than another synthetic night, once that set is large enough to rank
anything — which §7 shows it is not.

## 11. What this does not establish

* **That the class invariants are right.** Sixteen of them, each wrong dozens of
  times if wrong at all. No bound in this report reads one, and after DD6a the
  mechanical layers do not protect them per-rule. §0's lint pass and the
  committed-file tests are the whole argument, exactly as §3 of the
  pre-registration said before the night.
* **That the 12 accepted degraded sites cost nothing.** Task 6 judged them
  fluency costs rather than label changes. If that judgement were wrong it would
  surface as worse accuracy in the classes arm, which is 0.94 points *better* —
  weak evidence in favour, and not a test.
* **That real consultations improve.** §7 is a validity check that cannot rank.
* **That the operating point is right for classes.** Held, not tuned, and §10.1
  is the proposal to change that.
* **Whether a referent-only arm would read differently** from the 79.5%-referent
  bundle.
* **Whether the guard would catch the failure it exists for.** Still untested,
  two runs running.

---

*Companion: `2026-09-05-swap-class-plain-english.md`. Bounds:
`2026-09-05-swap-class-preregistration.md`. Library statistics quoted anywhere in
this ticket are the output of `python -m scripts.synthetic_data.class_stats`
(DD15) — 49 files, 2,506 non-blank non-comment lines, 71 members in 16 lists, 320
ordered pairs, 757 occurrences, of which referent 569 over 507 lines (20.2%);
reachable 4-gram ceiling +36.8% overall and +27.1% for the referent group alone.*

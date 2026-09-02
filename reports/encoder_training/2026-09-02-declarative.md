# Declarative fragments: the 2×2, and what it says about the libraries

*Write-up of the four-cell declarative sweep run on 2026-09-02 (task 7 of
`documentation/encoder_plans/procedural_fragment_generation_implementation.md`,
driven by `documentation/encoder_plans/procedural_fragment_task7_runsheet.md`).
Every number here comes from the six
`*_present.declarative_comparison.json` files under
`reports/encoder_training/decl/comparison/`. **Those files are the authority** —
where this document disagrees with one of them, the report is right and this is
stale.*

*The run's own record is `reports/training_runs/20260902-125946-decl-compare-2x2/`
— the log and a manifest carrying the argv, the exit code and the sha. Cited
rather than transcribed, per the runsheet.*

**The holdout labels were proposed by Claude and reviewed by the maintainer.**
They were not produced independently of the models being scored. The labeller and
the model share an architecture and could share a blind spot, which would inflate
every real-text figure below in a way no resampling would reveal.
`data/realistic/README.md` requires this said in every report that uses the set.

**Run:** `roberta-base`, single-head per signal, every layer unfrozen, five folds
over fragment clusters, `GENERATOR_VERSION` 4, `--train-seed 1234`,
`--determinism strict`, `--no-weights`, holdout on. One `declarative-compare`
invocation trained all four cells and wrote one report per signal — 4h00m19s
wall clock at sha `a35b1ea`, exit 0, torch 2.13.0+cu130. Six signals × four
cells × five folds = 120 fine-tunes.

| cell | `--companion-share` | `--declarative-share` | what it is |
|---|---|---|---|
| **A** `c0.0-d0.0` | 0.0 | 0.0 | the control |
| **B** `c0.0-d0.3` | 0.0 | 0.3 | declarative alone (the plan's Arm D) |
| **C** `c0.5-d0.0` | 0.5 | 0.0 | companions alone |
| **D** `c0.5-d0.3` | 0.5 | 0.3 | both |

Cell R at declarative 0.6 has not been run.

---

## Answer

**Declarative fragments made the invented-symptom rate worse, in every signal,
in both comparisons. The ticket's own primary metric moved the wrong way.**

On the 67 real submissions, `null -> true` — answering `true` about a signal the
patient never mentioned — rose in 6/6 signals from A to B, and rose or held in
6/6 from C to D. The rise is large: `flank_pain` +25.2 points (B over A) and
+20.8 (D over C); `haematuria` +33.9 and +3.9; `fever` +22.0 and +0.4.
Prediction 3 said this number would improve, and would move *least* for
`flank_pain`. It moved most, and upward.

**D does beat C on real-text decisive accuracy, sometimes hugely, but the gain
is a precision/recall trade rather than better reading.** C is close to
degenerate on three signals — `null` recall near 90–100% with decisive accuracy
of 40–53%, a model that mostly declines to answer. D answers more often: decisive
accuracy rises, `null` recall falls, invention rises. Overall real-text accuracy
moves D over C by **+10.4 / +10.2 / +3.6 / +2.7 / +0.3 / −7.8** points across the
six signals. That is not the shape of a capability gain.

**A large share of what separates the cells on real text is margin selection, not
data.** The per-fold decision margins swing across nearly the whole 0.0–0.9 range
*within a single cell* — `fever` cell A is `0.55, 0.55, 0.0, 0.45, 0.1`, cell D
is `0.0, 0.0, 0.75, 0.55, 0.65`. The margin gates `true`, so it is the direct
lever on `null -> true`, and it varies more between folds of one cell than the
cells vary from each other.

**The synthetic accuracy gain is partly free examples.** `declarative_v1` scores
**100.0%** with a perfectly diagonal confusion matrix in every cell that draws
from it, contributing ~1,200 examples and ~155 of the 573 effective clusters.
Removing that slice cuts D's edge over C from 1.6–3.9 points to 0.8–2.8, and
turns `dysuria` negative.

**And the finding nobody predicted: on `null_ambiguous` — the one slice where a
transformer can earn its keep — a fully fine-tuned 110M-parameter RoBERTa is
indistinguishable from TF-IDF logistic regression.** Point estimates within ±2.2
points on all six signals, McNemar p ≥ 0.36 on three, and where p is small it
splits two to one. By the report's own decision rule that is the
**library-bottleneck** reading of the ticket's question, and it holds regardless
of what the declarative flag does.

**Recommendation: do not ship `--declarative-share 0.3` on this evidence.** Run
cell R for completeness, then take the margin selector and the `null_ambiguous`
result as the two things this run actually found.

---

## 1. The headline: prediction 3, and it failed

`null -> true` on the 67 submissions, mean across folds of each fold's own rate.
Lower is better. Every figure is one number over 41–58 truly-`null` submissions.

| signal | null support | **A** | **B** | **C** | **D** | B−A | D−C |
|---|---|---|---|---|---|---|---|
| `dysuria_present` | 11 | 52.7% | 54.5% | 3.6% | 12.7% | **+1.8** | **+9.1** |
| `fever_present` | 49 | 23.7% | 45.7% | 0.0% | 0.4% | **+22.0** | **+0.4** |
| `flank_pain_present` | 53 | 45.7% | 70.9% | 9.1% | 29.8% | **+25.2** | **+20.8** |
| `haematuria_present` | 56 | 29.3% | 63.2% | 9.3% | 13.2% | **+33.9** | **+3.9** |
| `nocturia_present` | 58 | 0.7% | 14.1% | 0.3% | 0.3% | **+13.4** | **0.0** |
| `urinary_frequency_present` | 41 | 5.9% | 23.4% | 4.4% | 5.9% | **+17.5** | **+1.5** |

Six of six worse on B−A. Five of six worse and one level on D−C. There is no
signal on which declarative fragments reduced invention.

Running the 2×2 rather than the plan's 2×1 was the right call, and not for the
reason the runsheet gave. The runsheet's worry was that B beating A would be
companions arriving by a second route. The actual outcome is the mirror image:
**B is much worse than A**, and a 2×1 measured at companion 0 would have shown
that clearly enough — but only the D column shows that adding declarative
fragments *on top of a working fix* partly undoes it.

`flank_pain` is the worst case in both comparisons, against a prediction that
named it as the signal that would move least. The stated reasoning was inventory
size: `flank_pain` has the fewest authored phrases, so it should see the least
change. The opposite happened, which suggests the mechanism is not "more clinical
language about this signal" at all.

## 2. Why the synthetic set could not see any of this

The same metric on the recombination test slice, where it is 1–4.4% everywhere:

| signal | A | B | C | D |
|---|---|---|---|---|
| `dysuria` | 2.76% | 3.00% | 2.07% | 2.42% |
| `fever` | 2.42% | 1.14% | 1.62% | **0.94%** |
| `flank_pain` | 2.58% | 0.96% | 1.21% | 2.68% |
| `haematuria` | 2.22% | 2.19% | 3.11% | 2.85% |
| `nocturia` | 4.42% | 4.34% | 4.27% | 3.38% |
| `urinary_frequency` | 1.89% | 2.04% | 1.92% | 2.02% |

**The synthetic rate is lower in D than in C on four of six signals. The real
rate is higher in D than in C on five of six.** The two instruments disagree
about direction, and the synthetic one is the one that spans 3 points where the
real one spans 30.

This is the same fact section 10 already records from 2026-08-19, arriving a
second time from the other side: *the synthetic test set cannot contain the
failure companions were built to fix*, so it cannot see that failure returning
either. A reader who reads only the pooled tables in these six reports will
conclude that declarative fragments are a modest, safe improvement. They are not.

## 3. What actually moved on real text

Mean ± sd across folds, 67 submissions, one observation each.

| signal | | **A** | **B** | **C** | **D** |
|---|---|---|---|---|---|
| `dysuria` | all | 71.0% | 85.1% | 79.1% | **89.3%** |
| | decisive (n 56) | 78.6% | 93.9% | 78.6% | 92.9% |
| `fever` | all | 73.7% | 62.7% | 86.0% | **96.4%** |
| | decisive (n 18) | 76.7% | 92.2% | **48.9%** | 90.0% |
| `flank_pain` | all | 54.9% | 38.8% | **79.4%** | 71.6% |
| | decisive (n 14) | 84.3% | 92.9% | **40.0%** | 81.4% |
| `haematuria` | all | 68.1% | 46.6% | 84.2% | **86.9%** |
| | decisive (n 11) | 76.4% | 100.0% | **50.9%** | 87.3% |
| `nocturia` | all | 91.0% | 83.3% | 93.4% | **93.7%** |
| | decisive (n 9) | 44.4% | 71.1% | 53.3% | 55.6% |
| `urinary_frequency` | all | 76.7% | 79.7% | 76.1% | **79.7%** |
| | decisive (n 26) | 52.3% | 86.9% | 45.4% | 56.9% |

Two things to read off it.

**C is barely answering on three signals.** `fever` 48.9%, `flank_pain` 40.0%,
`haematuria` 50.9% decisive accuracy against `null` recall of 99.6%, 89.8% and
90.7%. On decisive slices of n 18, 14 and 11 that is a model that says "not
mentioned" almost always. Section 10's 2026-08-19 entry says decisive-cell
accuracy is what rules out a collapse to `null`; here, at the per-signal level
and at generator version 4, it does not rule it out.

**D's decisive gain over C is bought with `null` recall.** Every signal where D's
decisive accuracy jumps is a signal where D's `null -> true` also rises. The
paired McNemars back the accuracy movement — `fever` D ahead on 5/5 folds with
p ≤ 0.031 on four; `dysuria` D ahead on 4/5 with p = 0.0005 and 0.0034 on two —
but McNemar on total correctness cannot separate "reads decisive text better"
from "answers more often on a set that is 60–85% `null`". The decisive slices are
too small to settle it: worst-case half-widths are ±13 to ±33 points.

`flank_pain` is the one signal where D loses on overall accuracy (−7.8), and it
is also the largest invention rise. That is the coherent story: D answers more,
`flank_pain` has the least language to answer from, so the extra answers are
wrong.

## 4. The margin selector, which is probably the real story

Per-fold decision margins, one row per cell, in fold order:

| signal | A | B | C | D |
|---|---|---|---|---|
| `dysuria` | 0.0, 0.9, 0.8, 0.8, 0.0 | 0.55, 0.9, 0.9, 0.85, 0.05 | 0.05, 0.7, 0.9, 0.0, 0.15 | 0.1, 0.85, 0.9, 0.9, 0.4 |
| `fever` | 0.55, 0.55, 0.0, 0.45, 0.1 | 0.0, 0.85, 0.85, 0.9, 0.35 | 0.35, 0.0, 0.85, 0.9, 0.0 | 0.0, 0.0, 0.75, 0.55, 0.65 |
| `flank_pain` | 0.8, 0.85, 0.0, 0.0, 0.0 | 0.9, 0.1, 0.75, 0.0, 0.85 | 0.65, 0.25, 0.0, 0.8, 0.0 | 0.9, 0.6, 0.9, 0.9, 0.0 |
| `haematuria` | 0.9, 0.9, 0.4, 0.8, 0.0 | 0.9, 0.8, 0.6, 0.65, 0.15 | 0.9, 0.9, 0.0, 0.9, 0.55 | 0.9, 0.9, 0.5, 0.0, 0.35 |
| `nocturia` | 0.0, 0.0, 0.25, 0.2, 0.5 | 0.55, 0.85, 0.0, 0.0, 0.15 | 0.65, 0.3, 0.6, 0.05, 0.05 | 0.35, 0.35, 0.1, 0.0, 0.8 |
| `urinary_frequency` | 0.15, 0.05, 0.0, 0.9, 0.7 | 0.8, 0.9, 0.0, 0.9, 0.75 | 0.9, 0.9, 0.0, 0.9, 0.7 | 0.85, 0.2, 0.0, 0.9, 0.5 |

Twenty-four cells, and in twenty of them the five folds span more than half the
available range. Several jump from 0.0 to 0.9 between adjacent folds of the same
cell.

The margin is the threshold above which `true` may be answered — it is
*mechanically* the lever on `null -> true`, and the per-fold rates track it:
`fever` cell A selects `0.55, 0.55, 0.0, 0.45, 0.1` and inverts 26, 11, 10, 6, 5
of 49 submissions in those folds. The two lowest margins are not the two highest
rates, but the ordering is close enough that the margin is clearly doing a large
share of the work.

Each cell selects its margin on **its own** synthetic validation split, and those
splits differ between cells by construction — B and D contain 436 declarative
fragments A and C do not. So the selector is reading a distribution that the
treatment changed, on a criterion (`macro_f1` on validation) that has no
particular relationship to real-text invention, and it lands somewhere different
each time.

**This contaminates every cross-cell real-text comparison in the run**, and it is
not specific to declarative fragments — it is a property of the pipeline that
every future arm will inherit. Section 10's 2026-08-19 note that "no future
margin should be selected on a validation split in which this failure cannot
occur" is exactly this problem, recorded and not yet acted on. This run is the
evidence that it now matters more than the treatment being tested.

## 5. The synthetic gain is partly free examples

Pooled decisive accuracy over the recombination test slice:

| signal | A | B | C | D |
|---|---|---|---|---|
| `dysuria` | 95.4% | 96.0% | 93.5% | 94.1% |
| `fever` | 93.3% | 95.6% | 90.8% | 94.7% |
| `flank_pain` | 94.9% | 97.5% | 92.1% | 94.3% |
| `haematuria` | 91.3% | 93.9% | 89.4% | 92.2% |
| `nocturia` | 83.7% | 88.5% | 82.2% | 86.1% |
| `urinary_frequency` | 83.5% | 89.6% | 83.7% | 87.2% |

B and D lead everywhere. But their test sets are not A's and C's: adding
`--declarative-share 0.3` puts declarative fragments into the test split too, and
`eff n` rises from 418 to 573 on `fever`, 182 to 342 on `dysuria`, and similarly
elsewhere. Those added examples are free. In every cell that has them,
`declarative_v1` scores **100.0% [100.0%, 100.0%]** with an exactly diagonal
confusion matrix — 753/753 and 455/455 on `fever` cell D.

That is DD3 stated as a measurement: *nothing generated is a hard case*. The
frames cannot produce a hedge, a metaphor or a third-party attribution, so
everything they emit is a canonical claim the model gets right.

Removing the `declarative_v1` slice and recomputing accuracy over the remainder
(weighted by example count, from the by-library confusions in the JSON — the
report does not print this column):

| signal | A | B raw → excl | C | D raw → excl | D−C excl |
|---|---|---|---|---|---|
| `dysuria` | 95.4% | 96.0 → 95.2 | 93.5% | 94.1 → **92.9** | **−0.6** |
| `fever` | 93.3% | 95.6 → 94.7 | 90.8% | 94.7 → 93.6 | +2.8 |
| `flank_pain` | 94.9% | 97.5 → 97.0 | 92.1% | 94.3 → 93.2 | +1.1 |
| `haematuria` | 91.3% | 93.9 → 92.7 | 89.4% | 92.2 → 90.6 | +1.2 |
| `nocturia` | 83.7% | 88.5 → 86.0 | 82.2% | 86.1 → 83.3 | +1.1 |
| `urinary_frequency` | 83.5% | 89.6 → 87.3 | 83.7% | 87.2 → 84.5 | +0.8 |

The remaining edge is 0.8–2.8 points, and `dysuria` flips negative. It is still
not a clean read — the two cells' training texts differ as well as their test
texts, and no cell pairs with any other on the synthetic set, which is why every
cross-cell McNemar row in these reports is a recorded skip.

Prediction 4 holds directionally: where D gains on C it is `false` recall that
moves. `fever` 88.0 → 94.4, `flank_pain` 88.3 → 94.2, `dysuria` 91.6 → 94.8,
`nocturia` 74.7 → 80.9. On a test set whose composition changed, so it is a weak
hold.

## 6. The ticket's own question, which this run answers by accident

`null_ambiguous` is the slice the reports call "the only slice where a
transformer can earn its keep" — clear positives, clear negatives and
`null_structural` are handled by bag-of-words. On the reference cell A, which is
the one cell that pairs with the baselines:

| signal | `tfidf_logreg` | **A** (fine-tune) | McNemar p |
|---|---|---|---|
| `dysuria` | 94.1% [90.7, 97.0] | 94.0% [89.7, 97.5] | 0.389 |
| `fever` | 93.0% [90.6, 95.1] | 93.8% [91.0, 96.4] | 0.370 |
| `flank_pain` | 91.7% [88.0, 95.0] | 93.7% [89.7, 97.1] | 0.0126 |
| `haematuria` | 93.9% [90.6, 96.5] | 91.9% [87.3, 95.9] | 0.000289 |
| `nocturia` | 90.2% [86.9, 93.1] | 89.6% [86.0, 93.0] | 0.356 |
| `urinary_frequency` | 92.8% [90.0, 95.2] | 95.0% [92.2, 97.2] | 0.000946 |

Every point estimate is within 2.2 points of TF-IDF. Three of six are a coin
flip. Of the three that separate, TF-IDF wins one. **110M unfrozen parameters buy
nothing over a bag of words on the hard `null` sub-classes.**

The report's own decision rule, in "Reading the three together", says what that
means: *"Fine-tune no better than the frozen probe, with errors concentrated on a
handful of named fragments: those ideas are not learnable from the data we have,
and the next month is library work on the fragments the table names."* The error
concentration matches — cell A puts half its errors on 14 of 463 decisive
fragments on `fever`, against 27 for an even spread, with the worst ten carrying
39.1%.

Two caveats before this is quoted as settled. The comparison here is
fine-tune-against-TF-IDF, not fine-tune-against-frozen-probe; Arm A was skipped
in this run to halve the wall clock, so the rule's exact left-hand side is
missing. And this table must not be read alone: `majority_class` scores 100.0%
across this slice by answering `null` unconditionally. The fine-tune's `true` and
`false` recalls are 70–98% at the same time, so it is a real number — but the
caveat is what makes it one.

## 7. Cell C did not replicate the companion numbers, and could not have

The runsheet expected cell C to reproduce the committed companion result as a
free replication. It does not come close:

| signal | Arm0 (v3) | **A** (v4) | ArmP (v3) | **C** (v4) |
|---|---|---|---|---|
| `dysuria` | 72.7% | 52.7% | 23.6% | 3.6% |
| `fever` | 84.1% | 23.7% | 4.5% | 0.0% |
| `flank_pain` | 87.5% | 45.7% | 17.7% | 9.1% |
| `haematuria` | 80.4% | 29.3% | 12.5% | 9.3% |
| `nocturia` | 69.0% | 0.7% | 19.7% | 0.3% |
| `urinary_frequency` | 25.4% | 5.9% | 6.8% | 4.4% |

Every version-4 cell is far less invention-prone than its version-3 counterpart,
control included. That is not a regression and it is not a version-4 win: **the
two are different models.** The companion arms were trained on merged `joint6`
trees — one six-head model, `models/encoder/joint6`, scoring all six signals in
one report. These cells are **single-signal heads**; each declarative report
names the other five signals under "not scored, because no head exists for them".

Section 10 already records that joint training multiplies the real-text
`null -> true` rate by 3× to 24× (2026-08-17). A single-head model not doing that
is the expected result, and it accounts for the whole gap without any reference
to the generator version. **The runsheet's replication check was never able to
work**, because it compared across a model-topology change as well as a version
bump. Anyone writing this up should not report either direction of that table as
a finding.

## 8. The reporting bug

Every `null -> true` sentence in the "Paired on real text" section read
backwards. `report.py` computes `delta_points` as `left − right`, positive
meaning the right-hand run invents *less*, then appended a fixed
"in favour of `{right}`" regardless of sign. All six D-against-C lines are
negative, so all six credited D with a win it did not have:

> `null -> true` mean: 9.1% against 29.8% — **-20.8 points** in favour of
> `arm_b_finetune@c0.5-d0.3`.

Only the positive direction was covered by a test, which is why it survived. The
sentence now names the direction in words, and both directions plus the level
case are asserted on the rendered markdown. The six committed reports were
re-rendered from their own JSON — `render_markdown` reads the dict and nothing
else, so this cost no GPU time and moved exactly the six sentences per file and
nothing else.

The 2026-08-19 companion reports carry the old wording but every delta in them is
positive, so none of them was ever wrong. They are left as they are.

## 9. The predictions, scored

1. **Byte-identical output at `P = 0`** — *not verified in this run.* The fold
   trees were generated in a separate console run that was not saved to a branch,
   so the generation argv are not in a manifest, and `data/synthetic/generated/`
   is gitignored. The runsheet's two pre-flight checks may have been run; there is
   no record either way. The unit tests
   (`test_default_invocation_still_produces_the_golden_dataset`,
   `test_declarative_share_zero_is_inert_against_a_pool_that_could_serve_it`)
   still pass, which is the mechanism but not the real manifest's output.
   **Treat this as unscored, and save the generation run next time.**
2. **Structural nulls fall further at a given companion share** — *not scorable
   for the same reason.* The check needs the `.stats.json` sidecars, which were
   not committed. The one downstream proxy available, `null_structural` slice
   size, is not printed per cell in a form that separates the two shares.
3. **The invented-symptom rate improves** — **failed, comprehensively.** Section 1.
   Worse in 6/6 on B−A, worse-or-level in 6/6 on D−C, and worst on
   `flank_pain_present`, which was named as the signal that would move least.
4. **`false` recall improves most** — **held, weakly.** Section 5. It is where D's
   gain over C sits, on a test set whose composition changed.
5. **Near-duplicate pairs in the hand-written libraries do not move** — *not run.*
   `python -m scripts.synthetic_data --lint` was not part of this run.
6. **`P = 0.6` scores worse than `P = 0.3` on real text** — *not run, and now
   largely pre-answered.* Invention rose monotonically with declarative share at
   every companion share tested. Cell R is a confirmation rather than an open
   question, and DD8's argument survives on the 0.3 evidence alone. Still worth
   the three hours for the record, since DD8 rests on it.

Three of six predictions could not be scored, and two of those three failed for
the same avoidable reason: the generation step was not saved to a branch.

## 10. What this run does not answer

Unchanged from the runsheet, and still true:

* **Supervision per example.** At `--emit-signals primary` a fragment asserting
  three signals emits one key and discards the other two. This measures claim
  density, not supervision (12.2).
* **Hard cases.** DD3 — measured here as `declarative_v1` scoring 100.0% in every
  cell. The frames cannot produce a hedge, a metaphor or a third-party
  attribution.
* **Whether the real-text differences are real at all.** Decisive slices of n 9
  to n 56 carry worst-case half-widths of ±13 to ±33 points, and the labels were
  proposed by the same architecture being scored.

## 11. What to do next

1. **Do not ship `--declarative-share 0.3`.** The metric it was built to move
   moved the wrong way in every signal.
2. **Fix the margin selector before any further arm is measured.** It currently
   varies more between folds of one cell than the treatments vary from each
   other, and every cell selects on a validation split the treatment changed.
   Until that is addressed, no cross-arm real-text comparison in this pipeline is
   trustworthy — including the ones already committed.
3. **Run cell R** for the record, understanding it is now confirmatory.
4. **Take the `null_ambiguous` result seriously.** A fine-tune level with TF-IDF
   on the only slice that discriminates is the ticket's question answering itself
   in favour of library work. Re-run with Arm A included to complete the rule's
   left-hand side before acting on it.
5. **Save the generation run to a branch**, not just the training run. Two
   predictions were unscorable because the sidecars were never committed.

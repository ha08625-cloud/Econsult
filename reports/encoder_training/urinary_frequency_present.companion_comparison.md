# Encoder training: evaluation report

*Generated 2026-08-19T20:32:55+00:00.*

|  |  |
|---|---|
| signal | `urinary_frequency_present` |
| folds | `5` |
| generator version | `3` |
| generator base seed | `42` |
| generator seed rule | `base + 100 * fold + {train: 0, val: 1, test: 2}` |
| split salt | `0` |
| dataset dir | `data/synthetic/generated/arm0` |
| ruleset | `data/uti1.json` |
| ruleset hash | `325b33068307bc70ca085b27117a90c2ad9e71fac24a80f77c8107d08049bb9f` |
| examples per fold | `train 44680, val 9145, test 9015` |
| shuffle seed | `7` |
| dataset | `joint6` |
| joint signals | `dysuria_present, fever_present, flank_pain_present, haematuria_present, nocturia_present, urinary_frequency_present` |
| arm | `arm_b_finetune` |
| arms | `Arm0_control, ArmC_remargined, ArmP_companions` |
| arm0 dir | `data/synthetic/generated/arm0` |
| armp dir | `data/synthetic/generated/armp` |
| companion share | `0.0 against 0.5` |
| base model | `roberta-base` |
| pooling | `mean` |
| max seq len | `256` |
| device | `cuda` |
| epochs | `3` |
| batch size | `32` |
| lr | `2e-05` |
| warmup ratio | `0.1` |
| determinism | `strict` |
| train seed | `1234` |
| trainable | `all layers unfrozen, shared by every head` |
| holdout | `data/realistic/uti1_holdout.labels.tsv -- 67 real submissions, scored after test, selects nothing` |
| artefacts | `models/encoder/joint6` |
| model revision | `e2da8e2f811d1448a5b465c236feacd80ffbac7b` |
| revision pinned | `False` |
| tokeniser lowercases | `False` |
| tokeniser vocab size | `50265` |
| tokeniser discards casing | `False` |
| cluster tag coverage | `0 of 7 libraries carry cluster markers; 302 of 302 fragments are in libraries with none` |
| bootstrap | `2000 resamples over clusters, alpha=0.05, seed=0` |

**validation guided decisions**

* pooling mode (DD3) -- mean vs CLS, compared once
* learning rate
* epoch count (the epoch restored is the best-scoring one on the fold's own validation split)
* decision margin (DD9)

## How to read these numbers

Every table below prints **two** counts: `n`, the number of examples in the slice, and
`eff n`, the number of distinct fragment **clusters** behind them. The examples are
recombinations of a few hundred hand-written sentence fragments, and fragments tagged as
the same idea are grouped into one cluster. `eff n` is the number of independent ideas
the slice tested; `n` is how many times they were reshuffled.

**`eff n` is the sample size.** Every confidence interval here is a bootstrap that
resamples clusters, not examples. Resampling examples would measure the noise of the
recombination process rather than the noise that matters, and would report intervals
roughly `sqrt(n / eff n)` too narrow -- a factor of ten or more on these slices.

A slice with a large `n` and a small `eff n` is not a large sample. Ten thousand examples
built from sixty-six fragments is sixty-six ideas seen many times, and no amount of
further generation changes that. Where `eff n` is small, the interval is wide, and the
honest reading is that the slice cannot separate two models.

Two confusion matrices are printed for each model: **raw argmax**, and the same scores
under the fold's selected decision rule. They are separate because "the model is wrong"
and "the rule is conservative" are different findings. The rule maximises macro-F1
subject to a `null -> true` rate no worse than argmax's -- `null -> true` being the cell
that invents a symptom into a patient's pre-filled form, which is a constraint rather
than something to trade against F1.

## Cluster-tag coverage, and what it does to the intervals below

> **Warning: all 7 libraries behind this run carry no cluster markers at all, so every line in them counts as an independent idea.** Where that is not true -- where several lines are one idea written several ways -- the `eff n` of every slice drawn from those libraries is an **upper bound**, and the confidence intervals below are correspondingly **narrower than the truth**.
>
> Untagged: `urinary_frequency_false`, `urinary_frequency_null_adjacent`, `urinary_frequency_null_hedged`, `urinary_frequency_null_historical`, `urinary_frequency_null_metaphor`, `urinary_frequency_null_thirdparty`, `urinary_frequency_true`.

Tagging cannot inflate a number -- `[c01]` siblings are forced into one cluster and one
split, so it only ever *reduces* `eff n`, correctly, by stopping the same idea being
counted twice. The asymmetry is what makes cross-signal comparison unsafe: a fully
tagged signal is penalised for being honest and an untagged one is flattered by default,
so a ranking across signals is partly an artefact of this column.

| library | fragments | tagged | coverage |
|---|---|---|---|
| `urinary_frequency_false` | 46 | 0 | 0.0% |
| `urinary_frequency_null_adjacent` | 40 | 0 | 0.0% |
| `urinary_frequency_null_hedged` | 42 | 0 | 0.0% |
| `urinary_frequency_null_historical` | 40 | 0 | 0.0% |
| `urinary_frequency_null_metaphor` | 44 | 0 | 0.0% |
| `urinary_frequency_null_thirdparty` | 44 | 0 | 0.0% |
| `urinary_frequency_true` | 46 | 0 | 0.0% |

## Headline: fold-aggregated

Pooled over every fold, so each fragment cluster is a test cluster exactly once and the
aggregate test set is the whole library. Intervals are the cluster bootstrap; the across-fold
spread beside them is a stability check with four degrees of freedom, not a CI.

**Read the `decisive` column, not `overall`.** Structural nulls -- filler recombined with no
decisive fragment at all -- carry the single idea "no signal language anywhere", so they share
one resampling unit. That is the correct treatment and it makes the overall interval nearly
unreadable: one unit holding a third of the examples lands in a resample zero to three times,
swinging overall accuracy by twenty points on nothing. `decisive` drops them and is the slice
with a real sample behind it.

| model | kind | decisive n | eff n | decisive accuracy [95% CI] | decisive macro-F1 [95% CI] | overall acc | per-fold overall mean +/- sd |
|---|---|---|---|---|---|---|---|
| `arm_b_finetune@Arm0_control` | finetune | 7015 | **302** | 84.9% [79.6%, 89.8%] | 83.4% [77.0%, 88.8%] | 89.2% | 89.2% +/- 4.9% |
| `arm_b_finetune@ArmC_remargined` | finetune | 7015 | **302** | 85.0% [79.7%, 89.9%] | 83.5% [77.1%, 88.9%] | 89.3% | 89.3% +/- 4.9% |
| `arm_b_finetune@ArmP_companions` | finetune | 7015 | **302** | 85.0% [79.7%, 90.0%] | 83.1% [76.9%, 88.7%] | 89.2% | 89.2% +/- 4.7% |

### Null sub-class recall, pooled

The table the whole exercise exists for: how often each hard `null` sub-class is correctly
left as `null`. `eff n` here is the sub-class's entire library, which a single split cannot reach.

**Never read this table on its own.** Every example in these slices is truly `null`, so a model
that always answers `null` scores 100% across the row -- as `majority_class` below does. High
null recall is only a finding when the `true` and `false` recalls in the per-class tables are
high too.

| model | adjacent | attribution | hedged | historical | metaphor | third_party |
|---|---|---|---|---|---|---|
| `arm_b_finetune@Arm0_control` | 87.3% [76.8%, 96.4%] (eff n 40) | -- | 96.9% [93.0%, 99.8%] (eff n 42) | 94.0% [86.4%, 99.5%] (eff n 40) | 91.2% [82.3%, 98.8%] (eff n 44) | 99.5% [98.8%, 100.0%] (eff n 44) |
| `arm_b_finetune@ArmC_remargined` | 87.9% [77.8%, 96.7%] (eff n 40) | -- | 96.9% [93.0%, 99.8%] (eff n 42) | 94.0% [86.4%, 99.5%] (eff n 40) | 91.7% [83.3%, 98.8%] (eff n 44) | 99.5% [98.8%, 100.0%] (eff n 44) |
| `arm_b_finetune@ArmP_companions` | 90.5% [81.9%, 97.2%] (eff n 40) | -- | 94.2% [86.0%, 99.7%] (eff n 42) | 99.2% [98.5%, 99.8%] (eff n 40) | 92.2% [84.4%, 99.3%] (eff n 44) | 99.2% [98.5%, 99.8%] (eff n 44) |

## The real-text holdout

Scored against `data/realistic/uti1_holdout.labels.tsv` -- 67 free-text submissions
written to read like real patients, labelled once and used to select nothing. **Every
other number in this report is a recombination of the same fragment libraries the models
were trained on.** This section is the only measurement here that speaks to real patient
text, and it is a validity check rather than a comparison.

> This set cannot rank two models. Every figure below carries its own `n` and a worst-case half-width -- the widest a 95% interval on a proportion can be at that `n` -- and on the per-signal decisive slices that is +/-20 points or worse. It is a validity instrument: it can show that a number in the nineties on recombinations is really 55% on real text, which is the question that matters most and which nothing else here answers. It cannot separate two arms, and a report that uses it to is misreading it.

> **The labels were proposed by Claude and reviewed by the maintainer.** They were not produced independently of the models being scored. This is a real limitation and it belongs in every report that uses this set: the labeller and the model share an architecture and could in principle share a blind spot, which would inflate the score in a way no amount of resampling would reveal.

> 67 submissions written by one person share that person's voice and that person's idea of what a patient sounds like. Real submissions vary by age, first language, literacy, how ill the person feels while typing, and what they think a GP wants to hear. This is a large improvement on recombinations and it is still not a random sample of patients.

*Scored after the margin was selected on validation and after the synthetic test split was scored. This set selects nothing (README rule 2), and the call order is what makes that structural rather than a promise.*

*The folds are not pooled. Five folds are five models scored on the same 67 submissions, so pooling would count each submission five times; the figures below are the mean and spread across folds, and the spread is a stability check rather than a confidence interval.*

**Read the `decisive` columns.** A `null` cell is one a model scores by answering "no
information", which the majority-class baseline does perfectly; the decisive cells are
the ones where the patient said something the model has to read. Where a signal has no
`false` examples at all, its decisive figure is very nearly recall on `true` and nothing
here tests whether an explicit denial is read correctly.

Not scored, because no head exists for them: `recent_uti_present`.

### `null -> true` on real text -- the headline

How often each model answers `true` about a signal the submission never mentioned, as
the mean across folds of that fold's own rate. Every other number in this section is
read against this one: a model can post a respectable overall figure here purely by
answering `null` everywhere, and it can post a respectable *decisive* figure while still
inventing symptoms into most of the submissions that never raised them.

| signal | null support | `arm_b_finetune@Arm0_control` | `arm_b_finetune@ArmC_remargined` | `arm_b_finetune@ArmP_companions` |
|---|---|---|---|---|
| `dysuria_present` | 11 | 72.7% | 70.9% | 23.6% |
| `fever_present` | 49 | 84.1% | 77.6% | 4.5% |
| `flank_pain_present` | 53 | 87.5% | 85.3% | 17.7% |
| `haematuria_present` | 56 | 80.4% | 65.7% | 12.5% |
| `nocturia_present` | 58 | 69.0% | 53.4% | 19.7% |
| `urinary_frequency_present` | 41 | 25.4% | 20.5% | 6.8% |

### `arm_b_finetune@Arm0_control`

Recombination test slice: **n 7015**, **eff n 302** clusters, accuracy 84.9% [79.6%, 89.8%]. Holdout: **n 67** submissions, one observation each, scored by 5 fold models at margins {'dysuria_present': 0.15, 'fever_present': 0.9, 'flank_pain_present': 0.85, 'haematuria_present': 0.0, 'nocturia_present': 0.0, 'urinary_frequency_present': 0.25}, {'dysuria_present': 0.0, 'fever_present': 0.85, 'flank_pain_present': 0.0, 'haematuria_present': 0.9, 'nocturia_present': 0.15, 'urinary_frequency_present': 0.9}, {'dysuria_present': 0.75, 'fever_present': 0.0, 'flank_pain_present': 0.85, 'haematuria_present': 0.0, 'nocturia_present': 0.85, 'urinary_frequency_present': 0.05}, {'dysuria_present': 0.0, 'fever_present': 0.85, 'flank_pain_present': 0.0, 'haematuria_present': 0.0, 'nocturia_present': 0.85, 'urinary_frequency_present': 0.9}, {'dysuria_present': 0.2, 'fever_present': 0.4, 'flank_pain_present': 0.8, 'haematuria_present': 0.5, 'nocturia_present': 0.0, 'urinary_frequency_present': 0.9}. The two `n`s are printed together because they are not the same kind of number and the second is far the smaller.

| signal | true/false/null | omitted | decisive n | decisive acc (mean +/- sd) | worst-case half-width | all n | all acc (mean +/- sd) | null recall |
|---|---|---|---|---|---|---|---|---|
| `dysuria_present` | 56/0/11 | 0 | 56 | 82.9% +/- 3.2% | +/-13.1% | 67 | 72.5% +/- 2.3% | 20.0% +/- 4.1% |
| `fever_present` | 9/9/49 | 0 | 18 | 84.4% +/- 4.6% | +/-23.1% | 67 | 29.0% +/- 3.7% | 8.6% +/- 5.5% |
| `flank_pain_present` | 7/7/53 | 0 | 14 | 90.0% +/- 9.6% | +/-26.2% | 67 | 23.0% +/- 1.7% | 5.3% +/- 1.6% |
| `haematuria_present` | 9/2/56 | 0 | 11 | 100.0% +/- 0.0% | +/-29.5% | 67 | 21.5% +/- 3.1% | 6.1% +/- 3.7% |
| `nocturia_present` | 9/0/58 | 0 | 9 | 86.7% +/- 5.0% | +/-32.7% | 67 | 23.0% +/- 10.5% | 13.1% +/- 12.8% |
| `urinary_frequency_present` | 26/0/41 | 0 | 26 | 71.5% +/- 11.4% | +/-19.2% | 67 | 50.1% +/- 10.7% | 36.6% +/- 22.0% |

* `dysuria_present`: no `false` examples in this set, so its number is very nearly a recall-only measurement: nothing here tests whether an explicit denial is read correctly, which was the largest error family in the synthetic evaluation.
* `nocturia_present`: no `false` examples in this set, so its number is very nearly a recall-only measurement: nothing here tests whether an explicit denial is read correctly, which was the largest error family in the synthetic evaluation.
* `urinary_frequency_present`: no `false` examples in this set, so its number is very nearly a recall-only measurement: nothing here tests whether an explicit denial is read correctly, which was the largest error family in the synthetic evaluation.

`null -> true` on real text, per fold: `dysuria_present` 8, 8, 8, 9, 7 of 11; `fever_present` 42, 42, 43, 38, 41 of 49; `flank_pain_present` 47, 46, 46, 49, 44 of 53; `haematuria_present` 45, 40, 52, 47, 41 of 56; `nocturia_present` 46, 46, 41, 25, 42 of 58; `urinary_frequency_present` 10, 5, 28, 5, 4 of 41. This is the cell that invents a symptom into a patient's pre-filled form, counted here on submissions rather than on recombinations.

### `arm_b_finetune@ArmC_remargined`

Recombination test slice: **n 7015**, **eff n 302** clusters, accuracy 85.0% [79.7%, 89.9%]. Holdout: **n 67** submissions, one observation each, scored by 5 fold models at margins {'dysuria_present': 0.9, 'fever_present': 0.9, 'flank_pain_present': 0.9, 'haematuria_present': 0.9, 'nocturia_present': 0.9, 'urinary_frequency_present': 0.65}, {'dysuria_present': 0.9, 'fever_present': 0.9, 'flank_pain_present': 0.65, 'haematuria_present': 0.9, 'nocturia_present': 0.9, 'urinary_frequency_present': 0.9}, {'dysuria_present': 0.9, 'fever_present': 0.9, 'flank_pain_present': 0.9, 'haematuria_present': 0.9, 'nocturia_present': 0.85, 'urinary_frequency_present': 0.65}, {'dysuria_present': 0.9, 'fever_present': 0.9, 'flank_pain_present': 0.9, 'haematuria_present': 0.85, 'nocturia_present': 0.9, 'urinary_frequency_present': 0.85}, {'dysuria_present': 0.9, 'fever_present': 0.9, 'flank_pain_present': 0.9, 'haematuria_present': 0.9, 'nocturia_present': 0.9, 'urinary_frequency_present': 0.9}. The two `n`s are printed together because they are not the same kind of number and the second is far the smaller.

| signal | true/false/null | omitted | decisive n | decisive acc (mean +/- sd) | worst-case half-width | all n | all acc (mean +/- sd) | null recall |
|---|---|---|---|---|---|---|---|---|
| `dysuria_present` | 56/0/11 | 0 | 56 | 81.8% +/- 3.4% | +/-13.1% | 67 | 71.9% +/- 2.9% | 21.8% +/- 5.0% |
| `fever_present` | 9/9/49 | 0 | 18 | 83.3% +/- 5.6% | +/-23.1% | 67 | 30.1% +/- 4.0% | 10.6% +/- 6.7% |
| `flank_pain_present` | 7/7/53 | 0 | 14 | 92.9% +/- 7.1% | +/-26.2% | 67 | 23.9% +/- 1.5% | 5.7% +/- 2.3% |
| `haematuria_present` | 9/2/56 | 0 | 11 | 98.2% +/- 4.1% | +/-29.5% | 67 | 21.5% +/- 3.3% | 6.4% +/- 3.5% |
| `nocturia_present` | 9/0/58 | 0 | 9 | 80.0% +/- 14.5% | +/-32.7% | 67 | 27.5% +/- 11.7% | 19.3% +/- 15.1% |
| `urinary_frequency_present` | 26/0/41 | 0 | 26 | 67.7% +/- 11.4% | +/-19.2% | 67 | 49.9% +/- 9.9% | 38.5% +/- 15.3% |

* `dysuria_present`: no `false` examples in this set, so its number is very nearly a recall-only measurement: nothing here tests whether an explicit denial is read correctly, which was the largest error family in the synthetic evaluation.
* `nocturia_present`: no `false` examples in this set, so its number is very nearly a recall-only measurement: nothing here tests whether an explicit denial is read correctly, which was the largest error family in the synthetic evaluation.
* `urinary_frequency_present`: no `false` examples in this set, so its number is very nearly a recall-only measurement: nothing here tests whether an explicit denial is read correctly, which was the largest error family in the synthetic evaluation.

`null -> true` on real text, per fold: `dysuria_present` 8, 8, 8, 8, 7 of 11; `fever_present` 42, 40, 41, 36, 31 of 49; `flank_pain_present` 46, 46, 46, 47, 41 of 53; `haematuria_present` 14, 40, 47, 43, 40 of 56; `nocturia_present` 43, 39, 41, 21, 11 of 58; `urinary_frequency_present` 4, 5, 19, 10, 4 of 41. This is the cell that invents a symptom into a patient's pre-filled form, counted here on submissions rather than on recombinations.

### `arm_b_finetune@ArmP_companions`

Recombination test slice: **n 7015**, **eff n 302** clusters, accuracy 85.0% [79.7%, 90.0%]. Holdout: **n 67** submissions, one observation each, scored by 5 fold models at margins {'dysuria_present': 0.0, 'fever_present': 0.15, 'flank_pain_present': 0.0, 'haematuria_present': 0.85, 'nocturia_present': 0.0, 'urinary_frequency_present': 0.0}, {'dysuria_present': 0.0, 'fever_present': 0.0, 'flank_pain_present': 0.4, 'haematuria_present': 0.9, 'nocturia_present': 0.75, 'urinary_frequency_present': 0.9}, {'dysuria_present': 0.9, 'fever_present': 0.8, 'flank_pain_present': 0.8, 'haematuria_present': 0.0, 'nocturia_present': 0.0, 'urinary_frequency_present': 0.55}, {'dysuria_present': 0.0, 'fever_present': 0.85, 'flank_pain_present': 0.0, 'haematuria_present': 0.6, 'nocturia_present': 0.05, 'urinary_frequency_present': 0.25}, {'dysuria_present': 0.5, 'fever_present': 0.85, 'flank_pain_present': 0.85, 'haematuria_present': 0.2, 'nocturia_present': 0.75, 'urinary_frequency_present': 0.9}. The two `n`s are printed together because they are not the same kind of number and the second is far the smaller.

| signal | true/false/null | omitted | decisive n | decisive acc (mean +/- sd) | worst-case half-width | all n | all acc (mean +/- sd) | null recall |
|---|---|---|---|---|---|---|---|---|
| `dysuria_present` | 56/0/11 | 0 | 56 | 81.1% +/- 8.5% | +/-13.1% | 67 | 78.5% +/- 8.1% | 65.5% +/- 10.0% |
| `fever_present` | 9/9/49 | 0 | 18 | 83.3% +/- 11.1% | +/-23.1% | 67 | 90.4% +/- 3.9% | 93.1% +/- 2.7% |
| `flank_pain_present` | 7/7/53 | 0 | 14 | 81.4% +/- 6.4% | +/-26.2% | 67 | 80.3% +/- 1.9% | 80.0% +/- 1.7% |
| `haematuria_present` | 9/2/56 | 0 | 11 | 81.8% +/- 17.0% | +/-29.5% | 67 | 86.6% +/- 3.0% | 87.5% +/- 3.3% |
| `nocturia_present` | 9/0/58 | 0 | 9 | 75.6% +/- 9.3% | +/-32.7% | 67 | 77.9% +/- 2.7% | 78.3% +/- 4.0% |
| `urinary_frequency_present` | 26/0/41 | 0 | 26 | 41.5% +/- 11.7% | +/-19.2% | 67 | 72.2% +/- 5.3% | 91.7% +/- 2.2% |

* `dysuria_present`: no `false` examples in this set, so its number is very nearly a recall-only measurement: nothing here tests whether an explicit denial is read correctly, which was the largest error family in the synthetic evaluation.
* `nocturia_present`: no `false` examples in this set, so its number is very nearly a recall-only measurement: nothing here tests whether an explicit denial is read correctly, which was the largest error family in the synthetic evaluation.
* `urinary_frequency_present`: no `false` examples in this set, so its number is very nearly a recall-only measurement: nothing here tests whether an explicit denial is read correctly, which was the largest error family in the synthetic evaluation.

`null -> true` on real text, per fold: `dysuria_present` 4, 3, 2, 2, 2 of 11; `fever_present` 3, 2, 1, 2, 3 of 49; `flank_pain_present` 9, 9, 11, 10, 8 of 53; `haematuria_present` 7, 5, 10, 6, 7 of 56; `nocturia_present` 15, 11, 13, 9, 9 of 58; `urinary_frequency_present` 3, 3, 3, 2, 3 of 41. This is the cell that invents a symptom into a patient's pre-filled form, counted here on submissions rather than on recombinations.

## Paired on real text

The 67 submissions are the same 67 for every model here, so unlike the recombination
test slice they can be paired: the informative quantity is the submissions two models
disagree about, not the gap between two means. One test per fold, never pooled.

### `arm_b_finetune@Arm0_control` against `arm_b_finetune@ArmC_remargined`

| fold | pairs | only `arm_b_finetune@Arm0_control` | only `arm_b_finetune@ArmC_remargined` | p |
|---|---|---|---|---|
| 0 | 67 | 4 | 1 | 0.375 |
| 1 | 67 | 0 | 0 | 1 |
| 2 | 67 | 1 | 7 | 0.0703 |
| 3 | 67 | 4 | 0 | 0.125 |
| 4 | 67 | 0 | 0 | 1 |

`arm_b_finetune@Arm0_control` ahead on 2 folds, `arm_b_finetune@ArmC_remargined` on 1. `null -> true` mean: 25.4% against 20.5% -- **+4.9 points** in favour of `arm_b_finetune@ArmC_remargined`.

*One test per fold over the same 67 submissions, never concatenated: five folds are five models scored on one sample, and pooling would report a p-value for 335 observations that do not exist.*

### `arm_b_finetune@Arm0_control` against `arm_b_finetune@ArmP_companions`

| fold | pairs | only `arm_b_finetune@Arm0_control` | only `arm_b_finetune@ArmP_companions` | p |
|---|---|---|---|---|
| 0 | 67 | 6 | 34 | 8.36e-06 |
| 1 | 67 | 7 | 20 | 0.0192 |
| 2 | 67 | 16 | 30 | 0.0541 |
| 3 | 67 | 9 | 12 | 0.664 |
| 4 | 67 | 12 | 28 | 0.0166 |

`arm_b_finetune@Arm0_control` ahead on 0 folds, `arm_b_finetune@ArmP_companions` on 5. `null -> true` mean: 25.4% against 6.8% -- **+18.5 points** in favour of `arm_b_finetune@ArmP_companions`.

*One test per fold over the same 67 submissions, never concatenated: five folds are five models scored on one sample, and pooling would report a p-value for 335 observations that do not exist.*

### `arm_b_finetune@ArmC_remargined` against `arm_b_finetune@ArmP_companions`

| fold | pairs | only `arm_b_finetune@ArmC_remargined` | only `arm_b_finetune@ArmP_companions` | p |
|---|---|---|---|---|
| 0 | 67 | 3 | 34 | 1.23e-07 |
| 1 | 67 | 7 | 20 | 0.0192 |
| 2 | 67 | 16 | 24 | 0.268 |
| 3 | 67 | 9 | 16 | 0.23 |
| 4 | 67 | 12 | 28 | 0.0166 |

`arm_b_finetune@ArmC_remargined` ahead on 0 folds, `arm_b_finetune@ArmP_companions` on 5. `null -> true` mean: 20.5% against 6.8% -- **+13.7 points** in favour of `arm_b_finetune@ArmP_companions`.

*One test per fold over the same 67 submissions, never concatenated: five folds are five models scored on one sample, and pooling would report a p-value for 335 observations that do not exist.*

## The datasets behind these arms

Two arms, generated from the same libraries with the same seed, the same counts and the same fold triple, differing in `--companion-share` and in nothing else. Arm C is not a third dataset: it is Arm 0's trained model with its margins re-selected on Arm P's validation split.

| arm | tree | companion share | examples/fold (train) | filler-only kept | companions/example | worst spread by label mode |
|---|---|---|---|---|---|---|
| `Arm0_control` | `data/synthetic/generated/arm0` | 0.0 | 44680 | 3064 | 0.000 | 0.0000 |
| `ArmP_companions` | `data/synthetic/generated/armp` | 0.5 | 54410 | 1118 | 0.757 | 0.0238 |

**The last column is the leak detector, not a curiosity.** It is the largest gap between
any two label modes in mean companions per example, across every training split of that
arm. Companion count is drawn blind to the label mode by construction; if these rows ever
disagreed, companion count would have become a proxy for the label, pointing the wrong
way -- more clinical text implying more likely `null` -- and the arm would be void rather
than reinterpretable.

## The ticket's question: model or libraries?

This ticket exists to answer one question -- **is the bottleneck the model or the
fragment libraries?** -- and three numbers decide it. All three are on this page.

### 1. Accuracy on `null_ambiguous`

The only slice where a transformer can earn its keep. Clear positives, clear negatives
and `null_structural` are the easy three-quarters of the data; bag-of-words handles them,
so an overall accuracy is close to uninformative here.

**This table cannot be read on its own, and the first row is why.** Every example in this
slice is truly `null`, so a model that answers `null` unconditionally scores 100% across
it -- which is exactly what `majority_class` does, and it has learned nothing. A number
here is a finding only when the `true` and `false` recalls in the same model's per-class
table are high at the same time. The same caveat applies to every McNemar row below it.

| model | kind | n | eff n | accuracy [95% CI] |
|---|---|---|---|---|
| `arm_b_finetune@Arm0_control` | finetune | 3000 | **210** | 93.8% [90.9%, 96.8%] |
| `arm_b_finetune@ArmC_remargined` | finetune | 3000 | **210** | 94.1% [91.2%, 96.9%] |
| `arm_b_finetune@ArmP_companions` | finetune | 3000 | **210** | 95.0% [92.3%, 97.6%] |

### 2. The same comparison, paired

Two overlapping intervals do not settle whether one model beats another on the same
examples. McNemar does, over the examples the two disagree about -- read it alongside the
intervals above, never instead of them.

| pair | n | a only | b only | p |
|---|---|---|---|---|
| `arm_b_finetune@Arm0_control` vs `arm_b_finetune@ArmC_remargined` | 3000 | 0 | 0 | 1 |

Not on this table, because they cannot be paired at all -- different examples on the two sides, so there is nothing for McNemar to pair: `arm_b_finetune@Arm0_control` vs `arm_b_finetune@ArmP_companions`; `arm_b_finetune@ArmC_remargined` vs `arm_b_finetune@ArmP_companions`. Read those through the intervals above and the per-fold spread, and see "Pairs that could not be tested" below.

### 3. Where the errors fall

The per-fragment table below, as one number per model. Errors spread thinly across many
fragments say the method is too weak. Errors piled onto a handful say those specific ideas
are not learnable from the data we have -- and the table names them, which is what makes
this the most decision-useful thing in the report.

* `arm_b_finetune@Arm0_control`: 1060 errors across 55 of 302 decisive fragments. Half of them fall on **10** fragments (an even spread would be 27.5); the worst ten carry 51.1% of all errors.
* `arm_b_finetune@ArmC_remargined`: 1054 errors across 54 of 302 decisive fragments. Half of them fall on **10** fragments (an even spread would be 27.0); the worst ten carry 51.4% of all errors.
* `arm_b_finetune@ArmP_companions`: 1049 errors across 62 of 302 decisive fragments. Half of them fall on **9** fragments (an even spread would be 31.0); the worst ten carry 56.3% of all errors.

### Reading the three together

* Fine-tune clear of the frozen probe **and** clear of TF-IDF on the slice above: the
  frozen pooled representation was the bottleneck, and the next month is model work.
* Fine-tune no better than the frozen probe, with errors concentrated on a handful of
  named fragments: those ideas are not learnable from the data we have, and the next
  month is library work on the fragments the table names.
* Both arms poor with errors spread evenly across most fragments: neither reading is
  supported yet, and the honest answer is that the slice cannot separate them -- check
  `eff n` before concluding anything at all.

**The conclusion is a sentence a person writes after reading those three, in the ticket's
own terms.** This report does not write it. The numbers constrain the conclusion; they do
not determine it.

## What we expected before looking

Recorded before any run, in this module, so the result can be scored against a prediction
rather than rationalised after the fact. **Whoever writes this run up owes each bullet a
verdict -- held, or did not hold, and by how much.** A plan that records a prediction and
never scores it has wasted the prediction.

* Majority-class should land near 60%, which is the generator's `null` share and not a property of the data worth anything.
* The length-only model is the direct measurable test of the length leak `arch_training.md` section 9 argues for but has never measured. Materially above majority means text length is a usable proxy for the label, which is a library problem rather than a model one.
* TF-IDF should do well on clear positives, clear negatives and `null_structural`, and badly on the ambiguous sub-classes. Its overall accuracy is therefore close to uninformative. **The number that matters is the `null_ambiguous` slice**, tested with McNemar against the transformer once that exists.
* Both negative controls must fail. Shuffled train labels must score at chance on the unpermuted test split, and no fragment or cluster may appear on both sides of a split.
* Arm A -- the frozen probe -- should handle clear positives, clear negatives and `null_structural`, and should do **badly** on the five hard `null` sub-classes. Third-party attribution, tense and metaphor are compositional scope problems, and a single mean-pooled vector blurs the structure that carries them: a linear probe over it has no mechanism for "the fever belongs to the daughter". A bad Arm A result on those slices is the predicted outcome, not a bug.
* Arm A beating TF-IDF on `null_ambiguous` would be a genuine finding about the encoder; losing to it there would say the pooled representation discards what the ambiguous libraries are made of. Either way the comparison is McNemar's, not two point estimates side by side -- and neither answers the ticket's question on its own, because Arm A cannot separate "the libraries are the bottleneck" from "the method is too weak". That is Arm B's job.
* Arm B -- the fine-tune -- is the arm that answers the ticket, and **either outcome is a finding**. If unfreezing 110M parameters lifts the five hard `null` sub-classes clear of Arm A, the frozen pooled representation was the bottleneck and the fix is model work. If it does not -- if a fully fine-tuned encoder still cannot tell whose fever it is or when it happened -- then the limit is in the ideas the libraries contain, and the fix is library work on the fragments the per-fragment table names. Nothing here predicts which; the point of building both arms is that the question stops being answerable by argument.
* Arm B's negative control passes by doing **two** things at once: driving training loss towards zero, because 110M parameters can memorise a permutation, while scoring at chance on the unpermuted test split. Near-zero training loss on its own is not a failure and chance test performance on its own is not a pass; the sidecar records the per-fold loss curve so both halves can be read.
* Arm B is expected to be *unstable* across folds in a way Arm A is not. Fine-tuning a 110M-parameter model on 10,000 recombinations of a few dozen fragments has far more freedom to fit fold-specific detail, so the across-fold standard deviation should be the wider of the two. That is a property of the arm, not evidence against it -- but it is why the pooled cluster bootstrap, not the fold spread, remains the headline interval.
* `max_seq_len` is not the interesting constraint. The proof-of-concept run's median example is 36 tokens and its 90th percentile 54, against a limit of 256. Training on 36-token recombinations and eventually serving 300-token real submissions is a distribution shift no sequence length fixes.

## Negative controls and checks

* **fragment disjointness** -- checked, not assumed. Loading each fold asserts that no fragment and no cluster appears in two of its splits, so no hand-written sentence is on both sides of a train/test boundary and no `[c01]` sibling pair is split across one. Asserted at load time on every run, and a violation is a hard error rather than a warning.
* **test partition** -- checked. Across the 5 folds, 2387 distinct clusters are held out, each in exactly one fold, so pooling the folds counts every idea once. That figure spans every library in the manifest -- filler and other signals' libraries included -- not just this signal's; the per-slice `eff n` columns are the numbers that bound anything.
* **fold configuration** -- checked. The three splits of each fold agree on generator version, fold count, fold index and salt, and all folds agree on the salt.

## Paired comparisons (McNemar, raw argmax)

Exact two-sided McNemar over the examples the two models disagree about. Pairing unit is the
example, not the cluster -- see the limitations.

| pair | slice | n | a only | b only | p |
|---|---|---|---|---|---|
| `arm_b_finetune@Arm0_control` vs `arm_b_finetune@ArmC_remargined` | overall | 10000 | 0 | 0 | 1 |
| `arm_b_finetune@Arm0_control` vs `arm_b_finetune@ArmC_remargined` | null_ambiguous | 3000 | 0 | 0 | 1 |

### Pairs that could not be tested

McNemar pairs on the example id, so two models scored on **different examples** cannot be
compared this way at all -- there is nothing to pair. That is a property of the datasets,
not a result: read those runs through their pooled cluster intervals and their per-fold
spread, and do not read the absence of a row above as agreement between them.

| pair | slice | n (a) | n (b) | shared | reason |
|---|---|---|---|---|---|
| `arm_b_finetune@Arm0_control` vs `arm_b_finetune@ArmP_companions` | overall | 10000 | 10000 | 0 | example sets differ: arm_b_finetune@Arm0_control has 10000, arm_b_finetune@ArmP_companions has 10000, 0 in common |
| `arm_b_finetune@Arm0_control` vs `arm_b_finetune@ArmP_companions` | null_ambiguous | 3000 | 3000 | 0 | example sets differ: arm_b_finetune@Arm0_control has 3000, arm_b_finetune@ArmP_companions has 3000, 0 in common |
| `arm_b_finetune@ArmC_remargined` vs `arm_b_finetune@ArmP_companions` | overall | 10000 | 10000 | 0 | example sets differ: arm_b_finetune@ArmC_remargined has 10000, arm_b_finetune@ArmP_companions has 10000, 0 in common |
| `arm_b_finetune@ArmC_remargined` vs `arm_b_finetune@ArmP_companions` | null_ambiguous | 3000 | 3000 | 0 | example sets differ: arm_b_finetune@ArmC_remargined has 3000, arm_b_finetune@ArmP_companions has 3000, 0 in common |

## What moved, and where

The headline is the least useful output of a model comparison. These two tables are the
useful one: a diffuse lift and a fix to one error family are different findings, and an
aggregate accuracy cannot tell them apart. `spread` is max minus min across the models --
a row where every encoder lands together is a row model choice does not touch.

### By library, accuracy after the decision rule

Worst-performing library first. For a single-class library -- `fever_false` holds only
`false` examples -- accuracy here *is* that class's recall on that library.

| library | n | `arm_b_finetune@Arm0_control` | `arm_b_finetune@ArmC_remargined` | `arm_b_finetune@ArmP_companions` | spread |
|---|---|---|---|---|---|
| `urinary_frequency_true` | 1620 | 73.6% | 73.5% | 72.3% | 1.3pp |
| `urinary_frequency_false` | 2395 | 81.3% | 81.3% | 81.2% | 0.1pp |
| `urinary_frequency_null_adjacent` | 620 | 87.3% | 87.9% | 90.5% | 3.2pp |
| `urinary_frequency_null_metaphor` | 590 | 91.2% | 91.7% | 92.2% | 1.0pp |
| `urinary_frequency_null_historical` | 533 | 94.0% | 94.0% | 99.2% | 5.3pp |
| `urinary_frequency_null_hedged` | 616 | 96.9% | 96.9% | 94.2% | 2.8pp |
| `(none)` | 2985 | 99.4% | 99.4% | 99.0% | 0.4pp |
| `urinary_frequency_null_thirdparty` | 641 | 99.5% | 99.5% | 99.2% | 0.3pp |

### By fragment, errors

Ordered by the worst model's error count, so the fragments the comparison is about sort
to the top whichever encoder wins. Counts, not rates: these are the sentences a month of
library work would be spent on. The JSON holds every fragment.

| fragment | library | truth | `arm_b_finetune@Arm0_control` | `arm_b_finetune@ArmC_remargined` | `arm_b_finetune@ArmP_companions` | spread |
|---|---|---|---|---|---|---|
| `urinary_frequency_false:d293ee8c` | `urinary_frequency_false` | false | 116 | 116 | 93 | 23 |
| `urinary_frequency_true:11d16987` | `urinary_frequency_true` | true | 53 | 53 | 83 | 30 |
| `urinary_frequency_false:a15017c2` | `urinary_frequency_false` | false | 44 | 44 | 76 | 32 |
| `urinary_frequency_false:a9a59952` | `urinary_frequency_false` | false | 0 | 0 | 61 | 61 |
| `urinary_frequency_false:c631660d` | `urinary_frequency_false` | false | 55 | 55 | 52 | 3 |
| `urinary_frequency_false:63302b59` | `urinary_frequency_false` | false | 49 | 49 | 53 | 4 |
| `urinary_frequency_true:ffa90ce7` | `urinary_frequency_true` | true | 52 | 52 | 52 | 0 |
| `urinary_frequency_true:2c452329` | `urinary_frequency_true` | true | 49 | 49 | 48 | 1 |
| `urinary_frequency_false:941626e8` | `urinary_frequency_false` | false | 43 | 43 | 27 | 16 |
| `urinary_frequency_true:cf215b55` | `urinary_frequency_true` | true | 43 | 43 | 16 | 27 |
| `urinary_frequency_false:f78f9d25` | `urinary_frequency_false` | false | 38 | 38 | 0 | 38 |
| `urinary_frequency_true:1d671fe5` | `urinary_frequency_true` | true | 21 | 21 | 37 | 16 |
| `urinary_frequency_true:764389c0` | `urinary_frequency_true` | true | 23 | 23 | 36 | 13 |
| `urinary_frequency_false:6bb71206` | `urinary_frequency_false` | false | 35 | 35 | 17 | 18 |
| `urinary_frequency_false:f32c9e68` | `urinary_frequency_false` | false | 35 | 35 | 34 | 1 |
| `urinary_frequency_true:eccbc8ee` | `urinary_frequency_true` | true | 35 | 35 | 4 | 31 |
| `urinary_frequency_false:f3e3b17c` | `urinary_frequency_false` | false | 30 | 30 | 0 | 30 |
| `urinary_frequency_true:32cae421` | `urinary_frequency_true` | true | 29 | 29 | 29 | 0 |
| `urinary_frequency_false:046669da` | `urinary_frequency_false` | false | 0 | 0 | 28 | 28 |
| `urinary_frequency_true:57632816` | `urinary_frequency_true` | true | 7 | 7 | 27 | 20 |
| `urinary_frequency_true:c8d32074` | `urinary_frequency_true` | true | 25 | 25 | 25 | 0 |
| `urinary_frequency_true:20bd4d56` | `urinary_frequency_true` | true | 24 | 24 | 0 | 24 |
| `urinary_frequency_true:fecb0185` | `urinary_frequency_true` | true | 21 | 21 | 20 | 1 |
| `urinary_frequency_true:32946372` | `urinary_frequency_true` | true | 20 | 20 | 17 | 3 |
| `urinary_frequency_null_hedged:fc9770b8` | `urinary_frequency_null_hedged` | null | 0 | 0 | 19 | 19 |
| `urinary_frequency_true:617cfdc3` | `urinary_frequency_true` | true | 0 | 0 | 19 | 19 |
| `urinary_frequency_true:f9c03b9b` | `urinary_frequency_true` | true | 0 | 0 | 19 | 19 |
| `urinary_frequency_null_metaphor:fafdd681` | `urinary_frequency_null_metaphor` | null | 18 | 18 | 15 | 3 |
| `urinary_frequency_null_adjacent:b2b71c86` | `urinary_frequency_null_adjacent` | null | 17 | 17 | 13 | 4 |
| `urinary_frequency_null_adjacent:30abc414` | `urinary_frequency_null_adjacent` | null | 16 | 15 | 16 | 1 |
| `urinary_frequency_null_metaphor:eb9e9615` | `urinary_frequency_null_metaphor` | null | 15 | 12 | 16 | 4 |
| `urinary_frequency_null_adjacent:5b4c0201` | `urinary_frequency_null_adjacent` | null | 15 | 15 | 0 | 15 |
| `urinary_frequency_null_adjacent:c791bce4` | `urinary_frequency_null_adjacent` | null | 15 | 15 | 8 | 7 |
| `urinary_frequency_null_hedged:61fe8d58` | `urinary_frequency_null_hedged` | null | 10 | 10 | 14 | 4 |
| `urinary_frequency_null_historical:a55c033d` | `urinary_frequency_null_historical` | null | 14 | 14 | 0 | 14 |
| `urinary_frequency_null_adjacent:d67c5d52` | `urinary_frequency_null_adjacent` | null | 13 | 11 | 5 | 8 |
| `urinary_frequency_null_adjacent:15320912` | `urinary_frequency_null_adjacent` | null | 0 | 0 | 12 | 12 |
| `urinary_frequency_null_historical:8befbb86` | `urinary_frequency_null_historical` | null | 12 | 12 | 0 | 12 |
| `urinary_frequency_null_metaphor:5c1e4a7d` | `urinary_frequency_null_metaphor` | null | 12 | 12 | 0 | 12 |
| `urinary_frequency_null_metaphor:518f483f` | `urinary_frequency_null_metaphor` | null | 2 | 2 | 11 | 9 |

*45 further fragments erred on at least one model; the JSON holds them all.*

## `arm_b_finetune@Arm0_control`

`roberta-base` with **every layer unfrozen**, mean-pooled, with the same `Linear(768, 3)` head -- 110M trainable parameters against Arm A's 2,307. Three epochs at batch 32, learning rate 2e-5, 10% linear warmup, AdamW, fp32. No gradient checkpointing, no 8-bit optimiser, no LoRA, no gradient accumulation: the full model fits in 12GB with room to spare, so anything that reads like a compute compromise would be a mistake rather than a saving. This is the arm that separates "the fragment libraries are the bottleneck" from "the method is too weak": if a fully fine-tuned encoder still cannot read third-party attribution, tense or metaphor, the limit is in the ideas the libraries contain and the fix is library work, not model work. **Joint multi-head training**: 6 heads sharing one encoder (dysuria_present, fever_present, flank_pain_present, haematuria_present, nocturia_present, urinary_frequency_present). Epoch selection uses DD6's unweighted mean of every head's own validation macro-F1, so this signal's stopping point may differ from a single-signal run's own best epoch. Each head's margin is chosen independently on its own validation split -- no cross-head trade.

Decision-rule margins selected per fold (on each fold's own validation split): 0.05, 0.25, 0.9.

*Confusion matrix, raw argmax*

|  | pred false | pred true | pred null | total |
|---|---|---|---|---|
| **truth false** | 1937 | 259 | 199 | 2395 |
| **truth true** | 84 | 1254 | 282 | 1620 |
| **truth null** | 55 | 163 | 5767 | 5985 |
| **total** | 2076 | 1676 | 6248 | 10000 |

`null -> true`: 163 of 5985 truly-null examples (2.72%).

*Confusion matrix, after the decision rule*

|  | pred false | pred true | pred null | total |
|---|---|---|---|---|
| **truth false** | 1948 | 245 | 202 | 2395 |
| **truth true** | 96 | 1192 | 332 | 1620 |
| **truth null** | 57 | 146 | 5782 | 5985 |
| **total** | 2101 | 1583 | 6316 | 10000 |

`null -> true`: 146 of 5985 truly-null examples (2.44%).

### Per class, after the decision rule

| class | support | predicted | precision | recall | F1 |
|---|---|---|---|---|---|
| `false` | 2395 | 2101 | 92.7% | 81.3% | 86.7% |
| `true` | 1620 | 1583 | 75.3% | 73.6% | 74.4% |
| `null` | 5985 | 6316 | 91.5% | 96.6% | 94.0% |

### By label mode

| label mode | n | eff n | accuracy [95% CI] |
|---|---|---|---|
| false | 2395 | **46** | 81.3% [69.4%, 92.4%] |
| null_ambiguous | 3000 | **210** | 93.8% [90.9%, 96.8%] |
| null_structural | 2985 | **1** | 99.4% [99.4%, 99.4%] |
| true | 1620 | **46** | 73.6% [61.0%, 84.6%] |

### By null sub-class

| sub-class | n | eff n | null recall [95% CI] |
|---|---|---|---|
| adjacent | 621 | **40** | 87.3% [76.8%, 96.4%] |
| hedged | 622 | **42** | 96.9% [93.0%, 99.8%] |
| historical | 529 | **40** | 94.0% [86.4%, 99.5%] |
| metaphor | 592 | **44** | 91.2% [82.3%, 98.8%] |
| third_party | 636 | **44** | 99.5% [98.8%, 100.0%] |

### By fragment library

| library | n | eff n | accuracy [95% CI] |
|---|---|---|---|
| urinary_frequency_false | 2395 | **46** | 81.3% [69.4%, 92.4%] |
| urinary_frequency_null_adjacent | 621 | **40** | 87.3% [76.8%, 96.4%] |
| urinary_frequency_null_hedged | 622 | **42** | 96.9% [93.0%, 99.8%] |
| urinary_frequency_null_historical | 529 | **40** | 94.0% [86.4%, 99.5%] |
| urinary_frequency_null_metaphor | 592 | **44** | 91.2% [82.3%, 98.8%] |
| urinary_frequency_null_thirdparty | 636 | **44** | 99.5% [98.8%, 100.0%] |
| urinary_frequency_true | 1620 | **46** | 73.6% [61.0%, 84.6%] |
| (none) | 2985 | **1** | 99.4% [99.4%, 99.4%] |

### Per-fragment errors (worst first)

Whether errors are spread thinly across many fragments or piled onto a few is the difference
between "the method is too weak" (model work) and "these specific ideas are not learnable from
the data we have" (library work, and these are the fragments to write more of). No intervals:
a fragment is one cluster, so an interval over its own examples measures nothing.

55 of 302 decisive fragments were got wrong at least once.

`arm_b_finetune@Arm0_control`: 1060 errors across 55 of 302 decisive fragments. Half of them fall on **10** fragments (an even spread would be 27.5); the worst ten carry 51.1% of all errors.

| fragment | library | sub-class | truth | correct | accuracy | predicted as |
|---|---|---|---|---|---|---|
| `urinary_frequency_false:d293ee8c` | `urinary_frequency_false` | -- | false | 0/116 | 0.0% | true 116 |
| `urinary_frequency_false:c631660d` | `urinary_frequency_false` | -- | false | 0/55 | 0.0% | null 55 |
| `urinary_frequency_true:ffa90ce7` | `urinary_frequency_true` | -- | true | 0/52 | 0.0% | null 52 |
| `urinary_frequency_false:63302b59` | `urinary_frequency_false` | -- | false | 0/49 | 0.0% | true 49 |
| `urinary_frequency_true:2c452329` | `urinary_frequency_true` | -- | true | 0/49 | 0.0% | false 49 |
| `urinary_frequency_false:f32c9e68` | `urinary_frequency_false` | -- | false | 0/35 | 0.0% | true 35 |
| `urinary_frequency_true:32cae421` | `urinary_frequency_true` | -- | true | 0/29 | 0.0% | false 29 |
| `urinary_frequency_true:c8d32074` | `urinary_frequency_true` | -- | true | 0/25 | 0.0% | null 25 |
| `urinary_frequency_true:fecb0185` | `urinary_frequency_true` | -- | true | 0/21 | 0.0% | null 21 |
| `urinary_frequency_true:32946372` | `urinary_frequency_true` | -- | true | 0/20 | 0.0% | null 20 |
| `urinary_frequency_null_metaphor:fafdd681` | `urinary_frequency_null_metaphor` | metaphor | null | 0/18 | 0.0% | true 18 |
| `urinary_frequency_null_adjacent:b2b71c86` | `urinary_frequency_null_adjacent` | adjacent | null | 0/17 | 0.0% | true 17 |
| `urinary_frequency_null_adjacent:5b4c0201` | `urinary_frequency_null_adjacent` | adjacent | null | 0/15 | 0.0% | true 15 |
| `urinary_frequency_null_adjacent:c791bce4` | `urinary_frequency_null_adjacent` | adjacent | null | 0/15 | 0.0% | true 15 |
| `urinary_frequency_null_historical:8befbb86` | `urinary_frequency_null_historical` | historical | null | 0/12 | 0.0% | true 12 |
| `urinary_frequency_false:941626e8` | `urinary_frequency_false` | -- | false | 2/45 | 4.4% | false 2, null 43 |
| `urinary_frequency_true:cf215b55` | `urinary_frequency_true` | -- | true | 2/45 | 4.4% | false 1, true 2, null 42 |
| `urinary_frequency_null_adjacent:30abc414` | `urinary_frequency_null_adjacent` | adjacent | null | 1/17 | 5.9% | false 11, true 5, null 1 |
| `urinary_frequency_null_metaphor:eb9e9615` | `urinary_frequency_null_metaphor` | metaphor | null | 1/16 | 6.2% | true 15, null 1 |
| `urinary_frequency_null_historical:a55c033d` | `urinary_frequency_null_historical` | historical | null | 1/15 | 6.7% | false 14, null 1 |
| `urinary_frequency_null_metaphor:5c1e4a7d` | `urinary_frequency_null_metaphor` | metaphor | null | 1/13 | 7.7% | true 12, null 1 |
| `urinary_frequency_true:eccbc8ee` | `urinary_frequency_true` | -- | true | 3/38 | 7.9% | false 2, true 3, null 33 |
| `urinary_frequency_false:f78f9d25` | `urinary_frequency_false` | -- | false | 4/42 | 9.5% | false 4, null 38 |
| `urinary_frequency_true:20bd4d56` | `urinary_frequency_true` | -- | true | 3/27 | 11.1% | true 3, null 24 |
| `urinary_frequency_null_adjacent:d67c5d52` | `urinary_frequency_null_adjacent` | adjacent | null | 3/16 | 18.8% | true 13, null 3 |
| `urinary_frequency_true:11d16987` | `urinary_frequency_true` | -- | true | 25/78 | 32.1% | false 11, true 25, null 42 |
| `urinary_frequency_null_hedged:61fe8d58` | `urinary_frequency_null_hedged` | hedged | null | 5/15 | 33.3% | false 10, null 5 |
| `urinary_frequency_false:6bb71206` | `urinary_frequency_false` | -- | false | 18/53 | 34.0% | false 18, null 35 |
| `urinary_frequency_true:1d671fe5` | `urinary_frequency_true` | -- | true | 14/35 | 40.0% | false 1, true 14, null 20 |
| `urinary_frequency_false:f3e3b17c` | `urinary_frequency_false` | -- | false | 24/54 | 44.4% | false 24, null 30 |
| `urinary_frequency_true:5ef90c41` | `urinary_frequency_true` | -- | true | 15/26 | 57.7% | true 15, null 11 |
| `urinary_frequency_true:2491f080` | `urinary_frequency_true` | -- | true | 18/28 | 64.3% | true 18, null 10 |
| `urinary_frequency_null_hedged:5f612dfb` | `urinary_frequency_null_hedged` | hedged | null | 9/14 | 64.3% | true 5, null 9 |
| `urinary_frequency_true:764389c0` | `urinary_frequency_true` | -- | true | 42/65 | 64.6% | false 1, true 42, null 22 |
| `urinary_frequency_false:a15017c2` | `urinary_frequency_false` | -- | false | 82/126 | 65.1% | false 82, true 44 |
| `urinary_frequency_null_historical:9bf779d3` | `urinary_frequency_null_historical` | historical | null | 11/15 | 73.3% | false 4, null 11 |
| `urinary_frequency_true:57632816` | `urinary_frequency_true` | -- | true | 21/28 | 75.0% | true 21, null 7 |
| `urinary_frequency_null_metaphor:816dd75b` | `urinary_frequency_null_metaphor` | metaphor | null | 9/11 | 81.8% | true 2, null 9 |
| `urinary_frequency_null_hedged:fe13847c` | `urinary_frequency_null_hedged` | hedged | null | 14/17 | 82.4% | false 2, true 1, null 14 |
| `urinary_frequency_null_metaphor:0ec3759f` | `urinary_frequency_null_metaphor` | metaphor | null | 11/13 | 84.6% | false 2, null 11 |

*15 further fragments with at least one error are in the JSON sidecar; every fragment is there regardless of score.*

## `arm_b_finetune@ArmC_remargined`

`roberta-base` with **every layer unfrozen**, mean-pooled, with the same `Linear(768, 3)` head -- 110M trainable parameters against Arm A's 2,307. Three epochs at batch 32, learning rate 2e-5, 10% linear warmup, AdamW, fp32. No gradient checkpointing, no 8-bit optimiser, no LoRA, no gradient accumulation: the full model fits in 12GB with room to spare, so anything that reads like a compute compromise would be a mistake rather than a saving. This is the arm that separates "the fragment libraries are the bottleneck" from "the method is too weak": if a fully fine-tuned encoder still cannot read third-party attribution, tense or metaphor, the limit is in the ideas the libraries contain and the fix is library work, not model work. **Margin re-selected, not retrained**: these are the trained heads of the arm above, with every head's decision margin chosen on `ArmP_companions`'s validation split instead of their own. Identical weights, identical raw argmax scores, identical test examples -- the only difference is the threshold, so a gap between this arm and the one it came from is margin selection alone.

Decision-rule margins selected per fold (on each fold's own validation split): 0.65, 0.85, 0.9.

*Confusion matrix, raw argmax*

|  | pred false | pred true | pred null | total |
|---|---|---|---|---|
| **truth false** | 1937 | 259 | 199 | 2395 |
| **truth true** | 84 | 1254 | 282 | 1620 |
| **truth null** | 55 | 163 | 5767 | 5985 |
| **total** | 2076 | 1676 | 6248 | 10000 |

`null -> true`: 163 of 5985 truly-null examples (2.72%).

*Confusion matrix, after the decision rule*

|  | pred false | pred true | pred null | total |
|---|---|---|---|---|
| **truth false** | 1948 | 245 | 202 | 2395 |
| **truth true** | 96 | 1191 | 333 | 1620 |
| **truth null** | 57 | 139 | 5789 | 5985 |
| **total** | 2101 | 1575 | 6324 | 10000 |

`null -> true`: 139 of 5985 truly-null examples (2.32%).

### Per class, after the decision rule

| class | support | predicted | precision | recall | F1 |
|---|---|---|---|---|---|
| `false` | 2395 | 2101 | 92.7% | 81.3% | 86.7% |
| `true` | 1620 | 1575 | 75.6% | 73.5% | 74.6% |
| `null` | 5985 | 6324 | 91.5% | 96.7% | 94.1% |

### By label mode

| label mode | n | eff n | accuracy [95% CI] |
|---|---|---|---|
| false | 2395 | **46** | 81.3% [69.4%, 92.4%] |
| null_ambiguous | 3000 | **210** | 94.1% [91.2%, 96.9%] |
| null_structural | 2985 | **1** | 99.4% [99.4%, 99.4%] |
| true | 1620 | **46** | 73.5% [61.0%, 84.6%] |

### By null sub-class

| sub-class | n | eff n | null recall [95% CI] |
|---|---|---|---|
| adjacent | 621 | **40** | 87.9% [77.8%, 96.7%] |
| hedged | 622 | **42** | 96.9% [93.0%, 99.8%] |
| historical | 529 | **40** | 94.0% [86.4%, 99.5%] |
| metaphor | 592 | **44** | 91.7% [83.3%, 98.8%] |
| third_party | 636 | **44** | 99.5% [98.8%, 100.0%] |

### By fragment library

| library | n | eff n | accuracy [95% CI] |
|---|---|---|---|
| urinary_frequency_false | 2395 | **46** | 81.3% [69.4%, 92.4%] |
| urinary_frequency_null_adjacent | 621 | **40** | 87.9% [77.8%, 96.7%] |
| urinary_frequency_null_hedged | 622 | **42** | 96.9% [93.0%, 99.8%] |
| urinary_frequency_null_historical | 529 | **40** | 94.0% [86.4%, 99.5%] |
| urinary_frequency_null_metaphor | 592 | **44** | 91.7% [83.3%, 98.8%] |
| urinary_frequency_null_thirdparty | 636 | **44** | 99.5% [98.8%, 100.0%] |
| urinary_frequency_true | 1620 | **46** | 73.5% [61.0%, 84.6%] |
| (none) | 2985 | **1** | 99.4% [99.4%, 99.4%] |

### Per-fragment errors (worst first)

Whether errors are spread thinly across many fragments or piled onto a few is the difference
between "the method is too weak" (model work) and "these specific ideas are not learnable from
the data we have" (library work, and these are the fragments to write more of). No intervals:
a fragment is one cluster, so an interval over its own examples measures nothing.

54 of 302 decisive fragments were got wrong at least once.

`arm_b_finetune@ArmC_remargined`: 1054 errors across 54 of 302 decisive fragments. Half of them fall on **10** fragments (an even spread would be 27.0); the worst ten carry 51.4% of all errors.

| fragment | library | sub-class | truth | correct | accuracy | predicted as |
|---|---|---|---|---|---|---|
| `urinary_frequency_false:d293ee8c` | `urinary_frequency_false` | -- | false | 0/116 | 0.0% | true 116 |
| `urinary_frequency_false:c631660d` | `urinary_frequency_false` | -- | false | 0/55 | 0.0% | null 55 |
| `urinary_frequency_true:ffa90ce7` | `urinary_frequency_true` | -- | true | 0/52 | 0.0% | null 52 |
| `urinary_frequency_false:63302b59` | `urinary_frequency_false` | -- | false | 0/49 | 0.0% | true 49 |
| `urinary_frequency_true:2c452329` | `urinary_frequency_true` | -- | true | 0/49 | 0.0% | false 49 |
| `urinary_frequency_false:f32c9e68` | `urinary_frequency_false` | -- | false | 0/35 | 0.0% | true 35 |
| `urinary_frequency_true:32cae421` | `urinary_frequency_true` | -- | true | 0/29 | 0.0% | false 29 |
| `urinary_frequency_true:c8d32074` | `urinary_frequency_true` | -- | true | 0/25 | 0.0% | null 25 |
| `urinary_frequency_true:fecb0185` | `urinary_frequency_true` | -- | true | 0/21 | 0.0% | null 21 |
| `urinary_frequency_true:32946372` | `urinary_frequency_true` | -- | true | 0/20 | 0.0% | null 20 |
| `urinary_frequency_null_metaphor:fafdd681` | `urinary_frequency_null_metaphor` | metaphor | null | 0/18 | 0.0% | true 18 |
| `urinary_frequency_null_adjacent:b2b71c86` | `urinary_frequency_null_adjacent` | adjacent | null | 0/17 | 0.0% | true 17 |
| `urinary_frequency_null_adjacent:5b4c0201` | `urinary_frequency_null_adjacent` | adjacent | null | 0/15 | 0.0% | true 15 |
| `urinary_frequency_null_adjacent:c791bce4` | `urinary_frequency_null_adjacent` | adjacent | null | 0/15 | 0.0% | true 15 |
| `urinary_frequency_null_historical:8befbb86` | `urinary_frequency_null_historical` | historical | null | 0/12 | 0.0% | true 12 |
| `urinary_frequency_false:941626e8` | `urinary_frequency_false` | -- | false | 2/45 | 4.4% | false 2, null 43 |
| `urinary_frequency_true:cf215b55` | `urinary_frequency_true` | -- | true | 2/45 | 4.4% | false 1, true 2, null 42 |
| `urinary_frequency_null_historical:a55c033d` | `urinary_frequency_null_historical` | historical | null | 1/15 | 6.7% | false 14, null 1 |
| `urinary_frequency_null_metaphor:5c1e4a7d` | `urinary_frequency_null_metaphor` | metaphor | null | 1/13 | 7.7% | true 12, null 1 |
| `urinary_frequency_true:eccbc8ee` | `urinary_frequency_true` | -- | true | 3/38 | 7.9% | false 2, true 3, null 33 |
| `urinary_frequency_false:f78f9d25` | `urinary_frequency_false` | -- | false | 4/42 | 9.5% | false 4, null 38 |
| `urinary_frequency_true:20bd4d56` | `urinary_frequency_true` | -- | true | 3/27 | 11.1% | true 3, null 24 |
| `urinary_frequency_null_adjacent:30abc414` | `urinary_frequency_null_adjacent` | adjacent | null | 2/17 | 11.8% | false 11, true 4, null 2 |
| `urinary_frequency_null_metaphor:eb9e9615` | `urinary_frequency_null_metaphor` | metaphor | null | 4/16 | 25.0% | true 12, null 4 |
| `urinary_frequency_null_adjacent:d67c5d52` | `urinary_frequency_null_adjacent` | adjacent | null | 5/16 | 31.2% | true 11, null 5 |
| `urinary_frequency_true:11d16987` | `urinary_frequency_true` | -- | true | 25/78 | 32.1% | false 11, true 25, null 42 |
| `urinary_frequency_null_hedged:61fe8d58` | `urinary_frequency_null_hedged` | hedged | null | 5/15 | 33.3% | false 10, null 5 |
| `urinary_frequency_false:6bb71206` | `urinary_frequency_false` | -- | false | 18/53 | 34.0% | false 18, null 35 |
| `urinary_frequency_true:1d671fe5` | `urinary_frequency_true` | -- | true | 14/35 | 40.0% | false 1, true 14, null 20 |
| `urinary_frequency_false:f3e3b17c` | `urinary_frequency_false` | -- | false | 24/54 | 44.4% | false 24, null 30 |
| `urinary_frequency_true:5ef90c41` | `urinary_frequency_true` | -- | true | 15/26 | 57.7% | true 15, null 11 |
| `urinary_frequency_true:2491f080` | `urinary_frequency_true` | -- | true | 17/28 | 60.7% | true 17, null 11 |
| `urinary_frequency_null_hedged:5f612dfb` | `urinary_frequency_null_hedged` | hedged | null | 9/14 | 64.3% | true 5, null 9 |
| `urinary_frequency_true:764389c0` | `urinary_frequency_true` | -- | true | 42/65 | 64.6% | false 1, true 42, null 22 |
| `urinary_frequency_false:a15017c2` | `urinary_frequency_false` | -- | false | 82/126 | 65.1% | false 82, true 44 |
| `urinary_frequency_null_historical:9bf779d3` | `urinary_frequency_null_historical` | historical | null | 11/15 | 73.3% | false 4, null 11 |
| `urinary_frequency_true:57632816` | `urinary_frequency_true` | -- | true | 21/28 | 75.0% | true 21, null 7 |
| `urinary_frequency_null_metaphor:816dd75b` | `urinary_frequency_null_metaphor` | metaphor | null | 9/11 | 81.8% | true 2, null 9 |
| `urinary_frequency_null_hedged:fe13847c` | `urinary_frequency_null_hedged` | hedged | null | 14/17 | 82.4% | false 2, true 1, null 14 |
| `urinary_frequency_null_metaphor:0ec3759f` | `urinary_frequency_null_metaphor` | metaphor | null | 11/13 | 84.6% | false 2, null 11 |

*14 further fragments with at least one error are in the JSON sidecar; every fragment is there regardless of score.*

## `arm_b_finetune@ArmP_companions`

`roberta-base` with **every layer unfrozen**, mean-pooled, with the same `Linear(768, 3)` head -- 110M trainable parameters against Arm A's 2,307. Three epochs at batch 32, learning rate 2e-5, 10% linear warmup, AdamW, fp32. No gradient checkpointing, no 8-bit optimiser, no LoRA, no gradient accumulation: the full model fits in 12GB with room to spare, so anything that reads like a compute compromise would be a mistake rather than a saving. This is the arm that separates "the fragment libraries are the bottleneck" from "the method is too weak": if a fully fine-tuned encoder still cannot read third-party attribution, tense or metaphor, the limit is in the ideas the libraries contain and the fix is library work, not model work. **Joint multi-head training**: 6 heads sharing one encoder (dysuria_present, fever_present, flank_pain_present, haematuria_present, nocturia_present, urinary_frequency_present). Epoch selection uses DD6's unweighted mean of every head's own validation macro-F1, so this signal's stopping point may differ from a single-signal run's own best epoch. Each head's margin is chosen independently on its own validation split -- no cross-head trade.

Decision-rule margins selected per fold (on each fold's own validation split): 0.0, 0.25, 0.55, 0.9.

*Confusion matrix, raw argmax*

|  | pred false | pred true | pred null | total |
|---|---|---|---|---|
| **truth false** | 1899 | 395 | 101 | 2395 |
| **truth true** | 121 | 1214 | 285 | 1620 |
| **truth null** | 61 | 129 | 5795 | 5985 |
| **total** | 2081 | 1738 | 6181 | 10000 |

`null -> true`: 129 of 5985 truly-null examples (2.16%).

*Confusion matrix, after the decision rule*

|  | pred false | pred true | pred null | total |
|---|---|---|---|---|
| **truth false** | 1945 | 347 | 103 | 2395 |
| **truth true** | 139 | 1171 | 310 | 1620 |
| **truth null** | 70 | 110 | 5805 | 5985 |
| **total** | 2154 | 1628 | 6218 | 10000 |

`null -> true`: 110 of 5985 truly-null examples (1.84%).

### Per class, after the decision rule

| class | support | predicted | precision | recall | F1 |
|---|---|---|---|---|---|
| `false` | 2395 | 2154 | 90.3% | 81.2% | 85.5% |
| `true` | 1620 | 1628 | 71.9% | 72.3% | 72.1% |
| `null` | 5985 | 6218 | 93.4% | 97.0% | 95.1% |

### By label mode

| label mode | n | eff n | accuracy [95% CI] |
|---|---|---|---|
| false | 2395 | **46** | 81.2% [69.2%, 92.2%] |
| null_ambiguous | 3000 | **210** | 95.0% [92.3%, 97.6%] |
| null_structural | 2985 | **1** | 99.0% [99.0%, 99.0%] |
| true | 1620 | **46** | 72.3% [58.3%, 84.7%] |

### By null sub-class

| sub-class | n | eff n | null recall [95% CI] |
|---|---|---|---|
| adjacent | 620 | **40** | 90.5% [81.9%, 97.2%] |
| hedged | 616 | **42** | 94.2% [86.0%, 99.7%] |
| historical | 533 | **40** | 99.2% [98.5%, 99.8%] |
| metaphor | 590 | **44** | 92.2% [84.4%, 99.3%] |
| third_party | 641 | **44** | 99.2% [98.5%, 99.8%] |

### By fragment library

| library | n | eff n | accuracy [95% CI] |
|---|---|---|---|
| urinary_frequency_false | 2395 | **46** | 81.2% [69.2%, 92.2%] |
| urinary_frequency_null_adjacent | 620 | **40** | 90.5% [81.9%, 97.2%] |
| urinary_frequency_null_hedged | 616 | **42** | 94.2% [86.0%, 99.7%] |
| urinary_frequency_null_historical | 533 | **40** | 99.2% [98.5%, 99.8%] |
| urinary_frequency_null_metaphor | 590 | **44** | 92.2% [84.4%, 99.3%] |
| urinary_frequency_null_thirdparty | 641 | **44** | 99.2% [98.5%, 99.8%] |
| urinary_frequency_true | 1620 | **46** | 72.3% [58.3%, 84.7%] |
| (none) | 2985 | **1** | 99.0% [99.0%, 99.0%] |

### Per-fragment errors (worst first)

Whether errors are spread thinly across many fragments or piled onto a few is the difference
between "the method is too weak" (model work) and "these specific ideas are not learnable from
the data we have" (library work, and these are the fragments to write more of). No intervals:
a fragment is one cluster, so an interval over its own examples measures nothing.

62 of 302 decisive fragments were got wrong at least once.

`arm_b_finetune@ArmP_companions`: 1049 errors across 62 of 302 decisive fragments. Half of them fall on **9** fragments (an even spread would be 31.0); the worst ten carry 56.3% of all errors.

| fragment | library | sub-class | truth | correct | accuracy | predicted as |
|---|---|---|---|---|---|---|
| `urinary_frequency_true:11d16987` | `urinary_frequency_true` | -- | true | 0/83 | 0.0% | null 83 |
| `urinary_frequency_false:a9a59952` | `urinary_frequency_false` | -- | false | 0/61 | 0.0% | true 61 |
| `urinary_frequency_false:63302b59` | `urinary_frequency_false` | -- | false | 0/53 | 0.0% | true 53 |
| `urinary_frequency_false:c631660d` | `urinary_frequency_false` | -- | false | 0/52 | 0.0% | null 52 |
| `urinary_frequency_true:ffa90ce7` | `urinary_frequency_true` | -- | true | 0/52 | 0.0% | null 52 |
| `urinary_frequency_true:2c452329` | `urinary_frequency_true` | -- | true | 0/48 | 0.0% | false 48 |
| `urinary_frequency_true:1d671fe5` | `urinary_frequency_true` | -- | true | 0/37 | 0.0% | false 37 |
| `urinary_frequency_false:f32c9e68` | `urinary_frequency_false` | -- | false | 0/34 | 0.0% | true 34 |
| `urinary_frequency_true:32cae421` | `urinary_frequency_true` | -- | true | 0/29 | 0.0% | false 29 |
| `urinary_frequency_true:57632816` | `urinary_frequency_true` | -- | true | 0/27 | 0.0% | null 27 |
| `urinary_frequency_true:c8d32074` | `urinary_frequency_true` | -- | true | 0/25 | 0.0% | null 25 |
| `urinary_frequency_null_adjacent:30abc414` | `urinary_frequency_null_adjacent` | adjacent | null | 0/16 | 0.0% | false 16 |
| `urinary_frequency_null_metaphor:eb9e9615` | `urinary_frequency_null_metaphor` | metaphor | null | 0/16 | 0.0% | true 16 |
| `urinary_frequency_true:fecb0185` | `urinary_frequency_true` | -- | true | 1/21 | 4.8% | true 1, null 20 |
| `urinary_frequency_null_hedged:61fe8d58` | `urinary_frequency_null_hedged` | hedged | null | 1/15 | 6.7% | false 14, null 1 |
| `urinary_frequency_null_hedged:fc9770b8` | `urinary_frequency_null_hedged` | hedged | null | 2/21 | 9.5% | true 19, null 2 |
| `urinary_frequency_true:32946372` | `urinary_frequency_true` | -- | true | 3/20 | 15.0% | false 2, true 3, null 15 |
| `urinary_frequency_false:046669da` | `urinary_frequency_false` | -- | false | 5/33 | 15.2% | false 5, true 28 |
| `urinary_frequency_null_metaphor:518f483f` | `urinary_frequency_null_metaphor` | metaphor | null | 2/13 | 15.4% | false 9, true 2, null 2 |
| `urinary_frequency_null_metaphor:fafdd681` | `urinary_frequency_null_metaphor` | metaphor | null | 3/18 | 16.7% | true 15, null 3 |
| `urinary_frequency_true:f9c03b9b` | `urinary_frequency_true` | -- | true | 4/23 | 17.4% | true 4, null 19 |
| `urinary_frequency_false:d293ee8c` | `urinary_frequency_false` | -- | false | 20/113 | 17.7% | false 20, true 93 |
| `urinary_frequency_true:617cfdc3` | `urinary_frequency_true` | -- | true | 6/25 | 24.0% | true 6, null 19 |
| `urinary_frequency_null_adjacent:b2b71c86` | `urinary_frequency_null_adjacent` | adjacent | null | 5/18 | 27.8% | true 13, null 5 |
| `urinary_frequency_null_adjacent:15320912` | `urinary_frequency_null_adjacent` | adjacent | null | 7/19 | 36.8% | false 12, null 7 |
| `urinary_frequency_false:a15017c2` | `urinary_frequency_false` | -- | false | 50/126 | 39.7% | false 50, true 76 |
| `urinary_frequency_true:764389c0` | `urinary_frequency_true` | -- | true | 25/61 | 41.0% | false 21, true 25, null 15 |
| `urinary_frequency_false:941626e8` | `urinary_frequency_false` | -- | false | 21/48 | 43.8% | false 21, null 27 |
| `urinary_frequency_null_adjacent:c791bce4` | `urinary_frequency_null_adjacent` | adjacent | null | 7/15 | 46.7% | true 8, null 7 |
| `urinary_frequency_true:cf215b55` | `urinary_frequency_true` | -- | true | 28/44 | 63.6% | true 28, null 16 |
| `urinary_frequency_false:6bb71206` | `urinary_frequency_false` | -- | false | 35/52 | 67.3% | false 35, true 1, null 16 |
| `urinary_frequency_true:5ef90c41` | `urinary_frequency_true` | -- | true | 17/25 | 68.0% | true 17, null 8 |
| `urinary_frequency_null_adjacent:d67c5d52` | `urinary_frequency_null_adjacent` | adjacent | null | 12/17 | 70.6% | true 5, null 12 |
| `urinary_frequency_null_adjacent:fad41588` | `urinary_frequency_null_adjacent` | adjacent | null | 5/7 | 71.4% | true 2, null 5 |
| `urinary_frequency_true:fbca5613` | `urinary_frequency_true` | -- | true | 19/24 | 79.2% | true 19, null 5 |
| `urinary_frequency_false:a61aba66` | `urinary_frequency_false` | -- | false | 19/23 | 82.6% | false 19, null 4 |
| `urinary_frequency_false:7be58a30` | `urinary_frequency_false` | -- | false | 22/25 | 88.0% | false 22, null 3 |
| `urinary_frequency_null_thirdparty:d8cad4db` | `urinary_frequency_null_thirdparty` | third_party | null | 8/9 | 88.9% | false 1, null 8 |
| `urinary_frequency_true:eccbc8ee` | `urinary_frequency_true` | -- | true | 34/38 | 89.5% | false 1, true 34, null 3 |
| `urinary_frequency_true:f5216cf2` | `urinary_frequency_true` | -- | true | 17/19 | 89.5% | true 17, null 2 |

*22 further fragments with at least one error are in the JSON sidecar; every fragment is there regardless of score.*

## Appendix: per-fold numbers

Point estimates only. A single fold's test slice holds 2-5 clusters per hard sub-class, which
is the whole reason the headline is pooled.

### `arm_b_finetune@Arm0_control`

| fold | train n | val n | test n | margin | acc (raw) | acc (ruled) | macro-F1 | null->true |
|---|---|---|---|---|---|---|---|---|
| 0 | 44680 | 2000 | 2000 | 0.25 | 92.0% | 92.2% | 89.6% | 5.43% |
| 1 | 44680 | 2000 | 2000 | 0.9 | 84.5% | 82.5% | 74.8% | 0.17% |
| 2 | 44680 | 2000 | 2000 | 0.05 | 93.2% | 93.2% | 91.0% | 4.93% |
| 3 | 44680 | 2000 | 2000 | 0.9 | 93.5% | 92.7% | 89.9% | 0.08% |
| 4 | 44680 | 2000 | 2000 | 0.9 | 84.7% | 85.5% | 78.9% | 1.59% |

### `arm_b_finetune@ArmC_remargined`

| fold | train n | val n | test n | margin | acc (raw) | acc (ruled) | macro-F1 | null->true |
|---|---|---|---|---|---|---|---|---|
| 0 | 44680 | 2000 | 2000 | 0.65 | 92.0% | 92.3% | 89.9% | 5.10% |
| 1 | 44680 | 2000 | 2000 | 0.9 | 84.5% | 82.5% | 74.8% | 0.17% |
| 2 | 44680 | 2000 | 2000 | 0.65 | 93.2% | 93.3% | 91.0% | 4.68% |
| 3 | 44680 | 2000 | 2000 | 0.85 | 93.5% | 92.7% | 89.9% | 0.08% |
| 4 | 44680 | 2000 | 2000 | 0.9 | 84.7% | 85.5% | 78.9% | 1.59% |

### `arm_b_finetune@ArmP_companions`

| fold | train n | val n | test n | margin | acc (raw) | acc (ruled) | macro-F1 | null->true |
|---|---|---|---|---|---|---|---|---|
| 0 | 54410 | 2000 | 2000 | 0.0 | 91.5% | 91.5% | 87.6% | 3.17% |
| 1 | 54415 | 2000 | 2000 | 0.9 | 82.3% | 82.1% | 72.9% | 0.00% |
| 2 | 54410 | 2000 | 2000 | 0.55 | 90.0% | 89.8% | 85.9% | 4.68% |
| 3 | 54410 | 2000 | 2000 | 0.25 | 94.7% | 94.7% | 90.9% | 0.17% |
| 4 | 54405 | 2000 | 2000 | 0.9 | 86.8% | 87.9% | 82.2% | 1.17% |

## Limitations

* **Effective n, not n, bounds every number here.** A slice's example count says how much recombination happened. Its effective n -- the number of distinct hand-written fragment clusters behind it -- says how many independent ideas were tested, and that is what the error bar is computed over. Ten thousand examples built from sixty-six fragments is sixty-six ideas seen many times, and quoting the ten thousand is the single easiest way to over-read this report.
* **Fold aggregation buys about a factor of three on the error bar, not a factor of twelve.** Pooling five folds raises the effective n of each hard sub-class from 2-5 clusters to its whole library, 32-47. Uncertainty on a proportion falls as 1/sqrt(n), so roughly +/-30 points becomes roughly +/-8. That is the difference between a number that can carry a conclusion and one that cannot; it is not a twelve-fold improvement in precision.
* **The pooled result carries a small optimism.** Fold i's validation clusters are fold i+1's test clusters, so each fold's margin was selected on a sibling fold's test data. Within any one fold there is no leakage -- each fold trains its own model and never sees its own test bucket -- but the pooled figure is very slightly flattered. Nested cross-validation would remove it and is not worth the cost for one scalar per fold.
* **The across-fold standard deviation is a stability check, not a confidence interval.** Five folds give it four degrees of freedom, so it is itself noisy and will occasionally look reassuringly small for no reason. The headline interval is the pooled cluster bootstrap.
* **McNemar's pairing unit is the example, not the cluster.** It answers "did these two models behave differently on this data", which is narrower than "would they behave differently on new fragments". Where a slice's examples are recombinations of a few clusters it will overstate significance in exactly the way the cluster bootstrap avoids. Read it alongside the interval, never instead of it.
* **Fold mode trains on 60% of clusters, the legacy split on 70%.** Numbers here are therefore not directly comparable to any single-split figure recorded in `arch_training.md` section 10. The fold-aggregated numbers are the honest ones.
* **A slice containing only one class cannot be read on its own.** The five `null` sub-class slices hold nothing but truly-`null` examples, so a model that answers `null` unconditionally scores 100% on all of them. Sub-class recall is a finding only when the `true` and `false` recalls are high at the same time, which is why the per-class table sits beside it.
* **The overall interval is dominated by one resampling unit.** All structural nulls share one unit, by design -- thousands of recombinations of a handful of filler sentences are not thousands of observations. The cost is that the pooled overall accuracy swings widely under resampling for reasons that have nothing to do with the model. The `decisive` slice, which drops them, is the one to read.
* **The real-text holdout cannot rank two models, and is not a smaller version of the tables above.** 67 submissions with no cluster structure give roughly +/-12 points on one overall figure and +/-20 or worse on a per-signal decisive slice. It answers a different question -- does any of this transfer to text a patient actually wrote -- and it answers it in one direction only: a large drop there is conclusive, a small difference between two models there is noise.
* **Fragment libraries, not sample size, are the ceiling.** Forty-seven metaphor clusters is forty-seven ideas however many examples are drawn from them. Everything section 9 of `arch_training.md` says about what this data is and is not worth continues to apply in full.

## What this data is and is not worth

*Reproduced in full from `arch_training.md` sections 9 and 10 rather than cross-
referenced, because this report is read on its own and every number in it is bounded by
what follows.*

* **The validation score is a smoke test, not evidence.** Under the default bands validation holds 15 distinct positive fragments, and every `true` validation example is a recombination of those 15 sentences; one unlucky fragment moves the score several points. The training plan asks for around 200 fragments per signal. We have roughly half that for `true` and for `false` alike.
* **Length may still leak.** Fragment *count* is drawn from one distribution that never sees the label, so it cannot be a proxy for it. Fragment *length* is not controlled at all: `fever_true` fragments run from 3 words to 98, while the `fever_null` libraries sit in a 9-40 word band. The medians are close (16 against 15-19), so this is a tail problem rather than a systematic offset -- but a 98-word positive has no counterpart anywhere in the null libraries, and a model can notice that. The `length_only` baseline in this report is the direct measurement of how much is there to notice.
* **Urgency language leaks too.** About 17% of `fever_true` fragments bundle the fever claim with a justification -- "three important meetings I can't miss" -- against 8% of `fever_false` and almost none of `fever_null`. That is exactly the "sounds urgent, must be positive" shortcut the libraries are meant to prevent. Pairing with filler washes some of it out; fixing it properly is library work.
* **The examples are short.** Two or three sentences by default, against real submissions that are longer and messier. The variable fragment count narrows that gap rather than closing it: the count ceiling is the number of filler libraries, and past a few fragments each example still carries exactly one supervised claim, just buried in more noise. The proof-of-concept run's median example is 36 tokens against a `max_seq_len` of 256, so sequence length is not the constraint and raising it would fix nothing.
* **One signal per dataset, and six signals have libraries.** A generated example carries a label for the run's signal and no other, so nothing here is multi-label. What changed is that the filler libraries are now lint-verified silent about all six signals with libraries -- fever, dysuria, urinary frequency, nocturia, flank pain, haematuria -- rather than about fever alone. They are *not* silent about `recent_uti_present`, the seventh `send_to_encoder` signal, which has no libraries and so no lexicon: `uti_speculation` asserts it outright.
* **The six signals' numbers are not comparable to each other at face value.** Only the `fever_*` and `dysuria_*` confounder libraries are hand-tagged into clusters. The other four signals' libraries treat every line as an independent idea, which flatters their `eff n` and narrows their intervals; `dysuria`, tagged throughout, is penalised for it. The cluster-tag coverage table at the top of this report is the per-run statement of how far that applies here. It does not touch a fever-versus-fever comparison, which is scored on identical, already-tagged fever clusters.

### Effective sample size: count clusters, not examples

The single easiest way to over-read anything this pipeline produces is to quote an example count. **The effective sample size of any evaluation slice is the number of distinct clusters behind it, not the number of examples.** Ten thousand examples built from 66 training fragments is 66 ideas seen many times.

Clusters rather than fragments, because `[c01]`-tagged siblings are one idea written twice. They always land in the same split, so they are one observation and not two -- which means the manual clustering *reduces* effective n where it applies, correctly, because it stopped counting the same idea twice.

Under a single 70/15/15 split a per-sub-class score is computed over **2 to 5 independent ideas**, and all five hard sub-classes together are of that order. A third-party recall figure could then take only the values 0, 0.5 or 1.0, carrying an uncertainty of roughly +/-30 percentage points -- wider than any effect this ticket could plausibly detect. That is a library-size problem, not a splitter problem, and the fix for it is more fragments.

Pooling all five folds is the mitigation and is what this report does: every cluster is a test cluster in exactly one fold, so a sub-class's aggregate test set is its whole library.

| library | fragments | clusters (the effective n) |
|---|---|---|
| `fever_true` | 96 | **96** |
| `fever_false` | 98 | **98** |
| `fever_null_attribution` | 50 | **43** |
| `fever_null_hedged` | 73 | **63** |
| `fever_null_historical` | 45 | **36** |
| `fever_null_metaphor` | 55 | **47** |
| `fever_null_thirdparty` | 46 | **35** |

Note what that is worth and no more. Effective n rises 12- to 17-fold for the hard
sub-classes, but the error bar does **not** shrink 12- to 17-fold: uncertainty on a
proportion goes as 1/sqrt(n), so roughly +/-30 points becomes roughly +/-8. That is the
difference between a number that can carry a conclusion and one that cannot -- a metaphor
recall of 0.6 +/-0.08 is a finding, 0.5 +/-0.30 is noise. Folds create no new ideas, so 47
metaphor clusters is still 47 and everything above applies unchanged.

## The next ticket

* **Write more held-out submissions, and write the ones that are missing.** The 67 in `data/realistic/` exist and are scored above, which closes the previous next-ticket: everything else in this report is a recombination of the same few hundred fragments the models were trained on, and held-out *clusters* remove memorisation and nothing else -- the test examples are still short, still one supervised claim plus filler, still assembled by the same generator in the same register.
* The shortage in the held-out set is **specific rather than general**, and writing another 67 of the same shape would not fix it. What is missing is **explicit denials** -- "no burning", "I'm not going more often than usual", "no waking at night" -- and submissions where the patient turns out not to have a UTI at all. Three signals have no `false` example anywhere in the set, so a model that never predicts `false` is not penalised on them, and explicit denial was the largest error family in the synthetic evaluation.
* **Multi-symptom recombinations** (`arch_training.md` 12.5 and 12.6) are the other half. A generated example carries a label for one signal and no other, so every `null` example for a signal pairs an absence of that signal's language with *bland non-clinical* filler -- and real submissions are dense with clinical language about other symptoms. If "clinical-sounding text implies not-null" is a shortcut the models have taken, the holdout numbers above are where it shows, and joint multi-head training does not fix it because each head is masked on the other signals' examples.

# Encoder training: evaluation report

*Generated 2026-08-19T20:32:31+00:00.*

|  |  |
|---|---|
| signal | `haematuria_present` |
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
| cluster tag coverage | `0 of 5 libraries carry cluster markers; 225 of 225 fragments are in libraries with none` |
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

> **Warning: all 5 libraries behind this run carry no cluster markers at all, so every line in them counts as an independent idea.** Where that is not true -- where several lines are one idea written several ways -- the `eff n` of every slice drawn from those libraries is an **upper bound**, and the confidence intervals below are correspondingly **narrower than the truth**.
>
> Untagged: `haematuria_false`, `haematuria_null_hedged`, `haematuria_null_historical`, `haematuria_null_thirdparty`, `haematuria_true`.

Tagging cannot inflate a number -- `[c01]` siblings are forced into one cluster and one
split, so it only ever *reduces* `eff n`, correctly, by stopping the same idea being
counted twice. The asymmetry is what makes cross-signal comparison unsafe: a fully
tagged signal is penalised for being honest and an untagged one is flattered by default,
so a ranking across signals is partly an artefact of this column.

| library | fragments | tagged | coverage |
|---|---|---|---|
| `haematuria_false` | 45 | 0 | 0.0% |
| `haematuria_null_hedged` | 45 | 0 | 0.0% |
| `haematuria_null_historical` | 45 | 0 | 0.0% |
| `haematuria_null_thirdparty` | 45 | 0 | 0.0% |
| `haematuria_true` | 45 | 0 | 0.0% |

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
| `arm_b_finetune@Arm0_control` | finetune | 7015 | **225** | 95.6% [93.1%, 97.6%] | 95.4% [92.6%, 97.5%] | 96.9% | 96.9% +/- 2.0% |
| `arm_b_finetune@ArmC_remargined` | finetune | 7015 | **225** | 95.9% [93.5%, 97.8%] | 95.8% [93.1%, 97.8%] | 97.1% | 97.1% +/- 2.2% |
| `arm_b_finetune@ArmP_companions` | finetune | 7015 | **225** | 94.0% [90.7%, 96.9%] | 93.9% [90.4%, 96.7%] | 95.7% | 95.6% +/- 2.4% |

### Null sub-class recall, pooled

The table the whole exercise exists for: how often each hard `null` sub-class is correctly
left as `null`. `eff n` here is the sub-class's entire library, which a single split cannot reach.

**Never read this table on its own.** Every example in these slices is truly `null`, so a model
that always answers `null` scores 100% across the row -- as `majority_class` below does. High
null recall is only a finding when the `true` and `false` recalls in the per-class tables are
high too.

| model | adjacent | attribution | hedged | historical | metaphor | third_party |
|---|---|---|---|---|---|---|
| `arm_b_finetune@Arm0_control` | -- | -- | 83.3% [72.2%, 92.4%] (eff n 45) | 98.8% [96.9%, 100.0%] (eff n 45) | -- | 98.2% [94.3%, 100.0%] (eff n 45) |
| `arm_b_finetune@ArmC_remargined` | -- | -- | 84.9% [74.5%, 93.2%] (eff n 45) | 99.2% [97.6%, 100.0%] (eff n 45) | -- | 98.3% [94.6%, 100.0%] (eff n 45) |
| `arm_b_finetune@ArmP_companions` | -- | -- | 86.5% [75.7%, 95.0%] (eff n 45) | 99.3% [98.6%, 99.8%] (eff n 45) | -- | 98.9% [97.9%, 99.7%] (eff n 45) |

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

Recombination test slice: **n 7015**, **eff n 225** clusters, accuracy 95.6% [93.1%, 97.6%]. Holdout: **n 67** submissions, one observation each, scored by 5 fold models at margins {'dysuria_present': 0.15, 'fever_present': 0.9, 'flank_pain_present': 0.85, 'haematuria_present': 0.0, 'nocturia_present': 0.0, 'urinary_frequency_present': 0.25}, {'dysuria_present': 0.0, 'fever_present': 0.85, 'flank_pain_present': 0.0, 'haematuria_present': 0.9, 'nocturia_present': 0.15, 'urinary_frequency_present': 0.9}, {'dysuria_present': 0.75, 'fever_present': 0.0, 'flank_pain_present': 0.85, 'haematuria_present': 0.0, 'nocturia_present': 0.85, 'urinary_frequency_present': 0.05}, {'dysuria_present': 0.0, 'fever_present': 0.85, 'flank_pain_present': 0.0, 'haematuria_present': 0.0, 'nocturia_present': 0.85, 'urinary_frequency_present': 0.9}, {'dysuria_present': 0.2, 'fever_present': 0.4, 'flank_pain_present': 0.8, 'haematuria_present': 0.5, 'nocturia_present': 0.0, 'urinary_frequency_present': 0.9}. The two `n`s are printed together because they are not the same kind of number and the second is far the smaller.

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

Recombination test slice: **n 7015**, **eff n 225** clusters, accuracy 95.9% [93.5%, 97.8%]. Holdout: **n 67** submissions, one observation each, scored by 5 fold models at margins {'dysuria_present': 0.9, 'fever_present': 0.9, 'flank_pain_present': 0.9, 'haematuria_present': 0.9, 'nocturia_present': 0.9, 'urinary_frequency_present': 0.65}, {'dysuria_present': 0.9, 'fever_present': 0.9, 'flank_pain_present': 0.65, 'haematuria_present': 0.9, 'nocturia_present': 0.9, 'urinary_frequency_present': 0.9}, {'dysuria_present': 0.9, 'fever_present': 0.9, 'flank_pain_present': 0.9, 'haematuria_present': 0.9, 'nocturia_present': 0.85, 'urinary_frequency_present': 0.65}, {'dysuria_present': 0.9, 'fever_present': 0.9, 'flank_pain_present': 0.9, 'haematuria_present': 0.85, 'nocturia_present': 0.9, 'urinary_frequency_present': 0.85}, {'dysuria_present': 0.9, 'fever_present': 0.9, 'flank_pain_present': 0.9, 'haematuria_present': 0.9, 'nocturia_present': 0.9, 'urinary_frequency_present': 0.9}. The two `n`s are printed together because they are not the same kind of number and the second is far the smaller.

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

Recombination test slice: **n 7015**, **eff n 225** clusters, accuracy 94.0% [90.7%, 96.9%]. Holdout: **n 67** submissions, one observation each, scored by 5 fold models at margins {'dysuria_present': 0.0, 'fever_present': 0.15, 'flank_pain_present': 0.0, 'haematuria_present': 0.85, 'nocturia_present': 0.0, 'urinary_frequency_present': 0.0}, {'dysuria_present': 0.0, 'fever_present': 0.0, 'flank_pain_present': 0.4, 'haematuria_present': 0.9, 'nocturia_present': 0.75, 'urinary_frequency_present': 0.9}, {'dysuria_present': 0.9, 'fever_present': 0.8, 'flank_pain_present': 0.8, 'haematuria_present': 0.0, 'nocturia_present': 0.0, 'urinary_frequency_present': 0.55}, {'dysuria_present': 0.0, 'fever_present': 0.85, 'flank_pain_present': 0.0, 'haematuria_present': 0.6, 'nocturia_present': 0.05, 'urinary_frequency_present': 0.25}, {'dysuria_present': 0.5, 'fever_present': 0.85, 'flank_pain_present': 0.85, 'haematuria_present': 0.2, 'nocturia_present': 0.75, 'urinary_frequency_present': 0.9}. The two `n`s are printed together because they are not the same kind of number and the second is far the smaller.

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
| 0 | 67 | 1 | 0 | 1 |
| 1 | 67 | 0 | 0 | 1 |
| 2 | 67 | 0 | 0 | 1 |
| 3 | 67 | 0 | 1 | 1 |
| 4 | 67 | 0 | 0 | 1 |

`arm_b_finetune@Arm0_control` ahead on 1 folds, `arm_b_finetune@ArmC_remargined` on 1. `null -> true` mean: 80.4% against 65.7% -- **+14.6 points** in favour of `arm_b_finetune@ArmC_remargined`.

*One test per fold over the same 67 submissions, never concatenated: five folds are five models scored on one sample, and pooling would report a p-value for 335 observations that do not exist.*

### `arm_b_finetune@Arm0_control` against `arm_b_finetune@ArmP_companions`

| fold | pairs | only `arm_b_finetune@Arm0_control` | only `arm_b_finetune@ArmP_companions` | p |
|---|---|---|---|---|
| 0 | 67 | 5 | 47 | 1.28e-09 |
| 1 | 67 | 2 | 48 | 2.27e-12 |
| 2 | 67 | 0 | 43 | 2.27e-13 |
| 3 | 67 | 2 | 48 | 2.27e-12 |
| 4 | 67 | 2 | 43 | 5.89e-11 |

`arm_b_finetune@Arm0_control` ahead on 0 folds, `arm_b_finetune@ArmP_companions` on 5. `null -> true` mean: 80.4% against 12.5% -- **+67.9 points** in favour of `arm_b_finetune@ArmP_companions`.

*One test per fold over the same 67 submissions, never concatenated: five folds are five models scored on one sample, and pooling would report a p-value for 335 observations that do not exist.*

### `arm_b_finetune@ArmC_remargined` against `arm_b_finetune@ArmP_companions`

| fold | pairs | only `arm_b_finetune@ArmC_remargined` | only `arm_b_finetune@ArmP_companions` | p |
|---|---|---|---|---|
| 0 | 67 | 4 | 47 | 2.42e-10 |
| 1 | 67 | 2 | 48 | 2.27e-12 |
| 2 | 67 | 0 | 43 | 2.27e-13 |
| 3 | 67 | 2 | 47 | 4.36e-12 |
| 4 | 67 | 2 | 43 | 5.89e-11 |

`arm_b_finetune@ArmC_remargined` ahead on 0 folds, `arm_b_finetune@ArmP_companions` on 5. `null -> true` mean: 65.7% against 12.5% -- **+53.2 points** in favour of `arm_b_finetune@ArmP_companions`.

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
| `arm_b_finetune@Arm0_control` | finetune | 3000 | **135** | 93.0% [88.6%, 96.6%] |
| `arm_b_finetune@ArmC_remargined` | finetune | 3000 | **135** | 93.7% [89.6%, 97.1%] |
| `arm_b_finetune@ArmP_companions` | finetune | 3000 | **135** | 94.5% [90.6%, 97.6%] |

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

* `arm_b_finetune@Arm0_control`: 309 errors across 22 of 225 decisive fragments. Half of them fall on **6** fragments (an even spread would be 11.0); the worst ten carry 78.3% of all errors.
* `arm_b_finetune@ArmC_remargined`: 288 errors across 22 of 225 decisive fragments. Half of them fall on **6** fragments (an even spread would be 11.0); the worst ten carry 78.5% of all errors.
* `arm_b_finetune@ArmP_companions`: 419 errors across 40 of 225 decisive fragments. Half of them fall on **5** fragments (an even spread would be 20.0); the worst ten carry 79.0% of all errors.

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
| `haematuria_null_hedged` | 1088 | 83.3% | 84.9% | 86.5% | 3.1pp |
| `haematuria_false` | 2395 | 97.1% | 97.4% | 92.8% | 4.6pp |
| `haematuria_true` | 1620 | 98.2% | 97.7% | 94.9% | 3.3pp |
| `haematuria_null_thirdparty` | 963 | 98.2% | 98.3% | 98.9% | 0.7pp |
| `haematuria_null_historical` | 949 | 98.8% | 99.2% | 99.3% | 0.5pp |
| `(none)` | 2985 | 99.9% | 100.0% | 99.5% | 0.5pp |

### By fragment, errors

Ordered by the worst model's error count, so the fragments the comparison is about sort
to the top whichever encoder wins. Counts, not rates: these are the sentences a month of
library work would be spent on. The JSON holds every fragment.

| fragment | library | truth | `arm_b_finetune@Arm0_control` | `arm_b_finetune@ArmC_remargined` | `arm_b_finetune@ArmP_companions` | spread |
|---|---|---|---|---|---|---|
| `haematuria_false:cbd9cec5` | `haematuria_false` | false | 0 | 0 | 66 | 66 |
| `haematuria_false:d163df19` | `haematuria_false` | false | 19 | 19 | 54 | 35 |
| `haematuria_false:cb3cb6e6` | `haematuria_false` | false | 42 | 42 | 32 | 10 |
| `haematuria_null_hedged:ad81f888` | `haematuria_null_hedged` | null | 30 | 18 | 35 | 17 |
| `haematuria_true:16614edd` | `haematuria_true` | true | 0 | 0 | 35 | 35 |
| `haematuria_null_hedged:0a1e23ec` | `haematuria_null_hedged` | null | 32 | 32 | 33 | 1 |
| `haematuria_true:9207612b` | `haematuria_true` | true | 23 | 23 | 20 | 3 |
| `haematuria_null_hedged:58ace8f5` | `haematuria_null_hedged` | null | 21 | 18 | 12 | 9 |
| `haematuria_null_hedged:8524c012` | `haematuria_null_hedged` | null | 21 | 21 | 0 | 21 |
| `haematuria_true:6fadb8bc` | `haematuria_true` | true | 1 | 2 | 20 | 19 |
| `haematuria_null_hedged:e2b503fc` | `haematuria_null_hedged` | null | 19 | 19 | 18 | 1 |
| `haematuria_false:b471d351` | `haematuria_false` | false | 0 | 0 | 18 | 18 |
| `haematuria_null_hedged:dc7c4c42` | `haematuria_null_hedged` | null | 18 | 18 | 17 | 1 |
| `haematuria_null_thirdparty:e1a16c31` | `haematuria_null_thirdparty` | null | 17 | 16 | 3 | 14 |
| `haematuria_null_hedged:740e7688` | `haematuria_null_hedged` | null | 16 | 16 | 16 | 0 |
| `haematuria_null_hedged:f5ac0bee` | `haematuria_null_hedged` | null | 12 | 12 | 0 | 12 |
| `haematuria_null_hedged:b46c1780` | `haematuria_null_hedged` | null | 10 | 10 | 0 | 10 |
| `haematuria_false:eaac464c` | `haematuria_false` | false | 9 | 2 | 1 | 8 |
| `haematuria_null_hedged:64409bb8` | `haematuria_null_hedged` | null | 1 | 0 | 7 | 7 |
| `haematuria_null_historical:8a3575e2` | `haematuria_null_historical` | null | 7 | 7 | 0 | 7 |
| `haematuria_true:6773fb2e` | `haematuria_true` | true | 3 | 6 | 4 | 3 |
| `haematuria_null_historical:7ddf228a` | `haematuria_null_historical` | null | 5 | 1 | 2 | 4 |
| `haematuria_true:a87130d9` | `haematuria_true` | true | 0 | 3 | 0 | 3 |
| `haematuria_null_hedged:15c550d2` | `haematuria_null_hedged` | null | 0 | 0 | 2 | 2 |
| `haematuria_null_hedged:78f072f0` | `haematuria_null_hedged` | null | 0 | 0 | 2 | 2 |
| `haematuria_null_thirdparty:bcf9be7d` | `haematuria_null_thirdparty` | null | 0 | 0 | 2 | 2 |
| `haematuria_null_thirdparty:ca4c6a81` | `haematuria_null_thirdparty` | null | 0 | 0 | 2 | 2 |
| `haematuria_false:0a0b1113` | `haematuria_false` | false | 0 | 0 | 1 | 1 |
| `haematuria_null_hedged:086f7067` | `haematuria_null_hedged` | null | 0 | 0 | 1 | 1 |
| `haematuria_null_hedged:0dd010bf` | `haematuria_null_hedged` | null | 0 | 0 | 1 | 1 |
| `haematuria_null_hedged:429871c9` | `haematuria_null_hedged` | null | 0 | 0 | 1 | 1 |
| `haematuria_null_hedged:4d27f44a` | `haematuria_null_hedged` | null | 0 | 0 | 1 | 1 |
| `haematuria_null_hedged:97ee27ec` | `haematuria_null_hedged` | null | 1 | 0 | 0 | 1 |
| `haematuria_null_hedged:f1a0ec1e` | `haematuria_null_hedged` | null | 0 | 0 | 1 | 1 |
| `haematuria_null_historical:2fcc713c` | `haematuria_null_historical` | null | 0 | 0 | 1 | 1 |
| `haematuria_null_historical:5daf87be` | `haematuria_null_historical` | null | 0 | 0 | 1 | 1 |
| `haematuria_null_historical:5f3f6b5b` | `haematuria_null_historical` | null | 0 | 0 | 1 | 1 |
| `haematuria_null_historical:b891d9a3` | `haematuria_null_historical` | null | 0 | 0 | 1 | 1 |
| `haematuria_null_historical:e01f0d94` | `haematuria_null_historical` | null | 0 | 0 | 1 | 1 |
| `haematuria_null_thirdparty:0ec4495c` | `haematuria_null_thirdparty` | null | 0 | 0 | 1 | 1 |

*8 further fragments erred on at least one model; the JSON holds them all.*

## `arm_b_finetune@Arm0_control`

`roberta-base` with **every layer unfrozen**, mean-pooled, with the same `Linear(768, 3)` head -- 110M trainable parameters against Arm A's 2,307. Three epochs at batch 32, learning rate 2e-5, 10% linear warmup, AdamW, fp32. No gradient checkpointing, no 8-bit optimiser, no LoRA, no gradient accumulation: the full model fits in 12GB with room to spare, so anything that reads like a compute compromise would be a mistake rather than a saving. This is the arm that separates "the fragment libraries are the bottleneck" from "the method is too weak": if a fully fine-tuned encoder still cannot read third-party attribution, tense or metaphor, the limit is in the ideas the libraries contain and the fix is library work, not model work. **Joint multi-head training**: 6 heads sharing one encoder (dysuria_present, fever_present, flank_pain_present, haematuria_present, nocturia_present, urinary_frequency_present). Epoch selection uses DD6's unweighted mean of every head's own validation macro-F1, so this signal's stopping point may differ from a single-signal run's own best epoch. Each head's margin is chosen independently on its own validation split -- no cross-head trade.

Decision-rule margins selected per fold (on each fold's own validation split): 0.0, 0.5, 0.9.

*Confusion matrix, raw argmax*

|  | pred false | pred true | pred null | total |
|---|---|---|---|---|
| **truth false** | 2325 | 47 | 23 | 2395 |
| **truth true** | 3 | 1591 | 26 | 1620 |
| **truth null** | 75 | 145 | 5765 | 5985 |
| **total** | 2403 | 1783 | 5814 | 10000 |

`null -> true`: 145 of 5985 truly-null examples (2.42%).

*Confusion matrix, after the decision rule*

|  | pred false | pred true | pred null | total |
|---|---|---|---|---|
| **truth false** | 2325 | 47 | 23 | 2395 |
| **truth true** | 3 | 1591 | 26 | 1620 |
| **truth null** | 76 | 136 | 5773 | 5985 |
| **total** | 2404 | 1774 | 5822 | 10000 |

`null -> true`: 136 of 5985 truly-null examples (2.27%).

### Per class, after the decision rule

| class | support | predicted | precision | recall | F1 |
|---|---|---|---|---|---|
| `false` | 2395 | 2404 | 96.7% | 97.1% | 96.9% |
| `true` | 1620 | 1774 | 89.7% | 98.2% | 93.8% |
| `null` | 5985 | 5822 | 99.2% | 96.5% | 97.8% |

### By label mode

| label mode | n | eff n | accuracy [95% CI] |
|---|---|---|---|
| false | 2395 | **45** | 97.1% [92.6%, 100.0%] |
| null_ambiguous | 3000 | **135** | 93.0% [88.6%, 96.6%] |
| null_structural | 2985 | **1** | 99.9% [99.9%, 99.9%] |
| true | 1620 | **45** | 98.2% [95.0%, 99.9%] |

### By null sub-class

| sub-class | n | eff n | null recall [95% CI] |
|---|---|---|---|
| hedged | 1087 | **45** | 83.3% [72.2%, 92.4%] |
| historical | 966 | **45** | 98.8% [96.9%, 100.0%] |
| third_party | 947 | **45** | 98.2% [94.3%, 100.0%] |

### By fragment library

| library | n | eff n | accuracy [95% CI] |
|---|---|---|---|
| haematuria_false | 2395 | **45** | 97.1% [92.6%, 100.0%] |
| haematuria_null_hedged | 1087 | **45** | 83.3% [72.2%, 92.4%] |
| haematuria_null_historical | 966 | **45** | 98.8% [96.9%, 100.0%] |
| haematuria_null_thirdparty | 947 | **45** | 98.2% [94.3%, 100.0%] |
| haematuria_true | 1620 | **45** | 98.2% [95.0%, 99.9%] |
| (none) | 2985 | **1** | 99.9% [99.9%, 99.9%] |

### Per-fragment errors (worst first)

Whether errors are spread thinly across many fragments or piled onto a few is the difference
between "the method is too weak" (model work) and "these specific ideas are not learnable from
the data we have" (library work, and these are the fragments to write more of). No intervals:
a fragment is one cluster, so an interval over its own examples measures nothing.

22 of 225 decisive fragments were got wrong at least once.

`arm_b_finetune@Arm0_control`: 309 errors across 22 of 225 decisive fragments. Half of them fall on **6** fragments (an even spread would be 11.0); the worst ten carry 78.3% of all errors.

| fragment | library | sub-class | truth | correct | accuracy | predicted as |
|---|---|---|---|---|---|---|
| `haematuria_false:cb3cb6e6` | `haematuria_false` | -- | false | 0/42 | 0.0% | true 38, null 4 |
| `haematuria_null_hedged:0a1e23ec` | `haematuria_null_hedged` | hedged | null | 0/32 | 0.0% | true 32 |
| `haematuria_true:9207612b` | `haematuria_true` | -- | true | 0/23 | 0.0% | null 23 |
| `haematuria_null_hedged:8524c012` | `haematuria_null_hedged` | hedged | null | 0/21 | 0.0% | false 21 |
| `haematuria_null_hedged:e2b503fc` | `haematuria_null_hedged` | hedged | null | 0/19 | 0.0% | true 19 |
| `haematuria_null_hedged:dc7c4c42` | `haematuria_null_hedged` | hedged | null | 0/18 | 0.0% | false 18 |
| `haematuria_null_hedged:740e7688` | `haematuria_null_hedged` | hedged | null | 0/16 | 0.0% | false 16 |
| `haematuria_null_hedged:58ace8f5` | `haematuria_null_hedged` | hedged | null | 1/22 | 4.5% | true 21, null 1 |
| `haematuria_null_hedged:ad81f888` | `haematuria_null_hedged` | hedged | null | 5/35 | 14.3% | true 30, null 5 |
| `haematuria_null_thirdparty:e1a16c31` | `haematuria_null_thirdparty` | third_party | null | 4/21 | 19.0% | true 17, null 4 |
| `haematuria_null_hedged:f5ac0bee` | `haematuria_null_hedged` | hedged | null | 7/19 | 36.8% | false 12, null 7 |
| `haematuria_null_hedged:b46c1780` | `haematuria_null_hedged` | hedged | null | 9/19 | 47.4% | false 2, true 8, null 9 |
| `haematuria_false:d163df19` | `haematuria_false` | -- | false | 31/50 | 62.0% | false 31, null 19 |
| `haematuria_null_historical:8a3575e2` | `haematuria_null_historical` | historical | null | 14/21 | 66.7% | false 7, null 14 |
| `haematuria_false:eaac464c` | `haematuria_false` | -- | false | 32/41 | 78.0% | false 32, true 9 |
| `haematuria_null_historical:7ddf228a` | `haematuria_null_historical` | historical | null | 20/25 | 80.0% | true 5, null 20 |
| `haematuria_true:6773fb2e` | `haematuria_true` | -- | true | 24/27 | 88.9% | false 3, true 24 |
| `haematuria_true:e34024ba` | `haematuria_true` | -- | true | 18/19 | 94.7% | true 18, null 1 |
| `haematuria_null_hedged:64409bb8` | `haematuria_null_hedged` | hedged | null | 23/24 | 95.8% | true 1, null 23 |
| `haematuria_true:08f72e8e` | `haematuria_true` | -- | true | 24/25 | 96.0% | true 24, null 1 |
| `haematuria_null_hedged:97ee27ec` | `haematuria_null_hedged` | hedged | null | 27/28 | 96.4% | true 1, null 27 |
| `haematuria_true:6fadb8bc` | `haematuria_true` | -- | true | 66/67 | 98.5% | true 66, null 1 |

## `arm_b_finetune@ArmC_remargined`

`roberta-base` with **every layer unfrozen**, mean-pooled, with the same `Linear(768, 3)` head -- 110M trainable parameters against Arm A's 2,307. Three epochs at batch 32, learning rate 2e-5, 10% linear warmup, AdamW, fp32. No gradient checkpointing, no 8-bit optimiser, no LoRA, no gradient accumulation: the full model fits in 12GB with room to spare, so anything that reads like a compute compromise would be a mistake rather than a saving. This is the arm that separates "the fragment libraries are the bottleneck" from "the method is too weak": if a fully fine-tuned encoder still cannot read third-party attribution, tense or metaphor, the limit is in the ideas the libraries contain and the fix is library work, not model work. **Margin re-selected, not retrained**: these are the trained heads of the arm above, with every head's decision margin chosen on `ArmP_companions`'s validation split instead of their own. Identical weights, identical raw argmax scores, identical test examples -- the only difference is the threshold, so a gap between this arm and the one it came from is margin selection alone.

Decision-rule margins selected per fold (on each fold's own validation split): 0.85, 0.9.

*Confusion matrix, raw argmax*

|  | pred false | pred true | pred null | total |
|---|---|---|---|---|
| **truth false** | 2325 | 47 | 23 | 2395 |
| **truth true** | 3 | 1591 | 26 | 1620 |
| **truth null** | 75 | 145 | 5765 | 5985 |
| **total** | 2403 | 1783 | 5814 | 10000 |

`null -> true`: 145 of 5985 truly-null examples (2.42%).

*Confusion matrix, after the decision rule*

|  | pred false | pred true | pred null | total |
|---|---|---|---|---|
| **truth false** | 2332 | 37 | 26 | 2395 |
| **truth true** | 6 | 1583 | 31 | 1620 |
| **truth null** | 76 | 112 | 5797 | 5985 |
| **total** | 2414 | 1732 | 5854 | 10000 |

`null -> true`: 112 of 5985 truly-null examples (1.87%).

### Per class, after the decision rule

| class | support | predicted | precision | recall | F1 |
|---|---|---|---|---|---|
| `false` | 2395 | 2414 | 96.6% | 97.4% | 97.0% |
| `true` | 1620 | 1732 | 91.4% | 97.7% | 94.5% |
| `null` | 5985 | 5854 | 99.0% | 96.9% | 97.9% |

### By label mode

| label mode | n | eff n | accuracy [95% CI] |
|---|---|---|---|
| false | 2395 | **45** | 97.4% [93.0%, 100.0%] |
| null_ambiguous | 3000 | **135** | 93.7% [89.6%, 97.1%] |
| null_structural | 2985 | **1** | 100.0% [100.0%, 100.0%] |
| true | 1620 | **45** | 97.7% [94.3%, 99.7%] |

### By null sub-class

| sub-class | n | eff n | null recall [95% CI] |
|---|---|---|---|
| hedged | 1087 | **45** | 84.9% [74.5%, 93.2%] |
| historical | 966 | **45** | 99.2% [97.6%, 100.0%] |
| third_party | 947 | **45** | 98.3% [94.6%, 100.0%] |

### By fragment library

| library | n | eff n | accuracy [95% CI] |
|---|---|---|---|
| haematuria_false | 2395 | **45** | 97.4% [93.0%, 100.0%] |
| haematuria_null_hedged | 1087 | **45** | 84.9% [74.5%, 93.2%] |
| haematuria_null_historical | 966 | **45** | 99.2% [97.6%, 100.0%] |
| haematuria_null_thirdparty | 947 | **45** | 98.3% [94.6%, 100.0%] |
| haematuria_true | 1620 | **45** | 97.7% [94.3%, 99.7%] |
| (none) | 2985 | **1** | 100.0% [100.0%, 100.0%] |

### Per-fragment errors (worst first)

Whether errors are spread thinly across many fragments or piled onto a few is the difference
between "the method is too weak" (model work) and "these specific ideas are not learnable from
the data we have" (library work, and these are the fragments to write more of). No intervals:
a fragment is one cluster, so an interval over its own examples measures nothing.

22 of 225 decisive fragments were got wrong at least once.

`arm_b_finetune@ArmC_remargined`: 288 errors across 22 of 225 decisive fragments. Half of them fall on **6** fragments (an even spread would be 11.0); the worst ten carry 78.5% of all errors.

| fragment | library | sub-class | truth | correct | accuracy | predicted as |
|---|---|---|---|---|---|---|
| `haematuria_false:cb3cb6e6` | `haematuria_false` | -- | false | 0/42 | 0.0% | true 35, null 7 |
| `haematuria_null_hedged:0a1e23ec` | `haematuria_null_hedged` | hedged | null | 0/32 | 0.0% | true 32 |
| `haematuria_true:9207612b` | `haematuria_true` | -- | true | 0/23 | 0.0% | null 23 |
| `haematuria_null_hedged:8524c012` | `haematuria_null_hedged` | hedged | null | 0/21 | 0.0% | false 21 |
| `haematuria_null_hedged:e2b503fc` | `haematuria_null_hedged` | hedged | null | 0/19 | 0.0% | true 19 |
| `haematuria_null_hedged:dc7c4c42` | `haematuria_null_hedged` | hedged | null | 0/18 | 0.0% | false 18 |
| `haematuria_null_hedged:740e7688` | `haematuria_null_hedged` | hedged | null | 0/16 | 0.0% | false 16 |
| `haematuria_null_hedged:58ace8f5` | `haematuria_null_hedged` | hedged | null | 4/22 | 18.2% | true 18, null 4 |
| `haematuria_null_thirdparty:e1a16c31` | `haematuria_null_thirdparty` | third_party | null | 5/21 | 23.8% | true 16, null 5 |
| `haematuria_null_hedged:f5ac0bee` | `haematuria_null_hedged` | hedged | null | 7/19 | 36.8% | false 12, null 7 |
| `haematuria_null_hedged:b46c1780` | `haematuria_null_hedged` | hedged | null | 9/19 | 47.4% | false 2, true 8, null 9 |
| `haematuria_null_hedged:ad81f888` | `haematuria_null_hedged` | hedged | null | 17/35 | 48.6% | true 18, null 17 |
| `haematuria_false:d163df19` | `haematuria_false` | -- | false | 31/50 | 62.0% | false 31, null 19 |
| `haematuria_null_historical:8a3575e2` | `haematuria_null_historical` | historical | null | 14/21 | 66.7% | false 7, null 14 |
| `haematuria_true:6773fb2e` | `haematuria_true` | -- | true | 21/27 | 77.8% | false 6, true 21 |
| `haematuria_true:a87130d9` | `haematuria_true` | -- | true | 29/32 | 90.6% | true 29, null 3 |
| `haematuria_true:e34024ba` | `haematuria_true` | -- | true | 18/19 | 94.7% | true 18, null 1 |
| `haematuria_false:eaac464c` | `haematuria_false` | -- | false | 39/41 | 95.1% | false 39, true 2 |
| `haematuria_null_historical:7ddf228a` | `haematuria_null_historical` | historical | null | 24/25 | 96.0% | true 1, null 24 |
| `haematuria_true:08f72e8e` | `haematuria_true` | -- | true | 24/25 | 96.0% | true 24, null 1 |
| `haematuria_true:6fadb8bc` | `haematuria_true` | -- | true | 65/67 | 97.0% | true 65, null 2 |
| `haematuria_true:972bb99b` | `haematuria_true` | -- | true | 60/61 | 98.4% | true 60, null 1 |

## `arm_b_finetune@ArmP_companions`

`roberta-base` with **every layer unfrozen**, mean-pooled, with the same `Linear(768, 3)` head -- 110M trainable parameters against Arm A's 2,307. Three epochs at batch 32, learning rate 2e-5, 10% linear warmup, AdamW, fp32. No gradient checkpointing, no 8-bit optimiser, no LoRA, no gradient accumulation: the full model fits in 12GB with room to spare, so anything that reads like a compute compromise would be a mistake rather than a saving. This is the arm that separates "the fragment libraries are the bottleneck" from "the method is too weak": if a fully fine-tuned encoder still cannot read third-party attribution, tense or metaphor, the limit is in the ideas the libraries contain and the fix is library work, not model work. **Joint multi-head training**: 6 heads sharing one encoder (dysuria_present, fever_present, flank_pain_present, haematuria_present, nocturia_present, urinary_frequency_present). Epoch selection uses DD6's unweighted mean of every head's own validation macro-F1, so this signal's stopping point may differ from a single-signal run's own best epoch. Each head's margin is chosen independently on its own validation split -- no cross-head trade.

Decision-rule margins selected per fold (on each fold's own validation split): 0.0, 0.2, 0.6, 0.85, 0.9.

*Confusion matrix, raw argmax*

|  | pred false | pred true | pred null | total |
|---|---|---|---|---|
| **truth false** | 2219 | 55 | 121 | 2395 |
| **truth true** | 4 | 1555 | 61 | 1620 |
| **truth null** | 45 | 152 | 5788 | 5985 |
| **total** | 2268 | 1762 | 5970 | 10000 |

`null -> true`: 152 of 5985 truly-null examples (2.54%).

*Confusion matrix, after the decision rule*

|  | pred false | pred true | pred null | total |
|---|---|---|---|---|
| **truth false** | 2223 | 51 | 121 | 2395 |
| **truth true** | 7 | 1538 | 75 | 1620 |
| **truth null** | 46 | 135 | 5804 | 5985 |
| **total** | 2276 | 1724 | 6000 | 10000 |

`null -> true`: 135 of 5985 truly-null examples (2.26%).

### Per class, after the decision rule

| class | support | predicted | precision | recall | F1 |
|---|---|---|---|---|---|
| `false` | 2395 | 2276 | 97.7% | 92.8% | 95.2% |
| `true` | 1620 | 1724 | 89.2% | 94.9% | 92.0% |
| `null` | 5985 | 6000 | 96.7% | 97.0% | 96.9% |

### By label mode

| label mode | n | eff n | accuracy [95% CI] |
|---|---|---|---|
| false | 2395 | **45** | 92.8% [85.3%, 99.1%] |
| null_ambiguous | 3000 | **135** | 94.5% [90.6%, 97.6%] |
| null_structural | 2985 | **1** | 99.5% [99.5%, 99.5%] |
| true | 1620 | **45** | 94.9% [89.0%, 99.5%] |

### By null sub-class

| sub-class | n | eff n | null recall [95% CI] |
|---|---|---|---|
| hedged | 1088 | **45** | 86.5% [75.7%, 95.0%] |
| historical | 949 | **45** | 99.3% [98.6%, 99.8%] |
| third_party | 963 | **45** | 98.9% [97.9%, 99.7%] |

### By fragment library

| library | n | eff n | accuracy [95% CI] |
|---|---|---|---|
| haematuria_false | 2395 | **45** | 92.8% [85.3%, 99.1%] |
| haematuria_null_hedged | 1088 | **45** | 86.5% [75.7%, 95.0%] |
| haematuria_null_historical | 949 | **45** | 99.3% [98.6%, 99.8%] |
| haematuria_null_thirdparty | 963 | **45** | 98.9% [97.9%, 99.7%] |
| haematuria_true | 1620 | **45** | 94.9% [89.0%, 99.5%] |
| (none) | 2985 | **1** | 99.5% [99.5%, 99.5%] |

### Per-fragment errors (worst first)

Whether errors are spread thinly across many fragments or piled onto a few is the difference
between "the method is too weak" (model work) and "these specific ideas are not learnable from
the data we have" (library work, and these are the fragments to write more of). No intervals:
a fragment is one cluster, so an interval over its own examples measures nothing.

40 of 225 decisive fragments were got wrong at least once.

`arm_b_finetune@ArmP_companions`: 419 errors across 40 of 225 decisive fragments. Half of them fall on **5** fragments (an even spread would be 20.0); the worst ten carry 79.0% of all errors.

| fragment | library | sub-class | truth | correct | accuracy | predicted as |
|---|---|---|---|---|---|---|
| `haematuria_false:d163df19` | `haematuria_false` | -- | false | 0/54 | 0.0% | null 54 |
| `haematuria_null_hedged:ad81f888` | `haematuria_null_hedged` | hedged | null | 0/35 | 0.0% | true 35 |
| `haematuria_null_hedged:0a1e23ec` | `haematuria_null_hedged` | hedged | null | 0/33 | 0.0% | true 33 |
| `haematuria_null_hedged:dc7c4c42` | `haematuria_null_hedged` | hedged | null | 0/17 | 0.0% | false 17 |
| `haematuria_null_hedged:740e7688` | `haematuria_null_hedged` | hedged | null | 0/16 | 0.0% | false 16 |
| `haematuria_null_hedged:e2b503fc` | `haematuria_null_hedged` | hedged | null | 1/19 | 5.3% | true 18, null 1 |
| `haematuria_true:9207612b` | `haematuria_true` | -- | true | 2/22 | 9.1% | true 2, null 20 |
| `haematuria_false:cbd9cec5` | `haematuria_false` | -- | false | 7/73 | 9.6% | false 7, null 66 |
| `haematuria_true:16614edd` | `haematuria_true` | -- | true | 6/41 | 14.6% | true 6, null 35 |
| `haematuria_false:cb3cb6e6` | `haematuria_false` | -- | false | 9/41 | 22.0% | false 9, true 32 |
| `haematuria_null_hedged:58ace8f5` | `haematuria_null_hedged` | hedged | null | 10/22 | 45.5% | true 12, null 10 |
| `haematuria_false:b471d351` | `haematuria_false` | -- | false | 18/36 | 50.0% | false 18, true 18 |
| `haematuria_null_hedged:64409bb8` | `haematuria_null_hedged` | hedged | null | 16/23 | 69.6% | true 7, null 16 |
| `haematuria_true:6fadb8bc` | `haematuria_true` | -- | true | 46/66 | 69.7% | true 46, null 20 |
| `haematuria_true:6773fb2e` | `haematuria_true` | -- | true | 24/28 | 85.7% | false 4, true 24 |
| `haematuria_null_thirdparty:e1a16c31` | `haematuria_null_thirdparty` | third_party | null | 19/22 | 86.4% | true 3, null 19 |
| `haematuria_null_hedged:15c550d2` | `haematuria_null_hedged` | hedged | null | 21/23 | 91.3% | true 2, null 21 |
| `haematuria_null_historical:7ddf228a` | `haematuria_null_historical` | historical | null | 22/24 | 91.7% | true 2, null 22 |
| `haematuria_null_historical:2fcc713c` | `haematuria_null_historical` | historical | null | 13/14 | 92.9% | false 1, null 13 |
| `haematuria_null_hedged:78f072f0` | `haematuria_null_hedged` | hedged | null | 27/29 | 93.1% | false 1, true 1, null 27 |
| `haematuria_null_hedged:f1a0ec1e` | `haematuria_null_hedged` | hedged | null | 15/16 | 93.8% | false 1, null 15 |
| `haematuria_null_thirdparty:ca4c6a81` | `haematuria_null_thirdparty` | third_party | null | 31/33 | 93.9% | true 2, null 31 |
| `haematuria_null_hedged:4d27f44a` | `haematuria_null_hedged` | hedged | null | 16/17 | 94.1% | true 1, null 16 |
| `haematuria_null_historical:b891d9a3` | `haematuria_null_historical` | historical | null | 16/17 | 94.1% | true 1, null 16 |
| `haematuria_null_thirdparty:bcf9be7d` | `haematuria_null_thirdparty` | third_party | null | 33/35 | 94.3% | true 2, null 33 |
| `haematuria_null_historical:5f3f6b5b` | `haematuria_null_historical` | historical | null | 18/19 | 94.7% | false 1, null 18 |
| `haematuria_null_hedged:429871c9` | `haematuria_null_hedged` | hedged | null | 19/20 | 95.0% | true 1, null 19 |
| `haematuria_null_thirdparty:0ec4495c` | `haematuria_null_thirdparty` | third_party | null | 20/21 | 95.2% | true 1, null 20 |
| `haematuria_null_hedged:0dd010bf` | `haematuria_null_hedged` | hedged | null | 21/22 | 95.5% | true 1, null 21 |
| `haematuria_null_thirdparty:9cb5c60c` | `haematuria_null_thirdparty` | third_party | null | 23/24 | 95.8% | true 1, null 23 |
| `haematuria_null_historical:5daf87be` | `haematuria_null_historical` | historical | null | 27/28 | 96.4% | false 1, null 27 |
| `haematuria_null_historical:e01f0d94` | `haematuria_null_historical` | historical | null | 27/28 | 96.4% | false 1, null 27 |
| `haematuria_null_thirdparty:d5666834` | `haematuria_null_thirdparty` | third_party | null | 27/28 | 96.4% | false 1, null 27 |
| `haematuria_null_thirdparty:928fa29c` | `haematuria_null_thirdparty` | third_party | null | 29/30 | 96.7% | true 1, null 29 |
| `haematuria_null_hedged:086f7067` | `haematuria_null_hedged` | hedged | null | 35/36 | 97.2% | true 1, null 35 |
| `haematuria_false:eaac464c` | `haematuria_false` | -- | false | 37/38 | 97.4% | false 37, true 1 |
| `haematuria_true:f2e49699` | `haematuria_true` | -- | true | 51/52 | 98.1% | false 1, true 51 |
| `haematuria_false:0a0b1113` | `haematuria_false` | -- | false | 58/59 | 98.3% | false 58, null 1 |
| `haematuria_true:972bb99b` | `haematuria_true` | -- | true | 60/61 | 98.4% | false 1, true 60 |
| `haematuria_true:c0ff5eed` | `haematuria_true` | -- | true | 65/66 | 98.5% | false 1, true 65 |

## Appendix: per-fold numbers

Point estimates only. A single fold's test slice holds 2-5 clusters per hard sub-class, which
is the whole reason the headline is pooled.

### `arm_b_finetune@Arm0_control`

| fold | train n | val n | test n | margin | acc (raw) | acc (ruled) | macro-F1 | null->true |
|---|---|---|---|---|---|---|---|---|
| 0 | 44680 | 2000 | 2000 | 0.0 | 95.3% | 95.3% | 94.4% | 6.02% |
| 1 | 44680 | 2000 | 2000 | 0.9 | 94.6% | 94.8% | 94.7% | 2.26% |
| 2 | 44680 | 2000 | 2000 | 0.0 | 97.8% | 97.8% | 97.0% | 3.01% |
| 3 | 44680 | 2000 | 2000 | 0.0 | 96.7% | 96.7% | 94.9% | 0.00% |
| 4 | 44680 | 2000 | 2000 | 0.5 | 99.8% | 99.9% | 99.9% | 0.08% |

### `arm_b_finetune@ArmC_remargined`

| fold | train n | val n | test n | margin | acc (raw) | acc (ruled) | macro-F1 | null->true |
|---|---|---|---|---|---|---|---|---|
| 0 | 44680 | 2000 | 2000 | 0.9 | 95.3% | 95.3% | 94.3% | 5.51% |
| 1 | 44680 | 2000 | 2000 | 0.9 | 94.6% | 94.8% | 94.7% | 2.26% |
| 2 | 44680 | 2000 | 2000 | 0.9 | 97.8% | 98.9% | 98.6% | 1.59% |
| 3 | 44680 | 2000 | 2000 | 0.85 | 96.7% | 96.7% | 95.0% | 0.00% |
| 4 | 44680 | 2000 | 2000 | 0.9 | 99.8% | 99.9% | 99.9% | 0.00% |

### `arm_b_finetune@ArmP_companions`

| fold | train n | val n | test n | margin | acc (raw) | acc (ruled) | macro-F1 | null->true |
|---|---|---|---|---|---|---|---|---|
| 0 | 54410 | 2000 | 2000 | 0.85 | 93.6% | 94.1% | 93.2% | 5.01% |
| 1 | 54415 | 2000 | 2000 | 0.9 | 92.8% | 92.3% | 91.5% | 1.59% |
| 2 | 54410 | 2000 | 2000 | 0.0 | 96.7% | 96.7% | 95.5% | 3.17% |
| 3 | 54410 | 2000 | 2000 | 0.6 | 96.7% | 96.9% | 95.4% | 0.50% |
| 4 | 54405 | 2000 | 2000 | 0.2 | 98.4% | 98.3% | 97.8% | 1.00% |

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

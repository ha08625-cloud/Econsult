# Encoder training: evaluation report

*Generated 2026-09-02T15:56:00+00:00.*

|  |  |
|---|---|
| signal | `flank_pain_present` |
| folds | `5` |
| generator version | `4` |
| generator base seed | `42` |
| generator seed rule | `base + 100 * fold + {train: 0, val: 1, test: 2}` |
| split salt | `0` |
| dataset dir | `data/synthetic/generated/decl/c0.0-d0.0` |
| ruleset | `data/uti1.json` |
| ruleset hash | `325b33068307bc70ca085b27117a90c2ad9e71fac24a80f77c8107d08049bb9f` |
| examples per fold | `train 10000, val 2000, test 2000` |
| shuffle seed | `7` |
| report | `declarative sweep, 4 cells` |
| cells | `c0.0-d0.0, c0.0-d0.3, c0.5-d0.0, c0.5-d0.3` |
| reference cell | `data/synthetic/generated/decl/c0.0-d0.0` |
| selected epochs | `c0.0-d0.0 1, 1, 1, 2, 2, c0.0-d0.3 1, 3, 3, 2, 3, c0.5-d0.0 2, 1, 2, 3, 2, c0.5-d0.3 2, 2, 1, 2, 3` |
| arm | `arm_b_finetune` |
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
| trainable | `all layers unfrozen in every cell` |
| holdout | `data/realistic/uti1_holdout.labels.tsv -- 67 real submissions, scored after test, selects nothing` |
| negative control | `not run (--control is off)` |
| artefacts | `models/encoder-decl/comparison` |
| model revision | `e2da8e2f811d1448a5b465c236feacd80ffbac7b` |
| revision pinned | `False` |
| tokeniser lowercases | `False` |
| tokeniser vocab size | `50265` |
| tokeniser discards casing | `False` |
| cluster tag coverage | `1 of 6 libraries carry cluster markers; 243 of 695 fragments are in libraries with none` |
| bootstrap | `2000 resamples over clusters, alpha=0.05, seed=0` |

**arms**

* **c0.0-d0.0** (`data/synthetic/generated/decl/c0.0-d0.0`): 10000 examples per epoch, **10000** labelled positions for `flank_pain_present`
* **c0.0-d0.3** (`data/synthetic/generated/decl/c0.0-d0.3`): 10000 examples per epoch, **10000** labelled positions for `flank_pain_present`
* **c0.5-d0.0** (`data/synthetic/generated/decl/c0.5-d0.0`): 10000 examples per epoch, **10000** labelled positions for `flank_pain_present`
* **c0.5-d0.3** (`data/synthetic/generated/decl/c0.5-d0.3`): 10000 examples per epoch, **10000** labelled positions for `flank_pain_present`

**paired comparison**

none. Every cell holds different texts, so all McNemar rows are recorded as skipped; the real-text holdout is the shared instrument

**predictions**

* The invented-symptom rate on real text improves, most for the signals with the most inventory phrases and least for flank_pain_present.
* `false` recall improves most: explicit denials are 13% of the real set and 'but not X' is the construction patients use for them.
* A cell at declarative 0.6 scores worse on real text than one at 0.3, because the frame becomes the typical decisive sentence. If 0.6 wins, DD8's argument is wrong.
* Against a companion cell rather than against the all-zero control, the gain is smaller than it looks: companions already move null -> true from 84.1% to 4.5% on fever_present by themselves.

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

> **Warning: 5 of the 6 libraries behind this run carry no cluster markers at all, so every line in them counts as an independent idea.** Where that is not true -- where several lines are one idea written several ways -- the `eff n` of every slice drawn from those libraries is an **upper bound**, and the confidence intervals below are correspondingly **narrower than the truth**.
>
> Untagged: `flank_pain_false`, `flank_pain_null_hedged`, `flank_pain_null_historical`, `flank_pain_null_thirdparty`, `flank_pain_true`.

Tagging cannot inflate a number -- `[c01]` siblings are forced into one cluster and one
split, so it only ever *reduces* `eff n`, correctly, by stopping the same idea being
counted twice. The asymmetry is what makes cross-signal comparison unsafe: a fully
tagged signal is penalised for being honest and an untagged one is flattered by default,
so a ranking across signals is partly an artefact of this column.

| library | fragments | tagged | coverage |
|---|---|---|---|
| `flank_pain_false` | 55 | 0 | 0.0% |
| `flank_pain_null_hedged` | 53 | 0 | 0.0% |
| `flank_pain_null_historical` | 40 | 0 | 0.0% |
| `flank_pain_null_thirdparty` | 47 | 0 | 0.0% |
| `flank_pain_true` | 48 | 0 | 0.0% |
| `declarative_v1` | 452 | 452 | 100.0% |

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
| `majority_class` | baseline | 7022 | **243** | 43.6% [37.2%, 50.3%] | 20.2% [18.1%, 22.3%] | 60.4% | 60.4% +/- 0.2% |
| `length_only` | baseline | 7022 | **243** | 43.6% [37.2%, 50.3%] | 20.2% [18.1%, 22.3%] | 60.4% | 60.4% +/- 0.2% |
| `tfidf_logreg` | baseline | 7022 | **243** | 72.3% [67.1%, 77.6%] | 70.0% [64.1%, 75.7%] | 80.5% | 80.5% +/- 2.2% |
| `length_only__shuffled` | negative control | 7022 | **243** | 43.6% [37.2%, 50.3%] | 20.2% [18.1%, 22.3%] | 60.4% | 60.4% +/- 0.2% |
| `tfidf_logreg__shuffled` | negative control | 7022 | **243** | 43.6% [37.2%, 50.3%] | 20.2% [18.1%, 22.3%] | 60.4% | 60.4% +/- 0.2% |
| `arm_b_finetune@c0.0-d0.0` | finetune | 7022 | **243** | 94.9% [92.1%, 97.3%] | 94.7% [91.8%, 97.1%] | 96.4% | 96.4% +/- 1.5% |
| `arm_b_finetune@c0.0-d0.3` | finetune | 7022 | **400** | 97.5% [95.8%, 99.0%] | 97.5% [95.9%, 98.9%] | 98.2% | 98.2% +/- 0.7% |
| `arm_b_finetune@c0.5-d0.0` | finetune | 7022 | **243** | 92.1% [88.4%, 95.3%] | 92.1% [88.5%, 95.2%] | 94.3% | 94.3% +/- 3.4% |
| `arm_b_finetune@c0.5-d0.3` | finetune | 7022 | **400** | 94.3% [91.8%, 96.7%] | 94.1% [91.5%, 96.5%] | 95.9% | 95.9% +/- 2.0% |

### Null sub-class recall, pooled

The table the whole exercise exists for: how often each hard `null` sub-class is correctly
left as `null`. `eff n` here is the sub-class's entire library, which a single split cannot reach.

**Never read this table on its own.** Every example in these slices is truly `null`, so a model
that always answers `null` scores 100% across the row -- as `majority_class` below does. High
null recall is only a finding when the `true` and `false` recalls in the per-class tables are
high too.

| model | adjacent | attribution | hedged | historical | metaphor | third_party |
|---|---|---|---|---|---|---|
| `majority_class` | -- | -- | 100.0% [100.0%, 100.0%] (eff n 53) | 100.0% [100.0%, 100.0%] (eff n 40) | -- | 100.0% [100.0%, 100.0%] (eff n 47) |
| `length_only` | -- | -- | 100.0% [100.0%, 100.0%] (eff n 53) | 100.0% [100.0%, 100.0%] (eff n 40) | -- | 100.0% [100.0%, 100.0%] (eff n 47) |
| `tfidf_logreg` | -- | -- | 88.8% [81.8%, 94.8%] (eff n 53) | 91.4% [84.2%, 97.5%] (eff n 40) | -- | 95.5% [90.6%, 99.1%] (eff n 47) |
| `length_only__shuffled` | -- | -- | 100.0% [100.0%, 100.0%] (eff n 53) | 100.0% [100.0%, 100.0%] (eff n 40) | -- | 100.0% [100.0%, 100.0%] (eff n 47) |
| `tfidf_logreg__shuffled` | -- | -- | 99.9% [99.7%, 100.0%] (eff n 53) | 100.0% [100.0%, 100.0%] (eff n 40) | -- | 100.0% [100.0%, 100.0%] (eff n 47) |
| `arm_b_finetune@c0.0-d0.0` | -- | -- | 89.3% [80.8%, 96.4%] (eff n 53) | 93.1% [85.2%, 100.0%] (eff n 40) | -- | 99.3% [97.9%, 100.0%] (eff n 47) |
| `arm_b_finetune@c0.0-d0.3` | -- | -- | 94.1% [88.1%, 98.6%] (eff n 53) | 99.4% [98.2%, 100.0%] (eff n 40) | -- | 99.3% [98.2%, 100.0%] (eff n 47) |
| `arm_b_finetune@c0.5-d0.0` | -- | -- | 90.0% [81.3%, 97.0%] (eff n 53) | 99.8% [99.4%, 100.0%] (eff n 40) | -- | 95.5% [90.2%, 99.3%] (eff n 47) |
| `arm_b_finetune@c0.5-d0.3` | -- | -- | 86.8% [78.3%, 94.2%] (eff n 53) | 97.7% [93.8%, 99.8%] (eff n 40) | -- | 99.5% [98.9%, 100.0%] (eff n 47) |

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

Not scored, because no head exists for them: `dysuria_present`, `urinary_frequency_present`, `nocturia_present`, `fever_present`, `haematuria_present`, `recent_uti_present`.

### `null -> true` on real text -- the headline

How often each model answers `true` about a signal the submission never mentioned, as
the mean across folds of that fold's own rate. Every other number in this section is
read against this one: a model can post a respectable overall figure here purely by
answering `null` everywhere, and it can post a respectable *decisive* figure while still
inventing symptoms into most of the submissions that never raised them.

| signal | null support | `arm_b_finetune@c0.0-d0.0` | `arm_b_finetune@c0.0-d0.3` | `arm_b_finetune@c0.5-d0.0` | `arm_b_finetune@c0.5-d0.3` |
|---|---|---|---|---|---|
| `flank_pain_present` | 53 | 45.7% | 70.9% | 9.1% | 29.8% |

### `arm_b_finetune@c0.0-d0.0`

Recombination test slice: **n 7022**, **eff n 243** clusters, accuracy 94.9% [92.1%, 97.3%]. Holdout: **n 67** submissions, one observation each, scored by 5 fold models at margins 0.8, 0.85, 0.0, 0.0, 0.0. The two `n`s are printed together because they are not the same kind of number and the second is far the smaller.

| signal | true/false/null | omitted | decisive n | decisive acc (mean +/- sd) | worst-case half-width | all n | all acc (mean +/- sd) | null recall |
|---|---|---|---|---|---|---|---|---|
| `flank_pain_present` | 7/7/53 | 0 | 14 | 84.3% +/- 10.6% | +/-26.2% | 67 | 54.9% +/- 9.6% | 47.2% +/- 10.8% |

`null -> true` on real text, per fold: `flank_pain_present` 21, 29, 16, 31, 24 of 53. This is the cell that invents a symptom into a patient's pre-filled form, counted here on submissions rather than on recombinations.

### `arm_b_finetune@c0.0-d0.3`

Recombination test slice: **n 7022**, **eff n 400** clusters, accuracy 97.5% [95.8%, 99.0%]. Holdout: **n 67** submissions, one observation each, scored by 5 fold models at margins 0.9, 0.1, 0.75, 0.0, 0.85. The two `n`s are printed together because they are not the same kind of number and the second is far the smaller.

| signal | true/false/null | omitted | decisive n | decisive acc (mean +/- sd) | worst-case half-width | all n | all acc (mean +/- sd) | null recall |
|---|---|---|---|---|---|---|---|---|
| `flank_pain_present` | 7/7/53 | 0 | 14 | 92.9% +/- 0.0% | +/-26.2% | 67 | 38.8% +/- 5.6% | 24.5% +/- 7.1% |

`null -> true` on real text, per fold: `flank_pain_present` 36, 35, 39, 44, 34 of 53. This is the cell that invents a symptom into a patient's pre-filled form, counted here on submissions rather than on recombinations.

### `arm_b_finetune@c0.5-d0.0`

Recombination test slice: **n 7022**, **eff n 243** clusters, accuracy 92.1% [88.4%, 95.3%]. Holdout: **n 67** submissions, one observation each, scored by 5 fold models at margins 0.65, 0.25, 0.0, 0.8, 0.0. The two `n`s are printed together because they are not the same kind of number and the second is far the smaller.

| signal | true/false/null | omitted | decisive n | decisive acc (mean +/- sd) | worst-case half-width | all n | all acc (mean +/- sd) | null recall |
|---|---|---|---|---|---|---|---|---|
| `flank_pain_present` | 7/7/53 | 0 | 14 | 40.0% +/- 12.0% | +/-26.2% | 67 | 79.4% +/- 4.1% | 89.8% +/- 2.9% |

`null -> true` on real text, per fold: `flank_pain_present` 4, 4, 5, 4, 7 of 53. This is the cell that invents a symptom into a patient's pre-filled form, counted here on submissions rather than on recombinations.

### `arm_b_finetune@c0.5-d0.3`

Recombination test slice: **n 7022**, **eff n 400** clusters, accuracy 94.3% [91.8%, 96.7%]. Holdout: **n 67** submissions, one observation each, scored by 5 fold models at margins 0.9, 0.6, 0.9, 0.9, 0.0. The two `n`s are printed together because they are not the same kind of number and the second is far the smaller.

| signal | true/false/null | omitted | decisive n | decisive acc (mean +/- sd) | worst-case half-width | all n | all acc (mean +/- sd) | null recall |
|---|---|---|---|---|---|---|---|---|
| `flank_pain_present` | 7/7/53 | 0 | 14 | 81.4% +/- 10.8% | +/-26.2% | 67 | 71.6% +/- 4.4% | 69.1% +/- 7.1% |

`null -> true` on real text, per fold: `flank_pain_present` 11, 20, 18, 14, 16 of 53. This is the cell that invents a symptom into a patient's pre-filled form, counted here on submissions rather than on recombinations.

## Paired on real text

The 67 submissions are the same 67 for every model here, so unlike the recombination
test slice they can be paired: the informative quantity is the submissions two models
disagree about, not the gap between two means. One test per fold, never pooled.

### `arm_b_finetune@c0.0-d0.0` against `arm_b_finetune@c0.0-d0.3`

| fold | pairs | only `arm_b_finetune@c0.0-d0.0` | only `arm_b_finetune@c0.0-d0.3` | p |
|---|---|---|---|---|
| 0 | 67 | 15 | 0 | 6.1e-05 |
| 1 | 67 | 6 | 3 | 0.508 |
| 2 | 67 | 21 | 2 | 6.6e-05 |
| 3 | 67 | 13 | 3 | 0.0213 |
| 4 | 67 | 11 | 4 | 0.118 |

`arm_b_finetune@c0.0-d0.0` ahead on 5 folds, `arm_b_finetune@c0.0-d0.3` on 0. `null -> true` mean: 45.7% against 70.9% -- **25.3 points higher** for `arm_b_finetune@c0.0-d0.3` -- more invented symptoms.

*One test per fold over the same 67 submissions, never concatenated: five folds are five models scored on one sample, and pooling would report a p-value for 335 observations that do not exist.*

### `arm_b_finetune@c0.0-d0.0` against `arm_b_finetune@c0.5-d0.0`

| fold | pairs | only `arm_b_finetune@c0.0-d0.0` | only `arm_b_finetune@c0.5-d0.0` | p |
|---|---|---|---|---|
| 0 | 67 | 8 | 22 | 0.0161 |
| 1 | 67 | 6 | 29 | 0.000117 |
| 2 | 67 | 4 | 15 | 0.0192 |
| 3 | 67 | 6 | 28 | 0.000195 |
| 4 | 67 | 7 | 19 | 0.029 |

`arm_b_finetune@c0.0-d0.0` ahead on 0 folds, `arm_b_finetune@c0.5-d0.0` on 5. `null -> true` mean: 45.7% against 9.1% -- **36.6 points lower** for `arm_b_finetune@c0.5-d0.0` -- fewer invented symptoms.

*One test per fold over the same 67 submissions, never concatenated: five folds are five models scored on one sample, and pooling would report a p-value for 335 observations that do not exist.*

### `arm_b_finetune@c0.0-d0.0` against `arm_b_finetune@c0.5-d0.3`

| fold | pairs | only `arm_b_finetune@c0.0-d0.0` | only `arm_b_finetune@c0.5-d0.3` | p |
|---|---|---|---|---|
| 0 | 67 | 7 | 17 | 0.0639 |
| 1 | 67 | 4 | 17 | 0.0072 |
| 2 | 67 | 7 | 8 | 1 |
| 3 | 67 | 3 | 23 | 8.8e-05 |
| 4 | 67 | 6 | 18 | 0.0227 |

`arm_b_finetune@c0.0-d0.0` ahead on 0 folds, `arm_b_finetune@c0.5-d0.3` on 5. `null -> true` mean: 45.7% against 29.8% -- **15.8 points lower** for `arm_b_finetune@c0.5-d0.3` -- fewer invented symptoms.

*One test per fold over the same 67 submissions, never concatenated: five folds are five models scored on one sample, and pooling would report a p-value for 335 observations that do not exist.*

### `arm_b_finetune@c0.0-d0.3` against `arm_b_finetune@c0.5-d0.0`

| fold | pairs | only `arm_b_finetune@c0.0-d0.3` | only `arm_b_finetune@c0.5-d0.0` | p |
|---|---|---|---|---|
| 0 | 67 | 7 | 36 | 8.96e-06 |
| 1 | 67 | 7 | 33 | 4.23e-05 |
| 2 | 67 | 5 | 35 | 1.38e-06 |
| 3 | 67 | 9 | 41 | 5.61e-06 |
| 4 | 67 | 9 | 28 | 0.00256 |

`arm_b_finetune@c0.0-d0.3` ahead on 0 folds, `arm_b_finetune@c0.5-d0.0` on 5. `null -> true` mean: 70.9% against 9.1% -- **61.9 points lower** for `arm_b_finetune@c0.5-d0.0` -- fewer invented symptoms.

*One test per fold over the same 67 submissions, never concatenated: five folds are five models scored on one sample, and pooling would report a p-value for 335 observations that do not exist.*

### `arm_b_finetune@c0.0-d0.3` against `arm_b_finetune@c0.5-d0.3`

| fold | pairs | only `arm_b_finetune@c0.0-d0.3` | only `arm_b_finetune@c0.5-d0.3` | p |
|---|---|---|---|---|
| 0 | 67 | 4 | 29 | 1.09e-05 |
| 1 | 67 | 2 | 18 | 0.000402 |
| 2 | 67 | 0 | 20 | 1.91e-06 |
| 3 | 67 | 1 | 31 | 1.54e-08 |
| 4 | 67 | 1 | 20 | 2.1e-05 |

`arm_b_finetune@c0.0-d0.3` ahead on 0 folds, `arm_b_finetune@c0.5-d0.3` on 5. `null -> true` mean: 70.9% against 29.8% -- **41.1 points lower** for `arm_b_finetune@c0.5-d0.3` -- fewer invented symptoms.

*One test per fold over the same 67 submissions, never concatenated: five folds are five models scored on one sample, and pooling would report a p-value for 335 observations that do not exist.*

### `arm_b_finetune@c0.5-d0.0` against `arm_b_finetune@c0.5-d0.3`

| fold | pairs | only `arm_b_finetune@c0.5-d0.0` | only `arm_b_finetune@c0.5-d0.3` | p |
|---|---|---|---|---|
| 0 | 67 | 8 | 4 | 0.388 |
| 1 | 67 | 16 | 6 | 0.0525 |
| 2 | 67 | 15 | 5 | 0.0414 |
| 3 | 67 | 10 | 8 | 0.815 |
| 4 | 67 | 9 | 9 | 1 |

`arm_b_finetune@c0.5-d0.0` ahead on 4 folds, `arm_b_finetune@c0.5-d0.3` on 0. `null -> true` mean: 9.1% against 29.8% -- **20.8 points higher** for `arm_b_finetune@c0.5-d0.3` -- more invented symptoms.

*One test per fold over the same 67 submissions, never concatenated: five folds are five models scored on one sample, and pooling would report a p-value for 335 observations that do not exist.*

* `majority_class` against `length_only`: not paired -- one or both runs carry no real-text cells for this signal (not scored, or scored before the per-submission decisions were kept).
* `majority_class` against `tfidf_logreg`: not paired -- one or both runs carry no real-text cells for this signal (not scored, or scored before the per-submission decisions were kept).
* `majority_class` against `arm_b_finetune@c0.0-d0.0`: not paired -- one or both runs carry no real-text cells for this signal (not scored, or scored before the per-submission decisions were kept).
* `majority_class` against `arm_b_finetune@c0.0-d0.3`: not paired -- one or both runs carry no real-text cells for this signal (not scored, or scored before the per-submission decisions were kept).
* `majority_class` against `arm_b_finetune@c0.5-d0.0`: not paired -- one or both runs carry no real-text cells for this signal (not scored, or scored before the per-submission decisions were kept).
* `majority_class` against `arm_b_finetune@c0.5-d0.3`: not paired -- one or both runs carry no real-text cells for this signal (not scored, or scored before the per-submission decisions were kept).
* `length_only` against `tfidf_logreg`: not paired -- one or both runs carry no real-text cells for this signal (not scored, or scored before the per-submission decisions were kept).
* `length_only` against `arm_b_finetune@c0.0-d0.0`: not paired -- one or both runs carry no real-text cells for this signal (not scored, or scored before the per-submission decisions were kept).
* `length_only` against `arm_b_finetune@c0.0-d0.3`: not paired -- one or both runs carry no real-text cells for this signal (not scored, or scored before the per-submission decisions were kept).
* `length_only` against `arm_b_finetune@c0.5-d0.0`: not paired -- one or both runs carry no real-text cells for this signal (not scored, or scored before the per-submission decisions were kept).
* `length_only` against `arm_b_finetune@c0.5-d0.3`: not paired -- one or both runs carry no real-text cells for this signal (not scored, or scored before the per-submission decisions were kept).
* `tfidf_logreg` against `arm_b_finetune@c0.0-d0.0`: not paired -- one or both runs carry no real-text cells for this signal (not scored, or scored before the per-submission decisions were kept).
* `tfidf_logreg` against `arm_b_finetune@c0.0-d0.3`: not paired -- one or both runs carry no real-text cells for this signal (not scored, or scored before the per-submission decisions were kept).
* `tfidf_logreg` against `arm_b_finetune@c0.5-d0.0`: not paired -- one or both runs carry no real-text cells for this signal (not scored, or scored before the per-submission decisions were kept).
* `tfidf_logreg` against `arm_b_finetune@c0.5-d0.3`: not paired -- one or both runs carry no real-text cells for this signal (not scored, or scored before the per-submission decisions were kept).

## The cells behind these columns

One cell per `--cell`, each generated from the same libraries with the same seed, the same counts and the same fold triple, differing only in `--companion-share` and `--declarative-share`. The shares are read from each cell's own sidecars, not from this run's flags.

| cell | companion share | declarative share | generator | splits read | tree |
|---|---|---|---|---|---|
| `c0.0-d0.0` | 0.0 | 0.0 | 4 | 30 | `data/synthetic/generated/decl/c0.0-d0.0` |
| `c0.0-d0.3` | 0.0 | 0.3 | 4 | 30 | `data/synthetic/generated/decl/c0.0-d0.3` |
| `c0.5-d0.0` | 0.5 | 0.0 | 4 | 30 | `data/synthetic/generated/decl/c0.5-d0.0` |
| `c0.5-d0.3` | 0.5 | 0.3 | 4 | 30 | `data/synthetic/generated/decl/c0.5-d0.3` |


*`c0.0-d0.0` (data/synthetic/generated/decl/c0.0-d0.0) is the reference: the report's test slice, fold partition and cluster checks describe its tree..*

*No two cells are paired on the synthetic test set. Changing either share changes which fragments are drawn, so the example ids match across cells while the texts behind them do not; every cell after the reference is recorded as unpaired and its McNemar rows are skips rather than a test over pairs that do not exist. The 67 real-text submissions are the same for every cell and are where the cells are compared..*

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
| `majority_class` | baseline | 3062 | **140** | 100.0% [100.0%, 100.0%] |
| `length_only` | baseline | 3062 | **140** | 100.0% [100.0%, 100.0%] |
| `tfidf_logreg` | baseline | 3062 | **140** | 91.7% [88.0%, 95.0%] |
| `arm_b_finetune@c0.0-d0.0` | finetune | 3062 | **140** | 93.7% [89.7%, 97.1%] |
| `arm_b_finetune@c0.0-d0.3` | finetune | 3062 | **140** | 97.3% [94.9%, 99.3%] |
| `arm_b_finetune@c0.5-d0.0` | finetune | 3062 | **140** | 94.6% [90.9%, 97.7%] |
| `arm_b_finetune@c0.5-d0.3` | finetune | 3062 | **140** | 94.1% [90.6%, 97.3%] |

### 2. The same comparison, paired

Two overlapping intervals do not settle whether one model beats another on the same
examples. McNemar does, over the examples the two disagree about -- read it alongside the
intervals above, never instead of them.

| pair | n | a only | b only | p |
|---|---|---|---|---|
| `majority_class` vs `length_only` | 3062 | 0 | 0 | 1 |
| `majority_class` vs `tfidf_logreg` | 3062 | 254 | 0 | 6.91e-77 |
| `majority_class` vs `arm_b_finetune@c0.0-d0.0` | 3062 | 207 | 0 | 9.72e-63 |
| `length_only` vs `tfidf_logreg` | 3062 | 254 | 0 | 6.91e-77 |
| `length_only` vs `arm_b_finetune@c0.0-d0.0` | 3062 | 207 | 0 | 9.72e-63 |
| `tfidf_logreg` vs `arm_b_finetune@c0.0-d0.0` | 3062 | 147 | 194 | 0.0126 |

Not on this table, because they cannot be paired at all -- different examples on the two sides, so there is nothing for McNemar to pair: `majority_class` vs `arm_b_finetune@c0.0-d0.3`; `majority_class` vs `arm_b_finetune@c0.5-d0.0`; `majority_class` vs `arm_b_finetune@c0.5-d0.3`; `length_only` vs `arm_b_finetune@c0.0-d0.3`; `length_only` vs `arm_b_finetune@c0.5-d0.0`; `length_only` vs `arm_b_finetune@c0.5-d0.3`; `tfidf_logreg` vs `arm_b_finetune@c0.0-d0.3`; `tfidf_logreg` vs `arm_b_finetune@c0.5-d0.0`; `tfidf_logreg` vs `arm_b_finetune@c0.5-d0.3`; `arm_b_finetune@c0.0-d0.0` vs `arm_b_finetune@c0.0-d0.3`; `arm_b_finetune@c0.0-d0.0` vs `arm_b_finetune@c0.5-d0.0`; `arm_b_finetune@c0.0-d0.0` vs `arm_b_finetune@c0.5-d0.3`; `arm_b_finetune@c0.0-d0.3` vs `arm_b_finetune@c0.5-d0.0`; `arm_b_finetune@c0.0-d0.3` vs `arm_b_finetune@c0.5-d0.3`; `arm_b_finetune@c0.5-d0.0` vs `arm_b_finetune@c0.5-d0.3`. Read those through the intervals above and the per-fold spread, and see "Pairs that could not be tested" below.

### 3. Where the errors fall

The per-fragment table below, as one number per model. Errors spread thinly across many
fragments say the method is too weak. Errors piled onto a handful say those specific ideas
are not learnable from the data we have -- and the table names them, which is what makes
this the most decision-useful thing in the report.

* `majority_class`: 3960 errors across 103 of 243 decisive fragments. Half of them fall on **37** fragments (an even spread would be 51.5); the worst ten carry 17.0% of all errors.
* `length_only`: 3960 errors across 103 of 243 decisive fragments. Half of them fall on **37** fragments (an even spread would be 51.5); the worst ten carry 17.0% of all errors.
* `tfidf_logreg`: 1948 errors across 118 of 243 decisive fragments. Half of them fall on **24** fragments (an even spread would be 59.0); the worst ten carry 26.4% of all errors.
* `arm_b_finetune@c0.0-d0.0`: 358 errors across 28 of 243 decisive fragments. Half of them fall on **6** fragments (an even spread would be 14.0); the worst ten carry 75.7% of all errors.
* `arm_b_finetune@c0.0-d0.3`: 173 errors across 20 of 655 decisive fragments. Half of them fall on **4** fragments (an even spread would be 10.0); the worst ten carry 90.2% of all errors.
* `arm_b_finetune@c0.5-d0.0`: 558 errors across 46 of 243 decisive fragments. Half of them fall on **7** fragments (an even spread would be 23.0); the worst ten carry 64.9% of all errors.
* `arm_b_finetune@c0.5-d0.3`: 399 errors across 39 of 654 decisive fragments. Half of them fall on **8** fragments (an even spread would be 19.5); the worst ten carry 63.7% of all errors.

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
* **test partition** -- checked. Across the 5 folds, 2703 distinct clusters are held out, each in exactly one fold, so pooling the folds counts every idea once. That figure spans every library in the manifest -- filler and other signals' libraries included -- not just this signal's; the per-slice `eff n` columns are the numbers that bound anything.
* **fold configuration** -- checked. The three splits of each fold agree on generator version, fold count, fold index and salt, and all folds agree on the salt.
* **cell datasets** -- checked at load. Every cell's tree was loaded, and its two shares read from its own sidecars and asserted distinct, before any training started. The checks above describe the reference cell's tree, which is the one this report's test slice belongs to.

Shuffled-label controls, evaluated on the **unpermuted** test split. A large model will
memorise permuted training labels and drive train loss to zero; that is correct behaviour
and says nothing. Only the test score is the control.

| control | accuracy [95% CI] | macro-F1 [95% CI] |
|---|---|---|
| `length_only__shuffled` | 60.4% [39.0%, 76.8%] | 25.1% [18.7%, 29.0%] |
| `tfidf_logreg__shuffled` | 60.4% [39.0%, 76.8%] | 25.1% [18.7%, 29.0%] |

## Paired comparisons (McNemar, raw argmax)

Exact two-sided McNemar over the examples the two models disagree about. Pairing unit is the
example, not the cluster -- see the limitations.

| pair | slice | n | a only | b only | p |
|---|---|---|---|---|---|
| `majority_class` vs `length_only` | overall | 10000 | 0 | 0 | 1 |
| `majority_class` vs `length_only` | null_ambiguous | 3062 | 0 | 0 | 1 |
| `majority_class` vs `tfidf_logreg` | overall | 10000 | 259 | 2266 | 0 |
| `majority_class` vs `tfidf_logreg` | null_ambiguous | 3062 | 254 | 0 | 6.91e-77 |
| `majority_class` vs `arm_b_finetune@c0.0-d0.0` | overall | 10000 | 211 | 3795 | 0 |
| `majority_class` vs `arm_b_finetune@c0.0-d0.0` | null_ambiguous | 3062 | 207 | 0 | 9.72e-63 |
| `length_only` vs `tfidf_logreg` | overall | 10000 | 259 | 2266 | 0 |
| `length_only` vs `tfidf_logreg` | null_ambiguous | 3062 | 254 | 0 | 6.91e-77 |
| `length_only` vs `arm_b_finetune@c0.0-d0.0` | overall | 10000 | 211 | 3795 | 0 |
| `length_only` vs `arm_b_finetune@c0.0-d0.0` | null_ambiguous | 3062 | 207 | 0 | 9.72e-63 |
| `tfidf_logreg` vs `arm_b_finetune@c0.0-d0.0` | overall | 10000 | 159 | 1736 | 0 |
| `tfidf_logreg` vs `arm_b_finetune@c0.0-d0.0` | null_ambiguous | 3062 | 147 | 194 | 0.0126 |

### Pairs that could not be tested

McNemar pairs on the example id, so two models scored on **different examples** cannot be
compared this way at all -- there is nothing to pair. That is a property of the datasets,
not a result: read those runs through their pooled cluster intervals and their per-fold
spread, and do not read the absence of a row above as agreement between them.

| pair | slice | n (a) | n (b) | shared | reason |
|---|---|---|---|---|---|
| `majority_class` vs `arm_b_finetune@c0.0-d0.3` | overall | 10000 | 10000 | 0 | example sets differ: majority_class has 10000, arm_b_finetune@c0.0-d0.3 has 10000, 0 in common |
| `majority_class` vs `arm_b_finetune@c0.0-d0.3` | null_ambiguous | 3062 | 3062 | 0 | example sets differ: majority_class has 3062, arm_b_finetune@c0.0-d0.3 has 3062, 0 in common |
| `majority_class` vs `arm_b_finetune@c0.5-d0.0` | overall | 10000 | 10000 | 0 | example sets differ: majority_class has 10000, arm_b_finetune@c0.5-d0.0 has 10000, 0 in common |
| `majority_class` vs `arm_b_finetune@c0.5-d0.0` | null_ambiguous | 3062 | 3062 | 0 | example sets differ: majority_class has 3062, arm_b_finetune@c0.5-d0.0 has 3062, 0 in common |
| `majority_class` vs `arm_b_finetune@c0.5-d0.3` | overall | 10000 | 10000 | 0 | example sets differ: majority_class has 10000, arm_b_finetune@c0.5-d0.3 has 10000, 0 in common |
| `majority_class` vs `arm_b_finetune@c0.5-d0.3` | null_ambiguous | 3062 | 3062 | 0 | example sets differ: majority_class has 3062, arm_b_finetune@c0.5-d0.3 has 3062, 0 in common |
| `length_only` vs `arm_b_finetune@c0.0-d0.3` | overall | 10000 | 10000 | 0 | example sets differ: length_only has 10000, arm_b_finetune@c0.0-d0.3 has 10000, 0 in common |
| `length_only` vs `arm_b_finetune@c0.0-d0.3` | null_ambiguous | 3062 | 3062 | 0 | example sets differ: length_only has 3062, arm_b_finetune@c0.0-d0.3 has 3062, 0 in common |
| `length_only` vs `arm_b_finetune@c0.5-d0.0` | overall | 10000 | 10000 | 0 | example sets differ: length_only has 10000, arm_b_finetune@c0.5-d0.0 has 10000, 0 in common |
| `length_only` vs `arm_b_finetune@c0.5-d0.0` | null_ambiguous | 3062 | 3062 | 0 | example sets differ: length_only has 3062, arm_b_finetune@c0.5-d0.0 has 3062, 0 in common |
| `length_only` vs `arm_b_finetune@c0.5-d0.3` | overall | 10000 | 10000 | 0 | example sets differ: length_only has 10000, arm_b_finetune@c0.5-d0.3 has 10000, 0 in common |
| `length_only` vs `arm_b_finetune@c0.5-d0.3` | null_ambiguous | 3062 | 3062 | 0 | example sets differ: length_only has 3062, arm_b_finetune@c0.5-d0.3 has 3062, 0 in common |
| `tfidf_logreg` vs `arm_b_finetune@c0.0-d0.3` | overall | 10000 | 10000 | 0 | example sets differ: tfidf_logreg has 10000, arm_b_finetune@c0.0-d0.3 has 10000, 0 in common |
| `tfidf_logreg` vs `arm_b_finetune@c0.0-d0.3` | null_ambiguous | 3062 | 3062 | 0 | example sets differ: tfidf_logreg has 3062, arm_b_finetune@c0.0-d0.3 has 3062, 0 in common |
| `tfidf_logreg` vs `arm_b_finetune@c0.5-d0.0` | overall | 10000 | 10000 | 0 | example sets differ: tfidf_logreg has 10000, arm_b_finetune@c0.5-d0.0 has 10000, 0 in common |
| `tfidf_logreg` vs `arm_b_finetune@c0.5-d0.0` | null_ambiguous | 3062 | 3062 | 0 | example sets differ: tfidf_logreg has 3062, arm_b_finetune@c0.5-d0.0 has 3062, 0 in common |
| `tfidf_logreg` vs `arm_b_finetune@c0.5-d0.3` | overall | 10000 | 10000 | 0 | example sets differ: tfidf_logreg has 10000, arm_b_finetune@c0.5-d0.3 has 10000, 0 in common |
| `tfidf_logreg` vs `arm_b_finetune@c0.5-d0.3` | null_ambiguous | 3062 | 3062 | 0 | example sets differ: tfidf_logreg has 3062, arm_b_finetune@c0.5-d0.3 has 3062, 0 in common |
| `arm_b_finetune@c0.0-d0.0` vs `arm_b_finetune@c0.0-d0.3` | overall | 10000 | 10000 | 0 | example sets differ: arm_b_finetune@c0.0-d0.0 has 10000, arm_b_finetune@c0.0-d0.3 has 10000, 0 in common |
| `arm_b_finetune@c0.0-d0.0` vs `arm_b_finetune@c0.0-d0.3` | null_ambiguous | 3062 | 3062 | 0 | example sets differ: arm_b_finetune@c0.0-d0.0 has 3062, arm_b_finetune@c0.0-d0.3 has 3062, 0 in common |
| `arm_b_finetune@c0.0-d0.0` vs `arm_b_finetune@c0.5-d0.0` | overall | 10000 | 10000 | 0 | example sets differ: arm_b_finetune@c0.0-d0.0 has 10000, arm_b_finetune@c0.5-d0.0 has 10000, 0 in common |
| `arm_b_finetune@c0.0-d0.0` vs `arm_b_finetune@c0.5-d0.0` | null_ambiguous | 3062 | 3062 | 0 | example sets differ: arm_b_finetune@c0.0-d0.0 has 3062, arm_b_finetune@c0.5-d0.0 has 3062, 0 in common |
| `arm_b_finetune@c0.0-d0.0` vs `arm_b_finetune@c0.5-d0.3` | overall | 10000 | 10000 | 0 | example sets differ: arm_b_finetune@c0.0-d0.0 has 10000, arm_b_finetune@c0.5-d0.3 has 10000, 0 in common |
| `arm_b_finetune@c0.0-d0.0` vs `arm_b_finetune@c0.5-d0.3` | null_ambiguous | 3062 | 3062 | 0 | example sets differ: arm_b_finetune@c0.0-d0.0 has 3062, arm_b_finetune@c0.5-d0.3 has 3062, 0 in common |
| `arm_b_finetune@c0.0-d0.3` vs `arm_b_finetune@c0.5-d0.0` | overall | 10000 | 10000 | 0 | example sets differ: arm_b_finetune@c0.0-d0.3 has 10000, arm_b_finetune@c0.5-d0.0 has 10000, 0 in common |
| `arm_b_finetune@c0.0-d0.3` vs `arm_b_finetune@c0.5-d0.0` | null_ambiguous | 3062 | 3062 | 0 | example sets differ: arm_b_finetune@c0.0-d0.3 has 3062, arm_b_finetune@c0.5-d0.0 has 3062, 0 in common |
| `arm_b_finetune@c0.0-d0.3` vs `arm_b_finetune@c0.5-d0.3` | overall | 10000 | 10000 | 0 | example sets differ: arm_b_finetune@c0.0-d0.3 has 10000, arm_b_finetune@c0.5-d0.3 has 10000, 0 in common |
| `arm_b_finetune@c0.0-d0.3` vs `arm_b_finetune@c0.5-d0.3` | null_ambiguous | 3062 | 3062 | 0 | example sets differ: arm_b_finetune@c0.0-d0.3 has 3062, arm_b_finetune@c0.5-d0.3 has 3062, 0 in common |
| `arm_b_finetune@c0.5-d0.0` vs `arm_b_finetune@c0.5-d0.3` | overall | 10000 | 10000 | 0 | example sets differ: arm_b_finetune@c0.5-d0.0 has 10000, arm_b_finetune@c0.5-d0.3 has 10000, 0 in common |
| `arm_b_finetune@c0.5-d0.0` vs `arm_b_finetune@c0.5-d0.3` | null_ambiguous | 3062 | 3062 | 0 | example sets differ: arm_b_finetune@c0.5-d0.0 has 3062, arm_b_finetune@c0.5-d0.3 has 3062, 0 in common |

## What moved, and where

The headline is the least useful output of a model comparison. These two tables are the
useful one: a diffuse lift and a fix to one error family are different findings, and an
aggregate accuracy cannot tell them apart. `spread` is max minus min across the models --
a row where every encoder lands together is a row model choice does not touch.

### By library, accuracy after the decision rule

Worst-performing library first. For a single-class library -- `fever_false` holds only
`false` examples -- accuracy here *is* that class's recall on that library.

| library | n | `majority_class` | `length_only` | `tfidf_logreg` | `arm_b_finetune@c0.0-d0.0` | `arm_b_finetune@c0.0-d0.3` | `arm_b_finetune@c0.5-d0.0` | `arm_b_finetune@c0.5-d0.3` | spread |
|---|---|---|---|---|---|---|---|---|---|
| `flank_pain_false` | 1725 | 0.0% | 0.0% | 60.7% | 95.8% | 96.4% | 88.3% | 91.7% | 96.4pp |
| `flank_pain_true` | 1025 | 0.0% | 0.0% | 51.4% | 96.0% | 97.2% | 93.2% | 92.8% | 97.2pp |
| `flank_pain_null_hedged` | 1178 | 100.0% | 100.0% | 88.8% | 89.3% | 94.1% | 90.0% | 86.8% | 13.2pp |
| `flank_pain_null_historical` | 869 | 100.0% | 100.0% | 91.4% | 93.1% | 99.4% | 99.8% | 97.7% | 8.6pp |
| `flank_pain_null_thirdparty` | 1015 | 100.0% | 100.0% | 95.5% | 99.3% | 99.3% | 95.5% | 99.5% | 4.5pp |
| `(none)` | 2978 | 100.0% | 100.0% | 99.8% | 99.9% | 99.9% | 99.7% | 99.7% | 0.3pp |

### By fragment, errors

Ordered by the worst model's error count, so the fragments the comparison is about sort
to the top whichever encoder wins. Counts, not rates: these are the sentences a month of
library work would be spent on. The JSON holds every fragment.

| fragment | library | truth | `majority_class` | `length_only` | `tfidf_logreg` | `arm_b_finetune@c0.0-d0.0` | `arm_b_finetune@c0.0-d0.3` | `arm_b_finetune@c0.5-d0.0` | `arm_b_finetune@c0.5-d0.3` | spread |
|---|---|---|---|---|---|---|---|---|---|---|
| `flank_pain_false:4782be93` | `flank_pain_false` | false | 81 | 81 | 43 | 0 | 0 | 0 | 0 | 81 |
| `flank_pain_false:80bb4b40` | `flank_pain_false` | false | 76 | 76 | 50 | 0 | 0 | 0 | 0 | 76 |
| `flank_pain_false:4d4ec138` | `flank_pain_false` | false | 75 | 75 | 75 | 0 | 0 | 0 | 25 | 75 |
| `flank_pain_false:7b34cfc0` | `flank_pain_false` | false | 73 | 73 | 12 | 0 | 0 | 0 | 0 | 73 |
| `flank_pain_false:9b1cee9c` | `flank_pain_false` | false | 65 | 65 | 0 | 0 | 0 | 0 | 0 | 65 |
| `flank_pain_false:a2c9e38d` | `flank_pain_false` | false | 63 | 63 | 61 | 0 | 0 | 0 | 0 | 63 |
| `flank_pain_false:76bc0785` | `flank_pain_false` | false | 61 | 61 | 5 | 0 | 0 | 0 | 0 | 61 |
| `flank_pain_false:71da3a84` | `flank_pain_false` | false | 60 | 60 | 22 | 0 | 0 | 0 | 0 | 60 |
| `flank_pain_false:be00686d` | `flank_pain_false` | false | 60 | 60 | 0 | 0 | 0 | 0 | 0 | 60 |
| `flank_pain_false:d439a7ee` | `flank_pain_false` | false | 58 | 58 | 7 | 0 | 0 | 0 | 0 | 58 |
| `flank_pain_false:42aa75a8` | `flank_pain_false` | false | 57 | 57 | 9 | 0 | 0 | 0 | 0 | 57 |
| `flank_pain_false:bead93da` | `flank_pain_false` | false | 54 | 54 | 54 | 54 | 32 | 55 | 32 | 23 |
| `flank_pain_false:ad38bb4f` | `flank_pain_false` | false | 54 | 54 | 9 | 0 | 0 | 0 | 0 | 54 |
| `flank_pain_false:924082ae` | `flank_pain_false` | false | 52 | 52 | 0 | 0 | 0 | 0 | 0 | 52 |
| `flank_pain_false:9ba1c8d3` | `flank_pain_false` | false | 51 | 51 | 0 | 0 | 0 | 0 | 0 | 51 |
| `flank_pain_false:d37c1465` | `flank_pain_false` | false | 51 | 51 | 46 | 0 | 0 | 16 | 35 | 51 |
| `flank_pain_true:faa371b2` | `flank_pain_true` | true | 51 | 51 | 11 | 0 | 0 | 0 | 0 | 51 |
| `flank_pain_false:132f591d` | `flank_pain_false` | false | 50 | 50 | 35 | 0 | 0 | 0 | 0 | 50 |
| `flank_pain_false:37373d48` | `flank_pain_false` | false | 50 | 50 | 40 | 0 | 0 | 0 | 0 | 50 |
| `flank_pain_false:4947dcd5` | `flank_pain_false` | false | 50 | 50 | 39 | 0 | 0 | 0 | 0 | 50 |
| `flank_pain_false:6c762141` | `flank_pain_false` | false | 50 | 50 | 48 | 0 | 0 | 0 | 0 | 50 |
| `flank_pain_false:3273a39a` | `flank_pain_false` | false | 47 | 47 | 10 | 0 | 0 | 49 | 0 | 49 |
| `flank_pain_false:9ed5cbe0` | `flank_pain_false` | false | 49 | 49 | 0 | 0 | 0 | 0 | 0 | 49 |
| `flank_pain_true:801b09f3` | `flank_pain_true` | true | 49 | 49 | 49 | 8 | 3 | 2 | 1 | 48 |
| `flank_pain_false:6f0b7381` | `flank_pain_false` | false | 48 | 48 | 0 | 0 | 0 | 0 | 0 | 48 |
| `flank_pain_false:7f0a359d` | `flank_pain_false` | false | 48 | 48 | 1 | 0 | 0 | 0 | 0 | 48 |
| `flank_pain_false:d7abb5ec` | `flank_pain_false` | false | 47 | 47 | 47 | 47 | 30 | 48 | 30 | 18 |
| `flank_pain_false:f63b22a5` | `flank_pain_false` | false | 48 | 48 | 12 | 1 | 0 | 7 | 0 | 48 |
| `flank_pain_false:6cd7f2f5` | `flank_pain_false` | false | 47 | 47 | 30 | 0 | 0 | 0 | 0 | 47 |
| `flank_pain_false:a31e1604` | `flank_pain_false` | false | 47 | 47 | 3 | 0 | 0 | 0 | 0 | 47 |
| `flank_pain_false:f900bfea` | `flank_pain_false` | false | 46 | 46 | 33 | 0 | 0 | 44 | 0 | 46 |
| `flank_pain_false:27c1ea49` | `flank_pain_false` | false | 45 | 45 | 0 | 0 | 0 | 0 | 0 | 45 |
| `flank_pain_false:0d8df7a0` | `flank_pain_false` | false | 44 | 44 | 36 | 0 | 0 | 0 | 0 | 44 |
| `flank_pain_false:57d966db` | `flank_pain_false` | false | 44 | 44 | 0 | 0 | 0 | 0 | 0 | 44 |
| `flank_pain_false:b27cde7b` | `flank_pain_false` | false | 44 | 44 | 0 | 0 | 0 | 0 | 0 | 44 |
| `flank_pain_true:78957d62` | `flank_pain_true` | true | 44 | 44 | 3 | 0 | 0 | 0 | 0 | 44 |
| `flank_pain_false:b4c43f30` | `flank_pain_false` | false | 42 | 42 | 0 | 0 | 0 | 0 | 0 | 42 |
| `flank_pain_true:568725bb` | `flank_pain_true` | true | 42 | 42 | 42 | 0 | 0 | 0 | 0 | 42 |
| `flank_pain_false:536a4cfe` | `flank_pain_false` | false | 40 | 40 | 13 | 0 | 0 | 0 | 0 | 40 |
| `flank_pain_false:69f1f2f7` | `flank_pain_false` | false | 40 | 40 | 24 | 0 | 0 | 1 | 0 | 40 |

*122 further fragments erred on at least one model; the JSON holds them all.*

## `majority_class`

Always predicts the most common class in its fold's training split. Expected to score the generator's `null` share, which is a flag setting rather than a property of the data.

Decision-rule margins selected per fold (on each fold's own validation split): 0.0.
Every fold selected margin 0, so the ruled and raw views below are the same decisions. That is a finding rather than a bug: no margin improved macro-F1 without worsening the `null -> true` rate.

*Confusion matrix, raw argmax*

|  | pred false | pred true | pred null | total |
|---|---|---|---|---|
| **truth false** | 0 | 0 | 2479 | 2479 |
| **truth true** | 0 | 0 | 1481 | 1481 |
| **truth null** | 0 | 0 | 6040 | 6040 |
| **total** | 0 | 0 | 10000 | 10000 |

`null -> true`: 0 of 6040 truly-null examples (0.00%).

*Confusion matrix, after the decision rule*

|  | pred false | pred true | pred null | total |
|---|---|---|---|---|
| **truth false** | 0 | 0 | 2479 | 2479 |
| **truth true** | 0 | 0 | 1481 | 1481 |
| **truth null** | 0 | 0 | 6040 | 6040 |
| **total** | 0 | 0 | 10000 | 10000 |

`null -> true`: 0 of 6040 truly-null examples (0.00%).

### Per class, after the decision rule

| class | support | predicted | precision | recall | F1 |
|---|---|---|---|---|---|
| `false` | 2479 | 0 | -- | 0.0% | 0.0% |
| `true` | 1481 | 0 | -- | 0.0% | 0.0% |
| `null` | 6040 | 10000 | 60.4% | 100.0% | 75.3% |

### By label mode

| label mode | n | eff n | accuracy [95% CI] |
|---|---|---|---|
| false | 2479 | **55** | 0.0% [0.0%, 0.0%] |
| null_ambiguous | 3062 | **140** | 100.0% [100.0%, 100.0%] |
| null_structural | 2978 | **1** | 100.0% [100.0%, 100.0%] |
| true | 1481 | **48** | 0.0% [0.0%, 0.0%] |

### By null sub-class

| sub-class | n | eff n | null recall [95% CI] |
|---|---|---|---|
| hedged | 1183 | **53** | 100.0% [100.0%, 100.0%] |
| historical | 868 | **40** | 100.0% [100.0%, 100.0%] |
| third_party | 1011 | **47** | 100.0% [100.0%, 100.0%] |

### By fragment library

| library | n | eff n | accuracy [95% CI] |
|---|---|---|---|
| flank_pain_false | 2479 | **55** | 0.0% [0.0%, 0.0%] |
| flank_pain_null_hedged | 1183 | **53** | 100.0% [100.0%, 100.0%] |
| flank_pain_null_historical | 868 | **40** | 100.0% [100.0%, 100.0%] |
| flank_pain_null_thirdparty | 1011 | **47** | 100.0% [100.0%, 100.0%] |
| flank_pain_true | 1481 | **48** | 0.0% [0.0%, 0.0%] |
| (none) | 2978 | **1** | 100.0% [100.0%, 100.0%] |

### Per-fragment errors (worst first)

Whether errors are spread thinly across many fragments or piled onto a few is the difference
between "the method is too weak" (model work) and "these specific ideas are not learnable from
the data we have" (library work, and these are the fragments to write more of). No intervals:
a fragment is one cluster, so an interval over its own examples measures nothing.

103 of 243 decisive fragments were got wrong at least once.

`majority_class`: 3960 errors across 103 of 243 decisive fragments. Half of them fall on **37** fragments (an even spread would be 51.5); the worst ten carry 17.0% of all errors.

| fragment | library | sub-class | truth | correct | accuracy | predicted as |
|---|---|---|---|---|---|---|
| `flank_pain_false:4782be93` | `flank_pain_false` | -- | false | 0/81 | 0.0% | null 81 |
| `flank_pain_false:80bb4b40` | `flank_pain_false` | -- | false | 0/76 | 0.0% | null 76 |
| `flank_pain_false:4d4ec138` | `flank_pain_false` | -- | false | 0/75 | 0.0% | null 75 |
| `flank_pain_false:7b34cfc0` | `flank_pain_false` | -- | false | 0/73 | 0.0% | null 73 |
| `flank_pain_false:9b1cee9c` | `flank_pain_false` | -- | false | 0/65 | 0.0% | null 65 |
| `flank_pain_false:a2c9e38d` | `flank_pain_false` | -- | false | 0/63 | 0.0% | null 63 |
| `flank_pain_false:76bc0785` | `flank_pain_false` | -- | false | 0/61 | 0.0% | null 61 |
| `flank_pain_false:71da3a84` | `flank_pain_false` | -- | false | 0/60 | 0.0% | null 60 |
| `flank_pain_false:be00686d` | `flank_pain_false` | -- | false | 0/60 | 0.0% | null 60 |
| `flank_pain_false:d439a7ee` | `flank_pain_false` | -- | false | 0/58 | 0.0% | null 58 |
| `flank_pain_false:42aa75a8` | `flank_pain_false` | -- | false | 0/57 | 0.0% | null 57 |
| `flank_pain_false:ad38bb4f` | `flank_pain_false` | -- | false | 0/54 | 0.0% | null 54 |
| `flank_pain_false:bead93da` | `flank_pain_false` | -- | false | 0/54 | 0.0% | null 54 |
| `flank_pain_false:924082ae` | `flank_pain_false` | -- | false | 0/52 | 0.0% | null 52 |
| `flank_pain_false:9ba1c8d3` | `flank_pain_false` | -- | false | 0/51 | 0.0% | null 51 |
| `flank_pain_false:d37c1465` | `flank_pain_false` | -- | false | 0/51 | 0.0% | null 51 |
| `flank_pain_true:faa371b2` | `flank_pain_true` | -- | true | 0/51 | 0.0% | null 51 |
| `flank_pain_false:132f591d` | `flank_pain_false` | -- | false | 0/50 | 0.0% | null 50 |
| `flank_pain_false:37373d48` | `flank_pain_false` | -- | false | 0/50 | 0.0% | null 50 |
| `flank_pain_false:4947dcd5` | `flank_pain_false` | -- | false | 0/50 | 0.0% | null 50 |
| `flank_pain_false:6c762141` | `flank_pain_false` | -- | false | 0/50 | 0.0% | null 50 |
| `flank_pain_false:9ed5cbe0` | `flank_pain_false` | -- | false | 0/49 | 0.0% | null 49 |
| `flank_pain_true:801b09f3` | `flank_pain_true` | -- | true | 0/49 | 0.0% | null 49 |
| `flank_pain_false:6f0b7381` | `flank_pain_false` | -- | false | 0/48 | 0.0% | null 48 |
| `flank_pain_false:7f0a359d` | `flank_pain_false` | -- | false | 0/48 | 0.0% | null 48 |
| `flank_pain_false:f63b22a5` | `flank_pain_false` | -- | false | 0/48 | 0.0% | null 48 |
| `flank_pain_false:3273a39a` | `flank_pain_false` | -- | false | 0/47 | 0.0% | null 47 |
| `flank_pain_false:6cd7f2f5` | `flank_pain_false` | -- | false | 0/47 | 0.0% | null 47 |
| `flank_pain_false:a31e1604` | `flank_pain_false` | -- | false | 0/47 | 0.0% | null 47 |
| `flank_pain_false:d7abb5ec` | `flank_pain_false` | -- | false | 0/47 | 0.0% | null 47 |
| `flank_pain_false:f900bfea` | `flank_pain_false` | -- | false | 0/46 | 0.0% | null 46 |
| `flank_pain_false:27c1ea49` | `flank_pain_false` | -- | false | 0/45 | 0.0% | null 45 |
| `flank_pain_false:0d8df7a0` | `flank_pain_false` | -- | false | 0/44 | 0.0% | null 44 |
| `flank_pain_false:57d966db` | `flank_pain_false` | -- | false | 0/44 | 0.0% | null 44 |
| `flank_pain_false:b27cde7b` | `flank_pain_false` | -- | false | 0/44 | 0.0% | null 44 |
| `flank_pain_true:78957d62` | `flank_pain_true` | -- | true | 0/44 | 0.0% | null 44 |
| `flank_pain_false:b4c43f30` | `flank_pain_false` | -- | false | 0/42 | 0.0% | null 42 |
| `flank_pain_true:568725bb` | `flank_pain_true` | -- | true | 0/42 | 0.0% | null 42 |
| `flank_pain_false:536a4cfe` | `flank_pain_false` | -- | false | 0/40 | 0.0% | null 40 |
| `flank_pain_false:69f1f2f7` | `flank_pain_false` | -- | false | 0/40 | 0.0% | null 40 |

*63 further fragments with at least one error are in the JSON sidecar; every fragment is there regardless of score.*

## `length_only`

Logistic regression on token count alone. The direct measurable test of the length leak: anything materially above majority means text length is a usable proxy for the label, which is a fragment-library problem rather than a model one.

Decision-rule margins selected per fold (on each fold's own validation split): 0.0.
Every fold selected margin 0, so the ruled and raw views below are the same decisions. That is a finding rather than a bug: no margin improved macro-F1 without worsening the `null -> true` rate.

*Confusion matrix, raw argmax*

|  | pred false | pred true | pred null | total |
|---|---|---|---|---|
| **truth false** | 0 | 0 | 2479 | 2479 |
| **truth true** | 0 | 0 | 1481 | 1481 |
| **truth null** | 0 | 0 | 6040 | 6040 |
| **total** | 0 | 0 | 10000 | 10000 |

`null -> true`: 0 of 6040 truly-null examples (0.00%).

*Confusion matrix, after the decision rule*

|  | pred false | pred true | pred null | total |
|---|---|---|---|---|
| **truth false** | 0 | 0 | 2479 | 2479 |
| **truth true** | 0 | 0 | 1481 | 1481 |
| **truth null** | 0 | 0 | 6040 | 6040 |
| **total** | 0 | 0 | 10000 | 10000 |

`null -> true`: 0 of 6040 truly-null examples (0.00%).

### Per class, after the decision rule

| class | support | predicted | precision | recall | F1 |
|---|---|---|---|---|---|
| `false` | 2479 | 0 | -- | 0.0% | 0.0% |
| `true` | 1481 | 0 | -- | 0.0% | 0.0% |
| `null` | 6040 | 10000 | 60.4% | 100.0% | 75.3% |

### By label mode

| label mode | n | eff n | accuracy [95% CI] |
|---|---|---|---|
| false | 2479 | **55** | 0.0% [0.0%, 0.0%] |
| null_ambiguous | 3062 | **140** | 100.0% [100.0%, 100.0%] |
| null_structural | 2978 | **1** | 100.0% [100.0%, 100.0%] |
| true | 1481 | **48** | 0.0% [0.0%, 0.0%] |

### By null sub-class

| sub-class | n | eff n | null recall [95% CI] |
|---|---|---|---|
| hedged | 1183 | **53** | 100.0% [100.0%, 100.0%] |
| historical | 868 | **40** | 100.0% [100.0%, 100.0%] |
| third_party | 1011 | **47** | 100.0% [100.0%, 100.0%] |

### By fragment library

| library | n | eff n | accuracy [95% CI] |
|---|---|---|---|
| flank_pain_false | 2479 | **55** | 0.0% [0.0%, 0.0%] |
| flank_pain_null_hedged | 1183 | **53** | 100.0% [100.0%, 100.0%] |
| flank_pain_null_historical | 868 | **40** | 100.0% [100.0%, 100.0%] |
| flank_pain_null_thirdparty | 1011 | **47** | 100.0% [100.0%, 100.0%] |
| flank_pain_true | 1481 | **48** | 0.0% [0.0%, 0.0%] |
| (none) | 2978 | **1** | 100.0% [100.0%, 100.0%] |

### Per-fragment errors (worst first)

Whether errors are spread thinly across many fragments or piled onto a few is the difference
between "the method is too weak" (model work) and "these specific ideas are not learnable from
the data we have" (library work, and these are the fragments to write more of). No intervals:
a fragment is one cluster, so an interval over its own examples measures nothing.

103 of 243 decisive fragments were got wrong at least once.

`length_only`: 3960 errors across 103 of 243 decisive fragments. Half of them fall on **37** fragments (an even spread would be 51.5); the worst ten carry 17.0% of all errors.

| fragment | library | sub-class | truth | correct | accuracy | predicted as |
|---|---|---|---|---|---|---|
| `flank_pain_false:4782be93` | `flank_pain_false` | -- | false | 0/81 | 0.0% | null 81 |
| `flank_pain_false:80bb4b40` | `flank_pain_false` | -- | false | 0/76 | 0.0% | null 76 |
| `flank_pain_false:4d4ec138` | `flank_pain_false` | -- | false | 0/75 | 0.0% | null 75 |
| `flank_pain_false:7b34cfc0` | `flank_pain_false` | -- | false | 0/73 | 0.0% | null 73 |
| `flank_pain_false:9b1cee9c` | `flank_pain_false` | -- | false | 0/65 | 0.0% | null 65 |
| `flank_pain_false:a2c9e38d` | `flank_pain_false` | -- | false | 0/63 | 0.0% | null 63 |
| `flank_pain_false:76bc0785` | `flank_pain_false` | -- | false | 0/61 | 0.0% | null 61 |
| `flank_pain_false:71da3a84` | `flank_pain_false` | -- | false | 0/60 | 0.0% | null 60 |
| `flank_pain_false:be00686d` | `flank_pain_false` | -- | false | 0/60 | 0.0% | null 60 |
| `flank_pain_false:d439a7ee` | `flank_pain_false` | -- | false | 0/58 | 0.0% | null 58 |
| `flank_pain_false:42aa75a8` | `flank_pain_false` | -- | false | 0/57 | 0.0% | null 57 |
| `flank_pain_false:ad38bb4f` | `flank_pain_false` | -- | false | 0/54 | 0.0% | null 54 |
| `flank_pain_false:bead93da` | `flank_pain_false` | -- | false | 0/54 | 0.0% | null 54 |
| `flank_pain_false:924082ae` | `flank_pain_false` | -- | false | 0/52 | 0.0% | null 52 |
| `flank_pain_false:9ba1c8d3` | `flank_pain_false` | -- | false | 0/51 | 0.0% | null 51 |
| `flank_pain_false:d37c1465` | `flank_pain_false` | -- | false | 0/51 | 0.0% | null 51 |
| `flank_pain_true:faa371b2` | `flank_pain_true` | -- | true | 0/51 | 0.0% | null 51 |
| `flank_pain_false:132f591d` | `flank_pain_false` | -- | false | 0/50 | 0.0% | null 50 |
| `flank_pain_false:37373d48` | `flank_pain_false` | -- | false | 0/50 | 0.0% | null 50 |
| `flank_pain_false:4947dcd5` | `flank_pain_false` | -- | false | 0/50 | 0.0% | null 50 |
| `flank_pain_false:6c762141` | `flank_pain_false` | -- | false | 0/50 | 0.0% | null 50 |
| `flank_pain_false:9ed5cbe0` | `flank_pain_false` | -- | false | 0/49 | 0.0% | null 49 |
| `flank_pain_true:801b09f3` | `flank_pain_true` | -- | true | 0/49 | 0.0% | null 49 |
| `flank_pain_false:6f0b7381` | `flank_pain_false` | -- | false | 0/48 | 0.0% | null 48 |
| `flank_pain_false:7f0a359d` | `flank_pain_false` | -- | false | 0/48 | 0.0% | null 48 |
| `flank_pain_false:f63b22a5` | `flank_pain_false` | -- | false | 0/48 | 0.0% | null 48 |
| `flank_pain_false:3273a39a` | `flank_pain_false` | -- | false | 0/47 | 0.0% | null 47 |
| `flank_pain_false:6cd7f2f5` | `flank_pain_false` | -- | false | 0/47 | 0.0% | null 47 |
| `flank_pain_false:a31e1604` | `flank_pain_false` | -- | false | 0/47 | 0.0% | null 47 |
| `flank_pain_false:d7abb5ec` | `flank_pain_false` | -- | false | 0/47 | 0.0% | null 47 |
| `flank_pain_false:f900bfea` | `flank_pain_false` | -- | false | 0/46 | 0.0% | null 46 |
| `flank_pain_false:27c1ea49` | `flank_pain_false` | -- | false | 0/45 | 0.0% | null 45 |
| `flank_pain_false:0d8df7a0` | `flank_pain_false` | -- | false | 0/44 | 0.0% | null 44 |
| `flank_pain_false:57d966db` | `flank_pain_false` | -- | false | 0/44 | 0.0% | null 44 |
| `flank_pain_false:b27cde7b` | `flank_pain_false` | -- | false | 0/44 | 0.0% | null 44 |
| `flank_pain_true:78957d62` | `flank_pain_true` | -- | true | 0/44 | 0.0% | null 44 |
| `flank_pain_false:b4c43f30` | `flank_pain_false` | -- | false | 0/42 | 0.0% | null 42 |
| `flank_pain_true:568725bb` | `flank_pain_true` | -- | true | 0/42 | 0.0% | null 42 |
| `flank_pain_false:536a4cfe` | `flank_pain_false` | -- | false | 0/40 | 0.0% | null 40 |
| `flank_pain_false:69f1f2f7` | `flank_pain_false` | -- | false | 0/40 | 0.0% | null 40 |

*63 further fragments with at least one error are in the JSON sidecar; every fragment is there regardless of score.*

## `tfidf_logreg`

TF-IDF unigrams and bigrams into logistic regression. Tests whether the dataset is keyword-solvable. Its overall accuracy is close to uninformative; the `null_ambiguous` slice is the number that matters.

Decision-rule margins selected per fold (on each fold's own validation split): 0.0.
Every fold selected margin 0, so the ruled and raw views below are the same decisions. That is a finding rather than a bug: no margin improved macro-F1 without worsening the `null -> true` rate.

*Confusion matrix, raw argmax*

|  | pred false | pred true | pred null | total |
|---|---|---|---|---|
| **truth false** | 1505 | 56 | 918 | 2479 |
| **truth true** | 94 | 761 | 626 | 1481 |
| **truth null** | 126 | 133 | 5781 | 6040 |
| **total** | 1725 | 950 | 7325 | 10000 |

`null -> true`: 133 of 6040 truly-null examples (2.20%).

*Confusion matrix, after the decision rule*

|  | pred false | pred true | pred null | total |
|---|---|---|---|---|
| **truth false** | 1505 | 56 | 918 | 2479 |
| **truth true** | 94 | 761 | 626 | 1481 |
| **truth null** | 126 | 133 | 5781 | 6040 |
| **total** | 1725 | 950 | 7325 | 10000 |

`null -> true`: 133 of 6040 truly-null examples (2.20%).

### Per class, after the decision rule

| class | support | predicted | precision | recall | F1 |
|---|---|---|---|---|---|
| `false` | 2479 | 1725 | 87.2% | 60.7% | 71.6% |
| `true` | 1481 | 950 | 80.1% | 51.4% | 62.6% |
| `null` | 6040 | 7325 | 78.9% | 95.7% | 86.5% |

### By label mode

| label mode | n | eff n | accuracy [95% CI] |
|---|---|---|---|
| false | 2479 | **55** | 60.7% [50.3%, 71.1%] |
| null_ambiguous | 3062 | **140** | 91.7% [88.0%, 95.0%] |
| null_structural | 2978 | **1** | 99.8% [99.8%, 99.8%] |
| true | 1481 | **48** | 51.4% [40.1%, 63.3%] |

### By null sub-class

| sub-class | n | eff n | null recall [95% CI] |
|---|---|---|---|
| hedged | 1183 | **53** | 88.8% [81.8%, 94.8%] |
| historical | 868 | **40** | 91.4% [84.2%, 97.5%] |
| third_party | 1011 | **47** | 95.5% [90.6%, 99.1%] |

### By fragment library

| library | n | eff n | accuracy [95% CI] |
|---|---|---|---|
| flank_pain_false | 2479 | **55** | 60.7% [50.3%, 71.1%] |
| flank_pain_null_hedged | 1183 | **53** | 88.8% [81.8%, 94.8%] |
| flank_pain_null_historical | 868 | **40** | 91.4% [84.2%, 97.5%] |
| flank_pain_null_thirdparty | 1011 | **47** | 95.5% [90.6%, 99.1%] |
| flank_pain_true | 1481 | **48** | 51.4% [40.1%, 63.3%] |
| (none) | 2978 | **1** | 99.8% [99.8%, 99.8%] |

### Per-fragment errors (worst first)

Whether errors are spread thinly across many fragments or piled onto a few is the difference
between "the method is too weak" (model work) and "these specific ideas are not learnable from
the data we have" (library work, and these are the fragments to write more of). No intervals:
a fragment is one cluster, so an interval over its own examples measures nothing.

118 of 243 decisive fragments were got wrong at least once.

`tfidf_logreg`: 1948 errors across 118 of 243 decisive fragments. Half of them fall on **24** fragments (an even spread would be 59.0); the worst ten carry 26.4% of all errors.

| fragment | library | sub-class | truth | correct | accuracy | predicted as |
|---|---|---|---|---|---|---|
| `flank_pain_false:4d4ec138` | `flank_pain_false` | -- | false | 0/75 | 0.0% | null 75 |
| `flank_pain_false:bead93da` | `flank_pain_false` | -- | false | 0/54 | 0.0% | null 54 |
| `flank_pain_true:801b09f3` | `flank_pain_true` | -- | true | 0/49 | 0.0% | false 1, null 48 |
| `flank_pain_false:d7abb5ec` | `flank_pain_false` | -- | false | 0/47 | 0.0% | null 47 |
| `flank_pain_true:568725bb` | `flank_pain_true` | -- | true | 0/42 | 0.0% | null 42 |
| `flank_pain_true:ec43ab8c` | `flank_pain_true` | -- | true | 0/40 | 0.0% | false 23, null 17 |
| `flank_pain_true:47597ae1` | `flank_pain_true` | -- | true | 0/39 | 0.0% | null 39 |
| `flank_pain_true:a326ab18` | `flank_pain_true` | -- | true | 0/34 | 0.0% | false 2, null 32 |
| `flank_pain_true:720637db` | `flank_pain_true` | -- | true | 0/30 | 0.0% | null 30 |
| `flank_pain_false:b927c3ee` | `flank_pain_false` | -- | false | 0/29 | 0.0% | null 29 |
| `flank_pain_false:cbb11cce` | `flank_pain_false` | -- | false | 0/27 | 0.0% | null 27 |
| `flank_pain_true:be1f0c8f` | `flank_pain_true` | -- | true | 0/26 | 0.0% | false 3, null 23 |
| `flank_pain_false:1777a47f` | `flank_pain_false` | -- | false | 0/25 | 0.0% | null 25 |
| `flank_pain_true:cb7fde42` | `flank_pain_true` | -- | true | 0/19 | 0.0% | false 15, null 4 |
| `flank_pain_false:0468979b` | `flank_pain_false` | -- | false | 1/36 | 2.8% | false 1, null 35 |
| `flank_pain_true:d7d705f6` | `flank_pain_true` | -- | true | 1/36 | 2.8% | false 29, true 1, null 6 |
| `flank_pain_false:a2c9e38d` | `flank_pain_false` | -- | false | 2/63 | 3.2% | false 2, null 61 |
| `flank_pain_true:f0d12a02` | `flank_pain_true` | -- | true | 1/31 | 3.2% | false 1, true 1, null 29 |
| `flank_pain_false:6c762141` | `flank_pain_false` | -- | false | 2/50 | 4.0% | false 2, null 48 |
| `flank_pain_true:57ae6815` | `flank_pain_true` | -- | true | 1/22 | 4.5% | true 1, null 21 |
| `flank_pain_null_hedged:a6bdac0f` | `flank_pain_null_hedged` | hedged | null | 1/19 | 5.3% | true 18, null 1 |
| `flank_pain_null_hedged:d17ed4ab` | `flank_pain_null_hedged` | hedged | null | 1/17 | 5.9% | false 16, null 1 |
| `flank_pain_true:1dca9abd` | `flank_pain_true` | -- | true | 2/32 | 6.2% | false 4, true 2, null 26 |
| `flank_pain_true:990ffc20` | `flank_pain_true` | -- | true | 3/31 | 9.7% | true 3, null 28 |
| `flank_pain_false:d37c1465` | `flank_pain_false` | -- | false | 5/51 | 9.8% | false 5, true 22, null 24 |
| `flank_pain_true:79cde749` | `flank_pain_true` | -- | true | 2/20 | 10.0% | true 2, null 18 |
| `flank_pain_null_historical:c9da7977` | `flank_pain_null_historical` | historical | null | 2/19 | 10.5% | true 17, null 2 |
| `flank_pain_false:a7c193e8` | `flank_pain_false` | -- | false | 4/32 | 12.5% | false 4, null 28 |
| `flank_pain_null_hedged:2a3b1726` | `flank_pain_null_hedged` | hedged | null | 5/29 | 17.2% | true 24, null 5 |
| `flank_pain_false:0d8df7a0` | `flank_pain_false` | -- | false | 8/44 | 18.2% | false 8, null 36 |
| `flank_pain_null_thirdparty:d93c1422` | `flank_pain_null_thirdparty` | third_party | null | 4/22 | 18.2% | false 18, null 4 |
| `flank_pain_false:37373d48` | `flank_pain_false` | -- | false | 10/50 | 20.0% | false 10, null 40 |
| `flank_pain_true:b2b80fa1` | `flank_pain_true` | -- | true | 6/29 | 20.7% | true 6, null 23 |
| `flank_pain_false:4947dcd5` | `flank_pain_false` | -- | false | 11/50 | 22.0% | false 11, null 39 |
| `flank_pain_null_historical:68d1f572` | `flank_pain_null_historical` | historical | null | 6/26 | 23.1% | true 20, null 6 |
| `flank_pain_true:214c674e` | `flank_pain_true` | -- | true | 6/26 | 23.1% | false 2, true 6, null 18 |
| `flank_pain_true:a0c3fdbf` | `flank_pain_true` | -- | true | 8/33 | 24.2% | false 1, true 8, null 24 |
| `flank_pain_true:0d9a9389` | `flank_pain_true` | -- | true | 9/35 | 25.7% | false 1, true 9, null 25 |
| `flank_pain_null_hedged:73cf9df7` | `flank_pain_null_hedged` | hedged | null | 4/15 | 26.7% | true 11, null 4 |
| `flank_pain_false:f900bfea` | `flank_pain_false` | -- | false | 13/46 | 28.3% | false 13, null 33 |

*78 further fragments with at least one error are in the JSON sidecar; every fragment is there regardless of score.*

## `length_only__shuffled`

Logistic regression on token count alone. The direct measurable test of the length leak: anything materially above majority means text length is a usable proxy for the label, which is a fragment-library problem rather than a model one. **Negative control:** trained on permuted training labels (seed 7) and evaluated on the unpermuted test split, where it must land at chance.

Decision-rule margins selected per fold (on each fold's own validation split): 0.0.
Every fold selected margin 0, so the ruled and raw views below are the same decisions. That is a finding rather than a bug: no margin improved macro-F1 without worsening the `null -> true` rate.

*Confusion matrix, raw argmax*

|  | pred false | pred true | pred null | total |
|---|---|---|---|---|
| **truth false** | 0 | 0 | 2479 | 2479 |
| **truth true** | 0 | 0 | 1481 | 1481 |
| **truth null** | 0 | 0 | 6040 | 6040 |
| **total** | 0 | 0 | 10000 | 10000 |

`null -> true`: 0 of 6040 truly-null examples (0.00%).

*Confusion matrix, after the decision rule*

|  | pred false | pred true | pred null | total |
|---|---|---|---|---|
| **truth false** | 0 | 0 | 2479 | 2479 |
| **truth true** | 0 | 0 | 1481 | 1481 |
| **truth null** | 0 | 0 | 6040 | 6040 |
| **total** | 0 | 0 | 10000 | 10000 |

`null -> true`: 0 of 6040 truly-null examples (0.00%).

### Per class, after the decision rule

| class | support | predicted | precision | recall | F1 |
|---|---|---|---|---|---|
| `false` | 2479 | 0 | -- | 0.0% | 0.0% |
| `true` | 1481 | 0 | -- | 0.0% | 0.0% |
| `null` | 6040 | 10000 | 60.4% | 100.0% | 75.3% |

### By label mode

| label mode | n | eff n | accuracy [95% CI] |
|---|---|---|---|
| false | 2479 | **55** | 0.0% [0.0%, 0.0%] |
| null_ambiguous | 3062 | **140** | 100.0% [100.0%, 100.0%] |
| null_structural | 2978 | **1** | 100.0% [100.0%, 100.0%] |
| true | 1481 | **48** | 0.0% [0.0%, 0.0%] |

### By null sub-class

| sub-class | n | eff n | null recall [95% CI] |
|---|---|---|---|
| hedged | 1183 | **53** | 100.0% [100.0%, 100.0%] |
| historical | 868 | **40** | 100.0% [100.0%, 100.0%] |
| third_party | 1011 | **47** | 100.0% [100.0%, 100.0%] |

### By fragment library

| library | n | eff n | accuracy [95% CI] |
|---|---|---|---|
| flank_pain_false | 2479 | **55** | 0.0% [0.0%, 0.0%] |
| flank_pain_null_hedged | 1183 | **53** | 100.0% [100.0%, 100.0%] |
| flank_pain_null_historical | 868 | **40** | 100.0% [100.0%, 100.0%] |
| flank_pain_null_thirdparty | 1011 | **47** | 100.0% [100.0%, 100.0%] |
| flank_pain_true | 1481 | **48** | 0.0% [0.0%, 0.0%] |
| (none) | 2978 | **1** | 100.0% [100.0%, 100.0%] |

### Per-fragment errors (worst first)

Whether errors are spread thinly across many fragments or piled onto a few is the difference
between "the method is too weak" (model work) and "these specific ideas are not learnable from
the data we have" (library work, and these are the fragments to write more of). No intervals:
a fragment is one cluster, so an interval over its own examples measures nothing.

103 of 243 decisive fragments were got wrong at least once.

`length_only__shuffled`: 3960 errors across 103 of 243 decisive fragments. Half of them fall on **37** fragments (an even spread would be 51.5); the worst ten carry 17.0% of all errors.

| fragment | library | sub-class | truth | correct | accuracy | predicted as |
|---|---|---|---|---|---|---|
| `flank_pain_false:4782be93` | `flank_pain_false` | -- | false | 0/81 | 0.0% | null 81 |
| `flank_pain_false:80bb4b40` | `flank_pain_false` | -- | false | 0/76 | 0.0% | null 76 |
| `flank_pain_false:4d4ec138` | `flank_pain_false` | -- | false | 0/75 | 0.0% | null 75 |
| `flank_pain_false:7b34cfc0` | `flank_pain_false` | -- | false | 0/73 | 0.0% | null 73 |
| `flank_pain_false:9b1cee9c` | `flank_pain_false` | -- | false | 0/65 | 0.0% | null 65 |
| `flank_pain_false:a2c9e38d` | `flank_pain_false` | -- | false | 0/63 | 0.0% | null 63 |
| `flank_pain_false:76bc0785` | `flank_pain_false` | -- | false | 0/61 | 0.0% | null 61 |
| `flank_pain_false:71da3a84` | `flank_pain_false` | -- | false | 0/60 | 0.0% | null 60 |
| `flank_pain_false:be00686d` | `flank_pain_false` | -- | false | 0/60 | 0.0% | null 60 |
| `flank_pain_false:d439a7ee` | `flank_pain_false` | -- | false | 0/58 | 0.0% | null 58 |
| `flank_pain_false:42aa75a8` | `flank_pain_false` | -- | false | 0/57 | 0.0% | null 57 |
| `flank_pain_false:ad38bb4f` | `flank_pain_false` | -- | false | 0/54 | 0.0% | null 54 |
| `flank_pain_false:bead93da` | `flank_pain_false` | -- | false | 0/54 | 0.0% | null 54 |
| `flank_pain_false:924082ae` | `flank_pain_false` | -- | false | 0/52 | 0.0% | null 52 |
| `flank_pain_false:9ba1c8d3` | `flank_pain_false` | -- | false | 0/51 | 0.0% | null 51 |
| `flank_pain_false:d37c1465` | `flank_pain_false` | -- | false | 0/51 | 0.0% | null 51 |
| `flank_pain_true:faa371b2` | `flank_pain_true` | -- | true | 0/51 | 0.0% | null 51 |
| `flank_pain_false:132f591d` | `flank_pain_false` | -- | false | 0/50 | 0.0% | null 50 |
| `flank_pain_false:37373d48` | `flank_pain_false` | -- | false | 0/50 | 0.0% | null 50 |
| `flank_pain_false:4947dcd5` | `flank_pain_false` | -- | false | 0/50 | 0.0% | null 50 |
| `flank_pain_false:6c762141` | `flank_pain_false` | -- | false | 0/50 | 0.0% | null 50 |
| `flank_pain_false:9ed5cbe0` | `flank_pain_false` | -- | false | 0/49 | 0.0% | null 49 |
| `flank_pain_true:801b09f3` | `flank_pain_true` | -- | true | 0/49 | 0.0% | null 49 |
| `flank_pain_false:6f0b7381` | `flank_pain_false` | -- | false | 0/48 | 0.0% | null 48 |
| `flank_pain_false:7f0a359d` | `flank_pain_false` | -- | false | 0/48 | 0.0% | null 48 |
| `flank_pain_false:f63b22a5` | `flank_pain_false` | -- | false | 0/48 | 0.0% | null 48 |
| `flank_pain_false:3273a39a` | `flank_pain_false` | -- | false | 0/47 | 0.0% | null 47 |
| `flank_pain_false:6cd7f2f5` | `flank_pain_false` | -- | false | 0/47 | 0.0% | null 47 |
| `flank_pain_false:a31e1604` | `flank_pain_false` | -- | false | 0/47 | 0.0% | null 47 |
| `flank_pain_false:d7abb5ec` | `flank_pain_false` | -- | false | 0/47 | 0.0% | null 47 |
| `flank_pain_false:f900bfea` | `flank_pain_false` | -- | false | 0/46 | 0.0% | null 46 |
| `flank_pain_false:27c1ea49` | `flank_pain_false` | -- | false | 0/45 | 0.0% | null 45 |
| `flank_pain_false:0d8df7a0` | `flank_pain_false` | -- | false | 0/44 | 0.0% | null 44 |
| `flank_pain_false:57d966db` | `flank_pain_false` | -- | false | 0/44 | 0.0% | null 44 |
| `flank_pain_false:b27cde7b` | `flank_pain_false` | -- | false | 0/44 | 0.0% | null 44 |
| `flank_pain_true:78957d62` | `flank_pain_true` | -- | true | 0/44 | 0.0% | null 44 |
| `flank_pain_false:b4c43f30` | `flank_pain_false` | -- | false | 0/42 | 0.0% | null 42 |
| `flank_pain_true:568725bb` | `flank_pain_true` | -- | true | 0/42 | 0.0% | null 42 |
| `flank_pain_false:536a4cfe` | `flank_pain_false` | -- | false | 0/40 | 0.0% | null 40 |
| `flank_pain_false:69f1f2f7` | `flank_pain_false` | -- | false | 0/40 | 0.0% | null 40 |

*63 further fragments with at least one error are in the JSON sidecar; every fragment is there regardless of score.*

## `tfidf_logreg__shuffled`

TF-IDF unigrams and bigrams into logistic regression. Tests whether the dataset is keyword-solvable. Its overall accuracy is close to uninformative; the `null_ambiguous` slice is the number that matters. **Negative control:** trained on permuted training labels (seed 7) and evaluated on the unpermuted test split, where it must land at chance.

Decision-rule margins selected per fold (on each fold's own validation split): 0.0.
Every fold selected margin 0, so the ruled and raw views below are the same decisions. That is a finding rather than a bug: no margin improved macro-F1 without worsening the `null -> true` rate.

*Confusion matrix, raw argmax*

|  | pred false | pred true | pred null | total |
|---|---|---|---|---|
| **truth false** | 0 | 0 | 2479 | 2479 |
| **truth true** | 0 | 0 | 1481 | 1481 |
| **truth null** | 1 | 0 | 6039 | 6040 |
| **total** | 1 | 0 | 9999 | 10000 |

`null -> true`: 0 of 6040 truly-null examples (0.00%).

*Confusion matrix, after the decision rule*

|  | pred false | pred true | pred null | total |
|---|---|---|---|---|
| **truth false** | 0 | 0 | 2479 | 2479 |
| **truth true** | 0 | 0 | 1481 | 1481 |
| **truth null** | 1 | 0 | 6039 | 6040 |
| **total** | 1 | 0 | 9999 | 10000 |

`null -> true`: 0 of 6040 truly-null examples (0.00%).

### Per class, after the decision rule

| class | support | predicted | precision | recall | F1 |
|---|---|---|---|---|---|
| `false` | 2479 | 1 | 0.0% | 0.0% | 0.0% |
| `true` | 1481 | 0 | -- | 0.0% | 0.0% |
| `null` | 6040 | 9999 | 60.4% | 100.0% | 75.3% |

### By label mode

| label mode | n | eff n | accuracy [95% CI] |
|---|---|---|---|
| false | 2479 | **55** | 0.0% [0.0%, 0.0%] |
| null_ambiguous | 3062 | **140** | 100.0% [99.9%, 100.0%] |
| null_structural | 2978 | **1** | 100.0% [100.0%, 100.0%] |
| true | 1481 | **48** | 0.0% [0.0%, 0.0%] |

### By null sub-class

| sub-class | n | eff n | null recall [95% CI] |
|---|---|---|---|
| hedged | 1183 | **53** | 99.9% [99.7%, 100.0%] |
| historical | 868 | **40** | 100.0% [100.0%, 100.0%] |
| third_party | 1011 | **47** | 100.0% [100.0%, 100.0%] |

### By fragment library

| library | n | eff n | accuracy [95% CI] |
|---|---|---|---|
| flank_pain_false | 2479 | **55** | 0.0% [0.0%, 0.0%] |
| flank_pain_null_hedged | 1183 | **53** | 99.9% [99.7%, 100.0%] |
| flank_pain_null_historical | 868 | **40** | 100.0% [100.0%, 100.0%] |
| flank_pain_null_thirdparty | 1011 | **47** | 100.0% [100.0%, 100.0%] |
| flank_pain_true | 1481 | **48** | 0.0% [0.0%, 0.0%] |
| (none) | 2978 | **1** | 100.0% [100.0%, 100.0%] |

### Per-fragment errors (worst first)

Whether errors are spread thinly across many fragments or piled onto a few is the difference
between "the method is too weak" (model work) and "these specific ideas are not learnable from
the data we have" (library work, and these are the fragments to write more of). No intervals:
a fragment is one cluster, so an interval over its own examples measures nothing.

104 of 243 decisive fragments were got wrong at least once.

`tfidf_logreg__shuffled`: 3961 errors across 104 of 243 decisive fragments. Half of them fall on **37** fragments (an even spread would be 52.0); the worst ten carry 17.0% of all errors.

| fragment | library | sub-class | truth | correct | accuracy | predicted as |
|---|---|---|---|---|---|---|
| `flank_pain_false:4782be93` | `flank_pain_false` | -- | false | 0/81 | 0.0% | null 81 |
| `flank_pain_false:80bb4b40` | `flank_pain_false` | -- | false | 0/76 | 0.0% | null 76 |
| `flank_pain_false:4d4ec138` | `flank_pain_false` | -- | false | 0/75 | 0.0% | null 75 |
| `flank_pain_false:7b34cfc0` | `flank_pain_false` | -- | false | 0/73 | 0.0% | null 73 |
| `flank_pain_false:9b1cee9c` | `flank_pain_false` | -- | false | 0/65 | 0.0% | null 65 |
| `flank_pain_false:a2c9e38d` | `flank_pain_false` | -- | false | 0/63 | 0.0% | null 63 |
| `flank_pain_false:76bc0785` | `flank_pain_false` | -- | false | 0/61 | 0.0% | null 61 |
| `flank_pain_false:71da3a84` | `flank_pain_false` | -- | false | 0/60 | 0.0% | null 60 |
| `flank_pain_false:be00686d` | `flank_pain_false` | -- | false | 0/60 | 0.0% | null 60 |
| `flank_pain_false:d439a7ee` | `flank_pain_false` | -- | false | 0/58 | 0.0% | null 58 |
| `flank_pain_false:42aa75a8` | `flank_pain_false` | -- | false | 0/57 | 0.0% | null 57 |
| `flank_pain_false:ad38bb4f` | `flank_pain_false` | -- | false | 0/54 | 0.0% | null 54 |
| `flank_pain_false:bead93da` | `flank_pain_false` | -- | false | 0/54 | 0.0% | null 54 |
| `flank_pain_false:924082ae` | `flank_pain_false` | -- | false | 0/52 | 0.0% | null 52 |
| `flank_pain_false:9ba1c8d3` | `flank_pain_false` | -- | false | 0/51 | 0.0% | null 51 |
| `flank_pain_false:d37c1465` | `flank_pain_false` | -- | false | 0/51 | 0.0% | null 51 |
| `flank_pain_true:faa371b2` | `flank_pain_true` | -- | true | 0/51 | 0.0% | null 51 |
| `flank_pain_false:132f591d` | `flank_pain_false` | -- | false | 0/50 | 0.0% | null 50 |
| `flank_pain_false:37373d48` | `flank_pain_false` | -- | false | 0/50 | 0.0% | null 50 |
| `flank_pain_false:4947dcd5` | `flank_pain_false` | -- | false | 0/50 | 0.0% | null 50 |
| `flank_pain_false:6c762141` | `flank_pain_false` | -- | false | 0/50 | 0.0% | null 50 |
| `flank_pain_false:9ed5cbe0` | `flank_pain_false` | -- | false | 0/49 | 0.0% | null 49 |
| `flank_pain_true:801b09f3` | `flank_pain_true` | -- | true | 0/49 | 0.0% | null 49 |
| `flank_pain_false:6f0b7381` | `flank_pain_false` | -- | false | 0/48 | 0.0% | null 48 |
| `flank_pain_false:7f0a359d` | `flank_pain_false` | -- | false | 0/48 | 0.0% | null 48 |
| `flank_pain_false:f63b22a5` | `flank_pain_false` | -- | false | 0/48 | 0.0% | null 48 |
| `flank_pain_false:3273a39a` | `flank_pain_false` | -- | false | 0/47 | 0.0% | null 47 |
| `flank_pain_false:6cd7f2f5` | `flank_pain_false` | -- | false | 0/47 | 0.0% | null 47 |
| `flank_pain_false:a31e1604` | `flank_pain_false` | -- | false | 0/47 | 0.0% | null 47 |
| `flank_pain_false:d7abb5ec` | `flank_pain_false` | -- | false | 0/47 | 0.0% | null 47 |
| `flank_pain_false:f900bfea` | `flank_pain_false` | -- | false | 0/46 | 0.0% | null 46 |
| `flank_pain_false:27c1ea49` | `flank_pain_false` | -- | false | 0/45 | 0.0% | null 45 |
| `flank_pain_false:0d8df7a0` | `flank_pain_false` | -- | false | 0/44 | 0.0% | null 44 |
| `flank_pain_false:57d966db` | `flank_pain_false` | -- | false | 0/44 | 0.0% | null 44 |
| `flank_pain_false:b27cde7b` | `flank_pain_false` | -- | false | 0/44 | 0.0% | null 44 |
| `flank_pain_true:78957d62` | `flank_pain_true` | -- | true | 0/44 | 0.0% | null 44 |
| `flank_pain_false:b4c43f30` | `flank_pain_false` | -- | false | 0/42 | 0.0% | null 42 |
| `flank_pain_true:568725bb` | `flank_pain_true` | -- | true | 0/42 | 0.0% | null 42 |
| `flank_pain_false:536a4cfe` | `flank_pain_false` | -- | false | 0/40 | 0.0% | null 40 |
| `flank_pain_false:69f1f2f7` | `flank_pain_false` | -- | false | 0/40 | 0.0% | null 40 |

*64 further fragments with at least one error are in the JSON sidecar; every fragment is there regardless of score.*

## `arm_b_finetune@c0.0-d0.0`

`roberta-base` with **every layer unfrozen**, mean-pooled, with the same `Linear(768, 3)` head -- 110M trainable parameters against Arm A's 2,307. Three epochs at batch 32, learning rate 2e-5, 10% linear warmup, AdamW, fp32. No gradient checkpointing, no 8-bit optimiser, no LoRA, no gradient accumulation: the full model fits in 12GB with room to spare, so anything that reads like a compute compromise would be a mistake rather than a saving. This is the arm that separates "the fragment libraries are the bottleneck" from "the method is too weak": if a fully fine-tuned encoder still cannot read third-party attribution, tense or metaphor, the limit is in the ideas the libraries contain and the fix is library work, not model work.

Decision-rule margins selected per fold (on each fold's own validation split): 0.0, 0.8, 0.85.

*Confusion matrix, raw argmax*

|  | pred false | pred true | pred null | total |
|---|---|---|---|---|
| **truth false** | 2373 | 5 | 101 | 2479 |
| **truth true** | 18 | 1422 | 41 | 1481 |
| **truth null** | 42 | 169 | 5829 | 6040 |
| **total** | 2433 | 1596 | 5971 | 10000 |

`null -> true`: 169 of 6040 truly-null examples (2.80%).

*Confusion matrix, after the decision rule*

|  | pred false | pred true | pred null | total |
|---|---|---|---|---|
| **truth false** | 2374 | 3 | 102 | 2479 |
| **truth true** | 18 | 1422 | 41 | 1481 |
| **truth null** | 42 | 156 | 5842 | 6040 |
| **total** | 2434 | 1581 | 5985 | 10000 |

`null -> true`: 156 of 6040 truly-null examples (2.58%).

### Per class, after the decision rule

| class | support | predicted | precision | recall | F1 |
|---|---|---|---|---|---|
| `false` | 2479 | 2434 | 97.5% | 95.8% | 96.6% |
| `true` | 1481 | 1581 | 89.9% | 96.0% | 92.9% |
| `null` | 6040 | 5985 | 97.6% | 96.7% | 97.2% |

### By label mode

| label mode | n | eff n | accuracy [95% CI] |
|---|---|---|---|
| false | 2479 | **55** | 95.8% [89.3%, 100.0%] |
| null_ambiguous | 3062 | **140** | 93.7% [89.7%, 97.1%] |
| null_structural | 2978 | **1** | 99.9% [99.9%, 99.9%] |
| true | 1481 | **48** | 96.0% [91.6%, 99.3%] |

### By null sub-class

| sub-class | n | eff n | null recall [95% CI] |
|---|---|---|---|
| hedged | 1183 | **53** | 89.3% [80.8%, 96.4%] |
| historical | 868 | **40** | 93.1% [85.2%, 100.0%] |
| third_party | 1011 | **47** | 99.3% [97.9%, 100.0%] |

### By fragment library

| library | n | eff n | accuracy [95% CI] |
|---|---|---|---|
| flank_pain_false | 2479 | **55** | 95.8% [89.3%, 100.0%] |
| flank_pain_null_hedged | 1183 | **53** | 89.3% [80.8%, 96.4%] |
| flank_pain_null_historical | 868 | **40** | 93.1% [85.2%, 100.0%] |
| flank_pain_null_thirdparty | 1011 | **47** | 99.3% [97.9%, 100.0%] |
| flank_pain_true | 1481 | **48** | 96.0% [91.6%, 99.3%] |
| (none) | 2978 | **1** | 99.9% [99.9%, 99.9%] |

### Per-fragment errors (worst first)

Whether errors are spread thinly across many fragments or piled onto a few is the difference
between "the method is too weak" (model work) and "these specific ideas are not learnable from
the data we have" (library work, and these are the fragments to write more of). No intervals:
a fragment is one cluster, so an interval over its own examples measures nothing.

28 of 243 decisive fragments were got wrong at least once.

`arm_b_finetune@c0.0-d0.0`: 358 errors across 28 of 243 decisive fragments. Half of them fall on **6** fragments (an even spread would be 14.0); the worst ten carry 75.7% of all errors.

| fragment | library | sub-class | truth | correct | accuracy | predicted as |
|---|---|---|---|---|---|---|
| `flank_pain_false:bead93da` | `flank_pain_false` | -- | false | 0/54 | 0.0% | null 54 |
| `flank_pain_false:d7abb5ec` | `flank_pain_false` | -- | false | 0/47 | 0.0% | null 47 |
| `flank_pain_null_hedged:d9678a20` | `flank_pain_null_hedged` | hedged | null | 0/28 | 0.0% | true 28 |
| `flank_pain_null_hedged:0f9ee32b` | `flank_pain_null_hedged` | hedged | null | 0/25 | 0.0% | false 25 |
| `flank_pain_null_historical:1d821bf1` | `flank_pain_null_historical` | historical | null | 0/24 | 0.0% | true 24 |
| `flank_pain_null_hedged:b06aa9b7` | `flank_pain_null_hedged` | hedged | null | 0/20 | 0.0% | true 20 |
| `flank_pain_null_historical:c9da7977` | `flank_pain_null_historical` | historical | null | 0/19 | 0.0% | true 19 |
| `flank_pain_true:cb7fde42` | `flank_pain_true` | -- | true | 0/19 | 0.0% | null 19 |
| `flank_pain_null_hedged:d17ed4ab` | `flank_pain_null_hedged` | hedged | null | 1/17 | 5.9% | true 16, null 1 |
| `flank_pain_null_hedged:73cf9df7` | `flank_pain_null_hedged` | hedged | null | 4/15 | 26.7% | true 11, null 4 |
| `flank_pain_true:214c674e` | `flank_pain_true` | -- | true | 8/26 | 30.8% | false 18, true 8 |
| `flank_pain_null_historical:e5af2cf0` | `flank_pain_null_historical` | historical | null | 13/30 | 43.3% | true 17, null 13 |
| `flank_pain_null_hedged:480834dd` | `flank_pain_null_hedged` | hedged | null | 9/18 | 50.0% | true 9, null 9 |
| `flank_pain_null_hedged:7142f310` | `flank_pain_null_hedged` | hedged | null | 17/26 | 65.4% | false 9, null 17 |
| `flank_pain_true:d7d705f6` | `flank_pain_true` | -- | true | 26/36 | 72.2% | true 26, null 10 |
| `flank_pain_null_thirdparty:903a529b` | `flank_pain_null_thirdparty` | third_party | null | 19/26 | 73.1% | true 7, null 19 |
| `flank_pain_true:801b09f3` | `flank_pain_true` | -- | true | 41/49 | 83.7% | true 41, null 8 |
| `flank_pain_null_hedged:ffd17ec9` | `flank_pain_null_hedged` | hedged | null | 14/16 | 87.5% | false 2, null 14 |
| `flank_pain_true:be1f0c8f` | `flank_pain_true` | -- | true | 23/26 | 88.5% | true 23, null 3 |
| `flank_pain_false:cbb11cce` | `flank_pain_false` | -- | false | 24/27 | 88.9% | false 24, true 2, null 1 |
| `flank_pain_null_hedged:212f7bbf` | `flank_pain_null_hedged` | hedged | null | 23/25 | 92.0% | true 2, null 23 |
| `flank_pain_null_hedged:89d3997c` | `flank_pain_null_hedged` | hedged | null | 15/16 | 93.8% | false 1, null 15 |
| `flank_pain_null_hedged:c6ee7ef4` | `flank_pain_null_hedged` | hedged | null | 20/21 | 95.2% | false 1, null 20 |
| `flank_pain_null_hedged:dbe527b2` | `flank_pain_null_hedged` | hedged | null | 21/22 | 95.5% | true 1, null 21 |
| `flank_pain_null_hedged:bbcf908d` | `flank_pain_null_hedged` | hedged | null | 28/29 | 96.6% | true 1, null 28 |
| `flank_pain_null_hedged:2dedf8a9` | `flank_pain_null_hedged` | hedged | null | 29/30 | 96.7% | true 1, null 29 |
| `flank_pain_true:19e39218` | `flank_pain_true` | -- | true | 36/37 | 97.3% | true 36, null 1 |
| `flank_pain_false:f63b22a5` | `flank_pain_false` | -- | false | 47/48 | 97.9% | false 47, true 1 |

## `arm_b_finetune@c0.0-d0.3`

`roberta-base` with **every layer unfrozen**, mean-pooled, with the same `Linear(768, 3)` head -- 110M trainable parameters against Arm A's 2,307. Three epochs at batch 32, learning rate 2e-5, 10% linear warmup, AdamW, fp32. No gradient checkpointing, no 8-bit optimiser, no LoRA, no gradient accumulation: the full model fits in 12GB with room to spare, so anything that reads like a compute compromise would be a mistake rather than a saving. This is the arm that separates "the fragment libraries are the bottleneck" from "the method is too weak": if a fully fine-tuned encoder still cannot read third-party attribution, tense or metaphor, the limit is in the ideas the libraries contain and the fix is library work, not model work.

Decision-rule margins selected per fold (on each fold's own validation split): 0.0, 0.1, 0.75, 0.85, 0.9.

*Confusion matrix, raw argmax*

|  | pred false | pred true | pred null | total |
|---|---|---|---|---|
| **truth false** | 2417 | 0 | 62 | 2479 |
| **truth true** | 2 | 1459 | 20 | 1481 |
| **truth null** | 26 | 70 | 5944 | 6040 |
| **total** | 2445 | 1529 | 6026 | 10000 |

`null -> true`: 70 of 6040 truly-null examples (1.16%).

*Confusion matrix, after the decision rule*

|  | pred false | pred true | pred null | total |
|---|---|---|---|---|
| **truth false** | 2417 | 0 | 62 | 2479 |
| **truth true** | 3 | 1452 | 26 | 1481 |
| **truth null** | 26 | 58 | 5956 | 6040 |
| **total** | 2446 | 1510 | 6044 | 10000 |

`null -> true`: 58 of 6040 truly-null examples (0.96%).

### Per class, after the decision rule

| class | support | predicted | precision | recall | F1 |
|---|---|---|---|---|---|
| `false` | 2479 | 2446 | 98.8% | 97.5% | 98.2% |
| `true` | 1481 | 1510 | 96.2% | 98.0% | 97.1% |
| `null` | 6040 | 6044 | 98.5% | 98.6% | 98.6% |

### By label mode

| label mode | n | eff n | accuracy [95% CI] |
|---|---|---|---|
| false | 2479 | **131** | 97.5% [93.5%, 100.0%] |
| null_ambiguous | 3062 | **140** | 97.3% [94.9%, 99.3%] |
| null_structural | 2978 | **1** | 99.9% [99.9%, 99.9%] |
| true | 1481 | **129** | 98.0% [95.7%, 99.7%] |

### By null sub-class

| sub-class | n | eff n | null recall [95% CI] |
|---|---|---|---|
| hedged | 1183 | **53** | 94.1% [88.1%, 98.6%] |
| historical | 868 | **40** | 99.4% [98.2%, 100.0%] |
| third_party | 1011 | **47** | 99.3% [98.2%, 100.0%] |

### By fragment library

| library | n | eff n | accuracy [95% CI] |
|---|---|---|---|
| declarative_v1 | 1234 | **157** | 100.0% [100.0%, 100.0%] |
| flank_pain_false | 1707 | **55** | 96.4% [90.6%, 100.0%] |
| flank_pain_null_hedged | 1183 | **53** | 94.1% [88.1%, 98.6%] |
| flank_pain_null_historical | 868 | **40** | 99.4% [98.2%, 100.0%] |
| flank_pain_null_thirdparty | 1011 | **47** | 99.3% [98.2%, 100.0%] |
| flank_pain_true | 1019 | **48** | 97.2% [93.4%, 99.5%] |
| (none) | 2978 | **1** | 99.9% [99.9%, 99.9%] |

### Per-fragment errors (worst first)

Whether errors are spread thinly across many fragments or piled onto a few is the difference
between "the method is too weak" (model work) and "these specific ideas are not learnable from
the data we have" (library work, and these are the fragments to write more of). No intervals:
a fragment is one cluster, so an interval over its own examples measures nothing.

20 of 655 decisive fragments were got wrong at least once.

`arm_b_finetune@c0.0-d0.3`: 173 errors across 20 of 655 decisive fragments. Half of them fall on **4** fragments (an even spread would be 10.0); the worst ten carry 90.2% of all errors.

| fragment | library | sub-class | truth | correct | accuracy | predicted as |
|---|---|---|---|---|---|---|
| `flank_pain_false:bead93da` | `flank_pain_false` | -- | false | 0/32 | 0.0% | null 32 |
| `flank_pain_false:d7abb5ec` | `flank_pain_false` | -- | false | 0/30 | 0.0% | null 30 |
| `flank_pain_null_hedged:480834dd` | `flank_pain_null_hedged` | hedged | null | 0/18 | 0.0% | true 18 |
| `flank_pain_true:cb7fde42` | `flank_pain_true` | -- | true | 0/14 | 0.0% | null 14 |
| `flank_pain_null_hedged:0f9ee32b` | `flank_pain_null_hedged` | hedged | null | 1/25 | 4.0% | false 24, null 1 |
| `flank_pain_null_hedged:73cf9df7` | `flank_pain_null_hedged` | hedged | null | 4/15 | 26.7% | true 11, null 4 |
| `flank_pain_true:b2b80fa1` | `flank_pain_true` | -- | true | 16/23 | 69.6% | true 16, null 7 |
| `flank_pain_null_hedged:d9678a20` | `flank_pain_null_hedged` | hedged | null | 20/28 | 71.4% | true 8, null 20 |
| `flank_pain_null_hedged:52c46ca3` | `flank_pain_null_hedged` | hedged | null | 19/26 | 73.1% | true 7, null 19 |
| `flank_pain_null_thirdparty:d93c1422` | `flank_pain_null_thirdparty` | third_party | null | 17/22 | 77.3% | true 5, null 17 |
| `flank_pain_null_historical:1d821bf1` | `flank_pain_null_historical` | historical | null | 19/24 | 79.2% | true 5, null 19 |
| `flank_pain_true:801b09f3` | `flank_pain_true` | -- | true | 26/29 | 89.7% | false 1, true 26, null 2 |
| `flank_pain_true:214c674e` | `flank_pain_true` | -- | true | 20/22 | 90.9% | false 2, true 20 |
| `flank_pain_null_hedged:e5013045` | `flank_pain_null_hedged` | hedged | null | 14/15 | 93.3% | true 1, null 14 |
| `flank_pain_true:a50a0907` | `flank_pain_true` | -- | true | 14/15 | 93.3% | true 14, null 1 |
| `flank_pain_null_thirdparty:1b323aa4` | `flank_pain_null_thirdparty` | third_party | null | 17/18 | 94.4% | true 1, null 17 |
| `flank_pain_true:a326ab18` | `flank_pain_true` | -- | true | 22/23 | 95.7% | true 22, null 1 |
| `flank_pain_true:19e39218` | `flank_pain_true` | -- | true | 23/24 | 95.8% | true 23, null 1 |
| `flank_pain_null_hedged:d0b42e86` | `flank_pain_null_hedged` | hedged | null | 25/26 | 96.2% | true 1, null 25 |
| `flank_pain_null_thirdparty:903a529b` | `flank_pain_null_thirdparty` | third_party | null | 25/26 | 96.2% | true 1, null 25 |

## `arm_b_finetune@c0.5-d0.0`

`roberta-base` with **every layer unfrozen**, mean-pooled, with the same `Linear(768, 3)` head -- 110M trainable parameters against Arm A's 2,307. Three epochs at batch 32, learning rate 2e-5, 10% linear warmup, AdamW, fp32. No gradient checkpointing, no 8-bit optimiser, no LoRA, no gradient accumulation: the full model fits in 12GB with room to spare, so anything that reads like a compute compromise would be a mistake rather than a saving. This is the arm that separates "the fragment libraries are the bottleneck" from "the method is too weak": if a fully fine-tuned encoder still cannot read third-party attribution, tense or metaphor, the limit is in the ideas the libraries contain and the fix is library work, not model work.

Decision-rule margins selected per fold (on each fold's own validation split): 0.0, 0.25, 0.65, 0.8.

*Confusion matrix, raw argmax*

|  | pred false | pred true | pred null | total |
|---|---|---|---|---|
| **truth false** | 2185 | 55 | 239 | 2479 |
| **truth true** | 3 | 1384 | 94 | 1481 |
| **truth null** | 89 | 88 | 5863 | 6040 |
| **total** | 2277 | 1527 | 6196 | 10000 |

`null -> true`: 88 of 6040 truly-null examples (1.46%).

*Confusion matrix, after the decision rule*

|  | pred false | pred true | pred null | total |
|---|---|---|---|---|
| **truth false** | 2188 | 51 | 240 | 2479 |
| **truth true** | 3 | 1380 | 98 | 1481 |
| **truth null** | 101 | 73 | 5866 | 6040 |
| **total** | 2292 | 1504 | 6204 | 10000 |

`null -> true`: 73 of 6040 truly-null examples (1.21%).

### Per class, after the decision rule

| class | support | predicted | precision | recall | F1 |
|---|---|---|---|---|---|
| `false` | 2479 | 2292 | 95.5% | 88.3% | 91.7% |
| `true` | 1481 | 1504 | 91.8% | 93.2% | 92.5% |
| `null` | 6040 | 6204 | 94.6% | 97.1% | 95.8% |

### By label mode

| label mode | n | eff n | accuracy [95% CI] |
|---|---|---|---|
| false | 2479 | **55** | 88.3% [79.3%, 95.4%] |
| null_ambiguous | 3062 | **140** | 94.6% [90.9%, 97.7%] |
| null_structural | 2978 | **1** | 99.7% [99.7%, 99.7%] |
| true | 1481 | **48** | 93.2% [87.0%, 98.1%] |

### By null sub-class

| sub-class | n | eff n | null recall [95% CI] |
|---|---|---|---|
| hedged | 1178 | **53** | 90.0% [81.3%, 97.0%] |
| historical | 869 | **40** | 99.8% [99.4%, 100.0%] |
| third_party | 1015 | **47** | 95.5% [90.2%, 99.3%] |

### By fragment library

| library | n | eff n | accuracy [95% CI] |
|---|---|---|---|
| flank_pain_false | 2479 | **55** | 88.3% [79.3%, 95.4%] |
| flank_pain_null_hedged | 1178 | **53** | 90.0% [81.3%, 97.0%] |
| flank_pain_null_historical | 869 | **40** | 99.8% [99.4%, 100.0%] |
| flank_pain_null_thirdparty | 1015 | **47** | 95.5% [90.2%, 99.3%] |
| flank_pain_true | 1481 | **48** | 93.2% [87.0%, 98.1%] |
| (none) | 2978 | **1** | 99.7% [99.7%, 99.7%] |

### Per-fragment errors (worst first)

Whether errors are spread thinly across many fragments or piled onto a few is the difference
between "the method is too weak" (model work) and "these specific ideas are not learnable from
the data we have" (library work, and these are the fragments to write more of). No intervals:
a fragment is one cluster, so an interval over its own examples measures nothing.

46 of 243 decisive fragments were got wrong at least once.

`arm_b_finetune@c0.5-d0.0`: 558 errors across 46 of 243 decisive fragments. Half of them fall on **7** fragments (an even spread would be 23.0); the worst ten carry 64.9% of all errors.

| fragment | library | sub-class | truth | correct | accuracy | predicted as |
|---|---|---|---|---|---|---|
| `flank_pain_false:bead93da` | `flank_pain_false` | -- | false | 0/55 | 0.0% | null 55 |
| `flank_pain_false:d7abb5ec` | `flank_pain_false` | -- | false | 0/48 | 0.0% | null 48 |
| `flank_pain_false:0468979b` | `flank_pain_false` | -- | false | 0/37 | 0.0% | null 37 |
| `flank_pain_null_hedged:d9678a20` | `flank_pain_null_hedged` | hedged | null | 0/28 | 0.0% | true 28 |
| `flank_pain_true:cb7fde42` | `flank_pain_true` | -- | true | 0/20 | 0.0% | null 20 |
| `flank_pain_null_hedged:73cf9df7` | `flank_pain_null_hedged` | hedged | null | 0/16 | 0.0% | true 16 |
| `flank_pain_false:3273a39a` | `flank_pain_false` | -- | false | 1/50 | 2.0% | false 1, null 49 |
| `flank_pain_false:cbb11cce` | `flank_pain_false` | -- | false | 1/27 | 3.7% | false 1, true 25, null 1 |
| `flank_pain_null_hedged:d0b42e86` | `flank_pain_null_hedged` | hedged | null | 2/28 | 7.1% | false 26, null 2 |
| `flank_pain_true:214c674e` | `flank_pain_true` | -- | true | 2/25 | 8.0% | true 2, null 23 |
| `flank_pain_false:f900bfea` | `flank_pain_false` | -- | false | 4/48 | 8.3% | false 4, null 44 |
| `flank_pain_null_thirdparty:d93c1422` | `flank_pain_null_thirdparty` | third_party | null | 2/23 | 8.7% | false 15, true 6, null 2 |
| `flank_pain_true:b2b80fa1` | `flank_pain_true` | -- | true | 4/30 | 13.3% | true 4, null 26 |
| `flank_pain_null_hedged:1ee3ae69` | `flank_pain_null_hedged` | hedged | null | 4/22 | 18.2% | false 18, null 4 |
| `flank_pain_null_hedged:7142f310` | `flank_pain_null_hedged` | hedged | null | 5/25 | 20.0% | false 20, null 5 |
| `flank_pain_null_thirdparty:903a529b` | `flank_pain_null_thirdparty` | third_party | null | 8/23 | 34.8% | true 15, null 8 |
| `flank_pain_true:47597ae1` | `flank_pain_true` | -- | true | 20/40 | 50.0% | false 1, true 20, null 19 |
| `flank_pain_false:d37c1465` | `flank_pain_false` | -- | false | 36/52 | 69.2% | false 36, true 16 |
| `flank_pain_false:b927c3ee` | `flank_pain_false` | -- | false | 23/29 | 79.3% | false 23, null 6 |
| `flank_pain_false:f63b22a5` | `flank_pain_false` | -- | false | 40/47 | 85.1% | false 40, true 7 |
| `flank_pain_null_hedged:c51392ca` | `flank_pain_null_hedged` | hedged | null | 18/21 | 85.7% | false 3, null 18 |
| `flank_pain_null_thirdparty:a3f0cb47` | `flank_pain_null_thirdparty` | third_party | null | 21/24 | 87.5% | false 3, null 21 |
| `flank_pain_null_hedged:d17ed4ab` | `flank_pain_null_hedged` | hedged | null | 15/17 | 88.2% | false 1, true 1, null 15 |
| `flank_pain_true:37a629d7` | `flank_pain_true` | -- | true | 32/36 | 88.9% | true 32, null 4 |
| `flank_pain_true:a326ab18` | `flank_pain_true` | -- | true | 30/33 | 90.9% | false 1, true 30, null 2 |
| `flank_pain_null_thirdparty:60736399` | `flank_pain_null_thirdparty` | third_party | null | 15/16 | 93.8% | false 1, null 15 |
| `flank_pain_null_hedged:480834dd` | `flank_pain_null_hedged` | hedged | null | 17/18 | 94.4% | true 1, null 17 |
| `flank_pain_null_thirdparty:26bfb565` | `flank_pain_null_thirdparty` | third_party | null | 18/19 | 94.7% | true 1, null 18 |
| `flank_pain_null_thirdparty:3003d95a` | `flank_pain_null_thirdparty` | third_party | null | 18/19 | 94.7% | false 1, null 18 |
| `flank_pain_true:a50a0907` | `flank_pain_true` | -- | true | 19/20 | 95.0% | true 19, null 1 |
| `flank_pain_null_hedged:dbe527b2` | `flank_pain_null_hedged` | hedged | null | 21/22 | 95.5% | true 1, null 21 |
| `flank_pain_null_thirdparty:a161a995` | `flank_pain_null_thirdparty` | third_party | null | 21/22 | 95.5% | false 1, null 21 |
| `flank_pain_null_hedged:52c46ca3` | `flank_pain_null_hedged` | hedged | null | 22/23 | 95.7% | true 1, null 22 |
| `flank_pain_null_historical:1d821bf1` | `flank_pain_null_historical` | historical | null | 22/23 | 95.7% | true 1, null 22 |
| `flank_pain_true:801b09f3` | `flank_pain_true` | -- | true | 47/49 | 95.9% | false 1, true 47, null 1 |
| `flank_pain_false:1777a47f` | `flank_pain_false` | -- | false | 24/25 | 96.0% | false 24, true 1 |
| `flank_pain_null_hedged:5221d57c` | `flank_pain_null_hedged` | hedged | null | 24/25 | 96.0% | false 1, null 24 |
| `flank_pain_null_hedged:9512c1f5` | `flank_pain_null_hedged` | hedged | null | 24/25 | 96.0% | true 1, null 24 |
| `flank_pain_null_historical:d81e5c7b` | `flank_pain_null_historical` | historical | null | 25/26 | 96.2% | false 1, null 25 |
| `flank_pain_null_thirdparty:6b00ce7b` | `flank_pain_null_thirdparty` | third_party | null | 26/27 | 96.3% | false 1, null 26 |

*6 further fragments with at least one error are in the JSON sidecar; every fragment is there regardless of score.*

## `arm_b_finetune@c0.5-d0.3`

`roberta-base` with **every layer unfrozen**, mean-pooled, with the same `Linear(768, 3)` head -- 110M trainable parameters against Arm A's 2,307. Three epochs at batch 32, learning rate 2e-5, 10% linear warmup, AdamW, fp32. No gradient checkpointing, no 8-bit optimiser, no LoRA, no gradient accumulation: the full model fits in 12GB with room to spare, so anything that reads like a compute compromise would be a mistake rather than a saving. This is the arm that separates "the fragment libraries are the bottleneck" from "the method is too weak": if a fully fine-tuned encoder still cannot read third-party attribution, tense or metaphor, the limit is in the ideas the libraries contain and the fix is library work, not model work.

Decision-rule margins selected per fold (on each fold's own validation split): 0.0, 0.6, 0.9.

*Confusion matrix, raw argmax*

|  | pred false | pred true | pred null | total |
|---|---|---|---|---|
| **truth false** | 2334 | 2 | 143 | 2479 |
| **truth true** | 17 | 1423 | 41 | 1481 |
| **truth null** | 22 | 184 | 5834 | 6040 |
| **total** | 2373 | 1609 | 6018 | 10000 |

`null -> true`: 184 of 6040 truly-null examples (3.05%).

*Confusion matrix, after the decision rule*

|  | pred false | pred true | pred null | total |
|---|---|---|---|---|
| **truth false** | 2335 | 1 | 143 | 2479 |
| **truth true** | 20 | 1406 | 55 | 1481 |
| **truth null** | 28 | 162 | 5850 | 6040 |
| **total** | 2383 | 1569 | 6048 | 10000 |

`null -> true`: 162 of 6040 truly-null examples (2.68%).

### Per class, after the decision rule

| class | support | predicted | precision | recall | F1 |
|---|---|---|---|---|---|
| `false` | 2479 | 2383 | 98.0% | 94.2% | 96.1% |
| `true` | 1481 | 1569 | 89.6% | 94.9% | 92.2% |
| `null` | 6040 | 6048 | 96.7% | 96.9% | 96.8% |

### By label mode

| label mode | n | eff n | accuracy [95% CI] |
|---|---|---|---|
| false | 2479 | **131** | 94.2% [88.8%, 98.6%] |
| null_ambiguous | 3062 | **140** | 94.1% [90.6%, 97.3%] |
| null_structural | 2978 | **1** | 99.7% [99.7%, 99.7%] |
| true | 1481 | **129** | 94.9% [90.3%, 98.6%] |

### By null sub-class

| sub-class | n | eff n | null recall [95% CI] |
|---|---|---|---|
| hedged | 1178 | **53** | 86.8% [78.3%, 94.2%] |
| historical | 869 | **40** | 97.7% [93.8%, 99.8%] |
| third_party | 1015 | **47** | 99.5% [98.9%, 100.0%] |

### By fragment library

| library | n | eff n | accuracy [95% CI] |
|---|---|---|---|
| declarative_v1 | 1210 | **157** | 99.9% [99.7%, 100.0%] |
| flank_pain_false | 1725 | **55** | 91.7% [83.8%, 98.2%] |
| flank_pain_null_hedged | 1178 | **53** | 86.8% [78.3%, 94.2%] |
| flank_pain_null_historical | 869 | **40** | 97.7% [93.8%, 99.8%] |
| flank_pain_null_thirdparty | 1015 | **47** | 99.5% [98.9%, 100.0%] |
| flank_pain_true | 1025 | **48** | 92.8% [86.2%, 97.9%] |
| (none) | 2978 | **1** | 99.7% [99.7%, 99.7%] |

### Per-fragment errors (worst first)

Whether errors are spread thinly across many fragments or piled onto a few is the difference
between "the method is too weak" (model work) and "these specific ideas are not learnable from
the data we have" (library work, and these are the fragments to write more of). No intervals:
a fragment is one cluster, so an interval over its own examples measures nothing.

39 of 654 decisive fragments were got wrong at least once.

`arm_b_finetune@c0.5-d0.3`: 399 errors across 39 of 654 decisive fragments. Half of them fall on **8** fragments (an even spread would be 19.5); the worst ten carry 63.7% of all errors.

| fragment | library | sub-class | truth | correct | accuracy | predicted as |
|---|---|---|---|---|---|---|
| `flank_pain_false:d37c1465` | `flank_pain_false` | -- | false | 0/35 | 0.0% | null 35 |
| `flank_pain_false:bead93da` | `flank_pain_false` | -- | false | 0/32 | 0.0% | true 1, null 31 |
| `flank_pain_false:d7abb5ec` | `flank_pain_false` | -- | false | 0/30 | 0.0% | null 30 |
| `flank_pain_null_hedged:d9678a20` | `flank_pain_null_hedged` | hedged | null | 0/28 | 0.0% | true 28 |
| `flank_pain_false:b927c3ee` | `flank_pain_false` | -- | false | 0/21 | 0.0% | null 21 |
| `flank_pain_null_hedged:480834dd` | `flank_pain_null_hedged` | hedged | null | 0/18 | 0.0% | true 18 |
| `flank_pain_null_hedged:73cf9df7` | `flank_pain_null_hedged` | hedged | null | 0/16 | 0.0% | true 16 |
| `flank_pain_true:16e00186` | `flank_pain_true` | -- | true | 0/15 | 0.0% | false 15 |
| `flank_pain_null_hedged:d0b42e86` | `flank_pain_null_hedged` | hedged | null | 1/28 | 3.6% | false 11, true 16, null 1 |
| `flank_pain_true:19e39218` | `flank_pain_true` | -- | true | 2/24 | 8.3% | true 2, null 22 |
| `flank_pain_null_hedged:e5013045` | `flank_pain_null_hedged` | hedged | null | 2/15 | 13.3% | true 13, null 2 |
| `flank_pain_true:cb7fde42` | `flank_pain_true` | -- | true | 4/14 | 28.6% | true 4, null 10 |
| `flank_pain_null_historical:1d821bf1` | `flank_pain_null_historical` | historical | null | 7/23 | 30.4% | true 16, null 7 |
| `flank_pain_true:47597ae1` | `flank_pain_true` | -- | true | 14/30 | 46.7% | true 14, null 16 |
| `flank_pain_false:4d4ec138` | `flank_pain_false` | -- | false | 22/47 | 46.8% | false 22, null 25 |
| `flank_pain_null_hedged:d17ed4ab` | `flank_pain_null_hedged` | hedged | null | 8/17 | 47.1% | false 1, true 8, null 8 |
| `flank_pain_null_hedged:52c46ca3` | `flank_pain_null_hedged` | hedged | null | 11/23 | 47.8% | true 12, null 11 |
| `flank_pain_null_hedged:0817ad93` | `flank_pain_null_hedged` | hedged | null | 11/22 | 50.0% | true 11, null 11 |
| `flank_pain_null_hedged:1ee3ae69` | `flank_pain_null_hedged` | hedged | null | 11/22 | 50.0% | false 1, true 10, null 11 |
| `declarative_v1:7398c49e` | `declarative_v1` | -- | true | 2/3 | 66.7% | false 1, true 2 |
| `flank_pain_null_hedged:e51c02e1` | `flank_pain_null_hedged` | hedged | null | 15/21 | 71.4% | true 6, null 15 |
| `flank_pain_true:b2b80fa1` | `flank_pain_true` | -- | true | 18/23 | 78.3% | true 18, null 5 |
| `flank_pain_null_thirdparty:903a529b` | `flank_pain_null_thirdparty` | third_party | null | 21/23 | 91.3% | false 2, null 21 |
| `flank_pain_null_hedged:7142f310` | `flank_pain_null_hedged` | hedged | null | 23/25 | 92.0% | false 2, null 23 |
| `flank_pain_null_thirdparty:1d078e6d` | `flank_pain_null_thirdparty` | third_party | null | 24/26 | 92.3% | true 2, null 24 |
| `flank_pain_true:a50a0907` | `flank_pain_true` | -- | true | 13/14 | 92.9% | true 13, null 1 |
| `flank_pain_null_historical:b2c47e82` | `flank_pain_null_historical` | historical | null | 17/18 | 94.4% | true 1, null 17 |
| `flank_pain_null_thirdparty:26bfb565` | `flank_pain_null_thirdparty` | third_party | null | 18/19 | 94.7% | true 1, null 18 |
| `flank_pain_true:5ad4a1d1` | `flank_pain_true` | -- | true | 18/19 | 94.7% | false 1, true 18 |
| `flank_pain_null_historical:14365ab7` | `flank_pain_null_historical` | historical | null | 19/20 | 95.0% | false 1, null 19 |
| `flank_pain_null_historical:72182755` | `flank_pain_null_historical` | historical | null | 20/21 | 95.2% | false 1, null 20 |
| `flank_pain_false:cbb11cce` | `flank_pain_false` | -- | false | 21/22 | 95.5% | false 21, null 1 |
| `flank_pain_null_hedged:dbe527b2` | `flank_pain_null_hedged` | hedged | null | 21/22 | 95.5% | true 1, null 21 |
| `flank_pain_null_historical:fd2235a7` | `flank_pain_null_historical` | historical | null | 21/22 | 95.5% | true 1, null 21 |
| `flank_pain_true:214c674e` | `flank_pain_true` | -- | true | 21/22 | 95.5% | false 1, true 21 |
| `flank_pain_true:1dca9abd` | `flank_pain_true` | -- | true | 22/23 | 95.7% | true 22, null 1 |
| `flank_pain_true:f0d12a02` | `flank_pain_true` | -- | true | 22/23 | 95.7% | false 1, true 22 |
| `flank_pain_null_hedged:5221d57c` | `flank_pain_null_hedged` | hedged | null | 24/25 | 96.0% | false 1, null 24 |
| `flank_pain_true:801b09f3` | `flank_pain_true` | -- | true | 28/29 | 96.6% | false 1, true 28 |

## Appendix: per-fold numbers

Point estimates only. A single fold's test slice holds 2-5 clusters per hard sub-class, which
is the whole reason the headline is pooled.

### `majority_class`

| fold | train n | val n | test n | margin | acc (raw) | acc (ruled) | macro-F1 | null->true |
|---|---|---|---|---|---|---|---|---|
| 0 | 10000 | 2000 | 2000 | 0.0 | 60.5% | 60.5% | 25.1% | 0.00% |
| 1 | 10000 | 2000 | 2000 | 0.0 | 60.1% | 60.1% | 25.0% | 0.00% |
| 2 | 10000 | 2000 | 2000 | 0.0 | 60.4% | 60.4% | 25.1% | 0.00% |
| 3 | 10000 | 2000 | 2000 | 0.0 | 60.8% | 60.8% | 25.2% | 0.00% |
| 4 | 10000 | 2000 | 2000 | 0.0 | 60.3% | 60.3% | 25.1% | 0.00% |

### `length_only`

| fold | train n | val n | test n | margin | acc (raw) | acc (ruled) | macro-F1 | null->true |
|---|---|---|---|---|---|---|---|---|
| 0 | 10000 | 2000 | 2000 | 0.0 | 60.5% | 60.5% | 25.1% | 0.00% |
| 1 | 10000 | 2000 | 2000 | 0.0 | 60.1% | 60.1% | 25.0% | 0.00% |
| 2 | 10000 | 2000 | 2000 | 0.0 | 60.4% | 60.4% | 25.1% | 0.00% |
| 3 | 10000 | 2000 | 2000 | 0.0 | 60.8% | 60.8% | 25.2% | 0.00% |
| 4 | 10000 | 2000 | 2000 | 0.0 | 60.3% | 60.3% | 25.1% | 0.00% |

### `tfidf_logreg`

| fold | train n | val n | test n | margin | acc (raw) | acc (ruled) | macro-F1 | null->true |
|---|---|---|---|---|---|---|---|---|
| 0 | 10000 | 2000 | 2000 | 0.0 | 83.4% | 83.4% | 77.2% | 0.08% |
| 1 | 10000 | 2000 | 2000 | 0.0 | 78.8% | 78.8% | 70.1% | 0.58% |
| 2 | 10000 | 2000 | 2000 | 0.0 | 78.3% | 78.3% | 71.1% | 4.64% |
| 3 | 10000 | 2000 | 2000 | 0.0 | 79.8% | 79.8% | 72.7% | 2.06% |
| 4 | 10000 | 2000 | 2000 | 0.0 | 82.1% | 82.1% | 76.2% | 3.65% |

### `length_only__shuffled`

| fold | train n | val n | test n | margin | acc (raw) | acc (ruled) | macro-F1 | null->true |
|---|---|---|---|---|---|---|---|---|
| 0 | 10000 | 2000 | 2000 | 0.0 | 60.5% | 60.5% | 25.1% | 0.00% |
| 1 | 10000 | 2000 | 2000 | 0.0 | 60.1% | 60.1% | 25.0% | 0.00% |
| 2 | 10000 | 2000 | 2000 | 0.0 | 60.4% | 60.4% | 25.1% | 0.00% |
| 3 | 10000 | 2000 | 2000 | 0.0 | 60.8% | 60.8% | 25.2% | 0.00% |
| 4 | 10000 | 2000 | 2000 | 0.0 | 60.3% | 60.3% | 25.1% | 0.00% |

### `tfidf_logreg__shuffled`

| fold | train n | val n | test n | margin | acc (raw) | acc (ruled) | macro-F1 | null->true |
|---|---|---|---|---|---|---|---|---|
| 0 | 10000 | 2000 | 2000 | 0.0 | 60.4% | 60.4% | 25.1% | 0.00% |
| 1 | 10000 | 2000 | 2000 | 0.0 | 60.1% | 60.1% | 25.0% | 0.00% |
| 2 | 10000 | 2000 | 2000 | 0.0 | 60.4% | 60.4% | 25.1% | 0.00% |
| 3 | 10000 | 2000 | 2000 | 0.0 | 60.8% | 60.8% | 25.2% | 0.00% |
| 4 | 10000 | 2000 | 2000 | 0.0 | 60.3% | 60.3% | 25.1% | 0.00% |

### `arm_b_finetune@c0.0-d0.0`

| fold | train n | val n | test n | margin | acc (raw) | acc (ruled) | macro-F1 | null->true |
|---|---|---|---|---|---|---|---|---|
| 0 | 10000 | 2000 | 2000 | 0.8 | 95.9% | 96.3% | 95.4% | 5.13% |
| 1 | 10000 | 2000 | 2000 | 0.85 | 96.2% | 96.4% | 95.3% | 4.41% |
| 2 | 10000 | 2000 | 2000 | 0.0 | 94.0% | 94.0% | 92.5% | 3.06% |
| 3 | 10000 | 2000 | 2000 | 0.0 | 97.5% | 97.5% | 97.4% | 0.08% |
| 4 | 10000 | 2000 | 2000 | 0.0 | 97.8% | 97.8% | 97.6% | 0.25% |

### `arm_b_finetune@c0.0-d0.3`

| fold | train n | val n | test n | margin | acc (raw) | acc (ruled) | macro-F1 | null->true |
|---|---|---|---|---|---|---|---|---|
| 0 | 10000 | 2000 | 2000 | 0.9 | 99.1% | 99.1% | 98.7% | 1.49% |
| 1 | 10000 | 2000 | 2000 | 0.1 | 98.2% | 98.2% | 97.6% | 1.75% |
| 2 | 10000 | 2000 | 2000 | 0.75 | 97.2% | 97.2% | 96.7% | 0.99% |
| 3 | 10000 | 2000 | 2000 | 0.0 | 98.2% | 98.2% | 98.1% | 0.49% |
| 4 | 10000 | 2000 | 2000 | 0.85 | 98.4% | 98.6% | 98.7% | 0.08% |

### `arm_b_finetune@c0.5-d0.0`

| fold | train n | val n | test n | margin | acc (raw) | acc (ruled) | macro-F1 | null->true |
|---|---|---|---|---|---|---|---|---|
| 0 | 10000 | 2000 | 2000 | 0.65 | 95.8% | 95.8% | 94.3% | 0.33% |
| 1 | 10000 | 2000 | 2000 | 0.25 | 94.5% | 94.6% | 93.9% | 2.58% |
| 2 | 10000 | 2000 | 2000 | 0.0 | 88.4% | 88.4% | 86.0% | 2.57% |
| 3 | 10000 | 2000 | 2000 | 0.8 | 96.3% | 96.3% | 96.3% | 0.49% |
| 4 | 10000 | 2000 | 2000 | 0.0 | 96.6% | 96.6% | 95.9% | 0.08% |

### `arm_b_finetune@c0.5-d0.3`

| fold | train n | val n | test n | margin | acc (raw) | acc (ruled) | macro-F1 | null->true |
|---|---|---|---|---|---|---|---|---|
| 0 | 10000 | 2000 | 2000 | 0.9 | 96.9% | 96.5% | 95.8% | 2.15% |
| 1 | 10000 | 2000 | 2000 | 0.6 | 92.3% | 92.8% | 91.5% | 7.99% |
| 2 | 10000 | 2000 | 2000 | 0.9 | 95.6% | 95.5% | 94.3% | 1.99% |
| 3 | 10000 | 2000 | 2000 | 0.9 | 98.4% | 98.4% | 98.3% | 0.00% |
| 4 | 10000 | 2000 | 2000 | 0.0 | 96.4% | 96.4% | 95.6% | 1.33% |

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

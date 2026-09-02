# Encoder training: evaluation report

*Generated 2026-09-02T15:57:10+00:00.*

|  |  |
|---|---|
| signal | `haematuria_present` |
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
| selected epochs | `c0.0-d0.0 3, 1, 1, 2, 2, c0.0-d0.3 1, 3, 3, 3, 3, c0.5-d0.0 3, 2, 3, 3, 2, c0.5-d0.3 3, 1, 1, 2, 1` |
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
| cluster tag coverage | `1 of 6 libraries carry cluster markers; 225 of 691 fragments are in libraries with none` |
| bootstrap | `2000 resamples over clusters, alpha=0.05, seed=0` |

**arms**

* **c0.0-d0.0** (`data/synthetic/generated/decl/c0.0-d0.0`): 10000 examples per epoch, **10000** labelled positions for `haematuria_present`
* **c0.0-d0.3** (`data/synthetic/generated/decl/c0.0-d0.3`): 10000 examples per epoch, **10000** labelled positions for `haematuria_present`
* **c0.5-d0.0** (`data/synthetic/generated/decl/c0.5-d0.0`): 10000 examples per epoch, **10000** labelled positions for `haematuria_present`
* **c0.5-d0.3** (`data/synthetic/generated/decl/c0.5-d0.3`): 10000 examples per epoch, **10000** labelled positions for `haematuria_present`

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
| `declarative_v1` | 466 | 466 | 100.0% |

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
| `majority_class` | baseline | 7022 | **225** | 43.6% [36.8%, 51.0%] | 20.2% [17.9%, 22.5%] | 60.4% | 60.4% +/- 0.2% |
| `length_only` | baseline | 7022 | **225** | 44.0% [37.2%, 51.3%] | 21.0% [18.6%, 23.4%] | 60.6% | 60.6% +/- 0.4% |
| `tfidf_logreg` | baseline | 7022 | **225** | 74.3% [69.0%, 79.3%] | 70.4% [64.4%, 75.8%] | 81.9% | 81.9% +/- 3.0% |
| `length_only__shuffled` | negative control | 7022 | **225** | 43.6% [36.8%, 51.0%] | 20.2% [17.9%, 22.5%] | 60.4% | 60.4% +/- 0.2% |
| `tfidf_logreg__shuffled` | negative control | 7022 | **225** | 43.6% [36.8%, 51.0%] | 20.3% [17.9%, 22.6%] | 60.4% | 60.4% +/- 0.2% |
| `arm_b_finetune@c0.0-d0.0` | finetune | 7022 | **225** | 91.3% [87.3%, 94.6%] | 90.8% [86.6%, 94.2%] | 93.9% | 93.9% +/- 1.9% |
| `arm_b_finetune@c0.0-d0.3` | finetune | 7022 | **387** | 93.9% [91.0%, 96.6%] | 93.4% [90.2%, 96.2%] | 95.8% | 95.7% +/- 1.5% |
| `arm_b_finetune@c0.5-d0.0` | finetune | 7022 | **225** | 89.4% [84.9%, 93.4%] | 89.0% [84.3%, 93.0%] | 92.5% | 92.5% +/- 2.7% |
| `arm_b_finetune@c0.5-d0.3` | finetune | 7022 | **387** | 92.2% [88.9%, 95.1%] | 91.9% [88.3%, 94.8%] | 94.5% | 94.5% +/- 2.6% |

### Null sub-class recall, pooled

The table the whole exercise exists for: how often each hard `null` sub-class is correctly
left as `null`. `eff n` here is the sub-class's entire library, which a single split cannot reach.

**Never read this table on its own.** Every example in these slices is truly `null`, so a model
that always answers `null` scores 100% across the row -- as `majority_class` below does. High
null recall is only a finding when the `true` and `false` recalls in the per-class tables are
high too.

| model | adjacent | attribution | hedged | historical | metaphor | third_party |
|---|---|---|---|---|---|---|
| `majority_class` | -- | -- | 100.0% [100.0%, 100.0%] (eff n 45) | 100.0% [100.0%, 100.0%] (eff n 45) | -- | 100.0% [100.0%, 100.0%] (eff n 45) |
| `length_only` | -- | -- | 100.0% [100.0%, 100.0%] (eff n 45) | 100.0% [100.0%, 100.0%] (eff n 45) | -- | 100.0% [100.0%, 100.0%] (eff n 45) |
| `tfidf_logreg` | -- | -- | 90.9% [82.7%, 96.8%] (eff n 45) | 93.9% [89.0%, 98.0%] (eff n 45) | -- | 97.1% [94.0%, 99.4%] (eff n 45) |
| `length_only__shuffled` | -- | -- | 100.0% [100.0%, 100.0%] (eff n 45) | 100.0% [100.0%, 100.0%] (eff n 45) | -- | 100.0% [100.0%, 100.0%] (eff n 45) |
| `tfidf_logreg__shuffled` | -- | -- | 100.0% [100.0%, 100.0%] (eff n 45) | 100.0% [100.0%, 100.0%] (eff n 45) | -- | 100.0% [100.0%, 100.0%] (eff n 45) |
| `arm_b_finetune@c0.0-d0.0` | -- | -- | 80.8% [69.5%, 90.4%] (eff n 45) | 98.3% [95.5%, 100.0%] (eff n 45) | -- | 97.6% [93.3%, 100.0%] (eff n 45) |
| `arm_b_finetune@c0.0-d0.3` | -- | -- | 87.7% [78.4%, 95.3%] (eff n 45) | 98.6% [96.6%, 100.0%] (eff n 45) | -- | 98.0% [95.0%, 100.0%] (eff n 45) |
| `arm_b_finetune@c0.5-d0.0` | -- | -- | 85.8% [76.5%, 94.1%] (eff n 45) | 95.1% [87.5%, 99.8%] (eff n 45) | -- | 99.2% [97.8%, 100.0%] (eff n 45) |
| `arm_b_finetune@c0.5-d0.3` | -- | -- | 85.0% [75.0%, 93.5%] (eff n 45) | 98.0% [95.6%, 99.8%] (eff n 45) | -- | 98.8% [96.4%, 100.0%] (eff n 45) |

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

Not scored, because no head exists for them: `dysuria_present`, `urinary_frequency_present`, `nocturia_present`, `fever_present`, `flank_pain_present`, `recent_uti_present`.

### `null -> true` on real text -- the headline

How often each model answers `true` about a signal the submission never mentioned, as
the mean across folds of that fold's own rate. Every other number in this section is
read against this one: a model can post a respectable overall figure here purely by
answering `null` everywhere, and it can post a respectable *decisive* figure while still
inventing symptoms into most of the submissions that never raised them.

| signal | null support | `arm_b_finetune@c0.0-d0.0` | `arm_b_finetune@c0.0-d0.3` | `arm_b_finetune@c0.5-d0.0` | `arm_b_finetune@c0.5-d0.3` |
|---|---|---|---|---|---|
| `haematuria_present` | 56 | 29.3% | 63.2% | 9.3% | 13.2% |

### `arm_b_finetune@c0.0-d0.0`

Recombination test slice: **n 7022**, **eff n 225** clusters, accuracy 91.3% [87.3%, 94.6%]. Holdout: **n 67** submissions, one observation each, scored by 5 fold models at margins 0.9, 0.9, 0.4, 0.8, 0.0. The two `n`s are printed together because they are not the same kind of number and the second is far the smaller.

| signal | true/false/null | omitted | decisive n | decisive acc (mean +/- sd) | worst-case half-width | all n | all acc (mean +/- sd) | null recall |
|---|---|---|---|---|---|---|---|---|
| `haematuria_present` | 9/2/56 | 0 | 11 | 76.4% +/- 10.4% | +/-29.5% | 67 | 68.1% +/- 5.0% | 66.4% +/- 7.8% |

`null -> true` on real text, per fold: `haematuria_present` 13, 21, 17, 19, 12 of 56. This is the cell that invents a symptom into a patient's pre-filled form, counted here on submissions rather than on recombinations.

### `arm_b_finetune@c0.0-d0.3`

Recombination test slice: **n 7022**, **eff n 387** clusters, accuracy 93.9% [91.0%, 96.6%]. Holdout: **n 67** submissions, one observation each, scored by 5 fold models at margins 0.9, 0.8, 0.6, 0.65, 0.15. The two `n`s are printed together because they are not the same kind of number and the second is far the smaller.

| signal | true/false/null | omitted | decisive n | decisive acc (mean +/- sd) | worst-case half-width | all n | all acc (mean +/- sd) | null recall |
|---|---|---|---|---|---|---|---|---|
| `haematuria_present` | 9/2/56 | 0 | 11 | 100.0% +/- 0.0% | +/-29.5% | 67 | 46.6% +/- 8.3% | 36.1% +/- 9.9% |

`null -> true` on real text, per fold: `haematuria_present` 29, 33, 36, 35, 44 of 56. This is the cell that invents a symptom into a patient's pre-filled form, counted here on submissions rather than on recombinations.

### `arm_b_finetune@c0.5-d0.0`

Recombination test slice: **n 7022**, **eff n 225** clusters, accuracy 89.4% [84.9%, 93.4%]. Holdout: **n 67** submissions, one observation each, scored by 5 fold models at margins 0.9, 0.9, 0.0, 0.9, 0.55. The two `n`s are printed together because they are not the same kind of number and the second is far the smaller.

| signal | true/false/null | omitted | decisive n | decisive acc (mean +/- sd) | worst-case half-width | all n | all acc (mean +/- sd) | null recall |
|---|---|---|---|---|---|---|---|---|
| `haematuria_present` | 9/2/56 | 0 | 11 | 50.9% +/- 15.2% | +/-29.5% | 67 | 84.2% +/- 1.7% | 90.7% +/- 2.3% |

`null -> true` on real text, per fold: `haematuria_present` 4, 7, 5, 6, 4 of 56. This is the cell that invents a symptom into a patient's pre-filled form, counted here on submissions rather than on recombinations.

### `arm_b_finetune@c0.5-d0.3`

Recombination test slice: **n 7022**, **eff n 387** clusters, accuracy 92.2% [88.9%, 95.1%]. Holdout: **n 67** submissions, one observation each, scored by 5 fold models at margins 0.9, 0.9, 0.5, 0.0, 0.35. The two `n`s are printed together because they are not the same kind of number and the second is far the smaller.

| signal | true/false/null | omitted | decisive n | decisive acc (mean +/- sd) | worst-case half-width | all n | all acc (mean +/- sd) | null recall |
|---|---|---|---|---|---|---|---|---|
| `haematuria_present` | 9/2/56 | 0 | 11 | 87.3% +/- 12.2% | +/-29.5% | 67 | 86.9% +/- 2.7% | 86.8% +/- 3.7% |

`null -> true` on real text, per fold: `haematuria_present` 6, 6, 11, 7, 7 of 56. This is the cell that invents a symptom into a patient's pre-filled form, counted here on submissions rather than on recombinations.

## Paired on real text

The 67 submissions are the same 67 for every model here, so unlike the recombination
test slice they can be paired: the informative quantity is the submissions two models
disagree about, not the gap between two means. One test per fold, never pooled.

### `arm_b_finetune@c0.0-d0.0` against `arm_b_finetune@c0.0-d0.3`

| fold | pairs | only `arm_b_finetune@c0.0-d0.0` | only `arm_b_finetune@c0.0-d0.3` | p |
|---|---|---|---|---|
| 0 | 67 | 13 | 3 | 0.0213 |
| 1 | 67 | 12 | 4 | 0.0768 |
| 2 | 67 | 18 | 4 | 0.00434 |
| 3 | 67 | 14 | 1 | 0.000977 |
| 4 | 67 | 31 | 4 | 3.47e-06 |

`arm_b_finetune@c0.0-d0.0` ahead on 5 folds, `arm_b_finetune@c0.0-d0.3` on 0. `null -> true` mean: 29.3% against 63.2% -- **-33.9 points** in favour of `arm_b_finetune@c0.0-d0.3`.

*One test per fold over the same 67 submissions, never concatenated: five folds are five models scored on one sample, and pooling would report a p-value for 335 observations that do not exist.*

### `arm_b_finetune@c0.0-d0.0` against `arm_b_finetune@c0.5-d0.0`

| fold | pairs | only `arm_b_finetune@c0.0-d0.0` | only `arm_b_finetune@c0.5-d0.0` | p |
|---|---|---|---|---|
| 0 | 67 | 5 | 12 | 0.143 |
| 1 | 67 | 3 | 17 | 0.00258 |
| 2 | 67 | 3 | 14 | 0.0127 |
| 3 | 67 | 3 | 17 | 0.00258 |
| 4 | 67 | 3 | 11 | 0.0574 |

`arm_b_finetune@c0.0-d0.0` ahead on 0 folds, `arm_b_finetune@c0.5-d0.0` on 5. `null -> true` mean: 29.3% against 9.3% -- **+20.0 points** in favour of `arm_b_finetune@c0.5-d0.0`.

*One test per fold over the same 67 submissions, never concatenated: five folds are five models scored on one sample, and pooling would report a p-value for 335 observations that do not exist.*

### `arm_b_finetune@c0.0-d0.0` against `arm_b_finetune@c0.5-d0.3`

| fold | pairs | only `arm_b_finetune@c0.0-d0.0` | only `arm_b_finetune@c0.5-d0.3` | p |
|---|---|---|---|---|
| 0 | 67 | 1 | 11 | 0.00635 |
| 1 | 67 | 0 | 19 | 3.81e-06 |
| 2 | 67 | 3 | 14 | 0.0127 |
| 3 | 67 | 1 | 16 | 0.000275 |
| 4 | 67 | 2 | 10 | 0.0386 |

`arm_b_finetune@c0.0-d0.0` ahead on 0 folds, `arm_b_finetune@c0.5-d0.3` on 5. `null -> true` mean: 29.3% against 13.2% -- **+16.1 points** in favour of `arm_b_finetune@c0.5-d0.3`.

*One test per fold over the same 67 submissions, never concatenated: five folds are five models scored on one sample, and pooling would report a p-value for 335 observations that do not exist.*

### `arm_b_finetune@c0.0-d0.3` against `arm_b_finetune@c0.5-d0.0`

| fold | pairs | only `arm_b_finetune@c0.0-d0.3` | only `arm_b_finetune@c0.5-d0.0` | p |
|---|---|---|---|---|
| 0 | 67 | 8 | 25 | 0.00455 |
| 1 | 67 | 4 | 26 | 5.95e-05 |
| 2 | 67 | 6 | 31 | 4.13e-05 |
| 3 | 67 | 4 | 31 | 3.47e-06 |
| 4 | 67 | 5 | 40 | 7.88e-08 |

`arm_b_finetune@c0.0-d0.3` ahead on 0 folds, `arm_b_finetune@c0.5-d0.0` on 5. `null -> true` mean: 63.2% against 9.3% -- **+53.9 points** in favour of `arm_b_finetune@c0.5-d0.0`.

*One test per fold over the same 67 submissions, never concatenated: five folds are five models scored on one sample, and pooling would report a p-value for 335 observations that do not exist.*

### `arm_b_finetune@c0.0-d0.3` against `arm_b_finetune@c0.5-d0.3`

| fold | pairs | only `arm_b_finetune@c0.0-d0.3` | only `arm_b_finetune@c0.5-d0.3` | p |
|---|---|---|---|---|
| 0 | 67 | 3 | 23 | 8.8e-05 |
| 1 | 67 | 0 | 27 | 1.49e-08 |
| 2 | 67 | 1 | 26 | 4.17e-07 |
| 3 | 67 | 2 | 30 | 2.46e-07 |
| 4 | 67 | 2 | 37 | 2.84e-09 |

`arm_b_finetune@c0.0-d0.3` ahead on 0 folds, `arm_b_finetune@c0.5-d0.3` on 5. `null -> true` mean: 63.2% against 13.2% -- **+50.0 points** in favour of `arm_b_finetune@c0.5-d0.3`.

*One test per fold over the same 67 submissions, never concatenated: five folds are five models scored on one sample, and pooling would report a p-value for 335 observations that do not exist.*

### `arm_b_finetune@c0.5-d0.0` against `arm_b_finetune@c0.5-d0.3`

| fold | pairs | only `arm_b_finetune@c0.5-d0.0` | only `arm_b_finetune@c0.5-d0.3` | p |
|---|---|---|---|---|
| 0 | 67 | 2 | 5 | 0.453 |
| 1 | 67 | 2 | 7 | 0.18 |
| 2 | 67 | 7 | 7 | 1 |
| 3 | 67 | 4 | 5 | 1 |
| 4 | 67 | 6 | 6 | 1 |

`arm_b_finetune@c0.5-d0.0` ahead on 0 folds, `arm_b_finetune@c0.5-d0.3` on 3. `null -> true` mean: 9.3% against 13.2% -- **-3.9 points** in favour of `arm_b_finetune@c0.5-d0.3`.

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
| `majority_class` | baseline | 3062 | **135** | 100.0% [100.0%, 100.0%] |
| `length_only` | baseline | 3062 | **135** | 100.0% [100.0%, 100.0%] |
| `tfidf_logreg` | baseline | 3062 | **135** | 93.9% [90.6%, 96.5%] |
| `arm_b_finetune@c0.0-d0.0` | finetune | 3062 | **135** | 91.9% [87.3%, 95.9%] |
| `arm_b_finetune@c0.0-d0.3` | finetune | 3062 | **135** | 94.6% [91.1%, 97.6%] |
| `arm_b_finetune@c0.5-d0.0` | finetune | 3062 | **135** | 93.1% [88.9%, 96.8%] |
| `arm_b_finetune@c0.5-d0.3` | finetune | 3062 | **135** | 93.7% [90.0%, 97.1%] |

### 2. The same comparison, paired

Two overlapping intervals do not settle whether one model beats another on the same
examples. McNemar does, over the examples the two disagree about -- read it alongside the
intervals above, never instead of them.

| pair | n | a only | b only | p |
|---|---|---|---|---|
| `majority_class` vs `length_only` | 3062 | 0 | 0 | 1 |
| `majority_class` vs `tfidf_logreg` | 3062 | 189 | 0 | 2.55e-57 |
| `majority_class` vs `arm_b_finetune@c0.0-d0.0` | 3062 | 260 | 0 | 1.08e-78 |
| `length_only` vs `tfidf_logreg` | 3062 | 189 | 0 | 2.55e-57 |
| `length_only` vs `arm_b_finetune@c0.0-d0.0` | 3062 | 260 | 0 | 1.08e-78 |
| `tfidf_logreg` vs `arm_b_finetune@c0.0-d0.0` | 3062 | 223 | 152 | 0.000289 |

Not on this table, because they cannot be paired at all -- different examples on the two sides, so there is nothing for McNemar to pair: `majority_class` vs `arm_b_finetune@c0.0-d0.3`; `majority_class` vs `arm_b_finetune@c0.5-d0.0`; `majority_class` vs `arm_b_finetune@c0.5-d0.3`; `length_only` vs `arm_b_finetune@c0.0-d0.3`; `length_only` vs `arm_b_finetune@c0.5-d0.0`; `length_only` vs `arm_b_finetune@c0.5-d0.3`; `tfidf_logreg` vs `arm_b_finetune@c0.0-d0.3`; `tfidf_logreg` vs `arm_b_finetune@c0.5-d0.0`; `tfidf_logreg` vs `arm_b_finetune@c0.5-d0.3`; `arm_b_finetune@c0.0-d0.0` vs `arm_b_finetune@c0.0-d0.3`; `arm_b_finetune@c0.0-d0.0` vs `arm_b_finetune@c0.5-d0.0`; `arm_b_finetune@c0.0-d0.0` vs `arm_b_finetune@c0.5-d0.3`; `arm_b_finetune@c0.0-d0.3` vs `arm_b_finetune@c0.5-d0.0`; `arm_b_finetune@c0.0-d0.3` vs `arm_b_finetune@c0.5-d0.3`; `arm_b_finetune@c0.5-d0.0` vs `arm_b_finetune@c0.5-d0.3`. Read those through the intervals above and the per-fold spread, and see "Pairs that could not be tested" below.

### 3. Where the errors fall

The per-fragment table below, as one number per model. Errors spread thinly across many
fragments say the method is too weak. Errors piled onto a handful say those specific ideas
are not learnable from the data we have -- and the table names them, which is what makes
this the most decision-useful thing in the report.

* `majority_class`: 3960 errors across 90 of 225 decisive fragments. Half of them fall on **32** fragments (an even spread would be 45.0); the worst ten carry 18.0% of all errors.
* `length_only`: 3932 errors across 90 of 225 decisive fragments. Half of them fall on **32** fragments (an even spread would be 45.0); the worst ten carry 17.8% of all errors.
* `tfidf_logreg`: 1806 errors across 102 of 225 decisive fragments. Half of them fall on **21** fragments (an even spread would be 51.0); the worst ten carry 30.9% of all errors.
* `arm_b_finetune@c0.0-d0.0`: 608 errors across 35 of 225 decisive fragments. Half of them fall on **8** fragments (an even spread would be 17.5); the worst ten carry 60.7% of all errors.
* `arm_b_finetune@c0.0-d0.3`: 425 errors across 33 of 643 decisive fragments. Half of them fall on **6** fragments (an even spread would be 16.5); the worst ten carry 72.5% of all errors.
* `arm_b_finetune@c0.5-d0.0`: 745 errors across 48 of 225 decisive fragments. Half of them fall on **8** fragments (an even spread would be 24.0); the worst ten carry 61.1% of all errors.
* `arm_b_finetune@c0.5-d0.3`: 545 errors across 40 of 642 decisive fragments. Half of them fall on **8** fragments (an even spread would be 20.0); the worst ten carry 60.0% of all errors.

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
| `length_only__shuffled` | 60.4% [38.5%, 77.4%] | 25.1% [18.5%, 29.1%] |
| `tfidf_logreg__shuffled` | 60.4% [38.5%, 77.4%] | 25.1% [18.6%, 29.1%] |

## Paired comparisons (McNemar, raw argmax)

Exact two-sided McNemar over the examples the two models disagree about. Pairing unit is the
example, not the cluster -- see the limitations.

| pair | slice | n | a only | b only | p |
|---|---|---|---|---|---|
| `majority_class` vs `length_only` | overall | 10000 | 7 | 28 | 0.000508 |
| `majority_class` vs `length_only` | null_ambiguous | 3062 | 0 | 0 | 1 |
| `majority_class` vs `tfidf_logreg` | overall | 10000 | 195 | 2349 | 0 |
| `majority_class` vs `tfidf_logreg` | null_ambiguous | 3062 | 189 | 0 | 2.55e-57 |
| `majority_class` vs `arm_b_finetune@c0.0-d0.0` | overall | 10000 | 260 | 3621 | 0 |
| `majority_class` vs `arm_b_finetune@c0.0-d0.0` | null_ambiguous | 3062 | 260 | 0 | 1.08e-78 |
| `length_only` vs `tfidf_logreg` | overall | 10000 | 201 | 2334 | 0 |
| `length_only` vs `tfidf_logreg` | null_ambiguous | 3062 | 189 | 0 | 2.55e-57 |
| `length_only` vs `arm_b_finetune@c0.0-d0.0` | overall | 10000 | 260 | 3600 | 0 |
| `length_only` vs `arm_b_finetune@c0.0-d0.0` | null_ambiguous | 3062 | 260 | 0 | 1.08e-78 |
| `tfidf_logreg` vs `arm_b_finetune@c0.0-d0.0` | overall | 10000 | 270 | 1477 | 3.57e-201 |
| `tfidf_logreg` vs `arm_b_finetune@c0.0-d0.0` | null_ambiguous | 3062 | 223 | 152 | 0.000289 |

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
| `haematuria_false` | 1722 | 0.0% | 1.1% | 68.7% | 92.6% | 91.5% | 85.8% | 86.8% | 92.6pp |
| `haematuria_true` | 1024 | 0.0% | 0.0% | 43.2% | 88.1% | 88.8% | 87.7% | 87.9% | 88.8pp |
| `haematuria_null_hedged` | 1079 | 100.0% | 100.0% | 90.9% | 80.8% | 87.7% | 85.8% | 85.0% | 19.2pp |
| `haematuria_null_historical` | 1017 | 100.0% | 100.0% | 93.9% | 98.3% | 98.6% | 95.1% | 98.0% | 6.1pp |
| `haematuria_null_thirdparty` | 966 | 100.0% | 100.0% | 97.1% | 97.6% | 98.0% | 99.2% | 98.8% | 2.9pp |
| `(none)` | 2978 | 100.0% | 99.8% | 99.8% | 100.0% | 100.0% | 99.7% | 99.7% | 0.3pp |

### By fragment, errors

Ordered by the worst model's error count, so the fragments the comparison is about sort
to the top whichever encoder wins. Counts, not rates: these are the sentences a month of
library work would be spent on. The JSON holds every fragment.

| fragment | library | truth | `majority_class` | `length_only` | `tfidf_logreg` | `arm_b_finetune@c0.0-d0.0` | `arm_b_finetune@c0.0-d0.3` | `arm_b_finetune@c0.5-d0.0` | `arm_b_finetune@c0.5-d0.3` | spread |
|---|---|---|---|---|---|---|---|---|---|---|
| `haematuria_false:0e98be72` | `haematuria_false` | false | 81 | 81 | 80 | 0 | 2 | 81 | 38 | 81 |
| `haematuria_false:b3fd19df` | `haematuria_false` | false | 76 | 76 | 0 | 0 | 0 | 0 | 0 | 76 |
| `haematuria_false:56b8af62` | `haematuria_false` | false | 75 | 75 | 36 | 0 | 0 | 0 | 0 | 75 |
| `haematuria_false:94f9de34` | `haematuria_false` | false | 75 | 65 | 35 | 0 | 0 | 0 | 1 | 75 |
| `haematuria_false:acc7804e` | `haematuria_false` | false | 73 | 73 | 5 | 0 | 0 | 0 | 0 | 73 |
| `haematuria_true:c0ff5eed` | `haematuria_true` | true | 73 | 73 | 73 | 34 | 30 | 0 | 0 | 73 |
| `haematuria_false:e23c4950` | `haematuria_false` | false | 67 | 59 | 28 | 0 | 0 | 0 | 0 | 67 |
| `haematuria_false:64933508` | `haematuria_false` | false | 65 | 65 | 20 | 0 | 0 | 0 | 4 | 65 |
| `haematuria_false:b692c4ce` | `haematuria_false` | false | 65 | 65 | 9 | 0 | 0 | 0 | 0 | 65 |
| `haematuria_false:5e090855` | `haematuria_false` | false | 64 | 64 | 0 | 0 | 0 | 0 | 0 | 64 |
| `haematuria_false:a84358ef` | `haematuria_false` | false | 64 | 64 | 0 | 0 | 0 | 0 | 0 | 64 |
| `haematuria_false:cbd9cec5` | `haematuria_false` | false | 63 | 63 | 63 | 0 | 0 | 2 | 0 | 63 |
| `haematuria_false:b0d93eca` | `haematuria_false` | false | 62 | 62 | 0 | 0 | 0 | 0 | 0 | 62 |
| `haematuria_true:972bb99b` | `haematuria_true` | true | 62 | 62 | 5 | 0 | 0 | 0 | 0 | 62 |
| `haematuria_false:873d5c5b` | `haematuria_false` | false | 61 | 61 | 24 | 0 | 0 | 0 | 0 | 61 |
| `haematuria_false:0a0b1113` | `haematuria_false` | false | 60 | 60 | 53 | 0 | 0 | 26 | 22 | 60 |
| `haematuria_true:62126789` | `haematuria_true` | true | 60 | 60 | 2 | 0 | 0 | 0 | 0 | 60 |
| `haematuria_false:7240a8fb` | `haematuria_false` | false | 59 | 55 | 13 | 0 | 0 | 1 | 0 | 59 |
| `haematuria_true:6fadb8bc` | `haematuria_true` | true | 57 | 57 | 49 | 57 | 41 | 59 | 40 | 19 |
| `haematuria_true:7ea098d1` | `haematuria_true` | true | 59 | 59 | 32 | 0 | 0 | 0 | 0 | 59 |
| `haematuria_true:f2e49699` | `haematuria_true` | true | 59 | 59 | 33 | 1 | 0 | 0 | 0 | 59 |
| `haematuria_false:94644abb` | `haematuria_false` | false | 58 | 58 | 0 | 0 | 0 | 0 | 0 | 58 |
| `haematuria_false:d163df19` | `haematuria_false` | false | 58 | 58 | 57 | 58 | 36 | 56 | 39 | 22 |
| `haematuria_false:fc6a0704` | `haematuria_false` | false | 58 | 58 | 3 | 0 | 0 | 0 | 0 | 58 |
| `haematuria_true:150663fa` | `haematuria_true` | true | 58 | 58 | 22 | 0 | 0 | 5 | 0 | 58 |
| `haematuria_true:d93fd4ce` | `haematuria_true` | true | 58 | 58 | 7 | 0 | 0 | 0 | 0 | 58 |
| `haematuria_false:0722271d` | `haematuria_false` | false | 57 | 57 | 5 | 0 | 0 | 0 | 0 | 57 |
| `haematuria_false:4fda0b2c` | `haematuria_false` | false | 57 | 56 | 19 | 0 | 0 | 0 | 0 | 57 |
| `haematuria_false:cb3cb6e6` | `haematuria_false` | false | 57 | 54 | 51 | 39 | 30 | 2 | 7 | 55 |
| `haematuria_false:58488f8a` | `haematuria_false` | false | 56 | 56 | 0 | 0 | 0 | 0 | 0 | 56 |
| `haematuria_false:66629fb1` | `haematuria_false` | false | 56 | 56 | 38 | 0 | 0 | 12 | 33 | 56 |
| `haematuria_false:d9d4737d` | `haematuria_false` | false | 56 | 56 | 35 | 7 | 0 | 55 | 0 | 56 |
| `haematuria_true:245ed73d` | `haematuria_true` | true | 56 | 56 | 18 | 0 | 0 | 0 | 0 | 56 |
| `haematuria_false:5543da20` | `haematuria_false` | false | 55 | 55 | 7 | 0 | 0 | 0 | 0 | 55 |
| `haematuria_false:61bf080a` | `haematuria_false` | false | 55 | 55 | 2 | 0 | 0 | 0 | 0 | 55 |
| `haematuria_false:899e3ed9` | `haematuria_false` | false | 55 | 55 | 29 | 0 | 0 | 2 | 0 | 55 |
| `haematuria_false:9720fe1e` | `haematuria_false` | false | 55 | 53 | 0 | 0 | 0 | 0 | 0 | 55 |
| `haematuria_false:a9960bdc` | `haematuria_false` | false | 54 | 54 | 0 | 0 | 0 | 0 | 0 | 54 |
| `haematuria_false:c0157f0d` | `haematuria_false` | false | 52 | 52 | 0 | 0 | 0 | 0 | 0 | 52 |
| `haematuria_false:bae7d81c` | `haematuria_false` | false | 50 | 50 | 44 | 0 | 0 | 0 | 0 | 50 |

*106 further fragments erred on at least one model; the JSON holds them all.*

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
| false | 2479 | **45** | 0.0% [0.0%, 0.0%] |
| null_ambiguous | 3062 | **135** | 100.0% [100.0%, 100.0%] |
| null_structural | 2978 | **1** | 100.0% [100.0%, 100.0%] |
| true | 1481 | **45** | 0.0% [0.0%, 0.0%] |

### By null sub-class

| sub-class | n | eff n | null recall [95% CI] |
|---|---|---|---|
| hedged | 1082 | **45** | 100.0% [100.0%, 100.0%] |
| historical | 1008 | **45** | 100.0% [100.0%, 100.0%] |
| third_party | 972 | **45** | 100.0% [100.0%, 100.0%] |

### By fragment library

| library | n | eff n | accuracy [95% CI] |
|---|---|---|---|
| haematuria_false | 2479 | **45** | 0.0% [0.0%, 0.0%] |
| haematuria_null_hedged | 1082 | **45** | 100.0% [100.0%, 100.0%] |
| haematuria_null_historical | 1008 | **45** | 100.0% [100.0%, 100.0%] |
| haematuria_null_thirdparty | 972 | **45** | 100.0% [100.0%, 100.0%] |
| haematuria_true | 1481 | **45** | 0.0% [0.0%, 0.0%] |
| (none) | 2978 | **1** | 100.0% [100.0%, 100.0%] |

### Per-fragment errors (worst first)

Whether errors are spread thinly across many fragments or piled onto a few is the difference
between "the method is too weak" (model work) and "these specific ideas are not learnable from
the data we have" (library work, and these are the fragments to write more of). No intervals:
a fragment is one cluster, so an interval over its own examples measures nothing.

90 of 225 decisive fragments were got wrong at least once.

`majority_class`: 3960 errors across 90 of 225 decisive fragments. Half of them fall on **32** fragments (an even spread would be 45.0); the worst ten carry 18.0% of all errors.

| fragment | library | sub-class | truth | correct | accuracy | predicted as |
|---|---|---|---|---|---|---|
| `haematuria_false:0e98be72` | `haematuria_false` | -- | false | 0/81 | 0.0% | null 81 |
| `haematuria_false:b3fd19df` | `haematuria_false` | -- | false | 0/76 | 0.0% | null 76 |
| `haematuria_false:56b8af62` | `haematuria_false` | -- | false | 0/75 | 0.0% | null 75 |
| `haematuria_false:94f9de34` | `haematuria_false` | -- | false | 0/75 | 0.0% | null 75 |
| `haematuria_false:acc7804e` | `haematuria_false` | -- | false | 0/73 | 0.0% | null 73 |
| `haematuria_true:c0ff5eed` | `haematuria_true` | -- | true | 0/73 | 0.0% | null 73 |
| `haematuria_false:e23c4950` | `haematuria_false` | -- | false | 0/67 | 0.0% | null 67 |
| `haematuria_false:64933508` | `haematuria_false` | -- | false | 0/65 | 0.0% | null 65 |
| `haematuria_false:b692c4ce` | `haematuria_false` | -- | false | 0/65 | 0.0% | null 65 |
| `haematuria_false:5e090855` | `haematuria_false` | -- | false | 0/64 | 0.0% | null 64 |
| `haematuria_false:a84358ef` | `haematuria_false` | -- | false | 0/64 | 0.0% | null 64 |
| `haematuria_false:cbd9cec5` | `haematuria_false` | -- | false | 0/63 | 0.0% | null 63 |
| `haematuria_false:b0d93eca` | `haematuria_false` | -- | false | 0/62 | 0.0% | null 62 |
| `haematuria_true:972bb99b` | `haematuria_true` | -- | true | 0/62 | 0.0% | null 62 |
| `haematuria_false:873d5c5b` | `haematuria_false` | -- | false | 0/61 | 0.0% | null 61 |
| `haematuria_false:0a0b1113` | `haematuria_false` | -- | false | 0/60 | 0.0% | null 60 |
| `haematuria_true:62126789` | `haematuria_true` | -- | true | 0/60 | 0.0% | null 60 |
| `haematuria_false:7240a8fb` | `haematuria_false` | -- | false | 0/59 | 0.0% | null 59 |
| `haematuria_true:7ea098d1` | `haematuria_true` | -- | true | 0/59 | 0.0% | null 59 |
| `haematuria_true:f2e49699` | `haematuria_true` | -- | true | 0/59 | 0.0% | null 59 |
| `haematuria_false:94644abb` | `haematuria_false` | -- | false | 0/58 | 0.0% | null 58 |
| `haematuria_false:d163df19` | `haematuria_false` | -- | false | 0/58 | 0.0% | null 58 |
| `haematuria_false:fc6a0704` | `haematuria_false` | -- | false | 0/58 | 0.0% | null 58 |
| `haematuria_true:150663fa` | `haematuria_true` | -- | true | 0/58 | 0.0% | null 58 |
| `haematuria_true:d93fd4ce` | `haematuria_true` | -- | true | 0/58 | 0.0% | null 58 |
| `haematuria_false:0722271d` | `haematuria_false` | -- | false | 0/57 | 0.0% | null 57 |
| `haematuria_false:4fda0b2c` | `haematuria_false` | -- | false | 0/57 | 0.0% | null 57 |
| `haematuria_false:cb3cb6e6` | `haematuria_false` | -- | false | 0/57 | 0.0% | null 57 |
| `haematuria_true:6fadb8bc` | `haematuria_true` | -- | true | 0/57 | 0.0% | null 57 |
| `haematuria_false:58488f8a` | `haematuria_false` | -- | false | 0/56 | 0.0% | null 56 |
| `haematuria_false:66629fb1` | `haematuria_false` | -- | false | 0/56 | 0.0% | null 56 |
| `haematuria_false:d9d4737d` | `haematuria_false` | -- | false | 0/56 | 0.0% | null 56 |
| `haematuria_true:245ed73d` | `haematuria_true` | -- | true | 0/56 | 0.0% | null 56 |
| `haematuria_false:5543da20` | `haematuria_false` | -- | false | 0/55 | 0.0% | null 55 |
| `haematuria_false:61bf080a` | `haematuria_false` | -- | false | 0/55 | 0.0% | null 55 |
| `haematuria_false:899e3ed9` | `haematuria_false` | -- | false | 0/55 | 0.0% | null 55 |
| `haematuria_false:9720fe1e` | `haematuria_false` | -- | false | 0/55 | 0.0% | null 55 |
| `haematuria_false:a9960bdc` | `haematuria_false` | -- | false | 0/54 | 0.0% | null 54 |
| `haematuria_false:c0157f0d` | `haematuria_false` | -- | false | 0/52 | 0.0% | null 52 |
| `haematuria_false:bae7d81c` | `haematuria_false` | -- | false | 0/50 | 0.0% | null 50 |

*50 further fragments with at least one error are in the JSON sidecar; every fragment is there regardless of score.*

## `length_only`

Logistic regression on token count alone. The direct measurable test of the length leak: anything materially above majority means text length is a usable proxy for the label, which is a fragment-library problem rather than a model one.

Decision-rule margins selected per fold (on each fold's own validation split): 0.0.
Every fold selected margin 0, so the ruled and raw views below are the same decisions. That is a finding rather than a bug: no margin improved macro-F1 without worsening the `null -> true` rate.

*Confusion matrix, raw argmax*

|  | pred false | pred true | pred null | total |
|---|---|---|---|---|
| **truth false** | 28 | 0 | 2451 | 2479 |
| **truth true** | 1 | 0 | 1480 | 1481 |
| **truth null** | 7 | 0 | 6033 | 6040 |
| **total** | 36 | 0 | 9964 | 10000 |

`null -> true`: 0 of 6040 truly-null examples (0.00%).

*Confusion matrix, after the decision rule*

|  | pred false | pred true | pred null | total |
|---|---|---|---|---|
| **truth false** | 28 | 0 | 2451 | 2479 |
| **truth true** | 1 | 0 | 1480 | 1481 |
| **truth null** | 7 | 0 | 6033 | 6040 |
| **total** | 36 | 0 | 9964 | 10000 |

`null -> true`: 0 of 6040 truly-null examples (0.00%).

### Per class, after the decision rule

| class | support | predicted | precision | recall | F1 |
|---|---|---|---|---|---|
| `false` | 2479 | 36 | 77.8% | 1.1% | 2.2% |
| `true` | 1481 | 0 | -- | 0.0% | 0.0% |
| `null` | 6040 | 9964 | 60.5% | 99.9% | 75.4% |

### By label mode

| label mode | n | eff n | accuracy [95% CI] |
|---|---|---|---|
| false | 2479 | **45** | 1.1% [0.2%, 2.3%] |
| null_ambiguous | 3062 | **135** | 100.0% [100.0%, 100.0%] |
| null_structural | 2978 | **1** | 99.8% [99.8%, 99.8%] |
| true | 1481 | **45** | 0.0% [0.0%, 0.0%] |

### By null sub-class

| sub-class | n | eff n | null recall [95% CI] |
|---|---|---|---|
| hedged | 1082 | **45** | 100.0% [100.0%, 100.0%] |
| historical | 1008 | **45** | 100.0% [100.0%, 100.0%] |
| third_party | 972 | **45** | 100.0% [100.0%, 100.0%] |

### By fragment library

| library | n | eff n | accuracy [95% CI] |
|---|---|---|---|
| haematuria_false | 2479 | **45** | 1.1% [0.2%, 2.3%] |
| haematuria_null_hedged | 1082 | **45** | 100.0% [100.0%, 100.0%] |
| haematuria_null_historical | 1008 | **45** | 100.0% [100.0%, 100.0%] |
| haematuria_null_thirdparty | 972 | **45** | 100.0% [100.0%, 100.0%] |
| haematuria_true | 1481 | **45** | 0.0% [0.0%, 0.0%] |
| (none) | 2978 | **1** | 99.8% [99.8%, 99.8%] |

### Per-fragment errors (worst first)

Whether errors are spread thinly across many fragments or piled onto a few is the difference
between "the method is too weak" (model work) and "these specific ideas are not learnable from
the data we have" (library work, and these are the fragments to write more of). No intervals:
a fragment is one cluster, so an interval over its own examples measures nothing.

90 of 225 decisive fragments were got wrong at least once.

`length_only`: 3932 errors across 90 of 225 decisive fragments. Half of them fall on **32** fragments (an even spread would be 45.0); the worst ten carry 17.8% of all errors.

| fragment | library | sub-class | truth | correct | accuracy | predicted as |
|---|---|---|---|---|---|---|
| `haematuria_false:0e98be72` | `haematuria_false` | -- | false | 0/81 | 0.0% | null 81 |
| `haematuria_false:b3fd19df` | `haematuria_false` | -- | false | 0/76 | 0.0% | null 76 |
| `haematuria_false:56b8af62` | `haematuria_false` | -- | false | 0/75 | 0.0% | null 75 |
| `haematuria_false:acc7804e` | `haematuria_false` | -- | false | 0/73 | 0.0% | null 73 |
| `haematuria_true:c0ff5eed` | `haematuria_true` | -- | true | 0/73 | 0.0% | null 73 |
| `haematuria_false:64933508` | `haematuria_false` | -- | false | 0/65 | 0.0% | null 65 |
| `haematuria_false:b692c4ce` | `haematuria_false` | -- | false | 0/65 | 0.0% | null 65 |
| `haematuria_false:5e090855` | `haematuria_false` | -- | false | 0/64 | 0.0% | null 64 |
| `haematuria_false:a84358ef` | `haematuria_false` | -- | false | 0/64 | 0.0% | null 64 |
| `haematuria_false:cbd9cec5` | `haematuria_false` | -- | false | 0/63 | 0.0% | null 63 |
| `haematuria_false:b0d93eca` | `haematuria_false` | -- | false | 0/62 | 0.0% | null 62 |
| `haematuria_true:972bb99b` | `haematuria_true` | -- | true | 0/62 | 0.0% | null 62 |
| `haematuria_false:873d5c5b` | `haematuria_false` | -- | false | 0/61 | 0.0% | null 61 |
| `haematuria_false:0a0b1113` | `haematuria_false` | -- | false | 0/60 | 0.0% | null 60 |
| `haematuria_true:62126789` | `haematuria_true` | -- | true | 0/60 | 0.0% | null 60 |
| `haematuria_true:7ea098d1` | `haematuria_true` | -- | true | 0/59 | 0.0% | null 59 |
| `haematuria_true:f2e49699` | `haematuria_true` | -- | true | 0/59 | 0.0% | null 59 |
| `haematuria_false:94644abb` | `haematuria_false` | -- | false | 0/58 | 0.0% | null 58 |
| `haematuria_false:d163df19` | `haematuria_false` | -- | false | 0/58 | 0.0% | null 58 |
| `haematuria_false:fc6a0704` | `haematuria_false` | -- | false | 0/58 | 0.0% | null 58 |
| `haematuria_true:150663fa` | `haematuria_true` | -- | true | 0/58 | 0.0% | null 58 |
| `haematuria_true:d93fd4ce` | `haematuria_true` | -- | true | 0/58 | 0.0% | null 58 |
| `haematuria_false:0722271d` | `haematuria_false` | -- | false | 0/57 | 0.0% | null 57 |
| `haematuria_true:6fadb8bc` | `haematuria_true` | -- | true | 0/57 | 0.0% | null 57 |
| `haematuria_false:58488f8a` | `haematuria_false` | -- | false | 0/56 | 0.0% | null 56 |
| `haematuria_false:66629fb1` | `haematuria_false` | -- | false | 0/56 | 0.0% | null 56 |
| `haematuria_false:d9d4737d` | `haematuria_false` | -- | false | 0/56 | 0.0% | null 56 |
| `haematuria_true:245ed73d` | `haematuria_true` | -- | true | 0/56 | 0.0% | null 56 |
| `haematuria_false:5543da20` | `haematuria_false` | -- | false | 0/55 | 0.0% | null 55 |
| `haematuria_false:61bf080a` | `haematuria_false` | -- | false | 0/55 | 0.0% | null 55 |
| `haematuria_false:899e3ed9` | `haematuria_false` | -- | false | 0/55 | 0.0% | null 55 |
| `haematuria_false:a9960bdc` | `haematuria_false` | -- | false | 0/54 | 0.0% | null 54 |
| `haematuria_false:c0157f0d` | `haematuria_false` | -- | false | 0/52 | 0.0% | null 52 |
| `haematuria_false:bae7d81c` | `haematuria_false` | -- | false | 0/50 | 0.0% | null 50 |
| `haematuria_true:ed9c190f` | `haematuria_true` | -- | true | 0/49 | 0.0% | null 49 |
| `haematuria_false:21d7fe6b` | `haematuria_false` | -- | false | 0/47 | 0.0% | null 47 |
| `haematuria_false:75d091ba` | `haematuria_false` | -- | false | 0/47 | 0.0% | null 47 |
| `haematuria_false:079edd39` | `haematuria_false` | -- | false | 0/46 | 0.0% | null 46 |
| `haematuria_false:9c317cf3` | `haematuria_false` | -- | false | 0/46 | 0.0% | null 46 |
| `haematuria_false:f06e4c14` | `haematuria_false` | -- | false | 0/46 | 0.0% | null 46 |

*50 further fragments with at least one error are in the JSON sidecar; every fragment is there regardless of score.*

## `tfidf_logreg`

TF-IDF unigrams and bigrams into logistic regression. Tests whether the dataset is keyword-solvable. Its overall accuracy is close to uninformative; the `null_ambiguous` slice is the number that matters.

Decision-rule margins selected per fold (on each fold's own validation split): 0.0, 0.05.

*Confusion matrix, raw argmax*

|  | pred false | pred true | pred null | total |
|---|---|---|---|---|
| **truth false** | 1702 | 72 | 705 | 2479 |
| **truth true** | 135 | 647 | 699 | 1481 |
| **truth null** | 64 | 131 | 5845 | 6040 |
| **total** | 1901 | 850 | 7249 | 10000 |

`null -> true`: 131 of 6040 truly-null examples (2.17%).

*Confusion matrix, after the decision rule*

|  | pred false | pred true | pred null | total |
|---|---|---|---|---|
| **truth false** | 1702 | 72 | 705 | 2479 |
| **truth true** | 137 | 640 | 704 | 1481 |
| **truth null** | 64 | 130 | 5846 | 6040 |
| **total** | 1903 | 842 | 7255 | 10000 |

`null -> true`: 130 of 6040 truly-null examples (2.15%).

### Per class, after the decision rule

| class | support | predicted | precision | recall | F1 |
|---|---|---|---|---|---|
| `false` | 2479 | 1903 | 89.4% | 68.7% | 77.7% |
| `true` | 1481 | 842 | 76.0% | 43.2% | 55.1% |
| `null` | 6040 | 7255 | 80.6% | 96.8% | 87.9% |

### By label mode

| label mode | n | eff n | accuracy [95% CI] |
|---|---|---|---|
| false | 2479 | **45** | 68.7% [58.7%, 78.6%] |
| null_ambiguous | 3062 | **135** | 93.9% [90.6%, 96.5%] |
| null_structural | 2978 | **1** | 99.8% [99.8%, 99.8%] |
| true | 1481 | **45** | 43.2% [31.3%, 54.8%] |

### By null sub-class

| sub-class | n | eff n | null recall [95% CI] |
|---|---|---|---|
| hedged | 1082 | **45** | 90.9% [82.7%, 96.8%] |
| historical | 1008 | **45** | 93.9% [89.0%, 98.0%] |
| third_party | 972 | **45** | 97.1% [94.0%, 99.4%] |

### By fragment library

| library | n | eff n | accuracy [95% CI] |
|---|---|---|---|
| haematuria_false | 2479 | **45** | 68.7% [58.7%, 78.6%] |
| haematuria_null_hedged | 1082 | **45** | 90.9% [82.7%, 96.8%] |
| haematuria_null_historical | 1008 | **45** | 93.9% [89.0%, 98.0%] |
| haematuria_null_thirdparty | 972 | **45** | 97.1% [94.0%, 99.4%] |
| haematuria_true | 1481 | **45** | 43.2% [31.3%, 54.8%] |
| (none) | 2978 | **1** | 99.8% [99.8%, 99.8%] |

### Per-fragment errors (worst first)

Whether errors are spread thinly across many fragments or piled onto a few is the difference
between "the method is too weak" (model work) and "these specific ideas are not learnable from
the data we have" (library work, and these are the fragments to write more of). No intervals:
a fragment is one cluster, so an interval over its own examples measures nothing.

102 of 225 decisive fragments were got wrong at least once.

`tfidf_logreg`: 1806 errors across 102 of 225 decisive fragments. Half of them fall on **21** fragments (an even spread would be 51.0); the worst ten carry 30.9% of all errors.

| fragment | library | sub-class | truth | correct | accuracy | predicted as |
|---|---|---|---|---|---|---|
| `haematuria_true:c0ff5eed` | `haematuria_true` | -- | true | 0/73 | 0.0% | false 13, null 60 |
| `haematuria_false:cbd9cec5` | `haematuria_false` | -- | false | 0/63 | 0.0% | true 28, null 35 |
| `haematuria_true:ed9c190f` | `haematuria_true` | -- | true | 0/49 | 0.0% | false 28, null 21 |
| `haematuria_true:e93a6a13` | `haematuria_true` | -- | true | 0/36 | 0.0% | null 36 |
| `haematuria_true:b8b1c720` | `haematuria_true` | -- | true | 0/35 | 0.0% | null 35 |
| `haematuria_true:e34024ba` | `haematuria_true` | -- | true | 0/24 | 0.0% | null 24 |
| `haematuria_true:a621d471` | `haematuria_true` | -- | true | 0/21 | 0.0% | null 21 |
| `haematuria_true:fbab8b19` | `haematuria_true` | -- | true | 0/19 | 0.0% | null 19 |
| `haematuria_true:8b82a179` | `haematuria_true` | -- | true | 0/18 | 0.0% | null 18 |
| `haematuria_true:08f72e8e` | `haematuria_true` | -- | true | 0/17 | 0.0% | null 17 |
| `haematuria_false:0e98be72` | `haematuria_false` | -- | false | 1/81 | 1.2% | false 1, true 1, null 79 |
| `haematuria_false:d163df19` | `haematuria_false` | -- | false | 1/58 | 1.7% | false 1, null 57 |
| `haematuria_false:b471d351` | `haematuria_false` | -- | false | 1/40 | 2.5% | false 1, null 39 |
| `haematuria_true:a87130d9` | `haematuria_true` | -- | true | 1/26 | 3.8% | false 18, true 1, null 7 |
| `haematuria_true:16614edd` | `haematuria_true` | -- | true | 2/31 | 6.5% | true 2, null 29 |
| `haematuria_true:f49632f4` | `haematuria_true` | -- | true | 2/26 | 7.7% | true 2, null 24 |
| `haematuria_true:9e0324ed` | `haematuria_true` | -- | true | 2/25 | 8.0% | false 13, true 2, null 10 |
| `haematuria_true:9207612b` | `haematuria_true` | -- | true | 1/11 | 9.1% | false 1, true 1, null 9 |
| `haematuria_true:5cf89fbc` | `haematuria_true` | -- | true | 3/29 | 10.3% | false 7, true 3, null 19 |
| `haematuria_true:e0480739` | `haematuria_true` | -- | true | 3/29 | 10.3% | false 10, true 3, null 16 |
| `haematuria_false:cb3cb6e6` | `haematuria_false` | -- | false | 6/57 | 10.5% | false 6, true 1, null 50 |
| `haematuria_true:b54f9151` | `haematuria_true` | -- | true | 2/18 | 11.1% | false 6, true 2, null 10 |
| `haematuria_false:0a0b1113` | `haematuria_false` | -- | false | 7/60 | 11.7% | false 7, null 53 |
| `haematuria_false:bae7d81c` | `haematuria_false` | -- | false | 6/50 | 12.0% | false 6, true 2, null 42 |
| `haematuria_null_hedged:2e69277b` | `haematuria_null_hedged` | hedged | null | 4/31 | 12.9% | false 27, null 4 |
| `haematuria_true:6fadb8bc` | `haematuria_true` | -- | true | 8/57 | 14.0% | true 8, null 49 |
| `haematuria_true:cfd65dba` | `haematuria_true` | -- | true | 4/24 | 16.7% | false 5, true 4, null 15 |
| `haematuria_true:82bde4df` | `haematuria_true` | -- | true | 5/27 | 18.5% | false 22, true 5 |
| `haematuria_true:f9f24e70` | `haematuria_true` | -- | true | 7/36 | 19.4% | true 7, null 29 |
| `haematuria_null_hedged:0a1e23ec` | `haematuria_null_hedged` | hedged | null | 6/25 | 24.0% | true 19, null 6 |
| `haematuria_true:5f7823a3` | `haematuria_true` | -- | true | 9/34 | 26.5% | true 9, null 25 |
| `haematuria_true:58dc10f0` | `haematuria_true` | -- | true | 7/25 | 28.0% | false 1, true 7, null 17 |
| `haematuria_true:53852edd` | `haematuria_true` | -- | true | 5/16 | 31.2% | true 5, null 11 |
| `haematuria_null_hedged:740e7688` | `haematuria_null_hedged` | hedged | null | 7/22 | 31.8% | false 1, true 14, null 7 |
| `haematuria_null_hedged:58ace8f5` | `haematuria_null_hedged` | hedged | null | 8/25 | 32.0% | true 17, null 8 |
| `haematuria_false:66629fb1` | `haematuria_false` | -- | false | 18/56 | 32.1% | false 18, true 1, null 37 |
| `haematuria_false:d9d4737d` | `haematuria_false` | -- | false | 21/56 | 37.5% | false 21, null 35 |
| `haematuria_null_hedged:f7dcf718` | `haematuria_null_hedged` | hedged | null | 6/15 | 40.0% | true 9, null 6 |
| `haematuria_null_historical:74713fa7` | `haematuria_null_historical` | historical | null | 10/23 | 43.5% | false 10, true 3, null 10 |
| `haematuria_null_historical:2fe3bb50` | `haematuria_null_historical` | historical | null | 7/16 | 43.8% | false 9, null 7 |

*62 further fragments with at least one error are in the JSON sidecar; every fragment is there regardless of score.*

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
| false | 2479 | **45** | 0.0% [0.0%, 0.0%] |
| null_ambiguous | 3062 | **135** | 100.0% [100.0%, 100.0%] |
| null_structural | 2978 | **1** | 100.0% [100.0%, 100.0%] |
| true | 1481 | **45** | 0.0% [0.0%, 0.0%] |

### By null sub-class

| sub-class | n | eff n | null recall [95% CI] |
|---|---|---|---|
| hedged | 1082 | **45** | 100.0% [100.0%, 100.0%] |
| historical | 1008 | **45** | 100.0% [100.0%, 100.0%] |
| third_party | 972 | **45** | 100.0% [100.0%, 100.0%] |

### By fragment library

| library | n | eff n | accuracy [95% CI] |
|---|---|---|---|
| haematuria_false | 2479 | **45** | 0.0% [0.0%, 0.0%] |
| haematuria_null_hedged | 1082 | **45** | 100.0% [100.0%, 100.0%] |
| haematuria_null_historical | 1008 | **45** | 100.0% [100.0%, 100.0%] |
| haematuria_null_thirdparty | 972 | **45** | 100.0% [100.0%, 100.0%] |
| haematuria_true | 1481 | **45** | 0.0% [0.0%, 0.0%] |
| (none) | 2978 | **1** | 100.0% [100.0%, 100.0%] |

### Per-fragment errors (worst first)

Whether errors are spread thinly across many fragments or piled onto a few is the difference
between "the method is too weak" (model work) and "these specific ideas are not learnable from
the data we have" (library work, and these are the fragments to write more of). No intervals:
a fragment is one cluster, so an interval over its own examples measures nothing.

90 of 225 decisive fragments were got wrong at least once.

`length_only__shuffled`: 3960 errors across 90 of 225 decisive fragments. Half of them fall on **32** fragments (an even spread would be 45.0); the worst ten carry 18.0% of all errors.

| fragment | library | sub-class | truth | correct | accuracy | predicted as |
|---|---|---|---|---|---|---|
| `haematuria_false:0e98be72` | `haematuria_false` | -- | false | 0/81 | 0.0% | null 81 |
| `haematuria_false:b3fd19df` | `haematuria_false` | -- | false | 0/76 | 0.0% | null 76 |
| `haematuria_false:56b8af62` | `haematuria_false` | -- | false | 0/75 | 0.0% | null 75 |
| `haematuria_false:94f9de34` | `haematuria_false` | -- | false | 0/75 | 0.0% | null 75 |
| `haematuria_false:acc7804e` | `haematuria_false` | -- | false | 0/73 | 0.0% | null 73 |
| `haematuria_true:c0ff5eed` | `haematuria_true` | -- | true | 0/73 | 0.0% | null 73 |
| `haematuria_false:e23c4950` | `haematuria_false` | -- | false | 0/67 | 0.0% | null 67 |
| `haematuria_false:64933508` | `haematuria_false` | -- | false | 0/65 | 0.0% | null 65 |
| `haematuria_false:b692c4ce` | `haematuria_false` | -- | false | 0/65 | 0.0% | null 65 |
| `haematuria_false:5e090855` | `haematuria_false` | -- | false | 0/64 | 0.0% | null 64 |
| `haematuria_false:a84358ef` | `haematuria_false` | -- | false | 0/64 | 0.0% | null 64 |
| `haematuria_false:cbd9cec5` | `haematuria_false` | -- | false | 0/63 | 0.0% | null 63 |
| `haematuria_false:b0d93eca` | `haematuria_false` | -- | false | 0/62 | 0.0% | null 62 |
| `haematuria_true:972bb99b` | `haematuria_true` | -- | true | 0/62 | 0.0% | null 62 |
| `haematuria_false:873d5c5b` | `haematuria_false` | -- | false | 0/61 | 0.0% | null 61 |
| `haematuria_false:0a0b1113` | `haematuria_false` | -- | false | 0/60 | 0.0% | null 60 |
| `haematuria_true:62126789` | `haematuria_true` | -- | true | 0/60 | 0.0% | null 60 |
| `haematuria_false:7240a8fb` | `haematuria_false` | -- | false | 0/59 | 0.0% | null 59 |
| `haematuria_true:7ea098d1` | `haematuria_true` | -- | true | 0/59 | 0.0% | null 59 |
| `haematuria_true:f2e49699` | `haematuria_true` | -- | true | 0/59 | 0.0% | null 59 |
| `haematuria_false:94644abb` | `haematuria_false` | -- | false | 0/58 | 0.0% | null 58 |
| `haematuria_false:d163df19` | `haematuria_false` | -- | false | 0/58 | 0.0% | null 58 |
| `haematuria_false:fc6a0704` | `haematuria_false` | -- | false | 0/58 | 0.0% | null 58 |
| `haematuria_true:150663fa` | `haematuria_true` | -- | true | 0/58 | 0.0% | null 58 |
| `haematuria_true:d93fd4ce` | `haematuria_true` | -- | true | 0/58 | 0.0% | null 58 |
| `haematuria_false:0722271d` | `haematuria_false` | -- | false | 0/57 | 0.0% | null 57 |
| `haematuria_false:4fda0b2c` | `haematuria_false` | -- | false | 0/57 | 0.0% | null 57 |
| `haematuria_false:cb3cb6e6` | `haematuria_false` | -- | false | 0/57 | 0.0% | null 57 |
| `haematuria_true:6fadb8bc` | `haematuria_true` | -- | true | 0/57 | 0.0% | null 57 |
| `haematuria_false:58488f8a` | `haematuria_false` | -- | false | 0/56 | 0.0% | null 56 |
| `haematuria_false:66629fb1` | `haematuria_false` | -- | false | 0/56 | 0.0% | null 56 |
| `haematuria_false:d9d4737d` | `haematuria_false` | -- | false | 0/56 | 0.0% | null 56 |
| `haematuria_true:245ed73d` | `haematuria_true` | -- | true | 0/56 | 0.0% | null 56 |
| `haematuria_false:5543da20` | `haematuria_false` | -- | false | 0/55 | 0.0% | null 55 |
| `haematuria_false:61bf080a` | `haematuria_false` | -- | false | 0/55 | 0.0% | null 55 |
| `haematuria_false:899e3ed9` | `haematuria_false` | -- | false | 0/55 | 0.0% | null 55 |
| `haematuria_false:9720fe1e` | `haematuria_false` | -- | false | 0/55 | 0.0% | null 55 |
| `haematuria_false:a9960bdc` | `haematuria_false` | -- | false | 0/54 | 0.0% | null 54 |
| `haematuria_false:c0157f0d` | `haematuria_false` | -- | false | 0/52 | 0.0% | null 52 |
| `haematuria_false:bae7d81c` | `haematuria_false` | -- | false | 0/50 | 0.0% | null 50 |

*50 further fragments with at least one error are in the JSON sidecar; every fragment is there regardless of score.*

## `tfidf_logreg__shuffled`

TF-IDF unigrams and bigrams into logistic regression. Tests whether the dataset is keyword-solvable. Its overall accuracy is close to uninformative; the `null_ambiguous` slice is the number that matters. **Negative control:** trained on permuted training labels (seed 7) and evaluated on the unpermuted test split, where it must land at chance.

Decision-rule margins selected per fold (on each fold's own validation split): 0.0.
Every fold selected margin 0, so the ruled and raw views below are the same decisions. That is a finding rather than a bug: no margin improved macro-F1 without worsening the `null -> true` rate.

*Confusion matrix, raw argmax*

|  | pred false | pred true | pred null | total |
|---|---|---|---|---|
| **truth false** | 1 | 0 | 2478 | 2479 |
| **truth true** | 1 | 0 | 1480 | 1481 |
| **truth null** | 1 | 0 | 6039 | 6040 |
| **total** | 3 | 0 | 9997 | 10000 |

`null -> true`: 0 of 6040 truly-null examples (0.00%).

*Confusion matrix, after the decision rule*

|  | pred false | pred true | pred null | total |
|---|---|---|---|---|
| **truth false** | 1 | 0 | 2478 | 2479 |
| **truth true** | 1 | 0 | 1480 | 1481 |
| **truth null** | 1 | 0 | 6039 | 6040 |
| **total** | 3 | 0 | 9997 | 10000 |

`null -> true`: 0 of 6040 truly-null examples (0.00%).

### Per class, after the decision rule

| class | support | predicted | precision | recall | F1 |
|---|---|---|---|---|---|
| `false` | 2479 | 3 | 33.3% | 0.0% | 0.1% |
| `true` | 1481 | 0 | -- | 0.0% | 0.0% |
| `null` | 6040 | 9997 | 60.4% | 100.0% | 75.3% |

### By label mode

| label mode | n | eff n | accuracy [95% CI] |
|---|---|---|---|
| false | 2479 | **45** | 0.0% [0.0%, 0.1%] |
| null_ambiguous | 3062 | **135** | 100.0% [100.0%, 100.0%] |
| null_structural | 2978 | **1** | 100.0% [100.0%, 100.0%] |
| true | 1481 | **45** | 0.0% [0.0%, 0.0%] |

### By null sub-class

| sub-class | n | eff n | null recall [95% CI] |
|---|---|---|---|
| hedged | 1082 | **45** | 100.0% [100.0%, 100.0%] |
| historical | 1008 | **45** | 100.0% [100.0%, 100.0%] |
| third_party | 972 | **45** | 100.0% [100.0%, 100.0%] |

### By fragment library

| library | n | eff n | accuracy [95% CI] |
|---|---|---|---|
| haematuria_false | 2479 | **45** | 0.0% [0.0%, 0.1%] |
| haematuria_null_hedged | 1082 | **45** | 100.0% [100.0%, 100.0%] |
| haematuria_null_historical | 1008 | **45** | 100.0% [100.0%, 100.0%] |
| haematuria_null_thirdparty | 972 | **45** | 100.0% [100.0%, 100.0%] |
| haematuria_true | 1481 | **45** | 0.0% [0.0%, 0.0%] |
| (none) | 2978 | **1** | 100.0% [100.0%, 100.0%] |

### Per-fragment errors (worst first)

Whether errors are spread thinly across many fragments or piled onto a few is the difference
between "the method is too weak" (model work) and "these specific ideas are not learnable from
the data we have" (library work, and these are the fragments to write more of). No intervals:
a fragment is one cluster, so an interval over its own examples measures nothing.

90 of 225 decisive fragments were got wrong at least once.

`tfidf_logreg__shuffled`: 3959 errors across 90 of 225 decisive fragments. Half of them fall on **32** fragments (an even spread would be 45.0); the worst ten carry 18.0% of all errors.

| fragment | library | sub-class | truth | correct | accuracy | predicted as |
|---|---|---|---|---|---|---|
| `haematuria_false:0e98be72` | `haematuria_false` | -- | false | 0/81 | 0.0% | null 81 |
| `haematuria_false:b3fd19df` | `haematuria_false` | -- | false | 0/76 | 0.0% | null 76 |
| `haematuria_false:56b8af62` | `haematuria_false` | -- | false | 0/75 | 0.0% | null 75 |
| `haematuria_false:94f9de34` | `haematuria_false` | -- | false | 0/75 | 0.0% | null 75 |
| `haematuria_false:acc7804e` | `haematuria_false` | -- | false | 0/73 | 0.0% | null 73 |
| `haematuria_true:c0ff5eed` | `haematuria_true` | -- | true | 0/73 | 0.0% | null 73 |
| `haematuria_false:e23c4950` | `haematuria_false` | -- | false | 0/67 | 0.0% | null 67 |
| `haematuria_false:64933508` | `haematuria_false` | -- | false | 0/65 | 0.0% | null 65 |
| `haematuria_false:b692c4ce` | `haematuria_false` | -- | false | 0/65 | 0.0% | null 65 |
| `haematuria_false:5e090855` | `haematuria_false` | -- | false | 0/64 | 0.0% | null 64 |
| `haematuria_false:a84358ef` | `haematuria_false` | -- | false | 0/64 | 0.0% | null 64 |
| `haematuria_false:cbd9cec5` | `haematuria_false` | -- | false | 0/63 | 0.0% | null 63 |
| `haematuria_false:b0d93eca` | `haematuria_false` | -- | false | 0/62 | 0.0% | null 62 |
| `haematuria_true:972bb99b` | `haematuria_true` | -- | true | 0/62 | 0.0% | null 62 |
| `haematuria_false:873d5c5b` | `haematuria_false` | -- | false | 0/61 | 0.0% | null 61 |
| `haematuria_false:0a0b1113` | `haematuria_false` | -- | false | 0/60 | 0.0% | null 60 |
| `haematuria_true:62126789` | `haematuria_true` | -- | true | 0/60 | 0.0% | null 60 |
| `haematuria_false:7240a8fb` | `haematuria_false` | -- | false | 0/59 | 0.0% | null 59 |
| `haematuria_true:7ea098d1` | `haematuria_true` | -- | true | 0/59 | 0.0% | false 1, null 58 |
| `haematuria_true:f2e49699` | `haematuria_true` | -- | true | 0/59 | 0.0% | null 59 |
| `haematuria_false:94644abb` | `haematuria_false` | -- | false | 0/58 | 0.0% | null 58 |
| `haematuria_false:d163df19` | `haematuria_false` | -- | false | 0/58 | 0.0% | null 58 |
| `haematuria_false:fc6a0704` | `haematuria_false` | -- | false | 0/58 | 0.0% | null 58 |
| `haematuria_true:150663fa` | `haematuria_true` | -- | true | 0/58 | 0.0% | null 58 |
| `haematuria_true:d93fd4ce` | `haematuria_true` | -- | true | 0/58 | 0.0% | null 58 |
| `haematuria_false:0722271d` | `haematuria_false` | -- | false | 0/57 | 0.0% | null 57 |
| `haematuria_false:4fda0b2c` | `haematuria_false` | -- | false | 0/57 | 0.0% | null 57 |
| `haematuria_false:cb3cb6e6` | `haematuria_false` | -- | false | 0/57 | 0.0% | null 57 |
| `haematuria_true:6fadb8bc` | `haematuria_true` | -- | true | 0/57 | 0.0% | null 57 |
| `haematuria_false:58488f8a` | `haematuria_false` | -- | false | 0/56 | 0.0% | null 56 |
| `haematuria_false:66629fb1` | `haematuria_false` | -- | false | 0/56 | 0.0% | null 56 |
| `haematuria_true:245ed73d` | `haematuria_true` | -- | true | 0/56 | 0.0% | null 56 |
| `haematuria_false:5543da20` | `haematuria_false` | -- | false | 0/55 | 0.0% | null 55 |
| `haematuria_false:61bf080a` | `haematuria_false` | -- | false | 0/55 | 0.0% | null 55 |
| `haematuria_false:899e3ed9` | `haematuria_false` | -- | false | 0/55 | 0.0% | null 55 |
| `haematuria_false:9720fe1e` | `haematuria_false` | -- | false | 0/55 | 0.0% | null 55 |
| `haematuria_false:a9960bdc` | `haematuria_false` | -- | false | 0/54 | 0.0% | null 54 |
| `haematuria_false:c0157f0d` | `haematuria_false` | -- | false | 0/52 | 0.0% | null 52 |
| `haematuria_false:bae7d81c` | `haematuria_false` | -- | false | 0/50 | 0.0% | null 50 |
| `haematuria_true:ed9c190f` | `haematuria_true` | -- | true | 0/49 | 0.0% | null 49 |

*50 further fragments with at least one error are in the JSON sidecar; every fragment is there regardless of score.*

## `arm_b_finetune@c0.0-d0.0`

`roberta-base` with **every layer unfrozen**, mean-pooled, with the same `Linear(768, 3)` head -- 110M trainable parameters against Arm A's 2,307. Three epochs at batch 32, learning rate 2e-5, 10% linear warmup, AdamW, fp32. No gradient checkpointing, no 8-bit optimiser, no LoRA, no gradient accumulation: the full model fits in 12GB with room to spare, so anything that reads like a compute compromise would be a mistake rather than a saving. This is the arm that separates "the fragment libraries are the bottleneck" from "the method is too weak": if a fully fine-tuned encoder still cannot read third-party attribution, tense or metaphor, the limit is in the ideas the libraries contain and the fix is library work, not model work.

Decision-rule margins selected per fold (on each fold's own validation split): 0.0, 0.4, 0.8, 0.9.

*Confusion matrix, raw argmax*

|  | pred false | pred true | pred null | total |
|---|---|---|---|---|
| **truth false** | 2293 | 84 | 102 | 2479 |
| **truth true** | 8 | 1328 | 145 | 1481 |
| **truth null** | 111 | 149 | 5780 | 6040 |
| **total** | 2412 | 1561 | 6027 | 10000 |

`null -> true`: 149 of 6040 truly-null examples (2.47%).

*Confusion matrix, after the decision rule*

|  | pred false | pred true | pred null | total |
|---|---|---|---|---|
| **truth false** | 2295 | 81 | 103 | 2479 |
| **truth true** | 14 | 1305 | 162 | 1481 |
| **truth null** | 114 | 134 | 5792 | 6040 |
| **total** | 2423 | 1520 | 6057 | 10000 |

`null -> true`: 134 of 6040 truly-null examples (2.22%).

### Per class, after the decision rule

| class | support | predicted | precision | recall | F1 |
|---|---|---|---|---|---|
| `false` | 2479 | 2423 | 94.7% | 92.6% | 93.6% |
| `true` | 1481 | 1520 | 85.9% | 88.1% | 87.0% |
| `null` | 6040 | 6057 | 95.6% | 95.9% | 95.8% |

### By label mode

| label mode | n | eff n | accuracy [95% CI] |
|---|---|---|---|
| false | 2479 | **45** | 92.6% [85.2%, 98.4%] |
| null_ambiguous | 3062 | **135** | 91.9% [87.3%, 95.9%] |
| null_structural | 2978 | **1** | 100.0% [100.0%, 100.0%] |
| true | 1481 | **45** | 88.1% [78.7%, 95.7%] |

### By null sub-class

| sub-class | n | eff n | null recall [95% CI] |
|---|---|---|---|
| hedged | 1082 | **45** | 80.8% [69.5%, 90.4%] |
| historical | 1008 | **45** | 98.3% [95.5%, 100.0%] |
| third_party | 972 | **45** | 97.6% [93.3%, 100.0%] |

### By fragment library

| library | n | eff n | accuracy [95% CI] |
|---|---|---|---|
| haematuria_false | 2479 | **45** | 92.6% [85.2%, 98.4%] |
| haematuria_null_hedged | 1082 | **45** | 80.8% [69.5%, 90.4%] |
| haematuria_null_historical | 1008 | **45** | 98.3% [95.5%, 100.0%] |
| haematuria_null_thirdparty | 972 | **45** | 97.6% [93.3%, 100.0%] |
| haematuria_true | 1481 | **45** | 88.1% [78.7%, 95.7%] |
| (none) | 2978 | **1** | 100.0% [100.0%, 100.0%] |

### Per-fragment errors (worst first)

Whether errors are spread thinly across many fragments or piled onto a few is the difference
between "the method is too weak" (model work) and "these specific ideas are not learnable from
the data we have" (library work, and these are the fragments to write more of). No intervals:
a fragment is one cluster, so an interval over its own examples measures nothing.

35 of 225 decisive fragments were got wrong at least once.

`arm_b_finetune@c0.0-d0.0`: 608 errors across 35 of 225 decisive fragments. Half of them fall on **8** fragments (an even spread would be 17.5); the worst ten carry 60.7% of all errors.

| fragment | library | sub-class | truth | correct | accuracy | predicted as |
|---|---|---|---|---|---|---|
| `haematuria_false:d163df19` | `haematuria_false` | -- | false | 0/58 | 0.0% | null 58 |
| `haematuria_true:6fadb8bc` | `haematuria_true` | -- | true | 0/57 | 0.0% | null 57 |
| `haematuria_false:b471d351` | `haematuria_false` | -- | false | 0/40 | 0.0% | true 40 |
| `haematuria_false:eaac464c` | `haematuria_false` | -- | false | 0/40 | 0.0% | true 39, null 1 |
| `haematuria_null_hedged:ad81f888` | `haematuria_null_hedged` | hedged | null | 0/26 | 0.0% | true 26 |
| `haematuria_null_hedged:0a1e23ec` | `haematuria_null_hedged` | hedged | null | 0/25 | 0.0% | true 25 |
| `haematuria_null_hedged:d64cf17c` | `haematuria_null_hedged` | hedged | null | 0/24 | 0.0% | true 24 |
| `haematuria_null_hedged:740e7688` | `haematuria_null_hedged` | hedged | null | 0/22 | 0.0% | false 22 |
| `haematuria_null_hedged:b46c1780` | `haematuria_null_hedged` | hedged | null | 0/21 | 0.0% | false 20, true 1 |
| `haematuria_null_hedged:dc7c4c42` | `haematuria_null_hedged` | hedged | null | 0/21 | 0.0% | false 21 |
| `haematuria_true:9207612b` | `haematuria_true` | -- | true | 0/11 | 0.0% | null 11 |
| `haematuria_null_thirdparty:59ca6590` | `haematuria_null_thirdparty` | third_party | null | 1/19 | 5.3% | true 18, null 1 |
| `haematuria_true:fbab8b19` | `haematuria_true` | -- | true | 1/19 | 5.3% | true 1, null 18 |
| `haematuria_null_hedged:8524c012` | `haematuria_null_hedged` | hedged | null | 2/28 | 7.1% | false 26, null 2 |
| `haematuria_null_hedged:f5ac0bee` | `haematuria_null_hedged` | hedged | null | 1/13 | 7.7% | false 12, null 1 |
| `haematuria_null_hedged:211cfe81` | `haematuria_null_hedged` | hedged | null | 3/16 | 18.8% | false 1, true 12, null 3 |
| `haematuria_true:a87130d9` | `haematuria_true` | -- | true | 6/26 | 23.1% | true 6, null 20 |
| `haematuria_null_historical:8a3575e2` | `haematuria_null_historical` | historical | null | 4/16 | 25.0% | false 12, null 4 |
| `haematuria_false:cb3cb6e6` | `haematuria_false` | -- | false | 18/57 | 31.6% | false 18, true 1, null 38 |
| `haematuria_true:08f72e8e` | `haematuria_true` | -- | true | 7/17 | 41.2% | false 10, true 7 |
| `haematuria_true:c0ff5eed` | `haematuria_true` | -- | true | 39/73 | 53.4% | true 39, null 34 |
| `haematuria_null_hedged:e2b503fc` | `haematuria_null_hedged` | hedged | null | 16/27 | 59.3% | true 11, null 16 |
| `haematuria_null_hedged:d9bf40cb` | `haematuria_null_hedged` | hedged | null | 13/19 | 68.4% | true 6, null 13 |
| `haematuria_true:e34024ba` | `haematuria_true` | -- | true | 17/24 | 70.8% | true 17, null 7 |
| `haematuria_null_thirdparty:161d26ba` | `haematuria_null_thirdparty` | third_party | null | 14/19 | 73.7% | true 5, null 14 |
| `haematuria_true:e93a6a13` | `haematuria_true` | -- | true | 29/36 | 80.6% | true 29, null 7 |
| `haematuria_true:a621d471` | `haematuria_true` | -- | true | 18/21 | 85.7% | true 18, null 3 |
| `haematuria_null_historical:7ddf228a` | `haematuria_null_historical` | historical | null | 31/36 | 86.1% | true 5, null 31 |
| `haematuria_false:d9d4737d` | `haematuria_false` | -- | false | 49/56 | 87.5% | false 49, true 1, null 6 |
| `haematuria_true:6773fb2e` | `haematuria_true` | -- | true | 32/36 | 88.9% | false 4, true 32 |
| `haematuria_true:b8b1c720` | `haematuria_true` | -- | true | 33/35 | 94.3% | true 33, null 2 |
| `haematuria_true:ec01803e` | `haematuria_true` | -- | true | 22/23 | 95.7% | true 22, null 1 |
| `haematuria_null_hedged:1ee357f9` | `haematuria_null_hedged` | hedged | null | 25/26 | 96.2% | true 1, null 25 |
| `haematuria_true:5cf89fbc` | `haematuria_true` | -- | true | 28/29 | 96.6% | true 28, null 1 |
| `haematuria_true:f2e49699` | `haematuria_true` | -- | true | 58/59 | 98.3% | true 58, null 1 |

## `arm_b_finetune@c0.0-d0.3`

`roberta-base` with **every layer unfrozen**, mean-pooled, with the same `Linear(768, 3)` head -- 110M trainable parameters against Arm A's 2,307. Three epochs at batch 32, learning rate 2e-5, 10% linear warmup, AdamW, fp32. No gradient checkpointing, no 8-bit optimiser, no LoRA, no gradient accumulation: the full model fits in 12GB with room to spare, so anything that reads like a compute compromise would be a mistake rather than a saving. This is the arm that separates "the fragment libraries are the bottleneck" from "the method is too weak": if a fully fine-tuned encoder still cannot read third-party attribution, tense or metaphor, the limit is in the ideas the libraries contain and the fix is library work, not model work.

Decision-rule margins selected per fold (on each fold's own validation split): 0.15, 0.6, 0.65, 0.8, 0.9.

*Confusion matrix, raw argmax*

|  | pred false | pred true | pred null | total |
|---|---|---|---|---|
| **truth false** | 2333 | 72 | 74 | 2479 |
| **truth true** | 6 | 1382 | 93 | 1481 |
| **truth null** | 34 | 146 | 5860 | 6040 |
| **total** | 2373 | 1600 | 6027 | 10000 |

`null -> true`: 146 of 6040 truly-null examples (2.42%).

*Confusion matrix, after the decision rule*

|  | pred false | pred true | pred null | total |
|---|---|---|---|---|
| **truth false** | 2335 | 67 | 77 | 2479 |
| **truth true** | 8 | 1366 | 107 | 1481 |
| **truth null** | 34 | 132 | 5874 | 6040 |
| **total** | 2377 | 1565 | 6058 | 10000 |

`null -> true`: 132 of 6040 truly-null examples (2.19%).

### Per class, after the decision rule

| class | support | predicted | precision | recall | F1 |
|---|---|---|---|---|---|
| `false` | 2479 | 2377 | 98.2% | 94.2% | 96.2% |
| `true` | 1481 | 1565 | 87.3% | 92.2% | 89.7% |
| `null` | 6040 | 6058 | 97.0% | 97.3% | 97.1% |

### By label mode

| label mode | n | eff n | accuracy [95% CI] |
|---|---|---|---|
| false | 2479 | **128** | 94.2% [88.1%, 98.6%] |
| null_ambiguous | 3062 | **135** | 94.6% [91.1%, 97.6%] |
| null_structural | 2978 | **1** | 100.0% [100.0%, 100.0%] |
| true | 1481 | **124** | 92.2% [85.4%, 98.2%] |

### By null sub-class

| sub-class | n | eff n | null recall [95% CI] |
|---|---|---|---|
| hedged | 1082 | **45** | 87.7% [78.4%, 95.3%] |
| historical | 1008 | **45** | 98.6% [96.6%, 100.0%] |
| third_party | 972 | **45** | 98.0% [95.0%, 100.0%] |

### By fragment library

| library | n | eff n | accuracy [95% CI] |
|---|---|---|---|
| declarative_v1 | 1239 | **162** | 99.9% [99.7%, 100.0%] |
| haematuria_false | 1704 | **45** | 91.5% [83.1%, 98.0%] |
| haematuria_null_hedged | 1082 | **45** | 87.7% [78.4%, 95.3%] |
| haematuria_null_historical | 1008 | **45** | 98.6% [96.6%, 100.0%] |
| haematuria_null_thirdparty | 972 | **45** | 98.0% [95.0%, 100.0%] |
| haematuria_true | 1017 | **45** | 88.8% [78.9%, 97.0%] |
| (none) | 2978 | **1** | 100.0% [100.0%, 100.0%] |

### Per-fragment errors (worst first)

Whether errors are spread thinly across many fragments or piled onto a few is the difference
between "the method is too weak" (model work) and "these specific ideas are not learnable from
the data we have" (library work, and these are the fragments to write more of). No intervals:
a fragment is one cluster, so an interval over its own examples measures nothing.

33 of 643 decisive fragments were got wrong at least once.

`arm_b_finetune@c0.0-d0.3`: 425 errors across 33 of 643 decisive fragments. Half of them fall on **6** fragments (an even spread would be 16.5); the worst ten carry 72.5% of all errors.

| fragment | library | sub-class | truth | correct | accuracy | predicted as |
|---|---|---|---|---|---|---|
| `haematuria_true:6fadb8bc` | `haematuria_true` | -- | true | 0/41 | 0.0% | null 41 |
| `haematuria_false:d163df19` | `haematuria_false` | -- | false | 0/36 | 0.0% | null 36 |
| `haematuria_null_hedged:ad81f888` | `haematuria_null_hedged` | hedged | null | 0/26 | 0.0% | true 26 |
| `haematuria_null_hedged:0a1e23ec` | `haematuria_null_hedged` | hedged | null | 0/25 | 0.0% | true 25 |
| `haematuria_null_hedged:d64cf17c` | `haematuria_null_hedged` | hedged | null | 0/24 | 0.0% | true 24 |
| `haematuria_true:9207612b` | `haematuria_true` | -- | true | 0/12 | 0.0% | null 12 |
| `haematuria_null_thirdparty:610eccad` | `haematuria_null_thirdparty` | third_party | null | 0/11 | 0.0% | true 11 |
| `haematuria_false:eaac464c` | `haematuria_false` | -- | false | 1/42 | 2.4% | false 1, true 5, null 36 |
| `haematuria_false:b471d351` | `haematuria_false` | -- | false | 1/36 | 2.8% | false 1, true 35 |
| `haematuria_null_hedged:dc7c4c42` | `haematuria_null_hedged` | hedged | null | 1/21 | 4.8% | false 20, null 1 |
| `haematuria_false:cb3cb6e6` | `haematuria_false` | -- | false | 5/35 | 14.3% | false 5, true 27, null 3 |
| `haematuria_true:c0ff5eed` | `haematuria_true` | -- | true | 15/45 | 33.3% | true 15, null 30 |
| `haematuria_true:08f72e8e` | `haematuria_true` | -- | true | 6/14 | 42.9% | false 7, true 6, null 1 |
| `declarative_v1:866d5ae5` | `declarative_v1` | -- | true | 1/2 | 50.0% | false 1, true 1 |
| `haematuria_null_hedged:740e7688` | `haematuria_null_hedged` | hedged | null | 12/22 | 54.5% | false 10, null 12 |
| `haematuria_true:fbab8b19` | `haematuria_true` | -- | true | 6/11 | 54.5% | true 6, null 5 |
| `haematuria_true:e93a6a13` | `haematuria_true` | -- | true | 16/27 | 59.3% | true 16, null 11 |
| `haematuria_null_hedged:1ee357f9` | `haematuria_null_hedged` | hedged | null | 17/26 | 65.4% | true 9, null 17 |
| `haematuria_true:a87130d9` | `haematuria_true` | -- | true | 14/20 | 70.0% | true 14, null 6 |
| `haematuria_null_hedged:b46c1780` | `haematuria_null_hedged` | hedged | null | 15/21 | 71.4% | false 4, true 2, null 15 |
| `haematuria_null_historical:d046cb69` | `haematuria_null_historical` | historical | null | 22/30 | 73.3% | true 8, null 22 |
| `haematuria_null_thirdparty:161d26ba` | `haematuria_null_thirdparty` | third_party | null | 15/19 | 78.9% | true 4, null 15 |
| `haematuria_null_thirdparty:59ca6590` | `haematuria_null_thirdparty` | third_party | null | 15/19 | 78.9% | true 4, null 15 |
| `haematuria_null_hedged:086f7067` | `haematuria_null_hedged` | hedged | null | 30/37 | 81.1% | true 7, null 30 |
| `haematuria_null_historical:7ddf228a` | `haematuria_null_historical` | historical | null | 31/36 | 86.1% | true 5, null 31 |
| `haematuria_null_hedged:80ec8e70` | `haematuria_null_hedged` | hedged | null | 21/23 | 91.3% | true 2, null 21 |
| `haematuria_null_hedged:f5ac0bee` | `haematuria_null_hedged` | hedged | null | 12/13 | 92.3% | true 1, null 12 |
| `haematuria_true:ec01803e` | `haematuria_true` | -- | true | 14/15 | 93.3% | true 14, null 1 |
| `haematuria_null_hedged:211cfe81` | `haematuria_null_hedged` | hedged | null | 15/16 | 93.8% | true 1, null 15 |
| `haematuria_null_hedged:0dd010bf` | `haematuria_null_hedged` | hedged | null | 20/21 | 95.2% | true 1, null 20 |
| `haematuria_false:0e98be72` | `haematuria_false` | -- | false | 41/43 | 95.3% | false 41, null 2 |
| `haematuria_null_historical:b0ea834e` | `haematuria_null_historical` | historical | null | 21/22 | 95.5% | true 1, null 21 |
| `haematuria_null_hedged:e2b503fc` | `haematuria_null_hedged` | hedged | null | 26/27 | 96.3% | true 1, null 26 |

## `arm_b_finetune@c0.5-d0.0`

`roberta-base` with **every layer unfrozen**, mean-pooled, with the same `Linear(768, 3)` head -- 110M trainable parameters against Arm A's 2,307. Three epochs at batch 32, learning rate 2e-5, 10% linear warmup, AdamW, fp32. No gradient checkpointing, no 8-bit optimiser, no LoRA, no gradient accumulation: the full model fits in 12GB with room to spare, so anything that reads like a compute compromise would be a mistake rather than a saving. This is the arm that separates "the fragment libraries are the bottleneck" from "the method is too weak": if a fully fine-tuned encoder still cannot read third-party attribution, tense or metaphor, the limit is in the ideas the libraries contain and the fix is library work, not model work.

Decision-rule margins selected per fold (on each fold's own validation split): 0.0, 0.55, 0.9.

*Confusion matrix, raw argmax*

|  | pred false | pred true | pred null | total |
|---|---|---|---|---|
| **truth false** | 2127 | 57 | 295 | 2479 |
| **truth true** | 17 | 1329 | 135 | 1481 |
| **truth null** | 28 | 206 | 5806 | 6040 |
| **total** | 2172 | 1592 | 6236 | 10000 |

`null -> true`: 206 of 6040 truly-null examples (3.41%).

*Confusion matrix, after the decision rule*

|  | pred false | pred true | pred null | total |
|---|---|---|---|---|
| **truth false** | 2127 | 56 | 296 | 2479 |
| **truth true** | 18 | 1299 | 164 | 1481 |
| **truth null** | 31 | 188 | 5821 | 6040 |
| **total** | 2176 | 1543 | 6281 | 10000 |

`null -> true`: 188 of 6040 truly-null examples (3.11%).

### Per class, after the decision rule

| class | support | predicted | precision | recall | F1 |
|---|---|---|---|---|---|
| `false` | 2479 | 2176 | 97.7% | 85.8% | 91.4% |
| `true` | 1481 | 1543 | 84.2% | 87.7% | 85.9% |
| `null` | 6040 | 6281 | 92.7% | 96.4% | 94.5% |

### By label mode

| label mode | n | eff n | accuracy [95% CI] |
|---|---|---|---|
| false | 2479 | **45** | 85.8% [75.5%, 94.7%] |
| null_ambiguous | 3062 | **135** | 93.1% [88.9%, 96.8%] |
| null_structural | 2978 | **1** | 99.7% [99.7%, 99.7%] |
| true | 1481 | **45** | 87.7% [77.5%, 95.7%] |

### By null sub-class

| sub-class | n | eff n | null recall [95% CI] |
|---|---|---|---|
| hedged | 1079 | **45** | 85.8% [76.5%, 94.1%] |
| historical | 1017 | **45** | 95.1% [87.5%, 99.8%] |
| third_party | 966 | **45** | 99.2% [97.8%, 100.0%] |

### By fragment library

| library | n | eff n | accuracy [95% CI] |
|---|---|---|---|
| haematuria_false | 2479 | **45** | 85.8% [75.5%, 94.7%] |
| haematuria_null_hedged | 1079 | **45** | 85.8% [76.5%, 94.1%] |
| haematuria_null_historical | 1017 | **45** | 95.1% [87.5%, 99.8%] |
| haematuria_null_thirdparty | 966 | **45** | 99.2% [97.8%, 100.0%] |
| haematuria_true | 1481 | **45** | 87.7% [77.5%, 95.7%] |
| (none) | 2978 | **1** | 99.7% [99.7%, 99.7%] |

### Per-fragment errors (worst first)

Whether errors are spread thinly across many fragments or piled onto a few is the difference
between "the method is too weak" (model work) and "these specific ideas are not learnable from
the data we have" (library work, and these are the fragments to write more of). No intervals:
a fragment is one cluster, so an interval over its own examples measures nothing.

48 of 225 decisive fragments were got wrong at least once.

`arm_b_finetune@c0.5-d0.0`: 745 errors across 48 of 225 decisive fragments. Half of them fall on **8** fragments (an even spread would be 24.0); the worst ten carry 61.1% of all errors.

| fragment | library | sub-class | truth | correct | accuracy | predicted as |
|---|---|---|---|---|---|---|
| `haematuria_true:6fadb8bc` | `haematuria_true` | -- | true | 0/59 | 0.0% | null 59 |
| `haematuria_false:d9d4737d` | `haematuria_false` | -- | false | 0/55 | 0.0% | true 3, null 52 |
| `haematuria_false:b471d351` | `haematuria_false` | -- | false | 0/39 | 0.0% | true 39 |
| `haematuria_false:eaac464c` | `haematuria_false` | -- | false | 0/39 | 0.0% | true 13, null 26 |
| `haematuria_null_historical:7ddf228a` | `haematuria_null_historical` | historical | null | 0/38 | 0.0% | true 38 |
| `haematuria_false:a3acb31d` | `haematuria_false` | -- | false | 0/37 | 0.0% | null 37 |
| `haematuria_true:a87130d9` | `haematuria_true` | -- | true | 0/25 | 0.0% | null 25 |
| `haematuria_null_hedged:0a1e23ec` | `haematuria_null_hedged` | hedged | null | 0/24 | 0.0% | true 24 |
| `haematuria_null_hedged:d64cf17c` | `haematuria_null_hedged` | hedged | null | 0/24 | 0.0% | true 24 |
| `haematuria_null_hedged:740e7688` | `haematuria_null_hedged` | hedged | null | 0/21 | 0.0% | false 1, true 20 |
| `haematuria_true:08f72e8e` | `haematuria_true` | -- | true | 0/18 | 0.0% | false 18 |
| `haematuria_false:0e98be72` | `haematuria_false` | -- | false | 1/82 | 1.2% | false 1, null 81 |
| `haematuria_false:d163df19` | `haematuria_false` | -- | false | 1/57 | 1.8% | false 1, true 1, null 55 |
| `haematuria_null_hedged:dc7c4c42` | `haematuria_null_hedged` | hedged | null | 2/21 | 9.5% | false 19, null 2 |
| `haematuria_null_hedged:64409bb8` | `haematuria_null_hedged` | hedged | null | 6/30 | 20.0% | true 24, null 6 |
| `haematuria_true:16614edd` | `haematuria_true` | -- | true | 9/32 | 28.1% | true 9, null 23 |
| `haematuria_true:b8b1c720` | `haematuria_true` | -- | true | 11/36 | 30.6% | true 11, null 25 |
| `haematuria_null_hedged:ad81f888` | `haematuria_null_hedged` | hedged | null | 12/26 | 46.2% | true 14, null 12 |
| `haematuria_false:0a0b1113` | `haematuria_false` | -- | false | 30/56 | 53.6% | false 30, null 26 |
| `haematuria_null_hedged:1c99942a` | `haematuria_null_hedged` | hedged | null | 17/31 | 54.8% | true 14, null 17 |
| `haematuria_null_hedged:211cfe81` | `haematuria_null_hedged` | hedged | null | 11/16 | 68.8% | false 2, true 3, null 11 |
| `haematuria_true:e34024ba` | `haematuria_true` | -- | true | 16/22 | 72.7% | true 16, null 6 |
| `haematuria_null_thirdparty:130f1cd8` | `haematuria_null_thirdparty` | third_party | null | 20/26 | 76.9% | true 6, null 20 |
| `haematuria_true:fbab8b19` | `haematuria_true` | -- | true | 14/18 | 77.8% | true 14, null 4 |
| `haematuria_false:66629fb1` | `haematuria_false` | -- | false | 43/55 | 78.2% | false 43, null 12 |
| `haematuria_true:ec01803e` | `haematuria_true` | -- | true | 18/23 | 78.3% | true 18, null 5 |
| `haematuria_null_historical:a1d21e95` | `haematuria_null_historical` | historical | null | 29/37 | 78.4% | true 8, null 29 |
| `haematuria_true:f9f24e70` | `haematuria_true` | -- | true | 28/35 | 80.0% | true 28, null 7 |
| `haematuria_null_hedged:aa0a900a` | `haematuria_null_hedged` | hedged | null | 18/21 | 85.7% | true 3, null 18 |
| `haematuria_true:150663fa` | `haematuria_true` | -- | true | 52/57 | 91.2% | true 52, null 5 |
| `haematuria_true:07a7c858` | `haematuria_true` | -- | true | 24/26 | 92.3% | true 24, null 2 |
| `haematuria_true:5cf89fbc` | `haematuria_true` | -- | true | 29/31 | 93.5% | true 29, null 2 |
| `haematuria_null_historical:8a3575e2` | `haematuria_null_historical` | historical | null | 15/16 | 93.8% | false 1, null 15 |
| `haematuria_null_hedged:34af6f69` | `haematuria_null_hedged` | hedged | null | 18/19 | 94.7% | false 1, null 18 |
| `haematuria_true:a621d471` | `haematuria_true` | -- | true | 20/21 | 95.2% | true 20, null 1 |
| `haematuria_null_thirdparty:e1a16c31` | `haematuria_null_thirdparty` | third_party | null | 21/22 | 95.5% | true 1, null 21 |
| `haematuria_null_hedged:b46c1780` | `haematuria_null_hedged` | hedged | null | 22/23 | 95.7% | true 1, null 22 |
| `haematuria_null_historical:74713fa7` | `haematuria_null_historical` | historical | null | 22/23 | 95.7% | false 1, null 22 |
| `haematuria_null_hedged:58ace8f5` | `haematuria_null_hedged` | hedged | null | 25/26 | 96.2% | true 1, null 25 |
| `haematuria_null_historical:5896ca98` | `haematuria_null_historical` | historical | null | 26/27 | 96.3% | false 1, null 26 |

*8 further fragments with at least one error are in the JSON sidecar; every fragment is there regardless of score.*

## `arm_b_finetune@c0.5-d0.3`

`roberta-base` with **every layer unfrozen**, mean-pooled, with the same `Linear(768, 3)` head -- 110M trainable parameters against Arm A's 2,307. Three epochs at batch 32, learning rate 2e-5, 10% linear warmup, AdamW, fp32. No gradient checkpointing, no 8-bit optimiser, no LoRA, no gradient accumulation: the full model fits in 12GB with room to spare, so anything that reads like a compute compromise would be a mistake rather than a saving. This is the arm that separates "the fragment libraries are the bottleneck" from "the method is too weak": if a fully fine-tuned encoder still cannot read third-party attribution, tense or metaphor, the limit is in the ideas the libraries contain and the fix is library work, not model work.

Decision-rule margins selected per fold (on each fold's own validation split): 0.0, 0.35, 0.5, 0.9.

*Confusion matrix, raw argmax*

|  | pred false | pred true | pred null | total |
|---|---|---|---|---|
| **truth false** | 2252 | 42 | 185 | 2479 |
| **truth true** | 1 | 1373 | 107 | 1481 |
| **truth null** | 29 | 198 | 5813 | 6040 |
| **total** | 2282 | 1613 | 6105 | 10000 |

`null -> true`: 198 of 6040 truly-null examples (3.28%).

*Confusion matrix, after the decision rule*

|  | pred false | pred true | pred null | total |
|---|---|---|---|---|
| **truth false** | 2252 | 42 | 185 | 2479 |
| **truth true** | 1 | 1357 | 123 | 1481 |
| **truth null** | 32 | 172 | 5836 | 6040 |
| **total** | 2285 | 1571 | 6144 | 10000 |

`null -> true`: 172 of 6040 truly-null examples (2.85%).

### Per class, after the decision rule

| class | support | predicted | precision | recall | F1 |
|---|---|---|---|---|---|
| `false` | 2479 | 2285 | 98.6% | 90.8% | 94.5% |
| `true` | 1481 | 1571 | 86.4% | 91.6% | 88.9% |
| `null` | 6040 | 6144 | 95.0% | 96.6% | 95.8% |

### By label mode

| label mode | n | eff n | accuracy [95% CI] |
|---|---|---|---|
| false | 2479 | **128** | 90.8% [84.0%, 96.9%] |
| null_ambiguous | 3062 | **135** | 93.7% [90.0%, 97.1%] |
| null_structural | 2978 | **1** | 99.7% [99.7%, 99.7%] |
| true | 1481 | **124** | 91.6% [84.4%, 97.5%] |

### By null sub-class

| sub-class | n | eff n | null recall [95% CI] |
|---|---|---|---|
| hedged | 1079 | **45** | 85.0% [75.0%, 93.5%] |
| historical | 1017 | **45** | 98.0% [95.6%, 99.8%] |
| third_party | 966 | **45** | 98.8% [96.4%, 100.0%] |

### By fragment library

| library | n | eff n | accuracy [95% CI] |
|---|---|---|---|
| declarative_v1 | 1214 | **162** | 100.0% [100.0%, 100.0%] |
| haematuria_false | 1722 | **45** | 86.8% [77.2%, 95.1%] |
| haematuria_null_hedged | 1079 | **45** | 85.0% [75.0%, 93.5%] |
| haematuria_null_historical | 1017 | **45** | 98.0% [95.6%, 99.8%] |
| haematuria_null_thirdparty | 966 | **45** | 98.8% [96.4%, 100.0%] |
| haematuria_true | 1024 | **45** | 87.9% [77.2%, 96.0%] |
| (none) | 2978 | **1** | 99.7% [99.7%, 99.7%] |

### Per-fragment errors (worst first)

Whether errors are spread thinly across many fragments or piled onto a few is the difference
between "the method is too weak" (model work) and "these specific ideas are not learnable from
the data we have" (library work, and these are the fragments to write more of). No intervals:
a fragment is one cluster, so an interval over its own examples measures nothing.

40 of 642 decisive fragments were got wrong at least once.

`arm_b_finetune@c0.5-d0.3`: 545 errors across 40 of 642 decisive fragments. Half of them fall on **8** fragments (an even spread would be 20.0); the worst ten carry 60.0% of all errors.

| fragment | library | sub-class | truth | correct | accuracy | predicted as |
|---|---|---|---|---|---|---|
| `haematuria_false:eaac464c` | `haematuria_false` | -- | false | 0/44 | 0.0% | null 44 |
| `haematuria_false:d163df19` | `haematuria_false` | -- | false | 0/39 | 0.0% | null 39 |
| `haematuria_false:b471d351` | `haematuria_false` | -- | false | 0/35 | 0.0% | true 34, null 1 |
| `haematuria_null_hedged:0a1e23ec` | `haematuria_null_hedged` | hedged | null | 0/24 | 0.0% | true 24 |
| `haematuria_null_hedged:d64cf17c` | `haematuria_null_hedged` | hedged | null | 0/24 | 0.0% | true 24 |
| `haematuria_true:a87130d9` | `haematuria_true` | -- | true | 0/20 | 0.0% | false 1, null 19 |
| `haematuria_null_hedged:211cfe81` | `haematuria_null_hedged` | hedged | null | 0/16 | 0.0% | true 16 |
| `haematuria_true:9207612b` | `haematuria_true` | -- | true | 0/12 | 0.0% | null 12 |
| `haematuria_true:6fadb8bc` | `haematuria_true` | -- | true | 1/41 | 2.4% | true 1, null 40 |
| `haematuria_null_hedged:e2b503fc` | `haematuria_null_hedged` | hedged | null | 1/29 | 3.4% | true 28, null 1 |
| `haematuria_true:16614edd` | `haematuria_true` | -- | true | 1/22 | 4.5% | true 1, null 21 |
| `haematuria_null_hedged:740e7688` | `haematuria_null_hedged` | hedged | null | 1/21 | 4.8% | false 3, true 17, null 1 |
| `haematuria_null_hedged:dc7c4c42` | `haematuria_null_hedged` | hedged | null | 1/21 | 4.8% | false 20, null 1 |
| `haematuria_true:fbab8b19` | `haematuria_true` | -- | true | 1/12 | 8.3% | true 1, null 11 |
| `haematuria_null_thirdparty:610eccad` | `haematuria_null_thirdparty` | third_party | null | 1/11 | 9.1% | true 10, null 1 |
| `haematuria_false:0e98be72` | `haematuria_false` | -- | false | 4/42 | 9.5% | false 4, null 38 |
| `haematuria_false:66629fb1` | `haematuria_false` | -- | false | 5/38 | 13.2% | false 5, null 33 |
| `haematuria_true:ec01803e` | `haematuria_true` | -- | true | 3/15 | 20.0% | true 3, null 12 |
| `haematuria_false:0a0b1113` | `haematuria_false` | -- | false | 16/38 | 42.1% | false 16, null 22 |
| `haematuria_null_hedged:aa0a900a` | `haematuria_null_hedged` | hedged | null | 11/21 | 52.4% | true 10, null 11 |
| `haematuria_null_hedged:ad81f888` | `haematuria_null_hedged` | hedged | null | 15/26 | 57.7% | true 11, null 15 |
| `haematuria_true:07a7c858` | `haematuria_true` | -- | true | 8/12 | 66.7% | true 8, null 4 |
| `haematuria_null_historical:7ddf228a` | `haematuria_null_historical` | historical | null | 27/38 | 71.1% | true 11, null 27 |
| `haematuria_null_historical:559cea21` | `haematuria_null_historical` | historical | null | 20/26 | 76.9% | true 6, null 20 |
| `haematuria_true:e34024ba` | `haematuria_true` | -- | true | 10/13 | 76.9% | true 10, null 3 |
| `haematuria_false:cb3cb6e6` | `haematuria_false` | -- | false | 24/31 | 77.4% | false 24, true 7 |
| `haematuria_null_hedged:41281458` | `haematuria_null_hedged` | hedged | null | 25/29 | 86.2% | false 4, null 25 |
| `haematuria_false:a3acb31d` | `haematuria_false` | -- | false | 28/32 | 87.5% | false 28, null 4 |
| `haematuria_null_hedged:d9bf40cb` | `haematuria_null_hedged` | hedged | null | 17/19 | 89.5% | true 2, null 17 |
| `haematuria_false:64933508` | `haematuria_false` | -- | false | 42/46 | 91.3% | false 42, null 4 |
| `haematuria_null_hedged:f5ac0bee` | `haematuria_null_hedged` | hedged | null | 12/13 | 92.3% | true 1, null 12 |
| `haematuria_true:b8b1c720` | `haematuria_true` | -- | true | 12/13 | 92.3% | true 12, null 1 |
| `haematuria_null_thirdparty:161d26ba` | `haematuria_null_thirdparty` | third_party | null | 18/19 | 94.7% | true 1, null 18 |
| `haematuria_null_historical:6fd69041` | `haematuria_null_historical` | historical | null | 25/26 | 96.2% | true 1, null 25 |
| `haematuria_null_historical:ae265e50` | `haematuria_null_historical` | historical | null | 25/26 | 96.2% | false 1, null 25 |
| `haematuria_null_hedged:776ef5ce` | `haematuria_null_hedged` | hedged | null | 30/31 | 96.8% | true 1, null 30 |
| `haematuria_null_thirdparty:7e497073` | `haematuria_null_thirdparty` | third_party | null | 33/34 | 97.1% | true 1, null 33 |
| `haematuria_null_hedged:086f7067` | `haematuria_null_hedged` | hedged | null | 34/35 | 97.1% | true 1, null 34 |
| `haematuria_null_historical:fa6984ec` | `haematuria_null_historical` | historical | null | 34/35 | 97.1% | true 1, null 34 |
| `haematuria_false:94f9de34` | `haematuria_false` | -- | false | 61/62 | 98.4% | false 61, true 1 |

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
| 0 | 10000 | 2000 | 2000 | 0.0 | 60.8% | 60.8% | 26.1% | 0.00% |
| 1 | 10000 | 2000 | 2000 | 0.0 | 60.1% | 60.1% | 25.0% | 0.00% |
| 2 | 10000 | 2000 | 2000 | 0.0 | 60.4% | 60.4% | 25.1% | 0.00% |
| 3 | 10000 | 2000 | 2000 | 0.0 | 60.9% | 60.9% | 25.6% | 0.00% |
| 4 | 10000 | 2000 | 2000 | 0.0 | 60.9% | 60.9% | 27.4% | 0.00% |

### `tfidf_logreg`

| fold | train n | val n | test n | margin | acc (raw) | acc (ruled) | macro-F1 | null->true |
|---|---|---|---|---|---|---|---|---|
| 0 | 10000 | 2000 | 2000 | 0.0 | 81.3% | 81.3% | 71.5% | 5.13% |
| 1 | 10000 | 2000 | 2000 | 0.0 | 79.8% | 79.8% | 70.7% | 1.83% |
| 2 | 10000 | 2000 | 2000 | 0.0 | 81.8% | 81.8% | 73.3% | 0.17% |
| 3 | 10000 | 2000 | 2000 | 0.05 | 79.8% | 79.5% | 69.6% | 1.48% |
| 4 | 10000 | 2000 | 2000 | 0.0 | 87.0% | 87.0% | 81.8% | 2.16% |

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
| 0 | 10000 | 2000 | 2000 | 0.0 | 60.5% | 60.5% | 25.1% | 0.00% |
| 1 | 10000 | 2000 | 2000 | 0.0 | 60.1% | 60.1% | 25.0% | 0.00% |
| 2 | 10000 | 2000 | 2000 | 0.0 | 60.4% | 60.4% | 25.1% | 0.00% |
| 3 | 10000 | 2000 | 2000 | 0.0 | 60.8% | 60.8% | 25.2% | 0.00% |
| 4 | 10000 | 2000 | 2000 | 0.0 | 60.3% | 60.3% | 25.2% | 0.00% |

### `arm_b_finetune@c0.0-d0.0`

| fold | train n | val n | test n | margin | acc (raw) | acc (ruled) | macro-F1 | null->true |
|---|---|---|---|---|---|---|---|---|
| 0 | 10000 | 2000 | 2000 | 0.9 | 94.2% | 93.9% | 92.6% | 2.65% |
| 1 | 10000 | 2000 | 2000 | 0.9 | 91.4% | 91.8% | 91.5% | 3.99% |
| 2 | 10000 | 2000 | 2000 | 0.4 | 92.8% | 92.7% | 89.0% | 2.57% |
| 3 | 10000 | 2000 | 2000 | 0.8 | 94.8% | 94.5% | 92.4% | 1.89% |
| 4 | 10000 | 2000 | 2000 | 0.0 | 96.8% | 96.8% | 95.2% | 0.00% |

### `arm_b_finetune@c0.0-d0.3`

| fold | train n | val n | test n | margin | acc (raw) | acc (ruled) | macro-F1 | null->true |
|---|---|---|---|---|---|---|---|---|
| 0 | 10000 | 2000 | 2000 | 0.9 | 95.6% | 95.6% | 94.7% | 2.89% |
| 1 | 10000 | 2000 | 2000 | 0.8 | 96.6% | 96.7% | 96.3% | 2.41% |
| 2 | 10000 | 2000 | 2000 | 0.6 | 93.2% | 93.2% | 90.6% | 2.57% |
| 3 | 10000 | 2000 | 2000 | 0.65 | 96.4% | 96.3% | 94.1% | 1.56% |
| 4 | 10000 | 2000 | 2000 | 0.15 | 97.0% | 97.0% | 95.6% | 1.49% |

### `arm_b_finetune@c0.5-d0.0`

| fold | train n | val n | test n | margin | acc (raw) | acc (ruled) | macro-F1 | null->true |
|---|---|---|---|---|---|---|---|---|
| 0 | 10000 | 2000 | 2000 | 0.9 | 92.7% | 92.7% | 91.2% | 4.47% |
| 1 | 10000 | 2000 | 2000 | 0.9 | 89.9% | 89.2% | 87.4% | 4.24% |
| 2 | 10000 | 2000 | 2000 | 0.0 | 90.6% | 90.6% | 87.9% | 5.55% |
| 3 | 10000 | 2000 | 2000 | 0.9 | 96.7% | 96.3% | 95.2% | 0.08% |
| 4 | 10000 | 2000 | 2000 | 0.55 | 93.2% | 93.5% | 91.6% | 1.24% |

### `arm_b_finetune@c0.5-d0.3`

| fold | train n | val n | test n | margin | acc (raw) | acc (ruled) | macro-F1 | null->true |
|---|---|---|---|---|---|---|---|---|
| 0 | 10000 | 2000 | 2000 | 0.9 | 95.0% | 95.3% | 94.4% | 2.48% |
| 1 | 10000 | 2000 | 2000 | 0.9 | 90.8% | 90.3% | 88.7% | 7.99% |
| 2 | 10000 | 2000 | 2000 | 0.5 | 94.5% | 94.8% | 93.1% | 1.82% |
| 3 | 10000 | 2000 | 2000 | 0.0 | 94.5% | 94.5% | 93.2% | 1.15% |
| 4 | 10000 | 2000 | 2000 | 0.35 | 97.2% | 97.4% | 96.1% | 0.83% |

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

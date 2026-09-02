# Encoder training: evaluation report

*Generated 2026-09-02T15:59:59+00:00.*

|  |  |
|---|---|
| signal | `urinary_frequency_present` |
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
| selected epochs | `c0.0-d0.0 1, 3, 1, 2, 1, c0.0-d0.3 3, 3, 1, 1, 2, c0.5-d0.0 2, 3, 1, 3, 1, c0.5-d0.3 1, 3, 1, 1, 3` |
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
| cluster tag coverage | `1 of 8 libraries carry cluster markers; 302 of 739 fragments are in libraries with none` |
| bootstrap | `2000 resamples over clusters, alpha=0.05, seed=0` |

**arms**

* **c0.0-d0.0** (`data/synthetic/generated/decl/c0.0-d0.0`): 10000 examples per epoch, **10000** labelled positions for `urinary_frequency_present`
* **c0.0-d0.3** (`data/synthetic/generated/decl/c0.0-d0.3`): 10000 examples per epoch, **10000** labelled positions for `urinary_frequency_present`
* **c0.5-d0.0** (`data/synthetic/generated/decl/c0.5-d0.0`): 10000 examples per epoch, **10000** labelled positions for `urinary_frequency_present`
* **c0.5-d0.3** (`data/synthetic/generated/decl/c0.5-d0.3`): 10000 examples per epoch, **10000** labelled positions for `urinary_frequency_present`

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

> **Warning: 7 of the 8 libraries behind this run carry no cluster markers at all, so every line in them counts as an independent idea.** Where that is not true -- where several lines are one idea written several ways -- the `eff n` of every slice drawn from those libraries is an **upper bound**, and the confidence intervals below are correspondingly **narrower than the truth**.
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
| `declarative_v1` | 437 | 437 | 100.0% |

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
| `majority_class` | baseline | 7022 | **302** | 43.6% [37.6%, 50.8%] | 20.2% [18.2%, 22.5%] | 60.4% | 60.4% +/- 0.2% |
| `length_only` | baseline | 7022 | **302** | 43.6% [37.6%, 50.8%] | 20.2% [18.2%, 22.5%] | 60.4% | 60.4% +/- 0.2% |
| `tfidf_logreg` | baseline | 7022 | **302** | 59.8% [54.1%, 65.9%] | 48.4% [42.7%, 53.8%] | 71.6% | 71.6% +/- 3.1% |
| `length_only__shuffled` | negative control | 7022 | **302** | 43.6% [37.6%, 50.8%] | 20.2% [18.2%, 22.5%] | 60.4% | 60.4% +/- 0.2% |
| `tfidf_logreg__shuffled` | negative control | 7022 | **302** | 43.6% [37.5%, 50.8%] | 20.2% [18.2%, 22.5%] | 60.4% | 60.4% +/- 0.2% |
| `arm_b_finetune@c0.0-d0.0` | finetune | 7022 | **302** | 83.5% [77.8%, 88.8%] | 81.0% [74.4%, 87.0%] | 88.4% | 88.4% +/- 6.2% |
| `arm_b_finetune@c0.0-d0.3` | finetune | 7022 | **465** | 89.6% [85.9%, 93.0%] | 88.1% [84.0%, 91.9%] | 92.5% | 92.5% +/- 4.7% |
| `arm_b_finetune@c0.5-d0.0` | finetune | 7022 | **302** | 83.7% [78.8%, 88.3%] | 81.2% [75.3%, 86.1%] | 88.4% | 88.4% +/- 6.2% |
| `arm_b_finetune@c0.5-d0.3` | finetune | 7022 | **465** | 87.2% [83.1%, 90.9%] | 85.3% [80.7%, 89.4%] | 90.9% | 90.9% +/- 5.4% |

### Null sub-class recall, pooled

The table the whole exercise exists for: how often each hard `null` sub-class is correctly
left as `null`. `eff n` here is the sub-class's entire library, which a single split cannot reach.

**Never read this table on its own.** Every example in these slices is truly `null`, so a model
that always answers `null` scores 100% across the row -- as `majority_class` below does. High
null recall is only a finding when the `true` and `false` recalls in the per-class tables are
high too.

| model | adjacent | attribution | hedged | historical | metaphor | third_party |
|---|---|---|---|---|---|---|
| `majority_class` | 100.0% [100.0%, 100.0%] (eff n 40) | -- | 100.0% [100.0%, 100.0%] (eff n 42) | 100.0% [100.0%, 100.0%] (eff n 40) | 100.0% [100.0%, 100.0%] (eff n 44) | 100.0% [100.0%, 100.0%] (eff n 44) |
| `length_only` | 100.0% [100.0%, 100.0%] (eff n 40) | -- | 100.0% [100.0%, 100.0%] (eff n 42) | 100.0% [100.0%, 100.0%] (eff n 40) | 100.0% [100.0%, 100.0%] (eff n 44) | 100.0% [100.0%, 100.0%] (eff n 44) |
| `tfidf_logreg` | 95.8% [90.0%, 99.7%] (eff n 40) | -- | 92.1% [84.5%, 97.5%] (eff n 42) | 98.0% [94.9%, 99.8%] (eff n 40) | 95.7% [91.8%, 98.7%] (eff n 44) | 83.5% [75.2%, 90.7%] (eff n 44) |
| `length_only__shuffled` | 100.0% [100.0%, 100.0%] (eff n 40) | -- | 100.0% [100.0%, 100.0%] (eff n 42) | 100.0% [100.0%, 100.0%] (eff n 40) | 100.0% [100.0%, 100.0%] (eff n 44) | 100.0% [100.0%, 100.0%] (eff n 44) |
| `tfidf_logreg__shuffled` | 100.0% [100.0%, 100.0%] (eff n 40) | -- | 100.0% [100.0%, 100.0%] (eff n 42) | 99.8% [99.4%, 100.0%] (eff n 40) | 100.0% [100.0%, 100.0%] (eff n 44) | 100.0% [100.0%, 100.0%] (eff n 44) |
| `arm_b_finetune@c0.0-d0.0` | 91.4% [82.3%, 98.3%] (eff n 40) | -- | 92.9% [86.1%, 98.0%] (eff n 42) | 98.7% [96.7%, 100.0%] (eff n 40) | 94.1% [87.2%, 99.4%] (eff n 44) | 98.3% [96.7%, 99.7%] (eff n 44) |
| `arm_b_finetune@c0.0-d0.3` | 93.4% [85.3%, 99.5%] (eff n 40) | -- | 92.7% [86.1%, 97.7%] (eff n 42) | 99.6% [99.1%, 100.0%] (eff n 40) | 93.9% [86.9%, 99.1%] (eff n 44) | 99.2% [98.6%, 99.8%] (eff n 44) |
| `arm_b_finetune@c0.5-d0.0` | 96.9% [91.3%, 100.0%] (eff n 40) | -- | 87.6% [78.4%, 95.1%] (eff n 42) | 98.0% [93.7%, 100.0%] (eff n 40) | 96.4% [90.0%, 100.0%] (eff n 44) | 98.1% [95.8%, 100.0%] (eff n 44) |
| `arm_b_finetune@c0.5-d0.3` | 97.3% [92.5%, 100.0%] (eff n 40) | -- | 90.9% [83.2%, 97.1%] (eff n 42) | 98.5% [95.7%, 100.0%] (eff n 40) | 93.3% [85.1%, 100.0%] (eff n 44) | 99.5% [98.8%, 100.0%] (eff n 44) |

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

Not scored, because no head exists for them: `dysuria_present`, `nocturia_present`, `fever_present`, `flank_pain_present`, `haematuria_present`, `recent_uti_present`.

### `null -> true` on real text -- the headline

How often each model answers `true` about a signal the submission never mentioned, as
the mean across folds of that fold's own rate. Every other number in this section is
read against this one: a model can post a respectable overall figure here purely by
answering `null` everywhere, and it can post a respectable *decisive* figure while still
inventing symptoms into most of the submissions that never raised them.

| signal | null support | `arm_b_finetune@c0.0-d0.0` | `arm_b_finetune@c0.0-d0.3` | `arm_b_finetune@c0.5-d0.0` | `arm_b_finetune@c0.5-d0.3` |
|---|---|---|---|---|---|
| `urinary_frequency_present` | 41 | 5.9% | 23.4% | 4.4% | 5.9% |

### `arm_b_finetune@c0.0-d0.0`

Recombination test slice: **n 7022**, **eff n 302** clusters, accuracy 83.5% [77.8%, 88.8%]. Holdout: **n 67** submissions, one observation each, scored by 5 fold models at margins 0.15, 0.05, 0.0, 0.9, 0.7. The two `n`s are printed together because they are not the same kind of number and the second is far the smaller.

| signal | true/false/null | omitted | decisive n | decisive acc (mean +/- sd) | worst-case half-width | all n | all acc (mean +/- sd) | null recall |
|---|---|---|---|---|---|---|---|---|
| `urinary_frequency_present` | 26/0/41 | 0 | 26 | 52.3% +/- 13.8% | +/-19.2% | 67 | 76.7% +/- 4.8% | 92.2% +/- 2.0% |

* `urinary_frequency_present`: no `false` examples in this set, so its number is very nearly a recall-only measurement: nothing here tests whether an explicit denial is read correctly, which was the largest error family in the synthetic evaluation.

`null -> true` on real text, per fold: `urinary_frequency_present` 3, 2, 3, 1, 3 of 41. This is the cell that invents a symptom into a patient's pre-filled form, counted here on submissions rather than on recombinations.

### `arm_b_finetune@c0.0-d0.3`

Recombination test slice: **n 7022**, **eff n 465** clusters, accuracy 89.6% [85.9%, 93.0%]. Holdout: **n 67** submissions, one observation each, scored by 5 fold models at margins 0.8, 0.9, 0.0, 0.9, 0.75. The two `n`s are printed together because they are not the same kind of number and the second is far the smaller.

| signal | true/false/null | omitted | decisive n | decisive acc (mean +/- sd) | worst-case half-width | all n | all acc (mean +/- sd) | null recall |
|---|---|---|---|---|---|---|---|---|
| `urinary_frequency_present` | 26/0/41 | 0 | 26 | 86.9% +/- 18.8% | +/-19.2% | 67 | 79.7% +/- 4.8% | 75.1% +/- 13.5% |

* `urinary_frequency_present`: no `false` examples in this set, so its number is very nearly a recall-only measurement: nothing here tests whether an explicit denial is read correctly, which was the largest error family in the synthetic evaluation.

`null -> true` on real text, per fold: `urinary_frequency_present` 13, 16, 2, 9, 8 of 41. This is the cell that invents a symptom into a patient's pre-filled form, counted here on submissions rather than on recombinations.

### `arm_b_finetune@c0.5-d0.0`

Recombination test slice: **n 7022**, **eff n 302** clusters, accuracy 83.7% [78.8%, 88.3%]. Holdout: **n 67** submissions, one observation each, scored by 5 fold models at margins 0.9, 0.9, 0.0, 0.9, 0.7. The two `n`s are printed together because they are not the same kind of number and the second is far the smaller.

| signal | true/false/null | omitted | decisive n | decisive acc (mean +/- sd) | worst-case half-width | all n | all acc (mean +/- sd) | null recall |
|---|---|---|---|---|---|---|---|---|
| `urinary_frequency_present` | 26/0/41 | 0 | 26 | 45.4% +/- 18.9% | +/-19.2% | 67 | 76.1% +/- 5.8% | 95.6% +/- 3.2% |

* `urinary_frequency_present`: no `false` examples in this set, so its number is very nearly a recall-only measurement: nothing here tests whether an explicit denial is read correctly, which was the largest error family in the synthetic evaluation.

`null -> true` on real text, per fold: `urinary_frequency_present` 3, 3, 1, 0, 2 of 41. This is the cell that invents a symptom into a patient's pre-filled form, counted here on submissions rather than on recombinations.

### `arm_b_finetune@c0.5-d0.3`

Recombination test slice: **n 7022**, **eff n 465** clusters, accuracy 87.2% [83.1%, 90.9%]. Holdout: **n 67** submissions, one observation each, scored by 5 fold models at margins 0.85, 0.2, 0.0, 0.9, 0.5. The two `n`s are printed together because they are not the same kind of number and the second is far the smaller.

| signal | true/false/null | omitted | decisive n | decisive acc (mean +/- sd) | worst-case half-width | all n | all acc (mean +/- sd) | null recall |
|---|---|---|---|---|---|---|---|---|
| `urinary_frequency_present` | 26/0/41 | 0 | 26 | 56.9% +/- 10.3% | +/-19.2% | 67 | 79.7% +/- 4.4% | 94.1% +/- 1.3% |

* `urinary_frequency_present`: no `false` examples in this set, so its number is very nearly a recall-only measurement: nothing here tests whether an explicit denial is read correctly, which was the largest error family in the synthetic evaluation.

`null -> true` on real text, per fold: `urinary_frequency_present` 2, 2, 3, 2, 3 of 41. This is the cell that invents a symptom into a patient's pre-filled form, counted here on submissions rather than on recombinations.

## Paired on real text

The 67 submissions are the same 67 for every model here, so unlike the recombination
test slice they can be paired: the informative quantity is the submissions two models
disagree about, not the gap between two means. One test per fold, never pooled.

### `arm_b_finetune@c0.0-d0.0` against `arm_b_finetune@c0.0-d0.3`

| fold | pairs | only `arm_b_finetune@c0.0-d0.0` | only `arm_b_finetune@c0.0-d0.3` | p |
|---|---|---|---|---|
| 0 | 67 | 9 | 5 | 0.424 |
| 1 | 67 | 14 | 12 | 0.845 |
| 2 | 67 | 0 | 6 | 0.0312 |
| 3 | 67 | 8 | 13 | 0.383 |
| 4 | 67 | 6 | 11 | 0.332 |

`arm_b_finetune@c0.0-d0.0` ahead on 2 folds, `arm_b_finetune@c0.0-d0.3` on 3. `null -> true` mean: 5.9% against 23.4% -- **-17.6 points** in favour of `arm_b_finetune@c0.0-d0.3`.

*One test per fold over the same 67 submissions, never concatenated: five folds are five models scored on one sample, and pooling would report a p-value for 335 observations that do not exist.*

### `arm_b_finetune@c0.0-d0.0` against `arm_b_finetune@c0.5-d0.0`

| fold | pairs | only `arm_b_finetune@c0.0-d0.0` | only `arm_b_finetune@c0.5-d0.0` | p |
|---|---|---|---|---|
| 0 | 67 | 4 | 2 | 0.688 |
| 1 | 67 | 4 | 5 | 1 |
| 2 | 67 | 3 | 2 | 1 |
| 3 | 67 | 6 | 2 | 0.289 |
| 4 | 67 | 2 | 6 | 0.289 |

`arm_b_finetune@c0.0-d0.0` ahead on 3 folds, `arm_b_finetune@c0.5-d0.0` on 2. `null -> true` mean: 5.9% against 4.4% -- **+1.5 points** in favour of `arm_b_finetune@c0.5-d0.0`.

*One test per fold over the same 67 submissions, never concatenated: five folds are five models scored on one sample, and pooling would report a p-value for 335 observations that do not exist.*

### `arm_b_finetune@c0.0-d0.0` against `arm_b_finetune@c0.5-d0.3`

| fold | pairs | only `arm_b_finetune@c0.0-d0.0` | only `arm_b_finetune@c0.5-d0.3` | p |
|---|---|---|---|---|
| 0 | 67 | 5 | 5 | 1 |
| 1 | 67 | 2 | 7 | 0.18 |
| 2 | 67 | 0 | 2 | 0.5 |
| 3 | 67 | 4 | 4 | 1 |
| 4 | 67 | 5 | 8 | 0.581 |

`arm_b_finetune@c0.0-d0.0` ahead on 0 folds, `arm_b_finetune@c0.5-d0.3` on 3. `null -> true` mean: 5.9% against 5.9% -- **+0.0 points** in favour of `arm_b_finetune@c0.5-d0.3`.

*One test per fold over the same 67 submissions, never concatenated: five folds are five models scored on one sample, and pooling would report a p-value for 335 observations that do not exist.*

### `arm_b_finetune@c0.0-d0.3` against `arm_b_finetune@c0.5-d0.0`

| fold | pairs | only `arm_b_finetune@c0.0-d0.3` | only `arm_b_finetune@c0.5-d0.0` | p |
|---|---|---|---|---|
| 0 | 67 | 9 | 11 | 0.824 |
| 1 | 67 | 11 | 14 | 0.69 |
| 2 | 67 | 8 | 1 | 0.0391 |
| 3 | 67 | 19 | 10 | 0.136 |
| 4 | 67 | 8 | 7 | 1 |

`arm_b_finetune@c0.0-d0.3` ahead on 3 folds, `arm_b_finetune@c0.5-d0.0` on 2. `null -> true` mean: 23.4% against 4.4% -- **+19.0 points** in favour of `arm_b_finetune@c0.5-d0.0`.

*One test per fold over the same 67 submissions, never concatenated: five folds are five models scored on one sample, and pooling would report a p-value for 335 observations that do not exist.*

### `arm_b_finetune@c0.0-d0.3` against `arm_b_finetune@c0.5-d0.3`

| fold | pairs | only `arm_b_finetune@c0.0-d0.3` | only `arm_b_finetune@c0.5-d0.3` | p |
|---|---|---|---|---|
| 0 | 67 | 8 | 12 | 0.503 |
| 1 | 67 | 8 | 15 | 0.21 |
| 2 | 67 | 4 | 0 | 0.125 |
| 3 | 67 | 13 | 8 | 0.383 |
| 4 | 67 | 8 | 6 | 0.791 |

`arm_b_finetune@c0.0-d0.3` ahead on 3 folds, `arm_b_finetune@c0.5-d0.3` on 2. `null -> true` mean: 23.4% against 5.9% -- **+17.6 points** in favour of `arm_b_finetune@c0.5-d0.3`.

*One test per fold over the same 67 submissions, never concatenated: five folds are five models scored on one sample, and pooling would report a p-value for 335 observations that do not exist.*

### `arm_b_finetune@c0.5-d0.0` against `arm_b_finetune@c0.5-d0.3`

| fold | pairs | only `arm_b_finetune@c0.5-d0.0` | only `arm_b_finetune@c0.5-d0.3` | p |
|---|---|---|---|---|
| 0 | 67 | 1 | 3 | 0.625 |
| 1 | 67 | 0 | 4 | 0.125 |
| 2 | 67 | 2 | 5 | 0.453 |
| 3 | 67 | 2 | 6 | 0.289 |
| 4 | 67 | 4 | 3 | 1 |

`arm_b_finetune@c0.5-d0.0` ahead on 1 folds, `arm_b_finetune@c0.5-d0.3` on 4. `null -> true` mean: 4.4% against 5.9% -- **-1.5 points** in favour of `arm_b_finetune@c0.5-d0.3`.

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
| `majority_class` | baseline | 3062 | **210** | 100.0% [100.0%, 100.0%] |
| `length_only` | baseline | 3062 | **210** | 100.0% [100.0%, 100.0%] |
| `tfidf_logreg` | baseline | 3062 | **210** | 92.8% [90.0%, 95.2%] |
| `arm_b_finetune@c0.0-d0.0` | finetune | 3062 | **210** | 95.0% [92.2%, 97.2%] |
| `arm_b_finetune@c0.0-d0.3` | finetune | 3062 | **210** | 95.7% [93.1%, 97.9%] |
| `arm_b_finetune@c0.5-d0.0` | finetune | 3062 | **210** | 95.4% [92.6%, 97.6%] |
| `arm_b_finetune@c0.5-d0.3` | finetune | 3062 | **210** | 95.8% [93.1%, 98.0%] |

### 2. The same comparison, paired

Two overlapping intervals do not settle whether one model beats another on the same
examples. McNemar does, over the examples the two disagree about -- read it alongside the
intervals above, never instead of them.

| pair | n | a only | b only | p |
|---|---|---|---|---|
| `majority_class` vs `length_only` | 3062 | 0 | 0 | 1 |
| `majority_class` vs `tfidf_logreg` | 3062 | 230 | 0 | 1.16e-69 |
| `majority_class` vs `arm_b_finetune@c0.0-d0.0` | 3062 | 169 | 0 | 2.67e-51 |
| `length_only` vs `tfidf_logreg` | 3062 | 230 | 0 | 1.16e-69 |
| `length_only` vs `arm_b_finetune@c0.0-d0.0` | 3062 | 169 | 0 | 2.67e-51 |
| `tfidf_logreg` vs `arm_b_finetune@c0.0-d0.0` | 3062 | 135 | 196 | 0.000946 |

Not on this table, because they cannot be paired at all -- different examples on the two sides, so there is nothing for McNemar to pair: `majority_class` vs `arm_b_finetune@c0.0-d0.3`; `majority_class` vs `arm_b_finetune@c0.5-d0.0`; `majority_class` vs `arm_b_finetune@c0.5-d0.3`; `length_only` vs `arm_b_finetune@c0.0-d0.3`; `length_only` vs `arm_b_finetune@c0.5-d0.0`; `length_only` vs `arm_b_finetune@c0.5-d0.3`; `tfidf_logreg` vs `arm_b_finetune@c0.0-d0.3`; `tfidf_logreg` vs `arm_b_finetune@c0.5-d0.0`; `tfidf_logreg` vs `arm_b_finetune@c0.5-d0.3`; `arm_b_finetune@c0.0-d0.0` vs `arm_b_finetune@c0.0-d0.3`; `arm_b_finetune@c0.0-d0.0` vs `arm_b_finetune@c0.5-d0.0`; `arm_b_finetune@c0.0-d0.0` vs `arm_b_finetune@c0.5-d0.3`; `arm_b_finetune@c0.0-d0.3` vs `arm_b_finetune@c0.5-d0.0`; `arm_b_finetune@c0.0-d0.3` vs `arm_b_finetune@c0.5-d0.3`; `arm_b_finetune@c0.5-d0.0` vs `arm_b_finetune@c0.5-d0.3`. Read those through the intervals above and the per-fold spread, and see "Pairs that could not be tested" below.

### 3. Where the errors fall

The per-fragment table below, as one number per model. Errors spread thinly across many
fragments say the method is too weak. Errors piled onto a handful say those specific ideas
are not learnable from the data we have -- and the table names them, which is what makes
this the most decision-useful thing in the report.

* `majority_class`: 3960 errors across 92 of 302 decisive fragments. Half of them fall on **30** fragments (an even spread would be 46.0); the worst ten carry 22.6% of all errors.
* `length_only`: 3960 errors across 92 of 302 decisive fragments. Half of them fall on **30** fragments (an even spread would be 46.0); the worst ten carry 22.6% of all errors.
* `tfidf_logreg`: 2825 errors across 141 of 302 decisive fragments. Half of them fall on **30** fragments (an even spread would be 70.5); the worst ten carry 22.3% of all errors.
* `arm_b_finetune@c0.0-d0.0`: 1160 errors across 65 of 302 decisive fragments. Half of them fall on **10** fragments (an even spread would be 32.5); the worst ten carry 52.7% of all errors.
* `arm_b_finetune@c0.0-d0.3`: 733 errors across 63 of 694 decisive fragments. Half of them fall on **10** fragments (an even spread would be 31.5); the worst ten carry 53.2% of all errors.
* `arm_b_finetune@c0.5-d0.0`: 1143 errors across 65 of 302 decisive fragments. Half of them fall on **13** fragments (an even spread would be 32.5); the worst ten carry 41.1% of all errors.
* `arm_b_finetune@c0.5-d0.3`: 902 errors across 56 of 694 decisive fragments. Half of them fall on **13** fragments (an even spread would be 28.0); the worst ten carry 42.4% of all errors.

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
| `length_only__shuffled` | 60.4% [38.8%, 77.8%] | 25.1% [18.6%, 29.2%] |
| `tfidf_logreg__shuffled` | 60.4% [38.8%, 77.8%] | 25.1% [18.6%, 29.2%] |

## Paired comparisons (McNemar, raw argmax)

Exact two-sided McNemar over the examples the two models disagree about. Pairing unit is the
example, not the cluster -- see the limitations.

| pair | slice | n | a only | b only | p |
|---|---|---|---|---|---|
| `majority_class` vs `length_only` | overall | 10000 | 0 | 0 | 1 |
| `majority_class` vs `length_only` | null_ambiguous | 3062 | 0 | 0 | 1 |
| `majority_class` vs `tfidf_logreg` | overall | 10000 | 245 | 1375 | 1.15e-190 |
| `majority_class` vs `tfidf_logreg` | null_ambiguous | 3062 | 230 | 0 | 1.16e-69 |
| `majority_class` vs `arm_b_finetune@c0.0-d0.0` | overall | 10000 | 169 | 2973 | 0 |
| `majority_class` vs `arm_b_finetune@c0.0-d0.0` | null_ambiguous | 3062 | 169 | 0 | 2.67e-51 |
| `length_only` vs `tfidf_logreg` | overall | 10000 | 245 | 1375 | 1.15e-190 |
| `length_only` vs `tfidf_logreg` | null_ambiguous | 3062 | 230 | 0 | 1.16e-69 |
| `length_only` vs `arm_b_finetune@c0.0-d0.0` | overall | 10000 | 169 | 2973 | 0 |
| `length_only` vs `arm_b_finetune@c0.0-d0.0` | null_ambiguous | 3062 | 169 | 0 | 2.67e-51 |
| `tfidf_logreg` vs `arm_b_finetune@c0.0-d0.0` | overall | 10000 | 388 | 2062 | 1.38e-274 |
| `tfidf_logreg` vs `arm_b_finetune@c0.0-d0.0` | null_ambiguous | 3062 | 135 | 196 | 0.000946 |

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
| `urinary_frequency_false` | 1719 | 0.0% | 0.0% | 48.9% | 77.0% | 78.0% | 80.4% | 74.9% | 80.4pp |
| `urinary_frequency_true` | 1024 | 0.0% | 0.0% | 9.6% | 70.6% | 77.7% | 65.2% | 66.7% | 77.7pp |
| `urinary_frequency_null_thirdparty` | 638 | 100.0% | 100.0% | 83.5% | 98.3% | 99.2% | 98.1% | 99.5% | 16.5pp |
| `urinary_frequency_null_hedged` | 623 | 100.0% | 100.0% | 92.1% | 92.9% | 92.7% | 87.6% | 90.9% | 12.4pp |
| `urinary_frequency_null_adjacent` | 587 | 100.0% | 100.0% | 95.8% | 91.4% | 93.4% | 96.9% | 97.3% | 8.6pp |
| `urinary_frequency_null_metaphor` | 670 | 100.0% | 100.0% | 95.7% | 94.1% | 93.9% | 96.4% | 93.3% | 6.7pp |
| `urinary_frequency_null_historical` | 544 | 100.0% | 100.0% | 98.0% | 98.7% | 99.6% | 98.0% | 98.5% | 2.0pp |
| `(none)` | 2978 | 100.0% | 100.0% | 99.5% | 100.0% | 99.3% | 99.3% | 99.6% | 0.7pp |

### By fragment, errors

Ordered by the worst model's error count, so the fragments the comparison is about sort
to the top whichever encoder wins. Counts, not rates: these are the sentences a month of
library work would be spent on. The JSON holds every fragment.

| fragment | library | truth | `majority_class` | `length_only` | `tfidf_logreg` | `arm_b_finetune@c0.0-d0.0` | `arm_b_finetune@c0.0-d0.3` | `arm_b_finetune@c0.5-d0.0` | `arm_b_finetune@c0.5-d0.3` | spread |
|---|---|---|---|---|---|---|---|---|---|---|
| `urinary_frequency_false:a15017c2` | `urinary_frequency_false` | false | 133 | 133 | 35 | 122 | 59 | 8 | 42 | 125 |
| `urinary_frequency_false:a7fe81d1` | `urinary_frequency_false` | false | 127 | 127 | 112 | 0 | 0 | 0 | 0 | 127 |
| `urinary_frequency_false:d293ee8c` | `urinary_frequency_false` | false | 125 | 125 | 30 | 115 | 40 | 38 | 16 | 109 |
| `urinary_frequency_false:22b965f9` | `urinary_frequency_false` | false | 119 | 119 | 21 | 0 | 0 | 0 | 0 | 119 |
| `urinary_frequency_true:11d16987` | `urinary_frequency_true` | true | 66 | 66 | 66 | 62 | 42 | 70 | 48 | 28 |
| `urinary_frequency_true:272d2041` | `urinary_frequency_true` | true | 67 | 67 | 38 | 0 | 0 | 0 | 0 | 67 |
| `urinary_frequency_false:6c16f65e` | `urinary_frequency_false` | false | 66 | 66 | 0 | 0 | 0 | 0 | 0 | 66 |
| `urinary_frequency_false:1d7759da` | `urinary_frequency_false` | false | 65 | 65 | 62 | 0 | 0 | 0 | 0 | 65 |
| `urinary_frequency_false:7fc83941` | `urinary_frequency_false` | false | 65 | 65 | 7 | 0 | 0 | 0 | 0 | 65 |
| `urinary_frequency_false:f3e3b17c` | `urinary_frequency_false` | false | 63 | 63 | 41 | 0 | 0 | 0 | 0 | 63 |
| `urinary_frequency_false:a5342750` | `urinary_frequency_false` | false | 62 | 62 | 11 | 0 | 0 | 0 | 0 | 62 |
| `urinary_frequency_true:764389c0` | `urinary_frequency_true` | true | 62 | 62 | 62 | 46 | 37 | 37 | 31 | 31 |
| `urinary_frequency_false:c7b96e67` | `urinary_frequency_false` | false | 61 | 61 | 8 | 0 | 0 | 0 | 0 | 61 |
| `urinary_frequency_false:44543d5e` | `urinary_frequency_false` | false | 60 | 60 | 56 | 19 | 32 | 8 | 36 | 52 |
| `urinary_frequency_false:a9a59952` | `urinary_frequency_false` | false | 60 | 60 | 47 | 0 | 35 | 25 | 37 | 60 |
| `urinary_frequency_false:1a4ef542` | `urinary_frequency_false` | false | 57 | 57 | 7 | 0 | 0 | 6 | 0 | 57 |
| `urinary_frequency_false:cdacd51c` | `urinary_frequency_false` | false | 57 | 57 | 43 | 0 | 0 | 0 | 0 | 57 |
| `urinary_frequency_false:f78f9d25` | `urinary_frequency_false` | false | 57 | 57 | 57 | 11 | 8 | 0 | 0 | 57 |
| `urinary_frequency_false:70687811` | `urinary_frequency_false` | false | 56 | 56 | 8 | 0 | 0 | 0 | 0 | 56 |
| `urinary_frequency_false:838b4247` | `urinary_frequency_false` | false | 56 | 56 | 1 | 0 | 0 | 1 | 0 | 56 |
| `urinary_frequency_true:2a4e0890` | `urinary_frequency_true` | true | 56 | 56 | 56 | 0 | 0 | 0 | 0 | 56 |
| `urinary_frequency_true:ffa90ce7` | `urinary_frequency_true` | true | 56 | 56 | 56 | 13 | 31 | 1 | 39 | 55 |
| `urinary_frequency_false:767e3f26` | `urinary_frequency_false` | false | 55 | 55 | 0 | 0 | 0 | 0 | 0 | 55 |
| `urinary_frequency_false:8a1fa086` | `urinary_frequency_false` | false | 55 | 55 | 50 | 0 | 0 | 0 | 0 | 55 |
| `urinary_frequency_true:d01347c4` | `urinary_frequency_true` | true | 55 | 55 | 32 | 0 | 0 | 0 | 0 | 55 |
| `urinary_frequency_false:0c947cff` | `urinary_frequency_false` | false | 54 | 54 | 48 | 0 | 0 | 0 | 0 | 54 |
| `urinary_frequency_false:3f640028` | `urinary_frequency_false` | false | 54 | 54 | 10 | 0 | 0 | 0 | 0 | 54 |
| `urinary_frequency_false:bb59f573` | `urinary_frequency_false` | false | 54 | 54 | 0 | 0 | 0 | 0 | 0 | 54 |
| `urinary_frequency_false:c631660d` | `urinary_frequency_false` | false | 53 | 53 | 52 | 53 | 37 | 51 | 35 | 18 |
| `urinary_frequency_false:63302b59` | `urinary_frequency_false` | false | 52 | 52 | 21 | 52 | 37 | 50 | 39 | 31 |
| `urinary_frequency_false:99f7fbc1` | `urinary_frequency_false` | false | 52 | 52 | 1 | 0 | 0 | 0 | 0 | 52 |
| `urinary_frequency_false:f324736d` | `urinary_frequency_false` | false | 50 | 50 | 50 | 0 | 0 | 0 | 0 | 50 |
| `urinary_frequency_false:941626e8` | `urinary_frequency_false` | false | 44 | 44 | 31 | 44 | 35 | 47 | 35 | 16 |
| `urinary_frequency_false:42205311` | `urinary_frequency_false` | false | 46 | 46 | 7 | 0 | 0 | 0 | 0 | 46 |
| `urinary_frequency_true:87b688c8` | `urinary_frequency_true` | true | 46 | 46 | 43 | 0 | 0 | 0 | 0 | 46 |
| `urinary_frequency_false:fc6a56d2` | `urinary_frequency_false` | false | 44 | 44 | 38 | 0 | 2 | 45 | 38 | 45 |
| `urinary_frequency_false:f32c9e68` | `urinary_frequency_false` | false | 44 | 44 | 44 | 29 | 33 | 43 | 33 | 15 |
| `urinary_frequency_true:2c452329` | `urinary_frequency_true` | true | 43 | 43 | 42 | 43 | 0 | 44 | 26 | 44 |
| `urinary_frequency_false:6bb71206` | `urinary_frequency_false` | false | 42 | 42 | 42 | 42 | 35 | 42 | 31 | 11 |
| `urinary_frequency_false:3ce1d817` | `urinary_frequency_false` | false | 41 | 41 | 22 | 0 | 0 | 3 | 0 | 41 |

*127 further fragments erred on at least one model; the JSON holds them all.*

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
| false | 2479 | **46** | 0.0% [0.0%, 0.0%] |
| null_ambiguous | 3062 | **210** | 100.0% [100.0%, 100.0%] |
| null_structural | 2978 | **1** | 100.0% [100.0%, 100.0%] |
| true | 1481 | **46** | 0.0% [0.0%, 0.0%] |

### By null sub-class

| sub-class | n | eff n | null recall [95% CI] |
|---|---|---|---|
| adjacent | 590 | **40** | 100.0% [100.0%, 100.0%] |
| hedged | 617 | **42** | 100.0% [100.0%, 100.0%] |
| historical | 539 | **40** | 100.0% [100.0%, 100.0%] |
| metaphor | 674 | **44** | 100.0% [100.0%, 100.0%] |
| third_party | 642 | **44** | 100.0% [100.0%, 100.0%] |

### By fragment library

| library | n | eff n | accuracy [95% CI] |
|---|---|---|---|
| urinary_frequency_false | 2479 | **46** | 0.0% [0.0%, 0.0%] |
| urinary_frequency_null_adjacent | 590 | **40** | 100.0% [100.0%, 100.0%] |
| urinary_frequency_null_hedged | 617 | **42** | 100.0% [100.0%, 100.0%] |
| urinary_frequency_null_historical | 539 | **40** | 100.0% [100.0%, 100.0%] |
| urinary_frequency_null_metaphor | 674 | **44** | 100.0% [100.0%, 100.0%] |
| urinary_frequency_null_thirdparty | 642 | **44** | 100.0% [100.0%, 100.0%] |
| urinary_frequency_true | 1481 | **46** | 0.0% [0.0%, 0.0%] |
| (none) | 2978 | **1** | 100.0% [100.0%, 100.0%] |

### Per-fragment errors (worst first)

Whether errors are spread thinly across many fragments or piled onto a few is the difference
between "the method is too weak" (model work) and "these specific ideas are not learnable from
the data we have" (library work, and these are the fragments to write more of). No intervals:
a fragment is one cluster, so an interval over its own examples measures nothing.

92 of 302 decisive fragments were got wrong at least once.

`majority_class`: 3960 errors across 92 of 302 decisive fragments. Half of them fall on **30** fragments (an even spread would be 46.0); the worst ten carry 22.6% of all errors.

| fragment | library | sub-class | truth | correct | accuracy | predicted as |
|---|---|---|---|---|---|---|
| `urinary_frequency_false:a15017c2` | `urinary_frequency_false` | -- | false | 0/133 | 0.0% | null 133 |
| `urinary_frequency_false:a7fe81d1` | `urinary_frequency_false` | -- | false | 0/127 | 0.0% | null 127 |
| `urinary_frequency_false:d293ee8c` | `urinary_frequency_false` | -- | false | 0/125 | 0.0% | null 125 |
| `urinary_frequency_false:22b965f9` | `urinary_frequency_false` | -- | false | 0/119 | 0.0% | null 119 |
| `urinary_frequency_true:272d2041` | `urinary_frequency_true` | -- | true | 0/67 | 0.0% | null 67 |
| `urinary_frequency_false:6c16f65e` | `urinary_frequency_false` | -- | false | 0/66 | 0.0% | null 66 |
| `urinary_frequency_true:11d16987` | `urinary_frequency_true` | -- | true | 0/66 | 0.0% | null 66 |
| `urinary_frequency_false:1d7759da` | `urinary_frequency_false` | -- | false | 0/65 | 0.0% | null 65 |
| `urinary_frequency_false:7fc83941` | `urinary_frequency_false` | -- | false | 0/65 | 0.0% | null 65 |
| `urinary_frequency_false:f3e3b17c` | `urinary_frequency_false` | -- | false | 0/63 | 0.0% | null 63 |
| `urinary_frequency_false:a5342750` | `urinary_frequency_false` | -- | false | 0/62 | 0.0% | null 62 |
| `urinary_frequency_true:764389c0` | `urinary_frequency_true` | -- | true | 0/62 | 0.0% | null 62 |
| `urinary_frequency_false:c7b96e67` | `urinary_frequency_false` | -- | false | 0/61 | 0.0% | null 61 |
| `urinary_frequency_false:44543d5e` | `urinary_frequency_false` | -- | false | 0/60 | 0.0% | null 60 |
| `urinary_frequency_false:a9a59952` | `urinary_frequency_false` | -- | false | 0/60 | 0.0% | null 60 |
| `urinary_frequency_false:1a4ef542` | `urinary_frequency_false` | -- | false | 0/57 | 0.0% | null 57 |
| `urinary_frequency_false:cdacd51c` | `urinary_frequency_false` | -- | false | 0/57 | 0.0% | null 57 |
| `urinary_frequency_false:f78f9d25` | `urinary_frequency_false` | -- | false | 0/57 | 0.0% | null 57 |
| `urinary_frequency_false:70687811` | `urinary_frequency_false` | -- | false | 0/56 | 0.0% | null 56 |
| `urinary_frequency_false:838b4247` | `urinary_frequency_false` | -- | false | 0/56 | 0.0% | null 56 |
| `urinary_frequency_true:2a4e0890` | `urinary_frequency_true` | -- | true | 0/56 | 0.0% | null 56 |
| `urinary_frequency_true:ffa90ce7` | `urinary_frequency_true` | -- | true | 0/56 | 0.0% | null 56 |
| `urinary_frequency_false:767e3f26` | `urinary_frequency_false` | -- | false | 0/55 | 0.0% | null 55 |
| `urinary_frequency_false:8a1fa086` | `urinary_frequency_false` | -- | false | 0/55 | 0.0% | null 55 |
| `urinary_frequency_true:d01347c4` | `urinary_frequency_true` | -- | true | 0/55 | 0.0% | null 55 |
| `urinary_frequency_false:0c947cff` | `urinary_frequency_false` | -- | false | 0/54 | 0.0% | null 54 |
| `urinary_frequency_false:3f640028` | `urinary_frequency_false` | -- | false | 0/54 | 0.0% | null 54 |
| `urinary_frequency_false:bb59f573` | `urinary_frequency_false` | -- | false | 0/54 | 0.0% | null 54 |
| `urinary_frequency_false:c631660d` | `urinary_frequency_false` | -- | false | 0/53 | 0.0% | null 53 |
| `urinary_frequency_false:63302b59` | `urinary_frequency_false` | -- | false | 0/52 | 0.0% | null 52 |
| `urinary_frequency_false:99f7fbc1` | `urinary_frequency_false` | -- | false | 0/52 | 0.0% | null 52 |
| `urinary_frequency_false:f324736d` | `urinary_frequency_false` | -- | false | 0/50 | 0.0% | null 50 |
| `urinary_frequency_false:42205311` | `urinary_frequency_false` | -- | false | 0/46 | 0.0% | null 46 |
| `urinary_frequency_true:87b688c8` | `urinary_frequency_true` | -- | true | 0/46 | 0.0% | null 46 |
| `urinary_frequency_false:941626e8` | `urinary_frequency_false` | -- | false | 0/44 | 0.0% | null 44 |
| `urinary_frequency_false:f32c9e68` | `urinary_frequency_false` | -- | false | 0/44 | 0.0% | null 44 |
| `urinary_frequency_false:fc6a56d2` | `urinary_frequency_false` | -- | false | 0/44 | 0.0% | null 44 |
| `urinary_frequency_true:2c452329` | `urinary_frequency_true` | -- | true | 0/43 | 0.0% | null 43 |
| `urinary_frequency_false:6bb71206` | `urinary_frequency_false` | -- | false | 0/42 | 0.0% | null 42 |
| `urinary_frequency_false:3ce1d817` | `urinary_frequency_false` | -- | false | 0/41 | 0.0% | null 41 |

*52 further fragments with at least one error are in the JSON sidecar; every fragment is there regardless of score.*

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
| false | 2479 | **46** | 0.0% [0.0%, 0.0%] |
| null_ambiguous | 3062 | **210** | 100.0% [100.0%, 100.0%] |
| null_structural | 2978 | **1** | 100.0% [100.0%, 100.0%] |
| true | 1481 | **46** | 0.0% [0.0%, 0.0%] |

### By null sub-class

| sub-class | n | eff n | null recall [95% CI] |
|---|---|---|---|
| adjacent | 590 | **40** | 100.0% [100.0%, 100.0%] |
| hedged | 617 | **42** | 100.0% [100.0%, 100.0%] |
| historical | 539 | **40** | 100.0% [100.0%, 100.0%] |
| metaphor | 674 | **44** | 100.0% [100.0%, 100.0%] |
| third_party | 642 | **44** | 100.0% [100.0%, 100.0%] |

### By fragment library

| library | n | eff n | accuracy [95% CI] |
|---|---|---|---|
| urinary_frequency_false | 2479 | **46** | 0.0% [0.0%, 0.0%] |
| urinary_frequency_null_adjacent | 590 | **40** | 100.0% [100.0%, 100.0%] |
| urinary_frequency_null_hedged | 617 | **42** | 100.0% [100.0%, 100.0%] |
| urinary_frequency_null_historical | 539 | **40** | 100.0% [100.0%, 100.0%] |
| urinary_frequency_null_metaphor | 674 | **44** | 100.0% [100.0%, 100.0%] |
| urinary_frequency_null_thirdparty | 642 | **44** | 100.0% [100.0%, 100.0%] |
| urinary_frequency_true | 1481 | **46** | 0.0% [0.0%, 0.0%] |
| (none) | 2978 | **1** | 100.0% [100.0%, 100.0%] |

### Per-fragment errors (worst first)

Whether errors are spread thinly across many fragments or piled onto a few is the difference
between "the method is too weak" (model work) and "these specific ideas are not learnable from
the data we have" (library work, and these are the fragments to write more of). No intervals:
a fragment is one cluster, so an interval over its own examples measures nothing.

92 of 302 decisive fragments were got wrong at least once.

`length_only`: 3960 errors across 92 of 302 decisive fragments. Half of them fall on **30** fragments (an even spread would be 46.0); the worst ten carry 22.6% of all errors.

| fragment | library | sub-class | truth | correct | accuracy | predicted as |
|---|---|---|---|---|---|---|
| `urinary_frequency_false:a15017c2` | `urinary_frequency_false` | -- | false | 0/133 | 0.0% | null 133 |
| `urinary_frequency_false:a7fe81d1` | `urinary_frequency_false` | -- | false | 0/127 | 0.0% | null 127 |
| `urinary_frequency_false:d293ee8c` | `urinary_frequency_false` | -- | false | 0/125 | 0.0% | null 125 |
| `urinary_frequency_false:22b965f9` | `urinary_frequency_false` | -- | false | 0/119 | 0.0% | null 119 |
| `urinary_frequency_true:272d2041` | `urinary_frequency_true` | -- | true | 0/67 | 0.0% | null 67 |
| `urinary_frequency_false:6c16f65e` | `urinary_frequency_false` | -- | false | 0/66 | 0.0% | null 66 |
| `urinary_frequency_true:11d16987` | `urinary_frequency_true` | -- | true | 0/66 | 0.0% | null 66 |
| `urinary_frequency_false:1d7759da` | `urinary_frequency_false` | -- | false | 0/65 | 0.0% | null 65 |
| `urinary_frequency_false:7fc83941` | `urinary_frequency_false` | -- | false | 0/65 | 0.0% | null 65 |
| `urinary_frequency_false:f3e3b17c` | `urinary_frequency_false` | -- | false | 0/63 | 0.0% | null 63 |
| `urinary_frequency_false:a5342750` | `urinary_frequency_false` | -- | false | 0/62 | 0.0% | null 62 |
| `urinary_frequency_true:764389c0` | `urinary_frequency_true` | -- | true | 0/62 | 0.0% | null 62 |
| `urinary_frequency_false:c7b96e67` | `urinary_frequency_false` | -- | false | 0/61 | 0.0% | null 61 |
| `urinary_frequency_false:44543d5e` | `urinary_frequency_false` | -- | false | 0/60 | 0.0% | null 60 |
| `urinary_frequency_false:a9a59952` | `urinary_frequency_false` | -- | false | 0/60 | 0.0% | null 60 |
| `urinary_frequency_false:1a4ef542` | `urinary_frequency_false` | -- | false | 0/57 | 0.0% | null 57 |
| `urinary_frequency_false:cdacd51c` | `urinary_frequency_false` | -- | false | 0/57 | 0.0% | null 57 |
| `urinary_frequency_false:f78f9d25` | `urinary_frequency_false` | -- | false | 0/57 | 0.0% | null 57 |
| `urinary_frequency_false:70687811` | `urinary_frequency_false` | -- | false | 0/56 | 0.0% | null 56 |
| `urinary_frequency_false:838b4247` | `urinary_frequency_false` | -- | false | 0/56 | 0.0% | null 56 |
| `urinary_frequency_true:2a4e0890` | `urinary_frequency_true` | -- | true | 0/56 | 0.0% | null 56 |
| `urinary_frequency_true:ffa90ce7` | `urinary_frequency_true` | -- | true | 0/56 | 0.0% | null 56 |
| `urinary_frequency_false:767e3f26` | `urinary_frequency_false` | -- | false | 0/55 | 0.0% | null 55 |
| `urinary_frequency_false:8a1fa086` | `urinary_frequency_false` | -- | false | 0/55 | 0.0% | null 55 |
| `urinary_frequency_true:d01347c4` | `urinary_frequency_true` | -- | true | 0/55 | 0.0% | null 55 |
| `urinary_frequency_false:0c947cff` | `urinary_frequency_false` | -- | false | 0/54 | 0.0% | null 54 |
| `urinary_frequency_false:3f640028` | `urinary_frequency_false` | -- | false | 0/54 | 0.0% | null 54 |
| `urinary_frequency_false:bb59f573` | `urinary_frequency_false` | -- | false | 0/54 | 0.0% | null 54 |
| `urinary_frequency_false:c631660d` | `urinary_frequency_false` | -- | false | 0/53 | 0.0% | null 53 |
| `urinary_frequency_false:63302b59` | `urinary_frequency_false` | -- | false | 0/52 | 0.0% | null 52 |
| `urinary_frequency_false:99f7fbc1` | `urinary_frequency_false` | -- | false | 0/52 | 0.0% | null 52 |
| `urinary_frequency_false:f324736d` | `urinary_frequency_false` | -- | false | 0/50 | 0.0% | null 50 |
| `urinary_frequency_false:42205311` | `urinary_frequency_false` | -- | false | 0/46 | 0.0% | null 46 |
| `urinary_frequency_true:87b688c8` | `urinary_frequency_true` | -- | true | 0/46 | 0.0% | null 46 |
| `urinary_frequency_false:941626e8` | `urinary_frequency_false` | -- | false | 0/44 | 0.0% | null 44 |
| `urinary_frequency_false:f32c9e68` | `urinary_frequency_false` | -- | false | 0/44 | 0.0% | null 44 |
| `urinary_frequency_false:fc6a56d2` | `urinary_frequency_false` | -- | false | 0/44 | 0.0% | null 44 |
| `urinary_frequency_true:2c452329` | `urinary_frequency_true` | -- | true | 0/43 | 0.0% | null 43 |
| `urinary_frequency_false:6bb71206` | `urinary_frequency_false` | -- | false | 0/42 | 0.0% | null 42 |
| `urinary_frequency_false:3ce1d817` | `urinary_frequency_false` | -- | false | 0/41 | 0.0% | null 41 |

*52 further fragments with at least one error are in the JSON sidecar; every fragment is there regardless of score.*

## `tfidf_logreg`

TF-IDF unigrams and bigrams into logistic regression. Tests whether the dataset is keyword-solvable. Its overall accuracy is close to uninformative; the `null_ambiguous` slice is the number that matters.

Decision-rule margins selected per fold (on each fold's own validation split): 0.0, 0.25.

*Confusion matrix, raw argmax*

|  | pred false | pred true | pred null | total |
|---|---|---|---|---|
| **truth false** | 1212 | 184 | 1083 | 2479 |
| **truth true** | 224 | 163 | 1094 | 1481 |
| **truth null** | 106 | 139 | 5795 | 6040 |
| **total** | 1542 | 486 | 7972 | 10000 |

`null -> true`: 139 of 6040 truly-null examples (2.30%).

*Confusion matrix, after the decision rule*

|  | pred false | pred true | pred null | total |
|---|---|---|---|---|
| **truth false** | 1213 | 183 | 1083 | 2479 |
| **truth true** | 235 | 142 | 1104 | 1481 |
| **truth null** | 107 | 128 | 5805 | 6040 |
| **total** | 1555 | 453 | 7992 | 10000 |

`null -> true`: 128 of 6040 truly-null examples (2.12%).

### Per class, after the decision rule

| class | support | predicted | precision | recall | F1 |
|---|---|---|---|---|---|
| `false` | 2479 | 1555 | 78.0% | 48.9% | 60.1% |
| `true` | 1481 | 453 | 31.3% | 9.6% | 14.7% |
| `null` | 6040 | 7992 | 72.6% | 96.1% | 82.7% |

### By label mode

| label mode | n | eff n | accuracy [95% CI] |
|---|---|---|---|
| false | 2479 | **46** | 48.9% [37.3%, 60.2%] |
| null_ambiguous | 3062 | **210** | 92.8% [90.0%, 95.2%] |
| null_structural | 2978 | **1** | 99.5% [99.5%, 99.5%] |
| true | 1481 | **46** | 9.6% [3.7%, 16.2%] |

### By null sub-class

| sub-class | n | eff n | null recall [95% CI] |
|---|---|---|---|
| adjacent | 590 | **40** | 95.8% [90.0%, 99.7%] |
| hedged | 617 | **42** | 92.1% [84.5%, 97.5%] |
| historical | 539 | **40** | 98.0% [94.9%, 99.8%] |
| metaphor | 674 | **44** | 95.7% [91.8%, 98.7%] |
| third_party | 642 | **44** | 83.5% [75.2%, 90.7%] |

### By fragment library

| library | n | eff n | accuracy [95% CI] |
|---|---|---|---|
| urinary_frequency_false | 2479 | **46** | 48.9% [37.3%, 60.2%] |
| urinary_frequency_null_adjacent | 590 | **40** | 95.8% [90.0%, 99.7%] |
| urinary_frequency_null_hedged | 617 | **42** | 92.1% [84.5%, 97.5%] |
| urinary_frequency_null_historical | 539 | **40** | 98.0% [94.9%, 99.8%] |
| urinary_frequency_null_metaphor | 674 | **44** | 95.7% [91.8%, 98.7%] |
| urinary_frequency_null_thirdparty | 642 | **44** | 83.5% [75.2%, 90.7%] |
| urinary_frequency_true | 1481 | **46** | 9.6% [3.7%, 16.2%] |
| (none) | 2978 | **1** | 99.5% [99.5%, 99.5%] |

### Per-fragment errors (worst first)

Whether errors are spread thinly across many fragments or piled onto a few is the difference
between "the method is too weak" (model work) and "these specific ideas are not learnable from
the data we have" (library work, and these are the fragments to write more of). No intervals:
a fragment is one cluster, so an interval over its own examples measures nothing.

141 of 302 decisive fragments were got wrong at least once.

`tfidf_logreg`: 2825 errors across 141 of 302 decisive fragments. Half of them fall on **30** fragments (an even spread would be 70.5); the worst ten carry 22.3% of all errors.

| fragment | library | sub-class | truth | correct | accuracy | predicted as |
|---|---|---|---|---|---|---|
| `urinary_frequency_true:11d16987` | `urinary_frequency_true` | -- | true | 0/66 | 0.0% | null 66 |
| `urinary_frequency_true:764389c0` | `urinary_frequency_true` | -- | true | 0/62 | 0.0% | null 62 |
| `urinary_frequency_false:f78f9d25` | `urinary_frequency_false` | -- | false | 0/57 | 0.0% | true 1, null 56 |
| `urinary_frequency_true:2a4e0890` | `urinary_frequency_true` | -- | true | 0/56 | 0.0% | null 56 |
| `urinary_frequency_true:ffa90ce7` | `urinary_frequency_true` | -- | true | 0/56 | 0.0% | null 56 |
| `urinary_frequency_false:f324736d` | `urinary_frequency_false` | -- | false | 0/50 | 0.0% | null 50 |
| `urinary_frequency_false:f32c9e68` | `urinary_frequency_false` | -- | false | 0/44 | 0.0% | true 6, null 38 |
| `urinary_frequency_false:6bb71206` | `urinary_frequency_false` | -- | false | 0/42 | 0.0% | null 42 |
| `urinary_frequency_true:f6de3825` | `urinary_frequency_true` | -- | true | 0/40 | 0.0% | false 40 |
| `urinary_frequency_false:8ea3ee34` | `urinary_frequency_false` | -- | false | 0/37 | 0.0% | null 37 |
| `urinary_frequency_true:5008b431` | `urinary_frequency_true` | -- | true | 0/37 | 0.0% | false 9, null 28 |
| `urinary_frequency_true:617cfdc3` | `urinary_frequency_true` | -- | true | 0/37 | 0.0% | false 3, null 34 |
| `urinary_frequency_true:eccbc8ee` | `urinary_frequency_true` | -- | true | 0/36 | 0.0% | false 17, null 19 |
| `urinary_frequency_true:900c8b2c` | `urinary_frequency_true` | -- | true | 0/31 | 0.0% | false 3, null 28 |
| `urinary_frequency_true:e746abc0` | `urinary_frequency_true` | -- | true | 0/31 | 0.0% | false 1, null 30 |
| `urinary_frequency_false:b66fa498` | `urinary_frequency_false` | -- | false | 0/30 | 0.0% | true 16, null 14 |
| `urinary_frequency_false:c85c9d5a` | `urinary_frequency_false` | -- | false | 0/30 | 0.0% | null 30 |
| `urinary_frequency_true:fbca5613` | `urinary_frequency_true` | -- | true | 0/30 | 0.0% | null 30 |
| `urinary_frequency_true:5327793c` | `urinary_frequency_true` | -- | true | 0/28 | 0.0% | null 28 |
| `urinary_frequency_true:fecb0185` | `urinary_frequency_true` | -- | true | 0/28 | 0.0% | null 28 |
| `urinary_frequency_true:32946372` | `urinary_frequency_true` | -- | true | 0/27 | 0.0% | false 24, null 3 |
| `urinary_frequency_true:1d671fe5` | `urinary_frequency_true` | -- | true | 0/26 | 0.0% | false 2, null 24 |
| `urinary_frequency_true:16cfc7d7` | `urinary_frequency_true` | -- | true | 0/25 | 0.0% | null 25 |
| `urinary_frequency_true:f91afcaa` | `urinary_frequency_true` | -- | true | 0/25 | 0.0% | false 3, null 22 |
| `urinary_frequency_true:f9c03b9b` | `urinary_frequency_true` | -- | true | 0/23 | 0.0% | null 23 |
| `urinary_frequency_true:c87f1579` | `urinary_frequency_true` | -- | true | 0/22 | 0.0% | false 1, null 21 |
| `urinary_frequency_true:f0e98801` | `urinary_frequency_true` | -- | true | 0/22 | 0.0% | false 2, null 20 |
| `urinary_frequency_null_hedged:edde7771` | `urinary_frequency_null_hedged` | hedged | null | 0/21 | 0.0% | false 19, true 2 |
| `urinary_frequency_true:57632816` | `urinary_frequency_true` | -- | true | 0/21 | 0.0% | false 7, null 14 |
| `urinary_frequency_true:32cae421` | `urinary_frequency_true` | -- | true | 0/20 | 0.0% | false 20 |
| `urinary_frequency_true:95d4e96a` | `urinary_frequency_true` | -- | true | 0/20 | 0.0% | false 10, null 10 |
| `urinary_frequency_true:c8bfbc09` | `urinary_frequency_true` | -- | true | 0/19 | 0.0% | false 9, null 10 |
| `urinary_frequency_true:20bd4d56` | `urinary_frequency_true` | -- | true | 0/17 | 0.0% | null 17 |
| `urinary_frequency_true:2491f080` | `urinary_frequency_true` | -- | true | 0/17 | 0.0% | null 17 |
| `urinary_frequency_true:52b41248` | `urinary_frequency_true` | -- | true | 0/17 | 0.0% | null 17 |
| `urinary_frequency_true:f5216cf2` | `urinary_frequency_true` | -- | true | 0/17 | 0.0% | null 17 |
| `urinary_frequency_true:c8d32074` | `urinary_frequency_true` | -- | true | 0/15 | 0.0% | null 15 |
| `urinary_frequency_null_thirdparty:01a2c0ef` | `urinary_frequency_null_thirdparty` | third_party | null | 0/13 | 0.0% | true 13 |
| `urinary_frequency_true:5ef90c41` | `urinary_frequency_true` | -- | true | 0/13 | 0.0% | null 13 |
| `urinary_frequency_false:c631660d` | `urinary_frequency_false` | -- | false | 1/53 | 1.9% | false 1, null 52 |

*101 further fragments with at least one error are in the JSON sidecar; every fragment is there regardless of score.*

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
| false | 2479 | **46** | 0.0% [0.0%, 0.0%] |
| null_ambiguous | 3062 | **210** | 100.0% [100.0%, 100.0%] |
| null_structural | 2978 | **1** | 100.0% [100.0%, 100.0%] |
| true | 1481 | **46** | 0.0% [0.0%, 0.0%] |

### By null sub-class

| sub-class | n | eff n | null recall [95% CI] |
|---|---|---|---|
| adjacent | 590 | **40** | 100.0% [100.0%, 100.0%] |
| hedged | 617 | **42** | 100.0% [100.0%, 100.0%] |
| historical | 539 | **40** | 100.0% [100.0%, 100.0%] |
| metaphor | 674 | **44** | 100.0% [100.0%, 100.0%] |
| third_party | 642 | **44** | 100.0% [100.0%, 100.0%] |

### By fragment library

| library | n | eff n | accuracy [95% CI] |
|---|---|---|---|
| urinary_frequency_false | 2479 | **46** | 0.0% [0.0%, 0.0%] |
| urinary_frequency_null_adjacent | 590 | **40** | 100.0% [100.0%, 100.0%] |
| urinary_frequency_null_hedged | 617 | **42** | 100.0% [100.0%, 100.0%] |
| urinary_frequency_null_historical | 539 | **40** | 100.0% [100.0%, 100.0%] |
| urinary_frequency_null_metaphor | 674 | **44** | 100.0% [100.0%, 100.0%] |
| urinary_frequency_null_thirdparty | 642 | **44** | 100.0% [100.0%, 100.0%] |
| urinary_frequency_true | 1481 | **46** | 0.0% [0.0%, 0.0%] |
| (none) | 2978 | **1** | 100.0% [100.0%, 100.0%] |

### Per-fragment errors (worst first)

Whether errors are spread thinly across many fragments or piled onto a few is the difference
between "the method is too weak" (model work) and "these specific ideas are not learnable from
the data we have" (library work, and these are the fragments to write more of). No intervals:
a fragment is one cluster, so an interval over its own examples measures nothing.

92 of 302 decisive fragments were got wrong at least once.

`length_only__shuffled`: 3960 errors across 92 of 302 decisive fragments. Half of them fall on **30** fragments (an even spread would be 46.0); the worst ten carry 22.6% of all errors.

| fragment | library | sub-class | truth | correct | accuracy | predicted as |
|---|---|---|---|---|---|---|
| `urinary_frequency_false:a15017c2` | `urinary_frequency_false` | -- | false | 0/133 | 0.0% | null 133 |
| `urinary_frequency_false:a7fe81d1` | `urinary_frequency_false` | -- | false | 0/127 | 0.0% | null 127 |
| `urinary_frequency_false:d293ee8c` | `urinary_frequency_false` | -- | false | 0/125 | 0.0% | null 125 |
| `urinary_frequency_false:22b965f9` | `urinary_frequency_false` | -- | false | 0/119 | 0.0% | null 119 |
| `urinary_frequency_true:272d2041` | `urinary_frequency_true` | -- | true | 0/67 | 0.0% | null 67 |
| `urinary_frequency_false:6c16f65e` | `urinary_frequency_false` | -- | false | 0/66 | 0.0% | null 66 |
| `urinary_frequency_true:11d16987` | `urinary_frequency_true` | -- | true | 0/66 | 0.0% | null 66 |
| `urinary_frequency_false:1d7759da` | `urinary_frequency_false` | -- | false | 0/65 | 0.0% | null 65 |
| `urinary_frequency_false:7fc83941` | `urinary_frequency_false` | -- | false | 0/65 | 0.0% | null 65 |
| `urinary_frequency_false:f3e3b17c` | `urinary_frequency_false` | -- | false | 0/63 | 0.0% | null 63 |
| `urinary_frequency_false:a5342750` | `urinary_frequency_false` | -- | false | 0/62 | 0.0% | null 62 |
| `urinary_frequency_true:764389c0` | `urinary_frequency_true` | -- | true | 0/62 | 0.0% | null 62 |
| `urinary_frequency_false:c7b96e67` | `urinary_frequency_false` | -- | false | 0/61 | 0.0% | null 61 |
| `urinary_frequency_false:44543d5e` | `urinary_frequency_false` | -- | false | 0/60 | 0.0% | null 60 |
| `urinary_frequency_false:a9a59952` | `urinary_frequency_false` | -- | false | 0/60 | 0.0% | null 60 |
| `urinary_frequency_false:1a4ef542` | `urinary_frequency_false` | -- | false | 0/57 | 0.0% | null 57 |
| `urinary_frequency_false:cdacd51c` | `urinary_frequency_false` | -- | false | 0/57 | 0.0% | null 57 |
| `urinary_frequency_false:f78f9d25` | `urinary_frequency_false` | -- | false | 0/57 | 0.0% | null 57 |
| `urinary_frequency_false:70687811` | `urinary_frequency_false` | -- | false | 0/56 | 0.0% | null 56 |
| `urinary_frequency_false:838b4247` | `urinary_frequency_false` | -- | false | 0/56 | 0.0% | null 56 |
| `urinary_frequency_true:2a4e0890` | `urinary_frequency_true` | -- | true | 0/56 | 0.0% | null 56 |
| `urinary_frequency_true:ffa90ce7` | `urinary_frequency_true` | -- | true | 0/56 | 0.0% | null 56 |
| `urinary_frequency_false:767e3f26` | `urinary_frequency_false` | -- | false | 0/55 | 0.0% | null 55 |
| `urinary_frequency_false:8a1fa086` | `urinary_frequency_false` | -- | false | 0/55 | 0.0% | null 55 |
| `urinary_frequency_true:d01347c4` | `urinary_frequency_true` | -- | true | 0/55 | 0.0% | null 55 |
| `urinary_frequency_false:0c947cff` | `urinary_frequency_false` | -- | false | 0/54 | 0.0% | null 54 |
| `urinary_frequency_false:3f640028` | `urinary_frequency_false` | -- | false | 0/54 | 0.0% | null 54 |
| `urinary_frequency_false:bb59f573` | `urinary_frequency_false` | -- | false | 0/54 | 0.0% | null 54 |
| `urinary_frequency_false:c631660d` | `urinary_frequency_false` | -- | false | 0/53 | 0.0% | null 53 |
| `urinary_frequency_false:63302b59` | `urinary_frequency_false` | -- | false | 0/52 | 0.0% | null 52 |
| `urinary_frequency_false:99f7fbc1` | `urinary_frequency_false` | -- | false | 0/52 | 0.0% | null 52 |
| `urinary_frequency_false:f324736d` | `urinary_frequency_false` | -- | false | 0/50 | 0.0% | null 50 |
| `urinary_frequency_false:42205311` | `urinary_frequency_false` | -- | false | 0/46 | 0.0% | null 46 |
| `urinary_frequency_true:87b688c8` | `urinary_frequency_true` | -- | true | 0/46 | 0.0% | null 46 |
| `urinary_frequency_false:941626e8` | `urinary_frequency_false` | -- | false | 0/44 | 0.0% | null 44 |
| `urinary_frequency_false:f32c9e68` | `urinary_frequency_false` | -- | false | 0/44 | 0.0% | null 44 |
| `urinary_frequency_false:fc6a56d2` | `urinary_frequency_false` | -- | false | 0/44 | 0.0% | null 44 |
| `urinary_frequency_true:2c452329` | `urinary_frequency_true` | -- | true | 0/43 | 0.0% | null 43 |
| `urinary_frequency_false:6bb71206` | `urinary_frequency_false` | -- | false | 0/42 | 0.0% | null 42 |
| `urinary_frequency_false:3ce1d817` | `urinary_frequency_false` | -- | false | 0/41 | 0.0% | null 41 |

*52 further fragments with at least one error are in the JSON sidecar; every fragment is there regardless of score.*

## `tfidf_logreg__shuffled`

TF-IDF unigrams and bigrams into logistic regression. Tests whether the dataset is keyword-solvable. Its overall accuracy is close to uninformative; the `null_ambiguous` slice is the number that matters. **Negative control:** trained on permuted training labels (seed 7) and evaluated on the unpermuted test split, where it must land at chance.

Decision-rule margins selected per fold (on each fold's own validation split): 0.0.
Every fold selected margin 0, so the ruled and raw views below are the same decisions. That is a finding rather than a bug: no margin improved macro-F1 without worsening the `null -> true` rate.

*Confusion matrix, raw argmax*

|  | pred false | pred true | pred null | total |
|---|---|---|---|---|
| **truth false** | 0 | 0 | 2479 | 2479 |
| **truth true** | 0 | 0 | 1481 | 1481 |
| **truth null** | 3 | 0 | 6037 | 6040 |
| **total** | 3 | 0 | 9997 | 10000 |

`null -> true`: 0 of 6040 truly-null examples (0.00%).

*Confusion matrix, after the decision rule*

|  | pred false | pred true | pred null | total |
|---|---|---|---|---|
| **truth false** | 0 | 0 | 2479 | 2479 |
| **truth true** | 0 | 0 | 1481 | 1481 |
| **truth null** | 3 | 0 | 6037 | 6040 |
| **total** | 3 | 0 | 9997 | 10000 |

`null -> true`: 0 of 6040 truly-null examples (0.00%).

### Per class, after the decision rule

| class | support | predicted | precision | recall | F1 |
|---|---|---|---|---|---|
| `false` | 2479 | 3 | 0.0% | 0.0% | 0.0% |
| `true` | 1481 | 0 | -- | 0.0% | 0.0% |
| `null` | 6040 | 9997 | 60.4% | 100.0% | 75.3% |

### By label mode

| label mode | n | eff n | accuracy [95% CI] |
|---|---|---|---|
| false | 2479 | **46** | 0.0% [0.0%, 0.0%] |
| null_ambiguous | 3062 | **210** | 100.0% [99.9%, 100.0%] |
| null_structural | 2978 | **1** | 99.9% [99.9%, 99.9%] |
| true | 1481 | **46** | 0.0% [0.0%, 0.0%] |

### By null sub-class

| sub-class | n | eff n | null recall [95% CI] |
|---|---|---|---|
| adjacent | 590 | **40** | 100.0% [100.0%, 100.0%] |
| hedged | 617 | **42** | 100.0% [100.0%, 100.0%] |
| historical | 539 | **40** | 99.8% [99.4%, 100.0%] |
| metaphor | 674 | **44** | 100.0% [100.0%, 100.0%] |
| third_party | 642 | **44** | 100.0% [100.0%, 100.0%] |

### By fragment library

| library | n | eff n | accuracy [95% CI] |
|---|---|---|---|
| urinary_frequency_false | 2479 | **46** | 0.0% [0.0%, 0.0%] |
| urinary_frequency_null_adjacent | 590 | **40** | 100.0% [100.0%, 100.0%] |
| urinary_frequency_null_hedged | 617 | **42** | 100.0% [100.0%, 100.0%] |
| urinary_frequency_null_historical | 539 | **40** | 99.8% [99.4%, 100.0%] |
| urinary_frequency_null_metaphor | 674 | **44** | 100.0% [100.0%, 100.0%] |
| urinary_frequency_null_thirdparty | 642 | **44** | 100.0% [100.0%, 100.0%] |
| urinary_frequency_true | 1481 | **46** | 0.0% [0.0%, 0.0%] |
| (none) | 2978 | **1** | 99.9% [99.9%, 99.9%] |

### Per-fragment errors (worst first)

Whether errors are spread thinly across many fragments or piled onto a few is the difference
between "the method is too weak" (model work) and "these specific ideas are not learnable from
the data we have" (library work, and these are the fragments to write more of). No intervals:
a fragment is one cluster, so an interval over its own examples measures nothing.

93 of 302 decisive fragments were got wrong at least once.

`tfidf_logreg__shuffled`: 3961 errors across 93 of 302 decisive fragments. Half of them fall on **30** fragments (an even spread would be 46.5); the worst ten carry 22.6% of all errors.

| fragment | library | sub-class | truth | correct | accuracy | predicted as |
|---|---|---|---|---|---|---|
| `urinary_frequency_false:a15017c2` | `urinary_frequency_false` | -- | false | 0/133 | 0.0% | null 133 |
| `urinary_frequency_false:a7fe81d1` | `urinary_frequency_false` | -- | false | 0/127 | 0.0% | null 127 |
| `urinary_frequency_false:d293ee8c` | `urinary_frequency_false` | -- | false | 0/125 | 0.0% | null 125 |
| `urinary_frequency_false:22b965f9` | `urinary_frequency_false` | -- | false | 0/119 | 0.0% | null 119 |
| `urinary_frequency_true:272d2041` | `urinary_frequency_true` | -- | true | 0/67 | 0.0% | null 67 |
| `urinary_frequency_false:6c16f65e` | `urinary_frequency_false` | -- | false | 0/66 | 0.0% | null 66 |
| `urinary_frequency_true:11d16987` | `urinary_frequency_true` | -- | true | 0/66 | 0.0% | null 66 |
| `urinary_frequency_false:1d7759da` | `urinary_frequency_false` | -- | false | 0/65 | 0.0% | null 65 |
| `urinary_frequency_false:7fc83941` | `urinary_frequency_false` | -- | false | 0/65 | 0.0% | null 65 |
| `urinary_frequency_false:f3e3b17c` | `urinary_frequency_false` | -- | false | 0/63 | 0.0% | null 63 |
| `urinary_frequency_false:a5342750` | `urinary_frequency_false` | -- | false | 0/62 | 0.0% | null 62 |
| `urinary_frequency_true:764389c0` | `urinary_frequency_true` | -- | true | 0/62 | 0.0% | null 62 |
| `urinary_frequency_false:c7b96e67` | `urinary_frequency_false` | -- | false | 0/61 | 0.0% | null 61 |
| `urinary_frequency_false:44543d5e` | `urinary_frequency_false` | -- | false | 0/60 | 0.0% | null 60 |
| `urinary_frequency_false:a9a59952` | `urinary_frequency_false` | -- | false | 0/60 | 0.0% | null 60 |
| `urinary_frequency_false:1a4ef542` | `urinary_frequency_false` | -- | false | 0/57 | 0.0% | null 57 |
| `urinary_frequency_false:cdacd51c` | `urinary_frequency_false` | -- | false | 0/57 | 0.0% | null 57 |
| `urinary_frequency_false:f78f9d25` | `urinary_frequency_false` | -- | false | 0/57 | 0.0% | null 57 |
| `urinary_frequency_false:70687811` | `urinary_frequency_false` | -- | false | 0/56 | 0.0% | null 56 |
| `urinary_frequency_false:838b4247` | `urinary_frequency_false` | -- | false | 0/56 | 0.0% | null 56 |
| `urinary_frequency_true:2a4e0890` | `urinary_frequency_true` | -- | true | 0/56 | 0.0% | null 56 |
| `urinary_frequency_true:ffa90ce7` | `urinary_frequency_true` | -- | true | 0/56 | 0.0% | null 56 |
| `urinary_frequency_false:767e3f26` | `urinary_frequency_false` | -- | false | 0/55 | 0.0% | null 55 |
| `urinary_frequency_false:8a1fa086` | `urinary_frequency_false` | -- | false | 0/55 | 0.0% | null 55 |
| `urinary_frequency_true:d01347c4` | `urinary_frequency_true` | -- | true | 0/55 | 0.0% | null 55 |
| `urinary_frequency_false:0c947cff` | `urinary_frequency_false` | -- | false | 0/54 | 0.0% | null 54 |
| `urinary_frequency_false:3f640028` | `urinary_frequency_false` | -- | false | 0/54 | 0.0% | null 54 |
| `urinary_frequency_false:bb59f573` | `urinary_frequency_false` | -- | false | 0/54 | 0.0% | null 54 |
| `urinary_frequency_false:c631660d` | `urinary_frequency_false` | -- | false | 0/53 | 0.0% | null 53 |
| `urinary_frequency_false:63302b59` | `urinary_frequency_false` | -- | false | 0/52 | 0.0% | null 52 |
| `urinary_frequency_false:99f7fbc1` | `urinary_frequency_false` | -- | false | 0/52 | 0.0% | null 52 |
| `urinary_frequency_false:f324736d` | `urinary_frequency_false` | -- | false | 0/50 | 0.0% | null 50 |
| `urinary_frequency_false:42205311` | `urinary_frequency_false` | -- | false | 0/46 | 0.0% | null 46 |
| `urinary_frequency_true:87b688c8` | `urinary_frequency_true` | -- | true | 0/46 | 0.0% | null 46 |
| `urinary_frequency_false:941626e8` | `urinary_frequency_false` | -- | false | 0/44 | 0.0% | null 44 |
| `urinary_frequency_false:f32c9e68` | `urinary_frequency_false` | -- | false | 0/44 | 0.0% | null 44 |
| `urinary_frequency_false:fc6a56d2` | `urinary_frequency_false` | -- | false | 0/44 | 0.0% | null 44 |
| `urinary_frequency_true:2c452329` | `urinary_frequency_true` | -- | true | 0/43 | 0.0% | null 43 |
| `urinary_frequency_false:6bb71206` | `urinary_frequency_false` | -- | false | 0/42 | 0.0% | null 42 |
| `urinary_frequency_false:3ce1d817` | `urinary_frequency_false` | -- | false | 0/41 | 0.0% | null 41 |

*53 further fragments with at least one error are in the JSON sidecar; every fragment is there regardless of score.*

## `arm_b_finetune@c0.0-d0.0`

`roberta-base` with **every layer unfrozen**, mean-pooled, with the same `Linear(768, 3)` head -- 110M trainable parameters against Arm A's 2,307. Three epochs at batch 32, learning rate 2e-5, 10% linear warmup, AdamW, fp32. No gradient checkpointing, no 8-bit optimiser, no LoRA, no gradient accumulation: the full model fits in 12GB with room to spare, so anything that reads like a compute compromise would be a mistake rather than a saving. This is the arm that separates "the fragment libraries are the bottleneck" from "the method is too weak": if a fully fine-tuned encoder still cannot read third-party attribution, tense or metaphor, the limit is in the ideas the libraries contain and the fix is library work, not model work.

Decision-rule margins selected per fold (on each fold's own validation split): 0.0, 0.05, 0.15, 0.7, 0.9.

*Confusion matrix, raw argmax*

|  | pred false | pred true | pred null | total |
|---|---|---|---|---|
| **truth false** | 1899 | 381 | 199 | 2479 |
| **truth true** | 131 | 1074 | 276 | 1481 |
| **truth null** | 39 | 130 | 5871 | 6040 |
| **total** | 2069 | 1585 | 6346 | 10000 |

`null -> true`: 130 of 6040 truly-null examples (2.15%).

*Confusion matrix, after the decision rule*

|  | pred false | pred true | pred null | total |
|---|---|---|---|---|
| **truth false** | 1908 | 357 | 214 | 2479 |
| **truth true** | 132 | 1045 | 304 | 1481 |
| **truth null** | 39 | 114 | 5887 | 6040 |
| **total** | 2079 | 1516 | 6405 | 10000 |

`null -> true`: 114 of 6040 truly-null examples (1.89%).

### Per class, after the decision rule

| class | support | predicted | precision | recall | F1 |
|---|---|---|---|---|---|
| `false` | 2479 | 2079 | 91.8% | 77.0% | 83.7% |
| `true` | 1481 | 1516 | 68.9% | 70.6% | 69.7% |
| `null` | 6040 | 6405 | 91.9% | 97.5% | 94.6% |

### By label mode

| label mode | n | eff n | accuracy [95% CI] |
|---|---|---|---|
| false | 2479 | **46** | 77.0% [62.9%, 89.4%] |
| null_ambiguous | 3062 | **210** | 95.0% [92.2%, 97.2%] |
| null_structural | 2978 | **1** | 100.0% [100.0%, 100.0%] |
| true | 1481 | **46** | 70.6% [57.8%, 82.3%] |

### By null sub-class

| sub-class | n | eff n | null recall [95% CI] |
|---|---|---|---|
| adjacent | 590 | **40** | 91.4% [82.3%, 98.3%] |
| hedged | 617 | **42** | 92.9% [86.1%, 98.0%] |
| historical | 539 | **40** | 98.7% [96.7%, 100.0%] |
| metaphor | 674 | **44** | 94.1% [87.2%, 99.4%] |
| third_party | 642 | **44** | 98.3% [96.7%, 99.7%] |

### By fragment library

| library | n | eff n | accuracy [95% CI] |
|---|---|---|---|
| urinary_frequency_false | 2479 | **46** | 77.0% [62.9%, 89.4%] |
| urinary_frequency_null_adjacent | 590 | **40** | 91.4% [82.3%, 98.3%] |
| urinary_frequency_null_hedged | 617 | **42** | 92.9% [86.1%, 98.0%] |
| urinary_frequency_null_historical | 539 | **40** | 98.7% [96.7%, 100.0%] |
| urinary_frequency_null_metaphor | 674 | **44** | 94.1% [87.2%, 99.4%] |
| urinary_frequency_null_thirdparty | 642 | **44** | 98.3% [96.7%, 99.7%] |
| urinary_frequency_true | 1481 | **46** | 70.6% [57.8%, 82.3%] |
| (none) | 2978 | **1** | 100.0% [100.0%, 100.0%] |

### Per-fragment errors (worst first)

Whether errors are spread thinly across many fragments or piled onto a few is the difference
between "the method is too weak" (model work) and "these specific ideas are not learnable from
the data we have" (library work, and these are the fragments to write more of). No intervals:
a fragment is one cluster, so an interval over its own examples measures nothing.

65 of 302 decisive fragments were got wrong at least once.

`arm_b_finetune@c0.0-d0.0`: 1160 errors across 65 of 302 decisive fragments. Half of them fall on **10** fragments (an even spread would be 32.5); the worst ten carry 52.7% of all errors.

| fragment | library | sub-class | truth | correct | accuracy | predicted as |
|---|---|---|---|---|---|---|
| `urinary_frequency_false:c631660d` | `urinary_frequency_false` | -- | false | 0/53 | 0.0% | null 53 |
| `urinary_frequency_false:63302b59` | `urinary_frequency_false` | -- | false | 0/52 | 0.0% | true 52 |
| `urinary_frequency_false:941626e8` | `urinary_frequency_false` | -- | false | 0/44 | 0.0% | null 44 |
| `urinary_frequency_true:2c452329` | `urinary_frequency_true` | -- | true | 0/43 | 0.0% | false 42, null 1 |
| `urinary_frequency_false:6bb71206` | `urinary_frequency_false` | -- | false | 0/42 | 0.0% | true 34, null 8 |
| `urinary_frequency_true:f9c03b9b` | `urinary_frequency_true` | -- | true | 0/23 | 0.0% | null 23 |
| `urinary_frequency_true:32cae421` | `urinary_frequency_true` | -- | true | 0/20 | 0.0% | false 20 |
| `urinary_frequency_null_adjacent:c791bce4` | `urinary_frequency_null_adjacent` | adjacent | null | 0/17 | 0.0% | true 17 |
| `urinary_frequency_null_metaphor:518f483f` | `urinary_frequency_null_metaphor` | metaphor | null | 0/17 | 0.0% | false 6, true 11 |
| `urinary_frequency_true:2491f080` | `urinary_frequency_true` | -- | true | 0/17 | 0.0% | null 17 |
| `urinary_frequency_true:f5216cf2` | `urinary_frequency_true` | -- | true | 0/17 | 0.0% | null 17 |
| `urinary_frequency_true:c8d32074` | `urinary_frequency_true` | -- | true | 0/15 | 0.0% | null 15 |
| `urinary_frequency_null_hedged:ff5d90b8` | `urinary_frequency_null_hedged` | hedged | null | 0/13 | 0.0% | false 13 |
| `urinary_frequency_null_hedged:5f612dfb` | `urinary_frequency_null_hedged` | hedged | null | 0/11 | 0.0% | true 11 |
| `urinary_frequency_true:95d4e96a` | `urinary_frequency_true` | -- | true | 1/20 | 5.0% | true 1, null 19 |
| `urinary_frequency_true:20bd4d56` | `urinary_frequency_true` | -- | true | 1/17 | 5.9% | true 1, null 16 |
| `urinary_frequency_true:11d16987` | `urinary_frequency_true` | -- | true | 4/66 | 6.1% | false 1, true 4, null 61 |
| `urinary_frequency_false:d293ee8c` | `urinary_frequency_false` | -- | false | 10/125 | 8.0% | false 10, true 115 |
| `urinary_frequency_false:a15017c2` | `urinary_frequency_false` | -- | false | 11/133 | 8.3% | false 11, true 54, null 68 |
| `urinary_frequency_null_adjacent:d67c5d52` | `urinary_frequency_null_adjacent` | adjacent | null | 2/18 | 11.1% | true 16, null 2 |
| `urinary_frequency_true:617cfdc3` | `urinary_frequency_true` | -- | true | 5/37 | 13.5% | true 5, null 32 |
| `urinary_frequency_false:b66fa498` | `urinary_frequency_false` | -- | false | 5/30 | 16.7% | false 5, true 25 |
| `urinary_frequency_null_metaphor:eb9e9615` | `urinary_frequency_null_metaphor` | metaphor | null | 3/16 | 18.8% | false 12, true 1, null 3 |
| `urinary_frequency_true:35a67edf` | `urinary_frequency_true` | -- | true | 7/35 | 20.0% | true 7, null 28 |
| `urinary_frequency_true:32946372` | `urinary_frequency_true` | -- | true | 6/27 | 22.2% | false 21, true 6 |
| `urinary_frequency_true:764389c0` | `urinary_frequency_true` | -- | true | 16/62 | 25.8% | false 45, true 16, null 1 |
| `urinary_frequency_true:e746abc0` | `urinary_frequency_true` | -- | true | 10/31 | 32.3% | true 10, null 21 |
| `urinary_frequency_false:8239d5f6` | `urinary_frequency_false` | -- | false | 13/39 | 33.3% | false 13, true 26 |
| `urinary_frequency_false:f32c9e68` | `urinary_frequency_false` | -- | false | 15/44 | 34.1% | false 15, true 29 |
| `urinary_frequency_null_adjacent:15320912` | `urinary_frequency_null_adjacent` | adjacent | null | 7/17 | 41.2% | true 10, null 7 |
| `urinary_frequency_false:a61aba66` | `urinary_frequency_false` | -- | false | 19/39 | 48.7% | false 19, null 20 |
| `urinary_frequency_true:5327793c` | `urinary_frequency_true` | -- | true | 15/28 | 53.6% | true 15, null 13 |
| `urinary_frequency_null_adjacent:30abc414` | `urinary_frequency_null_adjacent` | adjacent | null | 7/13 | 53.8% | false 6, null 7 |
| `urinary_frequency_true:1d671fe5` | `urinary_frequency_true` | -- | true | 15/26 | 57.7% | false 1, true 15, null 10 |
| `urinary_frequency_null_hedged:fc9770b8` | `urinary_frequency_null_hedged` | hedged | null | 10/17 | 58.8% | true 7, null 10 |
| `urinary_frequency_null_historical:bfc85e83` | `urinary_frequency_null_historical` | historical | null | 6/10 | 60.0% | true 4, null 6 |
| `urinary_frequency_null_historical:8befbb86` | `urinary_frequency_null_historical` | historical | null | 5/8 | 62.5% | true 3, null 5 |
| `urinary_frequency_false:ec8210fb` | `urinary_frequency_false` | -- | false | 20/30 | 66.7% | false 20, null 10 |
| `urinary_frequency_false:44543d5e` | `urinary_frequency_false` | -- | false | 41/60 | 68.3% | false 41, true 19 |
| `urinary_frequency_null_hedged:fe13847c` | `urinary_frequency_null_hedged` | hedged | null | 11/16 | 68.8% | true 5, null 11 |

*25 further fragments with at least one error are in the JSON sidecar; every fragment is there regardless of score.*

## `arm_b_finetune@c0.0-d0.3`

`roberta-base` with **every layer unfrozen**, mean-pooled, with the same `Linear(768, 3)` head -- 110M trainable parameters against Arm A's 2,307. Three epochs at batch 32, learning rate 2e-5, 10% linear warmup, AdamW, fp32. No gradient checkpointing, no 8-bit optimiser, no LoRA, no gradient accumulation: the full model fits in 12GB with room to spare, so anything that reads like a compute compromise would be a mistake rather than a saving. This is the arm that separates "the fragment libraries are the bottleneck" from "the method is too weak": if a fully fine-tuned encoder still cannot read third-party attribution, tense or metaphor, the limit is in the ideas the libraries contain and the fix is library work, not model work.

Decision-rule margins selected per fold (on each fold's own validation split): 0.0, 0.75, 0.8, 0.9.

*Confusion matrix, raw argmax*

|  | pred false | pred true | pred null | total |
|---|---|---|---|---|
| **truth false** | 2063 | 314 | 102 | 2479 |
| **truth true** | 30 | 1277 | 174 | 1481 |
| **truth null** | 26 | 152 | 5862 | 6040 |
| **total** | 2119 | 1743 | 6138 | 10000 |

`null -> true`: 152 of 6040 truly-null examples (2.52%).

*Confusion matrix, after the decision rule*

|  | pred false | pred true | pred null | total |
|---|---|---|---|---|
| **truth false** | 2105 | 269 | 105 | 2479 |
| **truth true** | 30 | 1254 | 197 | 1481 |
| **truth null** | 29 | 123 | 5888 | 6040 |
| **total** | 2164 | 1646 | 6190 | 10000 |

`null -> true`: 123 of 6040 truly-null examples (2.04%).

### Per class, after the decision rule

| class | support | predicted | precision | recall | F1 |
|---|---|---|---|---|---|
| `false` | 2479 | 2164 | 97.3% | 84.9% | 90.7% |
| `true` | 1481 | 1646 | 76.2% | 84.7% | 80.2% |
| `null` | 6040 | 6190 | 95.1% | 97.5% | 96.3% |

### By label mode

| label mode | n | eff n | accuracy [95% CI] |
|---|---|---|---|
| false | 2479 | **124** | 84.9% [76.8%, 92.8%] |
| null_ambiguous | 3062 | **210** | 95.7% [93.1%, 97.9%] |
| null_structural | 2978 | **1** | 99.3% [99.3%, 99.3%] |
| true | 1481 | **131** | 84.7% [75.8%, 92.9%] |

### By null sub-class

| sub-class | n | eff n | null recall [95% CI] |
|---|---|---|---|
| adjacent | 590 | **40** | 93.4% [85.3%, 99.5%] |
| hedged | 617 | **42** | 92.7% [86.1%, 97.7%] |
| historical | 539 | **40** | 99.6% [99.1%, 100.0%] |
| metaphor | 674 | **44** | 93.9% [86.9%, 99.1%] |
| third_party | 642 | **44** | 99.2% [98.6%, 99.8%] |

### By fragment library

| library | n | eff n | accuracy [95% CI] |
|---|---|---|---|
| declarative_v1 | 1243 | **163** | 100.0% [100.0%, 100.0%] |
| urinary_frequency_false | 1697 | **46** | 78.0% [66.6%, 88.7%] |
| urinary_frequency_null_adjacent | 590 | **40** | 93.4% [85.3%, 99.5%] |
| urinary_frequency_null_hedged | 617 | **42** | 92.7% [86.1%, 97.7%] |
| urinary_frequency_null_historical | 539 | **40** | 99.6% [99.1%, 100.0%] |
| urinary_frequency_null_metaphor | 674 | **44** | 93.9% [86.9%, 99.1%] |
| urinary_frequency_null_thirdparty | 642 | **44** | 99.2% [98.6%, 99.8%] |
| urinary_frequency_true | 1020 | **46** | 77.7% [64.9%, 88.9%] |
| (none) | 2978 | **1** | 99.3% [99.3%, 99.3%] |

### Per-fragment errors (worst first)

Whether errors are spread thinly across many fragments or piled onto a few is the difference
between "the method is too weak" (model work) and "these specific ideas are not learnable from
the data we have" (library work, and these are the fragments to write more of). No intervals:
a fragment is one cluster, so an interval over its own examples measures nothing.

63 of 694 decisive fragments were got wrong at least once.

`arm_b_finetune@c0.0-d0.3`: 733 errors across 63 of 694 decisive fragments. Half of them fall on **10** fragments (an even spread would be 31.5); the worst ten carry 53.2% of all errors.

| fragment | library | sub-class | truth | correct | accuracy | predicted as |
|---|---|---|---|---|---|---|
| `urinary_frequency_false:63302b59` | `urinary_frequency_false` | -- | false | 0/37 | 0.0% | true 37 |
| `urinary_frequency_false:c631660d` | `urinary_frequency_false` | -- | false | 0/37 | 0.0% | null 37 |
| `urinary_frequency_true:764389c0` | `urinary_frequency_true` | -- | true | 0/37 | 0.0% | false 8, null 29 |
| `urinary_frequency_false:6bb71206` | `urinary_frequency_false` | -- | false | 0/35 | 0.0% | true 26, null 9 |
| `urinary_frequency_false:941626e8` | `urinary_frequency_false` | -- | false | 0/35 | 0.0% | null 35 |
| `urinary_frequency_false:a9a59952` | `urinary_frequency_false` | -- | false | 0/35 | 0.0% | true 35 |
| `urinary_frequency_false:f32c9e68` | `urinary_frequency_false` | -- | false | 0/33 | 0.0% | true 33 |
| `urinary_frequency_true:32cae421` | `urinary_frequency_true` | -- | true | 0/19 | 0.0% | false 19 |
| `urinary_frequency_null_metaphor:518f483f` | `urinary_frequency_null_metaphor` | metaphor | null | 0/17 | 0.0% | true 17 |
| `urinary_frequency_true:20bd4d56` | `urinary_frequency_true` | -- | true | 0/14 | 0.0% | null 14 |
| `urinary_frequency_null_hedged:ff5d90b8` | `urinary_frequency_null_hedged` | hedged | null | 0/13 | 0.0% | false 13 |
| `urinary_frequency_true:c8d32074` | `urinary_frequency_true` | -- | true | 0/13 | 0.0% | null 13 |
| `urinary_frequency_null_adjacent:d67c5d52` | `urinary_frequency_null_adjacent` | adjacent | null | 1/18 | 5.6% | true 17, null 1 |
| `urinary_frequency_true:fbca5613` | `urinary_frequency_true` | -- | true | 1/13 | 7.7% | true 1, null 12 |
| `urinary_frequency_null_adjacent:c791bce4` | `urinary_frequency_null_adjacent` | adjacent | null | 2/17 | 11.8% | true 15, null 2 |
| `urinary_frequency_true:11d16987` | `urinary_frequency_true` | -- | true | 7/49 | 14.3% | true 7, null 42 |
| `urinary_frequency_false:44543d5e` | `urinary_frequency_false` | -- | false | 6/38 | 15.8% | false 6, true 32 |
| `urinary_frequency_true:ffa90ce7` | `urinary_frequency_true` | -- | true | 6/37 | 16.2% | true 6, null 31 |
| `urinary_frequency_null_metaphor:5c1e4a7d` | `urinary_frequency_null_metaphor` | metaphor | null | 4/19 | 21.1% | true 15, null 4 |
| `urinary_frequency_true:5008b431` | `urinary_frequency_true` | -- | true | 7/24 | 29.2% | true 7, null 17 |
| `urinary_frequency_null_hedged:fc9770b8` | `urinary_frequency_null_hedged` | hedged | null | 5/17 | 29.4% | true 12, null 5 |
| `urinary_frequency_false:a15017c2` | `urinary_frequency_false` | -- | false | 44/103 | 42.7% | false 44, true 57, null 2 |
| `urinary_frequency_true:f5216cf2` | `urinary_frequency_true` | -- | true | 9/20 | 45.0% | true 9, null 11 |
| `urinary_frequency_false:d293ee8c` | `urinary_frequency_false` | -- | false | 39/79 | 49.4% | false 39, true 40 |
| `urinary_frequency_null_hedged:5f612dfb` | `urinary_frequency_null_hedged` | hedged | null | 6/11 | 54.5% | true 5, null 6 |
| `urinary_frequency_false:8239d5f6` | `urinary_frequency_false` | -- | false | 12/21 | 57.1% | false 12, true 6, null 3 |
| `urinary_frequency_true:f9c03b9b` | `urinary_frequency_true` | -- | true | 9/15 | 60.0% | true 9, null 6 |
| `urinary_frequency_true:32946372` | `urinary_frequency_true` | -- | true | 13/21 | 61.9% | false 3, true 13, null 5 |
| `urinary_frequency_null_hedged:b9718c37` | `urinary_frequency_null_hedged` | hedged | null | 10/16 | 62.5% | true 6, null 10 |
| `urinary_frequency_true:fecb0185` | `urinary_frequency_true` | -- | true | 12/18 | 66.7% | true 12, null 6 |
| `urinary_frequency_true:76e4e79f` | `urinary_frequency_true` | -- | true | 11/16 | 68.8% | true 11, null 5 |
| `urinary_frequency_null_adjacent:d4674700` | `urinary_frequency_null_adjacent` | adjacent | null | 11/15 | 73.3% | true 4, null 11 |
| `urinary_frequency_false:ec8210fb` | `urinary_frequency_false` | -- | false | 19/25 | 76.0% | false 19, null 6 |
| `urinary_frequency_false:f78f9d25` | `urinary_frequency_false` | -- | false | 27/35 | 77.1% | false 27, null 8 |
| `urinary_frequency_null_metaphor:280ac13b` | `urinary_frequency_null_metaphor` | metaphor | null | 7/9 | 77.8% | false 2, null 7 |
| `urinary_frequency_false:a61aba66` | `urinary_frequency_false` | -- | false | 18/22 | 81.8% | false 18, null 4 |
| `urinary_frequency_null_metaphor:90af7fc6` | `urinary_frequency_null_metaphor` | metaphor | null | 10/12 | 83.3% | true 2, null 10 |
| `urinary_frequency_null_hedged:bdf7d8ff` | `urinary_frequency_null_hedged` | hedged | null | 12/14 | 85.7% | true 2, null 12 |
| `urinary_frequency_true:c87f1579` | `urinary_frequency_true` | -- | true | 12/14 | 85.7% | true 12, null 2 |
| `urinary_frequency_true:95d4e96a` | `urinary_frequency_true` | -- | true | 13/15 | 86.7% | true 13, null 2 |

*23 further fragments with at least one error are in the JSON sidecar; every fragment is there regardless of score.*

## `arm_b_finetune@c0.5-d0.0`

`roberta-base` with **every layer unfrozen**, mean-pooled, with the same `Linear(768, 3)` head -- 110M trainable parameters against Arm A's 2,307. Three epochs at batch 32, learning rate 2e-5, 10% linear warmup, AdamW, fp32. No gradient checkpointing, no 8-bit optimiser, no LoRA, no gradient accumulation: the full model fits in 12GB with room to spare, so anything that reads like a compute compromise would be a mistake rather than a saving. This is the arm that separates "the fragment libraries are the bottleneck" from "the method is too weak": if a fully fine-tuned encoder still cannot read third-party attribution, tense or metaphor, the limit is in the ideas the libraries contain and the fix is library work, not model work.

Decision-rule margins selected per fold (on each fold's own validation split): 0.0, 0.7, 0.9.

*Confusion matrix, raw argmax*

|  | pred false | pred true | pred null | total |
|---|---|---|---|---|
| **truth false** | 1958 | 277 | 244 | 2479 |
| **truth true** | 86 | 1009 | 386 | 1481 |
| **truth null** | 46 | 162 | 5832 | 6040 |
| **total** | 2090 | 1448 | 6462 | 10000 |

`null -> true`: 162 of 6040 truly-null examples (2.68%).

*Confusion matrix, after the decision rule*

|  | pred false | pred true | pred null | total |
|---|---|---|---|---|
| **truth false** | 1994 | 240 | 245 | 2479 |
| **truth true** | 93 | 965 | 423 | 1481 |
| **truth null** | 47 | 116 | 5877 | 6040 |
| **total** | 2134 | 1321 | 6545 | 10000 |

`null -> true`: 116 of 6040 truly-null examples (1.92%).

### Per class, after the decision rule

| class | support | predicted | precision | recall | F1 |
|---|---|---|---|---|---|
| `false` | 2479 | 2134 | 93.4% | 80.4% | 86.5% |
| `true` | 1481 | 1321 | 73.1% | 65.2% | 68.9% |
| `null` | 6040 | 6545 | 89.8% | 97.3% | 93.4% |

### By label mode

| label mode | n | eff n | accuracy [95% CI] |
|---|---|---|---|
| false | 2479 | **46** | 80.4% [69.4%, 89.5%] |
| null_ambiguous | 3062 | **210** | 95.4% [92.6%, 97.6%] |
| null_structural | 2978 | **1** | 99.3% [99.3%, 99.3%] |
| true | 1481 | **46** | 65.2% [51.6%, 77.2%] |

### By null sub-class

| sub-class | n | eff n | null recall [95% CI] |
|---|---|---|---|
| adjacent | 587 | **40** | 96.9% [91.3%, 100.0%] |
| hedged | 623 | **42** | 87.6% [78.4%, 95.1%] |
| historical | 544 | **40** | 98.0% [93.7%, 100.0%] |
| metaphor | 670 | **44** | 96.4% [90.0%, 100.0%] |
| third_party | 638 | **44** | 98.1% [95.8%, 100.0%] |

### By fragment library

| library | n | eff n | accuracy [95% CI] |
|---|---|---|---|
| urinary_frequency_false | 2479 | **46** | 80.4% [69.4%, 89.5%] |
| urinary_frequency_null_adjacent | 587 | **40** | 96.9% [91.3%, 100.0%] |
| urinary_frequency_null_hedged | 623 | **42** | 87.6% [78.4%, 95.1%] |
| urinary_frequency_null_historical | 544 | **40** | 98.0% [93.7%, 100.0%] |
| urinary_frequency_null_metaphor | 670 | **44** | 96.4% [90.0%, 100.0%] |
| urinary_frequency_null_thirdparty | 638 | **44** | 98.1% [95.8%, 100.0%] |
| urinary_frequency_true | 1481 | **46** | 65.2% [51.6%, 77.2%] |
| (none) | 2978 | **1** | 99.3% [99.3%, 99.3%] |

### Per-fragment errors (worst first)

Whether errors are spread thinly across many fragments or piled onto a few is the difference
between "the method is too weak" (model work) and "these specific ideas are not learnable from
the data we have" (library work, and these are the fragments to write more of). No intervals:
a fragment is one cluster, so an interval over its own examples measures nothing.

65 of 302 decisive fragments were got wrong at least once.

`arm_b_finetune@c0.5-d0.0`: 1143 errors across 65 of 302 decisive fragments. Half of them fall on **13** fragments (an even spread would be 32.5); the worst ten carry 41.1% of all errors.

| fragment | library | sub-class | truth | correct | accuracy | predicted as |
|---|---|---|---|---|---|---|
| `urinary_frequency_true:11d16987` | `urinary_frequency_true` | -- | true | 0/70 | 0.0% | null 70 |
| `urinary_frequency_false:c631660d` | `urinary_frequency_false` | -- | false | 0/51 | 0.0% | null 51 |
| `urinary_frequency_false:63302b59` | `urinary_frequency_false` | -- | false | 0/50 | 0.0% | true 50 |
| `urinary_frequency_false:941626e8` | `urinary_frequency_false` | -- | false | 0/47 | 0.0% | null 47 |
| `urinary_frequency_false:fc6a56d2` | `urinary_frequency_false` | -- | false | 0/45 | 0.0% | true 45 |
| `urinary_frequency_true:2c452329` | `urinary_frequency_true` | -- | true | 0/44 | 0.0% | false 34, null 10 |
| `urinary_frequency_false:f32c9e68` | `urinary_frequency_false` | -- | false | 0/43 | 0.0% | true 43 |
| `urinary_frequency_false:6bb71206` | `urinary_frequency_false` | -- | false | 0/42 | 0.0% | null 42 |
| `urinary_frequency_false:a61aba66` | `urinary_frequency_false` | -- | false | 0/40 | 0.0% | null 40 |
| `urinary_frequency_true:617cfdc3` | `urinary_frequency_true` | -- | true | 0/34 | 0.0% | null 34 |
| `urinary_frequency_true:fbca5613` | `urinary_frequency_true` | -- | true | 0/32 | 0.0% | null 32 |
| `urinary_frequency_true:e746abc0` | `urinary_frequency_true` | -- | true | 0/30 | 0.0% | null 30 |
| `urinary_frequency_true:32cae421` | `urinary_frequency_true` | -- | true | 0/21 | 0.0% | false 21 |
| `urinary_frequency_true:c87f1579` | `urinary_frequency_true` | -- | true | 0/21 | 0.0% | null 21 |
| `urinary_frequency_true:f5216cf2` | `urinary_frequency_true` | -- | true | 0/20 | 0.0% | null 20 |
| `urinary_frequency_null_metaphor:518f483f` | `urinary_frequency_null_metaphor` | metaphor | null | 0/18 | 0.0% | false 18 |
| `urinary_frequency_true:20bd4d56` | `urinary_frequency_true` | -- | true | 0/18 | 0.0% | null 18 |
| `urinary_frequency_null_adjacent:15320912` | `urinary_frequency_null_adjacent` | adjacent | null | 0/16 | 0.0% | true 16 |
| `urinary_frequency_null_hedged:fe13847c` | `urinary_frequency_null_hedged` | hedged | null | 0/16 | 0.0% | false 2, true 14 |
| `urinary_frequency_true:52b41248` | `urinary_frequency_true` | -- | true | 0/16 | 0.0% | null 16 |
| `urinary_frequency_true:c8d32074` | `urinary_frequency_true` | -- | true | 0/14 | 0.0% | null 14 |
| `urinary_frequency_null_hedged:ff5d90b8` | `urinary_frequency_null_hedged` | hedged | null | 0/13 | 0.0% | false 13 |
| `urinary_frequency_true:5ef90c41` | `urinary_frequency_true` | -- | true | 0/13 | 0.0% | null 13 |
| `urinary_frequency_null_hedged:5f612dfb` | `urinary_frequency_null_hedged` | hedged | null | 0/11 | 0.0% | true 11 |
| `urinary_frequency_false:b66fa498` | `urinary_frequency_false` | -- | false | 1/29 | 3.4% | false 1, true 20, null 8 |
| `urinary_frequency_true:be3d7218` | `urinary_frequency_true` | -- | true | 2/21 | 9.5% | true 2, null 19 |
| `urinary_frequency_false:7be58a30` | `urinary_frequency_false` | -- | false | 5/31 | 16.1% | false 5, null 26 |
| `urinary_frequency_true:57632816` | `urinary_frequency_true` | -- | true | 4/22 | 18.2% | true 4, null 18 |
| `urinary_frequency_false:ec8210fb` | `urinary_frequency_false` | -- | false | 6/30 | 20.0% | false 6, null 24 |
| `urinary_frequency_null_hedged:bc056f4e` | `urinary_frequency_null_hedged` | hedged | null | 4/19 | 21.1% | true 15, null 4 |
| `urinary_frequency_true:35a67edf` | `urinary_frequency_true` | -- | true | 8/33 | 24.2% | true 8, null 25 |
| `urinary_frequency_true:32946372` | `urinary_frequency_true` | -- | true | 9/28 | 32.1% | false 19, true 9 |
| `urinary_frequency_null_historical:c3a6ffdb` | `urinary_frequency_null_historical` | historical | null | 5/15 | 33.3% | true 10, null 5 |
| `urinary_frequency_true:764389c0` | `urinary_frequency_true` | -- | true | 23/60 | 38.3% | false 3, true 23, null 34 |
| `urinary_frequency_true:f9c03b9b` | `urinary_frequency_true` | -- | true | 12/24 | 50.0% | true 12, null 12 |
| `urinary_frequency_null_hedged:61fe8d58` | `urinary_frequency_null_hedged` | hedged | null | 8/15 | 53.3% | true 7, null 8 |
| `urinary_frequency_true:1e5b372c` | `urinary_frequency_true` | -- | true | 22/39 | 56.4% | true 22, null 17 |
| `urinary_frequency_false:a9a59952` | `urinary_frequency_false` | -- | false | 40/65 | 61.5% | false 40, true 25 |
| `urinary_frequency_null_metaphor:92dfbbce` | `urinary_frequency_null_metaphor` | metaphor | null | 8/13 | 61.5% | true 5, null 8 |
| `urinary_frequency_true:fecb0185` | `urinary_frequency_true` | -- | true | 18/28 | 64.3% | true 18, null 10 |

*25 further fragments with at least one error are in the JSON sidecar; every fragment is there regardless of score.*

## `arm_b_finetune@c0.5-d0.3`

`roberta-base` with **every layer unfrozen**, mean-pooled, with the same `Linear(768, 3)` head -- 110M trainable parameters against Arm A's 2,307. Three epochs at batch 32, learning rate 2e-5, 10% linear warmup, AdamW, fp32. No gradient checkpointing, no 8-bit optimiser, no LoRA, no gradient accumulation: the full model fits in 12GB with room to spare, so anything that reads like a compute compromise would be a mistake rather than a saving. This is the arm that separates "the fragment libraries are the bottleneck" from "the method is too weak": if a fully fine-tuned encoder still cannot read third-party attribution, tense or metaphor, the limit is in the ideas the libraries contain and the fix is library work, not model work.

Decision-rule margins selected per fold (on each fold's own validation split): 0.0, 0.2, 0.5, 0.85, 0.9.

*Confusion matrix, raw argmax*

|  | pred false | pred true | pred null | total |
|---|---|---|---|---|
| **truth false** | 2032 | 296 | 151 | 2479 |
| **truth true** | 38 | 1169 | 274 | 1481 |
| **truth null** | 18 | 131 | 5891 | 6040 |
| **total** | 2088 | 1596 | 6316 | 10000 |

`null -> true`: 131 of 6040 truly-null examples (2.17%).

*Confusion matrix, after the decision rule*

|  | pred false | pred true | pred null | total |
|---|---|---|---|---|
| **truth false** | 2047 | 277 | 155 | 2479 |
| **truth true** | 41 | 1140 | 300 | 1481 |
| **truth null** | 18 | 122 | 5900 | 6040 |
| **total** | 2106 | 1539 | 6355 | 10000 |

`null -> true`: 122 of 6040 truly-null examples (2.02%).

### Per class, after the decision rule

| class | support | predicted | precision | recall | F1 |
|---|---|---|---|---|---|
| `false` | 2479 | 2106 | 97.2% | 82.6% | 89.3% |
| `true` | 1481 | 1539 | 74.1% | 77.0% | 75.5% |
| `null` | 6040 | 6355 | 92.8% | 97.7% | 95.2% |

### By label mode

| label mode | n | eff n | accuracy [95% CI] |
|---|---|---|---|
| false | 2479 | **124** | 82.6% [74.5%, 90.2%] |
| null_ambiguous | 3062 | **210** | 95.8% [93.1%, 98.0%] |
| null_structural | 2978 | **1** | 99.6% [99.6%, 99.6%] |
| true | 1481 | **131** | 77.0% [67.0%, 86.3%] |

### By null sub-class

| sub-class | n | eff n | null recall [95% CI] |
|---|---|---|---|
| adjacent | 587 | **40** | 97.3% [92.5%, 100.0%] |
| hedged | 623 | **42** | 90.9% [83.2%, 97.1%] |
| historical | 544 | **40** | 98.5% [95.7%, 100.0%] |
| metaphor | 670 | **44** | 93.3% [85.1%, 100.0%] |
| third_party | 638 | **44** | 99.5% [98.8%, 100.0%] |

### By fragment library

| library | n | eff n | accuracy [95% CI] |
|---|---|---|---|
| declarative_v1 | 1217 | **163** | 100.0% [100.0%, 100.0%] |
| urinary_frequency_false | 1719 | **46** | 74.9% [62.8%, 85.2%] |
| urinary_frequency_null_adjacent | 587 | **40** | 97.3% [92.5%, 100.0%] |
| urinary_frequency_null_hedged | 623 | **42** | 90.9% [83.2%, 97.1%] |
| urinary_frequency_null_historical | 544 | **40** | 98.5% [95.7%, 100.0%] |
| urinary_frequency_null_metaphor | 670 | **44** | 93.3% [85.1%, 100.0%] |
| urinary_frequency_null_thirdparty | 638 | **44** | 99.5% [98.8%, 100.0%] |
| urinary_frequency_true | 1024 | **46** | 66.7% [52.1%, 79.7%] |
| (none) | 2978 | **1** | 99.6% [99.6%, 99.6%] |

### Per-fragment errors (worst first)

Whether errors are spread thinly across many fragments or piled onto a few is the difference
between "the method is too weak" (model work) and "these specific ideas are not learnable from
the data we have" (library work, and these are the fragments to write more of). No intervals:
a fragment is one cluster, so an interval over its own examples measures nothing.

56 of 694 decisive fragments were got wrong at least once.

`arm_b_finetune@c0.5-d0.3`: 902 errors across 56 of 694 decisive fragments. Half of them fall on **13** fragments (an even spread would be 28.0); the worst ten carry 42.4% of all errors.

| fragment | library | sub-class | truth | correct | accuracy | predicted as |
|---|---|---|---|---|---|---|
| `urinary_frequency_true:11d16987` | `urinary_frequency_true` | -- | true | 0/48 | 0.0% | null 48 |
| `urinary_frequency_false:63302b59` | `urinary_frequency_false` | -- | false | 0/39 | 0.0% | true 39 |
| `urinary_frequency_true:ffa90ce7` | `urinary_frequency_true` | -- | true | 0/39 | 0.0% | null 39 |
| `urinary_frequency_false:941626e8` | `urinary_frequency_false` | -- | false | 0/35 | 0.0% | null 35 |
| `urinary_frequency_false:c631660d` | `urinary_frequency_false` | -- | false | 0/35 | 0.0% | null 35 |
| `urinary_frequency_false:f32c9e68` | `urinary_frequency_false` | -- | false | 0/33 | 0.0% | true 33 |
| `urinary_frequency_false:a61aba66` | `urinary_frequency_false` | -- | false | 0/22 | 0.0% | null 22 |
| `urinary_frequency_null_metaphor:5c1e4a7d` | `urinary_frequency_null_metaphor` | metaphor | null | 0/20 | 0.0% | true 20 |
| `urinary_frequency_true:32cae421` | `urinary_frequency_true` | -- | true | 0/19 | 0.0% | false 19 |
| `urinary_frequency_true:fecb0185` | `urinary_frequency_true` | -- | true | 0/17 | 0.0% | null 17 |
| `urinary_frequency_true:e746abc0` | `urinary_frequency_true` | -- | true | 0/15 | 0.0% | null 15 |
| `urinary_frequency_true:f9c03b9b` | `urinary_frequency_true` | -- | true | 0/15 | 0.0% | null 15 |
| `urinary_frequency_true:20bd4d56` | `urinary_frequency_true` | -- | true | 0/14 | 0.0% | null 14 |
| `urinary_frequency_null_hedged:ff5d90b8` | `urinary_frequency_null_hedged` | hedged | null | 0/13 | 0.0% | false 13 |
| `urinary_frequency_true:c8d32074` | `urinary_frequency_true` | -- | true | 0/13 | 0.0% | null 13 |
| `urinary_frequency_null_hedged:5f612dfb` | `urinary_frequency_null_hedged` | hedged | null | 0/11 | 0.0% | true 11 |
| `urinary_frequency_false:fc6a56d2` | `urinary_frequency_false` | -- | false | 1/39 | 2.6% | false 1, true 37, null 1 |
| `urinary_frequency_false:a9a59952` | `urinary_frequency_false` | -- | false | 1/38 | 2.6% | false 1, true 37 |
| `urinary_frequency_false:6bb71206` | `urinary_frequency_false` | -- | false | 1/32 | 3.1% | false 1, true 15, null 16 |
| `urinary_frequency_true:2c452329` | `urinary_frequency_true` | -- | true | 1/27 | 3.7% | false 20, true 1, null 6 |
| `urinary_frequency_false:7be58a30` | `urinary_frequency_false` | -- | false | 1/23 | 4.3% | false 1, null 22 |
| `urinary_frequency_true:f5216cf2` | `urinary_frequency_true` | -- | true | 1/21 | 4.8% | true 1, null 20 |
| `urinary_frequency_false:44543d5e` | `urinary_frequency_false` | -- | false | 2/38 | 5.3% | false 2, true 36 |
| `urinary_frequency_null_metaphor:518f483f` | `urinary_frequency_null_metaphor` | metaphor | null | 1/18 | 5.6% | true 17, null 1 |
| `urinary_frequency_false:b66fa498` | `urinary_frequency_false` | -- | false | 2/20 | 10.0% | false 2, true 18 |
| `urinary_frequency_true:52b41248` | `urinary_frequency_true` | -- | true | 2/16 | 12.5% | true 2, null 14 |
| `urinary_frequency_null_historical:60a6e077` | `urinary_frequency_null_historical` | historical | null | 1/8 | 12.5% | true 7, null 1 |
| `urinary_frequency_true:fbca5613` | `urinary_frequency_true` | -- | true | 2/13 | 15.4% | true 2, null 11 |
| `urinary_frequency_true:764389c0` | `urinary_frequency_true` | -- | true | 7/38 | 18.4% | true 7, null 31 |
| `urinary_frequency_null_hedged:fe13847c` | `urinary_frequency_null_hedged` | hedged | null | 3/16 | 18.8% | true 13, null 3 |
| `urinary_frequency_false:ec8210fb` | `urinary_frequency_false` | -- | false | 6/24 | 25.0% | false 6, null 18 |
| `urinary_frequency_true:5ef90c41` | `urinary_frequency_true` | -- | true | 3/12 | 25.0% | true 3, null 9 |
| `urinary_frequency_null_adjacent:c791bce4` | `urinary_frequency_null_adjacent` | adjacent | null | 5/18 | 27.8% | true 13, null 5 |
| `urinary_frequency_true:617cfdc3` | `urinary_frequency_true` | -- | true | 6/20 | 30.0% | true 6, null 14 |
| `urinary_frequency_null_hedged:8d4f425f` | `urinary_frequency_null_hedged` | hedged | null | 10/20 | 50.0% | true 10, null 10 |
| `urinary_frequency_null_metaphor:eb9e9615` | `urinary_frequency_null_metaphor` | metaphor | null | 8/16 | 50.0% | false 1, true 7, null 8 |
| `urinary_frequency_false:8239d5f6` | `urinary_frequency_false` | -- | false | 11/21 | 52.4% | false 11, true 10 |
| `urinary_frequency_true:57632816` | `urinary_frequency_true` | -- | true | 6/11 | 54.5% | true 6, null 5 |
| `urinary_frequency_true:c87f1579` | `urinary_frequency_true` | -- | true | 8/14 | 57.1% | true 8, null 6 |
| `urinary_frequency_true:5008b431` | `urinary_frequency_true` | -- | true | 14/24 | 58.3% | true 14, null 10 |

*16 further fragments with at least one error are in the JSON sidecar; every fragment is there regardless of score.*

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
| 0 | 10000 | 2000 | 2000 | 0.0 | 71.9% | 71.9% | 55.7% | 3.47% |
| 1 | 10000 | 2000 | 2000 | 0.0 | 70.2% | 70.2% | 50.5% | 1.25% |
| 2 | 10000 | 2000 | 2000 | 0.0 | 67.4% | 67.4% | 44.2% | 1.24% |
| 3 | 10000 | 2000 | 2000 | 0.25 | 76.1% | 75.6% | 52.6% | 0.66% |
| 4 | 10000 | 2000 | 2000 | 0.0 | 72.8% | 72.8% | 56.2% | 3.98% |

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
| 4 | 10000 | 2000 | 2000 | 0.0 | 60.2% | 60.2% | 25.1% | 0.00% |

### `arm_b_finetune@c0.0-d0.0`

| fold | train n | val n | test n | margin | acc (raw) | acc (ruled) | macro-F1 | null->true |
|---|---|---|---|---|---|---|---|---|
| 0 | 10000 | 2000 | 2000 | 0.15 | 96.0% | 96.0% | 93.8% | 2.48% |
| 1 | 10000 | 2000 | 2000 | 0.05 | 82.7% | 82.7% | 73.5% | 0.42% |
| 2 | 10000 | 2000 | 2000 | 0.0 | 85.5% | 85.5% | 77.8% | 2.48% |
| 3 | 10000 | 2000 | 2000 | 0.9 | 94.5% | 94.0% | 90.1% | 0.49% |
| 4 | 10000 | 2000 | 2000 | 0.7 | 83.5% | 83.8% | 76.4% | 3.57% |

### `arm_b_finetune@c0.0-d0.3`

| fold | train n | val n | test n | margin | acc (raw) | acc (ruled) | macro-F1 | null->true |
|---|---|---|---|---|---|---|---|---|
| 0 | 10000 | 2000 | 2000 | 0.8 | 97.0% | 97.2% | 95.6% | 1.82% |
| 1 | 10000 | 2000 | 2000 | 0.9 | 85.6% | 85.2% | 78.1% | 0.67% |
| 2 | 10000 | 2000 | 2000 | 0.0 | 93.0% | 93.0% | 90.5% | 3.64% |
| 3 | 10000 | 2000 | 2000 | 0.9 | 95.5% | 95.8% | 93.1% | 0.41% |
| 4 | 10000 | 2000 | 2000 | 0.75 | 89.1% | 91.3% | 87.4% | 3.65% |

### `arm_b_finetune@c0.5-d0.0`

| fold | train n | val n | test n | margin | acc (raw) | acc (ruled) | macro-F1 | null->true |
|---|---|---|---|---|---|---|---|---|
| 0 | 10000 | 2000 | 2000 | 0.9 | 94.5% | 95.0% | 91.7% | 0.66% |
| 1 | 10000 | 2000 | 2000 | 0.9 | 78.6% | 78.8% | 69.3% | 3.16% |
| 2 | 10000 | 2000 | 2000 | 0.0 | 86.1% | 86.1% | 79.8% | 0.08% |
| 3 | 10000 | 2000 | 2000 | 0.9 | 91.1% | 91.0% | 82.4% | 0.00% |
| 4 | 10000 | 2000 | 2000 | 0.7 | 89.8% | 91.0% | 87.7% | 5.72% |

### `arm_b_finetune@c0.5-d0.3`

| fold | train n | val n | test n | margin | acc (raw) | acc (ruled) | macro-F1 | null->true |
|---|---|---|---|---|---|---|---|---|
| 0 | 10000 | 2000 | 2000 | 0.85 | 96.1% | 96.1% | 93.5% | 0.99% |
| 1 | 10000 | 2000 | 2000 | 0.2 | 82.8% | 82.8% | 74.6% | 1.25% |
| 2 | 10000 | 2000 | 2000 | 0.0 | 88.1% | 88.1% | 84.2% | 3.31% |
| 3 | 10000 | 2000 | 2000 | 0.9 | 94.5% | 93.6% | 88.7% | 0.00% |
| 4 | 10000 | 2000 | 2000 | 0.5 | 93.0% | 93.7% | 91.0% | 4.56% |

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

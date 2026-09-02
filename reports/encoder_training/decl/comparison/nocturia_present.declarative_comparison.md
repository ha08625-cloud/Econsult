# Encoder training: evaluation report

*Generated 2026-09-02T15:58:38+00:00.*

|  |  |
|---|---|
| signal | `nocturia_present` |
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
| selected epochs | `c0.0-d0.0 1, 1, 3, 2, 1, c0.0-d0.3 1, 1, 1, 3, 2, c0.5-d0.0 1, 1, 3, 2, 3, c0.5-d0.3 3, 3, 1, 1, 1` |
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
| cluster tag coverage | `1 of 8 libraries carry cluster markers; 351 of 788 fragments are in libraries with none` |
| bootstrap | `2000 resamples over clusters, alpha=0.05, seed=0` |

**arms**

* **c0.0-d0.0** (`data/synthetic/generated/decl/c0.0-d0.0`): 10000 examples per epoch, **10000** labelled positions for `nocturia_present`
* **c0.0-d0.3** (`data/synthetic/generated/decl/c0.0-d0.3`): 10000 examples per epoch, **10000** labelled positions for `nocturia_present`
* **c0.5-d0.0** (`data/synthetic/generated/decl/c0.5-d0.0`): 10000 examples per epoch, **10000** labelled positions for `nocturia_present`
* **c0.5-d0.3** (`data/synthetic/generated/decl/c0.5-d0.3`): 10000 examples per epoch, **10000** labelled positions for `nocturia_present`

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
> Untagged: `nocturia_false`, `nocturia_null_attribution`, `nocturia_null_hedged`, `nocturia_null_historical`, `nocturia_null_metaphor`, `nocturia_null_thirdparty`, `nocturia_true`.

Tagging cannot inflate a number -- `[c01]` siblings are forced into one cluster and one
split, so it only ever *reduces* `eff n`, correctly, by stopping the same idea being
counted twice. The asymmetry is what makes cross-signal comparison unsafe: a fully
tagged signal is penalised for being honest and an untagged one is flattered by default,
so a ranking across signals is partly an artefact of this column.

| library | fragments | tagged | coverage |
|---|---|---|---|
| `nocturia_false` | 54 | 0 | 0.0% |
| `nocturia_null_attribution` | 51 | 0 | 0.0% |
| `nocturia_null_hedged` | 47 | 0 | 0.0% |
| `nocturia_null_historical` | 46 | 0 | 0.0% |
| `nocturia_null_metaphor` | 52 | 0 | 0.0% |
| `nocturia_null_thirdparty` | 47 | 0 | 0.0% |
| `nocturia_true` | 54 | 0 | 0.0% |
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
| `majority_class` | baseline | 7022 | **351** | 43.6% [38.0%, 49.8%] | 20.2% [18.4%, 22.2%] | 60.4% | 60.4% +/- 0.2% |
| `length_only` | baseline | 7022 | **351** | 43.6% [38.0%, 49.8%] | 20.2% [18.4%, 22.2%] | 60.4% | 60.4% +/- 0.2% |
| `tfidf_logreg` | baseline | 7022 | **351** | 65.1% [59.7%, 70.5%] | 60.9% [54.9%, 66.7%] | 75.4% | 75.4% +/- 3.1% |
| `length_only__shuffled` | negative control | 7022 | **351** | 43.6% [38.0%, 49.8%] | 20.2% [18.4%, 22.2%] | 60.4% | 60.4% +/- 0.2% |
| `tfidf_logreg__shuffled` | negative control | 7022 | **351** | 43.6% [38.0%, 49.7%] | 20.2% [18.4%, 22.2%] | 60.4% | 60.4% +/- 0.3% |
| `arm_b_finetune@c0.0-d0.0` | finetune | 7022 | **351** | 83.7% [79.4%, 87.9%] | 82.4% [77.6%, 86.7%] | 88.3% | 88.3% +/- 3.8% |
| `arm_b_finetune@c0.0-d0.3` | finetune | 7022 | **511** | 88.5% [85.2%, 91.5%] | 87.3% [83.7%, 90.6%] | 91.8% | 91.8% +/- 2.2% |
| `arm_b_finetune@c0.5-d0.0` | finetune | 7022 | **351** | 82.2% [77.3%, 86.8%] | 81.5% [76.3%, 86.1%] | 87.4% | 87.4% +/- 7.0% |
| `arm_b_finetune@c0.5-d0.3` | finetune | 7022 | **511** | 86.1% [82.2%, 89.8%] | 85.6% [81.4%, 89.3%] | 90.2% | 90.3% +/- 4.2% |

### Null sub-class recall, pooled

The table the whole exercise exists for: how often each hard `null` sub-class is correctly
left as `null`. `eff n` here is the sub-class's entire library, which a single split cannot reach.

**Never read this table on its own.** Every example in these slices is truly `null`, so a model
that always answers `null` scores 100% across the row -- as `majority_class` below does. High
null recall is only a finding when the `true` and `false` recalls in the per-class tables are
high too.

| model | adjacent | attribution | hedged | historical | metaphor | third_party |
|---|---|---|---|---|---|---|
| `majority_class` | -- | 100.0% [100.0%, 100.0%] (eff n 51) | 100.0% [100.0%, 100.0%] (eff n 47) | 100.0% [100.0%, 100.0%] (eff n 46) | 100.0% [100.0%, 100.0%] (eff n 52) | 100.0% [100.0%, 100.0%] (eff n 47) |
| `length_only` | -- | 100.0% [100.0%, 100.0%] (eff n 51) | 100.0% [100.0%, 100.0%] (eff n 47) | 100.0% [100.0%, 100.0%] (eff n 46) | 100.0% [100.0%, 100.0%] (eff n 52) | 100.0% [100.0%, 100.0%] (eff n 47) |
| `tfidf_logreg` | -- | 83.7% [73.9%, 92.2%] (eff n 51) | 97.1% [95.0%, 98.9%] (eff n 47) | 90.4% [83.5%, 96.1%] (eff n 46) | 93.1% [86.4%, 97.8%] (eff n 52) | 86.7% [77.7%, 93.8%] (eff n 47) |
| `length_only__shuffled` | -- | 100.0% [100.0%, 100.0%] (eff n 51) | 100.0% [100.0%, 100.0%] (eff n 47) | 100.0% [100.0%, 100.0%] (eff n 46) | 100.0% [100.0%, 100.0%] (eff n 52) | 100.0% [100.0%, 100.0%] (eff n 47) |
| `tfidf_logreg__shuffled` | -- | 99.7% [99.0%, 100.0%] (eff n 51) | 100.0% [100.0%, 100.0%] (eff n 47) | 100.0% [100.0%, 100.0%] (eff n 46) | 99.9% [99.5%, 100.0%] (eff n 52) | 100.0% [100.0%, 100.0%] (eff n 47) |
| `arm_b_finetune@c0.0-d0.0` | -- | 85.5% [74.8%, 93.7%] (eff n 51) | 86.1% [77.4%, 93.4%] (eff n 47) | 93.3% [85.5%, 99.5%] (eff n 46) | 93.9% [88.1%, 98.3%] (eff n 52) | 89.3% [79.4%, 97.4%] (eff n 47) |
| `arm_b_finetune@c0.0-d0.3` | -- | 88.1% [78.1%, 96.1%] (eff n 51) | 85.7% [76.9%, 93.3%] (eff n 47) | 89.5% [80.3%, 96.7%] (eff n 46) | 93.9% [87.7%, 98.8%] (eff n 52) | 92.7% [83.4%, 99.5%] (eff n 47) |
| `arm_b_finetune@c0.5-d0.0` | -- | 88.4% [78.6%, 96.2%] (eff n 51) | 86.9% [76.9%, 94.7%] (eff n 47) | 90.3% [81.3%, 97.1%] (eff n 46) | 96.2% [90.9%, 99.9%] (eff n 52) | 89.8% [80.3%, 97.6%] (eff n 47) |
| `arm_b_finetune@c0.5-d0.3` | -- | 86.6% [76.8%, 94.9%] (eff n 51) | 86.5% [76.6%, 94.5%] (eff n 47) | 92.8% [85.5%, 98.6%] (eff n 46) | 97.8% [94.0%, 99.9%] (eff n 52) | 93.9% [86.7%, 99.6%] (eff n 47) |

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

Not scored, because no head exists for them: `dysuria_present`, `urinary_frequency_present`, `fever_present`, `flank_pain_present`, `haematuria_present`, `recent_uti_present`.

### `null -> true` on real text -- the headline

How often each model answers `true` about a signal the submission never mentioned, as
the mean across folds of that fold's own rate. Every other number in this section is
read against this one: a model can post a respectable overall figure here purely by
answering `null` everywhere, and it can post a respectable *decisive* figure while still
inventing symptoms into most of the submissions that never raised them.

| signal | null support | `arm_b_finetune@c0.0-d0.0` | `arm_b_finetune@c0.0-d0.3` | `arm_b_finetune@c0.5-d0.0` | `arm_b_finetune@c0.5-d0.3` |
|---|---|---|---|---|---|
| `nocturia_present` | 58 | 0.7% | 14.1% | 0.3% | 0.3% |

### `arm_b_finetune@c0.0-d0.0`

Recombination test slice: **n 7022**, **eff n 351** clusters, accuracy 83.7% [79.4%, 87.9%]. Holdout: **n 67** submissions, one observation each, scored by 5 fold models at margins 0.0, 0.0, 0.25, 0.2, 0.5. The two `n`s are printed together because they are not the same kind of number and the second is far the smaller.

| signal | true/false/null | omitted | decisive n | decisive acc (mean +/- sd) | worst-case half-width | all n | all acc (mean +/- sd) | null recall |
|---|---|---|---|---|---|---|---|---|
| `nocturia_present` | 9/0/58 | 0 | 9 | 44.4% +/- 20.8% | +/-32.7% | 67 | 91.0% +/- 4.2% | 98.3% +/- 2.4% |

* `nocturia_present`: no `false` examples in this set, so its number is very nearly a recall-only measurement: nothing here tests whether an explicit denial is read correctly, which was the largest error family in the synthetic evaluation.

`null -> true` on real text, per fold: `nocturia_present` 0, 2, 0, 0, 0 of 58. This is the cell that invents a symptom into a patient's pre-filled form, counted here on submissions rather than on recombinations.

### `arm_b_finetune@c0.0-d0.3`

Recombination test slice: **n 7022**, **eff n 511** clusters, accuracy 88.5% [85.2%, 91.5%]. Holdout: **n 67** submissions, one observation each, scored by 5 fold models at margins 0.55, 0.85, 0.0, 0.0, 0.15. The two `n`s are printed together because they are not the same kind of number and the second is far the smaller.

| signal | true/false/null | omitted | decisive n | decisive acc (mean +/- sd) | worst-case half-width | all n | all acc (mean +/- sd) | null recall |
|---|---|---|---|---|---|---|---|---|
| `nocturia_present` | 9/0/58 | 0 | 9 | 71.1% +/- 14.9% | +/-32.7% | 67 | 83.3% +/- 9.6% | 85.2% +/- 11.9% |

* `nocturia_present`: no `false` examples in this set, so its number is very nearly a recall-only measurement: nothing here tests whether an explicit denial is read correctly, which was the largest error family in the synthetic evaluation.

`null -> true` on real text, per fold: `nocturia_present` 4, 19, 5, 11, 2 of 58. This is the cell that invents a symptom into a patient's pre-filled form, counted here on submissions rather than on recombinations.

### `arm_b_finetune@c0.5-d0.0`

Recombination test slice: **n 7022**, **eff n 351** clusters, accuracy 82.2% [77.3%, 86.8%]. Holdout: **n 67** submissions, one observation each, scored by 5 fold models at margins 0.65, 0.3, 0.6, 0.05, 0.05. The two `n`s are printed together because they are not the same kind of number and the second is far the smaller.

| signal | true/false/null | omitted | decisive n | decisive acc (mean +/- sd) | worst-case half-width | all n | all acc (mean +/- sd) | null recall |
|---|---|---|---|---|---|---|---|---|
| `nocturia_present` | 9/0/58 | 0 | 9 | 53.3% +/- 18.3% | +/-32.7% | 67 | 93.4% +/- 2.3% | 99.7% +/- 0.8% |

* `nocturia_present`: no `false` examples in this set, so its number is very nearly a recall-only measurement: nothing here tests whether an explicit denial is read correctly, which was the largest error family in the synthetic evaluation.

`null -> true` on real text, per fold: `nocturia_present` 1, 0, 0, 0, 0 of 58. This is the cell that invents a symptom into a patient's pre-filled form, counted here on submissions rather than on recombinations.

### `arm_b_finetune@c0.5-d0.3`

Recombination test slice: **n 7022**, **eff n 511** clusters, accuracy 86.1% [82.2%, 89.8%]. Holdout: **n 67** submissions, one observation each, scored by 5 fold models at margins 0.35, 0.35, 0.1, 0.0, 0.8. The two `n`s are printed together because they are not the same kind of number and the second is far the smaller.

| signal | true/false/null | omitted | decisive n | decisive acc (mean +/- sd) | worst-case half-width | all n | all acc (mean +/- sd) | null recall |
|---|---|---|---|---|---|---|---|---|
| `nocturia_present` | 9/0/58 | 0 | 9 | 55.6% +/- 11.1% | +/-32.7% | 67 | 93.7% +/- 1.6% | 99.7% +/- 0.8% |

* `nocturia_present`: no `false` examples in this set, so its number is very nearly a recall-only measurement: nothing here tests whether an explicit denial is read correctly, which was the largest error family in the synthetic evaluation.

`null -> true` on real text, per fold: `nocturia_present` 0, 0, 0, 1, 0 of 58. This is the cell that invents a symptom into a patient's pre-filled form, counted here on submissions rather than on recombinations.

## Paired on real text

The 67 submissions are the same 67 for every model here, so unlike the recombination
test slice they can be paired: the informative quantity is the submissions two models
disagree about, not the gap between two means. One test per fold, never pooled.

### `arm_b_finetune@c0.0-d0.0` against `arm_b_finetune@c0.0-d0.3`

| fold | pairs | only `arm_b_finetune@c0.0-d0.0` | only `arm_b_finetune@c0.0-d0.3` | p |
|---|---|---|---|---|
| 0 | 67 | 4 | 3 | 1 |
| 1 | 67 | 17 | 2 | 0.000729 |
| 2 | 67 | 6 | 2 | 0.289 |
| 3 | 67 | 11 | 6 | 0.332 |
| 4 | 67 | 3 | 2 | 1 |

`arm_b_finetune@c0.0-d0.0` ahead on 5 folds, `arm_b_finetune@c0.0-d0.3` on 0. `null -> true` mean: 0.7% against 14.1% -- **13.4 points higher** for `arm_b_finetune@c0.0-d0.3` -- more invented symptoms.

*One test per fold over the same 67 submissions, never concatenated: five folds are five models scored on one sample, and pooling would report a p-value for 335 observations that do not exist.*

### `arm_b_finetune@c0.0-d0.0` against `arm_b_finetune@c0.5-d0.0`

| fold | pairs | only `arm_b_finetune@c0.0-d0.0` | only `arm_b_finetune@c0.5-d0.0` | p |
|---|---|---|---|---|
| 0 | 67 | 1 | 2 | 1 |
| 1 | 67 | 0 | 2 | 0.5 |
| 2 | 67 | 0 | 0 | 1 |
| 3 | 67 | 0 | 4 | 0.125 |
| 4 | 67 | 0 | 1 | 1 |

`arm_b_finetune@c0.0-d0.0` ahead on 0 folds, `arm_b_finetune@c0.5-d0.0` on 4. `null -> true` mean: 0.7% against 0.3% -- **0.3 points lower** for `arm_b_finetune@c0.5-d0.0` -- fewer invented symptoms.

*One test per fold over the same 67 submissions, never concatenated: five folds are five models scored on one sample, and pooling would report a p-value for 335 observations that do not exist.*

### `arm_b_finetune@c0.0-d0.0` against `arm_b_finetune@c0.5-d0.3`

| fold | pairs | only `arm_b_finetune@c0.0-d0.0` | only `arm_b_finetune@c0.5-d0.3` | p |
|---|---|---|---|---|
| 0 | 67 | 0 | 2 | 0.5 |
| 1 | 67 | 1 | 3 | 0.625 |
| 2 | 67 | 1 | 0 | 1 |
| 3 | 67 | 1 | 7 | 0.0703 |
| 4 | 67 | 0 | 0 | 1 |

`arm_b_finetune@c0.0-d0.0` ahead on 1 folds, `arm_b_finetune@c0.5-d0.3` on 3. `null -> true` mean: 0.7% against 0.3% -- **0.3 points lower** for `arm_b_finetune@c0.5-d0.3` -- fewer invented symptoms.

*One test per fold over the same 67 submissions, never concatenated: five folds are five models scored on one sample, and pooling would report a p-value for 335 observations that do not exist.*

### `arm_b_finetune@c0.0-d0.3` against `arm_b_finetune@c0.5-d0.0`

| fold | pairs | only `arm_b_finetune@c0.0-d0.3` | only `arm_b_finetune@c0.5-d0.0` | p |
|---|---|---|---|---|
| 0 | 67 | 2 | 4 | 0.688 |
| 1 | 67 | 2 | 19 | 0.000221 |
| 2 | 67 | 2 | 6 | 0.289 |
| 3 | 67 | 3 | 12 | 0.0352 |
| 4 | 67 | 1 | 3 | 0.625 |

`arm_b_finetune@c0.0-d0.3` ahead on 0 folds, `arm_b_finetune@c0.5-d0.0` on 5. `null -> true` mean: 14.1% against 0.3% -- **13.8 points lower** for `arm_b_finetune@c0.5-d0.0` -- fewer invented symptoms.

*One test per fold over the same 67 submissions, never concatenated: five folds are five models scored on one sample, and pooling would report a p-value for 335 observations that do not exist.*

### `arm_b_finetune@c0.0-d0.3` against `arm_b_finetune@c0.5-d0.3`

| fold | pairs | only `arm_b_finetune@c0.0-d0.3` | only `arm_b_finetune@c0.5-d0.3` | p |
|---|---|---|---|---|
| 0 | 67 | 1 | 4 | 0.375 |
| 1 | 67 | 2 | 19 | 0.000221 |
| 2 | 67 | 3 | 6 | 0.508 |
| 3 | 67 | 0 | 11 | 0.000977 |
| 4 | 67 | 2 | 3 | 1 |

`arm_b_finetune@c0.0-d0.3` ahead on 0 folds, `arm_b_finetune@c0.5-d0.3` on 5. `null -> true` mean: 14.1% against 0.3% -- **13.8 points lower** for `arm_b_finetune@c0.5-d0.3` -- fewer invented symptoms.

*One test per fold over the same 67 submissions, never concatenated: five folds are five models scored on one sample, and pooling would report a p-value for 335 observations that do not exist.*

### `arm_b_finetune@c0.5-d0.0` against `arm_b_finetune@c0.5-d0.3`

| fold | pairs | only `arm_b_finetune@c0.5-d0.0` | only `arm_b_finetune@c0.5-d0.3` | p |
|---|---|---|---|---|
| 0 | 67 | 1 | 2 | 1 |
| 1 | 67 | 1 | 1 | 1 |
| 2 | 67 | 1 | 0 | 1 |
| 3 | 67 | 1 | 3 | 0.625 |
| 4 | 67 | 1 | 0 | 1 |

`arm_b_finetune@c0.5-d0.0` ahead on 2 folds, `arm_b_finetune@c0.5-d0.3` on 2. `null -> true` mean: 0.3% against 0.3% -- **level** between the two.

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
| `majority_class` | baseline | 3062 | **243** | 100.0% [100.0%, 100.0%] |
| `length_only` | baseline | 3062 | **243** | 100.0% [100.0%, 100.0%] |
| `tfidf_logreg` | baseline | 3062 | **243** | 90.2% [86.9%, 93.1%] |
| `arm_b_finetune@c0.0-d0.0` | finetune | 3062 | **243** | 89.6% [86.0%, 93.0%] |
| `arm_b_finetune@c0.0-d0.3` | finetune | 3062 | **243** | 90.1% [86.4%, 93.5%] |
| `arm_b_finetune@c0.5-d0.0` | finetune | 3062 | **243** | 90.5% [86.8%, 93.9%] |
| `arm_b_finetune@c0.5-d0.3` | finetune | 3062 | **243** | 91.6% [88.3%, 94.6%] |

### 2. The same comparison, paired

Two overlapping intervals do not settle whether one model beats another on the same
examples. McNemar does, over the examples the two disagree about -- read it alongside the
intervals above, never instead of them.

| pair | n | a only | b only | p |
|---|---|---|---|---|
| `majority_class` vs `length_only` | 3062 | 0 | 0 | 1 |
| `majority_class` vs `tfidf_logreg` | 3062 | 305 | 0 | 3.07e-92 |
| `majority_class` vs `arm_b_finetune@c0.0-d0.0` | 3062 | 325 | 0 | 2.93e-98 |
| `length_only` vs `tfidf_logreg` | 3062 | 305 | 0 | 3.07e-92 |
| `length_only` vs `arm_b_finetune@c0.0-d0.0` | 3062 | 325 | 0 | 2.93e-98 |
| `tfidf_logreg` vs `arm_b_finetune@c0.0-d0.0` | 3062 | 222 | 202 | 0.356 |

Not on this table, because they cannot be paired at all -- different examples on the two sides, so there is nothing for McNemar to pair: `majority_class` vs `arm_b_finetune@c0.0-d0.3`; `majority_class` vs `arm_b_finetune@c0.5-d0.0`; `majority_class` vs `arm_b_finetune@c0.5-d0.3`; `length_only` vs `arm_b_finetune@c0.0-d0.3`; `length_only` vs `arm_b_finetune@c0.5-d0.0`; `length_only` vs `arm_b_finetune@c0.5-d0.3`; `tfidf_logreg` vs `arm_b_finetune@c0.0-d0.3`; `tfidf_logreg` vs `arm_b_finetune@c0.5-d0.0`; `tfidf_logreg` vs `arm_b_finetune@c0.5-d0.3`; `arm_b_finetune@c0.0-d0.0` vs `arm_b_finetune@c0.0-d0.3`; `arm_b_finetune@c0.0-d0.0` vs `arm_b_finetune@c0.5-d0.0`; `arm_b_finetune@c0.0-d0.0` vs `arm_b_finetune@c0.5-d0.3`; `arm_b_finetune@c0.0-d0.3` vs `arm_b_finetune@c0.5-d0.0`; `arm_b_finetune@c0.0-d0.3` vs `arm_b_finetune@c0.5-d0.3`; `arm_b_finetune@c0.5-d0.0` vs `arm_b_finetune@c0.5-d0.3`. Read those through the intervals above and the per-fold spread, and see "Pairs that could not be tested" below.

### 3. Where the errors fall

The per-fragment table below, as one number per model. Errors spread thinly across many
fragments say the method is too weak. Errors piled onto a handful say those specific ideas
are not learnable from the data we have -- and the table names them, which is what makes
this the most decision-useful thing in the report.

* `majority_class`: 3960 errors across 108 of 351 decisive fragments. Half of them fall on **39** fragments (an even spread would be 54.0); the worst ten carry 15.8% of all errors.
* `length_only`: 3960 errors across 108 of 351 decisive fragments. Half of them fall on **39** fragments (an even spread would be 54.0); the worst ten carry 15.8% of all errors.
* `tfidf_logreg`: 2452 errors across 168 of 351 decisive fragments. Half of them fall on **28** fragments (an even spread would be 84.0); the worst ten carry 21.7% of all errors.
* `arm_b_finetune@c0.0-d0.0`: 1143 errors across 90 of 351 decisive fragments. Half of them fall on **16** fragments (an even spread would be 45.0); the worst ten carry 36.3% of all errors.
* `arm_b_finetune@c0.0-d0.3`: 810 errors across 83 of 749 decisive fragments. Half of them fall on **18** fragments (an even spread would be 41.5); the worst ten carry 33.1% of all errors.
* `arm_b_finetune@c0.5-d0.0`: 1247 errors across 81 of 351 decisive fragments. Half of them fall on **15** fragments (an even spread would be 40.5); the worst ten carry 37.8% of all errors.
* `arm_b_finetune@c0.5-d0.3`: 973 errors across 74 of 749 decisive fragments. Half of them fall on **17** fragments (an even spread would be 37.0); the worst ten carry 34.4% of all errors.

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
| `length_only__shuffled` | 60.4% [39.1%, 76.8%] | 25.1% [18.7%, 29.0%] |
| `tfidf_logreg__shuffled` | 60.4% [39.0%, 76.8%] | 25.1% [18.7%, 29.0%] |

## Paired comparisons (McNemar, raw argmax)

Exact two-sided McNemar over the examples the two models disagree about. Pairing unit is the
example, not the cluster -- see the limitations.

| pair | slice | n | a only | b only | p |
|---|---|---|---|---|---|
| `majority_class` vs `length_only` | overall | 10000 | 0 | 0 | 1 |
| `majority_class` vs `length_only` | null_ambiguous | 3062 | 0 | 0 | 1 |
| `majority_class` vs `tfidf_logreg` | overall | 10000 | 311 | 1803 | 7.21e-255 |
| `majority_class` vs `tfidf_logreg` | null_ambiguous | 3062 | 305 | 0 | 3.07e-92 |
| `majority_class` vs `arm_b_finetune@c0.0-d0.0` | overall | 10000 | 349 | 3139 | 0 |
| `majority_class` vs `arm_b_finetune@c0.0-d0.0` | null_ambiguous | 3062 | 325 | 0 | 2.93e-98 |
| `length_only` vs `tfidf_logreg` | overall | 10000 | 311 | 1803 | 7.21e-255 |
| `length_only` vs `tfidf_logreg` | null_ambiguous | 3062 | 305 | 0 | 3.07e-92 |
| `length_only` vs `arm_b_finetune@c0.0-d0.0` | overall | 10000 | 349 | 3139 | 0 |
| `length_only` vs `arm_b_finetune@c0.0-d0.0` | null_ambiguous | 3062 | 325 | 0 | 2.93e-98 |
| `tfidf_logreg` vs `arm_b_finetune@c0.0-d0.0` | overall | 10000 | 396 | 1694 | 1.78e-190 |
| `tfidf_logreg` vs `arm_b_finetune@c0.0-d0.0` | null_ambiguous | 3062 | 222 | 202 | 0.356 |

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
| `nocturia_false` | 1722 | 0.0% | 0.0% | 48.5% | 84.1% | 86.9% | 74.7% | 72.5% | 86.9pp |
| `nocturia_true` | 1025 | 0.0% | 0.0% | 41.0% | 70.9% | 72.3% | 77.9% | 76.3% | 77.9pp |
| `nocturia_null_attribution` | 655 | 100.0% | 100.0% | 83.7% | 85.5% | 88.1% | 88.4% | 86.6% | 16.3pp |
| `nocturia_null_hedged` | 587 | 100.0% | 100.0% | 97.1% | 86.1% | 85.7% | 86.9% | 86.5% | 14.3pp |
| `nocturia_null_thirdparty` | 578 | 100.0% | 100.0% | 86.7% | 89.3% | 92.7% | 89.8% | 93.9% | 13.3pp |
| `nocturia_null_historical` | 558 | 100.0% | 100.0% | 90.4% | 93.3% | 89.5% | 90.3% | 92.8% | 10.5pp |
| `nocturia_null_metaphor` | 684 | 100.0% | 100.0% | 93.1% | 93.9% | 93.9% | 96.2% | 97.8% | 6.9pp |
| `(none)` | 2978 | 100.0% | 100.0% | 99.8% | 99.2% | 99.6% | 99.6% | 99.9% | 0.8pp |

### By fragment, errors

Ordered by the worst model's error count, so the fragments the comparison is about sort
to the top whichever encoder wins. Counts, not rates: these are the sentences a month of
library work would be spent on. The JSON holds every fragment.

| fragment | library | truth | `majority_class` | `length_only` | `tfidf_logreg` | `arm_b_finetune@c0.0-d0.0` | `arm_b_finetune@c0.0-d0.3` | `arm_b_finetune@c0.5-d0.0` | `arm_b_finetune@c0.5-d0.3` | spread |
|---|---|---|---|---|---|---|---|---|---|---|
| `nocturia_false:75848908` | `nocturia_false` | false | 73 | 73 | 49 | 0 | 0 | 2 | 3 | 73 |
| `nocturia_false:0105f271` | `nocturia_false` | false | 68 | 68 | 55 | 0 | 0 | 0 | 0 | 68 |
| `nocturia_false:3a70bcb2` | `nocturia_false` | false | 66 | 66 | 66 | 0 | 0 | 0 | 0 | 66 |
| `nocturia_false:3e89d247` | `nocturia_false` | false | 65 | 65 | 64 | 0 | 0 | 0 | 0 | 65 |
| `nocturia_false:776d32bb` | `nocturia_false` | false | 64 | 64 | 55 | 0 | 0 | 0 | 0 | 64 |
| `nocturia_false:e6fd6a44` | `nocturia_false` | false | 60 | 60 | 0 | 49 | 26 | 64 | 31 | 64 |
| `nocturia_false:79441d6a` | `nocturia_false` | false | 59 | 59 | 8 | 0 | 0 | 0 | 0 | 59 |
| `nocturia_false:76105311` | `nocturia_false` | false | 57 | 57 | 9 | 0 | 0 | 0 | 0 | 57 |
| `nocturia_false:876119ca` | `nocturia_false` | false | 57 | 57 | 6 | 0 | 0 | 0 | 11 | 57 |
| `nocturia_false:cd9ee762` | `nocturia_false` | false | 57 | 57 | 3 | 0 | 0 | 0 | 0 | 57 |
| `nocturia_false:3fbd0758` | `nocturia_false` | false | 55 | 55 | 4 | 0 | 0 | 0 | 0 | 55 |
| `nocturia_false:31c155d0` | `nocturia_false` | false | 53 | 53 | 1 | 0 | 0 | 0 | 0 | 53 |
| `nocturia_false:3aab37fe` | `nocturia_false` | false | 53 | 53 | 51 | 53 | 44 | 50 | 43 | 10 |
| `nocturia_false:cddf064c` | `nocturia_false` | false | 53 | 53 | 46 | 0 | 0 | 0 | 0 | 53 |
| `nocturia_false:01f605e7` | `nocturia_false` | false | 52 | 52 | 16 | 0 | 0 | 2 | 0 | 52 |
| `nocturia_false:a9555a97` | `nocturia_false` | false | 52 | 52 | 43 | 5 | 0 | 0 | 0 | 52 |
| `nocturia_false:59e83d34` | `nocturia_false` | false | 51 | 51 | 5 | 0 | 2 | 0 | 0 | 51 |
| `nocturia_false:a9489bdd` | `nocturia_false` | false | 51 | 51 | 0 | 0 | 0 | 0 | 0 | 51 |
| `nocturia_false:21180255` | `nocturia_false` | false | 50 | 50 | 50 | 11 | 0 | 38 | 25 | 50 |
| `nocturia_false:98d02ead` | `nocturia_false` | false | 50 | 50 | 42 | 11 | 0 | 46 | 39 | 50 |
| `nocturia_false:48f35b91` | `nocturia_false` | false | 49 | 49 | 0 | 0 | 0 | 0 | 0 | 49 |
| `nocturia_false:55832b2b` | `nocturia_false` | false | 49 | 49 | 12 | 11 | 0 | 0 | 0 | 49 |
| `nocturia_false:b11139a0` | `nocturia_false` | false | 49 | 49 | 1 | 0 | 0 | 0 | 0 | 49 |
| `nocturia_true:86e1cd53` | `nocturia_true` | true | 49 | 49 | 49 | 49 | 29 | 49 | 29 | 20 |
| `nocturia_false:1bd2f6f8` | `nocturia_false` | false | 48 | 48 | 45 | 48 | 0 | 47 | 0 | 48 |
| `nocturia_false:b1f7e93f` | `nocturia_false` | false | 48 | 48 | 48 | 0 | 25 | 41 | 35 | 48 |
| `nocturia_false:c6a4c61b` | `nocturia_false` | false | 48 | 48 | 3 | 0 | 0 | 0 | 0 | 48 |
| `nocturia_false:eff52ced` | `nocturia_false` | false | 46 | 46 | 10 | 0 | 1 | 5 | 0 | 46 |
| `nocturia_true:c3f73311` | `nocturia_true` | true | 46 | 46 | 17 | 1 | 26 | 13 | 0 | 46 |
| `nocturia_false:5e819a32` | `nocturia_false` | false | 45 | 45 | 43 | 0 | 0 | 14 | 22 | 45 |
| `nocturia_false:99cd439f` | `nocturia_false` | false | 45 | 45 | 45 | 41 | 1 | 45 | 38 | 44 |
| `nocturia_false:bf88ba0d` | `nocturia_false` | false | 45 | 45 | 45 | 21 | 3 | 45 | 35 | 42 |
| `nocturia_false:f4140180` | `nocturia_false` | false | 45 | 45 | 1 | 0 | 0 | 0 | 0 | 45 |
| `nocturia_true:594869e7` | `nocturia_true` | true | 44 | 44 | 14 | 24 | 0 | 0 | 0 | 44 |
| `nocturia_false:1a41970c` | `nocturia_false` | false | 43 | 43 | 0 | 0 | 14 | 0 | 22 | 43 |
| `nocturia_false:1cb7de3b` | `nocturia_false` | false | 41 | 41 | 40 | 6 | 0 | 43 | 25 | 43 |
| `nocturia_false:4a12f37a` | `nocturia_false` | false | 43 | 43 | 42 | 6 | 0 | 7 | 0 | 43 |
| `nocturia_false:dfdc943b` | `nocturia_false` | false | 42 | 42 | 2 | 0 | 0 | 0 | 0 | 42 |
| `nocturia_false:08a0b22d` | `nocturia_false` | false | 41 | 41 | 0 | 0 | 0 | 0 | 0 | 41 |
| `nocturia_false:70c4843c` | `nocturia_false` | false | 41 | 41 | 28 | 0 | 0 | 1 | 2 | 41 |

*188 further fragments erred on at least one model; the JSON holds them all.*

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
| false | 2479 | **54** | 0.0% [0.0%, 0.0%] |
| null_ambiguous | 3062 | **243** | 100.0% [100.0%, 100.0%] |
| null_structural | 2978 | **1** | 100.0% [100.0%, 100.0%] |
| true | 1481 | **54** | 0.0% [0.0%, 0.0%] |

### By null sub-class

| sub-class | n | eff n | null recall [95% CI] |
|---|---|---|---|
| attribution | 657 | **51** | 100.0% [100.0%, 100.0%] |
| hedged | 588 | **47** | 100.0% [100.0%, 100.0%] |
| historical | 554 | **46** | 100.0% [100.0%, 100.0%] |
| metaphor | 684 | **52** | 100.0% [100.0%, 100.0%] |
| third_party | 579 | **47** | 100.0% [100.0%, 100.0%] |

### By fragment library

| library | n | eff n | accuracy [95% CI] |
|---|---|---|---|
| nocturia_false | 2479 | **54** | 0.0% [0.0%, 0.0%] |
| nocturia_null_attribution | 657 | **51** | 100.0% [100.0%, 100.0%] |
| nocturia_null_hedged | 588 | **47** | 100.0% [100.0%, 100.0%] |
| nocturia_null_historical | 554 | **46** | 100.0% [100.0%, 100.0%] |
| nocturia_null_metaphor | 684 | **52** | 100.0% [100.0%, 100.0%] |
| nocturia_null_thirdparty | 579 | **47** | 100.0% [100.0%, 100.0%] |
| nocturia_true | 1481 | **54** | 0.0% [0.0%, 0.0%] |
| (none) | 2978 | **1** | 100.0% [100.0%, 100.0%] |

### Per-fragment errors (worst first)

Whether errors are spread thinly across many fragments or piled onto a few is the difference
between "the method is too weak" (model work) and "these specific ideas are not learnable from
the data we have" (library work, and these are the fragments to write more of). No intervals:
a fragment is one cluster, so an interval over its own examples measures nothing.

108 of 351 decisive fragments were got wrong at least once.

`majority_class`: 3960 errors across 108 of 351 decisive fragments. Half of them fall on **39** fragments (an even spread would be 54.0); the worst ten carry 15.8% of all errors.

| fragment | library | sub-class | truth | correct | accuracy | predicted as |
|---|---|---|---|---|---|---|
| `nocturia_false:75848908` | `nocturia_false` | -- | false | 0/73 | 0.0% | null 73 |
| `nocturia_false:0105f271` | `nocturia_false` | -- | false | 0/68 | 0.0% | null 68 |
| `nocturia_false:3a70bcb2` | `nocturia_false` | -- | false | 0/66 | 0.0% | null 66 |
| `nocturia_false:3e89d247` | `nocturia_false` | -- | false | 0/65 | 0.0% | null 65 |
| `nocturia_false:776d32bb` | `nocturia_false` | -- | false | 0/64 | 0.0% | null 64 |
| `nocturia_false:e6fd6a44` | `nocturia_false` | -- | false | 0/60 | 0.0% | null 60 |
| `nocturia_false:79441d6a` | `nocturia_false` | -- | false | 0/59 | 0.0% | null 59 |
| `nocturia_false:76105311` | `nocturia_false` | -- | false | 0/57 | 0.0% | null 57 |
| `nocturia_false:876119ca` | `nocturia_false` | -- | false | 0/57 | 0.0% | null 57 |
| `nocturia_false:cd9ee762` | `nocturia_false` | -- | false | 0/57 | 0.0% | null 57 |
| `nocturia_false:3fbd0758` | `nocturia_false` | -- | false | 0/55 | 0.0% | null 55 |
| `nocturia_false:31c155d0` | `nocturia_false` | -- | false | 0/53 | 0.0% | null 53 |
| `nocturia_false:3aab37fe` | `nocturia_false` | -- | false | 0/53 | 0.0% | null 53 |
| `nocturia_false:cddf064c` | `nocturia_false` | -- | false | 0/53 | 0.0% | null 53 |
| `nocturia_false:01f605e7` | `nocturia_false` | -- | false | 0/52 | 0.0% | null 52 |
| `nocturia_false:a9555a97` | `nocturia_false` | -- | false | 0/52 | 0.0% | null 52 |
| `nocturia_false:59e83d34` | `nocturia_false` | -- | false | 0/51 | 0.0% | null 51 |
| `nocturia_false:a9489bdd` | `nocturia_false` | -- | false | 0/51 | 0.0% | null 51 |
| `nocturia_false:21180255` | `nocturia_false` | -- | false | 0/50 | 0.0% | null 50 |
| `nocturia_false:98d02ead` | `nocturia_false` | -- | false | 0/50 | 0.0% | null 50 |
| `nocturia_false:48f35b91` | `nocturia_false` | -- | false | 0/49 | 0.0% | null 49 |
| `nocturia_false:55832b2b` | `nocturia_false` | -- | false | 0/49 | 0.0% | null 49 |
| `nocturia_false:b11139a0` | `nocturia_false` | -- | false | 0/49 | 0.0% | null 49 |
| `nocturia_true:86e1cd53` | `nocturia_true` | -- | true | 0/49 | 0.0% | null 49 |
| `nocturia_false:1bd2f6f8` | `nocturia_false` | -- | false | 0/48 | 0.0% | null 48 |
| `nocturia_false:b1f7e93f` | `nocturia_false` | -- | false | 0/48 | 0.0% | null 48 |
| `nocturia_false:c6a4c61b` | `nocturia_false` | -- | false | 0/48 | 0.0% | null 48 |
| `nocturia_false:eff52ced` | `nocturia_false` | -- | false | 0/46 | 0.0% | null 46 |
| `nocturia_true:c3f73311` | `nocturia_true` | -- | true | 0/46 | 0.0% | null 46 |
| `nocturia_false:5e819a32` | `nocturia_false` | -- | false | 0/45 | 0.0% | null 45 |
| `nocturia_false:99cd439f` | `nocturia_false` | -- | false | 0/45 | 0.0% | null 45 |
| `nocturia_false:bf88ba0d` | `nocturia_false` | -- | false | 0/45 | 0.0% | null 45 |
| `nocturia_false:f4140180` | `nocturia_false` | -- | false | 0/45 | 0.0% | null 45 |
| `nocturia_true:594869e7` | `nocturia_true` | -- | true | 0/44 | 0.0% | null 44 |
| `nocturia_false:1a41970c` | `nocturia_false` | -- | false | 0/43 | 0.0% | null 43 |
| `nocturia_false:4a12f37a` | `nocturia_false` | -- | false | 0/43 | 0.0% | null 43 |
| `nocturia_false:dfdc943b` | `nocturia_false` | -- | false | 0/42 | 0.0% | null 42 |
| `nocturia_false:08a0b22d` | `nocturia_false` | -- | false | 0/41 | 0.0% | null 41 |
| `nocturia_false:1cb7de3b` | `nocturia_false` | -- | false | 0/41 | 0.0% | null 41 |
| `nocturia_false:70c4843c` | `nocturia_false` | -- | false | 0/41 | 0.0% | null 41 |

*68 further fragments with at least one error are in the JSON sidecar; every fragment is there regardless of score.*

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
| false | 2479 | **54** | 0.0% [0.0%, 0.0%] |
| null_ambiguous | 3062 | **243** | 100.0% [100.0%, 100.0%] |
| null_structural | 2978 | **1** | 100.0% [100.0%, 100.0%] |
| true | 1481 | **54** | 0.0% [0.0%, 0.0%] |

### By null sub-class

| sub-class | n | eff n | null recall [95% CI] |
|---|---|---|---|
| attribution | 657 | **51** | 100.0% [100.0%, 100.0%] |
| hedged | 588 | **47** | 100.0% [100.0%, 100.0%] |
| historical | 554 | **46** | 100.0% [100.0%, 100.0%] |
| metaphor | 684 | **52** | 100.0% [100.0%, 100.0%] |
| third_party | 579 | **47** | 100.0% [100.0%, 100.0%] |

### By fragment library

| library | n | eff n | accuracy [95% CI] |
|---|---|---|---|
| nocturia_false | 2479 | **54** | 0.0% [0.0%, 0.0%] |
| nocturia_null_attribution | 657 | **51** | 100.0% [100.0%, 100.0%] |
| nocturia_null_hedged | 588 | **47** | 100.0% [100.0%, 100.0%] |
| nocturia_null_historical | 554 | **46** | 100.0% [100.0%, 100.0%] |
| nocturia_null_metaphor | 684 | **52** | 100.0% [100.0%, 100.0%] |
| nocturia_null_thirdparty | 579 | **47** | 100.0% [100.0%, 100.0%] |
| nocturia_true | 1481 | **54** | 0.0% [0.0%, 0.0%] |
| (none) | 2978 | **1** | 100.0% [100.0%, 100.0%] |

### Per-fragment errors (worst first)

Whether errors are spread thinly across many fragments or piled onto a few is the difference
between "the method is too weak" (model work) and "these specific ideas are not learnable from
the data we have" (library work, and these are the fragments to write more of). No intervals:
a fragment is one cluster, so an interval over its own examples measures nothing.

108 of 351 decisive fragments were got wrong at least once.

`length_only`: 3960 errors across 108 of 351 decisive fragments. Half of them fall on **39** fragments (an even spread would be 54.0); the worst ten carry 15.8% of all errors.

| fragment | library | sub-class | truth | correct | accuracy | predicted as |
|---|---|---|---|---|---|---|
| `nocturia_false:75848908` | `nocturia_false` | -- | false | 0/73 | 0.0% | null 73 |
| `nocturia_false:0105f271` | `nocturia_false` | -- | false | 0/68 | 0.0% | null 68 |
| `nocturia_false:3a70bcb2` | `nocturia_false` | -- | false | 0/66 | 0.0% | null 66 |
| `nocturia_false:3e89d247` | `nocturia_false` | -- | false | 0/65 | 0.0% | null 65 |
| `nocturia_false:776d32bb` | `nocturia_false` | -- | false | 0/64 | 0.0% | null 64 |
| `nocturia_false:e6fd6a44` | `nocturia_false` | -- | false | 0/60 | 0.0% | null 60 |
| `nocturia_false:79441d6a` | `nocturia_false` | -- | false | 0/59 | 0.0% | null 59 |
| `nocturia_false:76105311` | `nocturia_false` | -- | false | 0/57 | 0.0% | null 57 |
| `nocturia_false:876119ca` | `nocturia_false` | -- | false | 0/57 | 0.0% | null 57 |
| `nocturia_false:cd9ee762` | `nocturia_false` | -- | false | 0/57 | 0.0% | null 57 |
| `nocturia_false:3fbd0758` | `nocturia_false` | -- | false | 0/55 | 0.0% | null 55 |
| `nocturia_false:31c155d0` | `nocturia_false` | -- | false | 0/53 | 0.0% | null 53 |
| `nocturia_false:3aab37fe` | `nocturia_false` | -- | false | 0/53 | 0.0% | null 53 |
| `nocturia_false:cddf064c` | `nocturia_false` | -- | false | 0/53 | 0.0% | null 53 |
| `nocturia_false:01f605e7` | `nocturia_false` | -- | false | 0/52 | 0.0% | null 52 |
| `nocturia_false:a9555a97` | `nocturia_false` | -- | false | 0/52 | 0.0% | null 52 |
| `nocturia_false:59e83d34` | `nocturia_false` | -- | false | 0/51 | 0.0% | null 51 |
| `nocturia_false:a9489bdd` | `nocturia_false` | -- | false | 0/51 | 0.0% | null 51 |
| `nocturia_false:21180255` | `nocturia_false` | -- | false | 0/50 | 0.0% | null 50 |
| `nocturia_false:98d02ead` | `nocturia_false` | -- | false | 0/50 | 0.0% | null 50 |
| `nocturia_false:48f35b91` | `nocturia_false` | -- | false | 0/49 | 0.0% | null 49 |
| `nocturia_false:55832b2b` | `nocturia_false` | -- | false | 0/49 | 0.0% | null 49 |
| `nocturia_false:b11139a0` | `nocturia_false` | -- | false | 0/49 | 0.0% | null 49 |
| `nocturia_true:86e1cd53` | `nocturia_true` | -- | true | 0/49 | 0.0% | null 49 |
| `nocturia_false:1bd2f6f8` | `nocturia_false` | -- | false | 0/48 | 0.0% | null 48 |
| `nocturia_false:b1f7e93f` | `nocturia_false` | -- | false | 0/48 | 0.0% | null 48 |
| `nocturia_false:c6a4c61b` | `nocturia_false` | -- | false | 0/48 | 0.0% | null 48 |
| `nocturia_false:eff52ced` | `nocturia_false` | -- | false | 0/46 | 0.0% | null 46 |
| `nocturia_true:c3f73311` | `nocturia_true` | -- | true | 0/46 | 0.0% | null 46 |
| `nocturia_false:5e819a32` | `nocturia_false` | -- | false | 0/45 | 0.0% | null 45 |
| `nocturia_false:99cd439f` | `nocturia_false` | -- | false | 0/45 | 0.0% | null 45 |
| `nocturia_false:bf88ba0d` | `nocturia_false` | -- | false | 0/45 | 0.0% | null 45 |
| `nocturia_false:f4140180` | `nocturia_false` | -- | false | 0/45 | 0.0% | null 45 |
| `nocturia_true:594869e7` | `nocturia_true` | -- | true | 0/44 | 0.0% | null 44 |
| `nocturia_false:1a41970c` | `nocturia_false` | -- | false | 0/43 | 0.0% | null 43 |
| `nocturia_false:4a12f37a` | `nocturia_false` | -- | false | 0/43 | 0.0% | null 43 |
| `nocturia_false:dfdc943b` | `nocturia_false` | -- | false | 0/42 | 0.0% | null 42 |
| `nocturia_false:08a0b22d` | `nocturia_false` | -- | false | 0/41 | 0.0% | null 41 |
| `nocturia_false:1cb7de3b` | `nocturia_false` | -- | false | 0/41 | 0.0% | null 41 |
| `nocturia_false:70c4843c` | `nocturia_false` | -- | false | 0/41 | 0.0% | null 41 |

*68 further fragments with at least one error are in the JSON sidecar; every fragment is there regardless of score.*

## `tfidf_logreg`

TF-IDF unigrams and bigrams into logistic regression. Tests whether the dataset is keyword-solvable. Its overall accuracy is close to uninformative; the `null_ambiguous` slice is the number that matters.

Decision-rule margins selected per fold (on each fold's own validation split): 0.0, 0.05.

*Confusion matrix, raw argmax*

|  | pred false | pred true | pred null | total |
|---|---|---|---|---|
| **truth false** | 1191 | 170 | 1118 | 2479 |
| **truth true** | 202 | 612 | 667 | 1481 |
| **truth null** | 142 | 169 | 5729 | 6040 |
| **total** | 1535 | 951 | 7514 | 10000 |

`null -> true`: 169 of 6040 truly-null examples (2.80%).

*Confusion matrix, after the decision rule*

|  | pred false | pred true | pred null | total |
|---|---|---|---|---|
| **truth false** | 1202 | 156 | 1121 | 2479 |
| **truth true** | 203 | 607 | 671 | 1481 |
| **truth null** | 143 | 163 | 5734 | 6040 |
| **total** | 1548 | 926 | 7526 | 10000 |

`null -> true`: 163 of 6040 truly-null examples (2.70%).

### Per class, after the decision rule

| class | support | predicted | precision | recall | F1 |
|---|---|---|---|---|---|
| `false` | 2479 | 1548 | 77.6% | 48.5% | 59.7% |
| `true` | 1481 | 926 | 65.6% | 41.0% | 50.4% |
| `null` | 6040 | 7526 | 76.2% | 94.9% | 84.5% |

### By label mode

| label mode | n | eff n | accuracy [95% CI] |
|---|---|---|---|
| false | 2479 | **54** | 48.5% [37.0%, 59.7%] |
| null_ambiguous | 3062 | **243** | 90.2% [86.9%, 93.1%] |
| null_structural | 2978 | **1** | 99.8% [99.8%, 99.8%] |
| true | 1481 | **54** | 41.0% [30.3%, 52.1%] |

### By null sub-class

| sub-class | n | eff n | null recall [95% CI] |
|---|---|---|---|
| attribution | 657 | **51** | 83.7% [73.9%, 92.2%] |
| hedged | 588 | **47** | 97.1% [95.0%, 98.9%] |
| historical | 554 | **46** | 90.4% [83.5%, 96.1%] |
| metaphor | 684 | **52** | 93.1% [86.4%, 97.8%] |
| third_party | 579 | **47** | 86.7% [77.7%, 93.8%] |

### By fragment library

| library | n | eff n | accuracy [95% CI] |
|---|---|---|---|
| nocturia_false | 2479 | **54** | 48.5% [37.0%, 59.7%] |
| nocturia_null_attribution | 657 | **51** | 83.7% [73.9%, 92.2%] |
| nocturia_null_hedged | 588 | **47** | 97.1% [95.0%, 98.9%] |
| nocturia_null_historical | 554 | **46** | 90.4% [83.5%, 96.1%] |
| nocturia_null_metaphor | 684 | **52** | 93.1% [86.4%, 97.8%] |
| nocturia_null_thirdparty | 579 | **47** | 86.7% [77.7%, 93.8%] |
| nocturia_true | 1481 | **54** | 41.0% [30.3%, 52.1%] |
| (none) | 2978 | **1** | 99.8% [99.8%, 99.8%] |

### Per-fragment errors (worst first)

Whether errors are spread thinly across many fragments or piled onto a few is the difference
between "the method is too weak" (model work) and "these specific ideas are not learnable from
the data we have" (library work, and these are the fragments to write more of). No intervals:
a fragment is one cluster, so an interval over its own examples measures nothing.

168 of 351 decisive fragments were got wrong at least once.

`tfidf_logreg`: 2452 errors across 168 of 351 decisive fragments. Half of them fall on **28** fragments (an even spread would be 84.0); the worst ten carry 21.7% of all errors.

| fragment | library | sub-class | truth | correct | accuracy | predicted as |
|---|---|---|---|---|---|---|
| `nocturia_false:3a70bcb2` | `nocturia_false` | -- | false | 0/66 | 0.0% | null 66 |
| `nocturia_false:21180255` | `nocturia_false` | -- | false | 0/50 | 0.0% | null 50 |
| `nocturia_true:86e1cd53` | `nocturia_true` | -- | true | 0/49 | 0.0% | null 49 |
| `nocturia_false:b1f7e93f` | `nocturia_false` | -- | false | 0/48 | 0.0% | true 48 |
| `nocturia_false:99cd439f` | `nocturia_false` | -- | false | 0/45 | 0.0% | null 45 |
| `nocturia_false:bf88ba0d` | `nocturia_false` | -- | false | 0/45 | 0.0% | null 45 |
| `nocturia_false:deb3785c` | `nocturia_false` | -- | false | 0/39 | 0.0% | null 39 |
| `nocturia_true:0740576d` | `nocturia_true` | -- | true | 0/38 | 0.0% | null 38 |
| `nocturia_true:4a4f4b70` | `nocturia_true` | -- | true | 0/34 | 0.0% | false 2, null 32 |
| `nocturia_true:126e0cfb` | `nocturia_true` | -- | true | 0/33 | 0.0% | false 5, null 28 |
| `nocturia_true:86863ee3` | `nocturia_true` | -- | true | 0/33 | 0.0% | false 1, null 32 |
| `nocturia_false:2ba145eb` | `nocturia_false` | -- | false | 0/32 | 0.0% | null 32 |
| `nocturia_true:39566c91` | `nocturia_true` | -- | true | 0/31 | 0.0% | false 3, null 28 |
| `nocturia_true:a2f6ab3f` | `nocturia_true` | -- | true | 0/30 | 0.0% | false 14, null 16 |
| `nocturia_true:f2891c69` | `nocturia_true` | -- | true | 0/30 | 0.0% | false 9, null 21 |
| `nocturia_false:14ecd3b3` | `nocturia_false` | -- | false | 0/29 | 0.0% | true 29 |
| `nocturia_false:5efba823` | `nocturia_false` | -- | false | 0/29 | 0.0% | null 29 |
| `nocturia_true:00a2bd48` | `nocturia_true` | -- | true | 0/28 | 0.0% | false 23, null 5 |
| `nocturia_true:0c394532` | `nocturia_true` | -- | true | 0/27 | 0.0% | false 1, null 26 |
| `nocturia_true:e853d9c0` | `nocturia_true` | -- | true | 0/27 | 0.0% | null 27 |
| `nocturia_true:4506c1ce` | `nocturia_true` | -- | true | 0/26 | 0.0% | null 26 |
| `nocturia_true:efa44ced` | `nocturia_true` | -- | true | 0/24 | 0.0% | null 24 |
| `nocturia_true:f81d11be` | `nocturia_true` | -- | true | 0/20 | 0.0% | null 20 |
| `nocturia_true:1e14667e` | `nocturia_true` | -- | true | 0/19 | 0.0% | false 17, null 2 |
| `nocturia_null_attribution:0dfc44e6` | `nocturia_null_attribution` | attribution | null | 0/17 | 0.0% | false 4, true 13 |
| `nocturia_null_attribution:e51cceef` | `nocturia_null_attribution` | attribution | null | 0/15 | 0.0% | false 1, true 14 |
| `nocturia_null_thirdparty:776f85a8` | `nocturia_null_thirdparty` | third_party | null | 0/15 | 0.0% | true 15 |
| `nocturia_true:4dc9876b` | `nocturia_true` | -- | true | 0/15 | 0.0% | false 1, null 14 |
| `nocturia_true:e847f8b0` | `nocturia_true` | -- | true | 0/14 | 0.0% | false 5, null 9 |
| `nocturia_null_thirdparty:6ecdd54e` | `nocturia_null_thirdparty` | third_party | null | 0/13 | 0.0% | false 1, true 12 |
| `nocturia_null_historical:9354ddb0` | `nocturia_null_historical` | historical | null | 0/11 | 0.0% | true 11 |
| `nocturia_null_attribution:0de14f1d` | `nocturia_null_attribution` | attribution | null | 0/9 | 0.0% | false 4, true 5 |
| `nocturia_false:3e89d247` | `nocturia_false` | -- | false | 1/65 | 1.5% | false 1, null 64 |
| `nocturia_false:4a12f37a` | `nocturia_false` | -- | false | 1/43 | 2.3% | false 1, null 42 |
| `nocturia_false:1cb7de3b` | `nocturia_false` | -- | false | 1/41 | 2.4% | false 1, null 40 |
| `nocturia_true:8cfc0f45` | `nocturia_true` | -- | true | 1/37 | 2.7% | true 1, null 36 |
| `nocturia_true:f3e4ee3e` | `nocturia_true` | -- | true | 1/35 | 2.9% | true 1, null 34 |
| `nocturia_true:2cbd088f` | `nocturia_true` | -- | true | 1/32 | 3.1% | false 5, true 1, null 26 |
| `nocturia_true:23c9421e` | `nocturia_true` | -- | true | 1/31 | 3.2% | false 23, true 1, null 7 |
| `nocturia_false:3aab37fe` | `nocturia_false` | -- | false | 2/53 | 3.8% | false 2, true 1, null 50 |

*128 further fragments with at least one error are in the JSON sidecar; every fragment is there regardless of score.*

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
| false | 2479 | **54** | 0.0% [0.0%, 0.0%] |
| null_ambiguous | 3062 | **243** | 100.0% [100.0%, 100.0%] |
| null_structural | 2978 | **1** | 100.0% [100.0%, 100.0%] |
| true | 1481 | **54** | 0.0% [0.0%, 0.0%] |

### By null sub-class

| sub-class | n | eff n | null recall [95% CI] |
|---|---|---|---|
| attribution | 657 | **51** | 100.0% [100.0%, 100.0%] |
| hedged | 588 | **47** | 100.0% [100.0%, 100.0%] |
| historical | 554 | **46** | 100.0% [100.0%, 100.0%] |
| metaphor | 684 | **52** | 100.0% [100.0%, 100.0%] |
| third_party | 579 | **47** | 100.0% [100.0%, 100.0%] |

### By fragment library

| library | n | eff n | accuracy [95% CI] |
|---|---|---|---|
| nocturia_false | 2479 | **54** | 0.0% [0.0%, 0.0%] |
| nocturia_null_attribution | 657 | **51** | 100.0% [100.0%, 100.0%] |
| nocturia_null_hedged | 588 | **47** | 100.0% [100.0%, 100.0%] |
| nocturia_null_historical | 554 | **46** | 100.0% [100.0%, 100.0%] |
| nocturia_null_metaphor | 684 | **52** | 100.0% [100.0%, 100.0%] |
| nocturia_null_thirdparty | 579 | **47** | 100.0% [100.0%, 100.0%] |
| nocturia_true | 1481 | **54** | 0.0% [0.0%, 0.0%] |
| (none) | 2978 | **1** | 100.0% [100.0%, 100.0%] |

### Per-fragment errors (worst first)

Whether errors are spread thinly across many fragments or piled onto a few is the difference
between "the method is too weak" (model work) and "these specific ideas are not learnable from
the data we have" (library work, and these are the fragments to write more of). No intervals:
a fragment is one cluster, so an interval over its own examples measures nothing.

108 of 351 decisive fragments were got wrong at least once.

`length_only__shuffled`: 3960 errors across 108 of 351 decisive fragments. Half of them fall on **39** fragments (an even spread would be 54.0); the worst ten carry 15.8% of all errors.

| fragment | library | sub-class | truth | correct | accuracy | predicted as |
|---|---|---|---|---|---|---|
| `nocturia_false:75848908` | `nocturia_false` | -- | false | 0/73 | 0.0% | null 73 |
| `nocturia_false:0105f271` | `nocturia_false` | -- | false | 0/68 | 0.0% | null 68 |
| `nocturia_false:3a70bcb2` | `nocturia_false` | -- | false | 0/66 | 0.0% | null 66 |
| `nocturia_false:3e89d247` | `nocturia_false` | -- | false | 0/65 | 0.0% | null 65 |
| `nocturia_false:776d32bb` | `nocturia_false` | -- | false | 0/64 | 0.0% | null 64 |
| `nocturia_false:e6fd6a44` | `nocturia_false` | -- | false | 0/60 | 0.0% | null 60 |
| `nocturia_false:79441d6a` | `nocturia_false` | -- | false | 0/59 | 0.0% | null 59 |
| `nocturia_false:76105311` | `nocturia_false` | -- | false | 0/57 | 0.0% | null 57 |
| `nocturia_false:876119ca` | `nocturia_false` | -- | false | 0/57 | 0.0% | null 57 |
| `nocturia_false:cd9ee762` | `nocturia_false` | -- | false | 0/57 | 0.0% | null 57 |
| `nocturia_false:3fbd0758` | `nocturia_false` | -- | false | 0/55 | 0.0% | null 55 |
| `nocturia_false:31c155d0` | `nocturia_false` | -- | false | 0/53 | 0.0% | null 53 |
| `nocturia_false:3aab37fe` | `nocturia_false` | -- | false | 0/53 | 0.0% | null 53 |
| `nocturia_false:cddf064c` | `nocturia_false` | -- | false | 0/53 | 0.0% | null 53 |
| `nocturia_false:01f605e7` | `nocturia_false` | -- | false | 0/52 | 0.0% | null 52 |
| `nocturia_false:a9555a97` | `nocturia_false` | -- | false | 0/52 | 0.0% | null 52 |
| `nocturia_false:59e83d34` | `nocturia_false` | -- | false | 0/51 | 0.0% | null 51 |
| `nocturia_false:a9489bdd` | `nocturia_false` | -- | false | 0/51 | 0.0% | null 51 |
| `nocturia_false:21180255` | `nocturia_false` | -- | false | 0/50 | 0.0% | null 50 |
| `nocturia_false:98d02ead` | `nocturia_false` | -- | false | 0/50 | 0.0% | null 50 |
| `nocturia_false:48f35b91` | `nocturia_false` | -- | false | 0/49 | 0.0% | null 49 |
| `nocturia_false:55832b2b` | `nocturia_false` | -- | false | 0/49 | 0.0% | null 49 |
| `nocturia_false:b11139a0` | `nocturia_false` | -- | false | 0/49 | 0.0% | null 49 |
| `nocturia_true:86e1cd53` | `nocturia_true` | -- | true | 0/49 | 0.0% | null 49 |
| `nocturia_false:1bd2f6f8` | `nocturia_false` | -- | false | 0/48 | 0.0% | null 48 |
| `nocturia_false:b1f7e93f` | `nocturia_false` | -- | false | 0/48 | 0.0% | null 48 |
| `nocturia_false:c6a4c61b` | `nocturia_false` | -- | false | 0/48 | 0.0% | null 48 |
| `nocturia_false:eff52ced` | `nocturia_false` | -- | false | 0/46 | 0.0% | null 46 |
| `nocturia_true:c3f73311` | `nocturia_true` | -- | true | 0/46 | 0.0% | null 46 |
| `nocturia_false:5e819a32` | `nocturia_false` | -- | false | 0/45 | 0.0% | null 45 |
| `nocturia_false:99cd439f` | `nocturia_false` | -- | false | 0/45 | 0.0% | null 45 |
| `nocturia_false:bf88ba0d` | `nocturia_false` | -- | false | 0/45 | 0.0% | null 45 |
| `nocturia_false:f4140180` | `nocturia_false` | -- | false | 0/45 | 0.0% | null 45 |
| `nocturia_true:594869e7` | `nocturia_true` | -- | true | 0/44 | 0.0% | null 44 |
| `nocturia_false:1a41970c` | `nocturia_false` | -- | false | 0/43 | 0.0% | null 43 |
| `nocturia_false:4a12f37a` | `nocturia_false` | -- | false | 0/43 | 0.0% | null 43 |
| `nocturia_false:dfdc943b` | `nocturia_false` | -- | false | 0/42 | 0.0% | null 42 |
| `nocturia_false:08a0b22d` | `nocturia_false` | -- | false | 0/41 | 0.0% | null 41 |
| `nocturia_false:1cb7de3b` | `nocturia_false` | -- | false | 0/41 | 0.0% | null 41 |
| `nocturia_false:70c4843c` | `nocturia_false` | -- | false | 0/41 | 0.0% | null 41 |

*68 further fragments with at least one error are in the JSON sidecar; every fragment is there regardless of score.*

## `tfidf_logreg__shuffled`

TF-IDF unigrams and bigrams into logistic regression. Tests whether the dataset is keyword-solvable. Its overall accuracy is close to uninformative; the `null_ambiguous` slice is the number that matters. **Negative control:** trained on permuted training labels (seed 7) and evaluated on the unpermuted test split, where it must land at chance.

Decision-rule margins selected per fold (on each fold's own validation split): 0.0.
Every fold selected margin 0, so the ruled and raw views below are the same decisions. That is a finding rather than a bug: no margin improved macro-F1 without worsening the `null -> true` rate.

*Confusion matrix, raw argmax*

|  | pred false | pred true | pred null | total |
|---|---|---|---|---|
| **truth false** | 0 | 0 | 2479 | 2479 |
| **truth true** | 1 | 0 | 1480 | 1481 |
| **truth null** | 4 | 0 | 6036 | 6040 |
| **total** | 5 | 0 | 9995 | 10000 |

`null -> true`: 0 of 6040 truly-null examples (0.00%).

*Confusion matrix, after the decision rule*

|  | pred false | pred true | pred null | total |
|---|---|---|---|---|
| **truth false** | 0 | 0 | 2479 | 2479 |
| **truth true** | 1 | 0 | 1480 | 1481 |
| **truth null** | 4 | 0 | 6036 | 6040 |
| **total** | 5 | 0 | 9995 | 10000 |

`null -> true`: 0 of 6040 truly-null examples (0.00%).

### Per class, after the decision rule

| class | support | predicted | precision | recall | F1 |
|---|---|---|---|---|---|
| `false` | 2479 | 5 | 0.0% | 0.0% | 0.0% |
| `true` | 1481 | 0 | -- | 0.0% | 0.0% |
| `null` | 6040 | 9995 | 60.4% | 99.9% | 75.3% |

### By label mode

| label mode | n | eff n | accuracy [95% CI] |
|---|---|---|---|
| false | 2479 | **54** | 0.0% [0.0%, 0.0%] |
| null_ambiguous | 3062 | **243** | 99.9% [99.7%, 100.0%] |
| null_structural | 2978 | **1** | 100.0% [100.0%, 100.0%] |
| true | 1481 | **54** | 0.0% [0.0%, 0.0%] |

### By null sub-class

| sub-class | n | eff n | null recall [95% CI] |
|---|---|---|---|
| attribution | 657 | **51** | 99.7% [99.0%, 100.0%] |
| hedged | 588 | **47** | 100.0% [100.0%, 100.0%] |
| historical | 554 | **46** | 100.0% [100.0%, 100.0%] |
| metaphor | 684 | **52** | 99.9% [99.5%, 100.0%] |
| third_party | 579 | **47** | 100.0% [100.0%, 100.0%] |

### By fragment library

| library | n | eff n | accuracy [95% CI] |
|---|---|---|---|
| nocturia_false | 2479 | **54** | 0.0% [0.0%, 0.0%] |
| nocturia_null_attribution | 657 | **51** | 99.7% [99.0%, 100.0%] |
| nocturia_null_hedged | 588 | **47** | 100.0% [100.0%, 100.0%] |
| nocturia_null_historical | 554 | **46** | 100.0% [100.0%, 100.0%] |
| nocturia_null_metaphor | 684 | **52** | 99.9% [99.5%, 100.0%] |
| nocturia_null_thirdparty | 579 | **47** | 100.0% [100.0%, 100.0%] |
| nocturia_true | 1481 | **54** | 0.0% [0.0%, 0.0%] |
| (none) | 2978 | **1** | 100.0% [100.0%, 100.0%] |

### Per-fragment errors (worst first)

Whether errors are spread thinly across many fragments or piled onto a few is the difference
between "the method is too weak" (model work) and "these specific ideas are not learnable from
the data we have" (library work, and these are the fragments to write more of). No intervals:
a fragment is one cluster, so an interval over its own examples measures nothing.

110 of 351 decisive fragments were got wrong at least once.

`tfidf_logreg__shuffled`: 3963 errors across 110 of 351 decisive fragments. Half of them fall on **39** fragments (an even spread would be 55.0); the worst ten carry 15.8% of all errors.

| fragment | library | sub-class | truth | correct | accuracy | predicted as |
|---|---|---|---|---|---|---|
| `nocturia_false:75848908` | `nocturia_false` | -- | false | 0/73 | 0.0% | null 73 |
| `nocturia_false:0105f271` | `nocturia_false` | -- | false | 0/68 | 0.0% | null 68 |
| `nocturia_false:3a70bcb2` | `nocturia_false` | -- | false | 0/66 | 0.0% | null 66 |
| `nocturia_false:3e89d247` | `nocturia_false` | -- | false | 0/65 | 0.0% | null 65 |
| `nocturia_false:776d32bb` | `nocturia_false` | -- | false | 0/64 | 0.0% | null 64 |
| `nocturia_false:e6fd6a44` | `nocturia_false` | -- | false | 0/60 | 0.0% | null 60 |
| `nocturia_false:79441d6a` | `nocturia_false` | -- | false | 0/59 | 0.0% | null 59 |
| `nocturia_false:76105311` | `nocturia_false` | -- | false | 0/57 | 0.0% | null 57 |
| `nocturia_false:876119ca` | `nocturia_false` | -- | false | 0/57 | 0.0% | null 57 |
| `nocturia_false:cd9ee762` | `nocturia_false` | -- | false | 0/57 | 0.0% | null 57 |
| `nocturia_false:3fbd0758` | `nocturia_false` | -- | false | 0/55 | 0.0% | null 55 |
| `nocturia_false:31c155d0` | `nocturia_false` | -- | false | 0/53 | 0.0% | null 53 |
| `nocturia_false:3aab37fe` | `nocturia_false` | -- | false | 0/53 | 0.0% | null 53 |
| `nocturia_false:cddf064c` | `nocturia_false` | -- | false | 0/53 | 0.0% | null 53 |
| `nocturia_false:01f605e7` | `nocturia_false` | -- | false | 0/52 | 0.0% | null 52 |
| `nocturia_false:a9555a97` | `nocturia_false` | -- | false | 0/52 | 0.0% | null 52 |
| `nocturia_false:59e83d34` | `nocturia_false` | -- | false | 0/51 | 0.0% | null 51 |
| `nocturia_false:a9489bdd` | `nocturia_false` | -- | false | 0/51 | 0.0% | null 51 |
| `nocturia_false:21180255` | `nocturia_false` | -- | false | 0/50 | 0.0% | null 50 |
| `nocturia_false:98d02ead` | `nocturia_false` | -- | false | 0/50 | 0.0% | null 50 |
| `nocturia_false:48f35b91` | `nocturia_false` | -- | false | 0/49 | 0.0% | null 49 |
| `nocturia_false:55832b2b` | `nocturia_false` | -- | false | 0/49 | 0.0% | null 49 |
| `nocturia_false:b11139a0` | `nocturia_false` | -- | false | 0/49 | 0.0% | null 49 |
| `nocturia_true:86e1cd53` | `nocturia_true` | -- | true | 0/49 | 0.0% | null 49 |
| `nocturia_false:1bd2f6f8` | `nocturia_false` | -- | false | 0/48 | 0.0% | null 48 |
| `nocturia_false:b1f7e93f` | `nocturia_false` | -- | false | 0/48 | 0.0% | null 48 |
| `nocturia_false:c6a4c61b` | `nocturia_false` | -- | false | 0/48 | 0.0% | null 48 |
| `nocturia_false:eff52ced` | `nocturia_false` | -- | false | 0/46 | 0.0% | null 46 |
| `nocturia_true:c3f73311` | `nocturia_true` | -- | true | 0/46 | 0.0% | null 46 |
| `nocturia_false:5e819a32` | `nocturia_false` | -- | false | 0/45 | 0.0% | null 45 |
| `nocturia_false:99cd439f` | `nocturia_false` | -- | false | 0/45 | 0.0% | null 45 |
| `nocturia_false:bf88ba0d` | `nocturia_false` | -- | false | 0/45 | 0.0% | null 45 |
| `nocturia_false:f4140180` | `nocturia_false` | -- | false | 0/45 | 0.0% | null 45 |
| `nocturia_true:594869e7` | `nocturia_true` | -- | true | 0/44 | 0.0% | null 44 |
| `nocturia_false:1a41970c` | `nocturia_false` | -- | false | 0/43 | 0.0% | null 43 |
| `nocturia_false:4a12f37a` | `nocturia_false` | -- | false | 0/43 | 0.0% | null 43 |
| `nocturia_false:dfdc943b` | `nocturia_false` | -- | false | 0/42 | 0.0% | null 42 |
| `nocturia_false:08a0b22d` | `nocturia_false` | -- | false | 0/41 | 0.0% | null 41 |
| `nocturia_false:1cb7de3b` | `nocturia_false` | -- | false | 0/41 | 0.0% | null 41 |
| `nocturia_false:70c4843c` | `nocturia_false` | -- | false | 0/41 | 0.0% | null 41 |

*70 further fragments with at least one error are in the JSON sidecar; every fragment is there regardless of score.*

## `arm_b_finetune@c0.0-d0.0`

`roberta-base` with **every layer unfrozen**, mean-pooled, with the same `Linear(768, 3)` head -- 110M trainable parameters against Arm A's 2,307. Three epochs at batch 32, learning rate 2e-5, 10% linear warmup, AdamW, fp32. No gradient checkpointing, no 8-bit optimiser, no LoRA, no gradient accumulation: the full model fits in 12GB with room to spare, so anything that reads like a compute compromise would be a mistake rather than a saving. This is the arm that separates "the fragment libraries are the bottleneck" from "the method is too weak": if a fully fine-tuned encoder still cannot read third-party attribution, tense or metaphor, the limit is in the ideas the libraries contain and the fix is library work, not model work.

Decision-rule margins selected per fold (on each fold's own validation split): 0.0, 0.2, 0.25, 0.5.

*Confusion matrix, raw argmax*

|  | pred false | pred true | pred null | total |
|---|---|---|---|---|
| **truth false** | 2083 | 60 | 336 | 2479 |
| **truth true** | 32 | 1056 | 393 | 1481 |
| **truth null** | 75 | 274 | 5691 | 6040 |
| **total** | 2190 | 1390 | 6420 | 10000 |

`null -> true`: 274 of 6040 truly-null examples (4.54%).

*Confusion matrix, after the decision rule*

|  | pred false | pred true | pred null | total |
|---|---|---|---|---|
| **truth false** | 2085 | 58 | 336 | 2479 |
| **truth true** | 32 | 1050 | 399 | 1481 |
| **truth null** | 75 | 267 | 5698 | 6040 |
| **total** | 2192 | 1375 | 6433 | 10000 |

`null -> true`: 267 of 6040 truly-null examples (4.42%).

### Per class, after the decision rule

| class | support | predicted | precision | recall | F1 |
|---|---|---|---|---|---|
| `false` | 2479 | 2192 | 95.1% | 84.1% | 89.3% |
| `true` | 1481 | 1375 | 76.4% | 70.9% | 73.5% |
| `null` | 6040 | 6433 | 88.6% | 94.3% | 91.4% |

### By label mode

| label mode | n | eff n | accuracy [95% CI] |
|---|---|---|---|
| false | 2479 | **54** | 84.1% [75.4%, 92.1%] |
| null_ambiguous | 3062 | **243** | 89.6% [86.0%, 93.0%] |
| null_structural | 2978 | **1** | 99.2% [99.2%, 99.2%] |
| true | 1481 | **54** | 70.9% [58.9%, 82.1%] |

### By null sub-class

| sub-class | n | eff n | null recall [95% CI] |
|---|---|---|---|
| attribution | 657 | **51** | 85.5% [74.8%, 93.7%] |
| hedged | 588 | **47** | 86.1% [77.4%, 93.4%] |
| historical | 554 | **46** | 93.3% [85.5%, 99.5%] |
| metaphor | 684 | **52** | 93.9% [88.1%, 98.3%] |
| third_party | 579 | **47** | 89.3% [79.4%, 97.4%] |

### By fragment library

| library | n | eff n | accuracy [95% CI] |
|---|---|---|---|
| nocturia_false | 2479 | **54** | 84.1% [75.4%, 92.1%] |
| nocturia_null_attribution | 657 | **51** | 85.5% [74.8%, 93.7%] |
| nocturia_null_hedged | 588 | **47** | 86.1% [77.4%, 93.4%] |
| nocturia_null_historical | 554 | **46** | 93.3% [85.5%, 99.5%] |
| nocturia_null_metaphor | 684 | **52** | 93.9% [88.1%, 98.3%] |
| nocturia_null_thirdparty | 579 | **47** | 89.3% [79.4%, 97.4%] |
| nocturia_true | 1481 | **54** | 70.9% [58.9%, 82.1%] |
| (none) | 2978 | **1** | 99.2% [99.2%, 99.2%] |

### Per-fragment errors (worst first)

Whether errors are spread thinly across many fragments or piled onto a few is the difference
between "the method is too weak" (model work) and "these specific ideas are not learnable from
the data we have" (library work, and these are the fragments to write more of). No intervals:
a fragment is one cluster, so an interval over its own examples measures nothing.

90 of 351 decisive fragments were got wrong at least once.

`arm_b_finetune@c0.0-d0.0`: 1143 errors across 90 of 351 decisive fragments. Half of them fall on **16** fragments (an even spread would be 45.0); the worst ten carry 36.3% of all errors.

| fragment | library | sub-class | truth | correct | accuracy | predicted as |
|---|---|---|---|---|---|---|
| `nocturia_false:3aab37fe` | `nocturia_false` | -- | false | 0/53 | 0.0% | null 53 |
| `nocturia_true:86e1cd53` | `nocturia_true` | -- | true | 0/49 | 0.0% | null 49 |
| `nocturia_false:1bd2f6f8` | `nocturia_false` | -- | false | 0/48 | 0.0% | null 48 |
| `nocturia_false:deb3785c` | `nocturia_false` | -- | false | 0/39 | 0.0% | null 39 |
| `nocturia_true:0740576d` | `nocturia_true` | -- | true | 0/38 | 0.0% | null 38 |
| `nocturia_true:f3e4ee3e` | `nocturia_true` | -- | true | 0/35 | 0.0% | null 35 |
| `nocturia_true:126e0cfb` | `nocturia_true` | -- | true | 0/33 | 0.0% | null 33 |
| `nocturia_true:54de6227` | `nocturia_true` | -- | true | 0/30 | 0.0% | false 30 |
| `nocturia_true:a2f6ab3f` | `nocturia_true` | -- | true | 0/30 | 0.0% | null 30 |
| `nocturia_false:5efba823` | `nocturia_false` | -- | false | 0/29 | 0.0% | null 29 |
| `nocturia_false:bc25d693` | `nocturia_false` | -- | false | 0/29 | 0.0% | true 29 |
| `nocturia_true:e853d9c0` | `nocturia_true` | -- | true | 0/27 | 0.0% | null 27 |
| `nocturia_true:4506c1ce` | `nocturia_true` | -- | true | 0/26 | 0.0% | null 26 |
| `nocturia_true:efa44ced` | `nocturia_true` | -- | true | 0/24 | 0.0% | null 24 |
| `nocturia_null_attribution:7fc5b7ab` | `nocturia_null_attribution` | attribution | null | 0/21 | 0.0% | true 21 |
| `nocturia_true:f81d11be` | `nocturia_true` | -- | true | 0/20 | 0.0% | null 20 |
| `nocturia_null_thirdparty:49d8e5c9` | `nocturia_null_thirdparty` | third_party | null | 0/18 | 0.0% | true 18 |
| `nocturia_null_attribution:0dfc44e6` | `nocturia_null_attribution` | attribution | null | 0/17 | 0.0% | true 17 |
| `nocturia_true:31923f27` | `nocturia_true` | -- | true | 0/17 | 0.0% | null 17 |
| `nocturia_null_thirdparty:776f85a8` | `nocturia_null_thirdparty` | third_party | null | 0/15 | 0.0% | true 15 |
| `nocturia_null_attribution:9017e283` | `nocturia_null_attribution` | attribution | null | 0/13 | 0.0% | true 13 |
| `nocturia_null_historical:0e6d519c` | `nocturia_null_historical` | historical | null | 0/13 | 0.0% | true 13 |
| `nocturia_null_hedged:d376c840` | `nocturia_null_hedged` | hedged | null | 0/12 | 0.0% | true 12 |
| `nocturia_null_historical:bdf2082b` | `nocturia_null_historical` | historical | null | 0/12 | 0.0% | true 12 |
| `nocturia_null_hedged:20ad42fe` | `nocturia_null_hedged` | hedged | null | 0/9 | 0.0% | true 9 |
| `nocturia_null_thirdparty:b79815e8` | `nocturia_null_thirdparty` | third_party | null | 0/9 | 0.0% | true 9 |
| `nocturia_null_metaphor:03b3b8c4` | `nocturia_null_metaphor` | metaphor | null | 1/13 | 7.7% | false 12, null 1 |
| `nocturia_false:99cd439f` | `nocturia_false` | -- | false | 4/45 | 8.9% | false 4, null 41 |
| `nocturia_null_attribution:7798eddd` | `nocturia_null_attribution` | attribution | null | 1/11 | 9.1% | true 10, null 1 |
| `nocturia_null_hedged:31bc996d` | `nocturia_null_hedged` | hedged | null | 1/11 | 9.1% | true 10, null 1 |
| `nocturia_null_attribution:e51cceef` | `nocturia_null_attribution` | attribution | null | 2/15 | 13.3% | true 13, null 2 |
| `nocturia_null_metaphor:3c29e25d` | `nocturia_null_metaphor` | metaphor | null | 1/7 | 14.3% | true 6, null 1 |
| `nocturia_true:86863ee3` | `nocturia_true` | -- | true | 5/33 | 15.2% | true 5, null 28 |
| `nocturia_false:e6fd6a44` | `nocturia_false` | -- | false | 11/60 | 18.3% | false 11, null 49 |
| `nocturia_null_hedged:b85fb3a3` | `nocturia_null_hedged` | hedged | null | 4/16 | 25.0% | true 12, null 4 |
| `nocturia_null_historical:a2c3c56b` | `nocturia_null_historical` | historical | null | 3/12 | 25.0% | false 9, null 3 |
| `nocturia_null_hedged:58ffb85e` | `nocturia_null_hedged` | hedged | null | 2/8 | 25.0% | true 6, null 2 |
| `nocturia_null_hedged:0d36ef4c` | `nocturia_null_hedged` | hedged | null | 3/11 | 27.3% | false 8, null 3 |
| `nocturia_null_thirdparty:54eb6d2b` | `nocturia_null_thirdparty` | third_party | null | 6/20 | 30.0% | true 14, null 6 |
| `nocturia_null_hedged:841744b2` | `nocturia_null_hedged` | hedged | null | 3/9 | 33.3% | false 4, true 2, null 3 |

*50 further fragments with at least one error are in the JSON sidecar; every fragment is there regardless of score.*

## `arm_b_finetune@c0.0-d0.3`

`roberta-base` with **every layer unfrozen**, mean-pooled, with the same `Linear(768, 3)` head -- 110M trainable parameters against Arm A's 2,307. Three epochs at batch 32, learning rate 2e-5, 10% linear warmup, AdamW, fp32. No gradient checkpointing, no 8-bit optimiser, no LoRA, no gradient accumulation: the full model fits in 12GB with room to spare, so anything that reads like a compute compromise would be a mistake rather than a saving. This is the arm that separates "the fragment libraries are the bottleneck" from "the method is too weak": if a fully fine-tuned encoder still cannot read third-party attribution, tense or metaphor, the limit is in the ideas the libraries contain and the fix is library work, not model work.

Decision-rule margins selected per fold (on each fold's own validation split): 0.0, 0.15, 0.55, 0.85.

*Confusion matrix, raw argmax*

|  | pred false | pred true | pred null | total |
|---|---|---|---|---|
| **truth false** | 2245 | 96 | 138 | 2479 |
| **truth true** | 34 | 1201 | 246 | 1481 |
| **truth null** | 53 | 283 | 5704 | 6040 |
| **total** | 2332 | 1580 | 6088 | 10000 |

`null -> true`: 283 of 6040 truly-null examples (4.69%).

*Confusion matrix, after the decision rule*

|  | pred false | pred true | pred null | total |
|---|---|---|---|---|
| **truth false** | 2256 | 84 | 139 | 2479 |
| **truth true** | 34 | 1198 | 249 | 1481 |
| **truth null** | 54 | 262 | 5724 | 6040 |
| **total** | 2344 | 1544 | 6112 | 10000 |

`null -> true`: 262 of 6040 truly-null examples (4.34%).

### Per class, after the decision rule

| class | support | predicted | precision | recall | F1 |
|---|---|---|---|---|---|
| `false` | 2479 | 2344 | 96.2% | 91.0% | 93.6% |
| `true` | 1481 | 1544 | 77.6% | 80.9% | 79.2% |
| `null` | 6040 | 6112 | 93.7% | 94.8% | 94.2% |

### By label mode

| label mode | n | eff n | accuracy [95% CI] |
|---|---|---|---|
| false | 2479 | **130** | 91.0% [85.2%, 96.1%] |
| null_ambiguous | 3062 | **243** | 90.1% [86.4%, 93.5%] |
| null_structural | 2978 | **1** | 99.6% [99.6%, 99.6%] |
| true | 1481 | **138** | 80.9% [72.2%, 89.6%] |

### By null sub-class

| sub-class | n | eff n | null recall [95% CI] |
|---|---|---|---|
| attribution | 657 | **51** | 88.1% [78.1%, 96.1%] |
| hedged | 588 | **47** | 85.7% [76.9%, 93.3%] |
| historical | 554 | **46** | 89.5% [80.3%, 96.7%] |
| metaphor | 684 | **52** | 93.9% [87.7%, 98.8%] |
| third_party | 579 | **47** | 92.7% [83.4%, 99.5%] |

### By fragment library

| library | n | eff n | accuracy [95% CI] |
|---|---|---|---|
| declarative_v1 | 1232 | **160** | 100.0% [100.0%, 100.0%] |
| nocturia_false | 1707 | **54** | 86.9% [78.4%, 94.2%] |
| nocturia_null_attribution | 657 | **51** | 88.1% [78.1%, 96.1%] |
| nocturia_null_hedged | 588 | **47** | 85.7% [76.9%, 93.3%] |
| nocturia_null_historical | 554 | **46** | 89.5% [80.3%, 96.7%] |
| nocturia_null_metaphor | 684 | **52** | 93.9% [87.7%, 98.8%] |
| nocturia_null_thirdparty | 579 | **47** | 92.7% [83.4%, 99.5%] |
| nocturia_true | 1021 | **54** | 72.3% [60.4%, 83.7%] |
| (none) | 2978 | **1** | 99.6% [99.6%, 99.6%] |

### Per-fragment errors (worst first)

Whether errors are spread thinly across many fragments or piled onto a few is the difference
between "the method is too weak" (model work) and "these specific ideas are not learnable from
the data we have" (library work, and these are the fragments to write more of). No intervals:
a fragment is one cluster, so an interval over its own examples measures nothing.

83 of 749 decisive fragments were got wrong at least once.

`arm_b_finetune@c0.0-d0.3`: 810 errors across 83 of 749 decisive fragments. Half of them fall on **18** fragments (an even spread would be 41.5); the worst ten carry 33.1% of all errors.

| fragment | library | sub-class | truth | correct | accuracy | predicted as |
|---|---|---|---|---|---|---|
| `nocturia_false:3aab37fe` | `nocturia_false` | -- | false | 0/44 | 0.0% | null 44 |
| `nocturia_true:86e1cd53` | `nocturia_true` | -- | true | 0/29 | 0.0% | null 29 |
| `nocturia_true:126e0cfb` | `nocturia_true` | -- | true | 0/27 | 0.0% | null 27 |
| `nocturia_true:0c394532` | `nocturia_true` | -- | true | 0/25 | 0.0% | false 25 |
| `nocturia_true:f3e4ee3e` | `nocturia_true` | -- | true | 0/22 | 0.0% | null 22 |
| `nocturia_false:bc25d693` | `nocturia_false` | -- | false | 0/21 | 0.0% | true 21 |
| `nocturia_null_attribution:7fc5b7ab` | `nocturia_null_attribution` | attribution | null | 0/21 | 0.0% | true 21 |
| `nocturia_null_thirdparty:54eb6d2b` | `nocturia_null_thirdparty` | third_party | null | 0/20 | 0.0% | true 20 |
| `nocturia_true:e853d9c0` | `nocturia_true` | -- | true | 0/20 | 0.0% | null 20 |
| `nocturia_true:0740576d` | `nocturia_true` | -- | true | 0/18 | 0.0% | null 18 |
| `nocturia_false:2e5a7e5a` | `nocturia_false` | -- | false | 0/17 | 0.0% | true 15, null 2 |
| `nocturia_false:deb3785c` | `nocturia_false` | -- | false | 0/17 | 0.0% | null 17 |
| `nocturia_null_attribution:0dfc44e6` | `nocturia_null_attribution` | attribution | null | 0/17 | 0.0% | true 17 |
| `nocturia_true:f81d11be` | `nocturia_true` | -- | true | 0/16 | 0.0% | null 16 |
| `nocturia_null_thirdparty:776f85a8` | `nocturia_null_thirdparty` | third_party | null | 0/15 | 0.0% | false 15 |
| `nocturia_null_historical:0e6d519c` | `nocturia_null_historical` | historical | null | 0/13 | 0.0% | true 13 |
| `nocturia_null_metaphor:03b3b8c4` | `nocturia_null_metaphor` | metaphor | null | 0/13 | 0.0% | false 13 |
| `nocturia_null_hedged:d376c840` | `nocturia_null_hedged` | hedged | null | 0/12 | 0.0% | true 12 |
| `nocturia_null_historical:bdf2082b` | `nocturia_null_historical` | historical | null | 0/12 | 0.0% | true 12 |
| `nocturia_null_metaphor:c666d342` | `nocturia_null_metaphor` | metaphor | null | 0/12 | 0.0% | true 12 |
| `nocturia_null_hedged:cf1d2bb8` | `nocturia_null_hedged` | hedged | null | 0/10 | 0.0% | true 10 |
| `nocturia_null_historical:a3dbb0b8` | `nocturia_null_historical` | historical | null | 0/10 | 0.0% | false 10 |
| `nocturia_null_hedged:20ad42fe` | `nocturia_null_hedged` | hedged | null | 0/9 | 0.0% | true 9 |
| `nocturia_null_historical:9c1540ad` | `nocturia_null_historical` | historical | null | 0/9 | 0.0% | true 9 |
| `nocturia_true:1e05f648` | `nocturia_true` | -- | true | 0/7 | 0.0% | null 7 |
| `nocturia_false:14ecd3b3` | `nocturia_false` | -- | false | 1/22 | 4.5% | false 1, true 21 |
| `nocturia_true:efa44ced` | `nocturia_true` | -- | true | 1/19 | 5.3% | true 1, null 18 |
| `nocturia_null_attribution:e51cceef` | `nocturia_null_attribution` | attribution | null | 1/15 | 6.7% | true 14, null 1 |
| `nocturia_true:17169e22` | `nocturia_true` | -- | true | 1/14 | 7.1% | true 1, null 13 |
| `nocturia_false:5efba823` | `nocturia_false` | -- | false | 2/25 | 8.0% | false 2, null 23 |
| `nocturia_null_attribution:b68c3406` | `nocturia_null_attribution` | attribution | null | 1/12 | 8.3% | true 11, null 1 |
| `nocturia_null_metaphor:a88b521b` | `nocturia_null_metaphor` | metaphor | null | 1/10 | 10.0% | false 9, null 1 |
| `nocturia_null_historical:809a17dd` | `nocturia_null_historical` | historical | null | 1/8 | 12.5% | true 7, null 1 |
| `nocturia_false:e6fd6a44` | `nocturia_false` | -- | false | 4/30 | 13.3% | false 4, null 26 |
| `nocturia_true:c3f73311` | `nocturia_true` | -- | true | 4/30 | 13.3% | true 4, null 26 |
| `nocturia_null_hedged:31bc996d` | `nocturia_null_hedged` | hedged | null | 2/11 | 18.2% | true 9, null 2 |
| `nocturia_null_hedged:b85fb3a3` | `nocturia_null_hedged` | hedged | null | 3/16 | 18.8% | true 13, null 3 |
| `nocturia_null_hedged:841744b2` | `nocturia_null_hedged` | hedged | null | 2/9 | 22.2% | true 7, null 2 |
| `nocturia_true:86863ee3` | `nocturia_true` | -- | true | 5/18 | 27.8% | true 5, null 13 |
| `nocturia_false:b1f7e93f` | `nocturia_false` | -- | false | 11/36 | 30.6% | false 11, true 25 |

*43 further fragments with at least one error are in the JSON sidecar; every fragment is there regardless of score.*

## `arm_b_finetune@c0.5-d0.0`

`roberta-base` with **every layer unfrozen**, mean-pooled, with the same `Linear(768, 3)` head -- 110M trainable parameters against Arm A's 2,307. Three epochs at batch 32, learning rate 2e-5, 10% linear warmup, AdamW, fp32. No gradient checkpointing, no 8-bit optimiser, no LoRA, no gradient accumulation: the full model fits in 12GB with room to spare, so anything that reads like a compute compromise would be a mistake rather than a saving. This is the arm that separates "the fragment libraries are the bottleneck" from "the method is too weak": if a fully fine-tuned encoder still cannot read third-party attribution, tense or metaphor, the limit is in the ideas the libraries contain and the fix is library work, not model work.

Decision-rule margins selected per fold (on each fold's own validation split): 0.05, 0.3, 0.6, 0.65.

*Confusion matrix, raw argmax*

|  | pred false | pred true | pred null | total |
|---|---|---|---|---|
| **truth false** | 1841 | 131 | 507 | 2479 |
| **truth true** | 6 | 1169 | 306 | 1481 |
| **truth null** | 39 | 277 | 5724 | 6040 |
| **total** | 1886 | 1577 | 6537 | 10000 |

`null -> true`: 277 of 6040 truly-null examples (4.59%).

*Confusion matrix, after the decision rule*

|  | pred false | pred true | pred null | total |
|---|---|---|---|---|
| **truth false** | 1851 | 118 | 510 | 2479 |
| **truth true** | 7 | 1154 | 320 | 1481 |
| **truth null** | 46 | 258 | 5736 | 6040 |
| **total** | 1904 | 1530 | 6566 | 10000 |

`null -> true`: 258 of 6040 truly-null examples (4.27%).

### Per class, after the decision rule

| class | support | predicted | precision | recall | F1 |
|---|---|---|---|---|---|
| `false` | 2479 | 1904 | 97.2% | 74.7% | 84.5% |
| `true` | 1481 | 1530 | 75.4% | 77.9% | 76.7% |
| `null` | 6040 | 6566 | 87.4% | 95.0% | 91.0% |

### By label mode

| label mode | n | eff n | accuracy [95% CI] |
|---|---|---|---|
| false | 2479 | **54** | 74.7% [63.7%, 85.5%] |
| null_ambiguous | 3062 | **243** | 90.5% [86.8%, 93.9%] |
| null_structural | 2978 | **1** | 99.6% [99.6%, 99.6%] |
| true | 1481 | **54** | 77.9% [66.8%, 88.0%] |

### By null sub-class

| sub-class | n | eff n | null recall [95% CI] |
|---|---|---|---|
| attribution | 655 | **51** | 88.4% [78.6%, 96.2%] |
| hedged | 587 | **47** | 86.9% [76.9%, 94.7%] |
| historical | 558 | **46** | 90.3% [81.3%, 97.1%] |
| metaphor | 684 | **52** | 96.2% [90.9%, 99.9%] |
| third_party | 578 | **47** | 89.8% [80.3%, 97.6%] |

### By fragment library

| library | n | eff n | accuracy [95% CI] |
|---|---|---|---|
| nocturia_false | 2479 | **54** | 74.7% [63.7%, 85.5%] |
| nocturia_null_attribution | 655 | **51** | 88.4% [78.6%, 96.2%] |
| nocturia_null_hedged | 587 | **47** | 86.9% [76.9%, 94.7%] |
| nocturia_null_historical | 558 | **46** | 90.3% [81.3%, 97.1%] |
| nocturia_null_metaphor | 684 | **52** | 96.2% [90.9%, 99.9%] |
| nocturia_null_thirdparty | 578 | **47** | 89.8% [80.3%, 97.6%] |
| nocturia_true | 1481 | **54** | 77.9% [66.8%, 88.0%] |
| (none) | 2978 | **1** | 99.6% [99.6%, 99.6%] |

### Per-fragment errors (worst first)

Whether errors are spread thinly across many fragments or piled onto a few is the difference
between "the method is too weak" (model work) and "these specific ideas are not learnable from
the data we have" (library work, and these are the fragments to write more of). No intervals:
a fragment is one cluster, so an interval over its own examples measures nothing.

81 of 351 decisive fragments were got wrong at least once.

`arm_b_finetune@c0.5-d0.0`: 1247 errors across 81 of 351 decisive fragments. Half of them fall on **15** fragments (an even spread would be 40.5); the worst ten carry 37.8% of all errors.

| fragment | library | sub-class | truth | correct | accuracy | predicted as |
|---|---|---|---|---|---|---|
| `nocturia_false:e6fd6a44` | `nocturia_false` | -- | false | 0/64 | 0.0% | null 64 |
| `nocturia_false:3aab37fe` | `nocturia_false` | -- | false | 0/50 | 0.0% | null 50 |
| `nocturia_true:86e1cd53` | `nocturia_true` | -- | true | 0/49 | 0.0% | false 1, null 48 |
| `nocturia_false:1bd2f6f8` | `nocturia_false` | -- | false | 0/47 | 0.0% | null 47 |
| `nocturia_false:98d02ead` | `nocturia_false` | -- | false | 0/46 | 0.0% | null 46 |
| `nocturia_false:bf88ba0d` | `nocturia_false` | -- | false | 0/45 | 0.0% | null 45 |
| `nocturia_false:1cb7de3b` | `nocturia_false` | -- | false | 0/43 | 0.0% | null 43 |
| `nocturia_false:deb3785c` | `nocturia_false` | -- | false | 0/41 | 0.0% | null 41 |
| `nocturia_true:0740576d` | `nocturia_true` | -- | true | 0/38 | 0.0% | null 38 |
| `nocturia_true:f3e4ee3e` | `nocturia_true` | -- | true | 0/36 | 0.0% | null 36 |
| `nocturia_true:126e0cfb` | `nocturia_true` | -- | true | 0/34 | 0.0% | null 34 |
| `nocturia_true:e853d9c0` | `nocturia_true` | -- | true | 0/30 | 0.0% | null 30 |
| `nocturia_false:5efba823` | `nocturia_false` | -- | false | 0/29 | 0.0% | null 29 |
| `nocturia_false:14ecd3b3` | `nocturia_false` | -- | false | 0/28 | 0.0% | true 28 |
| `nocturia_false:bc25d693` | `nocturia_false` | -- | false | 0/28 | 0.0% | true 28 |
| `nocturia_true:4506c1ce` | `nocturia_true` | -- | true | 0/25 | 0.0% | null 25 |
| `nocturia_null_attribution:7fc5b7ab` | `nocturia_null_attribution` | attribution | null | 0/22 | 0.0% | true 22 |
| `nocturia_true:f81d11be` | `nocturia_true` | -- | true | 0/20 | 0.0% | null 20 |
| `nocturia_null_thirdparty:49d8e5c9` | `nocturia_null_thirdparty` | third_party | null | 0/18 | 0.0% | true 18 |
| `nocturia_null_hedged:b85fb3a3` | `nocturia_null_hedged` | hedged | null | 0/17 | 0.0% | true 17 |
| `nocturia_true:31923f27` | `nocturia_true` | -- | true | 0/17 | 0.0% | null 17 |
| `nocturia_null_attribution:0dfc44e6` | `nocturia_null_attribution` | attribution | null | 0/16 | 0.0% | true 16 |
| `nocturia_null_thirdparty:776f85a8` | `nocturia_null_thirdparty` | third_party | null | 0/15 | 0.0% | false 2, true 13 |
| `nocturia_null_historical:0e6d519c` | `nocturia_null_historical` | historical | null | 0/13 | 0.0% | true 13 |
| `nocturia_null_thirdparty:3f34a4a7` | `nocturia_null_thirdparty` | third_party | null | 0/13 | 0.0% | true 13 |
| `nocturia_null_historical:bdf2082b` | `nocturia_null_historical` | historical | null | 0/12 | 0.0% | true 12 |
| `nocturia_null_metaphor:a88b521b` | `nocturia_null_metaphor` | metaphor | null | 0/12 | 0.0% | false 12 |
| `nocturia_null_metaphor:c666d342` | `nocturia_null_metaphor` | metaphor | null | 0/12 | 0.0% | true 12 |
| `nocturia_null_hedged:31bc996d` | `nocturia_null_hedged` | hedged | null | 0/11 | 0.0% | true 11 |
| `nocturia_null_hedged:d376c840` | `nocturia_null_hedged` | hedged | null | 0/11 | 0.0% | true 11 |
| `nocturia_null_attribution:0de14f1d` | `nocturia_null_attribution` | attribution | null | 0/9 | 0.0% | true 9 |
| `nocturia_null_hedged:841744b2` | `nocturia_null_hedged` | hedged | null | 0/9 | 0.0% | true 9 |
| `nocturia_null_hedged:20ad42fe` | `nocturia_null_hedged` | hedged | null | 0/8 | 0.0% | true 8 |
| `nocturia_null_hedged:58ffb85e` | `nocturia_null_hedged` | hedged | null | 0/8 | 0.0% | true 8 |
| `nocturia_null_thirdparty:a86fb1cc` | `nocturia_null_thirdparty` | third_party | null | 0/8 | 0.0% | false 8 |
| `nocturia_false:99cd439f` | `nocturia_false` | -- | false | 1/46 | 2.2% | false 1, null 45 |
| `nocturia_false:e4441873` | `nocturia_false` | -- | false | 1/34 | 2.9% | false 1, null 33 |
| `nocturia_true:efa44ced` | `nocturia_true` | -- | true | 2/26 | 7.7% | true 2, null 24 |
| `nocturia_null_attribution:6a302d90` | `nocturia_null_attribution` | attribution | null | 1/12 | 8.3% | false 4, true 7, null 1 |
| `nocturia_false:b1f7e93f` | `nocturia_false` | -- | false | 8/49 | 16.3% | false 8, true 41 |

*41 further fragments with at least one error are in the JSON sidecar; every fragment is there regardless of score.*

## `arm_b_finetune@c0.5-d0.3`

`roberta-base` with **every layer unfrozen**, mean-pooled, with the same `Linear(768, 3)` head -- 110M trainable parameters against Arm A's 2,307. Three epochs at batch 32, learning rate 2e-5, 10% linear warmup, AdamW, fp32. No gradient checkpointing, no 8-bit optimiser, no LoRA, no gradient accumulation: the full model fits in 12GB with room to spare, so anything that reads like a compute compromise would be a mistake rather than a saving. This is the arm that separates "the fragment libraries are the bottleneck" from "the method is too weak": if a fully fine-tuned encoder still cannot read third-party attribution, tense or metaphor, the limit is in the ideas the libraries contain and the fix is library work, not model work.

Decision-rule margins selected per fold (on each fold's own validation split): 0.0, 0.1, 0.35, 0.8.

*Confusion matrix, raw argmax*

|  | pred false | pred true | pred null | total |
|---|---|---|---|---|
| **truth false** | 2006 | 97 | 376 | 2479 |
| **truth true** | 0 | 1250 | 231 | 1481 |
| **truth null** | 54 | 218 | 5768 | 6040 |
| **total** | 2060 | 1565 | 6375 | 10000 |

`null -> true`: 218 of 6040 truly-null examples (3.61%).

*Confusion matrix, after the decision rule*

|  | pred false | pred true | pred null | total |
|---|---|---|---|---|
| **truth false** | 2006 | 96 | 377 | 2479 |
| **truth true** | 0 | 1238 | 243 | 1481 |
| **truth null** | 55 | 204 | 5781 | 6040 |
| **total** | 2061 | 1538 | 6401 | 10000 |

`null -> true`: 204 of 6040 truly-null examples (3.38%).

### Per class, after the decision rule

| class | support | predicted | precision | recall | F1 |
|---|---|---|---|---|---|
| `false` | 2479 | 2061 | 97.3% | 80.9% | 88.4% |
| `true` | 1481 | 1538 | 80.5% | 83.6% | 82.0% |
| `null` | 6040 | 6401 | 90.3% | 95.7% | 92.9% |

### By label mode

| label mode | n | eff n | accuracy [95% CI] |
|---|---|---|---|
| false | 2479 | **130** | 80.9% [72.2%, 88.9%] |
| null_ambiguous | 3062 | **243** | 91.6% [88.3%, 94.6%] |
| null_structural | 2978 | **1** | 99.9% [99.9%, 99.9%] |
| true | 1481 | **138** | 83.6% [75.1%, 91.5%] |

### By null sub-class

| sub-class | n | eff n | null recall [95% CI] |
|---|---|---|---|
| attribution | 655 | **51** | 86.6% [76.8%, 94.9%] |
| hedged | 587 | **47** | 86.5% [76.6%, 94.5%] |
| historical | 558 | **46** | 92.8% [85.5%, 98.6%] |
| metaphor | 684 | **52** | 97.8% [94.0%, 99.9%] |
| third_party | 578 | **47** | 93.9% [86.7%, 99.6%] |

### By fragment library

| library | n | eff n | accuracy [95% CI] |
|---|---|---|---|
| declarative_v1 | 1213 | **160** | 100.0% [100.0%, 100.0%] |
| nocturia_false | 1722 | **54** | 72.5% [61.0%, 83.8%] |
| nocturia_null_attribution | 655 | **51** | 86.6% [76.8%, 94.9%] |
| nocturia_null_hedged | 587 | **47** | 86.5% [76.6%, 94.5%] |
| nocturia_null_historical | 558 | **46** | 92.8% [85.5%, 98.6%] |
| nocturia_null_metaphor | 684 | **52** | 97.8% [94.0%, 99.9%] |
| nocturia_null_thirdparty | 578 | **47** | 93.9% [86.7%, 99.6%] |
| nocturia_true | 1025 | **54** | 76.3% [65.1%, 87.4%] |
| (none) | 2978 | **1** | 99.9% [99.9%, 99.9%] |

### Per-fragment errors (worst first)

Whether errors are spread thinly across many fragments or piled onto a few is the difference
between "the method is too weak" (model work) and "these specific ideas are not learnable from
the data we have" (library work, and these are the fragments to write more of). No intervals:
a fragment is one cluster, so an interval over its own examples measures nothing.

74 of 749 decisive fragments were got wrong at least once.

`arm_b_finetune@c0.5-d0.3`: 973 errors across 74 of 749 decisive fragments. Half of them fall on **17** fragments (an even spread would be 37.0); the worst ten carry 34.4% of all errors.

| fragment | library | sub-class | truth | correct | accuracy | predicted as |
|---|---|---|---|---|---|---|
| `nocturia_false:3aab37fe` | `nocturia_false` | -- | false | 0/43 | 0.0% | null 43 |
| `nocturia_false:99cd439f` | `nocturia_false` | -- | false | 0/38 | 0.0% | null 38 |
| `nocturia_false:b1f7e93f` | `nocturia_false` | -- | false | 0/35 | 0.0% | true 35 |
| `nocturia_false:bf88ba0d` | `nocturia_false` | -- | false | 0/35 | 0.0% | null 35 |
| `nocturia_false:9b901e69` | `nocturia_false` | -- | false | 0/32 | 0.0% | null 32 |
| `nocturia_false:e6fd6a44` | `nocturia_false` | -- | false | 0/31 | 0.0% | null 31 |
| `nocturia_true:86e1cd53` | `nocturia_true` | -- | true | 0/29 | 0.0% | null 29 |
| `nocturia_true:126e0cfb` | `nocturia_true` | -- | true | 0/28 | 0.0% | null 28 |
| `nocturia_false:21180255` | `nocturia_false` | -- | false | 0/25 | 0.0% | null 25 |
| `nocturia_false:5efba823` | `nocturia_false` | -- | false | 0/24 | 0.0% | null 24 |
| `nocturia_true:2cbd088f` | `nocturia_true` | -- | true | 0/23 | 0.0% | null 23 |
| `nocturia_false:1a41970c` | `nocturia_false` | -- | false | 0/22 | 0.0% | null 22 |
| `nocturia_null_attribution:7fc5b7ab` | `nocturia_null_attribution` | attribution | null | 0/22 | 0.0% | true 22 |
| `nocturia_true:f3e4ee3e` | `nocturia_true` | -- | true | 0/22 | 0.0% | null 22 |
| `nocturia_false:bc25d693` | `nocturia_false` | -- | false | 0/21 | 0.0% | true 21 |
| `nocturia_false:14ecd3b3` | `nocturia_false` | -- | false | 0/20 | 0.0% | true 20 |
| `nocturia_true:0740576d` | `nocturia_true` | -- | true | 0/19 | 0.0% | null 19 |
| `nocturia_true:e853d9c0` | `nocturia_true` | -- | true | 0/19 | 0.0% | null 19 |
| `nocturia_false:2e5a7e5a` | `nocturia_false` | -- | false | 0/17 | 0.0% | true 7, null 10 |
| `nocturia_false:deb3785c` | `nocturia_false` | -- | false | 0/17 | 0.0% | null 17 |
| `nocturia_null_hedged:b85fb3a3` | `nocturia_null_hedged` | hedged | null | 0/17 | 0.0% | true 17 |
| `nocturia_true:f81d11be` | `nocturia_true` | -- | true | 0/17 | 0.0% | null 17 |
| `nocturia_null_attribution:0dfc44e6` | `nocturia_null_attribution` | attribution | null | 0/16 | 0.0% | true 16 |
| `nocturia_null_thirdparty:776f85a8` | `nocturia_null_thirdparty` | third_party | null | 0/15 | 0.0% | false 15 |
| `nocturia_null_metaphor:a88b521b` | `nocturia_null_metaphor` | metaphor | null | 0/12 | 0.0% | false 12 |
| `nocturia_null_attribution:7798eddd` | `nocturia_null_attribution` | attribution | null | 0/11 | 0.0% | true 11 |
| `nocturia_null_hedged:cf1d2bb8` | `nocturia_null_hedged` | hedged | null | 0/11 | 0.0% | true 11 |
| `nocturia_null_hedged:58ffb85e` | `nocturia_null_hedged` | hedged | null | 0/8 | 0.0% | false 1, true 7 |
| `nocturia_false:98d02ead` | `nocturia_false` | -- | false | 1/40 | 2.5% | false 1, null 39 |
| `nocturia_false:1cb7de3b` | `nocturia_false` | -- | false | 1/26 | 3.8% | false 1, null 25 |
| `nocturia_true:39566c91` | `nocturia_true` | -- | true | 1/22 | 4.5% | true 1, null 21 |
| `nocturia_null_historical:d4317e27` | `nocturia_null_historical` | historical | null | 1/13 | 7.7% | true 12, null 1 |
| `nocturia_null_attribution:b68c3406` | `nocturia_null_attribution` | attribution | null | 1/12 | 8.3% | true 11, null 1 |
| `nocturia_null_hedged:841744b2` | `nocturia_null_hedged` | hedged | null | 1/9 | 11.1% | true 8, null 1 |
| `nocturia_false:5e819a32` | `nocturia_false` | -- | false | 3/25 | 12.0% | false 3, null 22 |
| `nocturia_null_historical:ef1c4633` | `nocturia_null_historical` | historical | null | 2/15 | 13.3% | true 13, null 2 |
| `nocturia_true:4506c1ce` | `nocturia_true` | -- | true | 3/22 | 13.6% | true 3, null 19 |
| `nocturia_true:efa44ced` | `nocturia_true` | -- | true | 3/19 | 15.8% | true 3, null 16 |
| `nocturia_null_attribution:6a302d90` | `nocturia_null_attribution` | attribution | null | 2/12 | 16.7% | true 10, null 2 |
| `nocturia_null_thirdparty:49d8e5c9` | `nocturia_null_thirdparty` | third_party | null | 4/18 | 22.2% | true 14, null 4 |

*34 further fragments with at least one error are in the JSON sidecar; every fragment is there regardless of score.*

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
| 0 | 10000 | 2000 | 2000 | 0.0 | 74.6% | 74.6% | 61.1% | 0.83% |
| 1 | 10000 | 2000 | 2000 | 0.0 | 74.0% | 74.0% | 64.4% | 2.50% |
| 2 | 10000 | 2000 | 2000 | 0.0 | 76.9% | 76.9% | 67.2% | 3.89% |
| 3 | 10000 | 2000 | 2000 | 0.05 | 71.3% | 71.9% | 55.6% | 1.48% |
| 4 | 10000 | 2000 | 2000 | 0.0 | 79.8% | 79.8% | 73.6% | 4.81% |

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
| 0 | 10000 | 2000 | 2000 | 0.0 | 85.7% | 85.7% | 81.2% | 1.24% |
| 1 | 10000 | 2000 | 2000 | 0.0 | 91.2% | 91.2% | 88.9% | 4.24% |
| 2 | 10000 | 2000 | 2000 | 0.25 | 83.0% | 83.0% | 76.3% | 5.30% |
| 3 | 10000 | 2000 | 2000 | 0.2 | 90.8% | 90.9% | 86.0% | 4.03% |
| 4 | 10000 | 2000 | 2000 | 0.5 | 90.8% | 90.8% | 88.4% | 7.30% |

### `arm_b_finetune@c0.0-d0.3`

| fold | train n | val n | test n | margin | acc (raw) | acc (ruled) | macro-F1 | null->true |
|---|---|---|---|---|---|---|---|---|
| 0 | 10000 | 2000 | 2000 | 0.55 | 87.9% | 88.5% | 85.4% | 4.30% |
| 1 | 10000 | 2000 | 2000 | 0.85 | 89.8% | 90.6% | 87.9% | 5.66% |
| 2 | 10000 | 2000 | 2000 | 0.0 | 92.5% | 92.5% | 89.6% | 2.98% |
| 3 | 10000 | 2000 | 2000 | 0.0 | 93.2% | 93.2% | 89.6% | 3.54% |
| 4 | 10000 | 2000 | 2000 | 0.15 | 94.2% | 94.1% | 91.5% | 5.22% |

### `arm_b_finetune@c0.5-d0.0`

| fold | train n | val n | test n | margin | acc (raw) | acc (ruled) | macro-F1 | null->true |
|---|---|---|---|---|---|---|---|---|
| 0 | 10000 | 2000 | 2000 | 0.65 | 78.3% | 78.6% | 71.3% | 3.89% |
| 1 | 10000 | 2000 | 2000 | 0.3 | 89.5% | 89.6% | 86.8% | 4.83% |
| 2 | 10000 | 2000 | 2000 | 0.6 | 81.5% | 81.6% | 75.0% | 4.88% |
| 3 | 10000 | 2000 | 2000 | 0.05 | 94.8% | 94.8% | 91.9% | 2.30% |
| 4 | 10000 | 2000 | 2000 | 0.05 | 92.5% | 92.5% | 90.1% | 5.47% |

### `arm_b_finetune@c0.5-d0.3`

| fold | train n | val n | test n | margin | acc (raw) | acc (ruled) | macro-F1 | null->true |
|---|---|---|---|---|---|---|---|---|
| 0 | 10000 | 2000 | 2000 | 0.35 | 84.5% | 84.5% | 80.8% | 5.29% |
| 1 | 10000 | 2000 | 2000 | 0.35 | 88.7% | 88.6% | 85.2% | 2.08% |
| 2 | 10000 | 2000 | 2000 | 0.1 | 89.4% | 89.3% | 86.0% | 0.91% |
| 3 | 10000 | 2000 | 2000 | 0.0 | 94.8% | 94.8% | 92.6% | 3.95% |
| 4 | 10000 | 2000 | 2000 | 0.8 | 93.8% | 94.0% | 92.4% | 4.64% |

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

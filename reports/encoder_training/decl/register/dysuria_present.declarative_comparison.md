# Encoder training: evaluation report

*Generated 2026-09-02T19:46:45+00:00.*

|  |  |
|---|---|
| signal | `dysuria_present` |
| folds | `5` |
| generator version | `4` |
| generator base seed | `42` |
| generator seed rule | `base + 100 * fold + {train: 0, val: 1, test: 2}` |
| split salt | `0` |
| dataset dir | `data/synthetic/generated/decl/c0.5-d0.0` |
| ruleset | `data/uti1.json` |
| ruleset hash | `325b33068307bc70ca085b27117a90c2ad9e71fac24a80f77c8107d08049bb9f` |
| examples per fold | `train 10000, val 2000, test 2000` |
| shuffle seed | `7` |
| report | `declarative sweep, 3 cells` |
| cells | `c0.5-d0.0, c0.5-d0.3, c0.5-d0.6` |
| reference cell | `data/synthetic/generated/decl/c0.5-d0.0` |
| selected epochs | `c0.5-d0.0 2, 1, 2, 1, 3, c0.5-d0.3 1, 1, 3, 3, 3, c0.5-d0.6 1, 2, 1, 1, 2` |
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
| artefacts | `models/encoder-decl/register` |
| model revision | `e2da8e2f811d1448a5b465c236feacd80ffbac7b` |
| revision pinned | `False` |
| tokeniser lowercases | `False` |
| tokeniser vocab size | `50265` |
| tokeniser discards casing | `False` |
| cluster tag coverage | `5 of 7 libraries carry cluster markers; 92 of 678 fragments are in libraries with none` |
| bootstrap | `2000 resamples over clusters, alpha=0.05, seed=0` |

**arms**

* **c0.5-d0.0** (`data/synthetic/generated/decl/c0.5-d0.0`): 10000 examples per epoch, **10000** labelled positions for `dysuria_present`
* **c0.5-d0.3** (`data/synthetic/generated/decl/c0.5-d0.3`): 10000 examples per epoch, **10000** labelled positions for `dysuria_present`
* **c0.5-d0.6** (`data/synthetic/generated/decl/c0.5-d0.6`): 10000 examples per epoch, **10000** labelled positions for `dysuria_present`

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

> **Warning: 2 of the 7 libraries behind this run carry no cluster markers at all, so every line in them counts as an independent idea.** Where that is not true -- where several lines are one idea written several ways -- the `eff n` of every slice drawn from those libraries is an **upper bound**, and the confidence intervals below are correspondingly **narrower than the truth**.
>
> Untagged: `dysuria_false`, `dysuria_true`.

Tagging cannot inflate a number -- `[c01]` siblings are forced into one cluster and one
split, so it only ever *reduces* `eff n`, correctly, by stopping the same idea being
counted twice. The asymmetry is what makes cross-signal comparison unsafe: a fully
tagged signal is penalised for being honest and an untagged one is flattered by default,
so a ranking across signals is partly an artefact of this column.

| library | fragments | tagged | coverage |
|---|---|---|---|
| `dysuria_false` | 47 | 0 | 0.0% |
| `dysuria_true` | 45 | 0 | 0.0% |
| `dysuria_null_metaphor` | 40 | 24 | 60.0% |
| `declarative_v1` | 422 | 422 | 100.0% |
| `dysuria_null_hedged` | 40 | 40 | 100.0% |
| `dysuria_null_historical` | 38 | 38 | 100.0% |
| `dysuria_null_thirdparty` | 46 | 46 | 100.0% |

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
| `majority_class` | baseline | 7022 | **182** | 43.6% [36.4%, 51.4%] | 20.2% [17.8%, 22.6%] | 60.4% | 60.4% +/- 0.2% |
| `length_only` | baseline | 7022 | **182** | 45.5% [38.6%, 53.0%] | 24.1% [21.3%, 26.9%] | 61.5% | 61.5% +/- 0.9% |
| `tfidf_logreg` | baseline | 7022 | **182** | 63.1% [57.2%, 69.2%] | 53.4% [47.8%, 58.6%] | 74.1% | 74.1% +/- 2.1% |
| `length_only__shuffled` | negative control | 7022 | **182** | 43.6% [36.4%, 51.4%] | 20.2% [17.8%, 22.6%] | 60.4% | 60.4% +/- 0.2% |
| `tfidf_logreg__shuffled` | negative control | 7022 | **182** | 43.8% [36.6%, 51.5%] | 20.9% [18.4%, 23.3%] | 60.4% | 60.4% +/- 0.2% |
| `arm_b_finetune@c0.5-d0.0` | finetune | 7022 | **182** | 93.5% [90.6%, 96.3%] | 93.5% [90.4%, 96.2%] | 95.4% | 95.4% +/- 2.6% |
| `arm_b_finetune@c0.5-d0.3` | finetune | 7022 | **342** | 94.1% [91.5%, 96.4%] | 93.8% [91.0%, 96.2%] | 95.8% | 95.8% +/- 2.0% |
| `arm_b_finetune@c0.5-d0.6` | finetune | 7022 | **351** | 96.5% [94.9%, 97.9%] | 96.2% [94.6%, 97.7%] | 97.4% | 97.4% +/- 0.5% |

### Null sub-class recall, pooled

The table the whole exercise exists for: how often each hard `null` sub-class is correctly
left as `null`. `eff n` here is the sub-class's entire library, which a single split cannot reach.

**Never read this table on its own.** Every example in these slices is truly `null`, so a model
that always answers `null` scores 100% across the row -- as `majority_class` below does. High
null recall is only a finding when the `true` and `false` recalls in the per-class tables are
high too.

| model | adjacent | attribution | hedged | historical | metaphor | third_party |
|---|---|---|---|---|---|---|
| `majority_class` | -- | -- | 100.0% [100.0%, 100.0%] (eff n 20) | 100.0% [100.0%, 100.0%] (eff n 19) | 100.0% [100.0%, 100.0%] (eff n 28) | 100.0% [100.0%, 100.0%] (eff n 23) |
| `length_only` | -- | -- | 100.0% [100.0%, 100.0%] (eff n 20) | 99.7% [99.0%, 100.0%] (eff n 19) | 99.7% [99.2%, 100.0%] (eff n 28) | 99.8% [99.3%, 100.0%] (eff n 23) |
| `tfidf_logreg` | -- | -- | 89.5% [82.8%, 95.7%] (eff n 20) | 99.1% [97.3%, 100.0%] (eff n 19) | 99.6% [99.1%, 100.0%] (eff n 28) | 96.5% [92.2%, 99.8%] (eff n 23) |
| `length_only__shuffled` | -- | -- | 100.0% [100.0%, 100.0%] (eff n 20) | 100.0% [100.0%, 100.0%] (eff n 19) | 100.0% [100.0%, 100.0%] (eff n 28) | 100.0% [100.0%, 100.0%] (eff n 23) |
| `tfidf_logreg__shuffled` | -- | -- | 99.6% [99.1%, 100.0%] (eff n 20) | 99.5% [98.8%, 100.0%] (eff n 19) | 99.3% [98.7%, 99.9%] (eff n 28) | 99.7% [99.2%, 100.0%] (eff n 23) |
| `arm_b_finetune@c0.5-d0.0` | -- | -- | 86.8% [77.1%, 95.1%] (eff n 20) | 99.1% [97.7%, 100.0%] (eff n 19) | 99.7% [99.3%, 100.0%] (eff n 28) | 95.6% [86.7%, 100.0%] (eff n 23) |
| `arm_b_finetune@c0.5-d0.3` | -- | -- | 89.0% [79.1%, 96.5%] (eff n 20) | 98.2% [95.1%, 99.8%] (eff n 19) | 99.5% [98.6%, 100.0%] (eff n 28) | 93.2% [83.8%, 99.9%] (eff n 23) |
| `arm_b_finetune@c0.5-d0.6` | -- | -- | 93.4% [85.7%, 99.0%] (eff n 20) | 98.0% [95.0%, 99.7%] (eff n 19) | 99.9% [99.6%, 100.0%] (eff n 28) | 95.5% [90.0%, 99.5%] (eff n 23) |

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

Not scored, because no head exists for them: `urinary_frequency_present`, `nocturia_present`, `fever_present`, `flank_pain_present`, `haematuria_present`, `recent_uti_present`.

### `null -> true` on real text -- the headline

How often each model answers `true` about a signal the submission never mentioned, as
the mean across folds of that fold's own rate. Every other number in this section is
read against this one: a model can post a respectable overall figure here purely by
answering `null` everywhere, and it can post a respectable *decisive* figure while still
inventing symptoms into most of the submissions that never raised them.

| signal | null support | `arm_b_finetune@c0.5-d0.0` | `arm_b_finetune@c0.5-d0.3` | `arm_b_finetune@c0.5-d0.6` |
|---|---|---|---|---|
| `dysuria_present` | 11 | 3.6% | 12.7% | 12.7% |

### `arm_b_finetune@c0.5-d0.0`

Recombination test slice: **n 7022**, **eff n 182** clusters, accuracy 93.5% [90.6%, 96.3%]. Holdout: **n 67** submissions, one observation each, scored by 5 fold models at margins 0.05, 0.7, 0.9, 0.0, 0.15. The two `n`s are printed together because they are not the same kind of number and the second is far the smaller.

| signal | true/false/null | omitted | decisive n | decisive acc (mean +/- sd) | worst-case half-width | all n | all acc (mean +/- sd) | null recall |
|---|---|---|---|---|---|---|---|---|
| `dysuria_present` | 56/0/11 | 0 | 56 | 78.6% +/- 7.7% | +/-13.1% | 67 | 79.1% +/- 6.4% | 81.8% +/- 0.0% |

* `dysuria_present`: no `false` examples in this set, so its number is very nearly a recall-only measurement: nothing here tests whether an explicit denial is read correctly, which was the largest error family in the synthetic evaluation.

`null -> true` on real text, per fold: `dysuria_present` 2, 0, 0, 0, 0 of 11. This is the cell that invents a symptom into a patient's pre-filled form, counted here on submissions rather than on recombinations.

### `arm_b_finetune@c0.5-d0.3`

Recombination test slice: **n 7022**, **eff n 342** clusters, accuracy 94.1% [91.5%, 96.4%]. Holdout: **n 67** submissions, one observation each, scored by 5 fold models at margins 0.1, 0.85, 0.9, 0.9, 0.4. The two `n`s are printed together because they are not the same kind of number and the second is far the smaller.

| signal | true/false/null | omitted | decisive n | decisive acc (mean +/- sd) | worst-case half-width | all n | all acc (mean +/- sd) | null recall |
|---|---|---|---|---|---|---|---|---|
| `dysuria_present` | 56/0/11 | 0 | 56 | 92.9% +/- 3.3% | +/-13.1% | 67 | 89.3% +/- 3.4% | 70.9% +/- 7.6% |

* `dysuria_present`: no `false` examples in this set, so its number is very nearly a recall-only measurement: nothing here tests whether an explicit denial is read correctly, which was the largest error family in the synthetic evaluation.

`null -> true` on real text, per fold: `dysuria_present` 3, 0, 1, 1, 2 of 11. This is the cell that invents a symptom into a patient's pre-filled form, counted here on submissions rather than on recombinations.

### `arm_b_finetune@c0.5-d0.6`

Recombination test slice: **n 7022**, **eff n 351** clusters, accuracy 96.5% [94.9%, 97.9%]. Holdout: **n 67** submissions, one observation each, scored by 5 fold models at margins 0.05, 0.75, 0.8, 0.0, 0.1. The two `n`s are printed together because they are not the same kind of number and the second is far the smaller.

| signal | true/false/null | omitted | decisive n | decisive acc (mean +/- sd) | worst-case half-width | all n | all acc (mean +/- sd) | null recall |
|---|---|---|---|---|---|---|---|---|
| `dysuria_present` | 56/0/11 | 0 | 56 | 85.4% +/- 9.0% | +/-13.1% | 67 | 83.3% +/- 6.5% | 72.7% +/- 6.4% |

* `dysuria_present`: no `false` examples in this set, so its number is very nearly a recall-only measurement: nothing here tests whether an explicit denial is read correctly, which was the largest error family in the synthetic evaluation.

`null -> true` on real text, per fold: `dysuria_present` 3, 1, 0, 2, 1 of 11. This is the cell that invents a symptom into a patient's pre-filled form, counted here on submissions rather than on recombinations.

## Paired on real text

The 67 submissions are the same 67 for every model here, so unlike the recombination
test slice they can be paired: the informative quantity is the submissions two models
disagree about, not the gap between two means. One test per fold, never pooled.

### `arm_b_finetune@c0.5-d0.0` against `arm_b_finetune@c0.5-d0.3`

| fold | pairs | only `arm_b_finetune@c0.5-d0.0` | only `arm_b_finetune@c0.5-d0.3` | p |
|---|---|---|---|---|
| 0 | 67 | 3 | 3 | 1 |
| 1 | 67 | 1 | 4 | 0.375 |
| 2 | 67 | 1 | 12 | 0.00342 |
| 3 | 67 | 1 | 15 | 0.000519 |
| 4 | 67 | 2 | 8 | 0.109 |

`arm_b_finetune@c0.5-d0.0` ahead on 0 folds, `arm_b_finetune@c0.5-d0.3` on 4. `null -> true` mean: 3.6% against 12.7% -- **-9.1 points** in favour of `arm_b_finetune@c0.5-d0.3`.

*One test per fold over the same 67 submissions, never concatenated: five folds are five models scored on one sample, and pooling would report a p-value for 335 observations that do not exist.*

### `arm_b_finetune@c0.5-d0.0` against `arm_b_finetune@c0.5-d0.6`

| fold | pairs | only `arm_b_finetune@c0.5-d0.0` | only `arm_b_finetune@c0.5-d0.6` | p |
|---|---|---|---|---|
| 0 | 67 | 2 | 4 | 0.688 |
| 1 | 67 | 4 | 5 | 1 |
| 2 | 67 | 9 | 7 | 0.804 |
| 3 | 67 | 3 | 9 | 0.146 |
| 4 | 67 | 2 | 9 | 0.0654 |

`arm_b_finetune@c0.5-d0.0` ahead on 1 folds, `arm_b_finetune@c0.5-d0.6` on 4. `null -> true` mean: 3.6% against 12.7% -- **-9.1 points** in favour of `arm_b_finetune@c0.5-d0.6`.

*One test per fold over the same 67 submissions, never concatenated: five folds are five models scored on one sample, and pooling would report a p-value for 335 observations that do not exist.*

### `arm_b_finetune@c0.5-d0.3` against `arm_b_finetune@c0.5-d0.6`

| fold | pairs | only `arm_b_finetune@c0.5-d0.3` | only `arm_b_finetune@c0.5-d0.6` | p |
|---|---|---|---|---|
| 0 | 67 | 1 | 3 | 0.625 |
| 1 | 67 | 3 | 1 | 0.625 |
| 2 | 67 | 14 | 1 | 0.000977 |
| 3 | 67 | 8 | 0 | 0.00781 |
| 4 | 67 | 2 | 3 | 1 |

`arm_b_finetune@c0.5-d0.3` ahead on 3 folds, `arm_b_finetune@c0.5-d0.6` on 2. `null -> true` mean: 12.7% against 12.7% -- **+0.0 points** in favour of `arm_b_finetune@c0.5-d0.6`.

*One test per fold over the same 67 submissions, never concatenated: five folds are five models scored on one sample, and pooling would report a p-value for 335 observations that do not exist.*

* `majority_class` against `length_only`: not paired -- one or both runs carry no real-text cells for this signal (not scored, or scored before the per-submission decisions were kept).
* `majority_class` against `tfidf_logreg`: not paired -- one or both runs carry no real-text cells for this signal (not scored, or scored before the per-submission decisions were kept).
* `majority_class` against `arm_b_finetune@c0.5-d0.0`: not paired -- one or both runs carry no real-text cells for this signal (not scored, or scored before the per-submission decisions were kept).
* `majority_class` against `arm_b_finetune@c0.5-d0.3`: not paired -- one or both runs carry no real-text cells for this signal (not scored, or scored before the per-submission decisions were kept).
* `majority_class` against `arm_b_finetune@c0.5-d0.6`: not paired -- one or both runs carry no real-text cells for this signal (not scored, or scored before the per-submission decisions were kept).
* `length_only` against `tfidf_logreg`: not paired -- one or both runs carry no real-text cells for this signal (not scored, or scored before the per-submission decisions were kept).
* `length_only` against `arm_b_finetune@c0.5-d0.0`: not paired -- one or both runs carry no real-text cells for this signal (not scored, or scored before the per-submission decisions were kept).
* `length_only` against `arm_b_finetune@c0.5-d0.3`: not paired -- one or both runs carry no real-text cells for this signal (not scored, or scored before the per-submission decisions were kept).
* `length_only` against `arm_b_finetune@c0.5-d0.6`: not paired -- one or both runs carry no real-text cells for this signal (not scored, or scored before the per-submission decisions were kept).
* `tfidf_logreg` against `arm_b_finetune@c0.5-d0.0`: not paired -- one or both runs carry no real-text cells for this signal (not scored, or scored before the per-submission decisions were kept).
* `tfidf_logreg` against `arm_b_finetune@c0.5-d0.3`: not paired -- one or both runs carry no real-text cells for this signal (not scored, or scored before the per-submission decisions were kept).
* `tfidf_logreg` against `arm_b_finetune@c0.5-d0.6`: not paired -- one or both runs carry no real-text cells for this signal (not scored, or scored before the per-submission decisions were kept).

## The cells behind these columns

One cell per `--cell`, each generated from the same libraries with the same seed, the same counts and the same fold triple, differing only in `--companion-share` and `--declarative-share`. The shares are read from each cell's own sidecars, not from this run's flags.

| cell | companion share | declarative share | generator | splits read | tree |
|---|---|---|---|---|---|
| `c0.5-d0.0` | 0.5 | 0.0 | 4 | 30 | `data/synthetic/generated/decl/c0.5-d0.0` |
| `c0.5-d0.3` | 0.5 | 0.3 | 4 | 30 | `data/synthetic/generated/decl/c0.5-d0.3` |
| `c0.5-d0.6` | 0.5 | 0.6 | 4 | 30 | `data/synthetic/generated/decl/c0.5-d0.6` |


*`c0.5-d0.0` (data/synthetic/generated/decl/c0.5-d0.0) is the reference: the report's test slice, fold partition and cluster checks describe its tree..*

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
| `majority_class` | baseline | 3062 | **90** | 100.0% [100.0%, 100.0%] |
| `length_only` | baseline | 3062 | **90** | 99.8% [99.5%, 100.0%] |
| `tfidf_logreg` | baseline | 3062 | **90** | 96.0% [93.6%, 98.1%] |
| `arm_b_finetune@c0.5-d0.0` | finetune | 3062 | **90** | 95.1% [91.2%, 98.2%] |
| `arm_b_finetune@c0.5-d0.3` | finetune | 3062 | **90** | 94.7% [90.8%, 97.7%] |
| `arm_b_finetune@c0.5-d0.6` | finetune | 3062 | **90** | 96.6% [94.0%, 98.6%] |

### 2. The same comparison, paired

Two overlapping intervals do not settle whether one model beats another on the same
examples. McNemar does, over the examples the two disagree about -- read it alongside the
intervals above, never instead of them.

| pair | n | a only | b only | p |
|---|---|---|---|---|
| `majority_class` vs `length_only` | 3062 | 6 | 0 | 0.0312 |
| `majority_class` vs `tfidf_logreg` | 3062 | 122 | 0 | 3.76e-37 |
| `majority_class` vs `arm_b_finetune@c0.5-d0.0` | 3062 | 157 | 0 | 1.09e-47 |
| `length_only` vs `tfidf_logreg` | 3062 | 122 | 6 | 3.35e-29 |
| `length_only` vs `arm_b_finetune@c0.5-d0.0` | 3062 | 157 | 6 | 4.22e-39 |
| `tfidf_logreg` vs `arm_b_finetune@c0.5-d0.0` | 3062 | 127 | 92 | 0.0214 |

Not on this table, because they cannot be paired at all -- different examples on the two sides, so there is nothing for McNemar to pair: `majority_class` vs `arm_b_finetune@c0.5-d0.3`; `majority_class` vs `arm_b_finetune@c0.5-d0.6`; `length_only` vs `arm_b_finetune@c0.5-d0.3`; `length_only` vs `arm_b_finetune@c0.5-d0.6`; `tfidf_logreg` vs `arm_b_finetune@c0.5-d0.3`; `tfidf_logreg` vs `arm_b_finetune@c0.5-d0.6`; `arm_b_finetune@c0.5-d0.0` vs `arm_b_finetune@c0.5-d0.3`; `arm_b_finetune@c0.5-d0.0` vs `arm_b_finetune@c0.5-d0.6`; `arm_b_finetune@c0.5-d0.3` vs `arm_b_finetune@c0.5-d0.6`. Read those through the intervals above and the per-fold spread, and see "Pairs that could not be tested" below.

### 3. Where the errors fall

The per-fragment table below, as one number per model. Errors spread thinly across many
fragments say the method is too weak. Errors piled onto a handful say those specific ideas
are not learnable from the data we have -- and the table names them, which is what makes
this the most decision-useful thing in the report.

* `majority_class`: 3960 errors across 92 of 256 decisive fragments. Half of them fall on **35** fragments (an even spread would be 46.0); the worst ten carry 16.3% of all errors.
* `length_only`: 3827 errors across 95 of 256 decisive fragments. Half of them fall on **35** fragments (an even spread would be 47.5); the worst ten carry 16.3% of all errors.
* `tfidf_logreg`: 2590 errors across 118 of 256 decisive fragments. Half of them fall on **30** fragments (an even spread would be 59.0); the worst ten carry 20.9% of all errors.
* `arm_b_finetune@c0.5-d0.0`: 453 errors across 35 of 256 decisive fragments. Half of them fall on **7** fragments (an even spread would be 17.5); the worst ten carry 66.2% of all errors.
* `arm_b_finetune@c0.5-d0.3`: 413 errors across 41 of 641 decisive fragments. Half of them fall on **9** fragments (an even spread would be 20.5); the worst ten carry 56.4% of all errors.
* `arm_b_finetune@c0.5-d0.6`: 249 errors across 41 of 671 decisive fragments. Half of them fall on **8** fragments (an even spread would be 20.5); the worst ten carry 59.0% of all errors.

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
| `length_only__shuffled` | 60.4% [38.1%, 77.3%] | 25.1% [18.4%, 29.1%] |
| `tfidf_logreg__shuffled` | 60.4% [38.2%, 77.1%] | 25.7% [18.9%, 29.8%] |

## Paired comparisons (McNemar, raw argmax)

Exact two-sided McNemar over the examples the two models disagree about. Pairing unit is the
example, not the cluster -- see the limitations.

| pair | slice | n | a only | b only | p |
|---|---|---|---|---|---|
| `majority_class` vs `length_only` | overall | 10000 | 34 | 139 | 2.86e-16 |
| `majority_class` vs `length_only` | null_ambiguous | 3062 | 6 | 0 | 0.0312 |
| `majority_class` vs `tfidf_logreg` | overall | 10000 | 127 | 1492 | 7.29e-296 |
| `majority_class` vs `tfidf_logreg` | null_ambiguous | 3062 | 122 | 0 | 3.76e-37 |
| `majority_class` vs `arm_b_finetune@c0.5-d0.0` | overall | 10000 | 163 | 3662 | 0 |
| `majority_class` vs `arm_b_finetune@c0.5-d0.0` | null_ambiguous | 3062 | 157 | 0 | 1.09e-47 |
| `length_only` vs `tfidf_logreg` | overall | 10000 | 161 | 1421 | 4.51e-252 |
| `length_only` vs `tfidf_logreg` | null_ambiguous | 3062 | 122 | 6 | 3.35e-29 |
| `length_only` vs `arm_b_finetune@c0.5-d0.0` | overall | 10000 | 168 | 3562 | 0 |
| `length_only` vs `arm_b_finetune@c0.5-d0.0` | null_ambiguous | 3062 | 157 | 6 | 4.22e-39 |
| `tfidf_logreg` vs `arm_b_finetune@c0.5-d0.0` | overall | 10000 | 164 | 2298 | 0 |
| `tfidf_logreg` vs `arm_b_finetune@c0.5-d0.0` | null_ambiguous | 3062 | 127 | 92 | 0.0214 |

### Pairs that could not be tested

McNemar pairs on the example id, so two models scored on **different examples** cannot be
compared this way at all -- there is nothing to pair. That is a property of the datasets,
not a result: read those runs through their pooled cluster intervals and their per-fold
spread, and do not read the absence of a row above as agreement between them.

| pair | slice | n (a) | n (b) | shared | reason |
|---|---|---|---|---|---|
| `majority_class` vs `arm_b_finetune@c0.5-d0.3` | overall | 10000 | 10000 | 0 | example sets differ: majority_class has 10000, arm_b_finetune@c0.5-d0.3 has 10000, 0 in common |
| `majority_class` vs `arm_b_finetune@c0.5-d0.3` | null_ambiguous | 3062 | 3062 | 0 | example sets differ: majority_class has 3062, arm_b_finetune@c0.5-d0.3 has 3062, 0 in common |
| `majority_class` vs `arm_b_finetune@c0.5-d0.6` | overall | 10000 | 10000 | 0 | example sets differ: majority_class has 10000, arm_b_finetune@c0.5-d0.6 has 10000, 0 in common |
| `majority_class` vs `arm_b_finetune@c0.5-d0.6` | null_ambiguous | 3062 | 3062 | 0 | example sets differ: majority_class has 3062, arm_b_finetune@c0.5-d0.6 has 3062, 0 in common |
| `length_only` vs `arm_b_finetune@c0.5-d0.3` | overall | 10000 | 10000 | 0 | example sets differ: length_only has 10000, arm_b_finetune@c0.5-d0.3 has 10000, 0 in common |
| `length_only` vs `arm_b_finetune@c0.5-d0.3` | null_ambiguous | 3062 | 3062 | 0 | example sets differ: length_only has 3062, arm_b_finetune@c0.5-d0.3 has 3062, 0 in common |
| `length_only` vs `arm_b_finetune@c0.5-d0.6` | overall | 10000 | 10000 | 0 | example sets differ: length_only has 10000, arm_b_finetune@c0.5-d0.6 has 10000, 0 in common |
| `length_only` vs `arm_b_finetune@c0.5-d0.6` | null_ambiguous | 3062 | 3062 | 0 | example sets differ: length_only has 3062, arm_b_finetune@c0.5-d0.6 has 3062, 0 in common |
| `tfidf_logreg` vs `arm_b_finetune@c0.5-d0.3` | overall | 10000 | 10000 | 0 | example sets differ: tfidf_logreg has 10000, arm_b_finetune@c0.5-d0.3 has 10000, 0 in common |
| `tfidf_logreg` vs `arm_b_finetune@c0.5-d0.3` | null_ambiguous | 3062 | 3062 | 0 | example sets differ: tfidf_logreg has 3062, arm_b_finetune@c0.5-d0.3 has 3062, 0 in common |
| `tfidf_logreg` vs `arm_b_finetune@c0.5-d0.6` | overall | 10000 | 10000 | 0 | example sets differ: tfidf_logreg has 10000, arm_b_finetune@c0.5-d0.6 has 10000, 0 in common |
| `tfidf_logreg` vs `arm_b_finetune@c0.5-d0.6` | null_ambiguous | 3062 | 3062 | 0 | example sets differ: tfidf_logreg has 3062, arm_b_finetune@c0.5-d0.6 has 3062, 0 in common |
| `arm_b_finetune@c0.5-d0.0` vs `arm_b_finetune@c0.5-d0.3` | overall | 10000 | 10000 | 0 | example sets differ: arm_b_finetune@c0.5-d0.0 has 10000, arm_b_finetune@c0.5-d0.3 has 10000, 0 in common |
| `arm_b_finetune@c0.5-d0.0` vs `arm_b_finetune@c0.5-d0.3` | null_ambiguous | 3062 | 3062 | 0 | example sets differ: arm_b_finetune@c0.5-d0.0 has 3062, arm_b_finetune@c0.5-d0.3 has 3062, 0 in common |
| `arm_b_finetune@c0.5-d0.0` vs `arm_b_finetune@c0.5-d0.6` | overall | 10000 | 10000 | 0 | example sets differ: arm_b_finetune@c0.5-d0.0 has 10000, arm_b_finetune@c0.5-d0.6 has 10000, 0 in common |
| `arm_b_finetune@c0.5-d0.0` vs `arm_b_finetune@c0.5-d0.6` | null_ambiguous | 3062 | 3062 | 0 | example sets differ: arm_b_finetune@c0.5-d0.0 has 3062, arm_b_finetune@c0.5-d0.6 has 3062, 0 in common |
| `arm_b_finetune@c0.5-d0.3` vs `arm_b_finetune@c0.5-d0.6` | overall | 10000 | 10000 | 0 | example sets differ: arm_b_finetune@c0.5-d0.3 has 10000, arm_b_finetune@c0.5-d0.6 has 10000, 0 in common |
| `arm_b_finetune@c0.5-d0.3` vs `arm_b_finetune@c0.5-d0.6` | null_ambiguous | 3062 | 3062 | 0 | example sets differ: arm_b_finetune@c0.5-d0.3 has 3062, arm_b_finetune@c0.5-d0.6 has 3062, 0 in common |

## What moved, and where

The headline is the least useful output of a model comparison. These two tables are the
useful one: a diffuse lift and a fix to one error family are different findings, and an
aggregate accuracy cannot tell them apart. `spread` is max minus min across the models --
a row where every encoder lands together is a row model choice does not touch.

### By library, accuracy after the decision rule

Worst-performing library first. For a single-class library -- `fever_false` holds only
`false` examples -- accuracy here *is* that class's recall on that library.

| library | n | `majority_class` | `length_only` | `tfidf_logreg` | `arm_b_finetune@c0.5-d0.0` | `arm_b_finetune@c0.5-d0.3` | `arm_b_finetune@c0.5-d0.6` | spread |
|---|---|---|---|---|---|---|---|---|
| `dysuria_false` | 955 | 0.0% | 5.6% | 51.3% | 91.6% | 92.5% | 94.6% | 94.6pp |
| `dysuria_true` | 612 | 0.0% | 0.0% | 14.9% | 93.6% | 88.1% | 85.0% | 93.6pp |
| `dysuria_null_hedged` | 789 | 100.0% | 100.0% | 89.5% | 86.8% | 89.0% | 93.4% | 13.2pp |
| `dysuria_null_thirdparty` | 865 | 100.0% | 99.8% | 96.5% | 95.6% | 93.2% | 95.5% | 6.8pp |
| `dysuria_null_historical` | 651 | 100.0% | 99.7% | 99.1% | 99.1% | 98.2% | 98.0% | 2.0pp |
| `(none)` | 2978 | 100.0% | 99.1% | 99.8% | 99.8% | 99.9% | 99.7% | 0.9pp |
| `dysuria_null_metaphor` | 757 | 100.0% | 99.7% | 99.6% | 99.7% | 99.5% | 99.9% | 0.5pp |

### By fragment, errors

Ordered by the worst model's error count, so the fragments the comparison is about sort
to the top whichever encoder wins. Counts, not rates: these are the sentences a month of
library work would be spent on. The JSON holds every fragment.

| fragment | library | truth | `majority_class` | `length_only` | `tfidf_logreg` | `arm_b_finetune@c0.5-d0.0` | `arm_b_finetune@c0.5-d0.3` | `arm_b_finetune@c0.5-d0.6` | spread |
|---|---|---|---|---|---|---|---|---|---|
| `dysuria_false:41c43f99` | `dysuria_false` | false | 69 | 69 | 61 | 0 | 0 | 0 | 69 |
| `dysuria_false:85e13aca` | `dysuria_false` | false | 68 | 63 | 1 | 0 | 0 | 0 | 68 |
| `dysuria_false:202255a3` | `dysuria_false` | false | 66 | 66 | 65 | 0 | 0 | 0 | 66 |
| `dysuria_false:2508af9f` | `dysuria_false` | false | 65 | 58 | 10 | 0 | 0 | 0 | 65 |
| `dysuria_false:82438593` | `dysuria_false` | false | 65 | 59 | 34 | 0 | 2 | 0 | 65 |
| `dysuria_false:5837e4e6` | `dysuria_false` | false | 64 | 50 | 56 | 0 | 0 | 1 | 64 |
| `dysuria_false:52998403` | `dysuria_false` | false | 63 | 63 | 0 | 0 | 0 | 0 | 63 |
| `dysuria_false:1fa9bf6a` | `dysuria_false` | false | 62 | 61 | 20 | 0 | 10 | 11 | 62 |
| `dysuria_false:62636499` | `dysuria_false` | false | 62 | 61 | 16 | 0 | 0 | 0 | 62 |
| `dysuria_false:78c1ede4` | `dysuria_false` | false | 62 | 62 | 13 | 0 | 0 | 0 | 62 |
| `dysuria_false:502574f5` | `dysuria_false` | false | 61 | 56 | 21 | 1 | 0 | 0 | 61 |
| `dysuria_false:90277b2d` | `dysuria_false` | false | 61 | 60 | 6 | 0 | 0 | 0 | 61 |
| `dysuria_false:915a7bf7` | `dysuria_false` | false | 61 | 56 | 33 | 0 | 0 | 0 | 61 |
| `dysuria_false:9b29601b` | `dysuria_false` | false | 60 | 60 | 48 | 0 | 0 | 0 | 60 |
| `dysuria_false:18791ae3` | `dysuria_false` | false | 59 | 59 | 1 | 0 | 0 | 0 | 59 |
| `dysuria_false:1548b49b` | `dysuria_false` | false | 57 | 51 | 56 | 0 | 0 | 0 | 57 |
| `dysuria_false:43aa9d18` | `dysuria_false` | false | 57 | 57 | 50 | 48 | 15 | 1 | 56 |
| `dysuria_false:47348026` | `dysuria_false` | false | 57 | 55 | 30 | 21 | 18 | 0 | 57 |
| `dysuria_false:70ff0f9d` | `dysuria_false` | false | 57 | 57 | 2 | 0 | 0 | 0 | 57 |
| `dysuria_false:d46403bb` | `dysuria_false` | false | 57 | 55 | 3 | 0 | 0 | 0 | 57 |
| `dysuria_false:9a3ed060` | `dysuria_false` | false | 56 | 54 | 55 | 12 | 0 | 0 | 56 |
| `dysuria_false:e75c2521` | `dysuria_false` | false | 56 | 54 | 28 | 0 | 0 | 0 | 56 |
| `dysuria_false:d3769665` | `dysuria_false` | false | 54 | 50 | 54 | 0 | 0 | 0 | 54 |
| `dysuria_false:f3a29d90` | `dysuria_false` | false | 54 | 53 | 20 | 0 | 0 | 0 | 54 |
| `dysuria_false:4299d111` | `dysuria_false` | false | 52 | 52 | 7 | 0 | 0 | 0 | 52 |
| `dysuria_false:7fcddee5` | `dysuria_false` | false | 51 | 51 | 43 | 0 | 0 | 1 | 51 |
| `dysuria_false:90df50ee` | `dysuria_false` | false | 51 | 48 | 4 | 0 | 0 | 0 | 51 |
| `dysuria_false:ab9389ac` | `dysuria_false` | false | 51 | 40 | 10 | 0 | 0 | 0 | 51 |
| `dysuria_false:1c30e825` | `dysuria_false` | false | 50 | 49 | 33 | 0 | 0 | 0 | 50 |
| `dysuria_false:3ce959c2` | `dysuria_false` | false | 50 | 48 | 45 | 32 | 13 | 0 | 50 |
| `dysuria_false:1c5be177` | `dysuria_false` | false | 49 | 44 | 2 | 0 | 0 | 0 | 49 |
| `dysuria_true:93845aa6` | `dysuria_true` | true | 49 | 49 | 49 | 0 | 0 | 4 | 49 |
| `dysuria_false:64f15eeb` | `dysuria_false` | false | 48 | 48 | 48 | 0 | 0 | 0 | 48 |
| `dysuria_false:79a25459` | `dysuria_false` | false | 48 | 46 | 30 | 0 | 0 | 0 | 48 |
| `dysuria_false:b2d71275` | `dysuria_false` | false | 47 | 47 | 47 | 0 | 0 | 0 | 47 |
| `dysuria_false:b58ab061` | `dysuria_false` | false | 46 | 35 | 14 | 0 | 0 | 0 | 46 |
| `dysuria_false:e122d65e` | `dysuria_false` | false | 45 | 44 | 37 | 45 | 39 | 20 | 25 |
| `dysuria_true:8ee469c9` | `dysuria_true` | true | 45 | 45 | 23 | 0 | 0 | 5 | 45 |
| `dysuria_false:b7450780` | `dysuria_false` | false | 44 | 32 | 41 | 0 | 0 | 0 | 44 |
| `dysuria_false:ca382087` | `dysuria_false` | false | 43 | 43 | 4 | 0 | 0 | 0 | 43 |

*99 further fragments erred on at least one model; the JSON holds them all.*

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
| false | 2479 | **47** | 0.0% [0.0%, 0.0%] |
| null_ambiguous | 3062 | **90** | 100.0% [100.0%, 100.0%] |
| null_structural | 2978 | **1** | 100.0% [100.0%, 100.0%] |
| true | 1481 | **45** | 0.0% [0.0%, 0.0%] |

### By null sub-class

| sub-class | n | eff n | null recall [95% CI] |
|---|---|---|---|
| hedged | 789 | **20** | 100.0% [100.0%, 100.0%] |
| historical | 651 | **19** | 100.0% [100.0%, 100.0%] |
| metaphor | 757 | **28** | 100.0% [100.0%, 100.0%] |
| third_party | 865 | **23** | 100.0% [100.0%, 100.0%] |

### By fragment library

| library | n | eff n | accuracy [95% CI] |
|---|---|---|---|
| dysuria_false | 2479 | **47** | 0.0% [0.0%, 0.0%] |
| dysuria_null_hedged | 789 | **20** | 100.0% [100.0%, 100.0%] |
| dysuria_null_historical | 651 | **19** | 100.0% [100.0%, 100.0%] |
| dysuria_null_metaphor | 757 | **28** | 100.0% [100.0%, 100.0%] |
| dysuria_null_thirdparty | 865 | **23** | 100.0% [100.0%, 100.0%] |
| dysuria_true | 1481 | **45** | 0.0% [0.0%, 0.0%] |
| (none) | 2978 | **1** | 100.0% [100.0%, 100.0%] |

### Per-fragment errors (worst first)

Whether errors are spread thinly across many fragments or piled onto a few is the difference
between "the method is too weak" (model work) and "these specific ideas are not learnable from
the data we have" (library work, and these are the fragments to write more of). No intervals:
a fragment is one cluster, so an interval over its own examples measures nothing.

92 of 256 decisive fragments were got wrong at least once.

`majority_class`: 3960 errors across 92 of 256 decisive fragments. Half of them fall on **35** fragments (an even spread would be 46.0); the worst ten carry 16.3% of all errors.

| fragment | library | sub-class | truth | correct | accuracy | predicted as |
|---|---|---|---|---|---|---|
| `dysuria_false:41c43f99` | `dysuria_false` | -- | false | 0/69 | 0.0% | null 69 |
| `dysuria_false:85e13aca` | `dysuria_false` | -- | false | 0/68 | 0.0% | null 68 |
| `dysuria_false:202255a3` | `dysuria_false` | -- | false | 0/66 | 0.0% | null 66 |
| `dysuria_false:2508af9f` | `dysuria_false` | -- | false | 0/65 | 0.0% | null 65 |
| `dysuria_false:82438593` | `dysuria_false` | -- | false | 0/65 | 0.0% | null 65 |
| `dysuria_false:5837e4e6` | `dysuria_false` | -- | false | 0/64 | 0.0% | null 64 |
| `dysuria_false:52998403` | `dysuria_false` | -- | false | 0/63 | 0.0% | null 63 |
| `dysuria_false:1fa9bf6a` | `dysuria_false` | -- | false | 0/62 | 0.0% | null 62 |
| `dysuria_false:62636499` | `dysuria_false` | -- | false | 0/62 | 0.0% | null 62 |
| `dysuria_false:78c1ede4` | `dysuria_false` | -- | false | 0/62 | 0.0% | null 62 |
| `dysuria_false:502574f5` | `dysuria_false` | -- | false | 0/61 | 0.0% | null 61 |
| `dysuria_false:90277b2d` | `dysuria_false` | -- | false | 0/61 | 0.0% | null 61 |
| `dysuria_false:915a7bf7` | `dysuria_false` | -- | false | 0/61 | 0.0% | null 61 |
| `dysuria_false:9b29601b` | `dysuria_false` | -- | false | 0/60 | 0.0% | null 60 |
| `dysuria_false:18791ae3` | `dysuria_false` | -- | false | 0/59 | 0.0% | null 59 |
| `dysuria_false:1548b49b` | `dysuria_false` | -- | false | 0/57 | 0.0% | null 57 |
| `dysuria_false:43aa9d18` | `dysuria_false` | -- | false | 0/57 | 0.0% | null 57 |
| `dysuria_false:47348026` | `dysuria_false` | -- | false | 0/57 | 0.0% | null 57 |
| `dysuria_false:70ff0f9d` | `dysuria_false` | -- | false | 0/57 | 0.0% | null 57 |
| `dysuria_false:d46403bb` | `dysuria_false` | -- | false | 0/57 | 0.0% | null 57 |
| `dysuria_false:9a3ed060` | `dysuria_false` | -- | false | 0/56 | 0.0% | null 56 |
| `dysuria_false:e75c2521` | `dysuria_false` | -- | false | 0/56 | 0.0% | null 56 |
| `dysuria_false:d3769665` | `dysuria_false` | -- | false | 0/54 | 0.0% | null 54 |
| `dysuria_false:f3a29d90` | `dysuria_false` | -- | false | 0/54 | 0.0% | null 54 |
| `dysuria_false:4299d111` | `dysuria_false` | -- | false | 0/52 | 0.0% | null 52 |
| `dysuria_false:7fcddee5` | `dysuria_false` | -- | false | 0/51 | 0.0% | null 51 |
| `dysuria_false:90df50ee` | `dysuria_false` | -- | false | 0/51 | 0.0% | null 51 |
| `dysuria_false:ab9389ac` | `dysuria_false` | -- | false | 0/51 | 0.0% | null 51 |
| `dysuria_false:1c30e825` | `dysuria_false` | -- | false | 0/50 | 0.0% | null 50 |
| `dysuria_false:3ce959c2` | `dysuria_false` | -- | false | 0/50 | 0.0% | null 50 |
| `dysuria_false:1c5be177` | `dysuria_false` | -- | false | 0/49 | 0.0% | null 49 |
| `dysuria_true:93845aa6` | `dysuria_true` | -- | true | 0/49 | 0.0% | null 49 |
| `dysuria_false:64f15eeb` | `dysuria_false` | -- | false | 0/48 | 0.0% | null 48 |
| `dysuria_false:79a25459` | `dysuria_false` | -- | false | 0/48 | 0.0% | null 48 |
| `dysuria_false:b2d71275` | `dysuria_false` | -- | false | 0/47 | 0.0% | null 47 |
| `dysuria_false:b58ab061` | `dysuria_false` | -- | false | 0/46 | 0.0% | null 46 |
| `dysuria_false:e122d65e` | `dysuria_false` | -- | false | 0/45 | 0.0% | null 45 |
| `dysuria_true:8ee469c9` | `dysuria_true` | -- | true | 0/45 | 0.0% | null 45 |
| `dysuria_false:b7450780` | `dysuria_false` | -- | false | 0/44 | 0.0% | null 44 |
| `dysuria_false:ca382087` | `dysuria_false` | -- | false | 0/43 | 0.0% | null 43 |

*52 further fragments with at least one error are in the JSON sidecar; every fragment is there regardless of score.*

## `length_only`

Logistic regression on token count alone. The direct measurable test of the length leak: anything materially above majority means text length is a usable proxy for the label, which is a fragment-library problem rather than a model one.

Decision-rule margins selected per fold (on each fold's own validation split): 0.0.
Every fold selected margin 0, so the ruled and raw views below are the same decisions. That is a finding rather than a bug: no margin improved macro-F1 without worsening the `null -> true` rate.

*Confusion matrix, raw argmax*

|  | pred false | pred true | pred null | total |
|---|---|---|---|---|
| **truth false** | 139 | 0 | 2340 | 2479 |
| **truth true** | 52 | 0 | 1429 | 1481 |
| **truth null** | 34 | 0 | 6006 | 6040 |
| **total** | 225 | 0 | 9775 | 10000 |

`null -> true`: 0 of 6040 truly-null examples (0.00%).

*Confusion matrix, after the decision rule*

|  | pred false | pred true | pred null | total |
|---|---|---|---|---|
| **truth false** | 139 | 0 | 2340 | 2479 |
| **truth true** | 52 | 0 | 1429 | 1481 |
| **truth null** | 34 | 0 | 6006 | 6040 |
| **total** | 225 | 0 | 9775 | 10000 |

`null -> true`: 0 of 6040 truly-null examples (0.00%).

### Per class, after the decision rule

| class | support | predicted | precision | recall | F1 |
|---|---|---|---|---|---|
| `false` | 2479 | 225 | 61.8% | 5.6% | 10.3% |
| `true` | 1481 | 0 | -- | 0.0% | 0.0% |
| `null` | 6040 | 9775 | 61.4% | 99.4% | 76.0% |

### By label mode

| label mode | n | eff n | accuracy [95% CI] |
|---|---|---|---|
| false | 2479 | **47** | 5.6% [3.7%, 7.7%] |
| null_ambiguous | 3062 | **90** | 99.8% [99.5%, 100.0%] |
| null_structural | 2978 | **1** | 99.1% [99.1%, 99.1%] |
| true | 1481 | **45** | 0.0% [0.0%, 0.0%] |

### By null sub-class

| sub-class | n | eff n | null recall [95% CI] |
|---|---|---|---|
| hedged | 789 | **20** | 100.0% [100.0%, 100.0%] |
| historical | 651 | **19** | 99.7% [99.0%, 100.0%] |
| metaphor | 757 | **28** | 99.7% [99.2%, 100.0%] |
| third_party | 865 | **23** | 99.8% [99.3%, 100.0%] |

### By fragment library

| library | n | eff n | accuracy [95% CI] |
|---|---|---|---|
| dysuria_false | 2479 | **47** | 5.6% [3.7%, 7.7%] |
| dysuria_null_hedged | 789 | **20** | 100.0% [100.0%, 100.0%] |
| dysuria_null_historical | 651 | **19** | 99.7% [99.0%, 100.0%] |
| dysuria_null_metaphor | 757 | **28** | 99.7% [99.2%, 100.0%] |
| dysuria_null_thirdparty | 865 | **23** | 99.8% [99.3%, 100.0%] |
| dysuria_true | 1481 | **45** | 0.0% [0.0%, 0.0%] |
| (none) | 2978 | **1** | 99.1% [99.1%, 99.1%] |

### Per-fragment errors (worst first)

Whether errors are spread thinly across many fragments or piled onto a few is the difference
between "the method is too weak" (model work) and "these specific ideas are not learnable from
the data we have" (library work, and these are the fragments to write more of). No intervals:
a fragment is one cluster, so an interval over its own examples measures nothing.

95 of 256 decisive fragments were got wrong at least once.

`length_only`: 3827 errors across 95 of 256 decisive fragments. Half of them fall on **35** fragments (an even spread would be 47.5); the worst ten carry 16.3% of all errors.

| fragment | library | sub-class | truth | correct | accuracy | predicted as |
|---|---|---|---|---|---|---|
| `dysuria_false:41c43f99` | `dysuria_false` | -- | false | 0/69 | 0.0% | null 69 |
| `dysuria_false:202255a3` | `dysuria_false` | -- | false | 0/66 | 0.0% | null 66 |
| `dysuria_false:52998403` | `dysuria_false` | -- | false | 0/63 | 0.0% | null 63 |
| `dysuria_false:78c1ede4` | `dysuria_false` | -- | false | 0/62 | 0.0% | null 62 |
| `dysuria_false:9b29601b` | `dysuria_false` | -- | false | 0/60 | 0.0% | null 60 |
| `dysuria_false:18791ae3` | `dysuria_false` | -- | false | 0/59 | 0.0% | null 59 |
| `dysuria_false:43aa9d18` | `dysuria_false` | -- | false | 0/57 | 0.0% | null 57 |
| `dysuria_false:70ff0f9d` | `dysuria_false` | -- | false | 0/57 | 0.0% | null 57 |
| `dysuria_false:4299d111` | `dysuria_false` | -- | false | 0/52 | 0.0% | null 52 |
| `dysuria_false:7fcddee5` | `dysuria_false` | -- | false | 0/51 | 0.0% | null 51 |
| `dysuria_true:93845aa6` | `dysuria_true` | -- | true | 0/49 | 0.0% | null 49 |
| `dysuria_false:64f15eeb` | `dysuria_false` | -- | false | 0/48 | 0.0% | null 48 |
| `dysuria_false:b2d71275` | `dysuria_false` | -- | false | 0/47 | 0.0% | null 47 |
| `dysuria_true:8ee469c9` | `dysuria_true` | -- | true | 0/45 | 0.0% | null 45 |
| `dysuria_false:ca382087` | `dysuria_false` | -- | false | 0/43 | 0.0% | null 43 |
| `dysuria_true:4694eaab` | `dysuria_true` | -- | true | 0/43 | 0.0% | null 43 |
| `dysuria_true:28c7bf7e` | `dysuria_true` | -- | true | 0/42 | 0.0% | false 1, null 41 |
| `dysuria_true:81b6882e` | `dysuria_true` | -- | true | 0/42 | 0.0% | null 42 |
| `dysuria_true:f02ba872` | `dysuria_true` | -- | true | 0/42 | 0.0% | null 42 |
| `dysuria_true:4c214872` | `dysuria_true` | -- | true | 0/41 | 0.0% | null 41 |
| `dysuria_true:8f0ade4e` | `dysuria_true` | -- | true | 0/39 | 0.0% | null 39 |
| `dysuria_true:a2448219` | `dysuria_true` | -- | true | 0/39 | 0.0% | null 39 |
| `dysuria_true:5fefaac6` | `dysuria_true` | -- | true | 0/38 | 0.0% | false 1, null 37 |
| `dysuria_true:71544e46` | `dysuria_true` | -- | true | 0/38 | 0.0% | false 5, null 33 |
| `dysuria_true:985d61a2` | `dysuria_true` | -- | true | 0/36 | 0.0% | null 36 |
| `dysuria_true:9c2b1e02` | `dysuria_true` | -- | true | 0/36 | 0.0% | false 3, null 33 |
| `dysuria_true:d39be0eb` | `dysuria_true` | -- | true | 0/36 | 0.0% | null 36 |
| `dysuria_true:f5df5754` | `dysuria_true` | -- | true | 0/36 | 0.0% | null 36 |
| `dysuria_false:756e426c` | `dysuria_false` | -- | false | 0/35 | 0.0% | null 35 |
| `dysuria_true:73d25d0c` | `dysuria_true` | -- | true | 0/35 | 0.0% | false 7, null 28 |
| `dysuria_true:146d5e49` | `dysuria_true` | -- | true | 0/34 | 0.0% | false 9, null 25 |
| `dysuria_true:7c711665` | `dysuria_true` | -- | true | 0/34 | 0.0% | null 34 |
| `dysuria_true:b898c2de` | `dysuria_true` | -- | true | 0/34 | 0.0% | null 34 |
| `dysuria_true:c3f7adf1` | `dysuria_true` | -- | true | 0/34 | 0.0% | null 34 |
| `dysuria_true:fd186b28` | `dysuria_true` | -- | true | 0/34 | 0.0% | false 10, null 24 |
| `dysuria_true:37c0a85e` | `dysuria_true` | -- | true | 0/32 | 0.0% | false 1, null 31 |
| `dysuria_true:614d867c` | `dysuria_true` | -- | true | 0/32 | 0.0% | null 32 |
| `dysuria_true:83eb7cdc` | `dysuria_true` | -- | true | 0/32 | 0.0% | null 32 |
| `dysuria_true:933cf995` | `dysuria_true` | -- | true | 0/32 | 0.0% | null 32 |
| `dysuria_true:abed15dd` | `dysuria_true` | -- | true | 0/32 | 0.0% | null 32 |

*55 further fragments with at least one error are in the JSON sidecar; every fragment is there regardless of score.*

## `tfidf_logreg`

TF-IDF unigrams and bigrams into logistic regression. Tests whether the dataset is keyword-solvable. Its overall accuracy is close to uninformative; the `null_ambiguous` slice is the number that matters.

Decision-rule margins selected per fold (on each fold's own validation split): 0.0.
Every fold selected margin 0, so the ruled and raw views below are the same decisions. That is a finding rather than a bug: no margin improved macro-F1 without worsening the `null -> true` rate.

*Confusion matrix, raw argmax*

|  | pred false | pred true | pred null | total |
|---|---|---|---|---|
| **truth false** | 1271 | 81 | 1127 | 2479 |
| **truth true** | 65 | 221 | 1195 | 1481 |
| **truth null** | 44 | 83 | 5913 | 6040 |
| **total** | 1380 | 385 | 8235 | 10000 |

`null -> true`: 83 of 6040 truly-null examples (1.37%).

*Confusion matrix, after the decision rule*

|  | pred false | pred true | pred null | total |
|---|---|---|---|---|
| **truth false** | 1271 | 81 | 1127 | 2479 |
| **truth true** | 65 | 221 | 1195 | 1481 |
| **truth null** | 44 | 83 | 5913 | 6040 |
| **total** | 1380 | 385 | 8235 | 10000 |

`null -> true`: 83 of 6040 truly-null examples (1.37%).

### Per class, after the decision rule

| class | support | predicted | precision | recall | F1 |
|---|---|---|---|---|---|
| `false` | 2479 | 1380 | 92.1% | 51.3% | 65.9% |
| `true` | 1481 | 385 | 57.4% | 14.9% | 23.7% |
| `null` | 6040 | 8235 | 71.8% | 97.9% | 82.8% |

### By label mode

| label mode | n | eff n | accuracy [95% CI] |
|---|---|---|---|
| false | 2479 | **47** | 51.3% [40.5%, 61.3%] |
| null_ambiguous | 3062 | **90** | 96.0% [93.6%, 98.1%] |
| null_structural | 2978 | **1** | 99.8% [99.8%, 99.8%] |
| true | 1481 | **45** | 14.9% [8.6%, 21.8%] |

### By null sub-class

| sub-class | n | eff n | null recall [95% CI] |
|---|---|---|---|
| hedged | 789 | **20** | 89.5% [82.8%, 95.7%] |
| historical | 651 | **19** | 99.1% [97.3%, 100.0%] |
| metaphor | 757 | **28** | 99.6% [99.1%, 100.0%] |
| third_party | 865 | **23** | 96.5% [92.2%, 99.8%] |

### By fragment library

| library | n | eff n | accuracy [95% CI] |
|---|---|---|---|
| dysuria_false | 2479 | **47** | 51.3% [40.5%, 61.3%] |
| dysuria_null_hedged | 789 | **20** | 89.5% [82.8%, 95.7%] |
| dysuria_null_historical | 651 | **19** | 99.1% [97.3%, 100.0%] |
| dysuria_null_metaphor | 757 | **28** | 99.6% [99.1%, 100.0%] |
| dysuria_null_thirdparty | 865 | **23** | 96.5% [92.2%, 99.8%] |
| dysuria_true | 1481 | **45** | 14.9% [8.6%, 21.8%] |
| (none) | 2978 | **1** | 99.8% [99.8%, 99.8%] |

### Per-fragment errors (worst first)

Whether errors are spread thinly across many fragments or piled onto a few is the difference
between "the method is too weak" (model work) and "these specific ideas are not learnable from
the data we have" (library work, and these are the fragments to write more of). No intervals:
a fragment is one cluster, so an interval over its own examples measures nothing.

118 of 256 decisive fragments were got wrong at least once.

`tfidf_logreg`: 2590 errors across 118 of 256 decisive fragments. Half of them fall on **30** fragments (an even spread would be 59.0); the worst ten carry 20.9% of all errors.

| fragment | library | sub-class | truth | correct | accuracy | predicted as |
|---|---|---|---|---|---|---|
| `dysuria_false:d3769665` | `dysuria_false` | -- | false | 0/54 | 0.0% | true 19, null 35 |
| `dysuria_true:93845aa6` | `dysuria_true` | -- | true | 0/49 | 0.0% | false 2, null 47 |
| `dysuria_false:64f15eeb` | `dysuria_false` | -- | false | 0/48 | 0.0% | null 48 |
| `dysuria_false:b2d71275` | `dysuria_false` | -- | false | 0/47 | 0.0% | true 1, null 46 |
| `dysuria_true:28c7bf7e` | `dysuria_true` | -- | true | 0/42 | 0.0% | false 6, null 36 |
| `dysuria_true:5fefaac6` | `dysuria_true` | -- | true | 0/38 | 0.0% | false 2, null 36 |
| `dysuria_true:71544e46` | `dysuria_true` | -- | true | 0/38 | 0.0% | null 38 |
| `dysuria_true:985d61a2` | `dysuria_true` | -- | true | 0/36 | 0.0% | null 36 |
| `dysuria_true:73d25d0c` | `dysuria_true` | -- | true | 0/35 | 0.0% | null 35 |
| `dysuria_true:146d5e49` | `dysuria_true` | -- | true | 0/34 | 0.0% | null 34 |
| `dysuria_true:b898c2de` | `dysuria_true` | -- | true | 0/34 | 0.0% | null 34 |
| `dysuria_true:83eb7cdc` | `dysuria_true` | -- | true | 0/32 | 0.0% | null 32 |
| `dysuria_true:abed15dd` | `dysuria_true` | -- | true | 0/32 | 0.0% | null 32 |
| `dysuria_true:09689dd1` | `dysuria_true` | -- | true | 0/30 | 0.0% | false 3, null 27 |
| `dysuria_true:0d7321c0` | `dysuria_true` | -- | true | 0/30 | 0.0% | null 30 |
| `dysuria_true:b87ef0cf` | `dysuria_true` | -- | true | 0/29 | 0.0% | null 29 |
| `dysuria_true:36a17090` | `dysuria_true` | -- | true | 0/28 | 0.0% | null 28 |
| `dysuria_true:6cadf930` | `dysuria_true` | -- | true | 0/27 | 0.0% | null 27 |
| `dysuria_true:aadce996` | `dysuria_true` | -- | true | 0/27 | 0.0% | false 1, null 26 |
| `dysuria_true:bc3a15bf` | `dysuria_true` | -- | true | 0/26 | 0.0% | null 26 |
| `dysuria_true:63f5b24c` | `dysuria_true` | -- | true | 0/25 | 0.0% | null 25 |
| `dysuria_true:c17c33dd` | `dysuria_true` | -- | true | 0/25 | 0.0% | false 1, null 24 |
| `dysuria_true:2e98f278` | `dysuria_true` | -- | true | 0/24 | 0.0% | null 24 |
| `dysuria_null_thirdparty:ddfe9a7b` | `dysuria_null_thirdparty` | third_party | null | 0/8 | 0.0% | true 8 |
| `dysuria_false:202255a3` | `dysuria_false` | -- | false | 1/66 | 1.5% | false 1, true 1, null 64 |
| `dysuria_false:1548b49b` | `dysuria_false` | -- | false | 1/57 | 1.8% | false 1, true 40, null 16 |
| `dysuria_false:9a3ed060` | `dysuria_false` | -- | false | 1/56 | 1.8% | false 1, null 55 |
| `dysuria_false:ffc68e8d` | `dysuria_false` | -- | false | 1/42 | 2.4% | false 1, null 41 |
| `dysuria_true:f02ba872` | `dysuria_true` | -- | true | 1/42 | 2.4% | false 3, true 1, null 38 |
| `dysuria_true:a2448219` | `dysuria_true` | -- | true | 1/39 | 2.6% | true 1, null 38 |
| `dysuria_true:f5df5754` | `dysuria_true` | -- | true | 1/36 | 2.8% | false 1, true 1, null 34 |
| `dysuria_true:c3f7adf1` | `dysuria_true` | -- | true | 1/34 | 2.9% | true 1, null 33 |
| `dysuria_true:37c0a85e` | `dysuria_true` | -- | true | 1/32 | 3.1% | false 3, true 1, null 28 |
| `dysuria_true:02037108` | `dysuria_true` | -- | true | 1/29 | 3.4% | true 1, null 28 |
| `dysuria_true:81b6882e` | `dysuria_true` | -- | true | 2/42 | 4.8% | false 17, true 2, null 23 |
| `dysuria_true:7c711665` | `dysuria_true` | -- | true | 2/34 | 5.9% | false 3, true 2, null 29 |
| `dysuria_false:b7450780` | `dysuria_false` | -- | false | 3/44 | 6.8% | false 3, null 41 |
| `dysuria_true:4694eaab` | `dysuria_true` | -- | true | 3/43 | 7.0% | true 3, null 40 |
| `dysuria_true:9c2b1e02` | `dysuria_true` | -- | true | 3/36 | 8.3% | true 3, null 33 |
| `dysuria_false:d1f38abb` | `dysuria_false` | -- | false | 4/43 | 9.3% | false 4, null 39 |

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
| false | 2479 | **47** | 0.0% [0.0%, 0.0%] |
| null_ambiguous | 3062 | **90** | 100.0% [100.0%, 100.0%] |
| null_structural | 2978 | **1** | 100.0% [100.0%, 100.0%] |
| true | 1481 | **45** | 0.0% [0.0%, 0.0%] |

### By null sub-class

| sub-class | n | eff n | null recall [95% CI] |
|---|---|---|---|
| hedged | 789 | **20** | 100.0% [100.0%, 100.0%] |
| historical | 651 | **19** | 100.0% [100.0%, 100.0%] |
| metaphor | 757 | **28** | 100.0% [100.0%, 100.0%] |
| third_party | 865 | **23** | 100.0% [100.0%, 100.0%] |

### By fragment library

| library | n | eff n | accuracy [95% CI] |
|---|---|---|---|
| dysuria_false | 2479 | **47** | 0.0% [0.0%, 0.0%] |
| dysuria_null_hedged | 789 | **20** | 100.0% [100.0%, 100.0%] |
| dysuria_null_historical | 651 | **19** | 100.0% [100.0%, 100.0%] |
| dysuria_null_metaphor | 757 | **28** | 100.0% [100.0%, 100.0%] |
| dysuria_null_thirdparty | 865 | **23** | 100.0% [100.0%, 100.0%] |
| dysuria_true | 1481 | **45** | 0.0% [0.0%, 0.0%] |
| (none) | 2978 | **1** | 100.0% [100.0%, 100.0%] |

### Per-fragment errors (worst first)

Whether errors are spread thinly across many fragments or piled onto a few is the difference
between "the method is too weak" (model work) and "these specific ideas are not learnable from
the data we have" (library work, and these are the fragments to write more of). No intervals:
a fragment is one cluster, so an interval over its own examples measures nothing.

92 of 256 decisive fragments were got wrong at least once.

`length_only__shuffled`: 3960 errors across 92 of 256 decisive fragments. Half of them fall on **35** fragments (an even spread would be 46.0); the worst ten carry 16.3% of all errors.

| fragment | library | sub-class | truth | correct | accuracy | predicted as |
|---|---|---|---|---|---|---|
| `dysuria_false:41c43f99` | `dysuria_false` | -- | false | 0/69 | 0.0% | null 69 |
| `dysuria_false:85e13aca` | `dysuria_false` | -- | false | 0/68 | 0.0% | null 68 |
| `dysuria_false:202255a3` | `dysuria_false` | -- | false | 0/66 | 0.0% | null 66 |
| `dysuria_false:2508af9f` | `dysuria_false` | -- | false | 0/65 | 0.0% | null 65 |
| `dysuria_false:82438593` | `dysuria_false` | -- | false | 0/65 | 0.0% | null 65 |
| `dysuria_false:5837e4e6` | `dysuria_false` | -- | false | 0/64 | 0.0% | null 64 |
| `dysuria_false:52998403` | `dysuria_false` | -- | false | 0/63 | 0.0% | null 63 |
| `dysuria_false:1fa9bf6a` | `dysuria_false` | -- | false | 0/62 | 0.0% | null 62 |
| `dysuria_false:62636499` | `dysuria_false` | -- | false | 0/62 | 0.0% | null 62 |
| `dysuria_false:78c1ede4` | `dysuria_false` | -- | false | 0/62 | 0.0% | null 62 |
| `dysuria_false:502574f5` | `dysuria_false` | -- | false | 0/61 | 0.0% | null 61 |
| `dysuria_false:90277b2d` | `dysuria_false` | -- | false | 0/61 | 0.0% | null 61 |
| `dysuria_false:915a7bf7` | `dysuria_false` | -- | false | 0/61 | 0.0% | null 61 |
| `dysuria_false:9b29601b` | `dysuria_false` | -- | false | 0/60 | 0.0% | null 60 |
| `dysuria_false:18791ae3` | `dysuria_false` | -- | false | 0/59 | 0.0% | null 59 |
| `dysuria_false:1548b49b` | `dysuria_false` | -- | false | 0/57 | 0.0% | null 57 |
| `dysuria_false:43aa9d18` | `dysuria_false` | -- | false | 0/57 | 0.0% | null 57 |
| `dysuria_false:47348026` | `dysuria_false` | -- | false | 0/57 | 0.0% | null 57 |
| `dysuria_false:70ff0f9d` | `dysuria_false` | -- | false | 0/57 | 0.0% | null 57 |
| `dysuria_false:d46403bb` | `dysuria_false` | -- | false | 0/57 | 0.0% | null 57 |
| `dysuria_false:9a3ed060` | `dysuria_false` | -- | false | 0/56 | 0.0% | null 56 |
| `dysuria_false:e75c2521` | `dysuria_false` | -- | false | 0/56 | 0.0% | null 56 |
| `dysuria_false:d3769665` | `dysuria_false` | -- | false | 0/54 | 0.0% | null 54 |
| `dysuria_false:f3a29d90` | `dysuria_false` | -- | false | 0/54 | 0.0% | null 54 |
| `dysuria_false:4299d111` | `dysuria_false` | -- | false | 0/52 | 0.0% | null 52 |
| `dysuria_false:7fcddee5` | `dysuria_false` | -- | false | 0/51 | 0.0% | null 51 |
| `dysuria_false:90df50ee` | `dysuria_false` | -- | false | 0/51 | 0.0% | null 51 |
| `dysuria_false:ab9389ac` | `dysuria_false` | -- | false | 0/51 | 0.0% | null 51 |
| `dysuria_false:1c30e825` | `dysuria_false` | -- | false | 0/50 | 0.0% | null 50 |
| `dysuria_false:3ce959c2` | `dysuria_false` | -- | false | 0/50 | 0.0% | null 50 |
| `dysuria_false:1c5be177` | `dysuria_false` | -- | false | 0/49 | 0.0% | null 49 |
| `dysuria_true:93845aa6` | `dysuria_true` | -- | true | 0/49 | 0.0% | null 49 |
| `dysuria_false:64f15eeb` | `dysuria_false` | -- | false | 0/48 | 0.0% | null 48 |
| `dysuria_false:79a25459` | `dysuria_false` | -- | false | 0/48 | 0.0% | null 48 |
| `dysuria_false:b2d71275` | `dysuria_false` | -- | false | 0/47 | 0.0% | null 47 |
| `dysuria_false:b58ab061` | `dysuria_false` | -- | false | 0/46 | 0.0% | null 46 |
| `dysuria_false:e122d65e` | `dysuria_false` | -- | false | 0/45 | 0.0% | null 45 |
| `dysuria_true:8ee469c9` | `dysuria_true` | -- | true | 0/45 | 0.0% | null 45 |
| `dysuria_false:b7450780` | `dysuria_false` | -- | false | 0/44 | 0.0% | null 44 |
| `dysuria_false:ca382087` | `dysuria_false` | -- | false | 0/43 | 0.0% | null 43 |

*52 further fragments with at least one error are in the JSON sidecar; every fragment is there regardless of score.*

## `tfidf_logreg__shuffled`

TF-IDF unigrams and bigrams into logistic regression. Tests whether the dataset is keyword-solvable. Its overall accuracy is close to uninformative; the `null_ambiguous` slice is the number that matters. **Negative control:** trained on permuted training labels (seed 7) and evaluated on the unpermuted test split, where it must land at chance.

Decision-rule margins selected per fold (on each fold's own validation split): 0.0.
Every fold selected margin 0, so the ruled and raw views below are the same decisions. That is a finding rather than a bug: no margin improved macro-F1 without worsening the `null -> true` rate.

*Confusion matrix, raw argmax*

|  | pred false | pred true | pred null | total |
|---|---|---|---|---|
| **truth false** | 25 | 0 | 2454 | 2479 |
| **truth true** | 5 | 0 | 1476 | 1481 |
| **truth null** | 25 | 0 | 6015 | 6040 |
| **total** | 55 | 0 | 9945 | 10000 |

`null -> true`: 0 of 6040 truly-null examples (0.00%).

*Confusion matrix, after the decision rule*

|  | pred false | pred true | pred null | total |
|---|---|---|---|---|
| **truth false** | 25 | 0 | 2454 | 2479 |
| **truth true** | 5 | 0 | 1476 | 1481 |
| **truth null** | 25 | 0 | 6015 | 6040 |
| **total** | 55 | 0 | 9945 | 10000 |

`null -> true`: 0 of 6040 truly-null examples (0.00%).

### Per class, after the decision rule

| class | support | predicted | precision | recall | F1 |
|---|---|---|---|---|---|
| `false` | 2479 | 55 | 45.5% | 1.0% | 2.0% |
| `true` | 1481 | 0 | -- | 0.0% | 0.0% |
| `null` | 6040 | 9945 | 60.5% | 99.6% | 75.3% |

### By label mode

| label mode | n | eff n | accuracy [95% CI] |
|---|---|---|---|
| false | 2479 | **47** | 1.0% [0.4%, 1.8%] |
| null_ambiguous | 3062 | **90** | 99.5% [99.3%, 99.8%] |
| null_structural | 2978 | **1** | 99.6% [99.6%, 99.6%] |
| true | 1481 | **45** | 0.0% [0.0%, 0.0%] |

### By null sub-class

| sub-class | n | eff n | null recall [95% CI] |
|---|---|---|---|
| hedged | 789 | **20** | 99.6% [99.1%, 100.0%] |
| historical | 651 | **19** | 99.5% [98.8%, 100.0%] |
| metaphor | 757 | **28** | 99.3% [98.7%, 99.9%] |
| third_party | 865 | **23** | 99.7% [99.2%, 100.0%] |

### By fragment library

| library | n | eff n | accuracy [95% CI] |
|---|---|---|---|
| dysuria_false | 2479 | **47** | 1.0% [0.4%, 1.8%] |
| dysuria_null_hedged | 789 | **20** | 99.6% [99.1%, 100.0%] |
| dysuria_null_historical | 651 | **19** | 99.5% [98.8%, 100.0%] |
| dysuria_null_metaphor | 757 | **28** | 99.3% [98.7%, 99.9%] |
| dysuria_null_thirdparty | 865 | **23** | 99.7% [99.2%, 100.0%] |
| dysuria_true | 1481 | **45** | 0.0% [0.0%, 0.0%] |
| (none) | 2978 | **1** | 99.6% [99.6%, 99.6%] |

### Per-fragment errors (worst first)

Whether errors are spread thinly across many fragments or piled onto a few is the difference
between "the method is too weak" (model work) and "these specific ideas are not learnable from
the data we have" (library work, and these are the fragments to write more of). No intervals:
a fragment is one cluster, so an interval over its own examples measures nothing.

103 of 256 decisive fragments were got wrong at least once.

`tfidf_logreg__shuffled`: 3949 errors across 103 of 256 decisive fragments. Half of them fall on **35** fragments (an even spread would be 51.5); the worst ten carry 16.3% of all errors.

| fragment | library | sub-class | truth | correct | accuracy | predicted as |
|---|---|---|---|---|---|---|
| `dysuria_false:41c43f99` | `dysuria_false` | -- | false | 0/69 | 0.0% | null 69 |
| `dysuria_false:85e13aca` | `dysuria_false` | -- | false | 0/68 | 0.0% | null 68 |
| `dysuria_false:202255a3` | `dysuria_false` | -- | false | 0/66 | 0.0% | null 66 |
| `dysuria_false:2508af9f` | `dysuria_false` | -- | false | 0/65 | 0.0% | null 65 |
| `dysuria_false:52998403` | `dysuria_false` | -- | false | 0/63 | 0.0% | null 63 |
| `dysuria_false:1fa9bf6a` | `dysuria_false` | -- | false | 0/62 | 0.0% | null 62 |
| `dysuria_false:62636499` | `dysuria_false` | -- | false | 0/62 | 0.0% | null 62 |
| `dysuria_false:502574f5` | `dysuria_false` | -- | false | 0/61 | 0.0% | null 61 |
| `dysuria_false:90277b2d` | `dysuria_false` | -- | false | 0/61 | 0.0% | null 61 |
| `dysuria_false:915a7bf7` | `dysuria_false` | -- | false | 0/61 | 0.0% | null 61 |
| `dysuria_false:9b29601b` | `dysuria_false` | -- | false | 0/60 | 0.0% | null 60 |
| `dysuria_false:18791ae3` | `dysuria_false` | -- | false | 0/59 | 0.0% | null 59 |
| `dysuria_false:1548b49b` | `dysuria_false` | -- | false | 0/57 | 0.0% | null 57 |
| `dysuria_false:43aa9d18` | `dysuria_false` | -- | false | 0/57 | 0.0% | null 57 |
| `dysuria_false:47348026` | `dysuria_false` | -- | false | 0/57 | 0.0% | null 57 |
| `dysuria_false:70ff0f9d` | `dysuria_false` | -- | false | 0/57 | 0.0% | null 57 |
| `dysuria_false:d46403bb` | `dysuria_false` | -- | false | 0/57 | 0.0% | null 57 |
| `dysuria_false:9a3ed060` | `dysuria_false` | -- | false | 0/56 | 0.0% | null 56 |
| `dysuria_false:e75c2521` | `dysuria_false` | -- | false | 0/56 | 0.0% | null 56 |
| `dysuria_false:f3a29d90` | `dysuria_false` | -- | false | 0/54 | 0.0% | null 54 |
| `dysuria_false:4299d111` | `dysuria_false` | -- | false | 0/52 | 0.0% | null 52 |
| `dysuria_false:7fcddee5` | `dysuria_false` | -- | false | 0/51 | 0.0% | null 51 |
| `dysuria_false:1c30e825` | `dysuria_false` | -- | false | 0/50 | 0.0% | null 50 |
| `dysuria_true:93845aa6` | `dysuria_true` | -- | true | 0/49 | 0.0% | null 49 |
| `dysuria_false:64f15eeb` | `dysuria_false` | -- | false | 0/48 | 0.0% | null 48 |
| `dysuria_false:79a25459` | `dysuria_false` | -- | false | 0/48 | 0.0% | null 48 |
| `dysuria_false:b58ab061` | `dysuria_false` | -- | false | 0/46 | 0.0% | null 46 |
| `dysuria_false:e122d65e` | `dysuria_false` | -- | false | 0/45 | 0.0% | null 45 |
| `dysuria_true:8ee469c9` | `dysuria_true` | -- | true | 0/45 | 0.0% | null 45 |
| `dysuria_false:ca382087` | `dysuria_false` | -- | false | 0/43 | 0.0% | null 43 |
| `dysuria_false:dad80d87` | `dysuria_false` | -- | false | 0/43 | 0.0% | null 43 |
| `dysuria_true:4694eaab` | `dysuria_true` | -- | true | 0/43 | 0.0% | null 43 |
| `dysuria_false:6aff89c0` | `dysuria_false` | -- | false | 0/42 | 0.0% | null 42 |
| `dysuria_false:ffc68e8d` | `dysuria_false` | -- | false | 0/42 | 0.0% | null 42 |
| `dysuria_true:28c7bf7e` | `dysuria_true` | -- | true | 0/42 | 0.0% | null 42 |
| `dysuria_true:81b6882e` | `dysuria_true` | -- | true | 0/42 | 0.0% | null 42 |
| `dysuria_true:f02ba872` | `dysuria_true` | -- | true | 0/42 | 0.0% | null 42 |
| `dysuria_true:4c214872` | `dysuria_true` | -- | true | 0/41 | 0.0% | false 2, null 39 |
| `dysuria_true:8f0ade4e` | `dysuria_true` | -- | true | 0/39 | 0.0% | null 39 |
| `dysuria_true:a2448219` | `dysuria_true` | -- | true | 0/39 | 0.0% | null 39 |

*63 further fragments with at least one error are in the JSON sidecar; every fragment is there regardless of score.*

## `arm_b_finetune@c0.5-d0.0`

`roberta-base` with **every layer unfrozen**, mean-pooled, with the same `Linear(768, 3)` head -- 110M trainable parameters against Arm A's 2,307. Three epochs at batch 32, learning rate 2e-5, 10% linear warmup, AdamW, fp32. No gradient checkpointing, no 8-bit optimiser, no LoRA, no gradient accumulation: the full model fits in 12GB with room to spare, so anything that reads like a compute compromise would be a mistake rather than a saving. This is the arm that separates "the fragment libraries are the bottleneck" from "the method is too weak": if a fully fine-tuned encoder still cannot read third-party attribution, tense or metaphor, the limit is in the ideas the libraries contain and the fix is library work, not model work.

Decision-rule margins selected per fold (on each fold's own validation split): 0.0, 0.05, 0.15, 0.7, 0.9.

*Confusion matrix, raw argmax*

|  | pred false | pred true | pred null | total |
|---|---|---|---|---|
| **truth false** | 2271 | 3 | 205 | 2479 |
| **truth true** | 0 | 1391 | 90 | 1481 |
| **truth null** | 26 | 137 | 5877 | 6040 |
| **total** | 2297 | 1531 | 6172 | 10000 |

`null -> true`: 137 of 6040 truly-null examples (2.27%).

*Confusion matrix, after the decision rule*

|  | pred false | pred true | pred null | total |
|---|---|---|---|---|
| **truth false** | 2271 | 3 | 205 | 2479 |
| **truth true** | 0 | 1386 | 95 | 1481 |
| **truth null** | 30 | 125 | 5885 | 6040 |
| **total** | 2301 | 1514 | 6185 | 10000 |

`null -> true`: 125 of 6040 truly-null examples (2.07%).

### Per class, after the decision rule

| class | support | predicted | precision | recall | F1 |
|---|---|---|---|---|---|
| `false` | 2479 | 2301 | 98.7% | 91.6% | 95.0% |
| `true` | 1481 | 1514 | 91.5% | 93.6% | 92.6% |
| `null` | 6040 | 6185 | 95.1% | 97.4% | 96.3% |

### By label mode

| label mode | n | eff n | accuracy [95% CI] |
|---|---|---|---|
| false | 2479 | **47** | 91.6% [84.8%, 97.4%] |
| null_ambiguous | 3062 | **90** | 95.1% [91.2%, 98.2%] |
| null_structural | 2978 | **1** | 99.8% [99.8%, 99.8%] |
| true | 1481 | **45** | 93.6% [88.3%, 97.7%] |

### By null sub-class

| sub-class | n | eff n | null recall [95% CI] |
|---|---|---|---|
| hedged | 789 | **20** | 86.8% [77.1%, 95.1%] |
| historical | 651 | **19** | 99.1% [97.7%, 100.0%] |
| metaphor | 757 | **28** | 99.7% [99.3%, 100.0%] |
| third_party | 865 | **23** | 95.6% [86.7%, 100.0%] |

### By fragment library

| library | n | eff n | accuracy [95% CI] |
|---|---|---|---|
| dysuria_false | 2479 | **47** | 91.6% [84.8%, 97.4%] |
| dysuria_null_hedged | 789 | **20** | 86.8% [77.1%, 95.1%] |
| dysuria_null_historical | 651 | **19** | 99.1% [97.7%, 100.0%] |
| dysuria_null_metaphor | 757 | **28** | 99.7% [99.3%, 100.0%] |
| dysuria_null_thirdparty | 865 | **23** | 95.6% [86.7%, 100.0%] |
| dysuria_true | 1481 | **45** | 93.6% [88.3%, 97.7%] |
| (none) | 2978 | **1** | 99.8% [99.8%, 99.8%] |

### Per-fragment errors (worst first)

Whether errors are spread thinly across many fragments or piled onto a few is the difference
between "the method is too weak" (model work) and "these specific ideas are not learnable from
the data we have" (library work, and these are the fragments to write more of). No intervals:
a fragment is one cluster, so an interval over its own examples measures nothing.

35 of 256 decisive fragments were got wrong at least once.

`arm_b_finetune@c0.5-d0.0`: 453 errors across 35 of 256 decisive fragments. Half of them fall on **7** fragments (an even spread would be 17.5); the worst ten carry 66.2% of all errors.

| fragment | library | sub-class | truth | correct | accuracy | predicted as |
|---|---|---|---|---|---|---|
| `dysuria_false:e122d65e` | `dysuria_false` | -- | false | 0/45 | 0.0% | null 45 |
| `dysuria_false:ffc68e8d` | `dysuria_false` | -- | false | 0/42 | 0.0% | null 42 |
| `dysuria_null_hedged:5bf05464` | `dysuria_null_hedged` | hedged | null | 0/15 | 0.0% | false 6, true 9 |
| `dysuria_null_hedged:a5baf1c1` | `dysuria_null_hedged` | hedged | null | 1/21 | 4.8% | true 20, null 1 |
| `dysuria_null_thirdparty:575791a4` | `dysuria_null_thirdparty` | third_party | null | 2/26 | 7.7% | true 24, null 2 |
| `dysuria_null_hedged:bea219da` | `dysuria_null_hedged` | hedged | null | 2/23 | 8.7% | true 21, null 2 |
| `dysuria_null_thirdparty:2fd8fdb5` | `dysuria_null_thirdparty` | third_party | null | 2/14 | 14.3% | true 12, null 2 |
| `dysuria_false:43aa9d18` | `dysuria_false` | -- | false | 9/57 | 15.8% | false 9, null 48 |
| `dysuria_true:146d5e49` | `dysuria_true` | -- | true | 6/34 | 17.6% | true 6, null 28 |
| `dysuria_null_hedged:7e24cdf5` | `dysuria_null_hedged` | hedged | null | 5/21 | 23.8% | false 13, true 3, null 5 |
| `dysuria_false:3ce959c2` | `dysuria_false` | -- | false | 18/50 | 36.0% | false 18, true 1, null 31 |
| `dysuria_true:2e98f278` | `dysuria_true` | -- | true | 10/24 | 41.7% | true 10, null 14 |
| `dysuria_null_hedged:ec574b54` | `dysuria_null_hedged` | hedged | null | 5/12 | 41.7% | false 6, true 1, null 5 |
| `dysuria_null_hedged:b1ae1f9d` | `dysuria_null_hedged` | hedged | null | 14/33 | 42.4% | true 19, null 14 |
| `dysuria_true:b898c2de` | `dysuria_true` | -- | true | 18/34 | 52.9% | true 18, null 16 |
| `dysuria_null_historical:e637313b` | `dysuria_null_historical` | historical | null | 5/9 | 55.6% | true 4, null 5 |
| `dysuria_true:a28e78a6` | `dysuria_true` | -- | true | 18/30 | 60.0% | true 18, null 12 |
| `dysuria_false:47348026` | `dysuria_false` | -- | false | 36/57 | 63.2% | false 36, null 21 |
| `dysuria_null_hedged:8e93e0ff` | `dysuria_null_hedged` | hedged | null | 10/14 | 71.4% | false 1, true 3, null 10 |
| `dysuria_true:63f5b24c` | `dysuria_true` | -- | true | 18/25 | 72.0% | true 18, null 7 |
| `dysuria_null_thirdparty:ddfe9a7b` | `dysuria_null_thirdparty` | third_party | null | 6/8 | 75.0% | true 2, null 6 |
| `dysuria_false:9a3ed060` | `dysuria_false` | -- | false | 44/56 | 78.6% | false 44, true 2, null 10 |
| `dysuria_true:98184373` | `dysuria_true` | -- | true | 23/28 | 82.1% | true 23, null 5 |
| `dysuria_true:985d61a2` | `dysuria_true` | -- | true | 30/36 | 83.3% | true 30, null 6 |
| `dysuria_false:d1f38abb` | `dysuria_false` | -- | false | 36/43 | 83.7% | false 36, null 7 |
| `dysuria_true:abed15dd` | `dysuria_true` | -- | true | 28/32 | 87.5% | true 28, null 4 |
| `dysuria_null_hedged:14bb8513` | `dysuria_null_hedged` | hedged | null | 12/13 | 92.3% | false 1, null 12 |
| `dysuria_true:02037108` | `dysuria_true` | -- | true | 27/29 | 93.1% | true 27, null 2 |
| `dysuria_null_historical:d77b52b4` | `dysuria_null_historical` | historical | null | 15/16 | 93.8% | false 1, null 15 |
| `dysuria_null_historical:56d2ab2b` | `dysuria_null_historical` | historical | null | 20/21 | 95.2% | true 1, null 20 |
| `dysuria_null_hedged:58a8b3c4` | `dysuria_null_hedged` | hedged | null | 21/22 | 95.5% | true 1, null 21 |
| `dysuria_null_metaphor:e06f807a` | `dysuria_null_metaphor` | metaphor | null | 24/25 | 96.0% | true 1, null 24 |
| `dysuria_null_metaphor:83929c02` | `dysuria_null_metaphor` | metaphor | null | 31/32 | 96.9% | true 1, null 31 |
| `dysuria_true:f5df5754` | `dysuria_true` | -- | true | 35/36 | 97.2% | true 35, null 1 |
| `dysuria_false:502574f5` | `dysuria_false` | -- | false | 60/61 | 98.4% | false 60, null 1 |

## `arm_b_finetune@c0.5-d0.3`

`roberta-base` with **every layer unfrozen**, mean-pooled, with the same `Linear(768, 3)` head -- 110M trainable parameters against Arm A's 2,307. Three epochs at batch 32, learning rate 2e-5, 10% linear warmup, AdamW, fp32. No gradient checkpointing, no 8-bit optimiser, no LoRA, no gradient accumulation: the full model fits in 12GB with room to spare, so anything that reads like a compute compromise would be a mistake rather than a saving. This is the arm that separates "the fragment libraries are the bottleneck" from "the method is too weak": if a fully fine-tuned encoder still cannot read third-party attribution, tense or metaphor, the limit is in the ideas the libraries contain and the fix is library work, not model work.

Decision-rule margins selected per fold (on each fold's own validation split): 0.1, 0.4, 0.85, 0.9.

*Confusion matrix, raw argmax*

|  | pred false | pred true | pred null | total |
|---|---|---|---|---|
| **truth false** | 2342 | 11 | 126 | 2479 |
| **truth true** | 1 | 1366 | 114 | 1481 |
| **truth null** | 20 | 164 | 5856 | 6040 |
| **total** | 2363 | 1541 | 6096 | 10000 |

`null -> true`: 164 of 6040 truly-null examples (2.72%).

*Confusion matrix, after the decision rule*

|  | pred false | pred true | pred null | total |
|---|---|---|---|---|
| **truth false** | 2350 | 3 | 126 | 2479 |
| **truth true** | 1 | 1359 | 121 | 1481 |
| **truth null** | 20 | 146 | 5874 | 6040 |
| **total** | 2371 | 1508 | 6121 | 10000 |

`null -> true`: 146 of 6040 truly-null examples (2.42%).

### Per class, after the decision rule

| class | support | predicted | precision | recall | F1 |
|---|---|---|---|---|---|
| `false` | 2479 | 2371 | 99.1% | 94.8% | 96.9% |
| `true` | 1481 | 1508 | 90.1% | 91.8% | 90.9% |
| `null` | 6040 | 6121 | 96.0% | 97.3% | 96.6% |

### By label mode

| label mode | n | eff n | accuracy [95% CI] |
|---|---|---|---|
| false | 2479 | **128** | 94.8% [89.7%, 98.6%] |
| null_ambiguous | 3062 | **90** | 94.7% [90.8%, 97.7%] |
| null_structural | 2978 | **1** | 99.9% [99.9%, 99.9%] |
| true | 1481 | **124** | 91.8% [85.9%, 96.9%] |

### By null sub-class

| sub-class | n | eff n | null recall [95% CI] |
|---|---|---|---|
| hedged | 789 | **20** | 89.0% [79.1%, 96.5%] |
| historical | 651 | **19** | 98.2% [95.1%, 99.8%] |
| metaphor | 757 | **28** | 99.5% [98.6%, 100.0%] |
| third_party | 865 | **23** | 93.2% [83.8%, 99.9%] |

### By fragment library

| library | n | eff n | accuracy [95% CI] |
|---|---|---|---|
| declarative_v1 | 1211 | **160** | 100.0% [100.0%, 100.0%] |
| dysuria_false | 1724 | **47** | 92.5% [86.1%, 97.9%] |
| dysuria_null_hedged | 789 | **20** | 89.0% [79.1%, 96.5%] |
| dysuria_null_historical | 651 | **19** | 98.2% [95.1%, 99.8%] |
| dysuria_null_metaphor | 757 | **28** | 99.5% [98.6%, 100.0%] |
| dysuria_null_thirdparty | 865 | **23** | 93.2% [83.8%, 99.9%] |
| dysuria_true | 1025 | **45** | 88.1% [79.6%, 95.4%] |
| (none) | 2978 | **1** | 99.9% [99.9%, 99.9%] |

### Per-fragment errors (worst first)

Whether errors are spread thinly across many fragments or piled onto a few is the difference
between "the method is too weak" (model work) and "these specific ideas are not learnable from
the data we have" (library work, and these are the fragments to write more of). No intervals:
a fragment is one cluster, so an interval over its own examples measures nothing.

41 of 641 decisive fragments were got wrong at least once.

`arm_b_finetune@c0.5-d0.3`: 413 errors across 41 of 641 decisive fragments. Half of them fall on **9** fragments (an even spread would be 20.5); the worst ten carry 56.4% of all errors.

| fragment | library | sub-class | truth | correct | accuracy | predicted as |
|---|---|---|---|---|---|---|
| `dysuria_false:e122d65e` | `dysuria_false` | -- | false | 0/39 | 0.0% | null 39 |
| `dysuria_false:ffc68e8d` | `dysuria_false` | -- | false | 0/32 | 0.0% | null 32 |
| `dysuria_null_thirdparty:575791a4` | `dysuria_null_thirdparty` | third_party | null | 0/26 | 0.0% | true 26 |
| `dysuria_null_hedged:bea219da` | `dysuria_null_hedged` | hedged | null | 0/23 | 0.0% | true 23 |
| `dysuria_true:98184373` | `dysuria_true` | -- | true | 0/23 | 0.0% | null 23 |
| `dysuria_null_thirdparty:4e732310` | `dysuria_null_thirdparty` | third_party | null | 0/16 | 0.0% | true 16 |
| `dysuria_null_hedged:5bf05464` | `dysuria_null_hedged` | hedged | null | 0/15 | 0.0% | true 15 |
| `dysuria_null_historical:e637313b` | `dysuria_null_historical` | historical | null | 0/9 | 0.0% | true 9 |
| `dysuria_true:985d61a2` | `dysuria_true` | -- | true | 1/22 | 4.5% | true 1, null 21 |
| `dysuria_null_hedged:ec574b54` | `dysuria_null_hedged` | hedged | null | 1/12 | 8.3% | true 11, null 1 |
| `dysuria_true:63f5b24c` | `dysuria_true` | -- | true | 2/19 | 10.5% | true 2, null 17 |
| `dysuria_null_thirdparty:ddfe9a7b` | `dysuria_null_thirdparty` | third_party | null | 1/8 | 12.5% | true 7, null 1 |
| `dysuria_true:f02ba872` | `dysuria_true` | -- | true | 3/21 | 14.3% | true 3, null 18 |
| `dysuria_true:2e98f278` | `dysuria_true` | -- | true | 3/17 | 17.6% | true 3, null 14 |
| `dysuria_null_hedged:7e24cdf5` | `dysuria_null_hedged` | hedged | null | 6/21 | 28.6% | false 15, null 6 |
| `dysuria_null_thirdparty:2fd8fdb5` | `dysuria_null_thirdparty` | third_party | null | 5/14 | 35.7% | true 9, null 5 |
| `dysuria_false:3ce959c2` | `dysuria_false` | -- | false | 14/27 | 51.9% | false 14, true 1, null 12 |
| `dysuria_true:f5df5754` | `dysuria_true` | -- | true | 18/32 | 56.2% | true 18, null 14 |
| `dysuria_false:43aa9d18` | `dysuria_false` | -- | false | 20/35 | 57.1% | false 20, null 15 |
| `dysuria_null_hedged:58a8b3c4` | `dysuria_null_hedged` | hedged | null | 13/22 | 59.1% | true 9, null 13 |
| `dysuria_false:47348026` | `dysuria_false` | -- | false | 31/49 | 63.3% | false 31, null 18 |
| `dysuria_null_hedged:6f4ffbfa` | `dysuria_null_hedged` | hedged | null | 12/17 | 70.6% | true 5, null 12 |
| `dysuria_false:1fa9bf6a` | `dysuria_false` | -- | false | 34/44 | 77.3% | false 34, null 10 |
| `dysuria_true:146d5e49` | `dysuria_true` | -- | true | 18/23 | 78.3% | true 18, null 5 |
| `dysuria_null_hedged:b1ae1f9d` | `dysuria_null_hedged` | hedged | null | 28/33 | 84.8% | true 5, null 28 |
| `dysuria_true:614d867c` | `dysuria_true` | -- | true | 17/20 | 85.0% | false 1, true 17, null 2 |
| `dysuria_true:02037108` | `dysuria_true` | -- | true | 13/15 | 86.7% | true 13, null 2 |
| `dysuria_true:7c711665` | `dysuria_true` | -- | true | 21/24 | 87.5% | true 21, null 3 |
| `dysuria_null_metaphor:83929c02` | `dysuria_null_metaphor` | metaphor | null | 29/32 | 90.6% | true 3, null 29 |
| `dysuria_null_hedged:14bb8513` | `dysuria_null_hedged` | hedged | null | 12/13 | 92.3% | false 1, null 12 |
| `dysuria_null_hedged:b023e25e` | `dysuria_null_hedged` | hedged | null | 12/13 | 92.3% | true 1, null 12 |
| `dysuria_null_historical:d77b52b4` | `dysuria_null_historical` | historical | null | 15/16 | 93.8% | false 1, null 15 |
| `dysuria_false:82438593` | `dysuria_false` | -- | false | 36/38 | 94.7% | false 36, true 2 |
| `dysuria_true:c17c33dd` | `dysuria_true` | -- | true | 18/19 | 94.7% | true 18, null 1 |
| `dysuria_true:3888fc9f` | `dysuria_true` | -- | true | 19/20 | 95.0% | true 19, null 1 |
| `dysuria_null_hedged:a5baf1c1` | `dysuria_null_hedged` | hedged | null | 20/21 | 95.2% | true 1, null 20 |
| `dysuria_null_historical:56d2ab2b` | `dysuria_null_historical` | historical | null | 20/21 | 95.2% | true 1, null 20 |
| `dysuria_null_metaphor:91b6dbda` | `dysuria_null_metaphor` | metaphor | null | 24/25 | 96.0% | true 1, null 24 |
| `dysuria_null_hedged:249a7342` | `dysuria_null_hedged` | hedged | null | 26/27 | 96.3% | true 1, null 26 |
| `dysuria_null_historical:ff52bf2d` | `dysuria_null_historical` | historical | null | 27/28 | 96.4% | false 1, null 27 |

*1 further fragments with at least one error are in the JSON sidecar; every fragment is there regardless of score.*

## `arm_b_finetune@c0.5-d0.6`

`roberta-base` with **every layer unfrozen**, mean-pooled, with the same `Linear(768, 3)` head -- 110M trainable parameters against Arm A's 2,307. Three epochs at batch 32, learning rate 2e-5, 10% linear warmup, AdamW, fp32. No gradient checkpointing, no 8-bit optimiser, no LoRA, no gradient accumulation: the full model fits in 12GB with room to spare, so anything that reads like a compute compromise would be a mistake rather than a saving. This is the arm that separates "the fragment libraries are the bottleneck" from "the method is too weak": if a fully fine-tuned encoder still cannot read third-party attribution, tense or metaphor, the limit is in the ideas the libraries contain and the fix is library work, not model work.

Decision-rule margins selected per fold (on each fold's own validation split): 0.0, 0.05, 0.1, 0.75, 0.8.

*Confusion matrix, raw argmax*

|  | pred false | pred true | pred null | total |
|---|---|---|---|---|
| **truth false** | 2427 | 0 | 52 | 2479 |
| **truth true** | 3 | 1396 | 82 | 1481 |
| **truth null** | 42 | 76 | 5922 | 6040 |
| **total** | 2472 | 1472 | 6056 | 10000 |

`null -> true`: 76 of 6040 truly-null examples (1.26%).

*Confusion matrix, after the decision rule*

|  | pred false | pred true | pred null | total |
|---|---|---|---|---|
| **truth false** | 2427 | 0 | 52 | 2479 |
| **truth true** | 4 | 1389 | 88 | 1481 |
| **truth null** | 42 | 73 | 5925 | 6040 |
| **total** | 2473 | 1462 | 6065 | 10000 |

`null -> true`: 73 of 6040 truly-null examples (1.21%).

### Per class, after the decision rule

| class | support | predicted | precision | recall | F1 |
|---|---|---|---|---|---|
| `false` | 2479 | 2473 | 98.1% | 97.9% | 98.0% |
| `true` | 1481 | 1462 | 95.0% | 93.8% | 94.4% |
| `null` | 6040 | 6065 | 97.7% | 98.1% | 97.9% |

### By label mode

| label mode | n | eff n | accuracy [95% CI] |
|---|---|---|---|
| false | 2479 | **128** | 97.9% [95.2%, 99.9%] |
| null_ambiguous | 3062 | **90** | 96.6% [94.0%, 98.6%] |
| null_structural | 2978 | **1** | 99.7% [99.7%, 99.7%] |
| true | 1481 | **133** | 93.8% [89.6%, 97.0%] |

### By null sub-class

| sub-class | n | eff n | null recall [95% CI] |
|---|---|---|---|
| hedged | 789 | **20** | 93.4% [85.7%, 99.0%] |
| historical | 651 | **19** | 98.0% [95.0%, 99.7%] |
| metaphor | 757 | **28** | 99.9% [99.6%, 100.0%] |
| third_party | 865 | **23** | 95.5% [90.0%, 99.5%] |

### By fragment library

| library | n | eff n | accuracy [95% CI] |
|---|---|---|---|
| declarative_v1 | 2393 | **169** | 100.0% [100.0%, 100.0%] |
| dysuria_false | 955 | **47** | 94.6% [88.2%, 99.6%] |
| dysuria_null_hedged | 789 | **20** | 93.4% [85.7%, 99.0%] |
| dysuria_null_historical | 651 | **19** | 98.0% [95.0%, 99.7%] |
| dysuria_null_metaphor | 757 | **28** | 99.9% [99.6%, 100.0%] |
| dysuria_null_thirdparty | 865 | **23** | 95.5% [90.0%, 99.5%] |
| dysuria_true | 612 | **45** | 85.0% [76.7%, 92.1%] |
| (none) | 2978 | **1** | 99.7% [99.7%, 99.7%] |

### Per-fragment errors (worst first)

Whether errors are spread thinly across many fragments or piled onto a few is the difference
between "the method is too weak" (model work) and "these specific ideas are not learnable from
the data we have" (library work, and these are the fragments to write more of). No intervals:
a fragment is one cluster, so an interval over its own examples measures nothing.

41 of 671 decisive fragments were got wrong at least once.

`arm_b_finetune@c0.5-d0.6`: 249 errors across 41 of 671 decisive fragments. Half of them fall on **8** fragments (an even spread would be 20.5); the worst ten carry 59.0% of all errors.

| fragment | library | sub-class | truth | correct | accuracy | predicted as |
|---|---|---|---|---|---|---|
| `dysuria_false:ffc68e8d` | `dysuria_false` | -- | false | 0/18 | 0.0% | null 18 |
| `dysuria_null_hedged:5bf05464` | `dysuria_null_hedged` | hedged | null | 0/15 | 0.0% | false 15 |
| `dysuria_null_historical:e637313b` | `dysuria_null_historical` | historical | null | 0/9 | 0.0% | true 9 |
| `dysuria_null_thirdparty:4e732310` | `dysuria_null_thirdparty` | third_party | null | 1/16 | 6.2% | false 1, true 14, null 1 |
| `dysuria_true:98184373` | `dysuria_true` | -- | true | 1/13 | 7.7% | true 1, null 12 |
| `dysuria_false:e122d65e` | `dysuria_false` | -- | false | 2/22 | 9.1% | false 2, null 20 |
| `dysuria_true:7c711665` | `dysuria_true` | -- | true | 2/17 | 11.8% | true 2, null 15 |
| `dysuria_true:146d5e49` | `dysuria_true` | -- | true | 3/13 | 23.1% | true 3, null 10 |
| `dysuria_null_hedged:ec574b54` | `dysuria_null_hedged` | hedged | null | 3/12 | 25.0% | false 8, true 1, null 3 |
| `dysuria_true:a28e78a6` | `dysuria_true` | -- | true | 5/16 | 31.2% | true 5, null 11 |
| `dysuria_true:2e98f278` | `dysuria_true` | -- | true | 3/8 | 37.5% | true 3, null 5 |
| `dysuria_true:abed15dd` | `dysuria_true` | -- | true | 3/8 | 37.5% | true 3, null 5 |
| `dysuria_null_thirdparty:575791a4` | `dysuria_null_thirdparty` | third_party | null | 10/26 | 38.5% | true 16, null 10 |
| `dysuria_true:a2448219` | `dysuria_true` | -- | true | 6/11 | 54.5% | true 6, null 5 |
| `dysuria_true:02037108` | `dysuria_true` | -- | true | 5/9 | 55.6% | true 5, null 4 |
| `dysuria_false:1fa9bf6a` | `dysuria_false` | -- | false | 14/25 | 56.0% | false 14, null 11 |
| `dysuria_null_hedged:b1ae1f9d` | `dysuria_null_hedged` | hedged | null | 19/33 | 57.6% | true 14, null 19 |
| `dysuria_null_thirdparty:ddfe9a7b` | `dysuria_null_thirdparty` | third_party | null | 5/8 | 62.5% | true 3, null 5 |
| `dysuria_true:933cf995` | `dysuria_true` | -- | true | 7/11 | 63.6% | true 7, null 4 |
| `dysuria_true:81b6882e` | `dysuria_true` | -- | true | 14/20 | 70.0% | true 14, null 6 |
| `dysuria_true:8ee469c9` | `dysuria_true` | -- | true | 12/17 | 70.6% | true 12, null 5 |
| `dysuria_null_hedged:aadc0b7c` | `dysuria_null_hedged` | hedged | null | 24/32 | 75.0% | false 8, null 24 |
| `dysuria_true:93845aa6` | `dysuria_true` | -- | true | 13/17 | 76.5% | true 13, null 4 |
| `dysuria_true:bc3a15bf` | `dysuria_true` | -- | true | 10/13 | 76.9% | false 3, true 10 |
| `dysuria_null_hedged:14bb8513` | `dysuria_null_hedged` | hedged | null | 11/13 | 84.6% | false 2, null 11 |
| `dysuria_true:614d867c` | `dysuria_true` | -- | true | 12/14 | 85.7% | false 1, true 12, null 1 |
| `dysuria_null_hedged:bea219da` | `dysuria_null_hedged` | hedged | null | 20/23 | 87.0% | true 3, null 20 |
| `dysuria_true:63f5b24c` | `dysuria_true` | -- | true | 11/12 | 91.7% | true 11, null 1 |
| `dysuria_null_thirdparty:2fd8fdb5` | `dysuria_null_thirdparty` | third_party | null | 13/14 | 92.9% | true 1, null 13 |
| `dysuria_null_thirdparty:5d0d98cb` | `dysuria_null_thirdparty` | third_party | null | 27/29 | 93.1% | true 2, null 27 |
| `dysuria_null_historical:d77b52b4` | `dysuria_null_historical` | historical | null | 15/16 | 93.8% | false 1, null 15 |
| `dysuria_false:7fcddee5` | `dysuria_false` | -- | false | 17/18 | 94.4% | false 17, null 1 |
| `dysuria_false:43aa9d18` | `dysuria_false` | -- | false | 19/20 | 95.0% | false 19, null 1 |
| `dysuria_null_historical:56d2ab2b` | `dysuria_null_historical` | historical | null | 20/21 | 95.2% | true 1, null 20 |
| `dysuria_null_historical:e258fbc6` | `dysuria_null_historical` | historical | null | 24/25 | 96.0% | true 1, null 24 |
| `dysuria_false:5837e4e6` | `dysuria_false` | -- | false | 26/27 | 96.3% | false 26, null 1 |
| `dysuria_null_hedged:a3a94ef2` | `dysuria_null_hedged` | hedged | null | 27/28 | 96.4% | true 1, null 27 |
| `dysuria_null_historical:ff52bf2d` | `dysuria_null_historical` | historical | null | 27/28 | 96.4% | false 1, null 27 |
| `dysuria_null_metaphor:13d149c8` | `dysuria_null_metaphor` | metaphor | null | 29/30 | 96.7% | true 1, null 29 |
| `dysuria_null_thirdparty:93c25b3d` | `dysuria_null_thirdparty` | third_party | null | 30/31 | 96.8% | true 1, null 30 |

*1 further fragments with at least one error are in the JSON sidecar; every fragment is there regardless of score.*

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
| 0 | 10000 | 2000 | 2000 | 0.0 | 61.1% | 61.1% | 27.0% | 0.00% |
| 1 | 10000 | 2000 | 2000 | 0.0 | 60.8% | 60.8% | 27.0% | 0.00% |
| 2 | 10000 | 2000 | 2000 | 0.0 | 60.6% | 60.6% | 25.8% | 0.00% |
| 3 | 10000 | 2000 | 2000 | 0.0 | 62.5% | 62.5% | 30.6% | 0.00% |
| 4 | 10000 | 2000 | 2000 | 0.0 | 62.4% | 62.4% | 32.4% | 0.00% |

### `tfidf_logreg`

| fold | train n | val n | test n | margin | acc (raw) | acc (ruled) | macro-F1 | null->true |
|---|---|---|---|---|---|---|---|---|
| 0 | 10000 | 2000 | 2000 | 0.0 | 71.0% | 71.0% | 55.2% | 4.14% |
| 1 | 10000 | 2000 | 2000 | 0.0 | 73.0% | 73.0% | 56.0% | 0.08% |
| 2 | 10000 | 2000 | 2000 | 0.0 | 76.2% | 76.2% | 60.1% | 0.41% |
| 3 | 10000 | 2000 | 2000 | 0.0 | 75.0% | 75.0% | 56.3% | 2.22% |
| 4 | 10000 | 2000 | 2000 | 0.0 | 75.1% | 75.1% | 59.2% | 0.00% |

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
| 0 | 10000 | 2000 | 2000 | 0.0 | 60.5% | 60.5% | 25.8% | 0.00% |
| 1 | 10000 | 2000 | 2000 | 0.0 | 60.1% | 60.1% | 25.9% | 0.00% |
| 2 | 10000 | 2000 | 2000 | 0.0 | 60.4% | 60.4% | 25.1% | 0.00% |
| 3 | 10000 | 2000 | 2000 | 0.0 | 60.5% | 60.5% | 25.4% | 0.00% |
| 4 | 10000 | 2000 | 2000 | 0.0 | 60.6% | 60.6% | 26.5% | 0.00% |

### `arm_b_finetune@c0.5-d0.0`

| fold | train n | val n | test n | margin | acc (raw) | acc (ruled) | macro-F1 | null->true |
|---|---|---|---|---|---|---|---|---|
| 0 | 10000 | 2000 | 2000 | 0.05 | 91.9% | 91.9% | 90.7% | 1.99% |
| 1 | 10000 | 2000 | 2000 | 0.7 | 97.0% | 97.0% | 96.7% | 0.33% |
| 2 | 10000 | 2000 | 2000 | 0.9 | 95.4% | 95.5% | 94.4% | 5.13% |
| 3 | 10000 | 2000 | 2000 | 0.0 | 98.6% | 98.6% | 98.4% | 0.99% |
| 4 | 10000 | 2000 | 2000 | 0.15 | 94.1% | 94.1% | 92.6% | 1.91% |

### `arm_b_finetune@c0.5-d0.3`

| fold | train n | val n | test n | margin | acc (raw) | acc (ruled) | macro-F1 | null->true |
|---|---|---|---|---|---|---|---|---|
| 0 | 10000 | 2000 | 2000 | 0.1 | 95.3% | 95.3% | 94.4% | 1.08% |
| 1 | 10000 | 2000 | 2000 | 0.85 | 93.2% | 93.0% | 90.7% | 2.16% |
| 2 | 10000 | 2000 | 2000 | 0.9 | 95.0% | 95.3% | 94.4% | 5.55% |
| 3 | 10000 | 2000 | 2000 | 0.9 | 96.9% | 97.8% | 97.0% | 3.21% |
| 4 | 10000 | 2000 | 2000 | 0.4 | 97.9% | 97.8% | 97.6% | 0.08% |

### `arm_b_finetune@c0.5-d0.6`

| fold | train n | val n | test n | margin | acc (raw) | acc (ruled) | macro-F1 | null->true |
|---|---|---|---|---|---|---|---|---|
| 0 | 10000 | 2000 | 2000 | 0.05 | 97.5% | 97.5% | 96.9% | 2.15% |
| 1 | 10000 | 2000 | 2000 | 0.75 | 96.8% | 96.7% | 96.0% | 1.91% |
| 2 | 10000 | 2000 | 2000 | 0.8 | 97.2% | 97.1% | 96.1% | 1.66% |
| 3 | 10000 | 2000 | 2000 | 0.0 | 98.0% | 98.0% | 97.8% | 0.33% |
| 4 | 10000 | 2000 | 2000 | 0.1 | 97.8% | 97.8% | 97.1% | 0.00% |

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

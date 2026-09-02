# Encoder training: evaluation report

*Generated 2026-09-02T19:51:00+00:00.*

|  |  |
|---|---|
| signal | `haematuria_present` |
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
| selected epochs | `c0.5-d0.0 3, 2, 3, 3, 2, c0.5-d0.3 3, 1, 1, 2, 1, c0.5-d0.6 1, 1, 1, 1, 2` |
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
| cluster tag coverage | `1 of 6 libraries carry cluster markers; 225 of 691 fragments are in libraries with none` |
| bootstrap | `2000 resamples over clusters, alpha=0.05, seed=0` |

**arms**

* **c0.5-d0.0** (`data/synthetic/generated/decl/c0.5-d0.0`): 10000 examples per epoch, **10000** labelled positions for `haematuria_present`
* **c0.5-d0.3** (`data/synthetic/generated/decl/c0.5-d0.3`): 10000 examples per epoch, **10000** labelled positions for `haematuria_present`
* **c0.5-d0.6** (`data/synthetic/generated/decl/c0.5-d0.6`): 10000 examples per epoch, **10000** labelled positions for `haematuria_present`

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
| `majority_class` | baseline | 7022 | **225** | 43.6% [36.9%, 50.8%] | 20.2% [18.0%, 22.5%] | 60.4% | 60.4% +/- 0.2% |
| `length_only` | baseline | 7022 | **225** | 44.0% [37.3%, 51.1%] | 21.0% [18.7%, 23.3%] | 60.7% | 60.6% +/- 0.4% |
| `tfidf_logreg` | baseline | 7022 | **225** | 68.1% [62.5%, 73.7%] | 62.3% [56.3%, 67.8%] | 77.5% | 77.5% +/- 2.4% |
| `length_only__shuffled` | negative control | 7022 | **225** | 43.6% [36.9%, 50.8%] | 20.2% [18.0%, 22.5%] | 60.4% | 60.4% +/- 0.2% |
| `tfidf_logreg__shuffled` | negative control | 7022 | **225** | 43.5% [36.8%, 50.5%] | 20.6% [18.3%, 22.9%] | 60.2% | 60.2% +/- 0.4% |
| `arm_b_finetune@c0.5-d0.0` | finetune | 7022 | **225** | 89.4% [84.9%, 93.4%] | 89.0% [84.3%, 93.0%] | 92.5% | 92.5% +/- 2.7% |
| `arm_b_finetune@c0.5-d0.3` | finetune | 7022 | **387** | 92.2% [88.9%, 95.1%] | 91.9% [88.3%, 94.8%] | 94.5% | 94.5% +/- 2.6% |
| `arm_b_finetune@c0.5-d0.6` | finetune | 7022 | **394** | 93.7% [91.1%, 95.9%] | 93.4% [90.7%, 95.6%] | 95.5% | 95.5% +/- 3.2% |

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
| `tfidf_logreg` | -- | -- | 92.4% [85.1%, 97.6%] (eff n 45) | 98.1% [96.9%, 99.2%] (eff n 45) | -- | 97.4% [94.8%, 99.3%] (eff n 45) |
| `length_only__shuffled` | -- | -- | 100.0% [100.0%, 100.0%] (eff n 45) | 100.0% [100.0%, 100.0%] (eff n 45) | -- | 100.0% [100.0%, 100.0%] (eff n 45) |
| `tfidf_logreg__shuffled` | -- | -- | 99.5% [99.1%, 99.9%] (eff n 45) | 98.5% [97.2%, 99.6%] (eff n 45) | -- | 99.4% [98.7%, 99.9%] (eff n 45) |
| `arm_b_finetune@c0.5-d0.0` | -- | -- | 85.8% [76.5%, 94.1%] (eff n 45) | 95.1% [87.5%, 99.8%] (eff n 45) | -- | 99.2% [97.8%, 100.0%] (eff n 45) |
| `arm_b_finetune@c0.5-d0.3` | -- | -- | 85.0% [75.0%, 93.5%] (eff n 45) | 98.0% [95.6%, 99.8%] (eff n 45) | -- | 98.8% [96.4%, 100.0%] (eff n 45) |
| `arm_b_finetune@c0.5-d0.6` | -- | -- | 85.5% [75.7%, 94.1%] (eff n 45) | 99.7% [99.3%, 100.0%] (eff n 45) | -- | 99.0% [97.3%, 99.9%] (eff n 45) |

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

| signal | null support | `arm_b_finetune@c0.5-d0.0` | `arm_b_finetune@c0.5-d0.3` | `arm_b_finetune@c0.5-d0.6` |
|---|---|---|---|---|
| `haematuria_present` | 56 | 9.3% | 13.2% | 14.6% |

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

### `arm_b_finetune@c0.5-d0.6`

Recombination test slice: **n 7022**, **eff n 394** clusters, accuracy 93.7% [91.1%, 95.9%]. Holdout: **n 67** submissions, one observation each, scored by 5 fold models at margins 0.9, 0.75, 0.8, 0.0, 0.05. The two `n`s are printed together because they are not the same kind of number and the second is far the smaller.

| signal | true/false/null | omitted | decisive n | decisive acc (mean +/- sd) | worst-case half-width | all n | all acc (mean +/- sd) | null recall |
|---|---|---|---|---|---|---|---|---|
| `haematuria_present` | 9/2/56 | 0 | 11 | 81.8% +/- 11.1% | +/-29.5% | 67 | 84.5% +/- 5.6% | 85.0% +/- 7.0% |

`null -> true` on real text, per fold: `haematuria_present` 14, 8, 5, 8, 6 of 56. This is the cell that invents a symptom into a patient's pre-filled form, counted here on submissions rather than on recombinations.

## Paired on real text

The 67 submissions are the same 67 for every model here, so unlike the recombination
test slice they can be paired: the informative quantity is the submissions two models
disagree about, not the gap between two means. One test per fold, never pooled.

### `arm_b_finetune@c0.5-d0.0` against `arm_b_finetune@c0.5-d0.3`

| fold | pairs | only `arm_b_finetune@c0.5-d0.0` | only `arm_b_finetune@c0.5-d0.3` | p |
|---|---|---|---|---|
| 0 | 67 | 2 | 5 | 0.453 |
| 1 | 67 | 2 | 7 | 0.18 |
| 2 | 67 | 7 | 7 | 1 |
| 3 | 67 | 4 | 5 | 1 |
| 4 | 67 | 6 | 6 | 1 |

`arm_b_finetune@c0.5-d0.0` ahead on 0 folds, `arm_b_finetune@c0.5-d0.3` on 3. `null -> true` mean: 9.3% against 13.2% -- **3.9 points higher** for `arm_b_finetune@c0.5-d0.3` -- more invented symptoms.

*One test per fold over the same 67 submissions, never concatenated: five folds are five models scored on one sample, and pooling would report a p-value for 335 observations that do not exist.*

### `arm_b_finetune@c0.5-d0.0` against `arm_b_finetune@c0.5-d0.6`

| fold | pairs | only `arm_b_finetune@c0.5-d0.0` | only `arm_b_finetune@c0.5-d0.6` | p |
|---|---|---|---|---|
| 0 | 67 | 11 | 7 | 0.481 |
| 1 | 67 | 4 | 5 | 1 |
| 2 | 67 | 2 | 6 | 0.289 |
| 3 | 67 | 8 | 6 | 0.791 |
| 4 | 67 | 3 | 5 | 0.727 |

`arm_b_finetune@c0.5-d0.0` ahead on 2 folds, `arm_b_finetune@c0.5-d0.6` on 3. `null -> true` mean: 9.3% against 14.6% -- **5.4 points higher** for `arm_b_finetune@c0.5-d0.6` -- more invented symptoms.

*One test per fold over the same 67 submissions, never concatenated: five folds are five models scored on one sample, and pooling would report a p-value for 335 observations that do not exist.*

### `arm_b_finetune@c0.5-d0.3` against `arm_b_finetune@c0.5-d0.6`

| fold | pairs | only `arm_b_finetune@c0.5-d0.3` | only `arm_b_finetune@c0.5-d0.6` | p |
|---|---|---|---|---|
| 0 | 67 | 9 | 2 | 0.0654 |
| 1 | 67 | 4 | 0 | 0.125 |
| 2 | 67 | 2 | 6 | 0.289 |
| 3 | 67 | 4 | 1 | 0.375 |
| 4 | 67 | 1 | 3 | 0.625 |

`arm_b_finetune@c0.5-d0.3` ahead on 3 folds, `arm_b_finetune@c0.5-d0.6` on 2. `null -> true` mean: 13.2% against 14.6% -- **1.4 points higher** for `arm_b_finetune@c0.5-d0.6` -- more invented symptoms.

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
| `majority_class` | baseline | 3062 | **135** | 100.0% [100.0%, 100.0%] |
| `length_only` | baseline | 3062 | **135** | 100.0% [100.0%, 100.0%] |
| `tfidf_logreg` | baseline | 3062 | **135** | 95.9% [93.2%, 97.9%] |
| `arm_b_finetune@c0.5-d0.0` | finetune | 3062 | **135** | 93.1% [88.9%, 96.8%] |
| `arm_b_finetune@c0.5-d0.3` | finetune | 3062 | **135** | 93.7% [90.0%, 97.1%] |
| `arm_b_finetune@c0.5-d0.6` | finetune | 3062 | **135** | 94.5% [90.7%, 97.7%] |

### 2. The same comparison, paired

Two overlapping intervals do not settle whether one model beats another on the same
examples. McNemar does, over the examples the two disagree about -- read it alongside the
intervals above, never instead of them.

| pair | n | a only | b only | p |
|---|---|---|---|---|
| `majority_class` vs `length_only` | 3062 | 0 | 0 | 1 |
| `majority_class` vs `tfidf_logreg` | 3062 | 126 | 0 | 2.35e-38 |
| `majority_class` vs `arm_b_finetune@c0.5-d0.0` | 3062 | 226 | 0 | 1.85e-68 |
| `length_only` vs `tfidf_logreg` | 3062 | 126 | 0 | 2.35e-38 |
| `length_only` vs `arm_b_finetune@c0.5-d0.0` | 3062 | 226 | 0 | 1.85e-68 |
| `tfidf_logreg` vs `arm_b_finetune@c0.5-d0.0` | 3062 | 191 | 91 | 2.57e-09 |

Not on this table, because they cannot be paired at all -- different examples on the two sides, so there is nothing for McNemar to pair: `majority_class` vs `arm_b_finetune@c0.5-d0.3`; `majority_class` vs `arm_b_finetune@c0.5-d0.6`; `length_only` vs `arm_b_finetune@c0.5-d0.3`; `length_only` vs `arm_b_finetune@c0.5-d0.6`; `tfidf_logreg` vs `arm_b_finetune@c0.5-d0.3`; `tfidf_logreg` vs `arm_b_finetune@c0.5-d0.6`; `arm_b_finetune@c0.5-d0.0` vs `arm_b_finetune@c0.5-d0.3`; `arm_b_finetune@c0.5-d0.0` vs `arm_b_finetune@c0.5-d0.6`; `arm_b_finetune@c0.5-d0.3` vs `arm_b_finetune@c0.5-d0.6`. Read those through the intervals above and the per-fold spread, and see "Pairs that could not be tested" below.

### 3. Where the errors fall

The per-fragment table below, as one number per model. Errors spread thinly across many
fragments say the method is too weak. Errors piled onto a handful say those specific ideas
are not learnable from the data we have -- and the table names them, which is what makes
this the most decision-useful thing in the report.

* `majority_class`: 3960 errors across 90 of 225 decisive fragments. Half of them fall on **32** fragments (an even spread would be 45.0); the worst ten carry 18.1% of all errors.
* `length_only`: 3933 errors across 90 of 225 decisive fragments. Half of them fall on **32** fragments (an even spread would be 45.0); the worst ten carry 17.8% of all errors.
* `tfidf_logreg`: 2242 errors across 113 of 225 decisive fragments. Half of them fall on **23** fragments (an even spread would be 56.5); the worst ten carry 25.8% of all errors.
* `arm_b_finetune@c0.5-d0.0`: 745 errors across 48 of 225 decisive fragments. Half of them fall on **8** fragments (an even spread would be 24.0); the worst ten carry 61.1% of all errors.
* `arm_b_finetune@c0.5-d0.3`: 545 errors across 40 of 642 decisive fragments. Half of them fall on **8** fragments (an even spread would be 20.0); the worst ten carry 60.0% of all errors.
* `arm_b_finetune@c0.5-d0.6`: 442 errors across 43 of 683 decisive fragments. Half of them fall on **10** fragments (an even spread would be 21.5); the worst ten carry 53.6% of all errors.

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
| `length_only__shuffled` | 60.4% [38.5%, 77.5%] | 25.1% [18.5%, 29.1%] |
| `tfidf_logreg__shuffled` | 60.2% [38.5%, 77.2%] | 25.5% [18.9%, 29.5%] |

## Paired comparisons (McNemar, raw argmax)

Exact two-sided McNemar over the examples the two models disagree about. Pairing unit is the
example, not the cluster -- see the limitations.

| pair | slice | n | a only | b only | p |
|---|---|---|---|---|---|
| `majority_class` vs `length_only` | overall | 10000 | 2 | 27 | 1.62e-06 |
| `majority_class` vs `length_only` | null_ambiguous | 3062 | 0 | 0 | 1 |
| `majority_class` vs `tfidf_logreg` | overall | 10000 | 131 | 1844 | 0 |
| `majority_class` vs `tfidf_logreg` | null_ambiguous | 3062 | 126 | 0 | 2.35e-38 |
| `majority_class` vs `arm_b_finetune@c0.5-d0.0` | overall | 10000 | 234 | 3456 | 0 |
| `majority_class` vs `arm_b_finetune@c0.5-d0.0` | null_ambiguous | 3062 | 226 | 0 | 1.85e-68 |
| `length_only` vs `tfidf_logreg` | overall | 10000 | 136 | 1824 | 0 |
| `length_only` vs `tfidf_logreg` | null_ambiguous | 3062 | 126 | 0 | 2.35e-38 |
| `length_only` vs `arm_b_finetune@c0.5-d0.0` | overall | 10000 | 236 | 3433 | 0 |
| `length_only` vs `arm_b_finetune@c0.5-d0.0` | null_ambiguous | 3062 | 226 | 0 | 1.85e-68 |
| `tfidf_logreg` vs `arm_b_finetune@c0.5-d0.0` | overall | 10000 | 241 | 1750 | 3.32e-282 |
| `tfidf_logreg` vs `arm_b_finetune@c0.5-d0.0` | null_ambiguous | 3062 | 191 | 91 | 2.57e-09 |

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
| `haematuria_false` | 953 | 0.0% | 1.1% | 56.1% | 85.8% | 86.8% | 82.8% | 86.8pp |
| `haematuria_true` | 611 | 0.0% | 0.0% | 30.6% | 87.7% | 87.9% | 82.3% | 87.9pp |
| `haematuria_null_hedged` | 1079 | 100.0% | 100.0% | 92.4% | 85.8% | 85.0% | 85.5% | 15.0pp |
| `haematuria_null_historical` | 1017 | 100.0% | 100.0% | 98.1% | 95.1% | 98.0% | 99.7% | 4.9pp |
| `haematuria_null_thirdparty` | 966 | 100.0% | 100.0% | 97.4% | 99.2% | 98.8% | 99.0% | 2.6pp |
| `(none)` | 2978 | 100.0% | 99.9% | 99.8% | 99.7% | 99.7% | 99.6% | 0.4pp |

### By fragment, errors

Ordered by the worst model's error count, so the fragments the comparison is about sort
to the top whichever encoder wins. Counts, not rates: these are the sentences a month of
library work would be spent on. The JSON holds every fragment.

| fragment | library | truth | `majority_class` | `length_only` | `tfidf_logreg` | `arm_b_finetune@c0.5-d0.0` | `arm_b_finetune@c0.5-d0.3` | `arm_b_finetune@c0.5-d0.6` | spread |
|---|---|---|---|---|---|---|---|---|---|
| `haematuria_false:0e98be72` | `haematuria_false` | false | 82 | 81 | 79 | 81 | 38 | 26 | 56 |
| `haematuria_false:acc7804e` | `haematuria_false` | false | 80 | 80 | 20 | 0 | 0 | 0 | 80 |
| `haematuria_false:56b8af62` | `haematuria_false` | false | 73 | 73 | 51 | 0 | 0 | 3 | 73 |
| `haematuria_false:94f9de34` | `haematuria_false` | false | 72 | 65 | 56 | 0 | 1 | 0 | 72 |
| `haematuria_false:b3fd19df` | `haematuria_false` | false | 72 | 72 | 9 | 0 | 0 | 0 | 72 |
| `haematuria_false:5e090855` | `haematuria_false` | false | 68 | 66 | 0 | 0 | 0 | 0 | 68 |
| `haematuria_false:b692c4ce` | `haematuria_false` | false | 68 | 68 | 20 | 0 | 0 | 0 | 68 |
| `haematuria_false:e23c4950` | `haematuria_false` | false | 68 | 63 | 36 | 0 | 0 | 0 | 68 |
| `haematuria_true:c0ff5eed` | `haematuria_true` | true | 68 | 68 | 65 | 0 | 0 | 6 | 68 |
| `haematuria_true:f2e49699` | `haematuria_true` | true | 65 | 65 | 51 | 0 | 0 | 1 | 65 |
| `haematuria_false:873d5c5b` | `haematuria_false` | false | 62 | 62 | 49 | 0 | 0 | 0 | 62 |
| `haematuria_false:94644abb` | `haematuria_false` | false | 62 | 62 | 0 | 0 | 0 | 0 | 62 |
| `haematuria_false:b0d93eca` | `haematuria_false` | false | 62 | 62 | 0 | 0 | 0 | 0 | 62 |
| `haematuria_true:62126789` | `haematuria_true` | true | 62 | 62 | 12 | 0 | 0 | 0 | 62 |
| `haematuria_true:972bb99b` | `haematuria_true` | true | 61 | 61 | 27 | 0 | 0 | 0 | 61 |
| `haematuria_false:64933508` | `haematuria_false` | false | 60 | 60 | 34 | 0 | 4 | 0 | 60 |
| `haematuria_false:a84358ef` | `haematuria_false` | false | 60 | 60 | 5 | 0 | 0 | 0 | 60 |
| `haematuria_true:7ea098d1` | `haematuria_true` | true | 60 | 60 | 43 | 0 | 0 | 0 | 60 |
| `haematuria_false:cbd9cec5` | `haematuria_false` | false | 59 | 59 | 56 | 2 | 0 | 22 | 59 |
| `haematuria_true:6fadb8bc` | `haematuria_true` | true | 59 | 59 | 59 | 59 | 40 | 23 | 36 |
| `haematuria_false:0722271d` | `haematuria_false` | false | 58 | 58 | 17 | 0 | 0 | 0 | 58 |
| `haematuria_false:58488f8a` | `haematuria_false` | false | 57 | 57 | 0 | 0 | 0 | 0 | 57 |
| `haematuria_false:61bf080a` | `haematuria_false` | false | 57 | 57 | 6 | 0 | 0 | 0 | 57 |
| `haematuria_false:7240a8fb` | `haematuria_false` | false | 57 | 52 | 37 | 1 | 0 | 0 | 57 |
| `haematuria_false:899e3ed9` | `haematuria_false` | false | 57 | 57 | 53 | 2 | 0 | 0 | 57 |
| `haematuria_false:a9960bdc` | `haematuria_false` | false | 57 | 57 | 0 | 0 | 0 | 0 | 57 |
| `haematuria_false:d163df19` | `haematuria_false` | false | 57 | 57 | 56 | 56 | 39 | 23 | 34 |
| `haematuria_false:fc6a0704` | `haematuria_false` | false | 57 | 57 | 17 | 0 | 0 | 0 | 57 |
| `haematuria_true:150663fa` | `haematuria_true` | true | 57 | 57 | 29 | 5 | 0 | 10 | 57 |
| `haematuria_false:0a0b1113` | `haematuria_false` | false | 56 | 56 | 52 | 26 | 22 | 22 | 34 |
| `haematuria_false:9720fe1e` | `haematuria_false` | false | 56 | 55 | 0 | 0 | 0 | 0 | 56 |
| `haematuria_true:d93fd4ce` | `haematuria_true` | true | 56 | 56 | 15 | 0 | 0 | 0 | 56 |
| `haematuria_false:5543da20` | `haematuria_false` | false | 55 | 55 | 10 | 0 | 0 | 0 | 55 |
| `haematuria_false:66629fb1` | `haematuria_false` | false | 55 | 55 | 52 | 12 | 33 | 18 | 43 |
| `haematuria_false:cb3cb6e6` | `haematuria_false` | false | 55 | 52 | 51 | 2 | 7 | 11 | 53 |
| `haematuria_false:d9d4737d` | `haematuria_false` | false | 55 | 55 | 50 | 55 | 0 | 0 | 55 |
| `haematuria_false:c0157f0d` | `haematuria_false` | false | 54 | 54 | 1 | 0 | 0 | 0 | 54 |
| `haematuria_true:245ed73d` | `haematuria_true` | true | 53 | 53 | 29 | 0 | 0 | 0 | 53 |
| `haematuria_false:079edd39` | `haematuria_false` | false | 52 | 52 | 0 | 0 | 0 | 0 | 52 |
| `haematuria_false:4fda0b2c` | `haematuria_false` | false | 52 | 50 | 31 | 0 | 0 | 0 | 52 |

*104 further fragments erred on at least one model; the JSON holds them all.*

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
| hedged | 1079 | **45** | 100.0% [100.0%, 100.0%] |
| historical | 1017 | **45** | 100.0% [100.0%, 100.0%] |
| third_party | 966 | **45** | 100.0% [100.0%, 100.0%] |

### By fragment library

| library | n | eff n | accuracy [95% CI] |
|---|---|---|---|
| haematuria_false | 2479 | **45** | 0.0% [0.0%, 0.0%] |
| haematuria_null_hedged | 1079 | **45** | 100.0% [100.0%, 100.0%] |
| haematuria_null_historical | 1017 | **45** | 100.0% [100.0%, 100.0%] |
| haematuria_null_thirdparty | 966 | **45** | 100.0% [100.0%, 100.0%] |
| haematuria_true | 1481 | **45** | 0.0% [0.0%, 0.0%] |
| (none) | 2978 | **1** | 100.0% [100.0%, 100.0%] |

### Per-fragment errors (worst first)

Whether errors are spread thinly across many fragments or piled onto a few is the difference
between "the method is too weak" (model work) and "these specific ideas are not learnable from
the data we have" (library work, and these are the fragments to write more of). No intervals:
a fragment is one cluster, so an interval over its own examples measures nothing.

90 of 225 decisive fragments were got wrong at least once.

`majority_class`: 3960 errors across 90 of 225 decisive fragments. Half of them fall on **32** fragments (an even spread would be 45.0); the worst ten carry 18.1% of all errors.

| fragment | library | sub-class | truth | correct | accuracy | predicted as |
|---|---|---|---|---|---|---|
| `haematuria_false:0e98be72` | `haematuria_false` | -- | false | 0/82 | 0.0% | null 82 |
| `haematuria_false:acc7804e` | `haematuria_false` | -- | false | 0/80 | 0.0% | null 80 |
| `haematuria_false:56b8af62` | `haematuria_false` | -- | false | 0/73 | 0.0% | null 73 |
| `haematuria_false:94f9de34` | `haematuria_false` | -- | false | 0/72 | 0.0% | null 72 |
| `haematuria_false:b3fd19df` | `haematuria_false` | -- | false | 0/72 | 0.0% | null 72 |
| `haematuria_false:5e090855` | `haematuria_false` | -- | false | 0/68 | 0.0% | null 68 |
| `haematuria_false:b692c4ce` | `haematuria_false` | -- | false | 0/68 | 0.0% | null 68 |
| `haematuria_false:e23c4950` | `haematuria_false` | -- | false | 0/68 | 0.0% | null 68 |
| `haematuria_true:c0ff5eed` | `haematuria_true` | -- | true | 0/68 | 0.0% | null 68 |
| `haematuria_true:f2e49699` | `haematuria_true` | -- | true | 0/65 | 0.0% | null 65 |
| `haematuria_false:873d5c5b` | `haematuria_false` | -- | false | 0/62 | 0.0% | null 62 |
| `haematuria_false:94644abb` | `haematuria_false` | -- | false | 0/62 | 0.0% | null 62 |
| `haematuria_false:b0d93eca` | `haematuria_false` | -- | false | 0/62 | 0.0% | null 62 |
| `haematuria_true:62126789` | `haematuria_true` | -- | true | 0/62 | 0.0% | null 62 |
| `haematuria_true:972bb99b` | `haematuria_true` | -- | true | 0/61 | 0.0% | null 61 |
| `haematuria_false:64933508` | `haematuria_false` | -- | false | 0/60 | 0.0% | null 60 |
| `haematuria_false:a84358ef` | `haematuria_false` | -- | false | 0/60 | 0.0% | null 60 |
| `haematuria_true:7ea098d1` | `haematuria_true` | -- | true | 0/60 | 0.0% | null 60 |
| `haematuria_false:cbd9cec5` | `haematuria_false` | -- | false | 0/59 | 0.0% | null 59 |
| `haematuria_true:6fadb8bc` | `haematuria_true` | -- | true | 0/59 | 0.0% | null 59 |
| `haematuria_false:0722271d` | `haematuria_false` | -- | false | 0/58 | 0.0% | null 58 |
| `haematuria_false:58488f8a` | `haematuria_false` | -- | false | 0/57 | 0.0% | null 57 |
| `haematuria_false:61bf080a` | `haematuria_false` | -- | false | 0/57 | 0.0% | null 57 |
| `haematuria_false:7240a8fb` | `haematuria_false` | -- | false | 0/57 | 0.0% | null 57 |
| `haematuria_false:899e3ed9` | `haematuria_false` | -- | false | 0/57 | 0.0% | null 57 |
| `haematuria_false:a9960bdc` | `haematuria_false` | -- | false | 0/57 | 0.0% | null 57 |
| `haematuria_false:d163df19` | `haematuria_false` | -- | false | 0/57 | 0.0% | null 57 |
| `haematuria_false:fc6a0704` | `haematuria_false` | -- | false | 0/57 | 0.0% | null 57 |
| `haematuria_true:150663fa` | `haematuria_true` | -- | true | 0/57 | 0.0% | null 57 |
| `haematuria_false:0a0b1113` | `haematuria_false` | -- | false | 0/56 | 0.0% | null 56 |
| `haematuria_false:9720fe1e` | `haematuria_false` | -- | false | 0/56 | 0.0% | null 56 |
| `haematuria_true:d93fd4ce` | `haematuria_true` | -- | true | 0/56 | 0.0% | null 56 |
| `haematuria_false:5543da20` | `haematuria_false` | -- | false | 0/55 | 0.0% | null 55 |
| `haematuria_false:66629fb1` | `haematuria_false` | -- | false | 0/55 | 0.0% | null 55 |
| `haematuria_false:cb3cb6e6` | `haematuria_false` | -- | false | 0/55 | 0.0% | null 55 |
| `haematuria_false:d9d4737d` | `haematuria_false` | -- | false | 0/55 | 0.0% | null 55 |
| `haematuria_false:c0157f0d` | `haematuria_false` | -- | false | 0/54 | 0.0% | null 54 |
| `haematuria_true:245ed73d` | `haematuria_true` | -- | true | 0/53 | 0.0% | null 53 |
| `haematuria_false:079edd39` | `haematuria_false` | -- | false | 0/52 | 0.0% | null 52 |
| `haematuria_false:4fda0b2c` | `haematuria_false` | -- | false | 0/52 | 0.0% | null 52 |

*50 further fragments with at least one error are in the JSON sidecar; every fragment is there regardless of score.*

## `length_only`

Logistic regression on token count alone. The direct measurable test of the length leak: anything materially above majority means text length is a usable proxy for the label, which is a fragment-library problem rather than a model one.

Decision-rule margins selected per fold (on each fold's own validation split): 0.0.
Every fold selected margin 0, so the ruled and raw views below are the same decisions. That is a finding rather than a bug: no margin improved macro-F1 without worsening the `null -> true` rate.

*Confusion matrix, raw argmax*

|  | pred false | pred true | pred null | total |
|---|---|---|---|---|
| **truth false** | 27 | 0 | 2452 | 2479 |
| **truth true** | 3 | 0 | 1478 | 1481 |
| **truth null** | 2 | 0 | 6038 | 6040 |
| **total** | 32 | 0 | 9968 | 10000 |

`null -> true`: 0 of 6040 truly-null examples (0.00%).

*Confusion matrix, after the decision rule*

|  | pred false | pred true | pred null | total |
|---|---|---|---|---|
| **truth false** | 27 | 0 | 2452 | 2479 |
| **truth true** | 3 | 0 | 1478 | 1481 |
| **truth null** | 2 | 0 | 6038 | 6040 |
| **total** | 32 | 0 | 9968 | 10000 |

`null -> true`: 0 of 6040 truly-null examples (0.00%).

### Per class, after the decision rule

| class | support | predicted | precision | recall | F1 |
|---|---|---|---|---|---|
| `false` | 2479 | 32 | 84.4% | 1.1% | 2.2% |
| `true` | 1481 | 0 | -- | 0.0% | 0.0% |
| `null` | 6040 | 9968 | 60.6% | 100.0% | 75.4% |

### By label mode

| label mode | n | eff n | accuracy [95% CI] |
|---|---|---|---|
| false | 2479 | **45** | 1.1% [0.4%, 2.0%] |
| null_ambiguous | 3062 | **135** | 100.0% [100.0%, 100.0%] |
| null_structural | 2978 | **1** | 99.9% [99.9%, 99.9%] |
| true | 1481 | **45** | 0.0% [0.0%, 0.0%] |

### By null sub-class

| sub-class | n | eff n | null recall [95% CI] |
|---|---|---|---|
| hedged | 1079 | **45** | 100.0% [100.0%, 100.0%] |
| historical | 1017 | **45** | 100.0% [100.0%, 100.0%] |
| third_party | 966 | **45** | 100.0% [100.0%, 100.0%] |

### By fragment library

| library | n | eff n | accuracy [95% CI] |
|---|---|---|---|
| haematuria_false | 2479 | **45** | 1.1% [0.4%, 2.0%] |
| haematuria_null_hedged | 1079 | **45** | 100.0% [100.0%, 100.0%] |
| haematuria_null_historical | 1017 | **45** | 100.0% [100.0%, 100.0%] |
| haematuria_null_thirdparty | 966 | **45** | 100.0% [100.0%, 100.0%] |
| haematuria_true | 1481 | **45** | 0.0% [0.0%, 0.0%] |
| (none) | 2978 | **1** | 99.9% [99.9%, 99.9%] |

### Per-fragment errors (worst first)

Whether errors are spread thinly across many fragments or piled onto a few is the difference
between "the method is too weak" (model work) and "these specific ideas are not learnable from
the data we have" (library work, and these are the fragments to write more of). No intervals:
a fragment is one cluster, so an interval over its own examples measures nothing.

90 of 225 decisive fragments were got wrong at least once.

`length_only`: 3933 errors across 90 of 225 decisive fragments. Half of them fall on **32** fragments (an even spread would be 45.0); the worst ten carry 17.8% of all errors.

| fragment | library | sub-class | truth | correct | accuracy | predicted as |
|---|---|---|---|---|---|---|
| `haematuria_false:acc7804e` | `haematuria_false` | -- | false | 0/80 | 0.0% | null 80 |
| `haematuria_false:56b8af62` | `haematuria_false` | -- | false | 0/73 | 0.0% | null 73 |
| `haematuria_false:b3fd19df` | `haematuria_false` | -- | false | 0/72 | 0.0% | null 72 |
| `haematuria_false:b692c4ce` | `haematuria_false` | -- | false | 0/68 | 0.0% | null 68 |
| `haematuria_true:c0ff5eed` | `haematuria_true` | -- | true | 0/68 | 0.0% | null 68 |
| `haematuria_true:f2e49699` | `haematuria_true` | -- | true | 0/65 | 0.0% | null 65 |
| `haematuria_false:873d5c5b` | `haematuria_false` | -- | false | 0/62 | 0.0% | null 62 |
| `haematuria_false:94644abb` | `haematuria_false` | -- | false | 0/62 | 0.0% | null 62 |
| `haematuria_false:b0d93eca` | `haematuria_false` | -- | false | 0/62 | 0.0% | null 62 |
| `haematuria_true:62126789` | `haematuria_true` | -- | true | 0/62 | 0.0% | null 62 |
| `haematuria_true:972bb99b` | `haematuria_true` | -- | true | 0/61 | 0.0% | null 61 |
| `haematuria_false:64933508` | `haematuria_false` | -- | false | 0/60 | 0.0% | null 60 |
| `haematuria_false:a84358ef` | `haematuria_false` | -- | false | 0/60 | 0.0% | null 60 |
| `haematuria_true:7ea098d1` | `haematuria_true` | -- | true | 0/60 | 0.0% | null 60 |
| `haematuria_false:cbd9cec5` | `haematuria_false` | -- | false | 0/59 | 0.0% | null 59 |
| `haematuria_true:6fadb8bc` | `haematuria_true` | -- | true | 0/59 | 0.0% | null 59 |
| `haematuria_false:0722271d` | `haematuria_false` | -- | false | 0/58 | 0.0% | null 58 |
| `haematuria_false:58488f8a` | `haematuria_false` | -- | false | 0/57 | 0.0% | null 57 |
| `haematuria_false:61bf080a` | `haematuria_false` | -- | false | 0/57 | 0.0% | null 57 |
| `haematuria_false:899e3ed9` | `haematuria_false` | -- | false | 0/57 | 0.0% | null 57 |
| `haematuria_false:a9960bdc` | `haematuria_false` | -- | false | 0/57 | 0.0% | null 57 |
| `haematuria_false:d163df19` | `haematuria_false` | -- | false | 0/57 | 0.0% | null 57 |
| `haematuria_false:fc6a0704` | `haematuria_false` | -- | false | 0/57 | 0.0% | null 57 |
| `haematuria_true:150663fa` | `haematuria_true` | -- | true | 0/57 | 0.0% | null 57 |
| `haematuria_false:0a0b1113` | `haematuria_false` | -- | false | 0/56 | 0.0% | null 56 |
| `haematuria_true:d93fd4ce` | `haematuria_true` | -- | true | 0/56 | 0.0% | false 1, null 55 |
| `haematuria_false:5543da20` | `haematuria_false` | -- | false | 0/55 | 0.0% | null 55 |
| `haematuria_false:66629fb1` | `haematuria_false` | -- | false | 0/55 | 0.0% | null 55 |
| `haematuria_false:d9d4737d` | `haematuria_false` | -- | false | 0/55 | 0.0% | null 55 |
| `haematuria_false:c0157f0d` | `haematuria_false` | -- | false | 0/54 | 0.0% | null 54 |
| `haematuria_true:245ed73d` | `haematuria_true` | -- | true | 0/53 | 0.0% | null 53 |
| `haematuria_false:079edd39` | `haematuria_false` | -- | false | 0/52 | 0.0% | null 52 |
| `haematuria_false:bae7d81c` | `haematuria_false` | -- | false | 0/51 | 0.0% | null 51 |
| `haematuria_false:21d7fe6b` | `haematuria_false` | -- | false | 0/50 | 0.0% | null 50 |
| `haematuria_true:ed9c190f` | `haematuria_true` | -- | true | 0/50 | 0.0% | null 50 |
| `haematuria_false:75d091ba` | `haematuria_false` | -- | false | 0/49 | 0.0% | null 49 |
| `haematuria_false:9c317cf3` | `haematuria_false` | -- | false | 0/47 | 0.0% | null 47 |
| `haematuria_false:b1f30cef` | `haematuria_false` | -- | false | 0/43 | 0.0% | null 43 |
| `haematuria_true:e93a6a13` | `haematuria_true` | -- | true | 0/42 | 0.0% | null 42 |
| `haematuria_false:f95aa356` | `haematuria_false` | -- | false | 0/41 | 0.0% | null 41 |

*50 further fragments with at least one error are in the JSON sidecar; every fragment is there regardless of score.*

## `tfidf_logreg`

TF-IDF unigrams and bigrams into logistic regression. Tests whether the dataset is keyword-solvable. Its overall accuracy is close to uninformative; the `null_ambiguous` slice is the number that matters.

Decision-rule margins selected per fold (on each fold's own validation split): 0.0.
Every fold selected margin 0, so the ruled and raw views below are the same decisions. That is a finding rather than a bug: no margin improved macro-F1 without worsening the `null -> true` rate.

*Confusion matrix, raw argmax*

|  | pred false | pred true | pred null | total |
|---|---|---|---|---|
| **truth false** | 1391 | 55 | 1033 | 2479 |
| **truth true** | 96 | 453 | 932 | 1481 |
| **truth null** | 60 | 71 | 5909 | 6040 |
| **total** | 1547 | 579 | 7874 | 10000 |

`null -> true`: 71 of 6040 truly-null examples (1.18%).

*Confusion matrix, after the decision rule*

|  | pred false | pred true | pred null | total |
|---|---|---|---|---|
| **truth false** | 1391 | 55 | 1033 | 2479 |
| **truth true** | 96 | 453 | 932 | 1481 |
| **truth null** | 60 | 71 | 5909 | 6040 |
| **total** | 1547 | 579 | 7874 | 10000 |

`null -> true`: 71 of 6040 truly-null examples (1.18%).

### Per class, after the decision rule

| class | support | predicted | precision | recall | F1 |
|---|---|---|---|---|---|
| `false` | 2479 | 1547 | 89.9% | 56.1% | 69.1% |
| `true` | 1481 | 579 | 78.2% | 30.6% | 44.0% |
| `null` | 6040 | 7874 | 75.0% | 97.8% | 84.9% |

### By label mode

| label mode | n | eff n | accuracy [95% CI] |
|---|---|---|---|
| false | 2479 | **45** | 56.1% [45.8%, 67.3%] |
| null_ambiguous | 3062 | **135** | 95.9% [93.2%, 97.9%] |
| null_structural | 2978 | **1** | 99.8% [99.8%, 99.8%] |
| true | 1481 | **45** | 30.6% [20.7%, 40.8%] |

### By null sub-class

| sub-class | n | eff n | null recall [95% CI] |
|---|---|---|---|
| hedged | 1079 | **45** | 92.4% [85.1%, 97.6%] |
| historical | 1017 | **45** | 98.1% [96.9%, 99.2%] |
| third_party | 966 | **45** | 97.4% [94.8%, 99.3%] |

### By fragment library

| library | n | eff n | accuracy [95% CI] |
|---|---|---|---|
| haematuria_false | 2479 | **45** | 56.1% [45.8%, 67.3%] |
| haematuria_null_hedged | 1079 | **45** | 92.4% [85.1%, 97.6%] |
| haematuria_null_historical | 1017 | **45** | 98.1% [96.9%, 99.2%] |
| haematuria_null_thirdparty | 966 | **45** | 97.4% [94.8%, 99.3%] |
| haematuria_true | 1481 | **45** | 30.6% [20.7%, 40.8%] |
| (none) | 2978 | **1** | 99.8% [99.8%, 99.8%] |

### Per-fragment errors (worst first)

Whether errors are spread thinly across many fragments or piled onto a few is the difference
between "the method is too weak" (model work) and "these specific ideas are not learnable from
the data we have" (library work, and these are the fragments to write more of). No intervals:
a fragment is one cluster, so an interval over its own examples measures nothing.

113 of 225 decisive fragments were got wrong at least once.

`tfidf_logreg`: 2242 errors across 113 of 225 decisive fragments. Half of them fall on **23** fragments (an even spread would be 56.5); the worst ten carry 25.8% of all errors.

| fragment | library | sub-class | truth | correct | accuracy | predicted as |
|---|---|---|---|---|---|---|
| `haematuria_true:6fadb8bc` | `haematuria_true` | -- | true | 0/59 | 0.0% | null 59 |
| `haematuria_true:ed9c190f` | `haematuria_true` | -- | true | 0/50 | 0.0% | false 14, null 36 |
| `haematuria_true:e93a6a13` | `haematuria_true` | -- | true | 0/42 | 0.0% | false 1, null 41 |
| `haematuria_true:b8b1c720` | `haematuria_true` | -- | true | 0/36 | 0.0% | null 36 |
| `haematuria_true:5cf89fbc` | `haematuria_true` | -- | true | 0/31 | 0.0% | false 6, null 25 |
| `haematuria_true:e0480739` | `haematuria_true` | -- | true | 0/29 | 0.0% | false 6, null 23 |
| `haematuria_true:f49632f4` | `haematuria_true` | -- | true | 0/27 | 0.0% | null 27 |
| `haematuria_true:e34024ba` | `haematuria_true` | -- | true | 0/22 | 0.0% | null 22 |
| `haematuria_true:a621d471` | `haematuria_true` | -- | true | 0/21 | 0.0% | false 1, null 20 |
| `haematuria_true:08f72e8e` | `haematuria_true` | -- | true | 0/18 | 0.0% | null 18 |
| `haematuria_true:b54f9151` | `haematuria_true` | -- | true | 0/18 | 0.0% | false 2, null 16 |
| `haematuria_true:fbab8b19` | `haematuria_true` | -- | true | 0/18 | 0.0% | false 1, null 17 |
| `haematuria_false:d163df19` | `haematuria_false` | -- | false | 1/57 | 1.8% | false 1, null 56 |
| `haematuria_false:b471d351` | `haematuria_false` | -- | false | 1/39 | 2.6% | false 1, null 38 |
| `haematuria_true:f9f24e70` | `haematuria_true` | -- | true | 1/35 | 2.9% | true 1, null 34 |
| `haematuria_true:16614edd` | `haematuria_true` | -- | true | 1/32 | 3.1% | true 1, null 31 |
| `haematuria_false:0e98be72` | `haematuria_false` | -- | false | 3/82 | 3.7% | false 3, null 79 |
| `haematuria_true:a87130d9` | `haematuria_true` | -- | true | 1/25 | 4.0% | false 5, true 1, null 19 |
| `haematuria_true:9e0324ed` | `haematuria_true` | -- | true | 1/23 | 4.3% | false 8, true 1, null 14 |
| `haematuria_true:c0ff5eed` | `haematuria_true` | -- | true | 3/68 | 4.4% | false 8, true 3, null 57 |
| `haematuria_false:cbd9cec5` | `haematuria_false` | -- | false | 3/59 | 5.1% | false 3, true 14, null 42 |
| `haematuria_true:8b82a179` | `haematuria_true` | -- | true | 1/19 | 5.3% | true 1, null 18 |
| `haematuria_false:66629fb1` | `haematuria_false` | -- | false | 3/55 | 5.5% | false 3, true 1, null 51 |
| `haematuria_true:53852edd` | `haematuria_true` | -- | true | 1/15 | 6.7% | true 1, null 14 |
| `haematuria_false:899e3ed9` | `haematuria_false` | -- | false | 4/57 | 7.0% | false 4, null 53 |
| `haematuria_false:0a0b1113` | `haematuria_false` | -- | false | 4/56 | 7.1% | false 4, null 52 |
| `haematuria_false:cb3cb6e6` | `haematuria_false` | -- | false | 4/55 | 7.3% | false 4, null 51 |
| `haematuria_false:bae7d81c` | `haematuria_false` | -- | false | 4/51 | 7.8% | false 4, true 1, null 46 |
| `haematuria_true:cfd65dba` | `haematuria_true` | -- | true | 2/24 | 8.3% | false 4, true 2, null 18 |
| `haematuria_false:d9d4737d` | `haematuria_false` | -- | false | 5/55 | 9.1% | false 5, true 1, null 49 |
| `haematuria_true:9207612b` | `haematuria_true` | -- | true | 1/11 | 9.1% | true 1, null 10 |
| `haematuria_true:6773fb2e` | `haematuria_true` | -- | true | 3/32 | 9.4% | true 3, null 29 |
| `haematuria_true:82bde4df` | `haematuria_true` | -- | true | 3/27 | 11.1% | false 19, true 3, null 5 |
| `haematuria_true:0a7c2d72` | `haematuria_true` | -- | true | 3/26 | 11.5% | false 1, true 3, null 22 |
| `haematuria_true:58dc10f0` | `haematuria_true` | -- | true | 3/24 | 12.5% | true 3, null 21 |
| `haematuria_null_hedged:2e69277b` | `haematuria_null_hedged` | hedged | null | 4/31 | 12.9% | false 27, null 4 |
| `haematuria_false:873d5c5b` | `haematuria_false` | -- | false | 13/62 | 21.0% | false 13, true 2, null 47 |
| `haematuria_true:5f7823a3` | `haematuria_true` | -- | true | 7/33 | 21.2% | true 7, null 26 |
| `haematuria_true:f2e49699` | `haematuria_true` | -- | true | 14/65 | 21.5% | false 7, true 14, null 44 |
| `haematuria_false:a3acb31d` | `haematuria_false` | -- | false | 8/37 | 21.6% | false 8, null 29 |

*73 further fragments with at least one error are in the JSON sidecar; every fragment is there regardless of score.*

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
| hedged | 1079 | **45** | 100.0% [100.0%, 100.0%] |
| historical | 1017 | **45** | 100.0% [100.0%, 100.0%] |
| third_party | 966 | **45** | 100.0% [100.0%, 100.0%] |

### By fragment library

| library | n | eff n | accuracy [95% CI] |
|---|---|---|---|
| haematuria_false | 2479 | **45** | 0.0% [0.0%, 0.0%] |
| haematuria_null_hedged | 1079 | **45** | 100.0% [100.0%, 100.0%] |
| haematuria_null_historical | 1017 | **45** | 100.0% [100.0%, 100.0%] |
| haematuria_null_thirdparty | 966 | **45** | 100.0% [100.0%, 100.0%] |
| haematuria_true | 1481 | **45** | 0.0% [0.0%, 0.0%] |
| (none) | 2978 | **1** | 100.0% [100.0%, 100.0%] |

### Per-fragment errors (worst first)

Whether errors are spread thinly across many fragments or piled onto a few is the difference
between "the method is too weak" (model work) and "these specific ideas are not learnable from
the data we have" (library work, and these are the fragments to write more of). No intervals:
a fragment is one cluster, so an interval over its own examples measures nothing.

90 of 225 decisive fragments were got wrong at least once.

`length_only__shuffled`: 3960 errors across 90 of 225 decisive fragments. Half of them fall on **32** fragments (an even spread would be 45.0); the worst ten carry 18.1% of all errors.

| fragment | library | sub-class | truth | correct | accuracy | predicted as |
|---|---|---|---|---|---|---|
| `haematuria_false:0e98be72` | `haematuria_false` | -- | false | 0/82 | 0.0% | null 82 |
| `haematuria_false:acc7804e` | `haematuria_false` | -- | false | 0/80 | 0.0% | null 80 |
| `haematuria_false:56b8af62` | `haematuria_false` | -- | false | 0/73 | 0.0% | null 73 |
| `haematuria_false:94f9de34` | `haematuria_false` | -- | false | 0/72 | 0.0% | null 72 |
| `haematuria_false:b3fd19df` | `haematuria_false` | -- | false | 0/72 | 0.0% | null 72 |
| `haematuria_false:5e090855` | `haematuria_false` | -- | false | 0/68 | 0.0% | null 68 |
| `haematuria_false:b692c4ce` | `haematuria_false` | -- | false | 0/68 | 0.0% | null 68 |
| `haematuria_false:e23c4950` | `haematuria_false` | -- | false | 0/68 | 0.0% | null 68 |
| `haematuria_true:c0ff5eed` | `haematuria_true` | -- | true | 0/68 | 0.0% | null 68 |
| `haematuria_true:f2e49699` | `haematuria_true` | -- | true | 0/65 | 0.0% | null 65 |
| `haematuria_false:873d5c5b` | `haematuria_false` | -- | false | 0/62 | 0.0% | null 62 |
| `haematuria_false:94644abb` | `haematuria_false` | -- | false | 0/62 | 0.0% | null 62 |
| `haematuria_false:b0d93eca` | `haematuria_false` | -- | false | 0/62 | 0.0% | null 62 |
| `haematuria_true:62126789` | `haematuria_true` | -- | true | 0/62 | 0.0% | null 62 |
| `haematuria_true:972bb99b` | `haematuria_true` | -- | true | 0/61 | 0.0% | null 61 |
| `haematuria_false:64933508` | `haematuria_false` | -- | false | 0/60 | 0.0% | null 60 |
| `haematuria_false:a84358ef` | `haematuria_false` | -- | false | 0/60 | 0.0% | null 60 |
| `haematuria_true:7ea098d1` | `haematuria_true` | -- | true | 0/60 | 0.0% | null 60 |
| `haematuria_false:cbd9cec5` | `haematuria_false` | -- | false | 0/59 | 0.0% | null 59 |
| `haematuria_true:6fadb8bc` | `haematuria_true` | -- | true | 0/59 | 0.0% | null 59 |
| `haematuria_false:0722271d` | `haematuria_false` | -- | false | 0/58 | 0.0% | null 58 |
| `haematuria_false:58488f8a` | `haematuria_false` | -- | false | 0/57 | 0.0% | null 57 |
| `haematuria_false:61bf080a` | `haematuria_false` | -- | false | 0/57 | 0.0% | null 57 |
| `haematuria_false:7240a8fb` | `haematuria_false` | -- | false | 0/57 | 0.0% | null 57 |
| `haematuria_false:899e3ed9` | `haematuria_false` | -- | false | 0/57 | 0.0% | null 57 |
| `haematuria_false:a9960bdc` | `haematuria_false` | -- | false | 0/57 | 0.0% | null 57 |
| `haematuria_false:d163df19` | `haematuria_false` | -- | false | 0/57 | 0.0% | null 57 |
| `haematuria_false:fc6a0704` | `haematuria_false` | -- | false | 0/57 | 0.0% | null 57 |
| `haematuria_true:150663fa` | `haematuria_true` | -- | true | 0/57 | 0.0% | null 57 |
| `haematuria_false:0a0b1113` | `haematuria_false` | -- | false | 0/56 | 0.0% | null 56 |
| `haematuria_false:9720fe1e` | `haematuria_false` | -- | false | 0/56 | 0.0% | null 56 |
| `haematuria_true:d93fd4ce` | `haematuria_true` | -- | true | 0/56 | 0.0% | null 56 |
| `haematuria_false:5543da20` | `haematuria_false` | -- | false | 0/55 | 0.0% | null 55 |
| `haematuria_false:66629fb1` | `haematuria_false` | -- | false | 0/55 | 0.0% | null 55 |
| `haematuria_false:cb3cb6e6` | `haematuria_false` | -- | false | 0/55 | 0.0% | null 55 |
| `haematuria_false:d9d4737d` | `haematuria_false` | -- | false | 0/55 | 0.0% | null 55 |
| `haematuria_false:c0157f0d` | `haematuria_false` | -- | false | 0/54 | 0.0% | null 54 |
| `haematuria_true:245ed73d` | `haematuria_true` | -- | true | 0/53 | 0.0% | null 53 |
| `haematuria_false:079edd39` | `haematuria_false` | -- | false | 0/52 | 0.0% | null 52 |
| `haematuria_false:4fda0b2c` | `haematuria_false` | -- | false | 0/52 | 0.0% | null 52 |

*50 further fragments with at least one error are in the JSON sidecar; every fragment is there regardless of score.*

## `tfidf_logreg__shuffled`

TF-IDF unigrams and bigrams into logistic regression. Tests whether the dataset is keyword-solvable. Its overall accuracy is close to uninformative; the `null_ambiguous` slice is the number that matters. **Negative control:** trained on permuted training labels (seed 7) and evaluated on the unpermuted test split, where it must land at chance.

Decision-rule margins selected per fold (on each fold's own validation split): 0.0.
Every fold selected margin 0, so the ruled and raw views below are the same decisions. That is a finding rather than a bug: no margin improved macro-F1 without worsening the `null -> true` rate.

*Confusion matrix, raw argmax*

|  | pred false | pred true | pred null | total |
|---|---|---|---|---|
| **truth false** | 15 | 0 | 2464 | 2479 |
| **truth true** | 2 | 1 | 1478 | 1481 |
| **truth null** | 36 | 1 | 6003 | 6040 |
| **total** | 53 | 2 | 9945 | 10000 |

`null -> true`: 1 of 6040 truly-null examples (0.02%).

*Confusion matrix, after the decision rule*

|  | pred false | pred true | pred null | total |
|---|---|---|---|---|
| **truth false** | 15 | 0 | 2464 | 2479 |
| **truth true** | 2 | 1 | 1478 | 1481 |
| **truth null** | 36 | 1 | 6003 | 6040 |
| **total** | 53 | 2 | 9945 | 10000 |

`null -> true`: 1 of 6040 truly-null examples (0.02%).

### Per class, after the decision rule

| class | support | predicted | precision | recall | F1 |
|---|---|---|---|---|---|
| `false` | 2479 | 53 | 28.3% | 0.6% | 1.2% |
| `true` | 1481 | 2 | 50.0% | 0.1% | 0.1% |
| `null` | 6040 | 9945 | 60.4% | 99.4% | 75.1% |

### By label mode

| label mode | n | eff n | accuracy [95% CI] |
|---|---|---|---|
| false | 2479 | **45** | 0.6% [0.3%, 1.0%] |
| null_ambiguous | 3062 | **135** | 99.2% [98.6%, 99.6%] |
| null_structural | 2978 | **1** | 99.6% [99.6%, 99.6%] |
| true | 1481 | **45** | 0.1% [0.0%, 0.2%] |

### By null sub-class

| sub-class | n | eff n | null recall [95% CI] |
|---|---|---|---|
| hedged | 1079 | **45** | 99.5% [99.1%, 99.9%] |
| historical | 1017 | **45** | 98.5% [97.2%, 99.6%] |
| third_party | 966 | **45** | 99.4% [98.7%, 99.9%] |

### By fragment library

| library | n | eff n | accuracy [95% CI] |
|---|---|---|---|
| haematuria_false | 2479 | **45** | 0.6% [0.3%, 1.0%] |
| haematuria_null_hedged | 1079 | **45** | 99.5% [99.1%, 99.9%] |
| haematuria_null_historical | 1017 | **45** | 98.5% [97.2%, 99.6%] |
| haematuria_null_thirdparty | 966 | **45** | 99.4% [98.7%, 99.9%] |
| haematuria_true | 1481 | **45** | 0.1% [0.0%, 0.2%] |
| (none) | 2978 | **1** | 99.6% [99.6%, 99.6%] |

### Per-fragment errors (worst first)

Whether errors are spread thinly across many fragments or piled onto a few is the difference
between "the method is too weak" (model work) and "these specific ideas are not learnable from
the data we have" (library work, and these are the fragments to write more of). No intervals:
a fragment is one cluster, so an interval over its own examples measures nothing.

108 of 225 decisive fragments were got wrong at least once.

`tfidf_logreg__shuffled`: 3970 errors across 108 of 225 decisive fragments. Half of them fall on **32** fragments (an even spread would be 54.0); the worst ten carry 18.0% of all errors.

| fragment | library | sub-class | truth | correct | accuracy | predicted as |
|---|---|---|---|---|---|---|
| `haematuria_false:0e98be72` | `haematuria_false` | -- | false | 0/82 | 0.0% | null 82 |
| `haematuria_false:acc7804e` | `haematuria_false` | -- | false | 0/80 | 0.0% | null 80 |
| `haematuria_false:b3fd19df` | `haematuria_false` | -- | false | 0/72 | 0.0% | null 72 |
| `haematuria_false:5e090855` | `haematuria_false` | -- | false | 0/68 | 0.0% | null 68 |
| `haematuria_false:b692c4ce` | `haematuria_false` | -- | false | 0/68 | 0.0% | null 68 |
| `haematuria_false:e23c4950` | `haematuria_false` | -- | false | 0/68 | 0.0% | null 68 |
| `haematuria_true:c0ff5eed` | `haematuria_true` | -- | true | 0/68 | 0.0% | null 68 |
| `haematuria_true:f2e49699` | `haematuria_true` | -- | true | 0/65 | 0.0% | null 65 |
| `haematuria_false:94644abb` | `haematuria_false` | -- | false | 0/62 | 0.0% | null 62 |
| `haematuria_false:b0d93eca` | `haematuria_false` | -- | false | 0/62 | 0.0% | null 62 |
| `haematuria_true:62126789` | `haematuria_true` | -- | true | 0/62 | 0.0% | null 62 |
| `haematuria_true:972bb99b` | `haematuria_true` | -- | true | 0/61 | 0.0% | null 61 |
| `haematuria_false:64933508` | `haematuria_false` | -- | false | 0/60 | 0.0% | null 60 |
| `haematuria_false:a84358ef` | `haematuria_false` | -- | false | 0/60 | 0.0% | null 60 |
| `haematuria_true:7ea098d1` | `haematuria_true` | -- | true | 0/60 | 0.0% | null 60 |
| `haematuria_false:0722271d` | `haematuria_false` | -- | false | 0/58 | 0.0% | null 58 |
| `haematuria_false:58488f8a` | `haematuria_false` | -- | false | 0/57 | 0.0% | null 57 |
| `haematuria_false:7240a8fb` | `haematuria_false` | -- | false | 0/57 | 0.0% | null 57 |
| `haematuria_false:899e3ed9` | `haematuria_false` | -- | false | 0/57 | 0.0% | null 57 |
| `haematuria_false:d163df19` | `haematuria_false` | -- | false | 0/57 | 0.0% | null 57 |
| `haematuria_false:fc6a0704` | `haematuria_false` | -- | false | 0/57 | 0.0% | null 57 |
| `haematuria_true:150663fa` | `haematuria_true` | -- | true | 0/57 | 0.0% | null 57 |
| `haematuria_false:0a0b1113` | `haematuria_false` | -- | false | 0/56 | 0.0% | null 56 |
| `haematuria_false:9720fe1e` | `haematuria_false` | -- | false | 0/56 | 0.0% | null 56 |
| `haematuria_true:d93fd4ce` | `haematuria_true` | -- | true | 0/56 | 0.0% | null 56 |
| `haematuria_false:5543da20` | `haematuria_false` | -- | false | 0/55 | 0.0% | null 55 |
| `haematuria_false:66629fb1` | `haematuria_false` | -- | false | 0/55 | 0.0% | null 55 |
| `haematuria_false:cb3cb6e6` | `haematuria_false` | -- | false | 0/55 | 0.0% | null 55 |
| `haematuria_false:d9d4737d` | `haematuria_false` | -- | false | 0/55 | 0.0% | null 55 |
| `haematuria_false:c0157f0d` | `haematuria_false` | -- | false | 0/54 | 0.0% | null 54 |
| `haematuria_true:245ed73d` | `haematuria_true` | -- | true | 0/53 | 0.0% | null 53 |
| `haematuria_false:079edd39` | `haematuria_false` | -- | false | 0/52 | 0.0% | null 52 |
| `haematuria_false:4fda0b2c` | `haematuria_false` | -- | false | 0/52 | 0.0% | null 52 |
| `haematuria_false:bae7d81c` | `haematuria_false` | -- | false | 0/51 | 0.0% | null 51 |
| `haematuria_false:21d7fe6b` | `haematuria_false` | -- | false | 0/50 | 0.0% | null 50 |
| `haematuria_true:ed9c190f` | `haematuria_true` | -- | true | 0/50 | 0.0% | false 1, null 49 |
| `haematuria_false:9c317cf3` | `haematuria_false` | -- | false | 0/47 | 0.0% | null 47 |
| `haematuria_false:b1f30cef` | `haematuria_false` | -- | false | 0/43 | 0.0% | null 43 |
| `haematuria_false:f06e4c14` | `haematuria_false` | -- | false | 0/43 | 0.0% | null 43 |
| `haematuria_true:e93a6a13` | `haematuria_true` | -- | true | 0/42 | 0.0% | null 42 |

*68 further fragments with at least one error are in the JSON sidecar; every fragment is there regardless of score.*

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

## `arm_b_finetune@c0.5-d0.6`

`roberta-base` with **every layer unfrozen**, mean-pooled, with the same `Linear(768, 3)` head -- 110M trainable parameters against Arm A's 2,307. Three epochs at batch 32, learning rate 2e-5, 10% linear warmup, AdamW, fp32. No gradient checkpointing, no 8-bit optimiser, no LoRA, no gradient accumulation: the full model fits in 12GB with room to spare, so anything that reads like a compute compromise would be a mistake rather than a saving. This is the arm that separates "the fragment libraries are the bottleneck" from "the method is too weak": if a fully fine-tuned encoder still cannot read third-party attribution, tense or metaphor, the limit is in the ideas the libraries contain and the fix is library work, not model work.

Decision-rule margins selected per fold (on each fold's own validation split): 0.0, 0.05, 0.75, 0.8, 0.9.

*Confusion matrix, raw argmax*

|  | pred false | pred true | pred null | total |
|---|---|---|---|---|
| **truth false** | 2314 | 23 | 142 | 2479 |
| **truth true** | 5 | 1384 | 92 | 1481 |
| **truth null** | 18 | 184 | 5838 | 6040 |
| **total** | 2337 | 1591 | 6072 | 10000 |

`null -> true`: 184 of 6040 truly-null examples (3.05%).

*Confusion matrix, after the decision rule*

|  | pred false | pred true | pred null | total |
|---|---|---|---|---|
| **truth false** | 2315 | 20 | 144 | 2479 |
| **truth true** | 7 | 1372 | 102 | 1481 |
| **truth null** | 20 | 161 | 5859 | 6040 |
| **total** | 2342 | 1553 | 6105 | 10000 |

`null -> true`: 161 of 6040 truly-null examples (2.67%).

### Per class, after the decision rule

| class | support | predicted | precision | recall | F1 |
|---|---|---|---|---|---|
| `false` | 2479 | 2342 | 98.8% | 93.4% | 96.0% |
| `true` | 1481 | 1553 | 88.3% | 92.6% | 90.4% |
| `null` | 6040 | 6105 | 96.0% | 97.0% | 96.5% |

### By label mode

| label mode | n | eff n | accuracy [95% CI] |
|---|---|---|---|
| false | 2479 | **131** | 93.4% [88.6%, 97.5%] |
| null_ambiguous | 3062 | **135** | 94.5% [90.7%, 97.7%] |
| null_structural | 2978 | **1** | 99.6% [99.6%, 99.6%] |
| true | 1481 | **128** | 92.6% [87.4%, 96.9%] |

### By null sub-class

| sub-class | n | eff n | null recall [95% CI] |
|---|---|---|---|
| hedged | 1079 | **45** | 85.5% [75.7%, 94.1%] |
| historical | 1017 | **45** | 99.7% [99.3%, 100.0%] |
| third_party | 966 | **45** | 99.0% [97.3%, 99.9%] |

### By fragment library

| library | n | eff n | accuracy [95% CI] |
|---|---|---|---|
| declarative_v1 | 2396 | **169** | 100.0% [99.9%, 100.0%] |
| haematuria_false | 953 | **45** | 82.8% [71.9%, 92.5%] |
| haematuria_null_hedged | 1079 | **45** | 85.5% [75.7%, 94.1%] |
| haematuria_null_historical | 1017 | **45** | 99.7% [99.3%, 100.0%] |
| haematuria_null_thirdparty | 966 | **45** | 99.0% [97.3%, 99.9%] |
| haematuria_true | 611 | **45** | 82.3% [70.2%, 91.7%] |
| (none) | 2978 | **1** | 99.6% [99.6%, 99.6%] |

### Per-fragment errors (worst first)

Whether errors are spread thinly across many fragments or piled onto a few is the difference
between "the method is too weak" (model work) and "these specific ideas are not learnable from
the data we have" (library work, and these are the fragments to write more of). No intervals:
a fragment is one cluster, so an interval over its own examples measures nothing.

43 of 683 decisive fragments were got wrong at least once.

`arm_b_finetune@c0.5-d0.6`: 442 errors across 43 of 683 decisive fragments. Half of them fall on **10** fragments (an even spread would be 21.5); the worst ten carry 53.6% of all errors.

| fragment | library | sub-class | truth | correct | accuracy | predicted as |
|---|---|---|---|---|---|---|
| `haematuria_null_hedged:e2b503fc` | `haematuria_null_hedged` | hedged | null | 0/29 | 0.0% | true 29 |
| `haematuria_false:0e98be72` | `haematuria_false` | -- | false | 0/26 | 0.0% | null 26 |
| `haematuria_null_hedged:0a1e23ec` | `haematuria_null_hedged` | hedged | null | 0/24 | 0.0% | true 24 |
| `haematuria_null_hedged:d64cf17c` | `haematuria_null_hedged` | hedged | null | 0/24 | 0.0% | true 24 |
| `haematuria_false:d163df19` | `haematuria_false` | -- | false | 0/23 | 0.0% | null 23 |
| `haematuria_false:eaac464c` | `haematuria_false` | -- | false | 0/23 | 0.0% | null 23 |
| `haematuria_true:6fadb8bc` | `haematuria_true` | -- | true | 0/23 | 0.0% | null 23 |
| `haematuria_null_hedged:aa0a900a` | `haematuria_null_hedged` | hedged | null | 0/21 | 0.0% | true 21 |
| `haematuria_true:16614edd` | `haematuria_true` | -- | true | 0/14 | 0.0% | null 14 |
| `haematuria_true:ec01803e` | `haematuria_true` | -- | true | 0/13 | 0.0% | null 13 |
| `haematuria_true:a87130d9` | `haematuria_true` | -- | true | 0/12 | 0.0% | false 1, null 11 |
| `haematuria_true:fbab8b19` | `haematuria_true` | -- | true | 0/8 | 0.0% | null 8 |
| `haematuria_true:e34024ba` | `haematuria_true` | -- | true | 0/7 | 0.0% | null 7 |
| `haematuria_null_hedged:740e7688` | `haematuria_null_hedged` | hedged | null | 1/21 | 4.8% | false 2, true 18, null 1 |
| `haematuria_false:b471d351` | `haematuria_false` | -- | false | 1/17 | 5.9% | false 1, true 12, null 4 |
| `haematuria_false:0a0b1113` | `haematuria_false` | -- | false | 3/25 | 12.0% | false 3, null 22 |
| `haematuria_false:66629fb1` | `haematuria_false` | -- | false | 4/22 | 18.2% | false 4, null 18 |
| `haematuria_true:08f72e8e` | `haematuria_true` | -- | true | 2/8 | 25.0% | false 3, true 2, null 3 |
| `haematuria_true:9207612b` | `haematuria_true` | -- | true | 2/8 | 25.0% | true 2, null 6 |
| `haematuria_null_hedged:dc7c4c42` | `haematuria_null_hedged` | hedged | null | 7/21 | 33.3% | true 14, null 7 |
| `haematuria_null_thirdparty:610eccad` | `haematuria_null_thirdparty` | third_party | null | 4/11 | 36.4% | true 7, null 4 |
| `haematuria_false:cbd9cec5` | `haematuria_false` | -- | false | 13/35 | 37.1% | false 13, null 22 |
| `haematuria_false:cb3cb6e6` | `haematuria_false` | -- | false | 7/18 | 38.9% | false 7, true 8, null 3 |
| `haematuria_null_hedged:211cfe81` | `haematuria_null_hedged` | hedged | null | 8/16 | 50.0% | false 7, true 1, null 8 |
| `haematuria_true:150663fa` | `haematuria_true` | -- | true | 14/24 | 58.3% | true 14, null 10 |
| `haematuria_null_hedged:1c99942a` | `haematuria_null_hedged` | hedged | null | 24/31 | 77.4% | true 7, null 24 |
| `haematuria_true:c0ff5eed` | `haematuria_true` | -- | true | 23/29 | 79.3% | true 23, null 6 |
| `haematuria_true:f9f24e70` | `haematuria_true` | -- | true | 8/10 | 80.0% | false 2, true 8 |
| `haematuria_false:56b8af62` | `haematuria_false` | -- | false | 17/20 | 85.0% | false 17, null 3 |
| `haematuria_null_hedged:46adb200` | `haematuria_null_hedged` | hedged | null | 17/20 | 85.0% | true 3, null 17 |
| `declarative_v1:c01bf698` | `declarative_v1` | -- | true | 7/8 | 87.5% | false 1, true 7 |
| `haematuria_null_hedged:58ace8f5` | `haematuria_null_hedged` | hedged | null | 24/26 | 92.3% | true 2, null 24 |
| `haematuria_null_hedged:34af6f69` | `haematuria_null_hedged` | hedged | null | 18/19 | 94.7% | false 1, null 18 |
| `haematuria_null_hedged:d9bf40cb` | `haematuria_null_hedged` | hedged | null | 18/19 | 94.7% | true 1, null 18 |
| `haematuria_null_thirdparty:161d26ba` | `haematuria_null_thirdparty` | third_party | null | 18/19 | 94.7% | true 1, null 18 |
| `haematuria_null_historical:ae265e50` | `haematuria_null_historical` | historical | null | 25/26 | 96.2% | false 1, null 25 |
| `haematuria_null_thirdparty:c37e504a` | `haematuria_null_thirdparty` | third_party | null | 28/29 | 96.6% | true 1, null 28 |
| `haematuria_null_hedged:776ef5ce` | `haematuria_null_hedged` | hedged | null | 30/31 | 96.8% | true 1, null 30 |
| `haematuria_true:f2e49699` | `haematuria_true` | -- | true | 31/32 | 96.9% | true 31, null 1 |
| `haematuria_null_historical:1ee55c82` | `haematuria_null_historical` | historical | null | 32/33 | 97.0% | true 1, null 32 |

*3 further fragments with at least one error are in the JSON sidecar; every fragment is there regardless of score.*

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
| 0 | 10000 | 2000 | 2000 | 0.0 | 60.9% | 60.9% | 26.4% | 0.00% |
| 1 | 10000 | 2000 | 2000 | 0.0 | 60.2% | 60.2% | 25.2% | 0.00% |
| 2 | 10000 | 2000 | 2000 | 0.0 | 60.4% | 60.4% | 25.1% | 0.00% |
| 3 | 10000 | 2000 | 2000 | 0.0 | 60.9% | 60.9% | 25.6% | 0.00% |
| 4 | 10000 | 2000 | 2000 | 0.0 | 60.9% | 60.9% | 27.0% | 0.00% |

### `tfidf_logreg`

| fold | train n | val n | test n | margin | acc (raw) | acc (ruled) | macro-F1 | null->true |
|---|---|---|---|---|---|---|---|---|
| 0 | 10000 | 2000 | 2000 | 0.0 | 77.6% | 77.6% | 64.0% | 3.64% |
| 1 | 10000 | 2000 | 2000 | 0.0 | 76.1% | 76.1% | 64.6% | 0.58% |
| 2 | 10000 | 2000 | 2000 | 0.0 | 76.9% | 76.9% | 64.6% | 0.17% |
| 3 | 10000 | 2000 | 2000 | 0.0 | 75.4% | 75.4% | 62.8% | 0.99% |
| 4 | 10000 | 2000 | 2000 | 0.0 | 81.5% | 81.5% | 73.0% | 0.50% |

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
| 0 | 10000 | 2000 | 2000 | 0.0 | 60.3% | 60.3% | 25.1% | 0.08% |
| 1 | 10000 | 2000 | 2000 | 0.0 | 59.8% | 59.8% | 25.2% | 0.00% |
| 2 | 10000 | 2000 | 2000 | 0.0 | 60.6% | 60.6% | 26.2% | 0.00% |
| 3 | 10000 | 2000 | 2000 | 0.0 | 60.5% | 60.5% | 25.4% | 0.00% |
| 4 | 10000 | 2000 | 2000 | 0.0 | 59.8% | 59.8% | 25.5% | 0.00% |

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

### `arm_b_finetune@c0.5-d0.6`

| fold | train n | val n | test n | margin | acc (raw) | acc (ruled) | macro-F1 | null->true |
|---|---|---|---|---|---|---|---|---|
| 0 | 10000 | 2000 | 2000 | 0.9 | 96.1% | 96.3% | 95.4% | 2.65% |
| 1 | 10000 | 2000 | 2000 | 0.75 | 89.3% | 90.0% | 88.4% | 9.15% |
| 2 | 10000 | 2000 | 2000 | 0.8 | 97.5% | 97.2% | 96.3% | 0.08% |
| 3 | 10000 | 2000 | 2000 | 0.0 | 95.7% | 95.7% | 94.4% | 0.74% |
| 4 | 10000 | 2000 | 2000 | 0.05 | 98.2% | 98.2% | 97.5% | 0.75% |

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

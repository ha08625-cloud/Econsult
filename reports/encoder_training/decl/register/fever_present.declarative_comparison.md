# Encoder training: evaluation report

*Generated 2026-09-02T19:48:20+00:00.*

|  |  |
|---|---|
| signal | `fever_present` |
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
| selected epochs | `c0.5-d0.0 3, 3, 2, 3, 2, c0.5-d0.3 3, 2, 3, 3, 3, c0.5-d0.6 2, 3, 2, 2, 3` |
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
| cluster tag coverage | `6 of 8 libraries carry cluster markers; 194 of 899 fragments are in libraries with none` |
| bootstrap | `2000 resamples over clusters, alpha=0.05, seed=0` |

**arms**

* **c0.5-d0.0** (`data/synthetic/generated/decl/c0.5-d0.0`): 10000 examples per epoch, **10000** labelled positions for `fever_present`
* **c0.5-d0.3** (`data/synthetic/generated/decl/c0.5-d0.3`): 10000 examples per epoch, **10000** labelled positions for `fever_present`
* **c0.5-d0.6** (`data/synthetic/generated/decl/c0.5-d0.6`): 10000 examples per epoch, **10000** labelled positions for `fever_present`

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

> **Warning: 2 of the 8 libraries behind this run carry no cluster markers at all, so every line in them counts as an independent idea.** Where that is not true -- where several lines are one idea written several ways -- the `eff n` of every slice drawn from those libraries is an **upper bound**, and the confidence intervals below are correspondingly **narrower than the truth**.
>
> Untagged: `fever_false`, `fever_true`.

Tagging cannot inflate a number -- `[c01]` siblings are forced into one cluster and one
split, so it only ever *reduces* `eff n`, correctly, by stopping the same idea being
counted twice. The asymmetry is what makes cross-signal comparison unsafe: a fully
tagged signal is penalised for being honest and an untagged one is flattered by default,
so a ranking across signals is partly an artefact of this column.

| library | fragments | tagged | coverage |
|---|---|---|---|
| `fever_false` | 98 | 0 | 0.0% |
| `fever_true` | 96 | 0 | 0.0% |
| `fever_null_hedged` | 73 | 20 | 27.4% |
| `fever_null_attribution` | 50 | 14 | 28.0% |
| `fever_null_metaphor` | 55 | 16 | 29.1% |
| `fever_null_historical` | 45 | 17 | 37.8% |
| `fever_null_thirdparty` | 46 | 22 | 47.8% |
| `declarative_v1` | 436 | 436 | 100.0% |

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
| `majority_class` | baseline | 7022 | **418** | 43.6% [38.6%, 48.8%] | 20.2% [18.6%, 21.9%] | 60.4% | 60.4% +/- 0.2% |
| `length_only` | baseline | 7022 | **418** | 43.9% [38.9%, 49.0%] | 21.3% [19.1%, 23.9%] | 60.6% | 60.6% +/- 0.3% |
| `tfidf_logreg` | baseline | 7022 | **418** | 68.6% [64.6%, 72.7%] | 64.5% [60.0%, 68.7%] | 77.8% | 77.8% +/- 4.5% |
| `length_only__shuffled` | negative control | 7022 | **418** | 43.6% [38.6%, 48.8%] | 20.2% [18.6%, 21.9%] | 60.4% | 60.4% +/- 0.2% |
| `tfidf_logreg__shuffled` | negative control | 7022 | **418** | 43.5% [38.5%, 48.7%] | 20.5% [18.7%, 22.1%] | 60.2% | 60.1% +/- 0.3% |
| `arm_b_finetune@c0.5-d0.0` | finetune | 7022 | **418** | 90.8% [88.0%, 93.3%] | 90.2% [87.1%, 92.7%] | 93.5% | 93.5% +/- 4.6% |
| `arm_b_finetune@c0.5-d0.3` | finetune | 7022 | **573** | 94.7% [92.9%, 96.3%] | 94.3% [92.4%, 96.0%] | 96.3% | 96.3% +/- 2.3% |
| `arm_b_finetune@c0.5-d0.6` | finetune | 7022 | **578** | 96.3% [95.0%, 97.5%] | 96.1% [94.8%, 97.4%] | 97.4% | 97.4% +/- 1.7% |

### Null sub-class recall, pooled

The table the whole exercise exists for: how often each hard `null` sub-class is correctly
left as `null`. `eff n` here is the sub-class's entire library, which a single split cannot reach.

**Never read this table on its own.** Every example in these slices is truly `null`, so a model
that always answers `null` scores 100% across the row -- as `majority_class` below does. High
null recall is only a finding when the `true` and `false` recalls in the per-class tables are
high too.

| model | adjacent | attribution | hedged | historical | metaphor | third_party |
|---|---|---|---|---|---|---|
| `majority_class` | -- | 100.0% [100.0%, 100.0%] (eff n 43) | 100.0% [100.0%, 100.0%] (eff n 63) | 100.0% [100.0%, 100.0%] (eff n 36) | 100.0% [100.0%, 100.0%] (eff n 47) | 100.0% [100.0%, 100.0%] (eff n 35) |
| `length_only` | -- | 100.0% [100.0%, 100.0%] (eff n 43) | 100.0% [100.0%, 100.0%] (eff n 63) | 100.0% [100.0%, 100.0%] (eff n 36) | 99.8% [99.5%, 100.0%] (eff n 47) | 100.0% [100.0%, 100.0%] (eff n 35) |
| `tfidf_logreg` | -- | 97.9% [95.9%, 99.5%] (eff n 43) | 91.6% [85.3%, 96.6%] (eff n 63) | 97.8% [95.4%, 99.5%] (eff n 36) | 98.3% [96.7%, 99.4%] (eff n 47) | 96.6% [92.9%, 99.3%] (eff n 35) |
| `length_only__shuffled` | -- | 100.0% [100.0%, 100.0%] (eff n 43) | 100.0% [100.0%, 100.0%] (eff n 63) | 100.0% [100.0%, 100.0%] (eff n 36) | 100.0% [100.0%, 100.0%] (eff n 47) | 100.0% [100.0%, 100.0%] (eff n 35) |
| `tfidf_logreg__shuffled` | -- | 99.5% [98.8%, 100.0%] (eff n 43) | 98.8% [97.8%, 99.6%] (eff n 63) | 99.8% [99.3%, 100.0%] (eff n 36) | 99.8% [99.5%, 100.0%] (eff n 47) | 99.6% [99.0%, 100.0%] (eff n 35) |
| `arm_b_finetune@c0.5-d0.0` | -- | 97.9% [94.4%, 100.0%] (eff n 43) | 90.7% [82.5%, 96.8%] (eff n 63) | 96.5% [92.1%, 99.8%] (eff n 36) | 99.7% [99.2%, 100.0%] (eff n 47) | 100.0% [100.0%, 100.0%] (eff n 35) |
| `arm_b_finetune@c0.5-d0.3` | -- | 98.1% [95.3%, 99.7%] (eff n 43) | 93.0% [86.2%, 98.0%] (eff n 63) | 97.5% [93.7%, 100.0%] (eff n 36) | 99.7% [98.9%, 100.0%] (eff n 47) | 100.0% [100.0%, 100.0%] (eff n 35) |
| `arm_b_finetune@c0.5-d0.6` | -- | 97.4% [91.9%, 100.0%] (eff n 43) | 91.9% [84.7%, 97.5%] (eff n 63) | 98.4% [95.0%, 100.0%] (eff n 36) | 98.8% [96.7%, 99.9%] (eff n 47) | 98.6% [96.6%, 100.0%] (eff n 35) |

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

Not scored, because no head exists for them: `dysuria_present`, `urinary_frequency_present`, `nocturia_present`, `flank_pain_present`, `haematuria_present`, `recent_uti_present`.

### `null -> true` on real text -- the headline

How often each model answers `true` about a signal the submission never mentioned, as
the mean across folds of that fold's own rate. Every other number in this section is
read against this one: a model can post a respectable overall figure here purely by
answering `null` everywhere, and it can post a respectable *decisive* figure while still
inventing symptoms into most of the submissions that never raised them.

| signal | null support | `arm_b_finetune@c0.5-d0.0` | `arm_b_finetune@c0.5-d0.3` | `arm_b_finetune@c0.5-d0.6` |
|---|---|---|---|---|
| `fever_present` | 49 | 0.0% | 0.4% | 1.6% |

### `arm_b_finetune@c0.5-d0.0`

Recombination test slice: **n 7022**, **eff n 418** clusters, accuracy 90.8% [88.0%, 93.3%]. Holdout: **n 67** submissions, one observation each, scored by 5 fold models at margins 0.35, 0.0, 0.85, 0.9, 0.0. The two `n`s are printed together because they are not the same kind of number and the second is far the smaller.

| signal | true/false/null | omitted | decisive n | decisive acc (mean +/- sd) | worst-case half-width | all n | all acc (mean +/- sd) | null recall |
|---|---|---|---|---|---|---|---|---|
| `fever_present` | 9/9/49 | 0 | 18 | 48.9% +/- 10.7% | +/-23.1% | 67 | 86.0% +/- 3.1% | 99.6% +/- 0.9% |

`null -> true` on real text, per fold: `fever_present` 0, 0, 0, 0, 0 of 49. This is the cell that invents a symptom into a patient's pre-filled form, counted here on submissions rather than on recombinations.

### `arm_b_finetune@c0.5-d0.3`

Recombination test slice: **n 7022**, **eff n 573** clusters, accuracy 94.7% [92.9%, 96.3%]. Holdout: **n 67** submissions, one observation each, scored by 5 fold models at margins 0.0, 0.0, 0.75, 0.55, 0.65. The two `n`s are printed together because they are not the same kind of number and the second is far the smaller.

| signal | true/false/null | omitted | decisive n | decisive acc (mean +/- sd) | worst-case half-width | all n | all acc (mean +/- sd) | null recall |
|---|---|---|---|---|---|---|---|---|
| `fever_present` | 9/9/49 | 0 | 18 | 90.0% +/- 2.5% | +/-23.1% | 67 | 96.4% +/- 0.8% | 98.8% +/- 1.1% |

`null -> true` on real text, per fold: `fever_present` 0, 1, 0, 0, 0 of 49. This is the cell that invents a symptom into a patient's pre-filled form, counted here on submissions rather than on recombinations.

### `arm_b_finetune@c0.5-d0.6`

Recombination test slice: **n 7022**, **eff n 578** clusters, accuracy 96.3% [95.0%, 97.5%]. Holdout: **n 67** submissions, one observation each, scored by 5 fold models at margins 0.0, 0.3, 0.9, 0.85, 0.2. The two `n`s are printed together because they are not the same kind of number and the second is far the smaller.

| signal | true/false/null | omitted | decisive n | decisive acc (mean +/- sd) | worst-case half-width | all n | all acc (mean +/- sd) | null recall |
|---|---|---|---|---|---|---|---|---|
| `fever_present` | 9/9/49 | 0 | 18 | 93.3% +/- 2.5% | +/-23.1% | 67 | 96.4% +/- 2.0% | 97.6% +/- 2.7% |

`null -> true` on real text, per fold: `fever_present` 2, 2, 0, 0, 0 of 49. This is the cell that invents a symptom into a patient's pre-filled form, counted here on submissions rather than on recombinations.

## Paired on real text

The 67 submissions are the same 67 for every model here, so unlike the recombination
test slice they can be paired: the informative quantity is the submissions two models
disagree about, not the gap between two means. One test per fold, never pooled.

### `arm_b_finetune@c0.5-d0.0` against `arm_b_finetune@c0.5-d0.3`

| fold | pairs | only `arm_b_finetune@c0.5-d0.0` | only `arm_b_finetune@c0.5-d0.3` | p |
|---|---|---|---|---|
| 0 | 67 | 0 | 6 | 0.0312 |
| 1 | 67 | 1 | 11 | 0.00635 |
| 2 | 67 | 1 | 5 | 0.219 |
| 3 | 67 | 0 | 7 | 0.0156 |
| 4 | 67 | 0 | 8 | 0.00781 |

`arm_b_finetune@c0.5-d0.0` ahead on 0 folds, `arm_b_finetune@c0.5-d0.3` on 5. `null -> true` mean: 0.0% against 0.4% -- **0.4 points higher** for `arm_b_finetune@c0.5-d0.3` -- more invented symptoms.

*One test per fold over the same 67 submissions, never concatenated: five folds are five models scored on one sample, and pooling would report a p-value for 335 observations that do not exist.*

### `arm_b_finetune@c0.5-d0.0` against `arm_b_finetune@c0.5-d0.6`

| fold | pairs | only `arm_b_finetune@c0.5-d0.0` | only `arm_b_finetune@c0.5-d0.6` | p |
|---|---|---|---|---|
| 0 | 67 | 3 | 7 | 0.344 |
| 1 | 67 | 2 | 11 | 0.0225 |
| 2 | 67 | 0 | 6 | 0.0312 |
| 3 | 67 | 1 | 7 | 0.0703 |
| 4 | 67 | 0 | 10 | 0.00195 |

`arm_b_finetune@c0.5-d0.0` ahead on 0 folds, `arm_b_finetune@c0.5-d0.6` on 5. `null -> true` mean: 0.0% against 1.6% -- **1.6 points higher** for `arm_b_finetune@c0.5-d0.6` -- more invented symptoms.

*One test per fold over the same 67 submissions, never concatenated: five folds are five models scored on one sample, and pooling would report a p-value for 335 observations that do not exist.*

### `arm_b_finetune@c0.5-d0.3` against `arm_b_finetune@c0.5-d0.6`

| fold | pairs | only `arm_b_finetune@c0.5-d0.3` | only `arm_b_finetune@c0.5-d0.6` | p |
|---|---|---|---|---|
| 0 | 67 | 3 | 1 | 0.625 |
| 1 | 67 | 2 | 1 | 1 |
| 2 | 67 | 0 | 2 | 0.5 |
| 3 | 67 | 1 | 0 | 1 |
| 4 | 67 | 0 | 2 | 0.5 |

`arm_b_finetune@c0.5-d0.3` ahead on 3 folds, `arm_b_finetune@c0.5-d0.6` on 2. `null -> true` mean: 0.4% against 1.6% -- **1.2 points higher** for `arm_b_finetune@c0.5-d0.6` -- more invented symptoms.

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
| `majority_class` | baseline | 3062 | **224** | 100.0% [100.0%, 100.0%] |
| `length_only` | baseline | 3062 | **224** | 100.0% [99.9%, 100.0%] |
| `tfidf_logreg` | baseline | 3062 | **224** | 96.0% [94.2%, 97.6%] |
| `arm_b_finetune@c0.5-d0.0` | finetune | 3062 | **224** | 96.4% [94.1%, 98.4%] |
| `arm_b_finetune@c0.5-d0.3` | finetune | 3062 | **224** | 97.3% [95.2%, 98.8%] |
| `arm_b_finetune@c0.5-d0.6` | finetune | 3062 | **224** | 96.6% [94.3%, 98.5%] |

### 2. The same comparison, paired

Two overlapping intervals do not settle whether one model beats another on the same
examples. McNemar does, over the examples the two disagree about -- read it alongside the
intervals above, never instead of them.

| pair | n | a only | b only | p |
|---|---|---|---|---|
| `majority_class` vs `length_only` | 3062 | 1 | 0 | 1 |
| `majority_class` vs `tfidf_logreg` | 3062 | 121 | 0 | 7.52e-37 |
| `majority_class` vs `arm_b_finetune@c0.5-d0.0` | 3062 | 125 | 0 | 4.7e-38 |
| `length_only` vs `tfidf_logreg` | 3062 | 121 | 1 | 4.63e-35 |
| `length_only` vs `arm_b_finetune@c0.5-d0.0` | 3062 | 125 | 1 | 2.99e-36 |
| `tfidf_logreg` vs `arm_b_finetune@c0.5-d0.0` | 3062 | 86 | 82 | 0.817 |

Not on this table, because they cannot be paired at all -- different examples on the two sides, so there is nothing for McNemar to pair: `majority_class` vs `arm_b_finetune@c0.5-d0.3`; `majority_class` vs `arm_b_finetune@c0.5-d0.6`; `length_only` vs `arm_b_finetune@c0.5-d0.3`; `length_only` vs `arm_b_finetune@c0.5-d0.6`; `tfidf_logreg` vs `arm_b_finetune@c0.5-d0.3`; `tfidf_logreg` vs `arm_b_finetune@c0.5-d0.6`; `arm_b_finetune@c0.5-d0.0` vs `arm_b_finetune@c0.5-d0.3`; `arm_b_finetune@c0.5-d0.0` vs `arm_b_finetune@c0.5-d0.6`; `arm_b_finetune@c0.5-d0.3` vs `arm_b_finetune@c0.5-d0.6`. Read those through the intervals above and the per-fold spread, and see "Pairs that could not be tested" below.

### 3. Where the errors fall

The per-fragment table below, as one number per model. Errors spread thinly across many
fragments say the method is too weak. Errors piled onto a handful say those specific ideas
are not learnable from the data we have -- and the table names them, which is what makes
this the most decision-useful thing in the report.

* `majority_class`: 3960 errors across 194 of 463 decisive fragments. Half of them fall on **71** fragments (an even spread would be 97.0); the worst ten carry 8.9% of all errors.
* `length_only`: 3938 errors across 194 of 463 decisive fragments. Half of them fall on **70** fragments (an even spread would be 97.0); the worst ten carry 9.0% of all errors.
* `tfidf_logreg`: 2205 errors across 208 of 463 decisive fragments. Half of them fall on **49** fragments (an even spread would be 104.0); the worst ten carry 13.7% of all errors.
* `arm_b_finetune@c0.5-d0.0`: 648 errors across 62 of 463 decisive fragments. Half of them fall on **16** fragments (an even spread would be 31.0); the worst ten carry 37.3% of all errors.
* `arm_b_finetune@c0.5-d0.3`: 370 errors across 62 of 852 decisive fragments. Half of them fall on **14** fragments (an even spread would be 31.0); the worst ten carry 40.0% of all errors.
* `arm_b_finetune@c0.5-d0.6`: 259 errors across 51 of 888 decisive fragments. Half of them fall on **13** fragments (an even spread would be 25.5); the worst ten carry 41.7% of all errors.

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
| `length_only__shuffled` | 60.4% [39.9%, 76.4%] | 25.1% [19.0%, 28.9%] |
| `tfidf_logreg__shuffled` | 60.2% [39.9%, 76.0%] | 25.3% [19.3%, 29.1%] |

## Paired comparisons (McNemar, raw argmax)

Exact two-sided McNemar over the examples the two models disagree about. Pairing unit is the
example, not the cluster -- see the limitations.

| pair | slice | n | a only | b only | p |
|---|---|---|---|---|---|
| `majority_class` vs `length_only` | overall | 10000 | 2 | 23 | 1.94e-05 |
| `majority_class` vs `length_only` | null_ambiguous | 3062 | 1 | 0 | 1 |
| `majority_class` vs `tfidf_logreg` | overall | 10000 | 132 | 1876 | 0 |
| `majority_class` vs `tfidf_logreg` | null_ambiguous | 3062 | 121 | 0 | 7.52e-37 |
| `majority_class` vs `arm_b_finetune@c0.5-d0.0` | overall | 10000 | 130 | 3415 | 0 |
| `majority_class` vs `arm_b_finetune@c0.5-d0.0` | null_ambiguous | 3062 | 125 | 0 | 4.7e-38 |
| `length_only` vs `tfidf_logreg` | overall | 10000 | 132 | 1855 | 0 |
| `length_only` vs `tfidf_logreg` | null_ambiguous | 3062 | 121 | 1 | 4.63e-35 |
| `length_only` vs `arm_b_finetune@c0.5-d0.0` | overall | 10000 | 130 | 3394 | 0 |
| `length_only` vs `arm_b_finetune@c0.5-d0.0` | null_ambiguous | 3062 | 125 | 1 | 2.99e-36 |
| `tfidf_logreg` vs `arm_b_finetune@c0.5-d0.0` | overall | 10000 | 134 | 1675 | 0 |
| `tfidf_logreg` vs `arm_b_finetune@c0.5-d0.0` | null_ambiguous | 3062 | 86 | 82 | 0.817 |

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
| `fever_false` | 953 | 0.0% | 0.1% | 52.0% | 88.0% | 91.9% | 92.7% | 92.7pp |
| `fever_true` | 612 | 0.0% | 1.4% | 39.6% | 83.7% | 85.8% | 86.3% | 86.3pp |
| `fever_null_hedged` | 832 | 100.0% | 100.0% | 91.6% | 90.7% | 93.0% | 91.9% | 9.3pp |
| `fever_null_historical` | 511 | 100.0% | 100.0% | 97.8% | 96.5% | 97.5% | 98.4% | 3.5pp |
| `fever_null_thirdparty` | 504 | 100.0% | 100.0% | 96.6% | 100.0% | 100.0% | 98.6% | 3.4pp |
| `fever_null_attribution` | 570 | 100.0% | 100.0% | 97.9% | 97.9% | 98.1% | 97.4% | 2.6pp |
| `fever_null_metaphor` | 645 | 100.0% | 99.8% | 98.3% | 99.7% | 99.7% | 98.8% | 1.7pp |
| `(none)` | 2978 | 100.0% | 100.0% | 99.6% | 99.9% | 100.0% | 99.9% | 0.4pp |

### By fragment, errors

Ordered by the worst model's error count, so the fragments the comparison is about sort
to the top whichever encoder wins. Counts, not rates: these are the sentences a month of
library work would be spent on. The JSON holds every fragment.

| fragment | library | truth | `majority_class` | `length_only` | `tfidf_logreg` | `arm_b_finetune@c0.5-d0.0` | `arm_b_finetune@c0.5-d0.3` | `arm_b_finetune@c0.5-d0.6` | spread |
|---|---|---|---|---|---|---|---|---|---|
| `fever_false:5a6a9b80` | `fever_false` | false | 38 | 38 | 1 | 0 | 0 | 0 | 38 |
| `fever_false:24e5c247` | `fever_false` | false | 36 | 36 | 29 | 0 | 0 | 0 | 36 |
| `fever_false:b9076eff` | `fever_false` | false | 36 | 36 | 28 | 0 | 1 | 4 | 36 |
| `fever_false:fc2ae0f2` | `fever_false` | false | 36 | 36 | 20 | 0 | 0 | 0 | 36 |
| `fever_false:17f6c637` | `fever_false` | false | 35 | 35 | 0 | 0 | 0 | 0 | 35 |
| `fever_false:55bf1913` | `fever_false` | false | 35 | 35 | 1 | 0 | 0 | 0 | 35 |
| `fever_false:9f46e710` | `fever_false` | false | 35 | 35 | 2 | 0 | 0 | 0 | 35 |
| `fever_false:d0ca84a7` | `fever_false` | false | 35 | 35 | 3 | 0 | 0 | 0 | 35 |
| `fever_false:0429068c` | `fever_false` | false | 34 | 34 | 34 | 0 | 0 | 0 | 34 |
| `fever_false:5969c6c9` | `fever_false` | false | 33 | 33 | 6 | 0 | 0 | 0 | 33 |
| `fever_false:b96ed279` | `fever_false` | false | 33 | 33 | 33 | 33 | 0 | 0 | 33 |
| `fever_false:f586e96d` | `fever_false` | false | 33 | 33 | 20 | 0 | 0 | 0 | 33 |
| `fever_false:2b944abc` | `fever_false` | false | 32 | 32 | 0 | 0 | 0 | 0 | 32 |
| `fever_false:a9a0220e` | `fever_false` | false | 32 | 32 | 0 | 0 | 0 | 0 | 32 |
| `fever_false:cdf2609b` | `fever_false` | false | 32 | 32 | 32 | 32 | 1 | 2 | 31 |
| `fever_false:5c2a065d` | `fever_false` | false | 31 | 31 | 31 | 31 | 18 | 8 | 23 |
| `fever_false:d5ed3ff1` | `fever_false` | false | 31 | 31 | 30 | 3 | 0 | 0 | 31 |
| `fever_false:de0596c4` | `fever_false` | false | 31 | 31 | 28 | 31 | 0 | 3 | 31 |
| `fever_false:e2aff3b8` | `fever_false` | false | 31 | 31 | 20 | 0 | 0 | 0 | 31 |
| `fever_false:758d5434` | `fever_false` | false | 30 | 30 | 0 | 1 | 0 | 0 | 30 |
| `fever_false:8d02bd9e` | `fever_false` | false | 30 | 30 | 27 | 11 | 3 | 4 | 27 |
| `fever_false:a5b671a1` | `fever_false` | false | 30 | 30 | 5 | 0 | 0 | 0 | 30 |
| `fever_false:3a3043ff` | `fever_false` | false | 29 | 29 | 19 | 12 | 16 | 0 | 29 |
| `fever_false:463f8189` | `fever_false` | false | 29 | 29 | 2 | 0 | 0 | 0 | 29 |
| `fever_false:cbf9d7a5` | `fever_false` | false | 29 | 29 | 29 | 0 | 0 | 0 | 29 |
| `fever_true:18173593` | `fever_true` | true | 29 | 29 | 12 | 0 | 0 | 0 | 29 |
| `fever_false:147d5cf0` | `fever_false` | false | 28 | 28 | 18 | 0 | 0 | 0 | 28 |
| `fever_false:43f5b35d` | `fever_false` | false | 28 | 28 | 19 | 0 | 0 | 0 | 28 |
| `fever_false:56a45ff1` | `fever_false` | false | 28 | 28 | 19 | 0 | 0 | 0 | 28 |
| `fever_false:7b64d17a` | `fever_false` | false | 28 | 28 | 23 | 0 | 0 | 0 | 28 |
| `fever_false:90f7b87f` | `fever_false` | false | 28 | 28 | 0 | 0 | 0 | 0 | 28 |
| `fever_false:a4cda1e2` | `fever_false` | false | 28 | 28 | 2 | 0 | 0 | 0 | 28 |
| `fever_false:a6c0d44a` | `fever_false` | false | 28 | 28 | 10 | 0 | 0 | 0 | 28 |
| `fever_true:753c7815` | `fever_true` | true | 28 | 28 | 0 | 0 | 0 | 0 | 28 |
| `fever_true:f3ee0d07` | `fever_true` | true | 28 | 28 | 0 | 0 | 0 | 0 | 28 |
| `fever_false:4bf3caad` | `fever_false` | false | 27 | 27 | 6 | 0 | 0 | 0 | 27 |
| `fever_false:78a4c55b` | `fever_false` | false | 27 | 27 | 0 | 0 | 0 | 0 | 27 |
| `fever_false:c747066d` | `fever_false` | false | 27 | 27 | 3 | 0 | 0 | 0 | 27 |
| `fever_true:1c3df822` | `fever_true` | true | 27 | 27 | 17 | 0 | 0 | 0 | 27 |
| `fever_false:033927e6` | `fever_false` | false | 26 | 26 | 26 | 0 | 0 | 0 | 26 |

*219 further fragments erred on at least one model; the JSON holds them all.*

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
| false | 2479 | **98** | 0.0% [0.0%, 0.0%] |
| null_ambiguous | 3062 | **224** | 100.0% [100.0%, 100.0%] |
| null_structural | 2978 | **1** | 100.0% [100.0%, 100.0%] |
| true | 1481 | **96** | 0.0% [0.0%, 0.0%] |

### By null sub-class

| sub-class | n | eff n | null recall [95% CI] |
|---|---|---|---|
| attribution | 570 | **43** | 100.0% [100.0%, 100.0%] |
| hedged | 832 | **63** | 100.0% [100.0%, 100.0%] |
| historical | 511 | **36** | 100.0% [100.0%, 100.0%] |
| metaphor | 645 | **47** | 100.0% [100.0%, 100.0%] |
| third_party | 504 | **35** | 100.0% [100.0%, 100.0%] |

### By fragment library

| library | n | eff n | accuracy [95% CI] |
|---|---|---|---|
| fever_false | 2479 | **98** | 0.0% [0.0%, 0.0%] |
| fever_null_attribution | 570 | **43** | 100.0% [100.0%, 100.0%] |
| fever_null_hedged | 832 | **63** | 100.0% [100.0%, 100.0%] |
| fever_null_historical | 511 | **36** | 100.0% [100.0%, 100.0%] |
| fever_null_metaphor | 645 | **47** | 100.0% [100.0%, 100.0%] |
| fever_null_thirdparty | 504 | **35** | 100.0% [100.0%, 100.0%] |
| fever_true | 1481 | **96** | 0.0% [0.0%, 0.0%] |
| (none) | 2978 | **1** | 100.0% [100.0%, 100.0%] |

### Per-fragment errors (worst first)

Whether errors are spread thinly across many fragments or piled onto a few is the difference
between "the method is too weak" (model work) and "these specific ideas are not learnable from
the data we have" (library work, and these are the fragments to write more of). No intervals:
a fragment is one cluster, so an interval over its own examples measures nothing.

194 of 463 decisive fragments were got wrong at least once.

`majority_class`: 3960 errors across 194 of 463 decisive fragments. Half of them fall on **71** fragments (an even spread would be 97.0); the worst ten carry 8.9% of all errors.

| fragment | library | sub-class | truth | correct | accuracy | predicted as |
|---|---|---|---|---|---|---|
| `fever_false:5a6a9b80` | `fever_false` | -- | false | 0/38 | 0.0% | null 38 |
| `fever_false:24e5c247` | `fever_false` | -- | false | 0/36 | 0.0% | null 36 |
| `fever_false:b9076eff` | `fever_false` | -- | false | 0/36 | 0.0% | null 36 |
| `fever_false:fc2ae0f2` | `fever_false` | -- | false | 0/36 | 0.0% | null 36 |
| `fever_false:17f6c637` | `fever_false` | -- | false | 0/35 | 0.0% | null 35 |
| `fever_false:55bf1913` | `fever_false` | -- | false | 0/35 | 0.0% | null 35 |
| `fever_false:9f46e710` | `fever_false` | -- | false | 0/35 | 0.0% | null 35 |
| `fever_false:d0ca84a7` | `fever_false` | -- | false | 0/35 | 0.0% | null 35 |
| `fever_false:0429068c` | `fever_false` | -- | false | 0/34 | 0.0% | null 34 |
| `fever_false:5969c6c9` | `fever_false` | -- | false | 0/33 | 0.0% | null 33 |
| `fever_false:b96ed279` | `fever_false` | -- | false | 0/33 | 0.0% | null 33 |
| `fever_false:f586e96d` | `fever_false` | -- | false | 0/33 | 0.0% | null 33 |
| `fever_false:2b944abc` | `fever_false` | -- | false | 0/32 | 0.0% | null 32 |
| `fever_false:a9a0220e` | `fever_false` | -- | false | 0/32 | 0.0% | null 32 |
| `fever_false:cdf2609b` | `fever_false` | -- | false | 0/32 | 0.0% | null 32 |
| `fever_false:5c2a065d` | `fever_false` | -- | false | 0/31 | 0.0% | null 31 |
| `fever_false:d5ed3ff1` | `fever_false` | -- | false | 0/31 | 0.0% | null 31 |
| `fever_false:de0596c4` | `fever_false` | -- | false | 0/31 | 0.0% | null 31 |
| `fever_false:e2aff3b8` | `fever_false` | -- | false | 0/31 | 0.0% | null 31 |
| `fever_false:758d5434` | `fever_false` | -- | false | 0/30 | 0.0% | null 30 |
| `fever_false:8d02bd9e` | `fever_false` | -- | false | 0/30 | 0.0% | null 30 |
| `fever_false:a5b671a1` | `fever_false` | -- | false | 0/30 | 0.0% | null 30 |
| `fever_false:3a3043ff` | `fever_false` | -- | false | 0/29 | 0.0% | null 29 |
| `fever_false:463f8189` | `fever_false` | -- | false | 0/29 | 0.0% | null 29 |
| `fever_false:cbf9d7a5` | `fever_false` | -- | false | 0/29 | 0.0% | null 29 |
| `fever_true:18173593` | `fever_true` | -- | true | 0/29 | 0.0% | null 29 |
| `fever_false:147d5cf0` | `fever_false` | -- | false | 0/28 | 0.0% | null 28 |
| `fever_false:43f5b35d` | `fever_false` | -- | false | 0/28 | 0.0% | null 28 |
| `fever_false:56a45ff1` | `fever_false` | -- | false | 0/28 | 0.0% | null 28 |
| `fever_false:7b64d17a` | `fever_false` | -- | false | 0/28 | 0.0% | null 28 |
| `fever_false:90f7b87f` | `fever_false` | -- | false | 0/28 | 0.0% | null 28 |
| `fever_false:a4cda1e2` | `fever_false` | -- | false | 0/28 | 0.0% | null 28 |
| `fever_false:a6c0d44a` | `fever_false` | -- | false | 0/28 | 0.0% | null 28 |
| `fever_true:753c7815` | `fever_true` | -- | true | 0/28 | 0.0% | null 28 |
| `fever_true:f3ee0d07` | `fever_true` | -- | true | 0/28 | 0.0% | null 28 |
| `fever_false:4bf3caad` | `fever_false` | -- | false | 0/27 | 0.0% | null 27 |
| `fever_false:78a4c55b` | `fever_false` | -- | false | 0/27 | 0.0% | null 27 |
| `fever_false:c747066d` | `fever_false` | -- | false | 0/27 | 0.0% | null 27 |
| `fever_true:1c3df822` | `fever_true` | -- | true | 0/27 | 0.0% | null 27 |
| `fever_false:033927e6` | `fever_false` | -- | false | 0/26 | 0.0% | null 26 |

*154 further fragments with at least one error are in the JSON sidecar; every fragment is there regardless of score.*

## `length_only`

Logistic regression on token count alone. The direct measurable test of the length leak: anything materially above majority means text length is a usable proxy for the label, which is a fragment-library problem rather than a model one.

Decision-rule margins selected per fold (on each fold's own validation split): 0.0.
Every fold selected margin 0, so the ruled and raw views below are the same decisions. That is a finding rather than a bug: no margin improved macro-F1 without worsening the `null -> true` rate.

*Confusion matrix, raw argmax*

|  | pred false | pred true | pred null | total |
|---|---|---|---|---|
| **truth false** | 3 | 0 | 2476 | 2479 |
| **truth true** | 43 | 20 | 1418 | 1481 |
| **truth null** | 2 | 0 | 6038 | 6040 |
| **total** | 48 | 20 | 9932 | 10000 |

`null -> true`: 0 of 6040 truly-null examples (0.00%).

*Confusion matrix, after the decision rule*

|  | pred false | pred true | pred null | total |
|---|---|---|---|---|
| **truth false** | 3 | 0 | 2476 | 2479 |
| **truth true** | 43 | 20 | 1418 | 1481 |
| **truth null** | 2 | 0 | 6038 | 6040 |
| **total** | 48 | 20 | 9932 | 10000 |

`null -> true`: 0 of 6040 truly-null examples (0.00%).

### Per class, after the decision rule

| class | support | predicted | precision | recall | F1 |
|---|---|---|---|---|---|
| `false` | 2479 | 48 | 6.2% | 0.1% | 0.2% |
| `true` | 1481 | 20 | 100.0% | 1.4% | 2.7% |
| `null` | 6040 | 9932 | 60.8% | 100.0% | 75.6% |

### By label mode

| label mode | n | eff n | accuracy [95% CI] |
|---|---|---|---|
| false | 2479 | **98** | 0.1% [0.0%, 0.4%] |
| null_ambiguous | 3062 | **224** | 100.0% [99.9%, 100.0%] |
| null_structural | 2978 | **1** | 100.0% [100.0%, 100.0%] |
| true | 1481 | **96** | 1.4% [0.0%, 4.2%] |

### By null sub-class

| sub-class | n | eff n | null recall [95% CI] |
|---|---|---|---|
| attribution | 570 | **43** | 100.0% [100.0%, 100.0%] |
| hedged | 832 | **63** | 100.0% [100.0%, 100.0%] |
| historical | 511 | **36** | 100.0% [100.0%, 100.0%] |
| metaphor | 645 | **47** | 99.8% [99.5%, 100.0%] |
| third_party | 504 | **35** | 100.0% [100.0%, 100.0%] |

### By fragment library

| library | n | eff n | accuracy [95% CI] |
|---|---|---|---|
| fever_false | 2479 | **98** | 0.1% [0.0%, 0.4%] |
| fever_null_attribution | 570 | **43** | 100.0% [100.0%, 100.0%] |
| fever_null_hedged | 832 | **63** | 100.0% [100.0%, 100.0%] |
| fever_null_historical | 511 | **36** | 100.0% [100.0%, 100.0%] |
| fever_null_metaphor | 645 | **47** | 99.8% [99.5%, 100.0%] |
| fever_null_thirdparty | 504 | **35** | 100.0% [100.0%, 100.0%] |
| fever_true | 1481 | **96** | 1.4% [0.0%, 4.2%] |
| (none) | 2978 | **1** | 100.0% [100.0%, 100.0%] |

### Per-fragment errors (worst first)

Whether errors are spread thinly across many fragments or piled onto a few is the difference
between "the method is too weak" (model work) and "these specific ideas are not learnable from
the data we have" (library work, and these are the fragments to write more of). No intervals:
a fragment is one cluster, so an interval over its own examples measures nothing.

194 of 463 decisive fragments were got wrong at least once.

`length_only`: 3938 errors across 194 of 463 decisive fragments. Half of them fall on **70** fragments (an even spread would be 97.0); the worst ten carry 9.0% of all errors.

| fragment | library | sub-class | truth | correct | accuracy | predicted as |
|---|---|---|---|---|---|---|
| `fever_false:5a6a9b80` | `fever_false` | -- | false | 0/38 | 0.0% | null 38 |
| `fever_false:24e5c247` | `fever_false` | -- | false | 0/36 | 0.0% | null 36 |
| `fever_false:b9076eff` | `fever_false` | -- | false | 0/36 | 0.0% | null 36 |
| `fever_false:fc2ae0f2` | `fever_false` | -- | false | 0/36 | 0.0% | null 36 |
| `fever_false:17f6c637` | `fever_false` | -- | false | 0/35 | 0.0% | null 35 |
| `fever_false:55bf1913` | `fever_false` | -- | false | 0/35 | 0.0% | null 35 |
| `fever_false:9f46e710` | `fever_false` | -- | false | 0/35 | 0.0% | null 35 |
| `fever_false:d0ca84a7` | `fever_false` | -- | false | 0/35 | 0.0% | null 35 |
| `fever_false:0429068c` | `fever_false` | -- | false | 0/34 | 0.0% | null 34 |
| `fever_false:5969c6c9` | `fever_false` | -- | false | 0/33 | 0.0% | null 33 |
| `fever_false:b96ed279` | `fever_false` | -- | false | 0/33 | 0.0% | null 33 |
| `fever_false:f586e96d` | `fever_false` | -- | false | 0/33 | 0.0% | null 33 |
| `fever_false:2b944abc` | `fever_false` | -- | false | 0/32 | 0.0% | null 32 |
| `fever_false:a9a0220e` | `fever_false` | -- | false | 0/32 | 0.0% | null 32 |
| `fever_false:cdf2609b` | `fever_false` | -- | false | 0/32 | 0.0% | null 32 |
| `fever_false:5c2a065d` | `fever_false` | -- | false | 0/31 | 0.0% | null 31 |
| `fever_false:d5ed3ff1` | `fever_false` | -- | false | 0/31 | 0.0% | null 31 |
| `fever_false:de0596c4` | `fever_false` | -- | false | 0/31 | 0.0% | null 31 |
| `fever_false:e2aff3b8` | `fever_false` | -- | false | 0/31 | 0.0% | null 31 |
| `fever_false:758d5434` | `fever_false` | -- | false | 0/30 | 0.0% | null 30 |
| `fever_false:8d02bd9e` | `fever_false` | -- | false | 0/30 | 0.0% | null 30 |
| `fever_false:a5b671a1` | `fever_false` | -- | false | 0/30 | 0.0% | null 30 |
| `fever_false:3a3043ff` | `fever_false` | -- | false | 0/29 | 0.0% | null 29 |
| `fever_false:463f8189` | `fever_false` | -- | false | 0/29 | 0.0% | null 29 |
| `fever_false:cbf9d7a5` | `fever_false` | -- | false | 0/29 | 0.0% | null 29 |
| `fever_true:18173593` | `fever_true` | -- | true | 0/29 | 0.0% | null 29 |
| `fever_false:147d5cf0` | `fever_false` | -- | false | 0/28 | 0.0% | null 28 |
| `fever_false:43f5b35d` | `fever_false` | -- | false | 0/28 | 0.0% | null 28 |
| `fever_false:56a45ff1` | `fever_false` | -- | false | 0/28 | 0.0% | null 28 |
| `fever_false:7b64d17a` | `fever_false` | -- | false | 0/28 | 0.0% | null 28 |
| `fever_false:90f7b87f` | `fever_false` | -- | false | 0/28 | 0.0% | null 28 |
| `fever_false:a4cda1e2` | `fever_false` | -- | false | 0/28 | 0.0% | null 28 |
| `fever_false:a6c0d44a` | `fever_false` | -- | false | 0/28 | 0.0% | null 28 |
| `fever_true:753c7815` | `fever_true` | -- | true | 0/28 | 0.0% | null 28 |
| `fever_true:f3ee0d07` | `fever_true` | -- | true | 0/28 | 0.0% | false 28 |
| `fever_false:4bf3caad` | `fever_false` | -- | false | 0/27 | 0.0% | null 27 |
| `fever_false:78a4c55b` | `fever_false` | -- | false | 0/27 | 0.0% | null 27 |
| `fever_false:c747066d` | `fever_false` | -- | false | 0/27 | 0.0% | null 27 |
| `fever_true:1c3df822` | `fever_true` | -- | true | 0/27 | 0.0% | null 27 |
| `fever_false:033927e6` | `fever_false` | -- | false | 0/26 | 0.0% | null 26 |

*154 further fragments with at least one error are in the JSON sidecar; every fragment is there regardless of score.*

## `tfidf_logreg`

TF-IDF unigrams and bigrams into logistic regression. Tests whether the dataset is keyword-solvable. Its overall accuracy is close to uninformative; the `null_ambiguous` slice is the number that matters.

Decision-rule margins selected per fold (on each fold's own validation split): 0.0.
Every fold selected margin 0, so the ruled and raw views below are the same decisions. That is a finding rather than a bug: no margin improved macro-F1 without worsening the `null -> true` rate.

*Confusion matrix, raw argmax*

|  | pred false | pred true | pred null | total |
|---|---|---|---|---|
| **truth false** | 1290 | 75 | 1114 | 2479 |
| **truth true** | 78 | 586 | 817 | 1481 |
| **truth null** | 93 | 39 | 5908 | 6040 |
| **total** | 1461 | 700 | 7839 | 10000 |

`null -> true`: 39 of 6040 truly-null examples (0.65%).

*Confusion matrix, after the decision rule*

|  | pred false | pred true | pred null | total |
|---|---|---|---|---|
| **truth false** | 1290 | 75 | 1114 | 2479 |
| **truth true** | 78 | 586 | 817 | 1481 |
| **truth null** | 93 | 39 | 5908 | 6040 |
| **total** | 1461 | 700 | 7839 | 10000 |

`null -> true`: 39 of 6040 truly-null examples (0.65%).

### Per class, after the decision rule

| class | support | predicted | precision | recall | F1 |
|---|---|---|---|---|---|
| `false` | 2479 | 1461 | 88.3% | 52.0% | 65.5% |
| `true` | 1481 | 700 | 83.7% | 39.6% | 53.7% |
| `null` | 6040 | 7839 | 75.4% | 97.8% | 85.1% |

### By label mode

| label mode | n | eff n | accuracy [95% CI] |
|---|---|---|---|
| false | 2479 | **98** | 52.0% [44.4%, 59.7%] |
| null_ambiguous | 3062 | **224** | 96.0% [94.2%, 97.6%] |
| null_structural | 2978 | **1** | 99.6% [99.6%, 99.6%] |
| true | 1481 | **96** | 39.6% [31.5%, 48.3%] |

### By null sub-class

| sub-class | n | eff n | null recall [95% CI] |
|---|---|---|---|
| attribution | 570 | **43** | 97.9% [95.9%, 99.5%] |
| hedged | 832 | **63** | 91.6% [85.3%, 96.6%] |
| historical | 511 | **36** | 97.8% [95.4%, 99.5%] |
| metaphor | 645 | **47** | 98.3% [96.7%, 99.4%] |
| third_party | 504 | **35** | 96.6% [92.9%, 99.3%] |

### By fragment library

| library | n | eff n | accuracy [95% CI] |
|---|---|---|---|
| fever_false | 2479 | **98** | 52.0% [44.4%, 59.7%] |
| fever_null_attribution | 570 | **43** | 97.9% [95.9%, 99.5%] |
| fever_null_hedged | 832 | **63** | 91.6% [85.3%, 96.6%] |
| fever_null_historical | 511 | **36** | 97.8% [95.4%, 99.5%] |
| fever_null_metaphor | 645 | **47** | 98.3% [96.7%, 99.4%] |
| fever_null_thirdparty | 504 | **35** | 96.6% [92.9%, 99.3%] |
| fever_true | 1481 | **96** | 39.6% [31.5%, 48.3%] |
| (none) | 2978 | **1** | 99.6% [99.6%, 99.6%] |

### Per-fragment errors (worst first)

Whether errors are spread thinly across many fragments or piled onto a few is the difference
between "the method is too weak" (model work) and "these specific ideas are not learnable from
the data we have" (library work, and these are the fragments to write more of). No intervals:
a fragment is one cluster, so an interval over its own examples measures nothing.

208 of 463 decisive fragments were got wrong at least once.

`tfidf_logreg`: 2205 errors across 208 of 463 decisive fragments. Half of them fall on **49** fragments (an even spread would be 104.0); the worst ten carry 13.7% of all errors.

| fragment | library | sub-class | truth | correct | accuracy | predicted as |
|---|---|---|---|---|---|---|
| `fever_false:0429068c` | `fever_false` | -- | false | 0/34 | 0.0% | true 2, null 32 |
| `fever_false:b96ed279` | `fever_false` | -- | false | 0/33 | 0.0% | null 33 |
| `fever_false:cdf2609b` | `fever_false` | -- | false | 0/32 | 0.0% | null 32 |
| `fever_false:5c2a065d` | `fever_false` | -- | false | 0/31 | 0.0% | null 31 |
| `fever_false:cbf9d7a5` | `fever_false` | -- | false | 0/29 | 0.0% | null 29 |
| `fever_false:033927e6` | `fever_false` | -- | false | 0/26 | 0.0% | null 26 |
| `fever_false:3de7ecac` | `fever_false` | -- | false | 0/26 | 0.0% | null 26 |
| `fever_false:03f2141f` | `fever_false` | -- | false | 0/25 | 0.0% | null 25 |
| `fever_false:44cd09fd` | `fever_false` | -- | false | 0/25 | 0.0% | null 25 |
| `fever_true:15a05d92` | `fever_true` | -- | true | 0/25 | 0.0% | null 25 |
| `fever_true:dd6bbec4` | `fever_true` | -- | true | 0/24 | 0.0% | null 24 |
| `fever_true:3d00c372` | `fever_true` | -- | true | 0/23 | 0.0% | null 23 |
| `fever_false:afdc7129` | `fever_false` | -- | false | 0/22 | 0.0% | null 22 |
| `fever_false:f6985a04` | `fever_false` | -- | false | 0/22 | 0.0% | true 1, null 21 |
| `fever_true:7ef2ecf5` | `fever_true` | -- | true | 0/22 | 0.0% | false 3, null 19 |
| `fever_true:ed3c8c83` | `fever_true` | -- | true | 0/20 | 0.0% | null 20 |
| `fever_true:c7489e90` | `fever_true` | -- | true | 0/19 | 0.0% | null 19 |
| `fever_false:6b3816ec` | `fever_false` | -- | false | 0/18 | 0.0% | null 18 |
| `fever_false:8f64f673` | `fever_false` | -- | false | 0/18 | 0.0% | null 18 |
| `fever_true:391fb2ce` | `fever_true` | -- | true | 0/18 | 0.0% | null 18 |
| `fever_true:7844c66b` | `fever_true` | -- | true | 0/18 | 0.0% | false 1, null 17 |
| `fever_false:ebba1ba0` | `fever_false` | -- | false | 0/17 | 0.0% | null 17 |
| `fever_true:cf13c84f` | `fever_true` | -- | true | 0/17 | 0.0% | null 17 |
| `fever_true:db1acb55` | `fever_true` | -- | true | 0/17 | 0.0% | null 17 |
| `fever_true:054f1309` | `fever_true` | -- | true | 0/16 | 0.0% | null 16 |
| `fever_false:f1e3b80c` | `fever_false` | -- | false | 0/15 | 0.0% | null 15 |
| `fever_true:199d4eb4` | `fever_true` | -- | true | 0/15 | 0.0% | null 15 |
| `fever_true:7f33b5f8` | `fever_true` | -- | true | 0/15 | 0.0% | null 15 |
| `fever_true:0ddb8a11` | `fever_true` | -- | true | 0/14 | 0.0% | null 14 |
| `fever_true:79211e25` | `fever_true` | -- | true | 0/14 | 0.0% | null 14 |
| `fever_true:97087dd7` | `fever_true` | -- | true | 0/14 | 0.0% | null 14 |
| `fever_true:d00c307b` | `fever_true` | -- | true | 0/14 | 0.0% | null 14 |
| `fever_true:e919adf9` | `fever_true` | -- | true | 0/14 | 0.0% | null 14 |
| `fever_true:7dc95cda` | `fever_true` | -- | true | 0/13 | 0.0% | null 13 |
| `fever_true:80f7ba2e` | `fever_true` | -- | true | 0/13 | 0.0% | null 13 |
| `fever_true:c5d3e4a0` | `fever_true` | -- | true | 0/13 | 0.0% | false 13 |
| `fever_true:ea6e86e9` | `fever_true` | -- | true | 0/13 | 0.0% | null 13 |
| `fever_true:f885b3cb` | `fever_true` | -- | true | 0/13 | 0.0% | null 13 |
| `fever_true:74ccf7bd` | `fever_true` | -- | true | 0/12 | 0.0% | null 12 |
| `fever_true:872e3af9` | `fever_true` | -- | true | 0/12 | 0.0% | null 12 |

*168 further fragments with at least one error are in the JSON sidecar; every fragment is there regardless of score.*

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
| false | 2479 | **98** | 0.0% [0.0%, 0.0%] |
| null_ambiguous | 3062 | **224** | 100.0% [100.0%, 100.0%] |
| null_structural | 2978 | **1** | 100.0% [100.0%, 100.0%] |
| true | 1481 | **96** | 0.0% [0.0%, 0.0%] |

### By null sub-class

| sub-class | n | eff n | null recall [95% CI] |
|---|---|---|---|
| attribution | 570 | **43** | 100.0% [100.0%, 100.0%] |
| hedged | 832 | **63** | 100.0% [100.0%, 100.0%] |
| historical | 511 | **36** | 100.0% [100.0%, 100.0%] |
| metaphor | 645 | **47** | 100.0% [100.0%, 100.0%] |
| third_party | 504 | **35** | 100.0% [100.0%, 100.0%] |

### By fragment library

| library | n | eff n | accuracy [95% CI] |
|---|---|---|---|
| fever_false | 2479 | **98** | 0.0% [0.0%, 0.0%] |
| fever_null_attribution | 570 | **43** | 100.0% [100.0%, 100.0%] |
| fever_null_hedged | 832 | **63** | 100.0% [100.0%, 100.0%] |
| fever_null_historical | 511 | **36** | 100.0% [100.0%, 100.0%] |
| fever_null_metaphor | 645 | **47** | 100.0% [100.0%, 100.0%] |
| fever_null_thirdparty | 504 | **35** | 100.0% [100.0%, 100.0%] |
| fever_true | 1481 | **96** | 0.0% [0.0%, 0.0%] |
| (none) | 2978 | **1** | 100.0% [100.0%, 100.0%] |

### Per-fragment errors (worst first)

Whether errors are spread thinly across many fragments or piled onto a few is the difference
between "the method is too weak" (model work) and "these specific ideas are not learnable from
the data we have" (library work, and these are the fragments to write more of). No intervals:
a fragment is one cluster, so an interval over its own examples measures nothing.

194 of 463 decisive fragments were got wrong at least once.

`length_only__shuffled`: 3960 errors across 194 of 463 decisive fragments. Half of them fall on **71** fragments (an even spread would be 97.0); the worst ten carry 8.9% of all errors.

| fragment | library | sub-class | truth | correct | accuracy | predicted as |
|---|---|---|---|---|---|---|
| `fever_false:5a6a9b80` | `fever_false` | -- | false | 0/38 | 0.0% | null 38 |
| `fever_false:24e5c247` | `fever_false` | -- | false | 0/36 | 0.0% | null 36 |
| `fever_false:b9076eff` | `fever_false` | -- | false | 0/36 | 0.0% | null 36 |
| `fever_false:fc2ae0f2` | `fever_false` | -- | false | 0/36 | 0.0% | null 36 |
| `fever_false:17f6c637` | `fever_false` | -- | false | 0/35 | 0.0% | null 35 |
| `fever_false:55bf1913` | `fever_false` | -- | false | 0/35 | 0.0% | null 35 |
| `fever_false:9f46e710` | `fever_false` | -- | false | 0/35 | 0.0% | null 35 |
| `fever_false:d0ca84a7` | `fever_false` | -- | false | 0/35 | 0.0% | null 35 |
| `fever_false:0429068c` | `fever_false` | -- | false | 0/34 | 0.0% | null 34 |
| `fever_false:5969c6c9` | `fever_false` | -- | false | 0/33 | 0.0% | null 33 |
| `fever_false:b96ed279` | `fever_false` | -- | false | 0/33 | 0.0% | null 33 |
| `fever_false:f586e96d` | `fever_false` | -- | false | 0/33 | 0.0% | null 33 |
| `fever_false:2b944abc` | `fever_false` | -- | false | 0/32 | 0.0% | null 32 |
| `fever_false:a9a0220e` | `fever_false` | -- | false | 0/32 | 0.0% | null 32 |
| `fever_false:cdf2609b` | `fever_false` | -- | false | 0/32 | 0.0% | null 32 |
| `fever_false:5c2a065d` | `fever_false` | -- | false | 0/31 | 0.0% | null 31 |
| `fever_false:d5ed3ff1` | `fever_false` | -- | false | 0/31 | 0.0% | null 31 |
| `fever_false:de0596c4` | `fever_false` | -- | false | 0/31 | 0.0% | null 31 |
| `fever_false:e2aff3b8` | `fever_false` | -- | false | 0/31 | 0.0% | null 31 |
| `fever_false:758d5434` | `fever_false` | -- | false | 0/30 | 0.0% | null 30 |
| `fever_false:8d02bd9e` | `fever_false` | -- | false | 0/30 | 0.0% | null 30 |
| `fever_false:a5b671a1` | `fever_false` | -- | false | 0/30 | 0.0% | null 30 |
| `fever_false:3a3043ff` | `fever_false` | -- | false | 0/29 | 0.0% | null 29 |
| `fever_false:463f8189` | `fever_false` | -- | false | 0/29 | 0.0% | null 29 |
| `fever_false:cbf9d7a5` | `fever_false` | -- | false | 0/29 | 0.0% | null 29 |
| `fever_true:18173593` | `fever_true` | -- | true | 0/29 | 0.0% | null 29 |
| `fever_false:147d5cf0` | `fever_false` | -- | false | 0/28 | 0.0% | null 28 |
| `fever_false:43f5b35d` | `fever_false` | -- | false | 0/28 | 0.0% | null 28 |
| `fever_false:56a45ff1` | `fever_false` | -- | false | 0/28 | 0.0% | null 28 |
| `fever_false:7b64d17a` | `fever_false` | -- | false | 0/28 | 0.0% | null 28 |
| `fever_false:90f7b87f` | `fever_false` | -- | false | 0/28 | 0.0% | null 28 |
| `fever_false:a4cda1e2` | `fever_false` | -- | false | 0/28 | 0.0% | null 28 |
| `fever_false:a6c0d44a` | `fever_false` | -- | false | 0/28 | 0.0% | null 28 |
| `fever_true:753c7815` | `fever_true` | -- | true | 0/28 | 0.0% | null 28 |
| `fever_true:f3ee0d07` | `fever_true` | -- | true | 0/28 | 0.0% | null 28 |
| `fever_false:4bf3caad` | `fever_false` | -- | false | 0/27 | 0.0% | null 27 |
| `fever_false:78a4c55b` | `fever_false` | -- | false | 0/27 | 0.0% | null 27 |
| `fever_false:c747066d` | `fever_false` | -- | false | 0/27 | 0.0% | null 27 |
| `fever_true:1c3df822` | `fever_true` | -- | true | 0/27 | 0.0% | null 27 |
| `fever_false:033927e6` | `fever_false` | -- | false | 0/26 | 0.0% | null 26 |

*154 further fragments with at least one error are in the JSON sidecar; every fragment is there regardless of score.*

## `tfidf_logreg__shuffled`

TF-IDF unigrams and bigrams into logistic regression. Tests whether the dataset is keyword-solvable. Its overall accuracy is close to uninformative; the `null_ambiguous` slice is the number that matters. **Negative control:** trained on permuted training labels (seed 7) and evaluated on the unpermuted test split, where it must land at chance.

Decision-rule margins selected per fold (on each fold's own validation split): 0.0, 0.05.

*Confusion matrix, raw argmax*

|  | pred false | pred true | pred null | total |
|---|---|---|---|---|
| **truth false** | 11 | 0 | 2468 | 2479 |
| **truth true** | 7 | 0 | 1474 | 1481 |
| **truth null** | 36 | 0 | 6004 | 6040 |
| **total** | 54 | 0 | 9946 | 10000 |

`null -> true`: 0 of 6040 truly-null examples (0.00%).

*Confusion matrix, after the decision rule*

|  | pred false | pred true | pred null | total |
|---|---|---|---|---|
| **truth false** | 11 | 0 | 2468 | 2479 |
| **truth true** | 7 | 0 | 1474 | 1481 |
| **truth null** | 36 | 0 | 6004 | 6040 |
| **total** | 54 | 0 | 9946 | 10000 |

`null -> true`: 0 of 6040 truly-null examples (0.00%).

### Per class, after the decision rule

| class | support | predicted | precision | recall | F1 |
|---|---|---|---|---|---|
| `false` | 2479 | 54 | 20.4% | 0.4% | 0.9% |
| `true` | 1481 | 0 | -- | 0.0% | 0.0% |
| `null` | 6040 | 9946 | 60.4% | 99.4% | 75.1% |

### By label mode

| label mode | n | eff n | accuracy [95% CI] |
|---|---|---|---|
| false | 2479 | **98** | 0.4% [0.0%, 1.0%] |
| null_ambiguous | 3062 | **224** | 99.4% [99.1%, 99.7%] |
| null_structural | 2978 | **1** | 99.4% [99.4%, 99.4%] |
| true | 1481 | **96** | 0.0% [0.0%, 0.0%] |

### By null sub-class

| sub-class | n | eff n | null recall [95% CI] |
|---|---|---|---|
| attribution | 570 | **43** | 99.5% [98.8%, 100.0%] |
| hedged | 832 | **63** | 98.8% [97.8%, 99.6%] |
| historical | 511 | **36** | 99.8% [99.3%, 100.0%] |
| metaphor | 645 | **47** | 99.8% [99.5%, 100.0%] |
| third_party | 504 | **35** | 99.6% [99.0%, 100.0%] |

### By fragment library

| library | n | eff n | accuracy [95% CI] |
|---|---|---|---|
| fever_false | 2479 | **98** | 0.4% [0.0%, 1.0%] |
| fever_null_attribution | 570 | **43** | 99.5% [98.8%, 100.0%] |
| fever_null_hedged | 832 | **63** | 98.8% [97.8%, 99.6%] |
| fever_null_historical | 511 | **36** | 99.8% [99.3%, 100.0%] |
| fever_null_metaphor | 645 | **47** | 99.8% [99.5%, 100.0%] |
| fever_null_thirdparty | 504 | **35** | 99.6% [99.0%, 100.0%] |
| fever_true | 1481 | **96** | 0.0% [0.0%, 0.0%] |
| (none) | 2978 | **1** | 99.4% [99.4%, 99.4%] |

### Per-fragment errors (worst first)

Whether errors are spread thinly across many fragments or piled onto a few is the difference
between "the method is too weak" (model work) and "these specific ideas are not learnable from
the data we have" (library work, and these are the fragments to write more of). No intervals:
a fragment is one cluster, so an interval over its own examples measures nothing.

208 of 463 decisive fragments were got wrong at least once.

`tfidf_logreg__shuffled`: 3966 errors across 208 of 463 decisive fragments. Half of them fall on **71** fragments (an even spread would be 104.0); the worst ten carry 8.9% of all errors.

| fragment | library | sub-class | truth | correct | accuracy | predicted as |
|---|---|---|---|---|---|---|
| `fever_false:5a6a9b80` | `fever_false` | -- | false | 0/38 | 0.0% | null 38 |
| `fever_false:24e5c247` | `fever_false` | -- | false | 0/36 | 0.0% | null 36 |
| `fever_false:b9076eff` | `fever_false` | -- | false | 0/36 | 0.0% | null 36 |
| `fever_false:fc2ae0f2` | `fever_false` | -- | false | 0/36 | 0.0% | null 36 |
| `fever_false:17f6c637` | `fever_false` | -- | false | 0/35 | 0.0% | null 35 |
| `fever_false:55bf1913` | `fever_false` | -- | false | 0/35 | 0.0% | null 35 |
| `fever_false:9f46e710` | `fever_false` | -- | false | 0/35 | 0.0% | null 35 |
| `fever_false:d0ca84a7` | `fever_false` | -- | false | 0/35 | 0.0% | null 35 |
| `fever_false:0429068c` | `fever_false` | -- | false | 0/34 | 0.0% | null 34 |
| `fever_false:5969c6c9` | `fever_false` | -- | false | 0/33 | 0.0% | null 33 |
| `fever_false:b96ed279` | `fever_false` | -- | false | 0/33 | 0.0% | null 33 |
| `fever_false:f586e96d` | `fever_false` | -- | false | 0/33 | 0.0% | null 33 |
| `fever_false:2b944abc` | `fever_false` | -- | false | 0/32 | 0.0% | null 32 |
| `fever_false:a9a0220e` | `fever_false` | -- | false | 0/32 | 0.0% | null 32 |
| `fever_false:cdf2609b` | `fever_false` | -- | false | 0/32 | 0.0% | null 32 |
| `fever_false:5c2a065d` | `fever_false` | -- | false | 0/31 | 0.0% | null 31 |
| `fever_false:d5ed3ff1` | `fever_false` | -- | false | 0/31 | 0.0% | null 31 |
| `fever_false:de0596c4` | `fever_false` | -- | false | 0/31 | 0.0% | null 31 |
| `fever_false:e2aff3b8` | `fever_false` | -- | false | 0/31 | 0.0% | null 31 |
| `fever_false:758d5434` | `fever_false` | -- | false | 0/30 | 0.0% | null 30 |
| `fever_false:8d02bd9e` | `fever_false` | -- | false | 0/30 | 0.0% | null 30 |
| `fever_false:a5b671a1` | `fever_false` | -- | false | 0/30 | 0.0% | null 30 |
| `fever_false:463f8189` | `fever_false` | -- | false | 0/29 | 0.0% | null 29 |
| `fever_true:18173593` | `fever_true` | -- | true | 0/29 | 0.0% | null 29 |
| `fever_false:147d5cf0` | `fever_false` | -- | false | 0/28 | 0.0% | null 28 |
| `fever_false:43f5b35d` | `fever_false` | -- | false | 0/28 | 0.0% | null 28 |
| `fever_false:56a45ff1` | `fever_false` | -- | false | 0/28 | 0.0% | null 28 |
| `fever_false:7b64d17a` | `fever_false` | -- | false | 0/28 | 0.0% | null 28 |
| `fever_false:90f7b87f` | `fever_false` | -- | false | 0/28 | 0.0% | null 28 |
| `fever_false:a4cda1e2` | `fever_false` | -- | false | 0/28 | 0.0% | null 28 |
| `fever_false:a6c0d44a` | `fever_false` | -- | false | 0/28 | 0.0% | null 28 |
| `fever_true:753c7815` | `fever_true` | -- | true | 0/28 | 0.0% | null 28 |
| `fever_true:f3ee0d07` | `fever_true` | -- | true | 0/28 | 0.0% | null 28 |
| `fever_false:4bf3caad` | `fever_false` | -- | false | 0/27 | 0.0% | null 27 |
| `fever_false:78a4c55b` | `fever_false` | -- | false | 0/27 | 0.0% | null 27 |
| `fever_false:c747066d` | `fever_false` | -- | false | 0/27 | 0.0% | null 27 |
| `fever_true:1c3df822` | `fever_true` | -- | true | 0/27 | 0.0% | null 27 |
| `fever_false:1bc39bc3` | `fever_false` | -- | false | 0/26 | 0.0% | null 26 |
| `fever_false:3de7ecac` | `fever_false` | -- | false | 0/26 | 0.0% | null 26 |
| `fever_false:662acc87` | `fever_false` | -- | false | 0/26 | 0.0% | null 26 |

*168 further fragments with at least one error are in the JSON sidecar; every fragment is there regardless of score.*

## `arm_b_finetune@c0.5-d0.0`

`roberta-base` with **every layer unfrozen**, mean-pooled, with the same `Linear(768, 3)` head -- 110M trainable parameters against Arm A's 2,307. Three epochs at batch 32, learning rate 2e-5, 10% linear warmup, AdamW, fp32. No gradient checkpointing, no 8-bit optimiser, no LoRA, no gradient accumulation: the full model fits in 12GB with room to spare, so anything that reads like a compute compromise would be a mistake rather than a saving. This is the arm that separates "the fragment libraries are the bottleneck" from "the method is too weak": if a fully fine-tuned encoder still cannot read third-party attribution, tense or metaphor, the limit is in the ideas the libraries contain and the fix is library work, not model work.

Decision-rule margins selected per fold (on each fold's own validation split): 0.0, 0.35, 0.85, 0.9.

*Confusion matrix, raw argmax*

|  | pred false | pred true | pred null | total |
|---|---|---|---|---|
| **truth false** | 2158 | 73 | 248 | 2479 |
| **truth true** | 26 | 1257 | 198 | 1481 |
| **truth null** | 11 | 119 | 5910 | 6040 |
| **total** | 2195 | 1449 | 6356 | 10000 |

`null -> true`: 119 of 6040 truly-null examples (1.97%).

*Confusion matrix, after the decision rule*

|  | pred false | pred true | pred null | total |
|---|---|---|---|---|
| **truth false** | 2181 | 47 | 251 | 2479 |
| **truth true** | 35 | 1240 | 206 | 1481 |
| **truth null** | 15 | 98 | 5927 | 6040 |
| **total** | 2231 | 1385 | 6384 | 10000 |

`null -> true`: 98 of 6040 truly-null examples (1.62%).

### Per class, after the decision rule

| class | support | predicted | precision | recall | F1 |
|---|---|---|---|---|---|
| `false` | 2479 | 2231 | 97.8% | 88.0% | 92.6% |
| `true` | 1481 | 1385 | 89.5% | 83.7% | 86.5% |
| `null` | 6040 | 6384 | 92.8% | 98.1% | 95.4% |

### By label mode

| label mode | n | eff n | accuracy [95% CI] |
|---|---|---|---|
| false | 2479 | **98** | 88.0% [81.7%, 93.8%] |
| null_ambiguous | 3062 | **224** | 96.4% [94.1%, 98.4%] |
| null_structural | 2978 | **1** | 99.9% [99.9%, 99.9%] |
| true | 1481 | **96** | 83.7% [76.8%, 90.5%] |

### By null sub-class

| sub-class | n | eff n | null recall [95% CI] |
|---|---|---|---|
| attribution | 570 | **43** | 97.9% [94.4%, 100.0%] |
| hedged | 832 | **63** | 90.7% [82.5%, 96.8%] |
| historical | 511 | **36** | 96.5% [92.1%, 99.8%] |
| metaphor | 645 | **47** | 99.7% [99.2%, 100.0%] |
| third_party | 504 | **35** | 100.0% [100.0%, 100.0%] |

### By fragment library

| library | n | eff n | accuracy [95% CI] |
|---|---|---|---|
| fever_false | 2479 | **98** | 88.0% [81.7%, 93.8%] |
| fever_null_attribution | 570 | **43** | 97.9% [94.4%, 100.0%] |
| fever_null_hedged | 832 | **63** | 90.7% [82.5%, 96.8%] |
| fever_null_historical | 511 | **36** | 96.5% [92.1%, 99.8%] |
| fever_null_metaphor | 645 | **47** | 99.7% [99.2%, 100.0%] |
| fever_null_thirdparty | 504 | **35** | 100.0% [100.0%, 100.0%] |
| fever_true | 1481 | **96** | 83.7% [76.8%, 90.5%] |
| (none) | 2978 | **1** | 99.9% [99.9%, 99.9%] |

### Per-fragment errors (worst first)

Whether errors are spread thinly across many fragments or piled onto a few is the difference
between "the method is too weak" (model work) and "these specific ideas are not learnable from
the data we have" (library work, and these are the fragments to write more of). No intervals:
a fragment is one cluster, so an interval over its own examples measures nothing.

62 of 463 decisive fragments were got wrong at least once.

`arm_b_finetune@c0.5-d0.0`: 648 errors across 62 of 463 decisive fragments. Half of them fall on **16** fragments (an even spread would be 31.0); the worst ten carry 37.3% of all errors.

| fragment | library | sub-class | truth | correct | accuracy | predicted as |
|---|---|---|---|---|---|---|
| `fever_false:b96ed279` | `fever_false` | -- | false | 0/33 | 0.0% | null 33 |
| `fever_false:cdf2609b` | `fever_false` | -- | false | 0/32 | 0.0% | null 32 |
| `fever_false:5c2a065d` | `fever_false` | -- | false | 0/31 | 0.0% | true 2, null 29 |
| `fever_false:de0596c4` | `fever_false` | -- | false | 0/31 | 0.0% | null 31 |
| `fever_true:391fb2ce` | `fever_true` | -- | true | 0/18 | 0.0% | null 18 |
| `fever_false:e8c514ff` | `fever_false` | -- | false | 0/16 | 0.0% | true 16 |
| `fever_null_hedged:5bf1b63f` | `fever_null_hedged` | hedged | null | 0/14 | 0.0% | true 14 |
| `fever_true:0ddb8a11` | `fever_true` | -- | true | 0/14 | 0.0% | null 14 |
| `fever_true:97087dd7` | `fever_true` | -- | true | 0/14 | 0.0% | null 14 |
| `fever_true:d00c307b` | `fever_true` | -- | true | 0/14 | 0.0% | null 14 |
| `fever_null_hedged:cf95d564` | `fever_null_hedged` | hedged | null | 0/13 | 0.0% | true 13 |
| `fever_true:c5d3e4a0` | `fever_true` | -- | true | 0/13 | 0.0% | false 13 |
| `fever_null_hedged:fafa0b56` | `fever_null_hedged` | hedged | null | 0/12 | 0.0% | true 12 |
| `fever_true:872e3af9` | `fever_true` | -- | true | 0/12 | 0.0% | null 12 |
| `fever_true:ed36ef0f` | `fever_true` | -- | true | 0/12 | 0.0% | null 12 |
| `fever_true:5e4f1da7` | `fever_true` | -- | true | 0/11 | 0.0% | null 11 |
| `fever_true:b950a4fc` | `fever_true` | -- | true | 0/11 | 0.0% | null 11 |
| `fever_null_hedged:42486de4` | `fever_null_hedged` | hedged | null | 0/10 | 0.0% | false 4, true 6 |
| `fever_null_hedged:8d1c41e3` | `fever_null_hedged` | hedged | null | 0/10 | 0.0% | true 10 |
| `fever_true:dd7a11e2` | `fever_true` | -- | true | 0/10 | 0.0% | null 10 |
| `fever_null_hedged:965c4a64` | `fever_null_hedged` | hedged | null | 0/9 | 0.0% | false 2, true 7 |
| `fever_null_historical:feadcb2c` | `fever_null_historical` | historical | null | 0/8 | 0.0% | true 8 |
| `fever_false:990bcf31` | `fever_false` | -- | false | 1/22 | 4.5% | false 1, null 21 |
| `fever_true:db1acb55` | `fever_true` | -- | true | 1/17 | 5.9% | false 16, true 1 |
| `fever_true:dd079c14` | `fever_true` | -- | true | 1/15 | 6.7% | true 1, null 14 |
| `fever_true:ef344ff7` | `fever_true` | -- | true | 1/12 | 8.3% | true 1, null 11 |
| `fever_false:afdc7129` | `fever_false` | -- | false | 2/22 | 9.1% | false 2, null 20 |
| `fever_false:3de7ecac` | `fever_false` | -- | false | 5/26 | 19.2% | false 5, null 21 |
| `fever_true:c7489e90` | `fever_true` | -- | true | 4/19 | 21.1% | true 4, null 15 |
| `fever_null_historical:1b314733` | `fever_null_historical` | historical | null | 2/7 | 28.6% | true 5, null 2 |
| `fever_false:93390aea` | `fever_false` | -- | false | 8/26 | 30.8% | false 8, null 18 |
| `fever_true:15a05d92` | `fever_true` | -- | true | 8/25 | 32.0% | true 8, null 17 |
| `fever_false:f1b6ac0d` | `fever_false` | -- | false | 8/24 | 33.3% | false 8, null 16 |
| `fever_true:74ccf7bd` | `fever_true` | -- | true | 4/12 | 33.3% | true 4, null 8 |
| `fever_true:7844c66b` | `fever_true` | -- | true | 7/18 | 38.9% | true 7, null 11 |
| `fever_null_attribution:17b7ab2a` | `fever_null_attribution` | attribution | null | 6/14 | 42.9% | true 8, null 6 |
| `fever_false:e70e24b6` | `fever_false` | -- | false | 12/26 | 46.2% | false 12, true 14 |
| `fever_false:f7d03fcb` | `fever_false` | -- | false | 12/21 | 57.1% | false 12, null 9 |
| `fever_false:3a3043ff` | `fever_false` | -- | false | 17/29 | 58.6% | false 17, true 12 |
| `fever_true:2ee57e4c` | `fever_true` | -- | true | 6/10 | 60.0% | true 6, null 4 |

*22 further fragments with at least one error are in the JSON sidecar; every fragment is there regardless of score.*

## `arm_b_finetune@c0.5-d0.3`

`roberta-base` with **every layer unfrozen**, mean-pooled, with the same `Linear(768, 3)` head -- 110M trainable parameters against Arm A's 2,307. Three epochs at batch 32, learning rate 2e-5, 10% linear warmup, AdamW, fp32. No gradient checkpointing, no 8-bit optimiser, no LoRA, no gradient accumulation: the full model fits in 12GB with room to spare, so anything that reads like a compute compromise would be a mistake rather than a saving. This is the arm that separates "the fragment libraries are the bottleneck" from "the method is too weak": if a fully fine-tuned encoder still cannot read third-party attribution, tense or metaphor, the limit is in the ideas the libraries contain and the fix is library work, not model work.

Decision-rule margins selected per fold (on each fold's own validation split): 0.0, 0.55, 0.65, 0.75.

*Confusion matrix, raw argmax*

|  | pred false | pred true | pred null | total |
|---|---|---|---|---|
| **truth false** | 2335 | 35 | 109 | 2479 |
| **truth true** | 22 | 1344 | 115 | 1481 |
| **truth null** | 28 | 61 | 5951 | 6040 |
| **total** | 2385 | 1440 | 6175 | 10000 |

`null -> true`: 61 of 6040 truly-null examples (1.01%).

*Confusion matrix, after the decision rule*

|  | pred false | pred true | pred null | total |
|---|---|---|---|---|
| **truth false** | 2339 | 30 | 110 | 2479 |
| **truth true** | 25 | 1335 | 121 | 1481 |
| **truth null** | 28 | 57 | 5955 | 6040 |
| **total** | 2392 | 1422 | 6186 | 10000 |

`null -> true`: 57 of 6040 truly-null examples (0.94%).

### Per class, after the decision rule

| class | support | predicted | precision | recall | F1 |
|---|---|---|---|---|---|
| `false` | 2479 | 2392 | 97.8% | 94.4% | 96.0% |
| `true` | 1481 | 1422 | 93.9% | 90.1% | 92.0% |
| `null` | 6040 | 6186 | 96.3% | 98.6% | 97.4% |

### By label mode

| label mode | n | eff n | accuracy [95% CI] |
|---|---|---|---|
| false | 2479 | **175** | 94.4% [90.5%, 97.6%] |
| null_ambiguous | 3062 | **224** | 97.3% [95.2%, 98.8%] |
| null_structural | 2978 | **1** | 100.0% [100.0%, 100.0%] |
| true | 1481 | **174** | 90.1% [85.9%, 94.1%] |

### By null sub-class

| sub-class | n | eff n | null recall [95% CI] |
|---|---|---|---|
| attribution | 570 | **43** | 98.1% [95.3%, 99.7%] |
| hedged | 832 | **63** | 93.0% [86.2%, 98.0%] |
| historical | 511 | **36** | 97.5% [93.7%, 100.0%] |
| metaphor | 645 | **47** | 99.7% [98.9%, 100.0%] |
| third_party | 504 | **35** | 100.0% [100.0%, 100.0%] |

### By fragment library

| library | n | eff n | accuracy [95% CI] |
|---|---|---|---|
| declarative_v1 | 1208 | **155** | 100.0% [100.0%, 100.0%] |
| fever_false | 1726 | **98** | 91.9% [86.6%, 96.3%] |
| fever_null_attribution | 570 | **43** | 98.1% [95.3%, 99.7%] |
| fever_null_hedged | 832 | **63** | 93.0% [86.2%, 98.0%] |
| fever_null_historical | 511 | **36** | 97.5% [93.7%, 100.0%] |
| fever_null_metaphor | 645 | **47** | 99.7% [98.9%, 100.0%] |
| fever_null_thirdparty | 504 | **35** | 100.0% [100.0%, 100.0%] |
| fever_true | 1026 | **96** | 85.8% [79.6%, 91.6%] |
| (none) | 2978 | **1** | 100.0% [100.0%, 100.0%] |

### Per-fragment errors (worst first)

Whether errors are spread thinly across many fragments or piled onto a few is the difference
between "the method is too weak" (model work) and "these specific ideas are not learnable from
the data we have" (library work, and these are the fragments to write more of). No intervals:
a fragment is one cluster, so an interval over its own examples measures nothing.

62 of 852 decisive fragments were got wrong at least once.

`arm_b_finetune@c0.5-d0.3`: 370 errors across 62 of 852 decisive fragments. Half of them fall on **14** fragments (an even spread would be 31.0); the worst ten carry 40.0% of all errors.

| fragment | library | sub-class | truth | correct | accuracy | predicted as |
|---|---|---|---|---|---|---|
| `fever_false:3de7ecac` | `fever_false` | -- | false | 0/22 | 0.0% | null 22 |
| `fever_false:afdc7129` | `fever_false` | -- | false | 0/20 | 0.0% | null 20 |
| `fever_false:5c2a065d` | `fever_false` | -- | false | 0/18 | 0.0% | true 2, null 16 |
| `fever_false:f7d03fcb` | `fever_false` | -- | false | 0/18 | 0.0% | null 18 |
| `fever_null_hedged:5bf1b63f` | `fever_null_hedged` | hedged | null | 0/14 | 0.0% | true 14 |
| `fever_null_hedged:42486de4` | `fever_null_hedged` | hedged | null | 0/10 | 0.0% | false 10 |
| `fever_true:2ee57e4c` | `fever_true` | -- | true | 0/10 | 0.0% | null 10 |
| `fever_true:b950a4fc` | `fever_true` | -- | true | 0/10 | 0.0% | null 10 |
| `fever_true:d00c307b` | `fever_true` | -- | true | 0/10 | 0.0% | null 10 |
| `fever_true:db1acb55` | `fever_true` | -- | true | 0/10 | 0.0% | false 10 |
| `fever_true:dd7a11e2` | `fever_true` | -- | true | 0/10 | 0.0% | null 10 |
| `fever_null_hedged:965c4a64` | `fever_null_hedged` | hedged | null | 0/9 | 0.0% | false 9 |
| `fever_null_historical:feadcb2c` | `fever_null_historical` | historical | null | 0/8 | 0.0% | true 8 |
| `fever_true:fc118943` | `fever_true` | -- | true | 0/8 | 0.0% | null 8 |
| `fever_true:5e4f1da7` | `fever_true` | -- | true | 0/7 | 0.0% | null 7 |
| `fever_true:0ddb8a11` | `fever_true` | -- | true | 0/5 | 0.0% | null 5 |
| `fever_true:ef344ff7` | `fever_true` | -- | true | 0/5 | 0.0% | false 1, null 4 |
| `fever_false:3a3043ff` | `fever_false` | -- | false | 1/17 | 5.9% | false 1, true 16 |
| `fever_true:97087dd7` | `fever_true` | -- | true | 1/9 | 11.1% | true 1, null 8 |
| `fever_true:7844c66b` | `fever_true` | -- | true | 2/12 | 16.7% | true 2, null 10 |
| `fever_true:dd079c14` | `fever_true` | -- | true | 1/6 | 16.7% | true 1, null 5 |
| `fever_null_hedged:8d1c41e3` | `fever_null_hedged` | hedged | null | 3/10 | 30.0% | true 7, null 3 |
| `fever_false:d15cd85c` | `fever_false` | -- | false | 5/15 | 33.3% | false 5, null 10 |
| `fever_null_hedged:fafa0b56` | `fever_null_hedged` | hedged | null | 4/12 | 33.3% | true 8, null 4 |
| `fever_null_attribution:7830c8db` | `fever_null_attribution` | attribution | null | 3/9 | 33.3% | true 6, null 3 |
| `fever_true:94ca0a26` | `fever_true` | -- | true | 2/6 | 33.3% | false 4, true 2 |
| `fever_true:01833454` | `fever_true` | -- | true | 5/14 | 35.7% | false 9, true 5 |
| `fever_true:ed36ef0f` | `fever_true` | -- | true | 5/12 | 41.7% | true 5, null 7 |
| `fever_false:e70e24b6` | `fever_false` | -- | false | 8/17 | 47.1% | false 8, true 9 |
| `fever_true:cccc5a01` | `fever_true` | -- | true | 5/9 | 55.6% | true 5, null 4 |
| `fever_true:ed3c8c83` | `fever_true` | -- | true | 5/9 | 55.6% | true 5, null 4 |
| `fever_true:5441ccb2` | `fever_true` | -- | true | 6/10 | 60.0% | true 6, null 4 |
| `fever_true:74ccf7bd` | `fever_true` | -- | true | 6/10 | 60.0% | true 6, null 4 |
| `fever_true:c5d3e4a0` | `fever_true` | -- | true | 6/10 | 60.0% | true 6, null 4 |
| `fever_true:c5273bcd` | `fever_true` | -- | true | 5/8 | 62.5% | true 5, null 3 |
| `fever_null_historical:f2a841ba` | `fever_null_historical` | historical | null | 7/11 | 63.6% | true 4, null 7 |
| `fever_false:0cc191ec` | `fever_false` | -- | false | 15/23 | 65.2% | false 15, null 8 |
| `fever_false:e0897296` | `fever_false` | -- | false | 10/15 | 66.7% | false 10, null 5 |
| `fever_false:ebac5db7` | `fever_false` | -- | false | 9/12 | 75.0% | false 9, null 3 |
| `fever_false:990bcf31` | `fever_false` | -- | false | 13/17 | 76.5% | false 13, null 4 |

*22 further fragments with at least one error are in the JSON sidecar; every fragment is there regardless of score.*

## `arm_b_finetune@c0.5-d0.6`

`roberta-base` with **every layer unfrozen**, mean-pooled, with the same `Linear(768, 3)` head -- 110M trainable parameters against Arm A's 2,307. Three epochs at batch 32, learning rate 2e-5, 10% linear warmup, AdamW, fp32. No gradient checkpointing, no 8-bit optimiser, no LoRA, no gradient accumulation: the full model fits in 12GB with room to spare, so anything that reads like a compute compromise would be a mistake rather than a saving. This is the arm that separates "the fragment libraries are the bottleneck" from "the method is too weak": if a fully fine-tuned encoder still cannot read third-party attribution, tense or metaphor, the limit is in the ideas the libraries contain and the fix is library work, not model work.

Decision-rule margins selected per fold (on each fold's own validation split): 0.0, 0.2, 0.3, 0.85, 0.9.

*Confusion matrix, raw argmax*

|  | pred false | pred true | pred null | total |
|---|---|---|---|---|
| **truth false** | 2408 | 3 | 68 | 2479 |
| **truth true** | 16 | 1401 | 64 | 1481 |
| **truth null** | 36 | 81 | 5923 | 6040 |
| **total** | 2460 | 1485 | 6055 | 10000 |

`null -> true`: 81 of 6040 truly-null examples (1.34%).

*Confusion matrix, after the decision rule*

|  | pred false | pred true | pred null | total |
|---|---|---|---|---|
| **truth false** | 2409 | 2 | 68 | 2479 |
| **truth true** | 16 | 1397 | 68 | 1481 |
| **truth null** | 41 | 67 | 5932 | 6040 |
| **total** | 2466 | 1466 | 6068 | 10000 |

`null -> true`: 67 of 6040 truly-null examples (1.11%).

### Per class, after the decision rule

| class | support | predicted | precision | recall | F1 |
|---|---|---|---|---|---|
| `false` | 2479 | 2466 | 97.7% | 97.2% | 97.4% |
| `true` | 1481 | 1466 | 95.3% | 94.3% | 94.8% |
| `null` | 6040 | 6068 | 97.8% | 98.2% | 98.0% |

### By label mode

| label mode | n | eff n | accuracy [95% CI] |
|---|---|---|---|
| false | 2479 | **177** | 97.2% [95.1%, 98.9%] |
| null_ambiguous | 3062 | **224** | 96.6% [94.3%, 98.5%] |
| null_structural | 2978 | **1** | 99.9% [99.9%, 99.9%] |
| true | 1481 | **177** | 94.3% [91.3%, 96.9%] |

### By null sub-class

| sub-class | n | eff n | null recall [95% CI] |
|---|---|---|---|
| attribution | 570 | **43** | 97.4% [91.9%, 100.0%] |
| hedged | 832 | **63** | 91.9% [84.7%, 97.5%] |
| historical | 511 | **36** | 98.4% [95.0%, 100.0%] |
| metaphor | 645 | **47** | 98.8% [96.7%, 99.9%] |
| third_party | 504 | **35** | 98.6% [96.6%, 100.0%] |

### By fragment library

| library | n | eff n | accuracy [95% CI] |
|---|---|---|---|
| declarative_v1 | 2395 | **161** | 100.0% [100.0%, 100.0%] |
| fever_false | 953 | **98** | 92.7% [87.5%, 97.1%] |
| fever_null_attribution | 570 | **43** | 97.4% [91.9%, 100.0%] |
| fever_null_hedged | 832 | **63** | 91.9% [84.7%, 97.5%] |
| fever_null_historical | 511 | **36** | 98.4% [95.0%, 100.0%] |
| fever_null_metaphor | 645 | **47** | 98.8% [96.7%, 99.9%] |
| fever_null_thirdparty | 504 | **35** | 98.6% [96.6%, 100.0%] |
| fever_true | 612 | **95** | 86.3% [79.5%, 91.8%] |
| (none) | 2978 | **1** | 99.9% [99.9%, 99.9%] |

### Per-fragment errors (worst first)

Whether errors are spread thinly across many fragments or piled onto a few is the difference
between "the method is too weak" (model work) and "these specific ideas are not learnable from
the data we have" (library work, and these are the fragments to write more of). No intervals:
a fragment is one cluster, so an interval over its own examples measures nothing.

51 of 888 decisive fragments were got wrong at least once.

`arm_b_finetune@c0.5-d0.6`: 259 errors across 51 of 888 decisive fragments. Half of them fall on **13** fragments (an even spread would be 25.5); the worst ten carry 41.7% of all errors.

| fragment | library | sub-class | truth | correct | accuracy | predicted as |
|---|---|---|---|---|---|---|
| `fever_null_attribution:17b7ab2a` | `fever_null_attribution` | attribution | null | 0/14 | 0.0% | true 14 |
| `fever_null_hedged:5bf1b63f` | `fever_null_hedged` | hedged | null | 0/14 | 0.0% | true 14 |
| `fever_false:f7d03fcb` | `fever_false` | -- | false | 0/12 | 0.0% | null 12 |
| `fever_false:3de7ecac` | `fever_false` | -- | false | 0/10 | 0.0% | null 10 |
| `fever_false:afdc7129` | `fever_false` | -- | false | 0/10 | 0.0% | null 10 |
| `fever_null_hedged:42486de4` | `fever_null_hedged` | hedged | null | 0/10 | 0.0% | false 10 |
| `fever_null_hedged:8d1c41e3` | `fever_null_hedged` | hedged | null | 0/10 | 0.0% | false 4, true 6 |
| `fever_null_hedged:965c4a64` | `fever_null_hedged` | hedged | null | 0/9 | 0.0% | false 9 |
| `fever_false:5c2a065d` | `fever_false` | -- | false | 0/8 | 0.0% | null 8 |
| `fever_null_historical:feadcb2c` | `fever_null_historical` | historical | null | 0/8 | 0.0% | true 8 |
| `fever_true:d00c307b` | `fever_true` | -- | true | 0/7 | 0.0% | null 7 |
| `fever_true:7844c66b` | `fever_true` | -- | true | 0/6 | 0.0% | null 6 |
| `fever_true:fc118943` | `fever_true` | -- | true | 0/6 | 0.0% | null 6 |
| `fever_true:b950a4fc` | `fever_true` | -- | true | 0/5 | 0.0% | null 5 |
| `fever_true:dd7a11e2` | `fever_true` | -- | true | 0/5 | 0.0% | null 5 |
| `fever_true:97087dd7` | `fever_true` | -- | true | 0/4 | 0.0% | null 4 |
| `fever_true:db1acb55` | `fever_true` | -- | true | 0/4 | 0.0% | false 4 |
| `fever_true:ef344ff7` | `fever_true` | -- | true | 0/4 | 0.0% | null 4 |
| `fever_true:0ddb8a11` | `fever_true` | -- | true | 0/3 | 0.0% | null 3 |
| `fever_true:5ce7adbd` | `fever_true` | -- | true | 0/3 | 0.0% | null 3 |
| `fever_true:5e4f1da7` | `fever_true` | -- | true | 0/3 | 0.0% | null 3 |
| `fever_true:94ca0a26` | `fever_true` | -- | true | 0/3 | 0.0% | false 3 |
| `fever_false:990bcf31` | `fever_false` | -- | false | 1/10 | 10.0% | false 1, null 9 |
| `fever_null_hedged:fafa0b56` | `fever_null_hedged` | hedged | null | 2/12 | 16.7% | true 10, null 2 |
| `fever_true:c5273bcd` | `fever_true` | -- | true | 1/5 | 20.0% | true 1, null 4 |
| `fever_true:dd079c14` | `fever_true` | -- | true | 1/5 | 20.0% | true 1, null 4 |
| `fever_true:34ea6a85` | `fever_true` | -- | true | 3/12 | 25.0% | false 9, true 3 |
| `fever_true:ed36ef0f` | `fever_true` | -- | true | 2/7 | 28.6% | true 2, null 5 |
| `fever_true:c76b6243` | `fever_true` | -- | true | 2/6 | 33.3% | true 2, null 4 |
| `fever_null_hedged:bba323b8` | `fever_null_hedged` | hedged | null | 5/14 | 35.7% | false 8, true 1, null 5 |
| `fever_false:de0596c4` | `fever_false` | -- | false | 2/5 | 40.0% | false 2, null 3 |
| `fever_null_metaphor:15ab0c24` | `fever_null_metaphor` | metaphor | null | 4/9 | 44.4% | false 5, null 4 |
| `fever_false:0cc191ec` | `fever_false` | -- | false | 5/11 | 45.5% | false 5, null 6 |
| `fever_false:8d02bd9e` | `fever_false` | -- | false | 4/8 | 50.0% | false 4, null 4 |
| `fever_true:2ee57e4c` | `fever_true` | -- | true | 3/5 | 60.0% | true 3, null 2 |
| `fever_false:b9076eff` | `fever_false` | -- | false | 7/11 | 63.6% | false 7, null 4 |
| `fever_null_thirdparty:05f9c98e` | `fever_null_thirdparty` | third_party | null | 10/14 | 71.4% | true 4, null 10 |
| `fever_null_hedged:2f76e581` | `fever_null_hedged` | hedged | null | 8/11 | 72.7% | false 2, true 1, null 8 |
| `fever_false:d15cd85c` | `fever_false` | -- | false | 6/8 | 75.0% | false 6, null 2 |
| `fever_false:cdf2609b` | `fever_false` | -- | false | 9/11 | 81.8% | false 9, true 2 |

*11 further fragments with at least one error are in the JSON sidecar; every fragment is there regardless of score.*

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
| 1 | 10000 | 2000 | 2000 | 0.0 | 61.1% | 61.1% | 29.3% | 0.00% |
| 2 | 10000 | 2000 | 2000 | 0.0 | 60.5% | 60.5% | 25.5% | 0.00% |
| 3 | 10000 | 2000 | 2000 | 0.0 | 60.7% | 60.7% | 25.3% | 0.00% |
| 4 | 10000 | 2000 | 2000 | 0.0 | 60.3% | 60.3% | 25.3% | 0.00% |

### `tfidf_logreg`

| fold | train n | val n | test n | margin | acc (raw) | acc (ruled) | macro-F1 | null->true |
|---|---|---|---|---|---|---|---|---|
| 0 | 10000 | 2000 | 2000 | 0.0 | 78.0% | 78.0% | 70.0% | 0.41% |
| 1 | 10000 | 2000 | 2000 | 0.0 | 72.6% | 72.6% | 59.7% | 0.25% |
| 2 | 10000 | 2000 | 2000 | 0.0 | 76.8% | 76.8% | 64.0% | 0.66% |
| 3 | 10000 | 2000 | 2000 | 0.0 | 76.8% | 76.8% | 67.1% | 1.48% |
| 4 | 10000 | 2000 | 2000 | 0.0 | 85.0% | 85.0% | 77.8% | 0.41% |

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
| 0 | 10000 | 2000 | 2000 | 0.0 | 60.3% | 60.3% | 25.1% | 0.00% |
| 1 | 10000 | 2000 | 2000 | 0.05 | 60.0% | 60.0% | 25.7% | 0.00% |
| 2 | 10000 | 2000 | 2000 | 0.0 | 60.1% | 60.1% | 25.3% | 0.00% |
| 3 | 10000 | 2000 | 2000 | 0.0 | 60.6% | 60.6% | 25.3% | 0.00% |
| 4 | 10000 | 2000 | 2000 | 0.0 | 59.8% | 59.8% | 25.3% | 0.00% |

### `arm_b_finetune@c0.5-d0.0`

| fold | train n | val n | test n | margin | acc (raw) | acc (ruled) | macro-F1 | null->true |
|---|---|---|---|---|---|---|---|---|
| 0 | 10000 | 2000 | 2000 | 0.35 | 95.8% | 95.8% | 95.1% | 0.41% |
| 1 | 10000 | 2000 | 2000 | 0.0 | 87.9% | 87.9% | 84.7% | 1.16% |
| 2 | 10000 | 2000 | 2000 | 0.85 | 89.0% | 90.1% | 86.4% | 4.06% |
| 3 | 10000 | 2000 | 2000 | 0.9 | 93.9% | 94.0% | 91.7% | 2.39% |
| 4 | 10000 | 2000 | 2000 | 0.0 | 99.6% | 99.6% | 99.3% | 0.08% |

### `arm_b_finetune@c0.5-d0.3`

| fold | train n | val n | test n | margin | acc (raw) | acc (ruled) | macro-F1 | null->true |
|---|---|---|---|---|---|---|---|---|
| 0 | 10000 | 2000 | 2000 | 0.0 | 97.9% | 97.9% | 97.5% | 0.17% |
| 1 | 10000 | 2000 | 2000 | 0.0 | 96.5% | 96.5% | 95.6% | 1.50% |
| 2 | 10000 | 2000 | 2000 | 0.75 | 93.5% | 93.6% | 91.0% | 1.32% |
| 3 | 10000 | 2000 | 2000 | 0.55 | 94.5% | 94.4% | 93.0% | 1.07% |
| 4 | 10000 | 2000 | 2000 | 0.65 | 99.2% | 99.1% | 98.6% | 0.66% |

### `arm_b_finetune@c0.5-d0.6`

| fold | train n | val n | test n | margin | acc (raw) | acc (ruled) | macro-F1 | null->true |
|---|---|---|---|---|---|---|---|---|
| 0 | 10000 | 2000 | 2000 | 0.0 | 98.0% | 98.0% | 97.3% | 0.58% |
| 1 | 10000 | 2000 | 2000 | 0.3 | 97.5% | 97.5% | 96.9% | 1.33% |
| 2 | 10000 | 2000 | 2000 | 0.9 | 94.8% | 95.0% | 93.7% | 2.73% |
| 3 | 10000 | 2000 | 2000 | 0.85 | 96.6% | 96.6% | 96.1% | 0.91% |
| 4 | 10000 | 2000 | 2000 | 0.2 | 99.8% | 99.8% | 99.8% | 0.00% |

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

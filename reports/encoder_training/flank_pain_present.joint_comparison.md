# Encoder training: evaluation report

*Generated 2026-08-17T11:28:47+00:00.*

|  |  |
|---|---|
| signal | `flank_pain_present` |
| folds | `5` |
| generator version | `2` |
| generator base seed | `42` |
| generator seed rule | `base + 100 * fold + {train: 0, val: 1, test: 2}` |
| split salt | `0` |
| dataset dir | `data/synthetic/generated/folds` |
| ruleset | `data/uti1.json` |
| ruleset hash | `325b33068307bc70ca085b27117a90c2ad9e71fac24a80f77c8107d08049bb9f` |
| examples per fold | `train 10000, val 2000, test 2000` |
| shuffle seed | `7` |
| report | `three-arm joint comparison (A1 single-signal, A2 volume, A3 joint)` |
| joint signals | `dysuria_present, fever_present, flank_pain_present, haematuria_present, nocturia_present, urinary_frequency_present` |
| volume arm | `included` |
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
| trainable | `all layers unfrozen in every arm` |
| holdout | `data/realistic/uti1_holdout.labels.tsv -- 67 real submissions, scored after test, selects nothing` |
| negative control | `not run (--control is off)` |
| artefacts | `models/encoder` |
| model revision | `e2da8e2f811d1448a5b465c236feacd80ffbac7b` |
| revision pinned | `True` |
| tokeniser lowercases | `False` |
| tokeniser vocab size | `50265` |
| tokeniser discards casing | `False` |
| cluster tag coverage | `0 of 5 libraries carry cluster markers; 243 of 243 fragments are in libraries with none` |
| bootstrap | `2000 resamples over clusters, alpha=0.05, seed=0` |

**arms**

* **A1_single** (`data/synthetic/generated/folds`): 10000 examples per epoch, **10000** labelled positions for `flank_pain_present` -- this signal's own dataset, one head. **The paired arm**: A3's slice for this signal *is* these examples, so A1 vs A3 is scored example for example and McNemar applies.
* **A2_volume** (`data/synthetic/generated/folds-volume`): 44680 examples per epoch, **44680** labelled positions for `flank_pain_present` -- this signal's own clusters again, recombined roughly 4.5x as many times, one head. **Unpaired, by construction**: its test examples are different texts with their own ids, so it is read through the pooled cluster interval and the per-fold spread and never through McNemar. It is here to bound how much of any A1-to-A3 movement encoder gradient steps alone could explain, at unchanged effective n.
* **A3_joint** (`joint6`): 44680 examples per epoch, **10000** labelled positions for `flank_pain_present` -- the merged tree, every head sharing one encoder. This head's supervision is unchanged from A1 -- a dysuria example carries no fever key at all, which is a mask rather than a `null` assertion -- so the only mechanism by which this arm can move is representational.

**paired comparison**

A1_single vs A3_joint, paired on this signal's test examples. A2_volume pairs with nothing and its McNemar rows are recorded as skipped rather than omitted

**selected epochs**

{'A1_single': "3, 3, 1, 1, 3 (this head's own best epoch would have been 2, 2, 0, 0, 2)", 'A2_volume': "3, 2, 1, 3, 2 (this head's own best epoch would have been 2, 1, 0, 2, 1)", 'A3_joint': "3, 3, 2, 3, 1 (this head's own best epoch would have been 2, 2, 1, 0, 1)"}

**what no arm isolates**

**No arm is matched to A3 on both encoder gradient steps and per-head supervision, because no such dataset exists**: holding one fixed moves the other. A1 vs A3 varies cross-symptom exposure and step count together, and A2 bounds how much of any movement step count alone could explain -- but nothing here isolates cross-symptom exposure on its own. A further confound is DD6: A1 stops at the epoch that maximises this head's own validation macro-F1, A3 at the epoch that maximises the unweighted mean across every head, so where the two diverge (see `selected_epochs`) part of any movement is the stopping rule rather than the representation.

**predictions**

* **A1 -> A2 (4.5x recombinations, identical clusters): little or nothing, possibly slightly negative.** Effective n is unchanged; only surface forms multiply. A large gain here makes the interesting question "why did more views of the same ideas help", and the answer is more likely optimisation than data.
* **A1 -> A3 on fever: within +/-2-3 points, i.e. probably not detectable.** The fever head gets no new supervision, only a differently-shaped encoder, and the paired five-fold sensitivity is itself roughly 2-3 points.
* **A1 -> A3 on `nocturia_present` and `urinary_frequency_present`: the one place a large effect is plausible, in either direction.** They are the two weakest signals, TF-IDF is also worst on exactly those two, and the working hypothesis is that they are near-synonyms. Joint training is the first thing that forces one encoder to hold both apart, and mutual disambiguation and mutual interference are both live.
* **Holdout: expect a large drop from the recombination numbers.** Every `null` training example for a signal pairs an absence of that signal's language with *bland non-clinical* filler, so "clinical-sounding symptom language implies not null" is an available shortcut, and real submissions are dense with clinical language about other symptoms. **The joint run does not fix it** -- each head is masked on the other signals' examples -- which is what ticket 6's multi-symptom recombinations are for.

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
| `majority_class` | baseline | 7022 | **243** | 43.6% [37.3%, 50.3%] | 20.2% [18.1%, 22.3%] | 60.4% | 60.4% +/- 0.2% |
| `length_only` | baseline | 7022 | **243** | 43.6% [37.3%, 50.3%] | 20.2% [18.1%, 22.3%] | 60.4% | 60.4% +/- 0.2% |
| `tfidf_logreg` | baseline | 7022 | **243** | 72.8% [67.5%, 77.9%] | 70.8% [65.0%, 76.2%] | 80.8% | 80.8% +/- 1.9% |
| `length_only__shuffled` | negative control | 7022 | **243** | 43.6% [37.3%, 50.3%] | 20.2% [18.1%, 22.3%] | 60.4% | 60.4% +/- 0.2% |
| `tfidf_logreg__shuffled` | negative control | 7022 | **243** | 43.6% [37.3%, 50.3%] | 20.2% [18.1%, 22.3%] | 60.4% | 60.4% +/- 0.3% |
| `arm_b_finetune@A1_single` | finetune | 7022 | **243** | 96.0% [93.2%, 98.2%] | 95.9% [93.2%, 98.0%] | 97.2% | 97.2% +/- 2.1% |
| `arm_b_finetune@A2_volume` | finetune | 6953 | **243** | 95.5% [92.6%, 97.8%] | 95.2% [92.2%, 97.6%] | 96.9% | 96.9% +/- 2.3% |
| `arm_b_finetune@A3_joint` | finetune | 7022 | **243** | 97.8% [95.9%, 99.3%] | 97.5% [95.2%, 99.2%] | 98.3% | 98.3% +/- 2.2% |

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
| `tfidf_logreg` | -- | -- | 89.4% [82.5%, 95.1%] (eff n 53) | 89.1% [80.9%, 96.1%] (eff n 40) | -- | 96.0% [91.6%, 99.1%] (eff n 47) |
| `length_only__shuffled` | -- | -- | 100.0% [100.0%, 100.0%] (eff n 53) | 100.0% [100.0%, 100.0%] (eff n 40) | -- | 100.0% [100.0%, 100.0%] (eff n 47) |
| `tfidf_logreg__shuffled` | -- | -- | 99.9% [99.7%, 100.0%] (eff n 53) | 100.0% [100.0%, 100.0%] (eff n 40) | -- | 100.0% [100.0%, 100.0%] (eff n 47) |
| `arm_b_finetune@A1_single` | -- | -- | 93.4% [86.0%, 99.3%] (eff n 53) | 98.5% [95.4%, 100.0%] (eff n 40) | -- | 97.4% [92.8%, 100.0%] (eff n 47) |
| `arm_b_finetune@A2_volume` | -- | -- | 93.5% [87.2%, 98.7%] (eff n 53) | 96.6% [89.7%, 100.0%] (eff n 40) | -- | 99.7% [99.1%, 100.0%] (eff n 47) |
| `arm_b_finetune@A3_joint` | -- | -- | 97.5% [94.2%, 99.8%] (eff n 53) | 99.9% [99.6%, 100.0%] (eff n 40) | -- | 98.1% [95.8%, 99.8%] (eff n 47) |

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

### `arm_b_finetune@A1_single`

Recombination test slice: **n 7022**, **eff n 243** clusters, accuracy 96.0% [93.2%, 98.2%]. Holdout: **n 67** submissions, one observation each, scored by 5 fold models at margins 0.4, 0.9, 0.0, 0.85, 0.35. The two `n`s are printed together because they are not the same kind of number and the second is far the smaller.

| signal | true/false/null | omitted | decisive n | decisive acc (mean +/- sd) | worst-case half-width | all n | all acc (mean +/- sd) | null recall |
|---|---|---|---|---|---|---|---|---|
| `flank_pain_present` | 7/7/53 | 0 | 14 | 84.3% +/- 7.8% | +/-26.2% | 67 | 49.9% +/- 14.0% | 40.8% +/- 19.6% |

`null -> true` on real text, per fold: `flank_pain_present` 16, 23, 29, 41, 31 of 53. This is the cell that invents a symptom into a patient's pre-filled form, counted here on submissions rather than on recombinations.

### `arm_b_finetune@A2_volume`

Recombination test slice: **n 6953**, **eff n 243** clusters, accuracy 95.5% [92.6%, 97.8%]. Holdout: **n 67** submissions, one observation each, scored by 5 fold models at margins 0.0, 0.85, 0.0, 0.0, 0.15. The two `n`s are printed together because they are not the same kind of number and the second is far the smaller.

| signal | true/false/null | omitted | decisive n | decisive acc (mean +/- sd) | worst-case half-width | all n | all acc (mean +/- sd) | null recall |
|---|---|---|---|---|---|---|---|---|
| `flank_pain_present` | 7/7/53 | 0 | 14 | 81.4% +/- 6.4% | +/-26.2% | 67 | 56.4% +/- 12.5% | 49.8% +/- 17.1% |

`null -> true` on real text, per fold: `flank_pain_present` 10, 19, 35, 27, 22 of 53. This is the cell that invents a symptom into a patient's pre-filled form, counted here on submissions rather than on recombinations.

### `arm_b_finetune@A3_joint`

Recombination test slice: **n 7022**, **eff n 243** clusters, accuracy 97.8% [95.9%, 99.3%]. Holdout: **n 67** submissions, one observation each, scored by 5 fold models at margins {'dysuria_present': 0.55, 'fever_present': 0.0, 'flank_pain_present': 0.0, 'haematuria_present': 0.6, 'nocturia_present': 0.0, 'urinary_frequency_present': 0.0}, {'dysuria_present': 0.65, 'fever_present': 0.9, 'flank_pain_present': 0.0, 'haematuria_present': 0.55, 'nocturia_present': 0.0, 'urinary_frequency_present': 0.0}, {'dysuria_present': 0.9, 'fever_present': 0.9, 'flank_pain_present': 0.75, 'haematuria_present': 0.0, 'nocturia_present': 0.0, 'urinary_frequency_present': 0.0}, {'dysuria_present': 0.9, 'fever_present': 0.9, 'flank_pain_present': 0.75, 'haematuria_present': 0.0, 'nocturia_present': 0.9, 'urinary_frequency_present': 0.9}, {'dysuria_present': 0.8, 'fever_present': 0.0, 'flank_pain_present': 0.3, 'haematuria_present': 0.9, 'nocturia_present': 0.9, 'urinary_frequency_present': 0.9}. The two `n`s are printed together because they are not the same kind of number and the second is far the smaller.

| signal | true/false/null | omitted | decisive n | decisive acc (mean +/- sd) | worst-case half-width | all n | all acc (mean +/- sd) | null recall |
|---|---|---|---|---|---|---|---|---|
| `dysuria_present` | 56/0/11 | 0 | 56 | 83.9% +/- 2.2% | +/-13.1% | 67 | 73.4% +/- 2.2% | 20.0% +/- 4.1% |
| `fever_present` | 9/9/49 | 0 | 18 | 88.9% +/- 3.9% | +/-23.1% | 67 | 31.3% +/- 7.8% | 10.2% +/- 9.5% |
| `flank_pain_present` | 7/7/53 | 0 | 14 | 92.9% +/- 5.1% | +/-26.2% | 67 | 23.0% +/- 1.3% | 4.5% +/- 1.0% |
| `haematuria_present` | 9/2/56 | 0 | 11 | 100.0% +/- 0.0% | +/-29.5% | 67 | 21.2% +/- 2.5% | 5.7% +/- 2.9% |
| `nocturia_present` | 9/0/58 | 0 | 9 | 75.6% +/- 18.3% | +/-32.7% | 67 | 33.1% +/- 21.7% | 26.6% +/- 27.9% |
| `urinary_frequency_present` | 26/0/41 | 0 | 26 | 79.2% +/- 3.4% | +/-19.2% | 67 | 52.2% +/- 10.3% | 35.1% +/- 18.7% |

* `dysuria_present`: no `false` examples in this set, so its number is very nearly a recall-only measurement: nothing here tests whether an explicit denial is read correctly, which was the largest error family in the synthetic evaluation.
* `nocturia_present`: no `false` examples in this set, so its number is very nearly a recall-only measurement: nothing here tests whether an explicit denial is read correctly, which was the largest error family in the synthetic evaluation.
* `urinary_frequency_present`: no `false` examples in this set, so its number is very nearly a recall-only measurement: nothing here tests whether an explicit denial is read correctly, which was the largest error family in the synthetic evaluation.

`null -> true` on real text, per fold: `dysuria_present` 7, 8, 8, 7, 7 of 11; `fever_present` 44, 41, 41, 29, 47 of 49; `flank_pain_present` 47, 47, 48, 46, 49 of 53; `haematuria_present` 34, 44, 53, 43, 46 of 56; `nocturia_present` 44, 44, 51, 13, 15 of 58; `urinary_frequency_present` 15, 27, 28, 16, 10 of 41. This is the cell that invents a symptom into a patient's pre-filled form, counted here on submissions rather than on recombinations.

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
| `tfidf_logreg` | baseline | 3062 | **140** | 91.5% [87.5%, 94.9%] |
| `arm_b_finetune@A1_single` | finetune | 3062 | **140** | 96.2% [92.7%, 99.0%] |
| `arm_b_finetune@A2_volume` | finetune | 2959 | **140** | 96.5% [93.4%, 99.1%] |
| `arm_b_finetune@A3_joint` | finetune | 3062 | **140** | 98.4% [97.0%, 99.5%] |

### 2. The same comparison, paired

Two overlapping intervals do not settle whether one model beats another on the same
examples. McNemar does, over the examples the two disagree about -- read it alongside the
intervals above, never instead of them.

| pair | n | a only | b only | p |
|---|---|---|---|---|
| `majority_class` vs `length_only` | 3062 | 0 | 0 | 1 |
| `majority_class` vs `tfidf_logreg` | 3062 | 260 | 0 | 1.08e-78 |
| `majority_class` vs `arm_b_finetune@A1_single` | 3062 | 124 | 0 | 9.4e-38 |
| `majority_class` vs `arm_b_finetune@A3_joint` | 3062 | 53 | 0 | 2.22e-16 |
| `length_only` vs `tfidf_logreg` | 3062 | 260 | 0 | 1.08e-78 |
| `length_only` vs `arm_b_finetune@A1_single` | 3062 | 124 | 0 | 9.4e-38 |
| `length_only` vs `arm_b_finetune@A3_joint` | 3062 | 53 | 0 | 2.22e-16 |
| `tfidf_logreg` vs `arm_b_finetune@A1_single` | 3062 | 101 | 237 | 9.71e-14 |
| `tfidf_logreg` vs `arm_b_finetune@A3_joint` | 3062 | 42 | 249 | 5.83e-37 |
| `arm_b_finetune@A1_single` vs `arm_b_finetune@A3_joint` | 3062 | 35 | 106 | 1.69e-09 |

Not on this table, because they cannot be paired at all -- different examples on the two sides, so there is nothing for McNemar to pair: `majority_class` vs `arm_b_finetune@A2_volume`; `length_only` vs `arm_b_finetune@A2_volume`; `tfidf_logreg` vs `arm_b_finetune@A2_volume`; `arm_b_finetune@A1_single` vs `arm_b_finetune@A2_volume`; `arm_b_finetune@A2_volume` vs `arm_b_finetune@A3_joint`. Read those through the intervals above and the per-fold spread, and see "Pairs that could not be tested" below.

### 3. Where the errors fall

The per-fragment table below, as one number per model. Errors spread thinly across many
fragments say the method is too weak. Errors piled onto a handful say those specific ideas
are not learnable from the data we have -- and the table names them, which is what makes
this the most decision-useful thing in the report.

* `majority_class`: 3960 errors across 103 of 243 decisive fragments. Half of them fall on **37** fragments (an even spread would be 51.5); the worst ten carry 17.0% of all errors.
* `length_only`: 3960 errors across 103 of 243 decisive fragments. Half of them fall on **37** fragments (an even spread would be 51.5); the worst ten carry 17.0% of all errors.
* `tfidf_logreg`: 1913 errors across 119 of 243 decisive fragments. Half of them fall on **23** fragments (an even spread would be 59.5); the worst ten carry 26.6% of all errors.
* `arm_b_finetune@A1_single`: 280 errors across 22 of 243 decisive fragments. Half of them fall on **4** fragments (an even spread would be 11.0); the worst ten carry 89.6% of all errors.
* `arm_b_finetune@A2_volume`: 312 errors across 19 of 243 decisive fragments. Half of them fall on **4** fragments (an even spread would be 9.5); the worst ten carry 87.2% of all errors.
* `arm_b_finetune@A3_joint`: 151 errors across 17 of 243 decisive fragments. Half of them fall on **3** fragments (an even spread would be 8.5); the worst ten carry 94.7% of all errors.

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
* **test partition** -- checked. Across the 5 folds, 2131 distinct clusters are held out, each in exactly one fold, so pooling the folds counts every idea once. That figure spans every library in the manifest -- filler and other signals' libraries included -- not just this signal's; the per-slice `eff n` columns are the numbers that bound anything.
* **fold configuration** -- checked. The three splits of each fold agree on generator version, fold count, fold index and salt, and all folds agree on the salt.
* **arm datasets** -- checked at load. Every arm's tree was loaded before any training started, and the merged tree was asserted to declare every head this comparison trains (dysuria_present, fever_present, flank_pain_present, haematuria_present, nocturia_present, urinary_frequency_present). The checks above describe A1's tree, which is the one this report's test slice belongs to.

Shuffled-label controls, evaluated on the **unpermuted** test split. A large model will
memorise permuted training labels and drive train loss to zero; that is correct behaviour
and says nothing. Only the test score is the control.

| control | accuracy [95% CI] | macro-F1 [95% CI] |
|---|---|---|
| `length_only__shuffled` | 60.4% [39.0%, 76.9%] | 25.1% [18.7%, 29.0%] |
| `tfidf_logreg__shuffled` | 60.4% [39.0%, 76.9%] | 25.1% [18.7%, 29.0%] |

## Paired comparisons (McNemar, raw argmax)

Exact two-sided McNemar over the examples the two models disagree about. Pairing unit is the
example, not the cluster -- see the limitations.

| pair | slice | n | a only | b only | p |
|---|---|---|---|---|---|
| `majority_class` vs `length_only` | overall | 10000 | 0 | 0 | 1 |
| `majority_class` vs `length_only` | null_ambiguous | 3062 | 0 | 0 | 1 |
| `majority_class` vs `tfidf_logreg` | overall | 10000 | 264 | 2307 | 0 |
| `majority_class` vs `tfidf_logreg` | null_ambiguous | 3062 | 260 | 0 | 1.08e-78 |
| `majority_class` vs `arm_b_finetune@A1_single` | overall | 10000 | 125 | 3798 | 0 |
| `majority_class` vs `arm_b_finetune@A1_single` | null_ambiguous | 3062 | 124 | 0 | 9.4e-38 |
| `majority_class` vs `arm_b_finetune@A3_joint` | overall | 10000 | 80 | 3855 | 0 |
| `majority_class` vs `arm_b_finetune@A3_joint` | null_ambiguous | 3062 | 53 | 0 | 2.22e-16 |
| `length_only` vs `tfidf_logreg` | overall | 10000 | 264 | 2307 | 0 |
| `length_only` vs `tfidf_logreg` | null_ambiguous | 3062 | 260 | 0 | 1.08e-78 |
| `length_only` vs `arm_b_finetune@A1_single` | overall | 10000 | 125 | 3798 | 0 |
| `length_only` vs `arm_b_finetune@A1_single` | null_ambiguous | 3062 | 124 | 0 | 9.4e-38 |
| `length_only` vs `arm_b_finetune@A3_joint` | overall | 10000 | 80 | 3855 | 0 |
| `length_only` vs `arm_b_finetune@A3_joint` | null_ambiguous | 3062 | 53 | 0 | 2.22e-16 |
| `tfidf_logreg` vs `arm_b_finetune@A1_single` | overall | 10000 | 115 | 1745 | 0 |
| `tfidf_logreg` vs `arm_b_finetune@A1_single` | null_ambiguous | 3062 | 101 | 237 | 9.71e-14 |
| `tfidf_logreg` vs `arm_b_finetune@A3_joint` | overall | 10000 | 96 | 1828 | 0 |
| `tfidf_logreg` vs `arm_b_finetune@A3_joint` | null_ambiguous | 3062 | 42 | 249 | 5.83e-37 |
| `arm_b_finetune@A1_single` vs `arm_b_finetune@A3_joint` | overall | 10000 | 143 | 245 | 2.52e-07 |
| `arm_b_finetune@A1_single` vs `arm_b_finetune@A3_joint` | null_ambiguous | 3062 | 35 | 106 | 1.69e-09 |

### Pairs that could not be tested

McNemar pairs on the example id, so two models scored on **different examples** cannot be
compared this way at all -- there is nothing to pair. That is a property of the datasets,
not a result: read those runs through their pooled cluster intervals and their per-fold
spread, and do not read the absence of a row above as agreement between them.

| pair | slice | n (a) | n (b) | shared | reason |
|---|---|---|---|---|---|
| `majority_class` vs `arm_b_finetune@A2_volume` | overall | 10000 | 10000 | 0 | example sets differ: majority_class has 10000, arm_b_finetune@A2_volume has 10000, 0 in common |
| `majority_class` vs `arm_b_finetune@A2_volume` | null_ambiguous | 3062 | 2959 | 0 | example sets differ: majority_class has 3062, arm_b_finetune@A2_volume has 2959, 0 in common |
| `length_only` vs `arm_b_finetune@A2_volume` | overall | 10000 | 10000 | 0 | example sets differ: length_only has 10000, arm_b_finetune@A2_volume has 10000, 0 in common |
| `length_only` vs `arm_b_finetune@A2_volume` | null_ambiguous | 3062 | 2959 | 0 | example sets differ: length_only has 3062, arm_b_finetune@A2_volume has 2959, 0 in common |
| `tfidf_logreg` vs `arm_b_finetune@A2_volume` | overall | 10000 | 10000 | 0 | example sets differ: tfidf_logreg has 10000, arm_b_finetune@A2_volume has 10000, 0 in common |
| `tfidf_logreg` vs `arm_b_finetune@A2_volume` | null_ambiguous | 3062 | 2959 | 0 | example sets differ: tfidf_logreg has 3062, arm_b_finetune@A2_volume has 2959, 0 in common |
| `arm_b_finetune@A1_single` vs `arm_b_finetune@A2_volume` | overall | 10000 | 10000 | 0 | example sets differ: arm_b_finetune@A1_single has 10000, arm_b_finetune@A2_volume has 10000, 0 in common |
| `arm_b_finetune@A1_single` vs `arm_b_finetune@A2_volume` | null_ambiguous | 3062 | 2959 | 0 | example sets differ: arm_b_finetune@A1_single has 3062, arm_b_finetune@A2_volume has 2959, 0 in common |
| `arm_b_finetune@A2_volume` vs `arm_b_finetune@A3_joint` | overall | 10000 | 10000 | 0 | example sets differ: arm_b_finetune@A2_volume has 10000, arm_b_finetune@A3_joint has 10000, 0 in common |
| `arm_b_finetune@A2_volume` vs `arm_b_finetune@A3_joint` | null_ambiguous | 2959 | 3062 | 0 | example sets differ: arm_b_finetune@A2_volume has 2959, arm_b_finetune@A3_joint has 3062, 0 in common |

## What moved, and where

The headline is the least useful output of a model comparison. These two tables are the
useful one: a diffuse lift and a fix to one error family are different findings, and an
aggregate accuracy cannot tell them apart. `spread` is max minus min across the models --
a row where every encoder lands together is a row model choice does not touch.

### By library, accuracy after the decision rule

Worst-performing library first. For a single-class library -- `fever_false` holds only
`false` examples -- accuracy here *is* that class's recall on that library.

| library | n | `majority_class` | `length_only` | `tfidf_logreg` | `arm_b_finetune@A1_single` | `arm_b_finetune@A2_volume` | `arm_b_finetune@A3_joint` | spread |
|---|---|---|---|---|---|---|---|---|
| `flank_pain_false` | 2479 | 0.0% | 0.0% | 61.1% | 95.2% | 95.8% | 99.8% | 99.8pp |
| `flank_pain_true` | 1481 | 0.0% | 0.0% | 53.5% | 96.9% | 93.1% | 93.5% | 96.9pp |
| `flank_pain_null_historical` | 874 | 100.0% | 100.0% | 89.1% | 98.5% | 96.6% | 99.9% | 10.9pp |
| `flank_pain_null_hedged` | 1170 | 100.0% | 100.0% | 89.4% | 93.4% | 93.5% | 97.5% | 10.6pp |
| `flank_pain_null_thirdparty` | 1018 | 100.0% | 100.0% | 96.0% | 97.4% | 99.7% | 98.1% | 4.0pp |
| `(none)` | 2978 | 100.0% | 100.0% | 99.9% | 100.0% | 100.0% | 99.3% | 0.7pp |

### By fragment, errors

Ordered by the worst model's error count, so the fragments the comparison is about sort
to the top whichever encoder wins. Counts, not rates: these are the sentences a month of
library work would be spent on. The JSON holds every fragment.

| fragment | library | truth | `majority_class` | `length_only` | `tfidf_logreg` | `arm_b_finetune@A1_single` | `arm_b_finetune@A2_volume` | `arm_b_finetune@A3_joint` | spread |
|---|---|---|---|---|---|---|---|---|---|
| `flank_pain_false:4782be93` | `flank_pain_false` | false | 81 | 81 | 37 | 0 | 0 | 0 | 81 |
| `flank_pain_false:4d4ec138` | `flank_pain_false` | false | 78 | 78 | 78 | 0 | 0 | 0 | 78 |
| `flank_pain_false:7b34cfc0` | `flank_pain_false` | false | 75 | 75 | 14 | 0 | 0 | 0 | 75 |
| `flank_pain_false:80bb4b40` | `flank_pain_false` | false | 74 | 74 | 51 | 0 | 0 | 0 | 74 |
| `flank_pain_false:9b1cee9c` | `flank_pain_false` | false | 64 | 64 | 0 | 0 | 0 | 0 | 64 |
| `flank_pain_false:76bc0785` | `flank_pain_false` | false | 61 | 61 | 5 | 0 | 0 | 0 | 61 |
| `flank_pain_false:d439a7ee` | `flank_pain_false` | false | 61 | 61 | 3 | 0 | 0 | 0 | 61 |
| `flank_pain_false:42aa75a8` | `flank_pain_false` | false | 60 | 60 | 10 | 0 | 0 | 0 | 60 |
| `flank_pain_false:71da3a84` | `flank_pain_false` | false | 60 | 60 | 29 | 0 | 0 | 0 | 60 |
| `flank_pain_false:be00686d` | `flank_pain_false` | false | 60 | 60 | 0 | 0 | 0 | 0 | 60 |
| `flank_pain_false:a2c9e38d` | `flank_pain_false` | false | 58 | 58 | 56 | 0 | 0 | 0 | 58 |
| `flank_pain_true:faa371b2` | `flank_pain_true` | true | 55 | 55 | 11 | 0 | 0 | 0 | 55 |
| `flank_pain_false:6c762141` | `flank_pain_false` | false | 54 | 54 | 51 | 0 | 0 | 0 | 54 |
| `flank_pain_false:d7abb5ec` | `flank_pain_false` | false | 49 | 49 | 49 | 49 | 54 | 0 | 54 |
| `flank_pain_false:9ba1c8d3` | `flank_pain_false` | false | 52 | 52 | 3 | 0 | 0 | 0 | 52 |
| `flank_pain_false:ad38bb4f` | `flank_pain_false` | false | 52 | 52 | 5 | 0 | 0 | 0 | 52 |
| `flank_pain_false:bead93da` | `flank_pain_false` | false | 52 | 52 | 52 | 52 | 47 | 0 | 52 |
| `flank_pain_false:3273a39a` | `flank_pain_false` | false | 51 | 51 | 11 | 0 | 0 | 0 | 51 |
| `flank_pain_false:d37c1465` | `flank_pain_false` | false | 51 | 51 | 43 | 0 | 0 | 0 | 51 |
| `flank_pain_false:4947dcd5` | `flank_pain_false` | false | 50 | 50 | 40 | 0 | 0 | 0 | 50 |
| `flank_pain_false:924082ae` | `flank_pain_false` | false | 50 | 50 | 0 | 0 | 0 | 0 | 50 |
| `flank_pain_false:9ed5cbe0` | `flank_pain_false` | false | 50 | 50 | 0 | 0 | 0 | 0 | 50 |
| `flank_pain_false:37373d48` | `flank_pain_false` | false | 49 | 49 | 36 | 0 | 0 | 0 | 49 |
| `flank_pain_false:a31e1604` | `flank_pain_false` | false | 49 | 49 | 0 | 0 | 0 | 0 | 49 |
| `flank_pain_false:f900bfea` | `flank_pain_false` | false | 49 | 49 | 40 | 0 | 0 | 0 | 49 |
| `flank_pain_false:132f591d` | `flank_pain_false` | false | 48 | 48 | 29 | 0 | 0 | 0 | 48 |
| `flank_pain_false:6cd7f2f5` | `flank_pain_false` | false | 48 | 48 | 32 | 0 | 0 | 0 | 48 |
| `flank_pain_true:801b09f3` | `flank_pain_true` | true | 48 | 48 | 48 | 1 | 23 | 48 | 47 |
| `flank_pain_false:6f0b7381` | `flank_pain_false` | false | 47 | 47 | 0 | 0 | 0 | 0 | 47 |
| `flank_pain_false:f63b22a5` | `flank_pain_false` | false | 47 | 47 | 15 | 12 | 0 | 6 | 47 |
| `flank_pain_false:0d8df7a0` | `flank_pain_false` | false | 45 | 45 | 38 | 0 | 0 | 0 | 45 |
| `flank_pain_false:57d966db` | `flank_pain_false` | false | 44 | 44 | 0 | 0 | 0 | 0 | 44 |
| `flank_pain_true:78957d62` | `flank_pain_true` | true | 44 | 44 | 0 | 0 | 0 | 0 | 44 |
| `flank_pain_false:27c1ea49` | `flank_pain_false` | false | 43 | 43 | 0 | 0 | 0 | 0 | 43 |
| `flank_pain_false:7f0a359d` | `flank_pain_false` | false | 43 | 43 | 0 | 0 | 0 | 0 | 43 |
| `flank_pain_false:b4c43f30` | `flank_pain_false` | false | 43 | 43 | 0 | 0 | 0 | 0 | 43 |
| `flank_pain_false:b27cde7b` | `flank_pain_false` | false | 41 | 41 | 0 | 0 | 0 | 0 | 41 |
| `flank_pain_true:ec43ab8c` | `flank_pain_true` | true | 41 | 41 | 41 | 0 | 0 | 0 | 41 |
| `flank_pain_false:536a4cfe` | `flank_pain_false` | false | 40 | 40 | 9 | 0 | 0 | 0 | 40 |
| `flank_pain_false:69f1f2f7` | `flank_pain_false` | false | 40 | 40 | 21 | 0 | 0 | 0 | 40 |

*116 further fragments erred on at least one model; the JSON holds them all.*

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
| hedged | 1170 | **53** | 100.0% [100.0%, 100.0%] |
| historical | 874 | **40** | 100.0% [100.0%, 100.0%] |
| third_party | 1018 | **47** | 100.0% [100.0%, 100.0%] |

### By fragment library

| library | n | eff n | accuracy [95% CI] |
|---|---|---|---|
| flank_pain_false | 2479 | **55** | 0.0% [0.0%, 0.0%] |
| flank_pain_null_hedged | 1170 | **53** | 100.0% [100.0%, 100.0%] |
| flank_pain_null_historical | 874 | **40** | 100.0% [100.0%, 100.0%] |
| flank_pain_null_thirdparty | 1018 | **47** | 100.0% [100.0%, 100.0%] |
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
| `flank_pain_false:4d4ec138` | `flank_pain_false` | -- | false | 0/78 | 0.0% | null 78 |
| `flank_pain_false:7b34cfc0` | `flank_pain_false` | -- | false | 0/75 | 0.0% | null 75 |
| `flank_pain_false:80bb4b40` | `flank_pain_false` | -- | false | 0/74 | 0.0% | null 74 |
| `flank_pain_false:9b1cee9c` | `flank_pain_false` | -- | false | 0/64 | 0.0% | null 64 |
| `flank_pain_false:76bc0785` | `flank_pain_false` | -- | false | 0/61 | 0.0% | null 61 |
| `flank_pain_false:d439a7ee` | `flank_pain_false` | -- | false | 0/61 | 0.0% | null 61 |
| `flank_pain_false:42aa75a8` | `flank_pain_false` | -- | false | 0/60 | 0.0% | null 60 |
| `flank_pain_false:71da3a84` | `flank_pain_false` | -- | false | 0/60 | 0.0% | null 60 |
| `flank_pain_false:be00686d` | `flank_pain_false` | -- | false | 0/60 | 0.0% | null 60 |
| `flank_pain_false:a2c9e38d` | `flank_pain_false` | -- | false | 0/58 | 0.0% | null 58 |
| `flank_pain_true:faa371b2` | `flank_pain_true` | -- | true | 0/55 | 0.0% | null 55 |
| `flank_pain_false:6c762141` | `flank_pain_false` | -- | false | 0/54 | 0.0% | null 54 |
| `flank_pain_false:9ba1c8d3` | `flank_pain_false` | -- | false | 0/52 | 0.0% | null 52 |
| `flank_pain_false:ad38bb4f` | `flank_pain_false` | -- | false | 0/52 | 0.0% | null 52 |
| `flank_pain_false:bead93da` | `flank_pain_false` | -- | false | 0/52 | 0.0% | null 52 |
| `flank_pain_false:3273a39a` | `flank_pain_false` | -- | false | 0/51 | 0.0% | null 51 |
| `flank_pain_false:d37c1465` | `flank_pain_false` | -- | false | 0/51 | 0.0% | null 51 |
| `flank_pain_false:4947dcd5` | `flank_pain_false` | -- | false | 0/50 | 0.0% | null 50 |
| `flank_pain_false:924082ae` | `flank_pain_false` | -- | false | 0/50 | 0.0% | null 50 |
| `flank_pain_false:9ed5cbe0` | `flank_pain_false` | -- | false | 0/50 | 0.0% | null 50 |
| `flank_pain_false:37373d48` | `flank_pain_false` | -- | false | 0/49 | 0.0% | null 49 |
| `flank_pain_false:a31e1604` | `flank_pain_false` | -- | false | 0/49 | 0.0% | null 49 |
| `flank_pain_false:d7abb5ec` | `flank_pain_false` | -- | false | 0/49 | 0.0% | null 49 |
| `flank_pain_false:f900bfea` | `flank_pain_false` | -- | false | 0/49 | 0.0% | null 49 |
| `flank_pain_false:132f591d` | `flank_pain_false` | -- | false | 0/48 | 0.0% | null 48 |
| `flank_pain_false:6cd7f2f5` | `flank_pain_false` | -- | false | 0/48 | 0.0% | null 48 |
| `flank_pain_true:801b09f3` | `flank_pain_true` | -- | true | 0/48 | 0.0% | null 48 |
| `flank_pain_false:6f0b7381` | `flank_pain_false` | -- | false | 0/47 | 0.0% | null 47 |
| `flank_pain_false:f63b22a5` | `flank_pain_false` | -- | false | 0/47 | 0.0% | null 47 |
| `flank_pain_false:0d8df7a0` | `flank_pain_false` | -- | false | 0/45 | 0.0% | null 45 |
| `flank_pain_false:57d966db` | `flank_pain_false` | -- | false | 0/44 | 0.0% | null 44 |
| `flank_pain_true:78957d62` | `flank_pain_true` | -- | true | 0/44 | 0.0% | null 44 |
| `flank_pain_false:27c1ea49` | `flank_pain_false` | -- | false | 0/43 | 0.0% | null 43 |
| `flank_pain_false:7f0a359d` | `flank_pain_false` | -- | false | 0/43 | 0.0% | null 43 |
| `flank_pain_false:b4c43f30` | `flank_pain_false` | -- | false | 0/43 | 0.0% | null 43 |
| `flank_pain_false:b27cde7b` | `flank_pain_false` | -- | false | 0/41 | 0.0% | null 41 |
| `flank_pain_true:ec43ab8c` | `flank_pain_true` | -- | true | 0/41 | 0.0% | null 41 |
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
| hedged | 1170 | **53** | 100.0% [100.0%, 100.0%] |
| historical | 874 | **40** | 100.0% [100.0%, 100.0%] |
| third_party | 1018 | **47** | 100.0% [100.0%, 100.0%] |

### By fragment library

| library | n | eff n | accuracy [95% CI] |
|---|---|---|---|
| flank_pain_false | 2479 | **55** | 0.0% [0.0%, 0.0%] |
| flank_pain_null_hedged | 1170 | **53** | 100.0% [100.0%, 100.0%] |
| flank_pain_null_historical | 874 | **40** | 100.0% [100.0%, 100.0%] |
| flank_pain_null_thirdparty | 1018 | **47** | 100.0% [100.0%, 100.0%] |
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
| `flank_pain_false:4d4ec138` | `flank_pain_false` | -- | false | 0/78 | 0.0% | null 78 |
| `flank_pain_false:7b34cfc0` | `flank_pain_false` | -- | false | 0/75 | 0.0% | null 75 |
| `flank_pain_false:80bb4b40` | `flank_pain_false` | -- | false | 0/74 | 0.0% | null 74 |
| `flank_pain_false:9b1cee9c` | `flank_pain_false` | -- | false | 0/64 | 0.0% | null 64 |
| `flank_pain_false:76bc0785` | `flank_pain_false` | -- | false | 0/61 | 0.0% | null 61 |
| `flank_pain_false:d439a7ee` | `flank_pain_false` | -- | false | 0/61 | 0.0% | null 61 |
| `flank_pain_false:42aa75a8` | `flank_pain_false` | -- | false | 0/60 | 0.0% | null 60 |
| `flank_pain_false:71da3a84` | `flank_pain_false` | -- | false | 0/60 | 0.0% | null 60 |
| `flank_pain_false:be00686d` | `flank_pain_false` | -- | false | 0/60 | 0.0% | null 60 |
| `flank_pain_false:a2c9e38d` | `flank_pain_false` | -- | false | 0/58 | 0.0% | null 58 |
| `flank_pain_true:faa371b2` | `flank_pain_true` | -- | true | 0/55 | 0.0% | null 55 |
| `flank_pain_false:6c762141` | `flank_pain_false` | -- | false | 0/54 | 0.0% | null 54 |
| `flank_pain_false:9ba1c8d3` | `flank_pain_false` | -- | false | 0/52 | 0.0% | null 52 |
| `flank_pain_false:ad38bb4f` | `flank_pain_false` | -- | false | 0/52 | 0.0% | null 52 |
| `flank_pain_false:bead93da` | `flank_pain_false` | -- | false | 0/52 | 0.0% | null 52 |
| `flank_pain_false:3273a39a` | `flank_pain_false` | -- | false | 0/51 | 0.0% | null 51 |
| `flank_pain_false:d37c1465` | `flank_pain_false` | -- | false | 0/51 | 0.0% | null 51 |
| `flank_pain_false:4947dcd5` | `flank_pain_false` | -- | false | 0/50 | 0.0% | null 50 |
| `flank_pain_false:924082ae` | `flank_pain_false` | -- | false | 0/50 | 0.0% | null 50 |
| `flank_pain_false:9ed5cbe0` | `flank_pain_false` | -- | false | 0/50 | 0.0% | null 50 |
| `flank_pain_false:37373d48` | `flank_pain_false` | -- | false | 0/49 | 0.0% | null 49 |
| `flank_pain_false:a31e1604` | `flank_pain_false` | -- | false | 0/49 | 0.0% | null 49 |
| `flank_pain_false:d7abb5ec` | `flank_pain_false` | -- | false | 0/49 | 0.0% | null 49 |
| `flank_pain_false:f900bfea` | `flank_pain_false` | -- | false | 0/49 | 0.0% | null 49 |
| `flank_pain_false:132f591d` | `flank_pain_false` | -- | false | 0/48 | 0.0% | null 48 |
| `flank_pain_false:6cd7f2f5` | `flank_pain_false` | -- | false | 0/48 | 0.0% | null 48 |
| `flank_pain_true:801b09f3` | `flank_pain_true` | -- | true | 0/48 | 0.0% | null 48 |
| `flank_pain_false:6f0b7381` | `flank_pain_false` | -- | false | 0/47 | 0.0% | null 47 |
| `flank_pain_false:f63b22a5` | `flank_pain_false` | -- | false | 0/47 | 0.0% | null 47 |
| `flank_pain_false:0d8df7a0` | `flank_pain_false` | -- | false | 0/45 | 0.0% | null 45 |
| `flank_pain_false:57d966db` | `flank_pain_false` | -- | false | 0/44 | 0.0% | null 44 |
| `flank_pain_true:78957d62` | `flank_pain_true` | -- | true | 0/44 | 0.0% | null 44 |
| `flank_pain_false:27c1ea49` | `flank_pain_false` | -- | false | 0/43 | 0.0% | null 43 |
| `flank_pain_false:7f0a359d` | `flank_pain_false` | -- | false | 0/43 | 0.0% | null 43 |
| `flank_pain_false:b4c43f30` | `flank_pain_false` | -- | false | 0/43 | 0.0% | null 43 |
| `flank_pain_false:b27cde7b` | `flank_pain_false` | -- | false | 0/41 | 0.0% | null 41 |
| `flank_pain_true:ec43ab8c` | `flank_pain_true` | -- | true | 0/41 | 0.0% | null 41 |
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
| **truth false** | 1515 | 47 | 917 | 2479 |
| **truth true** | 82 | 792 | 607 | 1481 |
| **truth null** | 114 | 150 | 5776 | 6040 |
| **total** | 1711 | 989 | 7300 | 10000 |

`null -> true`: 150 of 6040 truly-null examples (2.48%).

*Confusion matrix, after the decision rule*

|  | pred false | pred true | pred null | total |
|---|---|---|---|---|
| **truth false** | 1515 | 47 | 917 | 2479 |
| **truth true** | 82 | 792 | 607 | 1481 |
| **truth null** | 114 | 150 | 5776 | 6040 |
| **total** | 1711 | 989 | 7300 | 10000 |

`null -> true`: 150 of 6040 truly-null examples (2.48%).

### Per class, after the decision rule

| class | support | predicted | precision | recall | F1 |
|---|---|---|---|---|---|
| `false` | 2479 | 1711 | 88.5% | 61.1% | 72.3% |
| `true` | 1481 | 989 | 80.1% | 53.5% | 64.1% |
| `null` | 6040 | 7300 | 79.1% | 95.6% | 86.6% |

### By label mode

| label mode | n | eff n | accuracy [95% CI] |
|---|---|---|---|
| false | 2479 | **55** | 61.1% [50.6%, 71.5%] |
| null_ambiguous | 3062 | **140** | 91.5% [87.5%, 94.9%] |
| null_structural | 2978 | **1** | 99.9% [99.9%, 99.9%] |
| true | 1481 | **48** | 53.5% [42.2%, 65.2%] |

### By null sub-class

| sub-class | n | eff n | null recall [95% CI] |
|---|---|---|---|
| hedged | 1170 | **53** | 89.4% [82.5%, 95.1%] |
| historical | 874 | **40** | 89.1% [80.9%, 96.1%] |
| third_party | 1018 | **47** | 96.0% [91.6%, 99.1%] |

### By fragment library

| library | n | eff n | accuracy [95% CI] |
|---|---|---|---|
| flank_pain_false | 2479 | **55** | 61.1% [50.6%, 71.5%] |
| flank_pain_null_hedged | 1170 | **53** | 89.4% [82.5%, 95.1%] |
| flank_pain_null_historical | 874 | **40** | 89.1% [80.9%, 96.1%] |
| flank_pain_null_thirdparty | 1018 | **47** | 96.0% [91.6%, 99.1%] |
| flank_pain_true | 1481 | **48** | 53.5% [42.2%, 65.2%] |
| (none) | 2978 | **1** | 99.9% [99.9%, 99.9%] |

### Per-fragment errors (worst first)

Whether errors are spread thinly across many fragments or piled onto a few is the difference
between "the method is too weak" (model work) and "these specific ideas are not learnable from
the data we have" (library work, and these are the fragments to write more of). No intervals:
a fragment is one cluster, so an interval over its own examples measures nothing.

119 of 243 decisive fragments were got wrong at least once.

`tfidf_logreg`: 1913 errors across 119 of 243 decisive fragments. Half of them fall on **23** fragments (an even spread would be 59.5); the worst ten carry 26.6% of all errors.

| fragment | library | sub-class | truth | correct | accuracy | predicted as |
|---|---|---|---|---|---|---|
| `flank_pain_false:4d4ec138` | `flank_pain_false` | -- | false | 0/78 | 0.0% | null 78 |
| `flank_pain_false:bead93da` | `flank_pain_false` | -- | false | 0/52 | 0.0% | null 52 |
| `flank_pain_false:d7abb5ec` | `flank_pain_false` | -- | false | 0/49 | 0.0% | null 49 |
| `flank_pain_true:801b09f3` | `flank_pain_true` | -- | true | 0/48 | 0.0% | null 48 |
| `flank_pain_true:ec43ab8c` | `flank_pain_true` | -- | true | 0/41 | 0.0% | false 18, null 23 |
| `flank_pain_true:568725bb` | `flank_pain_true` | -- | true | 0/39 | 0.0% | null 39 |
| `flank_pain_true:47597ae1` | `flank_pain_true` | -- | true | 0/38 | 0.0% | null 38 |
| `flank_pain_true:a326ab18` | `flank_pain_true` | -- | true | 0/35 | 0.0% | false 4, null 31 |
| `flank_pain_false:a7c193e8` | `flank_pain_false` | -- | false | 0/31 | 0.0% | null 31 |
| `flank_pain_false:b927c3ee` | `flank_pain_false` | -- | false | 0/29 | 0.0% | null 29 |
| `flank_pain_true:720637db` | `flank_pain_true` | -- | true | 0/29 | 0.0% | null 29 |
| `flank_pain_false:cbb11cce` | `flank_pain_false` | -- | false | 0/27 | 0.0% | null 27 |
| `flank_pain_false:1777a47f` | `flank_pain_false` | -- | false | 0/25 | 0.0% | null 25 |
| `flank_pain_true:57ae6815` | `flank_pain_true` | -- | true | 0/22 | 0.0% | null 22 |
| `flank_pain_true:be1f0c8f` | `flank_pain_true` | -- | true | 0/21 | 0.0% | false 1, null 20 |
| `flank_pain_null_historical:c9da7977` | `flank_pain_null_historical` | historical | null | 0/19 | 0.0% | true 19 |
| `flank_pain_true:cb7fde42` | `flank_pain_true` | -- | true | 0/19 | 0.0% | false 13, null 6 |
| `flank_pain_false:a2c9e38d` | `flank_pain_false` | -- | false | 2/58 | 3.4% | false 2, null 56 |
| `flank_pain_false:6c762141` | `flank_pain_false` | -- | false | 3/54 | 5.6% | false 3, null 51 |
| `flank_pain_null_hedged:a6bdac0f` | `flank_pain_null_hedged` | hedged | null | 1/18 | 5.6% | true 17, null 1 |
| `flank_pain_true:1dca9abd` | `flank_pain_true` | -- | true | 2/33 | 6.1% | false 6, true 2, null 25 |
| `flank_pain_true:f0d12a02` | `flank_pain_true` | -- | true | 2/31 | 6.5% | false 1, true 2, null 28 |
| `flank_pain_true:d7d705f6` | `flank_pain_true` | -- | true | 3/36 | 8.3% | false 28, true 3, null 5 |
| `flank_pain_null_hedged:2a3b1726` | `flank_pain_null_hedged` | hedged | null | 3/28 | 10.7% | true 25, null 3 |
| `flank_pain_false:0468979b` | `flank_pain_false` | -- | false | 4/36 | 11.1% | false 4, null 32 |
| `flank_pain_null_hedged:d17ed4ab` | `flank_pain_null_hedged` | hedged | null | 2/18 | 11.1% | false 16, null 2 |
| `flank_pain_null_historical:68d1f572` | `flank_pain_null_historical` | historical | null | 3/26 | 11.5% | true 23, null 3 |
| `flank_pain_true:990ffc20` | `flank_pain_true` | -- | true | 4/33 | 12.1% | true 4, null 29 |
| `flank_pain_false:0d8df7a0` | `flank_pain_false` | -- | false | 7/45 | 15.6% | false 7, null 38 |
| `flank_pain_false:d37c1465` | `flank_pain_false` | -- | false | 8/51 | 15.7% | false 8, true 22, null 21 |
| `flank_pain_false:f900bfea` | `flank_pain_false` | -- | false | 9/49 | 18.4% | false 9, null 40 |
| `flank_pain_false:4947dcd5` | `flank_pain_false` | -- | false | 10/50 | 20.0% | false 10, true 1, null 39 |
| `flank_pain_true:0d9a9389` | `flank_pain_true` | -- | true | 7/35 | 20.0% | false 1, true 7, null 27 |
| `flank_pain_true:79cde749` | `flank_pain_true` | -- | true | 4/20 | 20.0% | true 4, null 16 |
| `flank_pain_null_thirdparty:d93c1422` | `flank_pain_null_thirdparty` | third_party | null | 5/23 | 21.7% | false 18, null 5 |
| `flank_pain_null_historical:47fc69d5` | `flank_pain_null_historical` | historical | null | 6/26 | 23.1% | true 20, null 6 |
| `flank_pain_true:b2b80fa1` | `flank_pain_true` | -- | true | 7/30 | 23.3% | true 7, null 23 |
| `flank_pain_false:37373d48` | `flank_pain_false` | -- | false | 13/49 | 26.5% | false 13, null 36 |
| `flank_pain_true:c7bed32e` | `flank_pain_true` | -- | true | 5/17 | 29.4% | false 2, true 5, null 10 |
| `flank_pain_true:59cc66fa` | `flank_pain_true` | -- | true | 6/20 | 30.0% | true 6, null 14 |

*79 further fragments with at least one error are in the JSON sidecar; every fragment is there regardless of score.*

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
| hedged | 1170 | **53** | 100.0% [100.0%, 100.0%] |
| historical | 874 | **40** | 100.0% [100.0%, 100.0%] |
| third_party | 1018 | **47** | 100.0% [100.0%, 100.0%] |

### By fragment library

| library | n | eff n | accuracy [95% CI] |
|---|---|---|---|
| flank_pain_false | 2479 | **55** | 0.0% [0.0%, 0.0%] |
| flank_pain_null_hedged | 1170 | **53** | 100.0% [100.0%, 100.0%] |
| flank_pain_null_historical | 874 | **40** | 100.0% [100.0%, 100.0%] |
| flank_pain_null_thirdparty | 1018 | **47** | 100.0% [100.0%, 100.0%] |
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
| `flank_pain_false:4d4ec138` | `flank_pain_false` | -- | false | 0/78 | 0.0% | null 78 |
| `flank_pain_false:7b34cfc0` | `flank_pain_false` | -- | false | 0/75 | 0.0% | null 75 |
| `flank_pain_false:80bb4b40` | `flank_pain_false` | -- | false | 0/74 | 0.0% | null 74 |
| `flank_pain_false:9b1cee9c` | `flank_pain_false` | -- | false | 0/64 | 0.0% | null 64 |
| `flank_pain_false:76bc0785` | `flank_pain_false` | -- | false | 0/61 | 0.0% | null 61 |
| `flank_pain_false:d439a7ee` | `flank_pain_false` | -- | false | 0/61 | 0.0% | null 61 |
| `flank_pain_false:42aa75a8` | `flank_pain_false` | -- | false | 0/60 | 0.0% | null 60 |
| `flank_pain_false:71da3a84` | `flank_pain_false` | -- | false | 0/60 | 0.0% | null 60 |
| `flank_pain_false:be00686d` | `flank_pain_false` | -- | false | 0/60 | 0.0% | null 60 |
| `flank_pain_false:a2c9e38d` | `flank_pain_false` | -- | false | 0/58 | 0.0% | null 58 |
| `flank_pain_true:faa371b2` | `flank_pain_true` | -- | true | 0/55 | 0.0% | null 55 |
| `flank_pain_false:6c762141` | `flank_pain_false` | -- | false | 0/54 | 0.0% | null 54 |
| `flank_pain_false:9ba1c8d3` | `flank_pain_false` | -- | false | 0/52 | 0.0% | null 52 |
| `flank_pain_false:ad38bb4f` | `flank_pain_false` | -- | false | 0/52 | 0.0% | null 52 |
| `flank_pain_false:bead93da` | `flank_pain_false` | -- | false | 0/52 | 0.0% | null 52 |
| `flank_pain_false:3273a39a` | `flank_pain_false` | -- | false | 0/51 | 0.0% | null 51 |
| `flank_pain_false:d37c1465` | `flank_pain_false` | -- | false | 0/51 | 0.0% | null 51 |
| `flank_pain_false:4947dcd5` | `flank_pain_false` | -- | false | 0/50 | 0.0% | null 50 |
| `flank_pain_false:924082ae` | `flank_pain_false` | -- | false | 0/50 | 0.0% | null 50 |
| `flank_pain_false:9ed5cbe0` | `flank_pain_false` | -- | false | 0/50 | 0.0% | null 50 |
| `flank_pain_false:37373d48` | `flank_pain_false` | -- | false | 0/49 | 0.0% | null 49 |
| `flank_pain_false:a31e1604` | `flank_pain_false` | -- | false | 0/49 | 0.0% | null 49 |
| `flank_pain_false:d7abb5ec` | `flank_pain_false` | -- | false | 0/49 | 0.0% | null 49 |
| `flank_pain_false:f900bfea` | `flank_pain_false` | -- | false | 0/49 | 0.0% | null 49 |
| `flank_pain_false:132f591d` | `flank_pain_false` | -- | false | 0/48 | 0.0% | null 48 |
| `flank_pain_false:6cd7f2f5` | `flank_pain_false` | -- | false | 0/48 | 0.0% | null 48 |
| `flank_pain_true:801b09f3` | `flank_pain_true` | -- | true | 0/48 | 0.0% | null 48 |
| `flank_pain_false:6f0b7381` | `flank_pain_false` | -- | false | 0/47 | 0.0% | null 47 |
| `flank_pain_false:f63b22a5` | `flank_pain_false` | -- | false | 0/47 | 0.0% | null 47 |
| `flank_pain_false:0d8df7a0` | `flank_pain_false` | -- | false | 0/45 | 0.0% | null 45 |
| `flank_pain_false:57d966db` | `flank_pain_false` | -- | false | 0/44 | 0.0% | null 44 |
| `flank_pain_true:78957d62` | `flank_pain_true` | -- | true | 0/44 | 0.0% | null 44 |
| `flank_pain_false:27c1ea49` | `flank_pain_false` | -- | false | 0/43 | 0.0% | null 43 |
| `flank_pain_false:7f0a359d` | `flank_pain_false` | -- | false | 0/43 | 0.0% | null 43 |
| `flank_pain_false:b4c43f30` | `flank_pain_false` | -- | false | 0/43 | 0.0% | null 43 |
| `flank_pain_false:b27cde7b` | `flank_pain_false` | -- | false | 0/41 | 0.0% | null 41 |
| `flank_pain_true:ec43ab8c` | `flank_pain_true` | -- | true | 0/41 | 0.0% | null 41 |
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
| hedged | 1170 | **53** | 99.9% [99.7%, 100.0%] |
| historical | 874 | **40** | 100.0% [100.0%, 100.0%] |
| third_party | 1018 | **47** | 100.0% [100.0%, 100.0%] |

### By fragment library

| library | n | eff n | accuracy [95% CI] |
|---|---|---|---|
| flank_pain_false | 2479 | **55** | 0.0% [0.0%, 0.0%] |
| flank_pain_null_hedged | 1170 | **53** | 99.9% [99.7%, 100.0%] |
| flank_pain_null_historical | 874 | **40** | 100.0% [100.0%, 100.0%] |
| flank_pain_null_thirdparty | 1018 | **47** | 100.0% [100.0%, 100.0%] |
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
| `flank_pain_false:4d4ec138` | `flank_pain_false` | -- | false | 0/78 | 0.0% | null 78 |
| `flank_pain_false:7b34cfc0` | `flank_pain_false` | -- | false | 0/75 | 0.0% | null 75 |
| `flank_pain_false:80bb4b40` | `flank_pain_false` | -- | false | 0/74 | 0.0% | null 74 |
| `flank_pain_false:9b1cee9c` | `flank_pain_false` | -- | false | 0/64 | 0.0% | null 64 |
| `flank_pain_false:76bc0785` | `flank_pain_false` | -- | false | 0/61 | 0.0% | null 61 |
| `flank_pain_false:d439a7ee` | `flank_pain_false` | -- | false | 0/61 | 0.0% | null 61 |
| `flank_pain_false:42aa75a8` | `flank_pain_false` | -- | false | 0/60 | 0.0% | null 60 |
| `flank_pain_false:71da3a84` | `flank_pain_false` | -- | false | 0/60 | 0.0% | null 60 |
| `flank_pain_false:be00686d` | `flank_pain_false` | -- | false | 0/60 | 0.0% | null 60 |
| `flank_pain_false:a2c9e38d` | `flank_pain_false` | -- | false | 0/58 | 0.0% | null 58 |
| `flank_pain_true:faa371b2` | `flank_pain_true` | -- | true | 0/55 | 0.0% | null 55 |
| `flank_pain_false:6c762141` | `flank_pain_false` | -- | false | 0/54 | 0.0% | null 54 |
| `flank_pain_false:9ba1c8d3` | `flank_pain_false` | -- | false | 0/52 | 0.0% | null 52 |
| `flank_pain_false:ad38bb4f` | `flank_pain_false` | -- | false | 0/52 | 0.0% | null 52 |
| `flank_pain_false:bead93da` | `flank_pain_false` | -- | false | 0/52 | 0.0% | null 52 |
| `flank_pain_false:3273a39a` | `flank_pain_false` | -- | false | 0/51 | 0.0% | null 51 |
| `flank_pain_false:d37c1465` | `flank_pain_false` | -- | false | 0/51 | 0.0% | null 51 |
| `flank_pain_false:4947dcd5` | `flank_pain_false` | -- | false | 0/50 | 0.0% | null 50 |
| `flank_pain_false:924082ae` | `flank_pain_false` | -- | false | 0/50 | 0.0% | null 50 |
| `flank_pain_false:9ed5cbe0` | `flank_pain_false` | -- | false | 0/50 | 0.0% | null 50 |
| `flank_pain_false:37373d48` | `flank_pain_false` | -- | false | 0/49 | 0.0% | null 49 |
| `flank_pain_false:a31e1604` | `flank_pain_false` | -- | false | 0/49 | 0.0% | null 49 |
| `flank_pain_false:d7abb5ec` | `flank_pain_false` | -- | false | 0/49 | 0.0% | null 49 |
| `flank_pain_false:f900bfea` | `flank_pain_false` | -- | false | 0/49 | 0.0% | null 49 |
| `flank_pain_false:132f591d` | `flank_pain_false` | -- | false | 0/48 | 0.0% | null 48 |
| `flank_pain_false:6cd7f2f5` | `flank_pain_false` | -- | false | 0/48 | 0.0% | null 48 |
| `flank_pain_true:801b09f3` | `flank_pain_true` | -- | true | 0/48 | 0.0% | null 48 |
| `flank_pain_false:6f0b7381` | `flank_pain_false` | -- | false | 0/47 | 0.0% | null 47 |
| `flank_pain_false:f63b22a5` | `flank_pain_false` | -- | false | 0/47 | 0.0% | null 47 |
| `flank_pain_false:0d8df7a0` | `flank_pain_false` | -- | false | 0/45 | 0.0% | null 45 |
| `flank_pain_false:57d966db` | `flank_pain_false` | -- | false | 0/44 | 0.0% | null 44 |
| `flank_pain_true:78957d62` | `flank_pain_true` | -- | true | 0/44 | 0.0% | null 44 |
| `flank_pain_false:27c1ea49` | `flank_pain_false` | -- | false | 0/43 | 0.0% | null 43 |
| `flank_pain_false:7f0a359d` | `flank_pain_false` | -- | false | 0/43 | 0.0% | null 43 |
| `flank_pain_false:b4c43f30` | `flank_pain_false` | -- | false | 0/43 | 0.0% | null 43 |
| `flank_pain_false:b27cde7b` | `flank_pain_false` | -- | false | 0/41 | 0.0% | null 41 |
| `flank_pain_true:ec43ab8c` | `flank_pain_true` | -- | true | 0/41 | 0.0% | null 41 |
| `flank_pain_false:536a4cfe` | `flank_pain_false` | -- | false | 0/40 | 0.0% | null 40 |
| `flank_pain_false:69f1f2f7` | `flank_pain_false` | -- | false | 0/40 | 0.0% | null 40 |

*64 further fragments with at least one error are in the JSON sidecar; every fragment is there regardless of score.*

## `arm_b_finetune@A1_single`

`roberta-base` with **every layer unfrozen**, mean-pooled, with the same `Linear(768, 3)` head -- 110M trainable parameters against Arm A's 2,307. Three epochs at batch 32, learning rate 2e-5, 10% linear warmup, AdamW, fp32. No gradient checkpointing, no 8-bit optimiser, no LoRA, no gradient accumulation: the full model fits in 12GB with room to spare, so anything that reads like a compute compromise would be a mistake rather than a saving. This is the arm that separates "the fragment libraries are the bottleneck" from "the method is too weak": if a fully fine-tuned encoder still cannot read third-party attribution, tense or metaphor, the limit is in the ideas the libraries contain and the fix is library work, not model work.

Decision-rule margins selected per fold (on each fold's own validation split): 0.0, 0.35, 0.4, 0.85, 0.9.

*Confusion matrix, raw argmax*

|  | pred false | pred true | pred null | total |
|---|---|---|---|---|
| **truth false** | 2361 | 13 | 105 | 2479 |
| **truth true** | 13 | 1437 | 31 | 1481 |
| **truth null** | 26 | 99 | 5915 | 6040 |
| **total** | 2400 | 1549 | 6051 | 10000 |

`null -> true`: 99 of 6040 truly-null examples (1.64%).

*Confusion matrix, after the decision rule*

|  | pred false | pred true | pred null | total |
|---|---|---|---|---|
| **truth false** | 2361 | 13 | 105 | 2479 |
| **truth true** | 13 | 1435 | 33 | 1481 |
| **truth null** | 26 | 91 | 5923 | 6040 |
| **total** | 2400 | 1539 | 6061 | 10000 |

`null -> true`: 91 of 6040 truly-null examples (1.51%).

### Per class, after the decision rule

| class | support | predicted | precision | recall | F1 |
|---|---|---|---|---|---|
| `false` | 2479 | 2400 | 98.4% | 95.2% | 96.8% |
| `true` | 1481 | 1539 | 93.2% | 96.9% | 95.0% |
| `null` | 6040 | 6061 | 97.7% | 98.1% | 97.9% |

### By label mode

| label mode | n | eff n | accuracy [95% CI] |
|---|---|---|---|
| false | 2479 | **55** | 95.2% [88.9%, 99.7%] |
| null_ambiguous | 3062 | **140** | 96.2% [92.7%, 99.0%] |
| null_structural | 2978 | **1** | 100.0% [100.0%, 100.0%] |
| true | 1481 | **48** | 96.9% [93.2%, 99.4%] |

### By null sub-class

| sub-class | n | eff n | null recall [95% CI] |
|---|---|---|---|
| hedged | 1170 | **53** | 93.4% [86.0%, 99.3%] |
| historical | 874 | **40** | 98.5% [95.4%, 100.0%] |
| third_party | 1018 | **47** | 97.4% [92.8%, 100.0%] |

### By fragment library

| library | n | eff n | accuracy [95% CI] |
|---|---|---|---|
| flank_pain_false | 2479 | **55** | 95.2% [88.9%, 99.7%] |
| flank_pain_null_hedged | 1170 | **53** | 93.4% [86.0%, 99.3%] |
| flank_pain_null_historical | 874 | **40** | 98.5% [95.4%, 100.0%] |
| flank_pain_null_thirdparty | 1018 | **47** | 97.4% [92.8%, 100.0%] |
| flank_pain_true | 1481 | **48** | 96.9% [93.2%, 99.4%] |
| (none) | 2978 | **1** | 100.0% [100.0%, 100.0%] |

### Per-fragment errors (worst first)

Whether errors are spread thinly across many fragments or piled onto a few is the difference
between "the method is too weak" (model work) and "these specific ideas are not learnable from
the data we have" (library work, and these are the fragments to write more of). No intervals:
a fragment is one cluster, so an interval over its own examples measures nothing.

22 of 243 decisive fragments were got wrong at least once.

`arm_b_finetune@A1_single`: 280 errors across 22 of 243 decisive fragments. Half of them fall on **4** fragments (an even spread would be 11.0); the worst ten carry 89.6% of all errors.

| fragment | library | sub-class | truth | correct | accuracy | predicted as |
|---|---|---|---|---|---|---|
| `flank_pain_false:bead93da` | `flank_pain_false` | -- | false | 0/52 | 0.0% | null 52 |
| `flank_pain_false:d7abb5ec` | `flank_pain_false` | -- | false | 0/49 | 0.0% | null 49 |
| `flank_pain_null_hedged:d9678a20` | `flank_pain_null_hedged` | hedged | null | 0/26 | 0.0% | true 26 |
| `flank_pain_null_hedged:0f9ee32b` | `flank_pain_null_hedged` | hedged | null | 0/24 | 0.0% | false 24 |
| `flank_pain_null_thirdparty:903a529b` | `flank_pain_null_thirdparty` | third_party | null | 0/23 | 0.0% | true 23 |
| `flank_pain_true:cb7fde42` | `flank_pain_true` | -- | true | 0/19 | 0.0% | null 19 |
| `flank_pain_null_hedged:e31c9f3a` | `flank_pain_null_hedged` | hedged | null | 1/21 | 4.8% | true 20, null 1 |
| `flank_pain_null_historical:c9da7977` | `flank_pain_null_historical` | historical | null | 6/19 | 31.6% | true 13, null 6 |
| `flank_pain_true:214c674e` | `flank_pain_true` | -- | true | 13/26 | 50.0% | false 13, true 13 |
| `flank_pain_false:f63b22a5` | `flank_pain_false` | -- | false | 35/47 | 74.5% | false 35, true 11, null 1 |
| `flank_pain_null_hedged:73cf9df7` | `flank_pain_null_hedged` | hedged | null | 12/16 | 75.0% | true 4, null 12 |
| `flank_pain_false:cbb11cce` | `flank_pain_false` | -- | false | 23/27 | 85.2% | false 23, true 2, null 2 |
| `flank_pain_true:a326ab18` | `flank_pain_true` | -- | true | 30/35 | 85.7% | true 30, null 5 |
| `flank_pain_true:47597ae1` | `flank_pain_true` | -- | true | 34/38 | 89.5% | true 34, null 4 |
| `flank_pain_true:a50a0907` | `flank_pain_true` | -- | true | 19/21 | 90.5% | true 19, null 2 |
| `flank_pain_null_thirdparty:0a767c61` | `flank_pain_null_thirdparty` | third_party | null | 23/25 | 92.0% | true 2, null 23 |
| `flank_pain_null_hedged:2dedf8a9` | `flank_pain_null_hedged` | hedged | null | 27/29 | 93.1% | true 2, null 27 |
| `flank_pain_null_thirdparty:1b323aa4` | `flank_pain_null_thirdparty` | third_party | null | 15/16 | 93.8% | true 1, null 15 |
| `flank_pain_true:19e39218` | `flank_pain_true` | -- | true | 34/36 | 94.4% | true 34, null 2 |
| `flank_pain_null_hedged:7142f310` | `flank_pain_null_hedged` | hedged | null | 24/25 | 96.0% | false 1, null 24 |
| `flank_pain_false:b927c3ee` | `flank_pain_false` | -- | false | 28/29 | 96.6% | false 28, null 1 |
| `flank_pain_true:801b09f3` | `flank_pain_true` | -- | true | 47/48 | 97.9% | true 47, null 1 |

## `arm_b_finetune@A2_volume`

`roberta-base` with **every layer unfrozen**, mean-pooled, with the same `Linear(768, 3)` head -- 110M trainable parameters against Arm A's 2,307. Three epochs at batch 32, learning rate 2e-5, 10% linear warmup, AdamW, fp32. No gradient checkpointing, no 8-bit optimiser, no LoRA, no gradient accumulation: the full model fits in 12GB with room to spare, so anything that reads like a compute compromise would be a mistake rather than a saving. This is the arm that separates "the fragment libraries are the bottleneck" from "the method is too weak": if a fully fine-tuned encoder still cannot read third-party attribution, tense or metaphor, the limit is in the ideas the libraries contain and the fix is library work, not model work.

Decision-rule margins selected per fold (on each fold's own validation split): 0.0, 0.15, 0.85.

*Confusion matrix, raw argmax*

|  | pred false | pred true | pred null | total |
|---|---|---|---|---|
| **truth false** | 2419 | 0 | 107 | 2526 |
| **truth true** | 52 | 1367 | 49 | 1468 |
| **truth null** | 19 | 86 | 5901 | 6006 |
| **total** | 2490 | 1453 | 6057 | 10000 |

`null -> true`: 86 of 6006 truly-null examples (1.43%).

*Confusion matrix, after the decision rule*

|  | pred false | pred true | pred null | total |
|---|---|---|---|---|
| **truth false** | 2419 | 0 | 107 | 2526 |
| **truth true** | 52 | 1367 | 49 | 1468 |
| **truth null** | 19 | 85 | 5902 | 6006 |
| **total** | 2490 | 1452 | 6058 | 10000 |

`null -> true`: 85 of 6006 truly-null examples (1.42%).

### Per class, after the decision rule

| class | support | predicted | precision | recall | F1 |
|---|---|---|---|---|---|
| `false` | 2526 | 2490 | 97.1% | 95.8% | 96.5% |
| `true` | 1468 | 1452 | 94.1% | 93.1% | 93.6% |
| `null` | 6006 | 6058 | 97.4% | 98.3% | 97.8% |

### By label mode

| label mode | n | eff n | accuracy [95% CI] |
|---|---|---|---|
| false | 2526 | **55** | 95.8% [89.5%, 100.0%] |
| null_ambiguous | 2959 | **140** | 96.5% [93.4%, 99.1%] |
| null_structural | 3047 | **1** | 100.0% [100.0%, 100.0%] |
| true | 1468 | **48** | 93.1% [86.3%, 98.3%] |

### By null sub-class

| sub-class | n | eff n | null recall [95% CI] |
|---|---|---|---|
| hedged | 1130 | **53** | 93.5% [87.2%, 98.7%] |
| historical | 830 | **40** | 96.6% [89.7%, 100.0%] |
| third_party | 999 | **47** | 99.7% [99.1%, 100.0%] |

### By fragment library

| library | n | eff n | accuracy [95% CI] |
|---|---|---|---|
| flank_pain_false | 2526 | **55** | 95.8% [89.5%, 100.0%] |
| flank_pain_null_hedged | 1130 | **53** | 93.5% [87.2%, 98.7%] |
| flank_pain_null_historical | 830 | **40** | 96.6% [89.7%, 100.0%] |
| flank_pain_null_thirdparty | 999 | **47** | 99.7% [99.1%, 100.0%] |
| flank_pain_true | 1468 | **48** | 93.1% [86.3%, 98.3%] |
| (none) | 3047 | **1** | 100.0% [100.0%, 100.0%] |

### Per-fragment errors (worst first)

Whether errors are spread thinly across many fragments or piled onto a few is the difference
between "the method is too weak" (model work) and "these specific ideas are not learnable from
the data we have" (library work, and these are the fragments to write more of). No intervals:
a fragment is one cluster, so an interval over its own examples measures nothing.

19 of 243 decisive fragments were got wrong at least once.

`arm_b_finetune@A2_volume`: 312 errors across 19 of 243 decisive fragments. Half of them fall on **4** fragments (an even spread would be 9.5); the worst ten carry 87.2% of all errors.

| fragment | library | sub-class | truth | correct | accuracy | predicted as |
|---|---|---|---|---|---|---|
| `flank_pain_false:d7abb5ec` | `flank_pain_false` | -- | false | 0/54 | 0.0% | null 54 |
| `flank_pain_false:bead93da` | `flank_pain_false` | -- | false | 0/47 | 0.0% | null 47 |
| `flank_pain_true:214c674e` | `flank_pain_true` | -- | true | 0/29 | 0.0% | false 29 |
| `flank_pain_true:cb7fde42` | `flank_pain_true` | -- | true | 0/24 | 0.0% | null 24 |
| `flank_pain_null_hedged:73cf9df7` | `flank_pain_null_hedged` | hedged | null | 0/21 | 0.0% | true 21 |
| `flank_pain_null_hedged:d9678a20` | `flank_pain_null_hedged` | hedged | null | 0/19 | 0.0% | true 19 |
| `flank_pain_null_historical:1d821bf1` | `flank_pain_null_historical` | historical | null | 2/30 | 6.7% | true 28, null 2 |
| `flank_pain_true:801b09f3` | `flank_pain_true` | -- | true | 4/27 | 14.8% | false 23, true 4 |
| `flank_pain_null_hedged:0f9ee32b` | `flank_pain_null_hedged` | hedged | null | 3/17 | 17.6% | false 14, null 3 |
| `flank_pain_null_hedged:480834dd` | `flank_pain_null_hedged` | hedged | null | 4/17 | 23.5% | true 13, null 4 |
| `flank_pain_true:b2b80fa1` | `flank_pain_true` | -- | true | 13/22 | 59.1% | true 13, null 9 |
| `flank_pain_null_hedged:7142f310` | `flank_pain_null_hedged` | hedged | null | 13/18 | 72.2% | false 5, null 13 |
| `flank_pain_true:be1f0c8f` | `flank_pain_true` | -- | true | 32/39 | 82.1% | true 32, null 7 |
| `flank_pain_false:b927c3ee` | `flank_pain_false` | -- | false | 28/34 | 82.4% | false 28, null 6 |
| `flank_pain_true:d7d705f6` | `flank_pain_true` | -- | true | 32/38 | 84.2% | true 32, null 6 |
| `flank_pain_null_thirdparty:903a529b` | `flank_pain_null_thirdparty` | third_party | null | 17/20 | 85.0% | true 3, null 17 |
| `flank_pain_true:a326ab18` | `flank_pain_true` | -- | true | 32/34 | 94.1% | true 32, null 2 |
| `flank_pain_null_hedged:e51c02e1` | `flank_pain_null_hedged` | hedged | null | 17/18 | 94.4% | true 1, null 17 |
| `flank_pain_true:c451668c` | `flank_pain_true` | -- | true | 35/36 | 97.2% | true 35, null 1 |

## `arm_b_finetune@A3_joint`

`roberta-base` with **every layer unfrozen**, mean-pooled, with the same `Linear(768, 3)` head -- 110M trainable parameters against Arm A's 2,307. Three epochs at batch 32, learning rate 2e-5, 10% linear warmup, AdamW, fp32. No gradient checkpointing, no 8-bit optimiser, no LoRA, no gradient accumulation: the full model fits in 12GB with room to spare, so anything that reads like a compute compromise would be a mistake rather than a saving. This is the arm that separates "the fragment libraries are the bottleneck" from "the method is too weak": if a fully fine-tuned encoder still cannot read third-party attribution, tense or metaphor, the limit is in the ideas the libraries contain and the fix is library work, not model work. **Joint multi-head training**: 6 heads sharing one encoder (dysuria_present, fever_present, flank_pain_present, haematuria_present, nocturia_present, urinary_frequency_present). Epoch selection uses DD6's unweighted mean of every head's own validation macro-F1, so this signal's stopping point may differ from a single-signal run's own best epoch. Each head's margin is chosen independently on its own validation split -- no cross-head trade.

Decision-rule margins selected per fold (on each fold's own validation split): 0.0, 0.3, 0.75.

*Confusion matrix, raw argmax*

|  | pred false | pred true | pred null | total |
|---|---|---|---|---|
| **truth false** | 2470 | 5 | 4 | 2479 |
| **truth true** | 26 | 1385 | 70 | 1481 |
| **truth null** | 34 | 46 | 5960 | 6040 |
| **total** | 2530 | 1436 | 6034 | 10000 |

`null -> true`: 46 of 6040 truly-null examples (0.76%).

*Confusion matrix, after the decision rule*

|  | pred false | pred true | pred null | total |
|---|---|---|---|---|
| **truth false** | 2473 | 2 | 4 | 2479 |
| **truth true** | 26 | 1385 | 70 | 1481 |
| **truth null** | 34 | 35 | 5971 | 6040 |
| **total** | 2533 | 1422 | 6045 | 10000 |

`null -> true`: 35 of 6040 truly-null examples (0.58%).

### Per class, after the decision rule

| class | support | predicted | precision | recall | F1 |
|---|---|---|---|---|---|
| `false` | 2479 | 2533 | 97.6% | 99.8% | 98.7% |
| `true` | 1481 | 1422 | 97.4% | 93.5% | 95.4% |
| `null` | 6040 | 6045 | 98.8% | 98.9% | 98.8% |

### By label mode

| label mode | n | eff n | accuracy [95% CI] |
|---|---|---|---|
| false | 2479 | **55** | 99.8% [99.2%, 100.0%] |
| null_ambiguous | 3062 | **140** | 98.4% [97.0%, 99.5%] |
| null_structural | 2978 | **1** | 99.3% [99.3%, 99.3%] |
| true | 1481 | **48** | 93.5% [85.2%, 99.7%] |

### By null sub-class

| sub-class | n | eff n | null recall [95% CI] |
|---|---|---|---|
| hedged | 1170 | **53** | 97.5% [94.2%, 99.8%] |
| historical | 874 | **40** | 99.9% [99.6%, 100.0%] |
| third_party | 1018 | **47** | 98.1% [95.8%, 99.8%] |

### By fragment library

| library | n | eff n | accuracy [95% CI] |
|---|---|---|---|
| flank_pain_false | 2479 | **55** | 99.8% [99.2%, 100.0%] |
| flank_pain_null_hedged | 1170 | **53** | 97.5% [94.2%, 99.8%] |
| flank_pain_null_historical | 874 | **40** | 99.9% [99.6%, 100.0%] |
| flank_pain_null_thirdparty | 1018 | **47** | 98.1% [95.8%, 99.8%] |
| flank_pain_true | 1481 | **48** | 93.5% [85.2%, 99.7%] |
| (none) | 2978 | **1** | 99.3% [99.3%, 99.3%] |

### Per-fragment errors (worst first)

Whether errors are spread thinly across many fragments or piled onto a few is the difference
between "the method is too weak" (model work) and "these specific ideas are not learnable from
the data we have" (library work, and these are the fragments to write more of). No intervals:
a fragment is one cluster, so an interval over its own examples measures nothing.

17 of 243 decisive fragments were got wrong at least once.

`arm_b_finetune@A3_joint`: 151 errors across 17 of 243 decisive fragments. Half of them fall on **3** fragments (an even spread would be 8.5); the worst ten carry 94.7% of all errors.

| fragment | library | sub-class | truth | correct | accuracy | predicted as |
|---|---|---|---|---|---|---|
| `flank_pain_true:801b09f3` | `flank_pain_true` | -- | true | 0/48 | 0.0% | null 48 |
| `flank_pain_true:214c674e` | `flank_pain_true` | -- | true | 0/26 | 0.0% | false 26 |
| `flank_pain_null_hedged:73cf9df7` | `flank_pain_null_hedged` | hedged | null | 0/16 | 0.0% | true 16 |
| `flank_pain_true:a50a0907` | `flank_pain_true` | -- | true | 4/21 | 19.0% | true 4, null 17 |
| `flank_pain_null_thirdparty:903a529b` | `flank_pain_null_thirdparty` | third_party | null | 12/23 | 52.2% | true 11, null 12 |
| `flank_pain_true:cb7fde42` | `flank_pain_true` | -- | true | 14/19 | 73.7% | true 14, null 5 |
| `flank_pain_null_hedged:3d9c58e1` | `flank_pain_null_hedged` | hedged | null | 18/24 | 75.0% | false 6, null 18 |
| `flank_pain_null_thirdparty:d93ccd13` | `flank_pain_null_thirdparty` | third_party | null | 19/23 | 82.6% | false 2, true 2, null 19 |
| `flank_pain_null_hedged:bbcf908d` | `flank_pain_null_hedged` | hedged | null | 24/28 | 85.7% | true 4, null 24 |
| `flank_pain_false:f63b22a5` | `flank_pain_false` | -- | false | 41/47 | 87.2% | false 41, true 2, null 4 |
| `flank_pain_null_hedged:c8fa5ec1` | `flank_pain_null_hedged` | hedged | null | 19/21 | 90.5% | false 2, null 19 |
| `flank_pain_null_thirdparty:3003d95a` | `flank_pain_null_thirdparty` | third_party | null | 18/19 | 94.7% | false 1, null 18 |
| `flank_pain_null_historical:62650d74` | `flank_pain_null_historical` | historical | null | 20/21 | 95.2% | false 1, null 20 |
| `flank_pain_null_thirdparty:1dad0f08` | `flank_pain_null_thirdparty` | third_party | null | 21/22 | 95.5% | false 1, null 21 |
| `flank_pain_null_thirdparty:89cfecd3` | `flank_pain_null_thirdparty` | third_party | null | 21/22 | 95.5% | false 1, null 21 |
| `flank_pain_null_hedged:327499ac` | `flank_pain_null_hedged` | hedged | null | 23/24 | 95.8% | false 1, null 23 |
| `flank_pain_null_thirdparty:1d078e6d` | `flank_pain_null_thirdparty` | third_party | null | 26/27 | 96.3% | false 1, null 26 |

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
| 0 | 10000 | 2000 | 2000 | 0.0 | 83.4% | 83.4% | 77.3% | 0.41% |
| 1 | 10000 | 2000 | 2000 | 0.0 | 79.2% | 79.2% | 71.0% | 0.67% |
| 2 | 10000 | 2000 | 2000 | 0.0 | 78.7% | 78.7% | 72.0% | 4.80% |
| 3 | 10000 | 2000 | 2000 | 0.0 | 81.4% | 81.4% | 75.4% | 2.14% |
| 4 | 10000 | 2000 | 2000 | 0.0 | 81.5% | 81.5% | 75.7% | 4.39% |

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
| 4 | 10000 | 2000 | 2000 | 0.0 | 60.3% | 60.3% | 25.1% | 0.00% |

### `arm_b_finetune@A1_single`

| fold | train n | val n | test n | margin | acc (raw) | acc (ruled) | macro-F1 | null->true |
|---|---|---|---|---|---|---|---|---|
| 0 | 10000 | 2000 | 2000 | 0.4 | 99.4% | 99.2% | 99.0% | 0.00% |
| 1 | 10000 | 2000 | 2000 | 0.9 | 97.6% | 97.7% | 96.8% | 2.16% |
| 2 | 10000 | 2000 | 2000 | 0.0 | 94.0% | 94.0% | 92.5% | 3.31% |
| 3 | 10000 | 2000 | 2000 | 0.85 | 96.0% | 96.3% | 95.9% | 2.06% |
| 4 | 10000 | 2000 | 2000 | 0.35 | 98.7% | 98.7% | 98.7% | 0.00% |

### `arm_b_finetune@A2_volume`

| fold | train n | val n | test n | margin | acc (raw) | acc (ruled) | macro-F1 | null->true |
|---|---|---|---|---|---|---|---|---|
| 0 | 44680 | 2000 | 2000 | 0.0 | 98.7% | 98.7% | 98.4% | 1.08% |
| 1 | 44680 | 2000 | 2000 | 0.85 | 96.4% | 96.5% | 95.4% | 3.99% |
| 2 | 44680 | 2000 | 2000 | 0.0 | 93.3% | 93.3% | 89.6% | 2.00% |
| 3 | 44680 | 2000 | 2000 | 0.0 | 97.0% | 97.0% | 97.0% | 0.00% |
| 4 | 44680 | 2000 | 2000 | 0.15 | 99.0% | 99.0% | 98.9% | 0.00% |

### `arm_b_finetune@A3_joint`

| fold | train n | val n | test n | margin | acc (raw) | acc (ruled) | macro-F1 | null->true |
|---|---|---|---|---|---|---|---|---|
| 0 | 44680 | 2000 | 2000 | 0.0 | 100.0% | 100.0% | 100.0% | 0.00% |
| 1 | 44830 | 2000 | 2000 | 0.0 | 98.9% | 98.9% | 98.5% | 0.00% |
| 2 | 45230 | 2000 | 2000 | 0.75 | 94.3% | 94.7% | 91.7% | 2.24% |
| 3 | 45430 | 2000 | 2000 | 0.75 | 99.7% | 100.0% | 99.9% | 0.08% |
| 4 | 45590 | 2000 | 2000 | 0.3 | 97.8% | 98.0% | 97.9% | 0.58% |

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

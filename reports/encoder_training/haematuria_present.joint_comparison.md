# Encoder training: evaluation report

*Generated 2026-08-17T11:29:45+00:00.*

|  |  |
|---|---|
| signal | `haematuria_present` |
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
| cluster tag coverage | `0 of 5 libraries carry cluster markers; 225 of 225 fragments are in libraries with none` |
| bootstrap | `2000 resamples over clusters, alpha=0.05, seed=0` |

**arms**

* **A1_single** (`data/synthetic/generated/folds`): 10000 examples per epoch, **10000** labelled positions for `haematuria_present` -- this signal's own dataset, one head. **The paired arm**: A3's slice for this signal *is* these examples, so A1 vs A3 is scored example for example and McNemar applies.
* **A2_volume** (`data/synthetic/generated/folds-volume`): 44680 examples per epoch, **44680** labelled positions for `haematuria_present` -- this signal's own clusters again, recombined roughly 4.5x as many times, one head. **Unpaired, by construction**: its test examples are different texts with their own ids, so it is read through the pooled cluster interval and the per-fold spread and never through McNemar. It is here to bound how much of any A1-to-A3 movement encoder gradient steps alone could explain, at unchanged effective n.
* **A3_joint** (`joint6`): 44680 examples per epoch, **10000** labelled positions for `haematuria_present` -- the merged tree, every head sharing one encoder. This head's supervision is unchanged from A1 -- a dysuria example carries no fever key at all, which is a mask rather than a `null` assertion -- so the only mechanism by which this arm can move is representational.

**paired comparison**

A1_single vs A3_joint, paired on this signal's test examples. A2_volume pairs with nothing and its McNemar rows are recorded as skipped rather than omitted

**selected epochs**

{'A1_single': "2, 2, 3, 3, 3 (this head's own best epoch would have been 1, 1, 2, 2, 2)", 'A2_volume': "1, 1, 1, 3, 1 (this head's own best epoch would have been 0, 0, 0, 2, 0)", 'A3_joint': "3, 3, 2, 3, 1 (this head's own best epoch would have been 2, 2, 1, 1, 1)"}

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
| `majority_class` | baseline | 7022 | **225** | 43.6% [36.8%, 51.0%] | 20.2% [17.9%, 22.5%] | 60.4% | 60.4% +/- 0.2% |
| `length_only` | baseline | 7022 | **225** | 44.2% [37.4%, 51.3%] | 21.4% [18.8%, 23.8%] | 60.8% | 60.8% +/- 0.5% |
| `tfidf_logreg` | baseline | 7022 | **225** | 74.7% [69.5%, 79.6%] | 71.1% [65.4%, 76.3%] | 82.1% | 82.1% +/- 3.5% |
| `length_only__shuffled` | negative control | 7022 | **225** | 43.6% [36.8%, 51.0%] | 20.2% [17.9%, 22.5%] | 60.4% | 60.4% +/- 0.2% |
| `tfidf_logreg__shuffled` | negative control | 7022 | **225** | 43.6% [36.8%, 50.9%] | 20.2% [17.9%, 22.5%] | 60.4% | 60.4% +/- 0.2% |
| `arm_b_finetune@A1_single` | finetune | 7022 | **225** | 91.5% [87.5%, 94.9%] | 90.7% [86.4%, 94.3%] | 94.0% | 94.0% +/- 2.4% |
| `arm_b_finetune@A2_volume` | finetune | 6953 | **225** | 92.8% [88.8%, 96.3%] | 92.2% [87.7%, 96.0%] | 94.9% | 94.9% +/- 1.7% |
| `arm_b_finetune@A3_joint` | finetune | 7022 | **225** | 94.9% [91.8%, 97.5%] | 94.5% [90.9%, 97.4%] | 96.2% | 96.2% +/- 1.5% |

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
| `tfidf_logreg` | -- | -- | 89.7% [81.3%, 96.0%] (eff n 45) | 94.6% [90.8%, 97.7%] (eff n 45) | -- | 96.3% [92.0%, 99.1%] (eff n 45) |
| `length_only__shuffled` | -- | -- | 100.0% [100.0%, 100.0%] (eff n 45) | 100.0% [100.0%, 100.0%] (eff n 45) | -- | 100.0% [100.0%, 100.0%] (eff n 45) |
| `tfidf_logreg__shuffled` | -- | -- | 99.9% [99.7%, 100.0%] (eff n 45) | 100.0% [100.0%, 100.0%] (eff n 45) | -- | 100.0% [100.0%, 100.0%] (eff n 45) |
| `arm_b_finetune@A1_single` | -- | -- | 84.2% [74.4%, 92.3%] (eff n 45) | 96.7% [89.9%, 100.0%] (eff n 45) | -- | 100.0% [100.0%, 100.0%] (eff n 45) |
| `arm_b_finetune@A2_volume` | -- | -- | 85.2% [73.5%, 94.8%] (eff n 45) | 97.0% [90.9%, 100.0%] (eff n 45) | -- | 99.6% [99.0%, 100.0%] (eff n 45) |
| `arm_b_finetune@A3_joint` | -- | -- | 87.3% [77.4%, 95.1%] (eff n 45) | 98.9% [97.3%, 100.0%] (eff n 45) | -- | 98.1% [94.3%, 100.0%] (eff n 45) |

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

### `arm_b_finetune@A1_single`

Recombination test slice: **n 7022**, **eff n 225** clusters, accuracy 91.5% [87.5%, 94.9%]. Holdout: **n 67** submissions, one observation each, scored by 5 fold models at margins 0.85, 0.9, 0.8, 0.0, 0.9. The two `n`s are printed together because they are not the same kind of number and the second is far the smaller.

| signal | true/false/null | omitted | decisive n | decisive acc (mean +/- sd) | worst-case half-width | all n | all acc (mean +/- sd) | null recall |
|---|---|---|---|---|---|---|---|---|
| `haematuria_present` | 9/2/56 | 0 | 11 | 74.5% +/- 13.5% | +/-29.5% | 67 | 74.6% +/- 6.8% | 74.6% +/- 7.5% |

`null -> true` on real text, per fold: `haematuria_present` 5, 14, 14, 15, 13 of 56. This is the cell that invents a symptom into a patient's pre-filled form, counted here on submissions rather than on recombinations.

### `arm_b_finetune@A2_volume`

Recombination test slice: **n 6953**, **eff n 225** clusters, accuracy 92.8% [88.8%, 96.3%]. Holdout: **n 67** submissions, one observation each, scored by 5 fold models at margins 0.85, 0.9, 0.9, 0.0, 0.75. The two `n`s are printed together because they are not the same kind of number and the second is far the smaller.

| signal | true/false/null | omitted | decisive n | decisive acc (mean +/- sd) | worst-case half-width | all n | all acc (mean +/- sd) | null recall |
|---|---|---|---|---|---|---|---|---|
| `haematuria_present` | 9/2/56 | 0 | 11 | 90.9% +/- 12.9% | +/-29.5% | 67 | 64.2% +/- 12.4% | 58.9% +/- 15.5% |

`null -> true` on real text, per fold: `haematuria_present` 13, 17, 15, 32, 21 of 56. This is the cell that invents a symptom into a patient's pre-filled form, counted here on submissions rather than on recombinations.

### `arm_b_finetune@A3_joint`

Recombination test slice: **n 7022**, **eff n 225** clusters, accuracy 94.9% [91.8%, 97.5%]. Holdout: **n 67** submissions, one observation each, scored by 5 fold models at margins {'dysuria_present': 0.55, 'fever_present': 0.0, 'flank_pain_present': 0.0, 'haematuria_present': 0.6, 'nocturia_present': 0.0, 'urinary_frequency_present': 0.0}, {'dysuria_present': 0.65, 'fever_present': 0.9, 'flank_pain_present': 0.0, 'haematuria_present': 0.55, 'nocturia_present': 0.0, 'urinary_frequency_present': 0.0}, {'dysuria_present': 0.9, 'fever_present': 0.9, 'flank_pain_present': 0.75, 'haematuria_present': 0.0, 'nocturia_present': 0.0, 'urinary_frequency_present': 0.0}, {'dysuria_present': 0.9, 'fever_present': 0.9, 'flank_pain_present': 0.75, 'haematuria_present': 0.0, 'nocturia_present': 0.9, 'urinary_frequency_present': 0.9}, {'dysuria_present': 0.8, 'fever_present': 0.0, 'flank_pain_present': 0.3, 'haematuria_present': 0.9, 'nocturia_present': 0.9, 'urinary_frequency_present': 0.9}. The two `n`s are printed together because they are not the same kind of number and the second is far the smaller.

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
| `majority_class` | baseline | 3062 | **135** | 100.0% [100.0%, 100.0%] |
| `length_only` | baseline | 3062 | **135** | 100.0% [100.0%, 100.0%] |
| `tfidf_logreg` | baseline | 3062 | **135** | 93.4% [90.0%, 96.2%] |
| `arm_b_finetune@A1_single` | finetune | 3062 | **135** | 93.3% [89.0%, 97.0%] |
| `arm_b_finetune@A2_volume` | finetune | 2959 | **135** | 93.7% [89.2%, 97.5%] |
| `arm_b_finetune@A3_joint` | finetune | 3062 | **135** | 94.6% [90.8%, 97.7%] |

### 2. The same comparison, paired

Two overlapping intervals do not settle whether one model beats another on the same
examples. McNemar does, over the examples the two disagree about -- read it alongside the
intervals above, never instead of them.

| pair | n | a only | b only | p |
|---|---|---|---|---|
| `majority_class` vs `length_only` | 3062 | 0 | 0 | 1 |
| `majority_class` vs `tfidf_logreg` | 3062 | 205 | 0 | 3.89e-62 |
| `majority_class` vs `arm_b_finetune@A1_single` | 3062 | 231 | 0 | 5.8e-70 |
| `majority_class` vs `arm_b_finetune@A3_joint` | 3062 | 179 | 0 | 2.61e-54 |
| `length_only` vs `tfidf_logreg` | 3062 | 205 | 0 | 3.89e-62 |
| `length_only` vs `arm_b_finetune@A1_single` | 3062 | 231 | 0 | 5.8e-70 |
| `length_only` vs `arm_b_finetune@A3_joint` | 3062 | 179 | 0 | 2.61e-54 |
| `tfidf_logreg` vs `arm_b_finetune@A1_single` | 3062 | 184 | 158 | 0.176 |
| `tfidf_logreg` vs `arm_b_finetune@A3_joint` | 3062 | 127 | 153 | 0.135 |
| `arm_b_finetune@A1_single` vs `arm_b_finetune@A3_joint` | 3062 | 81 | 133 | 0.000462 |

Not on this table, because they cannot be paired at all -- different examples on the two sides, so there is nothing for McNemar to pair: `majority_class` vs `arm_b_finetune@A2_volume`; `length_only` vs `arm_b_finetune@A2_volume`; `tfidf_logreg` vs `arm_b_finetune@A2_volume`; `arm_b_finetune@A1_single` vs `arm_b_finetune@A2_volume`; `arm_b_finetune@A2_volume` vs `arm_b_finetune@A3_joint`. Read those through the intervals above and the per-fold spread, and see "Pairs that could not be tested" below.

### 3. Where the errors fall

The per-fragment table below, as one number per model. Errors spread thinly across many
fragments say the method is too weak. Errors piled onto a handful say those specific ideas
are not learnable from the data we have -- and the table names them, which is what makes
this the most decision-useful thing in the report.

* `majority_class`: 3960 errors across 90 of 225 decisive fragments. Half of them fall on **32** fragments (an even spread would be 45.0); the worst ten carry 18.2% of all errors.
* `length_only`: 3921 errors across 90 of 225 decisive fragments. Half of them fall on **32** fragments (an even spread would be 45.0); the worst ten carry 17.9% of all errors.
* `tfidf_logreg`: 1779 errors across 114 of 225 decisive fragments. Half of them fall on **21** fragments (an even spread would be 57.0); the worst ten carry 30.7% of all errors.
* `arm_b_finetune@A1_single`: 600 errors across 30 of 225 decisive fragments. Half of them fall on **7** fragments (an even spread would be 15.0); the worst ten carry 67.2% of all errors.
* `arm_b_finetune@A2_volume`: 498 errors across 23 of 225 decisive fragments. Half of them fall on **5** fragments (an even spread would be 11.5); the worst ten carry 80.7% of all errors.
* `arm_b_finetune@A3_joint`: 357 errors across 22 of 225 decisive fragments. Half of them fall on **4** fragments (an even spread would be 11.0); the worst ten carry 86.8% of all errors.

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
| `length_only__shuffled` | 60.4% [38.5%, 77.5%] | 25.1% [18.5%, 29.1%] |
| `tfidf_logreg__shuffled` | 60.4% [38.5%, 77.5%] | 25.1% [18.5%, 29.1%] |

## Paired comparisons (McNemar, raw argmax)

Exact two-sided McNemar over the examples the two models disagree about. Pairing unit is the
example, not the cluster -- see the limitations.

| pair | slice | n | a only | b only | p |
|---|---|---|---|---|---|
| `majority_class` vs `length_only` | overall | 10000 | 3 | 39 | 5.63e-09 |
| `majority_class` vs `length_only` | null_ambiguous | 3062 | 0 | 0 | 1 |
| `majority_class` vs `tfidf_logreg` | overall | 10000 | 214 | 2385 | 0 |
| `majority_class` vs `tfidf_logreg` | null_ambiguous | 3062 | 205 | 0 | 3.89e-62 |
| `majority_class` vs `arm_b_finetune@A1_single` | overall | 10000 | 231 | 3572 | 0 |
| `majority_class` vs `arm_b_finetune@A1_single` | null_ambiguous | 3062 | 231 | 0 | 5.8e-70 |
| `majority_class` vs `arm_b_finetune@A3_joint` | overall | 10000 | 206 | 3781 | 0 |
| `majority_class` vs `arm_b_finetune@A3_joint` | null_ambiguous | 3062 | 179 | 0 | 2.61e-54 |
| `length_only` vs `tfidf_logreg` | overall | 10000 | 223 | 2358 | 0 |
| `length_only` vs `tfidf_logreg` | null_ambiguous | 3062 | 205 | 0 | 3.89e-62 |
| `length_only` vs `arm_b_finetune@A1_single` | overall | 10000 | 235 | 3540 | 0 |
| `length_only` vs `arm_b_finetune@A1_single` | null_ambiguous | 3062 | 231 | 0 | 5.8e-70 |
| `length_only` vs `arm_b_finetune@A3_joint` | overall | 10000 | 211 | 3750 | 0 |
| `length_only` vs `arm_b_finetune@A3_joint` | null_ambiguous | 3062 | 179 | 0 | 2.61e-54 |
| `tfidf_logreg` vs `arm_b_finetune@A1_single` | overall | 10000 | 249 | 1419 | 1.03e-198 |
| `tfidf_logreg` vs `arm_b_finetune@A1_single` | null_ambiguous | 3062 | 184 | 158 | 0.176 |
| `tfidf_logreg` vs `arm_b_finetune@A3_joint` | overall | 10000 | 187 | 1591 | 1.99e-277 |
| `tfidf_logreg` vs `arm_b_finetune@A3_joint` | null_ambiguous | 3062 | 127 | 153 | 0.135 |
| `arm_b_finetune@A1_single` vs `arm_b_finetune@A3_joint` | overall | 10000 | 129 | 363 | 8.49e-27 |
| `arm_b_finetune@A1_single` vs `arm_b_finetune@A3_joint` | null_ambiguous | 3062 | 81 | 133 | 0.000462 |

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
| `haematuria_false` | 2479 | 0.0% | 1.6% | 69.5% | 92.1% | 92.1% | 95.9% | 95.9pp |
| `haematuria_true` | 1481 | 0.0% | 0.0% | 44.6% | 86.6% | 92.4% | 94.0% | 94.0pp |
| `haematuria_null_hedged` | 1079 | 100.0% | 100.0% | 89.7% | 84.2% | 85.2% | 87.3% | 15.8pp |
| `haematuria_null_historical` | 1016 | 100.0% | 100.0% | 94.6% | 96.7% | 97.0% | 98.9% | 5.4pp |
| `haematuria_null_thirdparty` | 967 | 100.0% | 100.0% | 96.3% | 100.0% | 99.6% | 98.1% | 3.7pp |
| `(none)` | 2978 | 100.0% | 99.9% | 99.7% | 100.0% | 99.5% | 99.4% | 0.6pp |

### By fragment, errors

Ordered by the worst model's error count, so the fragments the comparison is about sort
to the top whichever encoder wins. Counts, not rates: these are the sentences a month of
library work would be spent on. The JSON holds every fragment.

| fragment | library | truth | `majority_class` | `length_only` | `tfidf_logreg` | `arm_b_finetune@A1_single` | `arm_b_finetune@A2_volume` | `arm_b_finetune@A3_joint` | spread |
|---|---|---|---|---|---|---|---|---|---|
| `haematuria_false:0e98be72` | `haematuria_false` | false | 81 | 81 | 79 | 0 | 0 | 0 | 81 |
| `haematuria_false:56b8af62` | `haematuria_false` | false | 78 | 78 | 43 | 0 | 0 | 0 | 78 |
| `haematuria_false:94f9de34` | `haematuria_false` | false | 76 | 62 | 20 | 0 | 0 | 0 | 76 |
| `haematuria_false:acc7804e` | `haematuria_false` | false | 75 | 75 | 7 | 0 | 0 | 0 | 75 |
| `haematuria_false:b3fd19df` | `haematuria_false` | false | 74 | 74 | 4 | 0 | 0 | 0 | 74 |
| `haematuria_true:c0ff5eed` | `haematuria_true` | true | 71 | 71 | 67 | 0 | 0 | 0 | 71 |
| `haematuria_false:d163df19` | `haematuria_false` | false | 58 | 58 | 56 | 58 | 69 | 44 | 25 |
| `haematuria_false:e23c4950` | `haematuria_false` | false | 69 | 58 | 24 | 0 | 0 | 0 | 69 |
| `haematuria_false:5e090855` | `haematuria_false` | false | 66 | 66 | 0 | 0 | 0 | 0 | 66 |
| `haematuria_false:64933508` | `haematuria_false` | false | 65 | 65 | 21 | 0 | 0 | 0 | 65 |
| `haematuria_false:b692c4ce` | `haematuria_false` | false | 64 | 64 | 8 | 0 | 0 | 0 | 64 |
| `haematuria_false:873d5c5b` | `haematuria_false` | false | 63 | 63 | 31 | 0 | 0 | 0 | 63 |
| `haematuria_false:b0d93eca` | `haematuria_false` | false | 63 | 63 | 0 | 0 | 0 | 0 | 63 |
| `haematuria_true:972bb99b` | `haematuria_true` | true | 63 | 63 | 8 | 0 | 0 | 0 | 63 |
| `haematuria_true:62126789` | `haematuria_true` | true | 62 | 62 | 2 | 0 | 0 | 0 | 62 |
| `haematuria_false:94644abb` | `haematuria_false` | false | 61 | 61 | 0 | 0 | 0 | 0 | 61 |
| `haematuria_false:fc6a0704` | `haematuria_false` | false | 61 | 61 | 3 | 0 | 0 | 0 | 61 |
| `haematuria_true:6fadb8bc` | `haematuria_true` | true | 60 | 60 | 52 | 60 | 59 | 57 | 8 |
| `haematuria_true:7ea098d1` | `haematuria_true` | true | 60 | 60 | 31 | 0 | 0 | 0 | 60 |
| `haematuria_true:f2e49699` | `haematuria_true` | true | 60 | 60 | 32 | 0 | 0 | 0 | 60 |
| `haematuria_false:a84358ef` | `haematuria_false` | false | 59 | 59 | 0 | 0 | 0 | 0 | 59 |
| `haematuria_true:150663fa` | `haematuria_true` | true | 59 | 59 | 14 | 0 | 0 | 0 | 59 |
| `haematuria_false:5543da20` | `haematuria_false` | false | 58 | 58 | 3 | 0 | 0 | 0 | 58 |
| `haematuria_false:cbd9cec5` | `haematuria_false` | false | 58 | 58 | 58 | 0 | 0 | 0 | 58 |
| `haematuria_false:0722271d` | `haematuria_false` | false | 57 | 57 | 4 | 0 | 0 | 0 | 57 |
| `haematuria_false:58488f8a` | `haematuria_false` | false | 57 | 57 | 0 | 0 | 0 | 0 | 57 |
| `haematuria_false:a9960bdc` | `haematuria_false` | false | 57 | 57 | 0 | 0 | 0 | 0 | 57 |
| `haematuria_true:d93fd4ce` | `haematuria_true` | true | 57 | 57 | 4 | 0 | 0 | 0 | 57 |
| `haematuria_false:0a0b1113` | `haematuria_false` | false | 56 | 56 | 53 | 0 | 0 | 0 | 56 |
| `haematuria_false:7240a8fb` | `haematuria_false` | false | 56 | 53 | 17 | 0 | 0 | 0 | 56 |
| `haematuria_false:c0157f0d` | `haematuria_false` | false | 56 | 56 | 1 | 0 | 0 | 0 | 56 |
| `haematuria_false:cb3cb6e6` | `haematuria_false` | false | 56 | 51 | 44 | 55 | 54 | 56 | 12 |
| `haematuria_false:d9d4737d` | `haematuria_false` | false | 56 | 55 | 27 | 0 | 0 | 0 | 56 |
| `haematuria_false:4fda0b2c` | `haematuria_false` | false | 55 | 50 | 14 | 0 | 0 | 0 | 55 |
| `haematuria_false:899e3ed9` | `haematuria_false` | false | 55 | 55 | 26 | 2 | 0 | 0 | 55 |
| `haematuria_false:66629fb1` | `haematuria_false` | false | 54 | 54 | 40 | 0 | 0 | 0 | 54 |
| `haematuria_false:9720fe1e` | `haematuria_false` | false | 53 | 53 | 0 | 0 | 0 | 0 | 53 |
| `haematuria_false:61bf080a` | `haematuria_false` | false | 52 | 52 | 1 | 0 | 0 | 0 | 52 |
| `haematuria_true:245ed73d` | `haematuria_true` | true | 51 | 51 | 17 | 0 | 0 | 0 | 51 |
| `haematuria_false:21d7fe6b` | `haematuria_false` | false | 49 | 49 | 21 | 0 | 0 | 0 | 49 |

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
| historical | 1016 | **45** | 100.0% [100.0%, 100.0%] |
| third_party | 967 | **45** | 100.0% [100.0%, 100.0%] |

### By fragment library

| library | n | eff n | accuracy [95% CI] |
|---|---|---|---|
| haematuria_false | 2479 | **45** | 0.0% [0.0%, 0.0%] |
| haematuria_null_hedged | 1079 | **45** | 100.0% [100.0%, 100.0%] |
| haematuria_null_historical | 1016 | **45** | 100.0% [100.0%, 100.0%] |
| haematuria_null_thirdparty | 967 | **45** | 100.0% [100.0%, 100.0%] |
| haematuria_true | 1481 | **45** | 0.0% [0.0%, 0.0%] |
| (none) | 2978 | **1** | 100.0% [100.0%, 100.0%] |

### Per-fragment errors (worst first)

Whether errors are spread thinly across many fragments or piled onto a few is the difference
between "the method is too weak" (model work) and "these specific ideas are not learnable from
the data we have" (library work, and these are the fragments to write more of). No intervals:
a fragment is one cluster, so an interval over its own examples measures nothing.

90 of 225 decisive fragments were got wrong at least once.

`majority_class`: 3960 errors across 90 of 225 decisive fragments. Half of them fall on **32** fragments (an even spread would be 45.0); the worst ten carry 18.2% of all errors.

| fragment | library | sub-class | truth | correct | accuracy | predicted as |
|---|---|---|---|---|---|---|
| `haematuria_false:0e98be72` | `haematuria_false` | -- | false | 0/81 | 0.0% | null 81 |
| `haematuria_false:56b8af62` | `haematuria_false` | -- | false | 0/78 | 0.0% | null 78 |
| `haematuria_false:94f9de34` | `haematuria_false` | -- | false | 0/76 | 0.0% | null 76 |
| `haematuria_false:acc7804e` | `haematuria_false` | -- | false | 0/75 | 0.0% | null 75 |
| `haematuria_false:b3fd19df` | `haematuria_false` | -- | false | 0/74 | 0.0% | null 74 |
| `haematuria_true:c0ff5eed` | `haematuria_true` | -- | true | 0/71 | 0.0% | null 71 |
| `haematuria_false:e23c4950` | `haematuria_false` | -- | false | 0/69 | 0.0% | null 69 |
| `haematuria_false:5e090855` | `haematuria_false` | -- | false | 0/66 | 0.0% | null 66 |
| `haematuria_false:64933508` | `haematuria_false` | -- | false | 0/65 | 0.0% | null 65 |
| `haematuria_false:b692c4ce` | `haematuria_false` | -- | false | 0/64 | 0.0% | null 64 |
| `haematuria_false:873d5c5b` | `haematuria_false` | -- | false | 0/63 | 0.0% | null 63 |
| `haematuria_false:b0d93eca` | `haematuria_false` | -- | false | 0/63 | 0.0% | null 63 |
| `haematuria_true:972bb99b` | `haematuria_true` | -- | true | 0/63 | 0.0% | null 63 |
| `haematuria_true:62126789` | `haematuria_true` | -- | true | 0/62 | 0.0% | null 62 |
| `haematuria_false:94644abb` | `haematuria_false` | -- | false | 0/61 | 0.0% | null 61 |
| `haematuria_false:fc6a0704` | `haematuria_false` | -- | false | 0/61 | 0.0% | null 61 |
| `haematuria_true:6fadb8bc` | `haematuria_true` | -- | true | 0/60 | 0.0% | null 60 |
| `haematuria_true:7ea098d1` | `haematuria_true` | -- | true | 0/60 | 0.0% | null 60 |
| `haematuria_true:f2e49699` | `haematuria_true` | -- | true | 0/60 | 0.0% | null 60 |
| `haematuria_false:a84358ef` | `haematuria_false` | -- | false | 0/59 | 0.0% | null 59 |
| `haematuria_true:150663fa` | `haematuria_true` | -- | true | 0/59 | 0.0% | null 59 |
| `haematuria_false:5543da20` | `haematuria_false` | -- | false | 0/58 | 0.0% | null 58 |
| `haematuria_false:cbd9cec5` | `haematuria_false` | -- | false | 0/58 | 0.0% | null 58 |
| `haematuria_false:d163df19` | `haematuria_false` | -- | false | 0/58 | 0.0% | null 58 |
| `haematuria_false:0722271d` | `haematuria_false` | -- | false | 0/57 | 0.0% | null 57 |
| `haematuria_false:58488f8a` | `haematuria_false` | -- | false | 0/57 | 0.0% | null 57 |
| `haematuria_false:a9960bdc` | `haematuria_false` | -- | false | 0/57 | 0.0% | null 57 |
| `haematuria_true:d93fd4ce` | `haematuria_true` | -- | true | 0/57 | 0.0% | null 57 |
| `haematuria_false:0a0b1113` | `haematuria_false` | -- | false | 0/56 | 0.0% | null 56 |
| `haematuria_false:7240a8fb` | `haematuria_false` | -- | false | 0/56 | 0.0% | null 56 |
| `haematuria_false:c0157f0d` | `haematuria_false` | -- | false | 0/56 | 0.0% | null 56 |
| `haematuria_false:cb3cb6e6` | `haematuria_false` | -- | false | 0/56 | 0.0% | null 56 |
| `haematuria_false:d9d4737d` | `haematuria_false` | -- | false | 0/56 | 0.0% | null 56 |
| `haematuria_false:4fda0b2c` | `haematuria_false` | -- | false | 0/55 | 0.0% | null 55 |
| `haematuria_false:899e3ed9` | `haematuria_false` | -- | false | 0/55 | 0.0% | null 55 |
| `haematuria_false:66629fb1` | `haematuria_false` | -- | false | 0/54 | 0.0% | null 54 |
| `haematuria_false:9720fe1e` | `haematuria_false` | -- | false | 0/53 | 0.0% | null 53 |
| `haematuria_false:61bf080a` | `haematuria_false` | -- | false | 0/52 | 0.0% | null 52 |
| `haematuria_true:245ed73d` | `haematuria_true` | -- | true | 0/51 | 0.0% | null 51 |
| `haematuria_false:21d7fe6b` | `haematuria_false` | -- | false | 0/49 | 0.0% | null 49 |

*50 further fragments with at least one error are in the JSON sidecar; every fragment is there regardless of score.*

## `length_only`

Logistic regression on token count alone. The direct measurable test of the length leak: anything materially above majority means text length is a usable proxy for the label, which is a fragment-library problem rather than a model one.

Decision-rule margins selected per fold (on each fold's own validation split): 0.0.
Every fold selected margin 0, so the ruled and raw views below are the same decisions. That is a finding rather than a bug: no margin improved macro-F1 without worsening the `null -> true` rate.

*Confusion matrix, raw argmax*

|  | pred false | pred true | pred null | total |
|---|---|---|---|---|
| **truth false** | 39 | 0 | 2440 | 2479 |
| **truth true** | 4 | 0 | 1477 | 1481 |
| **truth null** | 3 | 0 | 6037 | 6040 |
| **total** | 46 | 0 | 9954 | 10000 |

`null -> true`: 0 of 6040 truly-null examples (0.00%).

*Confusion matrix, after the decision rule*

|  | pred false | pred true | pred null | total |
|---|---|---|---|---|
| **truth false** | 39 | 0 | 2440 | 2479 |
| **truth true** | 4 | 0 | 1477 | 1481 |
| **truth null** | 3 | 0 | 6037 | 6040 |
| **total** | 46 | 0 | 9954 | 10000 |

`null -> true`: 0 of 6040 truly-null examples (0.00%).

### Per class, after the decision rule

| class | support | predicted | precision | recall | F1 |
|---|---|---|---|---|---|
| `false` | 2479 | 46 | 84.8% | 1.6% | 3.1% |
| `true` | 1481 | 0 | -- | 0.0% | 0.0% |
| `null` | 6040 | 9954 | 60.6% | 100.0% | 75.5% |

### By label mode

| label mode | n | eff n | accuracy [95% CI] |
|---|---|---|---|
| false | 2479 | **45** | 1.6% [0.4%, 3.2%] |
| null_ambiguous | 3062 | **135** | 100.0% [100.0%, 100.0%] |
| null_structural | 2978 | **1** | 99.9% [99.9%, 99.9%] |
| true | 1481 | **45** | 0.0% [0.0%, 0.0%] |

### By null sub-class

| sub-class | n | eff n | null recall [95% CI] |
|---|---|---|---|
| hedged | 1079 | **45** | 100.0% [100.0%, 100.0%] |
| historical | 1016 | **45** | 100.0% [100.0%, 100.0%] |
| third_party | 967 | **45** | 100.0% [100.0%, 100.0%] |

### By fragment library

| library | n | eff n | accuracy [95% CI] |
|---|---|---|---|
| haematuria_false | 2479 | **45** | 1.6% [0.4%, 3.2%] |
| haematuria_null_hedged | 1079 | **45** | 100.0% [100.0%, 100.0%] |
| haematuria_null_historical | 1016 | **45** | 100.0% [100.0%, 100.0%] |
| haematuria_null_thirdparty | 967 | **45** | 100.0% [100.0%, 100.0%] |
| haematuria_true | 1481 | **45** | 0.0% [0.0%, 0.0%] |
| (none) | 2978 | **1** | 99.9% [99.9%, 99.9%] |

### Per-fragment errors (worst first)

Whether errors are spread thinly across many fragments or piled onto a few is the difference
between "the method is too weak" (model work) and "these specific ideas are not learnable from
the data we have" (library work, and these are the fragments to write more of). No intervals:
a fragment is one cluster, so an interval over its own examples measures nothing.

90 of 225 decisive fragments were got wrong at least once.

`length_only`: 3921 errors across 90 of 225 decisive fragments. Half of them fall on **32** fragments (an even spread would be 45.0); the worst ten carry 17.9% of all errors.

| fragment | library | sub-class | truth | correct | accuracy | predicted as |
|---|---|---|---|---|---|---|
| `haematuria_false:0e98be72` | `haematuria_false` | -- | false | 0/81 | 0.0% | null 81 |
| `haematuria_false:56b8af62` | `haematuria_false` | -- | false | 0/78 | 0.0% | null 78 |
| `haematuria_false:acc7804e` | `haematuria_false` | -- | false | 0/75 | 0.0% | null 75 |
| `haematuria_false:b3fd19df` | `haematuria_false` | -- | false | 0/74 | 0.0% | null 74 |
| `haematuria_true:c0ff5eed` | `haematuria_true` | -- | true | 0/71 | 0.0% | null 71 |
| `haematuria_false:5e090855` | `haematuria_false` | -- | false | 0/66 | 0.0% | null 66 |
| `haematuria_false:64933508` | `haematuria_false` | -- | false | 0/65 | 0.0% | null 65 |
| `haematuria_false:b692c4ce` | `haematuria_false` | -- | false | 0/64 | 0.0% | null 64 |
| `haematuria_false:873d5c5b` | `haematuria_false` | -- | false | 0/63 | 0.0% | null 63 |
| `haematuria_false:b0d93eca` | `haematuria_false` | -- | false | 0/63 | 0.0% | null 63 |
| `haematuria_true:972bb99b` | `haematuria_true` | -- | true | 0/63 | 0.0% | null 63 |
| `haematuria_true:62126789` | `haematuria_true` | -- | true | 0/62 | 0.0% | null 62 |
| `haematuria_false:94644abb` | `haematuria_false` | -- | false | 0/61 | 0.0% | null 61 |
| `haematuria_false:fc6a0704` | `haematuria_false` | -- | false | 0/61 | 0.0% | null 61 |
| `haematuria_true:6fadb8bc` | `haematuria_true` | -- | true | 0/60 | 0.0% | null 60 |
| `haematuria_true:7ea098d1` | `haematuria_true` | -- | true | 0/60 | 0.0% | null 60 |
| `haematuria_true:f2e49699` | `haematuria_true` | -- | true | 0/60 | 0.0% | null 60 |
| `haematuria_false:a84358ef` | `haematuria_false` | -- | false | 0/59 | 0.0% | null 59 |
| `haematuria_true:150663fa` | `haematuria_true` | -- | true | 0/59 | 0.0% | null 59 |
| `haematuria_false:5543da20` | `haematuria_false` | -- | false | 0/58 | 0.0% | null 58 |
| `haematuria_false:cbd9cec5` | `haematuria_false` | -- | false | 0/58 | 0.0% | null 58 |
| `haematuria_false:d163df19` | `haematuria_false` | -- | false | 0/58 | 0.0% | null 58 |
| `haematuria_false:0722271d` | `haematuria_false` | -- | false | 0/57 | 0.0% | null 57 |
| `haematuria_false:58488f8a` | `haematuria_false` | -- | false | 0/57 | 0.0% | null 57 |
| `haematuria_false:a9960bdc` | `haematuria_false` | -- | false | 0/57 | 0.0% | null 57 |
| `haematuria_true:d93fd4ce` | `haematuria_true` | -- | true | 0/57 | 0.0% | null 57 |
| `haematuria_false:0a0b1113` | `haematuria_false` | -- | false | 0/56 | 0.0% | null 56 |
| `haematuria_false:c0157f0d` | `haematuria_false` | -- | false | 0/56 | 0.0% | null 56 |
| `haematuria_false:899e3ed9` | `haematuria_false` | -- | false | 0/55 | 0.0% | null 55 |
| `haematuria_false:66629fb1` | `haematuria_false` | -- | false | 0/54 | 0.0% | null 54 |
| `haematuria_false:9720fe1e` | `haematuria_false` | -- | false | 0/53 | 0.0% | null 53 |
| `haematuria_false:61bf080a` | `haematuria_false` | -- | false | 0/52 | 0.0% | null 52 |
| `haematuria_true:245ed73d` | `haematuria_true` | -- | true | 0/51 | 0.0% | null 51 |
| `haematuria_false:21d7fe6b` | `haematuria_false` | -- | false | 0/49 | 0.0% | null 49 |
| `haematuria_false:bae7d81c` | `haematuria_false` | -- | false | 0/49 | 0.0% | null 49 |
| `haematuria_true:ed9c190f` | `haematuria_true` | -- | true | 0/48 | 0.0% | null 48 |
| `haematuria_false:079edd39` | `haematuria_false` | -- | false | 0/47 | 0.0% | null 47 |
| `haematuria_false:75d091ba` | `haematuria_false` | -- | false | 0/47 | 0.0% | null 47 |
| `haematuria_false:9c317cf3` | `haematuria_false` | -- | false | 0/45 | 0.0% | null 45 |
| `haematuria_false:b1f30cef` | `haematuria_false` | -- | false | 0/45 | 0.0% | null 45 |

*50 further fragments with at least one error are in the JSON sidecar; every fragment is there regardless of score.*

## `tfidf_logreg`

TF-IDF unigrams and bigrams into logistic regression. Tests whether the dataset is keyword-solvable. Its overall accuracy is close to uninformative; the `null_ambiguous` slice is the number that matters.

Decision-rule margins selected per fold (on each fold's own validation split): 0.0, 0.05.

*Confusion matrix, raw argmax*

|  | pred false | pred true | pred null | total |
|---|---|---|---|---|
| **truth false** | 1712 | 60 | 707 | 2479 |
| **truth true** | 124 | 673 | 684 | 1481 |
| **truth null** | 59 | 155 | 5826 | 6040 |
| **total** | 1895 | 888 | 7217 | 10000 |

`null -> true`: 155 of 6040 truly-null examples (2.57%).

*Confusion matrix, after the decision rule*

|  | pred false | pred true | pred null | total |
|---|---|---|---|---|
| **truth false** | 1723 | 49 | 707 | 2479 |
| **truth true** | 124 | 660 | 697 | 1481 |
| **truth null** | 60 | 151 | 5829 | 6040 |
| **total** | 1907 | 860 | 7233 | 10000 |

`null -> true`: 151 of 6040 truly-null examples (2.50%).

### Per class, after the decision rule

| class | support | predicted | precision | recall | F1 |
|---|---|---|---|---|---|
| `false` | 2479 | 1907 | 90.4% | 69.5% | 78.6% |
| `true` | 1481 | 860 | 76.7% | 44.6% | 56.4% |
| `null` | 6040 | 7233 | 80.6% | 96.5% | 87.8% |

### By label mode

| label mode | n | eff n | accuracy [95% CI] |
|---|---|---|---|
| false | 2479 | **45** | 69.5% [59.7%, 79.5%] |
| null_ambiguous | 3062 | **135** | 93.4% [90.0%, 96.2%] |
| null_structural | 2978 | **1** | 99.7% [99.7%, 99.7%] |
| true | 1481 | **45** | 44.6% [32.8%, 56.2%] |

### By null sub-class

| sub-class | n | eff n | null recall [95% CI] |
|---|---|---|---|
| hedged | 1079 | **45** | 89.7% [81.3%, 96.0%] |
| historical | 1016 | **45** | 94.6% [90.8%, 97.7%] |
| third_party | 967 | **45** | 96.3% [92.0%, 99.1%] |

### By fragment library

| library | n | eff n | accuracy [95% CI] |
|---|---|---|---|
| haematuria_false | 2479 | **45** | 69.5% [59.7%, 79.5%] |
| haematuria_null_hedged | 1079 | **45** | 89.7% [81.3%, 96.0%] |
| haematuria_null_historical | 1016 | **45** | 94.6% [90.8%, 97.7%] |
| haematuria_null_thirdparty | 967 | **45** | 96.3% [92.0%, 99.1%] |
| haematuria_true | 1481 | **45** | 44.6% [32.8%, 56.2%] |
| (none) | 2978 | **1** | 99.7% [99.7%, 99.7%] |

### Per-fragment errors (worst first)

Whether errors are spread thinly across many fragments or piled onto a few is the difference
between "the method is too weak" (model work) and "these specific ideas are not learnable from
the data we have" (library work, and these are the fragments to write more of). No intervals:
a fragment is one cluster, so an interval over its own examples measures nothing.

114 of 225 decisive fragments were got wrong at least once.

`tfidf_logreg`: 1779 errors across 114 of 225 decisive fragments. Half of them fall on **21** fragments (an even spread would be 57.0); the worst ten carry 30.7% of all errors.

| fragment | library | sub-class | truth | correct | accuracy | predicted as |
|---|---|---|---|---|---|---|
| `haematuria_false:cbd9cec5` | `haematuria_false` | -- | false | 0/58 | 0.0% | true 16, null 42 |
| `haematuria_true:ed9c190f` | `haematuria_true` | -- | true | 0/48 | 0.0% | false 30, null 18 |
| `haematuria_true:e93a6a13` | `haematuria_true` | -- | true | 0/41 | 0.0% | null 41 |
| `haematuria_true:b8b1c720` | `haematuria_true` | -- | true | 0/34 | 0.0% | null 34 |
| `haematuria_true:5cf89fbc` | `haematuria_true` | -- | true | 0/29 | 0.0% | false 7, null 22 |
| `haematuria_true:f49632f4` | `haematuria_true` | -- | true | 0/26 | 0.0% | null 26 |
| `haematuria_true:e34024ba` | `haematuria_true` | -- | true | 0/22 | 0.0% | null 22 |
| `haematuria_true:9207612b` | `haematuria_true` | -- | true | 0/10 | 0.0% | null 10 |
| `haematuria_false:0e98be72` | `haematuria_false` | -- | false | 2/81 | 2.5% | false 2, null 79 |
| `haematuria_true:16614edd` | `haematuria_true` | -- | true | 1/32 | 3.1% | true 1, null 31 |
| `haematuria_false:d163df19` | `haematuria_false` | -- | false | 2/58 | 3.4% | false 2, true 1, null 55 |
| `haematuria_true:9e0324ed` | `haematuria_true` | -- | true | 1/26 | 3.8% | false 15, true 1, null 10 |
| `haematuria_false:bae7d81c` | `haematuria_false` | -- | false | 2/49 | 4.1% | false 2, true 1, null 46 |
| `haematuria_true:a621d471` | `haematuria_true` | -- | true | 1/22 | 4.5% | false 1, true 1, null 20 |
| `haematuria_false:b471d351` | `haematuria_false` | -- | false | 2/40 | 5.0% | false 2, null 38 |
| `haematuria_false:0a0b1113` | `haematuria_false` | -- | false | 3/56 | 5.4% | false 3, true 1, null 52 |
| `haematuria_true:c0ff5eed` | `haematuria_true` | -- | true | 4/71 | 5.6% | false 10, true 4, null 57 |
| `haematuria_true:08f72e8e` | `haematuria_true` | -- | true | 1/16 | 6.2% | true 1, null 15 |
| `haematuria_true:a87130d9` | `haematuria_true` | -- | true | 2/25 | 8.0% | false 13, true 2, null 10 |
| `haematuria_null_hedged:2e69277b` | `haematuria_null_hedged` | hedged | null | 3/32 | 9.4% | false 29, null 3 |
| `haematuria_true:8b82a179` | `haematuria_true` | -- | true | 2/18 | 11.1% | true 2, null 16 |
| `haematuria_true:fbab8b19` | `haematuria_true` | -- | true | 2/18 | 11.1% | true 2, null 16 |
| `haematuria_true:6fadb8bc` | `haematuria_true` | -- | true | 8/60 | 13.3% | true 8, null 52 |
| `haematuria_true:f9f24e70` | `haematuria_true` | -- | true | 5/36 | 13.9% | false 1, true 5, null 30 |
| `haematuria_null_hedged:58ace8f5` | `haematuria_null_hedged` | hedged | null | 4/25 | 16.0% | true 21, null 4 |
| `haematuria_true:58dc10f0` | `haematuria_true` | -- | true | 4/24 | 16.7% | false 2, true 4, null 18 |
| `haematuria_true:82bde4df` | `haematuria_true` | -- | true | 5/27 | 18.5% | false 21, true 5, null 1 |
| `haematuria_true:5f7823a3` | `haematuria_true` | -- | true | 7/34 | 20.6% | true 7, null 27 |
| `haematuria_null_hedged:0a1e23ec` | `haematuria_null_hedged` | hedged | null | 5/24 | 20.8% | true 19, null 5 |
| `haematuria_false:cb3cb6e6` | `haematuria_false` | -- | false | 12/56 | 21.4% | false 12, null 44 |
| `haematuria_true:cfd65dba` | `haematuria_true` | -- | true | 5/23 | 21.7% | false 5, true 5, null 13 |
| `haematuria_true:b54f9151` | `haematuria_true` | -- | true | 4/18 | 22.2% | false 5, true 4, null 9 |
| `haematuria_null_thirdparty:e1a16c31` | `haematuria_null_thirdparty` | third_party | null | 5/22 | 22.7% | true 17, null 5 |
| `haematuria_false:66629fb1` | `haematuria_false` | -- | false | 14/54 | 25.9% | false 14, true 2, null 38 |
| `haematuria_true:53852edd` | `haematuria_true` | -- | true | 5/15 | 33.3% | true 5, null 10 |
| `haematuria_true:e0480739` | `haematuria_true` | -- | true | 10/28 | 35.7% | false 7, true 10, null 11 |
| `haematuria_true:0a7c2d72` | `haematuria_true` | -- | true | 10/27 | 37.0% | true 10, null 17 |
| `haematuria_false:56b8af62` | `haematuria_false` | -- | false | 35/78 | 44.9% | false 35, true 1, null 42 |
| `haematuria_true:f2e49699` | `haematuria_true` | -- | true | 28/60 | 46.7% | false 5, true 28, null 27 |
| `haematuria_null_hedged:f7dcf718` | `haematuria_null_hedged` | hedged | null | 7/15 | 46.7% | true 8, null 7 |

*74 further fragments with at least one error are in the JSON sidecar; every fragment is there regardless of score.*

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
| historical | 1016 | **45** | 100.0% [100.0%, 100.0%] |
| third_party | 967 | **45** | 100.0% [100.0%, 100.0%] |

### By fragment library

| library | n | eff n | accuracy [95% CI] |
|---|---|---|---|
| haematuria_false | 2479 | **45** | 0.0% [0.0%, 0.0%] |
| haematuria_null_hedged | 1079 | **45** | 100.0% [100.0%, 100.0%] |
| haematuria_null_historical | 1016 | **45** | 100.0% [100.0%, 100.0%] |
| haematuria_null_thirdparty | 967 | **45** | 100.0% [100.0%, 100.0%] |
| haematuria_true | 1481 | **45** | 0.0% [0.0%, 0.0%] |
| (none) | 2978 | **1** | 100.0% [100.0%, 100.0%] |

### Per-fragment errors (worst first)

Whether errors are spread thinly across many fragments or piled onto a few is the difference
between "the method is too weak" (model work) and "these specific ideas are not learnable from
the data we have" (library work, and these are the fragments to write more of). No intervals:
a fragment is one cluster, so an interval over its own examples measures nothing.

90 of 225 decisive fragments were got wrong at least once.

`length_only__shuffled`: 3960 errors across 90 of 225 decisive fragments. Half of them fall on **32** fragments (an even spread would be 45.0); the worst ten carry 18.2% of all errors.

| fragment | library | sub-class | truth | correct | accuracy | predicted as |
|---|---|---|---|---|---|---|
| `haematuria_false:0e98be72` | `haematuria_false` | -- | false | 0/81 | 0.0% | null 81 |
| `haematuria_false:56b8af62` | `haematuria_false` | -- | false | 0/78 | 0.0% | null 78 |
| `haematuria_false:94f9de34` | `haematuria_false` | -- | false | 0/76 | 0.0% | null 76 |
| `haematuria_false:acc7804e` | `haematuria_false` | -- | false | 0/75 | 0.0% | null 75 |
| `haematuria_false:b3fd19df` | `haematuria_false` | -- | false | 0/74 | 0.0% | null 74 |
| `haematuria_true:c0ff5eed` | `haematuria_true` | -- | true | 0/71 | 0.0% | null 71 |
| `haematuria_false:e23c4950` | `haematuria_false` | -- | false | 0/69 | 0.0% | null 69 |
| `haematuria_false:5e090855` | `haematuria_false` | -- | false | 0/66 | 0.0% | null 66 |
| `haematuria_false:64933508` | `haematuria_false` | -- | false | 0/65 | 0.0% | null 65 |
| `haematuria_false:b692c4ce` | `haematuria_false` | -- | false | 0/64 | 0.0% | null 64 |
| `haematuria_false:873d5c5b` | `haematuria_false` | -- | false | 0/63 | 0.0% | null 63 |
| `haematuria_false:b0d93eca` | `haematuria_false` | -- | false | 0/63 | 0.0% | null 63 |
| `haematuria_true:972bb99b` | `haematuria_true` | -- | true | 0/63 | 0.0% | null 63 |
| `haematuria_true:62126789` | `haematuria_true` | -- | true | 0/62 | 0.0% | null 62 |
| `haematuria_false:94644abb` | `haematuria_false` | -- | false | 0/61 | 0.0% | null 61 |
| `haematuria_false:fc6a0704` | `haematuria_false` | -- | false | 0/61 | 0.0% | null 61 |
| `haematuria_true:6fadb8bc` | `haematuria_true` | -- | true | 0/60 | 0.0% | null 60 |
| `haematuria_true:7ea098d1` | `haematuria_true` | -- | true | 0/60 | 0.0% | null 60 |
| `haematuria_true:f2e49699` | `haematuria_true` | -- | true | 0/60 | 0.0% | null 60 |
| `haematuria_false:a84358ef` | `haematuria_false` | -- | false | 0/59 | 0.0% | null 59 |
| `haematuria_true:150663fa` | `haematuria_true` | -- | true | 0/59 | 0.0% | null 59 |
| `haematuria_false:5543da20` | `haematuria_false` | -- | false | 0/58 | 0.0% | null 58 |
| `haematuria_false:cbd9cec5` | `haematuria_false` | -- | false | 0/58 | 0.0% | null 58 |
| `haematuria_false:d163df19` | `haematuria_false` | -- | false | 0/58 | 0.0% | null 58 |
| `haematuria_false:0722271d` | `haematuria_false` | -- | false | 0/57 | 0.0% | null 57 |
| `haematuria_false:58488f8a` | `haematuria_false` | -- | false | 0/57 | 0.0% | null 57 |
| `haematuria_false:a9960bdc` | `haematuria_false` | -- | false | 0/57 | 0.0% | null 57 |
| `haematuria_true:d93fd4ce` | `haematuria_true` | -- | true | 0/57 | 0.0% | null 57 |
| `haematuria_false:0a0b1113` | `haematuria_false` | -- | false | 0/56 | 0.0% | null 56 |
| `haematuria_false:7240a8fb` | `haematuria_false` | -- | false | 0/56 | 0.0% | null 56 |
| `haematuria_false:c0157f0d` | `haematuria_false` | -- | false | 0/56 | 0.0% | null 56 |
| `haematuria_false:cb3cb6e6` | `haematuria_false` | -- | false | 0/56 | 0.0% | null 56 |
| `haematuria_false:d9d4737d` | `haematuria_false` | -- | false | 0/56 | 0.0% | null 56 |
| `haematuria_false:4fda0b2c` | `haematuria_false` | -- | false | 0/55 | 0.0% | null 55 |
| `haematuria_false:899e3ed9` | `haematuria_false` | -- | false | 0/55 | 0.0% | null 55 |
| `haematuria_false:66629fb1` | `haematuria_false` | -- | false | 0/54 | 0.0% | null 54 |
| `haematuria_false:9720fe1e` | `haematuria_false` | -- | false | 0/53 | 0.0% | null 53 |
| `haematuria_false:61bf080a` | `haematuria_false` | -- | false | 0/52 | 0.0% | null 52 |
| `haematuria_true:245ed73d` | `haematuria_true` | -- | true | 0/51 | 0.0% | null 51 |
| `haematuria_false:21d7fe6b` | `haematuria_false` | -- | false | 0/49 | 0.0% | null 49 |

*50 further fragments with at least one error are in the JSON sidecar; every fragment is there regardless of score.*

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
| false | 2479 | **45** | 0.0% [0.0%, 0.0%] |
| null_ambiguous | 3062 | **135** | 100.0% [99.9%, 100.0%] |
| null_structural | 2978 | **1** | 100.0% [100.0%, 100.0%] |
| true | 1481 | **45** | 0.0% [0.0%, 0.0%] |

### By null sub-class

| sub-class | n | eff n | null recall [95% CI] |
|---|---|---|---|
| hedged | 1079 | **45** | 99.9% [99.7%, 100.0%] |
| historical | 1016 | **45** | 100.0% [100.0%, 100.0%] |
| third_party | 967 | **45** | 100.0% [100.0%, 100.0%] |

### By fragment library

| library | n | eff n | accuracy [95% CI] |
|---|---|---|---|
| haematuria_false | 2479 | **45** | 0.0% [0.0%, 0.0%] |
| haematuria_null_hedged | 1079 | **45** | 99.9% [99.7%, 100.0%] |
| haematuria_null_historical | 1016 | **45** | 100.0% [100.0%, 100.0%] |
| haematuria_null_thirdparty | 967 | **45** | 100.0% [100.0%, 100.0%] |
| haematuria_true | 1481 | **45** | 0.0% [0.0%, 0.0%] |
| (none) | 2978 | **1** | 100.0% [100.0%, 100.0%] |

### Per-fragment errors (worst first)

Whether errors are spread thinly across many fragments or piled onto a few is the difference
between "the method is too weak" (model work) and "these specific ideas are not learnable from
the data we have" (library work, and these are the fragments to write more of). No intervals:
a fragment is one cluster, so an interval over its own examples measures nothing.

91 of 225 decisive fragments were got wrong at least once.

`tfidf_logreg__shuffled`: 3961 errors across 91 of 225 decisive fragments. Half of them fall on **32** fragments (an even spread would be 45.5); the worst ten carry 18.2% of all errors.

| fragment | library | sub-class | truth | correct | accuracy | predicted as |
|---|---|---|---|---|---|---|
| `haematuria_false:0e98be72` | `haematuria_false` | -- | false | 0/81 | 0.0% | null 81 |
| `haematuria_false:56b8af62` | `haematuria_false` | -- | false | 0/78 | 0.0% | null 78 |
| `haematuria_false:94f9de34` | `haematuria_false` | -- | false | 0/76 | 0.0% | null 76 |
| `haematuria_false:acc7804e` | `haematuria_false` | -- | false | 0/75 | 0.0% | null 75 |
| `haematuria_false:b3fd19df` | `haematuria_false` | -- | false | 0/74 | 0.0% | null 74 |
| `haematuria_true:c0ff5eed` | `haematuria_true` | -- | true | 0/71 | 0.0% | null 71 |
| `haematuria_false:e23c4950` | `haematuria_false` | -- | false | 0/69 | 0.0% | null 69 |
| `haematuria_false:5e090855` | `haematuria_false` | -- | false | 0/66 | 0.0% | null 66 |
| `haematuria_false:64933508` | `haematuria_false` | -- | false | 0/65 | 0.0% | null 65 |
| `haematuria_false:b692c4ce` | `haematuria_false` | -- | false | 0/64 | 0.0% | null 64 |
| `haematuria_false:873d5c5b` | `haematuria_false` | -- | false | 0/63 | 0.0% | null 63 |
| `haematuria_false:b0d93eca` | `haematuria_false` | -- | false | 0/63 | 0.0% | null 63 |
| `haematuria_true:972bb99b` | `haematuria_true` | -- | true | 0/63 | 0.0% | null 63 |
| `haematuria_true:62126789` | `haematuria_true` | -- | true | 0/62 | 0.0% | null 62 |
| `haematuria_false:94644abb` | `haematuria_false` | -- | false | 0/61 | 0.0% | null 61 |
| `haematuria_false:fc6a0704` | `haematuria_false` | -- | false | 0/61 | 0.0% | null 61 |
| `haematuria_true:6fadb8bc` | `haematuria_true` | -- | true | 0/60 | 0.0% | null 60 |
| `haematuria_true:7ea098d1` | `haematuria_true` | -- | true | 0/60 | 0.0% | null 60 |
| `haematuria_true:f2e49699` | `haematuria_true` | -- | true | 0/60 | 0.0% | null 60 |
| `haematuria_false:a84358ef` | `haematuria_false` | -- | false | 0/59 | 0.0% | null 59 |
| `haematuria_true:150663fa` | `haematuria_true` | -- | true | 0/59 | 0.0% | null 59 |
| `haematuria_false:5543da20` | `haematuria_false` | -- | false | 0/58 | 0.0% | null 58 |
| `haematuria_false:cbd9cec5` | `haematuria_false` | -- | false | 0/58 | 0.0% | null 58 |
| `haematuria_false:d163df19` | `haematuria_false` | -- | false | 0/58 | 0.0% | null 58 |
| `haematuria_false:0722271d` | `haematuria_false` | -- | false | 0/57 | 0.0% | null 57 |
| `haematuria_false:58488f8a` | `haematuria_false` | -- | false | 0/57 | 0.0% | null 57 |
| `haematuria_false:a9960bdc` | `haematuria_false` | -- | false | 0/57 | 0.0% | null 57 |
| `haematuria_true:d93fd4ce` | `haematuria_true` | -- | true | 0/57 | 0.0% | null 57 |
| `haematuria_false:0a0b1113` | `haematuria_false` | -- | false | 0/56 | 0.0% | null 56 |
| `haematuria_false:7240a8fb` | `haematuria_false` | -- | false | 0/56 | 0.0% | null 56 |
| `haematuria_false:c0157f0d` | `haematuria_false` | -- | false | 0/56 | 0.0% | null 56 |
| `haematuria_false:cb3cb6e6` | `haematuria_false` | -- | false | 0/56 | 0.0% | null 56 |
| `haematuria_false:d9d4737d` | `haematuria_false` | -- | false | 0/56 | 0.0% | null 56 |
| `haematuria_false:4fda0b2c` | `haematuria_false` | -- | false | 0/55 | 0.0% | null 55 |
| `haematuria_false:899e3ed9` | `haematuria_false` | -- | false | 0/55 | 0.0% | null 55 |
| `haematuria_false:66629fb1` | `haematuria_false` | -- | false | 0/54 | 0.0% | null 54 |
| `haematuria_false:9720fe1e` | `haematuria_false` | -- | false | 0/53 | 0.0% | null 53 |
| `haematuria_false:61bf080a` | `haematuria_false` | -- | false | 0/52 | 0.0% | null 52 |
| `haematuria_true:245ed73d` | `haematuria_true` | -- | true | 0/51 | 0.0% | null 51 |
| `haematuria_false:21d7fe6b` | `haematuria_false` | -- | false | 0/49 | 0.0% | null 49 |

*51 further fragments with at least one error are in the JSON sidecar; every fragment is there regardless of score.*

## `arm_b_finetune@A1_single`

`roberta-base` with **every layer unfrozen**, mean-pooled, with the same `Linear(768, 3)` head -- 110M trainable parameters against Arm A's 2,307. Three epochs at batch 32, learning rate 2e-5, 10% linear warmup, AdamW, fp32. No gradient checkpointing, no 8-bit optimiser, no LoRA, no gradient accumulation: the full model fits in 12GB with room to spare, so anything that reads like a compute compromise would be a mistake rather than a saving. This is the arm that separates "the fragment libraries are the bottleneck" from "the method is too weak": if a fully fine-tuned encoder still cannot read third-party attribution, tense or metaphor, the limit is in the ideas the libraries contain and the fix is library work, not model work.

Decision-rule margins selected per fold (on each fold's own validation split): 0.0, 0.8, 0.85, 0.9.

*Confusion matrix, raw argmax*

|  | pred false | pred true | pred null | total |
|---|---|---|---|---|
| **truth false** | 2274 | 98 | 107 | 2479 |
| **truth true** | 0 | 1298 | 183 | 1481 |
| **truth null** | 63 | 168 | 5809 | 6040 |
| **total** | 2337 | 1564 | 6099 | 10000 |

`null -> true`: 168 of 6040 truly-null examples (2.78%).

*Confusion matrix, after the decision rule*

|  | pred false | pred true | pred null | total |
|---|---|---|---|---|
| **truth false** | 2282 | 86 | 111 | 2479 |
| **truth true** | 0 | 1283 | 198 | 1481 |
| **truth null** | 64 | 141 | 5835 | 6040 |
| **total** | 2346 | 1510 | 6144 | 10000 |

`null -> true`: 141 of 6040 truly-null examples (2.33%).

### Per class, after the decision rule

| class | support | predicted | precision | recall | F1 |
|---|---|---|---|---|---|
| `false` | 2479 | 2346 | 97.3% | 92.1% | 94.6% |
| `true` | 1481 | 1510 | 85.0% | 86.6% | 85.8% |
| `null` | 6040 | 6144 | 95.0% | 96.6% | 95.8% |

### By label mode

| label mode | n | eff n | accuracy [95% CI] |
|---|---|---|---|
| false | 2479 | **45** | 92.1% [84.0%, 98.3%] |
| null_ambiguous | 3062 | **135** | 93.3% [89.0%, 97.0%] |
| null_structural | 2978 | **1** | 100.0% [100.0%, 100.0%] |
| true | 1481 | **45** | 86.6% [75.9%, 95.4%] |

### By null sub-class

| sub-class | n | eff n | null recall [95% CI] |
|---|---|---|---|
| hedged | 1079 | **45** | 84.2% [74.4%, 92.3%] |
| historical | 1016 | **45** | 96.7% [89.9%, 100.0%] |
| third_party | 967 | **45** | 100.0% [100.0%, 100.0%] |

### By fragment library

| library | n | eff n | accuracy [95% CI] |
|---|---|---|---|
| haematuria_false | 2479 | **45** | 92.1% [84.0%, 98.3%] |
| haematuria_null_hedged | 1079 | **45** | 84.2% [74.4%, 92.3%] |
| haematuria_null_historical | 1016 | **45** | 96.7% [89.9%, 100.0%] |
| haematuria_null_thirdparty | 967 | **45** | 100.0% [100.0%, 100.0%] |
| haematuria_true | 1481 | **45** | 86.6% [75.9%, 95.4%] |
| (none) | 2978 | **1** | 100.0% [100.0%, 100.0%] |

### Per-fragment errors (worst first)

Whether errors are spread thinly across many fragments or piled onto a few is the difference
between "the method is too weak" (model work) and "these specific ideas are not learnable from
the data we have" (library work, and these are the fragments to write more of). No intervals:
a fragment is one cluster, so an interval over its own examples measures nothing.

30 of 225 decisive fragments were got wrong at least once.

`arm_b_finetune@A1_single`: 600 errors across 30 of 225 decisive fragments. Half of them fall on **7** fragments (an even spread would be 15.0); the worst ten carry 67.2% of all errors.

| fragment | library | sub-class | truth | correct | accuracy | predicted as |
|---|---|---|---|---|---|---|
| `haematuria_true:6fadb8bc` | `haematuria_true` | -- | true | 0/60 | 0.0% | null 60 |
| `haematuria_false:d163df19` | `haematuria_false` | -- | false | 0/58 | 0.0% | null 58 |
| `haematuria_false:b471d351` | `haematuria_false` | -- | false | 0/40 | 0.0% | true 40 |
| `haematuria_false:eaac464c` | `haematuria_false` | -- | false | 0/39 | 0.0% | true 14, null 25 |
| `haematuria_null_hedged:ad81f888` | `haematuria_null_hedged` | hedged | null | 0/28 | 0.0% | true 28 |
| `haematuria_true:a87130d9` | `haematuria_true` | -- | true | 0/25 | 0.0% | null 25 |
| `haematuria_null_hedged:740e7688` | `haematuria_null_hedged` | hedged | null | 0/21 | 0.0% | false 21 |
| `haematuria_null_hedged:dc7c4c42` | `haematuria_null_hedged` | hedged | null | 0/21 | 0.0% | false 21 |
| `haematuria_true:9207612b` | `haematuria_true` | -- | true | 0/10 | 0.0% | null 10 |
| `haematuria_false:cb3cb6e6` | `haematuria_false` | -- | false | 1/56 | 1.8% | false 1, true 29, null 26 |
| `haematuria_true:e93a6a13` | `haematuria_true` | -- | true | 1/41 | 2.4% | true 1, null 40 |
| `haematuria_null_historical:7ddf228a` | `haematuria_null_historical` | historical | null | 4/38 | 10.5% | true 34, null 4 |
| `haematuria_true:5cf89fbc` | `haematuria_true` | -- | true | 5/29 | 17.2% | true 5, null 24 |
| `haematuria_null_hedged:d64cf17c` | `haematuria_null_hedged` | hedged | null | 5/23 | 21.7% | true 18, null 5 |
| `haematuria_null_hedged:4384f747` | `haematuria_null_hedged` | hedged | null | 10/30 | 33.3% | true 20, null 10 |
| `haematuria_true:fbab8b19` | `haematuria_true` | -- | true | 6/18 | 33.3% | true 6, null 12 |
| `haematuria_null_hedged:211cfe81` | `haematuria_null_hedged` | hedged | null | 5/15 | 33.3% | true 10, null 5 |
| `haematuria_null_hedged:0a1e23ec` | `haematuria_null_hedged` | hedged | null | 9/24 | 37.5% | true 15, null 9 |
| `haematuria_null_hedged:b46c1780` | `haematuria_null_hedged` | hedged | null | 9/23 | 39.1% | false 5, true 9, null 9 |
| `haematuria_null_hedged:8524c012` | `haematuria_null_hedged` | hedged | null | 12/29 | 41.4% | false 17, null 12 |
| `haematuria_true:b8b1c720` | `haematuria_true` | -- | true | 18/34 | 52.9% | true 18, null 16 |
| `haematuria_true:e34024ba` | `haematuria_true` | -- | true | 17/22 | 77.3% | true 17, null 5 |
| `haematuria_null_hedged:2e69277b` | `haematuria_null_hedged` | hedged | null | 25/32 | 78.1% | true 7, null 25 |
| `haematuria_true:a621d471` | `haematuria_true` | -- | true | 20/22 | 90.9% | true 20, null 2 |
| `haematuria_true:2da78bb9` | `haematuria_true` | -- | true | 28/30 | 93.3% | true 28, null 2 |
| `haematuria_true:08f72e8e` | `haematuria_true` | -- | true | 15/16 | 93.8% | true 15, null 1 |
| `haematuria_false:d1664e2b` | `haematuria_false` | -- | false | 33/35 | 94.3% | false 33, true 2 |
| `haematuria_false:899e3ed9` | `haematuria_false` | -- | false | 53/55 | 96.4% | false 53, null 2 |
| `haematuria_true:6773fb2e` | `haematuria_true` | -- | true | 33/34 | 97.1% | true 33, null 1 |
| `haematuria_false:0fb96680` | `haematuria_false` | -- | false | 40/41 | 97.6% | false 40, true 1 |

## `arm_b_finetune@A2_volume`

`roberta-base` with **every layer unfrozen**, mean-pooled, with the same `Linear(768, 3)` head -- 110M trainable parameters against Arm A's 2,307. Three epochs at batch 32, learning rate 2e-5, 10% linear warmup, AdamW, fp32. No gradient checkpointing, no 8-bit optimiser, no LoRA, no gradient accumulation: the full model fits in 12GB with room to spare, so anything that reads like a compute compromise would be a mistake rather than a saving. This is the arm that separates "the fragment libraries are the bottleneck" from "the method is too weak": if a fully fine-tuned encoder still cannot read third-party attribution, tense or metaphor, the limit is in the ideas the libraries contain and the fix is library work, not model work.

Decision-rule margins selected per fold (on each fold's own validation split): 0.0, 0.75, 0.85, 0.9.

*Confusion matrix, raw argmax*

|  | pred false | pred true | pred null | total |
|---|---|---|---|---|
| **truth false** | 2323 | 109 | 94 | 2526 |
| **truth true** | 20 | 1360 | 88 | 1468 |
| **truth null** | 42 | 177 | 5787 | 6006 |
| **total** | 2385 | 1646 | 5969 | 10000 |

`null -> true`: 177 of 6006 truly-null examples (2.95%).

*Confusion matrix, after the decision rule*

|  | pred false | pred true | pred null | total |
|---|---|---|---|---|
| **truth false** | 2327 | 98 | 101 | 2526 |
| **truth true** | 20 | 1356 | 92 | 1468 |
| **truth null** | 45 | 156 | 5805 | 6006 |
| **total** | 2392 | 1610 | 5998 | 10000 |

`null -> true`: 156 of 6006 truly-null examples (2.60%).

### Per class, after the decision rule

| class | support | predicted | precision | recall | F1 |
|---|---|---|---|---|---|
| `false` | 2526 | 2392 | 97.3% | 92.1% | 94.6% |
| `true` | 1468 | 1610 | 84.2% | 92.4% | 88.1% |
| `null` | 6006 | 5998 | 96.8% | 96.7% | 96.7% |

### By label mode

| label mode | n | eff n | accuracy [95% CI] |
|---|---|---|---|
| false | 2526 | **45** | 92.1% [84.1%, 98.7%] |
| null_ambiguous | 2959 | **135** | 93.7% [89.2%, 97.5%] |
| null_structural | 3047 | **1** | 99.5% [99.5%, 99.5%] |
| true | 1468 | **45** | 92.4% [82.9%, 99.3%] |

### By null sub-class

| sub-class | n | eff n | null recall [95% CI] |
|---|---|---|---|
| hedged | 1044 | **45** | 85.2% [73.5%, 94.8%] |
| historical | 977 | **45** | 97.0% [90.9%, 100.0%] |
| third_party | 938 | **45** | 99.6% [99.0%, 100.0%] |

### By fragment library

| library | n | eff n | accuracy [95% CI] |
|---|---|---|---|
| haematuria_false | 2526 | **45** | 92.1% [84.1%, 98.7%] |
| haematuria_null_hedged | 1044 | **45** | 85.2% [73.5%, 94.8%] |
| haematuria_null_historical | 977 | **45** | 97.0% [90.9%, 100.0%] |
| haematuria_null_thirdparty | 938 | **45** | 99.6% [99.0%, 100.0%] |
| haematuria_true | 1468 | **45** | 92.4% [82.9%, 99.3%] |
| (none) | 3047 | **1** | 99.5% [99.5%, 99.5%] |

### Per-fragment errors (worst first)

Whether errors are spread thinly across many fragments or piled onto a few is the difference
between "the method is too weak" (model work) and "these specific ideas are not learnable from
the data we have" (library work, and these are the fragments to write more of). No intervals:
a fragment is one cluster, so an interval over its own examples measures nothing.

23 of 225 decisive fragments were got wrong at least once.

`arm_b_finetune@A2_volume`: 498 errors across 23 of 225 decisive fragments. Half of them fall on **5** fragments (an even spread would be 11.5); the worst ten carry 80.7% of all errors.

| fragment | library | sub-class | truth | correct | accuracy | predicted as |
|---|---|---|---|---|---|---|
| `haematuria_false:d163df19` | `haematuria_false` | -- | false | 0/69 | 0.0% | null 69 |
| `haematuria_false:b471d351` | `haematuria_false` | -- | false | 0/44 | 0.0% | true 44 |
| `haematuria_null_hedged:ad81f888` | `haematuria_null_hedged` | hedged | null | 0/39 | 0.0% | true 39 |
| `haematuria_null_hedged:0a1e23ec` | `haematuria_null_hedged` | hedged | null | 0/32 | 0.0% | true 32 |
| `haematuria_true:9207612b` | `haematuria_true` | -- | true | 0/23 | 0.0% | null 23 |
| `haematuria_null_hedged:dc7c4c42` | `haematuria_null_hedged` | hedged | null | 0/21 | 0.0% | false 21 |
| `haematuria_null_hedged:b46c1780` | `haematuria_null_hedged` | hedged | null | 0/18 | 0.0% | false 18 |
| `haematuria_null_hedged:d64cf17c` | `haematuria_null_hedged` | hedged | null | 0/16 | 0.0% | true 16 |
| `haematuria_true:6fadb8bc` | `haematuria_true` | -- | true | 1/60 | 1.7% | true 1, null 59 |
| `haematuria_false:cb3cb6e6` | `haematuria_false` | -- | false | 9/63 | 14.3% | false 9, true 51, null 3 |
| `haematuria_null_historical:7ddf228a` | `haematuria_null_historical` | historical | null | 6/35 | 17.1% | true 29, null 6 |
| `haematuria_true:08f72e8e` | `haematuria_true` | -- | true | 7/27 | 25.9% | false 20, true 7 |
| `haematuria_false:eaac464c` | `haematuria_false` | -- | false | 14/46 | 30.4% | false 14, true 3, null 29 |
| `haematuria_null_hedged:64409bb8` | `haematuria_null_hedged` | hedged | null | 8/26 | 30.8% | true 18, null 8 |
| `haematuria_null_hedged:740e7688` | `haematuria_null_hedged` | hedged | null | 6/13 | 46.2% | false 6, true 1, null 6 |
| `haematuria_true:e93a6a13` | `haematuria_true` | -- | true | 18/27 | 66.7% | true 18, null 9 |
| `haematuria_null_thirdparty:e1a16c31` | `haematuria_null_thirdparty` | third_party | null | 20/22 | 90.9% | true 2, null 20 |
| `haematuria_null_hedged:211cfe81` | `haematuria_null_hedged` | hedged | null | 12/13 | 92.3% | true 1, null 12 |
| `haematuria_null_thirdparty:60839b8c` | `haematuria_null_thirdparty` | third_party | null | 22/23 | 95.7% | true 1, null 22 |
| `haematuria_null_hedged:79f3c50f` | `haematuria_null_hedged` | hedged | null | 24/25 | 96.0% | true 1, null 24 |
| `haematuria_true:fbab8b19` | `haematuria_true` | -- | true | 25/26 | 96.2% | true 25, null 1 |
| `haematuria_null_hedged:c61a8962` | `haematuria_null_hedged` | hedged | null | 28/29 | 96.6% | true 1, null 28 |
| `haematuria_null_thirdparty:70fdf138` | `haematuria_null_thirdparty` | third_party | null | 28/29 | 96.6% | true 1, null 28 |

## `arm_b_finetune@A3_joint`

`roberta-base` with **every layer unfrozen**, mean-pooled, with the same `Linear(768, 3)` head -- 110M trainable parameters against Arm A's 2,307. Three epochs at batch 32, learning rate 2e-5, 10% linear warmup, AdamW, fp32. No gradient checkpointing, no 8-bit optimiser, no LoRA, no gradient accumulation: the full model fits in 12GB with room to spare, so anything that reads like a compute compromise would be a mistake rather than a saving. This is the arm that separates "the fragment libraries are the bottleneck" from "the method is too weak": if a fully fine-tuned encoder still cannot read third-party attribution, tense or metaphor, the limit is in the ideas the libraries contain and the fix is library work, not model work. **Joint multi-head training**: 6 heads sharing one encoder (dysuria_present, fever_present, flank_pain_present, haematuria_present, nocturia_present, urinary_frequency_present). Epoch selection uses DD6's unweighted mean of every head's own validation macro-F1, so this signal's stopping point may differ from a single-signal run's own best epoch. Each head's margin is chosen independently on its own validation split -- no cross-head trade.

Decision-rule margins selected per fold (on each fold's own validation split): 0.0, 0.55, 0.6, 0.9.

*Confusion matrix, raw argmax*

|  | pred false | pred true | pred null | total |
|---|---|---|---|---|
| **truth false** | 2377 | 58 | 44 | 2479 |
| **truth true** | 20 | 1404 | 57 | 1481 |
| **truth null** | 87 | 119 | 5834 | 6040 |
| **total** | 2484 | 1581 | 5935 | 10000 |

`null -> true`: 119 of 6040 truly-null examples (1.97%).

*Confusion matrix, after the decision rule*

|  | pred false | pred true | pred null | total |
|---|---|---|---|---|
| **truth false** | 2377 | 58 | 44 | 2479 |
| **truth true** | 22 | 1392 | 67 | 1481 |
| **truth null** | 88 | 97 | 5855 | 6040 |
| **total** | 2487 | 1547 | 5966 | 10000 |

`null -> true`: 97 of 6040 truly-null examples (1.61%).

### Per class, after the decision rule

| class | support | predicted | precision | recall | F1 |
|---|---|---|---|---|---|
| `false` | 2479 | 2487 | 95.6% | 95.9% | 95.7% |
| `true` | 1481 | 1547 | 90.0% | 94.0% | 91.9% |
| `null` | 6040 | 5966 | 98.1% | 96.9% | 97.5% |

### By label mode

| label mode | n | eff n | accuracy [95% CI] |
|---|---|---|---|
| false | 2479 | **45** | 95.9% [89.9%, 100.0%] |
| null_ambiguous | 3062 | **135** | 94.6% [90.8%, 97.7%] |
| null_structural | 2978 | **1** | 99.4% [99.4%, 99.4%] |
| true | 1481 | **45** | 94.0% [85.1%, 100.0%] |

### By null sub-class

| sub-class | n | eff n | null recall [95% CI] |
|---|---|---|---|
| hedged | 1079 | **45** | 87.3% [77.4%, 95.1%] |
| historical | 1016 | **45** | 98.9% [97.3%, 100.0%] |
| third_party | 967 | **45** | 98.1% [94.3%, 100.0%] |

### By fragment library

| library | n | eff n | accuracy [95% CI] |
|---|---|---|---|
| haematuria_false | 2479 | **45** | 95.9% [89.9%, 100.0%] |
| haematuria_null_hedged | 1079 | **45** | 87.3% [77.4%, 95.1%] |
| haematuria_null_historical | 1016 | **45** | 98.9% [97.3%, 100.0%] |
| haematuria_null_thirdparty | 967 | **45** | 98.1% [94.3%, 100.0%] |
| haematuria_true | 1481 | **45** | 94.0% [85.1%, 100.0%] |
| (none) | 2978 | **1** | 99.4% [99.4%, 99.4%] |

### Per-fragment errors (worst first)

Whether errors are spread thinly across many fragments or piled onto a few is the difference
between "the method is too weak" (model work) and "these specific ideas are not learnable from
the data we have" (library work, and these are the fragments to write more of). No intervals:
a fragment is one cluster, so an interval over its own examples measures nothing.

22 of 225 decisive fragments were got wrong at least once.

`arm_b_finetune@A3_joint`: 357 errors across 22 of 225 decisive fragments. Half of them fall on **4** fragments (an even spread would be 11.0); the worst ten carry 86.8% of all errors.

| fragment | library | sub-class | truth | correct | accuracy | predicted as |
|---|---|---|---|---|---|---|
| `haematuria_false:cb3cb6e6` | `haematuria_false` | -- | false | 0/56 | 0.0% | true 56 |
| `haematuria_null_hedged:ad81f888` | `haematuria_null_hedged` | hedged | null | 0/28 | 0.0% | true 28 |
| `haematuria_null_hedged:0a1e23ec` | `haematuria_null_hedged` | hedged | null | 0/24 | 0.0% | true 24 |
| `haematuria_null_hedged:dc7c4c42` | `haematuria_null_hedged` | hedged | null | 0/21 | 0.0% | false 19, true 2 |
| `haematuria_null_hedged:f5ac0bee` | `haematuria_null_hedged` | hedged | null | 0/14 | 0.0% | false 14 |
| `haematuria_true:9207612b` | `haematuria_true` | -- | true | 0/10 | 0.0% | null 10 |
| `haematuria_true:6fadb8bc` | `haematuria_true` | -- | true | 3/60 | 5.0% | true 3, null 57 |
| `haematuria_null_hedged:8524c012` | `haematuria_null_hedged` | hedged | null | 2/29 | 6.9% | false 27, null 2 |
| `haematuria_null_thirdparty:e1a16c31` | `haematuria_null_thirdparty` | third_party | null | 5/22 | 22.7% | true 17, null 5 |
| `haematuria_false:d163df19` | `haematuria_false` | -- | false | 14/58 | 24.1% | false 14, null 44 |
| `haematuria_true:6773fb2e` | `haematuria_true` | -- | true | 12/34 | 35.3% | false 22, true 12 |
| `haematuria_null_hedged:58ace8f5` | `haematuria_null_hedged` | hedged | null | 15/25 | 60.0% | true 10, null 15 |
| `haematuria_null_historical:8a3575e2` | `haematuria_null_historical` | historical | null | 11/17 | 64.7% | false 6, null 11 |
| `haematuria_null_hedged:f1a0ec1e` | `haematuria_null_hedged` | hedged | null | 9/12 | 75.0% | false 3, null 9 |
| `haematuria_null_hedged:b46c1780` | `haematuria_null_hedged` | hedged | null | 19/23 | 82.6% | true 4, null 19 |
| `haematuria_null_hedged:740e7688` | `haematuria_null_hedged` | hedged | null | 18/21 | 85.7% | false 3, null 18 |
| `haematuria_null_historical:7ddf228a` | `haematuria_null_historical` | historical | null | 33/38 | 86.8% | true 5, null 33 |
| `haematuria_null_hedged:f7dcf718` | `haematuria_null_hedged` | hedged | null | 14/15 | 93.3% | true 1, null 14 |
| `haematuria_null_hedged:c9e20ae3` | `haematuria_null_hedged` | hedged | null | 16/17 | 94.1% | false 1, null 16 |
| `haematuria_false:eaac464c` | `haematuria_false` | -- | false | 37/39 | 94.9% | false 37, true 2 |
| `haematuria_null_hedged:39a2b404` | `haematuria_null_hedged` | hedged | null | 33/34 | 97.1% | false 1, null 33 |
| `haematuria_null_thirdparty:7e497073` | `haematuria_null_thirdparty` | third_party | null | 33/34 | 97.1% | false 1, null 33 |

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
| 0 | 10000 | 2000 | 2000 | 0.0 | 60.8% | 60.8% | 26.3% | 0.00% |
| 1 | 10000 | 2000 | 2000 | 0.0 | 60.1% | 60.1% | 25.0% | 0.00% |
| 2 | 10000 | 2000 | 2000 | 0.0 | 60.4% | 60.4% | 25.1% | 0.00% |
| 3 | 10000 | 2000 | 2000 | 0.0 | 61.0% | 61.0% | 25.9% | 0.00% |
| 4 | 10000 | 2000 | 2000 | 0.0 | 61.5% | 61.5% | 28.5% | 0.00% |

### `tfidf_logreg`

| fold | train n | val n | test n | margin | acc (raw) | acc (ruled) | macro-F1 | null->true |
|---|---|---|---|---|---|---|---|---|
| 0 | 10000 | 2000 | 2000 | 0.0 | 80.5% | 80.5% | 70.2% | 6.20% |
| 1 | 10000 | 2000 | 2000 | 0.0 | 79.8% | 79.8% | 71.2% | 1.83% |
| 2 | 10000 | 2000 | 2000 | 0.0 | 81.6% | 81.6% | 74.0% | 0.33% |
| 3 | 10000 | 2000 | 2000 | 0.0 | 80.5% | 80.5% | 71.6% | 2.22% |
| 4 | 10000 | 2000 | 2000 | 0.05 | 88.2% | 88.3% | 83.7% | 1.91% |

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

### `arm_b_finetune@A1_single`

| fold | train n | val n | test n | margin | acc (raw) | acc (ruled) | macro-F1 | null->true |
|---|---|---|---|---|---|---|---|---|
| 0 | 10000 | 2000 | 2000 | 0.85 | 92.0% | 91.8% | 89.0% | 1.24% |
| 1 | 10000 | 2000 | 2000 | 0.9 | 94.1% | 94.2% | 93.5% | 3.08% |
| 2 | 10000 | 2000 | 2000 | 0.8 | 90.3% | 91.5% | 88.8% | 7.37% |
| 3 | 10000 | 2000 | 2000 | 0.0 | 95.7% | 95.7% | 93.7% | 0.00% |
| 4 | 10000 | 2000 | 2000 | 0.9 | 97.0% | 97.0% | 95.3% | 0.00% |

### `arm_b_finetune@A2_volume`

| fold | train n | val n | test n | margin | acc (raw) | acc (ruled) | macro-F1 | null->true |
|---|---|---|---|---|---|---|---|---|
| 0 | 44680 | 2000 | 2000 | 0.85 | 93.5% | 93.5% | 92.5% | 4.33% |
| 1 | 44680 | 2000 | 2000 | 0.9 | 96.4% | 96.8% | 96.7% | 1.61% |
| 2 | 44680 | 2000 | 2000 | 0.9 | 92.5% | 92.8% | 89.9% | 5.45% |
| 3 | 44680 | 2000 | 2000 | 0.0 | 95.1% | 95.1% | 92.0% | 0.00% |
| 4 | 44680 | 2000 | 2000 | 0.75 | 96.1% | 96.2% | 94.5% | 1.41% |

### `arm_b_finetune@A3_joint`

| fold | train n | val n | test n | margin | acc (raw) | acc (ruled) | macro-F1 | null->true |
|---|---|---|---|---|---|---|---|---|
| 0 | 44680 | 2000 | 2000 | 0.6 | 93.9% | 94.1% | 92.5% | 4.22% |
| 1 | 44830 | 2000 | 2000 | 0.55 | 96.0% | 96.1% | 96.3% | 0.50% |
| 2 | 45230 | 2000 | 2000 | 0.0 | 98.2% | 98.2% | 97.6% | 2.73% |
| 3 | 45430 | 2000 | 2000 | 0.0 | 96.4% | 96.4% | 93.8% | 0.58% |
| 4 | 45590 | 2000 | 2000 | 0.9 | 96.3% | 96.4% | 94.9% | 0.00% |

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

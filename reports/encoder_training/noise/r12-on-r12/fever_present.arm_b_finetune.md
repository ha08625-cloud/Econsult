# Encoder training: evaluation report

*Generated 2026-08-31T07:42:03+00:00.*

|  |  |
|---|---|
| signal | `fever_present` |
| folds | `5` |
| generator version | `3` |
| generator base seed | `42` |
| generator seed rule | `base + 100 * fold + {train: 0, val: 1, test: 2}` |
| split salt | `0` |
| dataset dir | `data/synthetic/generated/noise/fever-r12` |
| ruleset | `data/uti1.json` |
| ruleset hash | `325b33068307bc70ca085b27117a90c2ad9e71fac24a80f77c8107d08049bb9f` |
| examples per fold | `train 10000, val 2000, test 2000` |
| shuffle seed | `7` |
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
| trainable | `all layers unfrozen` |
| holdout | `data/realistic/uti1_holdout.labels.tsv -- 67 real submissions, scored after test, selects nothing` |
| artefacts | `models/encoder-noise/r12-on-r12/fever_present/arm_b_finetune` |
| weights | `models/encoder-noise/r12-on-r12/fever_present/arm_b_finetune/weights -- ~440MB per fold, not committed` |
| model revision | `e2da8e2f811d1448a5b465c236feacd80ffbac7b` |
| revision pinned | `False` |
| tokeniser lowercases | `False` |
| tokeniser vocab size | `50265` |
| tokeniser discards casing | `False` |
| cluster tag coverage | `5 of 7 libraries carry cluster markers; 194 of 463 fragments are in libraries with none` |
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

> **Warning: 2 of the 7 libraries behind this run carry no cluster markers at all, so every line in them counts as an independent idea.** Where that is not true -- where several lines are one idea written several ways -- the `eff n` of every slice drawn from those libraries is an **upper bound**, and the confidence intervals below are correspondingly **narrower than the truth**.
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
| `length_only` | baseline | 7022 | **418** | 43.9% [38.8%, 49.1%] | 21.4% [19.1%, 23.9%] | 60.6% | 60.6% +/- 0.3% |
| `tfidf_logreg` | baseline | 7022 | **418** | 72.3% [68.8%, 75.8%] | 69.3% [65.5%, 73.0%] | 80.3% | 80.3% +/- 2.2% |
| `length_only__shuffled` | negative control | 7022 | **418** | 43.6% [38.6%, 48.8%] | 20.2% [18.6%, 21.9%] | 60.4% | 60.4% +/- 0.2% |
| `tfidf_logreg__shuffled` | negative control | 7022 | **418** | 43.2% [38.3%, 48.3%] | 20.4% [18.8%, 22.0%] | 59.7% | 59.7% +/- 0.4% |
| `arm_a_probe` | probe | 7022 | **418** | 74.3% [71.3%, 77.3%] | 71.4% [67.9%, 74.7%] | 81.6% | 81.6% +/- 2.6% |
| `arm_b_finetune` | finetune | 7022 | **418** | 93.3% [91.4%, 95.1%] | 92.7% [90.4%, 94.6%] | 95.2% | 95.2% +/- 3.0% |
| `arm_b_finetune__shuffled` | negative control | 7022 | **418** | 43.6% [38.6%, 48.8%] | 20.2% [18.6%, 21.9%] | 60.4% | 60.4% +/- 0.2% |

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
| `length_only` | -- | 99.5% [98.8%, 100.0%] (eff n 43) | 100.0% [100.0%, 100.0%] (eff n 63) | 100.0% [100.0%, 100.0%] (eff n 36) | 100.0% [100.0%, 100.0%] (eff n 47) | 100.0% [100.0%, 100.0%] (eff n 35) |
| `tfidf_logreg` | -- | 93.4% [89.4%, 97.0%] (eff n 43) | 87.3% [80.0%, 93.6%] (eff n 63) | 90.0% [84.7%, 94.2%] (eff n 36) | 96.4% [94.3%, 98.2%] (eff n 47) | 92.1% [87.8%, 96.1%] (eff n 35) |
| `length_only__shuffled` | -- | 100.0% [100.0%, 100.0%] (eff n 43) | 100.0% [100.0%, 100.0%] (eff n 63) | 100.0% [100.0%, 100.0%] (eff n 36) | 100.0% [100.0%, 100.0%] (eff n 47) | 100.0% [100.0%, 100.0%] (eff n 35) |
| `tfidf_logreg__shuffled` | -- | 97.9% [96.1%, 99.3%] (eff n 43) | 98.9% [98.2%, 99.6%] (eff n 63) | 99.0% [97.9%, 99.8%] (eff n 36) | 98.4% [96.6%, 99.8%] (eff n 47) | 99.4% [98.5%, 100.0%] (eff n 35) |
| `arm_a_probe` | -- | 86.8% [81.2%, 92.0%] (eff n 43) | 76.4% [70.2%, 82.3%] (eff n 63) | 88.3% [83.7%, 92.2%] (eff n 36) | 96.1% [93.8%, 97.9%] (eff n 47) | 94.3% [91.1%, 97.6%] (eff n 35) |
| `arm_b_finetune` | -- | 92.7% [85.9%, 97.9%] (eff n 43) | 87.9% [79.4%, 94.8%] (eff n 63) | 97.5% [93.9%, 99.6%] (eff n 36) | 98.3% [96.2%, 99.7%] (eff n 47) | 99.2% [98.2%, 100.0%] (eff n 35) |
| `arm_b_finetune__shuffled` | -- | 100.0% [100.0%, 100.0%] (eff n 43) | 100.0% [100.0%, 100.0%] (eff n 63) | 100.0% [100.0%, 100.0%] (eff n 36) | 100.0% [100.0%, 100.0%] (eff n 47) | 100.0% [100.0%, 100.0%] (eff n 35) |

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

| signal | null support | `arm_b_finetune` |
|---|---|---|
| `fever_present` | 49 | 14.3% |

### `arm_b_finetune`

Recombination test slice: **n 7022**, **eff n 418** clusters, accuracy 93.3% [91.4%, 95.1%]. Holdout: **n 67** submissions, one observation each, scored by 5 fold models at margins 0.85, 0.9, 0.0, 0.75, 0.0. The two `n`s are printed together because they are not the same kind of number and the second is far the smaller.

| signal | true/false/null | omitted | decisive n | decisive acc (mean +/- sd) | worst-case half-width | all n | all acc (mean +/- sd) | null recall |
|---|---|---|---|---|---|---|---|---|
| `fever_present` | 9/9/49 | 0 | 18 | 64.4% +/- 19.9% | +/-23.1% | 67 | 77.3% +/- 5.6% | 82.0% +/- 14.3% |

`null -> true` on real text, per fold: `fever_present` 3, 7, 15, 1, 9 of 49. This is the cell that invents a symptom into a patient's pre-filled form, counted here on submissions rather than on recombinations.

## Paired on real text

The 67 submissions are the same 67 for every model here, so unlike the recombination
test slice they can be paired: the informative quantity is the submissions two models
disagree about, not the gap between two means. One test per fold, never pooled.

* `majority_class` against `length_only`: not paired -- one or both runs carry no real-text cells for this signal (not scored, or scored before the per-submission decisions were kept).
* `majority_class` against `tfidf_logreg`: not paired -- one or both runs carry no real-text cells for this signal (not scored, or scored before the per-submission decisions were kept).
* `majority_class` against `arm_a_probe`: not paired -- one or both runs carry no real-text cells for this signal (not scored, or scored before the per-submission decisions were kept).
* `majority_class` against `arm_b_finetune`: not paired -- one or both runs carry no real-text cells for this signal (not scored, or scored before the per-submission decisions were kept).
* `length_only` against `tfidf_logreg`: not paired -- one or both runs carry no real-text cells for this signal (not scored, or scored before the per-submission decisions were kept).
* `length_only` against `arm_a_probe`: not paired -- one or both runs carry no real-text cells for this signal (not scored, or scored before the per-submission decisions were kept).
* `length_only` against `arm_b_finetune`: not paired -- one or both runs carry no real-text cells for this signal (not scored, or scored before the per-submission decisions were kept).
* `tfidf_logreg` against `arm_a_probe`: not paired -- one or both runs carry no real-text cells for this signal (not scored, or scored before the per-submission decisions were kept).
* `tfidf_logreg` against `arm_b_finetune`: not paired -- one or both runs carry no real-text cells for this signal (not scored, or scored before the per-submission decisions were kept).
* `arm_a_probe` against `arm_b_finetune`: not paired -- one or both runs carry no real-text cells for this signal (not scored, or scored before the per-submission decisions were kept).

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
| `length_only` | baseline | 3062 | **224** | 99.9% [99.8%, 100.0%] |
| `tfidf_logreg` | baseline | 3062 | **224** | 91.6% [89.2%, 93.7%] |
| `arm_a_probe` | probe | 3062 | **224** | 87.4% [84.8%, 89.7%] |
| `arm_b_finetune` | finetune | 3062 | **224** | 94.4% [91.9%, 96.7%] |

### 2. The same comparison, paired

Two overlapping intervals do not settle whether one model beats another on the same
examples. McNemar does, over the examples the two disagree about -- read it alongside the
intervals above, never instead of them.

| pair | n | a only | b only | p |
|---|---|---|---|---|
| `majority_class` vs `length_only` | 3062 | 3 | 0 | 0.25 |
| `majority_class` vs `tfidf_logreg` | 3062 | 257 | 0 | 8.64e-78 |
| `majority_class` vs `arm_a_probe` | 3062 | 406 | 0 | 1.21e-122 |
| `majority_class` vs `arm_b_finetune` | 3062 | 180 | 0 | 1.31e-54 |
| `length_only` vs `tfidf_logreg` | 3062 | 256 | 2 | 1.44e-73 |
| `length_only` vs `arm_a_probe` | 3062 | 404 | 1 | 9.83e-120 |
| `length_only` vs `arm_b_finetune` | 3062 | 179 | 2 | 1.07e-50 |
| `tfidf_logreg` vs `arm_a_probe` | 3062 | 304 | 155 | 3.19e-12 |
| `tfidf_logreg` vs `arm_b_finetune` | 3062 | 109 | 186 | 8.64e-06 |
| `arm_a_probe` vs `arm_b_finetune` | 3062 | 99 | 325 | 3.58e-29 |

### 3. Where the errors fall

The per-fragment table below, as one number per model. Errors spread thinly across many
fragments say the method is too weak. Errors piled onto a handful say those specific ideas
are not learnable from the data we have -- and the table names them, which is what makes
this the most decision-useful thing in the report.

* `majority_class`: 3960 errors across 194 of 463 decisive fragments. Half of them fall on **71** fragments (an even spread would be 97.0); the worst ten carry 8.9% of all errors.
* `length_only`: 3939 errors across 196 of 463 decisive fragments. Half of them fall on **70** fragments (an even spread would be 98.0); the worst ten carry 8.9% of all errors.
* `tfidf_logreg`: 1945 errors across 257 of 463 decisive fragments. Half of them fall on **50** fragments (an even spread would be 128.5); the worst ten carry 14.1% of all errors.
* `arm_a_probe`: 1803 errors across 291 of 463 decisive fragments. Half of them fall on **57** fragments (an even spread would be 145.5); the worst ten carry 13.0% of all errors.
* `arm_b_finetune`: 468 errors across 97 of 463 decisive fragments. Half of them fall on **17** fragments (an even spread would be 48.5); the worst ten carry 33.3% of all errors.

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

Shuffled-label controls, evaluated on the **unpermuted** test split. A large model will
memorise permuted training labels and drive train loss to zero; that is correct behaviour
and says nothing. Only the test score is the control.

| control | accuracy [95% CI] | macro-F1 [95% CI] |
|---|---|---|
| `length_only__shuffled` | 60.4% [39.9%, 76.5%] | 25.1% [19.0%, 28.9%] |
| `tfidf_logreg__shuffled` | 59.7% [39.6%, 75.5%] | 25.2% [19.2%, 29.0%] |
| `arm_b_finetune__shuffled` | 60.4% [39.9%, 76.5%] | 25.1% [19.0%, 28.9%] |

## Paired comparisons (McNemar, raw argmax)

Exact two-sided McNemar over the examples the two models disagree about. Pairing unit is the
example, not the cluster -- see the limitations.

| pair | slice | n | a only | b only | p |
|---|---|---|---|---|---|
| `majority_class` vs `length_only` | overall | 10000 | 3 | 24 | 4.92e-05 |
| `majority_class` vs `length_only` | null_ambiguous | 3062 | 3 | 0 | 0.25 |
| `majority_class` vs `tfidf_logreg` | overall | 10000 | 286 | 2272 | 0 |
| `majority_class` vs `tfidf_logreg` | null_ambiguous | 3062 | 257 | 0 | 8.64e-78 |
| `majority_class` vs `arm_a_probe` | overall | 10000 | 446 | 2566 | 0 |
| `majority_class` vs `arm_a_probe` | null_ambiguous | 3062 | 406 | 0 | 1.21e-122 |
| `majority_class` vs `arm_b_finetune` | overall | 10000 | 197 | 3674 | 0 |
| `majority_class` vs `arm_b_finetune` | null_ambiguous | 3062 | 180 | 0 | 1.31e-54 |
| `length_only` vs `tfidf_logreg` | overall | 10000 | 285 | 2250 | 0 |
| `length_only` vs `tfidf_logreg` | null_ambiguous | 3062 | 256 | 2 | 1.44e-73 |
| `length_only` vs `arm_a_probe` | overall | 10000 | 460 | 2559 | 0 |
| `length_only` vs `arm_a_probe` | null_ambiguous | 3062 | 404 | 1 | 9.83e-120 |
| `length_only` vs `arm_b_finetune` | overall | 10000 | 196 | 3652 | 0 |
| `length_only` vs `arm_b_finetune` | null_ambiguous | 3062 | 179 | 2 | 1.07e-50 |
| `tfidf_logreg` vs `arm_a_probe` | overall | 10000 | 774 | 908 | 0.00118 |
| `tfidf_logreg` vs `arm_a_probe` | null_ambiguous | 3062 | 304 | 155 | 3.19e-12 |
| `tfidf_logreg` vs `arm_b_finetune` | overall | 10000 | 153 | 1644 | 1.39e-315 |
| `tfidf_logreg` vs `arm_b_finetune` | null_ambiguous | 3062 | 109 | 186 | 8.64e-06 |
| `arm_a_probe` vs `arm_b_finetune` | overall | 10000 | 157 | 1514 | 9.51e-279 |
| `arm_a_probe` vs `arm_b_finetune` | null_ambiguous | 3062 | 99 | 325 | 3.58e-29 |

## What moved, and where

The headline is the least useful output of a model comparison. These two tables are the
useful one: a diffuse lift and a fix to one error family are different findings, and an
aggregate accuracy cannot tell them apart. `spread` is max minus min across the models --
a row where every encoder lands together is a row model choice does not touch.

### By library, accuracy after the decision rule

Worst-performing library first. For a single-class library -- `fever_false` holds only
`false` examples -- accuracy here *is* that class's recall on that library.

| library | n | `majority_class` | `length_only` | `tfidf_logreg` | `arm_a_probe` | `arm_b_finetune` | spread |
|---|---|---|---|---|---|---|---|
| `fever_false` | 2479 | 0.0% | 0.2% | 63.3% | 73.3% | 96.5% | 96.5pp |
| `fever_true` | 1481 | 0.0% | 1.4% | 47.5% | 49.0% | 85.7% | 85.7pp |
| `fever_null_hedged` | 828 | 100.0% | 100.0% | 87.3% | 76.4% | 87.9% | 23.6pp |
| `fever_null_attribution` | 574 | 100.0% | 99.5% | 93.4% | 86.8% | 92.7% | 13.2pp |
| `fever_null_historical` | 511 | 100.0% | 100.0% | 90.0% | 88.3% | 97.5% | 11.7pp |
| `fever_null_thirdparty` | 508 | 100.0% | 100.0% | 92.1% | 94.3% | 99.2% | 7.9pp |
| `fever_null_metaphor` | 641 | 100.0% | 100.0% | 96.4% | 96.1% | 98.3% | 3.9pp |
| `(none)` | 2978 | 100.0% | 100.0% | 99.0% | 98.7% | 99.4% | 1.3pp |

### By fragment, errors

Ordered by the worst model's error count, so the fragments the comparison is about sort
to the top whichever encoder wins. Counts, not rates: these are the sentences a month of
library work would be spent on. The JSON holds every fragment.

| fragment | library | truth | `majority_class` | `length_only` | `tfidf_logreg` | `arm_a_probe` | `arm_b_finetune` | spread |
|---|---|---|---|---|---|---|---|---|
| `fever_false:5a6a9b80` | `fever_false` | false | 40 | 40 | 1 | 7 | 0 | 40 |
| `fever_false:d0ca84a7` | `fever_false` | false | 37 | 37 | 0 | 3 | 0 | 37 |
| `fever_false:24e5c247` | `fever_false` | false | 36 | 36 | 11 | 10 | 1 | 35 |
| `fever_false:a9a0220e` | `fever_false` | false | 36 | 36 | 0 | 0 | 0 | 36 |
| `fever_false:0429068c` | `fever_false` | false | 34 | 34 | 13 | 0 | 0 | 34 |
| `fever_false:17f6c637` | `fever_false` | false | 34 | 34 | 0 | 0 | 0 | 34 |
| `fever_false:9f46e710` | `fever_false` | false | 34 | 34 | 1 | 3 | 0 | 34 |
| `fever_false:fc2ae0f2` | `fever_false` | false | 34 | 34 | 7 | 2 | 1 | 33 |
| `fever_false:5969c6c9` | `fever_false` | false | 33 | 33 | 3 | 9 | 0 | 33 |
| `fever_false:b9076eff` | `fever_false` | false | 33 | 33 | 14 | 20 | 2 | 31 |
| `fever_false:b96ed279` | `fever_false` | false | 33 | 33 | 33 | 17 | 0 | 33 |
| `fever_false:2b944abc` | `fever_false` | false | 32 | 32 | 2 | 2 | 0 | 32 |
| `fever_false:55bf1913` | `fever_false` | false | 32 | 32 | 1 | 0 | 0 | 32 |
| `fever_false:a5b671a1` | `fever_false` | false | 32 | 32 | 19 | 29 | 2 | 30 |
| `fever_false:cdf2609b` | `fever_false` | false | 32 | 32 | 31 | 9 | 1 | 31 |
| `fever_false:8d02bd9e` | `fever_false` | false | 31 | 31 | 22 | 10 | 0 | 31 |
| `fever_false:d5ed3ff1` | `fever_false` | false | 31 | 31 | 17 | 9 | 0 | 31 |
| `fever_false:de0596c4` | `fever_false` | false | 31 | 31 | 14 | 16 | 2 | 29 |
| `fever_false:e2aff3b8` | `fever_false` | false | 31 | 31 | 12 | 7 | 1 | 30 |
| `fever_false:f586e96d` | `fever_false` | false | 31 | 31 | 17 | 16 | 0 | 31 |
| `fever_false:56a45ff1` | `fever_false` | false | 30 | 30 | 3 | 4 | 0 | 30 |
| `fever_false:5c2a065d` | `fever_false` | false | 30 | 30 | 30 | 7 | 26 | 23 |
| `fever_false:c747066d` | `fever_false` | false | 30 | 30 | 5 | 3 | 0 | 30 |
| `fever_false:3a3043ff` | `fever_false` | false | 29 | 29 | 25 | 26 | 4 | 25 |
| `fever_false:463f8189` | `fever_false` | false | 29 | 29 | 1 | 7 | 0 | 29 |
| `fever_false:758d5434` | `fever_false` | false | 29 | 29 | 0 | 0 | 1 | 29 |
| `fever_false:7b64d17a` | `fever_false` | false | 29 | 29 | 16 | 7 | 0 | 29 |
| `fever_false:a4cda1e2` | `fever_false` | false | 29 | 29 | 5 | 0 | 0 | 29 |
| `fever_true:18173593` | `fever_true` | true | 29 | 29 | 20 | 25 | 0 | 29 |
| `fever_true:f3ee0d07` | `fever_true` | true | 29 | 29 | 0 | 0 | 0 | 29 |
| `fever_false:44cd09fd` | `fever_false` | false | 28 | 28 | 28 | 8 | 0 | 28 |
| `fever_false:a6c0d44a` | `fever_false` | false | 28 | 28 | 14 | 1 | 2 | 27 |
| `fever_false:cbf9d7a5` | `fever_false` | false | 28 | 28 | 27 | 21 | 0 | 28 |
| `fever_false:147d5cf0` | `fever_false` | false | 27 | 27 | 12 | 0 | 0 | 27 |
| `fever_false:3de7ecac` | `fever_false` | false | 27 | 27 | 24 | 15 | 0 | 27 |
| `fever_false:43f5b35d` | `fever_false` | false | 27 | 27 | 5 | 0 | 0 | 27 |
| `fever_false:8599e318` | `fever_false` | false | 27 | 27 | 4 | 2 | 0 | 27 |
| `fever_false:e70e24b6` | `fever_false` | false | 27 | 27 | 8 | 20 | 1 | 26 |
| `fever_true:753c7815` | `fever_true` | true | 27 | 27 | 0 | 0 | 0 | 27 |
| `fever_false:033927e6` | `fever_false` | false | 26 | 26 | 26 | 23 | 0 | 26 |

*319 further fragments erred on at least one model; the JSON holds them all.*

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
| attribution | 574 | **43** | 100.0% [100.0%, 100.0%] |
| hedged | 828 | **63** | 100.0% [100.0%, 100.0%] |
| historical | 511 | **36** | 100.0% [100.0%, 100.0%] |
| metaphor | 641 | **47** | 100.0% [100.0%, 100.0%] |
| third_party | 508 | **35** | 100.0% [100.0%, 100.0%] |

### By fragment library

| library | n | eff n | accuracy [95% CI] |
|---|---|---|---|
| fever_false | 2479 | **98** | 0.0% [0.0%, 0.0%] |
| fever_null_attribution | 574 | **43** | 100.0% [100.0%, 100.0%] |
| fever_null_hedged | 828 | **63** | 100.0% [100.0%, 100.0%] |
| fever_null_historical | 511 | **36** | 100.0% [100.0%, 100.0%] |
| fever_null_metaphor | 641 | **47** | 100.0% [100.0%, 100.0%] |
| fever_null_thirdparty | 508 | **35** | 100.0% [100.0%, 100.0%] |
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
| `fever_false:5a6a9b80` | `fever_false` | -- | false | 0/40 | 0.0% | null 40 |
| `fever_false:d0ca84a7` | `fever_false` | -- | false | 0/37 | 0.0% | null 37 |
| `fever_false:24e5c247` | `fever_false` | -- | false | 0/36 | 0.0% | null 36 |
| `fever_false:a9a0220e` | `fever_false` | -- | false | 0/36 | 0.0% | null 36 |
| `fever_false:0429068c` | `fever_false` | -- | false | 0/34 | 0.0% | null 34 |
| `fever_false:17f6c637` | `fever_false` | -- | false | 0/34 | 0.0% | null 34 |
| `fever_false:9f46e710` | `fever_false` | -- | false | 0/34 | 0.0% | null 34 |
| `fever_false:fc2ae0f2` | `fever_false` | -- | false | 0/34 | 0.0% | null 34 |
| `fever_false:5969c6c9` | `fever_false` | -- | false | 0/33 | 0.0% | null 33 |
| `fever_false:b9076eff` | `fever_false` | -- | false | 0/33 | 0.0% | null 33 |
| `fever_false:b96ed279` | `fever_false` | -- | false | 0/33 | 0.0% | null 33 |
| `fever_false:2b944abc` | `fever_false` | -- | false | 0/32 | 0.0% | null 32 |
| `fever_false:55bf1913` | `fever_false` | -- | false | 0/32 | 0.0% | null 32 |
| `fever_false:a5b671a1` | `fever_false` | -- | false | 0/32 | 0.0% | null 32 |
| `fever_false:cdf2609b` | `fever_false` | -- | false | 0/32 | 0.0% | null 32 |
| `fever_false:8d02bd9e` | `fever_false` | -- | false | 0/31 | 0.0% | null 31 |
| `fever_false:d5ed3ff1` | `fever_false` | -- | false | 0/31 | 0.0% | null 31 |
| `fever_false:de0596c4` | `fever_false` | -- | false | 0/31 | 0.0% | null 31 |
| `fever_false:e2aff3b8` | `fever_false` | -- | false | 0/31 | 0.0% | null 31 |
| `fever_false:f586e96d` | `fever_false` | -- | false | 0/31 | 0.0% | null 31 |
| `fever_false:56a45ff1` | `fever_false` | -- | false | 0/30 | 0.0% | null 30 |
| `fever_false:5c2a065d` | `fever_false` | -- | false | 0/30 | 0.0% | null 30 |
| `fever_false:c747066d` | `fever_false` | -- | false | 0/30 | 0.0% | null 30 |
| `fever_false:3a3043ff` | `fever_false` | -- | false | 0/29 | 0.0% | null 29 |
| `fever_false:463f8189` | `fever_false` | -- | false | 0/29 | 0.0% | null 29 |
| `fever_false:758d5434` | `fever_false` | -- | false | 0/29 | 0.0% | null 29 |
| `fever_false:7b64d17a` | `fever_false` | -- | false | 0/29 | 0.0% | null 29 |
| `fever_false:a4cda1e2` | `fever_false` | -- | false | 0/29 | 0.0% | null 29 |
| `fever_true:18173593` | `fever_true` | -- | true | 0/29 | 0.0% | null 29 |
| `fever_true:f3ee0d07` | `fever_true` | -- | true | 0/29 | 0.0% | null 29 |
| `fever_false:44cd09fd` | `fever_false` | -- | false | 0/28 | 0.0% | null 28 |
| `fever_false:a6c0d44a` | `fever_false` | -- | false | 0/28 | 0.0% | null 28 |
| `fever_false:cbf9d7a5` | `fever_false` | -- | false | 0/28 | 0.0% | null 28 |
| `fever_false:147d5cf0` | `fever_false` | -- | false | 0/27 | 0.0% | null 27 |
| `fever_false:3de7ecac` | `fever_false` | -- | false | 0/27 | 0.0% | null 27 |
| `fever_false:43f5b35d` | `fever_false` | -- | false | 0/27 | 0.0% | null 27 |
| `fever_false:8599e318` | `fever_false` | -- | false | 0/27 | 0.0% | null 27 |
| `fever_false:e70e24b6` | `fever_false` | -- | false | 0/27 | 0.0% | null 27 |
| `fever_true:753c7815` | `fever_true` | -- | true | 0/27 | 0.0% | null 27 |
| `fever_false:033927e6` | `fever_false` | -- | false | 0/26 | 0.0% | null 26 |

*154 further fragments with at least one error are in the JSON sidecar; every fragment is there regardless of score.*

## `length_only`

Logistic regression on token count alone. The direct measurable test of the length leak: anything materially above majority means text length is a usable proxy for the label, which is a fragment-library problem rather than a model one.

Decision-rule margins selected per fold (on each fold's own validation split): 0.0.
Every fold selected margin 0, so the ruled and raw views below are the same decisions. That is a finding rather than a bug: no margin improved macro-F1 without worsening the `null -> true` rate.

*Confusion matrix, raw argmax*

|  | pred false | pred true | pred null | total |
|---|---|---|---|---|
| **truth false** | 4 | 0 | 2475 | 2479 |
| **truth true** | 42 | 20 | 1419 | 1481 |
| **truth null** | 3 | 0 | 6037 | 6040 |
| **total** | 49 | 20 | 9931 | 10000 |

`null -> true`: 0 of 6040 truly-null examples (0.00%).

*Confusion matrix, after the decision rule*

|  | pred false | pred true | pred null | total |
|---|---|---|---|---|
| **truth false** | 4 | 0 | 2475 | 2479 |
| **truth true** | 42 | 20 | 1419 | 1481 |
| **truth null** | 3 | 0 | 6037 | 6040 |
| **total** | 49 | 20 | 9931 | 10000 |

`null -> true`: 0 of 6040 truly-null examples (0.00%).

### Per class, after the decision rule

| class | support | predicted | precision | recall | F1 |
|---|---|---|---|---|---|
| `false` | 2479 | 49 | 8.2% | 0.2% | 0.3% |
| `true` | 1481 | 20 | 100.0% | 1.4% | 2.7% |
| `null` | 6040 | 9931 | 60.8% | 100.0% | 75.6% |

### By label mode

| label mode | n | eff n | accuracy [95% CI] |
|---|---|---|---|
| false | 2479 | **98** | 0.2% [0.0%, 0.5%] |
| null_ambiguous | 3062 | **224** | 99.9% [99.8%, 100.0%] |
| null_structural | 2978 | **1** | 100.0% [100.0%, 100.0%] |
| true | 1481 | **96** | 1.4% [0.0%, 4.2%] |

### By null sub-class

| sub-class | n | eff n | null recall [95% CI] |
|---|---|---|---|
| attribution | 574 | **43** | 99.5% [98.8%, 100.0%] |
| hedged | 828 | **63** | 100.0% [100.0%, 100.0%] |
| historical | 511 | **36** | 100.0% [100.0%, 100.0%] |
| metaphor | 641 | **47** | 100.0% [100.0%, 100.0%] |
| third_party | 508 | **35** | 100.0% [100.0%, 100.0%] |

### By fragment library

| library | n | eff n | accuracy [95% CI] |
|---|---|---|---|
| fever_false | 2479 | **98** | 0.2% [0.0%, 0.5%] |
| fever_null_attribution | 574 | **43** | 99.5% [98.8%, 100.0%] |
| fever_null_hedged | 828 | **63** | 100.0% [100.0%, 100.0%] |
| fever_null_historical | 511 | **36** | 100.0% [100.0%, 100.0%] |
| fever_null_metaphor | 641 | **47** | 100.0% [100.0%, 100.0%] |
| fever_null_thirdparty | 508 | **35** | 100.0% [100.0%, 100.0%] |
| fever_true | 1481 | **96** | 1.4% [0.0%, 4.2%] |
| (none) | 2978 | **1** | 100.0% [100.0%, 100.0%] |

### Per-fragment errors (worst first)

Whether errors are spread thinly across many fragments or piled onto a few is the difference
between "the method is too weak" (model work) and "these specific ideas are not learnable from
the data we have" (library work, and these are the fragments to write more of). No intervals:
a fragment is one cluster, so an interval over its own examples measures nothing.

196 of 463 decisive fragments were got wrong at least once.

`length_only`: 3939 errors across 196 of 463 decisive fragments. Half of them fall on **70** fragments (an even spread would be 98.0); the worst ten carry 8.9% of all errors.

| fragment | library | sub-class | truth | correct | accuracy | predicted as |
|---|---|---|---|---|---|---|
| `fever_false:5a6a9b80` | `fever_false` | -- | false | 0/40 | 0.0% | null 40 |
| `fever_false:d0ca84a7` | `fever_false` | -- | false | 0/37 | 0.0% | null 37 |
| `fever_false:24e5c247` | `fever_false` | -- | false | 0/36 | 0.0% | null 36 |
| `fever_false:a9a0220e` | `fever_false` | -- | false | 0/36 | 0.0% | null 36 |
| `fever_false:0429068c` | `fever_false` | -- | false | 0/34 | 0.0% | null 34 |
| `fever_false:17f6c637` | `fever_false` | -- | false | 0/34 | 0.0% | null 34 |
| `fever_false:9f46e710` | `fever_false` | -- | false | 0/34 | 0.0% | null 34 |
| `fever_false:fc2ae0f2` | `fever_false` | -- | false | 0/34 | 0.0% | null 34 |
| `fever_false:5969c6c9` | `fever_false` | -- | false | 0/33 | 0.0% | null 33 |
| `fever_false:b9076eff` | `fever_false` | -- | false | 0/33 | 0.0% | null 33 |
| `fever_false:b96ed279` | `fever_false` | -- | false | 0/33 | 0.0% | null 33 |
| `fever_false:2b944abc` | `fever_false` | -- | false | 0/32 | 0.0% | null 32 |
| `fever_false:55bf1913` | `fever_false` | -- | false | 0/32 | 0.0% | null 32 |
| `fever_false:a5b671a1` | `fever_false` | -- | false | 0/32 | 0.0% | null 32 |
| `fever_false:cdf2609b` | `fever_false` | -- | false | 0/32 | 0.0% | null 32 |
| `fever_false:8d02bd9e` | `fever_false` | -- | false | 0/31 | 0.0% | null 31 |
| `fever_false:d5ed3ff1` | `fever_false` | -- | false | 0/31 | 0.0% | null 31 |
| `fever_false:de0596c4` | `fever_false` | -- | false | 0/31 | 0.0% | null 31 |
| `fever_false:e2aff3b8` | `fever_false` | -- | false | 0/31 | 0.0% | null 31 |
| `fever_false:f586e96d` | `fever_false` | -- | false | 0/31 | 0.0% | null 31 |
| `fever_false:56a45ff1` | `fever_false` | -- | false | 0/30 | 0.0% | null 30 |
| `fever_false:5c2a065d` | `fever_false` | -- | false | 0/30 | 0.0% | null 30 |
| `fever_false:c747066d` | `fever_false` | -- | false | 0/30 | 0.0% | null 30 |
| `fever_false:3a3043ff` | `fever_false` | -- | false | 0/29 | 0.0% | null 29 |
| `fever_false:463f8189` | `fever_false` | -- | false | 0/29 | 0.0% | null 29 |
| `fever_false:758d5434` | `fever_false` | -- | false | 0/29 | 0.0% | null 29 |
| `fever_false:7b64d17a` | `fever_false` | -- | false | 0/29 | 0.0% | null 29 |
| `fever_false:a4cda1e2` | `fever_false` | -- | false | 0/29 | 0.0% | null 29 |
| `fever_true:18173593` | `fever_true` | -- | true | 0/29 | 0.0% | null 29 |
| `fever_true:f3ee0d07` | `fever_true` | -- | true | 0/29 | 0.0% | false 29 |
| `fever_false:44cd09fd` | `fever_false` | -- | false | 0/28 | 0.0% | null 28 |
| `fever_false:a6c0d44a` | `fever_false` | -- | false | 0/28 | 0.0% | null 28 |
| `fever_false:cbf9d7a5` | `fever_false` | -- | false | 0/28 | 0.0% | null 28 |
| `fever_false:147d5cf0` | `fever_false` | -- | false | 0/27 | 0.0% | null 27 |
| `fever_false:3de7ecac` | `fever_false` | -- | false | 0/27 | 0.0% | null 27 |
| `fever_false:43f5b35d` | `fever_false` | -- | false | 0/27 | 0.0% | null 27 |
| `fever_false:8599e318` | `fever_false` | -- | false | 0/27 | 0.0% | null 27 |
| `fever_false:e70e24b6` | `fever_false` | -- | false | 0/27 | 0.0% | null 27 |
| `fever_true:753c7815` | `fever_true` | -- | true | 0/27 | 0.0% | null 27 |
| `fever_false:033927e6` | `fever_false` | -- | false | 0/26 | 0.0% | null 26 |

*156 further fragments with at least one error are in the JSON sidecar; every fragment is there regardless of score.*

## `tfidf_logreg`

TF-IDF unigrams and bigrams into logistic regression. Tests whether the dataset is keyword-solvable. Its overall accuracy is close to uninformative; the `null_ambiguous` slice is the number that matters.

Decision-rule margins selected per fold (on each fold's own validation split): 0.0.
Every fold selected margin 0, so the ruled and raw views below are the same decisions. That is a finding rather than a bug: no margin improved macro-F1 without worsening the `null -> true` rate.

*Confusion matrix, raw argmax*

|  | pred false | pred true | pred null | total |
|---|---|---|---|---|
| **truth false** | 1568 | 122 | 789 | 2479 |
| **truth true** | 128 | 704 | 649 | 1481 |
| **truth null** | 208 | 78 | 5754 | 6040 |
| **total** | 1904 | 904 | 7192 | 10000 |

`null -> true`: 78 of 6040 truly-null examples (1.29%).

*Confusion matrix, after the decision rule*

|  | pred false | pred true | pred null | total |
|---|---|---|---|---|
| **truth false** | 1568 | 122 | 789 | 2479 |
| **truth true** | 128 | 704 | 649 | 1481 |
| **truth null** | 208 | 78 | 5754 | 6040 |
| **total** | 1904 | 904 | 7192 | 10000 |

`null -> true`: 78 of 6040 truly-null examples (1.29%).

### Per class, after the decision rule

| class | support | predicted | precision | recall | F1 |
|---|---|---|---|---|---|
| `false` | 2479 | 1904 | 82.4% | 63.3% | 71.5% |
| `true` | 1481 | 904 | 77.9% | 47.5% | 59.0% |
| `null` | 6040 | 7192 | 80.0% | 95.3% | 87.0% |

### By label mode

| label mode | n | eff n | accuracy [95% CI] |
|---|---|---|---|
| false | 2479 | **98** | 63.3% [56.5%, 69.8%] |
| null_ambiguous | 3062 | **224** | 91.6% [89.2%, 93.7%] |
| null_structural | 2978 | **1** | 99.0% [99.0%, 99.0%] |
| true | 1481 | **96** | 47.5% [39.6%, 55.9%] |

### By null sub-class

| sub-class | n | eff n | null recall [95% CI] |
|---|---|---|---|
| attribution | 574 | **43** | 93.4% [89.4%, 97.0%] |
| hedged | 828 | **63** | 87.3% [80.0%, 93.6%] |
| historical | 511 | **36** | 90.0% [84.7%, 94.2%] |
| metaphor | 641 | **47** | 96.4% [94.3%, 98.2%] |
| third_party | 508 | **35** | 92.1% [87.8%, 96.1%] |

### By fragment library

| library | n | eff n | accuracy [95% CI] |
|---|---|---|---|
| fever_false | 2479 | **98** | 63.3% [56.5%, 69.8%] |
| fever_null_attribution | 574 | **43** | 93.4% [89.4%, 97.0%] |
| fever_null_hedged | 828 | **63** | 87.3% [80.0%, 93.6%] |
| fever_null_historical | 511 | **36** | 90.0% [84.7%, 94.2%] |
| fever_null_metaphor | 641 | **47** | 96.4% [94.3%, 98.2%] |
| fever_null_thirdparty | 508 | **35** | 92.1% [87.8%, 96.1%] |
| fever_true | 1481 | **96** | 47.5% [39.6%, 55.9%] |
| (none) | 2978 | **1** | 99.0% [99.0%, 99.0%] |

### Per-fragment errors (worst first)

Whether errors are spread thinly across many fragments or piled onto a few is the difference
between "the method is too weak" (model work) and "these specific ideas are not learnable from
the data we have" (library work, and these are the fragments to write more of). No intervals:
a fragment is one cluster, so an interval over its own examples measures nothing.

257 of 463 decisive fragments were got wrong at least once.

`tfidf_logreg`: 1945 errors across 257 of 463 decisive fragments. Half of them fall on **50** fragments (an even spread would be 128.5); the worst ten carry 14.1% of all errors.

| fragment | library | sub-class | truth | correct | accuracy | predicted as |
|---|---|---|---|---|---|---|
| `fever_false:b96ed279` | `fever_false` | -- | false | 0/33 | 0.0% | null 33 |
| `fever_false:5c2a065d` | `fever_false` | -- | false | 0/30 | 0.0% | true 1, null 29 |
| `fever_false:44cd09fd` | `fever_false` | -- | false | 0/28 | 0.0% | null 28 |
| `fever_false:033927e6` | `fever_false` | -- | false | 0/26 | 0.0% | null 26 |
| `fever_false:03f2141f` | `fever_false` | -- | false | 0/25 | 0.0% | null 25 |
| `fever_true:3d00c372` | `fever_true` | -- | true | 0/25 | 0.0% | null 25 |
| `fever_true:dd6bbec4` | `fever_true` | -- | true | 0/24 | 0.0% | null 24 |
| `fever_false:afdc7129` | `fever_false` | -- | false | 0/22 | 0.0% | null 22 |
| `fever_false:f6985a04` | `fever_false` | -- | false | 0/22 | 0.0% | true 7, null 15 |
| `fever_true:c7489e90` | `fever_true` | -- | true | 0/19 | 0.0% | false 1, null 18 |
| `fever_true:391fb2ce` | `fever_true` | -- | true | 0/18 | 0.0% | false 1, null 17 |
| `fever_true:7844c66b` | `fever_true` | -- | true | 0/18 | 0.0% | null 18 |
| `fever_true:01833454` | `fever_true` | -- | true | 0/16 | 0.0% | false 9, null 7 |
| `fever_true:054f1309` | `fever_true` | -- | true | 0/16 | 0.0% | null 16 |
| `fever_false:f1e3b80c` | `fever_false` | -- | false | 0/15 | 0.0% | null 15 |
| `fever_true:0ddb8a11` | `fever_true` | -- | true | 0/15 | 0.0% | null 15 |
| `fever_true:199d4eb4` | `fever_true` | -- | true | 0/14 | 0.0% | null 14 |
| `fever_true:79211e25` | `fever_true` | -- | true | 0/14 | 0.0% | null 14 |
| `fever_true:97087dd7` | `fever_true` | -- | true | 0/14 | 0.0% | null 14 |
| `fever_true:d00c307b` | `fever_true` | -- | true | 0/14 | 0.0% | null 14 |
| `fever_true:ef344ff7` | `fever_true` | -- | true | 0/13 | 0.0% | null 13 |
| `fever_true:f885b3cb` | `fever_true` | -- | true | 0/13 | 0.0% | null 13 |
| `fever_true:872e3af9` | `fever_true` | -- | true | 0/12 | 0.0% | null 12 |
| `fever_true:c5d3e4a0` | `fever_true` | -- | true | 0/12 | 0.0% | false 12 |
| `fever_true:ed36ef0f` | `fever_true` | -- | true | 0/12 | 0.0% | null 12 |
| `fever_null_hedged:42486de4` | `fever_null_hedged` | hedged | null | 0/11 | 0.0% | false 10, true 1 |
| `fever_true:781b30e3` | `fever_true` | -- | true | 0/11 | 0.0% | false 1, null 10 |
| `fever_true:dd7a11e2` | `fever_true` | -- | true | 0/10 | 0.0% | null 10 |
| `fever_true:5ce7adbd` | `fever_true` | -- | true | 0/9 | 0.0% | null 9 |
| `fever_true:c2b356a0` | `fever_true` | -- | true | 0/9 | 0.0% | null 9 |
| `fever_null_historical:2c3501f1` | `fever_null_historical` | historical | null | 0/1 | 0.0% | false 1 |
| `fever_false:cdf2609b` | `fever_false` | -- | false | 1/32 | 3.1% | false 1, null 31 |
| `fever_false:cbf9d7a5` | `fever_false` | -- | false | 1/28 | 3.6% | false 1, null 27 |
| `fever_true:cf13c84f` | `fever_true` | -- | true | 1/15 | 6.7% | false 1, true 1, null 13 |
| `fever_null_hedged:5bf1b63f` | `fever_null_hedged` | hedged | null | 1/14 | 7.1% | false 13, null 1 |
| `fever_true:80f7ba2e` | `fever_true` | -- | true | 1/13 | 7.7% | true 1, null 12 |
| `fever_true:e919adf9` | `fever_true` | -- | true | 1/13 | 7.7% | false 1, true 1, null 11 |
| `fever_false:8bcd3ef4` | `fever_false` | -- | false | 2/24 | 8.3% | false 2, true 1, null 21 |
| `fever_true:15a05d92` | `fever_true` | -- | true | 2/24 | 8.3% | true 2, null 22 |
| `fever_true:74ccf7bd` | `fever_true` | -- | true | 1/12 | 8.3% | true 1, null 11 |

*217 further fragments with at least one error are in the JSON sidecar; every fragment is there regardless of score.*

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
| attribution | 574 | **43** | 100.0% [100.0%, 100.0%] |
| hedged | 828 | **63** | 100.0% [100.0%, 100.0%] |
| historical | 511 | **36** | 100.0% [100.0%, 100.0%] |
| metaphor | 641 | **47** | 100.0% [100.0%, 100.0%] |
| third_party | 508 | **35** | 100.0% [100.0%, 100.0%] |

### By fragment library

| library | n | eff n | accuracy [95% CI] |
|---|---|---|---|
| fever_false | 2479 | **98** | 0.0% [0.0%, 0.0%] |
| fever_null_attribution | 574 | **43** | 100.0% [100.0%, 100.0%] |
| fever_null_hedged | 828 | **63** | 100.0% [100.0%, 100.0%] |
| fever_null_historical | 511 | **36** | 100.0% [100.0%, 100.0%] |
| fever_null_metaphor | 641 | **47** | 100.0% [100.0%, 100.0%] |
| fever_null_thirdparty | 508 | **35** | 100.0% [100.0%, 100.0%] |
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
| `fever_false:5a6a9b80` | `fever_false` | -- | false | 0/40 | 0.0% | null 40 |
| `fever_false:d0ca84a7` | `fever_false` | -- | false | 0/37 | 0.0% | null 37 |
| `fever_false:24e5c247` | `fever_false` | -- | false | 0/36 | 0.0% | null 36 |
| `fever_false:a9a0220e` | `fever_false` | -- | false | 0/36 | 0.0% | null 36 |
| `fever_false:0429068c` | `fever_false` | -- | false | 0/34 | 0.0% | null 34 |
| `fever_false:17f6c637` | `fever_false` | -- | false | 0/34 | 0.0% | null 34 |
| `fever_false:9f46e710` | `fever_false` | -- | false | 0/34 | 0.0% | null 34 |
| `fever_false:fc2ae0f2` | `fever_false` | -- | false | 0/34 | 0.0% | null 34 |
| `fever_false:5969c6c9` | `fever_false` | -- | false | 0/33 | 0.0% | null 33 |
| `fever_false:b9076eff` | `fever_false` | -- | false | 0/33 | 0.0% | null 33 |
| `fever_false:b96ed279` | `fever_false` | -- | false | 0/33 | 0.0% | null 33 |
| `fever_false:2b944abc` | `fever_false` | -- | false | 0/32 | 0.0% | null 32 |
| `fever_false:55bf1913` | `fever_false` | -- | false | 0/32 | 0.0% | null 32 |
| `fever_false:a5b671a1` | `fever_false` | -- | false | 0/32 | 0.0% | null 32 |
| `fever_false:cdf2609b` | `fever_false` | -- | false | 0/32 | 0.0% | null 32 |
| `fever_false:8d02bd9e` | `fever_false` | -- | false | 0/31 | 0.0% | null 31 |
| `fever_false:d5ed3ff1` | `fever_false` | -- | false | 0/31 | 0.0% | null 31 |
| `fever_false:de0596c4` | `fever_false` | -- | false | 0/31 | 0.0% | null 31 |
| `fever_false:e2aff3b8` | `fever_false` | -- | false | 0/31 | 0.0% | null 31 |
| `fever_false:f586e96d` | `fever_false` | -- | false | 0/31 | 0.0% | null 31 |
| `fever_false:56a45ff1` | `fever_false` | -- | false | 0/30 | 0.0% | null 30 |
| `fever_false:5c2a065d` | `fever_false` | -- | false | 0/30 | 0.0% | null 30 |
| `fever_false:c747066d` | `fever_false` | -- | false | 0/30 | 0.0% | null 30 |
| `fever_false:3a3043ff` | `fever_false` | -- | false | 0/29 | 0.0% | null 29 |
| `fever_false:463f8189` | `fever_false` | -- | false | 0/29 | 0.0% | null 29 |
| `fever_false:758d5434` | `fever_false` | -- | false | 0/29 | 0.0% | null 29 |
| `fever_false:7b64d17a` | `fever_false` | -- | false | 0/29 | 0.0% | null 29 |
| `fever_false:a4cda1e2` | `fever_false` | -- | false | 0/29 | 0.0% | null 29 |
| `fever_true:18173593` | `fever_true` | -- | true | 0/29 | 0.0% | null 29 |
| `fever_true:f3ee0d07` | `fever_true` | -- | true | 0/29 | 0.0% | null 29 |
| `fever_false:44cd09fd` | `fever_false` | -- | false | 0/28 | 0.0% | null 28 |
| `fever_false:a6c0d44a` | `fever_false` | -- | false | 0/28 | 0.0% | null 28 |
| `fever_false:cbf9d7a5` | `fever_false` | -- | false | 0/28 | 0.0% | null 28 |
| `fever_false:147d5cf0` | `fever_false` | -- | false | 0/27 | 0.0% | null 27 |
| `fever_false:3de7ecac` | `fever_false` | -- | false | 0/27 | 0.0% | null 27 |
| `fever_false:43f5b35d` | `fever_false` | -- | false | 0/27 | 0.0% | null 27 |
| `fever_false:8599e318` | `fever_false` | -- | false | 0/27 | 0.0% | null 27 |
| `fever_false:e70e24b6` | `fever_false` | -- | false | 0/27 | 0.0% | null 27 |
| `fever_true:753c7815` | `fever_true` | -- | true | 0/27 | 0.0% | null 27 |
| `fever_false:033927e6` | `fever_false` | -- | false | 0/26 | 0.0% | null 26 |

*154 further fragments with at least one error are in the JSON sidecar; every fragment is there regardless of score.*

## `tfidf_logreg__shuffled`

TF-IDF unigrams and bigrams into logistic regression. Tests whether the dataset is keyword-solvable. Its overall accuracy is close to uninformative; the `null_ambiguous` slice is the number that matters. **Negative control:** trained on permuted training labels (seed 7) and evaluated on the unpermuted test split, where it must land at chance.

Decision-rule margins selected per fold (on each fold's own validation split): 0.0.
Every fold selected margin 0, so the ruled and raw views below are the same decisions. That is a finding rather than a bug: no margin improved macro-F1 without worsening the `null -> true` rate.

*Confusion matrix, raw argmax*

|  | pred false | pred true | pred null | total |
|---|---|---|---|---|
| **truth false** | 11 | 2 | 2466 | 2479 |
| **truth true** | 11 | 0 | 1470 | 1481 |
| **truth null** | 84 | 0 | 5956 | 6040 |
| **total** | 106 | 2 | 9892 | 10000 |

`null -> true`: 0 of 6040 truly-null examples (0.00%).

*Confusion matrix, after the decision rule*

|  | pred false | pred true | pred null | total |
|---|---|---|---|---|
| **truth false** | 11 | 2 | 2466 | 2479 |
| **truth true** | 11 | 0 | 1470 | 1481 |
| **truth null** | 84 | 0 | 5956 | 6040 |
| **total** | 106 | 2 | 9892 | 10000 |

`null -> true`: 0 of 6040 truly-null examples (0.00%).

### Per class, after the decision rule

| class | support | predicted | precision | recall | F1 |
|---|---|---|---|---|---|
| `false` | 2479 | 106 | 10.4% | 0.4% | 0.9% |
| `true` | 1481 | 2 | 0.0% | 0.0% | 0.0% |
| `null` | 6040 | 9892 | 60.2% | 98.6% | 74.8% |

### By label mode

| label mode | n | eff n | accuracy [95% CI] |
|---|---|---|---|
| false | 2479 | **98** | 0.4% [0.2%, 0.8%] |
| null_ambiguous | 3062 | **224** | 98.7% [98.2%, 99.2%] |
| null_structural | 2978 | **1** | 98.5% [98.5%, 98.5%] |
| true | 1481 | **96** | 0.0% [0.0%, 0.0%] |

### By null sub-class

| sub-class | n | eff n | null recall [95% CI] |
|---|---|---|---|
| attribution | 574 | **43** | 97.9% [96.1%, 99.3%] |
| hedged | 828 | **63** | 98.9% [98.2%, 99.6%] |
| historical | 511 | **36** | 99.0% [97.9%, 99.8%] |
| metaphor | 641 | **47** | 98.4% [96.6%, 99.8%] |
| third_party | 508 | **35** | 99.4% [98.5%, 100.0%] |

### By fragment library

| library | n | eff n | accuracy [95% CI] |
|---|---|---|---|
| fever_false | 2479 | **98** | 0.4% [0.2%, 0.8%] |
| fever_null_attribution | 574 | **43** | 97.9% [96.1%, 99.3%] |
| fever_null_hedged | 828 | **63** | 98.9% [98.2%, 99.6%] |
| fever_null_historical | 511 | **36** | 99.0% [97.9%, 99.8%] |
| fever_null_metaphor | 641 | **47** | 98.4% [96.6%, 99.8%] |
| fever_null_thirdparty | 508 | **35** | 99.4% [98.5%, 100.0%] |
| fever_true | 1481 | **96** | 0.0% [0.0%, 0.0%] |
| (none) | 2978 | **1** | 98.5% [98.5%, 98.5%] |

### Per-fragment errors (worst first)

Whether errors are spread thinly across many fragments or piled onto a few is the difference
between "the method is too weak" (model work) and "these specific ideas are not learnable from
the data we have" (library work, and these are the fragments to write more of). No intervals:
a fragment is one cluster, so an interval over its own examples measures nothing.

221 of 463 decisive fragments were got wrong at least once.

`tfidf_logreg__shuffled`: 3988 errors across 221 of 463 decisive fragments. Half of them fall on **72** fragments (an even spread would be 110.5); the worst ten carry 8.8% of all errors.

| fragment | library | sub-class | truth | correct | accuracy | predicted as |
|---|---|---|---|---|---|---|
| `fever_false:5a6a9b80` | `fever_false` | -- | false | 0/40 | 0.0% | null 40 |
| `fever_false:d0ca84a7` | `fever_false` | -- | false | 0/37 | 0.0% | null 37 |
| `fever_false:24e5c247` | `fever_false` | -- | false | 0/36 | 0.0% | null 36 |
| `fever_false:a9a0220e` | `fever_false` | -- | false | 0/36 | 0.0% | null 36 |
| `fever_false:0429068c` | `fever_false` | -- | false | 0/34 | 0.0% | null 34 |
| `fever_false:17f6c637` | `fever_false` | -- | false | 0/34 | 0.0% | null 34 |
| `fever_false:9f46e710` | `fever_false` | -- | false | 0/34 | 0.0% | null 34 |
| `fever_false:fc2ae0f2` | `fever_false` | -- | false | 0/34 | 0.0% | null 34 |
| `fever_false:5969c6c9` | `fever_false` | -- | false | 0/33 | 0.0% | null 33 |
| `fever_false:b9076eff` | `fever_false` | -- | false | 0/33 | 0.0% | null 33 |
| `fever_false:b96ed279` | `fever_false` | -- | false | 0/33 | 0.0% | null 33 |
| `fever_false:2b944abc` | `fever_false` | -- | false | 0/32 | 0.0% | null 32 |
| `fever_false:55bf1913` | `fever_false` | -- | false | 0/32 | 0.0% | null 32 |
| `fever_false:a5b671a1` | `fever_false` | -- | false | 0/32 | 0.0% | null 32 |
| `fever_false:cdf2609b` | `fever_false` | -- | false | 0/32 | 0.0% | null 32 |
| `fever_false:8d02bd9e` | `fever_false` | -- | false | 0/31 | 0.0% | null 31 |
| `fever_false:d5ed3ff1` | `fever_false` | -- | false | 0/31 | 0.0% | null 31 |
| `fever_false:de0596c4` | `fever_false` | -- | false | 0/31 | 0.0% | null 31 |
| `fever_false:e2aff3b8` | `fever_false` | -- | false | 0/31 | 0.0% | null 31 |
| `fever_false:f586e96d` | `fever_false` | -- | false | 0/31 | 0.0% | null 31 |
| `fever_false:56a45ff1` | `fever_false` | -- | false | 0/30 | 0.0% | null 30 |
| `fever_false:5c2a065d` | `fever_false` | -- | false | 0/30 | 0.0% | null 30 |
| `fever_false:c747066d` | `fever_false` | -- | false | 0/30 | 0.0% | null 30 |
| `fever_false:3a3043ff` | `fever_false` | -- | false | 0/29 | 0.0% | null 29 |
| `fever_false:463f8189` | `fever_false` | -- | false | 0/29 | 0.0% | null 29 |
| `fever_false:758d5434` | `fever_false` | -- | false | 0/29 | 0.0% | null 29 |
| `fever_false:a4cda1e2` | `fever_false` | -- | false | 0/29 | 0.0% | null 29 |
| `fever_true:18173593` | `fever_true` | -- | true | 0/29 | 0.0% | null 29 |
| `fever_true:f3ee0d07` | `fever_true` | -- | true | 0/29 | 0.0% | null 29 |
| `fever_false:44cd09fd` | `fever_false` | -- | false | 0/28 | 0.0% | null 28 |
| `fever_false:a6c0d44a` | `fever_false` | -- | false | 0/28 | 0.0% | null 28 |
| `fever_false:cbf9d7a5` | `fever_false` | -- | false | 0/28 | 0.0% | null 28 |
| `fever_false:147d5cf0` | `fever_false` | -- | false | 0/27 | 0.0% | null 27 |
| `fever_false:3de7ecac` | `fever_false` | -- | false | 0/27 | 0.0% | null 27 |
| `fever_false:43f5b35d` | `fever_false` | -- | false | 0/27 | 0.0% | null 27 |
| `fever_false:8599e318` | `fever_false` | -- | false | 0/27 | 0.0% | null 27 |
| `fever_false:e70e24b6` | `fever_false` | -- | false | 0/27 | 0.0% | null 27 |
| `fever_true:753c7815` | `fever_true` | -- | true | 0/27 | 0.0% | null 27 |
| `fever_false:033927e6` | `fever_false` | -- | false | 0/26 | 0.0% | null 26 |
| `fever_false:4bf3caad` | `fever_false` | -- | false | 0/26 | 0.0% | null 26 |

*181 further fragments with at least one error are in the JSON sidecar; every fragment is there regardless of score.*

## `arm_a_probe`

Frozen `roberta-base`, mean-pooled, with a `Linear(768, 3)` probe over the cached embeddings (2,307 parameters). The encoder learns nothing; only the probe is fitted. Expected to handle clear positives, clear negatives and `null_structural`, and to do badly on the four hard `null` sub-classes, which turn on compositional scope that a single pooled vector blurs. That is the predicted result rather than a fault, and it is what makes Arm B necessary: a weak probe cannot distinguish "the libraries are the bottleneck" from "the method is too weak".

Decision-rule margins selected per fold (on each fold's own validation split): 0.0, 0.05, 0.1.

*Confusion matrix, raw argmax*

|  | pred false | pred true | pred null | total |
|---|---|---|---|---|
| **truth false** | 1807 | 142 | 530 | 2479 |
| **truth true** | 141 | 759 | 581 | 1481 |
| **truth null** | 293 | 153 | 5594 | 6040 |
| **total** | 2241 | 1054 | 6705 | 10000 |

`null -> true`: 153 of 6040 truly-null examples (2.53%).

*Confusion matrix, after the decision rule*

|  | pred false | pred true | pred null | total |
|---|---|---|---|---|
| **truth false** | 1817 | 125 | 537 | 2479 |
| **truth true** | 148 | 725 | 608 | 1481 |
| **truth null** | 300 | 124 | 5616 | 6040 |
| **total** | 2265 | 974 | 6761 | 10000 |

`null -> true`: 124 of 6040 truly-null examples (2.05%).

### Per class, after the decision rule

| class | support | predicted | precision | recall | F1 |
|---|---|---|---|---|---|
| `false` | 2479 | 2265 | 80.2% | 73.3% | 76.6% |
| `true` | 1481 | 974 | 74.4% | 49.0% | 59.1% |
| `null` | 6040 | 6761 | 83.1% | 93.0% | 87.7% |

### By label mode

| label mode | n | eff n | accuracy [95% CI] |
|---|---|---|---|
| false | 2479 | **98** | 73.3% [68.0%, 78.5%] |
| null_ambiguous | 3062 | **224** | 87.4% [84.8%, 89.7%] |
| null_structural | 2978 | **1** | 98.7% [98.7%, 98.7%] |
| true | 1481 | **96** | 49.0% [41.7%, 56.7%] |

### By null sub-class

| sub-class | n | eff n | null recall [95% CI] |
|---|---|---|---|
| attribution | 574 | **43** | 86.8% [81.2%, 92.0%] |
| hedged | 828 | **63** | 76.4% [70.2%, 82.3%] |
| historical | 511 | **36** | 88.3% [83.7%, 92.2%] |
| metaphor | 641 | **47** | 96.1% [93.8%, 97.9%] |
| third_party | 508 | **35** | 94.3% [91.1%, 97.6%] |

### By fragment library

| library | n | eff n | accuracy [95% CI] |
|---|---|---|---|
| fever_false | 2479 | **98** | 73.3% [68.0%, 78.5%] |
| fever_null_attribution | 574 | **43** | 86.8% [81.2%, 92.0%] |
| fever_null_hedged | 828 | **63** | 76.4% [70.2%, 82.3%] |
| fever_null_historical | 511 | **36** | 88.3% [83.7%, 92.2%] |
| fever_null_metaphor | 641 | **47** | 96.1% [93.8%, 97.9%] |
| fever_null_thirdparty | 508 | **35** | 94.3% [91.1%, 97.6%] |
| fever_true | 1481 | **96** | 49.0% [41.7%, 56.7%] |
| (none) | 2978 | **1** | 98.7% [98.7%, 98.7%] |

### Per-fragment errors (worst first)

Whether errors are spread thinly across many fragments or piled onto a few is the difference
between "the method is too weak" (model work) and "these specific ideas are not learnable from
the data we have" (library work, and these are the fragments to write more of). No intervals:
a fragment is one cluster, so an interval over its own examples measures nothing.

291 of 463 decisive fragments were got wrong at least once.

`arm_a_probe`: 1803 errors across 291 of 463 decisive fragments. Half of them fall on **57** fragments (an even spread would be 145.5); the worst ten carry 13.0% of all errors.

| fragment | library | sub-class | truth | correct | accuracy | predicted as |
|---|---|---|---|---|---|---|
| `fever_true:7ef2ecf5` | `fever_true` | -- | true | 0/23 | 0.0% | null 23 |
| `fever_true:391fb2ce` | `fever_true` | -- | true | 0/18 | 0.0% | false 4, null 14 |
| `fever_true:7844c66b` | `fever_true` | -- | true | 0/18 | 0.0% | false 4, null 14 |
| `fever_true:01833454` | `fever_true` | -- | true | 0/16 | 0.0% | false 12, null 4 |
| `fever_true:97087dd7` | `fever_true` | -- | true | 0/14 | 0.0% | false 3, null 11 |
| `fever_true:d00c307b` | `fever_true` | -- | true | 0/14 | 0.0% | null 14 |
| `fever_true:80f7ba2e` | `fever_true` | -- | true | 0/13 | 0.0% | false 1, null 12 |
| `fever_true:ef344ff7` | `fever_true` | -- | true | 0/13 | 0.0% | null 13 |
| `fever_true:f885b3cb` | `fever_true` | -- | true | 0/13 | 0.0% | null 13 |
| `fever_true:74ccf7bd` | `fever_true` | -- | true | 0/12 | 0.0% | null 12 |
| `fever_true:872e3af9` | `fever_true` | -- | true | 0/12 | 0.0% | false 3, null 9 |
| `fever_true:ed36ef0f` | `fever_true` | -- | true | 0/12 | 0.0% | null 12 |
| `fever_null_hedged:17a3f60a` | `fever_null_hedged` | hedged | null | 0/9 | 0.0% | true 9 |
| `fever_true:5ce7adbd` | `fever_true` | -- | true | 0/9 | 0.0% | false 9 |
| `fever_true:15a05d92` | `fever_true` | -- | true | 1/24 | 4.2% | false 2, true 1, null 21 |
| `fever_true:c7489e90` | `fever_true` | -- | true | 1/19 | 5.3% | false 2, true 1, null 16 |
| `fever_true:dd079c14` | `fever_true` | -- | true | 1/14 | 7.1% | true 1, null 13 |
| `fever_true:dd6bbec4` | `fever_true` | -- | true | 2/24 | 8.3% | false 8, true 2, null 14 |
| `fever_true:c5d3e4a0` | `fever_true` | -- | true | 1/12 | 8.3% | false 11, true 1 |
| `fever_false:afdc7129` | `fever_false` | -- | false | 2/22 | 9.1% | false 2, null 20 |
| `fever_false:a5b671a1` | `fever_false` | -- | false | 3/32 | 9.4% | false 3, true 29 |
| `fever_null_hedged:43dc94df` | `fever_null_hedged` | hedged | null | 1/10 | 10.0% | false 9, null 1 |
| `fever_false:3a3043ff` | `fever_false` | -- | false | 3/29 | 10.3% | false 3, true 10, null 16 |
| `fever_false:033927e6` | `fever_false` | -- | false | 3/26 | 11.5% | false 3, null 23 |
| `fever_true:1c3df822` | `fever_true` | -- | true | 3/26 | 11.5% | false 5, true 3, null 18 |
| `fever_true:a92fcdc7` | `fever_true` | -- | true | 2/17 | 11.8% | true 2, null 15 |
| `fever_true:0ddb8a11` | `fever_true` | -- | true | 2/15 | 13.3% | false 1, true 2, null 12 |
| `fever_true:18173593` | `fever_true` | -- | true | 4/29 | 13.8% | false 11, true 4, null 14 |
| `fever_false:e0897296` | `fever_false` | -- | false | 3/21 | 14.3% | false 3, true 2, null 16 |
| `fever_true:f0038e34` | `fever_true` | -- | true | 3/21 | 14.3% | true 3, null 18 |
| `fever_true:ed3c8c83` | `fever_true` | -- | true | 3/19 | 15.8% | true 3, null 16 |
| `fever_true:a6c8dae6` | `fever_true` | -- | true | 1/6 | 16.7% | true 1, null 5 |
| `fever_true:c3a107bf` | `fever_true` | -- | true | 1/6 | 16.7% | true 1, null 5 |
| `fever_false:ebba1ba0` | `fever_false` | -- | false | 3/16 | 18.8% | false 3, null 13 |
| `fever_true:7cad3f0f` | `fever_true` | -- | true | 4/20 | 20.0% | false 16, true 4 |
| `fever_true:199d4eb4` | `fever_true` | -- | true | 3/14 | 21.4% | true 3, null 11 |
| `fever_false:0cc191ec` | `fever_false` | -- | false | 5/23 | 21.7% | false 5, true 1, null 17 |
| `fever_null_hedged:965c4a64` | `fever_null_hedged` | hedged | null | 2/9 | 22.2% | false 1, true 6, null 2 |
| `fever_null_hedged:c3c6e72b` | `fever_null_hedged` | hedged | null | 2/9 | 22.2% | false 4, true 3, null 2 |
| `fever_true:c2b356a0` | `fever_true` | -- | true | 2/9 | 22.2% | true 2, null 7 |

*251 further fragments with at least one error are in the JSON sidecar; every fragment is there regardless of score.*

## `arm_b_finetune`

`roberta-base` with **every layer unfrozen**, mean-pooled, with the same `Linear(768, 3)` head -- 110M trainable parameters against Arm A's 2,307. Three epochs at batch 32, learning rate 2e-5, 10% linear warmup, AdamW, fp32. No gradient checkpointing, no 8-bit optimiser, no LoRA, no gradient accumulation: the full model fits in 12GB with room to spare, so anything that reads like a compute compromise would be a mistake rather than a saving. This is the arm that separates "the fragment libraries are the bottleneck" from "the method is too weak": if a fully fine-tuned encoder still cannot read third-party attribution, tense or metaphor, the limit is in the ideas the libraries contain and the fix is library work, not model work.

Decision-rule margins selected per fold (on each fold's own validation split): 0.0, 0.75, 0.85, 0.9.

*Confusion matrix, raw argmax*

|  | pred false | pred true | pred null | total |
|---|---|---|---|---|
| **truth false** | 2392 | 21 | 66 | 2479 |
| **truth true** | 15 | 1282 | 184 | 1481 |
| **truth null** | 64 | 133 | 5843 | 6040 |
| **total** | 2471 | 1436 | 6093 | 10000 |

`null -> true`: 133 of 6040 truly-null examples (2.20%).

*Confusion matrix, after the decision rule*

|  | pred false | pred true | pred null | total |
|---|---|---|---|---|
| **truth false** | 2393 | 14 | 72 | 2479 |
| **truth true** | 15 | 1269 | 197 | 1481 |
| **truth null** | 68 | 119 | 5853 | 6040 |
| **total** | 2476 | 1402 | 6122 | 10000 |

`null -> true`: 119 of 6040 truly-null examples (1.97%).

### Per class, after the decision rule

| class | support | predicted | precision | recall | F1 |
|---|---|---|---|---|---|
| `false` | 2479 | 2476 | 96.6% | 96.5% | 96.6% |
| `true` | 1481 | 1402 | 90.5% | 85.7% | 88.0% |
| `null` | 6040 | 6122 | 95.6% | 96.9% | 96.3% |

### By label mode

| label mode | n | eff n | accuracy [95% CI] |
|---|---|---|---|
| false | 2479 | **98** | 96.5% [93.7%, 98.5%] |
| null_ambiguous | 3062 | **224** | 94.4% [91.9%, 96.7%] |
| null_structural | 2978 | **1** | 99.4% [99.4%, 99.4%] |
| true | 1481 | **96** | 85.7% [79.5%, 91.7%] |

### By null sub-class

| sub-class | n | eff n | null recall [95% CI] |
|---|---|---|---|
| attribution | 574 | **43** | 92.7% [85.9%, 97.9%] |
| hedged | 828 | **63** | 87.9% [79.4%, 94.8%] |
| historical | 511 | **36** | 97.5% [93.9%, 99.6%] |
| metaphor | 641 | **47** | 98.3% [96.2%, 99.7%] |
| third_party | 508 | **35** | 99.2% [98.2%, 100.0%] |

### By fragment library

| library | n | eff n | accuracy [95% CI] |
|---|---|---|---|
| fever_false | 2479 | **98** | 96.5% [93.7%, 98.5%] |
| fever_null_attribution | 574 | **43** | 92.7% [85.9%, 97.9%] |
| fever_null_hedged | 828 | **63** | 87.9% [79.4%, 94.8%] |
| fever_null_historical | 511 | **36** | 97.5% [93.9%, 99.6%] |
| fever_null_metaphor | 641 | **47** | 98.3% [96.2%, 99.7%] |
| fever_null_thirdparty | 508 | **35** | 99.2% [98.2%, 100.0%] |
| fever_true | 1481 | **96** | 85.7% [79.5%, 91.7%] |
| (none) | 2978 | **1** | 99.4% [99.4%, 99.4%] |

### Per-fragment errors (worst first)

Whether errors are spread thinly across many fragments or piled onto a few is the difference
between "the method is too weak" (model work) and "these specific ideas are not learnable from
the data we have" (library work, and these are the fragments to write more of). No intervals:
a fragment is one cluster, so an interval over its own examples measures nothing.

97 of 463 decisive fragments were got wrong at least once.

`arm_b_finetune`: 468 errors across 97 of 463 decisive fragments. Half of them fall on **17** fragments (an even spread would be 48.5); the worst ten carry 33.3% of all errors.

| fragment | library | sub-class | truth | correct | accuracy | predicted as |
|---|---|---|---|---|---|---|
| `fever_true:391fb2ce` | `fever_true` | -- | true | 0/18 | 0.0% | null 18 |
| `fever_true:7844c66b` | `fever_true` | -- | true | 0/18 | 0.0% | false 1, null 17 |
| `fever_true:97087dd7` | `fever_true` | -- | true | 0/14 | 0.0% | null 14 |
| `fever_null_attribution:17b7ab2a` | `fever_null_attribution` | attribution | null | 0/13 | 0.0% | true 13 |
| `fever_null_hedged:cf95d564` | `fever_null_hedged` | hedged | null | 0/13 | 0.0% | true 13 |
| `fever_true:74ccf7bd` | `fever_true` | -- | true | 0/12 | 0.0% | null 12 |
| `fever_true:c5d3e4a0` | `fever_true` | -- | true | 0/12 | 0.0% | null 12 |
| `fever_null_hedged:42486de4` | `fever_null_hedged` | hedged | null | 0/11 | 0.0% | false 7, true 4 |
| `fever_null_hedged:965c4a64` | `fever_null_hedged` | hedged | null | 0/9 | 0.0% | false 4, true 5 |
| `fever_true:5ce7adbd` | `fever_true` | -- | true | 0/9 | 0.0% | null 9 |
| `fever_null_historical:feadcb2c` | `fever_null_historical` | historical | null | 0/8 | 0.0% | true 8 |
| `fever_true:0ddb8a11` | `fever_true` | -- | true | 1/15 | 6.7% | true 1, null 14 |
| `fever_null_hedged:5bf1b63f` | `fever_null_hedged` | hedged | null | 1/14 | 7.1% | false 3, true 10, null 1 |
| `fever_null_hedged:fafa0b56` | `fever_null_hedged` | hedged | null | 1/12 | 8.3% | true 11, null 1 |
| `fever_null_attribution:b03cf8b0` | `fever_null_attribution` | attribution | null | 1/11 | 9.1% | true 10, null 1 |
| `fever_null_hedged:9e333f46` | `fever_null_hedged` | hedged | null | 1/10 | 10.0% | false 8, true 1, null 1 |
| `fever_false:5c2a065d` | `fever_false` | -- | false | 4/30 | 13.3% | false 4, true 2, null 24 |
| `fever_true:ef344ff7` | `fever_true` | -- | true | 2/13 | 15.4% | true 2, null 11 |
| `fever_true:ed36ef0f` | `fever_true` | -- | true | 2/12 | 16.7% | true 2, null 10 |
| `fever_false:e8c514ff` | `fever_false` | -- | false | 3/16 | 18.8% | false 3, true 2, null 11 |
| `fever_null_hedged:081a5883` | `fever_null_hedged` | hedged | null | 3/16 | 18.8% | false 13, null 3 |
| `fever_true:01833454` | `fever_true` | -- | true | 4/16 | 25.0% | false 12, true 4 |
| `fever_true:872e3af9` | `fever_true` | -- | true | 3/12 | 25.0% | true 3, null 9 |
| `fever_true:ed3c8c83` | `fever_true` | -- | true | 5/19 | 26.3% | true 5, null 14 |
| `fever_true:d00c307b` | `fever_true` | -- | true | 4/14 | 28.6% | true 4, null 10 |
| `fever_null_hedged:8d1c41e3` | `fever_null_hedged` | hedged | null | 3/9 | 33.3% | false 1, true 5, null 3 |
| `fever_true:c7489e90` | `fever_true` | -- | true | 7/19 | 36.8% | true 7, null 12 |
| `fever_null_attribution:dba8c443` | `fever_null_attribution` | attribution | null | 5/11 | 45.5% | false 6, null 5 |
| `fever_true:15a05d92` | `fever_true` | -- | true | 12/24 | 50.0% | true 12, null 12 |
| `fever_null_attribution:d52abc40` | `fever_null_attribution` | attribution | null | 5/10 | 50.0% | false 5, null 5 |
| `fever_true:5e4f1da7` | `fever_true` | -- | true | 5/10 | 50.0% | true 5, null 5 |
| `fever_null_metaphor:625f220a` | `fever_null_metaphor` | metaphor | null | 6/11 | 54.5% | true 5, null 6 |
| `fever_false:afdc7129` | `fever_false` | -- | false | 13/22 | 59.1% | false 13, null 9 |
| `fever_false:0cc191ec` | `fever_false` | -- | false | 16/23 | 69.6% | false 16, null 7 |
| `fever_true:2ee57e4c` | `fever_true` | -- | true | 7/10 | 70.0% | true 7, null 3 |
| `fever_true:dd7a11e2` | `fever_true` | -- | true | 7/10 | 70.0% | true 7, null 3 |
| `fever_true:fc118943` | `fever_true` | -- | true | 8/11 | 72.7% | true 8, null 3 |
| `fever_null_attribution:29c6f386` | `fever_null_attribution` | attribution | null | 9/12 | 75.0% | true 3, null 9 |
| `fever_null_hedged:60bffa1a` | `fever_null_hedged` | hedged | null | 6/8 | 75.0% | true 2, null 6 |
| `fever_null_hedged:b8236158` | `fever_null_hedged` | hedged | null | 7/9 | 77.8% | true 2, null 7 |

*57 further fragments with at least one error are in the JSON sidecar; every fragment is there regardless of score.*

## `arm_b_finetune__shuffled`

`roberta-base` with **every layer unfrozen**, mean-pooled, with the same `Linear(768, 3)` head -- 110M trainable parameters against Arm A's 2,307. Three epochs at batch 32, learning rate 2e-5, 10% linear warmup, AdamW, fp32. No gradient checkpointing, no 8-bit optimiser, no LoRA, no gradient accumulation: the full model fits in 12GB with room to spare, so anything that reads like a compute compromise would be a mistake rather than a saving. This is the arm that separates "the fragment libraries are the bottleneck" from "the method is too weak": if a fully fine-tuned encoder still cannot read third-party attribution, tense or metaphor, the limit is in the ideas the libraries contain and the fix is library work, not model work. **Negative control:** fine-tuned on permuted training labels (seed 7) and evaluated on the unpermuted test split. A 110M-parameter model is expected to drive train loss towards zero by memorising the permutation while landing at chance on test; that combination is the control passing, and the per-fold train-loss curve in the sidecar is where the first half of it is read.

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
| attribution | 574 | **43** | 100.0% [100.0%, 100.0%] |
| hedged | 828 | **63** | 100.0% [100.0%, 100.0%] |
| historical | 511 | **36** | 100.0% [100.0%, 100.0%] |
| metaphor | 641 | **47** | 100.0% [100.0%, 100.0%] |
| third_party | 508 | **35** | 100.0% [100.0%, 100.0%] |

### By fragment library

| library | n | eff n | accuracy [95% CI] |
|---|---|---|---|
| fever_false | 2479 | **98** | 0.0% [0.0%, 0.0%] |
| fever_null_attribution | 574 | **43** | 100.0% [100.0%, 100.0%] |
| fever_null_hedged | 828 | **63** | 100.0% [100.0%, 100.0%] |
| fever_null_historical | 511 | **36** | 100.0% [100.0%, 100.0%] |
| fever_null_metaphor | 641 | **47** | 100.0% [100.0%, 100.0%] |
| fever_null_thirdparty | 508 | **35** | 100.0% [100.0%, 100.0%] |
| fever_true | 1481 | **96** | 0.0% [0.0%, 0.0%] |
| (none) | 2978 | **1** | 100.0% [100.0%, 100.0%] |

### Per-fragment errors (worst first)

Whether errors are spread thinly across many fragments or piled onto a few is the difference
between "the method is too weak" (model work) and "these specific ideas are not learnable from
the data we have" (library work, and these are the fragments to write more of). No intervals:
a fragment is one cluster, so an interval over its own examples measures nothing.

194 of 463 decisive fragments were got wrong at least once.

`arm_b_finetune__shuffled`: 3960 errors across 194 of 463 decisive fragments. Half of them fall on **71** fragments (an even spread would be 97.0); the worst ten carry 8.9% of all errors.

| fragment | library | sub-class | truth | correct | accuracy | predicted as |
|---|---|---|---|---|---|---|
| `fever_false:5a6a9b80` | `fever_false` | -- | false | 0/40 | 0.0% | null 40 |
| `fever_false:d0ca84a7` | `fever_false` | -- | false | 0/37 | 0.0% | null 37 |
| `fever_false:24e5c247` | `fever_false` | -- | false | 0/36 | 0.0% | null 36 |
| `fever_false:a9a0220e` | `fever_false` | -- | false | 0/36 | 0.0% | null 36 |
| `fever_false:0429068c` | `fever_false` | -- | false | 0/34 | 0.0% | null 34 |
| `fever_false:17f6c637` | `fever_false` | -- | false | 0/34 | 0.0% | null 34 |
| `fever_false:9f46e710` | `fever_false` | -- | false | 0/34 | 0.0% | null 34 |
| `fever_false:fc2ae0f2` | `fever_false` | -- | false | 0/34 | 0.0% | null 34 |
| `fever_false:5969c6c9` | `fever_false` | -- | false | 0/33 | 0.0% | null 33 |
| `fever_false:b9076eff` | `fever_false` | -- | false | 0/33 | 0.0% | null 33 |
| `fever_false:b96ed279` | `fever_false` | -- | false | 0/33 | 0.0% | null 33 |
| `fever_false:2b944abc` | `fever_false` | -- | false | 0/32 | 0.0% | null 32 |
| `fever_false:55bf1913` | `fever_false` | -- | false | 0/32 | 0.0% | null 32 |
| `fever_false:a5b671a1` | `fever_false` | -- | false | 0/32 | 0.0% | null 32 |
| `fever_false:cdf2609b` | `fever_false` | -- | false | 0/32 | 0.0% | null 32 |
| `fever_false:8d02bd9e` | `fever_false` | -- | false | 0/31 | 0.0% | null 31 |
| `fever_false:d5ed3ff1` | `fever_false` | -- | false | 0/31 | 0.0% | null 31 |
| `fever_false:de0596c4` | `fever_false` | -- | false | 0/31 | 0.0% | null 31 |
| `fever_false:e2aff3b8` | `fever_false` | -- | false | 0/31 | 0.0% | null 31 |
| `fever_false:f586e96d` | `fever_false` | -- | false | 0/31 | 0.0% | null 31 |
| `fever_false:56a45ff1` | `fever_false` | -- | false | 0/30 | 0.0% | null 30 |
| `fever_false:5c2a065d` | `fever_false` | -- | false | 0/30 | 0.0% | null 30 |
| `fever_false:c747066d` | `fever_false` | -- | false | 0/30 | 0.0% | null 30 |
| `fever_false:3a3043ff` | `fever_false` | -- | false | 0/29 | 0.0% | null 29 |
| `fever_false:463f8189` | `fever_false` | -- | false | 0/29 | 0.0% | null 29 |
| `fever_false:758d5434` | `fever_false` | -- | false | 0/29 | 0.0% | null 29 |
| `fever_false:7b64d17a` | `fever_false` | -- | false | 0/29 | 0.0% | null 29 |
| `fever_false:a4cda1e2` | `fever_false` | -- | false | 0/29 | 0.0% | null 29 |
| `fever_true:18173593` | `fever_true` | -- | true | 0/29 | 0.0% | null 29 |
| `fever_true:f3ee0d07` | `fever_true` | -- | true | 0/29 | 0.0% | null 29 |
| `fever_false:44cd09fd` | `fever_false` | -- | false | 0/28 | 0.0% | null 28 |
| `fever_false:a6c0d44a` | `fever_false` | -- | false | 0/28 | 0.0% | null 28 |
| `fever_false:cbf9d7a5` | `fever_false` | -- | false | 0/28 | 0.0% | null 28 |
| `fever_false:147d5cf0` | `fever_false` | -- | false | 0/27 | 0.0% | null 27 |
| `fever_false:3de7ecac` | `fever_false` | -- | false | 0/27 | 0.0% | null 27 |
| `fever_false:43f5b35d` | `fever_false` | -- | false | 0/27 | 0.0% | null 27 |
| `fever_false:8599e318` | `fever_false` | -- | false | 0/27 | 0.0% | null 27 |
| `fever_false:e70e24b6` | `fever_false` | -- | false | 0/27 | 0.0% | null 27 |
| `fever_true:753c7815` | `fever_true` | -- | true | 0/27 | 0.0% | null 27 |
| `fever_false:033927e6` | `fever_false` | -- | false | 0/26 | 0.0% | null 26 |

*154 further fragments with at least one error are in the JSON sidecar; every fragment is there regardless of score.*

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
| 2 | 10000 | 2000 | 2000 | 0.0 | 60.5% | 60.5% | 25.6% | 0.00% |
| 3 | 10000 | 2000 | 2000 | 0.0 | 60.8% | 60.8% | 25.3% | 0.00% |
| 4 | 10000 | 2000 | 2000 | 0.0 | 60.3% | 60.3% | 25.3% | 0.00% |

### `tfidf_logreg`

| fold | train n | val n | test n | margin | acc (raw) | acc (ruled) | macro-F1 | null->true |
|---|---|---|---|---|---|---|---|---|
| 0 | 10000 | 2000 | 2000 | 0.0 | 80.5% | 80.5% | 74.6% | 0.50% |
| 1 | 10000 | 2000 | 2000 | 0.0 | 78.0% | 78.0% | 68.9% | 0.50% |
| 2 | 10000 | 2000 | 2000 | 0.0 | 78.9% | 78.9% | 69.4% | 2.24% |
| 3 | 10000 | 2000 | 2000 | 0.0 | 80.1% | 80.1% | 73.5% | 2.06% |
| 4 | 10000 | 2000 | 2000 | 0.0 | 83.8% | 83.8% | 75.5% | 1.16% |

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
| 0 | 10000 | 2000 | 2000 | 0.0 | 59.2% | 59.2% | 25.6% | 0.00% |
| 1 | 10000 | 2000 | 2000 | 0.0 | 59.7% | 59.7% | 24.9% | 0.00% |
| 2 | 10000 | 2000 | 2000 | 0.0 | 59.4% | 59.4% | 25.2% | 0.00% |
| 3 | 10000 | 2000 | 2000 | 0.0 | 60.2% | 60.2% | 25.3% | 0.00% |
| 4 | 10000 | 2000 | 2000 | 0.0 | 59.9% | 59.9% | 25.0% | 0.00% |

### `arm_a_probe`

| fold | train n | val n | test n | margin | acc (raw) | acc (ruled) | macro-F1 | null->true |
|---|---|---|---|---|---|---|---|---|
| 0 | 10000 | 2000 | 2000 | 0.0 | 84.5% | 84.5% | 78.7% | 1.41% |
| 1 | 10000 | 2000 | 2000 | 0.0 | 78.5% | 78.5% | 69.4% | 1.41% |
| 2 | 10000 | 2000 | 2000 | 0.05 | 80.2% | 80.1% | 72.6% | 2.98% |
| 3 | 10000 | 2000 | 2000 | 0.1 | 80.6% | 80.8% | 74.4% | 3.46% |
| 4 | 10000 | 2000 | 2000 | 0.05 | 84.2% | 84.0% | 77.3% | 1.00% |

### `arm_b_finetune`

| fold | train n | val n | test n | margin | acc (raw) | acc (ruled) | macro-F1 | null->true |
|---|---|---|---|---|---|---|---|---|
| 0 | 10000 | 2000 | 2000 | 0.85 | 97.6% | 97.7% | 97.0% | 0.00% |
| 1 | 10000 | 2000 | 2000 | 0.9 | 93.0% | 92.8% | 90.0% | 0.92% |
| 2 | 10000 | 2000 | 2000 | 0.0 | 91.4% | 91.4% | 89.4% | 5.30% |
| 3 | 10000 | 2000 | 2000 | 0.75 | 95.8% | 95.8% | 94.5% | 2.14% |
| 4 | 10000 | 2000 | 2000 | 0.0 | 98.1% | 98.1% | 97.2% | 1.49% |

### `arm_b_finetune__shuffled`

| fold | train n | val n | test n | margin | acc (raw) | acc (ruled) | macro-F1 | null->true |
|---|---|---|---|---|---|---|---|---|
| 0 | 10000 | 2000 | 2000 | 0.0 | 60.5% | 60.5% | 25.1% | 0.00% |
| 1 | 10000 | 2000 | 2000 | 0.0 | 60.1% | 60.1% | 25.0% | 0.00% |
| 2 | 10000 | 2000 | 2000 | 0.0 | 60.4% | 60.4% | 25.1% | 0.00% |
| 3 | 10000 | 2000 | 2000 | 0.0 | 60.8% | 60.8% | 25.2% | 0.00% |
| 4 | 10000 | 2000 | 2000 | 0.0 | 60.3% | 60.3% | 25.1% | 0.00% |

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

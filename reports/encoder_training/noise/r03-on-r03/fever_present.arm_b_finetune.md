# Encoder training: evaluation report

*Generated 2026-08-31T06:54:14+00:00.*

|  |  |
|---|---|
| signal | `fever_present` |
| folds | `5` |
| generator version | `3` |
| generator base seed | `42` |
| generator seed rule | `base + 100 * fold + {train: 0, val: 1, test: 2}` |
| split salt | `0` |
| dataset dir | `data/synthetic/generated/noise/fever-r03` |
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
| artefacts | `models/encoder-noise/r03-on-r03/fever_present/arm_b_finetune` |
| weights | `models/encoder-noise/r03-on-r03/fever_present/arm_b_finetune/weights -- ~440MB per fold, not committed` |
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
| `length_only` | baseline | 7022 | **418** | 43.9% [38.9%, 49.1%] | 21.4% [19.1%, 23.9%] | 60.6% | 60.6% +/- 0.3% |
| `tfidf_logreg` | baseline | 7022 | **418** | 73.4% [69.9%, 77.0%] | 70.7% [66.5%, 74.4%] | 81.1% | 81.1% +/- 3.1% |
| `length_only__shuffled` | negative control | 7022 | **418** | 43.6% [38.6%, 48.8%] | 20.2% [18.6%, 21.9%] | 60.4% | 60.4% +/- 0.2% |
| `tfidf_logreg__shuffled` | negative control | 7022 | **418** | 43.5% [38.5%, 48.7%] | 20.3% [18.6%, 21.9%] | 60.2% | 60.2% +/- 0.3% |
| `arm_a_probe` | probe | 7022 | **418** | 75.3% [72.3%, 78.2%] | 72.6% [69.2%, 75.9%] | 82.2% | 82.2% +/- 2.9% |
| `arm_b_finetune` | finetune | 7022 | **418** | 93.4% [91.4%, 95.3%] | 92.8% [90.5%, 94.9%] | 95.3% | 95.3% +/- 3.1% |
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
| `tfidf_logreg` | -- | 94.4% [90.2%, 97.9%] (eff n 43) | 88.3% [81.0%, 94.4%] (eff n 63) | 91.2% [85.8%, 95.5%] (eff n 36) | 97.0% [94.6%, 98.9%] (eff n 47) | 92.9% [88.5%, 96.8%] (eff n 35) |
| `length_only__shuffled` | -- | 100.0% [100.0%, 100.0%] (eff n 43) | 100.0% [100.0%, 100.0%] (eff n 63) | 100.0% [100.0%, 100.0%] (eff n 36) | 100.0% [100.0%, 100.0%] (eff n 47) | 100.0% [100.0%, 100.0%] (eff n 35) |
| `tfidf_logreg__shuffled` | -- | 99.8% [99.4%, 100.0%] (eff n 43) | 99.6% [99.2%, 100.0%] (eff n 63) | 99.0% [98.2%, 99.8%] (eff n 36) | 100.0% [100.0%, 100.0%] (eff n 47) | 99.8% [99.4%, 100.0%] (eff n 35) |
| `arm_a_probe` | -- | 87.1% [81.5%, 92.1%] (eff n 43) | 77.8% [71.4%, 83.7%] (eff n 63) | 87.5% [82.6%, 91.9%] (eff n 36) | 96.3% [93.8%, 98.2%] (eff n 47) | 93.3% [89.6%, 96.8%] (eff n 35) |
| `arm_b_finetune` | -- | 94.3% [87.9%, 98.9%] (eff n 43) | 87.7% [79.2%, 95.1%] (eff n 63) | 96.3% [91.4%, 99.6%] (eff n 36) | 99.5% [98.9%, 100.0%] (eff n 47) | 100.0% [100.0%, 100.0%] (eff n 35) |
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
| `fever_present` | 49 | 11.0% |

### `arm_b_finetune`

Recombination test slice: **n 7022**, **eff n 418** clusters, accuracy 93.4% [91.4%, 95.3%]. Holdout: **n 67** submissions, one observation each, scored by 5 fold models at margins 0.0, 0.9, 0.45, 0.0, 0.0. The two `n`s are printed together because they are not the same kind of number and the second is far the smaller.

| signal | true/false/null | omitted | decisive n | decisive acc (mean +/- sd) | worst-case half-width | all n | all acc (mean +/- sd) | null recall |
|---|---|---|---|---|---|---|---|---|
| `fever_present` | 9/9/49 | 0 | 18 | 76.7% +/- 12.7% | +/-23.1% | 67 | 83.0% +/- 2.7% | 85.3% +/- 7.3% |

`null -> true` on real text, per fold: `fever_present` 5, 8, 7, 1, 6 of 49. This is the cell that invents a symptom into a patient's pre-filled form, counted here on submissions rather than on recombinations.

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
| `tfidf_logreg` | baseline | 3062 | **224** | 92.5% [90.1%, 94.6%] |
| `arm_a_probe` | probe | 3062 | **224** | 87.6% [85.2%, 89.8%] |
| `arm_b_finetune` | finetune | 3062 | **224** | 94.9% [92.0%, 97.3%] |

### 2. The same comparison, paired

Two overlapping intervals do not settle whether one model beats another on the same
examples. McNemar does, over the examples the two disagree about -- read it alongside the
intervals above, never instead of them.

| pair | n | a only | b only | p |
|---|---|---|---|---|
| `majority_class` vs `length_only` | 3062 | 3 | 0 | 0.25 |
| `majority_class` vs `tfidf_logreg` | 3062 | 229 | 0 | 2.32e-69 |
| `majority_class` vs `arm_a_probe` | 3062 | 382 | 0 | 2.03e-115 |
| `majority_class` vs `arm_b_finetune` | 3062 | 160 | 0 | 1.37e-48 |
| `length_only` vs `tfidf_logreg` | 3062 | 228 | 2 | 3.08e-65 |
| `length_only` vs `arm_a_probe` | 3062 | 380 | 1 | 1.55e-112 |
| `length_only` vs `arm_b_finetune` | 3062 | 159 | 2 | 8.92e-45 |
| `tfidf_logreg` vs `arm_a_probe` | 3062 | 293 | 140 | 1.56e-13 |
| `tfidf_logreg` vs `arm_b_finetune` | 3062 | 88 | 157 | 1.23e-05 |
| `arm_a_probe` vs `arm_b_finetune` | 3062 | 96 | 318 | 7.31e-29 |

### 3. Where the errors fall

The per-fragment table below, as one number per model. Errors spread thinly across many
fragments say the method is too weak. Errors piled onto a handful say those specific ideas
are not learnable from the data we have -- and the table names them, which is what makes
this the most decision-useful thing in the report.

* `majority_class`: 3960 errors across 194 of 463 decisive fragments. Half of them fall on **71** fragments (an even spread would be 97.0); the worst ten carry 8.9% of all errors.
* `length_only`: 3938 errors across 196 of 463 decisive fragments. Half of them fall on **70** fragments (an even spread would be 98.0); the worst ten carry 8.9% of all errors.
* `tfidf_logreg`: 1865 errors across 219 of 463 decisive fragments. Half of them fall on **47** fragments (an even spread would be 109.5); the worst ten carry 14.8% of all errors.
* `arm_a_probe`: 1735 errors across 281 of 463 decisive fragments. Half of them fall on **55** fragments (an even spread would be 140.5); the worst ten carry 13.3% of all errors.
* `arm_b_finetune`: 460 errors across 70 of 463 decisive fragments. Half of them fall on **15** fragments (an even spread would be 35.0); the worst ten carry 38.3% of all errors.

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
| `tfidf_logreg__shuffled` | 60.2% [39.8%, 76.2%] | 25.1% [19.0%, 28.9%] |
| `arm_b_finetune__shuffled` | 60.4% [39.9%, 76.5%] | 25.1% [19.0%, 28.9%] |

## Paired comparisons (McNemar, raw argmax)

Exact two-sided McNemar over the examples the two models disagree about. Pairing unit is the
example, not the cluster -- see the limitations.

| pair | slice | n | a only | b only | p |
|---|---|---|---|---|---|
| `majority_class` vs `length_only` | overall | 10000 | 3 | 25 | 2.74e-05 |
| `majority_class` vs `length_only` | null_ambiguous | 3062 | 3 | 0 | 0.25 |
| `majority_class` vs `tfidf_logreg` | overall | 10000 | 250 | 2324 | 0 |
| `majority_class` vs `tfidf_logreg` | null_ambiguous | 3062 | 229 | 0 | 2.32e-69 |
| `majority_class` vs `arm_a_probe` | overall | 10000 | 423 | 2608 | 0 |
| `majority_class` vs `arm_a_probe` | null_ambiguous | 3062 | 382 | 0 | 2.03e-115 |
| `majority_class` vs `arm_b_finetune` | overall | 10000 | 173 | 3668 | 0 |
| `majority_class` vs `arm_b_finetune` | null_ambiguous | 3062 | 160 | 0 | 1.37e-48 |
| `length_only` vs `tfidf_logreg` | overall | 10000 | 249 | 2301 | 0 |
| `length_only` vs `tfidf_logreg` | null_ambiguous | 3062 | 228 | 2 | 3.08e-65 |
| `length_only` vs `arm_a_probe` | overall | 10000 | 438 | 2601 | 0 |
| `length_only` vs `arm_a_probe` | null_ambiguous | 3062 | 380 | 1 | 1.55e-112 |
| `length_only` vs `arm_b_finetune` | overall | 10000 | 172 | 3645 | 0 |
| `length_only` vs `arm_b_finetune` | null_ambiguous | 3062 | 159 | 2 | 8.92e-45 |
| `tfidf_logreg` vs `arm_a_probe` | overall | 10000 | 784 | 895 | 0.00725 |
| `tfidf_logreg` vs `arm_a_probe` | null_ambiguous | 3062 | 293 | 140 | 1.56e-13 |
| `tfidf_logreg` vs `arm_b_finetune` | overall | 10000 | 124 | 1545 | 1.95e-312 |
| `tfidf_logreg` vs `arm_b_finetune` | null_ambiguous | 3062 | 88 | 157 | 1.23e-05 |
| `arm_a_probe` vs `arm_b_finetune` | overall | 10000 | 175 | 1485 | 9.62e-259 |
| `arm_a_probe` vs `arm_b_finetune` | null_ambiguous | 3062 | 96 | 318 | 7.31e-29 |

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
| `fever_false` | 2479 | 0.0% | 0.2% | 64.3% | 73.7% | 95.9% | 95.9pp |
| `fever_true` | 1481 | 0.0% | 1.4% | 49.3% | 52.6% | 86.4% | 86.4pp |
| `fever_null_hedged` | 828 | 100.0% | 100.0% | 88.3% | 77.8% | 87.7% | 22.2pp |
| `fever_null_attribution` | 574 | 100.0% | 99.5% | 94.4% | 87.1% | 94.3% | 12.9pp |
| `fever_null_historical` | 511 | 100.0% | 100.0% | 91.2% | 87.5% | 96.3% | 12.5pp |
| `fever_null_thirdparty` | 508 | 100.0% | 100.0% | 92.9% | 93.3% | 100.0% | 7.1pp |
| `fever_null_metaphor` | 641 | 100.0% | 100.0% | 97.0% | 96.3% | 99.5% | 3.7pp |
| `(none)` | 2978 | 100.0% | 100.0% | 99.3% | 98.6% | 99.6% | 1.4pp |

### By fragment, errors

Ordered by the worst model's error count, so the fragments the comparison is about sort
to the top whichever encoder wins. Counts, not rates: these are the sentences a month of
library work would be spent on. The JSON holds every fragment.

| fragment | library | truth | `majority_class` | `length_only` | `tfidf_logreg` | `arm_a_probe` | `arm_b_finetune` | spread |
|---|---|---|---|---|---|---|---|---|
| `fever_false:5a6a9b80` | `fever_false` | false | 40 | 40 | 0 | 3 | 0 | 40 |
| `fever_false:d0ca84a7` | `fever_false` | false | 37 | 37 | 0 | 1 | 0 | 37 |
| `fever_false:24e5c247` | `fever_false` | false | 36 | 36 | 10 | 10 | 0 | 36 |
| `fever_false:a9a0220e` | `fever_false` | false | 36 | 36 | 0 | 3 | 0 | 36 |
| `fever_false:0429068c` | `fever_false` | false | 34 | 34 | 19 | 0 | 0 | 34 |
| `fever_false:17f6c637` | `fever_false` | false | 34 | 34 | 0 | 0 | 0 | 34 |
| `fever_false:9f46e710` | `fever_false` | false | 34 | 34 | 0 | 3 | 0 | 34 |
| `fever_false:fc2ae0f2` | `fever_false` | false | 34 | 34 | 7 | 5 | 0 | 34 |
| `fever_false:5969c6c9` | `fever_false` | false | 33 | 33 | 1 | 9 | 0 | 33 |
| `fever_false:b9076eff` | `fever_false` | false | 33 | 33 | 13 | 23 | 1 | 32 |
| `fever_false:b96ed279` | `fever_false` | false | 33 | 33 | 33 | 14 | 0 | 33 |
| `fever_false:2b944abc` | `fever_false` | false | 32 | 32 | 0 | 0 | 0 | 32 |
| `fever_false:55bf1913` | `fever_false` | false | 32 | 32 | 0 | 0 | 0 | 32 |
| `fever_false:a5b671a1` | `fever_false` | false | 32 | 32 | 14 | 26 | 0 | 32 |
| `fever_false:cdf2609b` | `fever_false` | false | 32 | 32 | 29 | 7 | 0 | 32 |
| `fever_false:8d02bd9e` | `fever_false` | false | 31 | 31 | 21 | 5 | 0 | 31 |
| `fever_false:d5ed3ff1` | `fever_false` | false | 31 | 31 | 18 | 8 | 0 | 31 |
| `fever_false:de0596c4` | `fever_false` | false | 31 | 31 | 16 | 13 | 0 | 31 |
| `fever_false:e2aff3b8` | `fever_false` | false | 31 | 31 | 9 | 5 | 1 | 30 |
| `fever_false:f586e96d` | `fever_false` | false | 31 | 31 | 11 | 17 | 0 | 31 |
| `fever_false:56a45ff1` | `fever_false` | false | 30 | 30 | 5 | 4 | 0 | 30 |
| `fever_false:5c2a065d` | `fever_false` | false | 30 | 30 | 30 | 7 | 29 | 23 |
| `fever_false:c747066d` | `fever_false` | false | 30 | 30 | 0 | 2 | 0 | 30 |
| `fever_false:3a3043ff` | `fever_false` | false | 29 | 29 | 27 | 26 | 10 | 19 |
| `fever_false:463f8189` | `fever_false` | false | 29 | 29 | 0 | 3 | 0 | 29 |
| `fever_false:758d5434` | `fever_false` | false | 29 | 29 | 0 | 0 | 0 | 29 |
| `fever_false:7b64d17a` | `fever_false` | false | 29 | 29 | 23 | 6 | 0 | 29 |
| `fever_false:a4cda1e2` | `fever_false` | false | 29 | 29 | 0 | 0 | 0 | 29 |
| `fever_true:18173593` | `fever_true` | true | 29 | 29 | 16 | 21 | 0 | 29 |
| `fever_true:f3ee0d07` | `fever_true` | true | 29 | 29 | 0 | 0 | 0 | 29 |
| `fever_false:44cd09fd` | `fever_false` | false | 28 | 28 | 28 | 8 | 6 | 22 |
| `fever_false:a6c0d44a` | `fever_false` | false | 28 | 28 | 10 | 0 | 0 | 28 |
| `fever_false:cbf9d7a5` | `fever_false` | false | 28 | 28 | 27 | 23 | 0 | 28 |
| `fever_false:147d5cf0` | `fever_false` | false | 27 | 27 | 13 | 1 | 0 | 27 |
| `fever_false:3de7ecac` | `fever_false` | false | 27 | 27 | 27 | 14 | 6 | 21 |
| `fever_false:43f5b35d` | `fever_false` | false | 27 | 27 | 3 | 0 | 0 | 27 |
| `fever_false:8599e318` | `fever_false` | false | 27 | 27 | 2 | 2 | 0 | 27 |
| `fever_false:e70e24b6` | `fever_false` | false | 27 | 27 | 7 | 21 | 2 | 25 |
| `fever_true:753c7815` | `fever_true` | true | 27 | 27 | 0 | 0 | 0 | 27 |
| `fever_false:033927e6` | `fever_false` | false | 26 | 26 | 26 | 25 | 0 | 26 |

*311 further fragments erred on at least one model; the JSON holds them all.*

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
| **truth false** | 5 | 0 | 2474 | 2479 |
| **truth true** | 43 | 20 | 1418 | 1481 |
| **truth null** | 3 | 0 | 6037 | 6040 |
| **total** | 51 | 20 | 9929 | 10000 |

`null -> true`: 0 of 6040 truly-null examples (0.00%).

*Confusion matrix, after the decision rule*

|  | pred false | pred true | pred null | total |
|---|---|---|---|---|
| **truth false** | 5 | 0 | 2474 | 2479 |
| **truth true** | 43 | 20 | 1418 | 1481 |
| **truth null** | 3 | 0 | 6037 | 6040 |
| **total** | 51 | 20 | 9929 | 10000 |

`null -> true`: 0 of 6040 truly-null examples (0.00%).

### Per class, after the decision rule

| class | support | predicted | precision | recall | F1 |
|---|---|---|---|---|---|
| `false` | 2479 | 51 | 9.8% | 0.2% | 0.4% |
| `true` | 1481 | 20 | 100.0% | 1.4% | 2.7% |
| `null` | 6040 | 9929 | 60.8% | 100.0% | 75.6% |

### By label mode

| label mode | n | eff n | accuracy [95% CI] |
|---|---|---|---|
| false | 2479 | **98** | 0.2% [0.0%, 0.6%] |
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
| fever_false | 2479 | **98** | 0.2% [0.0%, 0.6%] |
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

`length_only`: 3938 errors across 196 of 463 decisive fragments. Half of them fall on **70** fragments (an even spread would be 98.0); the worst ten carry 8.9% of all errors.

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
| **truth false** | 1594 | 110 | 775 | 2479 |
| **truth true** | 100 | 730 | 651 | 1481 |
| **truth null** | 159 | 91 | 5790 | 6040 |
| **total** | 1853 | 931 | 7216 | 10000 |

`null -> true`: 91 of 6040 truly-null examples (1.51%).

*Confusion matrix, after the decision rule*

|  | pred false | pred true | pred null | total |
|---|---|---|---|---|
| **truth false** | 1594 | 110 | 775 | 2479 |
| **truth true** | 100 | 730 | 651 | 1481 |
| **truth null** | 159 | 91 | 5790 | 6040 |
| **total** | 1853 | 931 | 7216 | 10000 |

`null -> true`: 91 of 6040 truly-null examples (1.51%).

### Per class, after the decision rule

| class | support | predicted | precision | recall | F1 |
|---|---|---|---|---|---|
| `false` | 2479 | 1853 | 86.0% | 64.3% | 73.6% |
| `true` | 1481 | 931 | 78.4% | 49.3% | 60.5% |
| `null` | 6040 | 7216 | 80.2% | 95.9% | 87.4% |

### By label mode

| label mode | n | eff n | accuracy [95% CI] |
|---|---|---|---|
| false | 2479 | **98** | 64.3% [57.2%, 71.2%] |
| null_ambiguous | 3062 | **224** | 92.5% [90.1%, 94.6%] |
| null_structural | 2978 | **1** | 99.3% [99.3%, 99.3%] |
| true | 1481 | **96** | 49.3% [40.8%, 58.1%] |

### By null sub-class

| sub-class | n | eff n | null recall [95% CI] |
|---|---|---|---|
| attribution | 574 | **43** | 94.4% [90.2%, 97.9%] |
| hedged | 828 | **63** | 88.3% [81.0%, 94.4%] |
| historical | 511 | **36** | 91.2% [85.8%, 95.5%] |
| metaphor | 641 | **47** | 97.0% [94.6%, 98.9%] |
| third_party | 508 | **35** | 92.9% [88.5%, 96.8%] |

### By fragment library

| library | n | eff n | accuracy [95% CI] |
|---|---|---|---|
| fever_false | 2479 | **98** | 64.3% [57.2%, 71.2%] |
| fever_null_attribution | 574 | **43** | 94.4% [90.2%, 97.9%] |
| fever_null_hedged | 828 | **63** | 88.3% [81.0%, 94.4%] |
| fever_null_historical | 511 | **36** | 91.2% [85.8%, 95.5%] |
| fever_null_metaphor | 641 | **47** | 97.0% [94.6%, 98.9%] |
| fever_null_thirdparty | 508 | **35** | 92.9% [88.5%, 96.8%] |
| fever_true | 1481 | **96** | 49.3% [40.8%, 58.1%] |
| (none) | 2978 | **1** | 99.3% [99.3%, 99.3%] |

### Per-fragment errors (worst first)

Whether errors are spread thinly across many fragments or piled onto a few is the difference
between "the method is too weak" (model work) and "these specific ideas are not learnable from
the data we have" (library work, and these are the fragments to write more of). No intervals:
a fragment is one cluster, so an interval over its own examples measures nothing.

219 of 463 decisive fragments were got wrong at least once.

`tfidf_logreg`: 1865 errors across 219 of 463 decisive fragments. Half of them fall on **47** fragments (an even spread would be 109.5); the worst ten carry 14.8% of all errors.

| fragment | library | sub-class | truth | correct | accuracy | predicted as |
|---|---|---|---|---|---|---|
| `fever_false:b96ed279` | `fever_false` | -- | false | 0/33 | 0.0% | null 33 |
| `fever_false:5c2a065d` | `fever_false` | -- | false | 0/30 | 0.0% | true 1, null 29 |
| `fever_false:44cd09fd` | `fever_false` | -- | false | 0/28 | 0.0% | null 28 |
| `fever_false:3de7ecac` | `fever_false` | -- | false | 0/27 | 0.0% | null 27 |
| `fever_false:033927e6` | `fever_false` | -- | false | 0/26 | 0.0% | null 26 |
| `fever_true:3d00c372` | `fever_true` | -- | true | 0/25 | 0.0% | null 25 |
| `fever_false:8bcd3ef4` | `fever_false` | -- | false | 0/24 | 0.0% | true 1, null 23 |
| `fever_true:dd6bbec4` | `fever_true` | -- | true | 0/24 | 0.0% | null 24 |
| `fever_false:afdc7129` | `fever_false` | -- | false | 0/22 | 0.0% | null 22 |
| `fever_false:f6985a04` | `fever_false` | -- | false | 0/22 | 0.0% | true 4, null 18 |
| `fever_true:c7489e90` | `fever_true` | -- | true | 0/19 | 0.0% | null 19 |
| `fever_true:391fb2ce` | `fever_true` | -- | true | 0/18 | 0.0% | false 1, null 17 |
| `fever_true:7844c66b` | `fever_true` | -- | true | 0/18 | 0.0% | null 18 |
| `fever_true:01833454` | `fever_true` | -- | true | 0/16 | 0.0% | false 13, null 3 |
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
| `fever_true:781b30e3` | `fever_true` | -- | true | 0/11 | 0.0% | null 11 |
| `fever_true:5e4f1da7` | `fever_true` | -- | true | 0/10 | 0.0% | null 10 |
| `fever_true:dd7a11e2` | `fever_true` | -- | true | 0/10 | 0.0% | null 10 |
| `fever_true:3c3641a8` | `fever_true` | -- | true | 0/9 | 0.0% | null 9 |
| `fever_true:5ce7adbd` | `fever_true` | -- | true | 0/9 | 0.0% | false 1, null 8 |
| `fever_true:c2b356a0` | `fever_true` | -- | true | 0/9 | 0.0% | null 9 |
| `fever_null_historical:2c3501f1` | `fever_null_historical` | historical | null | 0/1 | 0.0% | false 1 |
| `fever_false:cbf9d7a5` | `fever_false` | -- | false | 1/28 | 3.6% | false 1, true 1, null 26 |
| `fever_false:b74a83cf` | `fever_false` | -- | false | 1/23 | 4.3% | false 1, null 22 |
| `fever_true:ed3c8c83` | `fever_true` | -- | true | 1/19 | 5.3% | true 1, null 18 |
| `fever_true:db1acb55` | `fever_true` | -- | true | 1/16 | 6.2% | false 2, true 1, null 13 |
| `fever_true:cf13c84f` | `fever_true` | -- | true | 1/15 | 6.7% | true 1, null 14 |
| `fever_false:3a3043ff` | `fever_false` | -- | false | 2/29 | 6.9% | false 2, true 20, null 7 |
| `fever_true:f32f1ddb` | `fever_true` | -- | true | 1/14 | 7.1% | true 1, null 13 |

*179 further fragments with at least one error are in the JSON sidecar; every fragment is there regardless of score.*

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
| **truth false** | 2 | 0 | 2477 | 2479 |
| **truth true** | 5 | 0 | 1476 | 1481 |
| **truth null** | 22 | 0 | 6018 | 6040 |
| **total** | 29 | 0 | 9971 | 10000 |

`null -> true`: 0 of 6040 truly-null examples (0.00%).

*Confusion matrix, after the decision rule*

|  | pred false | pred true | pred null | total |
|---|---|---|---|---|
| **truth false** | 2 | 0 | 2477 | 2479 |
| **truth true** | 5 | 0 | 1476 | 1481 |
| **truth null** | 22 | 0 | 6018 | 6040 |
| **total** | 29 | 0 | 9971 | 10000 |

`null -> true`: 0 of 6040 truly-null examples (0.00%).

### Per class, after the decision rule

| class | support | predicted | precision | recall | F1 |
|---|---|---|---|---|---|
| `false` | 2479 | 29 | 6.9% | 0.1% | 0.2% |
| `true` | 1481 | 0 | -- | 0.0% | 0.0% |
| `null` | 6040 | 9971 | 60.4% | 99.6% | 75.2% |

### By label mode

| label mode | n | eff n | accuracy [95% CI] |
|---|---|---|---|
| false | 2479 | **98** | 0.1% [0.0%, 0.2%] |
| null_ambiguous | 3062 | **224** | 99.7% [99.5%, 99.8%] |
| null_structural | 2978 | **1** | 99.6% [99.6%, 99.6%] |
| true | 1481 | **96** | 0.0% [0.0%, 0.0%] |

### By null sub-class

| sub-class | n | eff n | null recall [95% CI] |
|---|---|---|---|
| attribution | 574 | **43** | 99.8% [99.4%, 100.0%] |
| hedged | 828 | **63** | 99.6% [99.2%, 100.0%] |
| historical | 511 | **36** | 99.0% [98.2%, 99.8%] |
| metaphor | 641 | **47** | 100.0% [100.0%, 100.0%] |
| third_party | 508 | **35** | 99.8% [99.4%, 100.0%] |

### By fragment library

| library | n | eff n | accuracy [95% CI] |
|---|---|---|---|
| fever_false | 2479 | **98** | 0.1% [0.0%, 0.2%] |
| fever_null_attribution | 574 | **43** | 99.8% [99.4%, 100.0%] |
| fever_null_hedged | 828 | **63** | 99.6% [99.2%, 100.0%] |
| fever_null_historical | 511 | **36** | 99.0% [98.2%, 99.8%] |
| fever_null_metaphor | 641 | **47** | 100.0% [100.0%, 100.0%] |
| fever_null_thirdparty | 508 | **35** | 99.8% [99.4%, 100.0%] |
| fever_true | 1481 | **96** | 0.0% [0.0%, 0.0%] |
| (none) | 2978 | **1** | 99.6% [99.6%, 99.6%] |

### Per-fragment errors (worst first)

Whether errors are spread thinly across many fragments or piled onto a few is the difference
between "the method is too weak" (model work) and "these specific ideas are not learnable from
the data we have" (library work, and these are the fragments to write more of). No intervals:
a fragment is one cluster, so an interval over its own examples measures nothing.

204 of 463 decisive fragments were got wrong at least once.

`tfidf_logreg__shuffled`: 3968 errors across 204 of 463 decisive fragments. Half of them fall on **71** fragments (an even spread would be 102.0); the worst ten carry 8.8% of all errors.

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
| `fever_false:4bf3caad` | `fever_false` | -- | false | 0/26 | 0.0% | null 26 |

*164 further fragments with at least one error are in the JSON sidecar; every fragment is there regardless of score.*

## `arm_a_probe`

Frozen `roberta-base`, mean-pooled, with a `Linear(768, 3)` probe over the cached embeddings (2,307 parameters). The encoder learns nothing; only the probe is fitted. Expected to handle clear positives, clear negatives and `null_structural`, and to do badly on the four hard `null` sub-classes, which turn on compositional scope that a single pooled vector blurs. That is the predicted result rather than a fault, and it is what makes Arm B necessary: a weak probe cannot distinguish "the libraries are the bottleneck" from "the method is too weak".

Decision-rule margins selected per fold (on each fold's own validation split): 0.0, 0.05.

*Confusion matrix, raw argmax*

|  | pred false | pred true | pred null | total |
|---|---|---|---|---|
| **truth false** | 1824 | 145 | 510 | 2479 |
| **truth true** | 136 | 784 | 561 | 1481 |
| **truth null** | 275 | 148 | 5617 | 6040 |
| **total** | 2235 | 1077 | 6688 | 10000 |

`null -> true`: 148 of 6040 truly-null examples (2.45%).

*Confusion matrix, after the decision rule*

|  | pred false | pred true | pred null | total |
|---|---|---|---|---|
| **truth false** | 1826 | 143 | 510 | 2479 |
| **truth true** | 141 | 779 | 561 | 1481 |
| **truth null** | 277 | 144 | 5619 | 6040 |
| **total** | 2244 | 1066 | 6690 | 10000 |

`null -> true`: 144 of 6040 truly-null examples (2.38%).

### Per class, after the decision rule

| class | support | predicted | precision | recall | F1 |
|---|---|---|---|---|---|
| `false` | 2479 | 2244 | 81.4% | 73.7% | 77.3% |
| `true` | 1481 | 1066 | 73.1% | 52.6% | 61.2% |
| `null` | 6040 | 6690 | 84.0% | 93.0% | 88.3% |

### By label mode

| label mode | n | eff n | accuracy [95% CI] |
|---|---|---|---|
| false | 2479 | **98** | 73.7% [68.2%, 78.9%] |
| null_ambiguous | 3062 | **224** | 87.6% [85.2%, 89.8%] |
| null_structural | 2978 | **1** | 98.6% [98.6%, 98.6%] |
| true | 1481 | **96** | 52.6% [45.4%, 60.0%] |

### By null sub-class

| sub-class | n | eff n | null recall [95% CI] |
|---|---|---|---|
| attribution | 574 | **43** | 87.1% [81.5%, 92.1%] |
| hedged | 828 | **63** | 77.8% [71.4%, 83.7%] |
| historical | 511 | **36** | 87.5% [82.6%, 91.9%] |
| metaphor | 641 | **47** | 96.3% [93.8%, 98.2%] |
| third_party | 508 | **35** | 93.3% [89.6%, 96.8%] |

### By fragment library

| library | n | eff n | accuracy [95% CI] |
|---|---|---|---|
| fever_false | 2479 | **98** | 73.7% [68.2%, 78.9%] |
| fever_null_attribution | 574 | **43** | 87.1% [81.5%, 92.1%] |
| fever_null_hedged | 828 | **63** | 77.8% [71.4%, 83.7%] |
| fever_null_historical | 511 | **36** | 87.5% [82.6%, 91.9%] |
| fever_null_metaphor | 641 | **47** | 96.3% [93.8%, 98.2%] |
| fever_null_thirdparty | 508 | **35** | 93.3% [89.6%, 96.8%] |
| fever_true | 1481 | **96** | 52.6% [45.4%, 60.0%] |
| (none) | 2978 | **1** | 98.6% [98.6%, 98.6%] |

### Per-fragment errors (worst first)

Whether errors are spread thinly across many fragments or piled onto a few is the difference
between "the method is too weak" (model work) and "these specific ideas are not learnable from
the data we have" (library work, and these are the fragments to write more of). No intervals:
a fragment is one cluster, so an interval over its own examples measures nothing.

281 of 463 decisive fragments were got wrong at least once.

`arm_a_probe`: 1735 errors across 281 of 463 decisive fragments. Half of them fall on **55** fragments (an even spread would be 140.5); the worst ten carry 13.3% of all errors.

| fragment | library | sub-class | truth | correct | accuracy | predicted as |
|---|---|---|---|---|---|---|
| `fever_true:7ef2ecf5` | `fever_true` | -- | true | 0/23 | 0.0% | null 23 |
| `fever_true:7844c66b` | `fever_true` | -- | true | 0/18 | 0.0% | false 2, null 16 |
| `fever_true:80f7ba2e` | `fever_true` | -- | true | 0/13 | 0.0% | null 13 |
| `fever_true:ef344ff7` | `fever_true` | -- | true | 0/13 | 0.0% | null 13 |
| `fever_true:f885b3cb` | `fever_true` | -- | true | 0/13 | 0.0% | null 13 |
| `fever_true:872e3af9` | `fever_true` | -- | true | 0/12 | 0.0% | false 4, null 8 |
| `fever_true:ed36ef0f` | `fever_true` | -- | true | 0/12 | 0.0% | null 12 |
| `fever_null_hedged:17a3f60a` | `fever_null_hedged` | hedged | null | 0/9 | 0.0% | true 9 |
| `fever_true:5ce7adbd` | `fever_true` | -- | true | 0/9 | 0.0% | false 9 |
| `fever_null_historical:2c3501f1` | `fever_null_historical` | historical | null | 0/1 | 0.0% | false 1 |
| `fever_false:033927e6` | `fever_false` | -- | false | 1/26 | 3.8% | false 1, null 25 |
| `fever_true:f0038e34` | `fever_true` | -- | true | 1/21 | 4.8% | true 1, null 20 |
| `fever_true:c7489e90` | `fever_true` | -- | true | 1/19 | 5.3% | false 4, true 1, null 14 |
| `fever_true:391fb2ce` | `fever_true` | -- | true | 1/18 | 5.6% | false 5, true 1, null 12 |
| `fever_true:d00c307b` | `fever_true` | -- | true | 1/14 | 7.1% | true 1, null 13 |
| `fever_true:15a05d92` | `fever_true` | -- | true | 2/24 | 8.3% | false 4, true 2, null 18 |
| `fever_true:74ccf7bd` | `fever_true` | -- | true | 1/12 | 8.3% | true 1, null 11 |
| `fever_false:afdc7129` | `fever_false` | -- | false | 2/22 | 9.1% | false 2, null 20 |
| `fever_false:e0897296` | `fever_false` | -- | false | 2/21 | 9.5% | false 2, true 2, null 17 |
| `fever_true:7cad3f0f` | `fever_true` | -- | true | 2/20 | 10.0% | false 18, true 2 |
| `fever_false:3a3043ff` | `fever_false` | -- | false | 3/29 | 10.3% | false 3, true 10, null 16 |
| `fever_false:ebba1ba0` | `fever_false` | -- | false | 2/16 | 12.5% | false 2, null 14 |
| `fever_true:01833454` | `fever_true` | -- | true | 2/16 | 12.5% | false 12, true 2, null 2 |
| `fever_true:0ddb8a11` | `fever_true` | -- | true | 2/15 | 13.3% | false 1, true 2, null 12 |
| `fever_true:97087dd7` | `fever_true` | -- | true | 2/14 | 14.3% | false 1, true 2, null 11 |
| `fever_true:dd079c14` | `fever_true` | -- | true | 2/14 | 14.3% | false 1, true 2, null 11 |
| `fever_true:ed3c8c83` | `fever_true` | -- | true | 3/19 | 15.8% | true 3, null 16 |
| `fever_true:dd6bbec4` | `fever_true` | -- | true | 4/24 | 16.7% | false 7, true 4, null 13 |
| `fever_true:c76b6243` | `fever_true` | -- | true | 2/12 | 16.7% | true 2, null 10 |
| `fever_true:a6c8dae6` | `fever_true` | -- | true | 1/6 | 16.7% | true 1, null 5 |
| `fever_false:0cc191ec` | `fever_false` | -- | false | 4/23 | 17.4% | false 4, true 3, null 16 |
| `fever_true:511ef08b` | `fever_true` | -- | true | 3/17 | 17.6% | false 2, true 3, null 12 |
| `fever_true:a92fcdc7` | `fever_true` | -- | true | 3/17 | 17.6% | true 3, null 14 |
| `fever_false:cbf9d7a5` | `fever_false` | -- | false | 5/28 | 17.9% | false 5, true 19, null 4 |
| `fever_false:a5b671a1` | `fever_false` | -- | false | 6/32 | 18.8% | false 6, true 26 |
| `fever_true:1c3df822` | `fever_true` | -- | true | 5/26 | 19.2% | false 2, true 5, null 19 |
| `fever_null_hedged:43dc94df` | `fever_null_hedged` | hedged | null | 2/10 | 20.0% | false 8, null 2 |
| `fever_false:e70e24b6` | `fever_false` | -- | false | 6/27 | 22.2% | false 6, true 16, null 5 |
| `fever_null_hedged:42486de4` | `fever_null_hedged` | hedged | null | 3/11 | 27.3% | false 1, true 7, null 3 |
| `fever_null_historical:f26e2926` | `fever_null_historical` | historical | null | 3/11 | 27.3% | false 2, true 6, null 3 |

*241 further fragments with at least one error are in the JSON sidecar; every fragment is there regardless of score.*

## `arm_b_finetune`

`roberta-base` with **every layer unfrozen**, mean-pooled, with the same `Linear(768, 3)` head -- 110M trainable parameters against Arm A's 2,307. Three epochs at batch 32, learning rate 2e-5, 10% linear warmup, AdamW, fp32. No gradient checkpointing, no 8-bit optimiser, no LoRA, no gradient accumulation: the full model fits in 12GB with room to spare, so anything that reads like a compute compromise would be a mistake rather than a saving. This is the arm that separates "the fragment libraries are the bottleneck" from "the method is too weak": if a fully fine-tuned encoder still cannot read third-party attribution, tense or metaphor, the limit is in the ideas the libraries contain and the fix is library work, not model work.

Decision-rule margins selected per fold (on each fold's own validation split): 0.0, 0.45, 0.9.

*Confusion matrix, raw argmax*

|  | pred false | pred true | pred null | total |
|---|---|---|---|---|
| **truth false** | 2376 | 33 | 70 | 2479 |
| **truth true** | 8 | 1292 | 181 | 1481 |
| **truth null** | 71 | 102 | 5867 | 6040 |
| **total** | 2455 | 1427 | 6118 | 10000 |

`null -> true`: 102 of 6040 truly-null examples (1.69%).

*Confusion matrix, after the decision rule*

|  | pred false | pred true | pred null | total |
|---|---|---|---|---|
| **truth false** | 2378 | 26 | 75 | 2479 |
| **truth true** | 10 | 1279 | 192 | 1481 |
| **truth null** | 71 | 98 | 5871 | 6040 |
| **total** | 2459 | 1403 | 6138 | 10000 |

`null -> true`: 98 of 6040 truly-null examples (1.62%).

### Per class, after the decision rule

| class | support | predicted | precision | recall | F1 |
|---|---|---|---|---|---|
| `false` | 2479 | 2459 | 96.7% | 95.9% | 96.3% |
| `true` | 1481 | 1403 | 91.2% | 86.4% | 88.7% |
| `null` | 6040 | 6138 | 95.7% | 97.2% | 96.4% |

### By label mode

| label mode | n | eff n | accuracy [95% CI] |
|---|---|---|---|
| false | 2479 | **98** | 95.9% [92.6%, 98.5%] |
| null_ambiguous | 3062 | **224** | 94.9% [92.0%, 97.3%] |
| null_structural | 2978 | **1** | 99.6% [99.6%, 99.6%] |
| true | 1481 | **96** | 86.4% [79.8%, 92.4%] |

### By null sub-class

| sub-class | n | eff n | null recall [95% CI] |
|---|---|---|---|
| attribution | 574 | **43** | 94.3% [87.9%, 98.9%] |
| hedged | 828 | **63** | 87.7% [79.2%, 95.1%] |
| historical | 511 | **36** | 96.3% [91.4%, 99.6%] |
| metaphor | 641 | **47** | 99.5% [98.9%, 100.0%] |
| third_party | 508 | **35** | 100.0% [100.0%, 100.0%] |

### By fragment library

| library | n | eff n | accuracy [95% CI] |
|---|---|---|---|
| fever_false | 2479 | **98** | 95.9% [92.6%, 98.5%] |
| fever_null_attribution | 574 | **43** | 94.3% [87.9%, 98.9%] |
| fever_null_hedged | 828 | **63** | 87.7% [79.2%, 95.1%] |
| fever_null_historical | 511 | **36** | 96.3% [91.4%, 99.6%] |
| fever_null_metaphor | 641 | **47** | 99.5% [98.9%, 100.0%] |
| fever_null_thirdparty | 508 | **35** | 100.0% [100.0%, 100.0%] |
| fever_true | 1481 | **96** | 86.4% [79.8%, 92.4%] |
| (none) | 2978 | **1** | 99.6% [99.6%, 99.6%] |

### Per-fragment errors (worst first)

Whether errors are spread thinly across many fragments or piled onto a few is the difference
between "the method is too weak" (model work) and "these specific ideas are not learnable from
the data we have" (library work, and these are the fragments to write more of). No intervals:
a fragment is one cluster, so an interval over its own examples measures nothing.

70 of 463 decisive fragments were got wrong at least once.

`arm_b_finetune`: 460 errors across 70 of 463 decisive fragments. Half of them fall on **15** fragments (an even spread would be 35.0); the worst ten carry 38.3% of all errors.

| fragment | library | sub-class | truth | correct | accuracy | predicted as |
|---|---|---|---|---|---|---|
| `fever_true:391fb2ce` | `fever_true` | -- | true | 0/18 | 0.0% | null 18 |
| `fever_true:7844c66b` | `fever_true` | -- | true | 0/18 | 0.0% | false 1, null 17 |
| `fever_null_hedged:081a5883` | `fever_null_hedged` | hedged | null | 0/16 | 0.0% | false 16 |
| `fever_true:0ddb8a11` | `fever_true` | -- | true | 0/15 | 0.0% | null 15 |
| `fever_null_hedged:5bf1b63f` | `fever_null_hedged` | hedged | null | 0/14 | 0.0% | false 1, true 13 |
| `fever_true:97087dd7` | `fever_true` | -- | true | 0/14 | 0.0% | null 14 |
| `fever_null_attribution:17b7ab2a` | `fever_null_attribution` | attribution | null | 0/13 | 0.0% | true 13 |
| `fever_null_hedged:cf95d564` | `fever_null_hedged` | hedged | null | 0/13 | 0.0% | true 13 |
| `fever_true:ef344ff7` | `fever_true` | -- | true | 0/13 | 0.0% | null 13 |
| `fever_true:ed36ef0f` | `fever_true` | -- | true | 0/12 | 0.0% | null 12 |
| `fever_null_hedged:42486de4` | `fever_null_hedged` | hedged | null | 0/11 | 0.0% | false 11 |
| `fever_true:5e4f1da7` | `fever_true` | -- | true | 0/10 | 0.0% | null 10 |
| `fever_null_hedged:965c4a64` | `fever_null_hedged` | hedged | null | 0/9 | 0.0% | false 8, true 1 |
| `fever_true:5ce7adbd` | `fever_true` | -- | true | 0/9 | 0.0% | null 9 |
| `fever_null_historical:1b314733` | `fever_null_historical` | historical | null | 0/8 | 0.0% | true 8 |
| `fever_null_historical:feadcb2c` | `fever_null_historical` | historical | null | 0/8 | 0.0% | true 8 |
| `fever_null_historical:2c3501f1` | `fever_null_historical` | historical | null | 0/1 | 0.0% | false 1 |
| `fever_false:5c2a065d` | `fever_false` | -- | false | 1/30 | 3.3% | false 1, true 2, null 27 |
| `fever_true:c7489e90` | `fever_true` | -- | true | 1/19 | 5.3% | false 1, true 1, null 17 |
| `fever_true:c5d3e4a0` | `fever_true` | -- | true | 1/12 | 8.3% | false 3, true 1, null 8 |
| `fever_true:dd7a11e2` | `fever_true` | -- | true | 1/10 | 10.0% | true 1, null 9 |
| `fever_null_hedged:0de4380d` | `fever_null_hedged` | hedged | null | 3/20 | 15.0% | true 17, null 3 |
| `fever_false:afdc7129` | `fever_false` | -- | false | 5/22 | 22.7% | false 5, null 17 |
| `fever_true:74ccf7bd` | `fever_true` | -- | true | 3/12 | 25.0% | true 3, null 9 |
| `fever_null_attribution:dba8c443` | `fever_null_attribution` | attribution | null | 3/11 | 27.3% | false 8, null 3 |
| `fever_true:b950a4fc` | `fever_true` | -- | true | 3/11 | 27.3% | true 3, null 8 |
| `fever_false:e8c514ff` | `fever_false` | -- | false | 5/16 | 31.2% | false 5, true 11 |
| `fever_true:872e3af9` | `fever_true` | -- | true | 4/12 | 33.3% | true 4, null 8 |
| `fever_null_hedged:8d1c41e3` | `fever_null_hedged` | hedged | null | 3/9 | 33.3% | true 6, null 3 |
| `fever_true:ed3c8c83` | `fever_true` | -- | true | 7/19 | 36.8% | true 7, null 12 |
| `fever_null_hedged:9e333f46` | `fever_null_hedged` | hedged | null | 4/10 | 40.0% | false 6, null 4 |
| `fever_null_attribution:b03cf8b0` | `fever_null_attribution` | attribution | null | 6/11 | 54.5% | true 5, null 6 |
| `fever_false:3a3043ff` | `fever_false` | -- | false | 19/29 | 65.5% | false 19, true 10 |
| `fever_null_hedged:bba323b8` | `fever_null_hedged` | hedged | null | 9/13 | 69.2% | true 4, null 9 |
| `fever_true:2ee57e4c` | `fever_true` | -- | true | 7/10 | 70.0% | true 7, null 3 |
| `fever_false:ebac5db7` | `fever_false` | -- | false | 18/24 | 75.0% | false 18, null 6 |
| `fever_false:3de7ecac` | `fever_false` | -- | false | 21/27 | 77.8% | false 21, null 6 |
| `fever_null_hedged:89a2ef71` | `fever_null_hedged` | hedged | null | 7/9 | 77.8% | false 1, true 1, null 7 |
| `fever_false:44cd09fd` | `fever_false` | -- | false | 22/28 | 78.6% | false 22, null 6 |
| `fever_null_hedged:e15e94ba` | `fever_null_hedged` | hedged | null | 4/5 | 80.0% | false 1, null 4 |

*30 further fragments with at least one error are in the JSON sidecar; every fragment is there regardless of score.*

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
| 2 | 10000 | 2000 | 2000 | 0.0 | 60.5% | 60.5% | 25.8% | 0.00% |
| 3 | 10000 | 2000 | 2000 | 0.0 | 60.8% | 60.8% | 25.3% | 0.00% |
| 4 | 10000 | 2000 | 2000 | 0.0 | 60.3% | 60.3% | 25.3% | 0.00% |

### `tfidf_logreg`

| fold | train n | val n | test n | margin | acc (raw) | acc (ruled) | macro-F1 | null->true |
|---|---|---|---|---|---|---|---|---|
| 0 | 10000 | 2000 | 2000 | 0.0 | 81.3% | 81.3% | 76.1% | 0.74% |
| 1 | 10000 | 2000 | 2000 | 0.0 | 77.7% | 77.7% | 68.5% | 0.75% |
| 2 | 10000 | 2000 | 2000 | 0.0 | 79.7% | 79.7% | 70.0% | 2.57% |
| 3 | 10000 | 2000 | 2000 | 0.0 | 80.9% | 80.9% | 74.4% | 2.14% |
| 4 | 10000 | 2000 | 2000 | 0.0 | 86.1% | 86.1% | 79.1% | 1.33% |

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
| 0 | 10000 | 2000 | 2000 | 0.0 | 60.2% | 60.2% | 25.1% | 0.00% |
| 1 | 10000 | 2000 | 2000 | 0.0 | 59.8% | 59.8% | 25.0% | 0.00% |
| 2 | 10000 | 2000 | 2000 | 0.0 | 60.3% | 60.3% | 25.1% | 0.00% |
| 3 | 10000 | 2000 | 2000 | 0.0 | 60.7% | 60.7% | 25.2% | 0.00% |
| 4 | 10000 | 2000 | 2000 | 0.0 | 60.0% | 60.0% | 25.3% | 0.00% |

### `arm_a_probe`

| fold | train n | val n | test n | margin | acc (raw) | acc (ruled) | macro-F1 | null->true |
|---|---|---|---|---|---|---|---|---|
| 0 | 10000 | 2000 | 2000 | 0.0 | 85.7% | 85.7% | 79.9% | 1.08% |
| 1 | 10000 | 2000 | 2000 | 0.05 | 78.8% | 78.7% | 69.5% | 1.50% |
| 2 | 10000 | 2000 | 2000 | 0.0 | 81.0% | 81.0% | 74.4% | 3.97% |
| 3 | 10000 | 2000 | 2000 | 0.0 | 81.0% | 81.0% | 74.8% | 3.87% |
| 4 | 10000 | 2000 | 2000 | 0.0 | 84.9% | 84.9% | 79.1% | 1.49% |

### `arm_b_finetune`

| fold | train n | val n | test n | margin | acc (raw) | acc (ruled) | macro-F1 | null->true |
|---|---|---|---|---|---|---|---|---|
| 0 | 10000 | 2000 | 2000 | 0.0 | 97.8% | 97.8% | 97.2% | 0.66% |
| 1 | 10000 | 2000 | 2000 | 0.9 | 93.1% | 92.7% | 89.9% | 1.08% |
| 2 | 10000 | 2000 | 2000 | 0.45 | 91.4% | 91.5% | 89.1% | 3.06% |
| 3 | 10000 | 2000 | 2000 | 0.0 | 96.2% | 96.2% | 94.9% | 1.15% |
| 4 | 10000 | 2000 | 2000 | 0.0 | 98.3% | 98.3% | 97.7% | 2.16% |

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

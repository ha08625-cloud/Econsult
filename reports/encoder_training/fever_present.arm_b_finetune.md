# Encoder training: evaluation report

*Generated 2026-08-16T08:44:49+00:00.*

|  |  |
|---|---|
| signal | `fever_present` |
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
| validation guided decisions | `['pooling mode (DD3) -- mean vs CLS, compared once', 'learning rate', "epoch count (the epoch restored is the best-scoring one on the fold's own validation split)", 'decision margin (DD9)']` |
| artefacts | `models/encoder/fever_present/arm_b_finetune` |
| weights | `models/encoder/fever_present/arm_b_finetune/weights -- ~440MB per fold, not committed` |
| model revision | `e2da8e2f811d1448a5b465c236feacd80ffbac7b` |
| revision pinned | `False` |
| tokeniser lowercases | `False` |
| tokeniser vocab size | `50265` |
| tokeniser discards casing | `False` |
| cluster tag coverage | `5 of 7 libraries carry cluster markers; 194 of 463 fragments are in libraries with none` |
| bootstrap | `2000 resamples over clusters, alpha=0.05, seed=0` |

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
| `majority_class` | baseline | 7022 | **418** | 43.6% [38.6%, 48.9%] | 20.2% [18.6%, 21.9%] | 60.4% | 60.4% +/- 0.2% |
| `length_only` | baseline | 7022 | **418** | 43.9% [38.9%, 49.1%] | 21.4% [19.1%, 23.9%] | 60.6% | 60.6% +/- 0.4% |
| `tfidf_logreg` | baseline | 7022 | **418** | 73.6% [70.0%, 77.3%] | 70.8% [66.7%, 74.6%] | 81.4% | 81.4% +/- 3.1% |
| `length_only__shuffled` | negative control | 7022 | **418** | 43.6% [38.6%, 48.9%] | 20.2% [18.6%, 21.9%] | 60.4% | 60.4% +/- 0.2% |
| `tfidf_logreg__shuffled` | negative control | 7022 | **418** | 43.6% [38.6%, 48.9%] | 20.3% [18.6%, 21.9%] | 60.4% | 60.4% +/- 0.2% |
| `arm_a_probe` | probe | 7022 | **418** | 79.0% [76.2%, 81.6%] | 76.9% [73.8%, 79.8%] | 85.0% | 85.0% +/- 2.8% |
| `arm_b_finetune` | finetune | 7022 | **418** | 92.9% [90.6%, 95.0%] | 92.3% [89.7%, 94.6%] | 95.0% | 95.0% +/- 2.9% |
| `arm_b_finetune__shuffled` | negative control | 7022 | **418** | 43.6% [38.6%, 48.9%] | 20.2% [18.6%, 21.9%] | 60.4% | 60.4% +/- 0.2% |

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
| `length_only` | -- | 99.8% [99.4%, 100.0%] (eff n 43) | 99.9% [99.6%, 100.0%] (eff n 63) | 100.0% [100.0%, 100.0%] (eff n 36) | 99.8% [99.5%, 100.0%] (eff n 47) | 100.0% [100.0%, 100.0%] (eff n 35) |
| `tfidf_logreg` | -- | 95.3% [92.1%, 98.0%] (eff n 43) | 90.0% [82.4%, 96.0%] (eff n 63) | 92.9% [87.3%, 97.1%] (eff n 36) | 97.5% [95.2%, 99.2%] (eff n 47) | 93.7% [90.7%, 96.7%] (eff n 35) |
| `length_only__shuffled` | -- | 100.0% [100.0%, 100.0%] (eff n 43) | 100.0% [100.0%, 100.0%] (eff n 63) | 100.0% [100.0%, 100.0%] (eff n 36) | 100.0% [100.0%, 100.0%] (eff n 47) | 100.0% [100.0%, 100.0%] (eff n 35) |
| `tfidf_logreg__shuffled` | -- | 100.0% [100.0%, 100.0%] (eff n 43) | 100.0% [100.0%, 100.0%] (eff n 63) | 100.0% [100.0%, 100.0%] (eff n 36) | 100.0% [100.0%, 100.0%] (eff n 47) | 100.0% [100.0%, 100.0%] (eff n 35) |
| `arm_a_probe` | -- | 88.9% [82.7%, 94.0%] (eff n 43) | 81.9% [75.4%, 87.6%] (eff n 63) | 90.2% [84.4%, 94.7%] (eff n 36) | 94.9% [91.3%, 97.6%] (eff n 47) | 92.3% [88.1%, 96.4%] (eff n 35) |
| `arm_b_finetune` | -- | 96.3% [91.5%, 99.7%] (eff n 43) | 88.8% [80.1%, 95.7%] (eff n 63) | 96.3% [91.5%, 99.8%] (eff n 36) | 99.5% [98.5%, 100.0%] (eff n 47) | 100.0% [100.0%, 100.0%] (eff n 35) |
| `arm_b_finetune__shuffled` | -- | 100.0% [100.0%, 100.0%] (eff n 43) | 100.0% [100.0%, 100.0%] (eff n 63) | 100.0% [100.0%, 100.0%] (eff n 36) | 100.0% [100.0%, 100.0%] (eff n 47) | 100.0% [100.0%, 100.0%] (eff n 35) |

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
| `tfidf_logreg` | baseline | 3062 | **224** | 93.7% [91.3%, 95.7%] |
| `arm_a_probe` | probe | 3062 | **224** | 89.0% [86.5%, 91.4%] |
| `arm_b_finetune` | finetune | 3062 | **224** | 95.6% [93.0%, 97.8%] |

### 2. The same comparison, paired

Two overlapping intervals do not settle whether one model beats another on the same
examples. McNemar does, over the examples the two disagree about -- read it alongside the
intervals above, never instead of them.

| pair | n | a only | b only | p |
|---|---|---|---|---|
| `majority_class` vs `length_only` | 3062 | 3 | 0 | 0.25 |
| `majority_class` vs `tfidf_logreg` | 3062 | 194 | 0 | 7.97e-59 |
| `majority_class` vs `arm_a_probe` | 3062 | 336 | 0 | 1.43e-101 |
| `majority_class` vs `arm_b_finetune` | 3062 | 148 | 0 | 5.61e-45 |
| `length_only` vs `tfidf_logreg` | 3062 | 194 | 3 | 1.27e-53 |
| `length_only` vs `arm_a_probe` | 3062 | 334 | 1 | 9.6e-99 |
| `length_only` vs `arm_b_finetune` | 3062 | 147 | 2 | 3.13e-41 |
| `tfidf_logreg` vs `arm_a_probe` | 3062 | 267 | 125 | 5.99e-13 |
| `tfidf_logreg` vs `arm_b_finetune` | 3062 | 87 | 133 | 0.00234 |
| `arm_a_probe` vs `arm_b_finetune` | 3062 | 83 | 271 | 2.09e-24 |

### 3. Where the errors fall

The per-fragment table below, as one number per model. Errors spread thinly across many
fragments say the method is too weak. Errors piled onto a handful say those specific ideas
are not learnable from the data we have -- and the table names them, which is what makes
this the most decision-useful thing in the report.

* `majority_class`: 3960 errors across 194 of 463 decisive fragments. Half of them fall on **71** fragments (an even spread would be 97.0); the worst ten carry 8.9% of all errors.
* `length_only`: 3939 errors across 196 of 463 decisive fragments. Half of them fall on **70** fragments (an even spread would be 98.0); the worst ten carry 9.0% of all errors.
* `tfidf_logreg`: 1851 errors across 205 of 463 decisive fragments. Half of them fall on **46** fragments (an even spread would be 102.5); the worst ten carry 15.0% of all errors.
* `arm_a_probe`: 1477 errors across 263 of 463 decisive fragments. Half of them fall on **52** fragments (an even spread would be 131.5); the worst ten carry 15.0% of all errors.
* `arm_b_finetune`: 496 errors across 60 of 463 decisive fragments. Half of them fall on **14** fragments (an even spread would be 30.0); the worst ten carry 41.3% of all errors.

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

Shuffled-label controls, evaluated on the **unpermuted** test split. A large model will
memorise permuted training labels and drive train loss to zero; that is correct behaviour
and says nothing. Only the test score is the control.

| control | accuracy [95% CI] | macro-F1 [95% CI] |
|---|---|---|
| `length_only__shuffled` | 60.4% [39.9%, 76.5%] | 25.1% [19.0%, 28.9%] |
| `tfidf_logreg__shuffled` | 60.4% [39.9%, 76.5%] | 25.1% [19.0%, 28.9%] |
| `arm_b_finetune__shuffled` | 60.4% [39.9%, 76.5%] | 25.1% [19.0%, 28.9%] |

## Paired comparisons (McNemar, raw argmax)

Exact two-sided McNemar over the examples the two models disagree about. Pairing unit is the
example, not the cluster -- see the limitations.

| pair | slice | n | a only | b only | p |
|---|---|---|---|---|---|
| `majority_class` vs `length_only` | overall | 10000 | 3 | 24 | 4.92e-05 |
| `majority_class` vs `length_only` | null_ambiguous | 3062 | 3 | 0 | 0.25 |
| `majority_class` vs `tfidf_logreg` | overall | 10000 | 201 | 2303 | 0 |
| `majority_class` vs `tfidf_logreg` | null_ambiguous | 3062 | 194 | 0 | 7.97e-59 |
| `majority_class` vs `arm_a_probe` | overall | 10000 | 361 | 2819 | 0 |
| `majority_class` vs `arm_a_probe` | null_ambiguous | 3062 | 336 | 0 | 1.43e-101 |
| `majority_class` vs `arm_b_finetune` | overall | 10000 | 148 | 3606 | 0 |
| `majority_class` vs `arm_b_finetune` | null_ambiguous | 3062 | 148 | 0 | 5.61e-45 |
| `length_only` vs `tfidf_logreg` | overall | 10000 | 202 | 2283 | 0 |
| `length_only` vs `tfidf_logreg` | null_ambiguous | 3062 | 194 | 3 | 1.27e-53 |
| `length_only` vs `arm_a_probe` | overall | 10000 | 376 | 2813 | 0 |
| `length_only` vs `arm_a_probe` | null_ambiguous | 3062 | 334 | 1 | 9.6e-99 |
| `length_only` vs `arm_b_finetune` | overall | 10000 | 147 | 3584 | 0 |
| `length_only` vs `arm_b_finetune` | null_ambiguous | 3062 | 147 | 2 | 3.13e-41 |
| `tfidf_logreg` vs `arm_a_probe` | overall | 10000 | 617 | 973 | 3.89e-19 |
| `tfidf_logreg` vs `arm_a_probe` | null_ambiguous | 3062 | 267 | 125 | 5.99e-13 |
| `tfidf_logreg` vs `arm_b_finetune` | overall | 10000 | 158 | 1514 | 5.04e-278 |
| `tfidf_logreg` vs `arm_b_finetune` | null_ambiguous | 3062 | 87 | 133 | 0.00234 |
| `arm_a_probe` vs `arm_b_finetune` | overall | 10000 | 212 | 1212 | 2.51e-170 |
| `arm_a_probe` vs `arm_b_finetune` | null_ambiguous | 3062 | 83 | 271 | 2.09e-24 |

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
| `fever_false` | 2479 | 0.0% | 0.1% | 63.7% | 77.9% | 92.9% | 92.9pp |
| `fever_true` | 1481 | 0.0% | 1.4% | 48.9% | 60.0% | 87.6% | 87.6pp |
| `fever_null_hedged` | 833 | 100.0% | 99.9% | 90.0% | 81.9% | 88.8% | 18.1pp |
| `fever_null_attribution` | 569 | 100.0% | 99.8% | 95.3% | 88.9% | 96.3% | 11.1pp |
| `fever_null_historical` | 508 | 100.0% | 100.0% | 92.9% | 90.2% | 96.3% | 9.8pp |
| `fever_null_thirdparty` | 508 | 100.0% | 100.0% | 93.7% | 92.3% | 100.0% | 7.7pp |
| `fever_null_metaphor` | 644 | 100.0% | 99.8% | 97.5% | 94.9% | 99.5% | 5.1pp |
| `(none)` | 2978 | 100.0% | 100.0% | 99.8% | 99.2% | 100.0% | 0.8pp |

### By fragment, errors

Ordered by the worst model's error count, so the fragments the comparison is about sort
to the top whichever encoder wins. Counts, not rates: these are the sentences a month of
library work would be spent on. The JSON holds every fragment.

| fragment | library | truth | `majority_class` | `length_only` | `tfidf_logreg` | `arm_a_probe` | `arm_b_finetune` | spread |
|---|---|---|---|---|---|---|---|---|
| `fever_false:5a6a9b80` | `fever_false` | false | 42 | 42 | 0 | 1 | 0 | 42 |
| `fever_false:24e5c247` | `fever_false` | false | 37 | 37 | 9 | 6 | 0 | 37 |
| `fever_false:d0ca84a7` | `fever_false` | false | 37 | 37 | 0 | 0 | 0 | 37 |
| `fever_false:fc2ae0f2` | `fever_false` | false | 37 | 37 | 5 | 3 | 3 | 34 |
| `fever_false:17f6c637` | `fever_false` | false | 35 | 35 | 0 | 2 | 0 | 35 |
| `fever_false:9f46e710` | `fever_false` | false | 34 | 34 | 3 | 8 | 0 | 34 |
| `fever_false:55bf1913` | `fever_false` | false | 33 | 33 | 0 | 0 | 0 | 33 |
| `fever_false:5969c6c9` | `fever_false` | false | 33 | 33 | 0 | 7 | 0 | 33 |
| `fever_false:a9a0220e` | `fever_false` | false | 33 | 33 | 0 | 1 | 0 | 33 |
| `fever_false:b9076eff` | `fever_false` | false | 33 | 33 | 17 | 20 | 0 | 33 |
| `fever_false:b96ed279` | `fever_false` | false | 33 | 33 | 33 | 10 | 0 | 33 |
| `fever_false:f586e96d` | `fever_false` | false | 33 | 33 | 15 | 25 | 0 | 33 |
| `fever_false:2b944abc` | `fever_false` | false | 32 | 32 | 0 | 0 | 0 | 32 |
| `fever_false:cdf2609b` | `fever_false` | false | 32 | 32 | 31 | 5 | 1 | 31 |
| `fever_false:de0596c4` | `fever_false` | false | 32 | 32 | 17 | 9 | 0 | 32 |
| `fever_false:0429068c` | `fever_false` | false | 31 | 31 | 25 | 0 | 0 | 31 |
| `fever_false:a5b671a1` | `fever_false` | false | 31 | 31 | 16 | 26 | 1 | 30 |
| `fever_false:147d5cf0` | `fever_false` | false | 30 | 30 | 16 | 1 | 0 | 30 |
| `fever_false:56a45ff1` | `fever_false` | false | 30 | 30 | 6 | 4 | 0 | 30 |
| `fever_false:5c2a065d` | `fever_false` | false | 30 | 30 | 30 | 10 | 30 | 20 |
| `fever_false:8d02bd9e` | `fever_false` | false | 30 | 30 | 24 | 11 | 0 | 30 |
| `fever_false:d5ed3ff1` | `fever_false` | false | 30 | 30 | 18 | 5 | 0 | 30 |
| `fever_false:e2aff3b8` | `fever_false` | false | 30 | 30 | 16 | 1 | 0 | 30 |
| `fever_false:758d5434` | `fever_false` | false | 29 | 29 | 0 | 0 | 0 | 29 |
| `fever_false:cbf9d7a5` | `fever_false` | false | 29 | 29 | 29 | 27 | 9 | 20 |
| `fever_true:18173593` | `fever_true` | true | 29 | 29 | 13 | 16 | 0 | 29 |
| `fever_false:033927e6` | `fever_false` | false | 28 | 28 | 28 | 22 | 0 | 28 |
| `fever_false:3a3043ff` | `fever_false` | false | 28 | 28 | 17 | 20 | 28 | 11 |
| `fever_false:463f8189` | `fever_false` | false | 28 | 28 | 0 | 0 | 0 | 28 |
| `fever_false:7b64d17a` | `fever_false` | false | 28 | 28 | 20 | 4 | 0 | 28 |
| `fever_false:a4cda1e2` | `fever_false` | false | 28 | 28 | 0 | 0 | 0 | 28 |
| `fever_false:a6c0d44a` | `fever_false` | false | 28 | 28 | 11 | 0 | 0 | 28 |
| `fever_true:f3ee0d07` | `fever_true` | true | 28 | 28 | 0 | 0 | 0 | 28 |
| `fever_false:3de7ecac` | `fever_false` | false | 27 | 27 | 26 | 13 | 18 | 14 |
| `fever_false:43f5b35d` | `fever_false` | false | 27 | 27 | 5 | 0 | 0 | 27 |
| `fever_false:90f7b87f` | `fever_false` | false | 27 | 27 | 0 | 3 | 0 | 27 |
| `fever_false:c747066d` | `fever_false` | false | 27 | 27 | 2 | 1 | 0 | 27 |
| `fever_true:753c7815` | `fever_true` | true | 27 | 27 | 0 | 0 | 0 | 27 |
| `fever_false:4bf3caad` | `fever_false` | false | 26 | 26 | 1 | 7 | 0 | 26 |
| `fever_false:8599e318` | `fever_false` | false | 26 | 26 | 0 | 1 | 0 | 26 |

*288 further fragments erred on at least one model; the JSON holds them all.*

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
| attribution | 569 | **43** | 100.0% [100.0%, 100.0%] |
| hedged | 833 | **63** | 100.0% [100.0%, 100.0%] |
| historical | 508 | **36** | 100.0% [100.0%, 100.0%] |
| metaphor | 644 | **47** | 100.0% [100.0%, 100.0%] |
| third_party | 508 | **35** | 100.0% [100.0%, 100.0%] |

### By fragment library

| library | n | eff n | accuracy [95% CI] |
|---|---|---|---|
| fever_false | 2479 | **98** | 0.0% [0.0%, 0.0%] |
| fever_null_attribution | 569 | **43** | 100.0% [100.0%, 100.0%] |
| fever_null_hedged | 833 | **63** | 100.0% [100.0%, 100.0%] |
| fever_null_historical | 508 | **36** | 100.0% [100.0%, 100.0%] |
| fever_null_metaphor | 644 | **47** | 100.0% [100.0%, 100.0%] |
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
| `fever_false:5a6a9b80` | `fever_false` | -- | false | 0/42 | 0.0% | null 42 |
| `fever_false:24e5c247` | `fever_false` | -- | false | 0/37 | 0.0% | null 37 |
| `fever_false:d0ca84a7` | `fever_false` | -- | false | 0/37 | 0.0% | null 37 |
| `fever_false:fc2ae0f2` | `fever_false` | -- | false | 0/37 | 0.0% | null 37 |
| `fever_false:17f6c637` | `fever_false` | -- | false | 0/35 | 0.0% | null 35 |
| `fever_false:9f46e710` | `fever_false` | -- | false | 0/34 | 0.0% | null 34 |
| `fever_false:55bf1913` | `fever_false` | -- | false | 0/33 | 0.0% | null 33 |
| `fever_false:5969c6c9` | `fever_false` | -- | false | 0/33 | 0.0% | null 33 |
| `fever_false:a9a0220e` | `fever_false` | -- | false | 0/33 | 0.0% | null 33 |
| `fever_false:b9076eff` | `fever_false` | -- | false | 0/33 | 0.0% | null 33 |
| `fever_false:b96ed279` | `fever_false` | -- | false | 0/33 | 0.0% | null 33 |
| `fever_false:f586e96d` | `fever_false` | -- | false | 0/33 | 0.0% | null 33 |
| `fever_false:2b944abc` | `fever_false` | -- | false | 0/32 | 0.0% | null 32 |
| `fever_false:cdf2609b` | `fever_false` | -- | false | 0/32 | 0.0% | null 32 |
| `fever_false:de0596c4` | `fever_false` | -- | false | 0/32 | 0.0% | null 32 |
| `fever_false:0429068c` | `fever_false` | -- | false | 0/31 | 0.0% | null 31 |
| `fever_false:a5b671a1` | `fever_false` | -- | false | 0/31 | 0.0% | null 31 |
| `fever_false:147d5cf0` | `fever_false` | -- | false | 0/30 | 0.0% | null 30 |
| `fever_false:56a45ff1` | `fever_false` | -- | false | 0/30 | 0.0% | null 30 |
| `fever_false:5c2a065d` | `fever_false` | -- | false | 0/30 | 0.0% | null 30 |
| `fever_false:8d02bd9e` | `fever_false` | -- | false | 0/30 | 0.0% | null 30 |
| `fever_false:d5ed3ff1` | `fever_false` | -- | false | 0/30 | 0.0% | null 30 |
| `fever_false:e2aff3b8` | `fever_false` | -- | false | 0/30 | 0.0% | null 30 |
| `fever_false:758d5434` | `fever_false` | -- | false | 0/29 | 0.0% | null 29 |
| `fever_false:cbf9d7a5` | `fever_false` | -- | false | 0/29 | 0.0% | null 29 |
| `fever_true:18173593` | `fever_true` | -- | true | 0/29 | 0.0% | null 29 |
| `fever_false:033927e6` | `fever_false` | -- | false | 0/28 | 0.0% | null 28 |
| `fever_false:3a3043ff` | `fever_false` | -- | false | 0/28 | 0.0% | null 28 |
| `fever_false:463f8189` | `fever_false` | -- | false | 0/28 | 0.0% | null 28 |
| `fever_false:7b64d17a` | `fever_false` | -- | false | 0/28 | 0.0% | null 28 |
| `fever_false:a4cda1e2` | `fever_false` | -- | false | 0/28 | 0.0% | null 28 |
| `fever_false:a6c0d44a` | `fever_false` | -- | false | 0/28 | 0.0% | null 28 |
| `fever_true:f3ee0d07` | `fever_true` | -- | true | 0/28 | 0.0% | null 28 |
| `fever_false:3de7ecac` | `fever_false` | -- | false | 0/27 | 0.0% | null 27 |
| `fever_false:43f5b35d` | `fever_false` | -- | false | 0/27 | 0.0% | null 27 |
| `fever_false:90f7b87f` | `fever_false` | -- | false | 0/27 | 0.0% | null 27 |
| `fever_false:c747066d` | `fever_false` | -- | false | 0/27 | 0.0% | null 27 |
| `fever_true:753c7815` | `fever_true` | -- | true | 0/27 | 0.0% | null 27 |
| `fever_false:4bf3caad` | `fever_false` | -- | false | 0/26 | 0.0% | null 26 |
| `fever_false:8599e318` | `fever_false` | -- | false | 0/26 | 0.0% | null 26 |

*154 further fragments with at least one error are in the JSON sidecar; every fragment is there regardless of score.*

## `length_only`

Logistic regression on token count alone. The direct measurable test of the length leak: anything materially above majority means text length is a usable proxy for the label, which is a fragment-library problem rather than a model one.

Decision-rule margins selected per fold (on each fold's own validation split): 0.0.
Every fold selected margin 0, so the ruled and raw views below are the same decisions. That is a finding rather than a bug: no margin improved macro-F1 without worsening the `null -> true` rate.

*Confusion matrix, raw argmax*

|  | pred false | pred true | pred null | total |
|---|---|---|---|---|
| **truth false** | 3 | 0 | 2476 | 2479 |
| **truth true** | 43 | 21 | 1417 | 1481 |
| **truth null** | 3 | 0 | 6037 | 6040 |
| **total** | 49 | 21 | 9930 | 10000 |

`null -> true`: 0 of 6040 truly-null examples (0.00%).

*Confusion matrix, after the decision rule*

|  | pred false | pred true | pred null | total |
|---|---|---|---|---|
| **truth false** | 3 | 0 | 2476 | 2479 |
| **truth true** | 43 | 21 | 1417 | 1481 |
| **truth null** | 3 | 0 | 6037 | 6040 |
| **total** | 49 | 21 | 9930 | 10000 |

`null -> true`: 0 of 6040 truly-null examples (0.00%).

### Per class, after the decision rule

| class | support | predicted | precision | recall | F1 |
|---|---|---|---|---|---|
| `false` | 2479 | 49 | 6.1% | 0.1% | 0.2% |
| `true` | 1481 | 21 | 100.0% | 1.4% | 2.8% |
| `null` | 6040 | 9930 | 60.8% | 100.0% | 75.6% |

### By label mode

| label mode | n | eff n | accuracy [95% CI] |
|---|---|---|---|
| false | 2479 | **98** | 0.1% [0.0%, 0.3%] |
| null_ambiguous | 3062 | **224** | 99.9% [99.8%, 100.0%] |
| null_structural | 2978 | **1** | 100.0% [100.0%, 100.0%] |
| true | 1481 | **96** | 1.4% [0.0%, 4.4%] |

### By null sub-class

| sub-class | n | eff n | null recall [95% CI] |
|---|---|---|---|
| attribution | 569 | **43** | 99.8% [99.4%, 100.0%] |
| hedged | 833 | **63** | 99.9% [99.6%, 100.0%] |
| historical | 508 | **36** | 100.0% [100.0%, 100.0%] |
| metaphor | 644 | **47** | 99.8% [99.5%, 100.0%] |
| third_party | 508 | **35** | 100.0% [100.0%, 100.0%] |

### By fragment library

| library | n | eff n | accuracy [95% CI] |
|---|---|---|---|
| fever_false | 2479 | **98** | 0.1% [0.0%, 0.3%] |
| fever_null_attribution | 569 | **43** | 99.8% [99.4%, 100.0%] |
| fever_null_hedged | 833 | **63** | 99.9% [99.6%, 100.0%] |
| fever_null_historical | 508 | **36** | 100.0% [100.0%, 100.0%] |
| fever_null_metaphor | 644 | **47** | 99.8% [99.5%, 100.0%] |
| fever_null_thirdparty | 508 | **35** | 100.0% [100.0%, 100.0%] |
| fever_true | 1481 | **96** | 1.4% [0.0%, 4.4%] |
| (none) | 2978 | **1** | 100.0% [100.0%, 100.0%] |

### Per-fragment errors (worst first)

Whether errors are spread thinly across many fragments or piled onto a few is the difference
between "the method is too weak" (model work) and "these specific ideas are not learnable from
the data we have" (library work, and these are the fragments to write more of). No intervals:
a fragment is one cluster, so an interval over its own examples measures nothing.

196 of 463 decisive fragments were got wrong at least once.

`length_only`: 3939 errors across 196 of 463 decisive fragments. Half of them fall on **70** fragments (an even spread would be 98.0); the worst ten carry 9.0% of all errors.

| fragment | library | sub-class | truth | correct | accuracy | predicted as |
|---|---|---|---|---|---|---|
| `fever_false:5a6a9b80` | `fever_false` | -- | false | 0/42 | 0.0% | null 42 |
| `fever_false:24e5c247` | `fever_false` | -- | false | 0/37 | 0.0% | null 37 |
| `fever_false:d0ca84a7` | `fever_false` | -- | false | 0/37 | 0.0% | null 37 |
| `fever_false:fc2ae0f2` | `fever_false` | -- | false | 0/37 | 0.0% | null 37 |
| `fever_false:17f6c637` | `fever_false` | -- | false | 0/35 | 0.0% | null 35 |
| `fever_false:9f46e710` | `fever_false` | -- | false | 0/34 | 0.0% | null 34 |
| `fever_false:55bf1913` | `fever_false` | -- | false | 0/33 | 0.0% | null 33 |
| `fever_false:5969c6c9` | `fever_false` | -- | false | 0/33 | 0.0% | null 33 |
| `fever_false:a9a0220e` | `fever_false` | -- | false | 0/33 | 0.0% | null 33 |
| `fever_false:b9076eff` | `fever_false` | -- | false | 0/33 | 0.0% | null 33 |
| `fever_false:b96ed279` | `fever_false` | -- | false | 0/33 | 0.0% | null 33 |
| `fever_false:f586e96d` | `fever_false` | -- | false | 0/33 | 0.0% | null 33 |
| `fever_false:2b944abc` | `fever_false` | -- | false | 0/32 | 0.0% | null 32 |
| `fever_false:cdf2609b` | `fever_false` | -- | false | 0/32 | 0.0% | null 32 |
| `fever_false:de0596c4` | `fever_false` | -- | false | 0/32 | 0.0% | null 32 |
| `fever_false:0429068c` | `fever_false` | -- | false | 0/31 | 0.0% | null 31 |
| `fever_false:a5b671a1` | `fever_false` | -- | false | 0/31 | 0.0% | null 31 |
| `fever_false:147d5cf0` | `fever_false` | -- | false | 0/30 | 0.0% | null 30 |
| `fever_false:56a45ff1` | `fever_false` | -- | false | 0/30 | 0.0% | null 30 |
| `fever_false:5c2a065d` | `fever_false` | -- | false | 0/30 | 0.0% | null 30 |
| `fever_false:8d02bd9e` | `fever_false` | -- | false | 0/30 | 0.0% | null 30 |
| `fever_false:d5ed3ff1` | `fever_false` | -- | false | 0/30 | 0.0% | null 30 |
| `fever_false:e2aff3b8` | `fever_false` | -- | false | 0/30 | 0.0% | null 30 |
| `fever_false:758d5434` | `fever_false` | -- | false | 0/29 | 0.0% | null 29 |
| `fever_false:cbf9d7a5` | `fever_false` | -- | false | 0/29 | 0.0% | null 29 |
| `fever_true:18173593` | `fever_true` | -- | true | 0/29 | 0.0% | null 29 |
| `fever_false:033927e6` | `fever_false` | -- | false | 0/28 | 0.0% | null 28 |
| `fever_false:3a3043ff` | `fever_false` | -- | false | 0/28 | 0.0% | null 28 |
| `fever_false:463f8189` | `fever_false` | -- | false | 0/28 | 0.0% | null 28 |
| `fever_false:7b64d17a` | `fever_false` | -- | false | 0/28 | 0.0% | null 28 |
| `fever_false:a4cda1e2` | `fever_false` | -- | false | 0/28 | 0.0% | null 28 |
| `fever_false:a6c0d44a` | `fever_false` | -- | false | 0/28 | 0.0% | null 28 |
| `fever_true:f3ee0d07` | `fever_true` | -- | true | 0/28 | 0.0% | false 28 |
| `fever_false:3de7ecac` | `fever_false` | -- | false | 0/27 | 0.0% | null 27 |
| `fever_false:43f5b35d` | `fever_false` | -- | false | 0/27 | 0.0% | null 27 |
| `fever_false:90f7b87f` | `fever_false` | -- | false | 0/27 | 0.0% | null 27 |
| `fever_false:c747066d` | `fever_false` | -- | false | 0/27 | 0.0% | null 27 |
| `fever_true:753c7815` | `fever_true` | -- | true | 0/27 | 0.0% | null 27 |
| `fever_false:4bf3caad` | `fever_false` | -- | false | 0/26 | 0.0% | null 26 |
| `fever_false:8599e318` | `fever_false` | -- | false | 0/26 | 0.0% | null 26 |

*156 further fragments with at least one error are in the JSON sidecar; every fragment is there regardless of score.*

## `tfidf_logreg`

TF-IDF unigrams and bigrams into logistic regression. Tests whether the dataset is keyword-solvable. Its overall accuracy is close to uninformative; the `null_ambiguous` slice is the number that matters.

Decision-rule margins selected per fold (on each fold's own validation split): 0.0.
Every fold selected margin 0, so the ruled and raw views below are the same decisions. That is a finding rather than a bug: no margin improved macro-F1 without worsening the `null -> true` rate.

*Confusion matrix, raw argmax*

|  | pred false | pred true | pred null | total |
|---|---|---|---|---|
| **truth false** | 1579 | 113 | 787 | 2479 |
| **truth true** | 83 | 724 | 674 | 1481 |
| **truth null** | 138 | 63 | 5839 | 6040 |
| **total** | 1800 | 900 | 7300 | 10000 |

`null -> true`: 63 of 6040 truly-null examples (1.04%).

*Confusion matrix, after the decision rule*

|  | pred false | pred true | pred null | total |
|---|---|---|---|---|
| **truth false** | 1579 | 113 | 787 | 2479 |
| **truth true** | 83 | 724 | 674 | 1481 |
| **truth null** | 138 | 63 | 5839 | 6040 |
| **total** | 1800 | 900 | 7300 | 10000 |

`null -> true`: 63 of 6040 truly-null examples (1.04%).

### Per class, after the decision rule

| class | support | predicted | precision | recall | F1 |
|---|---|---|---|---|---|
| `false` | 2479 | 1800 | 87.7% | 63.7% | 73.8% |
| `true` | 1481 | 900 | 80.4% | 48.9% | 60.8% |
| `null` | 6040 | 7300 | 80.0% | 96.7% | 87.5% |

### By label mode

| label mode | n | eff n | accuracy [95% CI] |
|---|---|---|---|
| false | 2479 | **98** | 63.7% [56.5%, 70.9%] |
| null_ambiguous | 3062 | **224** | 93.7% [91.3%, 95.7%] |
| null_structural | 2978 | **1** | 99.8% [99.8%, 99.8%] |
| true | 1481 | **96** | 48.9% [40.4%, 57.7%] |

### By null sub-class

| sub-class | n | eff n | null recall [95% CI] |
|---|---|---|---|
| attribution | 569 | **43** | 95.3% [92.1%, 98.0%] |
| hedged | 833 | **63** | 90.0% [82.4%, 96.0%] |
| historical | 508 | **36** | 92.9% [87.3%, 97.1%] |
| metaphor | 644 | **47** | 97.5% [95.2%, 99.2%] |
| third_party | 508 | **35** | 93.7% [90.7%, 96.7%] |

### By fragment library

| library | n | eff n | accuracy [95% CI] |
|---|---|---|---|
| fever_false | 2479 | **98** | 63.7% [56.5%, 70.9%] |
| fever_null_attribution | 569 | **43** | 95.3% [92.1%, 98.0%] |
| fever_null_hedged | 833 | **63** | 90.0% [82.4%, 96.0%] |
| fever_null_historical | 508 | **36** | 92.9% [87.3%, 97.1%] |
| fever_null_metaphor | 644 | **47** | 97.5% [95.2%, 99.2%] |
| fever_null_thirdparty | 508 | **35** | 93.7% [90.7%, 96.7%] |
| fever_true | 1481 | **96** | 48.9% [40.4%, 57.7%] |
| (none) | 2978 | **1** | 99.8% [99.8%, 99.8%] |

### Per-fragment errors (worst first)

Whether errors are spread thinly across many fragments or piled onto a few is the difference
between "the method is too weak" (model work) and "these specific ideas are not learnable from
the data we have" (library work, and these are the fragments to write more of). No intervals:
a fragment is one cluster, so an interval over its own examples measures nothing.

205 of 463 decisive fragments were got wrong at least once.

`tfidf_logreg`: 1851 errors across 205 of 463 decisive fragments. Half of them fall on **46** fragments (an even spread would be 102.5); the worst ten carry 15.0% of all errors.

| fragment | library | sub-class | truth | correct | accuracy | predicted as |
|---|---|---|---|---|---|---|
| `fever_false:b96ed279` | `fever_false` | -- | false | 0/33 | 0.0% | null 33 |
| `fever_false:5c2a065d` | `fever_false` | -- | false | 0/30 | 0.0% | null 30 |
| `fever_false:cbf9d7a5` | `fever_false` | -- | false | 0/29 | 0.0% | null 29 |
| `fever_false:033927e6` | `fever_false` | -- | false | 0/28 | 0.0% | null 28 |
| `fever_false:44cd09fd` | `fever_false` | -- | false | 0/25 | 0.0% | null 25 |
| `fever_true:3d00c372` | `fever_true` | -- | true | 0/25 | 0.0% | null 25 |
| `fever_true:dd6bbec4` | `fever_true` | -- | true | 0/25 | 0.0% | null 25 |
| `fever_false:b74a83cf` | `fever_false` | -- | false | 0/23 | 0.0% | null 23 |
| `fever_false:f1b6ac0d` | `fever_false` | -- | false | 0/23 | 0.0% | true 1, null 22 |
| `fever_false:afdc7129` | `fever_false` | -- | false | 0/22 | 0.0% | null 22 |
| `fever_false:bf61fab6` | `fever_false` | -- | false | 0/22 | 0.0% | null 22 |
| `fever_false:f6985a04` | `fever_false` | -- | false | 0/21 | 0.0% | true 4, null 17 |
| `fever_true:391fb2ce` | `fever_true` | -- | true | 0/18 | 0.0% | false 1, null 17 |
| `fever_true:7844c66b` | `fever_true` | -- | true | 0/18 | 0.0% | null 18 |
| `fever_true:c7489e90` | `fever_true` | -- | true | 0/18 | 0.0% | null 18 |
| `fever_true:cf13c84f` | `fever_true` | -- | true | 0/17 | 0.0% | null 17 |
| `fever_true:01833454` | `fever_true` | -- | true | 0/16 | 0.0% | false 11, null 5 |
| `fever_false:f1e3b80c` | `fever_false` | -- | false | 0/15 | 0.0% | null 15 |
| `fever_null_hedged:18ebc3eb` | `fever_null_hedged` | hedged | null | 0/14 | 0.0% | false 14 |
| `fever_true:0ddb8a11` | `fever_true` | -- | true | 0/14 | 0.0% | null 14 |
| `fever_true:199d4eb4` | `fever_true` | -- | true | 0/14 | 0.0% | null 14 |
| `fever_true:79211e25` | `fever_true` | -- | true | 0/14 | 0.0% | null 14 |
| `fever_true:d00c307b` | `fever_true` | -- | true | 0/14 | 0.0% | null 14 |
| `fever_true:f32f1ddb` | `fever_true` | -- | true | 0/14 | 0.0% | null 14 |
| `fever_true:97087dd7` | `fever_true` | -- | true | 0/13 | 0.0% | null 13 |
| `fever_true:c5d3e4a0` | `fever_true` | -- | true | 0/13 | 0.0% | false 13 |
| `fever_true:ef344ff7` | `fever_true` | -- | true | 0/13 | 0.0% | null 13 |
| `fever_true:74ccf7bd` | `fever_true` | -- | true | 0/12 | 0.0% | null 12 |
| `fever_true:872e3af9` | `fever_true` | -- | true | 0/12 | 0.0% | null 12 |
| `fever_true:ed36ef0f` | `fever_true` | -- | true | 0/12 | 0.0% | null 12 |
| `fever_true:f885b3cb` | `fever_true` | -- | true | 0/12 | 0.0% | null 12 |
| `fever_true:5e4f1da7` | `fever_true` | -- | true | 0/11 | 0.0% | null 11 |
| `fever_true:781b30e3` | `fever_true` | -- | true | 0/11 | 0.0% | null 11 |
| `fever_true:b950a4fc` | `fever_true` | -- | true | 0/11 | 0.0% | null 11 |
| `fever_true:dd7a11e2` | `fever_true` | -- | true | 0/10 | 0.0% | null 10 |
| `fever_true:3c3641a8` | `fever_true` | -- | true | 0/9 | 0.0% | false 1, null 8 |
| `fever_true:5ce7adbd` | `fever_true` | -- | true | 0/9 | 0.0% | null 9 |
| `fever_true:c2b356a0` | `fever_true` | -- | true | 0/9 | 0.0% | null 9 |
| `fever_false:cdf2609b` | `fever_false` | -- | false | 1/32 | 3.1% | false 1, null 31 |
| `fever_false:3de7ecac` | `fever_false` | -- | false | 1/27 | 3.7% | false 1, null 26 |

*165 further fragments with at least one error are in the JSON sidecar; every fragment is there regardless of score.*

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
| attribution | 569 | **43** | 100.0% [100.0%, 100.0%] |
| hedged | 833 | **63** | 100.0% [100.0%, 100.0%] |
| historical | 508 | **36** | 100.0% [100.0%, 100.0%] |
| metaphor | 644 | **47** | 100.0% [100.0%, 100.0%] |
| third_party | 508 | **35** | 100.0% [100.0%, 100.0%] |

### By fragment library

| library | n | eff n | accuracy [95% CI] |
|---|---|---|---|
| fever_false | 2479 | **98** | 0.0% [0.0%, 0.0%] |
| fever_null_attribution | 569 | **43** | 100.0% [100.0%, 100.0%] |
| fever_null_hedged | 833 | **63** | 100.0% [100.0%, 100.0%] |
| fever_null_historical | 508 | **36** | 100.0% [100.0%, 100.0%] |
| fever_null_metaphor | 644 | **47** | 100.0% [100.0%, 100.0%] |
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
| `fever_false:5a6a9b80` | `fever_false` | -- | false | 0/42 | 0.0% | null 42 |
| `fever_false:24e5c247` | `fever_false` | -- | false | 0/37 | 0.0% | null 37 |
| `fever_false:d0ca84a7` | `fever_false` | -- | false | 0/37 | 0.0% | null 37 |
| `fever_false:fc2ae0f2` | `fever_false` | -- | false | 0/37 | 0.0% | null 37 |
| `fever_false:17f6c637` | `fever_false` | -- | false | 0/35 | 0.0% | null 35 |
| `fever_false:9f46e710` | `fever_false` | -- | false | 0/34 | 0.0% | null 34 |
| `fever_false:55bf1913` | `fever_false` | -- | false | 0/33 | 0.0% | null 33 |
| `fever_false:5969c6c9` | `fever_false` | -- | false | 0/33 | 0.0% | null 33 |
| `fever_false:a9a0220e` | `fever_false` | -- | false | 0/33 | 0.0% | null 33 |
| `fever_false:b9076eff` | `fever_false` | -- | false | 0/33 | 0.0% | null 33 |
| `fever_false:b96ed279` | `fever_false` | -- | false | 0/33 | 0.0% | null 33 |
| `fever_false:f586e96d` | `fever_false` | -- | false | 0/33 | 0.0% | null 33 |
| `fever_false:2b944abc` | `fever_false` | -- | false | 0/32 | 0.0% | null 32 |
| `fever_false:cdf2609b` | `fever_false` | -- | false | 0/32 | 0.0% | null 32 |
| `fever_false:de0596c4` | `fever_false` | -- | false | 0/32 | 0.0% | null 32 |
| `fever_false:0429068c` | `fever_false` | -- | false | 0/31 | 0.0% | null 31 |
| `fever_false:a5b671a1` | `fever_false` | -- | false | 0/31 | 0.0% | null 31 |
| `fever_false:147d5cf0` | `fever_false` | -- | false | 0/30 | 0.0% | null 30 |
| `fever_false:56a45ff1` | `fever_false` | -- | false | 0/30 | 0.0% | null 30 |
| `fever_false:5c2a065d` | `fever_false` | -- | false | 0/30 | 0.0% | null 30 |
| `fever_false:8d02bd9e` | `fever_false` | -- | false | 0/30 | 0.0% | null 30 |
| `fever_false:d5ed3ff1` | `fever_false` | -- | false | 0/30 | 0.0% | null 30 |
| `fever_false:e2aff3b8` | `fever_false` | -- | false | 0/30 | 0.0% | null 30 |
| `fever_false:758d5434` | `fever_false` | -- | false | 0/29 | 0.0% | null 29 |
| `fever_false:cbf9d7a5` | `fever_false` | -- | false | 0/29 | 0.0% | null 29 |
| `fever_true:18173593` | `fever_true` | -- | true | 0/29 | 0.0% | null 29 |
| `fever_false:033927e6` | `fever_false` | -- | false | 0/28 | 0.0% | null 28 |
| `fever_false:3a3043ff` | `fever_false` | -- | false | 0/28 | 0.0% | null 28 |
| `fever_false:463f8189` | `fever_false` | -- | false | 0/28 | 0.0% | null 28 |
| `fever_false:7b64d17a` | `fever_false` | -- | false | 0/28 | 0.0% | null 28 |
| `fever_false:a4cda1e2` | `fever_false` | -- | false | 0/28 | 0.0% | null 28 |
| `fever_false:a6c0d44a` | `fever_false` | -- | false | 0/28 | 0.0% | null 28 |
| `fever_true:f3ee0d07` | `fever_true` | -- | true | 0/28 | 0.0% | null 28 |
| `fever_false:3de7ecac` | `fever_false` | -- | false | 0/27 | 0.0% | null 27 |
| `fever_false:43f5b35d` | `fever_false` | -- | false | 0/27 | 0.0% | null 27 |
| `fever_false:90f7b87f` | `fever_false` | -- | false | 0/27 | 0.0% | null 27 |
| `fever_false:c747066d` | `fever_false` | -- | false | 0/27 | 0.0% | null 27 |
| `fever_true:753c7815` | `fever_true` | -- | true | 0/27 | 0.0% | null 27 |
| `fever_false:4bf3caad` | `fever_false` | -- | false | 0/26 | 0.0% | null 26 |
| `fever_false:8599e318` | `fever_false` | -- | false | 0/26 | 0.0% | null 26 |

*154 further fragments with at least one error are in the JSON sidecar; every fragment is there regardless of score.*

## `tfidf_logreg__shuffled`

TF-IDF unigrams and bigrams into logistic regression. Tests whether the dataset is keyword-solvable. Its overall accuracy is close to uninformative; the `null_ambiguous` slice is the number that matters. **Negative control:** trained on permuted training labels (seed 7) and evaluated on the unpermuted test split, where it must land at chance.

Decision-rule margins selected per fold (on each fold's own validation split): 0.0.
Every fold selected margin 0, so the ruled and raw views below are the same decisions. That is a finding rather than a bug: no margin improved macro-F1 without worsening the `null -> true` rate.

*Confusion matrix, raw argmax*

|  | pred false | pred true | pred null | total |
|---|---|---|---|---|
| **truth false** | 1 | 0 | 2478 | 2479 |
| **truth true** | 0 | 0 | 1481 | 1481 |
| **truth null** | 0 | 0 | 6040 | 6040 |
| **total** | 1 | 0 | 9999 | 10000 |

`null -> true`: 0 of 6040 truly-null examples (0.00%).

*Confusion matrix, after the decision rule*

|  | pred false | pred true | pred null | total |
|---|---|---|---|---|
| **truth false** | 1 | 0 | 2478 | 2479 |
| **truth true** | 0 | 0 | 1481 | 1481 |
| **truth null** | 0 | 0 | 6040 | 6040 |
| **total** | 1 | 0 | 9999 | 10000 |

`null -> true`: 0 of 6040 truly-null examples (0.00%).

### Per class, after the decision rule

| class | support | predicted | precision | recall | F1 |
|---|---|---|---|---|---|
| `false` | 2479 | 1 | 100.0% | 0.0% | 0.1% |
| `true` | 1481 | 0 | -- | 0.0% | 0.0% |
| `null` | 6040 | 9999 | 60.4% | 100.0% | 75.3% |

### By label mode

| label mode | n | eff n | accuracy [95% CI] |
|---|---|---|---|
| false | 2479 | **98** | 0.0% [0.0%, 0.1%] |
| null_ambiguous | 3062 | **224** | 100.0% [100.0%, 100.0%] |
| null_structural | 2978 | **1** | 100.0% [100.0%, 100.0%] |
| true | 1481 | **96** | 0.0% [0.0%, 0.0%] |

### By null sub-class

| sub-class | n | eff n | null recall [95% CI] |
|---|---|---|---|
| attribution | 569 | **43** | 100.0% [100.0%, 100.0%] |
| hedged | 833 | **63** | 100.0% [100.0%, 100.0%] |
| historical | 508 | **36** | 100.0% [100.0%, 100.0%] |
| metaphor | 644 | **47** | 100.0% [100.0%, 100.0%] |
| third_party | 508 | **35** | 100.0% [100.0%, 100.0%] |

### By fragment library

| library | n | eff n | accuracy [95% CI] |
|---|---|---|---|
| fever_false | 2479 | **98** | 0.0% [0.0%, 0.1%] |
| fever_null_attribution | 569 | **43** | 100.0% [100.0%, 100.0%] |
| fever_null_hedged | 833 | **63** | 100.0% [100.0%, 100.0%] |
| fever_null_historical | 508 | **36** | 100.0% [100.0%, 100.0%] |
| fever_null_metaphor | 644 | **47** | 100.0% [100.0%, 100.0%] |
| fever_null_thirdparty | 508 | **35** | 100.0% [100.0%, 100.0%] |
| fever_true | 1481 | **96** | 0.0% [0.0%, 0.0%] |
| (none) | 2978 | **1** | 100.0% [100.0%, 100.0%] |

### Per-fragment errors (worst first)

Whether errors are spread thinly across many fragments or piled onto a few is the difference
between "the method is too weak" (model work) and "these specific ideas are not learnable from
the data we have" (library work, and these are the fragments to write more of). No intervals:
a fragment is one cluster, so an interval over its own examples measures nothing.

194 of 463 decisive fragments were got wrong at least once.

`tfidf_logreg__shuffled`: 3959 errors across 194 of 463 decisive fragments. Half of them fall on **71** fragments (an even spread would be 97.0); the worst ten carry 8.9% of all errors.

| fragment | library | sub-class | truth | correct | accuracy | predicted as |
|---|---|---|---|---|---|---|
| `fever_false:5a6a9b80` | `fever_false` | -- | false | 0/42 | 0.0% | null 42 |
| `fever_false:24e5c247` | `fever_false` | -- | false | 0/37 | 0.0% | null 37 |
| `fever_false:d0ca84a7` | `fever_false` | -- | false | 0/37 | 0.0% | null 37 |
| `fever_false:fc2ae0f2` | `fever_false` | -- | false | 0/37 | 0.0% | null 37 |
| `fever_false:17f6c637` | `fever_false` | -- | false | 0/35 | 0.0% | null 35 |
| `fever_false:9f46e710` | `fever_false` | -- | false | 0/34 | 0.0% | null 34 |
| `fever_false:55bf1913` | `fever_false` | -- | false | 0/33 | 0.0% | null 33 |
| `fever_false:5969c6c9` | `fever_false` | -- | false | 0/33 | 0.0% | null 33 |
| `fever_false:a9a0220e` | `fever_false` | -- | false | 0/33 | 0.0% | null 33 |
| `fever_false:b9076eff` | `fever_false` | -- | false | 0/33 | 0.0% | null 33 |
| `fever_false:b96ed279` | `fever_false` | -- | false | 0/33 | 0.0% | null 33 |
| `fever_false:f586e96d` | `fever_false` | -- | false | 0/33 | 0.0% | null 33 |
| `fever_false:2b944abc` | `fever_false` | -- | false | 0/32 | 0.0% | null 32 |
| `fever_false:cdf2609b` | `fever_false` | -- | false | 0/32 | 0.0% | null 32 |
| `fever_false:de0596c4` | `fever_false` | -- | false | 0/32 | 0.0% | null 32 |
| `fever_false:0429068c` | `fever_false` | -- | false | 0/31 | 0.0% | null 31 |
| `fever_false:a5b671a1` | `fever_false` | -- | false | 0/31 | 0.0% | null 31 |
| `fever_false:147d5cf0` | `fever_false` | -- | false | 0/30 | 0.0% | null 30 |
| `fever_false:56a45ff1` | `fever_false` | -- | false | 0/30 | 0.0% | null 30 |
| `fever_false:5c2a065d` | `fever_false` | -- | false | 0/30 | 0.0% | null 30 |
| `fever_false:8d02bd9e` | `fever_false` | -- | false | 0/30 | 0.0% | null 30 |
| `fever_false:d5ed3ff1` | `fever_false` | -- | false | 0/30 | 0.0% | null 30 |
| `fever_false:e2aff3b8` | `fever_false` | -- | false | 0/30 | 0.0% | null 30 |
| `fever_false:758d5434` | `fever_false` | -- | false | 0/29 | 0.0% | null 29 |
| `fever_false:cbf9d7a5` | `fever_false` | -- | false | 0/29 | 0.0% | null 29 |
| `fever_true:18173593` | `fever_true` | -- | true | 0/29 | 0.0% | null 29 |
| `fever_false:033927e6` | `fever_false` | -- | false | 0/28 | 0.0% | null 28 |
| `fever_false:3a3043ff` | `fever_false` | -- | false | 0/28 | 0.0% | null 28 |
| `fever_false:463f8189` | `fever_false` | -- | false | 0/28 | 0.0% | null 28 |
| `fever_false:7b64d17a` | `fever_false` | -- | false | 0/28 | 0.0% | null 28 |
| `fever_false:a4cda1e2` | `fever_false` | -- | false | 0/28 | 0.0% | null 28 |
| `fever_false:a6c0d44a` | `fever_false` | -- | false | 0/28 | 0.0% | null 28 |
| `fever_true:f3ee0d07` | `fever_true` | -- | true | 0/28 | 0.0% | null 28 |
| `fever_false:3de7ecac` | `fever_false` | -- | false | 0/27 | 0.0% | null 27 |
| `fever_false:43f5b35d` | `fever_false` | -- | false | 0/27 | 0.0% | null 27 |
| `fever_false:c747066d` | `fever_false` | -- | false | 0/27 | 0.0% | null 27 |
| `fever_true:753c7815` | `fever_true` | -- | true | 0/27 | 0.0% | null 27 |
| `fever_false:4bf3caad` | `fever_false` | -- | false | 0/26 | 0.0% | null 26 |
| `fever_false:8599e318` | `fever_false` | -- | false | 0/26 | 0.0% | null 26 |
| `fever_false:8bcd3ef4` | `fever_false` | -- | false | 0/26 | 0.0% | null 26 |

*154 further fragments with at least one error are in the JSON sidecar; every fragment is there regardless of score.*

## `arm_a_probe`

Frozen `roberta-base`, mean-pooled, with a `Linear(768, 3)` probe over the cached embeddings (2,307 parameters). The encoder learns nothing; only the probe is fitted. Expected to handle clear positives, clear negatives and `null_structural`, and to do badly on the four hard `null` sub-classes, which turn on compositional scope that a single pooled vector blurs. That is the predicted result rather than a fault, and it is what makes Arm B necessary: a weak probe cannot distinguish "the libraries are the bottleneck" from "the method is too weak".

Decision-rule margins selected per fold (on each fold's own validation split): 0.0.
Every fold selected margin 0, so the ruled and raw views below are the same decisions. That is a finding rather than a bug: no margin improved macro-F1 without worsening the `null -> true` rate.

*Confusion matrix, raw argmax*

|  | pred false | pred true | pred null | total |
|---|---|---|---|---|
| **truth false** | 1930 | 141 | 408 | 2479 |
| **truth true** | 126 | 889 | 466 | 1481 |
| **truth null** | 231 | 130 | 5679 | 6040 |
| **total** | 2287 | 1160 | 6553 | 10000 |

`null -> true`: 130 of 6040 truly-null examples (2.15%).

*Confusion matrix, after the decision rule*

|  | pred false | pred true | pred null | total |
|---|---|---|---|---|
| **truth false** | 1930 | 141 | 408 | 2479 |
| **truth true** | 126 | 889 | 466 | 1481 |
| **truth null** | 231 | 130 | 5679 | 6040 |
| **total** | 2287 | 1160 | 6553 | 10000 |

`null -> true`: 130 of 6040 truly-null examples (2.15%).

### Per class, after the decision rule

| class | support | predicted | precision | recall | F1 |
|---|---|---|---|---|---|
| `false` | 2479 | 2287 | 84.4% | 77.9% | 81.0% |
| `true` | 1481 | 1160 | 76.6% | 60.0% | 67.3% |
| `null` | 6040 | 6553 | 86.7% | 94.0% | 90.2% |

### By label mode

| label mode | n | eff n | accuracy [95% CI] |
|---|---|---|---|
| false | 2479 | **98** | 77.9% [73.0%, 82.7%] |
| null_ambiguous | 3062 | **224** | 89.0% [86.5%, 91.4%] |
| null_structural | 2978 | **1** | 99.2% [99.2%, 99.2%] |
| true | 1481 | **96** | 60.0% [52.9%, 67.1%] |

### By null sub-class

| sub-class | n | eff n | null recall [95% CI] |
|---|---|---|---|
| attribution | 569 | **43** | 88.9% [82.7%, 94.0%] |
| hedged | 833 | **63** | 81.9% [75.4%, 87.6%] |
| historical | 508 | **36** | 90.2% [84.4%, 94.7%] |
| metaphor | 644 | **47** | 94.9% [91.3%, 97.6%] |
| third_party | 508 | **35** | 92.3% [88.1%, 96.4%] |

### By fragment library

| library | n | eff n | accuracy [95% CI] |
|---|---|---|---|
| fever_false | 2479 | **98** | 77.9% [73.0%, 82.7%] |
| fever_null_attribution | 569 | **43** | 88.9% [82.7%, 94.0%] |
| fever_null_hedged | 833 | **63** | 81.9% [75.4%, 87.6%] |
| fever_null_historical | 508 | **36** | 90.2% [84.4%, 94.7%] |
| fever_null_metaphor | 644 | **47** | 94.9% [91.3%, 97.6%] |
| fever_null_thirdparty | 508 | **35** | 92.3% [88.1%, 96.4%] |
| fever_true | 1481 | **96** | 60.0% [52.9%, 67.1%] |
| (none) | 2978 | **1** | 99.2% [99.2%, 99.2%] |

### Per-fragment errors (worst first)

Whether errors are spread thinly across many fragments or piled onto a few is the difference
between "the method is too weak" (model work) and "these specific ideas are not learnable from
the data we have" (library work, and these are the fragments to write more of). No intervals:
a fragment is one cluster, so an interval over its own examples measures nothing.

263 of 463 decisive fragments were got wrong at least once.

`arm_a_probe`: 1477 errors across 263 of 463 decisive fragments. Half of them fall on **52** fragments (an even spread would be 131.5); the worst ten carry 15.0% of all errors.

| fragment | library | sub-class | truth | correct | accuracy | predicted as |
|---|---|---|---|---|---|---|
| `fever_true:7ef2ecf5` | `fever_true` | -- | true | 0/23 | 0.0% | null 23 |
| `fever_true:7844c66b` | `fever_true` | -- | true | 0/18 | 0.0% | false 4, null 14 |
| `fever_true:a92fcdc7` | `fever_true` | -- | true | 0/17 | 0.0% | false 2, null 15 |
| `fever_true:0ddb8a11` | `fever_true` | -- | true | 0/14 | 0.0% | false 1, null 13 |
| `fever_true:d00c307b` | `fever_true` | -- | true | 0/14 | 0.0% | null 14 |
| `fever_true:80f7ba2e` | `fever_true` | -- | true | 0/13 | 0.0% | null 13 |
| `fever_true:ef344ff7` | `fever_true` | -- | true | 0/13 | 0.0% | null 13 |
| `fever_null_hedged:17a3f60a` | `fever_null_hedged` | hedged | null | 0/9 | 0.0% | true 9 |
| `fever_null_historical:2c3501f1` | `fever_null_historical` | historical | null | 0/1 | 0.0% | false 1 |
| `fever_false:cbf9d7a5` | `fever_false` | -- | false | 2/29 | 6.9% | false 2, true 19, null 8 |
| `fever_true:872e3af9` | `fever_true` | -- | true | 1/12 | 8.3% | false 2, true 1, null 9 |
| `fever_null_hedged:42486de4` | `fever_null_hedged` | hedged | null | 1/11 | 9.1% | false 2, true 8, null 1 |
| `fever_true:391fb2ce` | `fever_true` | -- | true | 2/18 | 11.1% | false 7, true 2, null 9 |
| `fever_null_hedged:965c4a64` | `fever_null_hedged` | hedged | null | 1/9 | 11.1% | false 4, true 4, null 1 |
| `fever_true:01833454` | `fever_true` | -- | true | 2/16 | 12.5% | false 11, true 2, null 3 |
| `fever_true:f0038e34` | `fever_true` | -- | true | 3/21 | 14.3% | true 3, null 18 |
| `fever_true:c5d3e4a0` | `fever_true` | -- | true | 2/13 | 15.4% | false 11, true 2 |
| `fever_false:a5b671a1` | `fever_false` | -- | false | 5/31 | 16.1% | false 5, true 26 |
| `fever_true:c7489e90` | `fever_true` | -- | true | 3/18 | 16.7% | false 3, true 3, null 12 |
| `fever_true:74ccf7bd` | `fever_true` | -- | true | 2/12 | 16.7% | true 2, null 10 |
| `fever_true:ed36ef0f` | `fever_true` | -- | true | 2/12 | 16.7% | true 2, null 10 |
| `fever_true:b950a4fc` | `fever_true` | -- | true | 2/11 | 18.2% | true 2, null 9 |
| `fever_true:15a05d92` | `fever_true` | -- | true | 5/25 | 20.0% | false 3, true 5, null 17 |
| `fever_null_hedged:8d1c41e3` | `fever_null_hedged` | hedged | null | 2/10 | 20.0% | false 7, true 1, null 2 |
| `fever_false:0cc191ec` | `fever_false` | -- | false | 5/24 | 20.8% | false 5, true 3, null 16 |
| `fever_false:033927e6` | `fever_false` | -- | false | 6/28 | 21.4% | false 6, null 22 |
| `fever_null_attribution:17b7ab2a` | `fever_null_attribution` | attribution | null | 3/14 | 21.4% | true 11, null 3 |
| `fever_true:199d4eb4` | `fever_true` | -- | true | 3/14 | 21.4% | false 1, true 3, null 10 |
| `fever_true:7cad3f0f` | `fever_true` | -- | true | 5/21 | 23.8% | false 16, true 5 |
| `fever_true:dd6bbec4` | `fever_true` | -- | true | 6/25 | 24.0% | false 12, true 6, null 7 |
| `fever_false:f586e96d` | `fever_false` | -- | false | 8/33 | 24.2% | false 8, true 21, null 4 |
| `fever_true:ed3c8c83` | `fever_true` | -- | true | 5/19 | 26.3% | true 5, null 14 |
| `fever_true:dd079c14` | `fever_true` | -- | true | 4/15 | 26.7% | true 4, null 11 |
| `fever_false:3a3043ff` | `fever_false` | -- | false | 8/28 | 28.6% | false 8, true 12, null 8 |
| `fever_null_historical:8f95e12e` | `fever_null_historical` | historical | null | 4/14 | 28.6% | false 10, null 4 |
| `fever_true:65e4286c` | `fever_true` | -- | true | 5/17 | 29.4% | true 5, null 12 |
| `fever_false:a0bfd501` | `fever_false` | -- | false | 6/20 | 30.0% | false 6, true 3, null 11 |
| `fever_null_hedged:2c30e4fe` | `fever_null_hedged` | hedged | null | 3/10 | 30.0% | false 1, true 6, null 3 |
| `fever_null_hedged:bcb7caae` | `fever_null_hedged` | hedged | null | 4/13 | 30.8% | false 3, true 6, null 4 |
| `fever_false:e8c514ff` | `fever_false` | -- | false | 5/16 | 31.2% | false 5, true 2, null 9 |

*223 further fragments with at least one error are in the JSON sidecar; every fragment is there regardless of score.*

## `arm_b_finetune`

`roberta-base` with **every layer unfrozen**, mean-pooled, with the same `Linear(768, 3)` head -- 110M trainable parameters against Arm A's 2,307. Three epochs at batch 32, learning rate 2e-5, 10% linear warmup, AdamW, fp32. No gradient checkpointing, no 8-bit optimiser, no LoRA, no gradient accumulation: the full model fits in 12GB with room to spare, so anything that reads like a compute compromise would be a mistake rather than a saving. This is the arm that separates "the fragment libraries are the bottleneck" from "the method is too weak": if a fully fine-tuned encoder still cannot read third-party attribution, tense or metaphor, the limit is in the ideas the libraries contain and the fix is library work, not model work.

Decision-rule margins selected per fold (on each fold's own validation split): 0.0, 0.1, 0.75, 0.9.

*Confusion matrix, raw argmax*

|  | pred false | pred true | pred null | total |
|---|---|---|---|---|
| **truth false** | 2298 | 88 | 93 | 2479 |
| **truth true** | 5 | 1308 | 168 | 1481 |
| **truth null** | 55 | 93 | 5892 | 6040 |
| **total** | 2358 | 1489 | 6153 | 10000 |

`null -> true`: 93 of 6040 truly-null examples (1.54%).

*Confusion matrix, after the decision rule*

|  | pred false | pred true | pred null | total |
|---|---|---|---|---|
| **truth false** | 2303 | 83 | 93 | 2479 |
| **truth true** | 6 | 1297 | 178 | 1481 |
| **truth null** | 55 | 81 | 5904 | 6040 |
| **total** | 2364 | 1461 | 6175 | 10000 |

`null -> true`: 81 of 6040 truly-null examples (1.34%).

### Per class, after the decision rule

| class | support | predicted | precision | recall | F1 |
|---|---|---|---|---|---|
| `false` | 2479 | 2364 | 97.4% | 92.9% | 95.1% |
| `true` | 1481 | 1461 | 88.8% | 87.6% | 88.2% |
| `null` | 6040 | 6175 | 95.6% | 97.7% | 96.7% |

### By label mode

| label mode | n | eff n | accuracy [95% CI] |
|---|---|---|---|
| false | 2479 | **98** | 92.9% [87.8%, 97.1%] |
| null_ambiguous | 3062 | **224** | 95.6% [93.0%, 97.8%] |
| null_structural | 2978 | **1** | 100.0% [100.0%, 100.0%] |
| true | 1481 | **96** | 87.6% [81.4%, 93.1%] |

### By null sub-class

| sub-class | n | eff n | null recall [95% CI] |
|---|---|---|---|
| attribution | 569 | **43** | 96.3% [91.5%, 99.7%] |
| hedged | 833 | **63** | 88.8% [80.1%, 95.7%] |
| historical | 508 | **36** | 96.3% [91.5%, 99.8%] |
| metaphor | 644 | **47** | 99.5% [98.5%, 100.0%] |
| third_party | 508 | **35** | 100.0% [100.0%, 100.0%] |

### By fragment library

| library | n | eff n | accuracy [95% CI] |
|---|---|---|---|
| fever_false | 2479 | **98** | 92.9% [87.8%, 97.1%] |
| fever_null_attribution | 569 | **43** | 96.3% [91.5%, 99.7%] |
| fever_null_hedged | 833 | **63** | 88.8% [80.1%, 95.7%] |
| fever_null_historical | 508 | **36** | 96.3% [91.5%, 99.8%] |
| fever_null_metaphor | 644 | **47** | 99.5% [98.5%, 100.0%] |
| fever_null_thirdparty | 508 | **35** | 100.0% [100.0%, 100.0%] |
| fever_true | 1481 | **96** | 87.6% [81.4%, 93.1%] |
| (none) | 2978 | **1** | 100.0% [100.0%, 100.0%] |

### Per-fragment errors (worst first)

Whether errors are spread thinly across many fragments or piled onto a few is the difference
between "the method is too weak" (model work) and "these specific ideas are not learnable from
the data we have" (library work, and these are the fragments to write more of). No intervals:
a fragment is one cluster, so an interval over its own examples measures nothing.

60 of 463 decisive fragments were got wrong at least once.

`arm_b_finetune`: 496 errors across 60 of 463 decisive fragments. Half of them fall on **14** fragments (an even spread would be 30.0); the worst ten carry 41.3% of all errors.

| fragment | library | sub-class | truth | correct | accuracy | predicted as |
|---|---|---|---|---|---|---|
| `fever_false:5c2a065d` | `fever_false` | -- | false | 0/30 | 0.0% | null 30 |
| `fever_false:3a3043ff` | `fever_false` | -- | false | 0/28 | 0.0% | true 28 |
| `fever_false:e70e24b6` | `fever_false` | -- | false | 0/26 | 0.0% | true 26 |
| `fever_false:f7d03fcb` | `fever_false` | -- | false | 0/22 | 0.0% | null 22 |
| `fever_true:391fb2ce` | `fever_true` | -- | true | 0/18 | 0.0% | null 18 |
| `fever_true:7844c66b` | `fever_true` | -- | true | 0/18 | 0.0% | null 18 |
| `fever_null_hedged:081a5883` | `fever_null_hedged` | hedged | null | 0/16 | 0.0% | false 16 |
| `fever_null_hedged:5bf1b63f` | `fever_null_hedged` | hedged | null | 0/14 | 0.0% | true 14 |
| `fever_true:0ddb8a11` | `fever_true` | -- | true | 0/14 | 0.0% | null 14 |
| `fever_true:d00c307b` | `fever_true` | -- | true | 0/14 | 0.0% | null 14 |
| `fever_true:ed36ef0f` | `fever_true` | -- | true | 0/12 | 0.0% | null 12 |
| `fever_null_hedged:42486de4` | `fever_null_hedged` | hedged | null | 0/11 | 0.0% | false 11 |
| `fever_true:5e4f1da7` | `fever_true` | -- | true | 0/11 | 0.0% | null 11 |
| `fever_null_hedged:8d1c41e3` | `fever_null_hedged` | hedged | null | 0/10 | 0.0% | true 10 |
| `fever_true:2ee57e4c` | `fever_true` | -- | true | 0/10 | 0.0% | null 10 |
| `fever_null_hedged:965c4a64` | `fever_null_hedged` | hedged | null | 0/9 | 0.0% | false 9 |
| `fever_true:5ce7adbd` | `fever_true` | -- | true | 0/9 | 0.0% | null 9 |
| `fever_null_historical:1b314733` | `fever_null_historical` | historical | null | 0/8 | 0.0% | true 8 |
| `fever_null_historical:feadcb2c` | `fever_null_historical` | historical | null | 0/8 | 0.0% | true 8 |
| `fever_null_historical:2c3501f1` | `fever_null_historical` | historical | null | 0/1 | 0.0% | false 1 |
| `fever_true:97087dd7` | `fever_true` | -- | true | 1/13 | 7.7% | true 1, null 12 |
| `fever_true:ef344ff7` | `fever_true` | -- | true | 1/13 | 7.7% | true 1, null 12 |
| `fever_true:74ccf7bd` | `fever_true` | -- | true | 1/12 | 8.3% | true 1, null 11 |
| `fever_true:b950a4fc` | `fever_true` | -- | true | 1/11 | 9.1% | true 1, null 10 |
| `fever_null_hedged:cf95d564` | `fever_null_hedged` | hedged | null | 2/13 | 15.4% | true 11, null 2 |
| `fever_false:e8c514ff` | `fever_false` | -- | false | 3/16 | 18.8% | false 3, true 13 |
| `fever_true:781b30e3` | `fever_true` | -- | true | 3/11 | 27.3% | true 3, null 8 |
| `fever_null_attribution:17b7ab2a` | `fever_null_attribution` | attribution | null | 4/14 | 28.6% | true 10, null 4 |
| `fever_false:3de7ecac` | `fever_false` | -- | false | 9/27 | 33.3% | false 9, null 18 |
| `fever_null_hedged:fafa0b56` | `fever_null_hedged` | hedged | null | 5/13 | 38.5% | true 8, null 5 |
| `fever_null_hedged:9e333f46` | `fever_null_hedged` | hedged | null | 4/10 | 40.0% | false 6, null 4 |
| `fever_false:93390aea` | `fever_false` | -- | false | 11/26 | 42.3% | false 11, null 15 |
| `fever_true:872e3af9` | `fever_true` | -- | true | 6/12 | 50.0% | true 6, null 6 |
| `fever_null_metaphor:4076133d` | `fever_null_metaphor` | metaphor | null | 3/6 | 50.0% | true 3, null 3 |
| `fever_null_attribution:dba8c443` | `fever_null_attribution` | attribution | null | 6/11 | 54.5% | false 5, null 6 |
| `fever_null_hedged:bba323b8` | `fever_null_hedged` | hedged | null | 9/14 | 64.3% | true 5, null 9 |
| `fever_false:5935e477` | `fever_false` | -- | false | 12/18 | 66.7% | false 12, true 6 |
| `fever_null_attribution:1eb2016b` | `fever_null_attribution` | attribution | null | 8/12 | 66.7% | false 4, null 8 |
| `fever_false:cbf9d7a5` | `fever_false` | -- | false | 20/29 | 69.0% | false 20, true 9 |
| `fever_true:199d4eb4` | `fever_true` | -- | true | 11/14 | 78.6% | true 11, null 3 |

*20 further fragments with at least one error are in the JSON sidecar; every fragment is there regardless of score.*

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
| attribution | 569 | **43** | 100.0% [100.0%, 100.0%] |
| hedged | 833 | **63** | 100.0% [100.0%, 100.0%] |
| historical | 508 | **36** | 100.0% [100.0%, 100.0%] |
| metaphor | 644 | **47** | 100.0% [100.0%, 100.0%] |
| third_party | 508 | **35** | 100.0% [100.0%, 100.0%] |

### By fragment library

| library | n | eff n | accuracy [95% CI] |
|---|---|---|---|
| fever_false | 2479 | **98** | 0.0% [0.0%, 0.0%] |
| fever_null_attribution | 569 | **43** | 100.0% [100.0%, 100.0%] |
| fever_null_hedged | 833 | **63** | 100.0% [100.0%, 100.0%] |
| fever_null_historical | 508 | **36** | 100.0% [100.0%, 100.0%] |
| fever_null_metaphor | 644 | **47** | 100.0% [100.0%, 100.0%] |
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
| `fever_false:5a6a9b80` | `fever_false` | -- | false | 0/42 | 0.0% | null 42 |
| `fever_false:24e5c247` | `fever_false` | -- | false | 0/37 | 0.0% | null 37 |
| `fever_false:d0ca84a7` | `fever_false` | -- | false | 0/37 | 0.0% | null 37 |
| `fever_false:fc2ae0f2` | `fever_false` | -- | false | 0/37 | 0.0% | null 37 |
| `fever_false:17f6c637` | `fever_false` | -- | false | 0/35 | 0.0% | null 35 |
| `fever_false:9f46e710` | `fever_false` | -- | false | 0/34 | 0.0% | null 34 |
| `fever_false:55bf1913` | `fever_false` | -- | false | 0/33 | 0.0% | null 33 |
| `fever_false:5969c6c9` | `fever_false` | -- | false | 0/33 | 0.0% | null 33 |
| `fever_false:a9a0220e` | `fever_false` | -- | false | 0/33 | 0.0% | null 33 |
| `fever_false:b9076eff` | `fever_false` | -- | false | 0/33 | 0.0% | null 33 |
| `fever_false:b96ed279` | `fever_false` | -- | false | 0/33 | 0.0% | null 33 |
| `fever_false:f586e96d` | `fever_false` | -- | false | 0/33 | 0.0% | null 33 |
| `fever_false:2b944abc` | `fever_false` | -- | false | 0/32 | 0.0% | null 32 |
| `fever_false:cdf2609b` | `fever_false` | -- | false | 0/32 | 0.0% | null 32 |
| `fever_false:de0596c4` | `fever_false` | -- | false | 0/32 | 0.0% | null 32 |
| `fever_false:0429068c` | `fever_false` | -- | false | 0/31 | 0.0% | null 31 |
| `fever_false:a5b671a1` | `fever_false` | -- | false | 0/31 | 0.0% | null 31 |
| `fever_false:147d5cf0` | `fever_false` | -- | false | 0/30 | 0.0% | null 30 |
| `fever_false:56a45ff1` | `fever_false` | -- | false | 0/30 | 0.0% | null 30 |
| `fever_false:5c2a065d` | `fever_false` | -- | false | 0/30 | 0.0% | null 30 |
| `fever_false:8d02bd9e` | `fever_false` | -- | false | 0/30 | 0.0% | null 30 |
| `fever_false:d5ed3ff1` | `fever_false` | -- | false | 0/30 | 0.0% | null 30 |
| `fever_false:e2aff3b8` | `fever_false` | -- | false | 0/30 | 0.0% | null 30 |
| `fever_false:758d5434` | `fever_false` | -- | false | 0/29 | 0.0% | null 29 |
| `fever_false:cbf9d7a5` | `fever_false` | -- | false | 0/29 | 0.0% | null 29 |
| `fever_true:18173593` | `fever_true` | -- | true | 0/29 | 0.0% | null 29 |
| `fever_false:033927e6` | `fever_false` | -- | false | 0/28 | 0.0% | null 28 |
| `fever_false:3a3043ff` | `fever_false` | -- | false | 0/28 | 0.0% | null 28 |
| `fever_false:463f8189` | `fever_false` | -- | false | 0/28 | 0.0% | null 28 |
| `fever_false:7b64d17a` | `fever_false` | -- | false | 0/28 | 0.0% | null 28 |
| `fever_false:a4cda1e2` | `fever_false` | -- | false | 0/28 | 0.0% | null 28 |
| `fever_false:a6c0d44a` | `fever_false` | -- | false | 0/28 | 0.0% | null 28 |
| `fever_true:f3ee0d07` | `fever_true` | -- | true | 0/28 | 0.0% | null 28 |
| `fever_false:3de7ecac` | `fever_false` | -- | false | 0/27 | 0.0% | null 27 |
| `fever_false:43f5b35d` | `fever_false` | -- | false | 0/27 | 0.0% | null 27 |
| `fever_false:90f7b87f` | `fever_false` | -- | false | 0/27 | 0.0% | null 27 |
| `fever_false:c747066d` | `fever_false` | -- | false | 0/27 | 0.0% | null 27 |
| `fever_true:753c7815` | `fever_true` | -- | true | 0/27 | 0.0% | null 27 |
| `fever_false:4bf3caad` | `fever_false` | -- | false | 0/26 | 0.0% | null 26 |
| `fever_false:8599e318` | `fever_false` | -- | false | 0/26 | 0.0% | null 26 |

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
| 1 | 10000 | 2000 | 2000 | 0.0 | 61.2% | 61.2% | 29.6% | 0.00% |
| 2 | 10000 | 2000 | 2000 | 0.0 | 60.4% | 60.4% | 25.4% | 0.00% |
| 3 | 10000 | 2000 | 2000 | 0.0 | 60.7% | 60.7% | 25.3% | 0.00% |
| 4 | 10000 | 2000 | 2000 | 0.0 | 60.3% | 60.3% | 25.3% | 0.00% |

### `tfidf_logreg`

| fold | train n | val n | test n | margin | acc (raw) | acc (ruled) | macro-F1 | null->true |
|---|---|---|---|---|---|---|---|---|
| 0 | 10000 | 2000 | 2000 | 0.0 | 82.0% | 82.0% | 76.3% | 0.99% |
| 1 | 10000 | 2000 | 2000 | 0.0 | 77.8% | 77.8% | 68.8% | 0.33% |
| 2 | 10000 | 2000 | 2000 | 0.0 | 80.2% | 80.2% | 70.3% | 1.49% |
| 3 | 10000 | 2000 | 2000 | 0.0 | 80.8% | 80.8% | 74.0% | 1.65% |
| 4 | 10000 | 2000 | 2000 | 0.0 | 86.2% | 86.2% | 79.9% | 0.75% |

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
| 0 | 10000 | 2000 | 2000 | 0.0 | 60.5% | 60.5% | 25.3% | 0.00% |
| 1 | 10000 | 2000 | 2000 | 0.0 | 60.1% | 60.1% | 25.0% | 0.00% |
| 2 | 10000 | 2000 | 2000 | 0.0 | 60.4% | 60.4% | 25.1% | 0.00% |
| 3 | 10000 | 2000 | 2000 | 0.0 | 60.8% | 60.8% | 25.2% | 0.00% |
| 4 | 10000 | 2000 | 2000 | 0.0 | 60.3% | 60.3% | 25.1% | 0.00% |

### `arm_a_probe`

| fold | train n | val n | test n | margin | acc (raw) | acc (ruled) | macro-F1 | null->true |
|---|---|---|---|---|---|---|---|---|
| 0 | 10000 | 2000 | 2000 | 0.0 | 88.2% | 88.2% | 84.4% | 1.49% |
| 1 | 10000 | 2000 | 2000 | 0.0 | 81.4% | 81.4% | 74.0% | 1.50% |
| 2 | 10000 | 2000 | 2000 | 0.0 | 83.0% | 83.0% | 76.5% | 3.39% |
| 3 | 10000 | 2000 | 2000 | 0.0 | 85.5% | 85.5% | 81.2% | 2.80% |
| 4 | 10000 | 2000 | 2000 | 0.0 | 86.8% | 86.8% | 81.4% | 1.58% |

### `arm_b_finetune`

| fold | train n | val n | test n | margin | acc (raw) | acc (ruled) | macro-F1 | null->true |
|---|---|---|---|---|---|---|---|---|
| 0 | 10000 | 2000 | 2000 | 0.0 | 95.2% | 95.2% | 94.0% | 0.83% |
| 1 | 10000 | 2000 | 2000 | 0.1 | 94.4% | 94.3% | 92.5% | 1.16% |
| 2 | 10000 | 2000 | 2000 | 0.75 | 91.2% | 91.3% | 88.1% | 3.48% |
| 3 | 10000 | 2000 | 2000 | 0.9 | 94.5% | 94.8% | 93.2% | 1.15% |
| 4 | 10000 | 2000 | 2000 | 0.0 | 99.5% | 99.5% | 99.1% | 0.08% |

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

* **Write 60-100 realistic full submissions by hand, deliberately unlike the recombinations, label them by hand, and hold them out permanently.** Never touched by a training decision, never used to select a margin, never used to choose a pooling mode.
* Everything scored in this report is a recombination of the same few hundred fragments the models were trained on. Held-out *clusters* remove memorisation, and that is all they remove: the test examples are still short, still one supervised claim plus filler, still assembled by the same generator from the same libraries in the same register. No number here measures what happens when a real patient writes three paragraphs in their own voice.
* This is cheap in code -- it is a JSONL file and a scoring run against the existing report writer -- and expensive in careful thought, which is why it is its own ticket rather than a task at the end of this one. Until it exists, nothing here resembles evidence about real patient text, however wide or narrow the intervals above are.

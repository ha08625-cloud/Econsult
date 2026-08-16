# Encoder training: evaluation report

*Generated 2026-08-16T09:49:49+00:00.*

|  |  |
|---|---|
| signal | `nocturia_present` |
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
| artefacts | `models/encoder/nocturia_present/arm_b_finetune` |
| weights | `models/encoder/nocturia_present/arm_b_finetune/weights -- ~440MB per fold, not committed` |
| model revision | `e2da8e2f811d1448a5b465c236feacd80ffbac7b` |
| revision pinned | `False` |
| tokeniser lowercases | `False` |
| tokeniser vocab size | `50265` |
| tokeniser discards casing | `False` |
| cluster tag coverage | `0 of 7 libraries carry cluster markers; 351 of 351 fragments are in libraries with none` |
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

> **Warning: all 7 libraries behind this run carry no cluster markers at all, so every line in them counts as an independent idea.** Where that is not true -- where several lines are one idea written several ways -- the `eff n` of every slice drawn from those libraries is an **upper bound**, and the confidence intervals below are correspondingly **narrower than the truth**.
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
| `majority_class` | baseline | 7022 | **351** | 43.6% [38.0%, 49.9%] | 20.2% [18.4%, 22.2%] | 60.4% | 60.4% +/- 0.2% |
| `length_only` | baseline | 7022 | **351** | 43.6% [38.0%, 49.9%] | 20.2% [18.4%, 22.2%] | 60.4% | 60.4% +/- 0.2% |
| `tfidf_logreg` | baseline | 7022 | **351** | 64.9% [59.5%, 70.4%] | 60.2% [54.3%, 66.2%] | 75.3% | 75.3% +/- 3.4% |
| `length_only__shuffled` | negative control | 7022 | **351** | 43.6% [38.0%, 49.9%] | 20.2% [18.4%, 22.2%] | 60.4% | 60.4% +/- 0.2% |
| `tfidf_logreg__shuffled` | negative control | 7022 | **351** | 43.6% [38.0%, 49.8%] | 20.2% [18.4%, 22.2%] | 60.4% | 60.4% +/- 0.2% |
| `arm_a_probe` | probe | 7022 | **351** | 70.4% [66.5%, 74.5%] | 68.4% [64.0%, 72.8%] | 79.1% | 79.1% +/- 1.4% |
| `arm_b_finetune` | finetune | 7022 | **351** | 83.0% [78.5%, 87.1%] | 81.7% [76.9%, 86.2%] | 87.9% | 87.9% +/- 3.3% |
| `arm_b_finetune__shuffled` | negative control | 7022 | **351** | 43.6% [38.0%, 49.9%] | 20.2% [18.4%, 22.2%] | 60.4% | 60.4% +/- 0.2% |

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
| `tfidf_logreg` | -- | 86.0% [77.0%, 93.3%] (eff n 51) | 97.3% [95.3%, 98.8%] (eff n 47) | 91.5% [85.1%, 96.6%] (eff n 46) | 93.1% [86.8%, 97.7%] (eff n 52) | 87.7% [78.8%, 94.8%] (eff n 47) |
| `length_only__shuffled` | -- | 100.0% [100.0%, 100.0%] (eff n 51) | 100.0% [100.0%, 100.0%] (eff n 47) | 100.0% [100.0%, 100.0%] (eff n 46) | 100.0% [100.0%, 100.0%] (eff n 52) | 100.0% [100.0%, 100.0%] (eff n 47) |
| `tfidf_logreg__shuffled` | -- | 99.8% [99.5%, 100.0%] (eff n 51) | 100.0% [100.0%, 100.0%] (eff n 47) | 100.0% [100.0%, 100.0%] (eff n 46) | 100.0% [100.0%, 100.0%] (eff n 52) | 100.0% [100.0%, 100.0%] (eff n 47) |
| `arm_a_probe` | -- | 73.3% [65.1%, 80.7%] (eff n 51) | 88.7% [83.5%, 92.9%] (eff n 47) | 89.2% [83.0%, 94.2%] (eff n 46) | 80.2% [71.9%, 88.1%] (eff n 52) | 83.4% [75.6%, 90.8%] (eff n 47) |
| `arm_b_finetune` | -- | 88.2% [79.1%, 95.7%] (eff n 51) | 80.9% [70.1%, 90.6%] (eff n 47) | 92.1% [84.2%, 98.1%] (eff n 46) | 91.6% [84.4%, 97.8%] (eff n 52) | 93.3% [85.2%, 99.4%] (eff n 47) |
| `arm_b_finetune__shuffled` | -- | 100.0% [100.0%, 100.0%] (eff n 51) | 100.0% [100.0%, 100.0%] (eff n 47) | 100.0% [100.0%, 100.0%] (eff n 46) | 100.0% [100.0%, 100.0%] (eff n 52) | 100.0% [100.0%, 100.0%] (eff n 47) |

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
| `tfidf_logreg` | baseline | 3062 | **243** | 91.1% [88.1%, 93.7%] |
| `arm_a_probe` | probe | 3062 | **243** | 82.6% [79.2%, 85.7%] |
| `arm_b_finetune` | finetune | 3062 | **243** | 89.2% [85.5%, 92.6%] |

### 2. The same comparison, paired

Two overlapping intervals do not settle whether one model beats another on the same
examples. McNemar does, over the examples the two disagree about -- read it alongside the
intervals above, never instead of them.

| pair | n | a only | b only | p |
|---|---|---|---|---|
| `majority_class` vs `length_only` | 3062 | 0 | 0 | 1 |
| `majority_class` vs `tfidf_logreg` | 3062 | 286 | 0 | 1.61e-86 |
| `majority_class` vs `arm_a_probe` | 3062 | 537 | 0 | 4.45e-162 |
| `majority_class` vs `arm_b_finetune` | 3062 | 339 | 0 | 1.79e-102 |
| `length_only` vs `tfidf_logreg` | 3062 | 286 | 0 | 1.61e-86 |
| `length_only` vs `arm_a_probe` | 3062 | 537 | 0 | 4.45e-162 |
| `length_only` vs `arm_b_finetune` | 3062 | 339 | 0 | 1.79e-102 |
| `tfidf_logreg` vs `arm_a_probe` | 3062 | 392 | 141 | 2.37e-28 |
| `tfidf_logreg` vs `arm_b_finetune` | 3062 | 251 | 198 | 0.014 |
| `arm_a_probe` vs `arm_b_finetune` | 3062 | 196 | 394 | 2.66e-16 |

### 3. Where the errors fall

The per-fragment table below, as one number per model. Errors spread thinly across many
fragments say the method is too weak. Errors piled onto a handful say those specific ideas
are not learnable from the data we have -- and the table names them, which is what makes
this the most decision-useful thing in the report.

* `majority_class`: 3960 errors across 108 of 351 decisive fragments. Half of them fall on **38** fragments (an even spread would be 54.0); the worst ten carry 15.8% of all errors.
* `length_only`: 3960 errors across 108 of 351 decisive fragments. Half of them fall on **38** fragments (an even spread would be 54.0); the worst ten carry 15.8% of all errors.
* `tfidf_logreg`: 2468 errors across 159 of 351 decisive fragments. Half of them fall on **29** fragments (an even spread would be 79.5); the worst ten carry 21.8% of all errors.
* `arm_a_probe`: 2080 errors across 231 of 351 decisive fragments. Half of them fall on **33** fragments (an even spread would be 115.5); the worst ten carry 21.3% of all errors.
* `arm_b_finetune`: 1194 errors across 86 of 351 decisive fragments. Half of them fall on **17** fragments (an even spread would be 43.0); the worst ten carry 33.9% of all errors.

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
| `length_only__shuffled` | 60.4% [39.1%, 76.8%] | 25.1% [18.7%, 29.0%] |
| `tfidf_logreg__shuffled` | 60.4% [39.1%, 76.8%] | 25.1% [18.7%, 29.0%] |
| `arm_b_finetune__shuffled` | 60.4% [39.1%, 76.8%] | 25.1% [18.7%, 29.0%] |

## Paired comparisons (McNemar, raw argmax)

Exact two-sided McNemar over the examples the two models disagree about. Pairing unit is the
example, not the cluster -- see the limitations.

| pair | slice | n | a only | b only | p |
|---|---|---|---|---|---|
| `majority_class` vs `length_only` | overall | 10000 | 0 | 0 | 1 |
| `majority_class` vs `length_only` | null_ambiguous | 3062 | 0 | 0 | 1 |
| `majority_class` vs `tfidf_logreg` | overall | 10000 | 288 | 1790 | 2.49e-264 |
| `majority_class` vs `tfidf_logreg` | null_ambiguous | 3062 | 286 | 0 | 1.61e-86 |
| `majority_class` vs `arm_a_probe` | overall | 10000 | 542 | 2418 | 4.35e-281 |
| `majority_class` vs `arm_a_probe` | null_ambiguous | 3062 | 537 | 0 | 4.45e-162 |
| `majority_class` vs `arm_b_finetune` | overall | 10000 | 355 | 3110 | 0 |
| `majority_class` vs `arm_b_finetune` | null_ambiguous | 3062 | 339 | 0 | 1.79e-102 |
| `length_only` vs `tfidf_logreg` | overall | 10000 | 288 | 1790 | 2.49e-264 |
| `length_only` vs `tfidf_logreg` | null_ambiguous | 3062 | 286 | 0 | 1.61e-86 |
| `length_only` vs `arm_a_probe` | overall | 10000 | 542 | 2418 | 4.35e-281 |
| `length_only` vs `arm_a_probe` | null_ambiguous | 3062 | 537 | 0 | 4.45e-162 |
| `length_only` vs `arm_b_finetune` | overall | 10000 | 355 | 3110 | 0 |
| `length_only` vs `arm_b_finetune` | null_ambiguous | 3062 | 339 | 0 | 1.79e-102 |
| `tfidf_logreg` vs `arm_a_probe` | overall | 10000 | 784 | 1158 | 2.06e-17 |
| `tfidf_logreg` vs `arm_a_probe` | null_ambiguous | 3062 | 392 | 141 | 2.37e-28 |
| `tfidf_logreg` vs `arm_b_finetune` | overall | 10000 | 454 | 1707 | 4.96e-170 |
| `tfidf_logreg` vs `arm_b_finetune` | null_ambiguous | 3062 | 251 | 198 | 0.014 |
| `arm_a_probe` vs `arm_b_finetune` | overall | 10000 | 456 | 1335 | 9.14e-100 |
| `arm_a_probe` vs `arm_b_finetune` | null_ambiguous | 3062 | 196 | 394 | 2.66e-16 |

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
| `nocturia_false` | 2479 | 0.0% | 0.0% | 48.2% | 64.4% | 82.4% | 82.4pp |
| `nocturia_true` | 1481 | 0.0% | 0.0% | 38.5% | 55.2% | 71.1% | 71.1pp |
| `nocturia_null_attribution` | 655 | 100.0% | 100.0% | 86.0% | 73.3% | 88.2% | 26.7pp |
| `nocturia_null_metaphor` | 682 | 100.0% | 100.0% | 93.1% | 80.2% | 91.6% | 19.8pp |
| `nocturia_null_hedged` | 592 | 100.0% | 100.0% | 97.3% | 88.7% | 80.9% | 19.1pp |
| `nocturia_null_thirdparty` | 579 | 100.0% | 100.0% | 87.7% | 83.4% | 93.3% | 16.6pp |
| `nocturia_null_historical` | 554 | 100.0% | 100.0% | 91.5% | 89.2% | 92.1% | 10.8pp |
| `(none)` | 2978 | 100.0% | 100.0% | 100.0% | 99.8% | 99.5% | 0.5pp |

### By fragment, errors

Ordered by the worst model's error count, so the fragments the comparison is about sort
to the top whichever encoder wins. Counts, not rates: these are the sentences a month of
library work would be spent on. The JSON holds every fragment.

| fragment | library | truth | `majority_class` | `length_only` | `tfidf_logreg` | `arm_a_probe` | `arm_b_finetune` | spread |
|---|---|---|---|---|---|---|---|---|
| `nocturia_false:75848908` | `nocturia_false` | false | 74 | 74 | 56 | 52 | 0 | 74 |
| `nocturia_false:3e89d247` | `nocturia_false` | false | 68 | 68 | 67 | 30 | 0 | 68 |
| `nocturia_false:0105f271` | `nocturia_false` | false | 67 | 67 | 56 | 26 | 0 | 67 |
| `nocturia_false:3a70bcb2` | `nocturia_false` | false | 63 | 63 | 63 | 20 | 0 | 63 |
| `nocturia_false:e6fd6a44` | `nocturia_false` | false | 61 | 61 | 0 | 7 | 7 | 61 |
| `nocturia_false:776d32bb` | `nocturia_false` | false | 60 | 60 | 52 | 8 | 0 | 60 |
| `nocturia_false:876119ca` | `nocturia_false` | false | 60 | 60 | 7 | 44 | 20 | 53 |
| `nocturia_false:79441d6a` | `nocturia_false` | false | 59 | 59 | 10 | 1 | 0 | 59 |
| `nocturia_false:76105311` | `nocturia_false` | false | 57 | 57 | 9 | 1 | 0 | 57 |
| `nocturia_false:01f605e7` | `nocturia_false` | false | 55 | 55 | 20 | 15 | 0 | 55 |
| `nocturia_false:3fbd0758` | `nocturia_false` | false | 55 | 55 | 3 | 4 | 0 | 55 |
| `nocturia_false:cd9ee762` | `nocturia_false` | false | 55 | 55 | 1 | 0 | 0 | 55 |
| `nocturia_false:21180255` | `nocturia_false` | false | 54 | 54 | 54 | 42 | 0 | 54 |
| `nocturia_false:31c155d0` | `nocturia_false` | false | 54 | 54 | 3 | 9 | 0 | 54 |
| `nocturia_false:a9489bdd` | `nocturia_false` | false | 54 | 54 | 1 | 1 | 0 | 54 |
| `nocturia_false:cddf064c` | `nocturia_false` | false | 53 | 53 | 48 | 9 | 0 | 53 |
| `nocturia_false:48f35b91` | `nocturia_false` | false | 52 | 52 | 0 | 5 | 0 | 52 |
| `nocturia_false:3aab37fe` | `nocturia_false` | false | 51 | 51 | 48 | 15 | 51 | 36 |
| `nocturia_false:a9555a97` | `nocturia_false` | false | 51 | 51 | 43 | 6 | 0 | 51 |
| `nocturia_false:59e83d34` | `nocturia_false` | false | 50 | 50 | 2 | 7 | 0 | 50 |
| `nocturia_true:c3f73311` | `nocturia_true` | true | 50 | 50 | 13 | 43 | 1 | 49 |
| `nocturia_false:1bd2f6f8` | `nocturia_false` | false | 49 | 49 | 45 | 49 | 49 | 4 |
| `nocturia_false:55832b2b` | `nocturia_false` | false | 49 | 49 | 12 | 7 | 0 | 49 |
| `nocturia_false:b11139a0` | `nocturia_false` | false | 49 | 49 | 0 | 4 | 0 | 49 |
| `nocturia_false:98d02ead` | `nocturia_false` | false | 48 | 48 | 40 | 47 | 32 | 16 |
| `nocturia_true:86e1cd53` | `nocturia_true` | true | 48 | 48 | 47 | 48 | 48 | 1 |
| `nocturia_false:bf88ba0d` | `nocturia_false` | false | 47 | 47 | 47 | 41 | 28 | 19 |
| `nocturia_false:eff52ced` | `nocturia_false` | false | 47 | 47 | 11 | 28 | 18 | 36 |
| `nocturia_false:5e819a32` | `nocturia_false` | false | 46 | 46 | 46 | 33 | 0 | 46 |
| `nocturia_false:b1f7e93f` | `nocturia_false` | false | 46 | 46 | 46 | 23 | 0 | 46 |
| `nocturia_false:c6a4c61b` | `nocturia_false` | false | 46 | 46 | 0 | 10 | 0 | 46 |
| `nocturia_false:99cd439f` | `nocturia_false` | false | 45 | 45 | 45 | 36 | 0 | 45 |
| `nocturia_false:dfdc943b` | `nocturia_false` | false | 45 | 45 | 2 | 21 | 0 | 45 |
| `nocturia_true:594869e7` | `nocturia_true` | true | 44 | 44 | 27 | 35 | 33 | 17 |
| `nocturia_false:1a41970c` | `nocturia_false` | false | 43 | 43 | 1 | 16 | 19 | 42 |
| `nocturia_false:1cb7de3b` | `nocturia_false` | false | 43 | 43 | 42 | 9 | 40 | 34 |
| `nocturia_false:4a12f37a` | `nocturia_false` | false | 43 | 43 | 42 | 13 | 0 | 43 |
| `nocturia_false:f4140180` | `nocturia_false` | false | 43 | 43 | 2 | 2 | 0 | 43 |
| `nocturia_false:08a0b22d` | `nocturia_false` | false | 41 | 41 | 0 | 8 | 0 | 41 |
| `nocturia_false:2e5a7e5a` | `nocturia_false` | false | 41 | 41 | 4 | 19 | 38 | 37 |

*221 further fragments erred on at least one model; the JSON holds them all.*

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
| attribution | 655 | **51** | 100.0% [100.0%, 100.0%] |
| hedged | 592 | **47** | 100.0% [100.0%, 100.0%] |
| historical | 554 | **46** | 100.0% [100.0%, 100.0%] |
| metaphor | 682 | **52** | 100.0% [100.0%, 100.0%] |
| third_party | 579 | **47** | 100.0% [100.0%, 100.0%] |

### By fragment library

| library | n | eff n | accuracy [95% CI] |
|---|---|---|---|
| nocturia_false | 2479 | **54** | 0.0% [0.0%, 0.0%] |
| nocturia_null_attribution | 655 | **51** | 100.0% [100.0%, 100.0%] |
| nocturia_null_hedged | 592 | **47** | 100.0% [100.0%, 100.0%] |
| nocturia_null_historical | 554 | **46** | 100.0% [100.0%, 100.0%] |
| nocturia_null_metaphor | 682 | **52** | 100.0% [100.0%, 100.0%] |
| nocturia_null_thirdparty | 579 | **47** | 100.0% [100.0%, 100.0%] |
| nocturia_true | 1481 | **54** | 0.0% [0.0%, 0.0%] |
| (none) | 2978 | **1** | 100.0% [100.0%, 100.0%] |

### Per-fragment errors (worst first)

Whether errors are spread thinly across many fragments or piled onto a few is the difference
between "the method is too weak" (model work) and "these specific ideas are not learnable from
the data we have" (library work, and these are the fragments to write more of). No intervals:
a fragment is one cluster, so an interval over its own examples measures nothing.

108 of 351 decisive fragments were got wrong at least once.

`majority_class`: 3960 errors across 108 of 351 decisive fragments. Half of them fall on **38** fragments (an even spread would be 54.0); the worst ten carry 15.8% of all errors.

| fragment | library | sub-class | truth | correct | accuracy | predicted as |
|---|---|---|---|---|---|---|
| `nocturia_false:75848908` | `nocturia_false` | -- | false | 0/74 | 0.0% | null 74 |
| `nocturia_false:3e89d247` | `nocturia_false` | -- | false | 0/68 | 0.0% | null 68 |
| `nocturia_false:0105f271` | `nocturia_false` | -- | false | 0/67 | 0.0% | null 67 |
| `nocturia_false:3a70bcb2` | `nocturia_false` | -- | false | 0/63 | 0.0% | null 63 |
| `nocturia_false:e6fd6a44` | `nocturia_false` | -- | false | 0/61 | 0.0% | null 61 |
| `nocturia_false:776d32bb` | `nocturia_false` | -- | false | 0/60 | 0.0% | null 60 |
| `nocturia_false:876119ca` | `nocturia_false` | -- | false | 0/60 | 0.0% | null 60 |
| `nocturia_false:79441d6a` | `nocturia_false` | -- | false | 0/59 | 0.0% | null 59 |
| `nocturia_false:76105311` | `nocturia_false` | -- | false | 0/57 | 0.0% | null 57 |
| `nocturia_false:01f605e7` | `nocturia_false` | -- | false | 0/55 | 0.0% | null 55 |
| `nocturia_false:3fbd0758` | `nocturia_false` | -- | false | 0/55 | 0.0% | null 55 |
| `nocturia_false:cd9ee762` | `nocturia_false` | -- | false | 0/55 | 0.0% | null 55 |
| `nocturia_false:21180255` | `nocturia_false` | -- | false | 0/54 | 0.0% | null 54 |
| `nocturia_false:31c155d0` | `nocturia_false` | -- | false | 0/54 | 0.0% | null 54 |
| `nocturia_false:a9489bdd` | `nocturia_false` | -- | false | 0/54 | 0.0% | null 54 |
| `nocturia_false:cddf064c` | `nocturia_false` | -- | false | 0/53 | 0.0% | null 53 |
| `nocturia_false:48f35b91` | `nocturia_false` | -- | false | 0/52 | 0.0% | null 52 |
| `nocturia_false:3aab37fe` | `nocturia_false` | -- | false | 0/51 | 0.0% | null 51 |
| `nocturia_false:a9555a97` | `nocturia_false` | -- | false | 0/51 | 0.0% | null 51 |
| `nocturia_false:59e83d34` | `nocturia_false` | -- | false | 0/50 | 0.0% | null 50 |
| `nocturia_true:c3f73311` | `nocturia_true` | -- | true | 0/50 | 0.0% | null 50 |
| `nocturia_false:1bd2f6f8` | `nocturia_false` | -- | false | 0/49 | 0.0% | null 49 |
| `nocturia_false:55832b2b` | `nocturia_false` | -- | false | 0/49 | 0.0% | null 49 |
| `nocturia_false:b11139a0` | `nocturia_false` | -- | false | 0/49 | 0.0% | null 49 |
| `nocturia_false:98d02ead` | `nocturia_false` | -- | false | 0/48 | 0.0% | null 48 |
| `nocturia_true:86e1cd53` | `nocturia_true` | -- | true | 0/48 | 0.0% | null 48 |
| `nocturia_false:bf88ba0d` | `nocturia_false` | -- | false | 0/47 | 0.0% | null 47 |
| `nocturia_false:eff52ced` | `nocturia_false` | -- | false | 0/47 | 0.0% | null 47 |
| `nocturia_false:5e819a32` | `nocturia_false` | -- | false | 0/46 | 0.0% | null 46 |
| `nocturia_false:b1f7e93f` | `nocturia_false` | -- | false | 0/46 | 0.0% | null 46 |
| `nocturia_false:c6a4c61b` | `nocturia_false` | -- | false | 0/46 | 0.0% | null 46 |
| `nocturia_false:99cd439f` | `nocturia_false` | -- | false | 0/45 | 0.0% | null 45 |
| `nocturia_false:dfdc943b` | `nocturia_false` | -- | false | 0/45 | 0.0% | null 45 |
| `nocturia_true:594869e7` | `nocturia_true` | -- | true | 0/44 | 0.0% | null 44 |
| `nocturia_false:1a41970c` | `nocturia_false` | -- | false | 0/43 | 0.0% | null 43 |
| `nocturia_false:1cb7de3b` | `nocturia_false` | -- | false | 0/43 | 0.0% | null 43 |
| `nocturia_false:4a12f37a` | `nocturia_false` | -- | false | 0/43 | 0.0% | null 43 |
| `nocturia_false:f4140180` | `nocturia_false` | -- | false | 0/43 | 0.0% | null 43 |
| `nocturia_false:08a0b22d` | `nocturia_false` | -- | false | 0/41 | 0.0% | null 41 |
| `nocturia_false:2e5a7e5a` | `nocturia_false` | -- | false | 0/41 | 0.0% | null 41 |

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
| attribution | 655 | **51** | 100.0% [100.0%, 100.0%] |
| hedged | 592 | **47** | 100.0% [100.0%, 100.0%] |
| historical | 554 | **46** | 100.0% [100.0%, 100.0%] |
| metaphor | 682 | **52** | 100.0% [100.0%, 100.0%] |
| third_party | 579 | **47** | 100.0% [100.0%, 100.0%] |

### By fragment library

| library | n | eff n | accuracy [95% CI] |
|---|---|---|---|
| nocturia_false | 2479 | **54** | 0.0% [0.0%, 0.0%] |
| nocturia_null_attribution | 655 | **51** | 100.0% [100.0%, 100.0%] |
| nocturia_null_hedged | 592 | **47** | 100.0% [100.0%, 100.0%] |
| nocturia_null_historical | 554 | **46** | 100.0% [100.0%, 100.0%] |
| nocturia_null_metaphor | 682 | **52** | 100.0% [100.0%, 100.0%] |
| nocturia_null_thirdparty | 579 | **47** | 100.0% [100.0%, 100.0%] |
| nocturia_true | 1481 | **54** | 0.0% [0.0%, 0.0%] |
| (none) | 2978 | **1** | 100.0% [100.0%, 100.0%] |

### Per-fragment errors (worst first)

Whether errors are spread thinly across many fragments or piled onto a few is the difference
between "the method is too weak" (model work) and "these specific ideas are not learnable from
the data we have" (library work, and these are the fragments to write more of). No intervals:
a fragment is one cluster, so an interval over its own examples measures nothing.

108 of 351 decisive fragments were got wrong at least once.

`length_only`: 3960 errors across 108 of 351 decisive fragments. Half of them fall on **38** fragments (an even spread would be 54.0); the worst ten carry 15.8% of all errors.

| fragment | library | sub-class | truth | correct | accuracy | predicted as |
|---|---|---|---|---|---|---|
| `nocturia_false:75848908` | `nocturia_false` | -- | false | 0/74 | 0.0% | null 74 |
| `nocturia_false:3e89d247` | `nocturia_false` | -- | false | 0/68 | 0.0% | null 68 |
| `nocturia_false:0105f271` | `nocturia_false` | -- | false | 0/67 | 0.0% | null 67 |
| `nocturia_false:3a70bcb2` | `nocturia_false` | -- | false | 0/63 | 0.0% | null 63 |
| `nocturia_false:e6fd6a44` | `nocturia_false` | -- | false | 0/61 | 0.0% | null 61 |
| `nocturia_false:776d32bb` | `nocturia_false` | -- | false | 0/60 | 0.0% | null 60 |
| `nocturia_false:876119ca` | `nocturia_false` | -- | false | 0/60 | 0.0% | null 60 |
| `nocturia_false:79441d6a` | `nocturia_false` | -- | false | 0/59 | 0.0% | null 59 |
| `nocturia_false:76105311` | `nocturia_false` | -- | false | 0/57 | 0.0% | null 57 |
| `nocturia_false:01f605e7` | `nocturia_false` | -- | false | 0/55 | 0.0% | null 55 |
| `nocturia_false:3fbd0758` | `nocturia_false` | -- | false | 0/55 | 0.0% | null 55 |
| `nocturia_false:cd9ee762` | `nocturia_false` | -- | false | 0/55 | 0.0% | null 55 |
| `nocturia_false:21180255` | `nocturia_false` | -- | false | 0/54 | 0.0% | null 54 |
| `nocturia_false:31c155d0` | `nocturia_false` | -- | false | 0/54 | 0.0% | null 54 |
| `nocturia_false:a9489bdd` | `nocturia_false` | -- | false | 0/54 | 0.0% | null 54 |
| `nocturia_false:cddf064c` | `nocturia_false` | -- | false | 0/53 | 0.0% | null 53 |
| `nocturia_false:48f35b91` | `nocturia_false` | -- | false | 0/52 | 0.0% | null 52 |
| `nocturia_false:3aab37fe` | `nocturia_false` | -- | false | 0/51 | 0.0% | null 51 |
| `nocturia_false:a9555a97` | `nocturia_false` | -- | false | 0/51 | 0.0% | null 51 |
| `nocturia_false:59e83d34` | `nocturia_false` | -- | false | 0/50 | 0.0% | null 50 |
| `nocturia_true:c3f73311` | `nocturia_true` | -- | true | 0/50 | 0.0% | null 50 |
| `nocturia_false:1bd2f6f8` | `nocturia_false` | -- | false | 0/49 | 0.0% | null 49 |
| `nocturia_false:55832b2b` | `nocturia_false` | -- | false | 0/49 | 0.0% | null 49 |
| `nocturia_false:b11139a0` | `nocturia_false` | -- | false | 0/49 | 0.0% | null 49 |
| `nocturia_false:98d02ead` | `nocturia_false` | -- | false | 0/48 | 0.0% | null 48 |
| `nocturia_true:86e1cd53` | `nocturia_true` | -- | true | 0/48 | 0.0% | null 48 |
| `nocturia_false:bf88ba0d` | `nocturia_false` | -- | false | 0/47 | 0.0% | null 47 |
| `nocturia_false:eff52ced` | `nocturia_false` | -- | false | 0/47 | 0.0% | null 47 |
| `nocturia_false:5e819a32` | `nocturia_false` | -- | false | 0/46 | 0.0% | null 46 |
| `nocturia_false:b1f7e93f` | `nocturia_false` | -- | false | 0/46 | 0.0% | null 46 |
| `nocturia_false:c6a4c61b` | `nocturia_false` | -- | false | 0/46 | 0.0% | null 46 |
| `nocturia_false:99cd439f` | `nocturia_false` | -- | false | 0/45 | 0.0% | null 45 |
| `nocturia_false:dfdc943b` | `nocturia_false` | -- | false | 0/45 | 0.0% | null 45 |
| `nocturia_true:594869e7` | `nocturia_true` | -- | true | 0/44 | 0.0% | null 44 |
| `nocturia_false:1a41970c` | `nocturia_false` | -- | false | 0/43 | 0.0% | null 43 |
| `nocturia_false:1cb7de3b` | `nocturia_false` | -- | false | 0/43 | 0.0% | null 43 |
| `nocturia_false:4a12f37a` | `nocturia_false` | -- | false | 0/43 | 0.0% | null 43 |
| `nocturia_false:f4140180` | `nocturia_false` | -- | false | 0/43 | 0.0% | null 43 |
| `nocturia_false:08a0b22d` | `nocturia_false` | -- | false | 0/41 | 0.0% | null 41 |
| `nocturia_false:2e5a7e5a` | `nocturia_false` | -- | false | 0/41 | 0.0% | null 41 |

*68 further fragments with at least one error are in the JSON sidecar; every fragment is there regardless of score.*

## `tfidf_logreg`

TF-IDF unigrams and bigrams into logistic regression. Tests whether the dataset is keyword-solvable. Its overall accuracy is close to uninformative; the `null_ambiguous` slice is the number that matters.

Decision-rule margins selected per fold (on each fold's own validation split): 0.0, 0.05, 0.2.

*Confusion matrix, raw argmax*

|  | pred false | pred true | pred null | total |
|---|---|---|---|---|
| **truth false** | 1183 | 166 | 1130 | 2479 |
| **truth true** | 212 | 607 | 662 | 1481 |
| **truth null** | 143 | 145 | 5752 | 6040 |
| **total** | 1538 | 918 | 7544 | 10000 |

`null -> true`: 145 of 6040 truly-null examples (2.40%).

*Confusion matrix, after the decision rule*

|  | pred false | pred true | pred null | total |
|---|---|---|---|---|
| **truth false** | 1195 | 151 | 1133 | 2479 |
| **truth true** | 228 | 570 | 683 | 1481 |
| **truth null** | 146 | 128 | 5766 | 6040 |
| **total** | 1569 | 849 | 7582 | 10000 |

`null -> true`: 128 of 6040 truly-null examples (2.12%).

### Per class, after the decision rule

| class | support | predicted | precision | recall | F1 |
|---|---|---|---|---|---|
| `false` | 2479 | 1569 | 76.2% | 48.2% | 59.0% |
| `true` | 1481 | 849 | 67.1% | 38.5% | 48.9% |
| `null` | 6040 | 7582 | 76.0% | 95.5% | 84.7% |

### By label mode

| label mode | n | eff n | accuracy [95% CI] |
|---|---|---|---|
| false | 2479 | **54** | 48.2% [36.3%, 59.7%] |
| null_ambiguous | 3062 | **243** | 91.1% [88.1%, 93.7%] |
| null_structural | 2978 | **1** | 100.0% [100.0%, 100.0%] |
| true | 1481 | **54** | 38.5% [29.2%, 48.8%] |

### By null sub-class

| sub-class | n | eff n | null recall [95% CI] |
|---|---|---|---|
| attribution | 655 | **51** | 86.0% [77.0%, 93.3%] |
| hedged | 592 | **47** | 97.3% [95.3%, 98.8%] |
| historical | 554 | **46** | 91.5% [85.1%, 96.6%] |
| metaphor | 682 | **52** | 93.1% [86.8%, 97.7%] |
| third_party | 579 | **47** | 87.7% [78.8%, 94.8%] |

### By fragment library

| library | n | eff n | accuracy [95% CI] |
|---|---|---|---|
| nocturia_false | 2479 | **54** | 48.2% [36.3%, 59.7%] |
| nocturia_null_attribution | 655 | **51** | 86.0% [77.0%, 93.3%] |
| nocturia_null_hedged | 592 | **47** | 97.3% [95.3%, 98.8%] |
| nocturia_null_historical | 554 | **46** | 91.5% [85.1%, 96.6%] |
| nocturia_null_metaphor | 682 | **52** | 93.1% [86.8%, 97.7%] |
| nocturia_null_thirdparty | 579 | **47** | 87.7% [78.8%, 94.8%] |
| nocturia_true | 1481 | **54** | 38.5% [29.2%, 48.8%] |
| (none) | 2978 | **1** | 100.0% [100.0%, 100.0%] |

### Per-fragment errors (worst first)

Whether errors are spread thinly across many fragments or piled onto a few is the difference
between "the method is too weak" (model work) and "these specific ideas are not learnable from
the data we have" (library work, and these are the fragments to write more of). No intervals:
a fragment is one cluster, so an interval over its own examples measures nothing.

159 of 351 decisive fragments were got wrong at least once.

`tfidf_logreg`: 2468 errors across 159 of 351 decisive fragments. Half of them fall on **29** fragments (an even spread would be 79.5); the worst ten carry 21.8% of all errors.

| fragment | library | sub-class | truth | correct | accuracy | predicted as |
|---|---|---|---|---|---|---|
| `nocturia_false:3a70bcb2` | `nocturia_false` | -- | false | 0/63 | 0.0% | true 2, null 61 |
| `nocturia_false:21180255` | `nocturia_false` | -- | false | 0/54 | 0.0% | null 54 |
| `nocturia_false:bf88ba0d` | `nocturia_false` | -- | false | 0/47 | 0.0% | null 47 |
| `nocturia_false:5e819a32` | `nocturia_false` | -- | false | 0/46 | 0.0% | true 5, null 41 |
| `nocturia_false:b1f7e93f` | `nocturia_false` | -- | false | 0/46 | 0.0% | true 46 |
| `nocturia_false:99cd439f` | `nocturia_false` | -- | false | 0/45 | 0.0% | null 45 |
| `nocturia_true:0740576d` | `nocturia_true` | -- | true | 0/40 | 0.0% | null 40 |
| `nocturia_false:deb3785c` | `nocturia_false` | -- | false | 0/38 | 0.0% | null 38 |
| `nocturia_false:0620aada` | `nocturia_false` | -- | false | 0/37 | 0.0% | null 37 |
| `nocturia_true:4a4f4b70` | `nocturia_true` | -- | true | 0/34 | 0.0% | false 2, null 32 |
| `nocturia_true:f3e4ee3e` | `nocturia_true` | -- | true | 0/34 | 0.0% | null 34 |
| `nocturia_false:2ba145eb` | `nocturia_false` | -- | false | 0/32 | 0.0% | null 32 |
| `nocturia_true:126e0cfb` | `nocturia_true` | -- | true | 0/32 | 0.0% | false 4, null 28 |
| `nocturia_true:a2f6ab3f` | `nocturia_true` | -- | true | 0/31 | 0.0% | false 15, null 16 |
| `nocturia_false:5efba823` | `nocturia_false` | -- | false | 0/30 | 0.0% | null 30 |
| `nocturia_true:f2891c69` | `nocturia_true` | -- | true | 0/30 | 0.0% | false 15, null 15 |
| `nocturia_false:14ecd3b3` | `nocturia_false` | -- | false | 0/28 | 0.0% | true 28 |
| `nocturia_true:00a2bd48` | `nocturia_true` | -- | true | 0/28 | 0.0% | false 22, null 6 |
| `nocturia_true:0c394532` | `nocturia_true` | -- | true | 0/27 | 0.0% | false 1, null 26 |
| `nocturia_true:4506c1ce` | `nocturia_true` | -- | true | 0/26 | 0.0% | null 26 |
| `nocturia_true:efa44ced` | `nocturia_true` | -- | true | 0/25 | 0.0% | null 25 |
| `nocturia_true:1e14667e` | `nocturia_true` | -- | true | 0/19 | 0.0% | false 17, null 2 |
| `nocturia_true:f81d11be` | `nocturia_true` | -- | true | 0/19 | 0.0% | null 19 |
| `nocturia_null_attribution:0dfc44e6` | `nocturia_null_attribution` | attribution | null | 0/16 | 0.0% | false 3, true 13 |
| `nocturia_true:4dc9876b` | `nocturia_true` | -- | true | 0/15 | 0.0% | false 1, null 14 |
| `nocturia_true:e847f8b0` | `nocturia_true` | -- | true | 0/15 | 0.0% | false 9, null 6 |
| `nocturia_null_thirdparty:6ecdd54e` | `nocturia_null_thirdparty` | third_party | null | 0/13 | 0.0% | false 2, true 11 |
| `nocturia_null_historical:9354ddb0` | `nocturia_null_historical` | historical | null | 0/11 | 0.0% | true 11 |
| `nocturia_false:3e89d247` | `nocturia_false` | -- | false | 1/68 | 1.5% | false 1, null 67 |
| `nocturia_true:86e1cd53` | `nocturia_true` | -- | true | 1/48 | 2.1% | false 2, true 1, null 45 |
| `nocturia_false:1cb7de3b` | `nocturia_false` | -- | false | 1/43 | 2.3% | false 1, null 42 |
| `nocturia_false:4a12f37a` | `nocturia_false` | -- | false | 1/43 | 2.3% | false 1, null 42 |
| `nocturia_true:23c9421e` | `nocturia_true` | -- | true | 1/33 | 3.0% | false 24, true 1, null 8 |
| `nocturia_true:39566c91` | `nocturia_true` | -- | true | 1/32 | 3.1% | false 2, true 1, null 29 |
| `nocturia_false:32f00a7f` | `nocturia_false` | -- | false | 1/31 | 3.2% | false 1, null 30 |
| `nocturia_false:72f0059f` | `nocturia_false` | -- | false | 1/30 | 3.3% | false 1, true 1, null 28 |
| `nocturia_true:e853d9c0` | `nocturia_true` | -- | true | 1/28 | 3.6% | true 1, null 27 |
| `nocturia_true:fa67d22f` | `nocturia_true` | -- | true | 1/25 | 4.0% | true 1, null 24 |
| `nocturia_true:8cfc0f45` | `nocturia_true` | -- | true | 2/35 | 5.7% | true 2, null 33 |
| `nocturia_false:3aab37fe` | `nocturia_false` | -- | false | 3/51 | 5.9% | false 3, null 48 |

*119 further fragments with at least one error are in the JSON sidecar; every fragment is there regardless of score.*

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
| attribution | 655 | **51** | 100.0% [100.0%, 100.0%] |
| hedged | 592 | **47** | 100.0% [100.0%, 100.0%] |
| historical | 554 | **46** | 100.0% [100.0%, 100.0%] |
| metaphor | 682 | **52** | 100.0% [100.0%, 100.0%] |
| third_party | 579 | **47** | 100.0% [100.0%, 100.0%] |

### By fragment library

| library | n | eff n | accuracy [95% CI] |
|---|---|---|---|
| nocturia_false | 2479 | **54** | 0.0% [0.0%, 0.0%] |
| nocturia_null_attribution | 655 | **51** | 100.0% [100.0%, 100.0%] |
| nocturia_null_hedged | 592 | **47** | 100.0% [100.0%, 100.0%] |
| nocturia_null_historical | 554 | **46** | 100.0% [100.0%, 100.0%] |
| nocturia_null_metaphor | 682 | **52** | 100.0% [100.0%, 100.0%] |
| nocturia_null_thirdparty | 579 | **47** | 100.0% [100.0%, 100.0%] |
| nocturia_true | 1481 | **54** | 0.0% [0.0%, 0.0%] |
| (none) | 2978 | **1** | 100.0% [100.0%, 100.0%] |

### Per-fragment errors (worst first)

Whether errors are spread thinly across many fragments or piled onto a few is the difference
between "the method is too weak" (model work) and "these specific ideas are not learnable from
the data we have" (library work, and these are the fragments to write more of). No intervals:
a fragment is one cluster, so an interval over its own examples measures nothing.

108 of 351 decisive fragments were got wrong at least once.

`length_only__shuffled`: 3960 errors across 108 of 351 decisive fragments. Half of them fall on **38** fragments (an even spread would be 54.0); the worst ten carry 15.8% of all errors.

| fragment | library | sub-class | truth | correct | accuracy | predicted as |
|---|---|---|---|---|---|---|
| `nocturia_false:75848908` | `nocturia_false` | -- | false | 0/74 | 0.0% | null 74 |
| `nocturia_false:3e89d247` | `nocturia_false` | -- | false | 0/68 | 0.0% | null 68 |
| `nocturia_false:0105f271` | `nocturia_false` | -- | false | 0/67 | 0.0% | null 67 |
| `nocturia_false:3a70bcb2` | `nocturia_false` | -- | false | 0/63 | 0.0% | null 63 |
| `nocturia_false:e6fd6a44` | `nocturia_false` | -- | false | 0/61 | 0.0% | null 61 |
| `nocturia_false:776d32bb` | `nocturia_false` | -- | false | 0/60 | 0.0% | null 60 |
| `nocturia_false:876119ca` | `nocturia_false` | -- | false | 0/60 | 0.0% | null 60 |
| `nocturia_false:79441d6a` | `nocturia_false` | -- | false | 0/59 | 0.0% | null 59 |
| `nocturia_false:76105311` | `nocturia_false` | -- | false | 0/57 | 0.0% | null 57 |
| `nocturia_false:01f605e7` | `nocturia_false` | -- | false | 0/55 | 0.0% | null 55 |
| `nocturia_false:3fbd0758` | `nocturia_false` | -- | false | 0/55 | 0.0% | null 55 |
| `nocturia_false:cd9ee762` | `nocturia_false` | -- | false | 0/55 | 0.0% | null 55 |
| `nocturia_false:21180255` | `nocturia_false` | -- | false | 0/54 | 0.0% | null 54 |
| `nocturia_false:31c155d0` | `nocturia_false` | -- | false | 0/54 | 0.0% | null 54 |
| `nocturia_false:a9489bdd` | `nocturia_false` | -- | false | 0/54 | 0.0% | null 54 |
| `nocturia_false:cddf064c` | `nocturia_false` | -- | false | 0/53 | 0.0% | null 53 |
| `nocturia_false:48f35b91` | `nocturia_false` | -- | false | 0/52 | 0.0% | null 52 |
| `nocturia_false:3aab37fe` | `nocturia_false` | -- | false | 0/51 | 0.0% | null 51 |
| `nocturia_false:a9555a97` | `nocturia_false` | -- | false | 0/51 | 0.0% | null 51 |
| `nocturia_false:59e83d34` | `nocturia_false` | -- | false | 0/50 | 0.0% | null 50 |
| `nocturia_true:c3f73311` | `nocturia_true` | -- | true | 0/50 | 0.0% | null 50 |
| `nocturia_false:1bd2f6f8` | `nocturia_false` | -- | false | 0/49 | 0.0% | null 49 |
| `nocturia_false:55832b2b` | `nocturia_false` | -- | false | 0/49 | 0.0% | null 49 |
| `nocturia_false:b11139a0` | `nocturia_false` | -- | false | 0/49 | 0.0% | null 49 |
| `nocturia_false:98d02ead` | `nocturia_false` | -- | false | 0/48 | 0.0% | null 48 |
| `nocturia_true:86e1cd53` | `nocturia_true` | -- | true | 0/48 | 0.0% | null 48 |
| `nocturia_false:bf88ba0d` | `nocturia_false` | -- | false | 0/47 | 0.0% | null 47 |
| `nocturia_false:eff52ced` | `nocturia_false` | -- | false | 0/47 | 0.0% | null 47 |
| `nocturia_false:5e819a32` | `nocturia_false` | -- | false | 0/46 | 0.0% | null 46 |
| `nocturia_false:b1f7e93f` | `nocturia_false` | -- | false | 0/46 | 0.0% | null 46 |
| `nocturia_false:c6a4c61b` | `nocturia_false` | -- | false | 0/46 | 0.0% | null 46 |
| `nocturia_false:99cd439f` | `nocturia_false` | -- | false | 0/45 | 0.0% | null 45 |
| `nocturia_false:dfdc943b` | `nocturia_false` | -- | false | 0/45 | 0.0% | null 45 |
| `nocturia_true:594869e7` | `nocturia_true` | -- | true | 0/44 | 0.0% | null 44 |
| `nocturia_false:1a41970c` | `nocturia_false` | -- | false | 0/43 | 0.0% | null 43 |
| `nocturia_false:1cb7de3b` | `nocturia_false` | -- | false | 0/43 | 0.0% | null 43 |
| `nocturia_false:4a12f37a` | `nocturia_false` | -- | false | 0/43 | 0.0% | null 43 |
| `nocturia_false:f4140180` | `nocturia_false` | -- | false | 0/43 | 0.0% | null 43 |
| `nocturia_false:08a0b22d` | `nocturia_false` | -- | false | 0/41 | 0.0% | null 41 |
| `nocturia_false:2e5a7e5a` | `nocturia_false` | -- | false | 0/41 | 0.0% | null 41 |

*68 further fragments with at least one error are in the JSON sidecar; every fragment is there regardless of score.*

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
| false | 2479 | **54** | 0.0% [0.0%, 0.0%] |
| null_ambiguous | 3062 | **243** | 100.0% [99.9%, 100.0%] |
| null_structural | 2978 | **1** | 100.0% [100.0%, 100.0%] |
| true | 1481 | **54** | 0.0% [0.0%, 0.0%] |

### By null sub-class

| sub-class | n | eff n | null recall [95% CI] |
|---|---|---|---|
| attribution | 655 | **51** | 99.8% [99.5%, 100.0%] |
| hedged | 592 | **47** | 100.0% [100.0%, 100.0%] |
| historical | 554 | **46** | 100.0% [100.0%, 100.0%] |
| metaphor | 682 | **52** | 100.0% [100.0%, 100.0%] |
| third_party | 579 | **47** | 100.0% [100.0%, 100.0%] |

### By fragment library

| library | n | eff n | accuracy [95% CI] |
|---|---|---|---|
| nocturia_false | 2479 | **54** | 0.0% [0.0%, 0.0%] |
| nocturia_null_attribution | 655 | **51** | 99.8% [99.5%, 100.0%] |
| nocturia_null_hedged | 592 | **47** | 100.0% [100.0%, 100.0%] |
| nocturia_null_historical | 554 | **46** | 100.0% [100.0%, 100.0%] |
| nocturia_null_metaphor | 682 | **52** | 100.0% [100.0%, 100.0%] |
| nocturia_null_thirdparty | 579 | **47** | 100.0% [100.0%, 100.0%] |
| nocturia_true | 1481 | **54** | 0.0% [0.0%, 0.0%] |
| (none) | 2978 | **1** | 100.0% [100.0%, 100.0%] |

### Per-fragment errors (worst first)

Whether errors are spread thinly across many fragments or piled onto a few is the difference
between "the method is too weak" (model work) and "these specific ideas are not learnable from
the data we have" (library work, and these are the fragments to write more of). No intervals:
a fragment is one cluster, so an interval over its own examples measures nothing.

109 of 351 decisive fragments were got wrong at least once.

`tfidf_logreg__shuffled`: 3961 errors across 109 of 351 decisive fragments. Half of them fall on **38** fragments (an even spread would be 54.5); the worst ten carry 15.8% of all errors.

| fragment | library | sub-class | truth | correct | accuracy | predicted as |
|---|---|---|---|---|---|---|
| `nocturia_false:75848908` | `nocturia_false` | -- | false | 0/74 | 0.0% | null 74 |
| `nocturia_false:3e89d247` | `nocturia_false` | -- | false | 0/68 | 0.0% | null 68 |
| `nocturia_false:0105f271` | `nocturia_false` | -- | false | 0/67 | 0.0% | null 67 |
| `nocturia_false:3a70bcb2` | `nocturia_false` | -- | false | 0/63 | 0.0% | null 63 |
| `nocturia_false:e6fd6a44` | `nocturia_false` | -- | false | 0/61 | 0.0% | null 61 |
| `nocturia_false:776d32bb` | `nocturia_false` | -- | false | 0/60 | 0.0% | null 60 |
| `nocturia_false:876119ca` | `nocturia_false` | -- | false | 0/60 | 0.0% | null 60 |
| `nocturia_false:79441d6a` | `nocturia_false` | -- | false | 0/59 | 0.0% | null 59 |
| `nocturia_false:76105311` | `nocturia_false` | -- | false | 0/57 | 0.0% | null 57 |
| `nocturia_false:01f605e7` | `nocturia_false` | -- | false | 0/55 | 0.0% | null 55 |
| `nocturia_false:3fbd0758` | `nocturia_false` | -- | false | 0/55 | 0.0% | null 55 |
| `nocturia_false:cd9ee762` | `nocturia_false` | -- | false | 0/55 | 0.0% | null 55 |
| `nocturia_false:21180255` | `nocturia_false` | -- | false | 0/54 | 0.0% | null 54 |
| `nocturia_false:31c155d0` | `nocturia_false` | -- | false | 0/54 | 0.0% | null 54 |
| `nocturia_false:a9489bdd` | `nocturia_false` | -- | false | 0/54 | 0.0% | null 54 |
| `nocturia_false:cddf064c` | `nocturia_false` | -- | false | 0/53 | 0.0% | null 53 |
| `nocturia_false:48f35b91` | `nocturia_false` | -- | false | 0/52 | 0.0% | null 52 |
| `nocturia_false:3aab37fe` | `nocturia_false` | -- | false | 0/51 | 0.0% | null 51 |
| `nocturia_false:a9555a97` | `nocturia_false` | -- | false | 0/51 | 0.0% | null 51 |
| `nocturia_false:59e83d34` | `nocturia_false` | -- | false | 0/50 | 0.0% | null 50 |
| `nocturia_true:c3f73311` | `nocturia_true` | -- | true | 0/50 | 0.0% | null 50 |
| `nocturia_false:1bd2f6f8` | `nocturia_false` | -- | false | 0/49 | 0.0% | null 49 |
| `nocturia_false:55832b2b` | `nocturia_false` | -- | false | 0/49 | 0.0% | null 49 |
| `nocturia_false:b11139a0` | `nocturia_false` | -- | false | 0/49 | 0.0% | null 49 |
| `nocturia_false:98d02ead` | `nocturia_false` | -- | false | 0/48 | 0.0% | null 48 |
| `nocturia_true:86e1cd53` | `nocturia_true` | -- | true | 0/48 | 0.0% | null 48 |
| `nocturia_false:bf88ba0d` | `nocturia_false` | -- | false | 0/47 | 0.0% | null 47 |
| `nocturia_false:eff52ced` | `nocturia_false` | -- | false | 0/47 | 0.0% | null 47 |
| `nocturia_false:5e819a32` | `nocturia_false` | -- | false | 0/46 | 0.0% | null 46 |
| `nocturia_false:b1f7e93f` | `nocturia_false` | -- | false | 0/46 | 0.0% | null 46 |
| `nocturia_false:c6a4c61b` | `nocturia_false` | -- | false | 0/46 | 0.0% | null 46 |
| `nocturia_false:99cd439f` | `nocturia_false` | -- | false | 0/45 | 0.0% | null 45 |
| `nocturia_false:dfdc943b` | `nocturia_false` | -- | false | 0/45 | 0.0% | null 45 |
| `nocturia_true:594869e7` | `nocturia_true` | -- | true | 0/44 | 0.0% | null 44 |
| `nocturia_false:1a41970c` | `nocturia_false` | -- | false | 0/43 | 0.0% | null 43 |
| `nocturia_false:1cb7de3b` | `nocturia_false` | -- | false | 0/43 | 0.0% | null 43 |
| `nocturia_false:4a12f37a` | `nocturia_false` | -- | false | 0/43 | 0.0% | null 43 |
| `nocturia_false:f4140180` | `nocturia_false` | -- | false | 0/43 | 0.0% | null 43 |
| `nocturia_false:08a0b22d` | `nocturia_false` | -- | false | 0/41 | 0.0% | null 41 |
| `nocturia_false:2e5a7e5a` | `nocturia_false` | -- | false | 0/41 | 0.0% | null 41 |

*69 further fragments with at least one error are in the JSON sidecar; every fragment is there regardless of score.*

## `arm_a_probe`

Frozen `roberta-base`, mean-pooled, with a `Linear(768, 3)` probe over the cached embeddings (2,307 parameters). The encoder learns nothing; only the probe is fitted. Expected to handle clear positives, clear negatives and `null_structural`, and to do badly on the four hard `null` sub-classes, which turn on compositional scope that a single pooled vector blurs. That is the predicted result rather than a fault, and it is what makes Arm B necessary: a weak probe cannot distinguish "the libraries are the bottleneck" from "the method is too weak".

Decision-rule margins selected per fold (on each fold's own validation split): 0.0, 0.05.

*Confusion matrix, raw argmax*

|  | pred false | pred true | pred null | total |
|---|---|---|---|---|
| **truth false** | 1595 | 156 | 728 | 2479 |
| **truth true** | 148 | 823 | 510 | 1481 |
| **truth null** | 285 | 257 | 5498 | 6040 |
| **total** | 2028 | 1236 | 6736 | 10000 |

`null -> true`: 257 of 6040 truly-null examples (4.25%).

*Confusion matrix, after the decision rule*

|  | pred false | pred true | pred null | total |
|---|---|---|---|---|
| **truth false** | 1596 | 155 | 728 | 2479 |
| **truth true** | 149 | 817 | 515 | 1481 |
| **truth null** | 287 | 251 | 5502 | 6040 |
| **total** | 2032 | 1223 | 6745 | 10000 |

`null -> true`: 251 of 6040 truly-null examples (4.16%).

### Per class, after the decision rule

| class | support | predicted | precision | recall | F1 |
|---|---|---|---|---|---|
| `false` | 2479 | 2032 | 78.5% | 64.4% | 70.8% |
| `true` | 1481 | 1223 | 66.8% | 55.2% | 60.4% |
| `null` | 6040 | 6745 | 81.6% | 91.1% | 86.1% |

### By label mode

| label mode | n | eff n | accuracy [95% CI] |
|---|---|---|---|
| false | 2479 | **54** | 64.4% [56.0%, 72.7%] |
| null_ambiguous | 3062 | **243** | 82.6% [79.2%, 85.7%] |
| null_structural | 2978 | **1** | 99.8% [99.8%, 99.8%] |
| true | 1481 | **54** | 55.2% [45.6%, 66.0%] |

### By null sub-class

| sub-class | n | eff n | null recall [95% CI] |
|---|---|---|---|
| attribution | 655 | **51** | 73.3% [65.1%, 80.7%] |
| hedged | 592 | **47** | 88.7% [83.5%, 92.9%] |
| historical | 554 | **46** | 89.2% [83.0%, 94.2%] |
| metaphor | 682 | **52** | 80.2% [71.9%, 88.1%] |
| third_party | 579 | **47** | 83.4% [75.6%, 90.8%] |

### By fragment library

| library | n | eff n | accuracy [95% CI] |
|---|---|---|---|
| nocturia_false | 2479 | **54** | 64.4% [56.0%, 72.7%] |
| nocturia_null_attribution | 655 | **51** | 73.3% [65.1%, 80.7%] |
| nocturia_null_hedged | 592 | **47** | 88.7% [83.5%, 92.9%] |
| nocturia_null_historical | 554 | **46** | 89.2% [83.0%, 94.2%] |
| nocturia_null_metaphor | 682 | **52** | 80.2% [71.9%, 88.1%] |
| nocturia_null_thirdparty | 579 | **47** | 83.4% [75.6%, 90.8%] |
| nocturia_true | 1481 | **54** | 55.2% [45.6%, 66.0%] |
| (none) | 2978 | **1** | 99.8% [99.8%, 99.8%] |

### Per-fragment errors (worst first)

Whether errors are spread thinly across many fragments or piled onto a few is the difference
between "the method is too weak" (model work) and "these specific ideas are not learnable from
the data we have" (library work, and these are the fragments to write more of). No intervals:
a fragment is one cluster, so an interval over its own examples measures nothing.

231 of 351 decisive fragments were got wrong at least once.

`arm_a_probe`: 2080 errors across 231 of 351 decisive fragments. Half of them fall on **33** fragments (an even spread would be 115.5); the worst ten carry 21.3% of all errors.

| fragment | library | sub-class | truth | correct | accuracy | predicted as |
|---|---|---|---|---|---|---|
| `nocturia_false:1bd2f6f8` | `nocturia_false` | -- | false | 0/49 | 0.0% | null 49 |
| `nocturia_true:86e1cd53` | `nocturia_true` | -- | true | 0/48 | 0.0% | false 7, null 41 |
| `nocturia_true:0740576d` | `nocturia_true` | -- | true | 0/40 | 0.0% | false 9, null 31 |
| `nocturia_true:f81d11be` | `nocturia_true` | -- | true | 0/19 | 0.0% | false 1, null 18 |
| `nocturia_null_attribution:0dfc44e6` | `nocturia_null_attribution` | attribution | null | 0/16 | 0.0% | false 3, true 13 |
| `nocturia_null_metaphor:c666d342` | `nocturia_null_metaphor` | metaphor | null | 0/12 | 0.0% | true 12 |
| `nocturia_null_metaphor:a88b521b` | `nocturia_null_metaphor` | metaphor | null | 0/11 | 0.0% | false 11 |
| `nocturia_false:98d02ead` | `nocturia_false` | -- | false | 1/48 | 2.1% | false 1, null 47 |
| `nocturia_false:deb3785c` | `nocturia_false` | -- | false | 1/38 | 2.6% | false 1, null 37 |
| `nocturia_true:4a4f4b70` | `nocturia_true` | -- | true | 1/34 | 2.9% | false 17, true 1, null 16 |
| `nocturia_false:5efba823` | `nocturia_false` | -- | false | 1/30 | 3.3% | false 1, null 29 |
| `nocturia_false:14ecd3b3` | `nocturia_false` | -- | false | 1/28 | 3.6% | false 1, true 25, null 2 |
| `nocturia_true:e853d9c0` | `nocturia_true` | -- | true | 1/28 | 3.6% | true 1, null 27 |
| `nocturia_false:72f0059f` | `nocturia_false` | -- | false | 2/30 | 6.7% | false 2, true 4, null 24 |
| `nocturia_null_thirdparty:776f85a8` | `nocturia_null_thirdparty` | third_party | null | 1/15 | 6.7% | true 14, null 1 |
| `nocturia_null_historical:0e6d519c` | `nocturia_null_historical` | historical | null | 1/13 | 7.7% | false 3, true 9, null 1 |
| `nocturia_null_metaphor:ebf3eba2` | `nocturia_null_metaphor` | metaphor | null | 1/13 | 7.7% | false 12, null 1 |
| `nocturia_true:efa44ced` | `nocturia_true` | -- | true | 2/25 | 8.0% | false 3, true 2, null 20 |
| `nocturia_true:3904c08b` | `nocturia_true` | -- | true | 2/21 | 9.5% | true 2, null 19 |
| `nocturia_false:bf88ba0d` | `nocturia_false` | -- | false | 6/47 | 12.8% | false 6, null 41 |
| `nocturia_true:c3f73311` | `nocturia_true` | -- | true | 7/50 | 14.0% | false 5, true 7, null 38 |
| `nocturia_null_thirdparty:3f34a4a7` | `nocturia_null_thirdparty` | third_party | null | 2/13 | 15.4% | false 4, true 7, null 2 |
| `nocturia_true:8bdf6dc7` | `nocturia_true` | -- | true | 4/23 | 17.4% | false 8, true 4, null 11 |
| `nocturia_true:126e0cfb` | `nocturia_true` | -- | true | 6/32 | 18.8% | false 7, true 6, null 19 |
| `nocturia_null_attribution:7fc5b7ab` | `nocturia_null_attribution` | attribution | null | 4/21 | 19.0% | false 1, true 16, null 4 |
| `nocturia_false:99cd439f` | `nocturia_false` | -- | false | 9/45 | 20.0% | false 9, null 36 |
| `nocturia_null_attribution:e51cceef` | `nocturia_null_attribution` | attribution | null | 3/15 | 20.0% | false 7, true 5, null 3 |
| `nocturia_true:594869e7` | `nocturia_true` | -- | true | 9/44 | 20.5% | false 4, true 9, null 31 |
| `nocturia_false:21180255` | `nocturia_false` | -- | false | 12/54 | 22.2% | false 12, null 42 |
| `nocturia_true:4506c1ce` | `nocturia_true` | -- | true | 6/26 | 23.1% | true 6, null 20 |
| `nocturia_null_attribution:57d09418` | `nocturia_null_attribution` | attribution | null | 4/17 | 23.5% | true 13, null 4 |
| `nocturia_null_metaphor:4d2cab75` | `nocturia_null_metaphor` | metaphor | null | 5/21 | 23.8% | false 16, null 5 |
| `nocturia_true:23c9421e` | `nocturia_true` | -- | true | 8/33 | 24.2% | false 7, true 8, null 18 |
| `nocturia_null_historical:a2c3c56b` | `nocturia_null_historical` | historical | null | 3/12 | 25.0% | false 9, null 3 |
| `nocturia_true:a2f6ab3f` | `nocturia_true` | -- | true | 8/31 | 25.8% | false 1, true 8, null 22 |
| `nocturia_false:876119ca` | `nocturia_false` | -- | false | 16/60 | 26.7% | false 16, true 41, null 3 |
| `nocturia_false:e4441873` | `nocturia_false` | -- | false | 9/33 | 27.3% | false 9, null 24 |
| `nocturia_true:2cbd088f` | `nocturia_true` | -- | true | 9/33 | 27.3% | false 14, true 9, null 10 |
| `nocturia_null_hedged:0d36ef4c` | `nocturia_null_hedged` | hedged | null | 3/11 | 27.3% | false 8, null 3 |
| `nocturia_false:5e819a32` | `nocturia_false` | -- | false | 13/46 | 28.3% | false 13, null 33 |

*191 further fragments with at least one error are in the JSON sidecar; every fragment is there regardless of score.*

## `arm_b_finetune`

`roberta-base` with **every layer unfrozen**, mean-pooled, with the same `Linear(768, 3)` head -- 110M trainable parameters against Arm A's 2,307. Three epochs at batch 32, learning rate 2e-5, 10% linear warmup, AdamW, fp32. No gradient checkpointing, no 8-bit optimiser, no LoRA, no gradient accumulation: the full model fits in 12GB with room to spare, so anything that reads like a compute compromise would be a mistake rather than a saving. This is the arm that separates "the fragment libraries are the bottleneck" from "the method is too weak": if a fully fine-tuned encoder still cannot read third-party attribution, tense or metaphor, the limit is in the ideas the libraries contain and the fix is library work, not model work.

Decision-rule margins selected per fold (on each fold's own validation split): 0.0, 0.05, 0.1, 0.15, 0.85.

*Confusion matrix, raw argmax*

|  | pred false | pred true | pred null | total |
|---|---|---|---|---|
| **truth false** | 2041 | 105 | 333 | 2479 |
| **truth true** | 9 | 1069 | 403 | 1481 |
| **truth null** | 99 | 256 | 5685 | 6040 |
| **total** | 2149 | 1430 | 6421 | 10000 |

`null -> true`: 256 of 6040 truly-null examples (4.24%).

*Confusion matrix, after the decision rule*

|  | pred false | pred true | pred null | total |
|---|---|---|---|---|
| **truth false** | 2043 | 101 | 335 | 2479 |
| **truth true** | 9 | 1053 | 419 | 1481 |
| **truth null** | 102 | 244 | 5694 | 6040 |
| **total** | 2154 | 1398 | 6448 | 10000 |

`null -> true`: 244 of 6040 truly-null examples (4.04%).

### Per class, after the decision rule

| class | support | predicted | precision | recall | F1 |
|---|---|---|---|---|---|
| `false` | 2479 | 2154 | 94.8% | 82.4% | 88.2% |
| `true` | 1481 | 1398 | 75.3% | 71.1% | 73.2% |
| `null` | 6040 | 6448 | 88.3% | 94.3% | 91.2% |

### By label mode

| label mode | n | eff n | accuracy [95% CI] |
|---|---|---|---|
| false | 2479 | **54** | 82.4% [73.2%, 90.9%] |
| null_ambiguous | 3062 | **243** | 89.2% [85.5%, 92.6%] |
| null_structural | 2978 | **1** | 99.5% [99.5%, 99.5%] |
| true | 1481 | **54** | 71.1% [59.4%, 81.9%] |

### By null sub-class

| sub-class | n | eff n | null recall [95% CI] |
|---|---|---|---|
| attribution | 655 | **51** | 88.2% [79.1%, 95.7%] |
| hedged | 592 | **47** | 80.9% [70.1%, 90.6%] |
| historical | 554 | **46** | 92.1% [84.2%, 98.1%] |
| metaphor | 682 | **52** | 91.6% [84.4%, 97.8%] |
| third_party | 579 | **47** | 93.3% [85.2%, 99.4%] |

### By fragment library

| library | n | eff n | accuracy [95% CI] |
|---|---|---|---|
| nocturia_false | 2479 | **54** | 82.4% [73.2%, 90.9%] |
| nocturia_null_attribution | 655 | **51** | 88.2% [79.1%, 95.7%] |
| nocturia_null_hedged | 592 | **47** | 80.9% [70.1%, 90.6%] |
| nocturia_null_historical | 554 | **46** | 92.1% [84.2%, 98.1%] |
| nocturia_null_metaphor | 682 | **52** | 91.6% [84.4%, 97.8%] |
| nocturia_null_thirdparty | 579 | **47** | 93.3% [85.2%, 99.4%] |
| nocturia_true | 1481 | **54** | 71.1% [59.4%, 81.9%] |
| (none) | 2978 | **1** | 99.5% [99.5%, 99.5%] |

### Per-fragment errors (worst first)

Whether errors are spread thinly across many fragments or piled onto a few is the difference
between "the method is too weak" (model work) and "these specific ideas are not learnable from
the data we have" (library work, and these are the fragments to write more of). No intervals:
a fragment is one cluster, so an interval over its own examples measures nothing.

86 of 351 decisive fragments were got wrong at least once.

`arm_b_finetune`: 1194 errors across 86 of 351 decisive fragments. Half of them fall on **17** fragments (an even spread would be 43.0); the worst ten carry 33.9% of all errors.

| fragment | library | sub-class | truth | correct | accuracy | predicted as |
|---|---|---|---|---|---|---|
| `nocturia_false:3aab37fe` | `nocturia_false` | -- | false | 0/51 | 0.0% | null 51 |
| `nocturia_false:1bd2f6f8` | `nocturia_false` | -- | false | 0/49 | 0.0% | null 49 |
| `nocturia_true:86e1cd53` | `nocturia_true` | -- | true | 0/48 | 0.0% | null 48 |
| `nocturia_true:0740576d` | `nocturia_true` | -- | true | 0/40 | 0.0% | false 2, null 38 |
| `nocturia_false:deb3785c` | `nocturia_false` | -- | false | 0/38 | 0.0% | null 38 |
| `nocturia_true:86863ee3` | `nocturia_true` | -- | true | 0/34 | 0.0% | null 34 |
| `nocturia_true:f3e4ee3e` | `nocturia_true` | -- | true | 0/34 | 0.0% | null 34 |
| `nocturia_true:126e0cfb` | `nocturia_true` | -- | true | 0/32 | 0.0% | null 32 |
| `nocturia_false:5efba823` | `nocturia_false` | -- | false | 0/30 | 0.0% | null 30 |
| `nocturia_false:bc25d693` | `nocturia_false` | -- | false | 0/29 | 0.0% | true 29 |
| `nocturia_true:e853d9c0` | `nocturia_true` | -- | true | 0/28 | 0.0% | null 28 |
| `nocturia_true:4506c1ce` | `nocturia_true` | -- | true | 0/26 | 0.0% | null 26 |
| `nocturia_null_attribution:7fc5b7ab` | `nocturia_null_attribution` | attribution | null | 0/21 | 0.0% | true 21 |
| `nocturia_null_thirdparty:49d8e5c9` | `nocturia_null_thirdparty` | third_party | null | 0/18 | 0.0% | true 18 |
| `nocturia_null_hedged:b85fb3a3` | `nocturia_null_hedged` | hedged | null | 0/16 | 0.0% | true 16 |
| `nocturia_null_attribution:e51cceef` | `nocturia_null_attribution` | attribution | null | 0/15 | 0.0% | true 15 |
| `nocturia_null_hedged:01c072bf` | `nocturia_null_hedged` | hedged | null | 0/15 | 0.0% | false 15 |
| `nocturia_null_thirdparty:776f85a8` | `nocturia_null_thirdparty` | third_party | null | 0/15 | 0.0% | false 15 |
| `nocturia_true:1e05f648` | `nocturia_true` | -- | true | 0/15 | 0.0% | false 1, null 14 |
| `nocturia_null_attribution:9017e283` | `nocturia_null_attribution` | attribution | null | 0/13 | 0.0% | true 13 |
| `nocturia_null_historical:0e6d519c` | `nocturia_null_historical` | historical | null | 0/13 | 0.0% | true 13 |
| `nocturia_null_metaphor:03b3b8c4` | `nocturia_null_metaphor` | metaphor | null | 0/13 | 0.0% | false 13 |
| `nocturia_null_attribution:6a302d90` | `nocturia_null_attribution` | attribution | null | 0/12 | 0.0% | false 2, true 10 |
| `nocturia_null_historical:bdf2082b` | `nocturia_null_historical` | historical | null | 0/12 | 0.0% | true 12 |
| `nocturia_null_metaphor:c666d342` | `nocturia_null_metaphor` | metaphor | null | 0/12 | 0.0% | true 12 |
| `nocturia_null_hedged:31bc996d` | `nocturia_null_hedged` | hedged | null | 0/11 | 0.0% | true 11 |
| `nocturia_null_metaphor:a88b521b` | `nocturia_null_metaphor` | metaphor | null | 0/11 | 0.0% | false 11 |
| `nocturia_null_hedged:20ad42fe` | `nocturia_null_hedged` | hedged | null | 0/9 | 0.0% | true 9 |
| `nocturia_null_hedged:841744b2` | `nocturia_null_hedged` | hedged | null | 0/9 | 0.0% | false 4, true 5 |
| `nocturia_false:14ecd3b3` | `nocturia_false` | -- | false | 1/28 | 3.6% | false 1, true 27 |
| `nocturia_true:efa44ced` | `nocturia_true` | -- | true | 1/25 | 4.0% | true 1, null 24 |
| `nocturia_true:31923f27` | `nocturia_true` | -- | true | 1/17 | 5.9% | true 1, null 16 |
| `nocturia_false:1cb7de3b` | `nocturia_false` | -- | false | 3/43 | 7.0% | false 3, null 40 |
| `nocturia_false:2e5a7e5a` | `nocturia_false` | -- | false | 3/41 | 7.3% | false 3, true 24, null 14 |
| `nocturia_null_hedged:8dad6abb` | `nocturia_null_hedged` | hedged | null | 1/11 | 9.1% | false 10, null 1 |
| `nocturia_null_hedged:58ffb85e` | `nocturia_null_hedged` | hedged | null | 1/8 | 12.5% | true 7, null 1 |
| `nocturia_true:a2f6ab3f` | `nocturia_true` | -- | true | 5/31 | 16.1% | true 5, null 26 |
| `nocturia_null_hedged:55035966` | `nocturia_null_hedged` | hedged | null | 3/16 | 18.8% | true 13, null 3 |
| `nocturia_true:4dc9876b` | `nocturia_true` | -- | true | 3/15 | 20.0% | true 3, null 12 |
| `nocturia_true:f2891c69` | `nocturia_true` | -- | true | 7/30 | 23.3% | true 7, null 23 |

*46 further fragments with at least one error are in the JSON sidecar; every fragment is there regardless of score.*

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
| false | 2479 | **54** | 0.0% [0.0%, 0.0%] |
| null_ambiguous | 3062 | **243** | 100.0% [100.0%, 100.0%] |
| null_structural | 2978 | **1** | 100.0% [100.0%, 100.0%] |
| true | 1481 | **54** | 0.0% [0.0%, 0.0%] |

### By null sub-class

| sub-class | n | eff n | null recall [95% CI] |
|---|---|---|---|
| attribution | 655 | **51** | 100.0% [100.0%, 100.0%] |
| hedged | 592 | **47** | 100.0% [100.0%, 100.0%] |
| historical | 554 | **46** | 100.0% [100.0%, 100.0%] |
| metaphor | 682 | **52** | 100.0% [100.0%, 100.0%] |
| third_party | 579 | **47** | 100.0% [100.0%, 100.0%] |

### By fragment library

| library | n | eff n | accuracy [95% CI] |
|---|---|---|---|
| nocturia_false | 2479 | **54** | 0.0% [0.0%, 0.0%] |
| nocturia_null_attribution | 655 | **51** | 100.0% [100.0%, 100.0%] |
| nocturia_null_hedged | 592 | **47** | 100.0% [100.0%, 100.0%] |
| nocturia_null_historical | 554 | **46** | 100.0% [100.0%, 100.0%] |
| nocturia_null_metaphor | 682 | **52** | 100.0% [100.0%, 100.0%] |
| nocturia_null_thirdparty | 579 | **47** | 100.0% [100.0%, 100.0%] |
| nocturia_true | 1481 | **54** | 0.0% [0.0%, 0.0%] |
| (none) | 2978 | **1** | 100.0% [100.0%, 100.0%] |

### Per-fragment errors (worst first)

Whether errors are spread thinly across many fragments or piled onto a few is the difference
between "the method is too weak" (model work) and "these specific ideas are not learnable from
the data we have" (library work, and these are the fragments to write more of). No intervals:
a fragment is one cluster, so an interval over its own examples measures nothing.

108 of 351 decisive fragments were got wrong at least once.

`arm_b_finetune__shuffled`: 3960 errors across 108 of 351 decisive fragments. Half of them fall on **38** fragments (an even spread would be 54.0); the worst ten carry 15.8% of all errors.

| fragment | library | sub-class | truth | correct | accuracy | predicted as |
|---|---|---|---|---|---|---|
| `nocturia_false:75848908` | `nocturia_false` | -- | false | 0/74 | 0.0% | null 74 |
| `nocturia_false:3e89d247` | `nocturia_false` | -- | false | 0/68 | 0.0% | null 68 |
| `nocturia_false:0105f271` | `nocturia_false` | -- | false | 0/67 | 0.0% | null 67 |
| `nocturia_false:3a70bcb2` | `nocturia_false` | -- | false | 0/63 | 0.0% | null 63 |
| `nocturia_false:e6fd6a44` | `nocturia_false` | -- | false | 0/61 | 0.0% | null 61 |
| `nocturia_false:776d32bb` | `nocturia_false` | -- | false | 0/60 | 0.0% | null 60 |
| `nocturia_false:876119ca` | `nocturia_false` | -- | false | 0/60 | 0.0% | null 60 |
| `nocturia_false:79441d6a` | `nocturia_false` | -- | false | 0/59 | 0.0% | null 59 |
| `nocturia_false:76105311` | `nocturia_false` | -- | false | 0/57 | 0.0% | null 57 |
| `nocturia_false:01f605e7` | `nocturia_false` | -- | false | 0/55 | 0.0% | null 55 |
| `nocturia_false:3fbd0758` | `nocturia_false` | -- | false | 0/55 | 0.0% | null 55 |
| `nocturia_false:cd9ee762` | `nocturia_false` | -- | false | 0/55 | 0.0% | null 55 |
| `nocturia_false:21180255` | `nocturia_false` | -- | false | 0/54 | 0.0% | null 54 |
| `nocturia_false:31c155d0` | `nocturia_false` | -- | false | 0/54 | 0.0% | null 54 |
| `nocturia_false:a9489bdd` | `nocturia_false` | -- | false | 0/54 | 0.0% | null 54 |
| `nocturia_false:cddf064c` | `nocturia_false` | -- | false | 0/53 | 0.0% | null 53 |
| `nocturia_false:48f35b91` | `nocturia_false` | -- | false | 0/52 | 0.0% | null 52 |
| `nocturia_false:3aab37fe` | `nocturia_false` | -- | false | 0/51 | 0.0% | null 51 |
| `nocturia_false:a9555a97` | `nocturia_false` | -- | false | 0/51 | 0.0% | null 51 |
| `nocturia_false:59e83d34` | `nocturia_false` | -- | false | 0/50 | 0.0% | null 50 |
| `nocturia_true:c3f73311` | `nocturia_true` | -- | true | 0/50 | 0.0% | null 50 |
| `nocturia_false:1bd2f6f8` | `nocturia_false` | -- | false | 0/49 | 0.0% | null 49 |
| `nocturia_false:55832b2b` | `nocturia_false` | -- | false | 0/49 | 0.0% | null 49 |
| `nocturia_false:b11139a0` | `nocturia_false` | -- | false | 0/49 | 0.0% | null 49 |
| `nocturia_false:98d02ead` | `nocturia_false` | -- | false | 0/48 | 0.0% | null 48 |
| `nocturia_true:86e1cd53` | `nocturia_true` | -- | true | 0/48 | 0.0% | null 48 |
| `nocturia_false:bf88ba0d` | `nocturia_false` | -- | false | 0/47 | 0.0% | null 47 |
| `nocturia_false:eff52ced` | `nocturia_false` | -- | false | 0/47 | 0.0% | null 47 |
| `nocturia_false:5e819a32` | `nocturia_false` | -- | false | 0/46 | 0.0% | null 46 |
| `nocturia_false:b1f7e93f` | `nocturia_false` | -- | false | 0/46 | 0.0% | null 46 |
| `nocturia_false:c6a4c61b` | `nocturia_false` | -- | false | 0/46 | 0.0% | null 46 |
| `nocturia_false:99cd439f` | `nocturia_false` | -- | false | 0/45 | 0.0% | null 45 |
| `nocturia_false:dfdc943b` | `nocturia_false` | -- | false | 0/45 | 0.0% | null 45 |
| `nocturia_true:594869e7` | `nocturia_true` | -- | true | 0/44 | 0.0% | null 44 |
| `nocturia_false:1a41970c` | `nocturia_false` | -- | false | 0/43 | 0.0% | null 43 |
| `nocturia_false:1cb7de3b` | `nocturia_false` | -- | false | 0/43 | 0.0% | null 43 |
| `nocturia_false:4a12f37a` | `nocturia_false` | -- | false | 0/43 | 0.0% | null 43 |
| `nocturia_false:f4140180` | `nocturia_false` | -- | false | 0/43 | 0.0% | null 43 |
| `nocturia_false:08a0b22d` | `nocturia_false` | -- | false | 0/41 | 0.0% | null 41 |
| `nocturia_false:2e5a7e5a` | `nocturia_false` | -- | false | 0/41 | 0.0% | null 41 |

*68 further fragments with at least one error are in the JSON sidecar; every fragment is there regardless of score.*

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
| 0 | 10000 | 2000 | 2000 | 0.0 | 74.5% | 74.5% | 61.1% | 0.50% |
| 1 | 10000 | 2000 | 2000 | 0.0 | 73.7% | 73.7% | 63.7% | 1.83% |
| 2 | 10000 | 2000 | 2000 | 0.2 | 77.0% | 76.3% | 64.1% | 2.57% |
| 3 | 10000 | 2000 | 2000 | 0.05 | 71.4% | 71.6% | 55.0% | 0.91% |
| 4 | 10000 | 2000 | 2000 | 0.0 | 80.5% | 80.5% | 74.0% | 4.81% |

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

### `arm_a_probe`

| fold | train n | val n | test n | margin | acc (raw) | acc (ruled) | macro-F1 | null->true |
|---|---|---|---|---|---|---|---|---|
| 0 | 10000 | 2000 | 2000 | 0.0 | 78.5% | 78.5% | 71.1% | 2.07% |
| 1 | 10000 | 2000 | 2000 | 0.0 | 80.8% | 80.8% | 75.3% | 4.24% |
| 2 | 10000 | 2000 | 2000 | 0.05 | 77.2% | 77.1% | 69.1% | 5.38% |
| 3 | 10000 | 2000 | 2000 | 0.0 | 79.8% | 79.8% | 72.0% | 2.88% |
| 4 | 10000 | 2000 | 2000 | 0.0 | 79.4% | 79.4% | 73.7% | 6.22% |

### `arm_b_finetune`

| fold | train n | val n | test n | margin | acc (raw) | acc (ruled) | macro-F1 | null->true |
|---|---|---|---|---|---|---|---|---|
| 0 | 10000 | 2000 | 2000 | 0.05 | 84.5% | 84.5% | 81.2% | 3.31% |
| 1 | 10000 | 2000 | 2000 | 0.15 | 86.9% | 87.1% | 83.1% | 5.66% |
| 2 | 10000 | 2000 | 2000 | 0.85 | 85.9% | 85.4% | 78.3% | 3.73% |
| 3 | 10000 | 2000 | 2000 | 0.0 | 92.0% | 92.0% | 87.2% | 2.14% |
| 4 | 10000 | 2000 | 2000 | 0.1 | 90.5% | 90.6% | 87.9% | 5.39% |

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

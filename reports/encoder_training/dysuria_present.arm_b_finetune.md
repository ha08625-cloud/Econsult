# Encoder training: evaluation report

*Generated 2026-08-16T09:07:34+00:00.*

|  |  |
|---|---|
| signal | `dysuria_present` |
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
| artefacts | `models/encoder/dysuria_present/arm_b_finetune` |
| weights | `models/encoder/dysuria_present/arm_b_finetune/weights -- ~440MB per fold, not committed` |
| model revision | `e2da8e2f811d1448a5b465c236feacd80ffbac7b` |
| revision pinned | `False` |
| tokeniser lowercases | `False` |
| tokeniser vocab size | `50265` |
| tokeniser discards casing | `False` |
| cluster tag coverage | `4 of 6 libraries carry cluster markers; 92 of 256 fragments are in libraries with none` |
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

> **Warning: 2 of the 6 libraries behind this run carry no cluster markers at all, so every line in them counts as an independent idea.** Where that is not true -- where several lines are one idea written several ways -- the `eff n` of every slice drawn from those libraries is an **upper bound**, and the confidence intervals below are correspondingly **narrower than the truth**.
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
| `majority_class` | baseline | 7022 | **182** | 43.6% [36.5%, 51.4%] | 20.2% [17.8%, 22.6%] | 60.4% | 60.4% +/- 0.2% |
| `length_only` | baseline | 7022 | **182** | 46.9% [40.0%, 54.1%] | 26.8% [23.8%, 29.7%] | 62.0% | 62.0% +/- 0.8% |
| `tfidf_logreg` | baseline | 7022 | **182** | 70.5% [64.9%, 76.0%] | 63.5% [57.8%, 68.7%] | 79.3% | 79.3% +/- 1.9% |
| `length_only__shuffled` | negative control | 7022 | **182** | 43.6% [36.5%, 51.4%] | 20.2% [17.8%, 22.6%] | 60.4% | 60.4% +/- 0.2% |
| `tfidf_logreg__shuffled` | negative control | 7022 | **182** | 43.6% [36.5%, 51.4%] | 20.3% [17.8%, 22.6%] | 60.4% | 60.4% +/- 0.2% |
| `arm_a_probe` | probe | 7022 | **182** | 82.4% [78.9%, 85.8%] | 81.0% [77.2%, 84.4%] | 87.2% | 87.2% +/- 4.5% |
| `arm_b_finetune` | finetune | 7022 | **182** | 94.9% [92.2%, 97.3%] | 94.3% [91.2%, 96.9%] | 96.4% | 96.4% +/- 1.6% |
| `arm_b_finetune__shuffled` | negative control | 7022 | **182** | 43.6% [36.5%, 51.4%] | 20.2% [17.8%, 22.6%] | 60.4% | 60.4% +/- 0.2% |

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
| `length_only` | -- | -- | 100.0% [100.0%, 100.0%] (eff n 20) | 98.2% [94.8%, 100.0%] (eff n 19) | 98.8% [97.6%, 99.7%] (eff n 28) | 99.3% [98.5%, 99.9%] (eff n 23) |
| `tfidf_logreg` | -- | -- | 84.7% [75.2%, 93.7%] (eff n 20) | 99.7% [99.2%, 100.0%] (eff n 19) | 99.7% [99.4%, 100.0%] (eff n 28) | 95.1% [89.5%, 99.6%] (eff n 23) |
| `length_only__shuffled` | -- | -- | 100.0% [100.0%, 100.0%] (eff n 20) | 100.0% [100.0%, 100.0%] (eff n 19) | 100.0% [100.0%, 100.0%] (eff n 28) | 100.0% [100.0%, 100.0%] (eff n 23) |
| `tfidf_logreg__shuffled` | -- | -- | 99.9% [99.6%, 100.0%] (eff n 20) | 99.8% [99.5%, 100.0%] (eff n 19) | 100.0% [100.0%, 100.0%] (eff n 28) | 100.0% [100.0%, 100.0%] (eff n 23) |
| `arm_a_probe` | -- | -- | 82.8% [76.7%, 89.5%] (eff n 20) | 95.6% [92.8%, 98.0%] (eff n 19) | 92.3% [85.3%, 98.6%] (eff n 28) | 90.6% [84.8%, 95.5%] (eff n 23) |
| `arm_b_finetune` | -- | -- | 84.5% [74.4%, 94.7%] (eff n 20) | 99.7% [99.0%, 100.0%] (eff n 19) | 91.8% [80.4%, 100.0%] (eff n 28) | 96.4% [89.5%, 100.0%] (eff n 23) |
| `arm_b_finetune__shuffled` | -- | -- | 100.0% [100.0%, 100.0%] (eff n 20) | 100.0% [100.0%, 100.0%] (eff n 19) | 100.0% [100.0%, 100.0%] (eff n 28) | 100.0% [100.0%, 100.0%] (eff n 23) |

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
| `length_only` | baseline | 3062 | **90** | 99.1% [98.2%, 99.7%] |
| `tfidf_logreg` | baseline | 3062 | **90** | 94.6% [91.2%, 97.4%] |
| `arm_a_probe` | probe | 3062 | **90** | 90.1% [86.8%, 93.3%] |
| `arm_b_finetune` | finetune | 3062 | **90** | 92.9% [88.0%, 96.9%] |

### 2. The same comparison, paired

Two overlapping intervals do not settle whether one model beats another on the same
examples. McNemar does, over the examples the two disagree about -- read it alongside the
intervals above, never instead of them.

| pair | n | a only | b only | p |
|---|---|---|---|---|
| `majority_class` vs `length_only` | 3062 | 27 | 0 | 1.49e-08 |
| `majority_class` vs `tfidf_logreg` | 3062 | 166 | 0 | 2.14e-50 |
| `majority_class` vs `arm_a_probe` | 3062 | 303 | 0 | 1.23e-91 |
| `majority_class` vs `arm_b_finetune` | 3062 | 227 | 0 | 9.27e-69 |
| `length_only` vs `tfidf_logreg` | 3062 | 166 | 27 | 1.33e-25 |
| `length_only` vs `arm_a_probe` | 3062 | 297 | 21 | 1.43e-63 |
| `length_only` vs `arm_b_finetune` | 3062 | 227 | 27 | 1.46e-40 |
| `tfidf_logreg` vs `arm_a_probe` | 3062 | 238 | 101 | 6.89e-14 |
| `tfidf_logreg` vs `arm_b_finetune` | 3062 | 141 | 80 | 4.91e-05 |
| `arm_a_probe` vs `arm_b_finetune` | 3062 | 126 | 202 | 3.2e-05 |

### 3. Where the errors fall

The per-fragment table below, as one number per model. Errors spread thinly across many
fragments say the method is too weak. Errors piled onto a handful say those specific ideas
are not learnable from the data we have -- and the table names them, which is what makes
this the most decision-useful thing in the report.

* `majority_class`: 3960 errors across 92 of 256 decisive fragments. Half of them fall on **35** fragments (an even spread would be 46.0); the worst ten carry 16.5% of all errors.
* `length_only`: 3731 errors across 105 of 256 decisive fragments. Half of them fall on **36** fragments (an even spread would be 52.5); the worst ten carry 16.0% of all errors.
* `tfidf_logreg`: 2069 errors across 104 of 256 decisive fragments. Half of them fall on **26** fragments (an even spread would be 52.0); the worst ten carry 24.5% of all errors.
* `arm_a_probe`: 1235 errors across 146 of 256 decisive fragments. Half of them fall on **24** fragments (an even spread would be 73.0); the worst ten carry 28.3% of all errors.
* `arm_b_finetune`: 358 errors across 28 of 256 decisive fragments. Half of them fall on **6** fragments (an even spread would be 14.0); the worst ten carry 76.8% of all errors.

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
| `length_only__shuffled` | 60.4% [38.1%, 77.2%] | 25.1% [18.4%, 29.1%] |
| `tfidf_logreg__shuffled` | 60.4% [38.1%, 77.2%] | 25.1% [18.4%, 29.1%] |
| `arm_b_finetune__shuffled` | 60.4% [38.1%, 77.2%] | 25.1% [18.4%, 29.1%] |

## Paired comparisons (McNemar, raw argmax)

Exact two-sided McNemar over the examples the two models disagree about. Pairing unit is the
example, not the cluster -- see the limitations.

| pair | slice | n | a only | b only | p |
|---|---|---|---|---|---|
| `majority_class` vs `length_only` | overall | 10000 | 95 | 256 | 3.37e-18 |
| `majority_class` vs `length_only` | null_ambiguous | 3062 | 27 | 0 | 1.49e-08 |
| `majority_class` vs `tfidf_logreg` | overall | 10000 | 171 | 2057 | 0 |
| `majority_class` vs `tfidf_logreg` | null_ambiguous | 3062 | 166 | 0 | 2.14e-50 |
| `majority_class` vs `arm_a_probe` | overall | 10000 | 348 | 3033 | 0 |
| `majority_class` vs `arm_a_probe` | null_ambiguous | 3062 | 303 | 0 | 1.23e-91 |
| `majority_class` vs `arm_b_finetune` | overall | 10000 | 231 | 3828 | 0 |
| `majority_class` vs `arm_b_finetune` | null_ambiguous | 3062 | 227 | 0 | 9.27e-69 |
| `length_only` vs `tfidf_logreg` | overall | 10000 | 218 | 1943 | 0 |
| `length_only` vs `tfidf_logreg` | null_ambiguous | 3062 | 166 | 27 | 1.33e-25 |
| `length_only` vs `arm_a_probe` | overall | 10000 | 349 | 2873 | 0 |
| `length_only` vs `arm_a_probe` | null_ambiguous | 3062 | 297 | 21 | 1.43e-63 |
| `length_only` vs `arm_b_finetune` | overall | 10000 | 236 | 3672 | 0 |
| `length_only` vs `arm_b_finetune` | null_ambiguous | 3062 | 227 | 27 | 1.46e-40 |
| `tfidf_logreg` vs `arm_a_probe` | overall | 10000 | 428 | 1227 | 2.97e-89 |
| `tfidf_logreg` vs `arm_a_probe` | null_ambiguous | 3062 | 238 | 101 | 6.89e-14 |
| `tfidf_logreg` vs `arm_b_finetune` | overall | 10000 | 156 | 1867 | 0 |
| `tfidf_logreg` vs `arm_b_finetune` | null_ambiguous | 3062 | 141 | 80 | 4.91e-05 |
| `arm_a_probe` vs `arm_b_finetune` | overall | 10000 | 171 | 1083 | 2.09e-162 |
| `arm_a_probe` vs `arm_b_finetune` | null_ambiguous | 3062 | 126 | 202 | 3.2e-05 |

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
| `dysuria_false` | 2479 | 0.0% | 10.3% | 67.2% | 82.2% | 98.5% | 98.5pp |
| `dysuria_true` | 1481 | 0.0% | 0.0% | 26.4% | 66.8% | 93.0% | 93.0pp |
| `dysuria_null_hedged` | 785 | 100.0% | 100.0% | 84.7% | 82.8% | 84.5% | 17.2pp |
| `dysuria_null_thirdparty` | 865 | 100.0% | 99.3% | 95.1% | 90.6% | 96.4% | 9.4pp |
| `dysuria_null_metaphor` | 758 | 100.0% | 98.8% | 99.7% | 92.3% | 91.8% | 8.2pp |
| `dysuria_null_historical` | 654 | 100.0% | 98.2% | 99.7% | 95.6% | 99.7% | 4.4pp |
| `(none)` | 2978 | 100.0% | 97.7% | 99.8% | 98.5% | 99.9% | 2.3pp |

### By fragment, errors

Ordered by the worst model's error count, so the fragments the comparison is about sort
to the top whichever encoder wins. Counts, not rates: these are the sentences a month of
library work would be spent on. The JSON holds every fragment.

| fragment | library | truth | `majority_class` | `length_only` | `tfidf_logreg` | `arm_a_probe` | `arm_b_finetune` | spread |
|---|---|---|---|---|---|---|---|---|
| `dysuria_false:85e13aca` | `dysuria_false` | false | 74 | 57 | 0 | 4 | 0 | 74 |
| `dysuria_false:82438593` | `dysuria_false` | false | 68 | 60 | 26 | 6 | 0 | 68 |
| `dysuria_false:202255a3` | `dysuria_false` | false | 67 | 64 | 67 | 11 | 0 | 67 |
| `dysuria_false:2508af9f` | `dysuria_false` | false | 67 | 55 | 10 | 5 | 0 | 67 |
| `dysuria_false:41c43f99` | `dysuria_false` | false | 66 | 62 | 24 | 19 | 0 | 66 |
| `dysuria_false:1fa9bf6a` | `dysuria_false` | false | 63 | 56 | 11 | 9 | 0 | 63 |
| `dysuria_false:52998403` | `dysuria_false` | false | 63 | 63 | 0 | 0 | 0 | 63 |
| `dysuria_false:5837e4e6` | `dysuria_false` | false | 63 | 48 | 53 | 33 | 0 | 63 |
| `dysuria_false:78c1ede4` | `dysuria_false` | false | 61 | 61 | 3 | 11 | 0 | 61 |
| `dysuria_false:e75c2521` | `dysuria_false` | false | 61 | 51 | 13 | 3 | 0 | 61 |
| `dysuria_false:90277b2d` | `dysuria_false` | false | 60 | 58 | 0 | 5 | 0 | 60 |
| `dysuria_false:9b29601b` | `dysuria_false` | false | 60 | 60 | 33 | 3 | 0 | 60 |
| `dysuria_false:915a7bf7` | `dysuria_false` | false | 59 | 54 | 16 | 6 | 0 | 59 |
| `dysuria_false:62636499` | `dysuria_false` | false | 58 | 53 | 2 | 3 | 0 | 58 |
| `dysuria_false:d46403bb` | `dysuria_false` | false | 58 | 55 | 0 | 3 | 0 | 58 |
| `dysuria_false:43aa9d18` | `dysuria_false` | false | 57 | 55 | 30 | 15 | 0 | 57 |
| `dysuria_false:f3a29d90` | `dysuria_false` | false | 57 | 54 | 7 | 1 | 0 | 57 |
| `dysuria_false:18791ae3` | `dysuria_false` | false | 56 | 56 | 0 | 7 | 0 | 56 |
| `dysuria_false:47348026` | `dysuria_false` | false | 56 | 50 | 25 | 10 | 0 | 56 |
| `dysuria_false:d3769665` | `dysuria_false` | false | 56 | 52 | 53 | 14 | 0 | 56 |
| `dysuria_false:4299d111` | `dysuria_false` | false | 55 | 55 | 3 | 5 | 0 | 55 |
| `dysuria_false:70ff0f9d` | `dysuria_false` | false | 55 | 55 | 0 | 1 | 0 | 55 |
| `dysuria_false:1548b49b` | `dysuria_false` | false | 54 | 38 | 54 | 12 | 0 | 54 |
| `dysuria_false:502574f5` | `dysuria_false` | false | 54 | 47 | 11 | 8 | 0 | 54 |
| `dysuria_false:1c30e825` | `dysuria_false` | false | 53 | 47 | 22 | 1 | 0 | 53 |
| `dysuria_false:7fcddee5` | `dysuria_false` | false | 53 | 53 | 23 | 0 | 0 | 53 |
| `dysuria_false:9a3ed060` | `dysuria_false` | false | 53 | 52 | 53 | 45 | 0 | 53 |
| `dysuria_false:90df50ee` | `dysuria_false` | false | 51 | 43 | 1 | 3 | 0 | 51 |
| `dysuria_false:ab9389ac` | `dysuria_false` | false | 50 | 40 | 2 | 1 | 0 | 50 |
| `dysuria_false:b2d71275` | `dysuria_false` | false | 50 | 50 | 50 | 47 | 0 | 50 |
| `dysuria_false:3ce959c2` | `dysuria_false` | false | 49 | 41 | 24 | 26 | 0 | 49 |
| `dysuria_false:1c5be177` | `dysuria_false` | false | 48 | 40 | 0 | 2 | 0 | 48 |
| `dysuria_true:93845aa6` | `dysuria_true` | true | 48 | 48 | 48 | 15 | 0 | 48 |
| `dysuria_false:79a25459` | `dysuria_false` | false | 47 | 45 | 7 | 0 | 0 | 47 |
| `dysuria_false:64f15eeb` | `dysuria_false` | false | 46 | 44 | 46 | 34 | 0 | 46 |
| `dysuria_false:ca382087` | `dysuria_false` | false | 44 | 44 | 1 | 1 | 0 | 44 |
| `dysuria_true:28c7bf7e` | `dysuria_true` | true | 44 | 44 | 44 | 0 | 0 | 44 |
| `dysuria_true:4694eaab` | `dysuria_true` | true | 44 | 44 | 30 | 0 | 0 | 44 |
| `dysuria_true:81b6882e` | `dysuria_true` | true | 44 | 44 | 37 | 10 | 0 | 44 |
| `dysuria_true:8ee469c9` | `dysuria_true` | true | 44 | 44 | 15 | 3 | 0 | 44 |

*132 further fragments erred on at least one model; the JSON holds them all.*

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
| hedged | 785 | **20** | 100.0% [100.0%, 100.0%] |
| historical | 654 | **19** | 100.0% [100.0%, 100.0%] |
| metaphor | 758 | **28** | 100.0% [100.0%, 100.0%] |
| third_party | 865 | **23** | 100.0% [100.0%, 100.0%] |

### By fragment library

| library | n | eff n | accuracy [95% CI] |
|---|---|---|---|
| dysuria_false | 2479 | **47** | 0.0% [0.0%, 0.0%] |
| dysuria_null_hedged | 785 | **20** | 100.0% [100.0%, 100.0%] |
| dysuria_null_historical | 654 | **19** | 100.0% [100.0%, 100.0%] |
| dysuria_null_metaphor | 758 | **28** | 100.0% [100.0%, 100.0%] |
| dysuria_null_thirdparty | 865 | **23** | 100.0% [100.0%, 100.0%] |
| dysuria_true | 1481 | **45** | 0.0% [0.0%, 0.0%] |
| (none) | 2978 | **1** | 100.0% [100.0%, 100.0%] |

### Per-fragment errors (worst first)

Whether errors are spread thinly across many fragments or piled onto a few is the difference
between "the method is too weak" (model work) and "these specific ideas are not learnable from
the data we have" (library work, and these are the fragments to write more of). No intervals:
a fragment is one cluster, so an interval over its own examples measures nothing.

92 of 256 decisive fragments were got wrong at least once.

`majority_class`: 3960 errors across 92 of 256 decisive fragments. Half of them fall on **35** fragments (an even spread would be 46.0); the worst ten carry 16.5% of all errors.

| fragment | library | sub-class | truth | correct | accuracy | predicted as |
|---|---|---|---|---|---|---|
| `dysuria_false:85e13aca` | `dysuria_false` | -- | false | 0/74 | 0.0% | null 74 |
| `dysuria_false:82438593` | `dysuria_false` | -- | false | 0/68 | 0.0% | null 68 |
| `dysuria_false:202255a3` | `dysuria_false` | -- | false | 0/67 | 0.0% | null 67 |
| `dysuria_false:2508af9f` | `dysuria_false` | -- | false | 0/67 | 0.0% | null 67 |
| `dysuria_false:41c43f99` | `dysuria_false` | -- | false | 0/66 | 0.0% | null 66 |
| `dysuria_false:1fa9bf6a` | `dysuria_false` | -- | false | 0/63 | 0.0% | null 63 |
| `dysuria_false:52998403` | `dysuria_false` | -- | false | 0/63 | 0.0% | null 63 |
| `dysuria_false:5837e4e6` | `dysuria_false` | -- | false | 0/63 | 0.0% | null 63 |
| `dysuria_false:78c1ede4` | `dysuria_false` | -- | false | 0/61 | 0.0% | null 61 |
| `dysuria_false:e75c2521` | `dysuria_false` | -- | false | 0/61 | 0.0% | null 61 |
| `dysuria_false:90277b2d` | `dysuria_false` | -- | false | 0/60 | 0.0% | null 60 |
| `dysuria_false:9b29601b` | `dysuria_false` | -- | false | 0/60 | 0.0% | null 60 |
| `dysuria_false:915a7bf7` | `dysuria_false` | -- | false | 0/59 | 0.0% | null 59 |
| `dysuria_false:62636499` | `dysuria_false` | -- | false | 0/58 | 0.0% | null 58 |
| `dysuria_false:d46403bb` | `dysuria_false` | -- | false | 0/58 | 0.0% | null 58 |
| `dysuria_false:43aa9d18` | `dysuria_false` | -- | false | 0/57 | 0.0% | null 57 |
| `dysuria_false:f3a29d90` | `dysuria_false` | -- | false | 0/57 | 0.0% | null 57 |
| `dysuria_false:18791ae3` | `dysuria_false` | -- | false | 0/56 | 0.0% | null 56 |
| `dysuria_false:47348026` | `dysuria_false` | -- | false | 0/56 | 0.0% | null 56 |
| `dysuria_false:d3769665` | `dysuria_false` | -- | false | 0/56 | 0.0% | null 56 |
| `dysuria_false:4299d111` | `dysuria_false` | -- | false | 0/55 | 0.0% | null 55 |
| `dysuria_false:70ff0f9d` | `dysuria_false` | -- | false | 0/55 | 0.0% | null 55 |
| `dysuria_false:1548b49b` | `dysuria_false` | -- | false | 0/54 | 0.0% | null 54 |
| `dysuria_false:502574f5` | `dysuria_false` | -- | false | 0/54 | 0.0% | null 54 |
| `dysuria_false:1c30e825` | `dysuria_false` | -- | false | 0/53 | 0.0% | null 53 |
| `dysuria_false:7fcddee5` | `dysuria_false` | -- | false | 0/53 | 0.0% | null 53 |
| `dysuria_false:9a3ed060` | `dysuria_false` | -- | false | 0/53 | 0.0% | null 53 |
| `dysuria_false:90df50ee` | `dysuria_false` | -- | false | 0/51 | 0.0% | null 51 |
| `dysuria_false:ab9389ac` | `dysuria_false` | -- | false | 0/50 | 0.0% | null 50 |
| `dysuria_false:b2d71275` | `dysuria_false` | -- | false | 0/50 | 0.0% | null 50 |
| `dysuria_false:3ce959c2` | `dysuria_false` | -- | false | 0/49 | 0.0% | null 49 |
| `dysuria_false:1c5be177` | `dysuria_false` | -- | false | 0/48 | 0.0% | null 48 |
| `dysuria_true:93845aa6` | `dysuria_true` | -- | true | 0/48 | 0.0% | null 48 |
| `dysuria_false:79a25459` | `dysuria_false` | -- | false | 0/47 | 0.0% | null 47 |
| `dysuria_false:64f15eeb` | `dysuria_false` | -- | false | 0/46 | 0.0% | null 46 |
| `dysuria_false:ca382087` | `dysuria_false` | -- | false | 0/44 | 0.0% | null 44 |
| `dysuria_true:28c7bf7e` | `dysuria_true` | -- | true | 0/44 | 0.0% | null 44 |
| `dysuria_true:4694eaab` | `dysuria_true` | -- | true | 0/44 | 0.0% | null 44 |
| `dysuria_true:81b6882e` | `dysuria_true` | -- | true | 0/44 | 0.0% | null 44 |
| `dysuria_true:8ee469c9` | `dysuria_true` | -- | true | 0/44 | 0.0% | null 44 |

*52 further fragments with at least one error are in the JSON sidecar; every fragment is there regardless of score.*

## `length_only`

Logistic regression on token count alone. The direct measurable test of the length leak: anything materially above majority means text length is a usable proxy for the label, which is a fragment-library problem rather than a model one.

Decision-rule margins selected per fold (on each fold's own validation split): 0.0.
Every fold selected margin 0, so the ruled and raw views below are the same decisions. That is a finding rather than a bug: no margin improved macro-F1 without worsening the `null -> true` rate.

*Confusion matrix, raw argmax*

|  | pred false | pred true | pred null | total |
|---|---|---|---|---|
| **truth false** | 256 | 0 | 2223 | 2479 |
| **truth true** | 88 | 0 | 1393 | 1481 |
| **truth null** | 95 | 0 | 5945 | 6040 |
| **total** | 439 | 0 | 9561 | 10000 |

`null -> true`: 0 of 6040 truly-null examples (0.00%).

*Confusion matrix, after the decision rule*

|  | pred false | pred true | pred null | total |
|---|---|---|---|---|
| **truth false** | 256 | 0 | 2223 | 2479 |
| **truth true** | 88 | 0 | 1393 | 1481 |
| **truth null** | 95 | 0 | 5945 | 6040 |
| **total** | 439 | 0 | 9561 | 10000 |

`null -> true`: 0 of 6040 truly-null examples (0.00%).

### Per class, after the decision rule

| class | support | predicted | precision | recall | F1 |
|---|---|---|---|---|---|
| `false` | 2479 | 439 | 58.3% | 10.3% | 17.5% |
| `true` | 1481 | 0 | -- | 0.0% | 0.0% |
| `null` | 6040 | 9561 | 62.2% | 98.4% | 76.2% |

### By label mode

| label mode | n | eff n | accuracy [95% CI] |
|---|---|---|---|
| false | 2479 | **47** | 10.3% [7.7%, 13.1%] |
| null_ambiguous | 3062 | **90** | 99.1% [98.2%, 99.7%] |
| null_structural | 2978 | **1** | 97.7% [97.7%, 97.7%] |
| true | 1481 | **45** | 0.0% [0.0%, 0.0%] |

### By null sub-class

| sub-class | n | eff n | null recall [95% CI] |
|---|---|---|---|
| hedged | 785 | **20** | 100.0% [100.0%, 100.0%] |
| historical | 654 | **19** | 98.2% [94.8%, 100.0%] |
| metaphor | 758 | **28** | 98.8% [97.6%, 99.7%] |
| third_party | 865 | **23** | 99.3% [98.5%, 99.9%] |

### By fragment library

| library | n | eff n | accuracy [95% CI] |
|---|---|---|---|
| dysuria_false | 2479 | **47** | 10.3% [7.7%, 13.1%] |
| dysuria_null_hedged | 785 | **20** | 100.0% [100.0%, 100.0%] |
| dysuria_null_historical | 654 | **19** | 98.2% [94.8%, 100.0%] |
| dysuria_null_metaphor | 758 | **28** | 98.8% [97.6%, 99.7%] |
| dysuria_null_thirdparty | 865 | **23** | 99.3% [98.5%, 99.9%] |
| dysuria_true | 1481 | **45** | 0.0% [0.0%, 0.0%] |
| (none) | 2978 | **1** | 97.7% [97.7%, 97.7%] |

### Per-fragment errors (worst first)

Whether errors are spread thinly across many fragments or piled onto a few is the difference
between "the method is too weak" (model work) and "these specific ideas are not learnable from
the data we have" (library work, and these are the fragments to write more of). No intervals:
a fragment is one cluster, so an interval over its own examples measures nothing.

105 of 256 decisive fragments were got wrong at least once.

`length_only`: 3731 errors across 105 of 256 decisive fragments. Half of them fall on **36** fragments (an even spread would be 52.5); the worst ten carry 16.0% of all errors.

| fragment | library | sub-class | truth | correct | accuracy | predicted as |
|---|---|---|---|---|---|---|
| `dysuria_false:52998403` | `dysuria_false` | -- | false | 0/63 | 0.0% | null 63 |
| `dysuria_false:78c1ede4` | `dysuria_false` | -- | false | 0/61 | 0.0% | null 61 |
| `dysuria_false:9b29601b` | `dysuria_false` | -- | false | 0/60 | 0.0% | null 60 |
| `dysuria_false:18791ae3` | `dysuria_false` | -- | false | 0/56 | 0.0% | null 56 |
| `dysuria_false:4299d111` | `dysuria_false` | -- | false | 0/55 | 0.0% | null 55 |
| `dysuria_false:70ff0f9d` | `dysuria_false` | -- | false | 0/55 | 0.0% | null 55 |
| `dysuria_false:7fcddee5` | `dysuria_false` | -- | false | 0/53 | 0.0% | null 53 |
| `dysuria_false:b2d71275` | `dysuria_false` | -- | false | 0/50 | 0.0% | null 50 |
| `dysuria_true:93845aa6` | `dysuria_true` | -- | true | 0/48 | 0.0% | null 48 |
| `dysuria_false:ca382087` | `dysuria_false` | -- | false | 0/44 | 0.0% | null 44 |
| `dysuria_true:28c7bf7e` | `dysuria_true` | -- | true | 0/44 | 0.0% | false 2, null 42 |
| `dysuria_true:4694eaab` | `dysuria_true` | -- | true | 0/44 | 0.0% | null 44 |
| `dysuria_true:81b6882e` | `dysuria_true` | -- | true | 0/44 | 0.0% | null 44 |
| `dysuria_true:8ee469c9` | `dysuria_true` | -- | true | 0/44 | 0.0% | null 44 |
| `dysuria_false:5f0bc325` | `dysuria_false` | -- | false | 0/41 | 0.0% | null 41 |
| `dysuria_true:4c214872` | `dysuria_true` | -- | true | 0/40 | 0.0% | null 40 |
| `dysuria_true:5fefaac6` | `dysuria_true` | -- | true | 0/40 | 0.0% | false 2, null 38 |
| `dysuria_true:8f0ade4e` | `dysuria_true` | -- | true | 0/40 | 0.0% | null 40 |
| `dysuria_true:a2448219` | `dysuria_true` | -- | true | 0/40 | 0.0% | null 40 |
| `dysuria_true:f02ba872` | `dysuria_true` | -- | true | 0/40 | 0.0% | null 40 |
| `dysuria_true:f5df5754` | `dysuria_true` | -- | true | 0/38 | 0.0% | null 38 |
| `dysuria_true:71544e46` | `dysuria_true` | -- | true | 0/37 | 0.0% | false 11, null 26 |
| `dysuria_true:7c711665` | `dysuria_true` | -- | true | 0/35 | 0.0% | false 2, null 33 |
| `dysuria_true:9c2b1e02` | `dysuria_true` | -- | true | 0/35 | 0.0% | false 7, null 28 |
| `dysuria_true:146d5e49` | `dysuria_true` | -- | true | 0/34 | 0.0% | false 11, null 23 |
| `dysuria_true:73d25d0c` | `dysuria_true` | -- | true | 0/34 | 0.0% | false 6, null 28 |
| `dysuria_true:933cf995` | `dysuria_true` | -- | true | 0/34 | 0.0% | false 1, null 33 |
| `dysuria_true:b898c2de` | `dysuria_true` | -- | true | 0/34 | 0.0% | false 2, null 32 |
| `dysuria_true:d39be0eb` | `dysuria_true` | -- | true | 0/34 | 0.0% | null 34 |
| `dysuria_true:0d7321c0` | `dysuria_true` | -- | true | 0/33 | 0.0% | false 12, null 21 |
| `dysuria_true:3888fc9f` | `dysuria_true` | -- | true | 0/33 | 0.0% | null 33 |
| `dysuria_true:83eb7cdc` | `dysuria_true` | -- | true | 0/33 | 0.0% | null 33 |
| `dysuria_true:abed15dd` | `dysuria_true` | -- | true | 0/33 | 0.0% | false 1, null 32 |
| `dysuria_true:985d61a2` | `dysuria_true` | -- | true | 0/32 | 0.0% | null 32 |
| `dysuria_true:c3f7adf1` | `dysuria_true` | -- | true | 0/32 | 0.0% | null 32 |
| `dysuria_true:fd186b28` | `dysuria_true` | -- | true | 0/32 | 0.0% | false 16, null 16 |
| `dysuria_true:02037108` | `dysuria_true` | -- | true | 0/31 | 0.0% | null 31 |
| `dysuria_true:614d867c` | `dysuria_true` | -- | true | 0/30 | 0.0% | null 30 |
| `dysuria_true:a28e78a6` | `dysuria_true` | -- | true | 0/30 | 0.0% | null 30 |
| `dysuria_true:b87ef0cf` | `dysuria_true` | -- | true | 0/30 | 0.0% | false 1, null 29 |

*65 further fragments with at least one error are in the JSON sidecar; every fragment is there regardless of score.*

## `tfidf_logreg`

TF-IDF unigrams and bigrams into logistic regression. Tests whether the dataset is keyword-solvable. Its overall accuracy is close to uninformative; the `null_ambiguous` slice is the number that matters.

Decision-rule margins selected per fold (on each fold's own validation split): 0.0.
Every fold selected margin 0, so the ruled and raw views below are the same decisions. That is a finding rather than a bug: no margin improved macro-F1 without worsening the `null -> true` rate.

*Confusion matrix, raw argmax*

|  | pred false | pred true | pred null | total |
|---|---|---|---|---|
| **truth false** | 1666 | 102 | 711 | 2479 |
| **truth true** | 106 | 391 | 984 | 1481 |
| **truth null** | 51 | 120 | 5869 | 6040 |
| **total** | 1823 | 613 | 7564 | 10000 |

`null -> true`: 120 of 6040 truly-null examples (1.99%).

*Confusion matrix, after the decision rule*

|  | pred false | pred true | pred null | total |
|---|---|---|---|---|
| **truth false** | 1666 | 102 | 711 | 2479 |
| **truth true** | 106 | 391 | 984 | 1481 |
| **truth null** | 51 | 120 | 5869 | 6040 |
| **total** | 1823 | 613 | 7564 | 10000 |

`null -> true`: 120 of 6040 truly-null examples (1.99%).

### Per class, after the decision rule

| class | support | predicted | precision | recall | F1 |
|---|---|---|---|---|---|
| `false` | 2479 | 1823 | 91.4% | 67.2% | 77.5% |
| `true` | 1481 | 613 | 63.8% | 26.4% | 37.3% |
| `null` | 6040 | 7564 | 77.6% | 97.2% | 86.3% |

### By label mode

| label mode | n | eff n | accuracy [95% CI] |
|---|---|---|---|
| false | 2479 | **47** | 67.2% [56.9%, 76.5%] |
| null_ambiguous | 3062 | **90** | 94.6% [91.2%, 97.4%] |
| null_structural | 2978 | **1** | 99.8% [99.8%, 99.8%] |
| true | 1481 | **45** | 26.4% [17.9%, 35.7%] |

### By null sub-class

| sub-class | n | eff n | null recall [95% CI] |
|---|---|---|---|
| hedged | 785 | **20** | 84.7% [75.2%, 93.7%] |
| historical | 654 | **19** | 99.7% [99.2%, 100.0%] |
| metaphor | 758 | **28** | 99.7% [99.4%, 100.0%] |
| third_party | 865 | **23** | 95.1% [89.5%, 99.6%] |

### By fragment library

| library | n | eff n | accuracy [95% CI] |
|---|---|---|---|
| dysuria_false | 2479 | **47** | 67.2% [56.9%, 76.5%] |
| dysuria_null_hedged | 785 | **20** | 84.7% [75.2%, 93.7%] |
| dysuria_null_historical | 654 | **19** | 99.7% [99.2%, 100.0%] |
| dysuria_null_metaphor | 758 | **28** | 99.7% [99.4%, 100.0%] |
| dysuria_null_thirdparty | 865 | **23** | 95.1% [89.5%, 99.6%] |
| dysuria_true | 1481 | **45** | 26.4% [17.9%, 35.7%] |
| (none) | 2978 | **1** | 99.8% [99.8%, 99.8%] |

### Per-fragment errors (worst first)

Whether errors are spread thinly across many fragments or piled onto a few is the difference
between "the method is too weak" (model work) and "these specific ideas are not learnable from
the data we have" (library work, and these are the fragments to write more of). No intervals:
a fragment is one cluster, so an interval over its own examples measures nothing.

104 of 256 decisive fragments were got wrong at least once.

`tfidf_logreg`: 2069 errors across 104 of 256 decisive fragments. Half of them fall on **26** fragments (an even spread would be 52.0); the worst ten carry 24.5% of all errors.

| fragment | library | sub-class | truth | correct | accuracy | predicted as |
|---|---|---|---|---|---|---|
| `dysuria_false:202255a3` | `dysuria_false` | -- | false | 0/67 | 0.0% | true 1, null 66 |
| `dysuria_false:1548b49b` | `dysuria_false` | -- | false | 0/54 | 0.0% | true 45, null 9 |
| `dysuria_false:9a3ed060` | `dysuria_false` | -- | false | 0/53 | 0.0% | null 53 |
| `dysuria_false:b2d71275` | `dysuria_false` | -- | false | 0/50 | 0.0% | true 4, null 46 |
| `dysuria_true:93845aa6` | `dysuria_true` | -- | true | 0/48 | 0.0% | null 48 |
| `dysuria_false:64f15eeb` | `dysuria_false` | -- | false | 0/46 | 0.0% | null 46 |
| `dysuria_true:28c7bf7e` | `dysuria_true` | -- | true | 0/44 | 0.0% | false 17, null 27 |
| `dysuria_false:ffc68e8d` | `dysuria_false` | -- | false | 0/39 | 0.0% | null 39 |
| `dysuria_true:146d5e49` | `dysuria_true` | -- | true | 0/34 | 0.0% | false 1, null 33 |
| `dysuria_true:73d25d0c` | `dysuria_true` | -- | true | 0/34 | 0.0% | null 34 |
| `dysuria_true:b898c2de` | `dysuria_true` | -- | true | 0/34 | 0.0% | null 34 |
| `dysuria_true:83eb7cdc` | `dysuria_true` | -- | true | 0/33 | 0.0% | null 33 |
| `dysuria_true:abed15dd` | `dysuria_true` | -- | true | 0/33 | 0.0% | null 33 |
| `dysuria_true:09689dd1` | `dysuria_true` | -- | true | 0/29 | 0.0% | false 7, null 22 |
| `dysuria_true:6cadf930` | `dysuria_true` | -- | true | 0/29 | 0.0% | false 3, null 26 |
| `dysuria_null_hedged:249a7342` | `dysuria_null_hedged` | hedged | null | 0/27 | 0.0% | true 27 |
| `dysuria_true:36a17090` | `dysuria_true` | -- | true | 0/26 | 0.0% | null 26 |
| `dysuria_true:bc3a15bf` | `dysuria_true` | -- | true | 0/25 | 0.0% | null 25 |
| `dysuria_true:2e98f278` | `dysuria_true` | -- | true | 0/24 | 0.0% | null 24 |
| `dysuria_null_thirdparty:2db889fa` | `dysuria_null_thirdparty` | third_party | null | 0/14 | 0.0% | false 1, true 13 |
| `dysuria_null_thirdparty:ddfe9a7b` | `dysuria_null_thirdparty` | third_party | null | 0/8 | 0.0% | true 8 |
| `dysuria_true:a2448219` | `dysuria_true` | -- | true | 1/40 | 2.5% | true 1, null 39 |
| `dysuria_true:63f5b24c` | `dysuria_true` | -- | true | 1/24 | 4.2% | true 1, null 23 |
| `dysuria_true:c17c33dd` | `dysuria_true` | -- | true | 1/24 | 4.2% | false 2, true 1, null 21 |
| `dysuria_true:f5df5754` | `dysuria_true` | -- | true | 2/38 | 5.3% | false 2, true 2, null 34 |
| `dysuria_false:d3769665` | `dysuria_false` | -- | false | 3/56 | 5.4% | false 3, true 35, null 18 |
| `dysuria_null_thirdparty:4e732310` | `dysuria_null_thirdparty` | third_party | null | 1/17 | 5.9% | false 10, true 6, null 1 |
| `dysuria_null_hedged:b1ae1f9d` | `dysuria_null_hedged` | hedged | null | 2/33 | 6.1% | true 31, null 2 |
| `dysuria_true:0d7321c0` | `dysuria_true` | -- | true | 2/33 | 6.1% | true 2, null 31 |
| `dysuria_true:985d61a2` | `dysuria_true` | -- | true | 2/32 | 6.2% | true 2, null 30 |
| `dysuria_true:c3f7adf1` | `dysuria_true` | -- | true | 2/32 | 6.2% | false 1, true 2, null 29 |
| `dysuria_true:89e28e2d` | `dysuria_true` | -- | true | 2/26 | 7.7% | true 2, null 24 |
| `dysuria_true:71544e46` | `dysuria_true` | -- | true | 3/37 | 8.1% | true 3, null 34 |
| `dysuria_true:f02ba872` | `dysuria_true` | -- | true | 4/40 | 10.0% | false 12, true 4, null 24 |
| `dysuria_null_hedged:5bf05464` | `dysuria_null_hedged` | hedged | null | 2/15 | 13.3% | false 13, null 2 |
| `dysuria_true:7c711665` | `dysuria_true` | -- | true | 5/35 | 14.3% | false 6, true 5, null 24 |
| `dysuria_true:37c0a85e` | `dysuria_true` | -- | true | 4/28 | 14.3% | true 4, null 24 |
| `dysuria_true:5fefaac6` | `dysuria_true` | -- | true | 6/40 | 15.0% | true 6, null 34 |
| `dysuria_false:5837e4e6` | `dysuria_false` | -- | false | 10/63 | 15.9% | false 10, null 53 |
| `dysuria_true:81b6882e` | `dysuria_true` | -- | true | 7/44 | 15.9% | false 27, true 7, null 10 |

*64 further fragments with at least one error are in the JSON sidecar; every fragment is there regardless of score.*

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
| hedged | 785 | **20** | 100.0% [100.0%, 100.0%] |
| historical | 654 | **19** | 100.0% [100.0%, 100.0%] |
| metaphor | 758 | **28** | 100.0% [100.0%, 100.0%] |
| third_party | 865 | **23** | 100.0% [100.0%, 100.0%] |

### By fragment library

| library | n | eff n | accuracy [95% CI] |
|---|---|---|---|
| dysuria_false | 2479 | **47** | 0.0% [0.0%, 0.0%] |
| dysuria_null_hedged | 785 | **20** | 100.0% [100.0%, 100.0%] |
| dysuria_null_historical | 654 | **19** | 100.0% [100.0%, 100.0%] |
| dysuria_null_metaphor | 758 | **28** | 100.0% [100.0%, 100.0%] |
| dysuria_null_thirdparty | 865 | **23** | 100.0% [100.0%, 100.0%] |
| dysuria_true | 1481 | **45** | 0.0% [0.0%, 0.0%] |
| (none) | 2978 | **1** | 100.0% [100.0%, 100.0%] |

### Per-fragment errors (worst first)

Whether errors are spread thinly across many fragments or piled onto a few is the difference
between "the method is too weak" (model work) and "these specific ideas are not learnable from
the data we have" (library work, and these are the fragments to write more of). No intervals:
a fragment is one cluster, so an interval over its own examples measures nothing.

92 of 256 decisive fragments were got wrong at least once.

`length_only__shuffled`: 3960 errors across 92 of 256 decisive fragments. Half of them fall on **35** fragments (an even spread would be 46.0); the worst ten carry 16.5% of all errors.

| fragment | library | sub-class | truth | correct | accuracy | predicted as |
|---|---|---|---|---|---|---|
| `dysuria_false:85e13aca` | `dysuria_false` | -- | false | 0/74 | 0.0% | null 74 |
| `dysuria_false:82438593` | `dysuria_false` | -- | false | 0/68 | 0.0% | null 68 |
| `dysuria_false:202255a3` | `dysuria_false` | -- | false | 0/67 | 0.0% | null 67 |
| `dysuria_false:2508af9f` | `dysuria_false` | -- | false | 0/67 | 0.0% | null 67 |
| `dysuria_false:41c43f99` | `dysuria_false` | -- | false | 0/66 | 0.0% | null 66 |
| `dysuria_false:1fa9bf6a` | `dysuria_false` | -- | false | 0/63 | 0.0% | null 63 |
| `dysuria_false:52998403` | `dysuria_false` | -- | false | 0/63 | 0.0% | null 63 |
| `dysuria_false:5837e4e6` | `dysuria_false` | -- | false | 0/63 | 0.0% | null 63 |
| `dysuria_false:78c1ede4` | `dysuria_false` | -- | false | 0/61 | 0.0% | null 61 |
| `dysuria_false:e75c2521` | `dysuria_false` | -- | false | 0/61 | 0.0% | null 61 |
| `dysuria_false:90277b2d` | `dysuria_false` | -- | false | 0/60 | 0.0% | null 60 |
| `dysuria_false:9b29601b` | `dysuria_false` | -- | false | 0/60 | 0.0% | null 60 |
| `dysuria_false:915a7bf7` | `dysuria_false` | -- | false | 0/59 | 0.0% | null 59 |
| `dysuria_false:62636499` | `dysuria_false` | -- | false | 0/58 | 0.0% | null 58 |
| `dysuria_false:d46403bb` | `dysuria_false` | -- | false | 0/58 | 0.0% | null 58 |
| `dysuria_false:43aa9d18` | `dysuria_false` | -- | false | 0/57 | 0.0% | null 57 |
| `dysuria_false:f3a29d90` | `dysuria_false` | -- | false | 0/57 | 0.0% | null 57 |
| `dysuria_false:18791ae3` | `dysuria_false` | -- | false | 0/56 | 0.0% | null 56 |
| `dysuria_false:47348026` | `dysuria_false` | -- | false | 0/56 | 0.0% | null 56 |
| `dysuria_false:d3769665` | `dysuria_false` | -- | false | 0/56 | 0.0% | null 56 |
| `dysuria_false:4299d111` | `dysuria_false` | -- | false | 0/55 | 0.0% | null 55 |
| `dysuria_false:70ff0f9d` | `dysuria_false` | -- | false | 0/55 | 0.0% | null 55 |
| `dysuria_false:1548b49b` | `dysuria_false` | -- | false | 0/54 | 0.0% | null 54 |
| `dysuria_false:502574f5` | `dysuria_false` | -- | false | 0/54 | 0.0% | null 54 |
| `dysuria_false:1c30e825` | `dysuria_false` | -- | false | 0/53 | 0.0% | null 53 |
| `dysuria_false:7fcddee5` | `dysuria_false` | -- | false | 0/53 | 0.0% | null 53 |
| `dysuria_false:9a3ed060` | `dysuria_false` | -- | false | 0/53 | 0.0% | null 53 |
| `dysuria_false:90df50ee` | `dysuria_false` | -- | false | 0/51 | 0.0% | null 51 |
| `dysuria_false:ab9389ac` | `dysuria_false` | -- | false | 0/50 | 0.0% | null 50 |
| `dysuria_false:b2d71275` | `dysuria_false` | -- | false | 0/50 | 0.0% | null 50 |
| `dysuria_false:3ce959c2` | `dysuria_false` | -- | false | 0/49 | 0.0% | null 49 |
| `dysuria_false:1c5be177` | `dysuria_false` | -- | false | 0/48 | 0.0% | null 48 |
| `dysuria_true:93845aa6` | `dysuria_true` | -- | true | 0/48 | 0.0% | null 48 |
| `dysuria_false:79a25459` | `dysuria_false` | -- | false | 0/47 | 0.0% | null 47 |
| `dysuria_false:64f15eeb` | `dysuria_false` | -- | false | 0/46 | 0.0% | null 46 |
| `dysuria_false:ca382087` | `dysuria_false` | -- | false | 0/44 | 0.0% | null 44 |
| `dysuria_true:28c7bf7e` | `dysuria_true` | -- | true | 0/44 | 0.0% | null 44 |
| `dysuria_true:4694eaab` | `dysuria_true` | -- | true | 0/44 | 0.0% | null 44 |
| `dysuria_true:81b6882e` | `dysuria_true` | -- | true | 0/44 | 0.0% | null 44 |
| `dysuria_true:8ee469c9` | `dysuria_true` | -- | true | 0/44 | 0.0% | null 44 |

*52 further fragments with at least one error are in the JSON sidecar; every fragment is there regardless of score.*

## `tfidf_logreg__shuffled`

TF-IDF unigrams and bigrams into logistic regression. Tests whether the dataset is keyword-solvable. Its overall accuracy is close to uninformative; the `null_ambiguous` slice is the number that matters. **Negative control:** trained on permuted training labels (seed 7) and evaluated on the unpermuted test split, where it must land at chance.

Decision-rule margins selected per fold (on each fold's own validation split): 0.0.
Every fold selected margin 0, so the ruled and raw views below are the same decisions. That is a finding rather than a bug: no margin improved macro-F1 without worsening the `null -> true` rate.

*Confusion matrix, raw argmax*

|  | pred false | pred true | pred null | total |
|---|---|---|---|---|
| **truth false** | 1 | 0 | 2478 | 2479 |
| **truth true** | 0 | 0 | 1481 | 1481 |
| **truth null** | 2 | 0 | 6038 | 6040 |
| **total** | 3 | 0 | 9997 | 10000 |

`null -> true`: 0 of 6040 truly-null examples (0.00%).

*Confusion matrix, after the decision rule*

|  | pred false | pred true | pred null | total |
|---|---|---|---|---|
| **truth false** | 1 | 0 | 2478 | 2479 |
| **truth true** | 0 | 0 | 1481 | 1481 |
| **truth null** | 2 | 0 | 6038 | 6040 |
| **total** | 3 | 0 | 9997 | 10000 |

`null -> true`: 0 of 6040 truly-null examples (0.00%).

### Per class, after the decision rule

| class | support | predicted | precision | recall | F1 |
|---|---|---|---|---|---|
| `false` | 2479 | 3 | 33.3% | 0.0% | 0.1% |
| `true` | 1481 | 0 | -- | 0.0% | 0.0% |
| `null` | 6040 | 9997 | 60.4% | 100.0% | 75.3% |

### By label mode

| label mode | n | eff n | accuracy [95% CI] |
|---|---|---|---|
| false | 2479 | **47** | 0.0% [0.0%, 0.1%] |
| null_ambiguous | 3062 | **90** | 99.9% [99.8%, 100.0%] |
| null_structural | 2978 | **1** | 100.0% [100.0%, 100.0%] |
| true | 1481 | **45** | 0.0% [0.0%, 0.0%] |

### By null sub-class

| sub-class | n | eff n | null recall [95% CI] |
|---|---|---|---|
| hedged | 785 | **20** | 99.9% [99.6%, 100.0%] |
| historical | 654 | **19** | 99.8% [99.5%, 100.0%] |
| metaphor | 758 | **28** | 100.0% [100.0%, 100.0%] |
| third_party | 865 | **23** | 100.0% [100.0%, 100.0%] |

### By fragment library

| library | n | eff n | accuracy [95% CI] |
|---|---|---|---|
| dysuria_false | 2479 | **47** | 0.0% [0.0%, 0.1%] |
| dysuria_null_hedged | 785 | **20** | 99.9% [99.6%, 100.0%] |
| dysuria_null_historical | 654 | **19** | 99.8% [99.5%, 100.0%] |
| dysuria_null_metaphor | 758 | **28** | 100.0% [100.0%, 100.0%] |
| dysuria_null_thirdparty | 865 | **23** | 100.0% [100.0%, 100.0%] |
| dysuria_true | 1481 | **45** | 0.0% [0.0%, 0.0%] |
| (none) | 2978 | **1** | 100.0% [100.0%, 100.0%] |

### Per-fragment errors (worst first)

Whether errors are spread thinly across many fragments or piled onto a few is the difference
between "the method is too weak" (model work) and "these specific ideas are not learnable from
the data we have" (library work, and these are the fragments to write more of). No intervals:
a fragment is one cluster, so an interval over its own examples measures nothing.

94 of 256 decisive fragments were got wrong at least once.

`tfidf_logreg__shuffled`: 3961 errors across 94 of 256 decisive fragments. Half of them fall on **35** fragments (an even spread would be 47.0); the worst ten carry 16.5% of all errors.

| fragment | library | sub-class | truth | correct | accuracy | predicted as |
|---|---|---|---|---|---|---|
| `dysuria_false:85e13aca` | `dysuria_false` | -- | false | 0/74 | 0.0% | null 74 |
| `dysuria_false:82438593` | `dysuria_false` | -- | false | 0/68 | 0.0% | null 68 |
| `dysuria_false:202255a3` | `dysuria_false` | -- | false | 0/67 | 0.0% | null 67 |
| `dysuria_false:2508af9f` | `dysuria_false` | -- | false | 0/67 | 0.0% | null 67 |
| `dysuria_false:41c43f99` | `dysuria_false` | -- | false | 0/66 | 0.0% | null 66 |
| `dysuria_false:1fa9bf6a` | `dysuria_false` | -- | false | 0/63 | 0.0% | null 63 |
| `dysuria_false:52998403` | `dysuria_false` | -- | false | 0/63 | 0.0% | null 63 |
| `dysuria_false:5837e4e6` | `dysuria_false` | -- | false | 0/63 | 0.0% | null 63 |
| `dysuria_false:78c1ede4` | `dysuria_false` | -- | false | 0/61 | 0.0% | null 61 |
| `dysuria_false:e75c2521` | `dysuria_false` | -- | false | 0/61 | 0.0% | null 61 |
| `dysuria_false:90277b2d` | `dysuria_false` | -- | false | 0/60 | 0.0% | null 60 |
| `dysuria_false:9b29601b` | `dysuria_false` | -- | false | 0/60 | 0.0% | null 60 |
| `dysuria_false:915a7bf7` | `dysuria_false` | -- | false | 0/59 | 0.0% | null 59 |
| `dysuria_false:62636499` | `dysuria_false` | -- | false | 0/58 | 0.0% | null 58 |
| `dysuria_false:d46403bb` | `dysuria_false` | -- | false | 0/58 | 0.0% | null 58 |
| `dysuria_false:43aa9d18` | `dysuria_false` | -- | false | 0/57 | 0.0% | null 57 |
| `dysuria_false:f3a29d90` | `dysuria_false` | -- | false | 0/57 | 0.0% | null 57 |
| `dysuria_false:18791ae3` | `dysuria_false` | -- | false | 0/56 | 0.0% | null 56 |
| `dysuria_false:47348026` | `dysuria_false` | -- | false | 0/56 | 0.0% | null 56 |
| `dysuria_false:d3769665` | `dysuria_false` | -- | false | 0/56 | 0.0% | null 56 |
| `dysuria_false:4299d111` | `dysuria_false` | -- | false | 0/55 | 0.0% | null 55 |
| `dysuria_false:70ff0f9d` | `dysuria_false` | -- | false | 0/55 | 0.0% | null 55 |
| `dysuria_false:502574f5` | `dysuria_false` | -- | false | 0/54 | 0.0% | null 54 |
| `dysuria_false:1c30e825` | `dysuria_false` | -- | false | 0/53 | 0.0% | null 53 |
| `dysuria_false:7fcddee5` | `dysuria_false` | -- | false | 0/53 | 0.0% | null 53 |
| `dysuria_false:9a3ed060` | `dysuria_false` | -- | false | 0/53 | 0.0% | null 53 |
| `dysuria_false:90df50ee` | `dysuria_false` | -- | false | 0/51 | 0.0% | null 51 |
| `dysuria_false:ab9389ac` | `dysuria_false` | -- | false | 0/50 | 0.0% | null 50 |
| `dysuria_false:b2d71275` | `dysuria_false` | -- | false | 0/50 | 0.0% | null 50 |
| `dysuria_false:3ce959c2` | `dysuria_false` | -- | false | 0/49 | 0.0% | null 49 |
| `dysuria_false:1c5be177` | `dysuria_false` | -- | false | 0/48 | 0.0% | null 48 |
| `dysuria_true:93845aa6` | `dysuria_true` | -- | true | 0/48 | 0.0% | null 48 |
| `dysuria_false:79a25459` | `dysuria_false` | -- | false | 0/47 | 0.0% | null 47 |
| `dysuria_false:64f15eeb` | `dysuria_false` | -- | false | 0/46 | 0.0% | null 46 |
| `dysuria_false:ca382087` | `dysuria_false` | -- | false | 0/44 | 0.0% | null 44 |
| `dysuria_true:28c7bf7e` | `dysuria_true` | -- | true | 0/44 | 0.0% | null 44 |
| `dysuria_true:4694eaab` | `dysuria_true` | -- | true | 0/44 | 0.0% | null 44 |
| `dysuria_true:81b6882e` | `dysuria_true` | -- | true | 0/44 | 0.0% | null 44 |
| `dysuria_true:8ee469c9` | `dysuria_true` | -- | true | 0/44 | 0.0% | null 44 |
| `dysuria_false:b58ab061` | `dysuria_false` | -- | false | 0/43 | 0.0% | null 43 |

*54 further fragments with at least one error are in the JSON sidecar; every fragment is there regardless of score.*

## `arm_a_probe`

Frozen `roberta-base`, mean-pooled, with a `Linear(768, 3)` probe over the cached embeddings (2,307 parameters). The encoder learns nothing; only the probe is fitted. Expected to handle clear positives, clear negatives and `null_structural`, and to do badly on the four hard `null` sub-classes, which turn on compositional scope that a single pooled vector blurs. That is the predicted result rather than a fault, and it is what makes Arm B necessary: a weak probe cannot distinguish "the libraries are the bottleneck" from "the method is too weak".

Decision-rule margins selected per fold (on each fold's own validation split): 0.0, 0.05.

*Confusion matrix, raw argmax*

|  | pred false | pred true | pred null | total |
|---|---|---|---|---|
| **truth false** | 2037 | 38 | 404 | 2479 |
| **truth true** | 58 | 996 | 427 | 1481 |
| **truth null** | 134 | 214 | 5692 | 6040 |
| **total** | 2229 | 1248 | 6523 | 10000 |

`null -> true`: 214 of 6040 truly-null examples (3.54%).

*Confusion matrix, after the decision rule*

|  | pred false | pred true | pred null | total |
|---|---|---|---|---|
| **truth false** | 2038 | 36 | 405 | 2479 |
| **truth true** | 61 | 990 | 430 | 1481 |
| **truth null** | 134 | 214 | 5692 | 6040 |
| **total** | 2233 | 1240 | 6527 | 10000 |

`null -> true`: 214 of 6040 truly-null examples (3.54%).

### Per class, after the decision rule

| class | support | predicted | precision | recall | F1 |
|---|---|---|---|---|---|
| `false` | 2479 | 2233 | 91.3% | 82.2% | 86.5% |
| `true` | 1481 | 1240 | 79.8% | 66.8% | 72.8% |
| `null` | 6040 | 6527 | 87.2% | 94.2% | 90.6% |

### By label mode

| label mode | n | eff n | accuracy [95% CI] |
|---|---|---|---|
| false | 2479 | **47** | 82.2% [75.2%, 88.1%] |
| null_ambiguous | 3062 | **90** | 90.1% [86.8%, 93.3%] |
| null_structural | 2978 | **1** | 98.5% [98.5%, 98.5%] |
| true | 1481 | **45** | 66.8% [57.2%, 75.0%] |

### By null sub-class

| sub-class | n | eff n | null recall [95% CI] |
|---|---|---|---|
| hedged | 785 | **20** | 82.8% [76.7%, 89.5%] |
| historical | 654 | **19** | 95.6% [92.8%, 98.0%] |
| metaphor | 758 | **28** | 92.3% [85.3%, 98.6%] |
| third_party | 865 | **23** | 90.6% [84.8%, 95.5%] |

### By fragment library

| library | n | eff n | accuracy [95% CI] |
|---|---|---|---|
| dysuria_false | 2479 | **47** | 82.2% [75.2%, 88.1%] |
| dysuria_null_hedged | 785 | **20** | 82.8% [76.7%, 89.5%] |
| dysuria_null_historical | 654 | **19** | 95.6% [92.8%, 98.0%] |
| dysuria_null_metaphor | 758 | **28** | 92.3% [85.3%, 98.6%] |
| dysuria_null_thirdparty | 865 | **23** | 90.6% [84.8%, 95.5%] |
| dysuria_true | 1481 | **45** | 66.8% [57.2%, 75.0%] |
| (none) | 2978 | **1** | 98.5% [98.5%, 98.5%] |

### Per-fragment errors (worst first)

Whether errors are spread thinly across many fragments or piled onto a few is the difference
between "the method is too weak" (model work) and "these specific ideas are not learnable from
the data we have" (library work, and these are the fragments to write more of). No intervals:
a fragment is one cluster, so an interval over its own examples measures nothing.

146 of 256 decisive fragments were got wrong at least once.

`arm_a_probe`: 1235 errors across 146 of 256 decisive fragments. Half of them fall on **24** fragments (an even spread would be 73.0); the worst ten carry 28.3% of all errors.

| fragment | library | sub-class | truth | correct | accuracy | predicted as |
|---|---|---|---|---|---|---|
| `dysuria_true:146d5e49` | `dysuria_true` | -- | true | 1/34 | 2.9% | false 1, true 1, null 32 |
| `dysuria_true:b898c2de` | `dysuria_true` | -- | true | 2/34 | 5.9% | true 2, null 32 |
| `dysuria_false:b2d71275` | `dysuria_false` | -- | false | 3/50 | 6.0% | false 3, null 47 |
| `dysuria_false:ffc68e8d` | `dysuria_false` | -- | false | 3/39 | 7.7% | false 3, true 2, null 34 |
| `dysuria_true:36a17090` | `dysuria_true` | -- | true | 2/26 | 7.7% | false 4, true 2, null 20 |
| `dysuria_true:2e98f278` | `dysuria_true` | -- | true | 2/24 | 8.3% | true 2, null 22 |
| `dysuria_true:0d7321c0` | `dysuria_true` | -- | true | 4/33 | 12.1% | false 3, true 4, null 26 |
| `dysuria_true:f02ba872` | `dysuria_true` | -- | true | 6/40 | 15.0% | true 6, null 34 |
| `dysuria_false:9a3ed060` | `dysuria_false` | -- | false | 8/53 | 15.1% | false 8, null 45 |
| `dysuria_true:c17c33dd` | `dysuria_true` | -- | true | 5/24 | 20.8% | false 5, true 5, null 14 |
| `dysuria_false:64f15eeb` | `dysuria_false` | -- | false | 12/46 | 26.1% | false 12, true 8, null 26 |
| `dysuria_true:7c711665` | `dysuria_true` | -- | true | 10/35 | 28.6% | false 14, true 10, null 11 |
| `dysuria_null_thirdparty:575791a4` | `dysuria_null_thirdparty` | third_party | null | 8/25 | 32.0% | false 1, true 16, null 8 |
| `dysuria_true:71544e46` | `dysuria_true` | -- | true | 13/37 | 35.1% | false 2, true 13, null 22 |
| `dysuria_true:6d04ed35` | `dysuria_true` | -- | true | 8/21 | 38.1% | true 8, null 13 |
| `dysuria_null_metaphor:90f14a54` | `dysuria_null_metaphor` | metaphor | null | 13/34 | 38.2% | true 21, null 13 |
| `dysuria_null_hedged:249a7342` | `dysuria_null_hedged` | hedged | null | 11/27 | 40.7% | true 16, null 11 |
| `dysuria_true:89e28e2d` | `dysuria_true` | -- | true | 11/26 | 42.3% | false 3, true 11, null 12 |
| `dysuria_true:abed15dd` | `dysuria_true` | -- | true | 14/33 | 42.4% | true 14, null 19 |
| `dysuria_true:37c0a85e` | `dysuria_true` | -- | true | 13/28 | 46.4% | false 2, true 13, null 13 |
| `dysuria_false:3ce959c2` | `dysuria_false` | -- | false | 23/49 | 46.9% | false 23, null 26 |
| `dysuria_false:5837e4e6` | `dysuria_false` | -- | false | 30/63 | 47.6% | false 30, true 3, null 30 |
| `dysuria_null_hedged:7e24cdf5` | `dysuria_null_hedged` | hedged | null | 10/21 | 47.6% | false 3, true 8, null 10 |
| `dysuria_null_metaphor:83929c02` | `dysuria_null_metaphor` | metaphor | null | 16/32 | 50.0% | true 16, null 16 |
| `dysuria_true:c3f7adf1` | `dysuria_true` | -- | true | 16/32 | 50.0% | false 4, true 16, null 12 |
| `dysuria_null_thirdparty:15e1b2f0` | `dysuria_null_thirdparty` | third_party | null | 11/22 | 50.0% | false 1, true 10, null 11 |
| `dysuria_true:83eb7cdc` | `dysuria_true` | -- | true | 17/33 | 51.5% | true 17, null 16 |
| `dysuria_null_metaphor:91b6dbda` | `dysuria_null_metaphor` | metaphor | null | 13/25 | 52.0% | true 12, null 13 |
| `dysuria_null_hedged:697a9433` | `dysuria_null_hedged` | hedged | null | 16/29 | 55.2% | false 6, true 7, null 16 |
| `dysuria_null_thirdparty:05d88e6a` | `dysuria_null_thirdparty` | third_party | null | 5/9 | 55.6% | true 4, null 5 |
| `dysuria_true:985d61a2` | `dysuria_true` | -- | true | 18/32 | 56.2% | true 18, null 14 |
| `dysuria_null_hedged:b1ae1f9d` | `dysuria_null_hedged` | hedged | null | 19/33 | 57.6% | false 6, true 8, null 19 |
| `dysuria_true:aadce996` | `dysuria_true` | -- | true | 16/27 | 59.3% | false 1, true 16, null 10 |
| `dysuria_true:933cf995` | `dysuria_true` | -- | true | 21/34 | 61.8% | true 21, null 13 |
| `dysuria_true:b87ef0cf` | `dysuria_true` | -- | true | 19/30 | 63.3% | false 1, true 19, null 10 |
| `dysuria_null_thirdparty:5d0d98cb` | `dysuria_null_thirdparty` | third_party | null | 18/28 | 64.3% | true 10, null 18 |
| `dysuria_null_historical:9ee1eafc` | `dysuria_null_historical` | historical | null | 11/17 | 64.7% | true 6, null 11 |
| `dysuria_null_hedged:bea219da` | `dysuria_null_hedged` | hedged | null | 15/23 | 65.2% | true 8, null 15 |
| `dysuria_true:63f5b24c` | `dysuria_true` | -- | true | 16/24 | 66.7% | true 16, null 8 |
| `dysuria_null_hedged:89b32ba7` | `dysuria_null_hedged` | hedged | null | 12/18 | 66.7% | false 3, true 3, null 12 |

*106 further fragments with at least one error are in the JSON sidecar; every fragment is there regardless of score.*

## `arm_b_finetune`

`roberta-base` with **every layer unfrozen**, mean-pooled, with the same `Linear(768, 3)` head -- 110M trainable parameters against Arm A's 2,307. Three epochs at batch 32, learning rate 2e-5, 10% linear warmup, AdamW, fp32. No gradient checkpointing, no 8-bit optimiser, no LoRA, no gradient accumulation: the full model fits in 12GB with room to spare, so anything that reads like a compute compromise would be a mistake rather than a saving. This is the arm that separates "the fragment libraries are the bottleneck" from "the method is too weak": if a fully fine-tuned encoder still cannot read third-party attribution, tense or metaphor, the limit is in the ideas the libraries contain and the fix is library work, not model work.

Decision-rule margins selected per fold (on each fold's own validation split): 0.0, 0.1, 0.4, 0.9.

*Confusion matrix, raw argmax*

|  | pred false | pred true | pred null | total |
|---|---|---|---|---|
| **truth false** | 2441 | 0 | 38 | 2479 |
| **truth true** | 1 | 1387 | 93 | 1481 |
| **truth null** | 10 | 221 | 5809 | 6040 |
| **total** | 2452 | 1608 | 5940 | 10000 |

`null -> true`: 221 of 6040 truly-null examples (3.66%).

*Confusion matrix, after the decision rule*

|  | pred false | pred true | pred null | total |
|---|---|---|---|---|
| **truth false** | 2441 | 0 | 38 | 2479 |
| **truth true** | 2 | 1378 | 101 | 1481 |
| **truth null** | 10 | 211 | 5819 | 6040 |
| **total** | 2453 | 1589 | 5958 | 10000 |

`null -> true`: 211 of 6040 truly-null examples (3.49%).

### Per class, after the decision rule

| class | support | predicted | precision | recall | F1 |
|---|---|---|---|---|---|
| `false` | 2479 | 2453 | 99.5% | 98.5% | 99.0% |
| `true` | 1481 | 1589 | 86.7% | 93.0% | 89.8% |
| `null` | 6040 | 5958 | 97.7% | 96.3% | 97.0% |

### By label mode

| label mode | n | eff n | accuracy [95% CI] |
|---|---|---|---|
| false | 2479 | **47** | 98.5% [95.2%, 100.0%] |
| null_ambiguous | 3062 | **90** | 92.9% [88.0%, 96.9%] |
| null_structural | 2978 | **1** | 99.9% [99.9%, 99.9%] |
| true | 1481 | **45** | 93.0% [86.0%, 98.5%] |

### By null sub-class

| sub-class | n | eff n | null recall [95% CI] |
|---|---|---|---|
| hedged | 785 | **20** | 84.5% [74.4%, 94.7%] |
| historical | 654 | **19** | 99.7% [99.0%, 100.0%] |
| metaphor | 758 | **28** | 91.8% [80.4%, 100.0%] |
| third_party | 865 | **23** | 96.4% [89.5%, 100.0%] |

### By fragment library

| library | n | eff n | accuracy [95% CI] |
|---|---|---|---|
| dysuria_false | 2479 | **47** | 98.5% [95.2%, 100.0%] |
| dysuria_null_hedged | 785 | **20** | 84.5% [74.4%, 94.7%] |
| dysuria_null_historical | 654 | **19** | 99.7% [99.0%, 100.0%] |
| dysuria_null_metaphor | 758 | **28** | 91.8% [80.4%, 100.0%] |
| dysuria_null_thirdparty | 865 | **23** | 96.4% [89.5%, 100.0%] |
| dysuria_true | 1481 | **45** | 93.0% [86.0%, 98.5%] |
| (none) | 2978 | **1** | 99.9% [99.9%, 99.9%] |

### Per-fragment errors (worst first)

Whether errors are spread thinly across many fragments or piled onto a few is the difference
between "the method is too weak" (model work) and "these specific ideas are not learnable from
the data we have" (library work, and these are the fragments to write more of). No intervals:
a fragment is one cluster, so an interval over its own examples measures nothing.

28 of 256 decisive fragments were got wrong at least once.

`arm_b_finetune`: 358 errors across 28 of 256 decisive fragments. Half of them fall on **6** fragments (an even spread would be 14.0); the worst ten carry 76.8% of all errors.

| fragment | library | sub-class | truth | correct | accuracy | predicted as |
|---|---|---|---|---|---|---|
| `dysuria_null_metaphor:83929c02` | `dysuria_null_metaphor` | metaphor | null | 0/32 | 0.0% | true 32 |
| `dysuria_true:985d61a2` | `dysuria_true` | -- | true | 0/32 | 0.0% | null 32 |
| `dysuria_null_hedged:249a7342` | `dysuria_null_hedged` | hedged | null | 0/27 | 0.0% | true 27 |
| `dysuria_null_metaphor:91b6dbda` | `dysuria_null_metaphor` | metaphor | null | 0/25 | 0.0% | true 25 |
| `dysuria_null_hedged:5bf05464` | `dysuria_null_hedged` | hedged | null | 0/15 | 0.0% | false 2, true 13 |
| `dysuria_false:ffc68e8d` | `dysuria_false` | -- | false | 1/39 | 2.6% | false 1, null 38 |
| `dysuria_null_hedged:b1ae1f9d` | `dysuria_null_hedged` | hedged | null | 1/33 | 3.0% | true 32, null 1 |
| `dysuria_null_hedged:7e24cdf5` | `dysuria_null_hedged` | hedged | null | 1/21 | 4.8% | true 20, null 1 |
| `dysuria_true:a28e78a6` | `dysuria_true` | -- | true | 2/30 | 6.7% | true 2, null 28 |
| `dysuria_null_thirdparty:575791a4` | `dysuria_null_thirdparty` | third_party | null | 3/25 | 12.0% | true 22, null 3 |
| `dysuria_null_hedged:bea219da` | `dysuria_null_hedged` | hedged | null | 5/23 | 21.7% | true 18, null 5 |
| `dysuria_true:146d5e49` | `dysuria_true` | -- | true | 15/34 | 44.1% | true 15, null 19 |
| `dysuria_null_thirdparty:2fd8fdb5` | `dysuria_null_thirdparty` | third_party | null | 8/14 | 57.1% | true 6, null 8 |
| `dysuria_true:63f5b24c` | `dysuria_true` | -- | true | 15/24 | 62.5% | true 15, null 9 |
| `dysuria_null_hedged:c6d1a9ae` | `dysuria_null_hedged` | hedged | null | 10/15 | 66.7% | true 5, null 10 |
| `dysuria_null_metaphor:732d4a18` | `dysuria_null_metaphor` | metaphor | null | 13/18 | 72.2% | true 5, null 13 |
| `dysuria_null_hedged:ec574b54` | `dysuria_null_hedged` | hedged | null | 8/11 | 72.7% | true 3, null 8 |
| `dysuria_null_thirdparty:4e732310` | `dysuria_null_thirdparty` | third_party | null | 14/17 | 82.4% | false 2, true 1, null 14 |
| `dysuria_true:2e98f278` | `dysuria_true` | -- | true | 20/24 | 83.3% | true 20, null 4 |
| `dysuria_null_hedged:89b32ba7` | `dysuria_null_hedged` | hedged | null | 16/18 | 88.9% | false 2, null 16 |
| `dysuria_true:37c0a85e` | `dysuria_true` | -- | true | 25/28 | 89.3% | true 25, null 3 |
| `dysuria_null_historical:e7c8cfef` | `dysuria_null_historical` | historical | null | 23/25 | 92.0% | true 2, null 23 |
| `dysuria_true:614d867c` | `dysuria_true` | -- | true | 28/30 | 93.3% | false 2, true 28 |
| `dysuria_true:abed15dd` | `dysuria_true` | -- | true | 31/33 | 93.9% | true 31, null 2 |
| `dysuria_true:6d04ed35` | `dysuria_true` | -- | true | 20/21 | 95.2% | true 20, null 1 |
| `dysuria_true:0d7321c0` | `dysuria_true` | -- | true | 32/33 | 97.0% | true 32, null 1 |
| `dysuria_true:b898c2de` | `dysuria_true` | -- | true | 33/34 | 97.1% | true 33, null 1 |
| `dysuria_true:8f0ade4e` | `dysuria_true` | -- | true | 39/40 | 97.5% | true 39, null 1 |

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
| false | 2479 | **47** | 0.0% [0.0%, 0.0%] |
| null_ambiguous | 3062 | **90** | 100.0% [100.0%, 100.0%] |
| null_structural | 2978 | **1** | 100.0% [100.0%, 100.0%] |
| true | 1481 | **45** | 0.0% [0.0%, 0.0%] |

### By null sub-class

| sub-class | n | eff n | null recall [95% CI] |
|---|---|---|---|
| hedged | 785 | **20** | 100.0% [100.0%, 100.0%] |
| historical | 654 | **19** | 100.0% [100.0%, 100.0%] |
| metaphor | 758 | **28** | 100.0% [100.0%, 100.0%] |
| third_party | 865 | **23** | 100.0% [100.0%, 100.0%] |

### By fragment library

| library | n | eff n | accuracy [95% CI] |
|---|---|---|---|
| dysuria_false | 2479 | **47** | 0.0% [0.0%, 0.0%] |
| dysuria_null_hedged | 785 | **20** | 100.0% [100.0%, 100.0%] |
| dysuria_null_historical | 654 | **19** | 100.0% [100.0%, 100.0%] |
| dysuria_null_metaphor | 758 | **28** | 100.0% [100.0%, 100.0%] |
| dysuria_null_thirdparty | 865 | **23** | 100.0% [100.0%, 100.0%] |
| dysuria_true | 1481 | **45** | 0.0% [0.0%, 0.0%] |
| (none) | 2978 | **1** | 100.0% [100.0%, 100.0%] |

### Per-fragment errors (worst first)

Whether errors are spread thinly across many fragments or piled onto a few is the difference
between "the method is too weak" (model work) and "these specific ideas are not learnable from
the data we have" (library work, and these are the fragments to write more of). No intervals:
a fragment is one cluster, so an interval over its own examples measures nothing.

92 of 256 decisive fragments were got wrong at least once.

`arm_b_finetune__shuffled`: 3960 errors across 92 of 256 decisive fragments. Half of them fall on **35** fragments (an even spread would be 46.0); the worst ten carry 16.5% of all errors.

| fragment | library | sub-class | truth | correct | accuracy | predicted as |
|---|---|---|---|---|---|---|
| `dysuria_false:85e13aca` | `dysuria_false` | -- | false | 0/74 | 0.0% | null 74 |
| `dysuria_false:82438593` | `dysuria_false` | -- | false | 0/68 | 0.0% | null 68 |
| `dysuria_false:202255a3` | `dysuria_false` | -- | false | 0/67 | 0.0% | null 67 |
| `dysuria_false:2508af9f` | `dysuria_false` | -- | false | 0/67 | 0.0% | null 67 |
| `dysuria_false:41c43f99` | `dysuria_false` | -- | false | 0/66 | 0.0% | null 66 |
| `dysuria_false:1fa9bf6a` | `dysuria_false` | -- | false | 0/63 | 0.0% | null 63 |
| `dysuria_false:52998403` | `dysuria_false` | -- | false | 0/63 | 0.0% | null 63 |
| `dysuria_false:5837e4e6` | `dysuria_false` | -- | false | 0/63 | 0.0% | null 63 |
| `dysuria_false:78c1ede4` | `dysuria_false` | -- | false | 0/61 | 0.0% | null 61 |
| `dysuria_false:e75c2521` | `dysuria_false` | -- | false | 0/61 | 0.0% | null 61 |
| `dysuria_false:90277b2d` | `dysuria_false` | -- | false | 0/60 | 0.0% | null 60 |
| `dysuria_false:9b29601b` | `dysuria_false` | -- | false | 0/60 | 0.0% | null 60 |
| `dysuria_false:915a7bf7` | `dysuria_false` | -- | false | 0/59 | 0.0% | null 59 |
| `dysuria_false:62636499` | `dysuria_false` | -- | false | 0/58 | 0.0% | null 58 |
| `dysuria_false:d46403bb` | `dysuria_false` | -- | false | 0/58 | 0.0% | null 58 |
| `dysuria_false:43aa9d18` | `dysuria_false` | -- | false | 0/57 | 0.0% | null 57 |
| `dysuria_false:f3a29d90` | `dysuria_false` | -- | false | 0/57 | 0.0% | null 57 |
| `dysuria_false:18791ae3` | `dysuria_false` | -- | false | 0/56 | 0.0% | null 56 |
| `dysuria_false:47348026` | `dysuria_false` | -- | false | 0/56 | 0.0% | null 56 |
| `dysuria_false:d3769665` | `dysuria_false` | -- | false | 0/56 | 0.0% | null 56 |
| `dysuria_false:4299d111` | `dysuria_false` | -- | false | 0/55 | 0.0% | null 55 |
| `dysuria_false:70ff0f9d` | `dysuria_false` | -- | false | 0/55 | 0.0% | null 55 |
| `dysuria_false:1548b49b` | `dysuria_false` | -- | false | 0/54 | 0.0% | null 54 |
| `dysuria_false:502574f5` | `dysuria_false` | -- | false | 0/54 | 0.0% | null 54 |
| `dysuria_false:1c30e825` | `dysuria_false` | -- | false | 0/53 | 0.0% | null 53 |
| `dysuria_false:7fcddee5` | `dysuria_false` | -- | false | 0/53 | 0.0% | null 53 |
| `dysuria_false:9a3ed060` | `dysuria_false` | -- | false | 0/53 | 0.0% | null 53 |
| `dysuria_false:90df50ee` | `dysuria_false` | -- | false | 0/51 | 0.0% | null 51 |
| `dysuria_false:ab9389ac` | `dysuria_false` | -- | false | 0/50 | 0.0% | null 50 |
| `dysuria_false:b2d71275` | `dysuria_false` | -- | false | 0/50 | 0.0% | null 50 |
| `dysuria_false:3ce959c2` | `dysuria_false` | -- | false | 0/49 | 0.0% | null 49 |
| `dysuria_false:1c5be177` | `dysuria_false` | -- | false | 0/48 | 0.0% | null 48 |
| `dysuria_true:93845aa6` | `dysuria_true` | -- | true | 0/48 | 0.0% | null 48 |
| `dysuria_false:79a25459` | `dysuria_false` | -- | false | 0/47 | 0.0% | null 47 |
| `dysuria_false:64f15eeb` | `dysuria_false` | -- | false | 0/46 | 0.0% | null 46 |
| `dysuria_false:ca382087` | `dysuria_false` | -- | false | 0/44 | 0.0% | null 44 |
| `dysuria_true:28c7bf7e` | `dysuria_true` | -- | true | 0/44 | 0.0% | null 44 |
| `dysuria_true:4694eaab` | `dysuria_true` | -- | true | 0/44 | 0.0% | null 44 |
| `dysuria_true:81b6882e` | `dysuria_true` | -- | true | 0/44 | 0.0% | null 44 |
| `dysuria_true:8ee469c9` | `dysuria_true` | -- | true | 0/44 | 0.0% | null 44 |

*52 further fragments with at least one error are in the JSON sidecar; every fragment is there regardless of score.*

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
| 0 | 10000 | 2000 | 2000 | 0.0 | 61.4% | 61.4% | 28.6% | 0.00% |
| 1 | 10000 | 2000 | 2000 | 0.0 | 62.1% | 62.1% | 30.8% | 0.00% |
| 2 | 10000 | 2000 | 2000 | 0.0 | 61.7% | 61.7% | 29.3% | 0.00% |
| 3 | 10000 | 2000 | 2000 | 0.0 | 63.3% | 63.3% | 33.0% | 0.00% |
| 4 | 10000 | 2000 | 2000 | 0.0 | 61.6% | 61.6% | 33.7% | 0.00% |

### `tfidf_logreg`

| fold | train n | val n | test n | margin | acc (raw) | acc (ruled) | macro-F1 | null->true |
|---|---|---|---|---|---|---|---|---|
| 0 | 10000 | 2000 | 2000 | 0.0 | 76.5% | 76.5% | 66.1% | 5.54% |
| 1 | 10000 | 2000 | 2000 | 0.0 | 79.0% | 79.0% | 67.0% | 0.83% |
| 2 | 10000 | 2000 | 2000 | 0.0 | 81.7% | 81.7% | 69.6% | 0.75% |
| 3 | 10000 | 2000 | 2000 | 0.0 | 79.0% | 79.0% | 65.5% | 2.80% |
| 4 | 10000 | 2000 | 2000 | 0.0 | 80.0% | 80.0% | 66.0% | 0.00% |

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
| 1 | 10000 | 2000 | 2000 | 0.0 | 60.2% | 60.2% | 25.2% | 0.00% |
| 2 | 10000 | 2000 | 2000 | 0.0 | 60.4% | 60.4% | 25.1% | 0.00% |
| 3 | 10000 | 2000 | 2000 | 0.0 | 60.8% | 60.8% | 25.2% | 0.00% |
| 4 | 10000 | 2000 | 2000 | 0.0 | 60.2% | 60.2% | 25.1% | 0.00% |

### `arm_a_probe`

| fold | train n | val n | test n | margin | acc (raw) | acc (ruled) | macro-F1 | null->true |
|---|---|---|---|---|---|---|---|---|
| 0 | 10000 | 2000 | 2000 | 0.0 | 80.2% | 80.2% | 74.6% | 8.27% |
| 1 | 10000 | 2000 | 2000 | 0.0 | 89.1% | 89.1% | 86.2% | 3.08% |
| 2 | 10000 | 2000 | 2000 | 0.0 | 89.4% | 89.4% | 86.3% | 4.72% |
| 3 | 10000 | 2000 | 2000 | 0.0 | 91.7% | 91.7% | 89.3% | 0.74% |
| 4 | 10000 | 2000 | 2000 | 0.05 | 85.9% | 85.6% | 80.0% | 0.91% |

### `arm_b_finetune`

| fold | train n | val n | test n | margin | acc (raw) | acc (ruled) | macro-F1 | null->true |
|---|---|---|---|---|---|---|---|---|
| 0 | 10000 | 2000 | 2000 | 0.0 | 94.5% | 94.5% | 93.1% | 7.69% |
| 1 | 10000 | 2000 | 2000 | 0.0 | 96.9% | 96.9% | 95.8% | 2.16% |
| 2 | 10000 | 2000 | 2000 | 0.9 | 94.8% | 95.0% | 93.5% | 5.88% |
| 3 | 10000 | 2000 | 2000 | 0.1 | 98.7% | 98.7% | 98.2% | 1.73% |
| 4 | 10000 | 2000 | 2000 | 0.4 | 96.9% | 96.8% | 96.3% | 0.00% |

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

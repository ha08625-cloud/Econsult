# Encoder training: evaluation report

*Generated 2026-08-16T09:28:20+00:00.*

|  |  |
|---|---|
| signal | `urinary_frequency_present` |
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
| artefacts | `models/encoder/urinary_frequency_present/arm_b_finetune` |
| weights | `models/encoder/urinary_frequency_present/arm_b_finetune/weights -- ~440MB per fold, not committed` |
| model revision | `e2da8e2f811d1448a5b465c236feacd80ffbac7b` |
| revision pinned | `False` |
| tokeniser lowercases | `False` |
| tokeniser vocab size | `50265` |
| tokeniser discards casing | `False` |
| cluster tag coverage | `0 of 7 libraries carry cluster markers; 302 of 302 fragments are in libraries with none` |
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
> Untagged: `urinary_frequency_false`, `urinary_frequency_null_adjacent`, `urinary_frequency_null_hedged`, `urinary_frequency_null_historical`, `urinary_frequency_null_metaphor`, `urinary_frequency_null_thirdparty`, `urinary_frequency_true`.

Tagging cannot inflate a number -- `[c01]` siblings are forced into one cluster and one
split, so it only ever *reduces* `eff n`, correctly, by stopping the same idea being
counted twice. The asymmetry is what makes cross-signal comparison unsafe: a fully
tagged signal is penalised for being honest and an untagged one is flattered by default,
so a ranking across signals is partly an artefact of this column.

| library | fragments | tagged | coverage |
|---|---|---|---|
| `urinary_frequency_false` | 46 | 0 | 0.0% |
| `urinary_frequency_null_adjacent` | 40 | 0 | 0.0% |
| `urinary_frequency_null_hedged` | 42 | 0 | 0.0% |
| `urinary_frequency_null_historical` | 40 | 0 | 0.0% |
| `urinary_frequency_null_metaphor` | 44 | 0 | 0.0% |
| `urinary_frequency_null_thirdparty` | 44 | 0 | 0.0% |
| `urinary_frequency_true` | 46 | 0 | 0.0% |

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
| `majority_class` | baseline | 7022 | **302** | 43.6% [37.6%, 50.8%] | 20.2% [18.2%, 22.4%] | 60.4% | 60.4% +/- 0.2% |
| `length_only` | baseline | 7022 | **302** | 43.6% [37.6%, 50.8%] | 20.2% [18.2%, 22.4%] | 60.4% | 60.4% +/- 0.2% |
| `tfidf_logreg` | baseline | 7022 | **302** | 59.9% [54.4%, 65.9%] | 49.1% [43.2%, 54.5%] | 71.7% | 71.7% +/- 3.5% |
| `length_only__shuffled` | negative control | 7022 | **302** | 43.6% [37.6%, 50.8%] | 20.2% [18.2%, 22.4%] | 60.4% | 60.4% +/- 0.2% |
| `tfidf_logreg__shuffled` | negative control | 7022 | **302** | 43.6% [37.6%, 50.7%] | 20.2% [18.2%, 22.4%] | 60.4% | 60.4% +/- 0.2% |
| `arm_a_probe` | probe | 7022 | **302** | 67.8% [63.5%, 72.2%] | 63.5% [58.5%, 68.0%] | 76.7% | 76.7% +/- 2.6% |
| `arm_b_finetune` | finetune | 7022 | **302** | 85.3% [80.8%, 89.5%] | 82.7% [77.1%, 87.5%] | 89.7% | 89.7% +/- 5.0% |
| `arm_b_finetune__shuffled` | negative control | 7022 | **302** | 43.6% [37.6%, 50.8%] | 20.2% [18.2%, 22.4%] | 60.4% | 60.4% +/- 0.2% |

### Null sub-class recall, pooled

The table the whole exercise exists for: how often each hard `null` sub-class is correctly
left as `null`. `eff n` here is the sub-class's entire library, which a single split cannot reach.

**Never read this table on its own.** Every example in these slices is truly `null`, so a model
that always answers `null` scores 100% across the row -- as `majority_class` below does. High
null recall is only a finding when the `true` and `false` recalls in the per-class tables are
high too.

| model | adjacent | attribution | hedged | historical | metaphor | third_party |
|---|---|---|---|---|---|---|
| `majority_class` | 100.0% [100.0%, 100.0%] (eff n 40) | -- | 100.0% [100.0%, 100.0%] (eff n 42) | 100.0% [100.0%, 100.0%] (eff n 40) | 100.0% [100.0%, 100.0%] (eff n 44) | 100.0% [100.0%, 100.0%] (eff n 44) |
| `length_only` | 100.0% [100.0%, 100.0%] (eff n 40) | -- | 100.0% [100.0%, 100.0%] (eff n 42) | 100.0% [100.0%, 100.0%] (eff n 40) | 100.0% [100.0%, 100.0%] (eff n 44) | 100.0% [100.0%, 100.0%] (eff n 44) |
| `tfidf_logreg` | 96.4% [91.0%, 99.7%] (eff n 40) | -- | 90.5% [84.2%, 95.6%] (eff n 42) | 98.0% [96.0%, 99.5%] (eff n 40) | 97.8% [95.8%, 99.4%] (eff n 44) | 83.3% [74.8%, 90.8%] (eff n 44) |
| `length_only__shuffled` | 100.0% [100.0%, 100.0%] (eff n 40) | -- | 100.0% [100.0%, 100.0%] (eff n 42) | 100.0% [100.0%, 100.0%] (eff n 40) | 100.0% [100.0%, 100.0%] (eff n 44) | 100.0% [100.0%, 100.0%] (eff n 44) |
| `tfidf_logreg__shuffled` | 100.0% [100.0%, 100.0%] (eff n 40) | -- | 100.0% [100.0%, 100.0%] (eff n 42) | 99.8% [99.4%, 100.0%] (eff n 40) | 100.0% [100.0%, 100.0%] (eff n 44) | 99.7% [99.1%, 100.0%] (eff n 44) |
| `arm_a_probe` | 90.6% [86.8%, 94.2%] (eff n 40) | -- | 77.1% [69.9%, 83.9%] (eff n 42) | 90.8% [85.6%, 95.3%] (eff n 40) | 92.3% [86.2%, 97.2%] (eff n 44) | 80.0% [73.0%, 86.0%] (eff n 44) |
| `arm_b_finetune` | 94.7% [88.2%, 99.3%] (eff n 40) | -- | 90.2% [81.7%, 96.9%] (eff n 42) | 100.0% [100.0%, 100.0%] (eff n 40) | 95.1% [88.9%, 99.7%] (eff n 44) | 98.8% [97.3%, 99.8%] (eff n 44) |
| `arm_b_finetune__shuffled` | 100.0% [100.0%, 100.0%] (eff n 40) | -- | 100.0% [100.0%, 100.0%] (eff n 42) | 100.0% [100.0%, 100.0%] (eff n 40) | 100.0% [100.0%, 100.0%] (eff n 44) | 100.0% [100.0%, 100.0%] (eff n 44) |

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
| `majority_class` | baseline | 3062 | **210** | 100.0% [100.0%, 100.0%] |
| `length_only` | baseline | 3062 | **210** | 100.0% [100.0%, 100.0%] |
| `tfidf_logreg` | baseline | 3062 | **210** | 93.0% [90.5%, 95.4%] |
| `arm_a_probe` | probe | 3062 | **210** | 86.1% [83.2%, 88.6%] |
| `arm_b_finetune` | finetune | 3062 | **210** | 95.7% [93.0%, 97.8%] |

### 2. The same comparison, paired

Two overlapping intervals do not settle whether one model beats another on the same
examples. McNemar does, over the examples the two disagree about -- read it alongside the
intervals above, never instead of them.

| pair | n | a only | b only | p |
|---|---|---|---|---|
| `majority_class` vs `length_only` | 3062 | 0 | 0 | 1 |
| `majority_class` vs `tfidf_logreg` | 3062 | 223 | 0 | 1.48e-67 |
| `majority_class` vs `arm_a_probe` | 3062 | 432 | 0 | 1.8e-130 |
| `majority_class` vs `arm_b_finetune` | 3062 | 159 | 0 | 2.74e-48 |
| `length_only` vs `tfidf_logreg` | 3062 | 223 | 0 | 1.48e-67 |
| `length_only` vs `arm_a_probe` | 3062 | 432 | 0 | 1.8e-130 |
| `length_only` vs `arm_b_finetune` | 3062 | 159 | 0 | 2.74e-48 |
| `tfidf_logreg` vs `arm_a_probe` | 3062 | 329 | 120 | 1.45e-23 |
| `tfidf_logreg` vs `arm_b_finetune` | 3062 | 121 | 185 | 0.000302 |
| `arm_a_probe` vs `arm_b_finetune` | 3062 | 93 | 366 | 2.45e-39 |

### 3. Where the errors fall

The per-fragment table below, as one number per model. Errors spread thinly across many
fragments say the method is too weak. Errors piled onto a handful say those specific ideas
are not learnable from the data we have -- and the table names them, which is what makes
this the most decision-useful thing in the report.

* `majority_class`: 3960 errors across 92 of 302 decisive fragments. Half of them fall on **30** fragments (an even spread would be 46.0); the worst ten carry 22.7% of all errors.
* `length_only`: 3960 errors across 92 of 302 decisive fragments. Half of them fall on **30** fragments (an even spread would be 46.0); the worst ten carry 22.7% of all errors.
* `tfidf_logreg`: 2815 errors across 143 of 302 decisive fragments. Half of them fall on **30** fragments (an even spread would be 71.5); the worst ten carry 21.8% of all errors.
* `arm_a_probe`: 2260 errors across 204 of 302 decisive fragments. Half of them fall on **32** fragments (an even spread would be 102.0); the worst ten carry 23.0% of all errors.
* `arm_b_finetune`: 1034 errors across 66 of 302 decisive fragments. Half of them fall on **11** fragments (an even spread would be 33.0); the worst ten carry 47.6% of all errors.

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
| `length_only__shuffled` | 60.4% [38.8%, 77.7%] | 25.1% [18.6%, 29.2%] |
| `tfidf_logreg__shuffled` | 60.4% [38.8%, 77.7%] | 25.1% [18.6%, 29.2%] |
| `arm_b_finetune__shuffled` | 60.4% [38.8%, 77.7%] | 25.1% [18.6%, 29.2%] |

## Paired comparisons (McNemar, raw argmax)

Exact two-sided McNemar over the examples the two models disagree about. Pairing unit is the
example, not the cluster -- see the limitations.

| pair | slice | n | a only | b only | p |
|---|---|---|---|---|---|
| `majority_class` vs `length_only` | overall | 10000 | 0 | 0 | 1 |
| `majority_class` vs `length_only` | null_ambiguous | 3062 | 0 | 0 | 1 |
| `majority_class` vs `tfidf_logreg` | overall | 10000 | 244 | 1364 | 1.18e-188 |
| `majority_class` vs `tfidf_logreg` | null_ambiguous | 3062 | 223 | 0 | 1.48e-67 |
| `majority_class` vs `arm_a_probe` | overall | 10000 | 506 | 2131 | 7.14e-236 |
| `majority_class` vs `arm_a_probe` | null_ambiguous | 3062 | 432 | 0 | 1.8e-130 |
| `majority_class` vs `arm_b_finetune` | overall | 10000 | 159 | 3057 | 0 |
| `majority_class` vs `arm_b_finetune` | null_ambiguous | 3062 | 159 | 0 | 2.74e-48 |
| `length_only` vs `tfidf_logreg` | overall | 10000 | 244 | 1364 | 1.18e-188 |
| `length_only` vs `tfidf_logreg` | null_ambiguous | 3062 | 223 | 0 | 1.48e-67 |
| `length_only` vs `arm_a_probe` | overall | 10000 | 506 | 2131 | 7.14e-236 |
| `length_only` vs `arm_a_probe` | null_ambiguous | 3062 | 432 | 0 | 1.8e-130 |
| `length_only` vs `arm_b_finetune` | overall | 10000 | 159 | 3057 | 0 |
| `length_only` vs `arm_b_finetune` | null_ambiguous | 3062 | 159 | 0 | 2.74e-48 |
| `tfidf_logreg` vs `arm_a_probe` | overall | 10000 | 725 | 1230 | 2.03e-30 |
| `tfidf_logreg` vs `arm_a_probe` | null_ambiguous | 3062 | 329 | 120 | 1.45e-23 |
| `tfidf_logreg` vs `arm_b_finetune` | overall | 10000 | 219 | 1997 | 0 |
| `tfidf_logreg` vs `arm_b_finetune` | null_ambiguous | 3062 | 121 | 185 | 0.000302 |
| `arm_a_probe` vs `arm_b_finetune` | overall | 10000 | 337 | 1610 | 1.86e-198 |
| `arm_a_probe` vs `arm_b_finetune` | null_ambiguous | 3062 | 93 | 366 | 2.45e-39 |

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
| `urinary_frequency_false` | 2479 | 0.0% | 0.0% | 48.1% | 61.7% | 84.1% | 84.1pp |
| `urinary_frequency_true` | 1481 | 0.0% | 0.0% | 11.1% | 40.3% | 65.8% | 65.8pp |
| `urinary_frequency_null_hedged` | 620 | 100.0% | 100.0% | 90.5% | 77.1% | 90.2% | 22.9pp |
| `urinary_frequency_null_thirdparty` | 640 | 100.0% | 100.0% | 83.3% | 80.0% | 98.8% | 20.0pp |
| `urinary_frequency_null_adjacent` | 588 | 100.0% | 100.0% | 96.4% | 90.6% | 94.7% | 9.4pp |
| `urinary_frequency_null_historical` | 541 | 100.0% | 100.0% | 98.0% | 90.8% | 100.0% | 9.2pp |
| `urinary_frequency_null_metaphor` | 673 | 100.0% | 100.0% | 97.8% | 92.3% | 95.1% | 7.7pp |
| `(none)` | 2978 | 100.0% | 100.0% | 99.3% | 97.5% | 100.0% | 2.5pp |

### By fragment, errors

Ordered by the worst model's error count, so the fragments the comparison is about sort
to the top whichever encoder wins. Counts, not rates: these are the sentences a month of
library work would be spent on. The JSON holds every fragment.

| fragment | library | truth | `majority_class` | `length_only` | `tfidf_logreg` | `arm_a_probe` | `arm_b_finetune` | spread |
|---|---|---|---|---|---|---|---|---|
| `urinary_frequency_false:a15017c2` | `urinary_frequency_false` | false | 137 | 137 | 29 | 20 | 50 | 117 |
| `urinary_frequency_false:22b965f9` | `urinary_frequency_false` | false | 123 | 123 | 17 | 24 | 0 | 123 |
| `urinary_frequency_false:d293ee8c` | `urinary_frequency_false` | false | 123 | 123 | 37 | 84 | 8 | 115 |
| `urinary_frequency_false:a7fe81d1` | `urinary_frequency_false` | false | 121 | 121 | 99 | 0 | 0 | 121 |
| `urinary_frequency_true:11d16987` | `urinary_frequency_true` | true | 69 | 69 | 69 | 55 | 67 | 14 |
| `urinary_frequency_false:6c16f65e` | `urinary_frequency_false` | false | 67 | 67 | 0 | 10 | 0 | 67 |
| `urinary_frequency_true:272d2041` | `urinary_frequency_true` | true | 67 | 67 | 42 | 32 | 0 | 67 |
| `urinary_frequency_false:7fc83941` | `urinary_frequency_false` | false | 65 | 65 | 16 | 32 | 0 | 65 |
| `urinary_frequency_false:a9a59952` | `urinary_frequency_false` | false | 64 | 64 | 58 | 52 | 64 | 12 |
| `urinary_frequency_false:1d7759da` | `urinary_frequency_false` | false | 62 | 62 | 59 | 46 | 2 | 60 |
| `urinary_frequency_false:f3e3b17c` | `urinary_frequency_false` | false | 62 | 62 | 39 | 3 | 0 | 62 |
| `urinary_frequency_true:764389c0` | `urinary_frequency_true` | true | 61 | 61 | 61 | 61 | 61 | 0 |
| `urinary_frequency_false:cdacd51c` | `urinary_frequency_false` | false | 60 | 60 | 42 | 39 | 0 | 60 |
| `urinary_frequency_false:767e3f26` | `urinary_frequency_false` | false | 58 | 58 | 2 | 32 | 0 | 58 |
| `urinary_frequency_false:a5342750` | `urinary_frequency_false` | false | 58 | 58 | 6 | 22 | 0 | 58 |
| `urinary_frequency_false:c7b96e67` | `urinary_frequency_false` | false | 58 | 58 | 13 | 23 | 0 | 58 |
| `urinary_frequency_false:0c947cff` | `urinary_frequency_false` | false | 57 | 57 | 48 | 16 | 0 | 57 |
| `urinary_frequency_false:1a4ef542` | `urinary_frequency_false` | false | 57 | 57 | 3 | 18 | 0 | 57 |
| `urinary_frequency_false:bb59f573` | `urinary_frequency_false` | false | 57 | 57 | 0 | 4 | 0 | 57 |
| `urinary_frequency_false:44543d5e` | `urinary_frequency_false` | false | 56 | 56 | 52 | 46 | 22 | 34 |
| `urinary_frequency_false:f78f9d25` | `urinary_frequency_false` | false | 56 | 56 | 56 | 16 | 36 | 40 |
| `urinary_frequency_false:70687811` | `urinary_frequency_false` | false | 55 | 55 | 7 | 18 | 0 | 55 |
| `urinary_frequency_false:8a1fa086` | `urinary_frequency_false` | false | 55 | 55 | 47 | 9 | 0 | 55 |
| `urinary_frequency_true:2a4e0890` | `urinary_frequency_true` | true | 55 | 55 | 55 | 23 | 0 | 55 |
| `urinary_frequency_true:d01347c4` | `urinary_frequency_true` | true | 55 | 55 | 22 | 4 | 0 | 55 |
| `urinary_frequency_true:ffa90ce7` | `urinary_frequency_true` | true | 55 | 55 | 55 | 55 | 25 | 30 |
| `urinary_frequency_false:3f640028` | `urinary_frequency_false` | false | 54 | 54 | 9 | 9 | 0 | 54 |
| `urinary_frequency_false:838b4247` | `urinary_frequency_false` | false | 54 | 54 | 1 | 3 | 0 | 54 |
| `urinary_frequency_false:63302b59` | `urinary_frequency_false` | false | 53 | 53 | 20 | 25 | 53 | 33 |
| `urinary_frequency_false:99f7fbc1` | `urinary_frequency_false` | false | 53 | 53 | 5 | 15 | 0 | 53 |
| `urinary_frequency_false:c631660d` | `urinary_frequency_false` | false | 51 | 51 | 51 | 44 | 48 | 7 |
| `urinary_frequency_false:f324736d` | `urinary_frequency_false` | false | 50 | 50 | 50 | 7 | 0 | 50 |
| `urinary_frequency_false:42205311` | `urinary_frequency_false` | false | 47 | 47 | 18 | 9 | 0 | 47 |
| `urinary_frequency_false:941626e8` | `urinary_frequency_false` | false | 47 | 47 | 38 | 37 | 14 | 33 |
| `urinary_frequency_true:73717ed3` | `urinary_frequency_true` | true | 47 | 47 | 42 | 16 | 18 | 31 |
| `urinary_frequency_false:f32c9e68` | `urinary_frequency_false` | false | 44 | 44 | 43 | 25 | 38 | 19 |
| `urinary_frequency_false:fc6a56d2` | `urinary_frequency_false` | false | 43 | 43 | 39 | 11 | 2 | 41 |
| `urinary_frequency_true:87b688c8` | `urinary_frequency_true` | true | 43 | 43 | 37 | 36 | 0 | 43 |
| `urinary_frequency_false:6bb71206` | `urinary_frequency_false` | false | 41 | 41 | 41 | 34 | 22 | 19 |
| `urinary_frequency_true:2c452329` | `urinary_frequency_true` | true | 41 | 41 | 41 | 38 | 40 | 3 |

*180 further fragments erred on at least one model; the JSON holds them all.*

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
| false | 2479 | **46** | 0.0% [0.0%, 0.0%] |
| null_ambiguous | 3062 | **210** | 100.0% [100.0%, 100.0%] |
| null_structural | 2978 | **1** | 100.0% [100.0%, 100.0%] |
| true | 1481 | **46** | 0.0% [0.0%, 0.0%] |

### By null sub-class

| sub-class | n | eff n | null recall [95% CI] |
|---|---|---|---|
| adjacent | 588 | **40** | 100.0% [100.0%, 100.0%] |
| hedged | 620 | **42** | 100.0% [100.0%, 100.0%] |
| historical | 541 | **40** | 100.0% [100.0%, 100.0%] |
| metaphor | 673 | **44** | 100.0% [100.0%, 100.0%] |
| third_party | 640 | **44** | 100.0% [100.0%, 100.0%] |

### By fragment library

| library | n | eff n | accuracy [95% CI] |
|---|---|---|---|
| urinary_frequency_false | 2479 | **46** | 0.0% [0.0%, 0.0%] |
| urinary_frequency_null_adjacent | 588 | **40** | 100.0% [100.0%, 100.0%] |
| urinary_frequency_null_hedged | 620 | **42** | 100.0% [100.0%, 100.0%] |
| urinary_frequency_null_historical | 541 | **40** | 100.0% [100.0%, 100.0%] |
| urinary_frequency_null_metaphor | 673 | **44** | 100.0% [100.0%, 100.0%] |
| urinary_frequency_null_thirdparty | 640 | **44** | 100.0% [100.0%, 100.0%] |
| urinary_frequency_true | 1481 | **46** | 0.0% [0.0%, 0.0%] |
| (none) | 2978 | **1** | 100.0% [100.0%, 100.0%] |

### Per-fragment errors (worst first)

Whether errors are spread thinly across many fragments or piled onto a few is the difference
between "the method is too weak" (model work) and "these specific ideas are not learnable from
the data we have" (library work, and these are the fragments to write more of). No intervals:
a fragment is one cluster, so an interval over its own examples measures nothing.

92 of 302 decisive fragments were got wrong at least once.

`majority_class`: 3960 errors across 92 of 302 decisive fragments. Half of them fall on **30** fragments (an even spread would be 46.0); the worst ten carry 22.7% of all errors.

| fragment | library | sub-class | truth | correct | accuracy | predicted as |
|---|---|---|---|---|---|---|
| `urinary_frequency_false:a15017c2` | `urinary_frequency_false` | -- | false | 0/137 | 0.0% | null 137 |
| `urinary_frequency_false:22b965f9` | `urinary_frequency_false` | -- | false | 0/123 | 0.0% | null 123 |
| `urinary_frequency_false:d293ee8c` | `urinary_frequency_false` | -- | false | 0/123 | 0.0% | null 123 |
| `urinary_frequency_false:a7fe81d1` | `urinary_frequency_false` | -- | false | 0/121 | 0.0% | null 121 |
| `urinary_frequency_true:11d16987` | `urinary_frequency_true` | -- | true | 0/69 | 0.0% | null 69 |
| `urinary_frequency_false:6c16f65e` | `urinary_frequency_false` | -- | false | 0/67 | 0.0% | null 67 |
| `urinary_frequency_true:272d2041` | `urinary_frequency_true` | -- | true | 0/67 | 0.0% | null 67 |
| `urinary_frequency_false:7fc83941` | `urinary_frequency_false` | -- | false | 0/65 | 0.0% | null 65 |
| `urinary_frequency_false:a9a59952` | `urinary_frequency_false` | -- | false | 0/64 | 0.0% | null 64 |
| `urinary_frequency_false:1d7759da` | `urinary_frequency_false` | -- | false | 0/62 | 0.0% | null 62 |
| `urinary_frequency_false:f3e3b17c` | `urinary_frequency_false` | -- | false | 0/62 | 0.0% | null 62 |
| `urinary_frequency_true:764389c0` | `urinary_frequency_true` | -- | true | 0/61 | 0.0% | null 61 |
| `urinary_frequency_false:cdacd51c` | `urinary_frequency_false` | -- | false | 0/60 | 0.0% | null 60 |
| `urinary_frequency_false:767e3f26` | `urinary_frequency_false` | -- | false | 0/58 | 0.0% | null 58 |
| `urinary_frequency_false:a5342750` | `urinary_frequency_false` | -- | false | 0/58 | 0.0% | null 58 |
| `urinary_frequency_false:c7b96e67` | `urinary_frequency_false` | -- | false | 0/58 | 0.0% | null 58 |
| `urinary_frequency_false:0c947cff` | `urinary_frequency_false` | -- | false | 0/57 | 0.0% | null 57 |
| `urinary_frequency_false:1a4ef542` | `urinary_frequency_false` | -- | false | 0/57 | 0.0% | null 57 |
| `urinary_frequency_false:bb59f573` | `urinary_frequency_false` | -- | false | 0/57 | 0.0% | null 57 |
| `urinary_frequency_false:44543d5e` | `urinary_frequency_false` | -- | false | 0/56 | 0.0% | null 56 |
| `urinary_frequency_false:f78f9d25` | `urinary_frequency_false` | -- | false | 0/56 | 0.0% | null 56 |
| `urinary_frequency_false:70687811` | `urinary_frequency_false` | -- | false | 0/55 | 0.0% | null 55 |
| `urinary_frequency_false:8a1fa086` | `urinary_frequency_false` | -- | false | 0/55 | 0.0% | null 55 |
| `urinary_frequency_true:2a4e0890` | `urinary_frequency_true` | -- | true | 0/55 | 0.0% | null 55 |
| `urinary_frequency_true:d01347c4` | `urinary_frequency_true` | -- | true | 0/55 | 0.0% | null 55 |
| `urinary_frequency_true:ffa90ce7` | `urinary_frequency_true` | -- | true | 0/55 | 0.0% | null 55 |
| `urinary_frequency_false:3f640028` | `urinary_frequency_false` | -- | false | 0/54 | 0.0% | null 54 |
| `urinary_frequency_false:838b4247` | `urinary_frequency_false` | -- | false | 0/54 | 0.0% | null 54 |
| `urinary_frequency_false:63302b59` | `urinary_frequency_false` | -- | false | 0/53 | 0.0% | null 53 |
| `urinary_frequency_false:99f7fbc1` | `urinary_frequency_false` | -- | false | 0/53 | 0.0% | null 53 |
| `urinary_frequency_false:c631660d` | `urinary_frequency_false` | -- | false | 0/51 | 0.0% | null 51 |
| `urinary_frequency_false:f324736d` | `urinary_frequency_false` | -- | false | 0/50 | 0.0% | null 50 |
| `urinary_frequency_false:42205311` | `urinary_frequency_false` | -- | false | 0/47 | 0.0% | null 47 |
| `urinary_frequency_false:941626e8` | `urinary_frequency_false` | -- | false | 0/47 | 0.0% | null 47 |
| `urinary_frequency_true:73717ed3` | `urinary_frequency_true` | -- | true | 0/47 | 0.0% | null 47 |
| `urinary_frequency_false:f32c9e68` | `urinary_frequency_false` | -- | false | 0/44 | 0.0% | null 44 |
| `urinary_frequency_false:fc6a56d2` | `urinary_frequency_false` | -- | false | 0/43 | 0.0% | null 43 |
| `urinary_frequency_true:87b688c8` | `urinary_frequency_true` | -- | true | 0/43 | 0.0% | null 43 |
| `urinary_frequency_false:6bb71206` | `urinary_frequency_false` | -- | false | 0/41 | 0.0% | null 41 |
| `urinary_frequency_true:2c452329` | `urinary_frequency_true` | -- | true | 0/41 | 0.0% | null 41 |

*52 further fragments with at least one error are in the JSON sidecar; every fragment is there regardless of score.*

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
| false | 2479 | **46** | 0.0% [0.0%, 0.0%] |
| null_ambiguous | 3062 | **210** | 100.0% [100.0%, 100.0%] |
| null_structural | 2978 | **1** | 100.0% [100.0%, 100.0%] |
| true | 1481 | **46** | 0.0% [0.0%, 0.0%] |

### By null sub-class

| sub-class | n | eff n | null recall [95% CI] |
|---|---|---|---|
| adjacent | 588 | **40** | 100.0% [100.0%, 100.0%] |
| hedged | 620 | **42** | 100.0% [100.0%, 100.0%] |
| historical | 541 | **40** | 100.0% [100.0%, 100.0%] |
| metaphor | 673 | **44** | 100.0% [100.0%, 100.0%] |
| third_party | 640 | **44** | 100.0% [100.0%, 100.0%] |

### By fragment library

| library | n | eff n | accuracy [95% CI] |
|---|---|---|---|
| urinary_frequency_false | 2479 | **46** | 0.0% [0.0%, 0.0%] |
| urinary_frequency_null_adjacent | 588 | **40** | 100.0% [100.0%, 100.0%] |
| urinary_frequency_null_hedged | 620 | **42** | 100.0% [100.0%, 100.0%] |
| urinary_frequency_null_historical | 541 | **40** | 100.0% [100.0%, 100.0%] |
| urinary_frequency_null_metaphor | 673 | **44** | 100.0% [100.0%, 100.0%] |
| urinary_frequency_null_thirdparty | 640 | **44** | 100.0% [100.0%, 100.0%] |
| urinary_frequency_true | 1481 | **46** | 0.0% [0.0%, 0.0%] |
| (none) | 2978 | **1** | 100.0% [100.0%, 100.0%] |

### Per-fragment errors (worst first)

Whether errors are spread thinly across many fragments or piled onto a few is the difference
between "the method is too weak" (model work) and "these specific ideas are not learnable from
the data we have" (library work, and these are the fragments to write more of). No intervals:
a fragment is one cluster, so an interval over its own examples measures nothing.

92 of 302 decisive fragments were got wrong at least once.

`length_only`: 3960 errors across 92 of 302 decisive fragments. Half of them fall on **30** fragments (an even spread would be 46.0); the worst ten carry 22.7% of all errors.

| fragment | library | sub-class | truth | correct | accuracy | predicted as |
|---|---|---|---|---|---|---|
| `urinary_frequency_false:a15017c2` | `urinary_frequency_false` | -- | false | 0/137 | 0.0% | null 137 |
| `urinary_frequency_false:22b965f9` | `urinary_frequency_false` | -- | false | 0/123 | 0.0% | null 123 |
| `urinary_frequency_false:d293ee8c` | `urinary_frequency_false` | -- | false | 0/123 | 0.0% | null 123 |
| `urinary_frequency_false:a7fe81d1` | `urinary_frequency_false` | -- | false | 0/121 | 0.0% | null 121 |
| `urinary_frequency_true:11d16987` | `urinary_frequency_true` | -- | true | 0/69 | 0.0% | null 69 |
| `urinary_frequency_false:6c16f65e` | `urinary_frequency_false` | -- | false | 0/67 | 0.0% | null 67 |
| `urinary_frequency_true:272d2041` | `urinary_frequency_true` | -- | true | 0/67 | 0.0% | null 67 |
| `urinary_frequency_false:7fc83941` | `urinary_frequency_false` | -- | false | 0/65 | 0.0% | null 65 |
| `urinary_frequency_false:a9a59952` | `urinary_frequency_false` | -- | false | 0/64 | 0.0% | null 64 |
| `urinary_frequency_false:1d7759da` | `urinary_frequency_false` | -- | false | 0/62 | 0.0% | null 62 |
| `urinary_frequency_false:f3e3b17c` | `urinary_frequency_false` | -- | false | 0/62 | 0.0% | null 62 |
| `urinary_frequency_true:764389c0` | `urinary_frequency_true` | -- | true | 0/61 | 0.0% | null 61 |
| `urinary_frequency_false:cdacd51c` | `urinary_frequency_false` | -- | false | 0/60 | 0.0% | null 60 |
| `urinary_frequency_false:767e3f26` | `urinary_frequency_false` | -- | false | 0/58 | 0.0% | null 58 |
| `urinary_frequency_false:a5342750` | `urinary_frequency_false` | -- | false | 0/58 | 0.0% | null 58 |
| `urinary_frequency_false:c7b96e67` | `urinary_frequency_false` | -- | false | 0/58 | 0.0% | null 58 |
| `urinary_frequency_false:0c947cff` | `urinary_frequency_false` | -- | false | 0/57 | 0.0% | null 57 |
| `urinary_frequency_false:1a4ef542` | `urinary_frequency_false` | -- | false | 0/57 | 0.0% | null 57 |
| `urinary_frequency_false:bb59f573` | `urinary_frequency_false` | -- | false | 0/57 | 0.0% | null 57 |
| `urinary_frequency_false:44543d5e` | `urinary_frequency_false` | -- | false | 0/56 | 0.0% | null 56 |
| `urinary_frequency_false:f78f9d25` | `urinary_frequency_false` | -- | false | 0/56 | 0.0% | null 56 |
| `urinary_frequency_false:70687811` | `urinary_frequency_false` | -- | false | 0/55 | 0.0% | null 55 |
| `urinary_frequency_false:8a1fa086` | `urinary_frequency_false` | -- | false | 0/55 | 0.0% | null 55 |
| `urinary_frequency_true:2a4e0890` | `urinary_frequency_true` | -- | true | 0/55 | 0.0% | null 55 |
| `urinary_frequency_true:d01347c4` | `urinary_frequency_true` | -- | true | 0/55 | 0.0% | null 55 |
| `urinary_frequency_true:ffa90ce7` | `urinary_frequency_true` | -- | true | 0/55 | 0.0% | null 55 |
| `urinary_frequency_false:3f640028` | `urinary_frequency_false` | -- | false | 0/54 | 0.0% | null 54 |
| `urinary_frequency_false:838b4247` | `urinary_frequency_false` | -- | false | 0/54 | 0.0% | null 54 |
| `urinary_frequency_false:63302b59` | `urinary_frequency_false` | -- | false | 0/53 | 0.0% | null 53 |
| `urinary_frequency_false:99f7fbc1` | `urinary_frequency_false` | -- | false | 0/53 | 0.0% | null 53 |
| `urinary_frequency_false:c631660d` | `urinary_frequency_false` | -- | false | 0/51 | 0.0% | null 51 |
| `urinary_frequency_false:f324736d` | `urinary_frequency_false` | -- | false | 0/50 | 0.0% | null 50 |
| `urinary_frequency_false:42205311` | `urinary_frequency_false` | -- | false | 0/47 | 0.0% | null 47 |
| `urinary_frequency_false:941626e8` | `urinary_frequency_false` | -- | false | 0/47 | 0.0% | null 47 |
| `urinary_frequency_true:73717ed3` | `urinary_frequency_true` | -- | true | 0/47 | 0.0% | null 47 |
| `urinary_frequency_false:f32c9e68` | `urinary_frequency_false` | -- | false | 0/44 | 0.0% | null 44 |
| `urinary_frequency_false:fc6a56d2` | `urinary_frequency_false` | -- | false | 0/43 | 0.0% | null 43 |
| `urinary_frequency_true:87b688c8` | `urinary_frequency_true` | -- | true | 0/43 | 0.0% | null 43 |
| `urinary_frequency_false:6bb71206` | `urinary_frequency_false` | -- | false | 0/41 | 0.0% | null 41 |
| `urinary_frequency_true:2c452329` | `urinary_frequency_true` | -- | true | 0/41 | 0.0% | null 41 |

*52 further fragments with at least one error are in the JSON sidecar; every fragment is there regardless of score.*

## `tfidf_logreg`

TF-IDF unigrams and bigrams into logistic regression. Tests whether the dataset is keyword-solvable. Its overall accuracy is close to uninformative; the `null_ambiguous` slice is the number that matters.

Decision-rule margins selected per fold (on each fold's own validation split): 0.0, 0.15.

*Confusion matrix, raw argmax*

|  | pred false | pred true | pred null | total |
|---|---|---|---|---|
| **truth false** | 1191 | 180 | 1108 | 2479 |
| **truth true** | 197 | 173 | 1111 | 1481 |
| **truth null** | 96 | 148 | 5796 | 6040 |
| **total** | 1484 | 501 | 8015 | 10000 |

`null -> true`: 148 of 6040 truly-null examples (2.45%).

*Confusion matrix, after the decision rule*

|  | pred false | pred true | pred null | total |
|---|---|---|---|---|
| **truth false** | 1193 | 178 | 1108 | 2479 |
| **truth true** | 205 | 165 | 1111 | 1481 |
| **truth null** | 96 | 137 | 5807 | 6040 |
| **total** | 1494 | 480 | 8026 | 10000 |

`null -> true`: 137 of 6040 truly-null examples (2.27%).

### Per class, after the decision rule

| class | support | predicted | precision | recall | F1 |
|---|---|---|---|---|---|
| `false` | 2479 | 1494 | 79.9% | 48.1% | 60.1% |
| `true` | 1481 | 480 | 34.4% | 11.1% | 16.8% |
| `null` | 6040 | 8026 | 72.4% | 96.1% | 82.6% |

### By label mode

| label mode | n | eff n | accuracy [95% CI] |
|---|---|---|---|
| false | 2479 | **46** | 48.1% [36.6%, 59.1%] |
| null_ambiguous | 3062 | **210** | 93.0% [90.5%, 95.4%] |
| null_structural | 2978 | **1** | 99.3% [99.3%, 99.3%] |
| true | 1481 | **46** | 11.1% [5.0%, 18.0%] |

### By null sub-class

| sub-class | n | eff n | null recall [95% CI] |
|---|---|---|---|
| adjacent | 588 | **40** | 96.4% [91.0%, 99.7%] |
| hedged | 620 | **42** | 90.5% [84.2%, 95.6%] |
| historical | 541 | **40** | 98.0% [96.0%, 99.5%] |
| metaphor | 673 | **44** | 97.8% [95.8%, 99.4%] |
| third_party | 640 | **44** | 83.3% [74.8%, 90.8%] |

### By fragment library

| library | n | eff n | accuracy [95% CI] |
|---|---|---|---|
| urinary_frequency_false | 2479 | **46** | 48.1% [36.6%, 59.1%] |
| urinary_frequency_null_adjacent | 588 | **40** | 96.4% [91.0%, 99.7%] |
| urinary_frequency_null_hedged | 620 | **42** | 90.5% [84.2%, 95.6%] |
| urinary_frequency_null_historical | 541 | **40** | 98.0% [96.0%, 99.5%] |
| urinary_frequency_null_metaphor | 673 | **44** | 97.8% [95.8%, 99.4%] |
| urinary_frequency_null_thirdparty | 640 | **44** | 83.3% [74.8%, 90.8%] |
| urinary_frequency_true | 1481 | **46** | 11.1% [5.0%, 18.0%] |
| (none) | 2978 | **1** | 99.3% [99.3%, 99.3%] |

### Per-fragment errors (worst first)

Whether errors are spread thinly across many fragments or piled onto a few is the difference
between "the method is too weak" (model work) and "these specific ideas are not learnable from
the data we have" (library work, and these are the fragments to write more of). No intervals:
a fragment is one cluster, so an interval over its own examples measures nothing.

143 of 302 decisive fragments were got wrong at least once.

`tfidf_logreg`: 2815 errors across 143 of 302 decisive fragments. Half of them fall on **30** fragments (an even spread would be 71.5); the worst ten carry 21.8% of all errors.

| fragment | library | sub-class | truth | correct | accuracy | predicted as |
|---|---|---|---|---|---|---|
| `urinary_frequency_true:11d16987` | `urinary_frequency_true` | -- | true | 0/69 | 0.0% | null 69 |
| `urinary_frequency_true:764389c0` | `urinary_frequency_true` | -- | true | 0/61 | 0.0% | null 61 |
| `urinary_frequency_false:f78f9d25` | `urinary_frequency_false` | -- | false | 0/56 | 0.0% | null 56 |
| `urinary_frequency_true:2a4e0890` | `urinary_frequency_true` | -- | true | 0/55 | 0.0% | null 55 |
| `urinary_frequency_true:ffa90ce7` | `urinary_frequency_true` | -- | true | 0/55 | 0.0% | null 55 |
| `urinary_frequency_false:c631660d` | `urinary_frequency_false` | -- | false | 0/51 | 0.0% | null 51 |
| `urinary_frequency_false:f324736d` | `urinary_frequency_false` | -- | false | 0/50 | 0.0% | null 50 |
| `urinary_frequency_false:6bb71206` | `urinary_frequency_false` | -- | false | 0/41 | 0.0% | null 41 |
| `urinary_frequency_true:2c452329` | `urinary_frequency_true` | -- | true | 0/41 | 0.0% | false 5, null 36 |
| `urinary_frequency_true:f6de3825` | `urinary_frequency_true` | -- | true | 0/41 | 0.0% | false 41 |
| `urinary_frequency_false:a61aba66` | `urinary_frequency_false` | -- | false | 0/39 | 0.0% | null 39 |
| `urinary_frequency_false:8ea3ee34` | `urinary_frequency_false` | -- | false | 0/37 | 0.0% | null 37 |
| `urinary_frequency_true:5008b431` | `urinary_frequency_true` | -- | true | 0/36 | 0.0% | false 9, null 27 |
| `urinary_frequency_true:eccbc8ee` | `urinary_frequency_true` | -- | true | 0/36 | 0.0% | false 11, null 25 |
| `urinary_frequency_true:617cfdc3` | `urinary_frequency_true` | -- | true | 0/35 | 0.0% | false 3, null 32 |
| `urinary_frequency_true:900c8b2c` | `urinary_frequency_true` | -- | true | 0/33 | 0.0% | false 1, null 32 |
| `urinary_frequency_false:c85c9d5a` | `urinary_frequency_false` | -- | false | 0/32 | 0.0% | null 32 |
| `urinary_frequency_true:fbca5613` | `urinary_frequency_true` | -- | true | 0/32 | 0.0% | null 32 |
| `urinary_frequency_true:e746abc0` | `urinary_frequency_true` | -- | true | 0/31 | 0.0% | false 1, null 30 |
| `urinary_frequency_false:7be58a30` | `urinary_frequency_false` | -- | false | 0/29 | 0.0% | null 29 |
| `urinary_frequency_false:b66fa498` | `urinary_frequency_false` | -- | false | 0/29 | 0.0% | true 14, null 15 |
| `urinary_frequency_true:fecb0185` | `urinary_frequency_true` | -- | true | 0/28 | 0.0% | false 1, null 27 |
| `urinary_frequency_true:1d671fe5` | `urinary_frequency_true` | -- | true | 0/27 | 0.0% | null 27 |
| `urinary_frequency_true:32946372` | `urinary_frequency_true` | -- | true | 0/27 | 0.0% | false 24, null 3 |
| `urinary_frequency_true:16cfc7d7` | `urinary_frequency_true` | -- | true | 0/25 | 0.0% | false 1, null 24 |
| `urinary_frequency_true:f9c03b9b` | `urinary_frequency_true` | -- | true | 0/24 | 0.0% | null 24 |
| `urinary_frequency_true:c87f1579` | `urinary_frequency_true` | -- | true | 0/22 | 0.0% | false 1, null 21 |
| `urinary_frequency_true:32cae421` | `urinary_frequency_true` | -- | true | 0/21 | 0.0% | false 21 |
| `urinary_frequency_true:f0e98801` | `urinary_frequency_true` | -- | true | 0/21 | 0.0% | false 2, null 19 |
| `urinary_frequency_true:95d4e96a` | `urinary_frequency_true` | -- | true | 0/20 | 0.0% | false 8, null 12 |
| `urinary_frequency_true:f5216cf2` | `urinary_frequency_true` | -- | true | 0/18 | 0.0% | null 18 |
| `urinary_frequency_true:2491f080` | `urinary_frequency_true` | -- | true | 0/17 | 0.0% | null 17 |
| `urinary_frequency_true:20bd4d56` | `urinary_frequency_true` | -- | true | 0/16 | 0.0% | null 16 |
| `urinary_frequency_true:52b41248` | `urinary_frequency_true` | -- | true | 0/16 | 0.0% | null 16 |
| `urinary_frequency_true:c8d32074` | `urinary_frequency_true` | -- | true | 0/14 | 0.0% | null 14 |
| `urinary_frequency_true:5ef90c41` | `urinary_frequency_true` | -- | true | 0/12 | 0.0% | null 12 |
| `urinary_frequency_false:f32c9e68` | `urinary_frequency_false` | -- | false | 1/44 | 2.3% | false 1, true 5, null 38 |
| `urinary_frequency_true:35a67edf` | `urinary_frequency_true` | -- | true | 1/33 | 3.0% | true 1, null 32 |
| `urinary_frequency_false:ec8210fb` | `urinary_frequency_false` | -- | false | 1/31 | 3.2% | false 1, null 30 |
| `urinary_frequency_true:5327793c` | `urinary_frequency_true` | -- | true | 1/27 | 3.7% | true 1, null 26 |

*103 further fragments with at least one error are in the JSON sidecar; every fragment is there regardless of score.*

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
| false | 2479 | **46** | 0.0% [0.0%, 0.0%] |
| null_ambiguous | 3062 | **210** | 100.0% [100.0%, 100.0%] |
| null_structural | 2978 | **1** | 100.0% [100.0%, 100.0%] |
| true | 1481 | **46** | 0.0% [0.0%, 0.0%] |

### By null sub-class

| sub-class | n | eff n | null recall [95% CI] |
|---|---|---|---|
| adjacent | 588 | **40** | 100.0% [100.0%, 100.0%] |
| hedged | 620 | **42** | 100.0% [100.0%, 100.0%] |
| historical | 541 | **40** | 100.0% [100.0%, 100.0%] |
| metaphor | 673 | **44** | 100.0% [100.0%, 100.0%] |
| third_party | 640 | **44** | 100.0% [100.0%, 100.0%] |

### By fragment library

| library | n | eff n | accuracy [95% CI] |
|---|---|---|---|
| urinary_frequency_false | 2479 | **46** | 0.0% [0.0%, 0.0%] |
| urinary_frequency_null_adjacent | 588 | **40** | 100.0% [100.0%, 100.0%] |
| urinary_frequency_null_hedged | 620 | **42** | 100.0% [100.0%, 100.0%] |
| urinary_frequency_null_historical | 541 | **40** | 100.0% [100.0%, 100.0%] |
| urinary_frequency_null_metaphor | 673 | **44** | 100.0% [100.0%, 100.0%] |
| urinary_frequency_null_thirdparty | 640 | **44** | 100.0% [100.0%, 100.0%] |
| urinary_frequency_true | 1481 | **46** | 0.0% [0.0%, 0.0%] |
| (none) | 2978 | **1** | 100.0% [100.0%, 100.0%] |

### Per-fragment errors (worst first)

Whether errors are spread thinly across many fragments or piled onto a few is the difference
between "the method is too weak" (model work) and "these specific ideas are not learnable from
the data we have" (library work, and these are the fragments to write more of). No intervals:
a fragment is one cluster, so an interval over its own examples measures nothing.

92 of 302 decisive fragments were got wrong at least once.

`length_only__shuffled`: 3960 errors across 92 of 302 decisive fragments. Half of them fall on **30** fragments (an even spread would be 46.0); the worst ten carry 22.7% of all errors.

| fragment | library | sub-class | truth | correct | accuracy | predicted as |
|---|---|---|---|---|---|---|
| `urinary_frequency_false:a15017c2` | `urinary_frequency_false` | -- | false | 0/137 | 0.0% | null 137 |
| `urinary_frequency_false:22b965f9` | `urinary_frequency_false` | -- | false | 0/123 | 0.0% | null 123 |
| `urinary_frequency_false:d293ee8c` | `urinary_frequency_false` | -- | false | 0/123 | 0.0% | null 123 |
| `urinary_frequency_false:a7fe81d1` | `urinary_frequency_false` | -- | false | 0/121 | 0.0% | null 121 |
| `urinary_frequency_true:11d16987` | `urinary_frequency_true` | -- | true | 0/69 | 0.0% | null 69 |
| `urinary_frequency_false:6c16f65e` | `urinary_frequency_false` | -- | false | 0/67 | 0.0% | null 67 |
| `urinary_frequency_true:272d2041` | `urinary_frequency_true` | -- | true | 0/67 | 0.0% | null 67 |
| `urinary_frequency_false:7fc83941` | `urinary_frequency_false` | -- | false | 0/65 | 0.0% | null 65 |
| `urinary_frequency_false:a9a59952` | `urinary_frequency_false` | -- | false | 0/64 | 0.0% | null 64 |
| `urinary_frequency_false:1d7759da` | `urinary_frequency_false` | -- | false | 0/62 | 0.0% | null 62 |
| `urinary_frequency_false:f3e3b17c` | `urinary_frequency_false` | -- | false | 0/62 | 0.0% | null 62 |
| `urinary_frequency_true:764389c0` | `urinary_frequency_true` | -- | true | 0/61 | 0.0% | null 61 |
| `urinary_frequency_false:cdacd51c` | `urinary_frequency_false` | -- | false | 0/60 | 0.0% | null 60 |
| `urinary_frequency_false:767e3f26` | `urinary_frequency_false` | -- | false | 0/58 | 0.0% | null 58 |
| `urinary_frequency_false:a5342750` | `urinary_frequency_false` | -- | false | 0/58 | 0.0% | null 58 |
| `urinary_frequency_false:c7b96e67` | `urinary_frequency_false` | -- | false | 0/58 | 0.0% | null 58 |
| `urinary_frequency_false:0c947cff` | `urinary_frequency_false` | -- | false | 0/57 | 0.0% | null 57 |
| `urinary_frequency_false:1a4ef542` | `urinary_frequency_false` | -- | false | 0/57 | 0.0% | null 57 |
| `urinary_frequency_false:bb59f573` | `urinary_frequency_false` | -- | false | 0/57 | 0.0% | null 57 |
| `urinary_frequency_false:44543d5e` | `urinary_frequency_false` | -- | false | 0/56 | 0.0% | null 56 |
| `urinary_frequency_false:f78f9d25` | `urinary_frequency_false` | -- | false | 0/56 | 0.0% | null 56 |
| `urinary_frequency_false:70687811` | `urinary_frequency_false` | -- | false | 0/55 | 0.0% | null 55 |
| `urinary_frequency_false:8a1fa086` | `urinary_frequency_false` | -- | false | 0/55 | 0.0% | null 55 |
| `urinary_frequency_true:2a4e0890` | `urinary_frequency_true` | -- | true | 0/55 | 0.0% | null 55 |
| `urinary_frequency_true:d01347c4` | `urinary_frequency_true` | -- | true | 0/55 | 0.0% | null 55 |
| `urinary_frequency_true:ffa90ce7` | `urinary_frequency_true` | -- | true | 0/55 | 0.0% | null 55 |
| `urinary_frequency_false:3f640028` | `urinary_frequency_false` | -- | false | 0/54 | 0.0% | null 54 |
| `urinary_frequency_false:838b4247` | `urinary_frequency_false` | -- | false | 0/54 | 0.0% | null 54 |
| `urinary_frequency_false:63302b59` | `urinary_frequency_false` | -- | false | 0/53 | 0.0% | null 53 |
| `urinary_frequency_false:99f7fbc1` | `urinary_frequency_false` | -- | false | 0/53 | 0.0% | null 53 |
| `urinary_frequency_false:c631660d` | `urinary_frequency_false` | -- | false | 0/51 | 0.0% | null 51 |
| `urinary_frequency_false:f324736d` | `urinary_frequency_false` | -- | false | 0/50 | 0.0% | null 50 |
| `urinary_frequency_false:42205311` | `urinary_frequency_false` | -- | false | 0/47 | 0.0% | null 47 |
| `urinary_frequency_false:941626e8` | `urinary_frequency_false` | -- | false | 0/47 | 0.0% | null 47 |
| `urinary_frequency_true:73717ed3` | `urinary_frequency_true` | -- | true | 0/47 | 0.0% | null 47 |
| `urinary_frequency_false:f32c9e68` | `urinary_frequency_false` | -- | false | 0/44 | 0.0% | null 44 |
| `urinary_frequency_false:fc6a56d2` | `urinary_frequency_false` | -- | false | 0/43 | 0.0% | null 43 |
| `urinary_frequency_true:87b688c8` | `urinary_frequency_true` | -- | true | 0/43 | 0.0% | null 43 |
| `urinary_frequency_false:6bb71206` | `urinary_frequency_false` | -- | false | 0/41 | 0.0% | null 41 |
| `urinary_frequency_true:2c452329` | `urinary_frequency_true` | -- | true | 0/41 | 0.0% | null 41 |

*52 further fragments with at least one error are in the JSON sidecar; every fragment is there regardless of score.*

## `tfidf_logreg__shuffled`

TF-IDF unigrams and bigrams into logistic regression. Tests whether the dataset is keyword-solvable. Its overall accuracy is close to uninformative; the `null_ambiguous` slice is the number that matters. **Negative control:** trained on permuted training labels (seed 7) and evaluated on the unpermuted test split, where it must land at chance.

Decision-rule margins selected per fold (on each fold's own validation split): 0.0.
Every fold selected margin 0, so the ruled and raw views below are the same decisions. That is a finding rather than a bug: no margin improved macro-F1 without worsening the `null -> true` rate.

*Confusion matrix, raw argmax*

|  | pred false | pred true | pred null | total |
|---|---|---|---|---|
| **truth false** | 0 | 0 | 2479 | 2479 |
| **truth true** | 0 | 0 | 1481 | 1481 |
| **truth null** | 4 | 0 | 6036 | 6040 |
| **total** | 4 | 0 | 9996 | 10000 |

`null -> true`: 0 of 6040 truly-null examples (0.00%).

*Confusion matrix, after the decision rule*

|  | pred false | pred true | pred null | total |
|---|---|---|---|---|
| **truth false** | 0 | 0 | 2479 | 2479 |
| **truth true** | 0 | 0 | 1481 | 1481 |
| **truth null** | 4 | 0 | 6036 | 6040 |
| **total** | 4 | 0 | 9996 | 10000 |

`null -> true`: 0 of 6040 truly-null examples (0.00%).

### Per class, after the decision rule

| class | support | predicted | precision | recall | F1 |
|---|---|---|---|---|---|
| `false` | 2479 | 4 | 0.0% | 0.0% | 0.0% |
| `true` | 1481 | 0 | -- | 0.0% | 0.0% |
| `null` | 6040 | 9996 | 60.4% | 99.9% | 75.3% |

### By label mode

| label mode | n | eff n | accuracy [95% CI] |
|---|---|---|---|
| false | 2479 | **46** | 0.0% [0.0%, 0.0%] |
| null_ambiguous | 3062 | **210** | 99.9% [99.7%, 100.0%] |
| null_structural | 2978 | **1** | 100.0% [100.0%, 100.0%] |
| true | 1481 | **46** | 0.0% [0.0%, 0.0%] |

### By null sub-class

| sub-class | n | eff n | null recall [95% CI] |
|---|---|---|---|
| adjacent | 588 | **40** | 100.0% [100.0%, 100.0%] |
| hedged | 620 | **42** | 100.0% [100.0%, 100.0%] |
| historical | 541 | **40** | 99.8% [99.4%, 100.0%] |
| metaphor | 673 | **44** | 100.0% [100.0%, 100.0%] |
| third_party | 640 | **44** | 99.7% [99.1%, 100.0%] |

### By fragment library

| library | n | eff n | accuracy [95% CI] |
|---|---|---|---|
| urinary_frequency_false | 2479 | **46** | 0.0% [0.0%, 0.0%] |
| urinary_frequency_null_adjacent | 588 | **40** | 100.0% [100.0%, 100.0%] |
| urinary_frequency_null_hedged | 620 | **42** | 100.0% [100.0%, 100.0%] |
| urinary_frequency_null_historical | 541 | **40** | 99.8% [99.4%, 100.0%] |
| urinary_frequency_null_metaphor | 673 | **44** | 100.0% [100.0%, 100.0%] |
| urinary_frequency_null_thirdparty | 640 | **44** | 99.7% [99.1%, 100.0%] |
| urinary_frequency_true | 1481 | **46** | 0.0% [0.0%, 0.0%] |
| (none) | 2978 | **1** | 100.0% [100.0%, 100.0%] |

### Per-fragment errors (worst first)

Whether errors are spread thinly across many fragments or piled onto a few is the difference
between "the method is too weak" (model work) and "these specific ideas are not learnable from
the data we have" (library work, and these are the fragments to write more of). No intervals:
a fragment is one cluster, so an interval over its own examples measures nothing.

94 of 302 decisive fragments were got wrong at least once.

`tfidf_logreg__shuffled`: 3963 errors across 94 of 302 decisive fragments. Half of them fall on **30** fragments (an even spread would be 47.0); the worst ten carry 22.7% of all errors.

| fragment | library | sub-class | truth | correct | accuracy | predicted as |
|---|---|---|---|---|---|---|
| `urinary_frequency_false:a15017c2` | `urinary_frequency_false` | -- | false | 0/137 | 0.0% | null 137 |
| `urinary_frequency_false:22b965f9` | `urinary_frequency_false` | -- | false | 0/123 | 0.0% | null 123 |
| `urinary_frequency_false:d293ee8c` | `urinary_frequency_false` | -- | false | 0/123 | 0.0% | null 123 |
| `urinary_frequency_false:a7fe81d1` | `urinary_frequency_false` | -- | false | 0/121 | 0.0% | null 121 |
| `urinary_frequency_true:11d16987` | `urinary_frequency_true` | -- | true | 0/69 | 0.0% | null 69 |
| `urinary_frequency_false:6c16f65e` | `urinary_frequency_false` | -- | false | 0/67 | 0.0% | null 67 |
| `urinary_frequency_true:272d2041` | `urinary_frequency_true` | -- | true | 0/67 | 0.0% | null 67 |
| `urinary_frequency_false:7fc83941` | `urinary_frequency_false` | -- | false | 0/65 | 0.0% | null 65 |
| `urinary_frequency_false:a9a59952` | `urinary_frequency_false` | -- | false | 0/64 | 0.0% | null 64 |
| `urinary_frequency_false:1d7759da` | `urinary_frequency_false` | -- | false | 0/62 | 0.0% | null 62 |
| `urinary_frequency_false:f3e3b17c` | `urinary_frequency_false` | -- | false | 0/62 | 0.0% | null 62 |
| `urinary_frequency_true:764389c0` | `urinary_frequency_true` | -- | true | 0/61 | 0.0% | null 61 |
| `urinary_frequency_false:cdacd51c` | `urinary_frequency_false` | -- | false | 0/60 | 0.0% | null 60 |
| `urinary_frequency_false:767e3f26` | `urinary_frequency_false` | -- | false | 0/58 | 0.0% | null 58 |
| `urinary_frequency_false:a5342750` | `urinary_frequency_false` | -- | false | 0/58 | 0.0% | null 58 |
| `urinary_frequency_false:c7b96e67` | `urinary_frequency_false` | -- | false | 0/58 | 0.0% | null 58 |
| `urinary_frequency_false:0c947cff` | `urinary_frequency_false` | -- | false | 0/57 | 0.0% | null 57 |
| `urinary_frequency_false:1a4ef542` | `urinary_frequency_false` | -- | false | 0/57 | 0.0% | null 57 |
| `urinary_frequency_false:bb59f573` | `urinary_frequency_false` | -- | false | 0/57 | 0.0% | null 57 |
| `urinary_frequency_false:44543d5e` | `urinary_frequency_false` | -- | false | 0/56 | 0.0% | null 56 |
| `urinary_frequency_false:f78f9d25` | `urinary_frequency_false` | -- | false | 0/56 | 0.0% | null 56 |
| `urinary_frequency_false:70687811` | `urinary_frequency_false` | -- | false | 0/55 | 0.0% | null 55 |
| `urinary_frequency_false:8a1fa086` | `urinary_frequency_false` | -- | false | 0/55 | 0.0% | null 55 |
| `urinary_frequency_true:2a4e0890` | `urinary_frequency_true` | -- | true | 0/55 | 0.0% | null 55 |
| `urinary_frequency_true:d01347c4` | `urinary_frequency_true` | -- | true | 0/55 | 0.0% | null 55 |
| `urinary_frequency_true:ffa90ce7` | `urinary_frequency_true` | -- | true | 0/55 | 0.0% | null 55 |
| `urinary_frequency_false:3f640028` | `urinary_frequency_false` | -- | false | 0/54 | 0.0% | null 54 |
| `urinary_frequency_false:838b4247` | `urinary_frequency_false` | -- | false | 0/54 | 0.0% | null 54 |
| `urinary_frequency_false:63302b59` | `urinary_frequency_false` | -- | false | 0/53 | 0.0% | null 53 |
| `urinary_frequency_false:99f7fbc1` | `urinary_frequency_false` | -- | false | 0/53 | 0.0% | null 53 |
| `urinary_frequency_false:c631660d` | `urinary_frequency_false` | -- | false | 0/51 | 0.0% | null 51 |
| `urinary_frequency_false:f324736d` | `urinary_frequency_false` | -- | false | 0/50 | 0.0% | null 50 |
| `urinary_frequency_false:42205311` | `urinary_frequency_false` | -- | false | 0/47 | 0.0% | null 47 |
| `urinary_frequency_false:941626e8` | `urinary_frequency_false` | -- | false | 0/47 | 0.0% | null 47 |
| `urinary_frequency_true:73717ed3` | `urinary_frequency_true` | -- | true | 0/47 | 0.0% | null 47 |
| `urinary_frequency_false:f32c9e68` | `urinary_frequency_false` | -- | false | 0/44 | 0.0% | null 44 |
| `urinary_frequency_false:fc6a56d2` | `urinary_frequency_false` | -- | false | 0/43 | 0.0% | null 43 |
| `urinary_frequency_true:87b688c8` | `urinary_frequency_true` | -- | true | 0/43 | 0.0% | null 43 |
| `urinary_frequency_false:6bb71206` | `urinary_frequency_false` | -- | false | 0/41 | 0.0% | null 41 |
| `urinary_frequency_true:2c452329` | `urinary_frequency_true` | -- | true | 0/41 | 0.0% | null 41 |

*54 further fragments with at least one error are in the JSON sidecar; every fragment is there regardless of score.*

## `arm_a_probe`

Frozen `roberta-base`, mean-pooled, with a `Linear(768, 3)` probe over the cached embeddings (2,307 parameters). The encoder learns nothing; only the probe is fitted. Expected to handle clear positives, clear negatives and `null_structural`, and to do badly on the four hard `null` sub-classes, which turn on compositional scope that a single pooled vector blurs. That is the predicted result rather than a fault, and it is what makes Arm B necessary: a weak probe cannot distinguish "the libraries are the bottleneck" from "the method is too weak".

Decision-rule margins selected per fold (on each fold's own validation split): 0.0, 0.05.

*Confusion matrix, raw argmax*

|  | pred false | pred true | pred null | total |
|---|---|---|---|---|
| **truth false** | 1524 | 277 | 678 | 2479 |
| **truth true** | 213 | 607 | 661 | 1481 |
| **truth null** | 273 | 233 | 5534 | 6040 |
| **total** | 2010 | 1117 | 6873 | 10000 |

`null -> true`: 233 of 6040 truly-null examples (3.86%).

*Confusion matrix, after the decision rule*

|  | pred false | pred true | pred null | total |
|---|---|---|---|---|
| **truth false** | 1530 | 268 | 681 | 2479 |
| **truth true** | 217 | 597 | 667 | 1481 |
| **truth null** | 278 | 223 | 5539 | 6040 |
| **total** | 2025 | 1088 | 6887 | 10000 |

`null -> true`: 223 of 6040 truly-null examples (3.69%).

### Per class, after the decision rule

| class | support | predicted | precision | recall | F1 |
|---|---|---|---|---|---|
| `false` | 2479 | 2025 | 75.6% | 61.7% | 67.9% |
| `true` | 1481 | 1088 | 54.9% | 40.3% | 46.5% |
| `null` | 6040 | 6887 | 80.4% | 91.7% | 85.7% |

### By label mode

| label mode | n | eff n | accuracy [95% CI] |
|---|---|---|---|
| false | 2479 | **46** | 61.7% [52.7%, 70.3%] |
| null_ambiguous | 3062 | **210** | 86.1% [83.2%, 88.6%] |
| null_structural | 2978 | **1** | 97.5% [97.5%, 97.5%] |
| true | 1481 | **46** | 40.3% [31.0%, 49.4%] |

### By null sub-class

| sub-class | n | eff n | null recall [95% CI] |
|---|---|---|---|
| adjacent | 588 | **40** | 90.6% [86.8%, 94.2%] |
| hedged | 620 | **42** | 77.1% [69.9%, 83.9%] |
| historical | 541 | **40** | 90.8% [85.6%, 95.3%] |
| metaphor | 673 | **44** | 92.3% [86.2%, 97.2%] |
| third_party | 640 | **44** | 80.0% [73.0%, 86.0%] |

### By fragment library

| library | n | eff n | accuracy [95% CI] |
|---|---|---|---|
| urinary_frequency_false | 2479 | **46** | 61.7% [52.7%, 70.3%] |
| urinary_frequency_null_adjacent | 588 | **40** | 90.6% [86.8%, 94.2%] |
| urinary_frequency_null_hedged | 620 | **42** | 77.1% [69.9%, 83.9%] |
| urinary_frequency_null_historical | 541 | **40** | 90.8% [85.6%, 95.3%] |
| urinary_frequency_null_metaphor | 673 | **44** | 92.3% [86.2%, 97.2%] |
| urinary_frequency_null_thirdparty | 640 | **44** | 80.0% [73.0%, 86.0%] |
| urinary_frequency_true | 1481 | **46** | 40.3% [31.0%, 49.4%] |
| (none) | 2978 | **1** | 97.5% [97.5%, 97.5%] |

### Per-fragment errors (worst first)

Whether errors are spread thinly across many fragments or piled onto a few is the difference
between "the method is too weak" (model work) and "these specific ideas are not learnable from
the data we have" (library work, and these are the fragments to write more of). No intervals:
a fragment is one cluster, so an interval over its own examples measures nothing.

204 of 302 decisive fragments were got wrong at least once.

`arm_a_probe`: 2260 errors across 204 of 302 decisive fragments. Half of them fall on **32** fragments (an even spread would be 102.0); the worst ten carry 23.0% of all errors.

| fragment | library | sub-class | truth | correct | accuracy | predicted as |
|---|---|---|---|---|---|---|
| `urinary_frequency_true:764389c0` | `urinary_frequency_true` | -- | true | 0/61 | 0.0% | false 11, null 50 |
| `urinary_frequency_true:ffa90ce7` | `urinary_frequency_true` | -- | true | 0/55 | 0.0% | null 55 |
| `urinary_frequency_true:32946372` | `urinary_frequency_true` | -- | true | 0/27 | 0.0% | false 15, null 12 |
| `urinary_frequency_true:32cae421` | `urinary_frequency_true` | -- | true | 0/21 | 0.0% | false 21 |
| `urinary_frequency_true:c8d32074` | `urinary_frequency_true` | -- | true | 0/14 | 0.0% | null 14 |
| `urinary_frequency_null_thirdparty:bf658595` | `urinary_frequency_null_thirdparty` | third_party | null | 0/13 | 0.0% | false 8, true 5 |
| `urinary_frequency_true:617cfdc3` | `urinary_frequency_true` | -- | true | 1/35 | 2.9% | false 6, true 1, null 28 |
| `urinary_frequency_true:f0e98801` | `urinary_frequency_true` | -- | true | 1/21 | 4.8% | false 6, true 1, null 14 |
| `urinary_frequency_true:2c452329` | `urinary_frequency_true` | -- | true | 3/41 | 7.3% | false 31, true 3, null 7 |
| `urinary_frequency_true:699a4e4a` | `urinary_frequency_true` | -- | true | 3/34 | 8.8% | true 3, null 31 |
| `urinary_frequency_null_metaphor:518f483f` | `urinary_frequency_null_metaphor` | metaphor | null | 2/17 | 11.8% | false 15, null 2 |
| `urinary_frequency_null_hedged:61fe8d58` | `urinary_frequency_null_hedged` | hedged | null | 2/15 | 13.3% | false 8, true 5, null 2 |
| `urinary_frequency_false:c631660d` | `urinary_frequency_false` | -- | false | 7/51 | 13.7% | false 7, null 44 |
| `urinary_frequency_true:87b688c8` | `urinary_frequency_true` | -- | true | 7/43 | 16.3% | false 3, true 7, null 33 |
| `urinary_frequency_false:6bb71206` | `urinary_frequency_false` | -- | false | 7/41 | 17.1% | false 7, null 34 |
| `urinary_frequency_false:b66fa498` | `urinary_frequency_false` | -- | false | 5/29 | 17.2% | false 5, true 13, null 11 |
| `urinary_frequency_false:44543d5e` | `urinary_frequency_false` | -- | false | 10/56 | 17.9% | false 10, true 24, null 22 |
| `urinary_frequency_true:1d671fe5` | `urinary_frequency_true` | -- | true | 5/27 | 18.5% | false 20, true 5, null 2 |
| `urinary_frequency_false:a9a59952` | `urinary_frequency_false` | -- | false | 12/64 | 18.8% | false 12, true 46, null 6 |
| `urinary_frequency_true:20bd4d56` | `urinary_frequency_true` | -- | true | 3/16 | 18.8% | true 3, null 13 |
| `urinary_frequency_false:3ce1d817` | `urinary_frequency_false` | -- | false | 8/40 | 20.0% | false 8, true 2, null 30 |
| `urinary_frequency_true:11d16987` | `urinary_frequency_true` | -- | true | 14/69 | 20.3% | false 4, true 14, null 51 |
| `urinary_frequency_false:941626e8` | `urinary_frequency_false` | -- | false | 10/47 | 21.3% | false 10, null 37 |
| `urinary_frequency_true:2491f080` | `urinary_frequency_true` | -- | true | 4/17 | 23.5% | true 4, null 13 |
| `urinary_frequency_true:fbca5613` | `urinary_frequency_true` | -- | true | 8/32 | 25.0% | false 2, true 8, null 22 |
| `urinary_frequency_false:1d7759da` | `urinary_frequency_false` | -- | false | 16/62 | 25.8% | false 16, true 3, null 43 |
| `urinary_frequency_false:8ea3ee34` | `urinary_frequency_false` | -- | false | 10/37 | 27.0% | false 10, true 3, null 24 |
| `urinary_frequency_true:900c8b2c` | `urinary_frequency_true` | -- | true | 9/33 | 27.3% | false 10, true 9, null 14 |
| `urinary_frequency_null_hedged:73e0bce7` | `urinary_frequency_null_hedged` | hedged | null | 4/14 | 28.6% | false 10, null 4 |
| `urinary_frequency_null_thirdparty:ef39e90f` | `urinary_frequency_null_thirdparty` | third_party | null | 5/17 | 29.4% | false 1, true 11, null 5 |
| `urinary_frequency_true:f91afcaa` | `urinary_frequency_true` | -- | true | 7/23 | 30.4% | false 2, true 7, null 14 |
| `urinary_frequency_null_thirdparty:d9aaf43b` | `urinary_frequency_null_thirdparty` | third_party | null | 4/13 | 30.8% | true 9, null 4 |
| `urinary_frequency_false:c85c9d5a` | `urinary_frequency_false` | -- | false | 10/32 | 31.2% | false 10, true 9, null 13 |
| `urinary_frequency_null_hedged:fe13847c` | `urinary_frequency_null_hedged` | hedged | null | 5/16 | 31.2% | false 9, true 2, null 5 |
| `urinary_frequency_null_metaphor:eb9e9615` | `urinary_frequency_null_metaphor` | metaphor | null | 5/16 | 31.2% | false 7, true 4, null 5 |
| `urinary_frequency_false:d293ee8c` | `urinary_frequency_false` | -- | false | 39/123 | 31.7% | false 39, true 69, null 15 |
| `urinary_frequency_true:c87f1579` | `urinary_frequency_true` | -- | true | 7/22 | 31.8% | false 5, true 7, null 10 |
| `urinary_frequency_true:3e2bc574` | `urinary_frequency_true` | -- | true | 12/37 | 32.4% | false 4, true 12, null 21 |
| `urinary_frequency_true:5ef90c41` | `urinary_frequency_true` | -- | true | 4/12 | 33.3% | false 1, true 4, null 7 |
| `urinary_frequency_false:cdacd51c` | `urinary_frequency_false` | -- | false | 21/60 | 35.0% | false 21, true 27, null 12 |

*164 further fragments with at least one error are in the JSON sidecar; every fragment is there regardless of score.*

## `arm_b_finetune`

`roberta-base` with **every layer unfrozen**, mean-pooled, with the same `Linear(768, 3)` head -- 110M trainable parameters against Arm A's 2,307. Three epochs at batch 32, learning rate 2e-5, 10% linear warmup, AdamW, fp32. No gradient checkpointing, no 8-bit optimiser, no LoRA, no gradient accumulation: the full model fits in 12GB with room to spare, so anything that reads like a compute compromise would be a mistake rather than a saving. This is the arm that separates "the fragment libraries are the bottleneck" from "the method is too weak": if a fully fine-tuned encoder still cannot read third-party attribution, tense or metaphor, the limit is in the ideas the libraries contain and the fix is library work, not model work.

Decision-rule margins selected per fold (on each fold's own validation split): 0.0, 0.05, 0.75, 0.9.

*Confusion matrix, raw argmax*

|  | pred false | pred true | pred null | total |
|---|---|---|---|---|
| **truth false** | 2064 | 253 | 162 | 2479 |
| **truth true** | 72 | 993 | 416 | 1481 |
| **truth null** | 13 | 146 | 5881 | 6040 |
| **total** | 2149 | 1392 | 6459 | 10000 |

`null -> true`: 146 of 6040 truly-null examples (2.42%).

*Confusion matrix, after the decision rule*

|  | pred false | pred true | pred null | total |
|---|---|---|---|---|
| **truth false** | 2085 | 223 | 171 | 2479 |
| **truth true** | 73 | 974 | 434 | 1481 |
| **truth null** | 16 | 117 | 5907 | 6040 |
| **total** | 2174 | 1314 | 6512 | 10000 |

`null -> true`: 117 of 6040 truly-null examples (1.94%).

### Per class, after the decision rule

| class | support | predicted | precision | recall | F1 |
|---|---|---|---|---|---|
| `false` | 2479 | 2174 | 95.9% | 84.1% | 89.6% |
| `true` | 1481 | 1314 | 74.1% | 65.8% | 69.7% |
| `null` | 6040 | 6512 | 90.7% | 97.8% | 94.1% |

### By label mode

| label mode | n | eff n | accuracy [95% CI] |
|---|---|---|---|
| false | 2479 | **46** | 84.1% [74.3%, 92.4%] |
| null_ambiguous | 3062 | **210** | 95.7% [93.0%, 97.8%] |
| null_structural | 2978 | **1** | 100.0% [100.0%, 100.0%] |
| true | 1481 | **46** | 65.8% [52.5%, 78.3%] |

### By null sub-class

| sub-class | n | eff n | null recall [95% CI] |
|---|---|---|---|
| adjacent | 588 | **40** | 94.7% [88.2%, 99.3%] |
| hedged | 620 | **42** | 90.2% [81.7%, 96.9%] |
| historical | 541 | **40** | 100.0% [100.0%, 100.0%] |
| metaphor | 673 | **44** | 95.1% [88.9%, 99.7%] |
| third_party | 640 | **44** | 98.8% [97.3%, 99.8%] |

### By fragment library

| library | n | eff n | accuracy [95% CI] |
|---|---|---|---|
| urinary_frequency_false | 2479 | **46** | 84.1% [74.3%, 92.4%] |
| urinary_frequency_null_adjacent | 588 | **40** | 94.7% [88.2%, 99.3%] |
| urinary_frequency_null_hedged | 620 | **42** | 90.2% [81.7%, 96.9%] |
| urinary_frequency_null_historical | 541 | **40** | 100.0% [100.0%, 100.0%] |
| urinary_frequency_null_metaphor | 673 | **44** | 95.1% [88.9%, 99.7%] |
| urinary_frequency_null_thirdparty | 640 | **44** | 98.8% [97.3%, 99.8%] |
| urinary_frequency_true | 1481 | **46** | 65.8% [52.5%, 78.3%] |
| (none) | 2978 | **1** | 100.0% [100.0%, 100.0%] |

### Per-fragment errors (worst first)

Whether errors are spread thinly across many fragments or piled onto a few is the difference
between "the method is too weak" (model work) and "these specific ideas are not learnable from
the data we have" (library work, and these are the fragments to write more of). No intervals:
a fragment is one cluster, so an interval over its own examples measures nothing.

66 of 302 decisive fragments were got wrong at least once.

`arm_b_finetune`: 1034 errors across 66 of 302 decisive fragments. Half of them fall on **11** fragments (an even spread would be 33.0); the worst ten carry 47.6% of all errors.

| fragment | library | sub-class | truth | correct | accuracy | predicted as |
|---|---|---|---|---|---|---|
| `urinary_frequency_false:a9a59952` | `urinary_frequency_false` | -- | false | 0/64 | 0.0% | true 64 |
| `urinary_frequency_true:764389c0` | `urinary_frequency_true` | -- | true | 0/61 | 0.0% | false 7, null 54 |
| `urinary_frequency_false:63302b59` | `urinary_frequency_false` | -- | false | 0/53 | 0.0% | true 53 |
| `urinary_frequency_true:617cfdc3` | `urinary_frequency_true` | -- | true | 0/35 | 0.0% | null 35 |
| `urinary_frequency_true:32946372` | `urinary_frequency_true` | -- | true | 0/27 | 0.0% | false 27 |
| `urinary_frequency_true:32cae421` | `urinary_frequency_true` | -- | true | 0/21 | 0.0% | false 21 |
| `urinary_frequency_true:f5216cf2` | `urinary_frequency_true` | -- | true | 0/18 | 0.0% | null 18 |
| `urinary_frequency_null_metaphor:518f483f` | `urinary_frequency_null_metaphor` | metaphor | null | 0/17 | 0.0% | false 2, true 15 |
| `urinary_frequency_null_hedged:ff5d90b8` | `urinary_frequency_null_hedged` | hedged | null | 0/15 | 0.0% | false 7, true 8 |
| `urinary_frequency_true:c8d32074` | `urinary_frequency_true` | -- | true | 0/14 | 0.0% | null 14 |
| `urinary_frequency_true:2c452329` | `urinary_frequency_true` | -- | true | 1/41 | 2.4% | false 15, true 1, null 25 |
| `urinary_frequency_true:11d16987` | `urinary_frequency_true` | -- | true | 2/69 | 2.9% | false 1, true 2, null 66 |
| `urinary_frequency_true:e746abc0` | `urinary_frequency_true` | -- | true | 1/31 | 3.2% | true 1, null 30 |
| `urinary_frequency_true:f9c03b9b` | `urinary_frequency_true` | -- | true | 1/24 | 4.2% | true 1, null 23 |
| `urinary_frequency_false:c631660d` | `urinary_frequency_false` | -- | false | 3/51 | 5.9% | false 3, null 48 |
| `urinary_frequency_null_adjacent:c791bce4` | `urinary_frequency_null_adjacent` | adjacent | null | 1/16 | 6.2% | true 15, null 1 |
| `urinary_frequency_null_hedged:41035ae0` | `urinary_frequency_null_hedged` | hedged | null | 1/13 | 7.7% | true 12, null 1 |
| `urinary_frequency_true:5ef90c41` | `urinary_frequency_true` | -- | true | 1/12 | 8.3% | true 1, null 11 |
| `urinary_frequency_null_hedged:5f612dfb` | `urinary_frequency_null_hedged` | hedged | null | 1/11 | 9.1% | false 1, true 9, null 1 |
| `urinary_frequency_true:2491f080` | `urinary_frequency_true` | -- | true | 2/17 | 11.8% | true 2, null 15 |
| `urinary_frequency_true:fbca5613` | `urinary_frequency_true` | -- | true | 4/32 | 12.5% | true 4, null 28 |
| `urinary_frequency_false:f32c9e68` | `urinary_frequency_false` | -- | false | 6/44 | 13.6% | false 6, true 38 |
| `urinary_frequency_null_hedged:bc056f4e` | `urinary_frequency_null_hedged` | hedged | null | 5/18 | 27.8% | true 13, null 5 |
| `urinary_frequency_false:f78f9d25` | `urinary_frequency_false` | -- | false | 20/56 | 35.7% | false 20, null 36 |
| `urinary_frequency_null_metaphor:eb9e9615` | `urinary_frequency_null_metaphor` | metaphor | null | 6/16 | 37.5% | true 10, null 6 |
| `urinary_frequency_false:6bb71206` | `urinary_frequency_false` | -- | false | 19/41 | 46.3% | false 19, true 17, null 5 |
| `urinary_frequency_true:5327793c` | `urinary_frequency_true` | -- | true | 13/27 | 48.1% | true 13, null 14 |
| `urinary_frequency_false:ec8210fb` | `urinary_frequency_false` | -- | false | 15/31 | 48.4% | false 15, null 16 |
| `urinary_frequency_true:ffa90ce7` | `urinary_frequency_true` | -- | true | 30/55 | 54.5% | true 30, null 25 |
| `urinary_frequency_true:fecb0185` | `urinary_frequency_true` | -- | true | 16/28 | 57.1% | true 16, null 12 |
| `urinary_frequency_null_adjacent:3d4efe39` | `urinary_frequency_null_adjacent` | adjacent | null | 10/17 | 58.8% | true 7, null 10 |
| `urinary_frequency_true:35a67edf` | `urinary_frequency_true` | -- | true | 20/33 | 60.6% | true 20, null 13 |
| `urinary_frequency_false:44543d5e` | `urinary_frequency_false` | -- | false | 34/56 | 60.7% | false 34, true 22 |
| `urinary_frequency_true:73717ed3` | `urinary_frequency_true` | -- | true | 29/47 | 61.7% | true 29, null 18 |
| `urinary_frequency_true:3e2bc574` | `urinary_frequency_true` | -- | true | 23/37 | 62.2% | true 23, null 14 |
| `urinary_frequency_null_adjacent:15320912` | `urinary_frequency_null_adjacent` | adjacent | null | 10/16 | 62.5% | true 6, null 10 |
| `urinary_frequency_false:a15017c2` | `urinary_frequency_false` | -- | false | 87/137 | 63.5% | false 87, true 9, null 41 |
| `urinary_frequency_false:941626e8` | `urinary_frequency_false` | -- | false | 33/47 | 70.2% | false 33, null 14 |
| `urinary_frequency_null_thirdparty:a995a326` | `urinary_frequency_null_thirdparty` | third_party | null | 11/15 | 73.3% | true 4, null 11 |
| `urinary_frequency_true:95d4e96a` | `urinary_frequency_true` | -- | true | 15/20 | 75.0% | true 15, null 5 |

*26 further fragments with at least one error are in the JSON sidecar; every fragment is there regardless of score.*

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
| false | 2479 | **46** | 0.0% [0.0%, 0.0%] |
| null_ambiguous | 3062 | **210** | 100.0% [100.0%, 100.0%] |
| null_structural | 2978 | **1** | 100.0% [100.0%, 100.0%] |
| true | 1481 | **46** | 0.0% [0.0%, 0.0%] |

### By null sub-class

| sub-class | n | eff n | null recall [95% CI] |
|---|---|---|---|
| adjacent | 588 | **40** | 100.0% [100.0%, 100.0%] |
| hedged | 620 | **42** | 100.0% [100.0%, 100.0%] |
| historical | 541 | **40** | 100.0% [100.0%, 100.0%] |
| metaphor | 673 | **44** | 100.0% [100.0%, 100.0%] |
| third_party | 640 | **44** | 100.0% [100.0%, 100.0%] |

### By fragment library

| library | n | eff n | accuracy [95% CI] |
|---|---|---|---|
| urinary_frequency_false | 2479 | **46** | 0.0% [0.0%, 0.0%] |
| urinary_frequency_null_adjacent | 588 | **40** | 100.0% [100.0%, 100.0%] |
| urinary_frequency_null_hedged | 620 | **42** | 100.0% [100.0%, 100.0%] |
| urinary_frequency_null_historical | 541 | **40** | 100.0% [100.0%, 100.0%] |
| urinary_frequency_null_metaphor | 673 | **44** | 100.0% [100.0%, 100.0%] |
| urinary_frequency_null_thirdparty | 640 | **44** | 100.0% [100.0%, 100.0%] |
| urinary_frequency_true | 1481 | **46** | 0.0% [0.0%, 0.0%] |
| (none) | 2978 | **1** | 100.0% [100.0%, 100.0%] |

### Per-fragment errors (worst first)

Whether errors are spread thinly across many fragments or piled onto a few is the difference
between "the method is too weak" (model work) and "these specific ideas are not learnable from
the data we have" (library work, and these are the fragments to write more of). No intervals:
a fragment is one cluster, so an interval over its own examples measures nothing.

92 of 302 decisive fragments were got wrong at least once.

`arm_b_finetune__shuffled`: 3960 errors across 92 of 302 decisive fragments. Half of them fall on **30** fragments (an even spread would be 46.0); the worst ten carry 22.7% of all errors.

| fragment | library | sub-class | truth | correct | accuracy | predicted as |
|---|---|---|---|---|---|---|
| `urinary_frequency_false:a15017c2` | `urinary_frequency_false` | -- | false | 0/137 | 0.0% | null 137 |
| `urinary_frequency_false:22b965f9` | `urinary_frequency_false` | -- | false | 0/123 | 0.0% | null 123 |
| `urinary_frequency_false:d293ee8c` | `urinary_frequency_false` | -- | false | 0/123 | 0.0% | null 123 |
| `urinary_frequency_false:a7fe81d1` | `urinary_frequency_false` | -- | false | 0/121 | 0.0% | null 121 |
| `urinary_frequency_true:11d16987` | `urinary_frequency_true` | -- | true | 0/69 | 0.0% | null 69 |
| `urinary_frequency_false:6c16f65e` | `urinary_frequency_false` | -- | false | 0/67 | 0.0% | null 67 |
| `urinary_frequency_true:272d2041` | `urinary_frequency_true` | -- | true | 0/67 | 0.0% | null 67 |
| `urinary_frequency_false:7fc83941` | `urinary_frequency_false` | -- | false | 0/65 | 0.0% | null 65 |
| `urinary_frequency_false:a9a59952` | `urinary_frequency_false` | -- | false | 0/64 | 0.0% | null 64 |
| `urinary_frequency_false:1d7759da` | `urinary_frequency_false` | -- | false | 0/62 | 0.0% | null 62 |
| `urinary_frequency_false:f3e3b17c` | `urinary_frequency_false` | -- | false | 0/62 | 0.0% | null 62 |
| `urinary_frequency_true:764389c0` | `urinary_frequency_true` | -- | true | 0/61 | 0.0% | null 61 |
| `urinary_frequency_false:cdacd51c` | `urinary_frequency_false` | -- | false | 0/60 | 0.0% | null 60 |
| `urinary_frequency_false:767e3f26` | `urinary_frequency_false` | -- | false | 0/58 | 0.0% | null 58 |
| `urinary_frequency_false:a5342750` | `urinary_frequency_false` | -- | false | 0/58 | 0.0% | null 58 |
| `urinary_frequency_false:c7b96e67` | `urinary_frequency_false` | -- | false | 0/58 | 0.0% | null 58 |
| `urinary_frequency_false:0c947cff` | `urinary_frequency_false` | -- | false | 0/57 | 0.0% | null 57 |
| `urinary_frequency_false:1a4ef542` | `urinary_frequency_false` | -- | false | 0/57 | 0.0% | null 57 |
| `urinary_frequency_false:bb59f573` | `urinary_frequency_false` | -- | false | 0/57 | 0.0% | null 57 |
| `urinary_frequency_false:44543d5e` | `urinary_frequency_false` | -- | false | 0/56 | 0.0% | null 56 |
| `urinary_frequency_false:f78f9d25` | `urinary_frequency_false` | -- | false | 0/56 | 0.0% | null 56 |
| `urinary_frequency_false:70687811` | `urinary_frequency_false` | -- | false | 0/55 | 0.0% | null 55 |
| `urinary_frequency_false:8a1fa086` | `urinary_frequency_false` | -- | false | 0/55 | 0.0% | null 55 |
| `urinary_frequency_true:2a4e0890` | `urinary_frequency_true` | -- | true | 0/55 | 0.0% | null 55 |
| `urinary_frequency_true:d01347c4` | `urinary_frequency_true` | -- | true | 0/55 | 0.0% | null 55 |
| `urinary_frequency_true:ffa90ce7` | `urinary_frequency_true` | -- | true | 0/55 | 0.0% | null 55 |
| `urinary_frequency_false:3f640028` | `urinary_frequency_false` | -- | false | 0/54 | 0.0% | null 54 |
| `urinary_frequency_false:838b4247` | `urinary_frequency_false` | -- | false | 0/54 | 0.0% | null 54 |
| `urinary_frequency_false:63302b59` | `urinary_frequency_false` | -- | false | 0/53 | 0.0% | null 53 |
| `urinary_frequency_false:99f7fbc1` | `urinary_frequency_false` | -- | false | 0/53 | 0.0% | null 53 |
| `urinary_frequency_false:c631660d` | `urinary_frequency_false` | -- | false | 0/51 | 0.0% | null 51 |
| `urinary_frequency_false:f324736d` | `urinary_frequency_false` | -- | false | 0/50 | 0.0% | null 50 |
| `urinary_frequency_false:42205311` | `urinary_frequency_false` | -- | false | 0/47 | 0.0% | null 47 |
| `urinary_frequency_false:941626e8` | `urinary_frequency_false` | -- | false | 0/47 | 0.0% | null 47 |
| `urinary_frequency_true:73717ed3` | `urinary_frequency_true` | -- | true | 0/47 | 0.0% | null 47 |
| `urinary_frequency_false:f32c9e68` | `urinary_frequency_false` | -- | false | 0/44 | 0.0% | null 44 |
| `urinary_frequency_false:fc6a56d2` | `urinary_frequency_false` | -- | false | 0/43 | 0.0% | null 43 |
| `urinary_frequency_true:87b688c8` | `urinary_frequency_true` | -- | true | 0/43 | 0.0% | null 43 |
| `urinary_frequency_false:6bb71206` | `urinary_frequency_false` | -- | false | 0/41 | 0.0% | null 41 |
| `urinary_frequency_true:2c452329` | `urinary_frequency_true` | -- | true | 0/41 | 0.0% | null 41 |

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
| 0 | 10000 | 2000 | 2000 | 0.0 | 60.5% | 60.5% | 25.1% | 0.00% |
| 1 | 10000 | 2000 | 2000 | 0.0 | 60.1% | 60.1% | 25.0% | 0.00% |
| 2 | 10000 | 2000 | 2000 | 0.0 | 60.4% | 60.4% | 25.1% | 0.00% |
| 3 | 10000 | 2000 | 2000 | 0.0 | 60.8% | 60.8% | 25.2% | 0.00% |
| 4 | 10000 | 2000 | 2000 | 0.0 | 60.3% | 60.3% | 25.1% | 0.00% |

### `tfidf_logreg`

| fold | train n | val n | test n | margin | acc (raw) | acc (ruled) | macro-F1 | null->true |
|---|---|---|---|---|---|---|---|---|
| 0 | 10000 | 2000 | 2000 | 0.0 | 71.8% | 71.8% | 57.2% | 4.88% |
| 1 | 10000 | 2000 | 2000 | 0.0 | 69.7% | 69.7% | 49.3% | 1.33% |
| 2 | 10000 | 2000 | 2000 | 0.0 | 66.9% | 66.9% | 43.4% | 0.91% |
| 3 | 10000 | 2000 | 2000 | 0.15 | 75.5% | 75.8% | 53.9% | 0.58% |
| 4 | 10000 | 2000 | 2000 | 0.0 | 74.2% | 74.2% | 57.9% | 3.65% |

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
| 3 | 10000 | 2000 | 2000 | 0.0 | 60.6% | 60.6% | 25.1% | 0.00% |
| 4 | 10000 | 2000 | 2000 | 0.0 | 60.3% | 60.3% | 25.1% | 0.00% |

### `arm_a_probe`

| fold | train n | val n | test n | margin | acc (raw) | acc (ruled) | macro-F1 | null->true |
|---|---|---|---|---|---|---|---|---|
| 0 | 10000 | 2000 | 2000 | 0.0 | 77.9% | 77.9% | 69.2% | 6.29% |
| 1 | 10000 | 2000 | 2000 | 0.0 | 75.0% | 75.0% | 62.4% | 1.33% |
| 2 | 10000 | 2000 | 2000 | 0.0 | 73.6% | 73.6% | 61.9% | 3.48% |
| 3 | 10000 | 2000 | 2000 | 0.0 | 80.3% | 80.3% | 71.0% | 3.13% |
| 4 | 10000 | 2000 | 2000 | 0.05 | 76.5% | 76.5% | 67.7% | 4.23% |

### `arm_b_finetune`

| fold | train n | val n | test n | margin | acc (raw) | acc (ruled) | macro-F1 | null->true |
|---|---|---|---|---|---|---|---|---|
| 0 | 10000 | 2000 | 2000 | 0.05 | 93.4% | 93.4% | 89.4% | 0.66% |
| 1 | 10000 | 2000 | 2000 | 0.0 | 82.0% | 82.0% | 73.0% | 2.25% |
| 2 | 10000 | 2000 | 2000 | 0.05 | 87.2% | 87.2% | 78.8% | 2.90% |
| 3 | 10000 | 2000 | 2000 | 0.75 | 92.7% | 92.8% | 88.8% | 0.41% |
| 4 | 10000 | 2000 | 2000 | 0.9 | 91.7% | 92.9% | 90.8% | 3.48% |

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

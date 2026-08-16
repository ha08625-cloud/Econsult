# Encoder training: evaluation report

*Generated 2026-08-16T10:10:42+00:00.*

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
| artefacts | `models/encoder/flank_pain_present/arm_b_finetune` |
| weights | `models/encoder/flank_pain_present/arm_b_finetune/weights -- ~440MB per fold, not committed` |
| model revision | `e2da8e2f811d1448a5b465c236feacd80ffbac7b` |
| revision pinned | `False` |
| tokeniser lowercases | `False` |
| tokeniser vocab size | `50265` |
| tokeniser discards casing | `False` |
| cluster tag coverage | `0 of 5 libraries carry cluster markers; 243 of 243 fragments are in libraries with none` |
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
| `arm_a_probe` | probe | 7022 | **243** | 80.7% [77.1%, 84.1%] | 80.2% [76.3%, 83.8%] | 86.2% | 86.2% +/- 3.0% |
| `arm_b_finetune` | finetune | 7022 | **243** | 96.0% [93.2%, 98.2%] | 95.9% [93.2%, 98.0%] | 97.2% | 97.2% +/- 2.1% |
| `arm_b_finetune__shuffled` | negative control | 7022 | **243** | 43.6% [37.3%, 50.3%] | 20.2% [18.1%, 22.3%] | 60.4% | 60.4% +/- 0.2% |

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
| `arm_a_probe` | -- | -- | 83.1% [76.6%, 89.1%] (eff n 53) | 94.2% [90.6%, 97.2%] (eff n 40) | -- | 93.3% [90.3%, 96.1%] (eff n 47) |
| `arm_b_finetune` | -- | -- | 93.4% [86.0%, 99.3%] (eff n 53) | 98.5% [95.4%, 100.0%] (eff n 40) | -- | 97.4% [92.8%, 100.0%] (eff n 47) |
| `arm_b_finetune__shuffled` | -- | -- | 100.0% [100.0%, 100.0%] (eff n 53) | 100.0% [100.0%, 100.0%] (eff n 40) | -- | 100.0% [100.0%, 100.0%] (eff n 47) |

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
| `arm_a_probe` | probe | 3062 | **140** | 89.6% [86.7%, 92.3%] |
| `arm_b_finetune` | finetune | 3062 | **140** | 96.2% [92.7%, 99.0%] |

### 2. The same comparison, paired

Two overlapping intervals do not settle whether one model beats another on the same
examples. McNemar does, over the examples the two disagree about -- read it alongside the
intervals above, never instead of them.

| pair | n | a only | b only | p |
|---|---|---|---|---|
| `majority_class` vs `length_only` | 3062 | 0 | 0 | 1 |
| `majority_class` vs `tfidf_logreg` | 3062 | 260 | 0 | 1.08e-78 |
| `majority_class` vs `arm_a_probe` | 3062 | 331 | 0 | 4.57e-100 |
| `majority_class` vs `arm_b_finetune` | 3062 | 124 | 0 | 9.4e-38 |
| `length_only` vs `tfidf_logreg` | 3062 | 260 | 0 | 1.08e-78 |
| `length_only` vs `arm_a_probe` | 3062 | 331 | 0 | 4.57e-100 |
| `length_only` vs `arm_b_finetune` | 3062 | 124 | 0 | 9.4e-38 |
| `tfidf_logreg` vs `arm_a_probe` | 3062 | 247 | 176 | 0.000648 |
| `tfidf_logreg` vs `arm_b_finetune` | 3062 | 101 | 237 | 9.71e-14 |
| `arm_a_probe` vs `arm_b_finetune` | 3062 | 69 | 276 | 1.88e-30 |

### 3. Where the errors fall

The per-fragment table below, as one number per model. Errors spread thinly across many
fragments say the method is too weak. Errors piled onto a handful say those specific ideas
are not learnable from the data we have -- and the table names them, which is what makes
this the most decision-useful thing in the report.

* `majority_class`: 3960 errors across 103 of 243 decisive fragments. Half of them fall on **37** fragments (an even spread would be 51.5); the worst ten carry 17.0% of all errors.
* `length_only`: 3960 errors across 103 of 243 decisive fragments. Half of them fall on **37** fragments (an even spread would be 51.5); the worst ten carry 17.0% of all errors.
* `tfidf_logreg`: 1913 errors across 119 of 243 decisive fragments. Half of them fall on **23** fragments (an even spread would be 59.5); the worst ten carry 26.6% of all errors.
* `arm_a_probe`: 1358 errors across 156 of 243 decisive fragments. Half of them fall on **23** fragments (an even spread would be 78.0); the worst ten carry 28.0% of all errors.
* `arm_b_finetune`: 280 errors across 22 of 243 decisive fragments. Half of them fall on **4** fragments (an even spread would be 11.0); the worst ten carry 89.6% of all errors.

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
| `length_only__shuffled` | 60.4% [39.0%, 76.9%] | 25.1% [18.7%, 29.0%] |
| `tfidf_logreg__shuffled` | 60.4% [39.0%, 76.9%] | 25.1% [18.7%, 29.0%] |
| `arm_b_finetune__shuffled` | 60.4% [39.0%, 76.9%] | 25.1% [18.7%, 29.0%] |

## Paired comparisons (McNemar, raw argmax)

Exact two-sided McNemar over the examples the two models disagree about. Pairing unit is the
example, not the cluster -- see the limitations.

| pair | slice | n | a only | b only | p |
|---|---|---|---|---|---|
| `majority_class` vs `length_only` | overall | 10000 | 0 | 0 | 1 |
| `majority_class` vs `length_only` | null_ambiguous | 3062 | 0 | 0 | 1 |
| `majority_class` vs `tfidf_logreg` | overall | 10000 | 264 | 2307 | 0 |
| `majority_class` vs `tfidf_logreg` | null_ambiguous | 3062 | 260 | 0 | 1.08e-78 |
| `majority_class` vs `arm_a_probe` | overall | 10000 | 348 | 2935 | 0 |
| `majority_class` vs `arm_a_probe` | null_ambiguous | 3062 | 331 | 0 | 4.57e-100 |
| `majority_class` vs `arm_b_finetune` | overall | 10000 | 125 | 3798 | 0 |
| `majority_class` vs `arm_b_finetune` | null_ambiguous | 3062 | 124 | 0 | 9.4e-38 |
| `length_only` vs `tfidf_logreg` | overall | 10000 | 264 | 2307 | 0 |
| `length_only` vs `tfidf_logreg` | null_ambiguous | 3062 | 260 | 0 | 1.08e-78 |
| `length_only` vs `arm_a_probe` | overall | 10000 | 348 | 2935 | 0 |
| `length_only` vs `arm_a_probe` | null_ambiguous | 3062 | 331 | 0 | 4.57e-100 |
| `length_only` vs `arm_b_finetune` | overall | 10000 | 125 | 3798 | 0 |
| `length_only` vs `arm_b_finetune` | null_ambiguous | 3062 | 124 | 0 | 9.4e-38 |
| `tfidf_logreg` vs `arm_a_probe` | overall | 10000 | 540 | 1084 | 3.77e-42 |
| `tfidf_logreg` vs `arm_a_probe` | null_ambiguous | 3062 | 247 | 176 | 0.000648 |
| `tfidf_logreg` vs `arm_b_finetune` | overall | 10000 | 115 | 1745 | 0 |
| `tfidf_logreg` vs `arm_b_finetune` | null_ambiguous | 3062 | 101 | 237 | 9.71e-14 |
| `arm_a_probe` vs `arm_b_finetune` | overall | 10000 | 93 | 1179 | 3.83e-240 |
| `arm_a_probe` vs `arm_b_finetune` | null_ambiguous | 3062 | 69 | 276 | 1.88e-30 |

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
| `flank_pain_false` | 2479 | 0.0% | 0.0% | 61.1% | 74.1% | 95.2% | 95.2pp |
| `flank_pain_true` | 1481 | 0.0% | 0.0% | 53.5% | 73.0% | 96.9% | 96.9pp |
| `flank_pain_null_hedged` | 1170 | 100.0% | 100.0% | 89.4% | 83.1% | 93.4% | 16.9pp |
| `flank_pain_null_historical` | 874 | 100.0% | 100.0% | 89.1% | 94.2% | 98.5% | 10.9pp |
| `flank_pain_null_thirdparty` | 1018 | 100.0% | 100.0% | 96.0% | 93.3% | 97.4% | 6.7pp |
| `(none)` | 2978 | 100.0% | 100.0% | 99.9% | 99.4% | 100.0% | 0.6pp |

### By fragment, errors

Ordered by the worst model's error count, so the fragments the comparison is about sort
to the top whichever encoder wins. Counts, not rates: these are the sentences a month of
library work would be spent on. The JSON holds every fragment.

| fragment | library | truth | `majority_class` | `length_only` | `tfidf_logreg` | `arm_a_probe` | `arm_b_finetune` | spread |
|---|---|---|---|---|---|---|---|---|
| `flank_pain_false:4782be93` | `flank_pain_false` | false | 81 | 81 | 37 | 13 | 0 | 81 |
| `flank_pain_false:4d4ec138` | `flank_pain_false` | false | 78 | 78 | 78 | 39 | 0 | 78 |
| `flank_pain_false:7b34cfc0` | `flank_pain_false` | false | 75 | 75 | 14 | 29 | 0 | 75 |
| `flank_pain_false:80bb4b40` | `flank_pain_false` | false | 74 | 74 | 51 | 8 | 0 | 74 |
| `flank_pain_false:9b1cee9c` | `flank_pain_false` | false | 64 | 64 | 0 | 0 | 0 | 64 |
| `flank_pain_false:76bc0785` | `flank_pain_false` | false | 61 | 61 | 5 | 26 | 0 | 61 |
| `flank_pain_false:d439a7ee` | `flank_pain_false` | false | 61 | 61 | 3 | 0 | 0 | 61 |
| `flank_pain_false:42aa75a8` | `flank_pain_false` | false | 60 | 60 | 10 | 10 | 0 | 60 |
| `flank_pain_false:71da3a84` | `flank_pain_false` | false | 60 | 60 | 29 | 6 | 0 | 60 |
| `flank_pain_false:be00686d` | `flank_pain_false` | false | 60 | 60 | 0 | 2 | 0 | 60 |
| `flank_pain_false:a2c9e38d` | `flank_pain_false` | false | 58 | 58 | 56 | 5 | 0 | 58 |
| `flank_pain_true:faa371b2` | `flank_pain_true` | true | 55 | 55 | 11 | 1 | 0 | 55 |
| `flank_pain_false:6c762141` | `flank_pain_false` | false | 54 | 54 | 51 | 40 | 0 | 54 |
| `flank_pain_false:9ba1c8d3` | `flank_pain_false` | false | 52 | 52 | 3 | 4 | 0 | 52 |
| `flank_pain_false:ad38bb4f` | `flank_pain_false` | false | 52 | 52 | 5 | 8 | 0 | 52 |
| `flank_pain_false:bead93da` | `flank_pain_false` | false | 52 | 52 | 52 | 43 | 52 | 9 |
| `flank_pain_false:3273a39a` | `flank_pain_false` | false | 51 | 51 | 11 | 4 | 0 | 51 |
| `flank_pain_false:d37c1465` | `flank_pain_false` | false | 51 | 51 | 43 | 13 | 0 | 51 |
| `flank_pain_false:4947dcd5` | `flank_pain_false` | false | 50 | 50 | 40 | 31 | 0 | 50 |
| `flank_pain_false:924082ae` | `flank_pain_false` | false | 50 | 50 | 0 | 3 | 0 | 50 |
| `flank_pain_false:9ed5cbe0` | `flank_pain_false` | false | 50 | 50 | 0 | 21 | 0 | 50 |
| `flank_pain_false:37373d48` | `flank_pain_false` | false | 49 | 49 | 36 | 28 | 0 | 49 |
| `flank_pain_false:a31e1604` | `flank_pain_false` | false | 49 | 49 | 0 | 5 | 0 | 49 |
| `flank_pain_false:d7abb5ec` | `flank_pain_false` | false | 49 | 49 | 49 | 49 | 49 | 0 |
| `flank_pain_false:f900bfea` | `flank_pain_false` | false | 49 | 49 | 40 | 11 | 0 | 49 |
| `flank_pain_false:132f591d` | `flank_pain_false` | false | 48 | 48 | 29 | 4 | 0 | 48 |
| `flank_pain_false:6cd7f2f5` | `flank_pain_false` | false | 48 | 48 | 32 | 0 | 0 | 48 |
| `flank_pain_true:801b09f3` | `flank_pain_true` | true | 48 | 48 | 48 | 46 | 1 | 47 |
| `flank_pain_false:6f0b7381` | `flank_pain_false` | false | 47 | 47 | 0 | 0 | 0 | 47 |
| `flank_pain_false:f63b22a5` | `flank_pain_false` | false | 47 | 47 | 15 | 9 | 12 | 38 |
| `flank_pain_false:0d8df7a0` | `flank_pain_false` | false | 45 | 45 | 38 | 27 | 0 | 45 |
| `flank_pain_false:57d966db` | `flank_pain_false` | false | 44 | 44 | 0 | 0 | 0 | 44 |
| `flank_pain_true:78957d62` | `flank_pain_true` | true | 44 | 44 | 0 | 0 | 0 | 44 |
| `flank_pain_false:27c1ea49` | `flank_pain_false` | false | 43 | 43 | 0 | 2 | 0 | 43 |
| `flank_pain_false:7f0a359d` | `flank_pain_false` | false | 43 | 43 | 0 | 0 | 0 | 43 |
| `flank_pain_false:b4c43f30` | `flank_pain_false` | false | 43 | 43 | 0 | 0 | 0 | 43 |
| `flank_pain_false:b27cde7b` | `flank_pain_false` | false | 41 | 41 | 0 | 0 | 0 | 41 |
| `flank_pain_true:ec43ab8c` | `flank_pain_true` | true | 41 | 41 | 41 | 2 | 0 | 41 |
| `flank_pain_false:536a4cfe` | `flank_pain_false` | false | 40 | 40 | 9 | 2 | 0 | 40 |
| `flank_pain_false:69f1f2f7` | `flank_pain_false` | false | 40 | 40 | 21 | 5 | 0 | 40 |

*148 further fragments erred on at least one model; the JSON holds them all.*

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

## `arm_a_probe`

Frozen `roberta-base`, mean-pooled, with a `Linear(768, 3)` probe over the cached embeddings (2,307 parameters). The encoder learns nothing; only the probe is fitted. Expected to handle clear positives, clear negatives and `null_structural`, and to do badly on the four hard `null` sub-classes, which turn on compositional scope that a single pooled vector blurs. That is the predicted result rather than a fault, and it is what makes Arm B necessary: a weak probe cannot distinguish "the libraries are the bottleneck" from "the method is too weak".

Decision-rule margins selected per fold (on each fold's own validation split): 0.0, 0.05, 0.1.

*Confusion matrix, raw argmax*

|  | pred false | pred true | pred null | total |
|---|---|---|---|---|
| **truth false** | 1833 | 74 | 572 | 2479 |
| **truth true** | 85 | 1102 | 294 | 1481 |
| **truth null** | 209 | 139 | 5692 | 6040 |
| **total** | 2127 | 1315 | 6558 | 10000 |

`null -> true`: 139 of 6040 truly-null examples (2.30%).

*Confusion matrix, after the decision rule*

|  | pred false | pred true | pred null | total |
|---|---|---|---|---|
| **truth false** | 1838 | 69 | 572 | 2479 |
| **truth true** | 96 | 1081 | 304 | 1481 |
| **truth null** | 212 | 122 | 5706 | 6040 |
| **total** | 2146 | 1272 | 6582 | 10000 |

`null -> true`: 122 of 6040 truly-null examples (2.02%).

### Per class, after the decision rule

| class | support | predicted | precision | recall | F1 |
|---|---|---|---|---|---|
| `false` | 2479 | 2146 | 85.6% | 74.1% | 79.5% |
| `true` | 1481 | 1272 | 85.0% | 73.0% | 78.5% |
| `null` | 6040 | 6582 | 86.7% | 94.5% | 90.4% |

### By label mode

| label mode | n | eff n | accuracy [95% CI] |
|---|---|---|---|
| false | 2479 | **55** | 74.1% [66.3%, 81.4%] |
| null_ambiguous | 3062 | **140** | 89.6% [86.7%, 92.3%] |
| null_structural | 2978 | **1** | 99.4% [99.4%, 99.4%] |
| true | 1481 | **48** | 73.0% [63.3%, 82.3%] |

### By null sub-class

| sub-class | n | eff n | null recall [95% CI] |
|---|---|---|---|
| hedged | 1170 | **53** | 83.1% [76.6%, 89.1%] |
| historical | 874 | **40** | 94.2% [90.6%, 97.2%] |
| third_party | 1018 | **47** | 93.3% [90.3%, 96.1%] |

### By fragment library

| library | n | eff n | accuracy [95% CI] |
|---|---|---|---|
| flank_pain_false | 2479 | **55** | 74.1% [66.3%, 81.4%] |
| flank_pain_null_hedged | 1170 | **53** | 83.1% [76.6%, 89.1%] |
| flank_pain_null_historical | 874 | **40** | 94.2% [90.6%, 97.2%] |
| flank_pain_null_thirdparty | 1018 | **47** | 93.3% [90.3%, 96.1%] |
| flank_pain_true | 1481 | **48** | 73.0% [63.3%, 82.3%] |
| (none) | 2978 | **1** | 99.4% [99.4%, 99.4%] |

### Per-fragment errors (worst first)

Whether errors are spread thinly across many fragments or piled onto a few is the difference
between "the method is too weak" (model work) and "these specific ideas are not learnable from
the data we have" (library work, and these are the fragments to write more of). No intervals:
a fragment is one cluster, so an interval over its own examples measures nothing.

156 of 243 decisive fragments were got wrong at least once.

`arm_a_probe`: 1358 errors across 156 of 243 decisive fragments. Half of them fall on **23** fragments (an even spread would be 78.0); the worst ten carry 28.0% of all errors.

| fragment | library | sub-class | truth | correct | accuracy | predicted as |
|---|---|---|---|---|---|---|
| `flank_pain_false:d7abb5ec` | `flank_pain_false` | -- | false | 0/49 | 0.0% | null 49 |
| `flank_pain_false:cbb11cce` | `flank_pain_false` | -- | false | 1/27 | 3.7% | false 1, true 1, null 25 |
| `flank_pain_true:801b09f3` | `flank_pain_true` | -- | true | 2/48 | 4.2% | true 2, null 46 |
| `flank_pain_true:568725bb` | `flank_pain_true` | -- | true | 2/39 | 5.1% | false 1, true 2, null 36 |
| `flank_pain_true:cb7fde42` | `flank_pain_true` | -- | true | 1/19 | 5.3% | true 1, null 18 |
| `flank_pain_false:b927c3ee` | `flank_pain_false` | -- | false | 2/29 | 6.9% | false 2, null 27 |
| `flank_pain_false:0468979b` | `flank_pain_false` | -- | false | 3/36 | 8.3% | false 3, null 33 |
| `flank_pain_true:a326ab18` | `flank_pain_true` | -- | true | 3/35 | 8.6% | false 6, true 3, null 26 |
| `flank_pain_null_hedged:d17ed4ab` | `flank_pain_null_hedged` | hedged | null | 2/18 | 11.1% | false 7, true 9, null 2 |
| `flank_pain_true:214c674e` | `flank_pain_true` | -- | true | 3/26 | 11.5% | false 21, true 3, null 2 |
| `flank_pain_true:37a629d7` | `flank_pain_true` | -- | true | 4/34 | 11.8% | false 7, true 4, null 23 |
| `flank_pain_false:bead93da` | `flank_pain_false` | -- | false | 9/52 | 17.3% | false 9, null 43 |
| `flank_pain_false:1777a47f` | `flank_pain_false` | -- | false | 6/25 | 24.0% | false 6, null 19 |
| `flank_pain_false:6c762141` | `flank_pain_false` | -- | false | 14/54 | 25.9% | false 14, null 40 |
| `flank_pain_true:16e00186` | `flank_pain_true` | -- | true | 9/31 | 29.0% | false 22, true 9 |
| `flank_pain_null_hedged:52c46ca3` | `flank_pain_null_hedged` | hedged | null | 8/26 | 30.8% | false 17, true 1, null 8 |
| `flank_pain_null_hedged:0f9ee32b` | `flank_pain_null_hedged` | hedged | null | 8/24 | 33.3% | false 16, null 8 |
| `flank_pain_null_thirdparty:b444dd39` | `flank_pain_null_thirdparty` | third_party | null | 6/16 | 37.5% | false 10, null 6 |
| `flank_pain_false:4947dcd5` | `flank_pain_false` | -- | false | 19/50 | 38.0% | false 19, null 31 |
| `flank_pain_null_hedged:e31c9f3a` | `flank_pain_null_hedged` | hedged | null | 8/21 | 38.1% | true 13, null 8 |
| `flank_pain_true:be1f0c8f` | `flank_pain_true` | -- | true | 8/21 | 38.1% | false 1, true 8, null 12 |
| `flank_pain_false:0d8df7a0` | `flank_pain_false` | -- | false | 18/45 | 40.0% | false 18, null 27 |
| `flank_pain_true:d7d705f6` | `flank_pain_true` | -- | true | 15/36 | 41.7% | false 9, true 15, null 12 |
| `flank_pain_false:37373d48` | `flank_pain_false` | -- | false | 21/49 | 42.9% | false 21, null 28 |
| `flank_pain_true:47597ae1` | `flank_pain_true` | -- | true | 17/38 | 44.7% | true 17, null 21 |
| `flank_pain_null_hedged:b06aa9b7` | `flank_pain_null_hedged` | hedged | null | 9/20 | 45.0% | false 2, true 9, null 9 |
| `flank_pain_null_hedged:c49f5999` | `flank_pain_null_hedged` | hedged | null | 9/20 | 45.0% | false 11, null 9 |
| `flank_pain_true:59cc66fa` | `flank_pain_true` | -- | true | 9/20 | 45.0% | false 1, true 9, null 10 |
| `flank_pain_null_hedged:2a3b1726` | `flank_pain_null_hedged` | hedged | null | 13/28 | 46.4% | false 1, true 14, null 13 |
| `flank_pain_true:0b172f6c` | `flank_pain_true` | -- | true | 16/33 | 48.5% | true 16, null 17 |
| `flank_pain_false:4d4ec138` | `flank_pain_false` | -- | false | 39/78 | 50.0% | false 39, null 39 |
| `flank_pain_null_hedged:d69080be` | `flank_pain_null_hedged` | hedged | null | 8/16 | 50.0% | false 8, null 8 |
| `flank_pain_true:0d9a9389` | `flank_pain_true` | -- | true | 18/35 | 51.4% | false 3, true 18, null 14 |
| `flank_pain_false:f35fd493` | `flank_pain_false` | -- | false | 14/26 | 53.8% | false 14, null 12 |
| `flank_pain_null_historical:1d821bf1` | `flank_pain_null_historical` | historical | null | 13/24 | 54.2% | false 4, true 7, null 13 |
| `flank_pain_null_hedged:1ee3ae69` | `flank_pain_null_hedged` | hedged | null | 12/22 | 54.5% | false 9, true 1, null 12 |
| `flank_pain_false:3967fa70` | `flank_pain_false` | -- | false | 16/29 | 55.2% | false 16, null 13 |
| `flank_pain_false:76bc0785` | `flank_pain_false` | -- | false | 35/61 | 57.4% | false 35, true 14, null 12 |
| `flank_pain_false:9ed5cbe0` | `flank_pain_false` | -- | false | 29/50 | 58.0% | false 29, null 21 |
| `flank_pain_false:a7c193e8` | `flank_pain_false` | -- | false | 18/31 | 58.1% | false 18, true 1, null 12 |

*116 further fragments with at least one error are in the JSON sidecar; every fragment is there regardless of score.*

## `arm_b_finetune`

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

`arm_b_finetune`: 280 errors across 22 of 243 decisive fragments. Half of them fall on **4** fragments (an even spread would be 11.0); the worst ten carry 89.6% of all errors.

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

`arm_b_finetune__shuffled`: 3960 errors across 103 of 243 decisive fragments. Half of them fall on **37** fragments (an even spread would be 51.5); the worst ten carry 17.0% of all errors.

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

### `arm_a_probe`

| fold | train n | val n | test n | margin | acc (raw) | acc (ruled) | macro-F1 | null->true |
|---|---|---|---|---|---|---|---|---|
| 0 | 10000 | 2000 | 2000 | 0.0 | 83.3% | 83.3% | 78.2% | 2.81% |
| 1 | 10000 | 2000 | 2000 | 0.05 | 86.4% | 86.7% | 83.5% | 2.00% |
| 2 | 10000 | 2000 | 2000 | 0.1 | 83.8% | 83.4% | 78.4% | 1.66% |
| 3 | 10000 | 2000 | 2000 | 0.0 | 87.4% | 87.4% | 85.1% | 2.88% |
| 4 | 10000 | 2000 | 2000 | 0.0 | 90.5% | 90.5% | 87.9% | 0.75% |

### `arm_b_finetune`

| fold | train n | val n | test n | margin | acc (raw) | acc (ruled) | macro-F1 | null->true |
|---|---|---|---|---|---|---|---|---|
| 0 | 10000 | 2000 | 2000 | 0.4 | 99.4% | 99.2% | 99.0% | 0.00% |
| 1 | 10000 | 2000 | 2000 | 0.9 | 97.6% | 97.7% | 96.8% | 2.16% |
| 2 | 10000 | 2000 | 2000 | 0.0 | 94.0% | 94.0% | 92.5% | 3.31% |
| 3 | 10000 | 2000 | 2000 | 0.85 | 96.0% | 96.3% | 95.9% | 2.06% |
| 4 | 10000 | 2000 | 2000 | 0.35 | 98.7% | 98.7% | 98.7% | 0.00% |

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

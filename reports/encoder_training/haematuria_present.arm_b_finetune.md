# Encoder training: evaluation report

*Generated 2026-08-16T10:30:29+00:00.*

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
| artefacts | `models/encoder/haematuria_present/arm_b_finetune` |
| weights | `models/encoder/haematuria_present/arm_b_finetune/weights -- ~440MB per fold, not committed` |
| model revision | `e2da8e2f811d1448a5b465c236feacd80ffbac7b` |
| revision pinned | `False` |
| tokeniser lowercases | `False` |
| tokeniser vocab size | `50265` |
| tokeniser discards casing | `False` |
| cluster tag coverage | `0 of 5 libraries carry cluster markers; 225 of 225 fragments are in libraries with none` |
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
| `arm_a_probe` | probe | 7022 | **225** | 82.8% [79.3%, 85.9%] | 81.6% [77.9%, 84.6%] | 87.5% | 87.5% +/- 2.7% |
| `arm_b_finetune` | finetune | 7022 | **225** | 91.5% [87.5%, 94.9%] | 90.7% [86.4%, 94.3%] | 94.0% | 94.0% +/- 2.4% |
| `arm_b_finetune__shuffled` | negative control | 7022 | **225** | 43.6% [36.8%, 51.0%] | 20.2% [17.9%, 22.5%] | 60.4% | 60.4% +/- 0.2% |

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
| `arm_a_probe` | -- | -- | 75.8% [66.4%, 83.6%] (eff n 45) | 97.3% [95.2%, 99.1%] (eff n 45) | -- | 96.5% [93.8%, 98.7%] (eff n 45) |
| `arm_b_finetune` | -- | -- | 84.2% [74.4%, 92.3%] (eff n 45) | 96.7% [89.9%, 100.0%] (eff n 45) | -- | 100.0% [100.0%, 100.0%] (eff n 45) |
| `arm_b_finetune__shuffled` | -- | -- | 100.0% [100.0%, 100.0%] (eff n 45) | 100.0% [100.0%, 100.0%] (eff n 45) | -- | 100.0% [100.0%, 100.0%] (eff n 45) |

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
| `arm_a_probe` | probe | 3062 | **135** | 89.5% [85.5%, 92.8%] |
| `arm_b_finetune` | finetune | 3062 | **135** | 93.3% [89.0%, 97.0%] |

### 2. The same comparison, paired

Two overlapping intervals do not settle whether one model beats another on the same
examples. McNemar does, over the examples the two disagree about -- read it alongside the
intervals above, never instead of them.

| pair | n | a only | b only | p |
|---|---|---|---|---|
| `majority_class` vs `length_only` | 3062 | 0 | 0 | 1 |
| `majority_class` vs `tfidf_logreg` | 3062 | 205 | 0 | 3.89e-62 |
| `majority_class` vs `arm_a_probe` | 3062 | 322 | 0 | 2.34e-97 |
| `majority_class` vs `arm_b_finetune` | 3062 | 231 | 0 | 5.8e-70 |
| `length_only` vs `tfidf_logreg` | 3062 | 205 | 0 | 3.89e-62 |
| `length_only` vs `arm_a_probe` | 3062 | 322 | 0 | 2.34e-97 |
| `length_only` vs `arm_b_finetune` | 3062 | 231 | 0 | 5.8e-70 |
| `tfidf_logreg` vs `arm_a_probe` | 3062 | 258 | 141 | 4.97e-09 |
| `tfidf_logreg` vs `arm_b_finetune` | 3062 | 184 | 158 | 0.176 |
| `arm_a_probe` vs `arm_b_finetune` | 3062 | 120 | 211 | 6.46e-07 |

### 3. Where the errors fall

The per-fragment table below, as one number per model. Errors spread thinly across many
fragments say the method is too weak. Errors piled onto a handful say those specific ideas
are not learnable from the data we have -- and the table names them, which is what makes
this the most decision-useful thing in the report.

* `majority_class`: 3960 errors across 90 of 225 decisive fragments. Half of them fall on **32** fragments (an even spread would be 45.0); the worst ten carry 18.2% of all errors.
* `length_only`: 3921 errors across 90 of 225 decisive fragments. Half of them fall on **32** fragments (an even spread would be 45.0); the worst ten carry 17.9% of all errors.
* `tfidf_logreg`: 1779 errors across 114 of 225 decisive fragments. Half of them fall on **21** fragments (an even spread would be 57.0); the worst ten carry 30.7% of all errors.
* `arm_a_probe`: 1205 errors across 133 of 225 decisive fragments. Half of them fall on **26** fragments (an even spread would be 66.5); the worst ten carry 27.1% of all errors.
* `arm_b_finetune`: 600 errors across 30 of 225 decisive fragments. Half of them fall on **7** fragments (an even spread would be 15.0); the worst ten carry 67.2% of all errors.

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
| `length_only__shuffled` | 60.4% [38.5%, 77.5%] | 25.1% [18.5%, 29.1%] |
| `tfidf_logreg__shuffled` | 60.4% [38.5%, 77.5%] | 25.1% [18.5%, 29.1%] |
| `arm_b_finetune__shuffled` | 60.4% [38.5%, 77.5%] | 25.1% [18.5%, 29.1%] |

## Paired comparisons (McNemar, raw argmax)

Exact two-sided McNemar over the examples the two models disagree about. Pairing unit is the
example, not the cluster -- see the limitations.

| pair | slice | n | a only | b only | p |
|---|---|---|---|---|---|
| `majority_class` vs `length_only` | overall | 10000 | 3 | 39 | 5.63e-09 |
| `majority_class` vs `length_only` | null_ambiguous | 3062 | 0 | 0 | 1 |
| `majority_class` vs `tfidf_logreg` | overall | 10000 | 214 | 2385 | 0 |
| `majority_class` vs `tfidf_logreg` | null_ambiguous | 3062 | 205 | 0 | 3.89e-62 |
| `majority_class` vs `arm_a_probe` | overall | 10000 | 366 | 3077 | 0 |
| `majority_class` vs `arm_a_probe` | null_ambiguous | 3062 | 322 | 0 | 2.34e-97 |
| `majority_class` vs `arm_b_finetune` | overall | 10000 | 231 | 3572 | 0 |
| `majority_class` vs `arm_b_finetune` | null_ambiguous | 3062 | 231 | 0 | 5.8e-70 |
| `length_only` vs `tfidf_logreg` | overall | 10000 | 223 | 2358 | 0 |
| `length_only` vs `tfidf_logreg` | null_ambiguous | 3062 | 205 | 0 | 3.89e-62 |
| `length_only` vs `arm_a_probe` | overall | 10000 | 369 | 3044 | 0 |
| `length_only` vs `arm_a_probe` | null_ambiguous | 3062 | 322 | 0 | 2.34e-97 |
| `length_only` vs `arm_b_finetune` | overall | 10000 | 235 | 3540 | 0 |
| `length_only` vs `arm_b_finetune` | null_ambiguous | 3062 | 231 | 0 | 5.8e-70 |
| `tfidf_logreg` vs `arm_a_probe` | overall | 10000 | 573 | 1113 | 5e-40 |
| `tfidf_logreg` vs `arm_a_probe` | null_ambiguous | 3062 | 258 | 141 | 4.97e-09 |
| `tfidf_logreg` vs `arm_b_finetune` | overall | 10000 | 249 | 1419 | 1.03e-198 |
| `tfidf_logreg` vs `arm_b_finetune` | null_ambiguous | 3062 | 184 | 158 | 0.176 |
| `arm_a_probe` vs `arm_b_finetune` | overall | 10000 | 251 | 881 | 1.77e-82 |
| `arm_a_probe` vs `arm_b_finetune` | null_ambiguous | 3062 | 120 | 211 | 6.46e-07 |

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
| `haematuria_false` | 2479 | 0.0% | 1.6% | 69.5% | 81.7% | 92.1% | 92.1pp |
| `haematuria_true` | 1481 | 0.0% | 0.0% | 44.6% | 71.0% | 86.6% | 86.6pp |
| `haematuria_null_hedged` | 1079 | 100.0% | 100.0% | 89.7% | 75.8% | 84.2% | 24.2pp |
| `haematuria_null_historical` | 1016 | 100.0% | 100.0% | 94.6% | 97.3% | 96.7% | 5.4pp |
| `haematuria_null_thirdparty` | 967 | 100.0% | 100.0% | 96.3% | 96.5% | 100.0% | 3.7pp |
| `(none)` | 2978 | 100.0% | 99.9% | 99.7% | 98.5% | 100.0% | 1.5pp |

### By fragment, errors

Ordered by the worst model's error count, so the fragments the comparison is about sort
to the top whichever encoder wins. Counts, not rates: these are the sentences a month of
library work would be spent on. The JSON holds every fragment.

| fragment | library | truth | `majority_class` | `length_only` | `tfidf_logreg` | `arm_a_probe` | `arm_b_finetune` | spread |
|---|---|---|---|---|---|---|---|---|
| `haematuria_false:0e98be72` | `haematuria_false` | false | 81 | 81 | 79 | 14 | 0 | 81 |
| `haematuria_false:56b8af62` | `haematuria_false` | false | 78 | 78 | 43 | 7 | 0 | 78 |
| `haematuria_false:94f9de34` | `haematuria_false` | false | 76 | 62 | 20 | 4 | 0 | 76 |
| `haematuria_false:acc7804e` | `haematuria_false` | false | 75 | 75 | 7 | 2 | 0 | 75 |
| `haematuria_false:b3fd19df` | `haematuria_false` | false | 74 | 74 | 4 | 8 | 0 | 74 |
| `haematuria_true:c0ff5eed` | `haematuria_true` | true | 71 | 71 | 67 | 13 | 0 | 71 |
| `haematuria_false:e23c4950` | `haematuria_false` | false | 69 | 58 | 24 | 7 | 0 | 69 |
| `haematuria_false:5e090855` | `haematuria_false` | false | 66 | 66 | 0 | 0 | 0 | 66 |
| `haematuria_false:64933508` | `haematuria_false` | false | 65 | 65 | 21 | 5 | 0 | 65 |
| `haematuria_false:b692c4ce` | `haematuria_false` | false | 64 | 64 | 8 | 30 | 0 | 64 |
| `haematuria_false:873d5c5b` | `haematuria_false` | false | 63 | 63 | 31 | 0 | 0 | 63 |
| `haematuria_false:b0d93eca` | `haematuria_false` | false | 63 | 63 | 0 | 0 | 0 | 63 |
| `haematuria_true:972bb99b` | `haematuria_true` | true | 63 | 63 | 8 | 7 | 0 | 63 |
| `haematuria_true:62126789` | `haematuria_true` | true | 62 | 62 | 2 | 12 | 0 | 62 |
| `haematuria_false:94644abb` | `haematuria_false` | false | 61 | 61 | 0 | 2 | 0 | 61 |
| `haematuria_false:fc6a0704` | `haematuria_false` | false | 61 | 61 | 3 | 10 | 0 | 61 |
| `haematuria_true:6fadb8bc` | `haematuria_true` | true | 60 | 60 | 52 | 42 | 60 | 18 |
| `haematuria_true:7ea098d1` | `haematuria_true` | true | 60 | 60 | 31 | 9 | 0 | 60 |
| `haematuria_true:f2e49699` | `haematuria_true` | true | 60 | 60 | 32 | 8 | 0 | 60 |
| `haematuria_false:a84358ef` | `haematuria_false` | false | 59 | 59 | 0 | 3 | 0 | 59 |
| `haematuria_true:150663fa` | `haematuria_true` | true | 59 | 59 | 14 | 0 | 0 | 59 |
| `haematuria_false:5543da20` | `haematuria_false` | false | 58 | 58 | 3 | 16 | 0 | 58 |
| `haematuria_false:cbd9cec5` | `haematuria_false` | false | 58 | 58 | 58 | 11 | 0 | 58 |
| `haematuria_false:d163df19` | `haematuria_false` | false | 58 | 58 | 56 | 52 | 58 | 6 |
| `haematuria_false:0722271d` | `haematuria_false` | false | 57 | 57 | 4 | 16 | 0 | 57 |
| `haematuria_false:58488f8a` | `haematuria_false` | false | 57 | 57 | 0 | 1 | 0 | 57 |
| `haematuria_false:a9960bdc` | `haematuria_false` | false | 57 | 57 | 0 | 0 | 0 | 57 |
| `haematuria_true:d93fd4ce` | `haematuria_true` | true | 57 | 57 | 4 | 14 | 0 | 57 |
| `haematuria_false:0a0b1113` | `haematuria_false` | false | 56 | 56 | 53 | 27 | 0 | 56 |
| `haematuria_false:7240a8fb` | `haematuria_false` | false | 56 | 53 | 17 | 16 | 0 | 56 |
| `haematuria_false:c0157f0d` | `haematuria_false` | false | 56 | 56 | 1 | 10 | 0 | 56 |
| `haematuria_false:cb3cb6e6` | `haematuria_false` | false | 56 | 51 | 44 | 46 | 55 | 12 |
| `haematuria_false:d9d4737d` | `haematuria_false` | false | 56 | 55 | 27 | 20 | 0 | 56 |
| `haematuria_false:4fda0b2c` | `haematuria_false` | false | 55 | 50 | 14 | 21 | 0 | 55 |
| `haematuria_false:899e3ed9` | `haematuria_false` | false | 55 | 55 | 26 | 4 | 2 | 53 |
| `haematuria_false:66629fb1` | `haematuria_false` | false | 54 | 54 | 40 | 16 | 0 | 54 |
| `haematuria_false:9720fe1e` | `haematuria_false` | false | 53 | 53 | 0 | 7 | 0 | 53 |
| `haematuria_false:61bf080a` | `haematuria_false` | false | 52 | 52 | 1 | 5 | 0 | 52 |
| `haematuria_true:245ed73d` | `haematuria_true` | true | 51 | 51 | 17 | 24 | 0 | 51 |
| `haematuria_false:21d7fe6b` | `haematuria_false` | false | 49 | 49 | 21 | 9 | 0 | 49 |

*122 further fragments erred on at least one model; the JSON holds them all.*

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

## `arm_a_probe`

Frozen `roberta-base`, mean-pooled, with a `Linear(768, 3)` probe over the cached embeddings (2,307 parameters). The encoder learns nothing; only the probe is fitted. Expected to handle clear positives, clear negatives and `null_structural`, and to do badly on the four hard `null` sub-classes, which turn on compositional scope that a single pooled vector blurs. That is the predicted result rather than a fault, and it is what makes Arm B necessary: a weak probe cannot distinguish "the libraries are the bottleneck" from "the method is too weak".

Decision-rule margins selected per fold (on each fold's own validation split): 0.0.
Every fold selected margin 0, so the ruled and raw views below are the same decisions. That is a finding rather than a bug: no margin improved macro-F1 without worsening the `null -> true` rate.

*Confusion matrix, raw argmax*

|  | pred false | pred true | pred null | total |
|---|---|---|---|---|
| **truth false** | 2025 | 78 | 376 | 2479 |
| **truth true** | 86 | 1052 | 343 | 1481 |
| **truth null** | 134 | 232 | 5674 | 6040 |
| **total** | 2245 | 1362 | 6393 | 10000 |

`null -> true`: 232 of 6040 truly-null examples (3.84%).

*Confusion matrix, after the decision rule*

|  | pred false | pred true | pred null | total |
|---|---|---|---|---|
| **truth false** | 2025 | 78 | 376 | 2479 |
| **truth true** | 86 | 1052 | 343 | 1481 |
| **truth null** | 134 | 232 | 5674 | 6040 |
| **total** | 2245 | 1362 | 6393 | 10000 |

`null -> true`: 232 of 6040 truly-null examples (3.84%).

### Per class, after the decision rule

| class | support | predicted | precision | recall | F1 |
|---|---|---|---|---|---|
| `false` | 2479 | 2245 | 90.2% | 81.7% | 85.7% |
| `true` | 1481 | 1362 | 77.2% | 71.0% | 74.0% |
| `null` | 6040 | 6393 | 88.8% | 93.9% | 91.3% |

### By label mode

| label mode | n | eff n | accuracy [95% CI] |
|---|---|---|---|
| false | 2479 | **45** | 81.7% [75.2%, 87.1%] |
| null_ambiguous | 3062 | **135** | 89.5% [85.5%, 92.8%] |
| null_structural | 2978 | **1** | 98.5% [98.5%, 98.5%] |
| true | 1481 | **45** | 71.0% [63.1%, 77.6%] |

### By null sub-class

| sub-class | n | eff n | null recall [95% CI] |
|---|---|---|---|
| hedged | 1079 | **45** | 75.8% [66.4%, 83.6%] |
| historical | 1016 | **45** | 97.3% [95.2%, 99.1%] |
| third_party | 967 | **45** | 96.5% [93.8%, 98.7%] |

### By fragment library

| library | n | eff n | accuracy [95% CI] |
|---|---|---|---|
| haematuria_false | 2479 | **45** | 81.7% [75.2%, 87.1%] |
| haematuria_null_hedged | 1079 | **45** | 75.8% [66.4%, 83.6%] |
| haematuria_null_historical | 1016 | **45** | 97.3% [95.2%, 99.1%] |
| haematuria_null_thirdparty | 967 | **45** | 96.5% [93.8%, 98.7%] |
| haematuria_true | 1481 | **45** | 71.0% [63.1%, 77.6%] |
| (none) | 2978 | **1** | 98.5% [98.5%, 98.5%] |

### Per-fragment errors (worst first)

Whether errors are spread thinly across many fragments or piled onto a few is the difference
between "the method is too weak" (model work) and "these specific ideas are not learnable from
the data we have" (library work, and these are the fragments to write more of). No intervals:
a fragment is one cluster, so an interval over its own examples measures nothing.

133 of 225 decisive fragments were got wrong at least once.

`arm_a_probe`: 1205 errors across 133 of 225 decisive fragments. Half of them fall on **26** fragments (an even spread would be 66.5); the worst ten carry 27.1% of all errors.

| fragment | library | sub-class | truth | correct | accuracy | predicted as |
|---|---|---|---|---|---|---|
| `haematuria_null_hedged:ad81f888` | `haematuria_null_hedged` | hedged | null | 0/28 | 0.0% | true 28 |
| `haematuria_true:a621d471` | `haematuria_true` | -- | true | 1/22 | 4.5% | false 2, true 1, null 19 |
| `haematuria_null_hedged:f5ac0bee` | `haematuria_null_hedged` | hedged | null | 1/14 | 7.1% | false 5, true 8, null 1 |
| `haematuria_true:9207612b` | `haematuria_true` | -- | true | 1/10 | 10.0% | true 1, null 9 |
| `haematuria_false:d163df19` | `haematuria_false` | -- | false | 6/58 | 10.3% | false 6, null 52 |
| `haematuria_true:fbab8b19` | `haematuria_true` | -- | true | 2/18 | 11.1% | false 1, true 2, null 15 |
| `haematuria_null_hedged:4384f747` | `haematuria_null_hedged` | hedged | null | 4/30 | 13.3% | false 1, true 25, null 4 |
| `haematuria_null_hedged:82a8ae4f` | `haematuria_null_hedged` | hedged | null | 2/14 | 14.3% | false 1, true 11, null 2 |
| `haematuria_null_hedged:f1a0ec1e` | `haematuria_null_hedged` | hedged | null | 2/12 | 16.7% | false 4, true 6, null 2 |
| `haematuria_false:cb3cb6e6` | `haematuria_false` | -- | false | 10/56 | 17.9% | false 10, true 5, null 41 |
| `haematuria_null_hedged:dc7c4c42` | `haematuria_null_hedged` | hedged | null | 4/21 | 19.0% | false 7, true 10, null 4 |
| `haematuria_null_hedged:0a1e23ec` | `haematuria_null_hedged` | hedged | null | 5/24 | 20.8% | true 19, null 5 |
| `haematuria_true:58dc10f0` | `haematuria_true` | -- | true | 6/24 | 25.0% | false 3, true 6, null 15 |
| `haematuria_true:e93a6a13` | `haematuria_true` | -- | true | 11/41 | 26.8% | false 6, true 11, null 24 |
| `haematuria_true:e34024ba` | `haematuria_true` | -- | true | 6/22 | 27.3% | false 5, true 6, null 11 |
| `haematuria_true:6fadb8bc` | `haematuria_true` | -- | true | 18/60 | 30.0% | false 1, true 18, null 41 |
| `haematuria_true:b8b1c720` | `haematuria_true` | -- | true | 14/34 | 41.2% | false 4, true 14, null 16 |
| `haematuria_null_hedged:80ec8e70` | `haematuria_null_hedged` | hedged | null | 10/23 | 43.5% | false 1, true 12, null 10 |
| `haematuria_null_hedged:58ace8f5` | `haematuria_null_hedged` | hedged | null | 11/25 | 44.0% | false 6, true 8, null 11 |
| `haematuria_false:eaac464c` | `haematuria_false` | -- | false | 18/39 | 46.2% | false 18, true 2, null 19 |
| `haematuria_null_historical:2fe3bb50` | `haematuria_null_historical` | historical | null | 7/15 | 46.7% | true 8, null 7 |
| `haematuria_null_hedged:d64cf17c` | `haematuria_null_hedged` | hedged | null | 11/23 | 47.8% | false 6, true 6, null 11 |
| `haematuria_null_hedged:578c2609` | `haematuria_null_hedged` | hedged | null | 15/31 | 48.4% | false 15, true 1, null 15 |
| `haematuria_true:f9f24e70` | `haematuria_true` | -- | true | 18/36 | 50.0% | false 2, true 18, null 16 |
| `haematuria_true:78fbdffb` | `haematuria_true` | -- | true | 14/28 | 50.0% | false 1, true 14, null 13 |
| `haematuria_false:0a0b1113` | `haematuria_false` | -- | false | 29/56 | 51.8% | false 29, null 27 |
| `haematuria_true:ec01803e` | `haematuria_true` | -- | true | 13/25 | 52.0% | true 13, null 12 |
| `haematuria_true:245ed73d` | `haematuria_true` | -- | true | 27/51 | 52.9% | false 23, true 27, null 1 |
| `haematuria_false:b692c4ce` | `haematuria_false` | -- | false | 34/64 | 53.1% | false 34, true 15, null 15 |
| `haematuria_false:b471d351` | `haematuria_false` | -- | false | 24/40 | 60.0% | false 24, true 10, null 6 |
| `haematuria_true:9bb5b3f3` | `haematuria_true` | -- | true | 12/20 | 60.0% | false 2, true 12, null 6 |
| `haematuria_true:9e0324ed` | `haematuria_true` | -- | true | 16/26 | 61.5% | false 1, true 16, null 9 |
| `haematuria_false:4fda0b2c` | `haematuria_false` | -- | false | 34/55 | 61.8% | false 34, true 7, null 14 |
| `haematuria_null_hedged:64409bb8` | `haematuria_null_hedged` | hedged | null | 18/29 | 62.1% | false 8, true 3, null 18 |
| `haematuria_true:08f72e8e` | `haematuria_true` | -- | true | 10/16 | 62.5% | false 1, true 10, null 5 |
| `haematuria_true:07a7c858` | `haematuria_true` | -- | true | 17/27 | 63.0% | true 17, null 10 |
| `haematuria_false:d9d4737d` | `haematuria_false` | -- | false | 36/56 | 64.3% | false 36, true 1, null 19 |
| `haematuria_true:5cf89fbc` | `haematuria_true` | -- | true | 19/29 | 65.5% | false 3, true 19, null 7 |
| `haematuria_false:9c317cf3` | `haematuria_false` | -- | false | 30/45 | 66.7% | false 30, true 1, null 14 |
| `haematuria_true:44d3145f` | `haematuria_true` | -- | true | 12/18 | 66.7% | false 6, true 12 |

*93 further fragments with at least one error are in the JSON sidecar; every fragment is there regardless of score.*

## `arm_b_finetune`

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

`arm_b_finetune`: 600 errors across 30 of 225 decisive fragments. Half of them fall on **7** fragments (an even spread would be 15.0); the worst ten carry 67.2% of all errors.

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

`arm_b_finetune__shuffled`: 3960 errors across 90 of 225 decisive fragments. Half of them fall on **32** fragments (an even spread would be 45.0); the worst ten carry 18.2% of all errors.

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

### `arm_a_probe`

| fold | train n | val n | test n | margin | acc (raw) | acc (ruled) | macro-F1 | null->true |
|---|---|---|---|---|---|---|---|---|
| 0 | 10000 | 2000 | 2000 | 0.0 | 84.2% | 84.2% | 79.7% | 4.55% |
| 1 | 10000 | 2000 | 2000 | 0.0 | 87.2% | 87.2% | 83.6% | 5.57% |
| 2 | 10000 | 2000 | 2000 | 0.0 | 90.1% | 90.1% | 87.9% | 5.30% |
| 3 | 10000 | 2000 | 2000 | 0.0 | 85.8% | 85.8% | 80.1% | 1.98% |
| 4 | 10000 | 2000 | 2000 | 0.0 | 90.3% | 90.3% | 86.2% | 1.82% |

### `arm_b_finetune`

| fold | train n | val n | test n | margin | acc (raw) | acc (ruled) | macro-F1 | null->true |
|---|---|---|---|---|---|---|---|---|
| 0 | 10000 | 2000 | 2000 | 0.85 | 92.0% | 91.8% | 89.0% | 1.24% |
| 1 | 10000 | 2000 | 2000 | 0.9 | 94.1% | 94.2% | 93.5% | 3.08% |
| 2 | 10000 | 2000 | 2000 | 0.8 | 90.3% | 91.5% | 88.8% | 7.37% |
| 3 | 10000 | 2000 | 2000 | 0.0 | 95.7% | 95.7% | 93.7% | 0.00% |
| 4 | 10000 | 2000 | 2000 | 0.9 | 97.0% | 97.0% | 95.3% | 0.00% |

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

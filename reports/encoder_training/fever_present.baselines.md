# Encoder training: evaluation report

*Generated 2026-08-08T12:30:42+00:00.*

|  |  |
|---|---|
| signal | `fever_present` |
| folds | `5` |
| generator version | `2` |
| generator base seed | `42` |
| generator seed rule | `base + 100 * fold + {train: 0, val: 1, test: 2}` |
| split salt | `32` |
| dataset dir | `data/synthetic/generated/folds` |
| ruleset | `data/uti1.json` |
| ruleset hash | `325b33068307bc70ca085b27117a90c2ad9e71fac24a80f77c8107d08049bb9f` |
| examples per fold | `train 10000, val 2000, test 2000` |
| shuffle seed | `7` |
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
| `majority_class` | baseline | 7022 | **306** | 43.6% [37.5%, 49.7%] | 20.2% [18.2%, 22.1%] | 60.4% | 60.4% +/- 0.2% |
| `length_only` | baseline | 7022 | **306** | 44.7% [38.9%, 50.6%] | 23.3% [20.9%, 25.6%] | 61.1% | 61.1% +/- 0.6% |
| `tfidf_logreg` | baseline | 7022 | **306** | 70.8% [66.0%, 75.9%] | 67.8% [62.4%, 72.9%] | 79.2% | 79.2% +/- 3.6% |
| `length_only__shuffled` | negative control | 7022 | **306** | 43.6% [37.5%, 49.7%] | 20.2% [18.2%, 22.1%] | 60.4% | 60.4% +/- 0.2% |
| `tfidf_logreg__shuffled` | negative control | 7022 | **306** | 43.6% [37.5%, 49.7%] | 20.2% [18.2%, 22.1%] | 60.4% | 60.4% +/- 0.3% |

### Null sub-class recall, pooled

The table the whole exercise exists for: how often each hard `null` sub-class is correctly
left as `null`. `eff n` here is the sub-class's entire library, which a single split cannot reach.

**Never read this table on its own.** Every example in these slices is truly `null`, so a model
that always answers `null` scores 100% across the row -- as `majority_class` below does. High
null recall is only a finding when the `true` and `false` recalls in the per-class tables are
high too.

| model | hedged | historical | metaphor | third_party |
|---|---|---|---|---|
| `majority_class` | 100.0% [100.0%, 100.0%] (eff n 32) | 100.0% [100.0%, 100.0%] (eff n 36) | 100.0% [100.0%, 100.0%] (eff n 47) | 100.0% [100.0%, 100.0%] (eff n 35) |
| `length_only` | 99.4% [98.8%, 99.9%] (eff n 32) | 99.5% [98.6%, 100.0%] (eff n 36) | 97.7% [94.3%, 99.6%] (eff n 47) | 98.8% [97.3%, 99.8%] (eff n 35) |
| `tfidf_logreg` | 89.7% [79.6%, 96.3%] (eff n 32) | 96.0% [92.3%, 98.6%] (eff n 36) | 94.0% [90.3%, 97.0%] (eff n 47) | 94.6% [89.7%, 98.4%] (eff n 35) |
| `length_only__shuffled` | 100.0% [100.0%, 100.0%] (eff n 32) | 100.0% [100.0%, 100.0%] (eff n 36) | 100.0% [100.0%, 100.0%] (eff n 47) | 100.0% [100.0%, 100.0%] (eff n 35) |
| `tfidf_logreg__shuffled` | 100.0% [100.0%, 100.0%] (eff n 32) | 100.0% [100.0%, 100.0%] (eff n 36) | 100.0% [100.0%, 100.0%] (eff n 47) | 100.0% [100.0%, 100.0%] (eff n 35) |

## What we expected before looking

* Majority-class should land near 60%, which is the generator's `null` share and not a property of the data worth anything.
* The length-only model is the direct measurable test of the length leak `arch_training.md` section 9 argues for but has never measured. Materially above majority means text length is a usable proxy for the label, which is a library problem rather than a model one.
* TF-IDF should do well on clear positives, clear negatives and `null_structural`, and badly on the ambiguous sub-classes. Its overall accuracy is therefore close to uninformative. **The number that matters is the `null_ambiguous` slice**, tested with McNemar against the transformer once that exists.
* Both negative controls must fail. Shuffled train labels must score at chance on the unpermuted test split, and no fragment or cluster may appear on both sides of a split.

## Negative controls and checks

* **fragment disjointness** -- checked, not assumed. Loading each fold asserts that no fragment and no cluster appears in two of its splits, so no hand-written sentence is on both sides of a train/test boundary and no `[c01]` sibling pair is split across one. Asserted at load time on every run, and a violation is a hard error rather than a warning.
* **test partition** -- checked. Across the 5 folds, 799 distinct clusters are held out, each in exactly one fold, so pooling the folds counts every idea once. That figure spans every library in the manifest -- filler and other signals' libraries included -- not just this signal's; the per-slice `eff n` columns are the numbers that bound anything.
* **fold configuration** -- checked. The three splits of each fold agree on generator version, fold count, fold index and salt, and all folds agree on the salt.

Shuffled-label controls, evaluated on the **unpermuted** test split. A large model will
memorise permuted training labels and drive train loss to zero; that is correct behaviour
and says nothing. Only the test score is the control.

| control | accuracy [95% CI] | macro-F1 [95% CI] |
|---|---|---|
| `length_only__shuffled` | 60.4% [39.4%, 77.1%] | 25.1% [18.8%, 29.0%] |
| `tfidf_logreg__shuffled` | 60.4% [39.4%, 77.0%] | 25.1% [18.8%, 29.0%] |

## Paired comparisons (McNemar, raw argmax)

Exact two-sided McNemar over the examples the two models disagree about. Pairing unit is the
example, not the cluster -- see the limitations.

| pair | slice | n | a only | b only | p |
|---|---|---|---|---|---|
| `majority_class` vs `length_only` | overall | 10000 | 47 | 114 | 1.32e-07 |
| `majority_class` vs `length_only` | null_ambiguous | 3062 | 37 | 0 | 1.46e-11 |
| `majority_class` vs `tfidf_logreg` | overall | 10000 | 233 | 2115 | 0 |
| `majority_class` vs `tfidf_logreg` | null_ambiguous | 3062 | 198 | 0 | 4.98e-60 |
| `length_only` vs `tfidf_logreg` | overall | 10000 | 309 | 2124 | 0 |
| `length_only` vs `tfidf_logreg` | null_ambiguous | 3062 | 197 | 36 | 4.6e-28 |

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
| false | 2479 | **60** | 0.0% [0.0%, 0.0%] |
| null_ambiguous | 3062 | **150** | 100.0% [100.0%, 100.0%] |
| null_structural | 2978 | **1** | 100.0% [100.0%, 100.0%] |
| true | 1481 | **96** | 0.0% [0.0%, 0.0%] |

### By null sub-class

| sub-class | n | eff n | null recall [95% CI] |
|---|---|---|---|
| hedged | 721 | **32** | 100.0% [100.0%, 100.0%] |
| historical | 751 | **36** | 100.0% [100.0%, 100.0%] |
| metaphor | 865 | **47** | 100.0% [100.0%, 100.0%] |
| third_party | 725 | **35** | 100.0% [100.0%, 100.0%] |

### By fragment library

| library | n | eff n | accuracy [95% CI] |
|---|---|---|---|
| fever_false | 2479 | **60** | 0.0% [0.0%, 0.0%] |
| fever_null_hedged | 721 | **32** | 100.0% [100.0%, 100.0%] |
| fever_null_historical | 751 | **36** | 100.0% [100.0%, 100.0%] |
| fever_null_metaphor | 865 | **47** | 100.0% [100.0%, 100.0%] |
| fever_null_thirdparty | 725 | **35** | 100.0% [100.0%, 100.0%] |
| fever_true | 1481 | **96** | 0.0% [0.0%, 0.0%] |
| (none) | 2978 | **1** | 100.0% [100.0%, 100.0%] |

### Per-fragment errors (worst first)

Whether errors are spread thinly across many fragments or piled onto a few is the difference
between "the method is too weak" (model work) and "these specific ideas are not learnable from
the data we have" (library work, and these are the fragments to write more of). No intervals:
a fragment is one cluster, so an interval over its own examples measures nothing.

156 of 344 decisive fragments were got wrong at least once.

| fragment | library | sub-class | truth | correct | accuracy | predicted as |
|---|---|---|---|---|---|---|
| `fever_false:357d0419` | `fever_false` | -- | false | 0/59 | 0.0% | null 59 |
| `fever_false:98e77994` | `fever_false` | -- | false | 0/59 | 0.0% | null 59 |
| `fever_false:5f8bdfcd` | `fever_false` | -- | false | 0/55 | 0.0% | null 55 |
| `fever_false:56a45ff1` | `fever_false` | -- | false | 0/54 | 0.0% | null 54 |
| `fever_false:e8c514ff` | `fever_false` | -- | false | 0/54 | 0.0% | null 54 |
| `fever_false:00302cae` | `fever_false` | -- | false | 0/53 | 0.0% | null 53 |
| `fever_false:a5b671a1` | `fever_false` | -- | false | 0/53 | 0.0% | null 53 |
| `fever_false:bf61fab6` | `fever_false` | -- | false | 0/53 | 0.0% | null 53 |
| `fever_false:033927e6` | `fever_false` | -- | false | 0/52 | 0.0% | null 52 |
| `fever_false:55bf1913` | `fever_false` | -- | false | 0/51 | 0.0% | null 51 |
| `fever_false:2e971b63` | `fever_false` | -- | false | 0/50 | 0.0% | null 50 |
| `fever_false:5eb45ee7` | `fever_false` | -- | false | 0/50 | 0.0% | null 50 |
| `fever_false:295f42b5` | `fever_false` | -- | false | 0/49 | 0.0% | null 49 |
| `fever_false:8599e318` | `fever_false` | -- | false | 0/49 | 0.0% | null 49 |
| `fever_false:d15cd85c` | `fever_false` | -- | false | 0/49 | 0.0% | null 49 |
| `fever_false:17f6c637` | `fever_false` | -- | false | 0/48 | 0.0% | null 48 |
| `fever_false:a0bfd501` | `fever_false` | -- | false | 0/47 | 0.0% | null 47 |
| `fever_false:b74a83cf` | `fever_false` | -- | false | 0/47 | 0.0% | null 47 |
| `fever_false:de0596c4` | `fever_false` | -- | false | 0/47 | 0.0% | null 47 |
| `fever_false:f6985a04` | `fever_false` | -- | false | 0/47 | 0.0% | null 47 |
| `fever_false:8d02bd9e` | `fever_false` | -- | false | 0/46 | 0.0% | null 46 |
| `fever_false:8f64f673` | `fever_false` | -- | false | 0/46 | 0.0% | null 46 |
| `fever_false:90f7b87f` | `fever_false` | -- | false | 0/46 | 0.0% | null 46 |
| `fever_false:acf258b4` | `fever_false` | -- | false | 0/46 | 0.0% | null 46 |
| `fever_false:b96ed279` | `fever_false` | -- | false | 0/46 | 0.0% | null 46 |
| `fever_false:147d5cf0` | `fever_false` | -- | false | 0/45 | 0.0% | null 45 |
| `fever_false:d0ca84a7` | `fever_false` | -- | false | 0/45 | 0.0% | null 45 |
| `fever_false:f1e3b80c` | `fever_false` | -- | false | 0/45 | 0.0% | null 45 |
| `fever_false:0c3535b0` | `fever_false` | -- | false | 0/44 | 0.0% | null 44 |
| `fever_false:1bc39bc3` | `fever_false` | -- | false | 0/44 | 0.0% | null 44 |
| `fever_false:463f8189` | `fever_false` | -- | false | 0/44 | 0.0% | null 44 |
| `fever_false:cba743d0` | `fever_false` | -- | false | 0/44 | 0.0% | null 44 |
| `fever_false:09f93f50` | `fever_false` | -- | false | 0/43 | 0.0% | null 43 |
| `fever_false:90623989` | `fever_false` | -- | false | 0/43 | 0.0% | null 43 |
| `fever_false:0429068c` | `fever_false` | -- | false | 0/39 | 0.0% | null 39 |
| `fever_false:93390aea` | `fever_false` | -- | false | 0/39 | 0.0% | null 39 |
| `fever_false:c747066d` | `fever_false` | -- | false | 0/38 | 0.0% | null 38 |
| `fever_false:e0897296` | `fever_false` | -- | false | 0/38 | 0.0% | null 38 |
| `fever_false:e270abe4` | `fever_false` | -- | false | 0/38 | 0.0% | null 38 |
| `fever_false:f586e96d` | `fever_false` | -- | false | 0/38 | 0.0% | null 38 |

*116 further fragments with at least one error are in the JSON sidecar; every fragment is there regardless of score.*

## `length_only`

Logistic regression on token count alone. The direct measurable test of the length leak: anything materially above majority means text length is a usable proxy for the label, which is a fragment-library problem rather than a model one.

Decision-rule margins selected per fold (on each fold's own validation split): 0.0.
Every fold selected margin 0, so the ruled and raw views below are the same decisions. That is a finding rather than a bug: no margin improved macro-F1 without worsening the `null -> true` rate.

*Confusion matrix, raw argmax*

|  | pred false | pred true | pred null | total |
|---|---|---|---|---|
| **truth false** | 114 | 0 | 2365 | 2479 |
| **truth true** | 74 | 0 | 1407 | 1481 |
| **truth null** | 47 | 0 | 5993 | 6040 |
| **total** | 235 | 0 | 9765 | 10000 |

`null -> true`: 0 of 6040 truly-null examples (0.00%).

*Confusion matrix, after the decision rule*

|  | pred false | pred true | pred null | total |
|---|---|---|---|---|
| **truth false** | 114 | 0 | 2365 | 2479 |
| **truth true** | 74 | 0 | 1407 | 1481 |
| **truth null** | 47 | 0 | 5993 | 6040 |
| **total** | 235 | 0 | 9765 | 10000 |

`null -> true`: 0 of 6040 truly-null examples (0.00%).

### Per class, after the decision rule

| class | support | predicted | precision | recall | F1 |
|---|---|---|---|---|---|
| `false` | 2479 | 235 | 48.5% | 4.6% | 8.4% |
| `true` | 1481 | 0 | -- | 0.0% | 0.0% |
| `null` | 6040 | 9765 | 61.4% | 99.2% | 75.8% |

### By label mode

| label mode | n | eff n | accuracy [95% CI] |
|---|---|---|---|
| false | 2479 | **60** | 4.6% [2.8%, 6.7%] |
| null_ambiguous | 3062 | **150** | 98.8% [97.8%, 99.5%] |
| null_structural | 2978 | **1** | 99.7% [99.7%, 99.7%] |
| true | 1481 | **96** | 0.0% [0.0%, 0.0%] |

### By null sub-class

| sub-class | n | eff n | null recall [95% CI] |
|---|---|---|---|
| hedged | 721 | **32** | 99.4% [98.8%, 99.9%] |
| historical | 751 | **36** | 99.5% [98.6%, 100.0%] |
| metaphor | 865 | **47** | 97.7% [94.3%, 99.6%] |
| third_party | 725 | **35** | 98.8% [97.3%, 99.8%] |

### By fragment library

| library | n | eff n | accuracy [95% CI] |
|---|---|---|---|
| fever_false | 2479 | **60** | 4.6% [2.8%, 6.7%] |
| fever_null_hedged | 721 | **32** | 99.4% [98.8%, 99.9%] |
| fever_null_historical | 751 | **36** | 99.5% [98.6%, 100.0%] |
| fever_null_metaphor | 865 | **47** | 97.7% [94.3%, 99.6%] |
| fever_null_thirdparty | 725 | **35** | 98.8% [97.3%, 99.8%] |
| fever_true | 1481 | **96** | 0.0% [0.0%, 0.0%] |
| (none) | 2978 | **1** | 99.7% [99.7%, 99.7%] |

### Per-fragment errors (worst first)

Whether errors are spread thinly across many fragments or piled onto a few is the difference
between "the method is too weak" (model work) and "these specific ideas are not learnable from
the data we have" (library work, and these are the fragments to write more of). No intervals:
a fragment is one cluster, so an interval over its own examples measures nothing.

175 of 344 decisive fragments were got wrong at least once.

| fragment | library | sub-class | truth | correct | accuracy | predicted as |
|---|---|---|---|---|---|---|
| `fever_false:357d0419` | `fever_false` | -- | false | 0/59 | 0.0% | null 59 |
| `fever_false:5f8bdfcd` | `fever_false` | -- | false | 0/55 | 0.0% | null 55 |
| `fever_false:56a45ff1` | `fever_false` | -- | false | 0/54 | 0.0% | null 54 |
| `fever_false:e8c514ff` | `fever_false` | -- | false | 0/54 | 0.0% | null 54 |
| `fever_false:00302cae` | `fever_false` | -- | false | 0/53 | 0.0% | null 53 |
| `fever_false:a5b671a1` | `fever_false` | -- | false | 0/53 | 0.0% | null 53 |
| `fever_false:55bf1913` | `fever_false` | -- | false | 0/51 | 0.0% | null 51 |
| `fever_false:2e971b63` | `fever_false` | -- | false | 0/50 | 0.0% | null 50 |
| `fever_false:5eb45ee7` | `fever_false` | -- | false | 0/50 | 0.0% | null 50 |
| `fever_false:295f42b5` | `fever_false` | -- | false | 0/49 | 0.0% | null 49 |
| `fever_false:8599e318` | `fever_false` | -- | false | 0/49 | 0.0% | null 49 |
| `fever_false:17f6c637` | `fever_false` | -- | false | 0/48 | 0.0% | null 48 |
| `fever_false:a0bfd501` | `fever_false` | -- | false | 0/47 | 0.0% | null 47 |
| `fever_false:b74a83cf` | `fever_false` | -- | false | 0/47 | 0.0% | null 47 |
| `fever_false:de0596c4` | `fever_false` | -- | false | 0/47 | 0.0% | null 47 |
| `fever_false:90f7b87f` | `fever_false` | -- | false | 0/46 | 0.0% | null 46 |
| `fever_false:147d5cf0` | `fever_false` | -- | false | 0/45 | 0.0% | null 45 |
| `fever_false:d0ca84a7` | `fever_false` | -- | false | 0/45 | 0.0% | null 45 |
| `fever_false:1bc39bc3` | `fever_false` | -- | false | 0/44 | 0.0% | null 44 |
| `fever_false:09f93f50` | `fever_false` | -- | false | 0/43 | 0.0% | null 43 |
| `fever_false:0429068c` | `fever_false` | -- | false | 0/39 | 0.0% | null 39 |
| `fever_false:e270abe4` | `fever_false` | -- | false | 0/38 | 0.0% | null 38 |
| `fever_false:f586e96d` | `fever_false` | -- | false | 0/38 | 0.0% | null 38 |
| `fever_false:80d7f6c1` | `fever_false` | -- | false | 0/36 | 0.0% | null 36 |
| `fever_false:990bcf31` | `fever_false` | -- | false | 0/33 | 0.0% | null 33 |
| `fever_false:cbf9d7a5` | `fever_false` | -- | false | 0/33 | 0.0% | null 33 |
| `fever_false:a1a7f33d` | `fever_false` | -- | false | 0/32 | 0.0% | null 32 |
| `fever_true:65e4286c` | `fever_true` | -- | true | 0/32 | 0.0% | false 4, null 28 |
| `fever_false:6b3816ec` | `fever_false` | -- | false | 0/30 | 0.0% | null 30 |
| `fever_false:a4cda1e2` | `fever_false` | -- | false | 0/29 | 0.0% | null 29 |
| `fever_false:f7d03fcb` | `fever_false` | -- | false | 0/28 | 0.0% | null 28 |
| `fever_false:4bf3caad` | `fever_false` | -- | false | 0/27 | 0.0% | null 27 |
| `fever_false:19e489f0` | `fever_false` | -- | false | 0/26 | 0.0% | null 26 |
| `fever_false:a9a0220e` | `fever_false` | -- | false | 0/26 | 0.0% | null 26 |
| `fever_true:c3a107bf` | `fever_true` | -- | true | 0/25 | 0.0% | null 25 |
| `fever_true:38830530` | `fever_true` | -- | true | 0/24 | 0.0% | null 24 |
| `fever_true:f885b3cb` | `fever_true` | -- | true | 0/23 | 0.0% | false 1, null 22 |
| `fever_true:0e1dc686` | `fever_true` | -- | true | 0/22 | 0.0% | null 22 |
| `fever_true:53332e1a` | `fever_true` | -- | true | 0/21 | 0.0% | null 21 |
| `fever_true:76170ee2` | `fever_true` | -- | true | 0/21 | 0.0% | false 4, null 17 |

*135 further fragments with at least one error are in the JSON sidecar; every fragment is there regardless of score.*

## `tfidf_logreg`

TF-IDF unigrams and bigrams into logistic regression. Tests whether the dataset is keyword-solvable. Its overall accuracy is close to uninformative; the `null_ambiguous` slice is the number that matters.

Decision-rule margins selected per fold (on each fold's own validation split): 0.0, 0.05.

*Confusion matrix, raw argmax*

|  | pred false | pred true | pred null | total |
|---|---|---|---|---|
| **truth false** | 1344 | 238 | 897 | 2479 |
| **truth true** | 68 | 771 | 642 | 1481 |
| **truth null** | 118 | 115 | 5807 | 6040 |
| **total** | 1530 | 1124 | 7346 | 10000 |

`null -> true`: 115 of 6040 truly-null examples (1.90%).

*Confusion matrix, after the decision rule*

|  | pred false | pred true | pred null | total |
|---|---|---|---|---|
| **truth false** | 1345 | 236 | 898 | 2479 |
| **truth true** | 69 | 763 | 649 | 1481 |
| **truth null** | 120 | 110 | 5810 | 6040 |
| **total** | 1534 | 1109 | 7357 | 10000 |

`null -> true`: 110 of 6040 truly-null examples (1.82%).

### Per class, after the decision rule

| class | support | predicted | precision | recall | F1 |
|---|---|---|---|---|---|
| `false` | 2479 | 1534 | 87.7% | 54.3% | 67.0% |
| `true` | 1481 | 1109 | 68.8% | 51.5% | 58.9% |
| `null` | 6040 | 7357 | 79.0% | 96.2% | 86.7% |

### By label mode

| label mode | n | eff n | accuracy [95% CI] |
|---|---|---|---|
| false | 2479 | **60** | 54.3% [43.5%, 65.2%] |
| null_ambiguous | 3062 | **150** | 93.6% [90.5%, 95.9%] |
| null_structural | 2978 | **1** | 98.8% [98.8%, 98.8%] |
| true | 1481 | **96** | 51.5% [43.5%, 59.6%] |

### By null sub-class

| sub-class | n | eff n | null recall [95% CI] |
|---|---|---|---|
| hedged | 721 | **32** | 89.7% [79.6%, 96.3%] |
| historical | 751 | **36** | 96.0% [92.3%, 98.6%] |
| metaphor | 865 | **47** | 94.0% [90.3%, 97.0%] |
| third_party | 725 | **35** | 94.6% [89.7%, 98.4%] |

### By fragment library

| library | n | eff n | accuracy [95% CI] |
|---|---|---|---|
| fever_false | 2479 | **60** | 54.3% [43.5%, 65.2%] |
| fever_null_hedged | 721 | **32** | 89.7% [79.6%, 96.3%] |
| fever_null_historical | 751 | **36** | 96.0% [92.3%, 98.6%] |
| fever_null_metaphor | 865 | **47** | 94.0% [90.3%, 97.0%] |
| fever_null_thirdparty | 725 | **35** | 94.6% [89.7%, 98.4%] |
| fever_true | 1481 | **96** | 51.5% [43.5%, 59.6%] |
| (none) | 2978 | **1** | 98.8% [98.8%, 98.8%] |

### Per-fragment errors (worst first)

Whether errors are spread thinly across many fragments or piled onto a few is the difference
between "the method is too weak" (model work) and "these specific ideas are not learnable from
the data we have" (library work, and these are the fragments to write more of). No intervals:
a fragment is one cluster, so an interval over its own examples measures nothing.

176 of 344 decisive fragments were got wrong at least once.

| fragment | library | sub-class | truth | correct | accuracy | predicted as |
|---|---|---|---|---|---|---|
| `fever_false:033927e6` | `fever_false` | -- | false | 0/52 | 0.0% | null 52 |
| `fever_false:b74a83cf` | `fever_false` | -- | false | 0/47 | 0.0% | null 47 |
| `fever_false:de0596c4` | `fever_false` | -- | false | 0/47 | 0.0% | true 16, null 31 |
| `fever_false:cbf9d7a5` | `fever_false` | -- | false | 0/33 | 0.0% | true 1, null 32 |
| `fever_true:f885b3cb` | `fever_true` | -- | true | 0/23 | 0.0% | null 23 |
| `fever_true:76170ee2` | `fever_true` | -- | true | 0/21 | 0.0% | null 21 |
| `fever_true:0ddb8a11` | `fever_true` | -- | true | 0/19 | 0.0% | null 19 |
| `fever_true:872e3af9` | `fever_true` | -- | true | 0/18 | 0.0% | null 18 |
| `fever_true:5e4f1da7` | `fever_true` | -- | true | 0/17 | 0.0% | null 17 |
| `fever_true:74ccf7bd` | `fever_true` | -- | true | 0/17 | 0.0% | null 17 |
| `fever_true:ef344ff7` | `fever_true` | -- | true | 0/17 | 0.0% | null 17 |
| `fever_null_hedged:965c4a64` | `fever_null_hedged` | hedged | null | 0/16 | 0.0% | false 12, true 4 |
| `fever_true:391fb2ce` | `fever_true` | -- | true | 0/15 | 0.0% | null 15 |
| `fever_true:97087dd7` | `fever_true` | -- | true | 0/15 | 0.0% | null 15 |
| `fever_true:d0dd4129` | `fever_true` | -- | true | 0/15 | 0.0% | null 15 |
| `fever_true:dd6bbec4` | `fever_true` | -- | true | 0/15 | 0.0% | null 15 |
| `fever_true:f32f1ddb` | `fever_true` | -- | true | 0/15 | 0.0% | false 1, null 14 |
| `fever_true:a92fcdc7` | `fever_true` | -- | true | 0/14 | 0.0% | null 14 |
| `fever_true:c2b356a0` | `fever_true` | -- | true | 0/14 | 0.0% | null 14 |
| `fever_true:c5d3e4a0` | `fever_true` | -- | true | 0/14 | 0.0% | false 14 |
| `fever_true:1c3df822` | `fever_true` | -- | true | 0/13 | 0.0% | false 1, null 12 |
| `fever_true:ed36ef0f` | `fever_true` | -- | true | 0/13 | 0.0% | null 13 |
| `fever_true:5ce7adbd` | `fever_true` | -- | true | 0/12 | 0.0% | null 12 |
| `fever_true:7844c66b` | `fever_true` | -- | true | 0/12 | 0.0% | null 12 |
| `fever_true:c7489e90` | `fever_true` | -- | true | 0/12 | 0.0% | null 12 |
| `fever_true:781b30e3` | `fever_true` | -- | true | 0/9 | 0.0% | null 9 |
| `fever_false:e8c514ff` | `fever_false` | -- | false | 1/54 | 1.9% | false 1, true 25, null 28 |
| `fever_false:b96ed279` | `fever_false` | -- | false | 1/46 | 2.2% | false 1, null 45 |
| `fever_false:464eb13e` | `fever_false` | -- | false | 1/28 | 3.6% | false 1, null 27 |
| `fever_false:f7d03fcb` | `fever_false` | -- | false | 1/28 | 3.6% | false 1, true 8, null 19 |
| `fever_false:f6985a04` | `fever_false` | -- | false | 2/47 | 4.3% | false 2, true 34, null 11 |
| `fever_false:e0897296` | `fever_false` | -- | false | 2/38 | 5.3% | false 2, true 34, null 2 |
| `fever_null_hedged:42486de4` | `fever_null_hedged` | hedged | null | 1/19 | 5.3% | false 5, true 13, null 1 |
| `fever_true:79211e25` | `fever_true` | -- | true | 1/19 | 5.3% | false 1, true 1, null 17 |
| `fever_true:d00c307b` | `fever_true` | -- | true | 1/19 | 5.3% | true 1, null 18 |
| `fever_true:a6c8dae6` | `fever_true` | -- | true | 1/15 | 6.7% | true 1, null 14 |
| `fever_true:ed3c8c83` | `fever_true` | -- | true | 1/13 | 7.7% | true 1, null 12 |
| `fever_false:f586e96d` | `fever_false` | -- | false | 3/38 | 7.9% | false 3, true 27, null 8 |
| `fever_false:8f64f673` | `fever_false` | -- | false | 4/46 | 8.7% | false 4, null 42 |
| `fever_false:f1e3b80c` | `fever_false` | -- | false | 4/45 | 8.9% | false 4, null 41 |

*136 further fragments with at least one error are in the JSON sidecar; every fragment is there regardless of score.*

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
| false | 2479 | **60** | 0.0% [0.0%, 0.0%] |
| null_ambiguous | 3062 | **150** | 100.0% [100.0%, 100.0%] |
| null_structural | 2978 | **1** | 100.0% [100.0%, 100.0%] |
| true | 1481 | **96** | 0.0% [0.0%, 0.0%] |

### By null sub-class

| sub-class | n | eff n | null recall [95% CI] |
|---|---|---|---|
| hedged | 721 | **32** | 100.0% [100.0%, 100.0%] |
| historical | 751 | **36** | 100.0% [100.0%, 100.0%] |
| metaphor | 865 | **47** | 100.0% [100.0%, 100.0%] |
| third_party | 725 | **35** | 100.0% [100.0%, 100.0%] |

### By fragment library

| library | n | eff n | accuracy [95% CI] |
|---|---|---|---|
| fever_false | 2479 | **60** | 0.0% [0.0%, 0.0%] |
| fever_null_hedged | 721 | **32** | 100.0% [100.0%, 100.0%] |
| fever_null_historical | 751 | **36** | 100.0% [100.0%, 100.0%] |
| fever_null_metaphor | 865 | **47** | 100.0% [100.0%, 100.0%] |
| fever_null_thirdparty | 725 | **35** | 100.0% [100.0%, 100.0%] |
| fever_true | 1481 | **96** | 0.0% [0.0%, 0.0%] |
| (none) | 2978 | **1** | 100.0% [100.0%, 100.0%] |

### Per-fragment errors (worst first)

Whether errors are spread thinly across many fragments or piled onto a few is the difference
between "the method is too weak" (model work) and "these specific ideas are not learnable from
the data we have" (library work, and these are the fragments to write more of). No intervals:
a fragment is one cluster, so an interval over its own examples measures nothing.

156 of 344 decisive fragments were got wrong at least once.

| fragment | library | sub-class | truth | correct | accuracy | predicted as |
|---|---|---|---|---|---|---|
| `fever_false:357d0419` | `fever_false` | -- | false | 0/59 | 0.0% | null 59 |
| `fever_false:98e77994` | `fever_false` | -- | false | 0/59 | 0.0% | null 59 |
| `fever_false:5f8bdfcd` | `fever_false` | -- | false | 0/55 | 0.0% | null 55 |
| `fever_false:56a45ff1` | `fever_false` | -- | false | 0/54 | 0.0% | null 54 |
| `fever_false:e8c514ff` | `fever_false` | -- | false | 0/54 | 0.0% | null 54 |
| `fever_false:00302cae` | `fever_false` | -- | false | 0/53 | 0.0% | null 53 |
| `fever_false:a5b671a1` | `fever_false` | -- | false | 0/53 | 0.0% | null 53 |
| `fever_false:bf61fab6` | `fever_false` | -- | false | 0/53 | 0.0% | null 53 |
| `fever_false:033927e6` | `fever_false` | -- | false | 0/52 | 0.0% | null 52 |
| `fever_false:55bf1913` | `fever_false` | -- | false | 0/51 | 0.0% | null 51 |
| `fever_false:2e971b63` | `fever_false` | -- | false | 0/50 | 0.0% | null 50 |
| `fever_false:5eb45ee7` | `fever_false` | -- | false | 0/50 | 0.0% | null 50 |
| `fever_false:295f42b5` | `fever_false` | -- | false | 0/49 | 0.0% | null 49 |
| `fever_false:8599e318` | `fever_false` | -- | false | 0/49 | 0.0% | null 49 |
| `fever_false:d15cd85c` | `fever_false` | -- | false | 0/49 | 0.0% | null 49 |
| `fever_false:17f6c637` | `fever_false` | -- | false | 0/48 | 0.0% | null 48 |
| `fever_false:a0bfd501` | `fever_false` | -- | false | 0/47 | 0.0% | null 47 |
| `fever_false:b74a83cf` | `fever_false` | -- | false | 0/47 | 0.0% | null 47 |
| `fever_false:de0596c4` | `fever_false` | -- | false | 0/47 | 0.0% | null 47 |
| `fever_false:f6985a04` | `fever_false` | -- | false | 0/47 | 0.0% | null 47 |
| `fever_false:8d02bd9e` | `fever_false` | -- | false | 0/46 | 0.0% | null 46 |
| `fever_false:8f64f673` | `fever_false` | -- | false | 0/46 | 0.0% | null 46 |
| `fever_false:90f7b87f` | `fever_false` | -- | false | 0/46 | 0.0% | null 46 |
| `fever_false:acf258b4` | `fever_false` | -- | false | 0/46 | 0.0% | null 46 |
| `fever_false:b96ed279` | `fever_false` | -- | false | 0/46 | 0.0% | null 46 |
| `fever_false:147d5cf0` | `fever_false` | -- | false | 0/45 | 0.0% | null 45 |
| `fever_false:d0ca84a7` | `fever_false` | -- | false | 0/45 | 0.0% | null 45 |
| `fever_false:f1e3b80c` | `fever_false` | -- | false | 0/45 | 0.0% | null 45 |
| `fever_false:0c3535b0` | `fever_false` | -- | false | 0/44 | 0.0% | null 44 |
| `fever_false:1bc39bc3` | `fever_false` | -- | false | 0/44 | 0.0% | null 44 |
| `fever_false:463f8189` | `fever_false` | -- | false | 0/44 | 0.0% | null 44 |
| `fever_false:cba743d0` | `fever_false` | -- | false | 0/44 | 0.0% | null 44 |
| `fever_false:09f93f50` | `fever_false` | -- | false | 0/43 | 0.0% | null 43 |
| `fever_false:90623989` | `fever_false` | -- | false | 0/43 | 0.0% | null 43 |
| `fever_false:0429068c` | `fever_false` | -- | false | 0/39 | 0.0% | null 39 |
| `fever_false:93390aea` | `fever_false` | -- | false | 0/39 | 0.0% | null 39 |
| `fever_false:c747066d` | `fever_false` | -- | false | 0/38 | 0.0% | null 38 |
| `fever_false:e0897296` | `fever_false` | -- | false | 0/38 | 0.0% | null 38 |
| `fever_false:e270abe4` | `fever_false` | -- | false | 0/38 | 0.0% | null 38 |
| `fever_false:f586e96d` | `fever_false` | -- | false | 0/38 | 0.0% | null 38 |

*116 further fragments with at least one error are in the JSON sidecar; every fragment is there regardless of score.*

## `tfidf_logreg__shuffled`

TF-IDF unigrams and bigrams into logistic regression. Tests whether the dataset is keyword-solvable. Its overall accuracy is close to uninformative; the `null_ambiguous` slice is the number that matters. **Negative control:** trained on permuted training labels (seed 7) and evaluated on the unpermuted test split, where it must land at chance.

Decision-rule margins selected per fold (on each fold's own validation split): 0.0.
Every fold selected margin 0, so the ruled and raw views below are the same decisions. That is a finding rather than a bug: no margin improved macro-F1 without worsening the `null -> true` rate.

*Confusion matrix, raw argmax*

|  | pred false | pred true | pred null | total |
|---|---|---|---|---|
| **truth false** | 0 | 0 | 2479 | 2479 |
| **truth true** | 1 | 0 | 1480 | 1481 |
| **truth null** | 2 | 0 | 6038 | 6040 |
| **total** | 3 | 0 | 9997 | 10000 |

`null -> true`: 0 of 6040 truly-null examples (0.00%).

*Confusion matrix, after the decision rule*

|  | pred false | pred true | pred null | total |
|---|---|---|---|---|
| **truth false** | 0 | 0 | 2479 | 2479 |
| **truth true** | 1 | 0 | 1480 | 1481 |
| **truth null** | 2 | 0 | 6038 | 6040 |
| **total** | 3 | 0 | 9997 | 10000 |

`null -> true`: 0 of 6040 truly-null examples (0.00%).

### Per class, after the decision rule

| class | support | predicted | precision | recall | F1 |
|---|---|---|---|---|---|
| `false` | 2479 | 3 | 0.0% | 0.0% | 0.0% |
| `true` | 1481 | 0 | -- | 0.0% | 0.0% |
| `null` | 6040 | 9997 | 60.4% | 100.0% | 75.3% |

### By label mode

| label mode | n | eff n | accuracy [95% CI] |
|---|---|---|---|
| false | 2479 | **60** | 0.0% [0.0%, 0.0%] |
| null_ambiguous | 3062 | **150** | 100.0% [100.0%, 100.0%] |
| null_structural | 2978 | **1** | 99.9% [99.9%, 99.9%] |
| true | 1481 | **96** | 0.0% [0.0%, 0.0%] |

### By null sub-class

| sub-class | n | eff n | null recall [95% CI] |
|---|---|---|---|
| hedged | 721 | **32** | 100.0% [100.0%, 100.0%] |
| historical | 751 | **36** | 100.0% [100.0%, 100.0%] |
| metaphor | 865 | **47** | 100.0% [100.0%, 100.0%] |
| third_party | 725 | **35** | 100.0% [100.0%, 100.0%] |

### By fragment library

| library | n | eff n | accuracy [95% CI] |
|---|---|---|---|
| fever_false | 2479 | **60** | 0.0% [0.0%, 0.0%] |
| fever_null_hedged | 721 | **32** | 100.0% [100.0%, 100.0%] |
| fever_null_historical | 751 | **36** | 100.0% [100.0%, 100.0%] |
| fever_null_metaphor | 865 | **47** | 100.0% [100.0%, 100.0%] |
| fever_null_thirdparty | 725 | **35** | 100.0% [100.0%, 100.0%] |
| fever_true | 1481 | **96** | 0.0% [0.0%, 0.0%] |
| (none) | 2978 | **1** | 99.9% [99.9%, 99.9%] |

### Per-fragment errors (worst first)

Whether errors are spread thinly across many fragments or piled onto a few is the difference
between "the method is too weak" (model work) and "these specific ideas are not learnable from
the data we have" (library work, and these are the fragments to write more of). No intervals:
a fragment is one cluster, so an interval over its own examples measures nothing.

156 of 344 decisive fragments were got wrong at least once.

| fragment | library | sub-class | truth | correct | accuracy | predicted as |
|---|---|---|---|---|---|---|
| `fever_false:357d0419` | `fever_false` | -- | false | 0/59 | 0.0% | null 59 |
| `fever_false:98e77994` | `fever_false` | -- | false | 0/59 | 0.0% | null 59 |
| `fever_false:5f8bdfcd` | `fever_false` | -- | false | 0/55 | 0.0% | null 55 |
| `fever_false:56a45ff1` | `fever_false` | -- | false | 0/54 | 0.0% | null 54 |
| `fever_false:e8c514ff` | `fever_false` | -- | false | 0/54 | 0.0% | null 54 |
| `fever_false:00302cae` | `fever_false` | -- | false | 0/53 | 0.0% | null 53 |
| `fever_false:a5b671a1` | `fever_false` | -- | false | 0/53 | 0.0% | null 53 |
| `fever_false:bf61fab6` | `fever_false` | -- | false | 0/53 | 0.0% | null 53 |
| `fever_false:033927e6` | `fever_false` | -- | false | 0/52 | 0.0% | null 52 |
| `fever_false:55bf1913` | `fever_false` | -- | false | 0/51 | 0.0% | null 51 |
| `fever_false:2e971b63` | `fever_false` | -- | false | 0/50 | 0.0% | null 50 |
| `fever_false:5eb45ee7` | `fever_false` | -- | false | 0/50 | 0.0% | null 50 |
| `fever_false:295f42b5` | `fever_false` | -- | false | 0/49 | 0.0% | null 49 |
| `fever_false:8599e318` | `fever_false` | -- | false | 0/49 | 0.0% | null 49 |
| `fever_false:d15cd85c` | `fever_false` | -- | false | 0/49 | 0.0% | null 49 |
| `fever_false:17f6c637` | `fever_false` | -- | false | 0/48 | 0.0% | null 48 |
| `fever_false:a0bfd501` | `fever_false` | -- | false | 0/47 | 0.0% | null 47 |
| `fever_false:b74a83cf` | `fever_false` | -- | false | 0/47 | 0.0% | null 47 |
| `fever_false:de0596c4` | `fever_false` | -- | false | 0/47 | 0.0% | null 47 |
| `fever_false:f6985a04` | `fever_false` | -- | false | 0/47 | 0.0% | null 47 |
| `fever_false:8d02bd9e` | `fever_false` | -- | false | 0/46 | 0.0% | null 46 |
| `fever_false:8f64f673` | `fever_false` | -- | false | 0/46 | 0.0% | null 46 |
| `fever_false:90f7b87f` | `fever_false` | -- | false | 0/46 | 0.0% | null 46 |
| `fever_false:acf258b4` | `fever_false` | -- | false | 0/46 | 0.0% | null 46 |
| `fever_false:b96ed279` | `fever_false` | -- | false | 0/46 | 0.0% | null 46 |
| `fever_false:147d5cf0` | `fever_false` | -- | false | 0/45 | 0.0% | null 45 |
| `fever_false:d0ca84a7` | `fever_false` | -- | false | 0/45 | 0.0% | null 45 |
| `fever_false:f1e3b80c` | `fever_false` | -- | false | 0/45 | 0.0% | null 45 |
| `fever_false:0c3535b0` | `fever_false` | -- | false | 0/44 | 0.0% | null 44 |
| `fever_false:1bc39bc3` | `fever_false` | -- | false | 0/44 | 0.0% | null 44 |
| `fever_false:463f8189` | `fever_false` | -- | false | 0/44 | 0.0% | null 44 |
| `fever_false:cba743d0` | `fever_false` | -- | false | 0/44 | 0.0% | null 44 |
| `fever_false:09f93f50` | `fever_false` | -- | false | 0/43 | 0.0% | null 43 |
| `fever_false:90623989` | `fever_false` | -- | false | 0/43 | 0.0% | null 43 |
| `fever_false:0429068c` | `fever_false` | -- | false | 0/39 | 0.0% | null 39 |
| `fever_false:93390aea` | `fever_false` | -- | false | 0/39 | 0.0% | null 39 |
| `fever_false:c747066d` | `fever_false` | -- | false | 0/38 | 0.0% | null 38 |
| `fever_false:e0897296` | `fever_false` | -- | false | 0/38 | 0.0% | null 38 |
| `fever_false:e270abe4` | `fever_false` | -- | false | 0/38 | 0.0% | null 38 |
| `fever_false:f586e96d` | `fever_false` | -- | false | 0/38 | 0.0% | null 38 |

*116 further fragments with at least one error are in the JSON sidecar; every fragment is there regardless of score.*

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
| 0 | 10000 | 2000 | 2000 | 0.0 | 61.9% | 61.9% | 29.5% | 0.00% |
| 1 | 10000 | 2000 | 2000 | 0.0 | 60.6% | 60.6% | 29.2% | 0.00% |
| 2 | 10000 | 2000 | 2000 | 0.0 | 60.3% | 60.3% | 25.7% | 0.00% |
| 3 | 10000 | 2000 | 2000 | 0.0 | 61.3% | 61.3% | 26.6% | 0.00% |
| 4 | 10000 | 2000 | 2000 | 0.0 | 61.4% | 61.4% | 29.1% | 0.00% |

### `tfidf_logreg`

| fold | train n | val n | test n | margin | acc (raw) | acc (ruled) | macro-F1 | null->true |
|---|---|---|---|---|---|---|---|---|
| 0 | 10000 | 2000 | 2000 | 0.0 | 82.2% | 82.2% | 74.2% | 0.41% |
| 1 | 10000 | 2000 | 2000 | 0.0 | 75.1% | 75.1% | 63.3% | 2.50% |
| 2 | 10000 | 2000 | 2000 | 0.0 | 83.5% | 83.5% | 76.6% | 0.58% |
| 3 | 10000 | 2000 | 2000 | 0.05 | 76.6% | 76.4% | 68.0% | 2.30% |
| 4 | 10000 | 2000 | 2000 | 0.0 | 78.6% | 78.6% | 72.1% | 3.32% |

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
| 1 | 10000 | 2000 | 2000 | 0.0 | 60.0% | 60.0% | 25.0% | 0.00% |
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
* **A slice containing only one class cannot be read on its own.** The four `null` sub-class slices hold nothing but truly-`null` examples, so a model that answers `null` unconditionally scores 100% on all of them. Sub-class recall is a finding only when the `true` and `false` recalls are high at the same time, which is why the per-class table sits beside it.
* **The overall interval is dominated by one resampling unit.** All structural nulls share one unit, by design -- thousands of recombinations of a handful of filler sentences are not thousands of observations. The cost is that the pooled overall accuracy swings widely under resampling for reasons that have nothing to do with the model. The `decisive` slice, which drops them, is the one to read.
* **Fragment libraries, not sample size, are the ceiling.** Forty-seven metaphor clusters is forty-seven ideas however many examples are drawn from them. Everything section 9 of `arch_training.md` says about what this data is and is not worth continues to apply in full.

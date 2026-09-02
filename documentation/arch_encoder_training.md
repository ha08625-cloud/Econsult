# Encoder Training and Evaluation (Offline Tooling)

**LLM INSTRUCTIONS:** This document explains what `scripts/encoder_training/`
does, why it is shaped the way it is, and how to read what it produces. It is
the *consumer* of the dataset; `arch_training.md` is the *producer* and is the
prerequisite for this one — sections 9 and 10 in particular. Read
`arch_encoder.md` for the boundary a trained model would eventually sit behind.
Read the code for signatures and flags; nothing here restates them.

---

## Scope

Training and evaluating one encoder head against the generated datasets, and
saying honestly what the resulting numbers are worth.

**Key files:** `scripts/encoder_training/*.py`, `requirements-ml.txt`,
`models/encoder/<signal>/<arm>/`, `reports/encoder_training/`

**Offline only.** Nothing here runs in the live application and `app/` never
imports it — `tests/test_wiring.py` and `tests/test_encoder_training_dataset.py`
both assert the dependency runs one way.

**Related:** `arch_training.md` (the dataset), `arch_encoder.md` (the runtime
boundary), `documentation/encoder/Fine_tuning_plan.md` (the training strategy).

---

## 1. The question this exists to answer

One question, and every design decision below is arranged to make it legible:

> **Is the bottleneck the model, or the fragment libraries?**

The work covers six signals — fever, dysuria, urinary frequency, nocturia, flank
pain, haematuria — each as an independent three-way classification (`true`,
`false`, `null`) trained by its own run. One head per run, not one model
answering six questions. If a fully fine-tuned encoder still
cannot tell whose fever it is or when it happened, the limit is in the ideas the
libraries contain and the next month is library work. If unfreezing the encoder
lifts the hard `null` sub-classes clear of a frozen probe, the representation was
the bottleneck and the next month is model work.

Nothing predicts which. The point of building both arms is that the question
stops being settled by argument.

**There is a third answer, and it is not a way out of the first two.** Some
fragments do not settle the clinical question at all, so their ceiling is below
100% however good the model and however large the library. `arch_training.md`
section 9 sets out which ones actually qualify — fewer than it first appears,
because `null` is itself the determinate answer for "the text does not say" —
and sets the rule that keeps this from swallowing the question above: a ceiling
below the general target is declared per library *before* the run that measures
it. Declared afterwards it is unfalsifiable, and a model-versus-libraries
comparison in which any inconvenient slice can be reclassified once seen answers
nothing.

---

## 2. Data flow

```
data/synthetic/*.txt  ──> scripts.synthetic_data ──> fever_present.foldN.{train,val,test}.jsonl
   (hand-written)          (label-first, cluster-      + .stats.json sidecar
                            aware fold splitting)         (provenance per fragment)
                                                            │
                                     dataset.py  <──────────┘
                                     (loads both files, asserts disjointness,
                                      attaches each example's resampling unit)
                                                            │
                      ┌─────────────────────┬───────────────┴────────┐
                      │                     │                        │
                 baselines.py           train.py (Arm A)        train.py (Arm B)
                 majority / length /    frozen encoder +        every layer
                 TF-IDF + logreg        Linear(768, 3)          unfrozen
                      │                     │                        │
                      └─────────────────────┴───────────────┬────────┘
                                                            │
                                    decision.py  ──> margin selected on each
                                    (DD9)             fold's own validation split
                                                            │
                                    metrics.py + report.py ──> reports/encoder_training/
                                    (cluster bootstrap,          <stem>.json  (always)
                                     McNemar, slicing)           <stem>.md    (worth keeping)
                                                            │
                                    models/encoder/<signal>/<arm>/
                                    metadata.json, foldN.head.json, foldN.decision.json
```

Everything upstream of the two arms is standard library. See section 6.

---

## 3. Five folds, not one split

**This is the load-bearing decision and the reason the tooling is shaped as it
is.** `arch_training.md` section 10 is the canonical statement of the problem:
the effective sample size of an evaluation slice is the number of distinct
fragment *clusters* behind it, not the number of examples.

Under a single 70/15/15 split, a per-sub-class recall figure rests on a handful
of clusters and carries an interval far wider than any effect this work could
plausibly detect, so as originally specified the ticket could not have answered
its own question. **`arch_training.md` section 10 has the arithmetic and the
current cluster counts; they are not repeated here**, because two copies of a
figure that moves whenever a library is tagged or grown is how the two documents
came to disagree about it.

Fold mode fixes it for about ten minutes of GPU time: every cluster is a test
cluster in exactly one fold, so pooling the five makes a sub-class's aggregate
test set its whole library.

**State the gain honestly.** Effective n rises severalfold; the error bar does
not fall as fast. Uncertainty on a proportion falls as 1/√n, so pooling roughly
halves the interval rather than removing it — which is the difference between a
number that can carry a conclusion and one that cannot, and nothing more.
Quoting the rise in effective n as though it were the improvement in precision is
wrong, and the report says so in its own limitations.

Folds create no new ideas. A library's clusters are its clusters however many
folds are run, so `arch_training.md` section 9 applies unchanged.

**One known and accepted subtlety.** Fold *i*'s validation clusters are fold
*i+1*'s test clusters. Within a fold that is not leakage — each fold trains its
own model and never sees its own test bucket — but the pooled result carries a
small optimism, because each fold's decision margin was selected on a sibling
fold's test data. Nested cross-validation would remove it and is not worth the
cost for one scalar per fold. Every report names it.

---

## 4. The two arms

**Arm A, the frozen probe.** The encoder is loaded once, every split is embedded
and cached, and a `Linear(768, 3)` is fitted over the vectors. Near-zero cost per
run once the cache exists, which is what makes it the arm that exercises the
plumbing — the loader, the margin selection, the artefact writer, the report.

**Arm B, the fine-tune.** Every layer unfrozen, three epochs at batch 32, lr
2e-5, 10% linear warmup, AdamW, fp32 — the published BERT-base recipe, fixed
before any run. Roughly two minutes per fold on a 12GB card.

**Arm A alone would have been worthless for the ticket's question**, which is
why both exist: a weak probe cannot separate "the libraries are the bottleneck"
from "the method is too weak". Arm A is *expected* to do badly on the four hard
`null` sub-classes — third-party attribution, tense and metaphor are
compositional scope problems, and a single mean-pooled vector blurs the structure
that carries them. That prediction is recorded in the report before any run.

Three implementation points that are easy to get wrong and invisible when you do:

* **Each fold loads the encoder afresh.** `run_finetune` takes an encoder
  *factory*, not an encoder. Reusing one object would start fold *i+1* from
  weights already fine-tuned on fold *i*'s training clusters, which are fold
  *i+1*'s validation and test clusters. Every disjointness check would still
  pass.
* **Exactly four things may be chosen against validation**: pooling mode,
  learning rate, epoch count, decision margin. The list is a constant in
  `train.py` and is written into both the sidecar and the report header, because
  how much the pooled result flatters itself depends on how many quantities were
  tuned that way.
* **The embedding cache is keyed in its filename** on base model revision,
  pooling mode, `max_seq_len`, generator version, dataset seed, signal, fold,
  split and a digest of the example texts. A stale cache hit produces a report
  full of plausible numbers with no warning anywhere, so every input that changes
  what an embedding *is* changes the name of the file holding it.

### 4a. The base encoder, and the comparison that chose it

**The encoder is `roberta-base`.** It is `DEFAULT_BASE_MODEL`, it is the only
choice the run console offers, and every report committed since 2026-08-16 was
produced with it. Nothing here should be run on anything else without a specific
reason, and a run on a different encoder cannot be read beside a committed report
whatever else it has in common with one.

That was decided once, by `compare-models`, in
`reports/encoder_training/fever_present.model_comparison.*`: `roberta-base` at
92.9% decisive accuracy against `Bio_ClinicalBERT`'s 84.1% and
`bert-base-uncased`'s 85.8%, over the same five folds. Two things explain the
gap. The largest error family on file is contrastive negation — "my mum had a
fever, I never got one myself" — which is negation scope and attribution rather
than clinical vocabulary, and BERT-base is weak there whatever corpus it was
pretrained on. And `Bio_ClinicalBERT` *discards patient casing*: it lowercases
its input into a 28,996-entry vocabulary inherited from `bert-base-cased`, so the
cased entries are unreachable and the casing section 5 of `arch_training.md`
deliberately preserves reaches it as noise. `roberta-base`'s byte-level BPE has
neither problem. That is the whole of what the retired encoders are still good
for; the reports and their write-ups hold the detail, and no live path points at
them.

`compare-models` itself remains, for a future question about named encoders, and
`--base-models` is required rather than defaulted so that using it is always a
deliberate act. Its design: Arm B over several base models against **the same
folds**, written into **one** report. The single report is the point — the paired
McNemar tests in `report.compare_models` run between the runs found in one
report, and two separately-written reports leave only overlapping confidence
intervals to compare, which the 2026-08-09 numbers say cannot separate anything
this comparison could plausibly produce (decisive CI [79.1, 88.0], per-fold sd
4.4%). Paired, the same five folds detect roughly 2–3 points.

Each encoder's run is named `arm_b_finetune@<label>` and its artefacts go to
`models/encoder/<signal>/arm_b_finetune__<slug>/`. Without a distinct label two
runs would both be called `arm_b_finetune` and every paired test would compare a
model against itself, so the labels are required to be distinct.

**The headline is not the output.** `model_movement` in the report is: per-library
accuracy and per-fragment error counts, side by side across encoders, with a
`spread` column. A diffuse lift and a fix to one error family are different
findings that lead to different next months, and an aggregate accuracy cannot
tell them apart. For a single-class library — `fever_false` holds only `false`
examples — that table's accuracy *is* that class's recall on it.

Two constraints on what can go in: `EXPECTED_HIDDEN_SIZE` is 768 and is asserted
at load, so a `-large` model is rejected rather than silently reshaping the head;
and the embedding cache keys on the resolved revision, so encoders never share
cached vectors.

**`TokeniserFacts.discards_casing`**, in `model.py`, is what caught the casing
defect above and is still checked on every load: true when a tokeniser lowercases
its input *and* holds a vocabulary built for cased text, which makes the cased
entries unreachable and fragments every capitalised word into subwords the
vocabulary was not organised around. It is `False` for `roberta-base`. It is
recorded rather than corrected — overriding `do_lower_case` would make
fine-tuning disagree with whatever the checkpoint was pretrained under — and the
report header carries `tokeniser_discards_casing` so the reading is available
rather than reconstructed.

### 4b. Joint multi-head training

`finetune --dataset <tree> --signals <signal ...>` trains one encoder with
several heads sharing it, over a merged tree `merge-folds` produced. `--dataset`
names the fold tree to load; `--signals` names which of its declared heads to
train, defaulting to every signal the fold declares. **A plain `finetune
--signal fever_present` call takes the single-signal path completely unchanged**
— same stem, same artefact directory, same report — which is what a
single-signal run's numbers being comparable to every report committed before
joint training existed depends on. That equality is proved rather than assumed:
the joint and single-signal fold runners are independent implementations and
`tests/test_encoder_training_arm_b.py` diffs their output on the same fold
rather than asserting a tautology.

Five decisions carry the design; the code is the authority on which function
does what.

**Training is joint; evaluation is per head.** The training split widens to
every example labelled for *any* trained signal — a dysuria example belongs in
it because it carries a dysuria label, even though it carries no key at all for
the other five heads. The loss already normalised over labelled positions across
every signal together, so nothing there changes. What is new is epoch and margin
selection.

**Epoch selection is one criterion across every head (DD6).** One shared encoder
means one set of weights to stop at, so per-head early stopping is impossible.
The criterion is the **unweighted** mean of every head's own validation
macro-F1 — not weighted by how many labelled examples each head has, because
that would let fever and dysuria decide nocturia's stopping point, and the weak
signals are exactly where this ticket's question is most alive. Every head's own
per-epoch macro-F1 is recorded in the sidecar too, so a report can show where a
head's own best epoch differed from the one DD6 selected — and where it does,
part of any movement against that head's single-signal run is the stopping rule
rather than the representation.

**Margin selection is per head, independently — no cross-head trade.** Each
head's margin is chosen on that head's own validation predictions alone, under
the unchanged DD9 objective. A margin that sacrificed nocturia's `null → true`
rate to buy fever a point of macro-F1 is a decision nobody asked for. A joint
`foldN.decision.json` is therefore always a `{signal: rule}` mapping, never a
single flat rule, with its own reader and writer kept separate from the
single-signal pair.

**Predictions are keyed by the id they had in their own signal's tree**
(merge.py DD4). Asking a merged example for a signal's id returns
`meta.source_ids[signal]`, and an unmerged one returns `example_id` unchanged,
so every existing pairing mechanism — McNemar above all — works across a joint
run's predictions and a single-signal run's without either module knowing the
other exists. Asking for a signal's id on an example that is masked for it is a
hard error, not a fallback: it means scoring a signal on an example that should
already have been excluded.

**Artefacts go to `models/encoder/joint<N>/<arm>/`**, not under any one trained
signal's directory — there is no single signal a joint model belongs to, and
putting it under one of six would either duplicate the shared ~440MB encoder N
times or leave five of six directories pointing at weights that live in a sixth.
One physical run yields one `ModelRun` **per trained head**, each shaped exactly
like a single-signal Arm B run's so it drops into that signal's own report
unchanged, written under the stem `<signal>.<dataset>.arm_b_finetune` so it
cannot collide with a single-signal report. Arm A and the baselines do not ride
along: both are single-head machinery, and the paired comparison this ticket
turns on is against a single-signal Arm B run made separately, not a probe
fitted beside the joint encoder.

---

### 4c. The three-arm comparison, and what it does not isolate

`joint-compare` is the only command here that loads **three** fold trees, one
per arm, and it exists because the question "does exposure to five other
symptoms' confounders help each symptom's answer" needs a control on both sides
of it.

| arm | tree | examples/epoch | that head's labelled positions |
|---|---|---|---|
| **A1** | that signal alone | 10,000 | **10,000** |
| **A2** | that signal alone, ~4.5× the recombinations | 44,680 | **44,680** |
| **A3** | the merged tree | 44,680 | **10,000** |

**A1 against A3 is the comparison.** It holds per-head supervision fixed and
varies exactly one thing: whether the shared encoder is also being pulled by
five other heads. It is pairable because A3's slice for a signal *is* that
signal's own examples, under the ids they had in its own tree (4b, DD4), so
McNemar, `_qualify` and the per-fragment table all work with no help from the
report layer.

**A2 is an unpaired volume control.** Its test examples are different texts, so
it pairs with nothing and is read through the pooled cluster interval and the
per-fold spread instead. It is retained deliberately: without it, a movement
between A1 and A3 cannot be separated from the fact that A3 takes 4.5× the
encoder gradient steps. Its prediction ids are qualified with the arm's own
label before the report sees them (`_as_unpaired`), so "A2 pairs with nothing"
is a property of what the report is handed rather than of how many examples
somebody happened to generate — two trees that coincidentally numbered the same
count of test examples would otherwise be paired text-for-different-text.

**What no arm isolates, and every report says so in its header.** There is no
arm matched to A3 on *both* encoder steps and per-head supervision, because no
such dataset exists — holding one fixed moves the other. A1↔A3 varies exposure
and step count together; A2 bounds how much of any movement step count alone can
explain. DD6 is a second confound: A1 stops at the epoch maximising its own
head's validation macro-F1 and A3 at the epoch maximising the unweighted mean
across heads, so the header prints both arms' selected epochs per fold and says
where this head's own best would have differed.

**One report per signal**, stem `<signal>.joint_comparison`, holding all three
arms, the baselines fitted on A1's folds, and the holdout numbers. One
six-signal report was rejected: the headline, ticket-question, sub-class recall
and per-fragment sections are all per-signal-slice by construction. Because a
report holds no per-example predictions, **A1 is re-run rather than read off
disk** — the paired test can only be computed inside the invocation that
produced both arms, and A1 is deterministic from the pinned seeds.

### 4d. The companion comparison: three arms, two trainings

`companion-compare` is the multi-symptom ticket's command. It loads **two**
merged trees, generated from the same libraries with the same seed, counts, fold
triple and salt, differing in `--companion-share` and in nothing else.

| arm | what it is | cost |
|---|---|---|
| **Arm 0** | `--companion-share 0`, joint six-head. The control, and the regenerated baseline at `GENERATOR_VERSION` 3. | 5 fold-trainings |
| **Arm P** | the same at a non-zero share. | 5 fold-trainings |
| **Arm C** | Arm 0's trained heads, every margin re-selected on **Arm P's** validation split. | free |

**Arm C is not a third dataset and not a third training run.** Same weights,
same raw argmax scores, same test examples; the only thing that moves is the
threshold each head applies. It runs inside Arm 0's fold loop, while the model
is still on the device, because reloading five fine-tuned encoders to change a
threshold would be an hour of I/O to avoid a minute of arithmetic. It exists to
separate *the training data change helped* from *the margin selection data
change helped*: the decision rule maximises macro-F1 subject to a `null → true`
rate no worse than argmax's, and until companions existed no validation split
contained the case the rule most needs to get right — text dense with another
symptom's clinical language whose correct answer is still `null`. If Arm C
captures most of Arm P's gain, the cheap fix was available without regenerating
anything, and that is the headline.

**Two pairing facts, and they point opposite ways.**

*Arm P cannot be paired on the synthetic test set.* Its examples are different
texts numbered from zero exactly as Arm 0's are, so the id sets match exactly
while the texts behind them do not — `compare_models` would pair two different
texts under one id and report a McNemar test over pairs that do not exist,
raising only in the lucky case where the two disagree about a truth. Its ids are
qualified with the arm's label before the report sees them, the same
`_as_unpaired` guard A2 uses. Arm 0 and Arm C *do* share a test set and are
paired on it, which is exactly the comparison "did the margin alone move
anything" needs.

*Every arm pairs on the real text.* The 67 submissions are the same 67 for all
three, so `holdout_comparisons` runs a paired McNemar per signal — **one test
per fold, never pooled**. Five folds are five models scored on one sample of 67;
concatenating them would hand McNemar 335 pairs over 67 observations. This is
what needed the per-submission decisions to be kept at all: `score_holdout` now
returns a `cells` block, the report reads it, runs its test and drops it, so the
committed JSON carries the comparison rather than 6,000 triples.

**One report per signal**, stem `<signal>.companion_comparison`, carrying all
three arms, the `null → true` cell as the headline of the real-text section, the
paired real-text tests, and a `companions` block recording each arm's generator
settings beside its DD5 leak detector — the largest gap between any two label
modes in mean companions per example, across every training split of that arm.
That last figure is in the report rather than in a one-off script because a
companion count that tracked the label mode would mean *more clinical text ⇒
more likely `null`*, and the arm would be void rather than reinterpretable.

### 4e. Scoring the declared threshold

`score-companions` reads those six reports back and prints the criteria that
were written down *before* the run, each marked `HELD` or `NOT HELD`
(`scripts/encoder_training/thresholds.py`). It trains nothing, needs no GPU and
imports nothing outside the stdlib; the criteria and their limits live in the
module as constants, so what is being scored is readable without running it.

**The threshold is scored by a program because it is easy to get wrong by
hand.** The primary criterion is a twenty-point gap on at least four of six
signals, each signal's figure a mean over five folds in a different file. The
negative control is a two-point limit read in the direction where *movement is
the failure* — the synthetic test set cannot contain the failure companions were
built to fix, so a large gain there is evidence of a new shortcut. Hand
arithmetic across thirty fold-means, with one of the four criteria pointing
backwards, is not a check anybody can re-run.

**DD5's leak detector is a gate, not a criterion.** It is scored first, off the
`companions` block, and a failure marks every criterion `NOT SCORED` and exits
non-zero rather than printing numbers a reader would use anyway. A run whose
companion draw correlates with the label did not test what it was built to test;
its scores are not a weaker answer, they are not an answer. Criteria that are
merely *not held* exit zero — a recorded failure is the command working.

**The collapse check is printed beside the criteria and is not one of them.**
There are two ways to drive the real-text `null → true` cell to nothing: stop
inventing symptoms, or stop answering. An arm that says `null` to everything
scores zero on that cell, clears the primary criterion on every signal, and --
because the accuracy guard is a comparison against Arm 0 rather than against the
66.7% all-`null` floor -- clears the guard too whenever Arm 0 sits below that
floor, which it does. So the scorer prints each arm's real-text accuracy on the
*decisive* cells alone beside its per-class recall: a collapse reads as decisive
accuracy falling with `null` recall at 100% and `true`/`false` recall at zero.
It is not scored, because it was not declared in advance; it is printed so that
a write-up cannot claim the guard ruled out something the guard does not test.

Arm C is reported without a verdict on purpose. Its criterion asks *how much* of
Arm P's gain a re-selected margin captured, and a high number is the ticket's
finding rather than its failure. Where Arm P did not gain on a signal, the
capture is reported as undefined rather than as a percentage of nothing.

---

### 4f. Cross-tree evaluation (`--test-dir`)

`finetune --test-dir` trains on `--data-dir`'s train and val splits and scores
against a *second* tree's test split. It exists for the noise experiment
(`arch_training.md` 12.6): the interesting cells are the off-diagonal ones —
train clean, score damaged, and back — and every other path in this package
trains and scores inside one tree, which can only produce the diagonal.

`dataset.swap_test_split` does the swap, and its checks are the whole point.
The two folds must agree on signal, fold count, fold index and split salt, they
must carry the same head set, and their test splits must hold **exactly the same
example ids and fragment ids**. That is what makes the swapped number a
comparison — the same held-out clusters in a different surface form — rather
than a plausible-looking score against an unrelated dataset. Both trees are
loaded and checked before the encoder is downloaded, so a wrong path costs a
second rather than an hour of GPU.

Unset, it changes nothing. It is on `finetune` alone: `probe`,
`compare-models` and `joint-compare` do not need it, and an unused flag on four
subcommands is four things to keep correct. When it is set, the report header
carries `test_dataset_dir` and the test tree's `noise` block, and the Arm B
artefact's dataset block carries `test_dir`.

**What it was built for, and what that found.** The noise sweep ran fifteen
cells on `fever_present` across five folds — a clean tree and three damage rates,
plus the conservative `--freeze-signal-vocabulary all` variant at the middle
rate. Because effective n is identical in every cell (noise creates no clusters),
the cells differ only in surface form. A clean-trained model loses 8.5 points of
decisive accuracy on text damaged at 12% per word; a rate-matched model recovers
essentially all of it and costs nothing on clean text, and a model trained at 3%
recovers 87% of the damage done at 12% — the cross-rate cells are the whole
reason the result is usable when the real damage rate is unmeasurable. The
off-diagonal cells are what carry all of that: the diagonals alone show only that
noise training does no harm.
`reports/encoder_training/2026-08-31-noise-2x2.md` is the write-up and the
authority on every figure.

Two limits of the flag are worth recording where they will be read. It scores two
*separately trained* models against id-identical test sets, and nothing in this
package performs a paired test across two report runs — so the sweep's central
comparison rests on non-overlapping unpaired intervals when a sharper test is
available in principle. And the real-text holdout is unaffected by `--test-dir`,
because it is scored on real submissions rather than on a tree; two cells sharing
a training tree therefore report identical holdout figures, which is a plumbing
check rather than a result.

## 5. How the numbers are made honest

Four mechanisms, all stdlib, all in `metrics.py` and `report.py`.

**The resampling unit is the cluster.** Every confidence interval is a bootstrap
over decisive clusters, not examples. Resampling examples would measure the noise
of the recombination process rather than the noise that matters, and would report
intervals roughly √(examples/clusters) too narrow — a factor of ten or more here.

**Every slice prints its effective n beside its example count.** Not a nicety:
it is the single guard against the failure mode `arch_training.md` section 10
names. A slice with n = 3,062 and eff n = 150 is 150 ideas seen many times.

**Comparisons between models are paired.** "Does the transformer beat
bag-of-words on `null_ambiguous`" cannot be answered by eyeballing two
independent point estimates, so `report.py` runs an exact McNemar test on
identical examples, on raw argmax decisions. Its pairing unit is the example, not
the cluster, so it answers "did these two models behave differently on this data"
rather than "would they behave differently on new fragments" — read it alongside
the interval, never instead of it.

**Across-fold spread is a stability check, not a confidence interval.** Five
folds give it four degrees of freedom. It is itself noisy and will occasionally
look reassuringly small for no reason. The pooled cluster bootstrap is the
headline.

Two slices are reported where one would be misleading. `overall` includes the
structural nulls, which all share one resampling unit — thousands of
recombinations of a handful of filler sentences are not thousands of observations
— and that one unit holding a third of the examples swings the pooled accuracy by
twenty points under resampling for reasons that have nothing to do with the
model. **`decisive` drops them and is the slice to read.**

**What "decisive" means, and what companions changed about it.** A fragment is
decisive for an example when it is not filler **and** its signal is one the
example carries a label for. Before `--companion-share` (`arch_training.md`
section 5) those were the same test, because the only non-filler fragment an
example could hold was its own signal's — so the loader tested filler-ness
alone. Above zero they come apart: a companion is another signal's clinical
language, non-filler by construction and saying nothing about the label this
example is supervised on. Reading only filler-ness there would count every
companion as a second decisive fragment and refuse to load the dataset at all,
which is what happened the first time a companion tree was handed to
`load_folds`. Two consequences worth knowing:

* A structural null may now hold clinical text and still have no decisive
  fragment, which is exactly what the mode has always meant — no fragment
  decisive **for this signal**.
* Structural nulls still share `STRUCTURAL_NULL_UNIT` as one resampling unit,
  and above zero that is more conservative than it used to be: they are drawn
  from the companion libraries as well as the filler ones, so they are no longer
  recombinations of a handful of sentences. Treating them as one unit understates
  their effective n rather than overstating it, which is the safe direction, so
  the slice is unchanged.
* A dataset from `--emit-signals all` carries a key for every signal its
  fragments jointly decide, so several fragments are decisive at once and it
  raises here by design. No arm loads one, and `merge-folds` refuses one too.

---

## 6. Two dependency tiers, and the boundary is load-bearing

Everything that decides what a number *means* — the loader, the metrics, the
cluster bootstrap, the decision rule, the report writer, the cache key, the
metadata sidecar — is standard library, so CI's unit job covers it on a runner
with no GPU and no ML wheels.

`torch`, `transformers` and `scikit-learn` live in `requirements-ml.txt`, which
CI never installs and the Dockerfile never sees. Tests that need them skip
themselves. `model.py` is the only module importing torch at module scope;
everything else imports it inside functions so the CLI stays importable without
it.

This is what stops a ~2.5GB torch wheel entering an image that serves forms. The
other half of that guarantee is `.dockerignore`: the Dockerfile copies `app/` and
`data/` explicitly rather than `COPY . .`, but `COPY data/ ./data/` takes the
whole directory, and `data/synthetic/generated/` holds ~40MB of JSONL and ~215MB
of cached vectors after a sweep. `.dockerignore` excludes it, plus `models/` and
`reports/`.

**Run `smoke-cuda` first on any new machine.** `torch.cuda.is_available()`
returns `True` on a wheel that cannot launch a single kernel — the failure mode a
Blackwell GPU produces with a pre-CUDA-12.8 build — so the subcommand runs a real
matmul and prints the compute capability beside torch's CUDA version. It is
separate from `smoke`, and network-free, because when it fails the 440MB encoder
download `smoke` performs is wasted. When it fails, the fix is a different torch
wheel and never a code change.

---

## 7. Artefacts

Trained heads go to `models/encoder/<signal>/<arm>/` as **JSON**, not pickles: a
2,307-parameter probe needs no binary format, and a JSON artefact is diffable in
review and loadable without torch. One directory per arm, because both arms write
the same filenames and a shared directory would have Arm B silently overwrite the
Arm A result it is being compared against.

Each fold writes `foldN.head.json` and `foldN.decision.json` — the margin travels
separately because it is retuned far more often than the weights — alongside one
`metadata.json` recording the base model and resolved revision, the tokeniser's
*measured* casing behaviour, pooling mode, every seed, the dataset provenance, the
ruleset hash, the validation numbers each margin was chosen from, and for Arm B
the per-fold training-loss curve and the determinism mode that actually ran.

**For Arm B the JSON head is not the model.** The 110M fine-tuned parameters
underneath it are, and they live in `arm_b_finetune/weights/foldN.encoder.pt`,
~440MB each, git-ignored. `foldN.head.json` records the path to its `.pt`, because
a 3×768 matrix on top of a different encoder is meaningless. Not committing them
is a deferral, not a punt: a fold regenerates in about two minutes from the pinned
seeds and revision, and where 2.2GB of weights should live durably is a question
this work does not answer.

`ruleset_hash()` is **duplicated** in `ruleset_hash.py` rather than imported from
`app/services/engine/ruleset.py`. Offline tooling must not couple to runtime
wiring, and a unit test asserting the two implementations agree on `data/uti1.json`
is cheaper than a coupling that prevents divergence. Note that the hash covers the
whole ruleset dict, so editing any unrelated question invalidates the recorded
hash — the right conservative default, but do not read a changed hash as a changed
fever definition.

---

## 8. Reading a report

`reports/encoder_training/<stem>.json` is always written and the markdown is
rendered *from* that JSON, so the two cannot disagree. **That folder's README
covers which stems exist, what is committed and what a write-up owes**; this
section is what to look at inside one.

The report is written to be read standalone, by someone who has not read these
documents. That is why it reproduces `arch_training.md` sections 9 and 10 in
full rather than citing them — the one place duplication is deliberate.

Five sections carry the weight:

* **Cluster-tag coverage** — printed above the headline, because it says how
  wide every interval below it should have been. A library with no `[cNN]`
  markers contributes one cluster per line by default, which is a claim that
  every line in it is an independent idea. Where that is false the library's
  `eff n` is an **upper bound** and its intervals are narrower than the truth.
  The warning fires whenever any library behind the run has zero coverage,
  which today is every run: `fever_true` and `fever_false` are untagged too.
  `arch_training.md` section 10 has the measured per-signal table and the
  reason this makes cross-signal rankings unsafe.
* **The ticket's question** — accuracy on `null_ambiguous`, the paired McNemar
  on the same slice, and where the errors fall. The report lays these out and
  explicitly declines to conclude: a renderer that concluded would be concluding
  from whichever comparison happened to clear a threshold someone picked while
  writing it.
* **Null sub-class recall, pooled** — the table the whole exercise exists for.
  Never read it alone: every example in those slices is truly `null`, so a model
  answering `null` unconditionally scores 100% across the row. It is a finding
  only when `true` and `false` recall are high at the same time.
* **Per-fragment errors, worst first** — the most decision-useful thing in the
  report. Errors spread thinly across many fragments mean the method is too weak;
  errors piled onto a handful mean those specific ideas are not learnable from the
  data we have, and the table names them. `error_concentration` states this as a
  number, against the fixed reference point that an even spread would put half the
  errors on half the erring fragments. "Not learnable from the data we have"
  splits one step further, and the table is where the split is visible: a thin
  library, an inconsistency in how a recurring case was sorted, or a fragment
  whose text genuinely does not settle the question. Only the third is a ceiling,
  and `arch_training.md` section 9 is the test for which one is in front of you.
* **Both confusion matrices** — raw argmax and post-decision-rule, because "the
  model is wrong" and "the rule is conservative" are different findings.
* **Pairs that could not be tested** — printed under the McNemar table whenever
  a report holds two runs scored on different examples (A2, above). McNemar
  pairs on the example id, so such a pair cannot be tested at all — and a reader
  who expected a comparison and found nothing would read the absence as "no
  difference found". Each entry names both runs, the slice, both sizes and how
  many ids they share. **A pair skipped for any reason other than a genuine
  dataset difference is a bug**, and the entry is what makes it findable: the
  only condition `compare_models` swallows is a differing example *set*, and a
  duplicate id or a truth disagreement on a shared one still raises.

A long header value — the arms table, what no arm isolates, the predictions
recorded before the run — is printed as prose under the header table rather than
inside a cell, because a markdown cell does not wrap and those are the entries a
reader most needs to be able to read.

The decision rule itself is a separate artefact with a stated objective: maximise
macro-F1 **subject to** a `null → true` rate no worse than argmax's. That cell
invents a symptom into a patient's pre-filled form, so it is a constraint and not
a term to trade against F1. The rule exists because the training mix (15/25/60) is
a generator flag rather than a measured prior over real submissions — reweighting
the loss would correct towards a second arbitrary target, whereas the decision
rule is tunable, versioned and documented.

---

## 9. What this deliberately does not do

* **It does not replace `encoder_stub.py`.** A single fever head *cannot*
  satisfy the runtime contract: `EncoderOutput.validate_against` requires output
  keys to match the ruleset's `send_to_encoder` signals exactly, and
  `data/uti1.json` declares seven. Swapping in a real encoder stays blocked until
  either all seven heads exist or that contract permits partial output. Recorded
  here so nobody plans around a swap that is not available.
* ~~**No multi-head or multi-signal training.**~~ **Built and measured.**
  `merge-folds` concatenates the per-signal fold trees into one that `load_folds`
  reads unchanged; `finetune --dataset <merged tree> --signals <heads>` trains
  several heads sharing one encoder (section 4b); `joint-compare` reports the
  three arms (section 4c) and ran on 2026-08-17; `companion-compare` reports the
  companion arms (section 4d) and ran on 2026-08-19.
  `arch_training.md` section 10 records what those runs established about the
  data and `reports/encoder_training/` holds the numbers.

  **The one thing that is easy to get wrong from here** is that a sweep must
  control for gradient steps. Merging six 10k datasets gives the encoder six
  times the updates, so a movement between A1 and A3 would otherwise confound
  cross-symptom exposure with step count. That is what the unpaired A2 arm is
  for, and it does not by itself isolate the question — the paired A1-vs-A3
  comparison does.
* **No hyperparameter search.** The recipe was fixed before any run. Four
  quantities may be chosen against validation and they are enumerated in code.
* ~~**No realistic held-out evaluation set.**~~ **Done.** `data/realistic/`
  holds 67 hand-written submissions and their labels, and every Arm B run since
  2026-08-16 scores them. Section 11 is the design and what the numbers are
  worth. What it does *not* close: the set is small, it is one person's voice,
  and it has no explicit denials on three of the six signals — see section 11.

---

## 10. Running it

```
python -m scripts.encoder_training generate-folds --folds 5   # 15 generator runs, scripted
python -m scripts.encoder_training merge-folds --folds 5      # concatenate six signals into one tree
python -m scripts.encoder_training baselines --folds 5        # majority / length / TF-IDF
python -m scripts.encoder_training smoke-cuda                 # can this GPU launch a kernel
python -m scripts.encoder_training smoke                      # ... and can it load the encoder
python -m scripts.encoder_training probe --folds 5            # Arm A, the frozen probe
python -m scripts.encoder_training finetune --folds 5         # Arm B, every layer unfrozen
python -m scripts.encoder_training finetune --folds 5 \       # Arm B, jointly: one encoder,
  --dataset joint6 --signals fever_present dysuria_present \  # every signal merge-folds wrote
  flank_pain_present haematuria_present nocturia_present urinary_frequency_present
python -m scripts.encoder_training compare-models --folds 5 \    # Arm B over several base
  --base-models roberta-base <other>                          # encoders; --base-models required
python -m scripts.encoder_training companion-compare --folds 5 \   # Arm 0, Arm P and Arm C
  --arm0-dir data/synthetic/generated/arm0 \
  --armp-dir data/synthetic/generated/armp \
  --dataset joint6
python -m scripts.encoder_training score-companions            # read those reports, score the
                                                               # declared threshold, no GPU
```

**Python 3.12 or later, in an environment of its own.** Every subcommand imports
the generator's CLI for one constant, and `recombine.py` uses PEP 695 generics,
so on 3.11 the whole package dies at import with a `SyntaxError` pointing at
`def _weighted_draw[KeyT](` — including `smoke-cuda`, which touches neither the
generator nor torch. It reads as a broken checkout and is nothing of the kind.
The environment needs `requirements-ml.txt` alone; nothing here imports `app/`,
so `requirements.txt` is not required for a training run.

`generate-folds` is scripted rather than documented as a shell loop because the
fifteen runs must agree on the fold count, the salt and the seed derivation, and a
loop that gets one of those wrong produces a directory that loads cleanly and
evaluates nonsense.

**Every command above runs on `roberta-base` without being told to** —
`DEFAULT_BASE_MODEL`, section 4a. `--base-model` exists but there is no reason to
pass it; a run on any other encoder produces numbers that cannot be read beside
any committed report, and it will not announce that. The base model is in every
report header; check it there before comparing anything.

By default `finetune` reports Arm B **and** Arm A **and** the baselines in one
report — the ticket's question is a paired comparison and McNemar can only make
it when both models are in the same report.
`reports/encoder_training/README.md` covers what is committed there and what a
write-up owes; it is not repeated here.

Both arms run a shuffled-label negative control by default. Arm B's control
passes by doing **two** things at once: driving training loss towards zero,
because 110M parameters can memorise a permutation, *and* scoring at chance on the
unpermuted test split. Either half alone means nothing, which is why the sidecar
keeps the loss curve.

`compare-models` is the one command whose negative control is **off** by default.
It is per-encoder work that would triple an already 3x sweep, and it answers a
question the run that motivated the comparison already answered; `--control`
turns it back on and the report header says which was done. Arm A is off by
default there too, since the frozen-vs-fine-tuned question is settled and every
extra run adds a row to each paired-comparison table.

`--folds` must match how the datasets were generated; the loader refuses a
directory whose sidecars disagree with the flag, whose filename lies about its
fold, or in which any cluster is a test cluster in two folds.

`finetune` and `compare-models` also score the real-text holdout by default —
see section 11. `--no-holdout` skips it and the report header says so; a
missing or mismatched labels file is a hard error rather than a silent skip,
raised before the encoder is loaded so it costs a second rather than an hour.

---

## 11. The real-text holdout

`data/realistic/` holds 67 free-text UTI submissions written to read like real
patients, their labels for all seven `send_to_encoder` signals, and the
arbitration notes for the cells where the call was arguable. **Its README is the
authority on what the set is, the five rules it is used under, its label
distribution and its limitations, and every report that quotes a number from it
prints those limitations rather than citing them.** This section is only what
the tooling does with the set.

**Why it exists.** Every other number this package produces is scored on
recombinations of the same fragment libraries the models were trained on. Held-out
*clusters* remove memorisation and nothing else: the test examples are still two
or three fragments, still exactly one supervised claim plus filler, still in the
generator's register. 92.9% there could be 55% here and no report written before
2026-08-16 would have shown it. This is the only measurement in the project that
speaks to text a patient actually wrote.

**Where it sits in the code.** `holdout.py` is standard library only and takes
the forward pass as an injected callable — the same tier boundary `dataset.py`
and `metrics.py` sit on, and for the same reason: everything deciding what the
number *means* is covered by CI's unit job on a runner with no ML wheels.
`train.encoder_scorer` is the torch half.

**Two of the README's rules are enforced by construction rather than by memory.**

* *It selects nothing.* Each fold model is scored here after its margin has been
  chosen on validation and after the synthetic test split has been scored. The
  order lives in one function, `train.select_then_score`, so a recording-fake
  unit test asserts the sequence instead of a reader trusting it. By the time
  the holdout is opened there is nothing left for it to influence.
* *The resampling unit is the submission.* There is no cluster structure here, so
  a submission's six or seven cells carry one unit id and resample together.
  Treating cells as independent would report an interval about √6 too narrow on
  the one set whose entire limitation is its size.

**Scored in-process, at the end of each fold, not as a later pass over saved
weights.** Three arms across six signals and five folds is 65 fine-tuned encoders
at ~440MB — roughly 28GB to retain and score later. Scoring 67 submissions while
the encoder is still in memory costs seconds and retains nothing.

**The folds are averaged, never pooled.** Five folds are five different models
scored on the *same* 67 submissions. Concatenating their predictions would count
each submission five times and claim an effective n of 335 for a sample of 67.
The report prints mean and across-fold spread, and the spread is a stability
check on four degrees of freedom rather than a confidence interval.

### What it can and cannot decide

**It cannot rank two models, and no report should use it to.** 67 submissions
give roughly ±12 points on one overall figure. Per signal it is worse: the
decisive slice — the cells where the patient actually said something, which is
the only slice that bounds anything — is 18 cells for `fever_present` and 6 for
`recent_uti_present`, so ±23 and ±40. The report prints that worst-case
half-width in the table beside each number rather than in a footnote, because
the failure mode here is a reader taking a per-signal figure at face value.

**It is a validity instrument, and it works in one direction.** A model in the
nineties on recombinations landing near chance on real text is unmissable at this
sample size. A three-point difference between two arms is not a finding.

Four limitations belong in every report that quotes it — the label provenance,
the one-person voice, the three signals with no `false` example, and the
signals whose figure is therefore a recall measurement. `data/realistic/README.md`
states them and the report prints all four rather than citing them. **The one
with teeth for a reader of this document is the third**: explicit denial was the
largest error family in the synthetic evaluation, and on three of six signals
this set cannot see it at all.

### Blank is not `null`

README rule 4: a signal the labeller *cannot judge* has its key omitted, and a
blank cell is that omission. `null` is a claim — the text raises the territory
and does not settle it, or is silent about it — and a model is scored on getting
it right. `holdout.py` refuses to merge the two and excludes an omitted cell from
numerator and denominator alike, exactly as `dataset.py` excludes a masked signal.

**No cell in today's file is blank, and that is correct rather than suspicious.**
Every submission is a UTI-context text, so every signal is either plainly raised
or plainly silent, and silence is `null` by the README's own definition. Arguable
is not the same as unjudgeable: the 13 arguable cells were judged, and the
arbitration file exists so a person can overturn them — two already were. A blank
becomes likely once the set gains the submissions it is missing, which is why the
loader implements the distinction whether or not the current file uses it.

### What is not scored here

Negative controls. A model fitted on permuted labels is not a candidate model,
and 67 submissions are too few to spend confirming that it is bad. Arm A and the
baselines are not scored either: Arm A reads a cached embedding matrix keyed to
the synthetic splits and the baselines are fitted on tokens, so neither has a
forward pass to hand these submissions without new machinery — and a
bag-of-words number on real text is not what the set is for. Arm B carries the
encoder that would eventually be deployed, so it is where the question is worth
asking.

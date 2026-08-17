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

Under a single 70/15/15 split, a per-sub-class recall figure rests on 2 to 6
clusters — it can only take the values 0, 0.5 or 1.0 — and carries roughly ±30
points of uncertainty. That is wider than any effect this work could plausibly
detect, so as originally specified the ticket could not have answered its own
question.

Fold mode fixes it for about ten minutes of GPU time. Every cluster is a test
cluster in exactly one fold, so pooling the five folds makes a sub-class's
aggregate test set its whole library: 32 to 47 clusters instead of 2 to 6.

**State the gain honestly.** Effective n rises 12- to 17-fold; the error bar does
not. Uncertainty on a proportion falls as 1/√n, so ±30 points becomes about ±8.
That is the difference between a number that can carry a conclusion and one that
cannot — a metaphor recall of 0.6 ±0.08 is a finding, 0.5 ±0.30 is noise. Quoting
the 12–17× figure as though it were the improvement in precision is wrong, and
the report says so in its own limitations.

Folds create no new ideas. Forty-seven metaphor clusters is forty-seven however
many folds are run, so `arch_training.md` section 9 applies unchanged.

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

### 4a. Comparing base encoders

`compare-models` runs Arm B over several base models against **the same folds**
and writes them into **one** report. The single report is the whole design: the
paired McNemar tests in `report.compare_models` run between the runs found in one
report, and two separately-written reports leave only overlapping confidence
intervals to compare — which the 2026-08-09 numbers say cannot separate anything
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

The default three, and why:

| encoder | role | what it isolates |
|---|---|---|
| `emilyalsentzer/Bio_ClinicalBERT` | incumbent | every number on file was produced with it |
| `bert-base-uncased` | control | pretraining corpus, and the tokeniser question below |
| `roberta-base` | contender | negation scope, not register |

The contender is on a different axis than clinical-vs-lay register, deliberately.
The largest error family on file is contrastive negation — "my mum had a fever,
I never got one myself" — which is negation scope and attribution rather than
vocabulary. BERT-base is weak there whatever it was pretrained on.
`microsoft/deberta-v3-base` is the stronger choice again on that axis and is a
valid `--base-models` value, but it needs `sentencepiece` and `protobuf`, which
`requirements-ml.txt` does not install.

Two constraints on what can go in: `EXPECTED_HIDDEN_SIZE` is 768 and is asserted
at load, so a `-large` model is rejected rather than silently reshaping the head;
and the embedding cache keys on the resolved revision, so encoders never share
cached vectors.

**The tokeniser fact this surfaced.** `TokeniserFacts.discards_casing` is true
when a tokeniser lowercases its input *and* holds a vocabulary built for cased
text — the cased entries then become unreachable and every capitalised word is
fragmented into subwords the vocabulary was not organised around. Bio_ClinicalBERT
is exactly that: `do_lower_case: true` over 28,996 entries inherited from
`bert-base-cased` via BioBERT. So the patient casing section 5 of
`arch_training.md` preserves reaches that encoder as noise, not signal.

This is recorded rather than corrected. Overriding `do_lower_case` would make
fine-tuning disagree with whatever the checkpoint was pretrained under, and the
shipped config is the only evidence of what that was. The honest response is the
comparison above, where `bert-base-uncased`'s vocabulary and casing agree by
construction — which also means part of any gain it shows is the tokeniser rather
than the register, and the report header carries `tokeniser_discards_casing` so
that reading is available rather than reconstructed.

### 4b. Joint multi-head training

`finetune --dataset <tree> --signals <signal ...>` trains one encoder with
several heads sharing it, over a merged tree `merge-folds` produced. `--dataset`
names the fold tree to load (the signal position of the fold filename);
`--signals` names which of its declared heads to train and evaluate, defaulting
to every signal the loaded fold declares. A plain `finetune --signal
fever_present` call still resolves both to `fever_present` and takes the
single-signal path completely unchanged — same stem, same artefact directory,
same report — which is what a single-signal run's numbers being comparable to
every report committed before joint training existed depends on. That equality
is proved rather than assumed: `run_finetune_joint_fold(fold, factory,
signals=[signal], ...)` and `run_finetune_fold(fold, factory, signal=signal,
...)` are independent implementations, and
`tests/test_encoder_training_arm_b.py` diffs their output on the same fold
rather than asserting a tautology.

**Training is joint; evaluation is per head.** `_labelled_any` widens the
training split to every example labelled for *any* trained signal — a dysuria
example belongs in it because it carries a dysuria label, even though it
carries no key at all for the other five heads. `masked_cross_entropy` already
normalised over labelled positions across every signal together (it always had
to, for the single-head case to be a special case of the general one), so
nothing there changes. What is new is epoch and margin selection.

**Epoch selection is one criterion across every head (DD6).** One shared
encoder means one set of weights to stop at, so per-head early stopping is
impossible. The criterion is the **unweighted** mean of every head's own
validation macro-F1 — not weighted by how many labelled examples each head has,
because that would let fever and dysuria decide nocturia's stopping point, and
the weak signals are exactly where this ticket's question is most alive. Every
head's own per-epoch macro-F1 is recorded in the sidecar too, not just the
mean, so a report can show where a head's own best epoch differed from the one
DD6 actually selected — and where it does, part of any movement against that
head's single-signal run is the stopping rule rather than the representation.

**Margin selection is per head, independently — no cross-head trade.** Each
head's margin is chosen by `select_margin` on that head's own validation
predictions alone, under the unchanged DD9 objective. A margin that sacrificed
nocturia's `null → true` rate to buy fever a point of macro-F1 is a decision
nobody asked for. `foldN.decision.json` under a joint artefact directory is
therefore always a `{signal: rule}` mapping, never a single flat rule —
`write_joint_artefacts`/`read_joint_decision` are the writer and reader for it,
kept separate from the single-signal `write_artefacts`/`DecisionRule.read` pair,
which is unchanged.

**Predictions are keyed by the id they had in their own signal's tree
(merge.py DD4).** `Example.id_for(signal)` returns `meta.source_ids[signal]`
on a merged tree and `example_id` unchanged on one that was never merged, and
`Prediction.from_example` calls it rather than reading `example_id` directly —
one small change in `metrics.py` that makes every existing pairing mechanism,
McNemar above all, work across a joint run's predictions and a single-signal
run's without either module knowing the other exists. Asking for a signal's id
on an example that is masked for it is a hard error, not a fallback: it means
scoring a signal on an example `is_labelled` should already have excluded.

**Artefacts go to `models/encoder/joint<N>/<arm>/`**, not under any one
trained signal's own directory — there is no single signal a joint model
belongs to, and putting it under one of six would either duplicate the shared
~440MB encoder N times or leave five of six directories pointing at weights
that live in a sixth. `foldN.head.json` holds every trained head's weights in
one file, keyed by signal, alongside the one `.pt` they all share.

**One `ModelRun` per trained head, from one physical run.** `run_finetune_joint`
returns a `signal -> ModelRun` mapping rather than one `ModelRun`: each entry is
that signal's own view of the same training run (`JointFineTuneFoldResult.
for_signal`), shaped exactly like a single-signal Arm B run's `ModelRun` so it
drops into that signal's own report unchanged. The CLI writes one report per
head, stem `<signal>.<dataset>.arm_b_finetune`, so it cannot collide with a
single-signal report's own `<signal>.arm_b_finetune` stem. Arm A and the
baselines do not ride along in a joint run: both are single-head machinery, and
the paired comparison this ticket turns on (A1 vs A3) is against a
single-signal Arm B run made separately, not a probe fitted beside the joint
encoder.

**What this does not do.** It does not decide which comparisons matter or how
they are reported — that is 4c, below. The sweep itself (task 5) has not been
run.

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

---

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

`reports/encoder_training/<stem>.json` is always written; the markdown is
rendered *from* that JSON and nothing else, so the human-readable report and the
machine-readable one cannot disagree. Commit the JSON always; commit the markdown
for runs worth keeping.

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
* ~~**No multi-head or multi-signal training.**~~ **The training path is done.**
  `planned_updates/multi_symptom_training_expansion.md` is the plan for this,
  and `arch_training.md` 12.8 is the summary. Three things it establishes that
  are easy to get wrong from here.

  **The six single-signal runs are done** (2026-08-16) and needed no code
  change, because `--signal` was already a flag on every subcommand. Six Arm B
  heads at `roberta-base`, one per signal, with Arm A and the baselines in each
  report; `arch_training.md` section 10 has the results table and
  `reports/encoder_training/2026-08-16-plain-english.md` is the write-up. Every
  shuffled-label control passed on all six. **Arm B beat Arm A on
  `null_ambiguous` in every signal**, p between 3e-05 and 2e-39 — the fever
  finding, replicated six times over. Six separate heads, not a joint model.

  **The merge step exists** (`scripts/encoder_training/merge.py`,
  `merge-folds`): it concatenates the six per-signal fold trees into one that
  `load_folds` reads unchanged, keeping every head masked where it had no label
  and every example's original id in `meta.source_ids`.

  **The joint training path exists** (section 4b): `finetune --dataset
  <merged tree> --signals <heads>` trains several heads sharing one encoder,
  with DD6's shared epoch criterion and independent per-head margins. What
  remains is the report shape that holds three arms per signal (A1, the
  volume-matched A2, and the joint A3) and is safe on an unpairable A2, and the
  six-signal sweep across all three arms — tasks 4 and 5 of
  `planned_updates/joint_multi_head_training_implementation.md`.

  Whatever runs the sweep must control for gradient steps. Merging six 10k
  datasets gives the encoder six times the updates, so a fever movement between
  A1 and A3 would confound cross-symptom exposure with step count. A2 — that
  signal alone at the merged example count, same clusters, same steps, more of
  them — is the unpaired control that bounds how much of any movement step
  count alone could explain; it does not by itself isolate the ticket's
  question, which is what the paired A1-vs-A3 comparison is for (DD1 of the
  implementation plan).
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
python -m scripts.encoder_training compare-models --folds 5   # Arm B over several base encoders
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

**`--base-model roberta-base` is not optional on a run meant to be comparable.**
`DEFAULT_BASE_MODEL` is `Bio_ClinicalBERT`, which `fever_present.model_comparison`
put nine points below roberta-base on decisive accuracy (84.1% against 92.9%).
Omit the flag and the run succeeds, reports nothing unusual, and produces numbers
that cannot be read beside any of the six committed reports. The base model is in
every report header; check it there before comparing anything.

By default `finetune` reports Arm B **and** Arm A **and** the baselines in one
report. That is not padding: the ticket's question is a paired comparison on the
`null_ambiguous` slice, and McNemar can only make it when both models are in the
same report. Arm A costs seconds once its embedding cache exists.

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
arbitration notes for the 13 cells where the call was arguable. Its README is
the authority on the rules; this section is what the tooling does with them and
how to read the number.

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

Four limitations belong in every report that quotes it, and the report prints
all four rather than citing them:

* **The labels were proposed by Claude and reviewed by the maintainer.** The
  labeller and the model share an architecture and could share a blind spot,
  which would inflate the score in a way no resampling would reveal.
* **One person's voice.** Real submissions vary by age, first language, literacy,
  how ill the person feels while typing, and what they think a GP wants to hear.
* **Three signals have no `false` example at all** — `dysuria_present`,
  `urinary_frequency_present`, `nocturia_present`. A model that never predicts
  `false` is not penalised on them, so their numbers are very nearly recall-only,
  and explicit denial was the largest error family in the synthetic evaluation.
* **`dysuria_present` is 56 `true` against 11 `null` and 0 `false`**, so its
  figure is a recall measurement and is reported as one.

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

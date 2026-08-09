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

The work covers exactly one signal, `fever_present`, as a three-way
classification: `true`, `false`, `null`. If a fully fine-tuned encoder still
cannot tell whose fever it is or when it happened, the limit is in the ideas the
libraries contain and the next month is library work. If unfreezing the encoder
lifts the hard `null` sub-classes clear of a frozen probe, the representation was
the bottleneck and the next month is model work.

Nothing predicts which. The point of building both arms is that the question
stops being settled by argument.

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

Four sections carry the weight:

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
  errors on half the erring fragments.
* **Both confusion matrices** — raw argmax and post-decision-rule, because "the
  model is wrong" and "the rule is conservative" are different findings.

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
* **No multi-head or multi-signal training.** The masked-loss path — a *missing*
  signal key means "exclude from the loss", an explicit `null` means "train
  towards the null class" — is written and unit-tested against synthetic
  fixtures, because with one signal it gets no coverage from real data and
  conflating the two after multi-head training starts is expensive.
* **No hyperparameter search.** The recipe was fixed before any run. Four
  quantities may be chosen against validation and they are enumerated in code.
* **No realistic held-out evaluation set.** This is the next ticket, and it is
  the one that decides whether anything here is evidence about real patient text:
  **60–100 hand-written realistic full submissions, deliberately unlike the
  recombinations, labelled by hand, held out and never touched by a training
  decision.** Held-out clusters remove memorisation and nothing else; the test
  examples are still short, still one supervised claim plus filler, still
  assembled by the same generator from the same libraries in the same register.

---

## 10. Running it

```
python -m scripts.encoder_training generate-folds --folds 5   # 15 generator runs, scripted
python -m scripts.encoder_training baselines --folds 5        # majority / length / TF-IDF
python -m scripts.encoder_training smoke-cuda                 # can this GPU launch a kernel
python -m scripts.encoder_training smoke                      # ... and can it load the encoder
python -m scripts.encoder_training probe --folds 5            # Arm A, the frozen probe
python -m scripts.encoder_training finetune --folds 5         # Arm B, every layer unfrozen
```

`generate-folds` is scripted rather than documented as a shell loop because the
fifteen runs must agree on the fold count, the salt and the seed derivation, and a
loop that gets one of those wrong produces a directory that loads cleanly and
evaluates nonsense.

By default `finetune` reports Arm B **and** Arm A **and** the baselines in one
report. That is not padding: the ticket's question is a paired comparison on the
`null_ambiguous` slice, and McNemar can only make it when both models are in the
same report. Arm A costs seconds once its embedding cache exists.

Both arms run a shuffled-label negative control by default. Arm B's control
passes by doing **two** things at once: driving training loss towards zero,
because 110M parameters can memorise a permutation, *and* scoring at chance on the
unpermuted test split. Either half alone means nothing, which is why the sidecar
keeps the loss curve.

`--folds` must match how the datasets were generated; the loader refuses a
directory whose sidecars disagree with the flag, whose filename lies about its
fold, or in which any cluster is a test cluster in two folds.

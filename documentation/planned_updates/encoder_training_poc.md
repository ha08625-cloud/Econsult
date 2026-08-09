# Provisional Plan: Build the encoder component and train the first head

**Status: provisional. Nothing here is built or agreed.** This is stage 1 of the
workflow in `CLAUDE.md` — a plan to be reviewed and expanded into an
implementation plan, not an implementation plan itself.

**Related:** `arch_training.md` (the dataset this consumes — read section 9 and
section 10 before reading section 5 of this document), `arch_encoder.md` (the
boundary a trained model eventually sits behind),
`documentation/encoder/Fine_tuning_plan.md` and
`documentation/planned_updates/add_encoder.md` (the earlier sketches this
supersedes on the points where they disagree — see section 3).

---

## 1. The question this ticket exists to answer

Not "can we train a model". We almost certainly can, and it will produce a
number above 90%, and that number will be close to meaningless. Section 9 of
`arch_training.md` is already blunt about why: the validation split holds **15
distinct positive fever fragments**, so every `true` example in validation is a
recombination of those 15 sentences.

The question worth spending the ticket on is:

> **Is the bottleneck the model or the fragment libraries?**

That decides what the next month looks like. If a fine-tuned ClinicalBERT
handles the hard `fever_null` sub-classes — third-party, historical, metaphor,
hay fever, attribution — then the pipeline works and the next work is scaling libraries and
signals (`arch_training.md` section 12). If it does not beat a bag-of-words
model on those same sub-classes, then no amount of model work helps and the next
work is library work: more fragments, more ideas, the length and urgency leaks in
section 9.

Everything in this plan is arranged to make that comparison legible. The
headline accuracy figure is close to worthless and should not be the thing we
report to ourselves.

**Predicted outcome, written down now so the plan can be judged against
reality later:** overall test accuracy 90%+; near-perfect on `null_structural`
and on clear positives and negatives; bag-of-words within a few points overall;
the transformer's only real advantage appearing on the `null_ambiguous` slice,
and even there weakest on metaphor and hay fever. If that prediction holds, the
ticket has succeeded — it will have told us where to spend effort next.

---

## 2. Scope

**In scope.** Offline tooling that reads the generated JSONL datasets, trains a
3-way head for `fever_present` on top of Bio_ClinicalBERT, evaluates it against
baselines with the slices that matter, and writes weights plus a metadata
sidecar plus a report to disk.

**Out of scope, deliberately.**

* **Replacing `encoder_stub.py`.** `app/` is untouched by this ticket, and
  nothing under `app/` imports anything this ticket adds. Serving a 440MB model
  from a Railway container — image size, cold start, per-submission CPU latency,
  Trivy surface — is a real and separate problem, and bundling it into this
  ticket would mean we could not tell which half had failed.
* **Multi-signal / multi-head training.** The dysuria and flank_pain libraries
  exist but the generator will not emit their labels: that needs the label
  vectors and declared silence of `arch_training.md` section 12.5. This ticket
  trains one head. The loss is nevertheless written with per-signal masking from
  day one (section 6.4) because retrofitting it later is where the mistake in
  `arch_training.md` section 7 gets made.
* **A realistic held-out evaluation set.** The single most valuable thing we
  could build next, and named here so it is not forgotten (section 9). Not this
  ticket.
* **Hyperparameter search.** Section 8 explains why searching against a
  15-fragment validation set is actively harmful.

---

## 3. Design decisions

Three of these overrule earlier documents. Where this plan and
`Fine_tuning_plan.md` / `add_encoder.md` disagree, those documents predate the
dataset actually existing, and this plan wins.

### 3.1 One 3-way softmax head per signal, not a binary head

`Fine_tuning_plan.md` section 0 says "N independent binary heads" each learning
`free_text → {true | false | null}`. That is a three-class problem described in
binary language, and the ambiguity has to be resolved before any code is written.

**Decision: one head per signal emitting three logits — `true`, `false`,
`null` — trained with cross-entropy.**

`add_encoder.md` section 4 sketches the alternative: a single sigmoid with
`p > 0.8 → true`, `p < 0.2 → false`, else `null`. That was reasonable when
written, but it gives `null` no training target of its own — you would have to
regress towards 0.5, which is unstable and makes the null band an artefact of
calibration rather than a learned category. `null` is 60% of the dataset and
contains five deliberately-separated hard sub-classes that exist precisely
because they are *learnable distinctions*. It earns a class.

The instinct behind `add_encoder.md` section 4 is still right about one thing,
and it moves rather than disappears: **the decision rule is separate from the
head, and it is not plain argmax** (section 6.5).

### 3.2 Two arms: frozen probe first, then fine-tune

Both `Fine_tuning_plan.md` section 0 and `add_encoder.md` section 2 describe a
*frozen* encoder with trained heads. `add_encoder.md` section 6 then says
"fine-tune ClinicalBERT". These are different experiments with very different
expected results, and the plan runs both:

* **Arm A — frozen encoder, linear probe.** Run Bio_ClinicalBERT once over all
  14,000 examples, cache the pooled embeddings to disk (~43MB as float32), train
  a 2,307-parameter head on them. Seconds per training run, so experimentation
  is effectively free.
* **Arm B — fine-tune.** Unfreeze the encoder and train end-to-end. ~940 steps
  at batch 32 for 3 epochs, which on the target hardware (RTX 5070, 12GB) is
  roughly two minutes.

**The hardware is not a constraint here, and that is worth saying explicitly
because it removes a whole category of decisions.** BERT-base fine-tuning at
batch 32 / seq 256 needs about 1.8GB for parameters, gradients and AdamW state,
plus a couple of GB of activations — call it 5GB against 12GB available. No
gradient checkpointing, no 8-bit optimiser, no LoRA, no gradient accumulation.
Batch 64 also fits comfortably if we want it. Anything in this plan that reads
like a compute compromise should be treated as a mistake.

Arm A is built first because it exercises every piece of plumbing — loader,
label masking, metrics, threshold selection, artefact writing — at a cost where
mistakes are cheap to find. It is a baseline, not the answer.

**Honest expectation about Arm A:** a linear probe on a frozen sentence
embedding will do well on clear positives, clear negatives and
`null_structural`, and poorly on the hard null sub-classes. Third-party
attribution ("my son has a fever"), tense ("I had one last month") and metaphor
("hay fever") all require compositional scope reasoning, and a single pooled
vector tends to blur exactly that. **This is why Arm B is not optional:** if we
built only Arm A and it scored badly on the hard cases, we could not distinguish
"the data is bad" from "the method is too weak", which is the one question the
ticket is for.

### 3.3 Mean pooling, not CLS

`download_clinicalBERT.md` step 6 uses the CLS token. That is the right thing
for a smoke test but generally the weaker choice for a frozen probe — BERT's CLS
representation was shaped by next-sentence prediction, not by sentence
similarity. **Decision: attention-mask-weighted mean pooling as the default, CLS
available as a config flag** so the two can be compared once rather than argued
about. Whichever is used is recorded in the artefact sidecar, because
`add_encoder.md` section 7 requires the pooling to be fixed and versioned.

---

## 4. Where the code lives

`scripts/encoder_training/`, mirroring `scripts/synthetic_data/` — offline
tooling, invoked as `python -m scripts.encoder_training`, never imported by
`app/`. Proposed shape:

| File | Responsibility | Needs torch? |
|---|---|---|
| `dataset.py` | Read JSONL + stats sidecar; build label tensors and the per-signal mask; assert split disjointness | No |
| `metrics.py` | Confusion matrices, per-class P/R/F1, sub-class slicing, threshold sweep | No |
| `baselines.py` | Majority-class, length-only, TF-IDF + logistic regression | sklearn |
| `embed.py` | Frozen embedding cache (Arm A) | Yes |
| `model.py` | Encoder wrapper + 3-way heads | Yes |
| `train.py` | Training loop for both arms | Yes |
| `report.py` | Write the JSON + markdown evaluation report | No |
| `__main__.py` | CLI | — |

**`dataset.py` and `metrics.py` are stdlib-only and that is a deliberate
constraint.** It means the loader logic and every metric can be unit-tested in
the existing CI `unit` job against fixtures, with no torch install and no GPU.
Hand-writing a confusion matrix and per-class F1 is thirty lines; importing
sklearn for it would push the most correctness-critical code in the ticket
outside what CI can check. Training itself never runs in CI.

### 4.1 Dependencies must not reach production

`torch` and `transformers` go in a new **`requirements-ml.txt`**, offline-only,
and never in `requirements.txt`. `requirements.txt` is what the Dockerfile
installs and what the Trivy scan in `security-scan.yml` gates on; adding ~2GB of
ML dependencies to the production image for code that does not run in production
would be a straightforward mistake.

This mirrors the containment `scripts/synthetic_data` already has — stdlib only,
never imported by `app/` — and it should get the same guard: a test asserting
that nothing under `app/` imports `scripts.encoder_training`.

**The RTX 5070 is Blackwell (compute capability `sm_120`), and this is the single
most likely thing in the ticket to eat an afternoon.** Blackwell needs a PyTorch
build against CUDA 12.8 or later; an older wheel will install and import
perfectly happily and then fail at the first kernel launch with `no kernel image
is available for execution on the device`. So `requirements-ml.txt` must pin the
torch version *and* record which CUDA index it came from
(`--index-url https://download.pytorch.org/whl/cu128` or later), because a bare
`pip install torch` may resolve to a wheel that cannot run on this GPU.

The first task of Arm B is therefore a smoke test in the spirit of
`download_clinicalBERT.md`, with one addition: **`torch.cuda.is_available()`
returning `True` does not prove anything.** It can report `True` on an
unsupported architecture, right up until a kernel actually launches. The check
has to run a real matmul on the device and print
`torch.version.cuda` alongside `torch.cuda.get_device_capability(0)` — expected
`(12, 0)`.

### 4.2 Artefacts

Proposed `models/encoder/fever_present/` holding the head weights and a JSON
sidecar. Arm A's head is ~2.3K parameters and can be committed. **Arm B's
fine-tuned encoder is ~440MB and must not be** — where it lives (GitHub release
asset, object storage, or regenerate-on-demand) is an open question in section
10, not something to decide by accident.

The sidecar is what later populates `model_name`, `model_version` and
`ruleset_hash` in `EncoderOutput`, so it needs, at minimum: base model ID **and
pinned HF revision SHA** (the bare name `emilyalsentzer/Bio_ClinicalBERT` can
move under us), tokenizer casing behaviour, pooling mode, `max_seq_len`,
training config, seeds, the dataset seed and `generator_version`, the ruleset
hash, the chosen decision thresholds, and the eval numbers the thresholds were
chosen from.

---

## 5. Step zero: the dataset is not on disk

`data/synthetic/generated/` is git-ignored and does not exist in a fresh clone.
Not a problem — it is exactly reproducible from the libraries plus a seed, which
is why it is ignored — but the first task regenerates all three splits and
records the seed used, because every number this ticket produces is relative to
that specific dataset.

```
python -m scripts.synthetic_data --split train --count 10000 --out data/synthetic/generated/fever_present.train.jsonl
python -m scripts.synthetic_data --split val   --count 2000  --out data/synthetic/generated/fever_present.val.jsonl
python -m scripts.synthetic_data --split test  --count 2000  --out data/synthetic/generated/fever_present.test.jsonl
```

The loader should read the `.stats.json` sidecar alongside each dataset and fail
if `generator_version` differs between splits — three splits from two different
generator versions is a silent way to get an uninterpretable result.

---

## 6. The training component

### 6.1 Sequence length

Bio_ClinicalBERT tops out at 512 positions. The proof-of-concept run has a median
of 36 tokens and a 90th percentile of 54, so **256 is proposed** — ample
headroom, half the compute of 512.

Worth stating plainly: this parameter is not the interesting constraint. Training
on 36-token recombinations and eventually serving 300-token real submissions is a
distribution shift that no `max_seq_len` setting fixes. It is the "examples are
still short" problem of `arch_training.md` section 9, and section 9 is right that
the fix is library work.

### 6.2 Tokenisation and casing

Bio_ClinicalBERT descends from BioBERT and therefore from `bert-base-cased`, so
casing is probably signal-bearing. `arch_training.md` section 5 already
preserves original casing, spelling and typos verbatim, which lines up well —
but the tokeniser's actual `do_lower_case` should be checked at load time and
recorded in the sidecar rather than assumed.

### 6.3 Class balance: leave the loss alone, move the thresholds

The dataset is 15% `true` / 25% `false` / 60% `null`. The temptation is class
weighting.

**Recommendation: train unweighted.** That 15/25/60 mix is a generator flag, not
a measured prior over real submissions — reweighting the loss to "correct" it
means correcting towards a second arbitrary target while making the model harder
to reason about. The place to express our actual asymmetric preference is the
decision rule (section 6.5), which is tunable, documented, and something the
encoder contract needs regardless.

### 6.4 Masked loss, written now, exercised by fixtures

Per `arch_training.md` section 7: a **missing** signal key means "this dataset
says nothing about this signal — exclude it from the loss"; an explicit `null`
means "train towards the null class". Conflating them would teach every head to
answer "not mentioned" to every question it was not specifically trained on.

With one signal there is never a missing key, so the masking path gets no
coverage from real data and needs a synthetic unit test. Writing it now costs
almost nothing; discovering it was wrong after multi-head training starts costs
a great deal.

### 6.5 The decision rule is a separate artefact

The head emits three logits. The encoder boundary permits only
`True | False | None` — `arch_encoder.md` and `phase_3.md` section 3.4 are
explicit that probabilities stay inside the encoder module and die there. So a
decision rule converts logits to a boolean-or-null, and it is a tuned,
versioned artefact in its own right.

**It should not be plain argmax.** Encoder output is advisory and the patient
confirms it, but a fabricated `true` arrives pre-filled in the patient's form and
acquiescence is real; a wrongly-confident `false` on a question feeding a safety
rule is worse still. A margin threshold — predict `true`/`false` only when that
class clears `null` by some margin, otherwise emit `null` — expresses the
asymmetry we actually want, and gives us one honest knob.

The margin is chosen on validation, recorded in the sidecar, and reported with
the numbers it was chosen from.

### 6.6 Determinism

Fixed seeds for Python, numpy and torch; `torch.use_deterministic_algorithms`
where it does not break an op we need. On CUDA that also requires
`CUBLAS_WORKSPACE_CONFIG=:4096:8` in the environment, or the deterministic flag
raises rather than silently doing nothing — the CLI should set it itself rather
than rely on a shell export someone forgets.

**Train in fp32, not bf16.** Blackwell has strong bf16 and it would roughly halve
the step time, but a two-minute training run has no speed problem to solve, and
reduced precision buys that speedup with numerical noise in exactly the metrics
we are trying to read carefully. At this scale, spend the hardware on
reproducibility instead. If some later run genuinely needs the throughput, bf16
becomes a recorded config flag rather than a silent default.

Honest limit: bitwise reproducibility across machines and across CPU/GPU is not
achievable and should not be claimed. The target is run-to-run reproducibility
on one machine, plus every number recorded in the sidecar so a rerun can be
compared rather than trusted.

---

## 7. Evaluation — the actual deliverable

### 7.1 Accuracy is not a metric here

`null` is 60% of the data. A model that answers `null` to everything scores 60%
and has learned nothing. Report instead:

1. **Full 3×3 confusion matrix**, and two cells called out by name: `null → true`
   (inventing a symptom into a patient's form) and `false → true` / `true → false`
   (flipping a patient's meaning).
2. **Per-class precision, recall, F1.**
3. **Recall on `null`, broken out by sub-class** — `hedged`, `metaphor`,
   `thirdparty`, `historical`, `attribution`, and `null_structural` separately.
   This is the single most valuable table the ticket produces, and it is the
   reason those libraries are five separate files rather than one
   (`arch_training.md` section 3). The slicing reads `meta.fragment_subclasses`
   from the JSONL. `attribution` is the row to read first: it is the sub-class
   where every surface cue points at a positive, so it is where a model that
   learned "first person + present tense + heat word" will show itself.
4. **Calibration on `null`** — `Fine_tuning_plan.md` section 4.2 is right that if
   null collapses, the safety boundary goes with it.

### 7.2 Baselines, which are the point of comparison

| Baseline | What it tells us |
|---|---|
| Majority class (always `null`) | The floor. ~60%. |
| Length-only logistic regression | Whether the length leak of `arch_training.md` section 9 is *measurably* exploitable, rather than hypothetically. |
| TF-IDF + logistic regression | Whether the dataset is keyword-solvable. |

**The bag-of-words baseline is the most informative twenty lines in this
ticket.** It should do well on clear positives, negatives and
`null_structural`, and badly on the ambiguous sub-classes. So the number that
matters is not "does ClinicalBERT beat BoW overall" — it is **"does ClinicalBERT
beat BoW on the `null_ambiguous` slice"**. That difference, and only that
difference, is the transformer earning its keep.

### 7.3 Negative controls

Cheap, and they are what makes the primary numbers believable:

* **Shuffled-label control.** Train the identical head on randomly permuted
  labels. It must land at chance. If it does not, something leaks in the loader
  or the split and every other number is void.
* **Fragment disjointness assertion.** Verify no `fragment_id` appears in two
  splits. The generator guarantees this and `test_synthetic_recombination.py`
  covers it — but the entire meaning of the validation score rests on the
  guarantee, so the training code should assert it rather than inherit it.

---

## 8. Validation discipline

Validation holds 15 distinct positive fragments. A hyperparameter search will
overfit that within a handful of trials while producing a rising, entirely
fictional score.

Proposed rules, to be written into the report:

* Sane defaults, chosen once, from published practice rather than from our
  validation set.
* A **hard cap on validation-guided decisions** — pooling mode, learning rate,
  epoch count, decision margin, and nothing else — with each one written down.
* **The test split is opened once**, at the end, and the number is reported
  whatever it is.

---

## 9. What this will and will not tell us

Following the pattern of `arch_training.md` section 9, because these numbers are
easy to over-read.

**It will tell us** whether the dataset teaches a model anything a keyword
matcher could not, and which specific hard sub-classes survive contact with a
real encoder. That is genuinely decision-useful: it points the next month at
either model work or library work.

**It will not tell us how the encoder will perform on real patient text.** The
test split is recombined from the same 300-odd hand-written fragments as the
training split, using the same joining logic and the same length profile. A good
test score means "the model learned our recombination task", which is a
necessary but weak precondition for reading real submissions.

**The only thing that would resemble evidence** is a small set of hand-written
realistic full submissions — 60 to 100, written deliberately unlike the
recombinations, labelled by hand — kept as a held-out set that no training
decision ever touches. That is cheap in code and expensive in careful thought,
it is the natural next ticket, and until it exists every number here should be
described as a smoke test.

---

## 10. Open questions for review

1. ~~**Fine-tuned weight storage.**~~ **Deferred to a separate follow-up
   ticket.** Arm B's ~440MB of weights stay on the local disk for the duration of
   this ticket, and durable storage — release asset, object storage, or
   regenerate-on-demand — is decided later. This is a comfortable deferral rather
   than a punt: training takes about two minutes from a pinned seed, so
   regenerate-on-demand is already a working answer, and the ticket's deliverable
   is the evaluation report rather than the weights. Nothing in this ticket
   depends on the outcome.
2. **Arm B unfreeze depth.** Partly resolved by the hardware: 12GB affords
   all-layers fine-tuning with room to spare, so **all-layers is the default**
   and top-N exists only as a comparison if all-layers proves unstable on 10k
   examples. Still worth agreeing before someone runs eight configurations
   against a 15-fragment validation set — see section 8.
3. **`models/` directory naming**, and whether it belongs at repo root alongside
   `data/` and `scripts/`.
4. **Does the report get committed?** A markdown eval report per run in git makes
   the history of what we learned durable; it also churns. Suggest committing the
   JSON sidecar always, the markdown report only for runs we want to keep.

**Drive-by observation, not in scope — separate follow-up ticket:**
`encoder_stub.py` emits `frequency_present`, but the ruleset's key is
`urinary_frequency_present`. The stub is only reached with definitions derived
from the ruleset, so the branch is dead rather than harmful — but it is the kind
of thing that becomes a real bug the moment someone copies the stub as a starting
point for the real encoder.

---

## 11. Proposed sequencing

Each step should leave something whose numbers can be trusted before the next
one starts.

1. **Regenerate the three splits** (section 5), record the seed.
2. **`dataset.py` + `metrics.py` + `baselines.py`, with unit tests.** No torch.
   Produces the baseline table and both negative controls. This is where most of
   the correctness risk lives, and it is the step that could already answer part
   of section 1's question.
3. **Arm A: frozen embedding cache + linear probe.** Exercises the full pipeline
   including artefact writing and threshold selection, at near-zero cost per run.
4. **Arm B: fine-tune.** Opens with the CUDA/Blackwell smoke test of section 4.1
   — prove a kernel launches on this GPU before writing a training loop that
   assumes one can. Then the arm that actually decides section 1.
5. **Compare, write the report, update `arch_encoder.md` and `file_structure.md`.**
   A new `arch_encoder_training.md` spoke plus an `architecture.md` capability
   index entry is probably warranted once there is a real component to document.

Steps 2 and 3 are one chat each. Step 4 is likely two — one to get it running,
one to get it honest.

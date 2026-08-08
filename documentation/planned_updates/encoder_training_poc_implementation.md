# Implementation Plan: Encoder training component and the first head

**Supersedes** `encoder_training_poc.md` (the provisional plan) on every point
where they disagree. That document remains the record of *why*; this one is the
record of *what to build*. Where it is silent, the provisional plan stands.

**Related:** `arch_training.md` (the dataset this consumes — sections 9 and 10,
including "Effective sample size", are prerequisites), `arch_encoder.md` (the
boundary a trained model eventually sits behind).

---

# Plan

Build offline tooling that reads the generated JSONL datasets, trains a 3-way
`fever_present` head on Bio_ClinicalBERT in two arms (frozen probe, then
fine-tune), compares both against baselines, and produces an evaluation report
whose numbers carry honest error bars.

The ticket exists to answer one question: **is the bottleneck the model or the
fragment libraries?** Everything below is arranged to make that comparison
legible, and the single largest change from the provisional plan is that the
comparison is now made across **five fragment folds** rather than one split.

## Why folds, and why this is the load-bearing change

The provisional plan named the per-sub-class null recall table as its most
valuable output. Against the current single split, that table is computed from
these test-split counts:

| Sub-class | test fragments | **test clusters** |
|---|---|---|
| `hedged` | 2 | **2** |
| `historical` | 3 | **3** |
| `metaphor` | 5 | **5** |
| `third_party` | 2 | **2** |

**Count clusters, not fragments.** The splitter hashes cluster keys, so
`[c01]`-tagged siblings always travel together and are not independent
observations. Fragments and clusters happen to coincide in the test split
above, but they do not in general — the validation split holds 3 `hedged`
fragments in only 2 clusters, and 7 `third_party` fragments in only 5.

A recall figure over 2 clusters can only be 0, 0.5 or 1.0. All four hard
sub-classes together are 12 clusters. The uncertainty on any such number is
roughly ±30 points — wider than any effect the ticket could plausibly detect,
so as specified the ticket could not answer its own question.

Five-fold cross-validation over fragment clusters fixes this for about ten
minutes of GPU time. Every cluster becomes a test cluster in exactly one fold,
so the aggregate slice sizes become the whole library:

| Sub-class | fragments | **clusters (the effective n)** |
|---|---|---|
| `hedged` | 42 | **32** |
| `historical` | 45 | **36** |
| `metaphor` | 55 | **47** |
| `third_party` | 46 | **35** |

That is a 12- to 17-fold improvement in the only quantity that matters, and it
costs one flag on the generator plus a loop. It does not create new ideas — 47
metaphor clusters is still 47 — so section 9 of `arch_training.md` continues to
apply in full.

---

# Scope

**In scope.** A `--folds`/`--fold` mode on the existing generator; a new
`scripts/encoder_training/` package; Arm A (frozen probe) and Arm B (fine-tune);
baselines; negative controls; fold-aggregated evaluation report with
per-fragment error analysis; artefact writing with a metadata sidecar.

**Out of scope, deliberately.** All four exclusions from the provisional plan
stand and are not revisited here: replacing `encoder_stub.py`; multi-signal /
multi-head training; a realistic hand-written held-out evaluation set;
hyperparameter search.

Two additions to the out-of-scope list, both discovered during review:

* **Durable storage for Arm B weights.** Deferred, as before. Weights stay on
  local disk for the duration of the ticket.
* **Making the trained head satisfy `EncoderOutput`.**
  `EncoderOutput.validate_against` (`app/models/encoder_contracts.py:41`)
  requires output keys to match the supplied definitions *exactly*, and
  `data/uti1.json` declares seven `send_to_encoder` signals. A single fever head
  therefore cannot satisfy the contract at all. This is correctly out of scope,
  but it means "swap in the real encoder" stays blocked until either all seven
  heads exist or the contract is changed to permit partial output. Recorded here
  so the constraint is visible before someone plans around it.

---

# Design Decisions

## DD1: Three-way softmax head, not a binary head with bands

Carried unchanged from the provisional plan section 3.1. One head per signal
emitting three logits (`true`, `false`, `null`), trained with cross-entropy.
`null` is 60% of the data and contains four deliberately-separated learnable
sub-classes; it earns a class rather than a calibration band.

## DD2: Two arms, Arm A first

Carried unchanged from provisional section 3.2. Arm A (frozen encoder, linear
probe over cached embeddings) exercises every piece of plumbing at near-zero
cost per run. Arm B (full fine-tune, all layers) is what actually decides the
ticket's question. Building only Arm A would leave "the data is bad" and "the
method is too weak" indistinguishable.

## DD3: Mean pooling default, CLS behind a flag

Carried unchanged from provisional section 3.3. Attention-mask-weighted mean
pooling is the default; CLS is a config flag so the two get compared once rather
than argued about. Whichever ran is recorded in the sidecar.

## DD4: Five-fold cross-validation over fragment clusters is the primary result

**New, and the reason this plan differs from the provisional one.** See "Why
folds" above.

Fold assignment reuses the existing cluster-aware machinery in
`scripts/synthetic_data/manifest.py`: `assign_split` already hashes a *cluster
key* rather than raw text, so template siblings and hand-tagged `[c01]` pairs
already travel together. Fold mode changes only which band the hash maps to.

**The legacy 70/15/15 split remains the default and stays byte-identical.** Fold
mode is opt-in. A fold's train share is 60% rather than 70%, so fold numbers are
*not* directly comparable to any figure recorded in `arch_training.md` section
10 — the fold-aggregated numbers are the honest ones and the report leads with
them.

## DD5: Every reported number carries an error bar, and the unit of resampling is the fragment

Three mechanisms, all stdlib:

1. **Across folds:** mean and sample standard deviation over the five folds.
2. **Within a fold:** bootstrap confidence intervals that resample **decisive
   clusters**, not examples. Resampling examples would report the noise of a
   recombination process rather than the noise that matters, and would produce
   confidence intervals roughly √(examples/clusters) too narrow.
3. **Between models:** a paired McNemar test on identical examples. "Does
   ClinicalBERT beat bag-of-words on `null_ambiguous`" is a paired question and
   must not be answered by eyeballing two independent point estimates.

**Every slice in the report prints its effective n — the number of distinct
decisive clusters behind it — next to its example count.** This is not a
nicety. It is the single guard against the failure mode `arch_training.md`
section 10 now names explicitly.

The unit is the **cluster**, not the fragment. `[c01]`-tagged siblings are the
same idea written twice and are not independent observations; the splitter
already treats them as one unit and the statistics must too. Across the fever
libraries this matters most where it hurts most: `fever_null_thirdparty` is 46
fragments but 35 clusters, and `fever_null_hedged` is 42 fragments but 32.

## DD6: Slice on `fragment_ids`, not `fragment_subclasses`

The provisional plan section 7.1 proposed slicing on `meta.fragment_subclasses`.
That is insufficient: the manifest only sets `subclass` on ambiguous and
confounder libraries, so `fever_true`, `fever_false` and all five filler
libraries come through as `None` and are indistinguishable from each other.

`meta.fragment_ids` are `{library}:{hash}` (`recombine.py:534`), which yields
both the library *and* the individual fragment. Slice on that. It also unlocks
DD7 for free.

## DD7: The per-fragment error table is a first-class deliverable

For every decisive fragment appearing in any test fold, report how often the
model got its examples right. This is more decision-useful than any slice
accuracy, and it is what actually answers the ticket's question:

* Errors spread thinly across many fragments → the method is too weak → model
  work.
* Errors concentrated on a handful of identifiable fragments → those specific
  ideas are unlearnable from the data we have → library work, and we know
  exactly which fragments to write more of.

A slice accuracy of 40% does not distinguish these. The table does.

## DD8: Train unweighted; express asymmetry in the decision rule

Carried unchanged from provisional section 6.3. The 15/25/60 mix is a generator
flag, not a measured prior over real submissions. Reweighting the loss corrects
towards a second arbitrary target. The asymmetry we actually care about lives in
the decision rule, which is tunable, versioned and documented.

## DD9: The decision rule is a separate artefact, and both matrices are reported

Carried from provisional section 6.5, with two additions:

* **The report prints the confusion matrix twice — raw argmax and
  post-decision-rule.** Otherwise "the model is wrong" and "the rule is
  conservative" are inseparable.
* **The margin selection objective is stated, not implied.** Choose the margin
  that maximises macro-F1 subject to a `null → true` rate no worse than argmax's.
  `null → true` is the cell that invents a symptom into a patient's pre-filled
  form; the rule exists to protect it, so it is a constraint, not a term.

The margin is selected on each fold's own validation split, never across folds.

## DD10: Masked loss written now, exercised by fixtures

Carried unchanged from provisional section 6.4. A **missing** signal key means
"exclude from the loss"; an explicit `null` means "train towards the null
class". With one signal there is never a missing key, so this path gets no
coverage from real data and needs a synthetic unit test. Conflating the two
after multi-head training starts is expensive; writing the test now is nearly
free.

## DD11: fp32, fixed seeds, honest reproducibility claims

Carried unchanged from provisional section 6.6. A two-minute run has no speed
problem worth buying with numerical noise in the metrics we are trying to read
carefully. `CUBLAS_WORKSPACE_CONFIG=:4096:8` is set by the CLI itself rather
than left to a shell export. The target is run-to-run reproducibility on one
machine; bitwise reproducibility across machines is not claimed.

## DD12: ML dependencies never reach production

Carried from provisional section 4.1, with corrections found during review:

* `torch`, `transformers` **and `scikit-learn`** go in `requirements-ml.txt`.
  The provisional plan named only the first two but section 4's table needs
  sklearn for `baselines.py`.
* **Pin Python 3.12**, matching the CI `unit` job and the repo's existing floor
  (`recombine.py:291` uses PEP 695 generics, so 3.12+ is already required).
  torch cu128 wheels are reliable on 3.12 and patchier on 3.13/3.14.
* The Blackwell warning stands and is the single most likely thing here to eat
  an afternoon: RTX 5070 is `sm_120`, needs a wheel built against CUDA 12.8+,
  and an older wheel installs and imports happily before failing at the first
  kernel launch. Record the index URL in the requirements file.

## DD13: `models/` at repo root is safe, but add a `.dockerignore`

This closes provisional open question 3. The Dockerfile uses explicit
`COPY app/ …`, `COPY data/ …` rather than `COPY . .`, so a root-level `models/`
never enters the production image.

However `COPY data/ ./data/` copies `data/` wholesale, there is no
`.dockerignore` in the repo, and `data/synthetic/generated/` is only
git-ignored. A local build after a generation run would bake ~40MB of training
JSONL into the production image. Add a `.dockerignore` covering
`data/synthetic/generated/` and `models/` as part of Task 6.

## DD14: The embedding cache is keyed on everything that invalidates it

The Arm A cache filename must encode: base model revision SHA, pooling mode,
`max_seq_len`, dataset seed, `generator_version`, and fold index. A stale cache
silently produces numbers that look fine and mean nothing. Putting the key in
the filename rather than a manifest means it cannot drift from what it labels.

## DD15: `ruleset_hash` is duplicated, not imported

The sidecar needs a ruleset hash (it eventually populates `EncoderOutput`), but
`ruleset_hash()` lives in `app/services/engine/ruleset.py:83` and
`scripts/synthetic_data/ruleset.py` carries an explicit documented decision not
to import from `app/`. Offline tooling must not couple to runtime wiring.

**Decision: duplicate the three-line function in `scripts/encoder_training/`**
and add a unit test asserting the two implementations agree on
`data/uti1.json`. A test that catches divergence is cheaper than a coupling that
prevents it.

Worth knowing when reading the sidecar: `ruleset_hash` covers the *whole*
ruleset dict, so editing any unrelated question invalidates the fever model's
recorded hash. That is the right conservative default; it is recorded here so
nobody reads a changed hash as a changed fever definition.

---

# Task 1: Fold-aware splitting in the generator

**A. State of the world.** The generator, its tests and its lint are complete
and merged; the proof-of-concept run produces output. Nothing in this plan has
been built. This task is the only change to `scripts/synthetic_data/`, and
everything downstream depends on it.

**B. Files and deliverables.**

| File | Change |
|---|---|
| `scripts/synthetic_data/manifest.py` | `assign_split` gains fold mode and a salt; `load_fragments` threads them through |
| `scripts/synthetic_data/__main__.py` | `--folds` and `--fold` CLI flags |
| `scripts/synthetic_data/recombine.py` | `build_stats` records fold config in the sidecar |
| `tests/test_synthetic_recombination.py` | New tests per C below |
| `documentation/arch_training.md` | Document fold mode in sections 6 and 11 |

Deliverable: `python -m scripts.synthetic_data --folds 5 --fold 0 --split test …`
generates a dataset whose test fragments are disjoint from the other four folds'
test fragments, and the default invocation produces byte-identical output to
today's.

**C. Instructions.**

1. Change `assign_split(cluster_key)` to
   `assign_split(cluster_key, *, folds=None, fold_index=0, salt="")`. Hash
   `f"{salt}:{cluster_key}"` when a salt is set, and the bare cluster key when
   it is not — an empty salt must reproduce the current digest exactly, because
   the existing datasets and every number in `arch_training.md` section 10
   depend on it.
2. With `folds=None`, keep the current 70/15/15 band logic untouched.
3. With `folds=K`, compute `bucket = digest % K` and assign: `test` when
   `bucket == fold_index`, `val` when `bucket == (fold_index + 1) % K`,
   `train` otherwise. At `K=5` that is 60/20/20 and every cluster is a test
   cluster in exactly one fold.
4. Thread `folds`, `fold_index` and `salt` through `load_fragments` to the CLI.
   Add `--folds` (int, default None) and `--fold` (int, default 0); reject
   `--fold` without `--folds`, and `--fold` outside `[0, folds)`.
5. **Handle the empty-cell guard, which will bite.** `check_no_empty_cells`
   runs over the *whole manifest* before `build_pools` filters by signal, so a
   flank_pain or dysuria cell emptied by an unlucky fold assignment blocks a
   fever run. The binding constraints are `dysuria_null_thirdparty` (7
   clusters) and `dysuria_null_hedged` (8) — both must populate all 5 buckets.
   Do **not** weaken the guard. Instead add `--find-fold-salt`, which searches
   integer salts from 0 upward and prints those that leave every library with
   every bucket populated. It is a lint-speed operation (no generation), so an
   exhaustive search to 1000 is free.
6. **Use salt `"32"`.** This search has already been run: at `K=5`, the salts
   satisfying the full-manifest guard are `32`, `136`, `179`, `266`, `291`
   (roughly 1 in 400, because the two 7- and 8-cluster dysuria libraries have to
   surject onto 5 buckets). Every later task uses `32`. Record it in this
   document, in the task 2 fixtures and in every sidecar. Implement
   `--find-fold-salt` anyway — it will be needed again the moment a library
   grows, and rediscovering the constraint by hand is worse than a flag.
   Note that if the fever libraries were the only constraint almost any salt
   would do; the requirement comes entirely from the unrelated seed libraries,
   which is worth knowing before someone "fixes" it by editing dysuria.
7. `build_stats` records `folds`, `fold_index` and `split_salt` in the sidecar.
   A dataset whose fold configuration is not recorded is uninterpretable.
8. Tests: (a) default invocation is byte-identical to a committed golden hash;
   (b) across `fold in range(5)`, every cluster key appears in `test` exactly
   once; (c) train/val/test fragment sets are disjoint within each fold;
   (d) `--fold` without `--folds` exits non-zero; (e) a salt that empties a cell
   still raises.

---

# Task 2: `dataset.py` and `metrics.py` — stdlib only, fully unit-tested

**A. State of the world.** Task 1 is complete: the generator can emit folds and
a salt has been chosen. No training code exists yet. This task builds the two
modules where most of the correctness risk lives, and deliberately builds them
without torch so the CI `unit` job can test every line.

**B. Files and deliverables.**

| File | Responsibility |
|---|---|
| `scripts/encoder_training/__init__.py` | Empty |
| `scripts/encoder_training/dataset.py` | Read JSONL + stats sidecar; label tensors as plain lists; per-signal mask; split disjointness assertion |
| `scripts/encoder_training/metrics.py` | Confusion matrix, per-class P/R/F1, slicing, effective n, bootstrap CI, McNemar, threshold sweep |
| `scripts/encoder_training/ruleset_hash.py` | Duplicated hash + parity test (DD15) |
| `tests/test_encoder_training_dataset.py` | New |
| `tests/test_encoder_training_metrics.py` | New |
| `tests/fixtures/encoder_training/` | Small hand-built JSONL fixtures |

Deliverable: `pytest tests/test_encoder_training_*.py` passes with no torch and
no GPU, and `ruff` is clean.

**C. Instructions.**

1. `dataset.py` loads a split's JSONL and its `.stats.json` sidecar together.
   **Fail loudly** if `generator_version` differs between the three splits of a
   fold, or if `folds`/`fold_index`/`split_salt` are inconsistent — three splits
   from two generator versions is a silent route to an uninterpretable result.
2. Represent labels as `0/1/2` for `false`/`true`/`null` plus a boolean mask per
   signal. **A missing signal key sets mask `False`; an explicit `null` sets
   mask `True` and class `null`** (DD10). Write the fixture for the missing-key
   case by hand — the generator will never produce one with a single signal.
3. Expose the decisive fragment for each example, derived from
   `meta.fragment_ids` by taking the id whose library prefix is not a filler
   library (DD6). Structural nulls have none; return `None`. Expose the library
   name and the subclass alongside it.
4. Assert fragment-level split disjointness at load time — no `fragment_id`
   appears in two splits of the same fold. The generator guarantees this and
   `test_synthetic_recombination.py` covers it, but the entire meaning of the
   evaluation rests on it, so the training code asserts rather than inherits.
5. `metrics.py`, all stdlib, roughly thirty lines each: 3×3 confusion matrix;
   per-class precision/recall/F1; macro-F1; slicing by label mode, by library
   and by subclass.
6. Every slice result carries **both** an example count and an effective n —
   the number of distinct decisive **clusters** in that slice, falling back to
   the fragment when it carries no cluster tag (DD5).
7. Bootstrap CI that resamples **decisive clusters** with replacement, then
   takes all examples belonging to the sampled clusters. Structural nulls form
   their own resampling unit. 2000 resamples, seeded. Resampling fragments
   rather than clusters would treat `[c01]` siblings as independent and report
   intervals that are too narrow.
8. McNemar's exact test on paired predictions: count discordant pairs, use a
   two-sided exact binomial from `math.comb`. No scipy.
9. Threshold sweep: for a grid of margins, return the full metric set so the
   DD9 objective can be applied by the caller. `metrics.py` computes; it does
   not choose.
10. `ruleset_hash.py` duplicates `app/services/engine/ruleset.py:83`, with a
    test asserting both produce the same digest for `data/uti1.json`.
11. Add a test asserting nothing under `app/` imports `scripts.encoder_training`
    — mirroring the containment guard `scripts/synthetic_data` already has.

---

# Task 3: Baselines, negative controls and the report writer

**A. State of the world.** Tasks 1 and 2 are complete: folds exist, and the
loader and every metric are unit-tested without torch. Still no torch code. This
task produces the first real numbers, and they are the comparison point that
the whole ticket is judged against.

**B. Files and deliverables.**

| File | Responsibility |
|---|---|
| `scripts/encoder_training/baselines.py` | Majority-class, length-only, TF-IDF + logistic regression |
| `scripts/encoder_training/report.py` | JSON + markdown report writer |
| `scripts/encoder_training/__main__.py` | CLI, `baselines` subcommand |
| `requirements-ml.txt` | New: sklearn now, torch/transformers in task 5 |
| `tests/test_encoder_training_baselines.py` | New |

Deliverable: a baseline table across all five folds, with error bars, plus both
negative controls, written to `reports/encoder_training/`.

**C. Instructions.**

1. Generate all five folds' three splits (15 runs of the task 1 CLI, scripted).
   Record the generator seed and the fold salt in the report header.
2. Three baselines, each trained and evaluated per fold: majority class (always
   `null`, expected ~60%); length-only logistic regression on token count —
   this is the direct measurable test of `arch_training.md` section 9's length
   leak, which until now has only been argued; TF-IDF + logistic regression,
   which tests whether the dataset is keyword-solvable.
3. Report every metric from DD5 for each baseline: full 3×3 matrix, per-class
   P/R/F1, the null sub-class breakdown with effective n, and bootstrap CIs.
4. **Negative control 1 — shuffled labels.** Permute the labels **of the train
   split only**, train the identical model, and evaluate on the **unpermuted
   test split**, where it must land at chance. Getting this wrong is a real
   trap: at Arm B a 110M-parameter model will memorise permuted train labels and
   drive train loss to zero, which is correct behaviour and looks like failure
   if you evaluate on train. Wire the control this way now so Arm B inherits it.
5. **Negative control 2 — fragment disjointness**, already asserted in task 2;
   the report states it was checked rather than assuming it.
6. `report.py` writes a JSON sidecar (always) and a markdown report (on request).
   The markdown leads with the fold-aggregated table; per-fold numbers go in an
   appendix.
7. The report template must include the per-fragment error table (DD7) even
   though only baselines populate it at this stage.
8. Note in the report that the TF-IDF baseline is expected to do well on clear
   positives, negatives and `null_structural`, and badly on the ambiguous
   sub-classes. **The number that matters is the `null_ambiguous` slice, tested
   with McNemar against the transformer in task 6** — not the overall accuracy.

---

# Task 4: Arm A — frozen embedding cache and linear probe

**A. State of the world.** Tasks 1–3 are complete: folds, a tested loader, every
metric, three baselines with error bars, and a report writer. This is the first
task that needs torch. It exercises the full training pipeline — embedding,
head, threshold selection, artefact writing — at seconds per run, so that
mistakes are found somewhere cheap.

**B. Files and deliverables.**

| File | Responsibility |
|---|---|
| `scripts/encoder_training/embed.py` | Frozen embedding cache |
| `scripts/encoder_training/model.py` | Encoder wrapper + 3-way head |
| `scripts/encoder_training/train.py` | Training loop, probe path |
| `requirements-ml.txt` | Add torch + transformers, pinned, with index URL |
| `models/encoder/fever_present/` | Head weights + sidecar (committable at ~2.3K params) |

Deliverable: Arm A numbers across five folds, in the same report format as the
baselines.

**C. Instructions.**

1. Pin the base model by **revision SHA**, not the bare name
   `emilyalsentzer/Bio_ClinicalBERT`, which can move. Record the SHA in the
   sidecar.
2. Check the tokeniser's actual `do_lower_case` at load time and record it
   rather than assuming. Bio_ClinicalBERT descends from `bert-base-cased`, so
   casing is probably signal-bearing, and `arch_training.md` section 5
   preserves original casing verbatim.
3. `max_seq_len = 256`. The PoC run's median is 36 tokens and 90th percentile
   54, so this is ample headroom at half the compute of 512. State plainly in
   the report that this parameter is not the interesting constraint —
   training on 36-token recombinations and eventually serving 300-token real
   submissions is a distribution shift no sequence length fixes.
4. Attention-mask-weighted mean pooling as default, CLS behind a flag (DD3).
5. Cache embeddings to disk keyed per DD14. Five folds × 14,000 examples ×
   768 floats × 4 bytes ≈ 215MB total. Verify the cache key changes when
   pooling mode changes — a test worth writing, because the failure is silent.
6. Head: `Linear(768, 3)`, 2,307 parameters. Cross-entropy with the DD10 mask.
7. Select the decision margin on each fold's own validation split using the
   DD9 objective. Record the margin and the validation numbers it was chosen
   from, per fold.
8. Write the sidecar with everything the provisional plan section 4.2 lists:
   base model ID and revision SHA, tokeniser casing, pooling mode,
   `max_seq_len`, training config, all seeds, dataset seed, `generator_version`,
   fold config and salt, `ruleset_hash`, chosen margins, and the eval numbers
   the margins came from.
9. Run the shuffled-label control from task 3 against the probe.
10. **Expect Arm A to do well on clear positives, clear negatives and
    `null_structural`, and poorly on the hard null sub-classes.** Third-party
    attribution, tense and metaphor all need compositional scope reasoning, and
    a single pooled vector blurs exactly that. A bad Arm A result on hard cases
    is the expected outcome, not a bug, and is precisely why Arm B is not
    optional.

---

# Task 5: Arm B — fine-tune (likely two chats)

**A. State of the world.** Tasks 1–4 are complete: the entire pipeline runs
end-to-end on a frozen encoder, with baselines and error bars for comparison.
Arm A's hard-case numbers are known. This task unfreezes the encoder, and it is
the arm that actually decides the ticket's question.

**B. Files and deliverables.**

| File | Change |
|---|---|
| `scripts/encoder_training/smoke_cuda.py` | New: Blackwell kernel-launch check |
| `scripts/encoder_training/train.py` | Fine-tune path |
| `scripts/encoder_training/__main__.py` | `finetune` subcommand |
| `models/encoder/fever_present/` | Sidecar only — **the ~440MB weights are not committed** |

Deliverable: Arm B numbers across five folds, same report format.

**C. Instructions.**

1. **Open with the CUDA smoke test, before writing a training loop that assumes
   a kernel launches.** `torch.cuda.is_available()` returning `True` proves
   nothing — it can report `True` on an unsupported architecture right up until
   a kernel actually runs. The check must execute a real matmul on the device
   and print `torch.version.cuda` alongside `torch.cuda.get_device_capability(0)`,
   expecting `(12, 0)`. If this fails, the fix is a torch wheel built against
   CUDA 12.8 or later (DD12), not a code change.
2. Unfreeze all layers. 12GB affords it comfortably: BERT-base at batch 32 /
   seq 256 needs ~1.8GB for parameters, gradients and AdamW state plus a couple
   of GB of activations, call it 5GB. **No gradient checkpointing, no 8-bit
   optimiser, no LoRA, no gradient accumulation.** Anything in the
   implementation that reads like a compute compromise is a mistake.
3. fp32, not bf16 (DD11). ~940 steps at batch 32 for 3 epochs, roughly two
   minutes per fold, ten minutes for all five.
4. Set `CUBLAS_WORKSPACE_CONFIG=:4096:8` from inside the CLI before importing
   torch, and enable `torch.use_deterministic_algorithms` where it does not
   break a needed op.
5. Defaults chosen once from published practice, **not from our validation
   set**: learning rate 2e-5, 3 epochs, linear warmup 10%, AdamW. The hard cap
   on validation-guided decisions is: pooling mode, learning rate, epoch count,
   decision margin. Nothing else. Write the list into the report.
6. Run the shuffled-label control, evaluated on the unpermuted test split per
   task 3 instruction 4. Expect near-zero train loss and chance test
   performance; that combination is the control passing.
7. Weights stay on local disk. The sidecar is committed; the weights are not.
   Regenerate-on-demand already works — two minutes from a pinned seed — so
   durable storage is a genuine deferral rather than a punt.
8. **The test split is opened once**, at the end, and the number is reported
   whatever it is. With folds this means: all five folds' test splits are
   evaluated in a single pass after every training decision is frozen.

---

# Task 6: Compare, report, document

**A. State of the world.** Tasks 1–5 are complete: baselines, Arm A and Arm B
all have fold-aggregated numbers with error bars, and every artefact carries a
sidecar. Nothing has been concluded yet. This task produces the actual
deliverable, which is the report rather than the weights.

**B. Files and deliverables.**

| File | Change |
|---|---|
| `reports/encoder_training/<date>.md` | The evaluation report |
| `documentation/arch_encoder_training.md` | New architecture spoke |
| `documentation/architecture.md` | Capability index entry |
| `documentation/file_structure.md` | New directories |
| `documentation/arch_training.md` | Fold mode, cross-referenced |
| `.dockerignore` | New (DD13) |

**C. Instructions.**

1. Run the paired McNemar comparison (DD5) between Arm B and TF-IDF **on the
   `null_ambiguous` slice specifically**, and between Arm B and Arm A on the
   same slice. That difference, and only that difference, is the transformer
   earning its keep.
2. Produce the per-fragment error table (DD7) and read it before writing any
   conclusion. It is what distinguishes "model too weak" from "these specific
   ideas are unlearnable from what we have".
3. Write the report against the provisional plan's recorded prediction —
   overall test accuracy 90%+, near-perfect on `null_structural` and clear
   positives and negatives, bag-of-words within a few points overall, the
   transformer's only real advantage on `null_ambiguous` and weakest there on
   metaphor and hay fever. **Report whether the prediction held.** A plan that
   records a prediction and then never scores it has wasted the prediction.
4. State the conclusion in the ticket's own terms: model bottleneck or library
   bottleneck, and what the next month should therefore contain.
5. Reproduce `arch_training.md` section 9 and the "Effective sample size"
   subsection in the report's limitations, in full rather than by reference.
   The report will be read on its own by someone who has not read the
   architecture docs, and every number in it is a smoke test.
6. Name the next ticket explicitly: **60–100 hand-written realistic full
   submissions, deliberately unlike the recombinations, labelled by hand, held
   out and never touched by a training decision.** It is cheap in code and
   expensive in careful thought, and until it exists nothing here resembles
   evidence about real patient text.
7. Add the `.dockerignore` per DD13, covering `data/synthetic/generated/` and
   `models/`.
8. Per provisional open question 4: commit the JSON sidecar always, the markdown
   report only for runs worth keeping.

---

# Follow-up tickets identified during review

Not in scope here; recorded so they are not lost.

1. **`encoder_stub.py` bugs.** Two, one of which is live. The dead one is known:
   the stub emits `frequency_present` where the ruleset key is
   `urinary_frequency_present`, so that branch is unreachable. The live one is
   worse: `if "no" in text` is a substring test, so `"now"`, `"not"`,
   `"nothing"` and `"know"` all match, and the stub returns `False` for
   essentially every signal on any realistic text — making the `elif` true-branch
   nearly unreachable regardless of key naming. Harmless while it is a
   placeholder; misleading the moment anyone quotes stub behaviour as a
   baseline or copies it as a starting point.
2. **Durable storage for fine-tuned weights** — release asset, object storage,
   or regenerate-on-demand.
3. **`EncoderOutput` partial-output contract** — see Scope. Blocks any real
   encoder until all seven heads exist or the contract changes.
4. **The realistic held-out evaluation set** — task 6 instruction 6. The single
   most valuable thing to build next.

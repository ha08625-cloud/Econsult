# Implementation Plan: Joint multi-head training and the real-text holdout

**Supersedes** the provisional plan in `joint_multi_head_training.md`, which is
kept for its verification record and its cost model. Where the two disagree,
this document is right — the provisional plan's arm design was reviewed against
the code and one comparison in it does not run. See DD1.

**Related:** `arch_training.md` (sections 7, 10 and 12.8 are prerequisites),
`arch_encoder_training.md` (sections 3, 4a, 5, 8 and 9),
`planned_updates/multi_symptom_training_expansion.md` (tickets 4 and 5),
`data/realistic/README.md` (the holdout's rules).

---

# Orientation for someone new to this

Six symptoms — fever, dysuria, urinary frequency, nocturia, flank pain,
haematuria — each have hand-written fragment libraries, each have a five-fold
generated dataset, and each have a fine-tuned `roberta-base` head trained on
2026-08-16. Six models, one question each. `arch_training.md` section 10 has the
results.

This ticket asks one encoder all six questions at once, and asks whether that
helps. The reason to want it is not the deployment shape — that stays blocked,
see DD8 — but a question nobody can currently answer: **does exposure to five
other symptoms' confounders make each symptom's answer better or worse?** The
"whose symptom is this / when did it happen / is this literal" skills the hard
`null` sub-classes test are not symptom-specific, so an encoder that has seen
them six times over may generalise better. Or the heads may interfere.

Two facts set what a good outcome looks like.

**The joint run adds no supervision to any head.** A dysuria example carries a
dysuria label and *no fever key at all* — which `dataset.py` reads as "mask this
head", not as "fever is null here". The fever head sees exactly the 10,000
labelled positions it saw before, in its 15/25/60 mix. What changes is that the
shared encoder is also being pulled by five other heads on text the fever head
never gets a gradient from. **The only mechanism by which this can help is
representational.** Anything that reads like "the model now learns that a dysuria
sentence means no fever" is describing ticket 6 (`arch_training.md` 12.5).

**The effect being looked for is small.** `arch_encoder_training.md` section 4a
puts the paired five-fold sensitivity at roughly 2–3 points. A result inside that
band is "no detectable effect", and that is a legitimate and likely outcome.

Alongside it, and cheap because the models are the same models, the six existing
signals get scored against 67 realistic submissions for the first time. That is
the only measurement in this project that speaks to real patient text. See DD9.

---

# Plan

Five tasks. The first four are code and can all be written while no GPU is busy;
the fifth is the sweep and the write-up.

1. **Task 1 — Holdout scoring.** `holdout.py`, wired into the fine-tune path
   after margin selection and test scoring.
2. **Task 2 — The merge tool.** Standard library, CI-covered: read six
   per-signal fold trees, write one merged tree with a valid sidecar.
3. **Task 3 — The joint training path.** Separate "which dataset" from "which
   heads"; per-head margins; one shared epoch-selection criterion.
4. **Task 4 — The report shape.** One comparison report per signal holding three
   arms, including making `compare_models` safe on unpairable arms.
5. **Task 5 — The sweep and the write-up.**

**Landing order is 1 → 2 → 3 → 4 → 5.** Task 1 first because it is small, it is
independent, and if it says the recombination numbers do not transfer at all then
tasks 2 to 5 are being run for a different reason than the one now on the table —
which is a decision the user should get to make before six hours of GPU, not
after.

---

# Scope

**In scope:** holdout scoring tooling; the merge tool; joint multi-head training
with per-head decision rules; the comparison report and the unpairable-arm fix;
the three-armed sweep across all six signals; the architecture-doc updates.

**Out of scope, deliberately:**

* **Label vectors and declared silence** (`arch_training.md` 12.5). The merge
  needs none of it — see DD3 — and attempting it here turns a two-week ticket
  into a two-month one.
* **Multi-symptom recombinations** (ticket 6). This is the thing that would
  actually put a dysuria sentence under a `fever_present: null` label. It is the
  right next ticket and it is not this one.
* **Splitting `expectations.txt`** and bumping `GENERATOR_VERSION`. See DD7.
* **`recent_uti_present`.** Still no libraries, still no head. See DD8.
* **Cluster-tagging the four untagged library sets** (ticket 7). Unchanged by
  anything here, and it still means those signals' absolute numbers are upper
  bounds.
* **Persisting per-example predictions in the report JSON.** Worth doing, not
  here. See DD2.
* **Deploying anything.** See DD8.

---

# Design Decisions

### DD1 — A1 vs A3 is the paired comparison; A2 is an unpaired volume control

This is the correction that reshapes the ticket. The provisional plan's DD3 named
**A3 vs A2** as "the answer", paired on McNemar. It cannot be, for two reasons.

**It does not run.** `metrics.mcnemar` (`metrics.py:527`) raises `MetricsError`
when the two sides' example-id sets differ, and `report.compare_models`
(`report.py:637`) runs McNemar between every pair of non-control runs. A2 is a
freshly generated ~44,680-example single-signal dataset: the same clusters as A1
and A3, but ~4.5× the recombinations of them, with its own `test-0000NN` ids. A2
pairs with nothing.

**It isolates the wrong thing.** Count labelled positions per head:

| arm | dataset | examples/epoch | that signal's labelled positions |
|---|---|---|---|
| **A1** | that signal alone, 10k | 10,000 | **10,000** |
| **A2** | that signal alone, ~45k | 44,680 | **44,680** |
| **A3** | the merged set | 44,680 | **10,000** |

The provisional DD3 matched A2 to A3 on encoder gradient steps, which is a real
confound worth controlling. But A2 gives the head under test **4.47× the
supervision A3 does**. A3 losing to A2 would be fully explained by supervision
volume, without cross-symptom exposure entering at all — which is the boring
explanation the control was meant to exclude, relocated rather than removed.

**A1 vs A3 holds per-head supervision fixed at 10,000 and varies exactly one
thing: whether the encoder also receives gradient from five other heads.** That
is the ticket's question. It is also the pairable comparison, because A3's merged
slice for a signal *is* that signal's own 10k splits — same examples, same texts,
same truths — and DD4's `source_ids` restore the ids so `_qualify`, `mcnemar` and
the per-fragment table all work untouched.

So:

* **A1 ↔ A3: paired McNemar on that signal's test slice. The answer.** Both arms
  must be produced in one invocation (DD5).
* **A2: unpaired.** Read via the pooled cluster-bootstrap interval and the
  per-fold spread, never via McNemar. It answers a different and genuinely
  interesting question — what 4.5× more recombinations of the *same* 418 clusters
  buys, at unchanged effective n. `arch_encoder_training.md` section 5 predicts
  "not much, and past some point negative"; nothing has measured it.

**A2 is retained for all six signals** at the user's direction. It is ~70% of the
GPU bill (see Cost) and it is bought deliberately: without it, a movement between
A1 and A3 cannot be separated from step count, and `nocturia` and
`urinary_frequency` — the two weakest signals and the two the docs suspect are
near-synonyms — are exactly where a real effect is most plausible.

**What no arm isolates, and the report must say so.** There is no arm matched to
A3 on *both* encoder steps and per-head supervision, because no such dataset
exists: holding one fixed moves the other. A1↔A3 varies exposure and step count
together; A2 bounds how much of any movement step count alone can explain. The
write-up states this rather than implying a clean isolation.

### DD2 — Unpairable arms are skipped visibly, not split into a second report

`build_report` calls `compare_models(runs)` unconditionally (`report.py:965`), so
a report holding A1, A2 and A3 raises on the first A2 pair. Two ways out:

1. Put A2 in its own report.
2. Teach `compare_models` to skip a pair whose example sets differ.

**Take 2.** Option 1 loses `model_movement`, which puts all three arms' per-library
accuracy side by side with a `spread` column — the one table that shows whether a
lift is diffuse or concentrated in one error family, and the shape this ticket
most wants to read. It also gives A2 its own cluster-tag-coverage block and its
own header, which invites exactly the cross-report eyeballing the bootstrap
intervals are too wide to support.

**The skip must be recorded, never silent.** A reader who expected three
comparisons and sees two will assume the third was null. `compare_models` gains a
`skipped` list alongside `comparisons`, each entry naming the two runs, the slice,
and the reason (`"example sets differ: A has 9045, B has 2000, 0 in common"`), and
`_render_comparisons` prints them under the table. A pair skipped for any reason
other than a genuine dataset difference is a bug, and the entry is what makes it
findable.

Rejected: normalising ids inside the report layer so A2 pairs anyway. A2's test
examples are different texts. There is nothing to pair.

### DD3 — The merge needs no regeneration, and no part of 12.5

`fold_bucket` is a pure hash of `{salt}:{cluster_key}` with no knowledge of
signals, so a cluster lands in the same fold in all six runs and cluster
disjointness survives concatenation for free. And because each example carries
only its own signal's key, the other five heads see a **missing** key, which
`dataset.py` already defines as "exclude from the loss" rather than as a `null`
assertion. No silence is declared, so none needs checking.

The one exception is the structural nulls, and task 2 of the phase-1 plan is what
makes it safe: labelling one filler-only example `null` for all six signals *is*
an assertion that the filler libraries are silent about all six, and the
generalised lint now holds that with zero baselined exceptions.

**Union the structural nulls; do not keep six copies.** Same gradients, 25% fewer
forward passes, and each head keeps exactly the 15/25/60 mix it trained on alone —
which is what keeps A1↔A3 clean.

**The merge tool asserts the identity rather than assuming it.** If anyone ever
adds the signal to `run_seed`'s derivation, six divergent structural-null sets
would dedupe to nothing, every head's class prior would shift, and nothing
downstream would notice. The assertion: for each fold and split, the structural-null
examples of all six datasets agree on `example_id`, `text` and
`meta.fragment_ids`, position for position. A mismatch is a hard error.

**Two further checks the provisional plan did not call for.**

*Fragment-block conflicts.* Task 2 said "union of the `fragments` blocks". A dict
union silently first-wins when the same `fragment_id` carries a different
`cluster_key`, `split` or `fragment_type` in two sources — which is precisely the
drift the assertion above exists to catch, arriving through the other door. Any
disagreement on a shared `fragment_id` is a hard error.

*Cross-signal cluster-key collisions.* `cluster_id` is namespaced `{library}:{tag}`
(`manifest.py:260`), so tagged clusters cannot collide across signals. **Untagged
ones can**: `cluster_key` falls back to `normalise(text)` (`manifest.py:116`),
which is not library-qualified, and `deduplicate` only runs within a single
generation run. Identical text in two signals' libraries becomes one resampling
unit spanning both. That deflates effective n rather than inflating it, so it is
the safe direction and not a blocker — but it is invisible, and invisible is what
this package exists to prevent. The merge reports the count and lists the keys in
its `merged_from` block; it does not fail on them.

### DD4 — Every merged example carries the id it had in each signal's dataset

All six datasets number examples `train-000000` upward, so a naive concatenation
collides every id and anything keyed on the id — McNemar's pairing above all —
would silently compare a model against itself.

But the comparison this ticket exists for is *paired on example id*: A1↔A3 on
fever's test slice only means anything if both models are asked about the same
2,000 texts, matched one to one.

So: the merged record gets a fresh `example_id` (`{signal}:{original}` for a
signal-owned example, `shared:{original}` for a deduped structural null), **and** a
`meta.source_ids` mapping of signal → the id that example had in that signal's own
dataset. A structural null carries all six; a fever example carries one.

**When the joint model reports predictions for signal S, it reports them under
`meta.source_ids[S]`.** Every existing pairing mechanism then works untouched,
because A3's fever predictions are keyed exactly as A1's are — including
`FoldRun.build`'s `fold{i}:` qualification, which is applied to both arms
identically and so survives the pairing.

Rejected: teaching the report layer to normalise ids. It puts the knowledge that
two ids are the same example in the one module with no way to check it.

### DD5 — One comparison report per signal, holding three arms

`build_report` already does everything needed *within* one signal: three
`ModelRun`s, pooled cluster bootstrap on each, paired McNemar between each
pairable pair (DD2), and `model_movement` putting per-library accuracy side by
side with a `spread` column.

Six reports, stem `<signal>.joint_comparison`, each holding A1, A2, A3 restricted
to that signal's test slice, plus the baselines. Plus one hand-written
`reports/encoder_training/<date>-plain-english.md`, following the 2026-08-16
pattern.

Rejected: one six-signal report. Its headline, ticket-question, sub-class recall
and per-fragment sections are all per-signal-slice by construction, so a
six-signal version needs a whole new section layer — and it would bury the paired
comparisons under a navigation problem.

**Consequence:** because report JSON holds no per-example predictions, A1 and A3
must be produced in one invocation. **A1 is re-run, not read off disk.** It is
deterministic from pinned seeds, it costs an hour, and it gets a holdout number
for free. A2, being unpaired, does not strictly need to be in the same
invocation — but it is, because it shares the folds' load and the report.

### DD6 — Joint epoch selection is one criterion across six heads

Not in the provisional plan and it is not optional. `finetune_fold_model` selects
`best_epoch` on one signal's validation macro-F1 (`train.py:866`). Six heads share
one encoder, so there is exactly one set of weights to stop at and per-head early
stopping is impossible.

**The criterion is the unweighted mean of the six heads' validation macro-F1**,
each computed on that head's own labelled validation examples. Unweighted because
the alternative — weighting by labelled count — would let fever and dysuria decide
the stopping point for nocturia, and the ticket's most interesting question is
about the weak signals.

**This is a confound and it is recorded, not hidden.** A1's fever head stops at
the epoch that maximises fever macro-F1; A3's fever head stops at the epoch that
maximises the six-head mean. Those can differ, and where they do, part of any
A1↔A3 movement is the stopping rule rather than the representation. It is
unavoidable with a shared encoder. Both arms' selected epochs go in the report
header so a reader can see when they diverged.

### DD7 — No `GENERATOR_VERSION` bump, and `expectations.txt` stays whole

The phase-1 plan's DD3 deferred splitting `expectations.txt` on the grounds that
the joint-training ticket "bumps `GENERATOR_VERSION` and regenerates everything
anyway". **That premise is false**: DD3's whole finding is that the merge needs no
regeneration.

Splitting it here would take the filler libraries from five to six, changing
`_draw_filler`'s distribution, changing every generated example, making A1's
numbers incomparable to A2's and A3's — and A1↔A3 is the finding. It belongs with
ticket 6, which regenerates everything for its own reasons.

The same applies to the 12.6 noise pass. Two variables at once produces a result
about neither.

### DD8 — Six heads, not seven, and the runtime swap stays blocked

`data/uti1.json` declares **seven** `send_to_encoder` signals.
`recent_uti_present` has no libraries, so a joint model has six heads and
`EncoderOutput.validate_against` requires the output keys to match the ruleset
exactly. **The joint model cannot replace `encoder_stub.py`.**

**Do not add an untrained seventh head to make the arity match.** A head that
never receives a gradient emits whatever its initialisation produces, behind a
contract saying the encoder answered the question. That is strictly worse than a
stub that is honestly a stub.

Recorded here because "we finally have a multi-head model" is the natural thing to
expect from this ticket and it is not what the ticket delivers. Closing the gap
means writing `recent_uti_present` libraries, or deciding that `EncoderOutput`
permits partial output — which `encoder_next_steps.md` section 6 already scopes.

### DD9 — The holdout is scored in-process, at the end of each fold

Not as a separate pass over saved weights, for two reasons.

**Disk.** A1, A2 and A3 across six signals and five folds is 65 fine-tuned
encoders at ~440MB — **~28GB** to retain and score later. Scoring the 67
submissions while the encoder is still in memory costs seconds and retains
nothing.

**The rules.** `data/realistic/README.md` is explicit that the set never selects
anything and is scored once per candidate model with the number recorded, bad ones
included. Ordering the call **after** margin selection and **after** test scoring
makes "it selected nothing" a structural property rather than a promise, and it
gets a test asserting the order.

`holdout.py` stays standard library: it loads and validates the TSV against the
ruleset and computes the metrics; the forward pass is supplied by the training
path. Same tier boundary as everything else that decides what a number means.

**What the holdout can and cannot decide.** Nothing about the arms. 67
submissions with no cluster structure gives roughly ±11 points on one overall
figure and something like ±30 per signal. It cannot rank A1 against A3 — that is
what the fold-pooled test set is for. It is a **validity** instrument: it can show
that 92.9% is really 55%, which is the question that matters most and which
nothing else answers.

### DD10 — Two things about the holdout labels, settled here

The provisional plan's DD7 left both open. One is already answered and one is not.

**Provenance is answered, and the answer is in `data/realistic/README.md`.** The
labels "were proposed by Claude and reviewed by the maintainer", and the 67 texts
were "written to read like real patients" rather than collected. Task 1 does not
investigate this; it **propagates** it. Every report that carries a holdout number
carries the README's own sentence: the labeller and the model share an
architecture and could share a blind spot, which would inflate the score in a way
no resampling would reveal.

**The missing-vs-`null` question is open and is real.** README rule 4 says a
signal the labeller cannot judge gets its key **omitted**, and defines a blank
cell as that omission. The TSV has a value in all 469 cells — zero blanks. Either
every signal was genuinely judgeable on every submission, or `null` absorbed some
"cannot say". Those are exactly the two things rule 4 exists to keep apart. Task 1
resolves it by review and records the answer in the README; `holdout.py`
implements the distinction either way, because the format has to support it even
if today's file does not use it.

**A third thing, found while reviewing: the README's distribution table disagrees
with the TSV.** README gives `urinary_frequency_present` 27 `true` / 40 `null` and
`recent_uti_present` 2 `true` / 5 `false` / 60 `null`; the TSV holds 26/41 and
2/4/61. Two cells. One of the two is stale and Task 1 fixes whichever it is —
before any report quotes either.

**And `dysuria_present` is 56 `true` / 11 `null` / 0 `false`**, so its holdout
number is very nearly a recall-only measurement and is reported as one.

---

# Predictions, recorded before the run

House rule from `arch_training.md` section 9: a ceiling or an expectation asserted
after a disappointing number is an excuse. These go in the report header.

* **A1 → A2 (4.5× recombinations, identical 418 clusters): little or nothing,
  possibly slightly negative.** Effective n is unchanged; only surface forms
  multiply. A large gain here makes the interesting question "why did more views
  of the same ideas help", and the answer is more likely optimisation than data.
* **A1 → A3 on fever: within ±2–3 points, i.e. probably not detectable.** The
  fever head gets no new supervision, only a differently-shaped encoder.
* **A1 → A3 on `nocturia` and `urinary_frequency`: the one place a large effect is
  plausible, in either direction.** They are the two weakest signals, TF-IDF is
  also worst on exactly those two, and the working hypothesis is that they are
  near-synonyms — "going a lot" against "going a lot at night". Joint training is
  the first thing that forces one encoder to hold both apart. Mutual
  disambiguation and mutual interference are both live.
* **Holdout: expect a large drop from the recombination numbers.** Every
  fever-`null` training example pairs no-fever-language with *bland non-clinical*
  filler, so "clinical-sounding symptom language ⇒ not null" is an available
  shortcut. Real submissions are dense with clinical language about other
  symptoms — dysuria is `true` in 56 of 67. If the shortcut exists, this is where
  it shows, and **the joint run does not fix it** (DD3: the fever head is masked on
  every dysuria example). Ticket 6 is what fixes it.

---

# Task 1: Holdout scoring

## A. State of the world

Six single-signal Arm B heads exist and are documented in `arch_training.md`
section 10. Every number in this project has been measured on recombinations of
the same fragment libraries the models were trained on. `data/realistic/` holds
67 submissions and their labels and has never been read by any code.

Nothing in this task has been completed.

## B. Files and deliverables

**New:**
* `scripts/encoder_training/holdout.py` — standard library only.
* `tests/test_encoder_training_holdout.py` — unit tests, no marker (see below).

**Modified:**
* `scripts/encoder_training/train.py` — call the holdout scorer at the end of
  `run_finetune_fold`, after `select_margin` and after test scoring.
* `scripts/encoder_training/report.py` — a `holdout` block per model, and a
  markdown section rendering it.
* `scripts/encoder_training/__main__.py` — `--holdout` path argument, defaulting
  to `data/realistic/uti1_holdout.labels.tsv`; `--no-holdout` to skip.
* `data/realistic/README.md` — correct the distribution table (DD10), record the
  resolution of the missing-vs-`null` question.
* `documentation/docs/arch_encoder_training.md` — a section on the holdout: what
  it measures, the ±30-point per-signal power, the DD10 provenance limitation.

**Deliverables:** every Arm B run from now on prints and records a real-text
number per signal alongside its recombination number, with both `n`s beside them.

## C. Instructions

1. **`holdout.py`, standard library.** It loads the TSV, validates the header
   against the ruleset's `send_to_encoder` signals (all seven; the six with heads
   are a subset and a signal with no head is simply not scored), and parses cells
   into the same three classes `dataset.py` uses plus a distinct *omitted* state
   for a blank cell. **A blank and a `null` must not collapse** — that is rule 4
   and it is the whole reason the module validates rather than reading with
   `csv.DictReader` and moving on.
2. **The resampling unit is the submission** (README rule 5), so the bootstrap
   here resamples submissions, not clusters. Reuse `metrics.bootstrap_ci` with
   each prediction's `unit` set to its `submission_id`.
3. **Compute per-signal accuracy and per-class recall**, plus one overall figure.
   Every per-signal number carries its own `n` and its interval. Print the
   ±30-point per-signal power **beside** each number, not in a footnote below the
   table — the whole failure mode here is a reader taking a per-signal number at
   face value.
4. **The forward pass is injected**, not imported. `holdout.py` takes a callable
   `(texts) -> per-signal class scores` and knows nothing about torch. This is
   the same tier boundary `dataset.py` and `metrics.py` sit on, and it is what
   lets CI's unit job cover every line of the logic that decides what a number
   means.
5. **Wire it into `run_finetune_fold` after test scoring.** Order is: fit →
   select epoch on val → select margin on val → score test → score holdout. Apply
   the fold's already-selected margin; the holdout selects nothing.
6. **Test the order explicitly.** A test that fails if the holdout call moves
   ahead of `select_margin` or ahead of test scoring. Assert it by construction —
   e.g. a recording fake whose call sequence is checked — rather than by reading
   the source.
7. **Resolve DD10's two open items.** Review the 11 `dysuria_present` `null`
   cells and any others where "cannot judge" is plausible, decide whether each is
   a genuine `null` or an omission, and record the decision in the README.
   Separately, recount the TSV and fix whichever of README/TSV is stale.
8. **Report block and markdown section.** State the provenance limitation in the
   section itself, quoting the README, not by reference.
9. `pytestmark` is **not** set — this is a unit test with no database and no ML
   dependency. Confirm `arch_testing.md` needs no change.

---

# Task 2: The merge tool

## A. State of the world

Task 1 is complete: every Arm B run carries a real-text number. Six per-signal
fold trees exist under `data/synthetic/generated/folds/`, each five folds of
three splits, generated at 10k/2k/2k. Nothing merges them.

## B. Files and deliverables

**New:**
* `scripts/encoder_training/merge.py` — standard library only.
* `tests/test_encoder_training_merge.py` — unit tests, no marker.

**Modified:**
* `scripts/encoder_training/__main__.py` — a `merge-folds` subcommand.
* `documentation/docs/arch_training.md` — the merged-tree convention, the
  `source_ids` rule, the structural-null union.

**Deliverables:** `python -m scripts.encoder_training merge-folds` reads six
per-signal fold trees and writes one merged tree that `dataset.load_folds`
accepts with every existing check passing and **no new escape hatch**.

## C. Instructions

1. **It lives in `encoder_training`, not `synthetic_data`**, because it is built
   on the fold-tree convention in `dataset.py`, and `encoder_training` already
   imports from `synthetic_data` — the other direction would be a back-import
   that `tests/test_wiring.py` exists to prevent the shape of.
2. **Output path follows `dataset.FOLD_FILENAME`** with the merged name in the
   `signal` position, so `load_folds(dir, "joint6", folds=5)` works with no
   special case. Do not invent a second filename convention.
3. **Assert the structural-null identity (DD3).** For each fold and split, the
   structural-null examples of all six sources must agree on `example_id`, `text`
   and `meta.fragment_ids`, position for position. A mismatch is a hard error with
   a message naming the fold, split, position and the two disagreeing signals.
4. **Union the structural nulls**, keeping one copy carrying all six signals'
   labels — all `null`, since that is what each source asserts — and all six
   `source_ids`.
5. **Every merged record gets a fresh `example_id` and a `meta.source_ids` map
   (DD4).** `{signal}:{original}` for a signal-owned example, `shared:{original}`
   for a deduped structural null. Preserve `split`, `text`, `meta.label_mode` and
   `meta.fragment_ids` verbatim.
6. **Merge the sidecars.** Union the `fragments` blocks; require agreement on
   `folds`, `fold_index`, `split_salt` and `generator_version`; set `signal` to
   the merged name; add a `merged_from` block naming the six sources with their
   own `signal`, example counts and seeds.
7. **Two checks the fragments union needs (DD3).** A shared `fragment_id` whose
   entries disagree on `cluster_key`, `split` or `fragment_type` is a **hard
   error**. A `cluster_key` shared by fragments from two different signals'
   libraries is **reported, not fatal**: count it, list the keys in `merged_from`,
   and print a one-line warning saying effective n is deflated by that much.
8. **Test that `load_folds` accepts the output** with `_check_disjoint`,
   `_check_fold_agreement` and `_check_test_partition` all passing on a
   synthesised six-signal fixture. That test is the contract; if it needs a new
   escape hatch in `dataset.py`, the merge is wrong, not the loader.
9. **Test the failure paths**: divergent structural nulls, conflicting fragment
   entries, disagreeing `split_salt`, and a source tree missing a fold.

---

# Task 3: The joint training path

## A. State of the world

Tasks 1 and 2 are complete: real-text scoring is wired in, and a merged six-signal
fold tree can be produced and loaded. `--signal` still means both "which dataset"
and "which head", and `run_finetune_fold` trains on one signal's labelled
examples only.

## B. Files and deliverables

**Modified:**
* `scripts/encoder_training/train.py` — the bulk of the work.
* `scripts/encoder_training/decision.py` — no change expected; confirm
  `select_margin` needs none.
* `scripts/encoder_training/__main__.py` — `--dataset` separated from
  `--signals`.
* `scripts/encoder_training/model.py` — `LinearHeads` is already a `ModuleDict`;
  confirm no change.
* `tests/test_encoder_training_arm_b.py` — joint-path tests.
* `documentation/docs/arch_encoder_training.md` — the joint path, per-head
  margins, DD6's shared epoch criterion.

**Deliverables:** one fine-tune run over the merged tree produces six heads, six
decision rules and six sets of test predictions keyed by `source_ids`.

## C. Instructions

1. **Separate "which dataset" from "which heads".** `--dataset` names the fold
   tree (the `signal` position in `FOLD_FILENAME`, and part of the embedding
   cache key via `embed.split_cache_key`). `--signals` is the set of heads to
   train and evaluate, defaulting to every signal the loaded fold declares. A
   single-signal run passes the same value for both and must produce **bitwise
   identical** results to today's — assert that with a test, because it is what
   makes A1's re-run comparable to the committed 2026-08-16 numbers.
2. **Train on every example, evaluate per head.** `masked_cross_entropy` and
   `target_matrix` already handle a multi-signal target matrix; the change is
   `_labelled`'s single-signal filter in `run_finetune_fold` (`train.py:974`),
   which becomes "every example labelled for *any* trained signal".
3. **Per-head margin selection.** Run `select_margin` on each head's own labelled
   validation examples, independently, under the unchanged DD9 objective. **No
   cross-head trade** — a margin that sacrifices nocturia to help fever is a
   decision nobody asked for. `foldN.decision.json` becomes a mapping of signal →
   rule; keep the single-signal shape readable by writing the mapping form
   always, including for single-signal runs, and migrate the reader.
4. **Epoch selection is the unweighted mean of the heads' validation macro-F1
   (DD6).** Record every head's per-epoch macro-F1 in the result, not just the
   mean, so the report can show where a head's own best epoch differed from the
   selected one.
5. **Fan one fold out into six `FoldRun`s.** `FineTuneFoldResult`,
   `head_artefact`, `write_artefacts` and `build_metadata` all take
   `signal: str` today and `REQUIRED_METADATA` lists `"signal"` as mandatory
   (`train.py:1123`). Generalise to a signal list, keeping the key present and
   scalar for single-signal runs so existing artefacts stay readable.
6. **Predictions are keyed by `source_ids` (DD4).** When scoring head S, each
   prediction's `example_id` is `meta.source_ids[S]`, not the merged id. A merged
   example with no `source_ids` entry for S must be unreachable — it is masked for
   S — and hitting one is a hard error, not a fallback.
7. **Artefact layout: `models/encoder/joint6/<arm>/`.** `<signal>/<arm>/` has no
   place for a model answering six questions. Decide it here, before artefacts are
   written.
8. **`build_metadata`'s `encoder_contract` note stands and is updated**: six heads
   still cannot satisfy `EncoderOutput.validate_against` against seven declared
   signals (DD8). Do not add a seventh head.
9. **Tests:** single-signal parity (item 1); a joint run on a small synthetic
   merged fixture producing six rules and six prediction sets; per-head margins
   selected independently; predictions keyed by `source_ids`; and that a head with
   no labelled validation examples fails loudly rather than silently taking a
   default margin.

---

# Task 4: The report shape

## A. State of the world

Tasks 1–3 are complete: the holdout is scored in-process, the merge tool exists,
and a joint run produces six heads with per-head rules and `source_ids`-keyed
predictions. `run_compare_models` still loads **one** fold tree
(`__main__.py:801`) and runs every arm against it, and `compare_models` still
raises on any unpairable pair.

## B. Files and deliverables

**Modified:**
* `scripts/encoder_training/report.py` — `compare_models` skip-and-record (DD2);
  the holdout block; `_render_comparisons` printing skipped pairs.
* `scripts/encoder_training/__main__.py` — a `joint-compare` subcommand loading
  three fold trees and emitting six per-signal reports.
* `tests/test_encoder_training_metrics.py` / a report test file — coverage for
  the skip path.
* `documentation/docs/arch_encoder_training.md` — the three-arm report shape and
  what each comparison does and does not isolate.

**Deliverables:** one invocation produces six `<signal>.joint_comparison.json`
plus markdown, each holding A1, A2, A3, the baselines and the holdout numbers.

## C. Instructions

1. **`compare_models` gains a skip path (DD2).** Compute the two id sets; if they
   differ, append to a `skipped` list with both run names, the slice, both sizes
   and the overlap count, and continue. Return `(comparisons, skipped)` or a dict;
   `build_report` stores both. **Do not swallow other `MetricsError`s** — a
   truth-disagreement on a shared id is still a bug and must still raise.
2. **`_render_comparisons` prints the skipped pairs** under the comparison table,
   with the reason. A reader must not be able to mistake "not pairable" for "no
   difference found".
3. **The new subcommand loads three fold trees**, one per arm — this is the
   structural change, because `run_compare_models` assumes one. Each arm is
   fine-tuned against its own folds; each arm's predictions are then restricted to
   one signal's slice and handed to `build_report` as a `ModelRun`.
4. **Restrict by signal, not by dataset.** A3's predictions for signal S are
   already only S's labelled examples (Task 3 item 6); A1's and A2's are
   single-signal by construction. The restriction is a filter on which `ModelRun`s
   go into which report, plus `header["signal"]`.
5. **Check `cluster_tag_coverage`'s `signal=` filter** (`report.py:547`) still says
   the right thing when the fragments block spans six signals' libraries. It
   filters on `fragment.signal_key`, so it should — but A3's fragments block is
   six times the size and the coverage percentages are the number a reader uses to
   decide whether to trust the intervals. Test it against a merged fixture.
6. **Note, out of scope, recorded:** `build_report` emits a hardcoded
   `FEVER_LIBRARY_CLUSTERS` constant into every report regardless of signal. It is
   pre-existing and wrong-shaped for a six-signal world. Leave it; open a ticket.
7. **The report header carries** both arms' selected epochs per head (DD6), the
   three arms' examples-per-epoch and labelled-positions-per-head (the DD1 table),
   and the predictions above verbatim.
8. **The header must state what no arm isolates** (DD1, final paragraph). A
   sentence, in the header, not in an appendix.

---

# Task 5: The sweep and the write-up

## A. State of the world

Tasks 1–4 are complete. All that remains is generating the datasets, running the
sweep and writing it up. No code changes are expected; a code change needed here
is a sign a previous task was incomplete.

## B. Files and deliverables

**New:**
* Six `reports/encoder_training/<signal>.joint_comparison.{json,md}`.
* `reports/encoder_training/<date>-plain-english.md`.

**Modified:**
* `documentation/docs/arch_training.md` — section 10 results table, 12.8 status.
* `documentation/docs/arch_encoder_training.md` — the joint result.
* `documentation/architecture.md` — 3.16's "Note on expanding past one signal".

## C. Instructions

1. **Three generation products, not two.** The provisional plan's Task 5 said
   "`generate-folds` for six signals at 45k; `merge-folds`", which is wrong:
   merging six 45k trees gives ~268k, not 44,680. The correct sequence is:
   * **(a)** six single-signal trees at the current 10k/2k/2k — these are A1's
     datasets and the merge's inputs;
   * **(b)** `merge-folds` over (a) → the merged tree, ~44,680 / 9,030 / 9,045 per
     fold — A3's dataset;
   * **(c)** six single-signal trees at counts matching (b) exactly — A2's
     datasets. Match the merged tree's per-split counts rather than rounding to
     45,000, or A2 stops being a step-matched control.
2. **Verify (b)'s counts before spending GPU.** 60,000 − 5×3,064 = 44,680 is the
   arithmetic; confirm the tool's actual output matches, per split, before the
   sweep starts.
3. **Run the sweep.** One `joint-compare` invocation per signal, producing A1, A2,
   A3, the baselines and the holdout numbers in one report. Budget ~6.5 hours of
   Arm B plus 30–60 minutes of embedding.
4. **Read A1↔A3 from the paired McNemar; read A2 from the intervals only.** A2 has
   no McNemar row anywhere in the output and the skipped-pairs section says why.
   Do not compare A2's point estimate to A1's or A3's without the intervals beside
   both.
5. **The write-up follows the 2026-08-16 pattern.** State the predictions first,
   then what happened, then what it means. Do not rank the six signals against each
   other in prose without restating the untagged-library caveat — that ranking is
   still substantially an artefact of which libraries carry cluster markers.
6. **The holdout is a separate finding from the arms.** Report it as a validity
   check with its own `n`s and the DD10 provenance limitation, and do not let a
   holdout number decide anything about A1, A2 or A3 (DD9).
7. **If the holdout says the numbers do not transfer**, say so plainly and stop
   short of recommending anything from the arms. A large drop makes ticket 6
   (clinical-language nulls) the priority over everything else on the roadmap, and
   this ticket's arm result becomes a smaller deal than it looks.

---

# Cost

**GPU, at ~2 minutes per 10k-example fold on a 12GB card:**

| arm | folds | per fold | total |
|---|---|---|---|
| A1 — six signals × 10k | 30 | ~2 min | ~60 min |
| A2 — six signals × 45k | 30 | ~9 min | ~270 min |
| A3 — joint × 45k | 5 | ~9 min | ~45 min |

**≈ 6.5 hours of Arm B**, plus the baselines. Embedding caches at 45k are roughly
4.5× the ~215MB a 10k sweep produces, per dataset variant: budget a few GB of disk
and another 30–60 minutes.

**A2 is 70% of that bill**, and it is bought deliberately (DD1). If time gets
short, dropping A2 for the four signals other than `nocturia` and
`urinary_frequency` recovers ~3 hours and loses the least — those two are where an
effect is most plausible and where a confounded number would be least useful.

**Generation** is minutes: three products (Task 5 item 1), ~600MB of git-ignored
JSONL. **Disk for weights: nothing**, given DD9.

---

# Open questions for the user

1. **Does A2 need its own holdout numbers?** It is six more models scored against
   the 67, which is free per DD9, and it is six more rows in the write-up for an
   arm that answers a side question. Scoring it costs nothing and reporting it
   costs attention. Default in this plan: score it, report it in the JSON, and keep
   it out of the markdown's headline table.
2. **Is `nocturia`-vs-`urinary_frequency` interference worth measuring directly?**
   A fourth arm — those two merged and nothing else — would isolate it from the
   other four. ~45 minutes of GPU. It is a different ticket's question but it is
   cheap enough to be worth an explicit no. Default: no.
3. **Should the report layer persist per-example predictions?** Re-running A1 is an
   hour and needs no code; persisting predictions is a schema change that makes
   every future comparison cheaper. This ticket wants the first (DD5); the third
   such ticket will want the second.

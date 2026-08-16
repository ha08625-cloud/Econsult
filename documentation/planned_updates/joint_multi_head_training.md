# Provisional plan: the combined training dataset run

**Status: provisional and not agreed.** This is stage-1 output — the discussion
and the design decisions, written down so they can be reviewed and expanded into
an implementation plan. Nothing here has been built.

**Related:** `arch_training.md` (sections 7, 10 and 12.8 are prerequisites),
`arch_encoder_training.md` (sections 3, 5, 8 and 9),
`planned_updates/multi_symptom_training_expansion.md` ("What comes next",
tickets 4 and 5), `data/realistic/README.md` (the held-out set's rules).

This is ticket 4 and ticket 5 of that document, taken together on purpose. The
reason they are one ticket rather than two is in DD8.

---

# Orientation for someone new to this

Six symptoms — fever, dysuria, urinary frequency, nocturia, flank pain,
haematuria — each have hand-written fragment libraries, each have a five-fold
generated dataset, and each have a fine-tuned `roberta-base` head trained on
2026-08-16. Six models, one question each. `arch_training.md` section 10 has the
results.

The next step is one encoder answering all six questions at once. The reason to
want it is not the deployment shape — that stays blocked, see DD5 — but a
question nobody can currently answer: **does exposure to five other symptoms'
confounders make each symptom's answer better or worse?** The "whose symptom is
this / when did it happen / is this literal" skills the hard `null` sub-classes
test are not symptom-specific, so an encoder that has seen them six times over
may generalise better. Or the heads may interfere with each other.

Two things about that question are worth understanding before reading anything
below, because they set what a good outcome even looks like.

**The joint run adds no supervision to any head.** A dysuria example carries a
dysuria label and *no fever key at all* — which `dataset.py` reads as "mask this
head", not as "fever is null here". So the fever head sees exactly the 10,000
labelled positions it saw before, in exactly its 15/25/60 mix. What changes is
that the shared encoder underneath it is also being pulled by five other heads
on text the fever head never gets a gradient from. **The only mechanism by which
this can help is representational.** Anything that reads like "the model now
learns that a dysuria sentence means no fever" is describing ticket 6
(`arch_training.md` 12.5), not this.

**The effect being looked for is small.** `arch_encoder_training.md` section 4a
puts the paired five-fold sensitivity at roughly 2–3 points. A result inside that
band is "no detectable effect", and that is a legitimate and likely outcome. This
ticket is worth doing because the answer changes what gets built next, not
because a win is expected.

---

# What was verified while writing this

Five claims the plan rests on, checked against the tree rather than inherited
from the documents.

1. **Structural nulls are byte-identical across signals.** `fever_present` and
   `dysuria_present` fold-0 train at the agreed recipe produce **3,064
   structural nulls each, with identical `example_id`s and identical text**, and
   **zero** text overlap outside them. The merge premise holds exactly as
   `arch_training.md` 12.8 states it.
2. **So are the `example_id`s of everything else, and that is the trap.** All six
   datasets number their examples `train-000000` upward. A naive concatenation
   collides every id, and anything keyed on the id — McNemar's pairing above all
   — would silently compare a model against itself. See DD2.
3. **The merged fold is ~45k, not 60k.** Per fold: **train 44,680, val 9,030,
   test 9,045.** The "60,000" in the plan of record is *labelled positions*,
   which is right, and it has been read as an example count, which is not. The
   step-matched control arm is therefore **45k, not 60k**. See DD3.
4. **45k single-signal generation works on the thinnest libraries.** Fever 1,753
   duplicate rejections, dysuria 3,358, haematuria 3,568, no `PoolExhaustedError`
   anywhere, ~3 seconds per run. Rejection rates rise from ~1% at 10k to 4–8% at
   45k, which is the pool working rather than a problem.
5. **The report JSON does not persist per-example predictions.** Its `models`
   blocks hold `per_fold`, `pooled`, `fold_spread`, `fragments` and
   `error_concentration` — pooled statistics, not decisions. So an arm can only
   be paired against arms produced in the same invocation. This is what forces
   DD4.

---

# Plan

Five tasks. The first four are code and can all be written while no GPU is busy;
the fifth is the sweep and the write-up.

1. **Task 1 — Score the six existing models against the 67 real submissions.**
   Smallest useful thing here, independent of everything else, and it is the only
   measurement that says whether any number in this project is evidence about
   real patient text.
2. **Task 2 — The merge tool.** Standard library, CI-covered: read six per-signal
   fold trees, write one merged tree with a valid sidecar.
3. **Task 3 — The joint training path.** Per-head margin selection, and the split
   between "which dataset" and "which heads".
4. **Task 4 — The report shape.** One comparison report per signal, holding three
   arms, reusing `build_report` unchanged.
5. **Task 5 — The sweep, and the write-up.** Three arms × six signals, every arm
   scored against the holdout, one plain-English report.

**Landing order is 1 → 2 → 3 → 4 → 5.** Task 1 first because it is small, it is
independent, and if it says the recombination numbers do not transfer at all then
tasks 2 to 5 are being run for a different reason than the one now on the table —
which is a decision the user should get to make before six hours of GPU, not
after.

---

# Scope

**In scope:** holdout scoring tooling and the labels' provenance question; the
merge tool; joint multi-head training with per-head decision rules; the
comparison report; the three-armed sweep across all six signals; every
architecture-doc update that goes with them.

**Out of scope, deliberately:**

* **Label vectors and declared silence** (`arch_training.md` 12.5). The merge
  needs none of it — see DD1 — and attempting it here would turn a two-week
  ticket into a two-month one.
* **Multi-symptom recombinations** (ticket 6). This is the thing that would
  actually put a dysuria sentence under a `fever_present: null` label. It is the
  right next ticket and it is not this one.
* **Splitting `expectations.txt`** and bumping `GENERATOR_VERSION`. The phase-1
  plan's DD3 parked both "with the joint-training ticket, which regenerates
  everything anyway". That premise is now false — see DD6.
* **`recent_uti_present`.** Still no libraries, still no head. See DD5.
* **Cluster-tagging the four untagged library sets** (ticket 7). Unchanged by
  anything here, and it still means those signals' absolute numbers are upper
  bounds.
* **Deploying anything.** See DD5.

---

# Design Decisions

### DD1 — The merge needs no regeneration, and no part of 12.5

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
which is what keeps the per-signal comparison against the 10k runs clean.

**The merge tool must assert the identity rather than assume it.** If anyone ever
adds the signal to `run_seed`'s derivation, six divergent structural-null sets
would dedupe to nothing, every head's class prior would shift, and nothing
downstream would notice. The assertion is: for each fold and split, the
structural-null examples of all six datasets agree on `example_id`, `text` and
`meta.fragment_ids`, position for position. A mismatch is a hard error.

### DD2 — Every merged example carries the id it had in each signal's dataset

This is the detail most likely to be got wrong quietly, and it is worth stating
as a rule rather than as an implementation note.

All six datasets number examples identically, so the merged file needs its own
key space. But the *comparisons this ticket exists for* are paired on example id:
joint-vs-single on fever's test slice only means anything if both models are
being asked about the same 2,000 texts, matched one to one.

So: the merged record gets a fresh `example_id` (`{signal}:{original}` for a
signal-owned example, `shared:{original}` for a deduped structural null), **and**
a `meta.source_ids` mapping of signal → the id that example had in that signal's
own dataset. A structural null carries all six; a fever example carries one.

**When the joint model reports predictions for signal S, it reports them under
`meta.source_ids[S]`.** Every existing pairing mechanism — `_qualify`,
`compare_models`, `mcnemar`, the per-fragment error table — then works untouched,
because the joint run's fever predictions are keyed exactly as the single-signal
fever run's are.

The alternative, teaching the report layer to normalise ids, was rejected: it
puts the knowledge that two ids are the same example in the one module that has
no way to check it.

### DD3 — The control arm is 45k, matched on examples per epoch

Merging six 10k datasets gives the encoder **4.47×** the gradient steps of a
single-signal run (44,680 examples per epoch against 10,000, at the same batch
size and epoch count). A fever movement would otherwise confound cross-symptom
exposure with step count, and step count is the boring explanation.

Three arms, then, per signal:

| arm | dataset | what it isolates |
|---|---|---|
| **A1** | that signal alone, 10k | the reference numbers already on file |
| **A2** | that signal alone, **45k** | step count and surface-form volume, at **identical effective n** |
| **A3** | the merged set, 45k | A2 plus five other symptoms' text |

**A3 vs A2, paired McNemar on that signal's test slice, is the answer.** A2 vs A1
is a second finding worth having on its own: the two runs rest on exactly the same
clusters — 418 for fever, unchanged — so it measures what 4.5× more
recombinations of the *same ideas* buys. `arch_training.md` section 5 predicts
"not much, and past some point negative"; nothing has measured it.

The plan of record says 60k. That is the naive 6 × 10k and it is wrong by the
15,320 structural nulls the merge removes. Matching on 60k would give A2 more
steps than A3 and quietly bias the comparison against the joint model.

**All six signals get all three arms.** Restricting A2 to fever would leave five
signals with a joint-vs-10k comparison that cannot separate diversity from step
count — and `nocturia` and `urinary_frequency`, the two weakest and the two the
docs suspect are near-synonyms of each other, are exactly where a real effect is
most plausible. Costing five extra control arms to be able to read that pair is
the right trade. See "Cost" below for what it actually buys and what it costs.

### DD4 — One comparison report per signal, holding three arms

`build_report` already does everything needed *within* one signal: three
`ModelRun`s, pooled cluster bootstrap on each, paired McNemar between each pair,
`model_movement` putting per-library accuracy side by side with a `spread` column.
That last one is the shape this ticket wants — a diffuse lift and a fix to one
error family are different findings — and it exists.

So: six reports, stem `<signal>.joint_comparison`, each holding A1, A2, A3 (plus
Arm A and the baselines as today) restricted to that signal's test slice. Plus one
hand-written `reports/encoder_training/<date>-plain-english.md`, following the
2026-08-16 pattern.

Rejected: one six-signal report. Its headline, ticket-question, sub-class recall
and per-fragment sections are all per-signal-slice by construction, so a
six-signal version needs a whole new section layer — and it would bury the paired
comparisons, which are the answer, under a navigation problem.

**Consequence, and it is the one that sets the sweep's shape:** because report
JSON holds no per-example predictions, all three arms must be produced in one
invocation. A1 is therefore **re-run**, not read off disk. It is deterministic
from pinned seeds, it costs an hour, and it gets a real-text number for free.

### DD5 — Six heads, not seven, and the runtime swap stays blocked

`data/uti1.json` declares **seven** `send_to_encoder` signals.
`recent_uti_present` has no libraries, so a joint model has six heads and
`EncoderOutput.validate_against` requires the output keys to match the ruleset
exactly. **The joint model cannot replace `encoder_stub.py`.**

**Do not add an untrained seventh head to make the arity match.** A head that
never receives a gradient emits whatever its initialisation produces, and it would
be doing so behind a contract that says the encoder answered the question. That is
strictly worse than a stub that is honestly a stub.

This is recorded here because "we finally have a multi-head model" is the natural
thing to expect from this ticket and it is not what the ticket delivers. Closing
that gap means either writing `recent_uti_present` libraries, or deciding that
`EncoderOutput` permits partial output — which `encoder_next_steps.md` section 6
already scopes as a cheap decision worth taking early.

### DD6 — No `GENERATOR_VERSION` bump, and `expectations.txt` stays whole

The phase-1 plan's DD3 deferred splitting `expectations.txt` on the grounds that
the joint-training ticket "bumps `GENERATOR_VERSION` and regenerates everything
anyway". **That premise is now false**: DD1's whole finding is that the merge
needs no regeneration.

Splitting it here would take the filler libraries from five to six, which changes
`_draw_filler`'s distribution, which changes every generated example, which makes
A1's committed numbers incomparable to A2's and A3's — and A1-vs-A2 is one of the
two findings this ticket produces. It belongs with ticket 6, which regenerates
everything for its own reasons.

The same applies to the 12.6 noise pass: it is independent of everything here and
should not be folded in. Two variables at once produces a result about neither.

### DD7 — The holdout is scored in-process, at the end of each fold

Not as a separate pass over saved weights, for two reasons.

**Disk.** A1 and A2 across six signals and five folds is 60 fine-tuned encoders at
~440MB, plus the joint run's five. Retaining them to score later is **~28GB**.
Scoring the 67 submissions while the encoder is still in memory — after the margin
has been selected on validation and after the test split has been scored — costs
seconds and retains nothing.

**The rules.** `data/realistic/README.md` is explicit that the set never selects
anything and is scored once per candidate model with the number recorded, bad ones
included. Ordering the call after margin selection and test scoring makes "it
selected nothing" a structural property rather than a promise, and it should have a
test asserting the order.

`holdout.py` stays standard library: it loads and validates the TSV against the
ruleset and computes the metrics; the forward pass is supplied by the training
path. Same tier boundary as everything else that decides what a number means.

**Two things about the labels to settle in task 1, not later.** The README's rule 4
says a signal the labeller cannot judge gets its key **omitted**, not set to
`null`. The TSV has a value in all 469 cells — no omissions anywhere. Either every
signal was genuinely judgeable on every submission, or `null` absorbed some
"cannot say", and those are exactly the two things that rule exists to keep apart.
And **`dysuria_present` is 56 `true` / 11 `null` / 0 `false`**, so its holdout
number is very nearly a recall-only measurement and should be reported as one.
Provenance is still unresolved (`arch_training.md` section 9): whether these are
real, clinician-written or generated decides what they are worth as evidence.

### DD8 — Why the holdout and the joint run are one ticket

They answer different questions and neither substitutes for the other, but the
models are the same models.

Every arm has to be fine-tuned anyway; scoring 67 texts at the end of each fold is
free; and the weights are not in the repository, so a later holdout ticket would
have to re-run all 35 fine-tunes purely to have something to score. Splitting them
costs a second six-hour sweep and buys nothing.

**Be clear-eyed about what the holdout can decide here: nothing about the arms.**
67 submissions with no cluster structure gives roughly ±11 points on one overall
decisive figure and something like ±30 per signal. It cannot rank A2 against A3 —
that is what the fold-pooled recombination test set is for. It is a **validity**
instrument: it can show that 92.9% is really 55%, which is the question that
matters most and which nothing else answers.

---

# Predictions, recorded before the run

House rule from `arch_training.md` section 9: a ceiling or an expectation asserted
after a disappointing number is an excuse. These go in the report header.

* **A1 → A2 (4.5× recombinations, identical 418 clusters): little or nothing,
  possibly slightly negative.** Effective n is unchanged; only surface forms
  multiply. If this shows a large gain, the interesting question becomes why more
  views of the same ideas helped, and the answer is more likely about optimisation
  than about data.
* **A2 → A3 on fever: within ±2–3 points, i.e. probably not detectable.** The
  fever head gets no new supervision, only a differently-shaped encoder.
* **A2 → A3 on `nocturia` and `urinary_frequency`: the one place a large effect is
  plausible, in either direction.** They are the two weakest signals, TF-IDF is
  also worst on exactly those two, and the working hypothesis is that they are
  near-synonyms — "going a lot" against "going a lot at night". Joint training is
  the first thing that forces one encoder to hold both apart. Mutual
  disambiguation and mutual interference are both live.
* **Holdout: expect a large drop from the recombination numbers.** Every
  fever-`null` example in training pairs no-fever-language with *bland
  non-clinical* filler, so "clinical-sounding symptom language ⇒ not null" is an
  available shortcut. Real submissions are dense with clinical language about other
  symptoms — dysuria is `true` in 56 of 67. If the shortcut exists, this is where
  it shows, and **the joint run does not fix it** (DD1: the fever head is masked on
  every dysuria example). Ticket 6 is what fixes it.

---

# Task sketches

Provisional; the implementation plan is where these get files and acceptance
criteria.

### Task 1 — Holdout scoring

`scripts/encoder_training/holdout.py`, standard library. Loads
`data/realistic/uti1_holdout.labels.tsv`, validates the header against the
ruleset's `send_to_encoder` signals, distinguishes a missing key from `null`,
computes per-signal accuracy and per-class recall with submission-level bootstrap
intervals, and refuses to run if asked to select anything. Settle the two label
questions in DD7. Wire it into the fine-tune path after test scoring. A report
block plus a section in the markdown, stating the ±30-point per-signal power
beside every per-signal number rather than below the table.

### Task 2 — The merge tool

`scripts/encoder_training/merge.py`, exposed as `python -m scripts.encoder_training
merge-folds`. It lives in `encoder_training` rather than `synthetic_data` because
it is built on the fold-tree convention in `dataset.py`, and `encoder_training`
already imports from `synthetic_data` — the other direction would be a back-import.

Reads six per-signal fold trees, asserts the structural-null identity (DD1), emits
one merged tree at `<name>.fold{i}.{split}.jsonl` with `meta.source_ids` (DD2) and
a merged sidecar: union of the `fragments` blocks, agreed `folds`/`fold_index`/
`split_salt`/`generator_version`, and a `merged_from` block naming the six sources.
Standard library, so CI's unit job covers it. `load_folds` must accept the result
with every existing check passing and no new escape hatch.

### Task 3 — The joint training path

Three changes, all small, all in places the code already anticipated.

* **Separate "which dataset" from "which heads".** `--signal` currently means
  both. Joint training needs a dataset name for the filename convention and the
  embedding cache key, and a *set* of signals for the heads.
* **Per-head margin selection.** `select_margin` on each head's labelled
  validation examples, independently, under the unchanged DD9 objective — no
  cross-head trade. `foldN.decision.json` becomes a mapping of signal → rule.
* **Train on every example, evaluate per head.** `masked_cross_entropy` and
  `target_matrix` already handle this; only `_labelled`'s single-signal filter in
  `run_finetune_fold` needs generalising.

`LinearHeads` is already a `ModuleDict` and needs no change.

### Task 4 — The report shape

Per-signal comparison reports (DD4). Mostly wiring: restrict each arm's pooled
predictions to one signal's slice and hand `build_report` three `ModelRun`s. Add
the holdout block. Check `cluster_tag_coverage`'s `signal=` filter still says the
right thing when the fragments block spans six signals' libraries.

### Task 5 — The sweep and the write-up

`generate-folds` for six signals at 45k; `merge-folds`; then one invocation per
signal producing A1, A2, A3 and the holdout numbers in one report. Then the
plain-English write-up. Do not rank the six signals against each other in prose
without restating the untagged-library caveat — that ranking is still
substantially an artefact of which libraries carry cluster markers.

---

# Cost

**GPU, at ~2 minutes per 10k-example fold on a 12GB card:**

| arm | folds | per fold | total |
|---|---|---|---|
| A1 — six signals × 10k | 30 | ~2 min | ~60 min |
| A2 — six signals × 45k | 30 | ~9 min | ~270 min |
| A3 — joint × 45k | 5 | ~9 min | ~45 min |

**≈ 6.5 hours of Arm B**, plus Arm A and the baselines. Those are near-free per
run once the embedding cache exists, but the caches themselves are not: at 45k
they are roughly 4.5× the ~215MB a 10k sweep produces, per dataset variant. Budget
a few GB of disk and another 30–60 minutes of embedding.

**A2 is 70% of that bill**, and it is the arm bought by answering "all six" rather
than "fever only". What it buys is a readable answer on `nocturia` and
`urinary_frequency`, which is where an effect is most likely and where a
confounded number would be least useful. Worth knowing that if time gets short,
dropping A2 for the four signals other than the weak pair recovers ~3 hours and
loses the least.

**Generation** is seconds per run: 6 signals × 5 folds × 3 splits at 45k, plus the
merge. Call it five minutes and ~600MB of git-ignored JSONL.

**Disk for weights: nothing**, given DD7. The `.pt` files are written per fold and
can be dropped as before.

---

# Open questions for the review chat

1. **Should A1 be re-run at all, or should the report layer learn to persist
   predictions?** Re-running is an hour and needs no code. Persisting predictions
   is a schema change that makes every future comparison cheaper. This ticket
   wants the first; the third such ticket will want the second.
2. **Does the joint run get its own `models/encoder/` layout?** `<signal>/<arm>/`
   has no place to put a model that answers six questions. `joint6/<arm>/` is the
   obvious answer; it wants deciding before artefacts are written, not after.
3. **Is `nocturia`-vs-`urinary_frequency` interference worth measuring directly?**
   A fourth arm — those two signals merged and nothing else — would isolate it
   from the other four. It is 45 minutes of GPU and it is a different ticket's
   question, but it is cheap enough to be worth an explicit no.
4. **What happens if task 1 says the numbers do not transfer?** Worth deciding the
   response before seeing it. A large drop makes ticket 6 (clinical-language
   nulls) the priority over anything else on the roadmap, and this ticket's
   remaining four tasks become a smaller deal than they look today.

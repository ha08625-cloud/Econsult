# Implementation Plan: Multi-symptom training expansion (phase 1)

**Related:** `arch_training.md` (the dataset — sections 3, 8, 10 and 12 are
prerequisites), `arch_encoder_training.md` (the trainer — sections 4a, 5 and 9),
`planned_updates/encoder_next_steps.md` (the real-text evaluation this feeds).

This plan covers **three tasks that are unblocked today**. It deliberately stops
short of joint multi-head training, which is scoped in "What comes next" at the
end and depends on `arch_training.md` section 12.5.

---

# Orientation for someone new to this

Everything trained so far has been one signal: `fever_present`. The fragment
libraries for five other symptoms — dysuria, urinary frequency, nocturia, flank
pain, haematuria — already exist and are already in the manifest, but nothing
has ever consumed them. The training tooling takes a `--signal` flag that
defaults to `fever_present`, and no one has ever passed anything else.

The goal of the wider piece of work is a model that reads a patient's free text
and answers all seven of the ruleset's encoder questions at once, rather than
one head per training run. The interesting open question along the way is
whether **training on other symptoms' confounders makes fever detection better
or worse**: the "whose symptom is this / when did it happen / is this literal"
skills that the hard `null` sub-classes test are not fever-specific, so an
encoder that has seen them across six symptoms may generalise better — or may
simply interfere with itself.

This plan does not answer that question. It builds the three things that have to
be true before the question can be asked honestly.

---

# Plan

1. **Task 1 — Folder restructure.** Introduce a condition layer under
   `data/synthetic/`, so "which files are about UTI" is answerable by looking.
   Verified dataset-neutral.
2. **Task 2 — Generalise the filler lint to every signal.** Today the lint
   checks filler libraries for *fever* language only. Every later step relies on
   filler being silent about all six signals, and nothing checks it.
3. **Task 3 — Six single-signal training runs.** Run the existing pipeline once
   per signal. No code changes. Produces the per-symptom baselines that any
   later joint run has to be compared against.

**Landing order matters and is 1 → 2 → 3.** Task 1 first so tasks 2 and 3 are
written against the final layout. Task 2 before task 3 because task 3's reports
should carry the generalised lint's output, and because task 2 is the
precondition for the structural-null union in the follow-on work.

---

# Scope

**In scope:** the folder restructure; the cross-signal filler lint; six
single-signal dataset generations and fine-tune runs; the report caveat for
untagged libraries; the architecture-doc updates that go with all three.

**Out of scope, deliberately:**

* **Joint multi-head training.** Scoped at the end of this document. It is the
  point of the exercise, and it is a separate ticket because it needs a merge
  step, per-head margin selection and a report shape that does not exist.
* **Label vectors and declared silence** (`arch_training.md` 12.5). Task 2 is
  the lint half of 12.5 and nothing else. No manifest schema change.
* **Cluster-tagging the four untagged libraries.** See "The untagged-library
  caveat" below — this plan documents the problem and quantifies it, and does
  not fix it.
* **Splitting `expectations.txt`** into generic and UTI-specific halves. Task 1
  moves files without changing what any library contains, because splitting a
  filler library changes the emitted dataset. See Task 1 design decision 3.
* **`recent_uti_present`.** The ruleset declares seven `send_to_encoder`
  signals; six have libraries. Nothing here closes that gap.

---

# Design Decisions

### DD1 — Task 1 is a pure move, and it is verified rather than asserted

Nothing in the generator keys off a library's *path*. `fragment_id` is
`{library_name}:{sha1(text)}`, `cluster_id` is `{library_name}:{tag}`, fold
assignment hashes the cluster key, and `_draw_filler` picks uniformly over
library *names*. Only the manifest's `file` values change.

This was checked, not reasoned about: the tree was restructured in a scratch
copy, the manifest paths rewritten, and `fever_present` and `haematuria_present`
train splits regenerated at the same seed. Both came out **byte-identical** to
the pre-move output. Task 1's acceptance criterion is that this stays true.

### DD2 — Symptom-agnostic filler lives outside the condition folder

`tangents`, `justifiers` and `emotional` contain zero condition-specific
language (verified by lexicon scan: 0 hits out of 270 lines). They are reusable
by any future condition and belong at the top level. `uti_speculation` is 36/40
UTI-specific and belongs under the condition.

`expectations.txt` is the awkward one: 26 of its 100 lines are UTI-specific
(urine culture, cystoscopy, trimethoprim, PSA). It stays whole, at the top
level, in Task 1 — see DD3.

### DD3 — Correct the structure now, correct the contents later

Splitting `expectations.txt` into two libraries is **not** dataset-neutral.
`_draw_filler` picks a library uniformly and then a fragment within it, so
going from five filler libraries to six changes every example's filler
distribution, which changes every generated dataset, which makes Task 3's
numbers incomparable to the `fever_present` numbers already on file
(`reports/encoder_training/fever_present.model_comparison.md`).

So Task 1 gets the *layout* right and leaves the *contents* alone. The
`expectations` split belongs with the joint-training ticket, which bumps
`GENERATOR_VERSION` and regenerates everything anyway. Task 1 records this as a
known wart in the doc rather than leaving it to be rediscovered.

### DD4 — The untagged-library caveat is reported, not fixed

`arch_training.md` section 3 records that only the `fever_null` and
`dysuria_null` libraries carry cluster markers, on the grounds that every other
library "was written as independent ideas, so effective n equals fragment count
there". That claim is load-bearing — it is what licenses reading
`urinary_frequency`, `nocturia`, `flank_pain` and `haematuria` numbers at face
value — and there is now evidence worth weighing against it.

The existing cross-split near-duplicate report (fold 0, ratio ≥ 0.6, which its
own docstring calls a lower bound) finds:

| signal | cross-split near-dup pairs | lines | rate |
|---|---|---|---|
| `flank_pain` | 17 | 243 | 7.0% |
| `nocturia` | 8 | 351 | 2.3% |
| `fever` | 8 | 463 | 1.7% |
| `dysuria` | 6 | 256 | 2.3% |
| `urinary_frequency` | 6 | 302 | 2.0% |
| `haematuria` | 5 | 225 | 2.2% |

`fever` and `dysuria` are *residuals* — their hand-tagged twins are already
forced into the same split and so cannot appear here at all. The four untagged
signals are raw. `flank_pain` at 7% is the outlier that most deserves a
re-read, and by inspection some untagged libraries do contain families that
read as one idea: `haematuria_true` describes urine colour by comparison to a
drink five times over (rosé, ribena, cranberry, plum, red wine).

**Consequence:** the four untagged signals will post *better* numbers than
fever, partly for reasons that have nothing to do with the symptom, and
`dysuria` will post worse numbers than it should because it is the only library
honestly clustered throughout. Task 3 makes this visible in the report header
instead of leaving a reader to reconstruct it.

**This does not touch the headline question.** Whether cross-symptom exposure
helps fever is a fever-vs-fever paired comparison on identical fever clusters,
and fever's `null` libraries are already tagged. The tagging debt corrupts the
other five symptoms' *absolute* numbers only.

### DD5 — Task 3 changes no generation settings

Every signal runs at exactly fever's recipe: 10,000/2,000/2,000, `15/25/60`,
`--null-ambiguous-ratio 0.5`, five folds, base seed 42, salt 0. Two reasons.
The per-symptom numbers are only interpretable against the fever run on file if
the recipe is identical; and because `run_seed` does not depend on the signal,
an unchanged recipe is what makes the six datasets mergeable later without
regeneration (see "What comes next").

---

# Task 1: Folder restructure

## A. State of the world

Nothing in this plan has been built. `data/synthetic/` is flat: `symptoms/`,
`filler/`, `drafts/`, `generated/`. The tree has only ever held one condition
(UTI), so nothing distinguishes "filler that works for any condition" from
"filler that is about urinary problems". A second ruleset would have nowhere to
put its libraries.

## B. Files and deliverables

**Moves (git mv, contents untouched):**

```
data/synthetic/
  manifest.json
  filler/                          condition-agnostic, shared by every condition
    tangents.txt                   (unmoved)
    justifiers.txt                 (unmoved)
    emotional.txt                  (unmoved)
    expectations.txt               (unmoved — see DD3)
  conditions/
    uti/
      symptoms/                    ← moved from data/synthetic/symptoms/
        fever/ dysuria/ urinary_frequency/ nocturia/ flank_pain/ haematuria/
      filler/
        uti_speculation.txt        ← moved from data/synthetic/filler/
  drafts/                          (unmoved)
  generated/                       (unmoved, git-ignored)
```

**Edits:**

* `data/synthetic/manifest.json` — the `file` value of all 37 symptom libraries
  and `uti_speculation`. **No `name` value changes.**
* `documentation/arch_training.md` — the section 3 tree diagram (lines ~85–96)
  and every path in the section 3 library table. The table is machine-checked
  (see below), so this is not optional.
* `documentation/file_structure.md` — the `data/synthetic/` entry.
* `tests/test_synthetic_recombination.py` — `_NON_LIBRARY_DIRS` and the
  manifest/doc merge guards, if they assume a flat tree.

**Not edited:** `.dockerignore` (`data/synthetic/generated/` is unchanged),
`scripts/` (no path constants below the manifest), `app/` (never reads this).

## C. Instructions

1. Do the moves with `git mv` so history follows the files.
2. Rewrite the manifest `file` paths. Change nothing else in the manifest —
   particularly not `name`, which is what every derived identifier is built
   from.
3. Update the section 3 table in `arch_training.md`. There is a test
   (`_DOC_ROW` in `tests/test_synthetic_recombination.py`) that parses rows of
   the form ``| `symptoms/fever/fever_true.txt` | 96 | …`` and asserts the path
   resolves and the line count matches, so a missed row fails CI rather than
   drifting silently. Update the tree diagram above the table too.
4. Add a short note to the section 3 prose recording that `expectations.txt`
   holds ~26 UTI-specific lines and stays in the shared filler for now, with
   DD3's reason.
5. **Prove the move is dataset-neutral.** Before the move, generate
   `fever_present` and one other signal (`haematuria_present`) at
   `--split train --count 800 --seed 42 --folds 5 --fold 0 --split-salt 0`.
   After the move, regenerate with the same flags and `diff`. Both must be
   byte-identical. If they are not, something keyed off a path that should not
   have — stop and find it rather than accepting the new output.
6. Run the touched tests: `tests/test_synthetic_recombination.py`. Typecheck.
   Do not run the full suite.

**Python 3.12 or later.** `recombine.py` uses PEP 695 generics, so on 3.11 the
whole package dies at import with a `SyntaxError` that reads like a broken
checkout.

---

# Task 2: Generalise the filler lint to every signal

## A. State of the world

Task 1 is done; the tree has a condition layer and generation output is
unchanged. This task is the lint half of `arch_training.md` section 12.5, and
nothing else from 12.5 — no manifest schema change, no label vectors, no
per-fragment silence declarations.

`lint.py` has `FEVER_LEXICON` (16 terms) and `filler_lexicon_hits`, which reports
filler fragments containing fever language. There is a test behind it
(`test_no_filler_fragment_contains_fever_language`) with an empty baseline, plus
two tests that stop the check rotting: one asserts the lexicon actually matches
real fever text, one asserts word boundaries keep `lithotripsy`/`photos`/`shot`
from tripping on "hot".

**Why this matters beyond tidiness.** A filler fragment can be paired with
anything, including an example labelled `null` purely because of its structure.
Fever language in filler makes that label a lie. Section 9 of `arch_training.md`
already records that `filler` carries "blood test" and "blood pressure tablets"
and that `tangents` carries sleep-disturbance lines — both are one honest reading
away from being haematuria and nocturia leaks, and today nothing checks either.
The follow-on work (labelling one structural null `null` for all six signals at
once) is not safe until this exists.

## B. Files and deliverables

* `scripts/synthetic_data/lint.py` — five new lexicons; `filler_lexicon_hits`
  generalised to report which *signal* each hit is against.
* `scripts/synthetic_data/__main__.py` — the `--lint` report section.
* `tests/test_synthetic_recombination.py` — extend the three existing tests to
  cover all six signals; one baseline set per signal.
* `documentation/arch_training.md` — section 8 (the lint) and the "Cross-signal
  silence" subsection of section 3.

## C. Instructions

1. Add a lexicon per signal alongside `FEVER_LEXICON`: `DYSURIA_LEXICON`,
   `URINARY_FREQUENCY_LEXICON`, `NOCTURIA_LEXICON`, `FLANK_PAIN_LEXICON`,
   `HAEMATURIA_LEXICON`. Keep them keyed by signal in one mapping so the report
   can name the signal a hit is against. Word-boundary matching throughout —
   the existing `_compile` already does this and it is the only thing keeping
   the check from failing on day one against clean data.
2. Generalise `filler_lexicon_hits` to return hits tagged with the signal.
   Keep the report grouped by signal; a single undifferentiated list would not
   say which label a hit falsifies.
3. **Expect this to fail on first run, and treat that as the point.** Known
   candidates: `expectations.txt` has ~26 lines of urinary/renal language
   (urine culture, cystoscopy, dipstick, bladder), `uti_speculation.txt` is
   36/40 UTI-specific, and `tangents.txt` carries sleep-disturbance lines that
   a nocturia lexicon may reach.
4. **Resolve each hit deliberately, and record the reasoning.** Three outcomes
   are legitimate and they are not interchangeable:
   * *the lexicon is too broad* — "blood test" is not haematuria, "kidney scan"
     is not flank pain. Narrow the lexicon and add the phrase to the
     substring-trap test so it stays narrow.
   * *the line is genuinely a leak* — move it out of filler or rewrite it.
   * *the line is a known, accepted exception* — put it in that signal's
     baseline set with a comment saying why, exactly as
     `FILLER_PURITY_BASELINE` does today.

   Do **not** clear hits by widening the baseline wholesale. An empty lexicon
   and a full baseline both make the test pass and neither checks anything.
5. Add the `flank_pain_false` exception already recorded in `arch_training.md`
   section 3 — three lines resolve the flank question by contrasting it against
   a urinary one ("it's just uncomfortable when I wee"), asserting
   `dysuria_present: true` inside a library that will eventually be declared
   silent on dysuria. This lint will not catch it (it checks filler, not signal
   libraries) but the doc note should point at the ticket that will.
6. Run `tests/test_synthetic_recombination.py`. Typecheck. Update section 8 of
   `arch_training.md` with the final per-signal baseline counts.

---

# Task 3: Six single-signal training runs

## A. State of the world

Tasks 1 and 2 are done: the tree has a condition layer, and the filler libraries
are checked silent against all six signals. **No code changes are needed for
this task** — `--signal` is already a flag on `generate-folds`, `baselines`,
`probe`, `finetune` and `compare-models`, and it already defaults to
`fever_present`. The only code deliverable is the report caveat in step 5.

`roberta-base` is the base model. The three-way comparison on file
(`fever_present.model_comparison.md`) put it at 92.9% decisive accuracy
[90.6, 95.0] against Bio_ClinicalBERT's 84.1% and bert-base-uncased's 85.8%, so
the encoder question is settled for now and this is a single-encoder Arm B
sweep.

## B. Files and deliverables

* `data/synthetic/generated/folds/<signal>.fold{0..4}.{train,val,test}.jsonl`
  for all six signals (git-ignored).
* `reports/encoder_training/<signal>.arm_b_finetune.{json,md}` × 6. Commit the
  JSON always; commit the markdown for all six, since these are the reference
  numbers everything later is compared against.
* `models/encoder/<signal>/arm_b_finetune/` × 6 — `metadata.json`, per-fold
  head and decision artefacts. The ~440MB `.pt` weights stay git-ignored.
* `scripts/encoder_training/report.py` — the untagged-library caveat.
* `documentation/arch_training.md` section 10, `arch_encoder_training.md`
  section 9 — updated to say six signals have been trained.

## C. Instructions

1. `smoke-cuda` first on whatever machine this runs on. `torch.cuda.is_available()`
   returns `True` on a wheel that cannot launch a kernel, and when it fails the
   fix is a different torch wheel and never a code change. Then `smoke`.
2. For each of the six signals, at **exactly** fever's settings (DD5):

   ```
   python -m scripts.encoder_training generate-folds  --signal <signal> --folds 5
   python -m scripts.encoder_training finetune --signal <signal> --folds 5 \
       --base-model roberta-base
   ```

   `finetune` reports Arm B, Arm A and the baselines in one report by default;
   leave that alone, since the baselines are what say whether a transformer
   earned its keep on each symptom.
3. **Expect `dysuria_present` and `haematuria_present` to be the awkward ones.**
   Dysuria has the fewest decisive clusters of any signal (182, against fever's
   418) because it is the only fully twin-tagged library set. Haematuria has
   five libraries and only three `null` sub-classes, so `_check_pools` is
   satisfied but the ambiguous pool is thin; watch for `PoolExhaustedError` at
   10,000 examples and report the count rather than quietly lowering it.
4. Record decisive accuracy, macro-F1 and the per-sub-class `null` recall table
   for each signal. Do not rank the six against each other in prose without
   restating DD4 — that ranking is substantially an artefact of which libraries
   are cluster-tagged.
5. **Add the untagged-library caveat to the report.** In `report.py`, compute
   per-library cluster-tag coverage (tagged lines / total lines) from the
   fragments already loaded, and:
   * add a `cluster_tag_coverage` block to the report header;
   * print a warning above the headline table when any library behind the run
     has 0% coverage, saying in one sentence that untagged libraries treat every
     line as an independent idea, that `eff n` is therefore an upper bound, and
     that intervals on those slices are narrower than the truth.

   Keep it in `report.py` (stdlib, covered by CI's unit job), not in the
   training path.
6. Targeted checks only: typecheck, and run the test files for whatever was
   touched (`tests/test_encoder_training_metrics.py` for the report change).
   Skip the full suite and skip `npm run build`; CI's unit job is the gate.

**Rough cost:** generation is seconds per run. Arm B is ~2 minutes per fold on a
12GB card, so six signals × 5 folds ≈ 1 hour of GPU, plus Arm A and the
baselines, which are near-free once the embedding cache exists.

---

# What comes next (not in scope, recorded so the sequencing is visible)

**Ticket 4 — Merge and joint multi-head training.** Merge the six per-signal
fold datasets into one and train all six heads over a shared encoder with the
masked loss. This is what actually answers "does exposure to other symptoms'
confounders help or hurt fever".

Three findings from planning it, recorded because they are not obvious and each
one saves a wrong turn:

* **The merge needs no regeneration.** Fold assignment (`fold_bucket`) is a pure
  hash of the cluster key and salt and does not know about signals, so the same
  filler fragment lands in the same fold in all six runs and cluster
  disjointness survives concatenation for free. Verified further: because
  `run_seed` ignores the signal, the six runs' **structural nulls are
  byte-identical, example-for-example** — the only text six per-signal datasets
  share is exactly their structural nulls. Merging is concatenate, drop five of
  the six copies, union the labels onto the survivor. The merge tool should
  *assert* that identity rather than assume it: if anyone ever adds the signal
  to the seed derivation, six divergent structural-null sets would dedupe to
  nothing and nothing downstream would notice.
* **Union the structural nulls' labels; do not multiply them.** A structural
  null is filler only, so it is legitimately `null` for all six signals at once.
  Labelled six ways it produces 45,000 examples with 60,000 labelled positions
  and each head sees exactly fever's 15/25/60 mix — identical gradients to naive
  6× concatenation, 25% fewer forward passes, and each head's prior preserved
  exactly, which is what makes the fever comparison clean. This is what Task 2's
  lint licenses: asserting `null` for six signals means asserting the filler is
  silent about six signals.
* **A three-armed comparison, not two.** Merging six 10k datasets gives the
  encoder 6× the gradient steps, so a fever movement would confound diversity
  with step count. Needs: A1 fever-only at 10k (Task 3's output), A2 fever-only
  at 60k (same 418 clusters, 6× the steps — isolates step count), A3 joint at
  60k. A3 vs A2, paired McNemar on the fever test slice, is the answer.

**Ticket 5 — Realistic held-out evaluation.** `data/realistic/uti1_holdout.labels.tsv`
holds 67 hand-written realistic submissions labelled across all seven signals —
402 labelled decisions — and no tooling reads it. Worth pulling forward rather
than leaving until last, because it is the only measurement that says whether a
recombination score means anything. Be clear-eyed about power: fever is 9 true /
9 false / 49 null there, so the fever interval will be roughly ±20 points.

It will not separate a 2-point difference. It will catch a much larger effect
that the recombination test set structurally cannot: every fever-`null` example
today pairs no-fever-language with **bland non-clinical filler** — weather,
parking, the MOT — so a model can score well by learning "clinical-sounding
symptom language ⇒ not null". Real submissions are dense with clinical language
about other symptoms (dysuria is `true` in 56 of the 67). If that shortcut
exists, this is where it shows.

**Ticket 6 — Multi-symptom recombinations** (`arch_training.md` 12.2, 12.3,
12.5). One example carrying several supervised keys — `{"dysuria_present": true,
"fever_present": null, "haematuria_present": null, …}` — which was always the
intended destination and is the thing that closes the gap above properly: a
dysuria sentence labelled `fever_present: null` is a *hard* structural null for
fever, one with clinical language in it. Needs the full 12.5 machinery
(declared silence per library, compatibility checking on the label vector), and
it is where the `expectations.txt` split from DD3 and the `GENERATOR_VERSION`
bump belong.

Note the prior consequence when it lands: the fever head would see ~93% `null`
rather than 60%, which is a much larger ask of a decision margin than the
current mix and may force the loss reweighting `arch_encoder_training.md`
section 8 deliberately avoided. **Structural nulls should shrink as this grows** —
patients rarely submit free text with no clinical content at all, so the
filler-only structural null is the least realistic example type in the dataset,
and ticket 6's examples do its job better.

**Ticket 7 — Cluster-tag the four untagged library sets** (DD4). Prioritise by
the cross-split near-duplicate report: `flank_pain` first at 7%. Cheap to defer,
because it changes no code and invalidates no design — it only means the four
signals' absolute numbers are upper bounds until it lands.

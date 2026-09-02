# Task 7 run sheet: the arms, the run and the report

Task 7 of `procedural_fragment_generation_implementation.md`. Tasks 1–6 are
merged; `--declarative-share` exists end to end and no measured arm has used it.

This file is the run sheet, not the plan. The plan's Task 7 section is the
authority on *why*; this is what to do, in order, with the decisions already
made. **The console is the intended route** — see "Running it from the console".
The terminal equivalents are given for each step because they are what the
console types, and because a step that fails is easier to debug directly.

---

## The gate (DD18) — open

The plan says this task must not start before the sixty-seven real submissions
are labelled and their provenance resolved. **Both are now true**, which was not
the case when the plan was written:

* `data/realistic/uti1_holdout.labels.tsv` holds all 67 rows with every cell
  filled — no blanks, which `data/realistic/README.md` records as the correct
  state rather than an omission.
* Provenance is resolved and documented: **the labels were proposed by Claude
  and reviewed by the maintainer.** That is a real limitation and
  `data/realistic/README.md` requires it to be restated in every report using
  the set. Put it in this one.

So Task 7 runs in full, real-set arm included.

**Read `data/realistic/README.md` before the first run.** Rule 2 (the set
selects nothing) and rule 3 (scored once per candidate model, and the number is
recorded, including the bad ones) are the two a run can quietly break.

---

## The design: a 2×2, not the plan's 2×1

The plan asks for two arms differing only in `--declarative-share`. **Run a 2×2
instead**, and the reason is in the committed companion reports:

| signal | `null -> true` at companion 0 | at companion 0.5 |
|---|---|---|
| `fever_present` | 84.1% | **4.5%** |
| `flank_pain_present` | 87.5% | 17.7% |
| `haematuria_present` | 80.4% | 12.5% |
| `dysuria_present` | 72.7% | 23.6% |

Companions already fixed the invented-symptom problem almost completely. A
declarative arm measured only at companion share 0 starts from that same bad
baseline, so **any improvement it shows may be the mechanism companions already
deliver, arriving by a second route** — more clinical language about other
signals in the text. Prediction 3 would come out true and mean nothing about
whether declarative fragments are worth shipping.

`generate-folds` now forwards `--companion-share` as well, so the combination is
expressible. The four cells:

| cell | companion | declarative | what it is |
|---|---|---|---|
| **A** | 0.0 | 0.0 | the control; byte-identical to a pre-flag tree |
| **B** | 0.0 | 0.3 | the plan's Arm D — declarative alone |
| **C** | 0.5 | 0.0 | companions alone; **replicates the known result at version 4** |
| **D** | 0.5 | 0.3 | both — the cell that decides whether this ships |

**D against C is the question.** B against A is the mechanism check, and C
against the committed companion numbers is a free replication that will catch a
version-4 regression if there is one.

Fifth cell **R** at companion 0.5, declarative 0.6, for prediction 6 — the only
cell that can find the register failure DD8 argues about. If R beats D on real
text, DD8's whole argument is wrong, and that is the most valuable thing this run
could find. It has its own console entry and its own report directory, so it can
be run after the 2×2 without disturbing it.

---

## Decisions already made, so they are not made twice

| decision | value | why |
|---|---|---|
| Signals | the six trainable ones | `recent_uti_present` is out by DD9 and has no trained head anyway |
| Folds | 5 | every committed run |
| Base model | `roberta-base` | the console default and what the committed reports used |
| Weights | `--no-weights` | ~440MB × 5 folds × 6 signals × 4 cells ≈ 53GB, none committed, all regenerable |
| Holdout | on | never `--no-holdout` here; the real set is the point |
| Control, Arm A | skipped | halves the wall clock; the 2026-08-31 noise sweep did the same |

**The flags are identical across cells** — they are baked into the console
entries, which is most of why the console is the right route here. Two shares
vary and nothing else.

---

## Running it from the console

### Start it

Double-click `tools/train-gui.bat` (Windows) or run `tools/train-gui.sh`. It
activates the `econsult-ml` conda environment, refuses to start a second console
on a busy port, and opens `http://127.0.0.1:8765/`.

**Closing the window stops the console and any run it started.** A cell takes
about an hour; leave it open.

If it says fastapi and uvicorn are not importable, `pip install -r
requirements-ml.txt` in that environment.

### The console entries

The catalogue has six new runs. The four sweep entries take **Companion
share** and **Declarative share** dropdowns, and the two together name the cell;
the two comparison entries have fixed cell lists and no dropdowns.

| entry | what it does |
|---|---|
| `Declarative sweep: generate folds for one signal` | one signal, one cell. Stdlib only, no GPU, about a minute |
| `Declarative sweep: generate folds for all six signals` | the whole cell's data, six steps, one run |
| `Declarative sweep: train and score one signal` | Arm B on one signal, five folds, ~10 min |
| `Declarative sweep: train and score all six signals` | the whole cell, ~1 hour |
| `Declarative sweep: compare the four cells` | trains all four and writes one report per signal, ~4 hours |
| `Declarative sweep: compare 0.3 against 0.6` | the register arm, three cells at companion 0.5, ~3 hours |

Every directory is built from both shares —
`data/synthetic/generated/decl/c0.5-d0.3`, and the matching `reports/` and
`models/` paths — so **no two cells can overwrite each other**. That is asserted
by `tests/test_training_gui.py::test_every_declarative_cell_writes_to_its_own_directories`,
because the alternative is a comparison of a tree against itself with nothing
raised anywhere.

### The order to click

For each of the four cells, in this order:

1. **Run `generate folds for all six signals`** with the cell's two shares.
   A minute. No GPU.
2. **Check the card's command preview** before clicking Run: it re-renders as
   you change the dropdowns and shows the exact argv. Confirm the two `--*-share`
   values and the `c…-d…` directory match the cell you meant.
3. **Run `train and score all six signals`** with the *same* two shares. About
   an hour. The Live log streams it; the verdict chip shows the step.
   **Skip this step if you are going to run `compare the four cells`** — that
   entry trains every cell itself, and doing both trains everything twice.
4. When it finishes, **Save this run to a branch** in the Git section. That
   copies the log and the run manifest — every step's argv, exit code, timings
   and the sha it ran at — into `reports/training_runs/<run_id>/` along with the
   reports, and pushes a branch. Cite that from the write-up instead of
   hand-transcribing a command matrix, which is what the 2026-08-31 noise sweep
   had to do.

**The console runs one thing at a time** and disables every Run button while
busy, so it cannot contend with itself for the GPU. That is a feature here: four
cells back to back is roughly four hours and needs no supervision beyond
noticing a red verdict.

### Preflight, once

Run **`CUDA smoke test`** first on a fresh machine or after any driver or wheel
change. Ten seconds, and it fails loudly rather than an hour into a training run.

---

## The terminal equivalents

What the console types, if you would rather drive it directly.

**Generate one cell** (companion 0.5, declarative 0.3 shown):

```bash
for sig in fever_present dysuria_present flank_pain_present \
           haematuria_present nocturia_present urinary_frequency_present; do
  python -m scripts.encoder_training generate-folds \
    --folds 5 --signal "$sig" \
    --companion-share 0.5 --declarative-share 0.3 \
    --out-dir data/synthetic/generated/decl/c0.5-d0.3
done
```

**Train one cell:**

```bash
for sig in fever_present dysuria_present flank_pain_present \
           haematuria_present nocturia_present urinary_frequency_present; do
  python -m scripts.encoder_training finetune \
    --folds 5 --signal "$sig" \
    --data-dir   data/synthetic/generated/decl/c0.5-d0.3 \
    --report-dir reports/encoder_training/decl/c0.5-d0.3 \
    --models-dir models/encoder-decl/c0.5-d0.3 \
    --base-model roberta-base \
    --determinism strict --train-seed 1234 \
    --no-weights --no-control --no-probe
done
```

`data/synthetic/generated/` is gitignored, so the trees are not committed and
are regenerable from the pinned seeds.

---

## Before training: two checks worth the five minutes

### Prediction 1 — byte-identity at zero

Everything downstream rests on it, and it costs no GPU:

```bash
python -m pytest tests/test_synthetic_recombination.py -q \
  -k "golden or inert_against_a_pool"
```

`test_default_invocation_still_produces_the_golden_dataset` pins the default
output against a recorded digest;
`test_declarative_share_zero_is_inert_against_a_pool_that_could_serve_it` proves
the draw is *skipped* rather than taken with probability zero, against a manifest
with a populated declarative pool.

Both use fixture manifests, so they prove the mechanism, not the real manifest's
output. For that, diff cell A against a tree generated from the commit before
the library entered the manifest:

```bash
git worktree add /tmp/pre-decl f653832^
cd /tmp/pre-decl && python -m scripts.encoder_training generate-folds \
  --signal fever_present --folds 5 --out-dir /tmp/pre-decl-folds
cd - && diff -r /tmp/pre-decl-folds data/synthetic/generated/decl/c0.0-d0.0 \
  --exclude='*.stats.json'
```

The JSONL must match exactly. Sidecars are excluded because
`generator_version` legitimately moved 3 → 4; diff them separately and confirm
that field is the only difference. **If the JSONL differs, stop** — DD4's pool
refactor changed a pool, and that is a bug rather than a result.

### The cells are the cells

A mis-set dropdown produces a run that succeeds and answers a different
question:

```bash
python - <<'EOF'
import json, pathlib
for cell in ("c0.0-d0.0", "c0.0-d0.3", "c0.5-d0.0", "c0.5-d0.3"):
    p = pathlib.Path(f"data/synthetic/generated/decl/{cell}"
                     "/fever_present.fold0.train.jsonl.stats.json")
    if not p.exists():
        print(f"{cell:12} not generated"); continue
    s = json.load(p.open())
    zero = s["companions"]["count_by_label_mode"]["null_structural"]["0"]
    print(f"{cell:12} companion {s['requested']['companion_share']} "
          f"declarative {s['requested']['declarative_share']} "
          f"| decl pool {s['split_pool_sizes']['declarative_positive']} "
          f"| filler-only nulls {zero}")
EOF
```

Each cell must report the shares you meant, at generator version 4. Two things
to look at:

* **The declarative pool is non-empty in every cell, A included** — the pool is
  built from the manifest regardless, and the *share* is what decides whether it
  is drawn from. So a non-zero pool on A is correct and proves nothing. What
  would be wrong is a **zero** pool on B or D: the library would not be loading,
  and the cell would silently be a duplicate of A or C.
* **Filler-only structural nulls** should read 3064 at companion 0 and **1118**
  at companion 0.5 — 1,118 is the figure the plan's prediction 2 was written
  against, so it doubles as a check that the companion passthrough reproduces
  the known measurement rather than something new.

---

## Reading the result

The report renders both numbers; nothing here needs a bespoke script.

**Fold-pooled decisive accuracy**, per signal per cell:

```bash
grep -H -E '^\| `arm_b_finetune` \| finetune' \
  reports/encoder_training/decl/*/*_present.arm_b_finetune.md
```

**The real set**, which is what the ticket exists for. Each per-signal report
carries a `## The real-text holdout` section whose first table is the headline:

```bash
for f in reports/encoder_training/decl/*/*_present.arm_b_finetune.md; do
  echo "=== $f"
  sed -n '/^### `null -> true` on real text/,/^###* /p' "$f" | head -12
done
```

If you trained the cells one at a time, each file's table has **one** model
column and you are reading four files side by side. `declarative-compare` writes
one report with a column per cell instead — see below.

**`null -> true` is the invented-symptom rate**: how often the model answers
`true` about a signal the submission never mentioned, as the mean across folds.
It is printed above the accuracy tables deliberately, because real-text accuracy
is dominated by the `null` cells a model scores by saying nothing.

Note the two `n`s the report prints side by side. The recombination test slice
is thousands of examples over hundreds of clusters; the holdout is 67
submissions at one observation each. **A difference between cells on the holdout
has to be large before it is real** — read the intervals, not the point
estimates.

### The comparison report

`declarative-compare` puts the cells in one report per signal, columns in
`--cell` order, stem `<signal>.declarative_comparison`:

```bash
python -m scripts.encoder_training declarative-compare --folds 5 \
  --cell data/synthetic/generated/decl/c0.0-d0.0 \
  --cell data/synthetic/generated/decl/c0.0-d0.3 \
  --cell data/synthetic/generated/decl/c0.5-d0.0 \
  --cell data/synthetic/generated/decl/c0.5-d0.3 \
  --report-dir reports/encoder_training/decl/comparison \
  --models-dir models/encoder-decl/comparison \
  --base-model roberta-base --determinism strict --train-seed 1234 --no-weights
```

or the **`compare the four cells`** console entry, which is the same command.

**It trains all four cells itself** — about four hours — rather than reading the
per-cell runs off disk, for the reason `joint-compare` re-runs A1: the reports
hold no per-example predictions, so anything comparing two cells can only be
computed inside the invocation that produced both. Running the four
`train and score` entries first and then this is training everything twice. Pick
one route:

* **The comparison entry alone** if you want the side-by-side report. Generate
  the four cells, then run it. This is the shorter path.
* **The four `train and score` entries** if you want them one at a time — a cell
  a day, say — and are content to read four report files side by side.

`companion-compare` cannot do this job: it wants merged `joint6` trees, and it
refuses two trees that share a `--companion-share`, which cells A and B do and
cells C and D do.

**What the report tells you, and what it does not.** Every cell holds different
texts under the same example ids, so no cell pairs with any other on the
synthetic test set: every McNemar row is a recorded skip, deliberately, and a
reader who takes those skips for a missing result has read it backwards. The 67
real-text submissions are the same for every cell and are the shared instrument.
The first `--cell` is the reference — its tree is what the report's test slice,
fold partition and cluster checks describe.

Guards, all of which fire before a tree is loaded: fewer than two cells, a
repeated directory, two cells at the same two shares, a cell whose shares cannot
be read from its sidecars, a path that does not exist, and every cell at
declarative 0. The shares are read back from each cell's own sidecars rather than
from the flags, so a directory named after the wrong cell cannot mislabel a
column.

For the register arm:

```bash
# --cell c0.5-d0.0 --cell c0.5-d0.3 --cell c0.5-d0.6
```

or the **`compare 0.3 against 0.6`** console entry.

---

## Writing down what the predictions did

All six, whatever they say, including the ones that went the wrong way.

1. **Byte-identical at `P = 0`** — from the checks above.
2. **Structural nulls fall further at a given companion share** — now testable,
   because the cells exist. Compare filler-only nulls in D against C.
3. **Invented-symptom rate improves**, most where the inventory has most
   phrases, least for `flank_pain_present` — B against A *and* D against C. The
   second comparison is the one that matters.
4. **`false` recall improves most** — from the `per_class` block.
5. **Near-duplicate pairs in the hand-written libraries do not move** —
   `python -m scripts.synthetic_data --lint`.
6. **`P = 0.6` scores worse than `P = 0.3` on real text** — cell R, via the
   register comparison.

---

## The report

`reports/encoder_training/<date>-declarative.md` plus its plain-English
companion, following the 2026-08-31 noise pair. Then update
`documentation/arch_training.md` section 10.

Four things it must say and will not say by itself:

* The holdout labels were **proposed by Claude and reviewed by the maintainer**;
  labeller and model share an architecture and could share a blind spot.
* These cells are **version 4** and not comparable with the version-3 companion
  arms or anything earlier — cell C is the bridge, and whether it reproduces the
  version-3 numbers is itself a finding.
* **Nothing generated is a hard case** (DD3). A dataset that grew in line count
  has not grown in difficulty; the per-sub-class counts are where to check that.
* Whether the decision rests on **D against C** or only on B against A. A reader
  comparing against the companion numbers will otherwise read a 2×1 as though it
  were the 2×2.

---

## What this run still cannot answer

* **Supervision per example.** At `--emit-signals primary` a fragment asserting
  three signals emits one key and the other two assertions are discarded.
  Banking them needs `--emit-signals all` and a `merge-folds` that accepts a
  multi-key tree (12.2). This measures claim density, not supervision.
* **Hard cases.** DD3 — the frames cannot produce a hedge, a metaphor or a
  third-party attribution, so the hard-case libraries remain the only source of
  those and `--null-ambiguous-ratio` still means what it meant.

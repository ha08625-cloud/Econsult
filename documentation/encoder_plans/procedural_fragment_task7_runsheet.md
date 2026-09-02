# Task 7 run sheet: the arms, the run and the report

Task 7 of `procedural_fragment_generation_implementation.md`. Tasks 1–6 are
merged; `--declarative-share` exists end to end and no measured arm has used it.

This file is the run sheet, not the plan. The plan's Task 7 section is the
authority on *why*; this is *what to type*, in order, with the decisions already
made.

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

So Task 7 runs in full, real-set arm included. Instruction 1's fallback — a
fold-pooled comparison with a note that the question was never asked — does not
apply.

**Read `data/realistic/README.md` before the first run.** Rule 2 (the set
selects nothing) and rule 3 (scored once per candidate model, and the number is
recorded, including the bad ones) are the two that a run can quietly break.

---

## Decisions already made, so they are not made twice

| decision | value | why |
|---|---|---|
| Signals | the six trainable ones | `recent_uti_present` is out by DD9 and has no trained head anyway |
| Arms | `P = 0.0` (Arm 0), `P = 0.3` (Arm D), `P = 0.6` (Arm R, optional) | plan instructions 2–4 |
| Folds | 5 | every committed run |
| Base model | `roberta-base` | the console default and what the committed reports used |
| Companion share | 0.0 | `generate-folds` does not expose the flag; see "What this run cannot answer" |
| Weights | `--no-weights` | ~440MB × 5 folds × 6 signals × 2 arms ≈ 26GB, none committed, all regenerable |
| Holdout | on (the default) | never pass `--no-holdout` here; the real set is the point |

**The flags must be identical across arms.** One flag, one difference. If you
drop `--no-probe` for Arm 0 you must drop it for Arm D too, or the comparison is
between two configurations rather than two datasets.

---

## Step 0 — preflight

```bash
git checkout main && git pull
python -c "import torch; print(torch.__version__, torch.cuda.is_available())"
python -m scripts.encoder_training smoke-cuda
```

`cuda.is_available()` must be `True`. Unlike the noise sweep there is no
`transformers` version to pin: both arms are trained here, together, on whatever
stack is installed, so they are comparable with each other. They are **not**
comparable with the 2026-08-19 companion arms (version 3) or anything earlier —
say so in the report.

---

## Step 1 — discharge prediction 1 before spending any GPU

Prediction 1 is that output is byte-identical at `P = 0`. It is cheap to check
and everything downstream rests on it.

```bash
python -m pytest tests/test_synthetic_recombination.py -q \
  -k "golden or inert_against_a_pool"
```

Two tests carry it: `test_default_invocation_still_produces_the_golden_dataset`
pins the default output against a recorded digest, and
`test_declarative_share_zero_is_inert_against_a_pool_that_could_serve_it`
proves the draw is *skipped* rather than taken with probability zero, against a
manifest that has a populated declarative pool.

**Both run against fixture manifests, so they prove the mechanism, not the real
manifest's output.** For the real-manifest assertion the plan asks for, diff
Arm 0 against a tree generated from the commit before the library entered the
manifest:

```bash
git worktree add /tmp/pre-decl f653832^
cd /tmp/pre-decl && python -m scripts.encoder_training generate-folds \
  --signal fever_present --folds 5 --out-dir /tmp/pre-decl-folds
cd - && diff -r /tmp/pre-decl-folds data/synthetic/generated/decl/arm0 \
  --exclude='*.stats.json'
```

Run this *after* Step 2 has written Arm 0. The JSONL must match exactly. The
sidecars are excluded because `generator_version` legitimately moved 3 → 4;
if you want to check them, diff them and confirm that field is the only
difference. **If the JSONL differs, stop** — DD4's pool refactor changed a pool
and that is a bug, not a result.

---

## Step 2 — generate the fold trees

One directory per arm; each holds all six signals' trees, since the fold
filename carries the signal.

```bash
for sig in fever_present dysuria_present flank_pain_present \
           haematuria_present nocturia_present urinary_frequency_present; do
  python -m scripts.encoder_training generate-folds \
    --signal "$sig" --folds 5 \
    --out-dir data/synthetic/generated/decl/arm0
done

for sig in fever_present dysuria_present flank_pain_present \
           haematuria_present nocturia_present urinary_frequency_present; do
  python -m scripts.encoder_training generate-folds \
    --signal "$sig" --folds 5 --declarative-share 0.3 \
    --out-dir data/synthetic/generated/decl/armD
done
```

Stdlib only, no GPU, a few minutes. `data/synthetic/generated/` is gitignored,
so these do not get committed and are regenerable from the pinned seeds.

Optional third arm (instruction 4 — the only arm that can find the register
failure prediction 6 describes):

```bash
# ... --declarative-share 0.6 --out-dir data/synthetic/generated/decl/armR
```

**Sanity-check before training**, or you may train two copies of one arm:

```bash
python - <<'EOF'
import json, pathlib
for arm in ("arm0", "armD"):
    p = pathlib.Path(f"data/synthetic/generated/decl/{arm}/fever_present.fold0.train.jsonl.stats.json")
    s = json.load(p.open())
    print(arm, "share:", s["requested"]["declarative_share"],
          "decl pool:", s["split_pool_sizes"]["declarative_positive"],
          "version:", s["generator_version"])
EOF
```

Arm 0 must read `0.0`, Arm D `0.3`, both at version 4, both with a non-empty
declarative pool. A zero pool on Arm D means the library is not being loaded and
the run would silently be a second Arm 0.

---

## Step 3 — train and score

Roughly two minutes a fold on a 12GB card, so ~10 minutes per signal per arm and
about two hours for the twelve runs. **Run them one at a time** — parallel runs
contend for the GPU.

```bash
for arm in arm0 armD; do
  for sig in fever_present dysuria_present flank_pain_present \
             haematuria_present nocturia_present urinary_frequency_present; do
    python -m scripts.encoder_training finetune \
      --signal "$sig" --folds 5 \
      --data-dir   "data/synthetic/generated/decl/$arm" \
      --report-dir "reports/encoder_training/decl/$arm" \
      --models-dir "models/encoder-decl/$arm" \
      --base-model roberta-base \
      --determinism strict --train-seed 1234 \
      --no-weights --no-control --no-probe
  done
done
```

On the three `--no-*` flags: `--no-weights` is not optional (disk).
`--no-control` and `--no-probe` drop the permuted-label negative control and
Arm A, roughly halving the wall clock; the 2026-08-31 noise sweep dropped both
plus baselines for the same reason. Baselines are kept because the majority-class
floor moves with the dataset and is the thing an arm has to beat. If you have the
GPU hours, drop all three `--no-*` except `--no-weights` — just do it for **both**
arms.

### Why not `companion-compare`?

It is the closest precedent — it is what produced the
`*.companion_comparison.md` reports, with both arms as columns of one table —
and **it cannot be reused here.** Two reasons, both hard:

* It requires *merged* `joint6` trees from `merge-folds`, not per-signal ones.
* It refuses two trees that share a `--companion-share`, on the grounds that
  they are two runs of one arm rather than two arms. Both declarative arms are
  at companion share 0.0, so it would raise `TrainError` before training.

So the arms are trained separately and compared across two report files, which
is what Step 4 does. A `declarative-compare` subcommand modelled on
`companion-compare` would give a single side-by-side report and is the nicer
route — but it is code work no Task 7 instruction asks for. Decide that before
Step 3, not after.

The holdout is scored automatically, once per fold model, after the margin has
been chosen on validation and after the synthetic test split. That ordering is
enforced in `train.select_then_score`, not by you remembering it.

---

## Step 4 — read the result

The report already renders both numbers; nothing here needs a bespoke script.

Fold-pooled decisive accuracy per signal per arm:

```bash
grep -H -E '^\| `arm_b_finetune` \| finetune' \
  reports/encoder_training/decl/arm*/*_present.arm_b_finetune.md
```

The real set, which is the number this ticket exists for. Each per-signal report
carries a `## The real-text holdout` section whose **first** table is
`### \`null -> true\` on real text -- the headline`:

```bash
for f in reports/encoder_training/decl/arm*/*_present.arm_b_finetune.md; do
  echo "=== $f"
  sed -n '/^### `null -> true` on real text/,/^###* /p' "$f" | head -12
done
```

Each file's table has **one** model column, because each arm was trained in its
own run; you are reading two files side by side rather than one table with two
columns. That is the cost of not having a `declarative-compare`.

**`null -> true` is the invented-symptom rate** — how often the model answers
`true` about a signal the submission never mentioned, as the mean across folds.
It is deliberately printed above the accuracy tables, because real-text accuracy
is dominated by the `null` cells that a model scores by saying nothing. This is
prediction 3's number, and 47%–89% (the 2026-08-17 joint run) is what it moves
against.

For prediction 4, the same section's per-signal table carries the `false` column
of the distribution and the decisive accuracy; the per-class recalls are in the
JSON at `holdout.by_signal[].per_class` if the markdown does not break them out
far enough.

Note the two `n`s the report prints side by side: the recombination test slice
is thousands of examples over hundreds of clusters, the holdout is 67
submissions at one observation each. They are not the same kind of number and
the second is far the smaller — a difference between arms on the holdout needs
to be large before it is real.

## Step 5 — write down what the predictions did

All six, whatever they say, including the ones that went the wrong way. The
plan's "Predictions, recorded before the run" section is the checklist:

1. Byte-identical at `P = 0` — from Step 1.
2. **Not testable by this run.** `generate-folds` has no `--companion-share`, so
   both arms are at 0.0 and there is no companion baseline to see structural
   nulls fall from. Read it off a directly-generated split instead
   (`python -m scripts.synthetic_data --companion-share 0.5 --declarative-share 0.3`)
   and report it as a separate observation, or say it was not measured. Do not
   quietly drop it.
3. Invented-symptom rate improves, most where the inventory has most phrases,
   least for `flank_pain_present` — from Step 4.
4. `false` recall improves most — from the `per_class` block.
5. Near-duplicate pairs in the hand-written libraries do not move — from
   `python -m scripts.synthetic_data --lint`.
6. `P = 0.6` scores worse on the real set than `P = 0.3`. Needs Arm R. If
   `P = 0.6` wins, DD8's whole argument is wrong and that is the most valuable
   thing this run could find.

---

## Step 6 — the report

`reports/encoder_training/<date>-declarative.md` plus its plain-English
companion, following the pattern of the 2026-08-31 noise pair. Then update
`documentation/arch_training.md` section 10.

Three things the report must say and will not say by itself:

* The holdout labels were **proposed by Claude and reviewed by the maintainer**;
  labeller and model share an architecture and could share a blind spot.
* These arms are **version 4** and not comparable with the version-3 companion
  arms or anything before them.
* Nothing generated is a hard case (DD3). A dataset that grew in line count has
  not grown in difficulty, and the per-sub-class counts are where to check that
  before believing otherwise.

---

## Step 7 — the console catalogue (instruction 7)

Code work, no GPU, and worth doing **before** Step 2 if you would rather drive
the runs from the training console than the terminal.

`scripts/training_gui/runs.json` does not yet know `--declarative-share`. The
console's parameters are enumerated strings only, which suits this exactly: the
enumeration *is* the arm list, and it makes the `P = 0.6` arm a dropdown rather
than something someone has to remember to run.

Add to both the `generate-folds` and `finetune` entries a parameter:

```json
{ "name": "share", "label": "Declarative share",
  "choices": ["0.0", "0.3", "0.6"], "default": "0.0" }
```

and thread `{share}` into the argv — `--declarative-share {share}` on
`generate-folds`, and into the `--out-dir` / `--data-dir` / `--report-dir` /
`--models-dir` paths on both, so the arms cannot overwrite each other. That
last part is the bit that matters: with the current entries both arms write to
the default directory and the second silently replaces the first.

---

## What this run cannot answer

* **Supervision per example.** At `--emit-signals primary` a fragment asserting
  three signals emits one key and the other two assertions are discarded.
  Banking them needs `--emit-signals all` and a `merge-folds` that accepts a
  multi-key tree (12.2). This run measures claim density, not supervision.
* **Whether declarative adds anything on top of companions — and this is the
  big one.** The committed companion reports already show the invented-symptom
  rate collapsing when companions were switched on: on `fever_present`,
  `null -> true` went from **84.1% at Arm 0 to 4.5% at Arm P**; `dysuria` 72.7%
  to 23.6%, `flank_pain` 87.5% to 17.7%, `haematuria` 80.4% to 12.5%. Both
  declarative arms here sit at companion share 0.0, so Arm 0 starts from that
  same bad baseline and any improvement Arm D shows may be **the same mechanism
  companions already fixed**, arriving by a second route — more clinical
  language about other signals in the text.

  Prediction 3 will probably come out true and will not, on its own, mean
  declarative fragments are worth shipping. The question that decides that is
  whether `P > 0` improves anything *at a non-zero companion share*, and
  `generate-folds` cannot express that combination today. Options, in order of
  cost: add `--companion-share` passthrough to `generate-folds` (a few lines,
  mirroring the `--declarative-share` passthrough already there) and run the
  arms at companion share 0.5; or run this 2×1 as specified and treat it as a
  mechanism check rather than a shipping decision. **Say which was chosen in the
  report** — a reader comparing against the companion numbers will otherwise
  read a 2×1 as though it were the 2×2.
* **Hard cases.** DD3 — the frames cannot produce a hedge, a metaphor or a
  third-party attribution, so the hard-case libraries remain the only source of
  those and `--null-ambiguous-ratio` still means what it meant.

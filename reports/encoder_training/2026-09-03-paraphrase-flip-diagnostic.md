# The paraphrase-flip diagnostic — 2026-09-03

Task 2 of the lexical variant expansion plan, and the second of its two gates.
**This document is the pre-registration.** The gate below (plan instruction 6)
is written and committed *before* any model is scored; the results section is
empty on purpose and is filled in by the run the last section describes.

Task 1 (`reports/synthetic_data/2026-09-03-token-label-association.md`) measured
the libraries and found the largest content-word association in the tree:
`fever` on 41 of 45 `fever_null_historical` lines and 0 of 50
`fever_null_attribution` ones, a within-`null` skew of 0.911. That is a fact
about the data. It is not evidence that a trained head *uses* the association.
This task asks the head directly, and it is built to be allowed to come back
negative: if a head barely changes its answer when only the vocabulary changes,
the expansion pass is not worth building and the ticket stops here.

## What is being measured

One real submission, rewritten three ways so that only its **vocabulary and
orthography** change. The fold's own decision rule is applied to the original
and to each rewrite, and the pair **flips** when the two predicted classes
differ. A flip is an error on one side of the pair, whichever side that is, and
seeing one needs no label — which is what makes this cheap: `uti1_holdout.labels.tsv`
is never opened, so the diagnostic costs the holdout nothing as a descriptive
measurement (plan DD8). It would cost the holdout its validity the moment a flip
rate were used to choose between two arms. Nothing here does that; the arm
comparison in Task 6 runs on the synthetic tree.

## The set

`data/realistic/uti1_paraphrases.tsv` — **13 submissions × 3 variants = 39
pairs**, over the real submissions rather than over test-split fragments,
because real text is where the register gap lives.

| column | what it is |
|---|---|
| `variant_id` | `holdout-NNNN-src` for the original, `holdout-NNNN-vK` for a rewrite |
| `submission_id` | the pairing key, and the resampling unit |
| `kind` | `source` or `variant` |
| `text` | one line, no tabs |

The `source` rows are the submissions **verbatim**, typos and all, and
`flip.load_paraphrases` checks them character for character against
`uti1_holdout.source.txt` on every load. That check is the thing that keeps this
a measurement of real text: a source tidied up on its way into the file measures
a rewrite against a rewrite, and the tidying is precisely the register axis being
probed.

The 13 were chosen for fever vocabulary, since `fever_present` is the pilot
signal Task 1 recommended: submissions 4, 6, 9, 13, 14, 17, 21, 24, 30, 31, 38,
41 and 52 between them carry `fever`, `temperature`, `high temperature`,
`feverish`, `hot`, and three explicit denials (`no fever`, `No fever or flank
pain`, `No fever yet`). The variants move that vocabulary in both directions —
`fever → temperature`, `temperature → fever`, both → `hot`/`running hot` — and
move the other signals' words too (`peeing`/`urinating`/`passing water`,
`urine`/`wee`, `flank`/`side`), so the same set says something about every head
in a joint checkpoint.

**What a variant may not change: tense, person, certainty, polarity.** A denial
stays a denial (`No blood, no fever` → `No blood, no high temperature`), a hedge
stays a hedge, and a first-person report stays first-person. That constraint is
enforced by hand review, not by code — the mechanical invariants in the plan's
DD6 belong to the rule files of Task 4, which do not exist and which this task
may well conclude are not needed.

**Provenance, carried into every number quoted from this set.** The variants
were written by Claude and reviewed by the maintainer. They are one model's idea
of which words are interchangeable, scored against a head built by the same
architecture. A flip found here is real — the two texts make the same claim and
the head answered differently. A flip *not* found here is weaker evidence,
because the variants may simply have failed to move the vocabulary the head is
actually reading.

## Power, stated before the numbers rather than under them

39 pairs, but the resampling unit is the **submission**: three rewrites of one
sentence are not three independent observations. So the effective *n* is 13, and
a 95% interval on a proportion at that *n* is worth roughly ±27 points at worst.

**This can separate "flips are common" from "flips are rare" and nothing finer.**
Any reading of the eventual number to the point is over-reading it, and the
report that records the result must quote the interval, not the point estimate
alone.

## The gate, pre-registered

The plan's instruction 6 asks for a gate of the form *"if the flip rate is below
X% and Task 1 showed no signal with a skew above Y, the ticket stops here"*.
**That two-clause form is now vacuous and is not what is being pre-registered
here**, which is worth saying plainly rather than quietly rewriting: Task 1 has
already read out at 0.911, so for any Y a reader would accept, the second clause
is false and the ticket could never stop no matter what the flip rate turned out
to be. The Y clause was written when Task 1's answer was unknown. It has been
answered, and the remaining decision rests on the flip rate alone.

So, committed before scoring:

| outcome | flip rate over the 39 pairs | what happens |
|---|---|---|
| **Stop** | point estimate **< 10%** *and* the 95% upper bound **< 20%** | The ticket stops at this report. The measured library skew is not one the head is reading, and Tasks 3–7 are not built. |
| **Proceed** | point estimate **≥ 25%** | The skew is learnable and expansion is worth building. Continue to Task 3. |
| **Judgement** | anything between | Neither answer is supported at n = 13. Resolved on the direction matrix and on the cheaper alternative below, in a written addendum to this report, not silently. |

Two secondary readings, recorded now so they are not invented afterwards to fit
the result:

* **The direction matrix decides what kind of fault it is.** `true → null` and
  `false → null` flips are the 12.6 shape — the head losing a decisive call when
  the wording moves — and are the case expansion is designed for. `true → false`
  flips are a different and worse fault, and expansion is not the fix for them.
* **A high flip rate does not by itself select expansion as the remedy.**
  Rewriting `fever_null_historical` so that it does not use "fever" on 41 of its
  45 lines is a library edit costing nothing downstream: no post-processing pass,
  no parallel tree, no rule format, no split risk. If the flips concentrate in
  the `null` sub-classes, that edit is the cheaper answer and should be compared
  against Task 3 before Task 3 is built.

## Result

**Not yet run.** The diagnostic needs a fine-tuned checkpoint, and there is none
to score:

* the fine-tuned encoder weights are **not committed** — `models/.gitignore`
  excludes the ~440MB `.pt` per fold, and every committed
  `fold*.head.json` records `encoder_weights_committed: false`;
* the session that built this tooling has no `models/**/weights/*.pt` on disk,
  no GPU, and no `torch` installed, so it can neither score a saved fold nor
  retrain one.

Everything that decides what the number *means* is nonetheless built and covered
by CI's unit job, because `flip.py` takes its forward pass as an injected
callable: `tests/test_encoder_training_flip.py` runs on a runner with no ML
wheels and pins the statistic, the direction matrix, the submission-level
resampling, the decision rule being applied to both sides, and each of the three
malformed-file failures.

### How to run it

On a machine with the ML dependencies and either the saved weights or the GPU
time to regenerate them (roughly two minutes a fold):

```
# only if no weights are on disk. A fold tree must be loaded at the K it was
# generated with, so this is the ordinary five-fold run; it writes one .pt per
# fold under .../arm_b_finetune/weights/
python -m scripts.encoder_training generate-folds --signal fever_present --folds 5
python -m scripts.encoder_training finetune --signal fever_present --folds 5

python -m scripts.encoder_training flip-rate \
  --weights models/encoder/fever_present/arm_b_finetune/weights/fold0.encoder.pt \
  --out reports/encoder_training/fever_present.paraphrase_flip.json
```

**Score one fold, not five.** The question is whether flips are common or rare,
and a number bounded by 13 submissions is not improved by averaging five models
over the same 13. If a second fold is scored anyway, report both rates rather
than pooling them: the folds share no test data but they do share these
submissions, so pooled pairs are not independent observations.

The margin is read from the fold's own `fold0.decision.json` by default, not
defaulted to argmax: a flip rate measured under a rule the fold never used is a
number about a model nobody deployed, and the two differ exactly where it
matters most, at the `null`/`true` boundary the margin exists to police.

`models/encoder/joint6/arm_b_finetune/weights/fold0.encoder.pt`, if it is the
checkpoint to hand, scores all six heads in the same pass and the same 39 pairs
— the command is identical.

When it has run, fill in the results section here with the overall rate **and
its interval**, the direction matrix, the per-signal rates, and the gate
outcome, then either continue to Task 3 or close the ticket. Recording the
number even when it kills the ticket is the point of the gate.

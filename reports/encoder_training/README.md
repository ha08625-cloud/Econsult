# Encoder training: evaluation reports

Output of `scripts/encoder_training`. Read
`documentation/arch_encoder_training.md` first — section 8 covers how to read a
report, and sections 3 and 5 cover why the error bars are what they are.

## What is committed here

| File | What it is |
|---|---|
| `<signal>.<stem>.json` | The report. Always committed — it is the machine-readable record and everything else is rendered from it. |
| `<signal>.<stem>.md` | The same report as markdown, rendered *from* that JSON so the two cannot disagree. Committed for runs worth keeping. |

`<stem>` is `baselines`, `arm_a_probe` or `arm_b_finetune`. An arm's report
carries the baselines too, and `finetune` carries Arm A as well: the ticket's
question is a **paired** comparison on the `null_ambiguous` slice, and McNemar
can only make it when both models are in one report.

## Current state

**Six signals have been trained, one head each** (2026-08-16): fever, dysuria,
urinary frequency, nocturia, flank pain, haematuria. Every
`<signal>.arm_b_finetune` report carries Arm B, Arm A and the three baselines
with their negative controls, five folds, `roberta-base`, on an RTX 5070. Six
separate single-signal heads — nothing here is a model that answers six
questions at once.

`2026-08-16-plain-english.md` is the write-up for that sweep, and it discharges
the six obligations below. It is written in plain language throughout rather
than as a translation of a separate technical document, because there is no
separate technical document for this sweep: it sources directly from the six
`<signal>.arm_b_finetune.json` files. **Those JSONs are authoritative** — if the
write-up and a JSON ever disagree, the JSON is right.

The short version: unfreezing the encoder beat the frozen probe on
`null_ambiguous` in all six signals, so the representation was a constraint
everywhere, not just for fever. What remains is concentrated on the *clear*
`_true`/`_false` libraries rather than on the confounder libraries written to be
the hard part — 39% to 87% of each signal's errors, and the confounder libraries
mostly sit at 0.90–1.00 recall. That is the 2026-08-09 fever finding replicating
across five more symptoms. Next month is library work on the clear classes,
starting with `urinary_frequency_true` (65.8%) and `nocturia_true` (71.1%).

**A caveat on one filename.** `fever_present.arm_b_finetune.*` was regenerated in
this sweep and its base model changed from `Bio_ClinicalBERT` to `roberta-base`,
so all six are now comparable. Nothing unique was lost: the version it replaced
was Bio_ClinicalBERT at 84.1% decisive, which is exactly the Bio_ClinicalBERT arm
still held in `fever_present.model_comparison.*`. `2026-08-09.md` and its
plain-English translation describe a **Bio_ClinicalBERT** run and are kept
unedited as the record of it — read their figures against `model_comparison`,
not against the current `fever_present.arm_b_finetune.*`, which is a different
encoder.

`fever_present.baselines` is the baselines-only report from the same folds, kept
because it is what a model has to beat and it runs without a GPU.

## Producing the ticket's report

```
pip install -r requirements-ml.txt          # read its header first on a Blackwell GPU
python -m scripts.encoder_training smoke-cuda    # ten seconds; do not skip it
python -m scripts.encoder_training generate-folds --folds 5
python -m scripts.encoder_training finetune --folds 5
```

`generate-folds` is seconds and stdlib-only. `finetune` reports Arm B, Arm A and
the baselines together and takes roughly twenty minutes on a 12GB card — two
minutes per fold per arm, doubled by the negative control.

## Writing the run up

The tooling computes the numbers. It deliberately does **not** write the
conclusion: the numbers constrain it but do not determine it, and a renderer that
concluded automatically would be concluding from whichever comparison happened to
clear a threshold picked while writing the renderer.

So a run worth keeping gets a dated write-up beside its JSON —
`<YYYY-MM-DD>.md` — and it owes six things:

1. **The paired comparison, read.** Arm B against TF-IDF on `null_ambiguous`,
   and Arm B against Arm A on the same slice. That difference, and only that
   difference, is the transformer earning its keep. It is in the report's
   "The ticket's question" section.
2. **The per-fragment error table, read before any conclusion is written.**
   Errors spread thinly across many fragments mean the method is too weak, so the
   next move is model work. Errors piled onto a handful mean those specific ideas
   are not learnable from the data we have, so the next move is library work — and
   the table names the fragments to write more of. A slice accuracy of 40% does
   not distinguish these.
3. **A verdict on each recorded prediction.** The report prints what was expected
   before any run — overall accuracy above 90%, near-perfect on `null_structural`
   and the clear classes, bag-of-words within a few points overall, the
   transformer's only real advantage on `null_ambiguous` and its weakest points
   there being metaphor and hay fever. Say whether each held. A plan that records
   a prediction and never scores it has wasted the prediction.
4. **The conclusion in the ticket's own terms**: model bottleneck or library
   bottleneck, and what the next month should therefore contain.
5. **The limitations, restated rather than linked.** The report already carries
   them: `arch_training.md` sections 9 and 10 in full, the fold-aggregate optimism
   (each fold's margin was selected on a sibling fold's test bucket), and the
   honest error-bar figure — folds raise effective n 12- to 17-fold, which narrows
   the per-sub-class interval from roughly ±30 points to roughly ±8, not to
   nothing.
6. **The next ticket, named.** 60–100 hand-written realistic full submissions,
   deliberately unlike the recombinations, labelled by hand, held out and never
   touched by a training decision. Until it exists nothing here resembles evidence
   about real patient text, whichever way the arms come out.

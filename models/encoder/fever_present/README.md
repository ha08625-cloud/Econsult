# `fever_present` head artefacts

This directory holds the trained `fever_present` heads. It is currently empty of
artefacts: **the weights below are produced by a run on a machine with a GPU and
network access to Hugging Face, and nothing in this repository fabricates them.**

## What lands here

One `metadata.json` per run, plus two files per fold:

| File | Contents |
|---|---|
| `metadata.json` | Base model and resolved revision SHA, the tokeniser's measured casing behaviour, pooling mode, `max_seq_len`, the full training config, every seed, dataset provenance and `generator_version`, `ruleset_hash`, and the validation numbers each fold's margin was chosen from |
| `foldN.head.json` | The `Linear(768, 3)` weights and bias for fold N — 2,307 parameters |
| `foldN.decision.json` | Fold N's decision rule: the margin, and the two `null -> true` rates that justify it |

JSON rather than a `.pt` pickle. A 2,307-parameter head has no need of a binary
format, and a JSON artefact is diffable in review, loadable without torch, and
cannot execute code when it is read. Arm A's heads are small enough to commit;
**Arm B's fine-tuned encoder is ~440MB and must not be** — where that lives is
still an open question, and until it is answered Arm B weights stay on local
disk.

The margin lives in its own file rather than inside the head because it is
retuned far more often than the weights are, and because it has to be readable
without loading a model.

## Producing them

```
pip install -r requirements-ml.txt
python -m scripts.encoder_training smoke                     # verify the GPU first
python -m scripts.encoder_training generate-folds --folds 5
python -m scripts.encoder_training probe --folds 5 --revision <commit-sha>
```

Pass `--revision`. The bare name `emilyalsentzer/Bio_ClinicalBERT` can move, and
an unpinned run is not reproducible; the resolved SHA is recorded either way and
a warning is printed when it was not pinned.

## What these weights are not

A single head cannot satisfy `EncoderOutput.validate_against`
(`app/models/encoder_contracts.py`), which requires output keys to match the
ruleset's `send_to_encoder` signals exactly — `data/uti1.json` declares seven.
Nothing here is wired into the running application, and `app/` never imports the
training package.

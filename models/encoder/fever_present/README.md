# `fever_present` head artefacts

This directory holds the trained `fever_present` heads, one sub-directory per
arm. It is currently empty of artefacts: **everything below is produced by a run
on a machine with a GPU and network access to Hugging Face, and nothing in this
repository fabricates them.**

```
fever_present/
  arm_a_probe/      # frozen encoder, Linear(768, 3) probe
  arm_b_finetune/   # every layer unfrozen
    weights/        # ~440MB per fold, git-ignored
```

One directory per arm rather than one shared one, because both write
`metadata.json` and `foldN.head.json` and a shared directory would have Arm B
silently overwrite Arm A's — the two results the ticket exists to compare.

## What lands here

Per arm: one `metadata.json` for the run, plus two files per fold.

| File | Contents |
|---|---|
| `metadata.json` | Base model and resolved revision SHA, the tokeniser's measured casing behaviour, pooling mode, `max_seq_len`, the full training config, every seed, dataset provenance and `generator_version`, `ruleset_hash`, and the validation numbers each fold's margin was chosen from. Arm B's also records the per-fold training-loss curve, the determinism mode that actually ran, and where the encoder weights went |
| `foldN.head.json` | The `Linear(768, 3)` weights and bias for fold N — 2,307 parameters |
| `foldN.decision.json` | Fold N's decision rule: the margin, and the two `null -> true` rates that justify it |

JSON rather than a `.pt` pickle. A 2,307-parameter head has no need of a binary
format, and a JSON artefact is diffable in review, loadable without torch, and
cannot execute code when it is read.

The margin lives in its own file rather than inside the head because it is
retuned far more often than the weights are, and because it has to be readable
without loading a model.

### Arm B's encoder weights are the model, and they are not committed

For Arm A the JSON head *is* the trained model: the encoder underneath it is
stock Bio_ClinicalBERT at the recorded revision. For Arm B it is not — the 110M
parameters beneath the head are what was fine-tuned, they live in
`arm_b_finetune/weights/foldN.encoder.pt`, and a three-by-768 matrix on top of a
different encoder is meaningless. `foldN.head.json` records the path to its
`.pt` for that reason.

`models/.gitignore` keeps the `.pt` files out of git. That is a deferral, not a
punt: regenerating a fold takes about two minutes from the pinned dataset seed
and base-model revision in the sidecar, so nothing is lost that cannot be
rebuilt, and where ~2.2GB of weights should live durably is a question this
ticket does not answer.

## Producing them

```
pip install -r requirements-ml.txt
python -m scripts.encoder_training smoke-cuda                     # the GPU, before anything else
python -m scripts.encoder_training smoke                          # and the encoder download
python -m scripts.encoder_training generate-folds --folds 5
python -m scripts.encoder_training probe --folds 5 --revision <commit-sha>     # Arm A
python -m scripts.encoder_training finetune --folds 5 --revision <commit-sha>  # Arm B
```

Pass `--revision`. The bare name `emilyalsentzer/Bio_ClinicalBERT` can move, and
an unpinned run is not reproducible; the resolved SHA is recorded either way and
a warning is printed when it was not pinned.

Run `smoke-cuda` first on any new machine. `torch.cuda.is_available()` returns
`True` on a wheel that cannot launch a single kernel — the failure a Blackwell
card produces with a pre-CUDA-12.8 build — so it runs a real matmul and prints
the compute capability beside torch's CUDA version. When it fails, the fix is a
different torch wheel, not a code change, and finding that out before a 440MB
download is the point of it being separate.

`finetune` refuses to run on the CPU unless asked, because a silent fallback
turns a ten-minute sweep into an overnight one. `--device cpu` or `--allow-cpu`
says it deliberately.

## What these weights are not

A single head cannot satisfy `EncoderOutput.validate_against`
(`app/models/encoder_contracts.py`), which requires output keys to match the
ruleset's `send_to_encoder` signals exactly — `data/uti1.json` declares seven.
Nothing here is wired into the running application, and `app/` never imports the
training package.

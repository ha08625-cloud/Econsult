"""Arm A: the frozen probe, and the artefacts a trained head is made of.

Arm A holds Bio_ClinicalBERT still, embeds every example once (:mod:`.embed`),
and fits ``Linear(768, 3)`` over the cached vectors. 2,307 parameters, seconds
per fold. Its job is not to be good -- it is to exercise the whole pipeline
where mistakes are cheap: embedding, caching, the masked loss, epoch selection,
margin selection, artefact writing, and the negative control, all in the shape
Arm B will reuse.

**What to expect, recorded before looking (instruction 10).** Clear positives,
clear negatives and ``null_structural`` should come out well. The four hard
``null`` sub-classes should not. Third-party attribution, tense and metaphor are
all *compositional scope* problems -- who the symptom belongs to, when it
happened, whether the word is literal -- and a single mean-pooled vector blurs
exactly the structure that carries them. A linear probe over such a vector has
no mechanism for "the fever belongs to the daughter". **A bad Arm A result on the
hard sub-classes is the expected outcome, not a bug**, and it is the reason Arm B
is not optional: without it, "the libraries are the bottleneck" and "the method
is too weak" stay indistinguishable, which is the one question this ticket
exists to answer.

**Torch is imported inside the functions that need it.** ``model.py`` is the
module that cannot avoid a module-level import; this one can, so it does, and the
config dataclass, the artefact layout and the metadata sidecar stay testable in
CI with no ML wheels installed. The sidecar in particular is a deliverable in its
own right -- it is what eventually populates ``model_name``, ``model_version``
and ``ruleset_hash`` in ``EncoderOutput`` -- so its contract deserves a test that
runs on every commit rather than only on a machine with a GPU.
"""

from __future__ import annotations

import json
import os
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from .baselines import permute_classes
from .dataset import CLASS_NAMES, MASKED_CLASS, Example, Fold, Split
from .decision import select_margin
from .embed import EmbeddingSpec, load_or_build
from .metrics import Prediction, apply_margin, confusion_matrix, macro_f1, repredict, summarise
from .report import FoldRun, ModelRun

if TYPE_CHECKING:  # pragma: no cover - typing only
    import torch

#: The model this ticket trains against. Bio_ClinicalBERT is BERT-base
#: initialised from BioBERT and further trained on MIMIC-III notes, which is the
#: closest freely available thing to the register patients write in.
DEFAULT_BASE_MODEL = "emilyalsentzer/Bio_ClinicalBERT"

#: Deterministic cuBLAS reductions (DD11). Torch requires this to be set in the
#: environment *before* CUDA initialises, which is why it is set by the CLI
#: rather than left to a shell export a reader has to remember.
CUBLAS_ENV_VAR = "CUBLAS_WORKSPACE_CONFIG"
CUBLAS_ENV_VALUE = ":4096:8"

#: Report/artefact name of the arm.
ARM_A_NAME = "arm_a_probe"

ARM_A_DESCRIPTION = (
    "Frozen Bio_ClinicalBERT, mean-pooled, with a `Linear(768, 3)` probe over the cached "
    "embeddings (2,307 parameters). The encoder learns nothing; only the probe is fitted. "
    "Expected to handle clear positives, clear negatives and `null_structural`, and to do badly "
    "on the four hard `null` sub-classes, which turn on compositional scope that a single pooled "
    "vector blurs. That is the predicted result rather than a fault, and it is what makes Arm B "
    'necessary: a weak probe cannot distinguish "the libraries are the bottleneck" from "the '
    'method is too weak".'
)


class TrainError(RuntimeError):
    """Raised when a training run cannot proceed as configured."""


@dataclass(frozen=True)
class ProbeConfig:
    """Arm A's hyperparameters, recorded verbatim in the sidecar.

    Not searched over. Hyperparameter search is explicitly out of scope, and a
    probe over frozen features is not where a point of macro-F1 is hiding.
    ``max_seq_len`` is 256 because the proof-of-concept run's median example is
    36 tokens and its 90th percentile 54 -- ample headroom at half the compute of
    512 -- and because the sequence length is not the interesting constraint
    here. Training on 36-token recombinations and eventually serving 300-token
    real submissions is a distribution shift no sequence length fixes.
    """

    base_model: str = DEFAULT_BASE_MODEL
    revision: str | None = None
    pooling: str = "mean"
    max_seq_len: int = 256
    epochs: int = 40
    batch_size: int = 256
    lr: float = 1e-3
    weight_decay: float = 0.0
    seed: int = 1234
    device: str = "auto"
    embed_batch_size: int = 64

    def to_dict(self) -> dict:
        return {
            "base_model": self.base_model,
            "revision": self.revision,
            "pooling": self.pooling,
            "max_seq_len": self.max_seq_len,
            "epochs": self.epochs,
            "batch_size": self.batch_size,
            "lr": self.lr,
            "weight_decay": self.weight_decay,
            "seed": self.seed,
            "fold_seed_rule": "seed + 1000 * fold_index",
            "device": self.device,
            "embed_batch_size": self.embed_batch_size,
            "loss": "cross_entropy, unweighted (DD8), masked on missing signals (DD10)",
            "optimiser": "AdamW",
            "epoch_selection": "highest macro-F1 on the fold's own validation split",
            "dtype": "float32",
        }

    def fold_seed(self, fold_index: object) -> int:
        """A distinct seed per fold, derived so one base seed reproduces the sweep."""
        try:
            offset = int(fold_index)
        except (TypeError, ValueError):
            offset = 0
        return self.seed + 1_000 * offset


@dataclass(frozen=True)
class ProbeFoldResult:
    """One fold's trained head, the evidence for its rule, and its predictions."""

    fold_index: object
    fold_run: FoldRun
    head_state: Mapping[str, Mapping[str, list]]
    n_parameters: int
    best_epoch: int
    val_macro_f1_by_epoch: tuple[float, ...]
    val_summary: Mapping[str, object]
    cache: Mapping[str, object] = field(default_factory=dict)

    def to_dict(self) -> dict:
        """The per-fold block of the metadata sidecar."""
        return {
            "fold": self.fold_index,
            "n_parameters": self.n_parameters,
            "best_epoch": self.best_epoch,
            "val_macro_f1_by_epoch": list(self.val_macro_f1_by_epoch),
            # The numbers the margin was chosen from, per instruction 8. A margin
            # without them is uninterpretable six months later.
            "validation": dict(self.val_summary),
            "decision_rule": self.fold_run.rule.to_dict(),
            "cache": dict(self.cache),
        }


# ---------------------------------------------------------------------------
# Determinism and devices (DD11)
# ---------------------------------------------------------------------------


def ensure_deterministic_env() -> str:
    """Set ``CUBLAS_WORKSPACE_CONFIG`` before torch is imported.

    Called by the CLI at start-up. Torch reads this variable when it initialises
    CUDA, so setting it afterwards has no effect and no error -- the run simply
    is not deterministic, and nothing says so. An existing value is respected
    rather than overwritten: a caller who set it deliberately knows something we
    do not.
    """
    os.environ.setdefault(CUBLAS_ENV_VAR, CUBLAS_ENV_VALUE)
    return os.environ[CUBLAS_ENV_VAR]


def resolve_device(requested: str = "auto") -> str:
    import torch

    if requested != "auto":
        return requested
    return "cuda" if torch.cuda.is_available() else "cpu"


def device_report(device: str) -> dict:
    """Prove the device can run a kernel, and record what it is.

    ``torch.cuda.is_available()`` returning ``True`` proves nothing. On an
    architecture the installed wheel was not built for -- an RTX 5070 is
    ``sm_120`` and needs CUDA 12.8 or later -- it reports ``True``, imports
    cleanly, and then fails at the first kernel launch with "no kernel image is
    available for execution on the device". So this runs a real matmul and lets
    that failure surface here, with the CUDA version and compute capability
    printed beside it, rather than twenty minutes into a training run.
    """
    import torch

    report: dict = {
        "device": device,
        "torch_version": torch.__version__,
        "torch_cuda_version": torch.version.cuda,
        "cuda_available": torch.cuda.is_available(),
        "deterministic_env": os.environ.get(CUBLAS_ENV_VAR),
    }
    if device.startswith("cuda"):
        index = torch.device(device).index or 0
        report["device_name"] = torch.cuda.get_device_name(index)
        report["compute_capability"] = list(torch.cuda.get_device_capability(index))

    left = torch.randn(64, 64, device=device, dtype=torch.float32)
    result = (left @ left.T).sum().item()
    report["kernel_launch_ok"] = bool(result == result)  # NaN would fail this
    return report


def seed_everything(seed: int) -> None:
    import torch

    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)
    torch.use_deterministic_algorithms(True)
    torch.backends.cudnn.benchmark = False


# ---------------------------------------------------------------------------
# Targets and predictions
# ---------------------------------------------------------------------------


def target_matrix(examples: Sequence[Example], signals: Sequence[str]) -> torch.Tensor:
    """``[n_examples, n_signals]`` class indices, :data:`MASKED_CLASS` where unlabelled."""
    import torch

    return torch.tensor(
        [[example.class_for(signal) for signal in signals] for example in examples],
        dtype=torch.long,
    )


def permute_targets(targets: torch.Tensor, *, seed: int) -> torch.Tensor:
    """Negative control 1: the same labels, attached to the wrong examples.

    Permuted per signal over the *labelled* positions only, so the mask survives
    intact and the class balance is preserved exactly. The control has to differ
    from the real run in one respect only -- whether the label has anything to do
    with the text.

    Note which split this is applied to. Train, always; validation and test are
    left alone and the control is scored against the truth. Wired the other way
    round it is worse than useless: at Arm B a 110M-parameter model will memorise
    permuted training labels and drive train loss to zero, which is correct
    behaviour and looks like failure if train is where you looked.
    """
    import torch

    permuted = targets.clone()
    for column in range(targets.shape[1]):
        rows = (targets[:, column] != MASKED_CLASS).nonzero(as_tuple=True)[0]
        if rows.numel() == 0:
            continue
        classes = [int(value) for value in targets[rows, column]]
        shuffled = permute_classes(classes, seed=seed + column)
        permuted[rows, column] = torch.tensor(shuffled, dtype=torch.long)
    return permuted


def predict(
    examples: Sequence[Example],
    embeddings: torch.Tensor,
    heads,
    *,
    signal: str,
    margin: float = 0.0,
) -> list[Prediction]:
    """Score a split, keeping softmax probabilities on every prediction.

    Probabilities rather than raw logits because the margin grid in
    :mod:`.decision` spans 0 to 0.9 as a *probability* gap; a margin applied to
    logits would mean something different on every fold.
    """
    import torch

    with torch.no_grad():
        logits = heads(embeddings)[signal]
        scores = torch.softmax(logits, dim=-1).cpu().tolist()

    if len(scores) != len(examples):
        raise TrainError(
            f"scored {len(scores)} rows against {len(examples)} examples; the embedding cache and "
            "the split are out of step"
        )
    return [
        Prediction.from_example(example, signal, apply_margin(row, margin), scores=row)
        for example, row in zip(examples, scores, strict=True)
    ]


def _labelled(split: Split, signal: str) -> list[Example]:
    return [example for example in split.examples if example.is_labelled(signal)]


def _rows_for(split: Split, embeddings: torch.Tensor, signal: str) -> tuple[list[Example], object]:
    """The examples this signal is labelled on, and their embedding rows.

    Filtering by index rather than re-embedding, so the cache stays keyed to the
    whole split regardless of which head is being trained.
    """
    import torch

    keep = [index for index, example in enumerate(split.examples) if example.is_labelled(signal)]
    if len(keep) == len(split.examples):
        return list(split.examples), embeddings
    index = torch.tensor(keep, dtype=torch.long)
    return [split.examples[position] for position in keep], embeddings.index_select(0, index)


# ---------------------------------------------------------------------------
# The probe itself
# ---------------------------------------------------------------------------


def train_probe(
    train_embeddings: torch.Tensor,
    train_targets: torch.Tensor,
    *,
    signals: Sequence[str],
    signal: str,
    val_examples: Sequence[Example],
    val_embeddings: torch.Tensor,
    config: ProbeConfig,
    seed: int,
    device: str,
) -> tuple[object, int, tuple[float, ...]]:
    """Fit the heads, choosing the epoch on validation macro-F1.

    Returns the heads, the chosen epoch, and macro-F1 at every epoch. Epoch
    selection is model selection and belongs on validation; the state from the
    best epoch is restored before the caller goes anywhere near test.
    """
    import torch

    from .model import LinearHeads, masked_cross_entropy

    seed_everything(seed)
    heads = LinearHeads(signals, hidden_size=train_embeddings.shape[1]).to(device)
    optimiser = torch.optim.AdamW(
        heads.parameters(), lr=config.lr, weight_decay=config.weight_decay
    )

    train_embeddings = train_embeddings.to(device)
    train_targets = train_targets.to(device)
    val_embeddings = val_embeddings.to(device)
    n_examples = train_embeddings.shape[0]
    generator = torch.Generator(device="cpu").manual_seed(seed)

    history: list[float] = []
    best_score = float("-inf")
    best_epoch = 0
    best_state = heads.state_lists()

    for epoch in range(1, config.epochs + 1):
        heads.train()
        order = torch.randperm(n_examples, generator=generator).to(device)
        for start in range(0, n_examples, config.batch_size):
            rows = order[start : start + config.batch_size]
            logits = heads(train_embeddings.index_select(0, rows))
            batch_targets = train_targets.index_select(0, rows)
            targets = {name: batch_targets[:, position] for position, name in enumerate(signals)}
            loss = masked_cross_entropy(logits, targets)
            optimiser.zero_grad(set_to_none=True)
            loss.backward()
            optimiser.step()

        heads.eval()
        val_predictions = predict(val_examples, val_embeddings, heads, signal=signal)
        score = macro_f1(confusion_matrix(val_predictions))
        history.append(-1.0 if score is None else score)
        if score is not None and score > best_score:
            best_score = score
            best_epoch = epoch
            best_state = heads.state_lists()

    heads.load_state_lists(best_state)
    heads.eval()
    return heads, best_epoch, tuple(history)


def run_probe_fold(
    fold: Fold,
    encoder,
    *,
    signal: str,
    config: ProbeConfig,
    cache_dir: Path | str,
    device: str,
    shuffle_seed: int | None = None,
    progress: bool = False,
) -> ProbeFoldResult:
    """Embed, fit, choose a margin on validation, then score test exactly once.

    The order is the procedure and it is not negotiable: fit on train, select the
    epoch on validation, select the margin on validation, and only then open
    test -- once, under a rule that was fixed before it was opened.
    """
    signals = tuple(fold.signals)
    if signal not in signals:
        raise TrainError(f"{signal!r} is not one of this dataset's signals: {signals}")

    cache: dict[str, object] = {}
    embeddings = {}
    for split in fold.splits:
        tensor, path, hit = load_or_build(
            split,
            encoder,
            signal=signal,
            directory=cache_dir,
            batch_size=config.embed_batch_size,
            progress=progress,
        )
        embeddings[split.name] = tensor
        cache[split.name] = {"path": str(path), "hit": hit}

    train_examples, train_rows = _rows_for(fold.train, embeddings["train"], signal)
    val_examples, val_rows = _rows_for(fold.val, embeddings["val"], signal)
    test_examples, test_rows = _rows_for(fold.test, embeddings["test"], signal)

    targets = target_matrix(train_examples, signals)
    if shuffle_seed is not None:
        targets = permute_targets(targets, seed=shuffle_seed + config.fold_seed(fold.fold_index))

    heads, best_epoch, history = train_probe(
        train_rows,
        targets,
        signals=signals,
        signal=signal,
        val_examples=val_examples,
        val_embeddings=val_rows,
        config=config,
        seed=config.fold_seed(fold.fold_index),
        device=device,
    )

    val_predictions = predict(val_examples, val_rows.to(device), heads, signal=signal)
    rule = select_margin(val_predictions)
    raw = predict(test_examples, test_rows.to(device), heads, signal=signal)

    val_scored = summarise(repredict(val_predictions, rule.margin, gated_class=rule.gated_class))
    return ProbeFoldResult(
        fold_index=fold.fold_index,
        fold_run=FoldRun.build(
            fold_index=fold.fold_index,
            n_train=len(train_examples),
            n_val=len(val_examples),
            n_test=len(raw),
            rule=rule,
            raw=raw,
            ruled=repredict(raw, rule.margin, gated_class=rule.gated_class),
        ),
        head_state=heads.state_lists(),
        n_parameters=heads.n_parameters,
        best_epoch=best_epoch,
        val_macro_f1_by_epoch=history,
        val_summary={
            "n_examples": val_scored.n_examples,
            "effective_n": val_scored.effective_n,
            "accuracy": val_scored.accuracy,
            "macro_f1": val_scored.macro_f1,
            "confusion": [list(row) for row in val_scored.confusion],
            "per_class_recall": {
                name: metrics.recall for name, metrics in val_scored.per_class.items()
            },
        },
        cache=cache,
    )


def run_probe(
    folds: Sequence[Fold],
    encoder,
    *,
    signal: str,
    config: ProbeConfig,
    cache_dir: Path | str,
    device: str,
    shuffle_seed: int | None = None,
    progress: bool = False,
) -> tuple[ModelRun, tuple[ProbeFoldResult, ...]]:
    """Run Arm A across every fold, as one reportable model plus its artefacts."""
    results = tuple(
        run_probe_fold(
            fold,
            encoder,
            signal=signal,
            config=config,
            cache_dir=cache_dir,
            device=device,
            shuffle_seed=shuffle_seed,
            progress=progress,
        )
        for fold in folds
    )
    control = shuffle_seed is not None
    run = ModelRun(
        name=f"{ARM_A_NAME}__shuffled" if control else ARM_A_NAME,
        kind="negative_control" if control else "probe",
        description=(
            f"{ARM_A_DESCRIPTION} **Negative control:** fitted on permuted training labels "
            f"(seed {shuffle_seed}) and evaluated on the unpermuted test split, where it must "
            "land at chance."
            if control
            else ARM_A_DESCRIPTION
        ),
        folds=tuple(result.fold_run for result in results),
    )
    return run, results


# ---------------------------------------------------------------------------
# Artefacts (provisional plan section 4.2)
# ---------------------------------------------------------------------------

#: Fields the metadata sidecar must carry. Asserted on write, because the
#: sidecar's whole purpose is to make a set of weights identifiable later, and a
#: field discovered missing six months on cannot be reconstructed.
REQUIRED_METADATA = (
    "arm",
    "signal",
    "classes",
    "encoder",
    "config",
    "device",
    "dataset",
    "ruleset_hash",
    "folds",
)


def build_metadata(
    *,
    signal: str,
    arm: str,
    encoder_facts: Mapping[str, object],
    config: ProbeConfig,
    device: Mapping[str, object],
    dataset: Mapping[str, object],
    ruleset: str,
    ruleset_hash: str,
    results: Sequence[ProbeFoldResult],
    control: Mapping[str, object] | None = None,
) -> dict:
    """Everything needed to identify a set of weights, in one dict.

    This is what eventually populates ``model_name``, ``model_version`` and
    ``ruleset_hash`` in ``EncoderOutput``. One thing to know when reading it:
    ``ruleset_hash`` covers the *whole* ruleset dict (DD15), so editing any
    unrelated question changes it. That is the right conservative default -- the
    hash says "trained against exactly this configuration" -- but a changed hash
    is not evidence that this signal's definition moved.

    Note also what this metadata does **not** claim. A single fever head cannot
    satisfy ``EncoderOutput.validate_against``, which requires output keys to
    match the ruleset's ``send_to_encoder`` signals exactly and finds seven of
    them in ``data/uti1.json``. Swapping in a real encoder stays blocked until
    either all seven heads exist or that contract permits partial output.
    """
    metadata = {
        "arm": arm,
        "signal": signal,
        "classes": list(CLASS_NAMES),
        "encoder": dict(encoder_facts),
        "config": config.to_dict(),
        "device": dict(device),
        "dataset": dict(dataset),
        "ruleset": ruleset,
        "ruleset_hash": ruleset_hash,
        "folds": [result.to_dict() for result in results],
        "margins": {
            "objective": (
                "maximise macro-F1 subject to a null -> true rate no worse than argmax's (DD9)"
            ),
            "selected_on": "each fold's own validation split, never test and never pooled",
            "by_fold": {str(result.fold_index): result.fold_run.rule.margin for result in results},
        },
        "encoder_contract": (
            "This head alone cannot satisfy EncoderOutput.validate_against: data/uti1.json "
            "declares seven send_to_encoder signals and the contract requires an exact key "
            "match. Out of scope for this ticket, and recorded so nobody plans around it."
        ),
    }
    if control is not None:
        metadata["negative_control"] = dict(control)

    missing = [field_name for field_name in REQUIRED_METADATA if field_name not in metadata]
    if missing:
        raise TrainError(f"metadata sidecar is missing {', '.join(missing)}")
    return metadata


def head_artefact(result: ProbeFoldResult, *, signal: str, arm: str) -> dict:
    """One fold's weights, as JSON rather than a pickle.

    2,307 parameters need no binary format, and a JSON artefact is diffable in a
    pull request, loadable without torch, and cannot execute code when it is
    read. The decision rule travels beside it rather than inside it, because the
    margin is retuned far more often than the weights are (DD9).
    """
    return {
        "arm": arm,
        "signal": signal,
        "fold": result.fold_index,
        "classes": list(CLASS_NAMES),
        "n_parameters": result.n_parameters,
        "best_epoch": result.best_epoch,
        "heads": {name: dict(state) for name, state in result.head_state.items()},
    }


def write_artefacts(
    directory: Path | str,
    *,
    signal: str,
    arm: str,
    metadata: Mapping[str, object],
    results: Sequence[ProbeFoldResult],
) -> list[Path]:
    """Write the metadata sidecar, and each fold's head and decision rule."""
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    written = [directory / "metadata.json"]
    written[0].write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")

    for result in results:
        stem = f"fold{result.fold_index}"
        head_path = directory / f"{stem}.head.json"
        head_path.write_text(
            json.dumps(head_artefact(result, signal=signal, arm=arm), indent=2) + "\n",
            encoding="utf-8",
        )
        written.append(head_path)
        written.append(result.fold_run.rule.write(directory / f"{stem}.decision.json"))
    return written


def load_head_artefact(path: Path | str) -> dict:
    """Read a head artefact back. No torch needed, which is half the point."""
    return json.loads(Path(path).read_text(encoding="utf-8"))


def spec_from_metadata(metadata: Mapping[str, object]) -> EmbeddingSpec:
    """Rebuild the embedding spec a sidecar describes, so a cache can be re-keyed."""
    encoder = metadata["encoder"]
    return EmbeddingSpec(
        base_model=encoder["base_model"],
        revision=encoder["revision"],
        pooling=encoder["pooling"],
        max_seq_len=encoder["max_seq_len"],
    )


__all__ = [
    "ARM_A_DESCRIPTION",
    "ARM_A_NAME",
    "CUBLAS_ENV_VALUE",
    "CUBLAS_ENV_VAR",
    "DEFAULT_BASE_MODEL",
    "ProbeConfig",
    "ProbeFoldResult",
    "TrainError",
    "build_metadata",
    "device_report",
    "ensure_deterministic_env",
    "head_artefact",
    "load_head_artefact",
    "permute_targets",
    "predict",
    "resolve_device",
    "run_probe",
    "run_probe_fold",
    "seed_everything",
    "spec_from_metadata",
    "target_matrix",
    "train_probe",
    "write_artefacts",
]

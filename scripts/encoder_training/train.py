"""Both arms: the frozen probe, the fine-tune, and the artefacts they produce.

Arm A holds Bio_ClinicalBERT still, embeds every example once (:mod:`.embed`),
and fits ``Linear(768, 3)`` over the cached vectors. 2,307 parameters, seconds
per fold. Its job is not to be good -- it is to exercise the whole pipeline
where mistakes are cheap: embedding, caching, the masked loss, epoch selection,
margin selection, artefact writing, and the negative control, all in the shape
Arm B reuses.

**Arm B unfreezes every layer and is the arm that decides the ticket's
question.** 110M parameters instead of 2,307, three epochs at batch 32, roughly
two minutes per fold on a 12GB card. It is deliberately *not* a compute
compromise: no gradient checkpointing, no 8-bit optimiser, no LoRA, no gradient
accumulation, fp32 rather than bf16 (DD11). The memory arithmetic says the full
thing fits with room to spare, and a run measured in minutes has no speed problem
worth buying with numerical noise in numbers we are trying to read to within a
point.

The two arms differ in one structural way beyond the obvious. Arm A can share a
single loaded encoder across every fold, because it never changes it. Arm B
**must** start each fold from the pretrained weights, so it takes an encoder
*factory* rather than an encoder: reusing one object would leave fold 1 starting
from a model already fine-tuned on fold 0's training data -- whose clusters are
fold 1's validation and test clusters. That is a leak no split check would catch,
because the dataset files would be blameless.

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
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from .baselines import permute_classes
from .dataset import CLASS_NAMES, MASKED_CLASS, Example, Fold, Split
from .decision import select_margin
from .embed import EmbeddingSpec, load_or_build
from .metrics import Prediction, apply_margin, confusion_matrix, macro_f1, repredict, summarise
from .report import FoldRun, ModelRun

# The device check lives in its own module because it is the first thing to run
# on a new machine and must be runnable on its own, before any model download
# (see :mod:`.smoke_cuda`). Re-exported here so callers that already import the
# training module keep working.
from .smoke_cuda import (
    CUBLAS_ENV_VALUE,
    CUBLAS_ENV_VAR,
    check_device,
    device_report,
    ensure_deterministic_env,
    resolve_device,
)

if TYPE_CHECKING:  # pragma: no cover - typing only
    import torch

    from .model import PooledEncoder

#: The model this ticket trains against. Bio_ClinicalBERT is BERT-base
#: initialised from BioBERT and further trained on MIMIC-III notes, which is the
#: closest freely available thing to the register patients write in.
DEFAULT_BASE_MODEL = "emilyalsentzer/Bio_ClinicalBERT"

#: Report/artefact name of the arm.
ARM_A_NAME = "arm_a_probe"

ARM_A_DESCRIPTION_TEMPLATE = (
    "Frozen {model}, mean-pooled, with a `Linear(768, 3)` probe over the cached "
    "embeddings (2,307 parameters). The encoder learns nothing; only the probe is fitted. "
    "Expected to handle clear positives, clear negatives and `null_structural`, and to do badly "
    "on the four hard `null` sub-classes, which turn on compositional scope that a single pooled "
    "vector blurs. That is the predicted result rather than a fault, and it is what makes Arm B "
    'necessary: a weak probe cannot distinguish "the libraries are the bottleneck" from "the '
    'method is too weak".'
)

ARM_A_DESCRIPTION = ARM_A_DESCRIPTION_TEMPLATE.format(model="Bio_ClinicalBERT")


#: Report/artefact name of the fine-tune arm.
ARM_B_NAME = "arm_b_finetune"

ARM_B_DESCRIPTION_TEMPLATE = (
    "{model} with **every layer unfrozen**, mean-pooled, with the same `Linear(768, 3)` "
    "head -- 110M trainable parameters against Arm A's 2,307. Three epochs at batch 32, learning "
    "rate 2e-5, 10% linear warmup, AdamW, fp32. No gradient checkpointing, no 8-bit optimiser, no "
    "LoRA, no gradient accumulation: the full model fits in 12GB with room to spare, so anything "
    "that reads like a compute compromise would be a mistake rather than a saving. This is the "
    'arm that separates "the fragment libraries are the bottleneck" from "the method is too '
    'weak": if a fully fine-tuned encoder still cannot read third-party attribution, tense or '
    "metaphor, the limit is in the ideas the libraries contain and the fix is library work, not "
    "model work."
)

ARM_B_DESCRIPTION = ARM_B_DESCRIPTION_TEMPLATE.format(model="Bio_ClinicalBERT")


def display_model(base_model: str) -> str:
    """The short name an encoder goes by in a report: ``org/Name`` -> ``Name``."""
    return base_model.rsplit("/", 1)[-1]


def arm_run_name(arm: str, label: str | None) -> str:
    """The name one arm's run carries in a report.

    A label is what makes several encoders comparable in a single report: every
    run in one report needs a distinct name, because :func:`report.compare_models`
    keys the paired McNemar tests on it and two runs called ``arm_b_finetune``
    would be reported as a model compared against itself.
    """
    return arm if label is None else f"{arm}@{label}"


#: The complete list of decisions this ticket permits the validation split to
#: make (task 5 instruction 5). Everything else -- warmup, weight decay, batch
#: size, gradient clipping, optimiser, epochs' order, seeds -- is fixed once from
#: published practice and never touched again. Written into the report because a
#: cap that lives only in a plan is not a cap: the number of quantities tuned
#: against validation is what decides how much the validation-selected margin
#: flatters the pooled result (DD4), and a reader cannot assess that from the
#: hyperparameters alone.
VALIDATION_GUIDED_DECISIONS = (
    "pooling mode (DD3) -- mean vs CLS, compared once",
    "learning rate",
    "epoch count (the epoch restored is the best-scoring one on the fold's own validation split)",
    "decision margin (DD9)",
)

#: Published-practice defaults for BERT-base fine-tuning, taken from the original
#: BERT paper's recommended range and unchanged since. They are **not** chosen
#: from our validation set, and hyperparameter search is out of scope.
FINETUNE_LR = 2e-5
FINETUNE_EPOCHS = 3
FINETUNE_WARMUP_RATIO = 0.1


class TrainError(RuntimeError):
    """Raised when a training run cannot proceed as configured."""


def derive_fold_seed(seed: int, fold_index: object) -> int:
    """A distinct seed per fold, derived so one base seed reproduces the sweep.

    Shared by both arms so the two are seeded the same way: comparing them is the
    point of the ticket, and a difference in seeding rules would be one more
    thing to rule out before believing a gap between them.
    """
    try:
        offset = int(fold_index)
    except (TypeError, ValueError):
        offset = 0
    return seed + 1_000 * offset


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
        return derive_fold_seed(self.seed, fold_index)


@dataclass(frozen=True)
class FineTuneConfig:
    """Arm B's hyperparameters, recorded verbatim in the sidecar.

    **Every default here was chosen once, from published practice, before any
    number was looked at.** Learning rate 2e-5, three epochs, 10% linear warmup
    and AdamW are the standard BERT-base fine-tuning recipe; batch 32 and
    sequence 256 are what the memory budget affords without any of the tricks
    that trade compute for memory. The only quantities this ticket allows the
    validation split to influence are listed in
    :data:`VALIDATION_GUIDED_DECISIONS`, and that list is written into the report.

    ``determinism`` is a mode rather than a Boolean because "enable
    ``use_deterministic_algorithms`` where it does not break a needed op" is a
    judgement that can only be made against a real torch version and a real
    model. Strict is the default and the intended setting; ``warn`` is the escape
    hatch for a backward kernel with no deterministic implementation, and which
    one ran is recorded rather than assumed.
    """

    base_model: str = DEFAULT_BASE_MODEL
    revision: str | None = None
    pooling: str = "mean"
    max_seq_len: int = 256
    epochs: int = FINETUNE_EPOCHS
    batch_size: int = 32
    lr: float = FINETUNE_LR
    weight_decay: float = 0.01
    warmup_ratio: float = FINETUNE_WARMUP_RATIO
    max_grad_norm: float = 1.0
    seed: int = 1234
    device: str = "auto"
    eval_batch_size: int = 64
    determinism: str = "strict"

    def __post_init__(self) -> None:
        if self.determinism not in DETERMINISM_MODES:
            raise TrainError(
                f"determinism must be one of {DETERMINISM_MODES}: {self.determinism!r}"
            )
        if not 0.0 <= self.warmup_ratio < 1.0:
            raise TrainError(f"warmup_ratio must be in [0, 1): {self.warmup_ratio}")

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
            "warmup_ratio": self.warmup_ratio,
            "max_grad_norm": self.max_grad_norm,
            "seed": self.seed,
            "fold_seed_rule": "seed + 1000 * fold_index",
            "device": self.device,
            "eval_batch_size": self.eval_batch_size,
            "determinism": self.determinism,
            "trainable": "all layers; the encoder is unfrozen and trained with the head",
            "loss": "cross_entropy, unweighted (DD8), masked on missing signals (DD10)",
            "optimiser": "AdamW with linear warmup then linear decay",
            "epoch_selection": "highest macro-F1 on the fold's own validation split",
            "dtype": "float32",
            "memory_strategy": (
                "none. No gradient checkpointing, no 8-bit optimiser, no LoRA, no gradient "
                "accumulation -- BERT-base at batch 32 / seq 256 fits in 12GB with room to spare"
            ),
            "hyperparameter_provenance": (
                "learning rate, epochs, warmup and optimiser are the published BERT-base recipe, "
                "fixed before any run. Hyperparameter search is out of scope"
            ),
            "validation_guided_decisions": list(VALIDATION_GUIDED_DECISIONS),
        }

    def fold_seed(self, fold_index: object) -> int:
        return derive_fold_seed(self.seed, fold_index)


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


@dataclass(frozen=True)
class FineTuneFoldResult:
    """One fold of Arm B: where its weights went, and what its training looked like.

    Shaped to be interchangeable with :class:`ProbeFoldResult` wherever the
    artefact writer and the metadata sidecar are concerned, so the two arms
    produce the same files and the same report.

    Two fields exist only for Arm B. ``train_loss_by_epoch`` is what makes the
    negative control readable: a 110M-parameter model *will* memorise permuted
    training labels, so near-zero train loss beside chance test performance is
    the control **passing**, and without the loss curve the reader sees only half
    of that. ``weights_path`` records where ~440MB of encoder went, because the
    weights themselves are deliberately not committed and a sidecar that cannot
    say where they are is a sidecar for nothing.
    """

    fold_index: object
    fold_run: FoldRun
    head_state: Mapping[str, Mapping[str, list]]
    n_parameters: int
    n_trainable: int
    best_epoch: int
    val_macro_f1_by_epoch: tuple[float, ...]
    train_loss_by_epoch: tuple[float, ...]
    val_summary: Mapping[str, object]
    steps_per_epoch: int
    warmup_steps: int
    weights_path: str | None = None

    def to_dict(self) -> dict:
        """The per-fold block of the metadata sidecar."""
        return {
            "fold": self.fold_index,
            "n_parameters": self.n_parameters,
            "n_trainable": self.n_trainable,
            "best_epoch": self.best_epoch,
            "val_macro_f1_by_epoch": list(self.val_macro_f1_by_epoch),
            "train_loss_by_epoch": list(self.train_loss_by_epoch),
            "steps_per_epoch": self.steps_per_epoch,
            "warmup_steps": self.warmup_steps,
            "validation": dict(self.val_summary),
            "decision_rule": self.fold_run.rule.to_dict(),
            "weights": {
                "path": self.weights_path,
                "committed": False,
                "note": (
                    "~440MB of fine-tuned encoder. Regenerable in about two minutes from the "
                    "pinned dataset seed and base-model revision recorded above, which is why "
                    "durable storage is deferred rather than punted"
                ),
            },
        }


# ---------------------------------------------------------------------------
# Determinism and devices (DD11)
# ---------------------------------------------------------------------------


#: How hard to insist on deterministic kernels (DD11, task 5 instruction 4).
#: ``strict`` raises when an op has no deterministic implementation, ``warn``
#: prints and continues, ``off`` disables the check entirely. Strict is the
#: default because a silently non-deterministic run is exactly the thing this
#: plan cannot afford; the other two exist because "enable it where it does not
#: break a needed op" is a decision that can only be made against an actual torch
#: version and an actual model, and whichever was used is recorded in the sidecar
#: rather than left to a reader to guess.
DETERMINISM_MODES = ("strict", "warn", "off")


def seed_everything(seed: int, determinism: str = "strict") -> None:
    import torch

    if determinism not in DETERMINISM_MODES:
        raise TrainError(f"determinism must be one of {DETERMINISM_MODES}: {determinism!r}")

    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)
    if determinism == "off":
        torch.use_deterministic_algorithms(False)
    else:
        torch.use_deterministic_algorithms(True, warn_only=determinism == "warn")
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
    label: str | None = None,
    progress: bool = False,
) -> tuple[ModelRun, tuple[ProbeFoldResult, ...]]:
    """Run Arm A across every fold, as one reportable model plus its artefacts.

    ``label`` distinguishes this run from other encoders' runs of the same arm in
    one report; it is ``None`` for the single-encoder commands, which keeps their
    run names, artefact paths and reports byte-identical to before.
    """
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
    base = arm_run_name(ARM_A_NAME, label)
    described = ARM_A_DESCRIPTION_TEMPLATE.format(model=f"`{display_model(config.base_model)}`")
    run = ModelRun(
        name=f"{base}__shuffled" if control else base,
        kind="negative_control" if control else "probe",
        description=(
            f"{described} **Negative control:** fitted on permuted training labels "
            f"(seed {shuffle_seed}) and evaluated on the unpermuted test split, where it must "
            "land at chance."
            if control
            else described
        ),
        folds=tuple(result.fold_run for result in results),
    )
    return run, results


# ---------------------------------------------------------------------------
# Arm B: the fine-tune
# ---------------------------------------------------------------------------


def warmup_then_decay(step: int, *, total_steps: int, warmup_steps: int) -> float:
    """Learning-rate multiplier: linear warmup, then linear decay to zero.

    The standard BERT fine-tuning schedule, written out rather than imported so
    the whole recipe is visible in one file and does not move under us when
    ``transformers`` reorganises its optimisation module. ``step`` is zero-based.
    """
    if warmup_steps > 0 and step < warmup_steps:
        return (step + 1) / warmup_steps
    remaining = max(total_steps - step, 0)
    denominator = max(total_steps - warmup_steps, 1)
    return remaining / denominator


def predict_finetuned(
    examples: Sequence[Example],
    encoder: PooledEncoder,
    heads,
    *,
    signal: str,
    batch_size: int = 64,
    margin: float = 0.0,
) -> list[Prediction]:
    """Score a split by running the encoder, in eval mode, under ``no_grad``.

    Arm A's :func:`predict` reads cached vectors; there is no cache here because
    the encoder changes every step, so this is the same contract paid for at full
    price. Softmax probabilities are kept on every prediction, because the margin
    grid in :mod:`.decision` is a probability gap.
    """
    import torch

    encoder.model.eval()
    heads.eval()
    scores: list[list[float]] = []
    with torch.no_grad():
        for start in range(0, len(examples), batch_size):
            chunk = examples[start : start + batch_size]
            batch = encoder.tokenise([example.text for example in chunk])
            logits = heads(encoder.forward_pooled(batch))[signal]
            scores.extend(torch.softmax(logits, dim=-1).cpu().tolist())

    return [
        Prediction.from_example(example, signal, apply_margin(row, margin), scores=row)
        for example, row in zip(examples, scores, strict=True)
    ]


def _snapshot(encoder: PooledEncoder) -> dict:
    """A CPU copy of the encoder's weights, for restoring the best epoch.

    On the CPU on purpose: a second 440MB copy on a 12GB card alongside the
    model, its gradients and AdamW's two moments is the one place this arm could
    run out of memory, and host RAM is free by comparison.
    """
    return {
        key: value.detach().to("cpu", copy=True)
        for key, value in encoder.model.state_dict().items()
    }


def finetune_fold_model(
    train_examples: Sequence[Example],
    train_targets: torch.Tensor,
    *,
    encoder: PooledEncoder,
    heads,
    signals: Sequence[str],
    signal: str,
    val_examples: Sequence[Example],
    config: FineTuneConfig,
    seed: int,
    progress: bool = False,
) -> tuple[int, tuple[float, ...], tuple[float, ...], int, int]:
    """Fine-tune every layer, choosing the epoch on validation macro-F1.

    Returns the chosen epoch, validation macro-F1 per epoch, mean training loss
    per epoch, steps per epoch and warmup steps. The best epoch's weights are
    restored into ``encoder`` and ``heads`` before returning, so the caller never
    has to remember to.

    Epoch selection is model selection and belongs on validation; it is one of
    the four decisions :data:`VALIDATION_GUIDED_DECISIONS` permits.
    """
    import torch
    from torch.nn.utils import clip_grad_norm_

    from .model import masked_cross_entropy

    seed_everything(seed, config.determinism)

    parameters = list(encoder.model.parameters()) + list(heads.parameters())
    optimiser = torch.optim.AdamW(parameters, lr=config.lr, weight_decay=config.weight_decay)

    n_examples = len(train_examples)
    steps_per_epoch = max(1, -(-n_examples // config.batch_size))  # ceil
    total_steps = steps_per_epoch * config.epochs
    warmup_steps = int(round(total_steps * config.warmup_ratio))
    scheduler = torch.optim.lr_scheduler.LambdaLR(
        optimiser,
        lambda step: warmup_then_decay(step, total_steps=total_steps, warmup_steps=warmup_steps),
    )

    device = encoder.device
    train_targets = train_targets.to(device)
    generator = torch.Generator(device="cpu").manual_seed(seed)

    val_history: list[float] = []
    loss_history: list[float] = []
    best_score = float("-inf")
    best_epoch = 0
    best_encoder = _snapshot(encoder)
    best_heads = heads.state_lists()

    for epoch in range(1, config.epochs + 1):
        encoder.model.train()
        heads.train()
        order = torch.randperm(n_examples, generator=generator).tolist()
        running = 0.0
        for start in range(0, n_examples, config.batch_size):
            rows = order[start : start + config.batch_size]
            batch = encoder.tokenise([train_examples[row].text for row in rows])
            index = torch.tensor(rows, dtype=torch.long, device=device)
            batch_targets = train_targets.index_select(0, index)
            targets = {name: batch_targets[:, position] for position, name in enumerate(signals)}

            logits = heads(encoder.forward_pooled(batch))
            loss = masked_cross_entropy(logits, targets)
            optimiser.zero_grad(set_to_none=True)
            loss.backward()
            clip_grad_norm_(parameters, config.max_grad_norm)
            optimiser.step()
            scheduler.step()
            running += float(loss.detach().item()) * len(rows)

        mean_loss = running / max(n_examples, 1)
        loss_history.append(mean_loss)

        predictions = predict_finetuned(
            val_examples, encoder, heads, signal=signal, batch_size=config.eval_batch_size
        )
        score = macro_f1(confusion_matrix(predictions))
        val_history.append(-1.0 if score is None else score)
        if progress:
            print(
                f"  epoch {epoch}/{config.epochs}: train loss {mean_loss:.4f}, "
                f"val macro-F1 {'--' if score is None else f'{score:.4f}'}",
                flush=True,
            )
        if score is not None and score > best_score:
            best_score = score
            best_epoch = epoch
            best_encoder = _snapshot(encoder)
            best_heads = heads.state_lists()

    encoder.model.load_state_dict(best_encoder)
    heads.load_state_lists(best_heads)
    encoder.model.eval()
    heads.eval()
    return best_epoch, tuple(val_history), tuple(loss_history), steps_per_epoch, warmup_steps


def write_finetuned_weights(
    path: Path | str,
    *,
    encoder: PooledEncoder,
    heads,
    signal: str,
    arm: str,
    fold_index: object,
) -> Path:
    """Write one fold's fine-tuned encoder and head to local disk.

    Roughly 440MB, and **not committed** -- ``models/.gitignore`` covers it. The
    payload repeats the base model, the resolved revision and the pooling mode so
    a file found on its own still says what it is; the metadata sidecar beside it
    is the committed record of the same facts.
    """
    import torch

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "arm": arm,
        "signal": signal,
        "fold": fold_index,
        "classes": list(CLASS_NAMES),
        **encoder.spec.to_dict(),
        "encoder_state_dict": {
            key: value.detach().cpu() for key, value in encoder.model.state_dict().items()
        },
        "heads": heads.state_lists(),
    }
    # Written to a sibling and moved, so an interrupted save leaves no file that
    # looks complete -- the same rule the embedding cache follows.
    temporary = path.with_suffix(path.suffix + ".partial")
    torch.save(payload, temporary)
    temporary.replace(path)
    return path


def run_finetune_fold(
    fold: Fold,
    encoder_factory: Callable[[], PooledEncoder],
    *,
    signal: str,
    config: FineTuneConfig,
    weights_dir: Path | str | None = None,
    shuffle_seed: int | None = None,
    progress: bool = False,
) -> FineTuneFoldResult:
    """Fine-tune on one fold, select on validation, then score test exactly once.

    ``encoder_factory`` returns a **freshly loaded** encoder. That is not a
    stylistic preference: reusing one object across folds would start fold *i+1*
    from weights already fine-tuned on fold *i*'s training clusters, which are
    fold *i+1*'s validation and test clusters. The dataset files would be
    blameless, every disjointness check would pass, and the numbers would be
    quietly inflated.

    The order is the procedure: fit on train, select the epoch on validation,
    select the margin on validation, and only then open test -- once, under a rule
    fixed before it was opened.
    """
    import torch

    from .model import LinearHeads

    signals = tuple(fold.signals)
    if signal not in signals:
        raise TrainError(f"{signal!r} is not one of this dataset's signals: {signals}")

    seed = config.fold_seed(fold.fold_index)
    seed_everything(seed, config.determinism)

    encoder = encoder_factory()
    if getattr(encoder.model, "is_gradient_checkpointing", False):
        raise TrainError(
            "gradient checkpointing is enabled on the encoder. Arm B is specified as a "
            "full-memory run -- no checkpointing, no 8-bit optimiser, no LoRA, no accumulation -- "
            "because the model fits without them; anything that reads like a compute compromise "
            "here is a mistake rather than a saving"
        )
    heads = LinearHeads(signals, hidden_size=int(encoder.model.config.hidden_size)).to(
        encoder.device
    )

    train_examples = _labelled(fold.train, signal)
    val_examples = _labelled(fold.val, signal)
    test_examples = _labelled(fold.test, signal)

    targets = target_matrix(train_examples, signals)
    if shuffle_seed is not None:
        targets = permute_targets(targets, seed=shuffle_seed + seed)

    best_epoch, val_history, loss_history, steps_per_epoch, warmup_steps = finetune_fold_model(
        train_examples,
        targets,
        encoder=encoder,
        heads=heads,
        signals=signals,
        signal=signal,
        val_examples=val_examples,
        config=config,
        seed=seed,
        progress=progress,
    )

    val_predictions = predict_finetuned(
        val_examples, encoder, heads, signal=signal, batch_size=config.eval_batch_size
    )
    rule = select_margin(val_predictions)
    raw = predict_finetuned(
        test_examples, encoder, heads, signal=signal, batch_size=config.eval_batch_size
    )

    weights_path = None
    if weights_dir is not None:
        weights_path = str(
            write_finetuned_weights(
                Path(weights_dir) / f"fold{fold.fold_index}.encoder.pt",
                encoder=encoder,
                heads=heads,
                signal=signal,
                arm=ARM_B_NAME,
                fold_index=fold.fold_index,
            )
        )

    val_scored = summarise(repredict(val_predictions, rule.margin, gated_class=rule.gated_class))
    result = FineTuneFoldResult(
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
        n_parameters=sum(
            parameter.numel()
            for parameter in list(encoder.model.parameters()) + list(heads.parameters())
        ),
        n_trainable=sum(
            parameter.numel()
            for parameter in list(encoder.model.parameters()) + list(heads.parameters())
            if parameter.requires_grad
        ),
        best_epoch=best_epoch,
        val_macro_f1_by_epoch=val_history,
        train_loss_by_epoch=loss_history,
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
        steps_per_epoch=steps_per_epoch,
        warmup_steps=warmup_steps,
        weights_path=weights_path,
    )

    # Five folds is five 440MB models plus their optimiser state. Dropping each
    # one before the next is loaded is what keeps the sweep inside 12GB.
    del encoder, heads
    if torch.cuda.is_available():
        torch.cuda.empty_cache()
    return result


def run_finetune(
    folds: Sequence[Fold],
    encoder_factory: Callable[[], PooledEncoder],
    *,
    signal: str,
    config: FineTuneConfig,
    weights_dir: Path | str | None = None,
    shuffle_seed: int | None = None,
    label: str | None = None,
    progress: bool = False,
) -> tuple[ModelRun, tuple[FineTuneFoldResult, ...]]:
    """Run Arm B across every fold, as one reportable model plus its artefacts.

    ``label`` distinguishes this run from other encoders' runs of the same arm in
    one report; it is ``None`` for the single-encoder commands, which keeps their
    run names, artefact paths and reports byte-identical to before.
    """
    results: list[FineTuneFoldResult] = []
    for fold in folds:
        if progress:
            print(f"fold {fold.fold_index}:", flush=True)
        results.append(
            run_finetune_fold(
                fold,
                encoder_factory,
                signal=signal,
                config=config,
                weights_dir=weights_dir,
                shuffle_seed=shuffle_seed,
                progress=progress,
            )
        )

    control = shuffle_seed is not None
    base = arm_run_name(ARM_B_NAME, label)
    described = ARM_B_DESCRIPTION_TEMPLATE.format(model=f"`{display_model(config.base_model)}`")
    run = ModelRun(
        name=f"{base}__shuffled" if control else base,
        kind="negative_control" if control else "finetune",
        description=(
            f"{described} **Negative control:** fine-tuned on permuted training labels "
            f"(seed {shuffle_seed}) and evaluated on the unpermuted test split. A 110M-parameter "
            "model is expected to drive train loss towards zero by memorising the permutation "
            "while landing at chance on test; that combination is the control passing, and the "
            "per-fold train-loss curve in the sidecar is where the first half of it is read."
            if control
            else described
        ),
        folds=tuple(result.fold_run for result in results),
    )
    return run, tuple(results)


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
    config: ProbeConfig | FineTuneConfig,
    device: Mapping[str, object],
    dataset: Mapping[str, object],
    ruleset: str,
    ruleset_hash: str,
    results: Sequence[ProbeFoldResult | FineTuneFoldResult],
    control: Mapping[str, object] | None = None,
) -> dict:
    """Everything needed to identify a set of weights, in one dict.

    Both arms use it, and their per-fold blocks differ only in what each result
    class chooses to record. Sharing one sidecar shape is deliberate: the two
    arms are compared against each other, and two artefact formats would be one
    more difference to rule out before believing the comparison.

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


def head_artefact(result: ProbeFoldResult | FineTuneFoldResult, *, signal: str, arm: str) -> dict:
    """One fold's *head* weights, as JSON rather than a pickle.

    2,307 parameters need no binary format, and a JSON artefact is diffable in a
    pull request, loadable without torch, and cannot execute code when it is
    read. The decision rule travels beside it rather than inside it, because the
    margin is retuned far more often than the weights are (DD9).

    For Arm B this file is **not the model**: the 110M-parameter encoder beneath
    the head is what was actually fine-tuned, and it lives in the ``.pt`` named by
    ``encoder_weights``, uncommitted. A three-by-768 matrix on top of a different
    encoder is meaningless, so the two are only useful together and the pointer
    between them belongs in the artefact rather than in someone's memory.
    """
    artefact = {
        "arm": arm,
        "signal": signal,
        "fold": result.fold_index,
        "classes": list(CLASS_NAMES),
        "n_parameters": result.n_parameters,
        "best_epoch": result.best_epoch,
        "heads": {name: dict(state) for name, state in result.head_state.items()},
    }
    weights_path = getattr(result, "weights_path", None)
    if weights_path is not None:
        artefact["encoder_weights"] = weights_path
        artefact["encoder_weights_committed"] = False
    return artefact


def write_artefacts(
    directory: Path | str,
    *,
    signal: str,
    arm: str,
    metadata: Mapping[str, object],
    results: Sequence[ProbeFoldResult | FineTuneFoldResult],
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
    "ARM_A_DESCRIPTION_TEMPLATE",
    "ARM_A_NAME",
    "ARM_B_DESCRIPTION",
    "ARM_B_DESCRIPTION_TEMPLATE",
    "ARM_B_NAME",
    "CUBLAS_ENV_VALUE",
    "CUBLAS_ENV_VAR",
    "DEFAULT_BASE_MODEL",
    "DETERMINISM_MODES",
    "FINETUNE_EPOCHS",
    "FINETUNE_LR",
    "FINETUNE_WARMUP_RATIO",
    "VALIDATION_GUIDED_DECISIONS",
    "FineTuneConfig",
    "FineTuneFoldResult",
    "ProbeConfig",
    "ProbeFoldResult",
    "TrainError",
    "arm_run_name",
    "build_metadata",
    "check_device",
    "derive_fold_seed",
    "display_model",
    "device_report",
    "ensure_deterministic_env",
    "finetune_fold_model",
    "head_artefact",
    "load_head_artefact",
    "permute_targets",
    "predict",
    "predict_finetuned",
    "resolve_device",
    "run_finetune",
    "run_finetune_fold",
    "run_probe",
    "run_probe_fold",
    "seed_everything",
    "spec_from_metadata",
    "target_matrix",
    "train_probe",
    "warmup_then_decay",
    "write_artefacts",
    "write_finetuned_weights",
]

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
from .decision import DecisionRule, select_margin
from .embed import EmbeddingSpec, load_or_build
from .holdout import HoldoutSet, score_holdout
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
    #: This fold's score against the real-text holdout, or ``None`` where the
    #: run was made with ``--no-holdout``. Recorded in the sidecar as well as in
    #: the report because README rule 3 asks for it to be recorded per candidate
    #: model, bad ones included, and the sidecar is what identifies the model.
    holdout: Mapping[str, object] | None = None

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
            "holdout": None if self.holdout is None else dict(self.holdout),
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


@dataclass(frozen=True)
class RemarginedFoldResult:
    """One fold's Arm C: the same trained model under a margin chosen elsewhere.

    Holds no weights and no training history because it has none -- it is
    :class:`JointFineTuneFoldResult`'s own model, re-decided. What it does hold
    is a full :class:`FoldRun` per head, so the arm drops into a report beside
    the one it came from with no special case anywhere downstream.
    """

    fold_index: object
    signals: tuple[str, ...]
    #: Where the margins were selected: the fold tree whose validation split was
    #: used, recorded because "Arm 0's model" and "Arm 0's model under Arm P's
    #: margin" differ in nothing else and a reader must be able to tell them
    #: apart six months on.
    margin_source: str
    fold_runs: Mapping[str, FoldRun]
    holdout: Mapping[str, object] | None = None

    def to_dict(self) -> dict:
        return {
            "fold": self.fold_index,
            "signals": list(self.signals),
            "margin_source": self.margin_source,
            "decision_rules": {
                signal: fold_run.rule.to_dict() for signal, fold_run in self.fold_runs.items()
            },
            "holdout": None if self.holdout is None else dict(self.holdout),
        }


@dataclass(frozen=True)
class JointFineTuneFoldResult:
    """One fold of a joint multi-head fine-tune: several heads, one shared encoder.

    Where :class:`FineTuneFoldResult` is one signal's view of one fold,
    this is the physical training run behind several signals' views of it at
    once: one encoder, ``len(signals)`` heads sharing it, one epoch chosen by
    DD6's unweighted mean of every head's own validation macro-F1, and one
    margin per head chosen independently on that head's own validation split
    (task 3 instruction 3 -- no cross-head trade).

    :meth:`for_signal` fans this out into the single-signal shape the existing
    report machinery already knows how to read (task 3 instruction 5), so
    ``head_artefact``, ``build_metadata`` and the report builder need no change
    at all for the per-signal reports this produces.
    """

    fold_index: object
    signals: tuple[str, ...]
    #: signal -> that head's FoldRun: its own rule, its own raw/ruled test
    #: predictions (keyed by that signal's own ids via ``Example.id_for``), and
    #: its own holdout block (identical across signals -- see ``holdout`` below).
    fold_runs: Mapping[str, FoldRun]
    #: Every head's weights, keyed by signal -- already the shape
    #: ``LinearHeads.state_lists()`` returns, so nothing here reshapes it.
    head_state: Mapping[str, Mapping[str, list]]
    n_parameters: int
    n_trainable: int
    #: The epoch chosen by DD6's shared criterion -- the same epoch for every
    #: head, because there is one shared encoder and therefore one set of
    #: weights to stop at.
    best_epoch: int
    #: signal -> that head's own validation macro-F1 at every epoch, recorded in
    #: full (not just the mean) so a report can show where a head's own best
    #: epoch differed from the one DD6 actually selected.
    val_macro_f1_by_epoch: Mapping[str, tuple[float, ...]]
    #: The unweighted mean across heads at every epoch -- the DD6 selection
    #: criterion itself, over the same epochs ``val_macro_f1_by_epoch`` covers.
    mean_val_macro_f1_by_epoch: tuple[float, ...]
    train_loss_by_epoch: tuple[float, ...]
    #: signal -> that head's own validation summary (n, eff n, accuracy, ...).
    val_summary: Mapping[str, Mapping[str, object]]
    steps_per_epoch: int
    warmup_steps: int
    weights_path: str | None = None
    #: One holdout block covering every trained signal, scored once per fold
    #: under each head's own selected margin (DD9's per-fold, in-process rule,
    #: unchanged). Identical across every signal's fanned-out result, because it
    #: is one scoring of one shared encoder against the same 67 submissions.
    holdout: Mapping[str, object] | None = None
    #: Arm C, when this fold was run with a ``remargin_fold``: the same trained
    #: heads under margins selected on that other tree's validation split. Never
    #: a second training run, and ``None`` on every fold that was not asked for
    #: one.
    remargined: RemarginedFoldResult | None = None

    def for_signal(self, signal: str) -> FineTuneFoldResult:
        """This fold's result, in the single-signal shape a report already reads.

        The weights recorded are every head's, not just ``signal``'s -- a joint
        model's ``.pt`` holds every head sharing the encoder, so a single-signal
        slice of ``head_state`` would be a head artefact pointing at weights it
        cannot reconstruct predictions from on its own.
        """
        return FineTuneFoldResult(
            fold_index=self.fold_index,
            fold_run=self.fold_runs[signal],
            head_state=self.head_state,
            n_parameters=self.n_parameters,
            n_trainable=self.n_trainable,
            best_epoch=self.best_epoch,
            val_macro_f1_by_epoch=self.val_macro_f1_by_epoch[signal],
            train_loss_by_epoch=self.train_loss_by_epoch,
            val_summary=self.val_summary[signal],
            steps_per_epoch=self.steps_per_epoch,
            warmup_steps=self.warmup_steps,
            weights_path=self.weights_path,
            holdout=self.holdout,
        )

    def to_dict(self) -> dict:
        """The per-fold block of the joint metadata sidecar (task 3 instruction 5)."""
        return {
            "fold": self.fold_index,
            "signals": list(self.signals),
            "n_parameters": self.n_parameters,
            "n_trainable": self.n_trainable,
            "best_epoch": self.best_epoch,
            "epoch_selection": (
                "the unweighted mean of every head's own validation macro-F1 (DD6): fever and "
                "dysuria do not get to decide nocturia's stopping point"
            ),
            "val_macro_f1_by_epoch": {
                signal: list(values) for signal, values in self.val_macro_f1_by_epoch.items()
            },
            "mean_val_macro_f1_by_epoch": list(self.mean_val_macro_f1_by_epoch),
            "train_loss_by_epoch": list(self.train_loss_by_epoch),
            "steps_per_epoch": self.steps_per_epoch,
            "warmup_steps": self.warmup_steps,
            "validation": {signal: dict(summary) for signal, summary in self.val_summary.items()},
            "decision_rules": {
                signal: fold_run.rule.to_dict() for signal, fold_run in self.fold_runs.items()
            },
            "holdout": None if self.holdout is None else dict(self.holdout),
            "remargined": None if self.remargined is None else self.remargined.to_dict(),
            "weights": {
                "path": self.weights_path,
                "committed": False,
                "note": (
                    "~440MB of fine-tuned encoder, shared by every head listed above. Regenerable "
                    "in about two minutes from the pinned dataset seed and base-model revision "
                    "recorded above, which is why durable storage is deferred rather than punted"
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


def _labelled_any(split: Split, signals: Sequence[str]) -> list[Example]:
    """Every example labelled for *at least one* of ``signals`` (task 3 instruction 2).

    The joint train split: a dysuria example belongs in it because it carries a
    dysuria label, even though it carries no key at all for the other five heads
    being trained. For a single-signal call (``signals`` of length one) this is
    exactly :func:`_labelled`, which is what keeps a single-signal joint run
    identical to today's.
    """
    return [example for example in split.examples if any(example.is_labelled(s) for s in signals)]


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


def predict_finetuned_multi(
    examples: Sequence[Example],
    encoder: PooledEncoder,
    heads,
    *,
    signals: Sequence[str],
    batch_size: int = 64,
) -> dict[str, list[Prediction]]:
    """:func:`predict_finetuned` for every trained head at once, from one forward pass.

    The whole reason this exists rather than calling :func:`predict_finetuned`
    once per signal: the encoder forward pass is the expensive part, and a joint
    model's heads all sit on top of the same pooled vector, so batching over
    ``examples`` once and reading every head's logits off it costs one pass
    instead of ``len(signals)``.

    Each example is scored for a signal only where it is labelled for that
    signal (``dataset.py``'s mask), exactly as :func:`predict_finetuned` would if
    called on that signal's own pre-filtered example list -- so for a
    single-signal call (``signals`` of length one, over examples every one of
    which is labelled for it) this reproduces :func:`predict_finetuned` batch for
    batch, which is what the single-signal parity test in
    ``tests/test_encoder_training_arm_b.py`` pins.

    Always argmax (``margin=0.0``): the raw view is what :func:`decision.select_margin`
    needs and what the ``raw`` confusion matrix is built from; a ruled view is
    produced afterwards with :func:`metrics.repredict` under whichever margin was
    chosen, exactly as the single-signal path does.
    """
    import torch

    encoder.model.eval()
    heads.eval()
    per_signal: dict[str, list[Prediction]] = {signal: [] for signal in signals}
    with torch.no_grad():
        for start in range(0, len(examples), batch_size):
            chunk = examples[start : start + batch_size]
            batch = encoder.tokenise([example.text for example in chunk])
            logits = heads(encoder.forward_pooled(batch))
            scores_by_signal = {
                signal: torch.softmax(logits[signal], dim=-1).cpu().tolist() for signal in signals
            }
            for signal in signals:
                rows = scores_by_signal[signal]
                for example, row in zip(chunk, rows, strict=True):
                    if not example.is_labelled(signal):
                        continue
                    per_signal[signal].append(
                        Prediction.from_example(example, signal, apply_margin(row, 0.0), scores=row)
                    )
    return per_signal


def encoder_scorer(
    encoder: PooledEncoder,
    heads,
    *,
    signals: Sequence[str],
    batch_size: int = 64,
) -> Callable[[Sequence[str]], dict[str, list[list[float]]]]:
    """The forward pass :func:`holdout.score_holdout` asks for, as a closure.

    ``holdout.py`` is standard-library only and takes the forward pass as a
    callable rather than importing one, so every line of the logic that decides
    what a holdout number *means* is coverable by CI's unit job. This is the
    torch half of that boundary: raw text in, softmax probabilities per head
    out, in the order the texts arrived.

    Probabilities rather than logits, for the same reason
    :func:`predict_finetuned` keeps them: the margin grid in :mod:`.decision` is
    a probability gap, and the margin applied to the holdout is the one already
    selected on the fold's own validation split.

    Every head is scored in one pass rather than one head at a time. For a
    single-signal run that is a set of one; for a joint model it is what stops
    the six heads costing six encoder passes over the same 67 submissions.
    """

    def score(texts: Sequence[str]) -> dict[str, list[list[float]]]:
        import torch

        encoder.model.eval()
        heads.eval()
        collected: dict[str, list[list[float]]] = {signal: [] for signal in signals}
        with torch.no_grad():
            for start in range(0, len(texts), batch_size):
                chunk = list(texts[start : start + batch_size])
                logits = heads(encoder.forward_pooled(encoder.tokenise(chunk)))
                for signal in signals:
                    collected[signal].extend(torch.softmax(logits[signal], dim=-1).cpu().tolist())
        return collected

    return score


def _fold_scorers(
    encoder: PooledEncoder,
    heads,
    *,
    signal: str,
    signals: Sequence[str],
    test_examples: Sequence[Example],
    holdout: HoldoutSet | None,
    batch_size: int,
) -> tuple[Callable[[DecisionRule], list[Prediction]], Callable[[DecisionRule], dict | None]]:
    """The two things :func:`select_then_score` calls, bound to one fold's model.

    A function rather than two closures written inline in
    :func:`run_finetune_fold`, so that the encoder and heads reach them as
    arguments. Written inline they would capture the caller's locals, which that
    function deletes before ``torch.cuda.empty_cache()`` -- and a closure holding
    a live reference to 440MB of encoder past the point the memory was supposed
    to be released is exactly the kind of leak the five-fold sweep cannot afford.
    """

    def score_test(rule: DecisionRule) -> list[Prediction]:
        # Argmax, deliberately -- the rule is not applied here. `raw` is the
        # unruled view and the ruled one is `repredict`ed from the same scores,
        # so the two confusion matrices the report prints differ only by the
        # rule. The rule is still passed in, because the *order* is what this
        # signature exists to express.
        return predict_finetuned(
            test_examples, encoder, heads, signal=signal, batch_size=batch_size
        )

    def score_realistic(rule: DecisionRule) -> dict | None:
        if holdout is None:
            return None
        return score_holdout(
            holdout,
            encoder_scorer(encoder, heads, signals=signals, batch_size=batch_size),
            # One head per fine-tune run today, so this is a list of one. It is
            # the model's head set rather than the holdout's column set: a
            # ruleset signal with no head is listed as unscored, not guessed at.
            signals=[signal],
            margin=rule.margin,
            gated_class=rule.gated_class,
        )

    return score_test, score_realistic


def _joint_fold_scorers(
    encoder: PooledEncoder,
    heads,
    *,
    signals: Sequence[str],
    test_examples: Sequence[Example],
    holdout: HoldoutSet | None,
    batch_size: int,
) -> tuple[
    Callable[[Mapping[str, DecisionRule]], dict[str, list[Prediction]]],
    Callable[[Mapping[str, DecisionRule]], dict | None],
]:
    """:func:`_fold_scorers`, generalised to one rule per head (task 3 instruction 3).

    ``test_examples`` is the union of examples labelled for any trained signal
    (:func:`_labelled_any`); :func:`predict_finetuned_multi` filters each one to
    the heads it is actually labelled for, so passing the union costs nothing --
    a head simply gets no prediction for an example that was never reachable
    for it.
    """

    def score_test(rules: Mapping[str, DecisionRule]) -> dict[str, list[Prediction]]:
        # Argmax, deliberately, exactly as `_fold_scorers.score_test` is -- the
        # rules are not applied here; `repredict` builds the ruled view from the
        # same scores afterwards, per head.
        return predict_finetuned_multi(
            test_examples, encoder, heads, signals=signals, batch_size=batch_size
        )

    def score_realistic(rules: Mapping[str, DecisionRule]) -> dict | None:
        if holdout is None:
            return None
        # gated_class is not part of the per-head trade DD9 asks about -- every
        # rule in this codebase selects it as CLASS_TRUE (decision.py's own
        # default), so there is one to quote rather than a mapping of six
        # identical values.
        gated_classes = {rule.gated_class for rule in rules.values()}
        if len(gated_classes) > 1:
            raise TrainError(
                f"the heads disagree on gated_class: {sorted(gated_classes)}; the holdout scorer "
                "does not support scoring different heads against different gated classes"
            )
        return score_holdout(
            holdout,
            encoder_scorer(encoder, heads, signals=signals, batch_size=batch_size),
            signals=list(signals),
            margin={signal: rules[signal].margin for signal in signals},
            gated_class=next(iter(gated_classes)),
        )

    return score_test, score_realistic


def describe_holdout(block: Mapping[str, object], signal: str) -> str:
    """One fold's real-text result as a line for the terminal.

    Printed as the run goes rather than left to the report, because a sweep is
    watched and this is the number the whole exercise is anxious about. The
    decisive count travels with it: 18 real cells is not 2,000 recombinations
    and a bare percentage invites the reader to forget that.
    """
    by_signal: Sequence[Mapping[str, object]] = block["by_signal"]  # type: ignore[assignment]
    entry = next((item for item in by_signal if item["signal"] == signal), None)
    if entry is None:
        return f"  holdout: {signal} not scored"
    decisive = entry["decisive"]
    point = decisive["accuracy"]["point"]
    rendered = "--" if point is None else f"{100 * point:.1f}%"
    half = decisive["worst_case_half_width"]
    band = "" if half is None else f" (worst-case +/-{100 * half:.0f})"
    return (
        f"  holdout: {signal} decisive {rendered}{band} on {decisive['n_cells']} cells "
        f"of {block['n_submissions']} real submissions, at margin {block['margin']}"
    )


def select_then_score(
    val_predictions: Sequence[Prediction],
    *,
    score_test: Callable[[DecisionRule], list[Prediction]],
    score_realistic: Callable[[DecisionRule], dict | None],
) -> tuple[DecisionRule, list[Prediction], dict | None]:
    """The order is the procedure, in one place that can be tested without a GPU.

    Margin from validation, then the synthetic test split, then the real-text
    holdout -- in that order and no other. The holdout's rules
    (``data/realistic/README.md``) say it selects nothing and is scored once per
    candidate model with the number recorded, and running it last is what makes
    "it selected nothing" a structural property rather than a promise: by the
    time it is called, the margin is fixed and test has already been opened, so
    there is nothing left for it to influence.

    Extracted from :func:`run_finetune_fold` deliberately. Inlined there it
    would only be checkable by reading the source or by a test that needs torch,
    a GPU-shaped fixture and a real encoder; here a recording fake asserts the
    call sequence on every commit. ``tests/test_encoder_training_holdout.py``
    is that test, and it is the reason this function exists.
    """
    rule = select_margin(val_predictions)
    test_predictions = score_test(rule)
    realistic = score_realistic(rule)
    return rule, test_predictions, realistic


def select_then_score_multi(
    val_predictions_by_signal: Mapping[str, Sequence[Prediction]],
    *,
    score_test: Callable[[Mapping[str, DecisionRule]], dict[str, list[Prediction]]],
    score_realistic: Callable[[Mapping[str, DecisionRule]], dict | None],
) -> tuple[dict[str, DecisionRule], dict[str, list[Prediction]], dict | None]:
    """:func:`select_then_score`, generalised to one rule per head.

    Every head's margin is selected on its own validation predictions,
    independently -- no cross-head trade (task 3 instruction 3) -- and only once
    every rule is fixed is anything scored: the synthetic test split per head,
    then the real-text holdout last of all, under every head's own rule at once.
    The order is what DD9's "the holdout selects nothing" rests on, generalised
    the same way :func:`select_then_score` states it.
    """
    rules = {
        signal: select_margin(predictions)
        for signal, predictions in val_predictions_by_signal.items()
    }
    test_predictions = score_test(rules)
    realistic = score_realistic(rules)
    return rules, test_predictions, realistic


def remargin_multi(
    alt_val_predictions_by_signal: Mapping[str, Sequence[Prediction]],
    *,
    raw_by_signal: Mapping[str, Sequence[Prediction]],
    score_realistic: Callable[[Mapping[str, DecisionRule]], dict | None],
) -> tuple[dict[str, DecisionRule], dict[str, list[Prediction]], dict | None]:
    """Re-select every head's margin on a **different** dataset's validation split.

    This is Arm C, and it is the arm that says whether the expensive half of the
    multi-symptom ticket was necessary. The model is not retrained and not
    reloaded: the same trained heads keep the same raw argmax scores on the same
    test examples, and the only thing that changes is the margin the decision
    rule applies to them -- chosen against validation data drawn from the other
    arm's generator settings.

    Why that can matter on its own: the decision rule maximises macro-F1 subject
    to a `null -> true` rate no worse than argmax's, and until companions existed
    no validation split contained the case the rule most needs to get right --
    text dense with another symptom's clinical language whose correct answer is
    still `null`. Margin selection has never been given a fair question to
    answer, and this asks it one for the cost of a forward pass.

    Pure, and separated from the training loop for that reason: the ordering it
    encodes -- new rules from the alternate validation split, then the *existing*
    raw test predictions re-decided, then the real-text holdout last of all -- is
    the same discipline :func:`select_then_score_multi` states, and a recording
    fake asserts it on every commit with no GPU in sight.
    """
    rules = {
        signal: select_margin(predictions)
        for signal, predictions in alt_val_predictions_by_signal.items()
    }
    missing = [signal for signal in raw_by_signal if signal not in rules]
    if missing:
        raise TrainError(
            f"no alternate validation predictions for {missing}; every head being re-margined "
            "needs its own, and a head silently keeping its original margin would be reported "
            "as a re-margined result that is nothing of the kind"
        )
    ruled = {
        signal: repredict(
            list(raw_by_signal[signal]), rules[signal].margin, gated_class=rules[signal].gated_class
        )
        for signal in raw_by_signal
    }
    realistic = score_realistic(rules)
    return rules, ruled, realistic


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


def finetune_joint_fold_model(
    train_examples: Sequence[Example],
    train_targets: torch.Tensor,
    *,
    encoder: PooledEncoder,
    heads,
    signals: Sequence[str],
    val_examples: Sequence[Example],
    config: FineTuneConfig,
    seed: int,
    progress: bool = False,
) -> tuple[int, dict[str, tuple[float, ...]], tuple[float, ...], tuple[float, ...], int, int]:
    """:func:`finetune_fold_model`, generalised to DD6's shared epoch criterion.

    One shared encoder and ``len(signals)`` heads means one set of weights to
    stop at, so per-head early stopping is impossible. The criterion is the
    **unweighted** mean of every head's own validation macro-F1 (DD6) -- not any
    one head's own score, and not weighted by how many labelled examples each
    head has, because that would let fever and dysuria decide nocturia's
    stopping point. For a single-signal call the mean has one term and equals
    that head's own score, which is what keeps a single-signal joint run
    numerically identical to :func:`finetune_fold_model`.

    Returns the chosen epoch, every head's own per-epoch validation macro-F1
    (signal -> tuple, recorded in full rather than only the mean, per instruction
    4), the per-epoch mean that selection actually used, mean training loss per
    epoch, steps per epoch and warmup steps.
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

    val_history: dict[str, list[float]] = {signal: [] for signal in signals}
    mean_history: list[float] = []
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

        predictions_by_signal = predict_finetuned_multi(
            val_examples, encoder, heads, signals=signals, batch_size=config.eval_batch_size
        )
        per_signal_scores: dict[str, float | None] = {}
        for signal in signals:
            score = macro_f1(confusion_matrix(predictions_by_signal[signal]))
            per_signal_scores[signal] = score
            val_history[signal].append(-1.0 if score is None else score)
        defined = [score for score in per_signal_scores.values() if score is not None]
        mean_score = sum(defined) / len(defined) if defined else None
        mean_history.append(-1.0 if mean_score is None else mean_score)
        if progress:
            per_head = ", ".join(
                f"{signal} {'--' if score is None else f'{score:.4f}'}"
                for signal, score in per_signal_scores.items()
            )
            print(
                f"  epoch {epoch}/{config.epochs}: train loss {mean_loss:.4f}, "
                f"val macro-F1 mean {'--' if mean_score is None else f'{mean_score:.4f}'} "
                f"({per_head})",
                flush=True,
            )
        if mean_score is not None and mean_score > best_score:
            best_score = mean_score
            best_epoch = epoch
            best_encoder = _snapshot(encoder)
            best_heads = heads.state_lists()

    encoder.model.load_state_dict(best_encoder)
    heads.load_state_lists(best_heads)
    encoder.model.eval()
    heads.eval()
    return (
        best_epoch,
        {signal: tuple(values) for signal, values in val_history.items()},
        tuple(mean_history),
        tuple(loss_history),
        steps_per_epoch,
        warmup_steps,
    )


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


def write_joint_finetuned_weights(
    path: Path | str,
    *,
    encoder: PooledEncoder,
    heads,
    signals: Sequence[str],
    arm: str,
    fold_index: object,
) -> Path:
    """:func:`write_finetuned_weights`, generalised to every head sharing the encoder.

    Still one ``.pt`` per fold, not one per head: the encoder is the ~440MB part
    and it is shared, so writing it once per signal would repeat the same
    payload ``len(signals)`` times for nothing. ``heads.state_lists()`` already
    holds every trained signal's weights, keyed by signal.
    """
    import torch

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "arm": arm,
        "signals": list(signals),
        "fold": fold_index,
        "classes": list(CLASS_NAMES),
        **encoder.spec.to_dict(),
        "encoder_state_dict": {
            key: value.detach().cpu() for key, value in encoder.model.state_dict().items()
        },
        "heads": heads.state_lists(),
    }
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
    holdout: HoldoutSet | None = None,
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
    fixed before it was opened. The real-text holdout comes last of all, under
    the margin test was scored with; :func:`select_then_score` is where that
    order lives so it can be asserted without a GPU.

    ``holdout`` is the 67 real submissions in ``data/realistic/``, already
    loaded and validated. ``None`` skips the check, and the report says so
    rather than reporting nothing.
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
    score_test, score_realistic = _fold_scorers(
        encoder,
        heads,
        signal=signal,
        signals=signals,
        test_examples=test_examples,
        holdout=holdout,
        batch_size=config.eval_batch_size,
    )
    rule, raw, realistic = select_then_score(
        val_predictions, score_test=score_test, score_realistic=score_realistic
    )
    # The two closures hold the only other references to the encoder, so they go
    # before it does; see the note beside the `del` at the end of this function.
    del score_test, score_realistic

    if realistic is not None:
        print(describe_holdout(realistic, signal), flush=True)

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
            holdout=realistic,
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
        holdout=realistic,
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
    holdout: HoldoutSet | None = None,
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
                holdout=holdout,
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


def run_finetune_joint_fold(
    fold: Fold,
    encoder_factory: Callable[[], PooledEncoder],
    *,
    signals: Sequence[str],
    config: FineTuneConfig,
    weights_dir: Path | str | None = None,
    shuffle_seed: int | None = None,
    holdout: HoldoutSet | None = None,
    remargin_fold: Fold | None = None,
    remargin_source: str = "",
    progress: bool = False,
) -> JointFineTuneFoldResult:
    """:func:`run_finetune_fold`, generalised to several heads sharing one encoder.

    A single-signal call (``signals`` of length one) is designed to be
    numerically identical to :func:`run_finetune_fold` on the same fold --
    ``tests/test_encoder_training_arm_b.py`` proves it by running both and
    diffing the result, rather than assuming it, because the two are
    independent implementations and that is the point of the test.

    The order is still the procedure DD9 asks for, generalised to several
    heads: fit on train (every example labelled for *any* trained signal,
    instruction 2), select the epoch on the DD6 shared criterion, select every
    head's margin independently on its own validation split (instruction 3,
    no cross-head trade), then open test once per head, and the real-text
    holdout last of all, under every head's own already-chosen margin.
    """
    import torch

    from .model import LinearHeads

    dataset_signals = tuple(fold.signals)
    signals = tuple(signals)
    unknown = [signal for signal in signals if signal not in dataset_signals]
    if unknown:
        raise TrainError(f"{unknown!r} are not among this dataset's signals: {dataset_signals}")
    if not signals:
        raise TrainError("a joint run needs at least one signal to train a head for")

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

    train_examples = _labelled_any(fold.train, signals)
    val_examples = _labelled_any(fold.val, signals)
    test_examples = _labelled_any(fold.test, signals)

    # Instruction 9: a head with no labelled validation examples fails loudly
    # rather than silently taking a default margin -- `select_margin` itself
    # refuses an empty split, but that error would be unreadable this far from
    # which head caused it.
    for signal in signals:
        if not any(example.is_labelled(signal) for example in val_examples):
            raise TrainError(
                f"{signal!r} has no labelled validation examples in fold {fold.fold_index}; a "
                "margin cannot be honestly selected for a head with nothing to select it on"
            )

    targets = target_matrix(train_examples, signals)
    if shuffle_seed is not None:
        targets = permute_targets(targets, seed=shuffle_seed + seed)

    best_epoch, val_history, mean_history, loss_history, steps_per_epoch, warmup_steps = (
        finetune_joint_fold_model(
            train_examples,
            targets,
            encoder=encoder,
            heads=heads,
            signals=signals,
            val_examples=val_examples,
            config=config,
            seed=seed,
            progress=progress,
        )
    )

    val_predictions_by_signal = predict_finetuned_multi(
        val_examples, encoder, heads, signals=signals, batch_size=config.eval_batch_size
    )
    score_test, score_realistic = _joint_fold_scorers(
        encoder,
        heads,
        signals=signals,
        test_examples=test_examples,
        holdout=holdout,
        batch_size=config.eval_batch_size,
    )
    rules, raw_by_signal, realistic = select_then_score_multi(
        val_predictions_by_signal, score_test=score_test, score_realistic=score_realistic
    )
    # Arm C, while the model is still on the device: the same heads, the same
    # raw scores, margins re-selected on the other arm's validation split. It
    # costs one forward pass over 2,000 examples plus a re-scoring of the 67
    # submissions, and it is what separates "the training data change helped"
    # from "the *margin selection* data change helped". Done here rather than
    # from saved weights because reloading five fine-tuned encoders to change a
    # threshold would be an hour of I/O to avoid a minute of arithmetic.
    remargined = None
    if remargin_fold is not None:
        alt_val_examples = _labelled_any(remargin_fold.val, signals)
        for signal in signals:
            if not any(example.is_labelled(signal) for example in alt_val_examples):
                raise TrainError(
                    f"{signal!r} has no labelled validation examples in the re-margining fold "
                    f"{remargin_fold.fold_index}; a margin cannot be honestly re-selected for a "
                    "head with nothing to select it on"
                )
        alt_val_predictions = predict_finetuned_multi(
            alt_val_examples, encoder, heads, signals=signals, batch_size=config.eval_batch_size
        )
        alt_rules, alt_ruled, alt_realistic = remargin_multi(
            alt_val_predictions, raw_by_signal=raw_by_signal, score_realistic=score_realistic
        )
        remargined = RemarginedFoldResult(
            fold_index=fold.fold_index,
            signals=signals,
            margin_source=remargin_source or str(remargin_fold.fold_index),
            fold_runs={
                signal: FoldRun.build(
                    fold_index=fold.fold_index,
                    n_train=len(train_examples),
                    n_val=len(alt_val_predictions[signal]),
                    n_test=len(raw_by_signal[signal]),
                    rule=alt_rules[signal],
                    raw=raw_by_signal[signal],
                    ruled=alt_ruled[signal],
                    holdout=alt_realistic,
                )
                for signal in signals
            },
            holdout=alt_realistic,
        )

    # The two closures hold the only other references to the encoder, so they go
    # before it does; see the note beside the `del` at the end of this function.
    del score_test, score_realistic

    if realistic is not None:
        for signal in signals:
            print(describe_holdout(realistic, signal), flush=True)

    weights_path = None
    if weights_dir is not None:
        weights_path = str(
            write_joint_finetuned_weights(
                Path(weights_dir) / f"fold{fold.fold_index}.encoder.pt",
                encoder=encoder,
                heads=heads,
                signals=signals,
                arm=ARM_B_NAME,
                fold_index=fold.fold_index,
            )
        )

    fold_runs: dict[str, FoldRun] = {}
    val_summary: dict[str, dict] = {}
    for signal in signals:
        rule = rules[signal]
        raw = raw_by_signal[signal]
        val_scored = summarise(
            repredict(val_predictions_by_signal[signal], rule.margin, gated_class=rule.gated_class)
        )
        val_summary[signal] = {
            "n_examples": val_scored.n_examples,
            "effective_n": val_scored.effective_n,
            "accuracy": val_scored.accuracy,
            "macro_f1": val_scored.macro_f1,
            "confusion": [list(row) for row in val_scored.confusion],
            "per_class_recall": {
                name: metrics.recall for name, metrics in val_scored.per_class.items()
            },
        }
        fold_runs[signal] = FoldRun.build(
            fold_index=fold.fold_index,
            n_train=len(train_examples),
            n_val=len(val_predictions_by_signal[signal]),
            n_test=len(raw),
            rule=rule,
            raw=raw,
            ruled=repredict(raw, rule.margin, gated_class=rule.gated_class),
            holdout=realistic,
        )

    result = JointFineTuneFoldResult(
        fold_index=fold.fold_index,
        signals=signals,
        fold_runs=fold_runs,
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
        mean_val_macro_f1_by_epoch=mean_history,
        train_loss_by_epoch=loss_history,
        val_summary=val_summary,
        steps_per_epoch=steps_per_epoch,
        warmup_steps=warmup_steps,
        weights_path=weights_path,
        holdout=realistic,
        remargined=remargined,
    )

    # Five folds is five 440MB models plus their optimiser state. Dropping each
    # one before the next is loaded is what keeps the sweep inside 12GB.
    del encoder, heads
    if torch.cuda.is_available():
        torch.cuda.empty_cache()
    return result


def run_finetune_joint(
    folds: Sequence[Fold],
    encoder_factory: Callable[[], PooledEncoder],
    *,
    signals: Sequence[str],
    config: FineTuneConfig,
    weights_dir: Path | str | None = None,
    shuffle_seed: int | None = None,
    holdout: HoldoutSet | None = None,
    label: str | None = None,
    remargin_folds: Sequence[Fold] | None = None,
    remargin_source: str = "",
    progress: bool = False,
) -> tuple[dict[str, ModelRun], tuple[JointFineTuneFoldResult, ...]]:
    """Run the joint fine-tune across every fold, fanned out into one ModelRun per head.

    Returns a signal -> ModelRun mapping rather than one ModelRun, because DD5's
    report shape is one report per signal: each entry is that signal's own view
    of the *same* physical training run (one encoder, every head sharing it),
    shaped exactly as a single-signal Arm B run's ``ModelRun`` so it drops into
    that signal's report unchanged (task 3 instruction 5).
    """
    # Matched by fold *index*, never by position: the two trees are separate
    # runs of the generator and a caller that loaded one of them in a different
    # order would otherwise re-margin fold 0 against fold 3's validation split,
    # whose test clusters are fold 0's training clusters. Nothing downstream
    # would notice, and the resulting arm would look like a slightly odd Arm C.
    remargin_by_index = {fold.fold_index: fold for fold in remargin_folds or ()}
    if remargin_folds is not None:
        missing = [fold.fold_index for fold in folds if fold.fold_index not in remargin_by_index]
        if missing:
            raise TrainError(
                f"the re-margining tree has no folds {missing}, which the trained tree has. "
                "Arm C needs the same fold configuration on both sides"
            )

    results: list[JointFineTuneFoldResult] = []
    for fold in folds:
        if progress:
            print(f"fold {fold.fold_index}:", flush=True)
        results.append(
            run_finetune_joint_fold(
                fold,
                encoder_factory,
                signals=signals,
                config=config,
                weights_dir=weights_dir,
                shuffle_seed=shuffle_seed,
                holdout=holdout,
                remargin_fold=remargin_by_index.get(fold.fold_index),
                remargin_source=remargin_source,
                progress=progress,
            )
        )

    control = shuffle_seed is not None
    base = arm_run_name(ARM_B_NAME, label)
    described = ARM_B_DESCRIPTION_TEMPLATE.format(model=f"`{display_model(config.base_model)}`")
    joint_note = (
        f"**Joint multi-head training**: {len(signals)} heads sharing one encoder "
        f"({', '.join(signals)}). Epoch selection uses DD6's unweighted mean of every head's own "
        "validation macro-F1, so this signal's stopping point may differ from a single-signal "
        "run's own best epoch. Each head's margin is chosen independently on its own validation "
        "split -- no cross-head trade."
    )
    name = f"{base}__shuffled" if control else base
    kind = "negative_control" if control else "finetune"
    description = (
        f"{described} {joint_note} **Negative control:** fine-tuned on permuted training labels "
        f"(seed {shuffle_seed}) and evaluated on the unpermuted test split."
        if control
        else f"{described} {joint_note}"
    )
    runs = {
        signal: ModelRun(
            name=name,
            kind=kind,
            description=description,
            folds=tuple(result.for_signal(signal).fold_run for result in results),
        )
        for signal in signals
    }
    return runs, tuple(results)


def remargined_runs(
    results: Sequence[JointFineTuneFoldResult],
    *,
    signals: Sequence[str],
    config: FineTuneConfig,
    label: str,
    margin_source: str,
) -> dict[str, ModelRun]:
    """Arm C as one :class:`~.report.ModelRun` per head, from an existing sweep.

    Takes no encoder and does no work beyond assembling what
    :func:`run_finetune_joint_fold` already computed, because Arm C *is* the
    trained arm -- the same weights, the same argmax scores, a different
    threshold. Raises rather than returning an empty mapping when the folds were
    not run with a ``remargin_fold``: an arm silently missing from a three-arm
    report is the failure mode this whole comparison exists to avoid.
    """
    missing = [result.fold_index for result in results if result.remargined is None]
    if missing:
        raise TrainError(
            f"folds {missing} were not run with a re-margining fold, so there is no Arm C for "
            "them. Pass remargin_folds to run_finetune_joint"
        )
    described = ARM_B_DESCRIPTION_TEMPLATE.format(model=f"`{display_model(config.base_model)}`")
    return {
        signal: ModelRun(
            name=arm_run_name(ARM_B_NAME, label),
            kind="finetune",
            description=(
                f"{described} **Margin re-selected, not retrained**: these are the trained heads "
                f"of the arm above, with every head's decision margin chosen on {margin_source}'s "
                "validation split instead of their own. Identical weights, identical raw argmax "
                "scores, identical test examples -- the only difference is the threshold, so a "
                "gap between this arm and the one it came from is margin selection alone."
            ),
            folds=tuple(result.remargined.fold_runs[signal] for result in results),
        )
        for signal in signals
    }


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


#: The joint metadata sidecar's own required fields (task 3 instruction 5):
#: ``signals`` (plural, a list) in place of ``signal``, everything else shared
#: with :data:`REQUIRED_METADATA`.
REQUIRED_JOINT_METADATA = tuple(
    "signals" if field_name == "signal" else field_name for field_name in REQUIRED_METADATA
)


def build_joint_metadata(
    *,
    signals: Sequence[str],
    arm: str,
    encoder_facts: Mapping[str, object],
    config: ProbeConfig | FineTuneConfig,
    device: Mapping[str, object],
    dataset: Mapping[str, object],
    ruleset: str,
    ruleset_hash: str,
    results: Sequence[JointFineTuneFoldResult],
    control: Mapping[str, object] | None = None,
) -> dict:
    """:func:`build_metadata`, generalised to a signal list (task 3 instruction 5).

    Kept as its own function rather than a branch inside :func:`build_metadata`:
    the per-fold blocks are shaped entirely differently (per-signal margins and
    per-signal validation summaries rather than one of each), and a single
    function silently switching shape on the type of ``signal`` would be a worse
    read than two functions that each say what they build.
    """
    metadata = {
        "arm": arm,
        "signals": list(signals),
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
                "maximise macro-F1 subject to a null -> true rate no worse than argmax's (DD9), "
                "per head, independently -- no cross-head trade (task 3 instruction 3)"
            ),
            "selected_on": "each fold's own validation split, never test and never pooled",
            "by_fold": {
                str(result.fold_index): {
                    signal: result.fold_runs[signal].rule.margin for signal in signals
                }
                for result in results
            },
        },
        "epoch_selection": (
            "one shared epoch across every head (DD6): the unweighted mean of every head's own "
            "validation macro-F1. Per-head early stopping is impossible with one shared encoder"
        ),
        "encoder_contract": (
            "This joint model cannot satisfy EncoderOutput.validate_against: data/uti1.json "
            "declares seven send_to_encoder signals and recent_uti_present has no fragment "
            "library and therefore no head here, so at most six of seven keys can ever be "
            "produced and the contract requires an exact match. Out of scope for this ticket, "
            "and recorded so nobody plans around a swap that is not available (DD8)."
        ),
    }
    if control is not None:
        metadata["negative_control"] = dict(control)

    missing = [field_name for field_name in REQUIRED_JOINT_METADATA if field_name not in metadata]
    if missing:
        raise TrainError(f"joint metadata sidecar is missing {', '.join(missing)}")
    return metadata


def joint_head_artefact(result: JointFineTuneFoldResult, *, arm: str) -> dict:
    """:func:`head_artefact`, generalised to every head sharing one encoder.

    One file per fold holding every trained signal's head, because that is what
    one fine-tune run over a merged tree actually produces -- there is no
    per-signal encoder to point six separate artefacts at.
    """
    artefact = {
        "arm": arm,
        "signals": list(result.signals),
        "fold": result.fold_index,
        "classes": list(CLASS_NAMES),
        "n_parameters": result.n_parameters,
        "best_epoch": result.best_epoch,
        "heads": {signal: dict(state) for signal, state in result.head_state.items()},
    }
    if result.weights_path is not None:
        artefact["encoder_weights"] = result.weights_path
        artefact["encoder_weights_committed"] = False
    return artefact


def write_joint_artefacts(
    directory: Path | str,
    *,
    arm: str,
    metadata: Mapping[str, object],
    results: Sequence[JointFineTuneFoldResult],
) -> list[Path]:
    """:func:`write_artefacts`, generalised to one joint model (task 3 instruction 7).

    ``models/encoder/joint<N>/<arm>/`` rather than ``<signal>/<arm>/``: there is
    no single signal this model belongs under, and a directory per trained
    signal would either duplicate the shared ~440MB encoder N times or leave
    five of six directories pointing at weights that live in a sixth.

    ``foldN.decision.json`` is written in mapping form -- ``{signal: rule}`` --
    always, per instruction 3, which is new: the existing single-signal
    ``write_artefacts`` still writes one flat rule and is unchanged by this.
    """
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    written = [directory / "metadata.json"]
    written[0].write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")

    for result in results:
        stem = f"fold{result.fold_index}"
        head_path = directory / f"{stem}.head.json"
        head_path.write_text(
            json.dumps(joint_head_artefact(result, arm=arm), indent=2) + "\n", encoding="utf-8"
        )
        written.append(head_path)

        decision_path = directory / f"{stem}.decision.json"
        decision_payload = {
            signal: fold_run.rule.to_dict() for signal, fold_run in result.fold_runs.items()
        }
        decision_path.write_text(json.dumps(decision_payload, indent=2) + "\n", encoding="utf-8")
        written.append(decision_path)
    return written


def read_joint_decision(path: Path | str) -> dict[str, DecisionRule]:
    """Read a joint ``foldN.decision.json`` back: signal -> its own rule.

    The reader instruction 3 asks for, migrated to the mapping form
    :func:`write_joint_artefacts` always writes -- including for a single-signal
    joint run, so the shape does not depend on how many heads were trained.
    """
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    return {signal: DecisionRule.from_dict(rule) for signal, rule in payload.items()}


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
    "REQUIRED_JOINT_METADATA",
    "FineTuneConfig",
    "FineTuneFoldResult",
    "JointFineTuneFoldResult",
    "ProbeConfig",
    "ProbeFoldResult",
    "TrainError",
    "arm_run_name",
    "build_joint_metadata",
    "build_metadata",
    "check_device",
    "derive_fold_seed",
    "describe_holdout",
    "display_model",
    "device_report",
    "encoder_scorer",
    "ensure_deterministic_env",
    "finetune_fold_model",
    "finetune_joint_fold_model",
    "head_artefact",
    "joint_head_artefact",
    "load_head_artefact",
    "permute_targets",
    "predict",
    "predict_finetuned",
    "predict_finetuned_multi",
    "read_joint_decision",
    "resolve_device",
    "run_finetune",
    "run_finetune_fold",
    "run_finetune_joint",
    "run_finetune_joint_fold",
    "run_probe",
    "run_probe_fold",
    "seed_everything",
    "select_then_score",
    "select_then_score_multi",
    "spec_from_metadata",
    "target_matrix",
    "train_probe",
    "warmup_then_decay",
    "write_artefacts",
    "write_finetuned_weights",
    "write_joint_artefacts",
    "write_joint_finetuned_weights",
]

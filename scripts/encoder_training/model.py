"""The encoder wrapper, the 3-way heads, and the masked loss.

**This is the first module in the package that imports torch at module scope,
and the boundary is deliberate.** Everything upstream of it -- the loader, every
metric, the decision rule, the report writer, the baselines' non-``fit`` logic --
is standard library, so CI's unit job covers the code that decides what a number
*means* on a runner with no GPU and no ML wheels. A module defining
``nn.Module`` subclasses cannot honour that, so it sits below the line and its
callers import it lazily.

Three pieces:

**Pooling (DD3).** Attention-mask-weighted mean pooling by default, CLS behind a
flag. Mean pooling is the default because a sentence's meaning here is spread
across it -- "no temperature, I checked twice" turns on the whole clause -- and
because Bio_ClinicalBERT's CLS vector was never trained by a next-sentence or
contrastive objective that would make it a sentence summary on its own. The flag
exists so the two get compared once and recorded, rather than argued about.

**The head.** ``Linear(768, 3)`` per signal: 2,307 parameters, three logits,
softmax cross-entropy (DD1). ``null`` is 60% of the data and holds four
deliberately-separated learnable sub-classes, so it earns a class of its own
rather than a calibration band on a binary output. The heads are a ``ModuleDict``
keyed by signal even though this ticket trains exactly one, because the shape of
the multi-head case is what forces the loss below to be written correctly now.

**The masked loss (DD10).** A *missing* signal key means "this dataset says
nothing about that signal, exclude it from the loss". An explicit ``null`` means
"train towards the null class". With one head there is never a missing key, so
this path gets no coverage from real data and is covered by unit tests instead.
Conflating the two once multi-head training starts is expensive and nearly
invisible: every head learns to answer "not mentioned" on every other head's
data, and the only symptom is that the model is mysteriously bad.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

import torch
from torch import nn
from torch.nn import functional as F  # noqa: N812 - torch's own conventional alias
from transformers import AutoModel, AutoTokenizer

from .dataset import CLASS_NAMES, MASKED_CLASS
from .embed import POOLING_MODES, EmbeddingSpec, EmbedError

#: Three logits per signal: ``false``, ``true``, ``null``.
N_CLASSES = len(CLASS_NAMES)

#: Bio_ClinicalBERT is a BERT-base, so 768. Asserted rather than assumed: a
#: silently different hidden size would produce a head of the wrong shape and a
#: cache that cannot be compared with anything already on disk.
EXPECTED_HIDDEN_SIZE = 768

#: The pair the casing probe runs on. A model that lowercases its input maps
#: both to the same ids; one that does not, does not.
_CASING_PROBE = ("Fever", "fever")


class ModelError(RuntimeError):
    """Raised when the encoder or a head cannot be built as asked."""


@dataclass(frozen=True)
class TokeniserFacts:
    """What the tokeniser actually does, checked at load time rather than assumed.

    Bio_ClinicalBERT descends from ``bert-base-cased`` and
    `arch_training.md` section 5 preserves original casing verbatim, so casing is
    probably signal-bearing -- "Fever" in a sentence a patient capitalised is not
    noise. That makes the tokeniser's behaviour worth *recording* rather than
    believing: ``do_lower_case`` is a constructor argument that a repository can
    set either way, and the attribute is absent entirely on some fast
    tokenisers.

    ``lowercases_input`` is therefore a behavioural probe -- tokenise ``Fever``
    and ``fever`` and compare the ids -- and ``reported_do_lower_case`` is
    whatever the object claims, which may be ``None``. Both go in the sidecar.
    """

    reported_do_lower_case: bool | None
    lowercases_input: bool
    vocab_size: int
    model_max_length: int
    tokenizer_class: str

    def to_dict(self) -> dict:
        return {
            "reported_do_lower_case": self.reported_do_lower_case,
            "lowercases_input": self.lowercases_input,
            "vocab_size": self.vocab_size,
            "model_max_length": self.model_max_length,
            "tokenizer_class": self.tokenizer_class,
        }


def probe_tokeniser(tokenizer) -> TokeniserFacts:
    """Establish what the tokeniser does to casing, by running it."""
    upper, lower = (
        tokenizer(text, add_special_tokens=False)["input_ids"] for text in _CASING_PROBE
    )
    reported = getattr(tokenizer, "do_lower_case", None)
    if reported is None and hasattr(tokenizer, "init_kwargs"):
        reported = tokenizer.init_kwargs.get("do_lower_case")
    return TokeniserFacts(
        reported_do_lower_case=None if reported is None else bool(reported),
        lowercases_input=upper == lower,
        vocab_size=int(tokenizer.vocab_size),
        model_max_length=int(tokenizer.model_max_length),
        tokenizer_class=type(tokenizer).__name__,
    )


def pool(
    last_hidden_state: torch.Tensor, attention_mask: torch.Tensor, mode: str = "mean"
) -> torch.Tensor:
    """Reduce a sequence of token vectors to one vector per example.

    Mean pooling is weighted by the attention mask, which is the whole point:
    averaging over the padded positions would make an example's embedding depend
    on the longest sentence in its batch, and the resulting numbers would drift
    with the batch size rather than with the text.
    """
    if mode not in POOLING_MODES:
        raise ModelError(f"pooling must be one of {POOLING_MODES}: {mode!r}")
    if mode == "cls":
        return last_hidden_state[:, 0, :]

    weights = attention_mask.unsqueeze(-1).to(last_hidden_state.dtype)
    summed = (last_hidden_state * weights).sum(dim=1)
    # An all-zero mask cannot happen for real text -- every tokenisation carries
    # [CLS] -- but dividing by zero would produce NaNs that survive into the
    # cache and poison a whole fold, so the floor is cheap insurance.
    counts = weights.sum(dim=1).clamp(min=1.0)
    return summed / counts


class PooledEncoder:
    """Bio_ClinicalBERT (or any HF encoder) reduced to one vector per text.

    Not an ``nn.Module``: it owns a tokeniser as well as a model, and the two
    travel together everywhere. Arm A calls :meth:`embed` once per split under
    ``no_grad``; Arm B will call :meth:`forward_pooled` inside its training loop
    with gradients on.
    """

    def __init__(
        self,
        base_model: str,
        *,
        revision: str | None = None,
        pooling: str = "mean",
        max_seq_len: int = 256,
        device: str = "cpu",
    ) -> None:
        if pooling not in POOLING_MODES:
            raise ModelError(f"pooling must be one of {POOLING_MODES}: {pooling!r}")
        self.base_model = base_model
        self.requested_revision = revision
        self.pooling = pooling
        self.max_seq_len = max_seq_len
        self.device = device
        self.tokenizer = None
        self.model = None
        self.facts: TokeniserFacts | None = None
        self._resolved_revision: str | None = None

    # -- loading ------------------------------------------------------------

    def load(self) -> PooledEncoder:
        """Load the tokeniser and weights, and pin down what was actually loaded.

        The revision is resolved rather than trusted. ``AutoModel`` will happily
        follow a branch, and ``emilyalsentzer/Bio_ClinicalBERT`` at ``main`` is
        not a fixed object: the same command a month apart can produce different
        weights, identical filenames, and an embedding cache that mixes the two.
        """
        kwargs = {} if self.requested_revision is None else {"revision": self.requested_revision}
        self.tokenizer = AutoTokenizer.from_pretrained(self.base_model, **kwargs)
        self.model = AutoModel.from_pretrained(self.base_model, **kwargs)
        # fp32 throughout (DD11). A run measured in minutes has no speed problem
        # worth buying with numerical noise in numbers we are trying to read to
        # within a point.
        self.model = self.model.to(dtype=torch.float32, device=self.device)
        self.model.eval()

        hidden = int(self.model.config.hidden_size)
        if hidden != EXPECTED_HIDDEN_SIZE:
            raise ModelError(
                f"{self.base_model} has hidden size {hidden}, not {EXPECTED_HIDDEN_SIZE}. The "
                "head shape and every cached embedding assume a BERT-base encoder"
            )

        self.facts = probe_tokeniser(self.tokenizer)
        self._resolved_revision = self._resolve_revision()
        return self

    def _resolve_revision(self) -> str:
        """The commit the weights actually came from.

        ``transformers`` records it on the config when it resolved the model
        through the hub. A local directory has no commit, so a caller loading one
        must say what to call it -- an unkeyed cache is worse than an error,
        because it is the failure that produces plausible numbers.
        """
        resolved = getattr(self.model.config, "_commit_hash", None)
        if resolved:
            return str(resolved)
        if self.requested_revision:
            return self.requested_revision
        raise EmbedError(
            f"{self.base_model} did not report a commit hash and no --revision was given, so "
            "nothing can honestly identify these weights. Pass --revision with the commit SHA "
            "you intend to pin (a bare branch name is not a pin)"
        )

    @property
    def revision(self) -> str:
        if self._resolved_revision is None:
            raise ModelError("the encoder has not been loaded yet")
        return self._resolved_revision

    @property
    def revision_pinned(self) -> bool:
        """Whether the caller pinned a revision, as opposed to taking whatever was current."""
        return self.requested_revision is not None

    @property
    def spec(self) -> EmbeddingSpec:
        """The cache key's view of this encoder (DD14)."""
        return EmbeddingSpec(
            base_model=self.base_model,
            revision=self.revision,
            pooling=self.pooling,
            max_seq_len=self.max_seq_len,
        )

    def to_dict(self) -> dict:
        """The encoder's contribution to the metadata sidecar."""
        return {
            **self.spec.to_dict(),
            "requested_revision": self.requested_revision,
            "revision_pinned": self.revision_pinned,
            "hidden_size": int(self.model.config.hidden_size),
            "tokeniser": None if self.facts is None else self.facts.to_dict(),
        }

    # -- forward passes -----------------------------------------------------

    def tokenise(self, texts: Sequence[str]) -> dict[str, torch.Tensor]:
        batch = self.tokenizer(
            list(texts),
            padding=True,
            truncation=True,
            max_length=self.max_seq_len,
            return_tensors="pt",
        )
        return {key: value.to(self.device) for key, value in batch.items()}

    def forward_pooled(self, batch: Mapping[str, torch.Tensor]) -> torch.Tensor:
        """One pooled vector per example, with gradients if the caller wants them."""
        outputs = self.model(**batch)
        return pool(outputs.last_hidden_state, batch["attention_mask"], self.pooling)

    @torch.no_grad()
    def embed(
        self, texts: Sequence[str], *, batch_size: int = 64, progress: bool = False
    ) -> torch.Tensor:
        """Pooled embeddings for many texts, on the CPU, in input order.

        Returned on the CPU regardless of the compute device: these go straight
        into a cache file, and 215MB of fold embeddings has no business occupying
        GPU memory while a probe trains.
        """
        rows: list[torch.Tensor] = []
        for start in range(0, len(texts), batch_size):
            chunk = texts[start : start + batch_size]
            rows.append(self.forward_pooled(self.tokenise(chunk)).cpu())
            if progress:
                print(f"  embedded {min(start + batch_size, len(texts))}/{len(texts)}", flush=True)
        if not rows:
            return torch.zeros((0, EXPECTED_HIDDEN_SIZE), dtype=torch.float32)
        return torch.cat(rows, dim=0)


class LinearHeads(nn.Module):
    """One ``Linear(hidden, 3)`` per signal (DD1).

    A ``ModuleDict`` for a ticket that trains a single head, because the loss
    below has to be written for the multi-head case to be written correctly at
    all, and a dict of one is the cheapest way to keep that honest.
    """

    def __init__(self, signals: Sequence[str], hidden_size: int = EXPECTED_HIDDEN_SIZE) -> None:
        super().__init__()
        if not signals:
            raise ModelError("a head set needs at least one signal")
        self.signals = tuple(signals)
        self.hidden_size = hidden_size
        self.heads = nn.ModuleDict(
            {signal: nn.Linear(hidden_size, N_CLASSES) for signal in self.signals}
        )

    @property
    def n_parameters(self) -> int:
        return sum(parameter.numel() for parameter in self.parameters())

    def forward(self, pooled: torch.Tensor) -> dict[str, torch.Tensor]:
        return {signal: head(pooled) for signal, head in self.heads.items()}

    def state_lists(self) -> dict[str, dict[str, list]]:
        """Weights as plain nested lists, for the JSON artefact.

        A 2,307-parameter head has no need of a binary format, and a pickle in
        the repository is a worse artefact than a diffable one: this is readable
        without torch, reviewable in a pull request, and cannot execute code on
        load.
        """
        return {
            signal: {
                "weight": head.weight.detach().cpu().tolist(),
                "bias": head.bias.detach().cpu().tolist(),
            }
            for signal, head in self.heads.items()
        }

    def load_state_lists(self, state: Mapping[str, Mapping[str, Sequence]]) -> LinearHeads:
        """Inverse of :meth:`state_lists`."""
        with torch.no_grad():
            for signal, head in self.heads.items():
                if signal not in state:
                    raise ModelError(f"no saved weights for signal {signal!r}")
                head.weight.copy_(torch.tensor(state[signal]["weight"], dtype=torch.float32))
                head.bias.copy_(torch.tensor(state[signal]["bias"], dtype=torch.float32))
        return self


def masked_cross_entropy(
    logits: Mapping[str, torch.Tensor], targets: Mapping[str, torch.Tensor]
) -> torch.Tensor:
    """Cross-entropy over the labelled positions only (DD10).

    Positions holding :data:`~.dataset.MASKED_CLASS` are excluded from both the
    numerator and the denominator, and the mean is taken over the labelled
    positions across *all* signals together rather than per signal. That
    difference matters once there are several heads: averaging per-signal means
    would weight a head with ten labelled examples equally with one that has ten
    thousand.

    A batch in which nothing is labelled returns a zero that is still connected
    to the graph, so ``backward`` is well defined and the step is a no-op.
    ``F.cross_entropy`` with every target ignored returns NaN instead, which
    would silently destroy every weight in the model on the next step.
    """
    total = None
    count = 0
    for signal, values in logits.items():
        if signal not in targets:
            raise ModelError(f"no targets for signal {signal!r}")
        target = targets[signal]
        labelled = int((target != MASKED_CLASS).sum().item())
        if labelled == 0:
            continue
        summed = F.cross_entropy(values, target, ignore_index=MASKED_CLASS, reduction="sum")
        total = summed if total is None else total + summed
        count += labelled

    if total is None:
        # Keep the graph: a detached zero would make the optimiser step on stale
        # gradients rather than on none.
        any_logits = next(iter(logits.values()))
        return any_logits.sum() * 0.0
    return total / count


__all__ = [
    "EXPECTED_HIDDEN_SIZE",
    "N_CLASSES",
    "LinearHeads",
    "ModelError",
    "PooledEncoder",
    "TokeniserFacts",
    "masked_cross_entropy",
    "pool",
    "probe_tokeniser",
]

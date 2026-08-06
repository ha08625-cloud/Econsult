"""Label-first recombination of fragments into training examples.

The ordering in :func:`generate` is the whole point of this module: an
:class:`ExampleSpec` -- the label and its mode -- exists before a single
fragment is chosen, and fragment selection is a pure consequence of it. Label
leakage is therefore structurally impossible rather than merely avoided; there
is no point in the pipeline at which the text could influence the label.

Two rules run through everything here:

* **Every collection sampled from is a sorted sequence.** Per-example seeds
  make the generator reproducible, but that guarantee evaporates the moment
  sampling iterates a ``set`` or an insertion-ordered dict. This is the usual
  way a "deterministic" generator quietly stops being one.
* **Pools are split-restricted for filler too.** Restricting only the signal
  pool would leak filler text across the train/val boundary, which is exactly
  as damaging as leaking signal text.
"""

from __future__ import annotations

import math
import random
from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from .manifest import Fragment
from .normalise import normalise

#: Bumped when a change to this module would alter the emitted dataset.
GENERATOR_VERSION = 1

#: Held constant across every class so fragment *count* cannot proxy the label.
#: Fragment *length* is not held constant -- see the stats sidecar.
FRAGMENTS_PER_EXAMPLE = 2

#: Redraws allowed before an example is declared unsatisfiable.
MAX_ASSEMBLY_RETRIES = 50

#: Label prior at training time. Operational cost asymmetry belongs in the
#: decision threshold at inference, not baked into the dataset.
DEFAULT_DISTRIBUTION = {"true": 0.15, "false": 0.25, "null": 0.60}

#: Share of ``null`` examples that carry a fever-adjacent fragment rather than
#: no fever fragment at all. The most consequential knob in the script: at 0.0
#: "no fever words -> null" is trivially learnable and the model collapses on
#: the hard confounders.
DEFAULT_NULL_AMBIGUOUS_RATIO = 0.5

#: Fixed iteration order for distribution sampling. Iterating the distribution
#: dict instead would make output depend on the order the CLI parsed flags in.
LABELS = ("true", "false", "null")

#: The four label modes; ``null`` splits into two structurally distinct kinds.
LABEL_MODES = ("true", "false", "null_structural", "null_ambiguous")

_TERMINAL_PUNCTUATION = ".!?"


class DistributionError(ValueError):
    """Raised when a requested label distribution is unusable."""


class PoolError(ValueError):
    """Raised when the fragment pools cannot support the requested generation."""


class PoolExhaustedError(RuntimeError):
    """Raised when the unique-text space is too small for the requested count."""


@dataclass(frozen=True)
class ExampleSpec:
    """The label, decided before any text exists."""

    example_id: str
    labels: dict[str, bool | None]
    label_mode: str


@dataclass(frozen=True)
class AssembledExample:
    """A finished example: spec plus the text that was built to satisfy it."""

    example_id: str
    split: str
    text: str
    labels: dict[str, bool | None]
    meta: dict


@dataclass(frozen=True)
class FragmentPools:
    """Split-restricted fragment pools for one signal, ready to sample from.

    Every member is a sorted tuple, and ``filler`` is a sorted tuple of
    ``(library, fragments)`` pairs rather than a dict, so that sampling order
    cannot depend on manifest ordering or dict insertion order.
    """

    split: str
    signal_key: str
    positive: tuple[Fragment, ...]
    negative: tuple[Fragment, ...]
    ambiguous: tuple[Fragment, ...]
    filler: tuple[tuple[str, tuple[Fragment, ...]], ...]

    @property
    def filler_libraries(self) -> tuple[str, ...]:
        return tuple(name for name, _ in self.filler)

    def filler_pool(self, library: str) -> tuple[Fragment, ...]:
        for name, fragments in self.filler:
            if name == library:
                return fragments
        raise KeyError(library)


def parse_distribution(text: str) -> dict[str, float]:
    """Parse ``null=0.60,false=0.25,true=0.15`` into a validated distribution.

    Rejects unknown labels, missing labels, and any total that is not 1.0
    within float tolerance -- a distribution that silently does not sum to one
    would skew the dataset in a way nothing downstream could detect.
    """
    parsed: dict[str, float] = {}
    for chunk in text.split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        label, sep, raw = chunk.partition("=")
        label = label.strip()
        if not sep:
            raise DistributionError(f"malformed --dist term {chunk!r}, expected 'label=weight'")
        if label not in LABELS:
            raise DistributionError(
                f"unknown label {label!r} in --dist (permitted: {', '.join(LABELS)})"
            )
        if label in parsed:
            raise DistributionError(f"label {label!r} appears twice in --dist")
        try:
            weight = float(raw)
        except ValueError:
            raise DistributionError(f"weight for {label!r} is not a number: {raw!r}") from None
        if weight < 0:
            raise DistributionError(f"weight for {label!r} is negative: {weight}")
        parsed[label] = weight

    missing = [label for label in LABELS if label not in parsed]
    if missing:
        raise DistributionError(f"--dist is missing weights for: {', '.join(missing)}")

    total = sum(parsed.values())
    if abs(total - 1.0) > 1e-9:
        raise DistributionError(f"--dist weights sum to {total!r}, not 1.0")
    return parsed


def build_pools(fragments: Iterable[Fragment], signal_key: str, split: str) -> FragmentPools:
    """Group fragments for one signal and one split into sampling pools.

    Fragments for other signals are dropped rather than treated as filler: a
    ``dysuria_present`` positive says nothing about ``fever_present``, but
    asserting that is library work we have not done, so it must not be
    silently assumed here.
    """
    in_split = sorted(
        (f for f in fragments if f.split == split),
        key=lambda f: f.fragment_id,
    )

    def signal_pool(*types: str) -> tuple[Fragment, ...]:
        return tuple(f for f in in_split if f.signal_key == signal_key and f.fragment_type in types)

    filler_by_library: dict[str, list[Fragment]] = {}
    for fragment in in_split:
        if fragment.fragment_type == "filler":
            filler_by_library.setdefault(fragment.library, []).append(fragment)

    pools = FragmentPools(
        split=split,
        signal_key=signal_key,
        positive=signal_pool("positive"),
        negative=signal_pool("negative"),
        ambiguous=signal_pool("ambiguous", "confounder"),
        filler=tuple((name, tuple(filler_by_library[name])) for name in sorted(filler_by_library)),
    )
    _check_pools(pools)
    return pools


def _check_pools(pools: FragmentPools) -> None:
    """Fail fast on pools that cannot serve every label mode.

    An empty pool discovered halfway through a 10,000-example run wastes the
    run; discovered here it is a one-line message.
    """
    empty = [
        name
        for name, pool in (
            ("positive", pools.positive),
            ("negative", pools.negative),
            ("ambiguous/confounder", pools.ambiguous),
        )
        if not pool
    ]
    if empty:
        raise PoolError(
            f"split {pools.split!r} has no {', '.join(empty)} fragments for "
            f"signal {pools.signal_key!r}"
        )
    # null_structural draws two fillers from two *different* libraries.
    if len(pools.filler) < 2:
        raise PoolError(
            f"split {pools.split!r} has {len(pools.filler)} filler libraries, but "
            "structural nulls need two distinct ones"
        )


def sample_label_mode(
    rng: random.Random, distribution: dict[str, float], null_ambiguous_ratio: float
) -> str:
    """Draw a label mode. Called before any fragment is looked at."""
    draw = rng.random()
    cumulative = 0.0
    label = LABELS[-1]
    for candidate in LABELS:
        cumulative += distribution[candidate]
        if draw < cumulative:
            label = candidate
            break

    if label != "null":
        return label
    return "null_ambiguous" if rng.random() < null_ambiguous_ratio else "null_structural"


def labels_for_mode(signal_key: str, label_mode: str) -> dict[str, bool | None]:
    """Map a label mode to the emitted label dict.

    The trainer contract this encodes: **key absent != value null**. An absent
    key means "no label for this head, mask its loss"; ``None`` means "the
    label for this head is None". Get that wrong when this data is merged with
    another signal's, and every head learns to predict null on every other
    head's data.
    """
    if label_mode == "true":
        return {signal_key: True}
    if label_mode == "false":
        return {signal_key: False}
    if label_mode in ("null_structural", "null_ambiguous"):
        return {signal_key: None}
    raise ValueError(f"unknown label mode {label_mode!r}")


def make_spec(
    rng: random.Random,
    *,
    example_id: str,
    signal_key: str,
    distribution: dict[str, float],
    null_ambiguous_ratio: float,
) -> ExampleSpec:
    """Build the label-first spec for one example."""
    label_mode = sample_label_mode(rng, distribution, null_ambiguous_ratio)
    return ExampleSpec(
        example_id=example_id,
        labels=labels_for_mode(signal_key, label_mode),
        label_mode=label_mode,
    )


def _draw_filler(rng: random.Random, pools: FragmentPools, exclude: Sequence[str] = ()) -> Fragment:
    """Pick a filler library uniformly, then a fragment within it.

    Pooling all filler fragments together would let the largest library
    outweigh the smallest roughly 3:1 and lose entropy coverage, so the
    library is the unit of uniformity, not the fragment.
    """
    candidates = [name for name in pools.filler_libraries if name not in exclude]
    if not candidates:
        raise PoolError(f"split {pools.split!r} has no filler library outside {list(exclude)}")
    library = rng.choice(candidates)
    return rng.choice(pools.filler_pool(library))


def select_fragments(rng: random.Random, pools: FragmentPools, label_mode: str) -> list[Fragment]:
    """Choose exactly :data:`FRAGMENTS_PER_EXAMPLE` fragments for a label mode.

    The invariants of Fine_tuning_plan.md section 5.2 hold by construction
    here, not by a check afterwards: each mode reads from exactly one signal
    pool, so a ``false`` example cannot contain a positive fragment, no example
    holds both a positive and a negative, and no example holds a decisive
    fragment alongside an ambiguous one.
    """
    if label_mode == "true":
        chosen = [rng.choice(pools.positive), _draw_filler(rng, pools)]
    elif label_mode == "false":
        chosen = [rng.choice(pools.negative), _draw_filler(rng, pools)]
    elif label_mode == "null_ambiguous":
        chosen = [rng.choice(pools.ambiguous), _draw_filler(rng, pools)]
    elif label_mode == "null_structural":
        # Two fillers from two different libraries: same-library pairs read
        # oddly and narrow the distribution for no gain.
        first = _draw_filler(rng, pools)
        chosen = [first, _draw_filler(rng, pools, exclude=(first.library,))]
    else:
        raise ValueError(f"unknown label mode {label_mode!r}")

    # A decisive fragment must be able to sit first or second.
    rng.shuffle(chosen)
    if len(chosen) != FRAGMENTS_PER_EXAMPLE:
        raise AssertionError(
            f"{label_mode!r} produced {len(chosen)} fragments, not {FRAGMENTS_PER_EXAMPLE}"
        )
    return chosen


def assemble_text(fragments: Sequence[Fragment]) -> str:
    """Join fragments into one blurb, preserving each fragment verbatim.

    Only two edits are made: surrounding whitespace goes, and a terminal ``.``
    is appended where a fragment ends with no sentence punctuation. Casing,
    contractions and typos are kept -- the encoder receives raw user input at
    runtime, so laundering it here would train on a distribution the encoder
    never sees.
    """
    parts = []
    for fragment in fragments:
        text = fragment.text.strip()
        if text and text[-1] not in _TERMINAL_PUNCTUATION:
            text += "."
        parts.append(text)
    return " ".join(parts)


def generate(
    pools: FragmentPools,
    *,
    count: int,
    seed: int,
    distribution: dict[str, float] | None = None,
    null_ambiguous_ratio: float = DEFAULT_NULL_AMBIGUOUS_RATIO,
) -> tuple[list[AssembledExample], dict]:
    """Generate ``count`` examples for one split, plus generation telemetry.

    Returns ``(examples, telemetry)``. Telemetry feeds the stats sidecar and is
    kept separate from the examples so the JSONL stays exactly the training
    schema.
    """
    if count < 0:
        raise ValueError(f"count must not be negative: {count}")
    if not 0.0 <= null_ambiguous_ratio <= 1.0:
        raise DistributionError(f"null-ambiguous-ratio must be in [0, 1]: {null_ambiguous_ratio}")
    distribution = dict(distribution or DEFAULT_DISTRIBUTION)

    examples: list[AssembledExample] = []
    # Membership-tested only, never iterated, so it cannot perturb determinism.
    seen: set[str] = set()
    rejections = 0
    max_retries = 0

    for index in range(count):
        # Per-example seeds, so changing --count does not reshuffle examples
        # that were already generated. Random() seeds from a string via
        # SHA-512, so this is stable across processes and PYTHONHASHSEED.
        rng = random.Random(f"{seed}|{pools.split}|{index}")
        spec = make_spec(
            rng,
            example_id=f"{pools.split}-{index:06d}",
            signal_key=pools.signal_key,
            distribution=distribution,
            null_ambiguous_ratio=null_ambiguous_ratio,
        )

        for attempt in range(MAX_ASSEMBLY_RETRIES + 1):
            fragments = select_fragments(rng, pools, spec.label_mode)
            text = assemble_text(fragments)
            key = normalise(text)
            if key not in seen:
                break
            rejections += 1
            max_retries = max(max_retries, attempt + 1)
        else:
            # Never silently emit fewer examples than requested, and never
            # silently skew the distribution by giving up on a label mode.
            raise PoolExhaustedError(
                f"could not find an unused {spec.label_mode!r} example for split "
                f"{pools.split!r} after {MAX_ASSEMBLY_RETRIES} retries at index {index}; "
                "the fragment pool is too small for the requested count"
            )

        seen.add(key)
        examples.append(
            AssembledExample(
                example_id=spec.example_id,
                split=pools.split,
                text=text,
                labels=spec.labels,
                meta={
                    "label_mode": spec.label_mode,
                    "fragment_ids": [f.fragment_id for f in fragments],
                    "fragment_subclasses": [f.subclass for f in fragments],
                    "seed": seed,
                    "generator_version": GENERATOR_VERSION,
                },
            )
        )

    telemetry = {
        "duplicate_rejections": rejections,
        "max_retries_for_one_example": max_retries,
    }
    return examples, telemetry


def _percentile(values: Sequence[int], fraction: float) -> float:
    """Nearest-rank percentile over a sorted copy of ``values``."""
    if not values:
        return 0.0
    ordered = sorted(values)
    rank = min(len(ordered), max(1, math.ceil(fraction * len(ordered))))
    return float(ordered[rank - 1])


def _median(values: Sequence[int]) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    mid = len(ordered) // 2
    if len(ordered) % 2:
        return float(ordered[mid])
    return (ordered[mid - 1] + ordered[mid]) / 2


def _length_stats(texts: Sequence[str]) -> dict:
    counts = [len(text.split()) for text in texts]
    return {
        "count": len(counts),
        "median_tokens": _median(counts),
        "p90_tokens": _percentile(counts, 0.9),
    }


def build_stats(
    examples: Sequence[AssembledExample],
    *,
    telemetry: dict,
    fragments: Iterable[Fragment],
    pools: FragmentPools,
    count: int,
    seed: int,
    distribution: dict[str, float],
    null_ambiguous_ratio: float,
    manifest_path: str,
    ruleset_path: str,
) -> dict:
    """Assemble the stats sidecar.

    This is the first thing anyone reaches for when a training run looks
    wrong, so it records what was asked for next to what was produced -- and
    the length distribution per label class, which is the one known confound
    this pipeline measures rather than mitigates.
    """
    signal_key = pools.signal_key

    realised_modes = {mode: 0 for mode in LABEL_MODES}
    realised_labels = {label: 0 for label in LABELS}
    texts_by_mode: dict[str, list[str]] = {mode: [] for mode in LABEL_MODES}
    texts_by_label: dict[str, list[str]] = {label: [] for label in LABELS}

    for example in examples:
        mode = example.meta["label_mode"]
        label = "null" if example.labels[signal_key] is None else str(example.labels[signal_key])
        label = label.lower()
        realised_modes[mode] += 1
        realised_labels[label] += 1
        texts_by_mode[mode].append(example.text)
        texts_by_label[label].append(example.text)

    pool_sizes: dict[str, dict[str, int]] = {}
    for fragment in fragments:
        pool_sizes.setdefault(fragment.library, {"train": 0, "val": 0, "test": 0})
        pool_sizes[fragment.library][fragment.split] += 1

    return {
        "generator_version": GENERATOR_VERSION,
        "seed": seed,
        "signal": signal_key,
        "split": pools.split,
        "manifest": manifest_path,
        "ruleset": ruleset_path,
        "requested": {
            "count": count,
            "distribution": {label: distribution[label] for label in LABELS},
            "null_ambiguous_ratio": null_ambiguous_ratio,
            "labels": {label: round(count * distribution[label]) for label in LABELS},
        },
        "realised": {
            "count": len(examples),
            "labels": realised_labels,
            "label_modes": realised_modes,
        },
        "fragment_pool_sizes": {name: pool_sizes[name] for name in sorted(pool_sizes)},
        "split_pool_sizes": {
            "positive": len(pools.positive),
            "negative": len(pools.negative),
            "ambiguous_or_confounder": len(pools.ambiguous),
            "filler": {name: len(pool) for name, pool in pools.filler},
        },
        "duplicate_rejections": telemetry["duplicate_rejections"],
        "max_retries_for_one_example": telemetry["max_retries_for_one_example"],
        # DD6: fragment count is held constant, fragment length is not. If the
        # class medians differ by more than roughly 1.5x, length is a usable
        # proxy for the label and that is an argument for rebalancing the
        # libraries, not for changing this script.
        "token_counts": {
            "by_label": {label: _length_stats(texts_by_label[label]) for label in LABELS},
            "by_label_mode": {mode: _length_stats(texts_by_mode[mode]) for mode in LABEL_MODES},
        },
    }


def to_record(example: AssembledExample) -> dict:
    """Render one example as the training-schema dict written to JSONL."""
    return {
        "example_id": example.example_id,
        "split": example.split,
        "text": example.text,
        "labels": example.labels,
        "meta": example.meta,
    }

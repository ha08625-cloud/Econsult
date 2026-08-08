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
* **The fragment-count mix does not vary by label mode.** The count is drawn
  from one distribution that never sees the label. If it varied, text length
  would be a usable proxy for the label -- see
  :data:`DEFAULT_FRAGMENT_COUNTS`.
"""

from __future__ import annotations

import math
import random
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass

from .manifest import Fragment, cluster_key
from .normalise import normalise

#: Bumped when a change to this module would alter the emitted dataset.
GENERATOR_VERSION = 2

#: How many fragments an example is built from, as a weighted mix. Drawn per
#: example from **one distribution that knows nothing about the label mode**,
#: and that is the whole safety argument for this knob: if three-fragment
#: examples were more often ``true`` than ``null``, text length would become a
#: usable proxy for the label and the validation score would look good while
#: the model learned nothing about fever. The stats sidecar reports realised
#: counts per label so the property is checked on every run, not assumed.
#:
#: Exactly one decisive fragment at every count; the remainder are filler, so
#: the decisive fragment's share of the text falls as the count rises. That is
#: the point (harder, more realistic examples), but it is also why "more is
#: better" is false here: past some count each example still carries one
#: supervised claim, buried in progressively more noise.
DEFAULT_FRAGMENT_COUNTS = {2: 0.5, 3: 0.5}

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
    #: Drawn independently of the label mode, and held fixed across the
    #: duplicate-retry loop in :func:`generate` so a count that is harder to
    #: satisfy uniquely cannot be quietly under-sampled.
    fragment_count: int


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


def _parse_weighted_terms(text: str, *, flag: str, term: str) -> dict[str, float]:
    """Parse ``a=0.6,b=0.4`` into ``{"a": 0.6, "b": 0.4}``.

    Shared by every weighted-mix flag. ``flag`` and ``term`` are interpolated
    into the messages so a bad ``--fragment-counts`` does not report itself as
    a ``--dist`` problem. Keys are returned verbatim; the caller decides what a
    key is allowed to be.
    """
    parsed: dict[str, float] = {}
    for chunk in text.split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        key, sep, raw = chunk.partition("=")
        key = key.strip()
        if not sep:
            raise DistributionError(f"malformed {flag} term {chunk!r}, expected '{term}=weight'")
        if key in parsed:
            raise DistributionError(f"{term} {key!r} appears twice in {flag}")
        try:
            weight = float(raw)
        except ValueError:
            raise DistributionError(f"weight for {key!r} is not a number: {raw!r}") from None
        if weight < 0:
            raise DistributionError(f"weight for {key!r} is negative: {weight}")
        parsed[key] = weight
    return parsed


def _check_weights_sum_to_one(weights: Mapping[object, float], *, flag: str) -> None:
    """A mix that silently does not sum to one skews the dataset undetectably."""
    total = sum(weights.values())
    if abs(total - 1.0) > 1e-9:
        raise DistributionError(f"{flag} weights sum to {total!r}, not 1.0")


def parse_distribution(text: str) -> dict[str, float]:
    """Parse ``null=0.60,false=0.25,true=0.15`` into a validated distribution.

    Rejects unknown labels, missing labels, and any total that is not 1.0
    within float tolerance -- a distribution that silently does not sum to one
    would skew the dataset in a way nothing downstream could detect.
    """
    parsed: dict[str, float] = {}
    for label, weight in _parse_weighted_terms(text, flag="--dist", term="label").items():
        if label not in LABELS:
            raise DistributionError(
                f"unknown label {label!r} in --dist (permitted: {', '.join(LABELS)})"
            )
        parsed[label] = weight

    missing = [label for label in LABELS if label not in parsed]
    if missing:
        raise DistributionError(f"--dist is missing weights for: {', '.join(missing)}")

    _check_weights_sum_to_one(parsed, flag="--dist")
    return parsed


def parse_fragment_counts(text: str) -> dict[int, float]:
    """Parse ``2=0.5,3=0.5`` into a validated fragment-count mix.

    Bounded below at two: a lone filler is a trivially easy ``null`` and a lone
    decisive fragment removes the noise floor entirely. There is no upper bound
    here -- the real ceiling is the number of filler libraries available, which
    only :func:`generate` knows.
    """
    parsed: dict[int, float] = {}
    for raw_key, weight in _parse_weighted_terms(
        text, flag="--fragment-counts", term="count"
    ).items():
        try:
            count = int(raw_key)
        except ValueError:
            raise DistributionError(
                f"fragment count {raw_key!r} in --fragment-counts is not an integer"
            ) from None
        if count < 2:
            raise DistributionError(
                f"fragment count {count} in --fragment-counts is below the minimum of 2"
            )
        if count in parsed:
            raise DistributionError(f"count {count!r} appears twice in --fragment-counts")
        parsed[count] = weight

    if not parsed:
        raise DistributionError("--fragment-counts is empty, expected e.g. '2=0.5,3=0.5'")

    _check_weights_sum_to_one(parsed, flag="--fragment-counts")
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


def _weighted_draw[KeyT](
    rng: random.Random, weights: Mapping[KeyT, float], order: Sequence[KeyT]
) -> KeyT:
    """Cumulative-sum draw over ``order``, consuming exactly one ``random()``.

    ``order`` is explicit rather than taken from ``weights`` because iterating
    the mapping would make the output depend on the order the CLI happened to
    parse the flag's terms in -- the module docstring's rule about sorted
    sequences applies to weight mappings too.
    """
    draw = rng.random()
    cumulative = 0.0
    chosen = order[-1]
    for candidate in order:
        cumulative += weights[candidate]
        if draw < cumulative:
            chosen = candidate
            break
    return chosen


def sample_label_mode(
    rng: random.Random, distribution: dict[str, float], null_ambiguous_ratio: float
) -> str:
    """Draw a label mode. Called before any fragment is looked at."""
    label = _weighted_draw(rng, distribution, LABELS)
    if label != "null":
        return label
    return "null_ambiguous" if rng.random() < null_ambiguous_ratio else "null_structural"


def sample_fragment_count(rng: random.Random, fragment_counts: Mapping[int, float]) -> int:
    """Draw how many fragments this example holds.

    Deliberately takes no label or label mode: the mix must be identical across
    all four modes or fragment count becomes a proxy for the label.
    """
    return _weighted_draw(rng, fragment_counts, sorted(fragment_counts))


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
    fragment_counts: Mapping[int, float],
) -> ExampleSpec:
    """Build the label-first spec for one example.

    The count is drawn **after** the label mode, and the order is load-bearing
    in two ways. It leaves ``sample_label_mode`` consuming exactly the draws it
    consumed before this feature existed, so the realised label distribution
    for a given seed does not move; and it keeps the count downstream of the
    label rather than entangled with it.
    """
    label_mode = sample_label_mode(rng, distribution, null_ambiguous_ratio)
    return ExampleSpec(
        example_id=example_id,
        labels=labels_for_mode(signal_key, label_mode),
        label_mode=label_mode,
        fragment_count=sample_fragment_count(rng, fragment_counts),
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


def select_fragments(
    rng: random.Random, pools: FragmentPools, label_mode: str, fragment_count: int
) -> list[Fragment]:
    """Choose exactly ``fragment_count`` fragments for a label mode.

    The invariants of Fine_tuning_plan.md section 5.2 hold by construction
    here, not by a check afterwards: each mode reads from exactly one signal
    pool, so a ``false`` example cannot contain a positive fragment, no example
    holds both a positive and a negative, and no example holds a decisive
    fragment alongside an ambiguous one.

    Exactly one decisive fragment at every count (Fine_tuning_plan.md Rule 2 --
    one signal, one decisive fragment); every additional fragment is filler.
    """
    signal_pools = {
        "true": pools.positive,
        "false": pools.negative,
        "null_ambiguous": pools.ambiguous,
    }
    if label_mode in signal_pools:
        chosen = [rng.choice(signal_pools[label_mode])]
        fillers_wanted = fragment_count - 1
    elif label_mode == "null_structural":
        chosen = []
        fillers_wanted = fragment_count
    else:
        raise ValueError(f"unknown label mode {label_mode!r}")

    # Every filler in an example comes from a different library: repeats read
    # as consecutive tangents in the same voice and narrow the distribution for
    # no gain. This is what caps the fragment count at the number of filler
    # libraries, checked up front in generate().
    used_libraries: list[str] = []
    for _ in range(fillers_wanted):
        filler = _draw_filler(rng, pools, exclude=used_libraries)
        used_libraries.append(filler.library)
        chosen.append(filler)

    # A decisive fragment must be able to sit in any position.
    rng.shuffle(chosen)
    if len(chosen) != fragment_count:
        raise AssertionError(
            f"{label_mode!r} produced {len(chosen)} fragments, not {fragment_count}"
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
    fragment_counts: Mapping[int, float] | None = None,
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
    fragment_counts = dict(fragment_counts or DEFAULT_FRAGMENT_COUNTS)

    # Checked here rather than in _check_pools, which cannot know the requested
    # mix: an N-fragment structural null needs N distinct filler libraries, so
    # the largest requested count is a hard floor on how many must exist.
    largest = max(fragment_counts)
    if len(pools.filler) < largest:
        raise PoolError(
            f"--fragment-counts asks for up to {largest} fragments per example, which needs "
            f"{largest} distinct filler libraries, but split {pools.split!r} has "
            f"{len(pools.filler)}: {', '.join(pools.filler_libraries)}"
        )

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
            fragment_counts=fragment_counts,
        )

        for attempt in range(MAX_ASSEMBLY_RETRIES + 1):
            fragments = select_fragments(rng, pools, spec.label_mode, spec.fragment_count)
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
                f"could not find an unused {spec.fragment_count}-fragment "
                f"{spec.label_mode!r} example for split {pools.split!r} after "
                f"{MAX_ASSEMBLY_RETRIES} retries at index {index}; "
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


def _fragment_provenance(fragments: Iterable[Fragment], split: str) -> dict[str, dict]:
    """Project the split's fragments into the sidecar's ``fragments`` block.

    Everything here already lives on :class:`~.manifest.Fragment`; none of it
    survives into the dataset otherwise. ``meta.fragment_ids`` name the library
    but say nothing about which fragments are the same idea, and nothing at all
    says which libraries are filler -- so without this block a consumer cannot
    compute effective sample size, which is the number of distinct *clusters*
    behind a slice rather than the number of examples.

    The obvious alternative -- have the consumer re-read the manifest and the
    ``.txt`` libraries -- is rejected because it fails silently. Edit a library
    after generating and the cluster grouping is quietly wrong, producing
    confidence intervals that are too narrow with nothing raised anywhere. A
    dataset and its sidecar describe themselves; that is the whole point.

    Only the generated split's fragments are recorded, because only they can
    appear in the JSONL. ``split`` is kept on every entry regardless, so blocks
    merged across a fold's three sidecars stay unambiguous.
    """
    return {
        fragment.fragment_id: {
            "library": fragment.library,
            "cluster_key": cluster_key(fragment.cluster_id, fragment.text),
            "fragment_type": fragment.fragment_type,
            "signal_key": fragment.signal_key,
            "subclass": fragment.subclass,
            "split": fragment.split,
        }
        for fragment in sorted(
            (f for f in fragments if f.split == split), key=lambda f: f.fragment_id
        )
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
    fragment_counts: Mapping[int, float],
    manifest_path: str,
    ruleset_path: str,
    folds: int | None = None,
    fold_index: int | None = None,
    split_salt: str = "",
) -> dict:
    """Assemble the stats sidecar.

    This is the first thing anyone reaches for when a training run looks
    wrong, so it records what was asked for next to what was produced -- and
    the length distribution per label class, which is the one known confound
    this pipeline measures rather than mitigates.

    Every emitted mapping is string-keyed, including the fragment-count
    tallies. ``json.dump`` coerces integer keys to strings silently, and a dict
    that is written string-keyed but built int-keyed will bite whoever reads
    the sidecar back.

    The fold configuration is recorded because a dataset whose fold
    configuration is unknown is uninterpretable: ``test`` means a different set
    of clusters under every ``(folds, fold_index, split_salt)`` triple, and
    nothing in the JSONL says which one produced it.
    """
    signal_key = pools.signal_key
    fragments = list(fragments)
    count_keys = [str(n) for n in sorted(fragment_counts)]

    def _empty_count_tally() -> dict[str, int]:
        return {key: 0 for key in count_keys}

    realised_modes = {mode: 0 for mode in LABEL_MODES}
    realised_labels = {label: 0 for label in LABELS}
    texts_by_mode: dict[str, list[str]] = {mode: [] for mode in LABEL_MODES}
    texts_by_label: dict[str, list[str]] = {label: [] for label in LABELS}
    counts_by_mode = {mode: _empty_count_tally() for mode in LABEL_MODES}
    counts_by_label = {label: _empty_count_tally() for label in LABELS}
    texts_by_count: dict[str, list[str]] = {key: [] for key in count_keys}

    for example in examples:
        mode = example.meta["label_mode"]
        label = "null" if example.labels[signal_key] is None else str(example.labels[signal_key])
        label = label.lower()
        # DD8: derived, never stored twice. A second copy is one more thing
        # that can disagree with itself.
        count_key = str(len(example.meta["fragment_ids"]))
        realised_modes[mode] += 1
        realised_labels[label] += 1
        texts_by_mode[mode].append(example.text)
        texts_by_label[label].append(example.text)
        counts_by_mode[mode][count_key] = counts_by_mode[mode].get(count_key, 0) + 1
        counts_by_label[label][count_key] = counts_by_label[label].get(count_key, 0) + 1
        texts_by_count.setdefault(count_key, []).append(example.text)

    pool_sizes: dict[str, dict[str, int]] = {}
    for fragment in fragments:
        pool_sizes.setdefault(fragment.library, {"train": 0, "val": 0, "test": 0})
        pool_sizes[fragment.library][fragment.split] += 1

    return {
        "generator_version": GENERATOR_VERSION,
        "seed": seed,
        "signal": signal_key,
        "split": pools.split,
        "folds": folds,
        "fold_index": fold_index,
        "split_salt": split_salt,
        "manifest": manifest_path,
        "ruleset": ruleset_path,
        "requested": {
            "count": count,
            "distribution": {label: distribution[label] for label in LABELS},
            "null_ambiguous_ratio": null_ambiguous_ratio,
            "labels": {label: round(count * distribution[label]) for label in LABELS},
            "fragment_counts": {str(n): fragment_counts[n] for n in sorted(fragment_counts)},
        },
        "realised": {
            "count": len(examples),
            "labels": realised_labels,
            "label_modes": realised_modes,
        },
        # The leak detector for the variable fragment count, and the reason it
        # is safe. The count mix is drawn independently of the label, so these
        # rows should agree with each other and with the requested mix. If one
        # label ever skews long, fragment count has become a proxy for the
        # label -- the exact shortcut a fixed count used to rule out.
        "fragment_counts": {
            "by_label": {label: counts_by_label[label] for label in LABELS},
            "by_label_mode": {mode: counts_by_mode[mode] for mode in LABEL_MODES},
        },
        "fragment_pool_sizes": {name: pool_sizes[name] for name in sorted(pool_sizes)},
        # Cluster and library provenance for every fragment this split could
        # draw on. Effective sample size is counted in clusters, and slicing is
        # done per library and per fragment; neither is recoverable from the
        # JSONL alone. See _fragment_provenance.
        "fragments": _fragment_provenance(fragments, pools.split),
        "split_pool_sizes": {
            "positive": len(pools.positive),
            "negative": len(pools.negative),
            "ambiguous_or_confounder": len(pools.ambiguous),
            "filler": {name: len(pool) for name, pool in pools.filler},
        },
        "duplicate_rejections": telemetry["duplicate_rejections"],
        "max_retries_for_one_example": telemetry["max_retries_for_one_example"],
        # DD6: fragment count varies but its distribution does not vary by
        # label; fragment length is not controlled at all. If the class medians
        # differ by more than roughly 1.5x, length is a usable proxy for the
        # label and that is an argument for rebalancing the libraries, not for
        # changing this script. Read the by_label row against the by_label row
        # of fragment_counts above: a length gap that the count mix explains is
        # a different problem from one it does not.
        "token_counts": {
            "by_label": {label: _length_stats(texts_by_label[label]) for label in LABELS},
            "by_label_mode": {mode: _length_stats(texts_by_mode[mode]) for mode in LABEL_MODES},
            "by_fragment_count": {
                key: _length_stats(texts) for key, texts in sorted(texts_by_count.items())
            },
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

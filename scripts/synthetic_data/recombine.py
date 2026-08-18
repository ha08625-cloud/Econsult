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
#: 3 adds the companion draw and ``meta.filler_only``. The draw is inert at
#: ``--companion-share 0`` -- the fragments chosen for a given seed are exactly
#: what version 2 chose, pinned by ``GOLDEN_DEFAULT_SPLIT_CONTENT_SHA256`` --
#: but the extra ``meta`` key moves every byte, so the version moves with it.
GENERATOR_VERSION = 3

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

#: Share of an example's non-decisive slots that carry another signal's
#: clinical language instead of filler. 0.0 reproduces every dataset generated
#: before companions existed, and the whole path is skipped at that value.
#:
#: The failure this exists to fix: every ``null`` example ever generated paired
#: the absence of the signal's language with bland non-clinical filler, so
#: "clinical-sounding text -> not null" was a perfect rule on our data and a
#: catastrophic one on real submissions, where the median message asserts
#: something about two of the six signals.
DEFAULT_COMPANION_SHARE = 0.0

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
    #: Foreign-signal fragments eligible to stand in a non-decisive slot, as
    #: ``(signal, library, fragments)`` sorted by both names. Eligibility is the
    #: library's ``null_on`` declaration for ``signal_key`` and nothing else.
    #:
    #: **Nothing draws from this yet.** It is built here so that the companion
    #: draw, when it arrives, reads a pool rather than re-deriving eligibility
    #: from the manifest at draw time. Populating it changes no generated byte,
    #: which a test asserts against the golden digest.
    companion: tuple[tuple[str, str, tuple[Fragment, ...]], ...] = ()
    #: Filler libraries dropped from ``filler`` because they are undeclared on
    #: ``signal_key``. Recorded rather than merely discarded: a silently smaller
    #: filler pool changes every ``_draw_filler`` outcome with nothing to show
    #: for it, and the CLI prints this list.
    undeclared_filler: tuple[str, ...] = ()

    @property
    def filler_libraries(self) -> tuple[str, ...]:
        return tuple(name for name, _ in self.filler)

    @property
    def companion_signals(self) -> tuple[str, ...]:
        """Signals with at least one eligible companion library, in draw order."""
        return tuple(sorted({signal for signal, _, _ in self.companion}))

    def filler_pool(self, library: str) -> tuple[Fragment, ...]:
        for name, fragments in self.filler:
            if name == library:
                return fragments
        raise KeyError(library)

    def companion_pool(self, signal: str, library: str) -> tuple[Fragment, ...]:
        for candidate, name, fragments in self.companion:
            if candidate == signal and name == library:
                return fragments
        raise KeyError((signal, library))


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

    A fragment reaches a non-decisive slot only if its library has *declared*
    that ``signal_key`` is ``null`` on every one of its lines. That was always
    the rule; what changed is that the declaration is now written down in the
    manifest instead of being assumed for filler and unavailable for everything
    else. Two consequences:

    * **Filler is filtered rather than trusted.** Filler has been silent on all
      seven signals since the lint started checking, so today the filter removes
      nothing and the golden digest holds. It stops being free the moment a
      filler library goes undeclared on some signal, and that is a reason to
      keep it from happening quietly rather than a reason to skip the filter.
    * **Other signals' fragments are collected instead of dropped.** They were
      dropped because "a ``dysuria_present`` positive says nothing about
      ``fever_present``" was library work nobody had done; the ``null_on``
      declaration is that work. An *undeclared* pair is still ineligible, which
      is the honest state rather than a workaround: a smaller companion pool is
      a smaller dataset, not a wrong one.

    A library's own signal never appears in ``companion``. The primary signal
    enters an example through the decisive slot alone -- otherwise a
    ``fever_null_hedged`` fragment could land in a ``fever_present`` structural
    null, and ``--null-ambiguous-ratio`` would stop distinguishing anything.
    """
    in_split = sorted(
        (f for f in fragments if f.split == split),
        key=lambda f: f.fragment_id,
    )

    def signal_pool(*types: str) -> tuple[Fragment, ...]:
        return tuple(f for f in in_split if f.signal_key == signal_key and f.fragment_type in types)

    filler_by_library: dict[str, list[Fragment]] = {}
    undeclared_filler: set[str] = set()
    companion_by_pair: dict[tuple[str, str], list[Fragment]] = {}
    for fragment in in_split:
        if fragment.fragment_type == "filler":
            if fragment.declares_null_on(signal_key):
                filler_by_library.setdefault(fragment.library, []).append(fragment)
            else:
                undeclared_filler.add(fragment.library)
        elif fragment.signal_key != signal_key and fragment.declares_null_on(signal_key):
            companion_by_pair.setdefault((fragment.signal_key, fragment.library), []).append(
                fragment
            )

    pools = FragmentPools(
        split=split,
        signal_key=signal_key,
        positive=signal_pool("positive"),
        negative=signal_pool("negative"),
        ambiguous=signal_pool("ambiguous", "confounder"),
        filler=tuple((name, tuple(filler_by_library[name])) for name in sorted(filler_by_library)),
        companion=tuple(
            (signal, library, tuple(companion_by_pair[(signal, library)]))
            for signal, library in sorted(companion_by_pair)
        ),
        undeclared_filler=tuple(sorted(undeclared_filler)),
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
            f"split {pools.split!r} has {len(pools.filler)} filler libraries eligible for "
            f"signal {pools.signal_key!r}, but structural nulls need two distinct ones"
            + undeclared_filler_hint(pools)
        )


def undeclared_filler_hint(pools: FragmentPools) -> str:
    """Name the filler libraries an undeclared pair has taken out of the run.

    A pool error whose real cause is a missing manifest declaration reads as a
    library-size problem otherwise, and the fix is three lines of JSON rather
    than three hundred fragments. Empty when nothing was excluded, so the
    ordinary too-small-library message is unchanged.
    """
    if not pools.undeclared_filler:
        return ""
    return (
        f"; {len(pools.undeclared_filler)} further filler librar"
        f"{'y is' if len(pools.undeclared_filler) == 1 else 'ies are'} undeclared on "
        f"{pools.signal_key!r} and therefore ineligible "
        f"({', '.join(pools.undeclared_filler)}). Resolve each pair one of three ways "
        "(arch_training.md section 4): leave it undeclared and accept the smaller pool, "
        'add a null_on entry with basis "absent" if the library never mentions the signal, '
        'or basis "policy" plus a note if it does mention it and the label is null anyway'
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


def companion_bounds(
    fragment_count: int, *, filler_libraries: int, companion_signals: int
) -> tuple[int, int]:
    """How many companions an example of ``fragment_count`` fragments may hold.

    Takes no label and no label mode, and that is the point (DD5). A structural
    null has one *more* non-decisive slot than every other mode at the same
    count, so an independent per-slot draw would give structural nulls twice the
    companions at the default count of two -- and companion count would become a
    proxy for the label pointing the wrong way: *more clinical text -> more
    likely null*. A model can learn that without reading anything, and it would
    flatter this change for exactly the wrong reason.

    So the draw runs over ``fragment_count - 1`` slots in **every** mode. A
    structural null's remaining slot is always filler, which also keeps at least
    one filler fragment in it. The equalisation is by construction rather than by
    check.

    Both bounds are functions of the count and the pool sizes alone:

    * **Upper** -- one fragment per signal (DD8), so no more companions than
      there are eligible signals, and never the whole example.
    * **Lower** -- every filler in an example comes from a different library, so
      an example wanting more fillers than there are filler libraries must make
      up the difference in companions. This is what raises the fragment-count
      ceiling above the number of filler libraries for the first time (DD17);
      at ``--companion-share 0`` the upper bound is forced to zero and the lower
      bound must therefore be zero, which is the pre-companion ceiling exactly.
    """
    upper = min(fragment_count - 1, companion_signals)
    lower = max(0, fragment_count - filler_libraries)
    return lower, upper


def sample_companion_count(
    rng: random.Random, *, bounds: tuple[int, int], companion_share: float
) -> int:
    """Draw how many of this example's non-decisive slots carry a companion.

    Deliberately takes no label and no label mode, for the same reason
    :func:`sample_fragment_count` does not: the distribution must be identical
    across all four modes or the count becomes a proxy for the label. ``bounds``
    comes from :func:`companion_bounds`, which is itself label-blind.

    Consumes no randomness at ``companion_share == 0``, so a run at the default
    draws exactly the sequence it drew before companions existed.
    """
    lower, upper = bounds
    if companion_share <= 0.0:
        if lower > 0:
            raise PoolError(
                f"an example needs at least {lower} companion fragments but --companion-share is 0"
            )
        return 0
    drawn = sum(1 for _ in range(upper) if rng.random() < companion_share)
    return max(drawn, lower)


def _draw_companion(
    rng: random.Random, pools: FragmentPools, exclude: Sequence[str] = ()
) -> Fragment:
    """Pick a foreign signal uniformly, then a library within it, then a fragment.

    Uniform over *signals* rather than over the pooled fragments, for the reason
    :func:`_draw_filler` picks a library first: pooling would let the largest
    library speak for its signal. None of the three draws sees the label mode
    (DD6) -- if they did, companions would be disproportionately ``true`` in
    ``true`` examples and we would have replaced "clinical language -> not null"
    with "clinical language -> true", which is the same failure wearing a
    different hat.

    ``exclude`` carries the signals already drawn for this example, so no example
    holds two fragments from one signal (DD8). Two would either agree, doubling
    the evidence for one claim and teaching nothing, or disagree, which no single
    emitted label could describe.

    The primary signal is not in ``pools.companion`` at all: it enters an example
    through the decisive slot alone.
    """
    signals = [signal for signal in pools.companion_signals if signal not in exclude]
    if not signals:
        raise PoolError(
            f"split {pools.split!r} has no companion signal for {pools.signal_key!r} "
            f"outside {list(exclude)}"
        )
    signal = rng.choice(signals)
    libraries = [library for candidate, library, _ in pools.companion if candidate == signal]
    library = rng.choice(libraries)
    return rng.choice(pools.companion_pool(signal, library))


def select_fragments(
    rng: random.Random,
    pools: FragmentPools,
    label_mode: str,
    fragment_count: int,
    *,
    companion_share: float = DEFAULT_COMPANION_SHARE,
) -> list[Fragment]:
    """Choose exactly ``fragment_count`` fragments for a label mode.

    The invariants of Fine_tuning_plan.md section 5.2 hold by construction
    here, not by a check afterwards: each mode reads from exactly one signal
    pool, so a ``false`` example cannot contain a positive fragment, no example
    holds both a positive and a negative, and no example holds a decisive
    fragment alongside an ambiguous one.

    Exactly one decisive fragment at every count (Fine_tuning_plan.md Rule 2 --
    one signal, one decisive fragment); every remaining slot is filler, or -- at
    ``companion_share > 0`` -- another signal's clinical language, which is
    ``null`` on this signal because the library said so in the manifest.
    """
    signal_pools = {
        "true": pools.positive,
        "false": pools.negative,
        "null_ambiguous": pools.ambiguous,
    }
    if label_mode in signal_pools:
        chosen = [rng.choice(signal_pools[label_mode])]
    elif label_mode == "null_structural":
        chosen = []
    else:
        raise ValueError(f"unknown label mode {label_mode!r}")

    # Drawn from the count and the pool sizes alone, never from label_mode --
    # see companion_bounds. At share 0 this consumes no randomness and returns
    # zero, so the filler loop below draws exactly what it always drew.
    companions_wanted = sample_companion_count(
        rng,
        bounds=companion_bounds(
            fragment_count,
            filler_libraries=len(pools.filler),
            companion_signals=len(pools.companion_signals),
        ),
        companion_share=companion_share,
    )
    fillers_wanted = fragment_count - len(chosen) - companions_wanted

    # Every filler in an example comes from a different library: repeats read
    # as consecutive tangents in the same voice and narrow the distribution for
    # no gain. This is what caps the fragment count at the number of filler
    # libraries plus the number of companion signals, checked up front in
    # generate().
    used_libraries: list[str] = []
    for _ in range(fillers_wanted):
        filler = _draw_filler(rng, pools, exclude=used_libraries)
        used_libraries.append(filler.library)
        chosen.append(filler)

    # One fragment per signal, tracked the way used_libraries tracks filler.
    used_signals: list[str] = []
    for _ in range(companions_wanted):
        companion = _draw_companion(rng, pools, exclude=used_signals)
        used_signals.append(str(companion.signal_key))
        chosen.append(companion)

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
    companion_share: float = DEFAULT_COMPANION_SHARE,
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
    if not 0.0 <= companion_share <= 1.0:
        raise DistributionError(f"companion-share must be in [0, 1]: {companion_share}")
    distribution = dict(distribution or DEFAULT_DISTRIBUTION)
    fragment_counts = dict(fragment_counts or DEFAULT_FRAGMENT_COUNTS)

    if companion_share > 0.0 and not pools.companion_signals:
        # Loud rather than a silent fallback to filler: a run asked for
        # companions and would otherwise produce the control arm's dataset
        # under the treatment arm's flags, which nothing downstream could tell
        # apart from the real thing.
        raise PoolError(
            f"--companion-share {companion_share} was requested but split {pools.split!r} has no "
            f"library declared null_on {pools.signal_key!r} outside that signal's own libraries"
        )

    # Checked here rather than in _check_pools, which cannot know the requested
    # mix. An N-fragment example needs N distinct sources: filler libraries, and
    # -- at companion_share > 0 -- eligible companion signals, at most one
    # fragment each. At share 0 the companion bound is zero and this is exactly
    # the pre-companion check: N distinct filler libraries for a structural null.
    largest = max(fragment_counts)
    lower, upper = companion_bounds(
        largest,
        filler_libraries=len(pools.filler),
        companion_signals=len(pools.companion_signals) if companion_share > 0.0 else 0,
    )
    if lower > upper:
        needed = (
            "distinct filler libraries"
            if companion_share <= 0.0
            else ("distinct sources (filler libraries plus companion signals, one fragment each)")
        )
        available = (
            f"{len(pools.filler)}: {', '.join(pools.filler_libraries)}"
            if companion_share <= 0.0
            else f"{len(pools.filler) + len(pools.companion_signals)}: "
            f"{', '.join(pools.filler_libraries)} and companions from "
            f"{', '.join(pools.companion_signals)}"
        )
        raise PoolError(
            f"--fragment-counts asks for up to {largest} fragments per example, which needs "
            f"{largest} {needed}, but split {pools.split!r} has {available}"
            + undeclared_filler_hint(pools)
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
            fragments = select_fragments(
                rng,
                pools,
                spec.label_mode,
                spec.fragment_count,
                companion_share=companion_share,
            )
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
                    # DD10: a structural null is no longer filler-only at
                    # companion_share > 0 -- it keeps its name because it keeps
                    # its defining property, no fragment decisive for this
                    # signal. Written once here because the merge's
                    # structural-null dedup and the report both need it and
                    # neither should re-derive it from fragment_ids.
                    "filler_only": all(f.fragment_type == "filler" for f in fragments),
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


#: A companion's own-signal polarity, projected onto the label its own head
#: would carry. ``filler`` never appears here: a companion is by definition a
#: fragment from another signal's library.
_TYPE_TO_LABEL = {
    "positive": "true",
    "negative": "false",
    "ambiguous": "null",
    "confounder": "null",
}


def _companion_stats(
    examples: Sequence[AssembledExample],
    *,
    fragments: Sequence[Fragment],
    signal_key: str,
    max_fragment_count: int,
) -> dict:
    """Tally the companion draw: the leak detector for DD5, plus the mix.

    ``count_by_label_mode`` is the row that matters and nothing downstream would
    surface a violation on its own. A companion count that skews towards
    ``null_structural`` means companion count has become a proxy for the label,
    pointing the wrong way -- *more clinical text -> more likely null* -- and the
    run is void rather than reinterpretable. It would otherwise present as a
    validation score that looks fine and a model that does not transfer, which
    is the shape of the failure this whole feature exists to remove.

    ``label_mix_by_label`` is the second half of the same question asked of
    *which* companion rather than how many: if ``true`` examples drew ``true``
    companions more often than ``null`` examples did, we would have replaced
    "clinical language -> not null" with "clinical language -> true".

    Companions are identified from the split's fragment provenance rather than
    stored per record: a fragment whose ``signal_key`` is neither absent nor the
    primary signal reached a non-decisive slot, which is what a companion is.
    """
    origin = {
        fragment.fragment_id: (fragment.signal_key, fragment.fragment_type)
        for fragment in fragments
    }
    count_keys = [str(n) for n in range(max_fragment_count)]

    def _empty_counts() -> dict[str, int]:
        return {key: 0 for key in count_keys}

    def _empty_labels() -> dict[str, int]:
        return {label: 0 for label in LABELS}

    by_label = {label: _empty_counts() for label in LABELS}
    by_label_mode = {mode: _empty_counts() for mode in LABEL_MODES}
    signals: dict[str, int] = {}
    label_mix = {label: _empty_labels() for label in LABELS}

    for example in examples:
        label = "null" if example.labels[signal_key] is None else str(example.labels[signal_key])
        label = label.lower()
        mode = example.meta["label_mode"]
        drawn = 0
        for fragment_id in example.meta["fragment_ids"]:
            fragment_signal, fragment_type = origin.get(fragment_id, (None, "filler"))
            if fragment_signal is None or fragment_signal == signal_key:
                continue
            drawn += 1
            signals[fragment_signal] = signals.get(fragment_signal, 0) + 1
            companion_label = _TYPE_TO_LABEL[fragment_type]
            label_mix[label][companion_label] += 1
        count_key = str(drawn)
        by_label[label][count_key] = by_label[label].get(count_key, 0) + 1
        by_label_mode[mode][count_key] = by_label_mode[mode].get(count_key, 0) + 1

    return {
        "count_by_label": by_label,
        "count_by_label_mode": by_label_mode,
        "signals": {name: signals[name] for name in sorted(signals)},
        "label_mix_by_label": label_mix,
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
    companion_share: float = DEFAULT_COMPANION_SHARE,
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
            "companion_share": companion_share,
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
        # The DD5 leak detector, in the same shape as fragment_counts above and
        # read the same way: the by_label_mode rows must agree with each other.
        # See _companion_stats for what disagreement means.
        "companions": _companion_stats(
            examples,
            fragments=fragments,
            signal_key=signal_key,
            max_fragment_count=max(fragment_counts),
        ),
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
            "companion": {
                f"{signal}/{library}": len(pool) for signal, library, pool in pools.companion
            },
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

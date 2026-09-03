"""The paraphrase-flip diagnostic: does a trained head change its answer when only the words do?

Task 2 of the lexical variant expansion plan, and the second of its two gates.
Task 1 measured the *libraries* and found a large content-word association --
``fever`` on 91% of ``fever_null_historical`` lines and 0% of
``fever_null_attribution`` ones. A measured association in the data is not
evidence that a trained head uses it. This module tests whether it does, and it
is built to be allowed to come back negative: if a head barely flips under
paraphrase, the expansion pass is not worth building and the ticket stops here.

**What a flip is.** One submission, rewritten so that only its vocabulary and
orthography change -- not its tense, not its person, not its certainty, not its
polarity. Same claim, different words. The fold's decision rule is applied to
both, and the pair *flips* when the two predicted classes differ. A flip is
therefore always an error on one side of the pair, whichever side that is, and
no label is needed to see it. That is what makes this diagnostic cheap: it reads
the 67 real submissions without consuming the holdout's validity, because it
selects nothing and scores no label (plan DD8).

**Where the numbers are computed** is the same tier boundary :mod:`.holdout`
sits on: standard library plus :mod:`.metrics`, with the forward pass
**injected** as a ``(texts) -> {signal: per-class scores}`` callable. Everything
that decides what the number *means* is coverable by CI's unit job on a runner
with no GPU and no ML wheels.

**How the statistic reuses the confusion matrix.** A pair is stored as a
:class:`~.metrics.Prediction` whose ``truth`` is the *source's* predicted class
and whose ``predicted`` is the *variant's*. The confusion matrix of those
predictions is then exactly the flip-direction matrix -- which class went to
which -- and the flip rate is one minus its accuracy. That is not a trick to
save code: 12.6 found decisive recall draining into ``null`` and the *direction*
was the useful half of the finding, so the direction matrix has to be a
first-class output rather than something reconstructed later.

**What it cannot do.** Ten or fifteen submissions with three or four variants
each is thirty to sixty paired observations resampled over ten to fifteen
independent units. That can separate "flips are common" from "flips are rare"
and nothing finer, and :data:`POWER_NOTE` says so beside every number rather
than under it.
"""

from __future__ import annotations

import csv
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from .dataset import CLASS_NAMES, CLASS_TRUE
from .metrics import (
    DEFAULT_ALPHA,
    DEFAULT_RESAMPLES,
    Interval,
    Prediction,
    accuracy,
    apply_margin,
    bootstrap_confusion_ci,
    confusion_matrix,
)

#: The default paraphrase set, and the only one that exists.
DEFAULT_PARAPHRASE_PATH = Path("data/realistic/uti1_paraphrases.tsv")

ID_COLUMN = "variant_id"
SOURCE_COLUMN = "submission_id"
KIND_COLUMN = "kind"
TEXT_COLUMN = "text"

#: The two values ``kind`` may take. ``source`` is the submission verbatim from
#: `uti1_holdout.source.txt`; ``variant`` is a hand-written paraphrase of it.
KIND_SOURCE = "source"
KIND_VARIANT = "variant"

#: Carried into every report that quotes a number from this set, for the same
#: reason `holdout.PROVENANCE_NOTE` is: the variants were written by the same
#: architecture that is being scored, and a reader has to be told that.
PROVENANCE_NOTE = (
    "**The paraphrases were written by Claude and reviewed by the maintainer.** They are not an "
    "independent sample of how a different patient would have phrased the same complaint: they "
    "are one model's idea of which words are interchangeable, scored against a head built by the "
    "same architecture. A flip found here is real -- the two texts make the same claim and the "
    "head answered differently. A flip *not* found here is weaker evidence, because the variants "
    "may simply not have moved the vocabulary the head is actually reading."
)

#: The rule that keeps this diagnostic off the holdout's ledger.
SELECTS_NOTHING_NOTE = (
    "This diagnostic reads the real submissions and scores no label: a flip is a disagreement "
    "between two predictions, so `uti1_holdout.labels.tsv` is never opened. It therefore costs "
    "the holdout nothing as a descriptive measurement (plan DD8). It would cost the holdout its "
    "validity the moment a flip rate were used to choose between two arms, and nothing here does "
    "that: the arm comparison in Task 6 runs on the synthetic tree."
)

#: What the sample can and cannot support, printed beside the numbers.
POWER_NOTE = (
    "The resampling unit is the submission, not the pair: one submission's variants are "
    "rewrites of the same sentence and are not independent of one another. So the effective n "
    "is the number of submissions, not the number of pairs, and at a dozen submissions a 95% "
    "interval on a proportion is worth roughly +/-25 points at worst. This can separate 'flips "
    "are common' from 'flips are rare'. It cannot support a precise rate, and a report that "
    "quotes one to the point is over-reading it."
)


class FlipError(ValueError):
    """Raised when the paraphrase set, or a scoring of it, cannot be trusted."""


@dataclass(frozen=True)
class Variant:
    """One rewrite of one submission."""

    variant_id: str
    submission_id: str
    text: str


@dataclass(frozen=True)
class ParaphraseGroup:
    """One submission and its variants.

    A group with no variants is a hard error at load time rather than a group
    contributing nothing: a source that lost its variants is a set that quietly
    got smaller, which is the failure mode this diagnostic can least afford at
    an n this size.
    """

    submission_id: str
    source_id: str
    source_text: str
    variants: tuple[Variant, ...]

    @property
    def n_pairs(self) -> int:
        return len(self.variants)


@dataclass(frozen=True)
class ParaphraseSet:
    """The whole hand-written set: sources, their variants, and where they came from."""

    path: Path
    groups: tuple[ParaphraseGroup, ...]

    def __len__(self) -> int:
        return len(self.groups)

    @property
    def n_pairs(self) -> int:
        return sum(group.n_pairs for group in self.groups)

    @property
    def texts(self) -> tuple[str, ...]:
        """Every text to score, sources and variants interleaved, in group order.

        One flat sequence because the scorer takes one: the pairing is rebuilt
        by :func:`build_pairs` from this same order, so the two must not drift.
        """
        collected: list[str] = []
        for group in self.groups:
            collected.append(group.source_text)
            collected.extend(variant.text for variant in group.variants)
        return tuple(collected)


def load_paraphrases(
    path: Path | str = DEFAULT_PARAPHRASE_PATH,
    *,
    sources: Mapping[str, str] | None = None,
) -> ParaphraseSet:
    """Load and validate the paraphrase TSV.

    Three things are hard errors, each because tolerating them would silently
    change what the diagnostic measured:

    * a ``variant`` row whose ``submission_id`` has no ``source`` row -- the pair
      has nothing to be compared against;
    * a ``source`` row with no variants -- a submission that contributes no pair
      and would otherwise disappear from the count without saying so;
    * a repeated ``variant_id``, or two ``source`` rows for one submission.

    ``sources``, when given, is ``{submission_id: text}`` from the holdout's own
    source file, and every ``source`` row is checked against it character for
    character. The set is only a paraphrase set if the thing being paraphrased is
    the real submission; a source row that has been tidied up on its way into
    this file measures a rewrite against a rewrite.
    """
    path = Path(path)
    if not path.is_file():
        raise FlipError(f"paraphrase set not found: {path}")

    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.reader(handle, delimiter="\t")
        try:
            header = next(reader)
        except StopIteration as error:
            raise FlipError(f"{path} is empty") from error
        rows = [row for row in reader if any(cell.strip() for cell in row)]

    expected_header = [ID_COLUMN, SOURCE_COLUMN, KIND_COLUMN, TEXT_COLUMN]
    if header != expected_header:
        raise FlipError(f"{path} must have the header {expected_header}; it has {header}")

    source_rows: dict[str, tuple[str, str]] = {}
    variants: dict[str, list[Variant]] = {}
    order: list[str] = []
    seen_ids: set[str] = set()

    for number, row in enumerate(rows, start=2):
        if len(row) != len(header):
            raise FlipError(f"{path}:{number} has {len(row)} fields against the header's 4")
        variant_id, submission_id, kind = (cell.strip() for cell in row[:3])
        text = row[3]

        if not variant_id:
            raise FlipError(f"{path}:{number} has no {ID_COLUMN}")
        if variant_id in seen_ids:
            raise FlipError(f"{path}:{number} repeats {ID_COLUMN} {variant_id!r}")
        seen_ids.add(variant_id)
        if not submission_id:
            raise FlipError(f"{path}:{number} ({variant_id}) has no {SOURCE_COLUMN}")
        if not text.strip():
            raise FlipError(f"{path}:{number} ({variant_id}) has no text")
        if kind not in (KIND_SOURCE, KIND_VARIANT):
            raise FlipError(
                f"{path}:{number} ({variant_id}) has kind {kind!r}; it must be "
                f"{KIND_SOURCE!r} or {KIND_VARIANT!r}"
            )

        if submission_id not in variants:
            variants[submission_id] = []
            order.append(submission_id)
        if kind == KIND_SOURCE:
            if submission_id in source_rows:
                raise FlipError(
                    f"{path}:{number} is a second {KIND_SOURCE!r} row for {submission_id!r}; "
                    "a submission has one original and any number of variants"
                )
            source_rows[submission_id] = (variant_id, text)
        else:
            variants[submission_id].append(
                Variant(variant_id=variant_id, submission_id=submission_id, text=text)
            )

    orphans = [submission_id for submission_id in order if submission_id not in source_rows]
    if orphans:
        raise FlipError(
            f"{path} has variants for {orphans} with no {KIND_SOURCE!r} row. A variant with "
            "nothing to be compared against is not a pair, and dropping it would shrink the set "
            "without saying so"
        )
    barren = [submission_id for submission_id in order if not variants[submission_id]]
    if barren:
        raise FlipError(
            f"{path} has a {KIND_SOURCE!r} row for {barren} with no variants. A source with no "
            "variants contributes no pair; delete the row or write its variants"
        )

    if sources is not None:
        for submission_id in order:
            if submission_id not in sources:
                raise FlipError(
                    f"{path} names submission {submission_id!r}, which is not in the holdout "
                    "source file"
                )
            if source_rows[submission_id][1] != sources[submission_id]:
                raise FlipError(
                    f"{path}'s {KIND_SOURCE!r} row for {submission_id!r} is not the submission "
                    "verbatim. A paraphrase set measures a rewrite against the real text; a "
                    "tidied-up source measures a rewrite against a rewrite"
                )

    groups = tuple(
        ParaphraseGroup(
            submission_id=submission_id,
            source_id=source_rows[submission_id][0],
            source_text=source_rows[submission_id][1],
            variants=tuple(variants[submission_id]),
        )
        for submission_id in order
    )
    if not groups:
        raise FlipError(f"{path} holds no submissions")
    return ParaphraseSet(path=path, groups=groups)


def load_holdout_sources(path: Path | str) -> dict[str, str]:
    """``{submission_id: text}`` from `uti1_holdout.source.txt`.

    Ids are assigned by line order, exactly as `data/realistic/README.md` says
    and as the labels file already assumes. Read from the source file rather
    than from the labels TSV so this check does not depend on the labels, which
    this diagnostic must never open.
    """
    path = Path(path)
    if not path.is_file():
        raise FlipError(f"holdout source not found: {path}")
    lines = path.read_text(encoding="utf-8").splitlines()
    return {
        f"holdout-{number:04d}": line for number, line in enumerate(lines, start=1) if line.strip()
    }


def flip_rate(confusion: Sequence[Sequence[int]]) -> float | None:
    """Share of pairs whose two predictions disagree: one minus accuracy.

    ``None`` on an empty slice rather than zero, so an empty resample is dropped
    from the bootstrap instead of being scored as "nothing flipped".
    """
    agreement = accuracy(confusion)
    return None if agreement is None else 1.0 - agreement


def build_pairs(
    paraphrases: ParaphraseSet,
    scores: Mapping[str, Sequence[Sequence[float]]],
    *,
    signals: Sequence[str],
    margin: float | Mapping[str, float] = 0.0,
    gated_class: int = CLASS_TRUE,
) -> dict[str, list[Prediction]]:
    """Turn one forward pass over :attr:`ParaphraseSet.texts` into paired predictions.

    ``truth`` is the source's decided class and ``predicted`` is the variant's,
    so the confusion matrix of the result is the flip-direction matrix and its
    accuracy is the agreement rate. ``unit`` is the submission, which is what
    makes a submission's variants resample together (:data:`POWER_NOTE`).
    """
    per_signal: dict[str, list[Prediction]] = {}
    expected = len(paraphrases.texts)
    for signal in signals:
        rows = scores.get(signal)
        if rows is None:
            raise FlipError(
                f"the scorer returned nothing for {signal!r}; it was asked for "
                f"{list(signals)} and answered {sorted(scores)}"
            )
        if len(rows) != expected:
            raise FlipError(
                f"the scorer returned {len(rows)} rows for {signal!r} against {expected} texts"
            )
        if isinstance(margin, Mapping) and signal not in margin:
            raise FlipError(
                f"no margin given for {signal!r}; every signal being scored needs its own "
                f"already-selected margin, and {list(margin)} did not include it"
            )
        resolved = margin[signal] if isinstance(margin, Mapping) else margin

        predictions: list[Prediction] = []
        cursor = 0
        for group in paraphrases.groups:
            source_class = apply_margin(
                tuple(float(value) for value in rows[cursor]), resolved, gated_class=gated_class
            )
            cursor += 1
            for variant in group.variants:
                variant_scores = tuple(float(value) for value in rows[cursor])
                cursor += 1
                predictions.append(
                    Prediction(
                        example_id=f"{variant.variant_id}:{signal}",
                        truth=source_class,
                        predicted=apply_margin(variant_scores, resolved, gated_class=gated_class),
                        unit=group.submission_id,
                        scores=variant_scores,
                    )
                )
        per_signal[signal] = predictions
    return per_signal


def _interval_dict(interval: Interval) -> dict:
    return {
        "point": interval.point,
        "low": interval.low,
        "high": interval.high,
        "effective_n": interval.effective_n,
        "resamples_used": interval.resamples_used,
    }


def _direction_matrix(predictions: Sequence[Prediction]) -> dict:
    """The flip-direction matrix, as counts and as named off-diagonal cells.

    The matrix alone is what the statistic is computed from; the named cells are
    what a reader acts on. 12.6's finding was not "recall moved" but "decisive
    recall drained into `null`", and that sentence is only writable from the
    off-diagonal.
    """
    matrix = confusion_matrix(predictions)
    transitions = {
        f"{CLASS_NAMES[source]} -> {CLASS_NAMES[target]}": matrix[source][target]
        for source in range(len(CLASS_NAMES))
        for target in range(len(CLASS_NAMES))
        if source != target and matrix[source][target]
    }
    return {
        "matrix": [list(row) for row in matrix],
        "rows": "the source's class",
        "columns": "the variant's class",
        "transitions": dict(sorted(transitions.items(), key=lambda item: (-item[1], item[0]))),
    }


def _block(predictions: Sequence[Prediction], *, resamples: int, seed: int, alpha: float) -> dict:
    interval = bootstrap_confusion_ci(
        predictions, flip_rate, resamples=resamples, seed=seed, alpha=alpha
    )
    return {
        "n_pairs": len(predictions),
        "n_submissions": interval.effective_n,
        "flip_rate": _interval_dict(interval),
        "flips": sum(1 for prediction in predictions if not prediction.correct),
        "direction": _direction_matrix(predictions),
    }


def score_flips(
    paraphrases: ParaphraseSet,
    scorer: Callable[[Sequence[str]], Mapping[str, Sequence[Sequence[float]]]],
    *,
    signals: Sequence[str],
    margin: float | Mapping[str, float] = 0.0,
    gated_class: int = CLASS_TRUE,
    resamples: int = DEFAULT_RESAMPLES,
    seed: int = 0,
    alpha: float = DEFAULT_ALPHA,
) -> dict:
    """Score one model's paraphrase-flip rate, overall and per signal.

    ``margin`` arrives already selected on the fold's own validation split, for
    the reason :func:`holdout.score_holdout` gives: this function selects
    nothing, and giving it nothing to select with is what makes that structural.
    """
    per_signal = build_pairs(
        paraphrases,
        scorer(paraphrases.texts),
        signals=signals,
        margin=margin,
        gated_class=gated_class,
    )
    pooled: list[Prediction] = []
    by_signal: list[dict] = []
    for signal in signals:
        predictions = per_signal[signal]
        pooled.extend(predictions)
        by_signal.append(
            {
                "signal": signal,
                "margin": margin[signal] if isinstance(margin, Mapping) else margin,
                **_block(predictions, resamples=resamples, seed=seed, alpha=alpha),
            }
        )

    return {
        "path": str(paraphrases.path),
        "n_submissions": len(paraphrases),
        "n_pairs": paraphrases.n_pairs,
        "signals_scored": list(signals),
        "margin": margin if not isinstance(margin, Mapping) else dict(margin),
        "bootstrap": {"resamples": resamples, "seed": seed, "alpha": alpha},
        "resampling_unit": "the submission; a submission's variants are not independent",
        "overall": _block(pooled, resamples=resamples, seed=seed, alpha=alpha),
        "by_signal": by_signal,
        "pairs": {
            signal: [
                {
                    "id": prediction.example_id,
                    "unit": prediction.unit,
                    "source": prediction.truth,
                    "variant": prediction.predicted,
                }
                for prediction in per_signal[signal]
            ]
            for signal in signals
        },
        "provenance": PROVENANCE_NOTE,
        "selects_nothing": SELECTS_NOTHING_NOTE,
        "power": POWER_NOTE,
    }


def _format_rate(block: Mapping[str, object]) -> str:
    interval = block["flip_rate"]
    point = interval["point"]
    if point is None:
        return "n/a"
    if interval["low"] is None:
        return f"{point:.1%}"
    return f"{point:.1%} [{interval['low']:.1%}, {interval['high']:.1%}]"


def describe_flips(result: Mapping[str, object]) -> list[str]:
    """The result as printable lines: the rate, its interval, and where the flips went.

    Stdlib, and returned rather than printed, so CI's unit job can assert what a
    reader will actually see. The direction lines are not decoration -- a flip
    rate on its own does not distinguish a head that wobbles between `true` and
    `null` from one that wobbles between `true` and `false`, and those are
    different faults.
    """
    overall = result["overall"]
    lines = [
        f"paraphrase flips: {_format_rate(overall)} of {overall['n_pairs']} pairs "
        f"over {overall['n_submissions']} submissions",
        f"  {overall['flips']} pair(s) disagreed between the source and its variant",
    ]
    transitions = overall["direction"]["transitions"]
    if transitions:
        lines.append(
            "  direction (source -> variant): "
            + ", ".join(f"{name} x{count}" for name, count in transitions.items())
        )
    else:
        lines.append("  direction: no pair changed class")
    for entry in result["by_signal"]:
        block_transitions = entry["direction"]["transitions"]
        detail = (
            "; ".join(f"{name} x{count}" for name, count in block_transitions.items())
            or "no change"
        )
        lines.append(
            f"  {entry['signal']}: {_format_rate(entry)} "
            f"({entry['flips']}/{entry['n_pairs']}) -- {detail}"
        )
    lines.append(f"  power: {result['power']}")
    return lines


__all__ = [
    "DEFAULT_PARAPHRASE_PATH",
    "KIND_SOURCE",
    "KIND_VARIANT",
    "POWER_NOTE",
    "PROVENANCE_NOTE",
    "SELECTS_NOTHING_NOTE",
    "FlipError",
    "ParaphraseGroup",
    "ParaphraseSet",
    "Variant",
    "build_pairs",
    "describe_flips",
    "flip_rate",
    "load_holdout_sources",
    "load_paraphrases",
    "score_flips",
]

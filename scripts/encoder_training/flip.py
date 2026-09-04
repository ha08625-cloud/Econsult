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

----

**The second half of this module is Task 6's, and it measures a different thing
with the same statistic.** Task 2 asks whether a head flips on thirteen
hand-written rewrites of real submissions; Task 6 asks whether it flips on ten
thousand machine-made rewrites of its own test split, where the rewrite is
`expand.py`'s and the pairing is by ``example_id`` rather than by a column in a
TSV. :func:`score_tree_flips` is that measurement, and three things about it are
deliberate:

* **It reads written predictions, not a model.** The four cells of Task 6's 2x2
  are four separate ``finetune`` invocations because ``--test-dir`` is a single
  path, so no one process ever holds both of an arm's scorings. The flip rate is
  therefore computed *post hoc* from the per-example predictions each cell wrote
  (``finetune --predictions``), which also means it costs no GPU and is coverable
  by CI's unit job like everything else here.
* **The denominator is the changed pairs.** An example the pass left alone cannot
  flip, and counting it would dilute the rate towards zero by exactly the clean
  share (plan DD7). :data:`CHANGED_ONLY_NOTE` is printed beside the number.
* **The resampling unit is the cluster, not the example.** Ten thousand examples
  sit on a few hundred decisive fragment clusters, so an example-level bootstrap
  would report an interval several times too narrow (`arch_training.md` section
  10). ``Example.resampling_unit`` is what :func:`pair_trees` carries across.
"""

from __future__ import annotations

import csv
import json
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from .dataset import CLASS_NAMES, CLASS_TRUE, load_folds
from .metrics import (
    DEFAULT_ALPHA,
    DEFAULT_RESAMPLES,
    Interval,
    Prediction,
    accuracy,
    apply_margin,
    bootstrap_confusion_ci,
    confusion_matrix,
    effective_n,
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


# ---------------------------------------------------------------------------
# Task 6: the paired flip rate between two matched trees
# ---------------------------------------------------------------------------

#: Why the denominator is the changed pairs and not every pair (plan DD7).
CHANGED_ONLY_NOTE = (
    "The denominator is the pairs the expansion pass actually changed. An example it left "
    "alone -- the clean share, plus every example holding no match site -- is byte-identical "
    "on both sides and cannot flip, so including it would drag the rate towards zero by an "
    "amount that says nothing about the model and everything about `--clean-share`. The "
    "unchanged count is reported beside the rate rather than folded into it."
)

#: Why the bootstrap resamples clusters (plan DD7, `arch_training.md` section 10).
CLUSTER_UNIT_NOTE = (
    "The resampling unit is the decisive fragment's cluster, not the example. Ten thousand "
    "test examples sit on a few hundred clusters, because every example recombines a decisive "
    "fragment with filler; resampling examples would treat rewrites of one idea as independent "
    "observations and report an interval several times too narrow."
)

#: DD8's negative control, carried into the report rather than left in the plan.
NO_GROWTH_NOTE = (
    "The expanded tree holds exactly as many examples as the clean one, paired example_id for "
    "example_id: expansion creates no fragments and no clusters, so effective sample size is "
    "identical in every cell. A difference between two cells can therefore only be robustness "
    "to paraphrase; it can never be better coverage."
)

#: What a flip is, and what it is not, in the tree setting.
TREE_FLIP_NOTE = (
    "A flip is a disagreement between one arm's prediction on the clean test tree and the same "
    "arm's prediction on the expanded test tree, for the same example_id. The two texts make "
    "the same claim under rules whose declared invariant is that they change neither tense, "
    "person, certainty nor polarity, so a flip is an error on one side of the pair, whichever "
    "side that is. No label is read to see one."
)


@dataclass(frozen=True)
class TreePair:
    """One example as it appears in both trees: its cluster, and whether it moved."""

    example_id: str
    unit: str
    changed: bool
    label_mode: str | None = None
    library: str | None = None


def pair_trees(
    clean_dir: Path | str,
    expanded_dir: Path | str,
    *,
    signal: str,
    folds: int,
) -> tuple[TreePair, ...]:
    """Walk two matched fold trees' test splits and pair them by ``example_id``.

    The ids are qualified with their fold (``fold0:test-000017``) exactly as
    :func:`report.FoldRun.build` qualifies them, because the generator numbers
    examples per split and an unqualified id names one example in each of the
    five folds. Pairing on the unqualified id would silently collapse five
    examples into one and compare four fifths of the tree against the wrong row.

    Every structural difference is a hard error rather than a dropped pair: two
    trees that no longer hold the same examples are not two scorings of one test
    set, and a flip rate computed over whatever they happen to share is a number
    about the intersection.
    """
    clean_folds = load_folds(clean_dir, signal, folds=folds)
    expanded_folds = load_folds(expanded_dir, signal, folds=folds)

    pairs: list[TreePair] = []
    for fold_index, (clean_fold, expanded_fold) in enumerate(
        zip(clean_folds, expanded_folds, strict=True)
    ):
        clean_examples = list(clean_fold.test.examples)
        expanded_examples = list(expanded_fold.test.examples)
        if len(clean_examples) != len(expanded_examples):
            raise FlipError(
                f"fold {fold_index}'s test splits hold {len(clean_examples)} and "
                f"{len(expanded_examples)} examples; {clean_dir} and {expanded_dir} are not two "
                "versions of one tree"
            )
        for clean, expanded in zip(clean_examples, expanded_examples, strict=True):
            if clean.example_id != expanded.example_id:
                raise FlipError(
                    f"fold {fold_index}'s test splits disagree at {clean.example_id!r} vs "
                    f"{expanded.example_id!r}; expansion preserves ids and filenames, so a "
                    "mismatch means these are two different generations rather than one "
                    "generation expanded"
                )
            pairs.append(
                TreePair(
                    example_id=f"fold{fold_index}:{clean.id_for(signal)}",
                    unit=clean.resampling_unit,
                    changed=clean.text != expanded.text,
                    label_mode=clean.label_mode,
                    library=clean.library,
                )
            )
    return tuple(pairs)


def write_predictions(
    path: Path | str,
    predictions: Iterable[Prediction],
    *,
    header: Mapping[str, object] | None = None,
) -> Path:
    """Write one model's per-example decisions where a later process can pair them.

    Written rather than returned because the four cells of Task 6's 2x2 are four
    separate ``finetune`` invocations -- ``--test-dir`` is a single path, not a
    repeatable one -- so no single process ever holds both of an arm's scorings.
    The file is the only place the two can meet.

    ``scores`` are deliberately not written. They would triple the file for the
    sake of a margin sweep that has already happened: the decisions here are the
    ones the fold's selected rule actually made, and re-deciding them under some
    other rule downstream would produce a flip rate for a model nobody ran.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "header": dict(header or {}),
        "classes": list(CLASS_NAMES),
        "view": "ruled -- each fold's own selected margin, not argmax",
        "predictions": [
            {
                "example_id": prediction.example_id,
                "unit": prediction.unit,
                "truth": prediction.truth,
                "predicted": prediction.predicted,
                "label_mode": prediction.label_mode,
                "library": prediction.library,
                "subclass": prediction.subclass,
                "fragment_id": prediction.fragment_id,
            }
            for prediction in predictions
        ],
    }
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return path


def load_predictions(path: Path | str) -> dict:
    """Read a file :func:`write_predictions` wrote, checking it holds distinct ids."""
    path = Path(path)
    if not path.is_file():
        raise FlipError(
            f"predictions not found: {path}. They are written by `finetune --predictions`; a "
            "cell run without that flag cannot take part in a paired flip rate"
        )
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise FlipError(f"{path} is not valid JSON: {error}") from error
    if not isinstance(payload, Mapping) or not isinstance(payload.get("predictions"), list):
        raise FlipError(f"{path} must be an object holding a 'predictions' list")
    seen: set[str] = set()
    for row in payload["predictions"]:
        if not isinstance(row, Mapping) or "example_id" not in row or "predicted" not in row:
            raise FlipError(f"{path} holds a row without an example_id and a predicted class")
        example_id = str(row["example_id"])
        if example_id in seen:
            raise FlipError(
                f"{path} names {example_id!r} twice. Ids are qualified by fold, so a repeat "
                "means two folds' predictions were pooled without qualification and the pairing "
                "would compare the wrong rows"
            )
        seen.add(example_id)
    return dict(payload)


def decided_classes(payload: Mapping[str, object]) -> dict[str, int]:
    """``{example_id: predicted class}`` from a loaded predictions file."""
    return {str(row["example_id"]): int(row["predicted"]) for row in payload["predictions"]}


def build_tree_pairs(
    pairs: Sequence[TreePair],
    clean: Mapping[str, int],
    expanded: Mapping[str, int],
) -> list[Prediction]:
    """One :class:`~.metrics.Prediction` per *changed* pair, clean vs expanded.

    ``truth`` is the arm's decision on the clean text and ``predicted`` is its
    decision on the expanded text, so the confusion matrix of the result is the
    flip-direction matrix and one minus its accuracy is the flip rate -- the
    same reuse :func:`build_pairs` makes, for the same reason: "the head wobbles
    between `true` and `null`" and "the head wobbles between `true` and `false`"
    are different faults and a scalar cannot separate them.
    """
    missing = [
        pair.example_id
        for pair in pairs
        if pair.example_id not in clean or pair.example_id not in expanded
    ]
    if missing:
        raise FlipError(
            f"{len(missing)} example(s) are in the trees but not in both prediction files, "
            f"starting with {missing[:3]}. The two cells were scored on different examples, so "
            "there is no pairing to compute"
        )
    return [
        Prediction(
            example_id=pair.example_id,
            truth=clean[pair.example_id],
            predicted=expanded[pair.example_id],
            unit=pair.unit,
            label_mode=pair.label_mode,
            library=pair.library,
        )
        for pair in pairs
        if pair.changed
    ]


def _by_label_mode(
    predictions: Sequence[Prediction], *, resamples: int, seed: int, alpha: float
) -> list[dict]:
    """Flip rate per label mode, so a rate driven by one class is visible as that."""
    modes: dict[str, list[Prediction]] = {}
    for prediction in predictions:
        modes.setdefault(prediction.label_mode or "unlabelled", []).append(prediction)
    return [
        {
            "label_mode": mode,
            **_block(modes[mode], resamples=resamples, seed=seed, alpha=alpha),
        }
        for mode in sorted(modes)
    ]


def score_tree_flips(
    pairs: Sequence[TreePair],
    clean: Mapping[str, int],
    expanded: Mapping[str, int],
    *,
    arm: str,
    resamples: int = DEFAULT_RESAMPLES,
    seed: int = 0,
    alpha: float = DEFAULT_ALPHA,
) -> dict:
    """One arm's paired flip rate between the clean and expanded test trees."""
    predictions = build_tree_pairs(pairs, clean, expanded)
    changed = sum(1 for pair in pairs if pair.changed)
    if not predictions:
        raise FlipError(
            "the expansion pass changed no example in the test split, so there is nothing to "
            "pair. Check --rate and --clean-share: a rate that changes nothing measures nothing"
        )
    return {
        "arm": arm,
        "n_examples": len(pairs),
        "n_changed": changed,
        "changed_share": round(changed / len(pairs), 4) if pairs else 0.0,
        "n_unchanged": len(pairs) - changed,
        **_block(predictions, resamples=resamples, seed=seed, alpha=alpha),
        # `_block` names the bootstrap's effective n after Task 2's resampling
        # unit. Here it is the cluster, and a reader of this file should not
        # have to know that to read the number.
        "n_clusters": effective_n(predictions),
        "by_label_mode": _by_label_mode(predictions, resamples=resamples, seed=seed, alpha=alpha),
        "bootstrap": {"resamples": resamples, "seed": seed, "alpha": alpha},
        "resampling_unit": "the decisive fragment's cluster",
        "what_a_flip_is": TREE_FLIP_NOTE,
        "denominator": CHANGED_ONLY_NOTE,
        "cluster_unit": CLUSTER_UNIT_NOTE,
        "no_growth": NO_GROWTH_NOTE,
    }


#: Where a report's decisive-cell accuracy lives, so the guard reads one thing
#: rather than re-deriving it from a confusion matrix a renderer already
#: summarised.
DECISIVE_ACCURACY_PATH = ("pooled", "ruled", "decisive", "accuracy")


def read_decisive_accuracy(report_path: Path | str, *, model: str) -> dict:
    """The named model's pooled decisive-cell accuracy, out of a written report.

    The guard is on the *decisive* cells for the reason `arch_training.md`
    section 10 gives about the companion run: two thirds of the test tree is
    ``null``, so a head that answered ``null`` to everything would post a
    respectable overall accuracy and a flip rate of zero. Decisive accuracy is
    the number that refuses to be gamed that way, which is why it and not
    overall accuracy is what the pre-registered bound is written against.
    """
    report_path = Path(report_path)
    if not report_path.is_file():
        raise FlipError(f"report not found: {report_path}")
    try:
        report = json.loads(report_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise FlipError(f"{report_path} is not valid JSON: {error}") from error
    models = report.get("models")
    if not isinstance(models, list):
        raise FlipError(f"{report_path} holds no 'models' list")
    for entry in models:
        if isinstance(entry, Mapping) and entry.get("name") == model:
            block: object = entry
            for key in DECISIVE_ACCURACY_PATH:
                if not isinstance(block, Mapping) or key not in block:
                    raise FlipError(
                        f"{report_path}'s {model!r} has no {'.'.join(DECISIVE_ACCURACY_PATH)} block"
                    )
                block = block[key]
            if not isinstance(block, Mapping):
                raise FlipError(f"{report_path}'s {model!r} decisive accuracy is not a block")
            return {"report": str(report_path), "model": model, **dict(block)}
    names = sorted(str(entry.get("name")) for entry in models if isinstance(entry, Mapping))
    raise FlipError(f"{report_path} holds no model named {model!r}; it holds {names}")


def score_guard(
    baseline_report: Path | str,
    arm_report: Path | str,
    *,
    bound: float,
    model: str,
) -> dict:
    """DD7's guard: did the expanded arm buy its flip rate by getting worse?

    Both numbers are read from the **clean** test tree, which is the only place
    the two arms are scored on identical text. An arm that lowers the flip rate
    while losing decisive accuracy has not become robust to paraphrase; it has
    become less willing to commit, and a flip rate cannot tell the difference.

    ``bound`` is a drop in accuracy points, pre-registered before the first
    training run. The comparison is against the point estimate deliberately: the
    intervals here overlap at any effect this experiment could plausibly produce,
    and a guard that only fires on a separated interval is a guard that never
    fires.
    """
    if bound < 0:
        raise FlipError(f"the guard bound is a drop and must not be negative: {bound}")
    baseline = read_decisive_accuracy(baseline_report, model=model)
    arm = read_decisive_accuracy(arm_report, model=model)
    if baseline["point"] is None or arm["point"] is None:
        raise FlipError(
            "one of the reports has no decisive-cell accuracy, so the guard cannot be scored"
        )
    drop = baseline["point"] - arm["point"]
    return {
        "measured_on": "the clean test tree, both arms",
        "model": model,
        "bound": bound,
        "baseline": baseline,
        "arm": arm,
        "drop": drop,
        "passed": drop <= bound,
        "why": (
            "a flip rate falls to zero for a head that answers `null` to everything, so a "
            "lower flip rate is only a win if decisive accuracy held (plan DD7)"
        ),
    }


def describe_tree_flips(result: Mapping[str, object]) -> list[str]:
    """One arm's paired result as printable lines."""
    lines = [
        f"{result['arm']}: paired flips {_format_rate(result)} of {result['n_pairs']} changed "
        f"pairs over {result['n_clusters']} clusters",
        f"  {result['n_changed']}/{result['n_examples']} examples were changed by the pass "
        f"({result['changed_share']:.1%}); {result['n_unchanged']} could not flip and are excluded",
    ]
    transitions = result["direction"]["transitions"]
    if transitions:
        lines.append(
            "  direction (clean -> expanded): "
            + ", ".join(f"{name} x{count}" for name, count in transitions.items())
        )
    else:
        lines.append("  direction: no pair changed class")
    for entry in result["by_label_mode"]:
        transitions = entry["direction"]["transitions"]
        detail = "; ".join(f"{name} x{count}" for name, count in transitions.items()) or "no change"
        lines.append(
            f"  {entry['label_mode']}: {_format_rate(entry)} "
            f"({entry['flips']}/{entry['n_pairs']}) -- {detail}"
        )
    return lines


def describe_guard(guard: Mapping[str, object]) -> list[str]:
    """The guard as printable lines, saying plainly whether it held."""
    baseline = guard["baseline"]["point"]
    arm = guard["arm"]["point"]
    return [
        f"guard: decisive-cell accuracy on the clean test tree, {guard['model']}",
        f"  baseline {baseline:.4f} -> arm {arm:.4f}; drop {guard['drop']:+.4f} "
        f"against a bound of {guard['bound']:.4f}",
        f"  {'HELD' if guard['passed'] else 'FAILED -- the arm bought its flip rate'}",
    ]


__all__ = [
    "CHANGED_ONLY_NOTE",
    "CLUSTER_UNIT_NOTE",
    "DEFAULT_PARAPHRASE_PATH",
    "KIND_SOURCE",
    "KIND_VARIANT",
    "NO_GROWTH_NOTE",
    "POWER_NOTE",
    "PROVENANCE_NOTE",
    "SELECTS_NOTHING_NOTE",
    "TREE_FLIP_NOTE",
    "FlipError",
    "ParaphraseGroup",
    "ParaphraseSet",
    "TreePair",
    "Variant",
    "build_pairs",
    "build_tree_pairs",
    "decided_classes",
    "describe_flips",
    "describe_guard",
    "describe_tree_flips",
    "flip_rate",
    "load_holdout_sources",
    "load_paraphrases",
    "load_predictions",
    "pair_trees",
    "read_decisive_accuracy",
    "score_flips",
    "score_guard",
    "score_tree_flips",
    "write_predictions",
]

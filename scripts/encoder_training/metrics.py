"""Scoring, slicing and error bars for the encoder heads. Standard library only.

This module computes; it never chooses. It will tell a caller the macro-F1 and
the ``null -> true`` rate at every margin on a grid, but the decision rule's
objective (DD9) is applied by the caller, on the fold's own validation split.
Keeping the choice out of here is what lets the same functions score the
validation sweep and the untouched test set without one quietly conditioning
the other.

**Every slice carries an effective n, and the unit is the cluster.** A slice's
example count says how much recombination happened; its effective n says how
many distinct hand-written ideas are behind it, and only the second one bounds
what the slice can support. Ten thousand examples built from 66 fragments is 66
ideas seen many times. The two counts are reported side by side everywhere
because quoting the first alone is the single easiest way to over-read anything
this pipeline produces.

Three mechanisms, in the order they should be read:

* :func:`bootstrap_ci` resamples **clusters**, not examples, and is the
  headline interval. Resampling examples would measure the noise of the
  recombination process rather than the noise that matters, and would produce
  intervals roughly sqrt(examples / clusters) too narrow.
* Across-fold spread (mean and sample standard deviation over five folds) is a
  *stability* check with four degrees of freedom, not a confidence interval. It
  is noisy and will sometimes look reassuringly small for no reason.
* :func:`mcnemar` answers paired questions -- "does this model beat that one on
  this slice" -- which cannot be answered by eyeballing two independent point
  estimates of overlapping intervals.
"""

from __future__ import annotations

import math
import random
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass

from .dataset import CLASS_NAMES, CLASS_NULL, CLASS_TRUE, Example

#: Class indices in confusion-matrix order.
CLASSES = tuple(range(len(CLASS_NAMES)))

#: Resamples drawn by :func:`bootstrap_ci`. Enough that the percentile bounds
#: are stable to well under a point at the interval widths this data supports,
#: and cheap: the statistic runs over a few thousand integers.
DEFAULT_RESAMPLES = 2000

#: Two-sided coverage of the reported interval.
DEFAULT_ALPHA = 0.05


class MetricsError(ValueError):
    """Raised when a metric is asked for something it cannot answer."""


@dataclass(frozen=True)
class Prediction:
    """One scored example: what was true, what was predicted, and where it came from.

    ``unit`` is the resampling unit -- the decisive fragment's cluster, or the
    shared structural-null unit. It is carried on the prediction rather than
    looked up later so that a prediction can be pooled across folds, written to
    disk and re-read without the sidecars having to travel with it.
    """

    example_id: str
    truth: int
    predicted: int
    unit: str
    label_mode: str | None = None
    library: str | None = None
    subclass: str | None = None
    fragment_id: str | None = None
    #: Per-class scores (probabilities or logits) in :data:`CLASSES` order.
    #: Required only by the margin sweep.
    scores: tuple[float, ...] | None = None

    @property
    def correct(self) -> bool:
        return self.truth == self.predicted

    @classmethod
    def from_example(
        cls,
        example: Example,
        signal: str,
        predicted: int,
        *,
        scores: Sequence[float] | None = None,
    ) -> Prediction:
        """Build a prediction from a loaded example, carrying its provenance across."""
        if not example.is_labelled(signal):
            raise MetricsError(
                f"example {example.example_id!r} carries no label for {signal!r}, so it cannot "
                "be scored; a masked example belongs in neither the numerator nor the "
                "denominator"
            )
        return cls(
            example_id=example.example_id,
            truth=example.class_for(signal),
            predicted=predicted,
            unit=example.resampling_unit,
            label_mode=example.label_mode,
            library=example.library,
            subclass=example.subclass,
            fragment_id=example.fragment_id,
            scores=None if scores is None else tuple(scores),
        )


@dataclass(frozen=True)
class ClassMetrics:
    """Precision, recall and F1 for one class, with the counts behind them.

    ``None`` rather than ``0.0`` where a quantity is undefined: precision over
    zero predictions and recall over zero support are not zeroes, and averaging
    them in as zeroes silently drags a macro score down for a class the slice
    never contained.
    """

    label: str
    support: int
    predicted: int
    true_positives: int
    precision: float | None
    recall: float | None
    f1: float | None


@dataclass(frozen=True)
class SliceSummary:
    """Everything reported about one slice, including both of its counts."""

    n_examples: int
    #: Distinct clusters behind the slice -- the number that bounds what it can
    #: support. See the module docstring.
    effective_n: int
    confusion: tuple[tuple[int, ...], ...]
    per_class: Mapping[str, ClassMetrics]
    macro_f1: float | None
    accuracy: float | None


@dataclass(frozen=True)
class Interval:
    """A percentile bootstrap interval, with the effective n it was drawn over."""

    point: float | None
    low: float | None
    high: float | None
    effective_n: int
    resamples_used: int


@dataclass(frozen=True)
class McNemarResult:
    """The paired comparison of two models on the same examples."""

    n_pairs: int
    a_only_correct: int
    b_only_correct: int
    p_value: float


@dataclass(frozen=True)
class MarginRow:
    """One row of the decision-rule sweep."""

    margin: float
    summary: SliceSummary
    #: Examples truly ``null`` that the rule calls ``true`` -- the cell that
    #: invents a symptom into a patient's pre-filled form. A constraint in the
    #: DD9 objective, never a term to be traded off.
    null_to_true: int
    null_to_true_rate: float | None


# ---------------------------------------------------------------------------
# Confusion matrix and per-class metrics
# ---------------------------------------------------------------------------


def confusion_matrix(predictions: Iterable[Prediction]) -> tuple[tuple[int, ...], ...]:
    """Rows are truth, columns are prediction, both in :data:`CLASS_NAMES` order."""
    matrix = [[0 for _ in CLASSES] for _ in CLASSES]
    for prediction in predictions:
        for value, name in ((prediction.truth, "truth"), (prediction.predicted, "prediction")):
            if value not in CLASSES:
                raise MetricsError(
                    f"example {prediction.example_id!r} has {name} class {value!r}, which is not "
                    f"one of {CLASSES}"
                )
        matrix[prediction.truth][prediction.predicted] += 1
    return tuple(tuple(row) for row in matrix)


def per_class_metrics(
    confusion: Sequence[Sequence[int]],
) -> dict[str, ClassMetrics]:
    """Precision, recall and F1 per class, from a confusion matrix."""
    metrics: dict[str, ClassMetrics] = {}
    for index, label in enumerate(CLASS_NAMES):
        true_positives = confusion[index][index]
        support = sum(confusion[index])
        predicted = sum(row[index] for row in confusion)

        precision = true_positives / predicted if predicted else None
        recall = true_positives / support if support else None
        if support == 0 and predicted == 0:
            # The class is absent from this slice entirely: neither predicted
            # nor present. Scoring it 0.0 would be an opinion about data that
            # does not exist.
            f1: float | None = None
        else:
            p = precision or 0.0
            r = recall or 0.0
            f1 = 0.0 if (p + r) == 0 else 2 * p * r / (p + r)

        metrics[label] = ClassMetrics(
            label=label,
            support=support,
            predicted=predicted,
            true_positives=true_positives,
            precision=precision,
            recall=recall,
            f1=f1,
        )
    return metrics


def macro_f1(confusion: Sequence[Sequence[int]]) -> float | None:
    """Unweighted mean F1 over the classes the slice actually contains.

    Classes absent from the slice in both truth and prediction are skipped
    rather than counted as zero; see :class:`ClassMetrics`.
    """
    scores = [
        metrics.f1 for metrics in per_class_metrics(confusion).values() if metrics.f1 is not None
    ]
    return sum(scores) / len(scores) if scores else None


def accuracy(confusion: Sequence[Sequence[int]]) -> float | None:
    total = sum(sum(row) for row in confusion)
    if not total:
        return None
    return sum(confusion[index][index] for index in CLASSES) / total


def null_to_true_rate(confusion: Sequence[Sequence[int]]) -> float | None:
    """Share of truly-``null`` examples called ``true``.

    The cell DD9's decision rule exists to protect: a false ``true`` here
    pre-fills a symptom the patient never reported.
    """
    support = sum(confusion[CLASS_NULL])
    if not support:
        return None
    return confusion[CLASS_NULL][CLASS_TRUE] / support


# ---------------------------------------------------------------------------
# Slicing and effective sample size
# ---------------------------------------------------------------------------


def effective_n(predictions: Iterable[Prediction]) -> int:
    """Distinct resampling units -- clusters -- behind a slice.

    Not the example count, and the gap between the two is large: a sub-class
    whose test slice holds hundreds of examples may hold two ideas.
    """
    return len({prediction.unit for prediction in predictions})


def summarise(predictions: Sequence[Prediction]) -> SliceSummary:
    """Score one slice, reporting its example count and effective n together."""
    confusion = confusion_matrix(predictions)
    return SliceSummary(
        n_examples=len(predictions),
        effective_n=effective_n(predictions),
        confusion=confusion,
        per_class=per_class_metrics(confusion),
        macro_f1=macro_f1(confusion),
        accuracy=accuracy(confusion),
    )


def slice_by(
    predictions: Iterable[Prediction], key: Callable[[Prediction], object]
) -> dict[object, list[Prediction]]:
    """Group predictions by an arbitrary key, in sorted key order.

    ``None`` sorts last under a stable rendering of the key, so a
    "no decisive fragment" group never collides with a real library name.
    """
    grouped: dict[object, list[Prediction]] = {}
    for prediction in predictions:
        grouped.setdefault(key(prediction), []).append(prediction)
    return {
        group: grouped[group]
        for group in sorted(grouped, key=lambda value: (value is None, str(value)))
    }


def slice_by_label_mode(predictions: Iterable[Prediction]) -> dict[object, list[Prediction]]:
    return slice_by(predictions, lambda prediction: prediction.label_mode)


def slice_by_library(predictions: Iterable[Prediction]) -> dict[object, list[Prediction]]:
    """Slice on the decisive fragment's library (DD6).

    The library, not ``meta.fragment_subclasses``: the manifest only sets a
    subclass on the ambiguous and confounder libraries, so slicing on subclass
    alone collapses ``fever_true``, ``fever_false`` and all five filler
    libraries into one indistinguishable ``None`` bucket.
    """
    return slice_by(predictions, lambda prediction: prediction.library)


def slice_by_subclass(predictions: Iterable[Prediction]) -> dict[object, list[Prediction]]:
    return slice_by(predictions, lambda prediction: prediction.subclass)


def slice_by_fragment(predictions: Iterable[Prediction]) -> dict[object, list[Prediction]]:
    """Group by decisive fragment -- the DD7 per-fragment error table.

    More decision-useful than any slice accuracy, because it separates the two
    explanations a low score has. Errors spread thinly across many fragments
    means the method is too weak; errors concentrated on a handful means those
    specific ideas are unlearnable from the data we have, and names them.
    """
    return slice_by(predictions, lambda prediction: prediction.fragment_id)


# ---------------------------------------------------------------------------
# Error bars
# ---------------------------------------------------------------------------


def accuracy_statistic(predictions: Sequence[Prediction]) -> float | None:
    """Accuracy as a :func:`bootstrap_ci` statistic."""
    return accuracy(confusion_matrix(predictions))


def macro_f1_statistic(predictions: Sequence[Prediction]) -> float | None:
    """Macro-F1 as a :func:`bootstrap_ci` statistic."""
    return macro_f1(confusion_matrix(predictions))


def recall_statistic(class_index: int) -> Callable[[Sequence[Prediction]], float | None]:
    """Recall for one class, as a :func:`bootstrap_ci` statistic.

    The headline per-sub-class number: "how often does the model call a
    third-party mention ``null``". Returns ``None`` for a resample containing
    no examples of the class, which :func:`bootstrap_ci` drops rather than
    scoring zero.
    """

    def statistic(predictions: Sequence[Prediction]) -> float | None:
        return per_class_metrics(confusion_matrix(predictions))[CLASS_NAMES[class_index]].recall

    return statistic


def bootstrap_ci(
    predictions: Sequence[Prediction],
    statistic: Callable[[Sequence[Prediction]], float | None],
    *,
    resamples: int = DEFAULT_RESAMPLES,
    seed: int = 0,
    alpha: float = DEFAULT_ALPHA,
) -> Interval:
    """Percentile bootstrap over **clusters**, not examples.

    Each resample draws as many units as the slice has, with replacement, and
    takes every example belonging to a drawn unit. Resampling examples instead
    would treat ``[c01]`` siblings and the hundreds of recombinations of one
    fragment as independent observations, and report an interval roughly
    sqrt(examples / clusters) too narrow -- which for these datasets is a factor
    of ten or more.

    Resamples for which the statistic is undefined (an empty class, say) are
    dropped and counted in ``resamples_used`` rather than silently scored zero.
    """
    if not 0.0 < alpha < 1.0:
        raise MetricsError(f"alpha must be in (0, 1): {alpha}")
    if resamples < 1:
        raise MetricsError(f"resamples must be at least 1: {resamples}")

    by_unit = slice_by(predictions, lambda prediction: prediction.unit)
    units = list(by_unit)
    point = statistic(list(predictions))
    if not units:
        return Interval(point=point, low=None, high=None, effective_n=0, resamples_used=0)

    rng = random.Random(seed)
    values: list[float] = []
    for _ in range(resamples):
        drawn: list[Prediction] = []
        for _ in units:
            drawn.extend(by_unit[units[rng.randrange(len(units))]])
        value = statistic(drawn)
        if value is not None:
            values.append(value)

    if not values:
        return Interval(point=point, low=None, high=None, effective_n=len(units), resamples_used=0)

    values.sort()
    low_index = max(0, min(len(values) - 1, math.floor(alpha / 2 * len(values))))
    high_index = max(0, min(len(values) - 1, math.ceil((1 - alpha / 2) * len(values)) - 1))
    return Interval(
        point=point,
        low=values[low_index],
        high=values[high_index],
        effective_n=len(units),
        resamples_used=len(values),
    )


def bootstrap_confusion_ci(
    predictions: Sequence[Prediction],
    statistic: Callable[[Sequence[Sequence[int]]], float | None],
    *,
    resamples: int = DEFAULT_RESAMPLES,
    seed: int = 0,
    alpha: float = DEFAULT_ALPHA,
) -> Interval:
    """:func:`bootstrap_ci` for statistics that read only the confusion matrix.

    Identical resampling -- same units, same order, same random draws, so for a
    confusion-derived statistic this returns exactly what :func:`bootstrap_ci`
    returns, and ``test_confusion_bootstrap_matches_the_general_one`` pins that.
    The difference is cost: each resample sums one 3x3 matrix per drawn cluster
    instead of rescoring every example belonging to it. A pooled slice here is
    ten thousand examples over a couple of hundred clusters, so the general
    form is roughly fifty times the work for the same number, and the report
    asks for it well over a hundred times.

    Use :func:`bootstrap_ci` for anything the matrix does not determine.
    """
    if not 0.0 < alpha < 1.0:
        raise MetricsError(f"alpha must be in (0, 1): {alpha}")
    if resamples < 1:
        raise MetricsError(f"resamples must be at least 1: {resamples}")

    by_unit = slice_by(predictions, lambda prediction: prediction.unit)
    units = list(by_unit)
    point = statistic(confusion_matrix(predictions))
    if not units:
        return Interval(point=point, low=None, high=None, effective_n=0, resamples_used=0)

    # One flat 9-cell matrix per unit, in the same order slice_by yields them.
    flat = [[cell for row in confusion_matrix(by_unit[unit]) for cell in row] for unit in units]

    rng = random.Random(seed)
    values: list[float] = []
    size = len(units)
    for _ in range(resamples):
        totals = [0] * 9
        for _ in range(size):
            drawn = flat[rng.randrange(size)]
            for cell in range(9):
                totals[cell] += drawn[cell]
        value = statistic(tuple(tuple(totals[row * 3 : row * 3 + 3]) for row in CLASSES))
        if value is not None:
            values.append(value)

    if not values:
        return Interval(point=point, low=None, high=None, effective_n=size, resamples_used=0)

    values.sort()
    low_index = max(0, min(len(values) - 1, math.floor(alpha / 2 * len(values))))
    high_index = max(0, min(len(values) - 1, math.ceil((1 - alpha / 2) * len(values)) - 1))
    return Interval(
        point=point,
        low=values[low_index],
        high=values[high_index],
        effective_n=size,
        resamples_used=len(values),
    )


def class_recall(class_index: int) -> Callable[[Sequence[Sequence[int]]], float | None]:
    """Recall for one class, as a :func:`bootstrap_confusion_ci` statistic."""

    def statistic(confusion: Sequence[Sequence[int]]) -> float | None:
        return per_class_metrics(confusion)[CLASS_NAMES[class_index]].recall

    return statistic


def _two_sided_exact_binomial(successes: int, trials: int) -> float:
    """Two-sided exact binomial p-value at p = 0.5, from :func:`math.comb`.

    Exact rather than the chi-square approximation, and stdlib rather than
    scipy: the discordant-pair counts here are small enough that the
    approximation is the wrong tool and large enough that the arithmetic is
    trivial either way.
    """
    if trials == 0:
        return 1.0
    tail = min(successes, trials - successes)
    cumulative = sum(math.comb(trials, k) for k in range(tail + 1))
    return min(1.0, 2 * cumulative / 2**trials)


def mcnemar(a: Sequence[Prediction], b: Sequence[Prediction]) -> McNemarResult:
    """Exact McNemar test on two models' predictions over the same examples.

    "Does ClinicalBERT beat bag-of-words on ``null_ambiguous``" is a paired
    question: both models saw the same examples, so the informative quantity is
    the examples they disagree about, not the gap between two independent point
    estimates.

    Note what the pairing unit is here. This is a test over *examples*, so where
    a slice's examples are recombinations of a few clusters it will overstate
    significance in exactly the way :func:`bootstrap_ci` avoids. It answers
    "did these two models behave differently on this data", which is a narrower
    question than "would they behave differently on new fragments" -- read it
    alongside the cluster interval, never instead of it.
    """
    by_id_a = {prediction.example_id: prediction for prediction in a}
    by_id_b = {prediction.example_id: prediction for prediction in b}
    if set(by_id_a) != set(by_id_b):
        raise MetricsError(
            "McNemar needs identical example sets on both sides: "
            f"{len(set(by_id_a) ^ set(by_id_b))} example(s) appear on only one"
        )
    if len(by_id_a) != len(a) or len(by_id_b) != len(b):
        raise MetricsError("McNemar needs unique example ids; duplicates were passed")

    a_only = 0
    b_only = 0
    for example_id, left in by_id_a.items():
        right = by_id_b[example_id]
        if left.truth != right.truth:
            raise MetricsError(
                f"the two sides disagree about the truth for example {example_id!r}: "
                f"{left.truth} against {right.truth}"
            )
        if left.correct and not right.correct:
            a_only += 1
        elif right.correct and not left.correct:
            b_only += 1

    discordant = a_only + b_only
    return McNemarResult(
        n_pairs=len(by_id_a),
        a_only_correct=a_only,
        b_only_correct=b_only,
        p_value=_two_sided_exact_binomial(min(a_only, b_only), discordant),
    )


# ---------------------------------------------------------------------------
# The decision rule (DD9): computed here, chosen by the caller
# ---------------------------------------------------------------------------


def apply_margin(scores: Sequence[float], margin: float, *, gated_class: int = CLASS_TRUE) -> int:
    """Argmax, except ``gated_class`` must beat its best rival by ``margin``.

    The asymmetry we care about operationally lives in the decision rule rather
    than in the training loss (DD8): the class mix is a generator flag, not a
    measured prior over real submissions, so reweighting the loss would only
    correct towards a second arbitrary target. The rule, by contrast, is
    tunable, versioned and reported.

    ``margin=0`` reproduces plain argmax exactly, so the two confusion matrices
    the report prints differ only by the rule. Ties go to the lowest class
    index, which is ``false``, then ``true``, then ``null``.
    """
    if len(scores) != len(CLASSES):
        raise MetricsError(f"expected {len(CLASSES)} scores, got {len(scores)}")
    best = max(CLASSES, key=lambda index: (scores[index], -index))
    if best != gated_class:
        return best

    rivals = [index for index in CLASSES if index != gated_class]
    runner_up = max(rivals, key=lambda index: (scores[index], -index))
    if scores[gated_class] - scores[runner_up] >= margin:
        return gated_class
    return runner_up


def repredict(
    predictions: Sequence[Prediction], margin: float, *, gated_class: int = CLASS_TRUE
) -> list[Prediction]:
    """Re-decide every prediction under a margin, keeping all other fields."""
    rewritten: list[Prediction] = []
    for prediction in predictions:
        if prediction.scores is None:
            raise MetricsError(
                f"example {prediction.example_id!r} carries no scores, so no decision rule "
                "other than the one already applied can be evaluated on it"
            )
        decided = apply_margin(prediction.scores, margin, gated_class=gated_class)
        rewritten.append(
            Prediction(
                example_id=prediction.example_id,
                truth=prediction.truth,
                predicted=decided,
                unit=prediction.unit,
                label_mode=prediction.label_mode,
                library=prediction.library,
                subclass=prediction.subclass,
                fragment_id=prediction.fragment_id,
                scores=prediction.scores,
            )
        )
    return rewritten


def sweep_margins(
    predictions: Sequence[Prediction],
    margins: Iterable[float],
    *,
    gated_class: int = CLASS_TRUE,
) -> list[MarginRow]:
    """Score every margin on a grid, returning the full metric set for each.

    Deliberately returns rows rather than a winner. DD9's objective -- maximise
    macro-F1 subject to a ``null -> true`` rate no worse than argmax's -- is
    applied by the caller against the fold's own validation split, and keeping
    it out of here is what stops a future caller quietly selecting a margin on
    test data.
    """
    rows: list[MarginRow] = []
    for margin in margins:
        decided = repredict(predictions, margin, gated_class=gated_class)
        summary = summarise(decided)
        rows.append(
            MarginRow(
                margin=margin,
                summary=summary,
                null_to_true=summary.confusion[CLASS_NULL][CLASS_TRUE],
                null_to_true_rate=null_to_true_rate(summary.confusion),
            )
        )
    return rows


# ---------------------------------------------------------------------------
# Across folds
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class FoldSpread:
    """Mean and spread of one metric across folds.

    A **stability** check, not a confidence interval, and the report has to say
    so. Five folds give the sample standard deviation four degrees of freedom,
    so it is itself noisy and will occasionally look reassuringly small for no
    reason. The headline interval is the pooled cluster bootstrap.
    """

    n_folds: int
    mean: float
    sd: float | None
    values: tuple[float, ...]


def fold_spread(values: Sequence[float]) -> FoldSpread:
    """Mean and sample standard deviation of a metric over the folds."""
    if not values:
        raise MetricsError("fold_spread needs at least one fold")
    mean = sum(values) / len(values)
    if len(values) < 2:
        sd = None
    else:
        variance = sum((value - mean) ** 2 for value in values) / (len(values) - 1)
        sd = math.sqrt(variance)
    return FoldSpread(n_folds=len(values), mean=mean, sd=sd, values=tuple(values))

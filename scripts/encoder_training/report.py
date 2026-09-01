"""The evaluation report: what a run produced, and what it is worth.

Standard library only, like everything upstream of the arms themselves.

Two things about the shape of this module are deliberate.

**The markdown is rendered from the JSON, never alongside it.** :func:`build_report`
produces one dict and :func:`render_markdown` reads that dict and nothing else,
so the human-readable report and the machine-readable one cannot disagree. A
report whose prose has drifted from its own sidecar is worse than no report.

**Every slice prints two counts.** ``n`` is how many examples the slice holds and
``eff n`` is how many distinct fragment *clusters* are behind them. Only the
second bounds what the slice can support, and the gap between them here is a
factor of fifty or more. The "How to read these numbers" section this module
emits reproduces that argument in full rather than citing it, because the report
is read standalone by people who have not read `arch_training.md`.

**Two things are duplicated on purpose, and only two.** `arch_training.md`
sections 9 and 10 are reproduced in full (:data:`DATA_LIMITS`,
:data:`EFFECTIVE_SAMPLE_SIZE`) rather than cross-referenced, because the report
is read standalone by people who have not read the architecture docs and every
number in it is bounded by what those sections say. Everywhere else, cross-refer.

**The report lays the ticket's question out and stops.** ``_render_ticket_question``
assembles the three numbers the model-or-libraries decision turns on -- accuracy
on ``null_ambiguous``, the paired McNemar on the same slice, and where the errors
fall -- and then says in as many words that the conclusion is a sentence a person
writes. Concluding automatically would mean concluding from whichever comparison
happened to clear a threshold picked while writing a renderer.

:class:`FoldRun` and :class:`ModelRun` are the input contract. Anything that
wants to be reported -- the baselines here, the frozen probe and the fine-tune
later -- produces those and hands them over. That is why they live here rather
than in :mod:`.baselines`.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from .dataset import CLASS_NAMES, CLASS_NULL, CLASS_TRUE
from .decision import DecisionRule
from .metrics import (
    DEFAULT_ALPHA,
    DEFAULT_RESAMPLES,
    Interval,
    McNemarResult,
    Prediction,
    accuracy,
    bootstrap_confusion_ci,
    class_recall,
    confusion_matrix,
    effective_n,
    fold_spread,
    macro_f1,
    mcnemar,
    null_to_true_rate,
    per_class_metrics,
    slice_by_fragment,
    slice_by_label_mode,
    slice_by_library,
    slice_by_subclass,
)

#: 2 added the error-concentration block, the reproduced data limits and the
#: named next ticket. Additive -- a version 1 reader still finds everything it
#: knew about -- but the version moves anyway, because a consumer that wants the
#: DD7 concentration statistic needs a way to say so.
#:
#: 3 added `model_movement`: the per-library and per-fragment comparison across
#: several encoders in one report. Additive again, and empty on a report holding
#: fewer than two non-control models, which is every report written before the
#: `compare-models` command existed.
#:
#: 4 added `cluster_tag_coverage`: per-library cluster-marker coverage, and the
#: warning that goes with it. Additive, and empty on any report built without a
#: `fragments` argument, which is every report written before six signals were
#: trainable and the question "is this library's eff n real" started to have
#: different answers for different signals.
#:
#: 5 added `holdout`: each model's score against the 67 real-text submissions in
#: `data/realistic/`, per signal, aggregated across the folds. Additive, and
#: `null` on any report whose runs did not score it -- which is every report
#: written before the set was readable by any code, and any run made with
#: `--no-holdout`.
#:
#: 6 added `skipped_comparisons`: the pairs McNemar could not be run on because
#: the two runs were scored on different examples, each with the reason. Additive
#: -- `comparisons` still holds exactly what it held -- and empty on every report
#: whose runs all share one test set, which is every report written before a
#: three-arm joint comparison put a differently-generated dataset in the same
#: report as the one it is being compared against.
#:
#: 7 added `holdout_comparisons` (and `skipped_holdout_comparisons`) -- the
#: paired McNemar between models on the 67 real-text submissions, fold by fold --
#: and `companions`, the generator settings behind each arm's dataset. Additive,
#: and both are empty on any report whose runs did not score the holdout or whose
#: caller passed no companion block, which is every report written before two
#: arms differing only in `--companion-share` had to be compared.
SCHEMA_VERSION = 7

#: Sub-classes the hard `null` libraries carry, across every signal rather than
#: fever alone. Listed so that a sub-class the manifest declares but no test fold
#: happened to draw shows up as an empty row rather than vanishing from the table
#: -- and, more importantly, so that a sub-class added to the manifest and
#: forgotten here cannot vanish from the one table the whole exercise exists for.
#: `tests/test_encoder_training_baselines.py` asserts this tuple covers every
#: sub-class the real manifest declares for **every** signal with libraries: the
#: check used to be fever-only, and `adjacent` -- which only
#: `urinary_frequency_null_adjacent` carries -- was missing here for exactly as
#: long as nothing but fever was ever trained.
NULL_SUBCLASSES = (
    "adjacent",
    "attribution",
    "hedged",
    "historical",
    "metaphor",
    "third_party",
)

#: Rows of the per-fragment error table (DD7) the markdown prints inline. The
#: JSON always holds every fragment; this only bounds what a reader scrolls
#: past. Worst-first, so the cap never hides the interesting end.
DEFAULT_FRAGMENT_ROWS = 40

#: How a prediction with no value for a slicing key is named in the output.
#: ``null`` in JSON would collide with the ``null`` *class*, which is a
#: different thing entirely and appears three columns away.
UNSLICED = "(none)"


@dataclass(frozen=True)
class BootstrapConfig:
    """Resampling parameters, recorded in the report so a rerun is comparable."""

    resamples: int = DEFAULT_RESAMPLES
    seed: int = 0
    alpha: float = DEFAULT_ALPHA

    def to_dict(self) -> dict:
        return {"resamples": self.resamples, "seed": self.seed, "alpha": self.alpha}


@dataclass(frozen=True)
class FoldRun:
    """One model's result on one fold: both decisions, and the rule between them.

    ``raw`` is plain argmax and ``ruled`` is the same scores under the fold's
    selected margin. Both are kept because "the model is wrong" and "the rule is
    conservative" are different findings and a single matrix cannot separate
    them (DD9).
    """

    fold_index: int
    n_train: int
    n_val: int
    n_test: int
    rule: DecisionRule
    raw: tuple[Prediction, ...]
    ruled: tuple[Prediction, ...]
    #: This fold's score against the real-text holdout, as
    #: :func:`holdout.score_holdout` returned it, or ``None`` where the run was
    #: made with ``--no-holdout`` or by an arm that does not score it.
    holdout: Mapping[str, object] | None = None

    @classmethod
    def build(
        cls,
        *,
        fold_index: int,
        n_train: int,
        n_val: int,
        n_test: int,
        rule: DecisionRule,
        raw: Sequence[Prediction],
        ruled: Sequence[Prediction],
        holdout: Mapping[str, object] | None = None,
    ) -> FoldRun:
        """Build a fold's result, qualifying every example id with its fold.

        The generator numbers examples per split, so ``test-000017`` names one
        example in every fold. Pooling unqualified ids would silently collapse
        five different examples into one for anything that keys on the id --
        McNemar's pairing above all, which would then compare a model against
        itself on four fifths of the data. Qualifying here rather than at each
        call site is the difference between a rule and a rule someone remembers.
        """
        return cls(
            fold_index=fold_index,
            n_train=n_train,
            n_val=n_val,
            n_test=n_test,
            rule=rule,
            raw=tuple(_qualify(prediction, fold_index) for prediction in raw),
            ruled=tuple(_qualify(prediction, fold_index) for prediction in ruled),
            # Deliberately *not* qualified. The holdout's 67 submissions are the
            # same 67 in every fold -- that is the whole point of a held-out set
            # -- so a fold prefix here would suggest five independent samples
            # where there is one, scored five times.
            holdout=None if holdout is None else dict(holdout),
        )


@dataclass(frozen=True)
class ModelRun:
    """One model across every fold. The unit :func:`build_report` reports on."""

    name: str
    kind: str
    description: str
    folds: tuple[FoldRun, ...] = field(default_factory=tuple)

    @property
    def is_control(self) -> bool:
        return self.kind == "negative_control"

    def pooled(self, view: str) -> tuple[Prediction, ...]:
        """Every fold's test predictions, concatenated.

        Pooling is legitimate precisely because each cluster is a test cluster in
        exactly one fold -- ``dataset.load_folds`` asserts it. What pooling does
        *not* remove is the DD4 optimism: these are five models whose margins
        were each selected on a sibling fold's test clusters.
        """
        return tuple(prediction for fold in self.folds for prediction in getattr(fold, view))


def _qualify(prediction: Prediction, fold_index: int) -> Prediction:
    if prediction.example_id.startswith(f"fold{fold_index}:"):
        return prediction
    return Prediction(
        example_id=f"fold{fold_index}:{prediction.example_id}",
        truth=prediction.truth,
        predicted=prediction.predicted,
        unit=prediction.unit,
        label_mode=prediction.label_mode,
        library=prediction.library,
        subclass=prediction.subclass,
        fragment_id=prediction.fragment_id,
        scores=prediction.scores,
    )


# ---------------------------------------------------------------------------
# Building the JSON report
# ---------------------------------------------------------------------------


def _interval_dict(interval: Interval) -> dict:
    return {
        "point": interval.point,
        "low": interval.low,
        "high": interval.high,
        "effective_n": interval.effective_n,
        "resamples_used": interval.resamples_used,
    }


def _point_dict(value: float | None, units: int) -> dict:
    """A point estimate in interval shape, for slices no bootstrap was run on."""
    return {
        "point": value,
        "low": None,
        "high": None,
        "effective_n": units,
        "resamples_used": 0,
    }


#: The statistics a slice can carry, as confusion-matrix functions.
STATISTICS: Mapping[str, Callable[[Sequence[Sequence[int]]], float | None]] = {
    "accuracy": accuracy,
    "macro_f1": macro_f1,
    "null_recall": class_recall(CLASS_NULL),
}


def _slice_entry(
    name: str,
    predictions: Sequence[Prediction],
    *,
    statistics: Sequence[str],
    boot: BootstrapConfig | None,
) -> dict:
    """Score one slice. ``boot=None`` gives point estimates with no interval."""
    matrix = confusion_matrix(predictions)
    units = effective_n(predictions)
    entry: dict = {
        "name": name,
        "n_examples": len(predictions),
        "effective_n": units,
        "confusion": [list(row) for row in matrix],
    }
    for statistic in statistics:
        function = STATISTICS[statistic]
        if boot is None:
            entry[statistic] = _point_dict(function(matrix), units)
        else:
            entry[statistic] = _interval_dict(
                bootstrap_confusion_ci(
                    predictions,
                    function,
                    resamples=boot.resamples,
                    seed=boot.seed,
                    alpha=boot.alpha,
                )
            )
    return entry


def _per_class_dict(matrix: Sequence[Sequence[int]]) -> dict:
    return {
        name: {
            "support": metrics.support,
            "predicted": metrics.predicted,
            "true_positives": metrics.true_positives,
            "precision": metrics.precision,
            "recall": metrics.recall,
            "f1": metrics.f1,
        }
        for name, metrics in per_class_metrics(matrix).items()
    }


def _grouped_entries(
    groups: Mapping[object, list[Prediction]],
    *,
    statistics: Sequence[str],
    boot: BootstrapConfig | None,
    only: Sequence[str] | None = None,
) -> list[dict]:
    entries = []
    for key, predictions in groups.items():
        name = UNSLICED if key is None else str(key)
        if only is not None and name not in only:
            continue
        entries.append(_slice_entry(name, predictions, statistics=statistics, boot=boot))
    return entries


def _view(
    predictions: Sequence[Prediction],
    *,
    boot: BootstrapConfig | None,
    slice_boot: BootstrapConfig | None,
) -> dict:
    """Everything reported about one set of decisions (raw argmax, or ruled).

    ``slice_boot`` is separate from ``boot`` so the raw view can carry a
    bootstrapped headline without paying for intervals on forty sub-slices it
    shares with the ruled view whenever the selected margin is zero.
    """
    matrix = confusion_matrix(predictions)
    subclass_groups = slice_by_subclass(predictions)
    decisive = [prediction for prediction in predictions if prediction.fragment_id is not None]
    return {
        "overall": _slice_entry(
            "overall", predictions, statistics=("accuracy", "macro_f1"), boot=boot
        ),
        # Structural nulls -- filler recombined with no decisive fragment at all
        # -- share one resampling unit, because thousands of recombinations of a
        # handful of filler sentences are not thousands of observations. That is
        # right, and it makes the *overall* interval nearly unreadable: one unit
        # holding a third of the examples appears 0, 1, 2 or 3 times in a
        # resample, so the overall accuracy swings by twenty points on nothing.
        # This slice drops them, and it is the honest headline of the two.
        "decisive": _slice_entry(
            "decisive", decisive, statistics=("accuracy", "macro_f1"), boot=boot
        ),
        "per_class": _per_class_dict(matrix),
        "null_to_true": {
            "count": matrix[CLASS_NULL][CLASS_TRUE],
            "rate": null_to_true_rate(matrix),
            "null_support": sum(matrix[CLASS_NULL]),
        },
        "by_label_mode": _grouped_entries(
            slice_by_label_mode(predictions),
            statistics=("accuracy", "macro_f1"),
            boot=slice_boot,
        ),
        "by_subclass": _grouped_entries(
            subclass_groups,
            statistics=("null_recall",),
            boot=slice_boot,
            only=NULL_SUBCLASSES,
        ),
        "by_library": _grouped_entries(
            slice_by_library(predictions), statistics=("accuracy",), boot=slice_boot
        ),
    }


def _error_concentration(rows: Sequence[Mapping[str, object]]) -> dict:
    """Turn the per-fragment table into the one number the ticket turns on.

    DD7 poses a qualitative question -- are the errors spread thinly across many
    fragments, or piled onto a handful? -- and leaves it to a reader scrolling a
    forty-row table. That reading is the difference between "the method is too
    weak" and "these specific ideas are not learnable from the data we have",
    which is the ticket's whole question, so it is worth computing rather than
    eyeballing.

    ``fragments_carrying_half`` against ``fragments_with_errors`` is the
    comparison to read, and it has a fixed reference point: if every erring
    fragment erred equally often, half the errors would sit on half of them, so
    a share near 50% is an even spread and a share near zero is concentration.
    ``share_in_worst_ten`` is the same shape of statement against a fixed
    number of fragments, which is what a library-work decision would actually
    be taken on.
    """
    counts = sorted((int(row["n_examples"]) - int(row["n_correct"]) for row in rows), reverse=True)
    errors = [count for count in counts if count]
    total = sum(errors)
    if not total:
        return {
            "decisive_fragments": len(rows),
            "fragments_with_errors": 0,
            "total_errors": 0,
            "fragments_carrying_half": 0,
            "even_spread_would_be": None,
            "share_in_worst_ten": None,
        }
    running = 0
    carrying_half = 0
    for count in errors:
        running += count
        carrying_half += 1
        if running * 2 >= total:
            break
    return {
        "decisive_fragments": len(rows),
        "fragments_with_errors": len(errors),
        "total_errors": total,
        "fragments_carrying_half": carrying_half,
        # What an even spread across the erring fragments would have given, so
        # the figure above is read against something rather than against a hunch.
        "even_spread_would_be": len(errors) / 2,
        "share_in_worst_ten": sum(errors[:10]) / total,
    }


def _fragment_table(predictions: Sequence[Prediction]) -> list[dict]:
    """The DD7 per-fragment error table, worst first.

    The most decision-useful thing in the report, and the one that actually
    answers the ticket's question. Errors spread thinly across many fragments
    say the method is too weak, so the next move is model work. Errors piled
    onto a handful say those specific ideas are not learnable from the data we
    have, so the next move is library work -- and this table names them.

    No confidence intervals here on purpose: a fragment is one cluster or part
    of one, so an interval over its own examples would be measuring the
    recombination process and nothing else.
    """
    rows = []
    for fragment_id, group in slice_by_fragment(predictions).items():
        if fragment_id is None:
            continue
        first = group[0]
        correct = sum(1 for prediction in group if prediction.correct)
        predicted_counts = [0] * len(CLASS_NAMES)
        for prediction in group:
            predicted_counts[prediction.predicted] += 1
        rows.append(
            {
                "fragment_id": str(fragment_id),
                "library": first.library,
                "subclass": first.subclass,
                "truth": CLASS_NAMES[first.truth],
                "n_examples": len(group),
                "n_correct": correct,
                "accuracy": correct / len(group),
                "predicted": dict(zip(CLASS_NAMES, predicted_counts, strict=True)),
            }
        )
    rows.sort(key=lambda row: (row["accuracy"], -row["n_examples"], row["fragment_id"]))
    return rows


def model_movement(models: Sequence[Mapping[str, object]]) -> dict:
    """What changed *where*, model by model, rather than in the headline.

    A headline accuracy is the least useful output of a model comparison here.
    The 2026-08-09 run put 71% of its errors on two libraries and half of them on
    17 fragments, so the question a second encoder has to answer is not "is it
    better on average" but "does it move that short list". A diffuse lift and a
    fix to contrastive negation are different findings and would lead to
    different next months; an aggregate cannot tell them apart.

    Both tables are built from the model blocks already in the report rather than
    from the predictions again, so they cannot disagree with the per-model
    sections below them. Rows are ordered by the *worst* model's error count, so
    the fragments the whole comparison is about sort to the top whichever encoder
    happens to win. Only non-control models appear: a shuffled-label run's error
    count is not a fact about a fragment.

    ``spread`` is the max-minus-min across models on a row -- the column to read.
    A library or fragment where every model lands within a point is one that
    model choice does not touch, whatever the headline does.
    """
    named = [model for model in models if model.get("kind") != "negative_control"]
    names = [str(model["name"]) for model in named]
    if len(named) < 2:
        return {"models": names, "by_library": [], "by_fragment": []}

    library_accuracy: dict[str, dict[str, float]] = {}
    library_support: dict[str, int] = {}
    for model in named:
        for entry in model["pooled"]["ruled"]["by_library"]:
            library = str(entry["name"])
            point = (entry.get("accuracy") or {}).get("point")
            if point is None:
                continue
            library_accuracy.setdefault(library, {})[str(model["name"])] = float(point)
            library_support[library] = int(entry["n_examples"])

    by_library = [
        {
            "library": library,
            "n_examples": library_support[library],
            "accuracy": scores,
            "spread": max(scores.values()) - min(scores.values()),
        }
        for library, scores in library_accuracy.items()
        if len(scores) == len(names)
    ]
    by_library.sort(key=lambda row: (min(row["accuracy"].values()), row["library"]))

    fragment_errors: dict[str, dict[str, int]] = {}
    fragment_meta: dict[str, dict] = {}
    for model in named:
        for row in model["fragments"]:
            fragment_id = str(row["fragment_id"])
            errors = int(row["n_examples"]) - int(row["n_correct"])
            fragment_errors.setdefault(fragment_id, {})[str(model["name"])] = errors
            fragment_meta.setdefault(
                fragment_id,
                {"library": row["library"], "subclass": row["subclass"], "truth": row["truth"]},
            )

    by_fragment = [
        {
            "fragment_id": fragment_id,
            **fragment_meta[fragment_id],
            "errors": counts,
            "spread": max(counts.values()) - min(counts.values()),
        }
        for fragment_id, counts in fragment_errors.items()
        if len(counts) == len(names) and max(counts.values()) > 0
    ]
    by_fragment.sort(key=lambda row: (-max(row["errors"].values()), row["fragment_id"]))

    return {"models": names, "by_library": by_library, "by_fragment": by_fragment}


def _is_cluster_tagged(library: str, cluster_key: str) -> bool:
    """Did this fragment's line carry a ``[cNN]`` marker?

    The sidecar records the *key the splitter hashed*, not the marker, and the
    generator's rule (``manifest.cluster_key``) is: a tagged line hashes
    ``{library}:{tag}``, an untagged one hashes its own normalised text. So the
    namespace prefix is the tag's fingerprint, and reading it back this way is
    what lets the coverage table be built from the sidecar rather than by
    re-opening the libraries -- which the report must never do, for the reason
    :data:`FEVER_LIBRARY_CLUSTERS` gives: the libraries may have been edited
    since the dataset was generated, and a table that silently re-read them
    would describe a different library than the numbers above it came from.
    """
    return cluster_key.startswith(f"{library}:")


def cluster_tag_coverage(fragments: Sequence, *, signal: str | None = None) -> dict:
    """Per-library share of lines carrying a cluster marker, for this signal.

    This exists because ``eff n`` -- the number that bounds every interval in
    this report -- is computed over *clusters*, and a library with no cluster
    markers contributes one cluster per line by default. That default is a
    claim, not a measurement: it says every line in the library is an
    independent idea. Where it is true the eff n is right; where it is not, the
    library's eff n is an **upper bound** and every interval on a slice drawn
    from it is narrower than the truth.

    The claim is currently made for four of the six trainable signals. Only the
    `fever_*` and `dysuria_*` confounder libraries were hand-tagged, so
    `urinary_frequency`, `nocturia`, `flank_pain` and `haematuria` post their
    numbers on the untested assumption -- and `dysuria`, the only signal
    clustered throughout, posts *worse* numbers than it should for the same
    reason, because tagging is the thing that stops one idea being counted
    twice. A reader comparing signals without that in front of them is reading
    a ranking that is substantially an artefact of which libraries were tagged.

    Restricted to the run's own signal. Filler libraries carry no signal and are
    never a decisive fragment, so they never appear in the ``by_library`` slice
    this annotates; listing them here would put five permanently-0% rows above
    a warning that is about something else.

    The restriction is over ``signals``, not the scalar ``signal_key``, because
    a declarative fragment decides several signals and carries no scalar. Read
    the old way it would be dropped from every signal's table while still
    appearing in that signal's ``by_library`` rows -- a library posting numbers
    with no coverage line under them, which is the one thing this table exists
    to prevent.
    """
    tagged: dict[str, int] = {}
    total: dict[str, int] = {}
    for fragment in fragments:
        if signal is not None and signal not in (fragment.signals or ()):
            continue
        if fragment.is_filler:
            continue
        library = fragment.library
        total[library] = total.get(library, 0) + 1
        if _is_cluster_tagged(library, fragment.cluster_key):
            tagged[library] = tagged.get(library, 0) + 1

    libraries = [
        {
            "library": library,
            "fragments": count,
            "tagged": tagged.get(library, 0),
            "coverage": tagged.get(library, 0) / count,
        }
        for library, count in sorted(total.items())
    ]
    libraries.sort(key=lambda row: (row["coverage"], row["library"]))
    untagged = [row["library"] for row in libraries if not row["tagged"]]
    return {
        "signal": signal,
        "libraries": libraries,
        "untagged_libraries": untagged,
        "fragments_in_untagged_libraries": sum(
            row["fragments"] for row in libraries if not row["tagged"]
        ),
        "total_fragments": sum(row["fragments"] for row in libraries),
    }


def _coverage_summary(coverage: Mapping[str, object]) -> str:
    """The coverage block as one line, for the header table."""
    libraries = coverage.get("libraries") or []
    if not libraries:
        return "not recorded"
    untagged = coverage.get("untagged_libraries") or []
    return (
        f"{len(libraries) - len(untagged)} of {len(libraries)} libraries carry cluster markers; "
        f"{coverage['fragments_in_untagged_libraries']} of {coverage['total_fragments']} "
        "fragments are in libraries with none"
    )


def _mcnemar_dict(left: ModelRun, right: ModelRun, slice_name: str, result: McNemarResult) -> dict:
    return {
        "a": left.name,
        "b": right.name,
        "slice": slice_name,
        "n_pairs": result.n_pairs,
        "a_only_correct": result.a_only_correct,
        "b_only_correct": result.b_only_correct,
        "p_value": result.p_value,
    }


def _restrict(predictions: Sequence[Prediction], slice_name: str) -> list[Prediction]:
    if slice_name == "overall":
        return list(predictions)
    return [prediction for prediction in predictions if prediction.label_mode == slice_name]


def _skipped_dict(
    left: ModelRun,
    right: ModelRun,
    slice_name: str,
    a: Sequence[Prediction],
    b: Sequence[Prediction],
) -> dict:
    """Why one pair could not be tested, in enough detail to tell bug from fact."""
    a_ids = {prediction.example_id for prediction in a}
    b_ids = {prediction.example_id for prediction in b}
    common = len(a_ids & b_ids)
    return {
        "a": left.name,
        "b": right.name,
        "slice": slice_name,
        "n_a": len(a_ids),
        "n_b": len(b_ids),
        "n_common": common,
        "reason": (
            f"example sets differ: {left.name} has {len(a_ids)}, {right.name} has {len(b_ids)}, "
            f"{common} in common"
        ),
    }


def compare_models(
    runs: Sequence[ModelRun], *, slices: Sequence[str] = ("overall", "null_ambiguous")
) -> tuple[list[dict], list[dict]]:
    """Paired McNemar tests between every pair of non-control models.

    Run on the **raw** argmax decisions. Comparing two models under two
    separately-tuned margins would confound a difference in the models with a
    difference in their rules, and the rule is the thing that is easiest to
    change afterwards.

    Returns ``(comparisons, skipped)``. A pair whose two sides were scored on
    **different examples** cannot be paired at all -- there is nothing to pair --
    and one report can now legitimately hold such a pair: the three-arm joint
    comparison puts A2, a freshly generated dataset with its own example ids, in
    the same report as the two arms that share one. Those pairs are recorded in
    ``skipped`` rather than dropped, because a reader who expected three
    comparisons and finds two will otherwise read the missing one as "no
    difference found". A pair skipped for any reason other than a genuine
    dataset difference is a bug, and the entry is what makes it findable.

    Only that one condition is caught here. Every other :class:`MetricsError`
    -- duplicate ids, or the two sides disagreeing about an example's truth --
    is still raised, because both mean something is wrong with the report's
    inputs rather than with the pairing.
    """
    comparable = [run for run in runs if not run.is_control]
    comparisons: list[dict] = []
    skipped: list[dict] = []
    for index, left in enumerate(comparable):
        for right in comparable[index + 1 :]:
            for slice_name in slices:
                a = _restrict(left.pooled("raw"), slice_name)
                b = _restrict(right.pooled("raw"), slice_name)
                if not a or not b:
                    continue
                if {prediction.example_id for prediction in a} != {
                    prediction.example_id for prediction in b
                }:
                    skipped.append(_skipped_dict(left, right, slice_name, a, b))
                    continue
                comparisons.append(_mcnemar_dict(left, right, slice_name, mcnemar(a, b)))
    return comparisons, skipped


def _null_to_true_fold_rates(entries: Sequence[Mapping[str, object]]) -> list[float | None]:
    """One `null -> true` rate per fold, from that fold's own counts."""
    rates: list[float | None] = []
    for entry in entries:
        cell = entry["null_to_true"]
        support = cell["null_support"]
        rates.append(None if not support else cell["count"] / support)
    return rates


def _holdout_cells(fold: FoldRun, signal: str) -> list[Prediction] | None:
    """One fold's real-text decisions for one signal, or ``None`` if unavailable.

    ``None`` covers three different situations on purpose -- the run did not
    score the holdout, it was scored by code written before the cells were kept,
    or this signal was not among the heads scored -- because all three mean the
    same thing to the caller: there is nothing to pair, and the reason belongs
    in a skip entry rather than in an exception.
    """
    block = fold.holdout
    if not block:
        return None
    cells = block.get("cells")
    if not isinstance(cells, Mapping) or signal not in cells:
        return None
    return [
        Prediction(
            example_id=str(cell["id"]),
            truth=int(cell["truth"]),
            predicted=int(cell["predicted"]),
            unit=str(cell.get("unit") or cell["id"]),
        )
        for cell in cells[signal]
    ]


def _null_to_true_rates(run: ModelRun, signal: str) -> list[float | None]:
    """Each fold's real-text ``null -> true`` rate for one signal."""
    rates: list[float | None] = []
    for fold in run.folds:
        block = fold.holdout
        entry = None
        if block:
            entry = next(
                (item for item in block.get("by_signal", ()) if item.get("signal") == signal),
                None,
            )
        if entry is None:
            rates.append(None)
            continue
        cell = entry["null_to_true"]
        support = cell["null_support"]
        rates.append(None if not support else cell["count"] / support)
    return rates


def _mean(values: Sequence[float | None]) -> float | None:
    present = [value for value in values if value is not None]
    return sum(present) / len(present) if present else None


def holdout_comparisons(
    runs: Sequence[ModelRun], *, signal: str | None
) -> tuple[list[dict], list[dict]]:
    """Paired McNemar between every pair of models on the **real-text** holdout.

    This is the comparison the multi-symptom ticket turns on, and it is separate
    from :func:`compare_models` for a reason that is not presentational. Two arms
    generated at different companion shares hold *different texts under the same
    example ids*, so their synthetic test splits cannot be paired at all -- but
    the holdout is the same 67 submissions for every arm, scored by every fold,
    and it pairs exactly.

    **Fold by fold, never pooled.** Five folds are five models scored on one
    sample of 67; concatenating them would hand McNemar 335 pairs over 67
    observations and report a p-value for a sample size that does not exist. So
    each fold gets its own test, all five are reported, and the summary counts
    how many folds moved which way rather than combining them into one number.
    Even per fold this is a test over *cells*: a submission contributes up to one
    cell per signal here, and the folds are five models trained on overlapping
    data, so the five p-values are neither independent of each other nor a
    confidence statement about new patients.

    ``signal`` is the head this report is about. ``None`` -- a report with no
    single signal -- returns nothing rather than guessing which head to pair.
    """
    if signal is None:
        return [], []
    comparable = [run for run in runs if not run.is_control]
    comparisons: list[dict] = []
    skipped: list[dict] = []
    for index, left in enumerate(comparable):
        for right in comparable[index + 1 :]:
            if len(left.folds) != len(right.folds):
                skipped.append(
                    {
                        "left": left.name,
                        "right": right.name,
                        "signal": signal,
                        "reason": (
                            f"{left.name} has {len(left.folds)} folds and {right.name} has "
                            f"{len(right.folds)}, so there is no fold-for-fold pairing"
                        ),
                    }
                )
                continue

            rows: list[dict] = []
            reason: str | None = None
            for left_fold, right_fold in zip(left.folds, right.folds, strict=True):
                a = _holdout_cells(left_fold, signal)
                b = _holdout_cells(right_fold, signal)
                if a is None or b is None:
                    reason = (
                        "one or both runs carry no real-text cells for this signal (not scored, "
                        "or scored before the per-submission decisions were kept)"
                    )
                    break
                if {prediction.example_id for prediction in a} != {
                    prediction.example_id for prediction in b
                }:
                    reason = (
                        "the two runs scored different submissions, so the real-text results "
                        "cannot be paired"
                    )
                    break
                result = mcnemar(a, b)
                rows.append(
                    {
                        "fold": left_fold.fold_index,
                        "n_pairs": result.n_pairs,
                        "left_only_correct": result.a_only_correct,
                        "right_only_correct": result.b_only_correct,
                        "p_value": result.p_value,
                    }
                )
            if reason is not None:
                skipped.append(
                    {"left": left.name, "right": right.name, "signal": signal, "reason": reason}
                )
                continue

            left_rates = _null_to_true_rates(left, signal)
            right_rates = _null_to_true_rates(right, signal)
            left_mean, right_mean = _mean(left_rates), _mean(right_rates)
            comparisons.append(
                {
                    "left": left.name,
                    "right": right.name,
                    "signal": signal,
                    "n_pairs": rows[0]["n_pairs"] if rows else 0,
                    "folds": rows,
                    "left_better_folds": sum(
                        1 for row in rows if row["left_only_correct"] > row["right_only_correct"]
                    ),
                    "right_better_folds": sum(
                        1 for row in rows if row["right_only_correct"] > row["left_only_correct"]
                    ),
                    "null_to_true": {
                        "left_rates": left_rates,
                        "right_rates": right_rates,
                        "left_mean": left_mean,
                        "right_mean": right_mean,
                        # Positive means the right-hand run answers `true` on
                        # truly-null real text less often than the left one --
                        # the direction the ticket's threshold is written in.
                        "delta_points": (
                            None
                            if left_mean is None or right_mean is None
                            else 100 * (left_mean - right_mean)
                        ),
                    },
                    "not_pooled": (
                        "one test per fold over the same 67 submissions, never concatenated: five "
                        "folds are five models scored on one sample, and pooling would report a "
                        "p-value for 335 observations that do not exist"
                    ),
                }
            )
    return comparisons, skipped


def _holdout_spread(values: Sequence[float | None]) -> dict:
    """Mean and sd of one holdout statistic across the folds.

    Folds whose statistic is undefined -- an empty slice -- are dropped rather
    than scored zero, and how many contributed is recorded beside the mean.
    """
    present = [value for value in values if value is not None]
    if not present:
        return {"mean": None, "sd": None, "n_folds": 0, "values": list(values)}
    spread = fold_spread(present)
    return {
        "mean": spread.mean,
        "sd": spread.sd,
        "n_folds": spread.n_folds,
        "values": list(values),
    }


def _holdout_slice(blocks: Sequence[Mapping[str, object]], key: str) -> dict:
    """One holdout slice across the folds: fixed counts, spread accuracy.

    ``n_cells`` and ``n_submissions`` are properties of the *set*, not of a
    model, so they are asserted identical across folds rather than averaged --
    five folds scoring different numbers of cells would mean the label file
    changed under the run.
    """
    slices = [block[key] for block in blocks]
    counts = {(entry["n_cells"], entry["n_submissions"]) for entry in slices}
    if len(counts) > 1:
        raise ValueError(
            f"the folds disagree about the size of the holdout {key!r} slice: {sorted(counts)}. "
            "The held-out set is the same 67 submissions in every fold, so this means the labels "
            "file changed mid-run and no number from it is interpretable"
        )
    n_cells, n_submissions = counts.pop()
    return {
        "n_cells": n_cells,
        "n_submissions": n_submissions,
        "worst_case_half_width": slices[0]["worst_case_half_width"],
        "accuracy": _holdout_spread([entry["accuracy"]["point"] for entry in slices]),
        "per_fold": [
            {
                "point": entry["accuracy"]["point"],
                "low": entry["accuracy"]["low"],
                "high": entry["accuracy"]["high"],
            }
            for entry in slices
        ],
    }


def holdout_summary(run: ModelRun) -> dict | None:
    """One model's real-text holdout numbers, aggregated across its folds.

    ``None`` when no fold scored it, so a report built before this existed --
    or with ``--no-holdout`` -- carries no empty section pretending the check
    ran.

    **The folds are not pooled, and that is the whole design of this block.**
    Five folds are five different models scored on the *same* 67 submissions,
    so concatenating their predictions would count each submission five times
    and report an effective n of 335 for a set that holds 67 observations. Mean
    and spread across folds is what five models on one sample supports; the
    spread is a stability check on the same four degrees of freedom the
    synthetic fold spread has, not a confidence interval.
    """
    blocks = [fold.holdout for fold in run.folds if fold.holdout is not None]
    if not blocks:
        return None
    if len(blocks) != len(run.folds):
        raise ValueError(
            f"{run.name}: {len(blocks)} of {len(run.folds)} folds carry a holdout score. A "
            "partially-scored holdout would make the mean below an average over a different set "
            "of models than the report's other numbers describe"
        )

    paths = {str(block["path"]) for block in blocks}
    if len(paths) > 1:
        raise ValueError(f"{run.name}: the folds scored different holdout files: {sorted(paths)}")

    signals = list(blocks[0]["signals_scored"])
    by_signal: list[dict] = []
    for position, signal in enumerate(signals):
        entries = [block["by_signal"][position] for block in blocks]
        if {entry["signal"] for entry in entries} != {signal}:
            raise ValueError(f"{run.name}: the folds' holdout signals are in different orders")
        entry = {
            "signal": signal,
            "distribution": entries[0]["distribution"],
            "all": _holdout_slice(entries, "all"),
            "decisive": _holdout_slice(entries, "decisive"),
            "per_class_recall": {
                name: _holdout_spread([entry["per_class"][name]["recall"] for entry in entries])
                for name in CLASS_NAMES
            },
            # The headline of the real-text section, and the cell the
            # multi-symptom ticket's declared threshold is written against: how
            # often a model asserts `true` about a signal a real submission
            # never mentioned. Counts are per fold; the rate and its mean are
            # derived here so a reader scoring a threshold is not doing
            # arithmetic across five folds by hand.
            "null_to_true": {
                "null_support": entries[0]["null_to_true"]["null_support"],
                "counts": [entry["null_to_true"]["count"] for entry in entries],
                "rates": _null_to_true_fold_rates(entries),
                "mean_rate": _mean(_null_to_true_fold_rates(entries)),
            },
        }
        caveats = {entry.get("caveat") for entry in entries if entry.get("caveat")}
        if caveats:
            entry["caveat"] = sorted(caveats)[0]
        by_signal.append(entry)

    return {
        "path": paths.pop(),
        "n_submissions": blocks[0]["n_submissions"],
        "n_folds": len(blocks),
        "signals_scored": signals,
        "signals_not_scored": list(blocks[0]["signals_not_scored"]),
        "margins": [block["margin"] for block in blocks],
        "bootstrap": blocks[0]["bootstrap"],
        "resampling_unit": blocks[0]["resampling_unit"],
        "selected_nothing": blocks[0]["selected_nothing"],
        "not_pooled": (
            "the folds are not pooled. Five folds are five models scored on the same 67 "
            "submissions, so pooling would count each submission five times; the figures below "
            "are the mean and spread across folds, and the spread is a stability check rather "
            "than a confidence interval"
        ),
        "overall": _holdout_slice(blocks, "overall"),
        "decisive": _holdout_slice(blocks, "decisive"),
        "by_signal": by_signal,
        "provenance": blocks[0]["provenance"],
        "voice": blocks[0]["voice"],
        "power": blocks[0]["power"],
    }


def _model_block(run: ModelRun, *, boot: BootstrapConfig) -> dict:
    ruled = run.pooled("ruled")
    raw = run.pooled("raw")
    margins = {fold.rule.margin for fold in run.folds}
    rule_is_argmax = margins == {0.0}

    fragments = _fragment_table(ruled)
    accuracies = [accuracy(confusion_matrix(fold.ruled)) or 0.0 for fold in run.folds]
    macros = [macro_f1(confusion_matrix(fold.ruled)) or 0.0 for fold in run.folds]
    spread = {
        "accuracy": _spread_dict(fold_spread(accuracies)),
        "macro_f1": _spread_dict(fold_spread(macros)),
    }

    return {
        "name": run.name,
        "kind": run.kind,
        "description": run.description,
        "rule_is_argmax": rule_is_argmax,
        "margins": [{"fold": fold.fold_index, **fold.rule.to_dict()} for fold in run.folds],
        "per_fold": [
            {
                "fold": fold.fold_index,
                "n_train": fold.n_train,
                "n_val": fold.n_val,
                "n_test": fold.n_test,
                "margin": fold.rule.margin,
                "raw": _fold_point(fold.raw),
                "ruled": _fold_point(fold.ruled),
            }
            for fold in run.folds
        ],
        "fold_spread": spread,
        "pooled": {
            # Intervals on every sub-slice of the ruled view, which is the one
            # a deployment would use; the raw view carries a bootstrapped
            # headline and point estimates below it. When the selected margin is
            # zero on every fold the two views are the same numbers anyway.
            "ruled": _view(ruled, boot=boot, slice_boot=boot),
            "raw": _view(raw, boot=boot, slice_boot=None),
        },
        "fragments": fragments,
        "error_concentration": _error_concentration(fragments),
        # `None` where the run did not score it, so a report built before the
        # holdout existed carries no section claiming the check ran.
        "holdout": holdout_summary(run),
    }


def _fold_point(predictions: Sequence[Prediction]) -> dict:
    matrix = confusion_matrix(predictions)
    return {
        "n_examples": len(predictions),
        "effective_n": effective_n(predictions),
        "accuracy": accuracy(matrix),
        "macro_f1": macro_f1(matrix),
        "null_to_true_rate": null_to_true_rate(matrix),
    }


def _spread_dict(spread) -> dict:
    return {
        "n_folds": spread.n_folds,
        "mean": spread.mean,
        "sd": spread.sd,
        "values": list(spread.values),
    }


#: Statements the report must carry every time, because each one is a way the
#: numbers above them get over-read. They are written out rather than left to a
#: reader's memory of the plan: a report is read standalone or not at all.
LIMITATIONS = (
    "**Effective n, not n, bounds every number here.** A slice's example count says how much "
    "recombination happened. Its effective n -- the number of distinct hand-written fragment "
    "clusters behind it -- says how many independent ideas were tested, and that is what the "
    "error bar is computed over. Ten thousand examples built from sixty-six fragments is "
    "sixty-six ideas seen many times, and quoting the ten thousand is the single easiest way to "
    "over-read this report.",
    "**Fold aggregation buys about a factor of three on the error bar, not a factor of twelve.** "
    "Pooling five folds raises the effective n of each hard sub-class from 2-5 clusters to its "
    "whole library, 32-47. Uncertainty on a proportion falls as 1/sqrt(n), so roughly +/-30 "
    "points becomes roughly +/-8. That is the difference between a number that can carry a "
    "conclusion and one that cannot; it is not a twelve-fold improvement in precision.",
    "**The pooled result carries a small optimism.** Fold i's validation clusters are fold i+1's "
    "test clusters, so each fold's margin was selected on a sibling fold's test data. Within any "
    "one fold there is no leakage -- each fold trains its own model and never sees its own test "
    "bucket -- but the pooled figure is very slightly flattered. Nested cross-validation would "
    "remove it and is not worth the cost for one scalar per fold.",
    "**The across-fold standard deviation is a stability check, not a confidence interval.** "
    "Five folds give it four degrees of freedom, so it is itself noisy and will occasionally look "
    "reassuringly small for no reason. The headline interval is the pooled cluster bootstrap.",
    "**McNemar's pairing unit is the example, not the cluster.** It answers \"did these two "
    'models behave differently on this data", which is narrower than "would they behave '
    "differently on new fragments\". Where a slice's examples are recombinations of a few "
    "clusters it will overstate significance in exactly the way the cluster bootstrap avoids. "
    "Read it alongside the interval, never instead of it.",
    "**Fold mode trains on 60% of clusters, the legacy split on 70%.** Numbers here are "
    "therefore not directly comparable to any single-split figure recorded in "
    "`arch_training.md` section 10. The fold-aggregated numbers are the honest ones.",
    "**A slice containing only one class cannot be read on its own.** The five `null` sub-class "
    "slices hold nothing but truly-`null` examples, so a model that answers `null` unconditionally "
    "scores 100% on all of them. Sub-class recall is a finding only when the `true` and `false` "
    "recalls are high at the same time, which is why the per-class table sits beside it.",
    "**The overall interval is dominated by one resampling unit.** All structural nulls share "
    "one unit, by design -- thousands of recombinations of a handful of filler sentences are not "
    "thousands of observations. The cost is that the pooled overall accuracy swings widely under "
    "resampling for reasons that have nothing to do with the model. The `decisive` slice, which "
    "drops them, is the one to read.",
    "**The real-text holdout cannot rank two models, and is not a smaller version of the tables "
    "above.** 67 submissions with no cluster structure give roughly +/-12 points on one overall "
    "figure and +/-20 or worse on a per-signal decisive slice. It answers a different question -- "
    "does any of this transfer to text a patient actually wrote -- and it answers it in one "
    "direction only: a large drop there is conclusive, a small difference between two models "
    "there is noise.",
    "**Fragment libraries, not sample size, are the ceiling.** Forty-seven metaphor clusters is "
    "forty-seven ideas however many examples are drawn from them. Everything section 9 of "
    "`arch_training.md` says about what this data is and is not worth continues to apply in "
    "full.",
)

#: What we expect to see before looking, recorded so the report can be scored
#: against a prediction rather than rationalised after the fact.
EXPECTATIONS = (
    "Majority-class should land near 60%, which is the generator's `null` share and not a "
    "property of the data worth anything.",
    "The length-only model is the direct measurable test of the length leak `arch_training.md` "
    "section 9 argues for but has never measured. Materially above majority means text length "
    "is a usable proxy for the label, which is a library problem rather than a model one.",
    "TF-IDF should do well on clear positives, clear negatives and `null_structural`, and badly "
    "on the ambiguous sub-classes. Its overall accuracy is therefore close to uninformative. "
    "**The number that matters is the `null_ambiguous` slice**, tested with McNemar against the "
    "transformer once that exists.",
    "Both negative controls must fail. Shuffled train labels must score at chance on the "
    "unpermuted test split, and no fragment or cluster may appear on both sides of a split.",
    "Arm A -- the frozen probe -- should handle clear positives, clear negatives and "
    "`null_structural`, and should do **badly** on the five hard `null` sub-classes. "
    "Third-party attribution, tense and metaphor are compositional scope problems, and a single "
    "mean-pooled vector blurs the structure that carries them: a linear probe over it has no "
    'mechanism for "the fever belongs to the daughter". A bad Arm A result on those slices is '
    "the predicted outcome, not a bug.",
    "Arm A beating TF-IDF on `null_ambiguous` would be a genuine finding about the encoder; "
    "losing to it there would say the pooled representation discards what the ambiguous "
    "libraries are made of. Either way the comparison is McNemar's, not two point estimates "
    "side by side -- and neither answers the ticket's question on its own, because Arm A cannot "
    'separate "the libraries are the bottleneck" from "the method is too weak". That is Arm '
    "B's job.",
    "Arm B -- the fine-tune -- is the arm that answers the ticket, and **either outcome is a "
    "finding**. If unfreezing 110M parameters lifts the five hard `null` sub-classes clear of "
    "Arm A, the frozen pooled representation was the bottleneck and the fix is model work. If it "
    "does not -- if a fully fine-tuned encoder still cannot tell whose fever it is or when it "
    "happened -- then the limit is in the ideas the libraries contain, and the fix is library "
    "work on the fragments the per-fragment table names. Nothing here predicts which; the point "
    "of building both arms is that the question stops being answerable by argument.",
    "Arm B's negative control passes by doing **two** things at once: driving training loss "
    "towards zero, because 110M parameters can memorise a permutation, while scoring at chance "
    "on the unpermuted test split. Near-zero training loss on its own is not a failure and "
    "chance test performance on its own is not a pass; the sidecar records the per-fold loss "
    "curve so both halves can be read.",
    "Arm B is expected to be *unstable* across folds in a way Arm A is not. Fine-tuning a "
    "110M-parameter model on 10,000 recombinations of a few dozen fragments has far more freedom "
    "to fit fold-specific detail, so the across-fold standard deviation should be the wider of "
    "the two. That is a property of the arm, not evidence against it -- but it is why the pooled "
    "cluster bootstrap, not the fold spread, remains the headline interval.",
    "`max_seq_len` is not the interesting constraint. The proof-of-concept run's median example "
    "is 36 tokens and its 90th percentile 54, against a limit of 256. Training on 36-token "
    "recombinations and eventually serving 300-token real submissions is a distribution shift no "
    "sequence length fixes.",
)


#: The `fever_present` libraries as fragments and as **clusters**, which is what
#: the effective-sample-size argument is actually made of. Pooled over all five
#: folds every cluster is a test cluster exactly once, so these are the effective
#: n a sub-class row can reach.
#:
#: Hard-coded rather than derived, because the report must not open the fragment
#: libraries: they may have moved since the dataset was generated, and a table
#: that silently re-read them would describe a different library than the one the
#: numbers above it came from. `tests/test_encoder_training_report.py` asserts
#: this table against the real libraries, so drift is caught in CI instead.
FEVER_LIBRARY_CLUSTERS = (
    ("fever_true", 96, 96),
    ("fever_false", 98, 98),
    ("fever_null_attribution", 50, 43),
    ("fever_null_hedged", 73, 63),
    ("fever_null_historical", 45, 36),
    ("fever_null_metaphor", 55, 47),
    ("fever_null_thirdparty", 46, 35),
)

#: `arch_training.md` section 9 -- "what this data is and is not worth" --
#: reproduced rather than cross-referenced. This is the one place duplication is
#: deliberate: the report is read standalone by people who have not read the
#: architecture docs, and every number in it is bounded by these five facts. A
#: cross-reference here would be a footnote nobody follows.
DATA_LIMITS = (
    "**The validation score is a smoke test, not evidence.** Under the default bands validation "
    "holds 15 distinct positive fragments, and every `true` validation example is a recombination "
    "of those 15 sentences; one unlucky fragment moves the score several points. The training "
    "plan asks for around 200 fragments per signal. We have roughly half that for `true` and for "
    "`false` alike.",
    "**Length may still leak.** Fragment *count* is drawn from one distribution that never sees "
    "the label, so it cannot be a proxy for it. Fragment *length* is not controlled at all: "
    "`fever_true` fragments run from 3 words to 98, while the `fever_null` libraries sit in a "
    "9-40 word band. The medians are close (16 against 15-19), so this is a tail problem rather "
    "than a systematic offset -- but a 98-word positive has no counterpart anywhere in the null "
    "libraries, and a model can notice that. The `length_only` baseline in this report is the "
    "direct measurement of how much is there to notice.",
    "**Urgency language leaks too.** About 17% of `fever_true` fragments bundle the fever claim "
    'with a justification -- "three important meetings I can\'t miss" -- against 8% of '
    '`fever_false` and almost none of `fever_null`. That is exactly the "sounds urgent, must be '
    'positive" shortcut the libraries are meant to prevent. Pairing with filler washes some of it '
    "out; fixing it properly is library work.",
    "**The examples are short.** Two or three sentences by default, against real submissions that "
    "are longer and messier. The variable fragment count narrows that gap rather than closing it: "
    "the count ceiling is the number of filler libraries, and past a few fragments each example "
    "still carries exactly one supervised claim, just buried in more noise. The proof-of-concept "
    "run's median example is 36 tokens against a `max_seq_len` of 256, so sequence length is not "
    "the constraint and raising it would fix nothing.",
    "**One signal per dataset, and six signals have libraries.** A generated example carries a "
    "label for the run's signal and no other, so nothing here is multi-label. What changed is "
    "that the filler libraries are now lint-verified silent about all six signals with libraries "
    "-- fever, dysuria, urinary frequency, nocturia, flank pain, haematuria -- rather than about "
    "fever alone. They are *not* silent about `recent_uti_present`, the seventh "
    "`send_to_encoder` signal, which has no libraries and so no lexicon: `uti_speculation` "
    "asserts it outright.",
    "**The six signals' numbers are not comparable to each other at face value.** Only the "
    "`fever_*` and `dysuria_*` confounder libraries are hand-tagged into clusters. The other four "
    "signals' libraries treat every line as an independent idea, which flatters their `eff n` and "
    "narrows their intervals; `dysuria`, tagged throughout, is penalised for it. The "
    "cluster-tag coverage table at the top of this report is the per-run statement of how far "
    "that applies here. It does not touch a fever-versus-fever comparison, which is scored on "
    "identical, already-tagged fever clusters.",
)

#: The "Effective sample size" subsection of `arch_training.md` section 10,
#: reproduced for the same reason as :data:`DATA_LIMITS`. It is the single
#: easiest way to over-read anything in this report, so it is stated before the
#: reader can reach for an example count.
EFFECTIVE_SAMPLE_SIZE = (
    "The single easiest way to over-read anything this pipeline produces is to quote an example "
    "count. **The effective sample size of any evaluation slice is the number of distinct "
    "clusters behind it, not the number of examples.** Ten thousand examples built from 66 "
    "training fragments is 66 ideas seen many times.",
    "Clusters rather than fragments, because `[c01]`-tagged siblings are one idea written twice. "
    "They always land in the same split, so they are one observation and not two -- which means "
    "the manual clustering *reduces* effective n where it applies, correctly, because it stopped "
    "counting the same idea twice.",
    "Under a single 70/15/15 split a per-sub-class score is computed over **2 to 5 independent "
    "ideas**, and all five hard sub-classes together are of that order. A third-party recall "
    "figure could "
    "then take only the values 0, 0.5 or 1.0, carrying an uncertainty of roughly +/-30 percentage "
    "points -- wider than any effect this ticket could plausibly detect. That is a library-size "
    "problem, not a splitter problem, and the fix for it is more fragments.",
    "Pooling all five folds is the mitigation and is what this report does: every cluster is a "
    "test cluster in exactly one fold, so a sub-class's aggregate test set is its whole library.",
)

#: The next ticket, named rather than gestured at. It is cheap in code and
#: expensive in careful thought, and it is the one that decides whether anything
#: in this report is evidence about real patient text.
NEXT_TICKET = (
    "**Write more held-out submissions, and write the ones that are missing.** The 67 in "
    "`data/realistic/` exist and are scored above, which closes the previous next-ticket: "
    "everything else in this report is a recombination of the same few hundred fragments the "
    "models were trained on, and held-out *clusters* remove memorisation and nothing else -- the "
    "test examples are still short, still one supervised claim plus filler, still assembled by "
    "the same generator in the same register.",
    "The shortage in the held-out set is **specific rather than general**, and writing another 67 "
    "of the same shape would not fix it. What is missing is **explicit denials** -- "
    '"no burning", '
    '"I\'m not going more often than usual", "no waking at night" -- and submissions where the '
    "patient turns out not to have a UTI at all. Three signals have no `false` example anywhere "
    "in the set, so a model that never predicts `false` is not penalised on them, and explicit "
    "denial was the largest error family in the synthetic evaluation.",
    "**Multi-symptom recombinations** (`arch_training.md` 12.5 and 12.6) are the other half. A "
    "generated example carries a label for one signal and no other, so every `null` example for a "
    "signal pairs an absence of that signal's language with *bland non-clinical* filler -- and "
    "real submissions are dense with clinical language about other symptoms. If "
    '"clinical-sounding text implies not-null" is a shortcut the models have taken, the holdout '
    "numbers above are where it shows, and joint multi-head training does not fix it because each "
    "head is masked on the other signals' examples.",
)


def build_report(
    runs: Sequence[ModelRun],
    *,
    header: Mapping[str, object],
    boot: BootstrapConfig = BootstrapConfig(),
    checks: Mapping[str, object] | None = None,
    fragments: Sequence | None = None,
    companions: Mapping[str, object] | None = None,
) -> dict:
    """Assemble the whole report as one JSON-serialisable dict.

    ``fragments`` is the run's :class:`~.dataset.FragmentInfo` provenance, from
    the sidecars the folds were loaded with. Optional so that a caller with only
    predictions still gets a report; omitting it costs the cluster-tag coverage
    block and the warning that goes with it, and nothing else.
    """
    models = [_model_block(run, boot=boot) for run in runs]
    coverage = cluster_tag_coverage(
        fragments or (), signal=header.get("signal") if fragments else None
    )
    comparisons, skipped = compare_models(runs)
    signal = header.get("signal")
    real_comparisons, real_skipped = holdout_comparisons(
        runs, signal=str(signal) if signal else None
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        # The full coverage block lives at the top level with every other
        # structured block; the header carries the one-line version of it,
        # because `_render_header` renders each header value as a single table
        # cell and a list of dicts there would be unreadable in exactly the
        # place a reader looks first.
        "header": {**header, "cluster_tag_coverage": _coverage_summary(coverage)},
        "cluster_tag_coverage": coverage,
        "bootstrap": boot.to_dict(),
        "checks": dict(checks or {}),
        "models": models,
        "comparisons": comparisons,
        # Never merged into `comparisons`, and never dropped: "could not be
        # tested" and "tested and found nothing" are different statements and a
        # reader must not be able to mistake one for the other.
        "skipped_comparisons": skipped,
        # The synthetic comparisons above and these are not two views of one
        # thing. `comparisons` pairs on the recombinations, which two arms
        # generated at different companion shares do not share; these pair on
        # the 67 real submissions, which every arm scores identically.
        "holdout_comparisons": real_comparisons,
        "skipped_holdout_comparisons": real_skipped,
        # What generated the data behind each arm in this report. Empty unless
        # the caller passed it, which is every command whose report holds one
        # dataset and therefore has nothing to distinguish.
        "companions": dict(companions or {}),
        "model_movement": model_movement(models),
        "expectations": list(EXPECTATIONS),
        "limitations": list(LIMITATIONS),
        "data_limits": list(DATA_LIMITS),
        "effective_sample_size": list(EFFECTIVE_SAMPLE_SIZE),
        "library_clusters": [
            {"library": name, "fragments": fragments, "clusters": clusters}
            for name, fragments, clusters in FEVER_LIBRARY_CLUSTERS
        ],
        "next_ticket": list(NEXT_TICKET),
    }


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------

DASH = "--"


def _pct(value: float | None, digits: int = 1) -> str:
    return DASH if value is None else f"{100 * value:.{digits}f}%"


def _ci(entry: Mapping[str, object] | None) -> str:
    """Render a statistic as ``point [low, high]``, or just the point."""
    if entry is None:
        return DASH
    point = _pct(entry.get("point"))
    low, high = entry.get("low"), entry.get("high")
    if low is None or high is None:
        return point
    return f"{point} [{_pct(low)}, {_pct(high)}]"


def _table(headers: Sequence[str], rows: Sequence[Sequence[str]]) -> list[str]:
    lines = [
        "| " + " | ".join(headers) + " |",
        "|" + "|".join("---" for _ in headers) + "|",
    ]
    lines.extend("| " + " | ".join(str(cell) for cell in row) + " |" for row in rows)
    lines.append("")
    return lines


def _confusion_lines(matrix: Sequence[Sequence[int]], caption: str) -> list[str]:
    rows = []
    for index, name in enumerate(CLASS_NAMES):
        total = sum(matrix[index])
        rows.append([f"**truth {name}**", *(str(cell) for cell in matrix[index]), str(total)])
    predicted_totals = [
        sum(matrix[row][column] for row in range(len(CLASS_NAMES)))
        for column in range(len(CLASS_NAMES))
    ]
    rows.append(
        ["**total**", *(str(total) for total in predicted_totals), str(sum(predicted_totals))]
    )
    return [f"*{caption}*", ""] + _table(
        ["", *(f"pred {name}" for name in CLASS_NAMES), "total"], rows
    )


def _slice_rows(entries: Sequence[Mapping[str, object]], statistic: str) -> list[list[str]]:
    return [
        [
            str(entry["name"]),
            str(entry["n_examples"]),
            f"**{entry['effective_n']}**",
            _ci(entry.get(statistic)),
        ]
        for entry in entries
    ]


#: How long a header value may be before it is printed as prose under the table
#: instead of inside a cell. A markdown table cell does not wrap, and a header
#: entry that is a paragraph -- what a run's arms hold fixed, what no arm
#: isolates, what was predicted before looking -- is exactly the entry a reader
#: most needs to be able to read.
HEADER_CELL_LIMIT = 120


def _header_prose(key: str, value: object) -> list[str]:
    """One over-long header value, as prose: a paragraph, or a bulleted list.

    A mapping is bulleted by name rather than passed to ``str``, which would
    print a Python dict repr -- quotes, braces and all -- into the part of the
    report a reader looks at first.
    """
    lines = [f"**{key.replace('_', ' ')}**", ""]
    if isinstance(value, Mapping):
        lines.extend(f"* **{name}**: {entry}" for name, entry in value.items())
    elif isinstance(value, (list, tuple)):
        lines.extend(f"* {item}" for item in value)
    else:
        lines.append(str(value))
    lines.append("")
    return lines


def _render_header(report: Mapping[str, object]) -> list[str]:
    header = report["header"]
    lines = ["# Encoder training: evaluation report", ""]
    lines.append(f"*Generated {report['generated_at']}.*")
    lines.append("")
    rows = []
    prose: list[tuple[str, object]] = []
    for key, value in header.items():
        if isinstance(value, Mapping):
            rendered = ", ".join(f"{name} {count}" for name, count in value.items())
        elif isinstance(value, (list, tuple)):
            rendered = ", ".join(str(item) for item in value)
        else:
            rendered = str(value)
        if len(rendered) > HEADER_CELL_LIMIT:
            prose.append((key, value))
            continue
        rows.append([key.replace("_", " "), f"`{rendered}`"])
    boot = report["bootstrap"]
    rows.append(
        [
            "bootstrap",
            f"`{boot['resamples']} resamples over clusters, alpha={boot['alpha']}, "
            f"seed={boot['seed']}`",
        ]
    )
    lines.extend(_table(["", ""], rows))
    for key, value in prose:
        lines.extend(_header_prose(key, value))
    return lines


def _render_how_to_read() -> list[str]:
    return [
        "## How to read these numbers",
        "",
        "Every table below prints **two** counts: `n`, the number of examples in the slice, and",
        "`eff n`, the number of distinct fragment **clusters** behind them. The examples are",
        "recombinations of a few hundred hand-written sentence fragments, and fragments tagged as",
        "the same idea are grouped into one cluster. `eff n` is the number of independent ideas",
        "the slice tested; `n` is how many times they were reshuffled.",
        "",
        "**`eff n` is the sample size.** Every confidence interval here is a bootstrap that",
        "resamples clusters, not examples. Resampling examples would measure the noise of the",
        "recombination process rather than the noise that matters, and would report intervals",
        "roughly `sqrt(n / eff n)` too narrow -- a factor of ten or more on these slices.",
        "",
        "A slice with a large `n` and a small `eff n` is not a large sample. Ten thousand examples",
        "built from sixty-six fragments is sixty-six ideas seen many times, and no amount of",
        "further generation changes that. Where `eff n` is small, the interval is wide, and the",
        "honest reading is that the slice cannot separate two models.",
        "",
        "Two confusion matrices are printed for each model: **raw argmax**, and the same scores",
        'under the fold\'s selected decision rule. They are separate because "the model is wrong"',
        'and "the rule is conservative" are different findings. The rule maximises macro-F1',
        "subject to a `null -> true` rate no worse than argmax's -- `null -> true` being the cell",
        "that invents a symptom into a patient's pre-filled form, which is a constraint rather",
        "than something to trade against F1.",
        "",
    ]


def _render_cluster_tag_coverage(report: Mapping[str, object]) -> list[str]:
    """The coverage table, and the warning it exists to carry.

    Sits immediately above the headline because it is a statement about how wide
    every interval in that table should have been, and a caveat printed after the
    number it qualifies is a caveat nobody reads.

    Omitted entirely when no library is behind the run -- a report built without
    fragment provenance -- rather than printed empty, on the same principle as
    :func:`_render_model_movement`: a heading with nothing under it invites a
    reader to conclude the check ran and found nothing.
    """
    coverage = report.get("cluster_tag_coverage") or {}
    libraries = coverage.get("libraries") or []
    if not libraries:
        return []

    lines = ["## Cluster-tag coverage, and what it does to the intervals below", ""]
    untagged = coverage.get("untagged_libraries") or []
    if untagged:
        total = len(libraries)
        if len(untagged) == 1:
            subject = "1 library"
        elif len(untagged) == total:
            subject = f"all {total} libraries"
        else:
            subject = f"{len(untagged)} of the {total} libraries"
        verb = "carries" if len(untagged) == 1 else "carry"
        them = "it" if len(untagged) == 1 else "them"
        lines.append(
            f"> **Warning: {subject} behind this run {verb} no cluster markers at "
            f"all, so every line in {them} counts as an independent idea.** Where that is not "
            "true -- where several lines are one idea written several ways -- the `eff n` of "
            "every slice drawn from those libraries is an **upper bound**, and the confidence "
            "intervals below are correspondingly **narrower than the truth**."
        )
        lines.append(">")
        lines.append("> Untagged: " + ", ".join(f"`{name}`" for name in untagged) + ".")
        lines.append("")

    lines.append(
        "Tagging cannot inflate a number -- `[c01]` siblings are forced into one cluster and one"
    )
    lines.append(
        "split, so it only ever *reduces* `eff n`, correctly, by stopping the same idea being"
    )
    lines.append(
        "counted twice. The asymmetry is what makes cross-signal comparison unsafe: a fully"
    )
    lines.append(
        "tagged signal is penalised for being honest and an untagged one is flattered by default,"
    )
    lines.append("so a ranking across signals is partly an artefact of this column.")
    lines.append("")
    lines.extend(
        _table(
            ["library", "fragments", "tagged", "coverage"],
            [
                [
                    f"`{row['library']}`",
                    str(row["fragments"]),
                    str(row["tagged"]),
                    _pct(row["coverage"]),
                ]
                for row in libraries
            ],
        )
    )
    return lines


def _render_headline(report: Mapping[str, object]) -> list[str]:
    lines = ["## Headline: fold-aggregated", ""]
    lines.append(
        "Pooled over every fold, so each fragment cluster is a test cluster exactly once and the"
    )
    lines.append(
        "aggregate test set is the whole library. Intervals are the cluster bootstrap; the "
        "across-fold"
    )
    lines.append("spread beside them is a stability check with four degrees of freedom, not a CI.")
    lines.append("")
    lines.append(
        "**Read the `decisive` column, not `overall`.** Structural nulls -- filler recombined "
        "with no"
    )
    lines.append(
        'decisive fragment at all -- carry the single idea "no signal language anywhere", so '
        "they share"
    )
    lines.append(
        "one resampling unit. That is the correct treatment and it makes the overall interval "
        "nearly"
    )
    lines.append(
        "unreadable: one unit holding a third of the examples lands in a resample zero to three "
        "times,"
    )
    lines.append(
        "swinging overall accuracy by twenty points on nothing. `decisive` drops them and is the "
        "slice"
    )
    lines.append("with a real sample behind it.")
    lines.append("")

    rows = []
    for model in report["models"]:
        overall = model["pooled"]["ruled"]["overall"]
        decisive = model["pooled"]["ruled"]["decisive"]
        spread = model["fold_spread"]
        rows.append(
            [
                f"`{model['name']}`",
                model["kind"].replace("_", " "),
                str(decisive["n_examples"]),
                f"**{decisive['effective_n']}**",
                _ci(decisive["accuracy"]),
                _ci(decisive["macro_f1"]),
                _pct(overall["accuracy"]["point"]),
                _pct(spread["accuracy"]["mean"]) + " +/- " + _pct(spread["accuracy"]["sd"]),
            ]
        )
    lines.extend(
        _table(
            [
                "model",
                "kind",
                "decisive n",
                "eff n",
                "decisive accuracy [95% CI]",
                "decisive macro-F1 [95% CI]",
                "overall acc",
                "per-fold overall mean +/- sd",
            ],
            rows,
        )
    )

    lines.append("### Null sub-class recall, pooled")
    lines.append("")
    lines.append(
        "The table the whole exercise exists for: how often each hard `null` sub-class is correctly"
    )
    lines.append(
        "left as `null`. `eff n` here is the sub-class's entire library, which a single split "
        "cannot reach."
    )
    lines.append("")
    lines.append(
        "**Never read this table on its own.** Every example in these slices is truly `null`, so "
        "a model"
    )
    lines.append(
        "that always answers `null` scores 100% across the row -- as `majority_class` below "
        "does. High"
    )
    lines.append(
        "null recall is only a finding when the `true` and `false` recalls in the per-class "
        "tables are"
    )
    lines.append("high too.")
    lines.append("")
    # The named sub-classes only. Everything the manifest gives no sub-class to
    # -- structural nulls, and every declarative fragment (DD3: nothing a fixed
    # frame generates is a hard case) -- groups under ``None`` and is not a
    # column here. That slice grows with --declarative-share while this table
    # stays the same width, so a reader comparing arms should read it against
    # the per-class tables above rather than as a share of the dataset.
    subclass_names = list(NULL_SUBCLASSES)
    rows = []
    for model in report["models"]:
        by_subclass = {entry["name"]: entry for entry in model["pooled"]["ruled"]["by_subclass"]}
        row = [f"`{model['name']}`"]
        for name in subclass_names:
            entry = by_subclass.get(name)
            if entry is None:
                row.append(DASH)
            else:
                row.append(f"{_ci(entry['null_recall'])} (eff n {entry['effective_n']})")
        rows.append(row)
    lines.extend(_table(["model", *subclass_names], rows))
    return lines


def _sentence(text: str) -> str:
    """Capitalise the first letter and end the sentence, leaving the rest alone.

    ``str.capitalize`` would lowercase everything after it, which turns
    "README rule 2" into "readme rule 2" in the one place a reader is being
    pointed at a file to go and read.
    """
    return text[:1].upper() + text[1:] + "."


def _spread_cell(spread: Mapping[str, object]) -> str:
    """``mean +/- sd`` across folds, or just the mean where there is one fold."""
    mean = spread.get("mean")
    if mean is None:
        return DASH
    sd = spread.get("sd")
    if sd is None:
        return _pct(mean)
    return f"{_pct(mean)} +/- {_pct(sd)}"


def _render_null_to_true_headline(scored: Sequence[Mapping[str, object]]) -> list[str]:
    """`null -> true` on real text, per signal and per model, first.

    Promoted above the accuracy tables deliberately. Overall real-text accuracy
    is dominated by the `null` cells, which a model scores by saying nothing;
    this cell is the one that invents a symptom into a patient's pre-filled
    form, and on the 2026-08-17 joint run it sat between 47% and 89% while the
    accuracy beside it looked survivable.
    """
    signals = [entry["signal"] for entry in scored[0]["holdout"]["by_signal"]]
    if not signals:
        return []
    rows = []
    for signal in signals:
        cells = [f"`{signal}`"]
        support = None
        for model in scored:
            entry = next(item for item in model["holdout"]["by_signal"] if item["signal"] == signal)
            support = entry["null_to_true"]["null_support"]
            cells.append(_pct(entry["null_to_true"]["mean_rate"]))
        rows.append([cells[0], str(support), *cells[1:]])
    return [
        "### `null -> true` on real text -- the headline",
        "",
        "How often each model answers `true` about a signal the submission never mentioned, as",
        "the mean across folds of that fold's own rate. Every other number in this section is",
        "read against this one: a model can post a respectable overall figure here purely by",
        "answering `null` everywhere, and it can post a respectable *decisive* figure while still",
        "inventing symptoms into most of the submissions that never raised them.",
        "",
        *_table(
            ["signal", "null support", *(f"`{model['name']}`" for model in scored)],
            rows,
        ),
    ]


def _render_holdout_comparisons(report: Mapping[str, object]) -> list[str]:
    """The paired real-text tests, and the ones that could not be run."""
    comparisons = report.get("holdout_comparisons") or []
    skipped = report.get("skipped_holdout_comparisons") or []
    if not comparisons and not skipped:
        return []

    lines = [
        "## Paired on real text",
        "",
        "The 67 submissions are the same 67 for every model here, so unlike the recombination",
        "test slice they can be paired: the informative quantity is the submissions two models",
        "disagree about, not the gap between two means. One test per fold, never pooled.",
        "",
    ]
    for entry in comparisons:
        lines.append(f"### `{entry['left']}` against `{entry['right']}`")
        lines.append("")
        lines.extend(
            _table(
                ["fold", "pairs", f"only `{entry['left']}`", f"only `{entry['right']}`", "p"],
                [
                    [
                        str(row["fold"]),
                        str(row["n_pairs"]),
                        str(row["left_only_correct"]),
                        str(row["right_only_correct"]),
                        f"{row['p_value']:.3g}",
                    ]
                    for row in entry["folds"]
                ],
            )
        )
        rate = entry["null_to_true"]
        delta = rate["delta_points"]
        lines.append(
            f"`{entry['left']}` ahead on {entry['left_better_folds']} folds, "
            f"`{entry['right']}` on {entry['right_better_folds']}. "
            f"`null -> true` mean: {_pct(rate['left_mean'])} against {_pct(rate['right_mean'])}"
            + (
                "."
                if delta is None
                else f" -- **{delta:+.1f} points** in favour of `{entry['right']}`."
            )
        )
        lines.append("")
        lines.append(f"*{_sentence(entry['not_pooled'])}*")
        lines.append("")
    for entry in skipped:
        lines.append(
            f"* `{entry['left']}` against `{entry['right']}`: not paired -- {entry['reason']}."
        )
    if skipped:
        lines.append("")
    return lines


def _render_companions(report: Mapping[str, object]) -> list[str]:
    """What generated each arm's data, when the report holds more than one arm."""
    companions = report.get("companions") or {}
    arms = companions.get("arms") or []
    if not arms:
        return []
    lines = [
        "## The datasets behind these arms",
        "",
        f"{companions.get('note', '')}".strip(),
        "",
        *_table(
            [
                "arm",
                "tree",
                "companion share",
                "examples/fold (train)",
                "filler-only kept",
                "companions/example",
                "worst spread by label mode",
            ],
            [
                [
                    f"`{arm['label']}`",
                    f"`{arm['dataset_dir']}`",
                    str(arm["companion_share"]),
                    str(arm.get("train_examples", DASH)),
                    str(arm.get("filler_only_kept", DASH)),
                    DASH
                    if arm.get("companions_per_example") is None
                    else f"{arm['companions_per_example']:.3f}",
                    DASH
                    if arm.get("worst_label_mode_spread") is None
                    else f"{arm['worst_label_mode_spread']:.4f}",
                ]
                for arm in arms
            ],
        ),
        "**The last column is the leak detector, not a curiosity.** It is the largest gap between",
        "any two label modes in mean companions per example, across every training split of that",
        "arm. Companion count is drawn blind to the label mode by construction; if these rows ever",
        "disagreed, companion count would have become a proxy for the label, pointing the wrong",
        "way -- more clinical text implying more likely `null` -- and the arm would be void rather",
        "than reinterpretable.",
        "",
    ]
    return lines


def _render_holdout(report: Mapping[str, object]) -> list[str]:
    """The only numbers in this report that speak to real patient text.

    Placed immediately below the headline rather than in an appendix, because
    the question it answers -- is any of the above evidence about real
    submissions at all -- comes before every question the tables above it
    settle. Omitted entirely when no model scored it, rather than printed
    empty: a heading with nothing under it invites a reader to conclude the
    check ran and found nothing.
    """
    scored = [model for model in report["models"] if model.get("holdout")]
    if not scored:
        return []

    first = scored[0]["holdout"]
    lines = [
        "## The real-text holdout",
        "",
        f"Scored against `{first['path']}` -- {first['n_submissions']} free-text submissions",
        "written to read like real patients, labelled once and used to select nothing. **Every",
        "other number in this report is a recombination of the same fragment libraries the models",
        "were trained on.** This section is the only measurement here that speaks to real patient",
        "text, and it is a validity check rather than a comparison.",
        "",
        f"> {first['power']}",
        "",
        f"> {first['provenance']}",
        "",
        f"> {first['voice']}",
        "",
        f"*{_sentence(first['selected_nothing'])}*",
        "",
        f"*{_sentence(first['not_pooled'])}*",
        "",
        '**Read the `decisive` columns.** A `null` cell is one a model scores by answering "no',
        'information", which the majority-class baseline does perfectly; the decisive cells are',
        "the ones where the patient said something the model has to read. Where a signal has no",
        "`false` examples at all, its decisive figure is very nearly recall on `true` and nothing",
        "here tests whether an explicit denial is read correctly.",
        "",
    ]
    if first["signals_not_scored"]:
        lines.append(
            "Not scored, because no head exists for them: "
            + ", ".join(f"`{signal}`" for signal in first["signals_not_scored"])
            + "."
        )
        lines.append("")

    lines.extend(_render_null_to_true_headline(scored))

    for model in scored:
        holdout = model["holdout"]
        synthetic = model["pooled"]["ruled"]["decisive"]
        lines.append(f"### `{model['name']}`")
        lines.append("")
        lines.append(
            f"Recombination test slice: **n {synthetic['n_examples']}**, "
            f"**eff n {synthetic['effective_n']}** clusters, accuracy "
            f"{_ci(synthetic['accuracy'])}. Holdout: **n {holdout['n_submissions']}** "
            f"submissions, one observation each, scored by "
            f"{holdout['n_folds']} fold models at margins "
            f"{', '.join(str(margin) for margin in holdout['margins'])}. "
            "The two `n`s are printed together because they are not the same kind of number and "
            "the second is far the smaller."
        )
        lines.append("")
        rows = []
        for entry in holdout["by_signal"]:
            distribution = entry["distribution"]
            decisive = entry["decisive"]
            everything = entry["all"]
            rows.append(
                [
                    f"`{entry['signal']}`",
                    f"{distribution['true']}/{distribution['false']}/{distribution['null']}",
                    str(distribution["omitted"]),
                    str(decisive["n_cells"]),
                    _spread_cell(decisive["accuracy"]),
                    "+/-" + _pct(decisive["worst_case_half_width"]),
                    str(everything["n_cells"]),
                    _spread_cell(everything["accuracy"]),
                    _spread_cell(entry["per_class_recall"]["null"]),
                ]
            )
        lines.extend(
            _table(
                [
                    "signal",
                    "true/false/null",
                    "omitted",
                    "decisive n",
                    "decisive acc (mean +/- sd)",
                    "worst-case half-width",
                    "all n",
                    "all acc (mean +/- sd)",
                    "null recall",
                ],
                rows,
            )
        )
        caveats = [entry for entry in holdout["by_signal"] if entry.get("caveat")]
        for entry in caveats:
            lines.append(f"* `{entry['signal']}`: {entry['caveat']}.")
        if caveats:
            lines.append("")
        lines.append(
            "`null -> true` on real text, per fold: "
            + "; ".join(
                f"`{entry['signal']}` "
                + ", ".join(str(count) for count in entry["null_to_true"]["counts"])
                + f" of {entry['null_to_true']['null_support']}"
                for entry in holdout["by_signal"]
            )
            + ". This is the cell that invents a symptom into a patient's pre-filled form, "
            "counted here on submissions rather than on recombinations."
        )
        lines.append("")
    return lines


#: The slice the ticket is decided on. Clear positives, clear negatives and
#: `null_structural` are the easy three-quarters of the data and every model
#: here is expected to handle them; a transformer can only earn its keep on the
#: fragments that carry fever language and still mean `null`.
DECIDING_SLICE = "null_ambiguous"


def _concentration_sentence(model: Mapping[str, object]) -> str:
    """One model's error concentration, in a sentence with its reference point."""
    stats = model["error_concentration"]
    if not stats["total_errors"]:
        return f"`{model['name']}`: no errors on any decisive fragment."
    even = stats["even_spread_would_be"]
    return (
        f"`{model['name']}`: {stats['total_errors']} errors across "
        f"{stats['fragments_with_errors']} of {stats['decisive_fragments']} decisive fragments. "
        f"Half of them fall on **{stats['fragments_carrying_half']}** fragments "
        f"(an even spread would be {even:.1f}); the worst ten carry "
        f"{_pct(stats['share_in_worst_ten'])} of all errors."
    )


def _render_ticket_question(report: Mapping[str, object]) -> list[str]:
    """The section the ticket exists for, assembled from three numbers.

    Deliberately stops short of stating a conclusion. The three numbers below
    constrain it but do not determine it, and a report that concluded
    automatically would be concluding from whichever comparison happened to
    clear a threshold someone picked while writing the renderer.
    """
    models = [model for model in report["models"] if model["kind"] != "negative_control"]
    lines = [
        "## The ticket's question: model or libraries?",
        "",
        "This ticket exists to answer one question -- **is the bottleneck the model or the",
        "fragment libraries?** -- and three numbers decide it. All three are on this page.",
        "",
        f"### 1. Accuracy on `{DECIDING_SLICE}`",
        "",
        "The only slice where a transformer can earn its keep. Clear positives, clear negatives",
        "and `null_structural` are the easy three-quarters of the data; bag-of-words handles them,",
        "so an overall accuracy is close to uninformative here.",
        "",
        "**This table cannot be read on its own, and the first row is why.** Every example in this",
        "slice is truly `null`, so a model that answers `null` unconditionally scores 100% across",
        "it -- which is exactly what `majority_class` does, and it has learned nothing. A number",
        "here is a finding only when the `true` and `false` recalls in the same model's per-class",
        "table are high at the same time. The same caveat applies to every McNemar row below it.",
        "",
    ]
    rows = []
    for model in models:
        entry = next(
            (
                entry
                for entry in model["pooled"]["ruled"]["by_label_mode"]
                if entry["name"] == DECIDING_SLICE
            ),
            None,
        )
        if entry is None:
            continue
        rows.append(
            [
                f"`{model['name']}`",
                model["kind"].replace("_", " "),
                str(entry["n_examples"]),
                f"**{entry['effective_n']}**",
                _ci(entry["accuracy"]),
            ]
        )
    lines.extend(_table(["model", "kind", "n", "eff n", "accuracy [95% CI]"], rows))

    lines.append("### 2. The same comparison, paired")
    lines.append("")
    lines.append(
        "Two overlapping intervals do not settle whether one model beats another on the same"
    )
    lines.append(
        "examples. McNemar does, over the examples the two disagree about -- read it alongside the"
    )
    lines.append("intervals above, never instead of them.")
    lines.append("")
    deciding = [
        comparison for comparison in report["comparisons"] if comparison["slice"] == DECIDING_SLICE
    ]
    if deciding:
        rows = [
            [
                f"`{comparison['a']}` vs `{comparison['b']}`",
                str(comparison["n_pairs"]),
                str(comparison["a_only_correct"]),
                str(comparison["b_only_correct"]),
                f"{comparison['p_value']:.3g}",
            ]
            for comparison in deciding
        ]
        lines.extend(_table(["pair", "n", "a only", "b only", "p"], rows))
    else:
        lines.append(f"No pair of non-control models carries a `{DECIDING_SLICE}` slice.")
        lines.append("")

    # Named here as well as under the comparison table, because this is the
    # section a reader comes to for the answer: a missing row on the deciding
    # slice is exactly the one most likely to be read as "no difference".
    unpairable = [
        entry
        for entry in (report.get("skipped_comparisons") or [])
        if entry["slice"] == DECIDING_SLICE
    ]
    if unpairable:
        lines.append(
            "Not on this table, because they cannot be paired at all -- different examples on the "
            "two sides, so there is nothing for McNemar to pair: "
            + "; ".join(f"`{entry['a']}` vs `{entry['b']}`" for entry in unpairable)
            + ". Read those through the intervals above and the per-fold spread, and see "
            '"Pairs that could not be tested" below.'
        )
        lines.append("")

    lines.append("### 3. Where the errors fall")
    lines.append("")
    lines.append(
        "The per-fragment table below, as one number per model. Errors spread thinly across many"
    )
    lines.append(
        "fragments say the method is too weak. Errors piled onto a handful say those specific ideas"
    )
    lines.append(
        "are not learnable from the data we have -- and the table names them, which is what makes"
    )
    lines.append("this the most decision-useful thing in the report.")
    lines.append("")
    lines.extend(f"* {_concentration_sentence(model)}" for model in models)
    lines.append("")

    lines.append("### Reading the three together")
    lines.append("")
    lines.append(
        "* Fine-tune clear of the frozen probe **and** clear of TF-IDF on the slice above: the"
    )
    lines.append(
        "  frozen pooled representation was the bottleneck, and the next month is model work."
    )
    lines.append(
        "* Fine-tune no better than the frozen probe, with errors concentrated on a handful of"
    )
    lines.append(
        "  named fragments: those ideas are not learnable from the data we have, and the next"
    )
    lines.append("  month is library work on the fragments the table names.")
    lines.append(
        "* Both arms poor with errors spread evenly across most fragments: neither reading is"
    )
    lines.append(
        "  supported yet, and the honest answer is that the slice cannot separate them -- check"
    )
    lines.append("  `eff n` before concluding anything at all.")
    lines.append("")
    lines.append(
        "**The conclusion is a sentence a person writes after reading those three, in the ticket's"
    )
    lines.append(
        "own terms.** This report does not write it. The numbers constrain the conclusion; they do"
    )
    lines.append("not determine it.")
    lines.append("")
    return lines


def _render_model(model: Mapping[str, object], *, fragment_rows: int) -> list[str]:
    lines = [f"## `{model['name']}`", "", model["description"], ""]

    margins = sorted({entry["margin"] for entry in model["margins"]})
    lines.append(
        f"Decision-rule margins selected per fold (on each fold's own validation split): "
        f"{', '.join(str(margin) for margin in margins)}."
    )
    if model["rule_is_argmax"]:
        lines.append(
            "Every fold selected margin 0, so the ruled and raw views below are the same "
            "decisions. That is a finding rather than a bug: no margin improved macro-F1 without "
            "worsening the `null -> true` rate."
        )
    lines.append("")

    for view_name, caption in (("raw", "raw argmax"), ("ruled", "after the decision rule")):
        view = model["pooled"][view_name]
        lines.extend(_confusion_lines(view["overall"]["confusion"], f"Confusion matrix, {caption}"))
        rate = view["null_to_true"]
        lines.append(
            f"`null -> true`: {rate['count']} of {rate['null_support']} truly-null examples "
            f"({_pct(rate['rate'], 2)})."
        )
        lines.append("")

    lines.append("### Per class, after the decision rule")
    lines.append("")
    rows = [
        [
            f"`{name}`",
            str(metrics["support"]),
            str(metrics["predicted"]),
            _pct(metrics["precision"]),
            _pct(metrics["recall"]),
            _pct(metrics["f1"]),
        ]
        for name, metrics in model["pooled"]["ruled"]["per_class"].items()
    ]
    lines.extend(_table(["class", "support", "predicted", "precision", "recall", "F1"], rows))

    lines.append("### By label mode")
    lines.append("")
    lines.extend(
        _table(
            ["label mode", "n", "eff n", "accuracy [95% CI]"],
            _slice_rows(model["pooled"]["ruled"]["by_label_mode"], "accuracy"),
        )
    )

    lines.append("### By null sub-class")
    lines.append("")
    lines.extend(
        _table(
            ["sub-class", "n", "eff n", "null recall [95% CI]"],
            _slice_rows(model["pooled"]["ruled"]["by_subclass"], "null_recall"),
        )
    )

    lines.append("### By fragment library")
    lines.append("")
    lines.extend(
        _table(
            ["library", "n", "eff n", "accuracy [95% CI]"],
            _slice_rows(model["pooled"]["ruled"]["by_library"], "accuracy"),
        )
    )

    lines.extend(_render_fragments(model, fragment_rows=fragment_rows))
    return lines


def _render_fragments(model: Mapping[str, object], *, fragment_rows: int) -> list[str]:
    fragments = model["fragments"]
    lines = ["### Per-fragment errors (worst first)", ""]
    lines.append(
        "Whether errors are spread thinly across many fragments or piled onto a few is the "
        "difference"
    )
    lines.append(
        'between "the method is too weak" (model work) and "these specific ideas are not '
        "learnable from"
    )
    lines.append(
        'the data we have" (library work, and these are the fragments to write more of). No '
        "intervals:"
    )
    lines.append(
        "a fragment is one cluster, so an interval over its own examples measures nothing."
    )
    lines.append("")

    wrong = [row for row in fragments if row["n_correct"] < row["n_examples"]]
    lines.append(
        f"{len(wrong)} of {len(fragments)} decisive fragments were got wrong at least once."
    )
    lines.append("")
    lines.append(_concentration_sentence(model))
    lines.append("")
    shown = wrong[:fragment_rows]
    rows = [
        [
            f"`{row['fragment_id']}`",
            f"`{row['library']}`",
            row["subclass"] or DASH,
            row["truth"],
            f"{row['n_correct']}/{row['n_examples']}",
            _pct(row["accuracy"]),
            ", ".join(f"{name} {count}" for name, count in row["predicted"].items() if count),
        ]
        for row in shown
    ]
    lines.extend(
        _table(
            ["fragment", "library", "sub-class", "truth", "correct", "accuracy", "predicted as"],
            rows,
        )
    )
    if len(wrong) > len(shown):
        lines.append(
            f"*{len(wrong) - len(shown)} further fragments with at least one error are in the "
            "JSON sidecar; every fragment is there regardless of score.*"
        )
        lines.append("")
    return lines


def _render_skipped(report: Mapping[str, object]) -> list[str]:
    """The pairs that could not be paired, and why.

    Printed under the comparison table rather than omitted, because the failure
    mode this exists to prevent is silent: a reader who expected a comparison
    and does not find one reads its absence as "no difference found". "Not
    pairable" and "no difference" are opposite statements.
    """
    skipped = report.get("skipped_comparisons") or []
    if not skipped:
        return []
    lines = [
        "### Pairs that could not be tested",
        "",
        "McNemar pairs on the example id, so two models scored on **different examples** cannot be",
        "compared this way at all -- there is nothing to pair. That is a property of the datasets,",
        "not a result: read those runs through their pooled cluster intervals and their per-fold",
        "spread, and do not read the absence of a row above as agreement between them.",
        "",
    ]
    lines.extend(
        _table(
            ["pair", "slice", "n (a)", "n (b)", "shared", "reason"],
            [
                [
                    f"`{entry['a']}` vs `{entry['b']}`",
                    entry["slice"],
                    str(entry["n_a"]),
                    str(entry["n_b"]),
                    str(entry["n_common"]),
                    entry["reason"],
                ]
                for entry in skipped
            ],
        )
    )
    return lines


def _render_comparisons(report: Mapping[str, object]) -> list[str]:
    comparisons = report["comparisons"]
    lines = ["## Paired comparisons (McNemar, raw argmax)", ""]
    if not comparisons:
        lines.append("No pair of non-control models to compare.")
        lines.append("")
        lines.extend(_render_skipped(report))
        return lines
    lines.append(
        "Exact two-sided McNemar over the examples the two models disagree about. Pairing unit is "
        "the"
    )
    lines.append("example, not the cluster -- see the limitations.")
    lines.append("")
    rows = [
        [
            f"`{comparison['a']}` vs `{comparison['b']}`",
            comparison["slice"],
            str(comparison["n_pairs"]),
            str(comparison["a_only_correct"]),
            str(comparison["b_only_correct"]),
            f"{comparison['p_value']:.3g}",
        ]
        for comparison in comparisons
    ]
    lines.extend(_table(["pair", "slice", "n", "a only", "b only", "p"], rows))
    lines.extend(_render_skipped(report))
    return lines


def _render_checks(report: Mapping[str, object]) -> list[str]:
    checks = report["checks"]
    lines = ["## Negative controls and checks", ""]
    if not checks:
        lines.append("No checks recorded.")
        lines.append("")
        return lines
    for name, detail in checks.items():
        lines.append(f"* **{name.replace('_', ' ')}** -- {detail}")
    lines.append("")

    controls = [model for model in report["models"] if model["kind"] == "negative_control"]
    if controls:
        lines.append(
            "Shuffled-label controls, evaluated on the **unpermuted** test split. A large model "
            "will"
        )
        lines.append(
            "memorise permuted training labels and drive train loss to zero; that is correct "
            "behaviour"
        )
        lines.append("and says nothing. Only the test score is the control.")
        lines.append("")
        rows = [
            [
                f"`{model['name']}`",
                _ci(model["pooled"]["raw"]["overall"]["accuracy"]),
                _ci(model["pooled"]["raw"]["overall"]["macro_f1"]),
            ]
            for model in controls
        ]
        lines.extend(_table(["control", "accuracy [95% CI]", "macro-F1 [95% CI]"], rows))
    return lines


def _render_appendix(report: Mapping[str, object]) -> list[str]:
    lines = ["## Appendix: per-fold numbers", ""]
    lines.append(
        "Point estimates only. A single fold's test slice holds 2-5 clusters per hard sub-class, "
        "which"
    )
    lines.append("is the whole reason the headline is pooled.")
    lines.append("")
    for model in report["models"]:
        lines.append(f"### `{model['name']}`")
        lines.append("")
        rows = [
            [
                str(entry["fold"]),
                str(entry["n_train"]),
                str(entry["n_val"]),
                str(entry["n_test"]),
                str(entry["margin"]),
                _pct(entry["raw"]["accuracy"]),
                _pct(entry["ruled"]["accuracy"]),
                _pct(entry["ruled"]["macro_f1"]),
                _pct(entry["ruled"]["null_to_true_rate"], 2),
            ]
            for entry in model["per_fold"]
        ]
        lines.extend(
            _table(
                [
                    "fold",
                    "train n",
                    "val n",
                    "test n",
                    "margin",
                    "acc (raw)",
                    "acc (ruled)",
                    "macro-F1",
                    "null->true",
                ],
                rows,
            )
        )
    return lines


def _render_expectations(report: Mapping[str, object]) -> list[str]:
    """What was predicted before the run, and the instruction to score it.

    The prediction is worth nothing unless someone goes back and says whether it
    held, so the demand to do that is printed next to it rather than left in the
    implementation plan.
    """
    lines = ["## What we expected before looking", ""]
    lines.append(
        "Recorded before any run, in this module, so the result can be scored against a prediction"
    )
    lines.append(
        "rather than rationalised after the fact. **Whoever writes this run up owes each bullet a"
    )
    lines.append(
        "verdict -- held, or did not hold, and by how much.** A plan that records a prediction and"
    )
    lines.append("never scores it has wasted the prediction.")
    lines.append("")
    lines.extend(f"* {bullet}" for bullet in report["expectations"])
    lines.append("")
    return lines


def _render_data_limits(report: Mapping[str, object]) -> list[str]:
    """`arch_training.md` sections 9 and 10, reproduced in full rather than cited.

    The one place in this package where duplication is deliberate. Everywhere
    else cross-references; here the report is read standalone, by someone who
    has not read the architecture docs, and every number above is bounded by
    what this section says.
    """
    lines = [
        "## What this data is and is not worth",
        "",
        "*Reproduced in full from `arch_training.md` sections 9 and 10 rather than cross-",
        "referenced, because this report is read on its own and every number in it is bounded by",
        "what follows.*",
        "",
    ]
    lines.extend(f"* {bullet}" for bullet in report["data_limits"])
    lines.append("")
    lines.append("### Effective sample size: count clusters, not examples")
    lines.append("")
    for paragraph in report["effective_sample_size"]:
        lines.append(paragraph)
        lines.append("")
    rows = [
        [
            f"`{entry['library']}`",
            str(entry["fragments"]),
            f"**{entry['clusters']}**",
        ]
        for entry in report["library_clusters"]
    ]
    lines.extend(_table(["library", "fragments", "clusters (the effective n)"], rows))
    lines.append(
        "Note what that is worth and no more. Effective n rises 12- to 17-fold for the hard"
    )
    lines.append(
        "sub-classes, but the error bar does **not** shrink 12- to 17-fold: uncertainty on a"
    )
    lines.append(
        "proportion goes as 1/sqrt(n), so roughly +/-30 points becomes roughly +/-8. That is the"
    )
    lines.append(
        "difference between a number that can carry a conclusion and one that cannot -- a metaphor"
    )
    lines.append(
        "recall of 0.6 +/-0.08 is a finding, 0.5 +/-0.30 is noise. Folds create no new ideas, so 47"
    )
    lines.append("metaphor clusters is still 47 and everything above applies unchanged.")
    lines.append("")
    return lines


def _render_model_movement(report: Mapping[str, object], *, fragment_rows: int) -> list[str]:
    """Where a model comparison actually gets decided.

    Omitted entirely from a single-model report rather than printed empty: a
    section headed "what moved" under one model is an invitation to read a column
    of absolute error counts as a comparison.
    """
    movement = report.get("model_movement") or {}
    libraries = movement.get("by_library") or []
    fragments = movement.get("by_fragment") or []
    if not libraries and not fragments:
        return []

    names = list(movement["models"])
    lines = [
        "## What moved, and where",
        "",
        "The headline is the least useful output of a model comparison. These two tables are the",
        "useful one: a diffuse lift and a fix to one error family are different findings, and an",
        "aggregate accuracy cannot tell them apart. `spread` is max minus min across the models --",
        "a row where every encoder lands together is a row model choice does not touch.",
        "",
        "### By library, accuracy after the decision rule",
        "",
        "Worst-performing library first. For a single-class library -- `fever_false` holds only",
        "`false` examples -- accuracy here *is* that class's recall on that library.",
        "",
    ]
    lines.extend(
        _table(
            ["library", "n", *(f"`{name}`" for name in names), "spread"],
            [
                [
                    f"`{row['library']}`",
                    str(row["n_examples"]),
                    *(_pct(row["accuracy"][name]) for name in names),
                    f"{100 * row['spread']:.1f}pp",
                ]
                for row in libraries
            ],
        )
    )
    lines.append("### By fragment, errors")
    lines.append("")
    lines.append(
        "Ordered by the worst model's error count, so the fragments the comparison is about sort"
    )
    lines.append(
        "to the top whichever encoder wins. Counts, not rates: these are the sentences a month of"
    )
    lines.append("library work would be spent on. The JSON holds every fragment.")
    lines.append("")
    lines.extend(
        _table(
            ["fragment", "library", "truth", *(f"`{name}`" for name in names), "spread"],
            [
                [
                    f"`{row['fragment_id']}`",
                    f"`{row['library']}`",
                    str(row["truth"]),
                    *(str(row["errors"][name]) for name in names),
                    str(row["spread"]),
                ]
                for row in fragments[:fragment_rows]
            ],
        )
    )
    if len(fragments) > fragment_rows:
        lines.append(
            f"*{len(fragments) - fragment_rows} further fragments erred on at least one model; "
            "the JSON holds them all.*"
        )
        lines.append("")
    return lines


def _render_bullets(title: str, bullets: Sequence[str]) -> list[str]:
    lines = [f"## {title}", ""]
    lines.extend(f"* {bullet}" for bullet in bullets)
    lines.append("")
    return lines


def render_markdown(
    report: Mapping[str, object], *, fragment_rows: int = DEFAULT_FRAGMENT_ROWS
) -> str:
    """Render the report dict as markdown. Reads the dict and nothing else."""
    lines: list[str] = []
    lines.extend(_render_header(report))
    lines.extend(_render_how_to_read())
    lines.extend(_render_cluster_tag_coverage(report))
    lines.extend(_render_headline(report))
    lines.extend(_render_holdout(report))
    lines.extend(_render_holdout_comparisons(report))
    lines.extend(_render_companions(report))
    lines.extend(_render_ticket_question(report))
    lines.extend(_render_expectations(report))
    lines.extend(_render_checks(report))
    lines.extend(_render_comparisons(report))
    lines.extend(_render_model_movement(report, fragment_rows=fragment_rows))
    for model in report["models"]:
        lines.extend(_render_model(model, fragment_rows=fragment_rows))
    lines.extend(_render_appendix(report))
    lines.extend(_render_bullets("Limitations", report["limitations"]))
    lines.extend(_render_data_limits(report))
    lines.extend(_render_bullets("The next ticket", report["next_ticket"]))
    return "\n".join(lines).rstrip() + "\n"


def write_report(
    report: Mapping[str, object],
    directory: Path | str,
    *,
    stem: str,
    markdown: bool = True,
    fragment_rows: int = DEFAULT_FRAGMENT_ROWS,
) -> tuple[Path, Path | None]:
    """Write the JSON sidecar (always) and the markdown report (on request)."""
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    json_path = directory / f"{stem}.json"
    json_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    if not markdown:
        return json_path, None
    markdown_path = directory / f"{stem}.md"
    markdown_path.write_text(render_markdown(report, fragment_rows=fragment_rows), encoding="utf-8")
    return json_path, markdown_path

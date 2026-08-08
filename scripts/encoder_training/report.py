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

SCHEMA_VERSION = 1

#: Sub-classes the four hard `fever_null` libraries carry. Listed so that a
#: sub-class the manifest declares but no test fold happened to draw shows up as
#: an empty row rather than vanishing from the table.
NULL_SUBCLASSES = ("hedged", "historical", "metaphor", "third_party")

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


def compare_models(
    runs: Sequence[ModelRun], *, slices: Sequence[str] = ("overall", "null_ambiguous")
) -> list[dict]:
    """Paired McNemar tests between every pair of non-control models.

    Run on the **raw** argmax decisions. Comparing two models under two
    separately-tuned margins would confound a difference in the models with a
    difference in their rules, and the rule is the thing that is easiest to
    change afterwards.
    """
    comparable = [run for run in runs if not run.is_control]
    comparisons: list[dict] = []
    for index, left in enumerate(comparable):
        for right in comparable[index + 1 :]:
            for slice_name in slices:
                a = _restrict(left.pooled("raw"), slice_name)
                b = _restrict(right.pooled("raw"), slice_name)
                if not a or not b:
                    continue
                comparisons.append(_mcnemar_dict(left, right, slice_name, mcnemar(a, b)))
    return comparisons


def _model_block(run: ModelRun, *, boot: BootstrapConfig) -> dict:
    ruled = run.pooled("ruled")
    raw = run.pooled("raw")
    margins = {fold.rule.margin for fold in run.folds}
    rule_is_argmax = margins == {0.0}

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
        "fragments": _fragment_table(ruled),
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
    "**A slice containing only one class cannot be read on its own.** The four `null` sub-class "
    "slices hold nothing but truly-`null` examples, so a model that answers `null` unconditionally "
    "scores 100% on all of them. Sub-class recall is a finding only when the `true` and `false` "
    "recalls are high at the same time, which is why the per-class table sits beside it.",
    "**The overall interval is dominated by one resampling unit.** All structural nulls share "
    "one unit, by design -- thousands of recombinations of a handful of filler sentences are not "
    "thousands of observations. The cost is that the pooled overall accuracy swings widely under "
    "resampling for reasons that have nothing to do with the model. The `decisive` slice, which "
    "drops them, is the one to read.",
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
    "`null_structural`, and should do **badly** on the four hard `null` sub-classes. "
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
    "finding**. If unfreezing 110M parameters lifts the four hard `null` sub-classes clear of "
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


def build_report(
    runs: Sequence[ModelRun],
    *,
    header: Mapping[str, object],
    boot: BootstrapConfig = BootstrapConfig(),
    checks: Mapping[str, object] | None = None,
) -> dict:
    """Assemble the whole report as one JSON-serialisable dict."""
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "header": dict(header),
        "bootstrap": boot.to_dict(),
        "checks": dict(checks or {}),
        "models": [_model_block(run, boot=boot) for run in runs],
        "comparisons": compare_models(runs),
        "expectations": list(EXPECTATIONS),
        "limitations": list(LIMITATIONS),
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


def _render_header(report: Mapping[str, object]) -> list[str]:
    header = report["header"]
    lines = ["# Encoder training: evaluation report", ""]
    lines.append(f"*Generated {report['generated_at']}.*")
    lines.append("")
    rows = []
    for key, value in header.items():
        if isinstance(value, Mapping):
            rendered = ", ".join(f"{name} {count}" for name, count in value.items())
        else:
            rendered = str(value)
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


def _render_comparisons(report: Mapping[str, object]) -> list[str]:
    comparisons = report["comparisons"]
    lines = ["## Paired comparisons (McNemar, raw argmax)", ""]
    if not comparisons:
        lines.append("No pair of non-control models to compare.")
        lines.append("")
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
    lines.extend(_render_headline(report))
    lines.extend(_render_bullets("What we expected before looking", report["expectations"]))
    lines.extend(_render_checks(report))
    lines.extend(_render_comparisons(report))
    for model in report["models"]:
        lines.extend(_render_model(model, fragment_rows=fragment_rows))
    lines.extend(_render_appendix(report))
    lines.extend(_render_bullets("Limitations", report["limitations"]))
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

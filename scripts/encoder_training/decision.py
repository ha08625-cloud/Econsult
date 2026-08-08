"""The decision rule (DD9): the margin, how it is chosen, and how it is stored.

:mod:`.metrics` computes every margin's consequences and deliberately refuses to
pick one. This module picks, and it is a separate module rather than a few lines
inside a training script because the rule is a **separate artefact**: a trained
head plus a margin is what gets deployed, the margin is retuned far more often
than the weights, and it has to be readable without loading a model.

**The objective, stated rather than implied.** Choose the margin that maximises
macro-F1 *subject to* a ``null -> true`` rate no worse than plain argmax's.
``null -> true`` is the cell that invents a symptom into a patient's pre-filled
form, so it is a constraint, not a term to be traded off against F1. A rule that
bought two points of macro-F1 by inventing a few more fevers would be the wrong
rule at any exchange rate.

**Where it is selected matters more than how.** Always on the fold's own
validation split, never on test and never pooled across folds. Fold *i*'s
validation clusters are fold *i+1*'s test clusters, so pooling the selection
would put every fold's margin in contact with another fold's test data -- the
optimism DD4 already accepts one layer of, and which there is no reason to
deepen.

Training stays unweighted (DD8). The 15/25/60 class mix is a generator flag, not
a measured prior over real submissions, so reweighting the loss would only
correct towards a second arbitrary target. The asymmetry we actually care about
lives here instead, where it is tunable, versioned and reported.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from .dataset import CLASS_NAMES, CLASS_TRUE
from .metrics import MarginRow, MetricsError, Prediction, apply_margin, sweep_margins

#: The margin grid. Scores are probabilities, so a margin is a probability gap
#: and the grid spans the meaningful range at a resolution finer than the data
#: can distinguish -- which is the right way round, since a coarser grid would
#: make the choice depend on where the ticks happened to fall. ``0.0`` must be
#: present: it is plain argmax, and it is the constraint's reference point.
DEFAULT_MARGINS: tuple[float, ...] = tuple(round(0.05 * step, 2) for step in range(19))

#: Slack allowed when comparing a candidate's ``null -> true`` rate against
#: argmax's. Floating-point only: two rates that are the same ratio of the same
#: integers should compare equal, and without this they occasionally do not.
RATE_TOLERANCE = 1e-12


class DecisionError(ValueError):
    """Raised when a margin cannot be selected from what was supplied."""


@dataclass(frozen=True)
class DecisionRule:
    """A margin, plus the evidence for choosing it.

    The provenance fields are not decoration. A margin on its own is
    uninterpretable six months later: ``0.35`` says nothing about whether it was
    bought at the cost of the cell it exists to protect, and the two rates
    recorded here say exactly that.
    """

    margin: float
    gated_class: int = CLASS_TRUE
    #: Which split the margin was chosen on. Recorded so that a rule selected on
    #: test -- which nothing here does, but a future caller could -- is visible
    #: in the artefact rather than only in the code that wrote it.
    selected_on: str = "val"
    #: ``null -> true`` rate at margin 0 on the selection split: the constraint.
    argmax_null_to_true_rate: float | None = None
    #: ``null -> true`` rate this margin achieves on the selection split.
    null_to_true_rate: float | None = None
    #: Macro-F1 this margin achieves on the selection split.
    macro_f1: float | None = None
    #: Every margin considered, so the choice can be re-derived without a rerun.
    margins_considered: tuple[float, ...] = DEFAULT_MARGINS

    @property
    def gated_class_name(self) -> str:
        return CLASS_NAMES[self.gated_class]

    def decide(self, scores: Sequence[float]) -> int:
        """Apply the rule to one example's per-class scores."""
        return apply_margin(scores, self.margin, gated_class=self.gated_class)

    def to_dict(self) -> dict:
        return {
            "margin": self.margin,
            "gated_class": self.gated_class,
            "gated_class_name": self.gated_class_name,
            "selected_on": self.selected_on,
            "argmax_null_to_true_rate": self.argmax_null_to_true_rate,
            "null_to_true_rate": self.null_to_true_rate,
            "macro_f1": self.macro_f1,
            "margins_considered": list(self.margins_considered),
        }

    @classmethod
    def from_dict(cls, payload: dict) -> DecisionRule:
        return cls(
            margin=payload["margin"],
            gated_class=payload.get("gated_class", CLASS_TRUE),
            selected_on=payload.get("selected_on", "val"),
            argmax_null_to_true_rate=payload.get("argmax_null_to_true_rate"),
            null_to_true_rate=payload.get("null_to_true_rate"),
            macro_f1=payload.get("macro_f1"),
            margins_considered=tuple(payload.get("margins_considered", DEFAULT_MARGINS)),
        )

    def write(self, path: Path | str) -> Path:
        """Write the rule beside a model, as its own file."""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.to_dict(), indent=2) + "\n", encoding="utf-8")
        return path

    @classmethod
    def read(cls, path: Path | str) -> DecisionRule:
        return cls.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))


def _rank(row: MarginRow) -> tuple:
    """Sort key for candidate margins: best first.

    Macro-F1 descending is the objective. The two tie-breaks are chosen so the
    rule is the least interventionist one that ties: prefer the lower
    ``null -> true`` rate, then the smaller margin. Without them the winner
    would depend on grid iteration order, which is not a thing a clinical
    decision rule should depend on.
    """
    macro = -1.0 if row.summary.macro_f1 is None else row.summary.macro_f1
    rate = 0.0 if row.null_to_true_rate is None else row.null_to_true_rate
    return (-macro, rate, row.margin)


def select_margin(
    predictions: Sequence[Prediction],
    *,
    margins: Sequence[float] = DEFAULT_MARGINS,
    gated_class: int = CLASS_TRUE,
    selected_on: str = "val",
) -> DecisionRule:
    """Choose a margin on a **validation** slice, by the DD9 objective.

    ``predictions`` must carry scores; a slice scored under one rule already
    cannot be re-decided under another. Every margin the grid contains is
    evaluated, the ones that worsen the ``null -> true`` rate against argmax are
    discarded, and the best remaining macro-F1 wins.

    Note what the constraint does when the model is very weak. A model that
    never predicts ``true`` has a ``null -> true`` rate of zero, no margin can
    beat that, and argmax wins by default -- correctly. The rule protects a cell;
    it cannot improve a model that is not using the cell.
    """
    if not predictions:
        raise DecisionError("cannot select a margin on an empty split")
    grid = tuple(margins)
    if not any(margin == 0.0 for margin in grid):
        raise DecisionError(
            "the margin grid must contain 0.0: it is plain argmax, and the constraint is "
            "expressed relative to it"
        )
    if any(prediction.scores is None for prediction in predictions):
        raise MetricsError(
            "margin selection needs per-class scores; predictions without them have already "
            "had a decision rule applied and cannot be re-decided"
        )

    rows = sweep_margins(predictions, grid, gated_class=gated_class)
    by_margin = {row.margin: row for row in rows}
    argmax_rate = by_margin[0.0].null_to_true_rate

    if argmax_rate is None:
        # No truly-null examples on the selection split, so the constraint has
        # nothing to bind on. Not silently ignored: the caller gets a rule whose
        # recorded rates are None, which is what makes it visible in the report.
        eligible = list(rows)
    else:
        eligible = [
            row
            for row in rows
            if row.null_to_true_rate is None
            or row.null_to_true_rate <= argmax_rate + RATE_TOLERANCE
        ]

    best = min(eligible, key=_rank)
    return DecisionRule(
        margin=best.margin,
        gated_class=gated_class,
        selected_on=selected_on,
        argmax_null_to_true_rate=argmax_rate,
        null_to_true_rate=best.null_to_true_rate,
        macro_f1=best.summary.macro_f1,
        margins_considered=grid,
    )

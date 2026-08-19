"""Score the multi-symptom ticket's declared threshold from the written reports.

Task 7 step 6. The four criteria were written down *before* the run (they are
reproduced verbatim in ``__main__.COMPANION_PREDICTIONS`` and printed inside
every report), and this module does nothing but read them back off disk and
say ``held`` or ``not held``. It makes no judgement, and there is deliberately
no threshold in it that the run could have chosen for itself.

**Why this is a module and not a reader with a calculator.** The primary
criterion is a twenty-point gap on at least four of six signals, where each
signal's number is a mean over five folds sitting in a different file; the
negative control is a two-point limit read in the direction where *movement is
the failure*. Both are easy to get subtly wrong by hand and impossible to
re-check afterwards. The reports' JSON is authoritative -- the markdown rounds
-- so this reads the JSON.

**The gate comes first and it is a gate.** DD5's leak detector (task 7
instruction 7) asks whether companion count tracks the label mode. If it does,
companions became a proxy for the answer, the arms differ in something other
than what they were meant to differ in, and no score below is interpretable.
That is a void run rather than a bad result, so a failed gate exits non-zero
and marks every criterion ``VOID`` rather than printing numbers a reader would
inevitably read anyway.

Criteria that are *not held* exit zero. A recorded failure is this command
working, not this command erroring.
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path

#: The arm labels as they appear in a report, after ``train.arm_run_name`` has
#: qualified them (``arm_b_finetune@Arm0_control``). Matched on the suffix so a
#: report written with a different base arm name still resolves.
ARM0 = "Arm0_control"
ARMP = "ArmP_companions"
ARMC = "ArmC_remargined"

#: The declared threshold, in the units it was declared in. Percentage points,
#: not ratios: the criterion says "20 points below", so 82% against 55% is 27
#: and not 33%.
PRIMARY_POINTS = 20.0

#: How many of the six signals have to clear it.
PRIMARY_SIGNALS_REQUIRED = 4

#: The negative control's limit, in either direction. The synthetic test set
#: cannot contain the failure companions were built to fix -- its `null -> true`
#: cell already runs at 0.58%-2.53% -- so a large *improvement* here is evidence
#: of a new shortcut and fails this control exactly as a large regression would.
NEGATIVE_CONTROL_POINTS = 2.0

#: DD5's gate: the largest difference, between any two label modes, in mean
#: companions per example on a training split. Task 6 measured roughly 0.024 at
#: share 0.5; this is the "materially above that" line, set loose enough that
#: sampling noise on a 10,000-example split does not trip it and tight enough
#: that a real correlation with the label cannot hide under it.
LEAK_SPREAD_LIMIT = 0.05

REPORT_SUFFIX = ".companion_comparison.json"


class ThresholdError(Exception):
    """A report that cannot be scored: missing, malformed, or missing an arm."""


@dataclass(frozen=True)
class SignalScore:
    """Every number the four criteria need, for one signal."""

    signal: str
    real_null_to_true: dict[str, float | None]
    real_accuracy: dict[str, float | None]
    synthetic_null_to_true: dict[str, float | None]
    #: Per-fold McNemar rows for Arm 0 against Arm P on the 67 submissions.
    paired: Mapping[str, object] | None = None

    @property
    def primary_delta(self) -> float | None:
        """Points by which Arm P's real-text `null -> true` sits below Arm 0's."""
        return _delta_points(self.real_null_to_true[ARM0], self.real_null_to_true[ARMP])

    @property
    def armc_delta(self) -> float | None:
        """The same for Arm C, whose gain cost nothing but a re-selected margin."""
        return _delta_points(self.real_null_to_true[ARM0], self.real_null_to_true[ARMC])

    @property
    def armc_capture(self) -> float | None:
        """The fraction of Arm P's gain that margin re-selection alone captured.

        ``None`` when Arm P did not gain: a ratio against a zero or negative
        denominator is not a share of anything, and printing one would invent a
        finding out of two numbers that both failed.
        """
        armp, armc = self.primary_delta, self.armc_delta
        if armp is None or armc is None or armp <= 0:
            return None
        return armc / armp

    @property
    def negative_control_movement(self) -> float | None:
        """Absolute movement of the *synthetic* `null -> true` cell, in points."""
        delta = _delta_points(self.synthetic_null_to_true[ARM0], self.synthetic_null_to_true[ARMP])
        return None if delta is None else abs(delta)


@dataclass(frozen=True)
class Criterion:
    """One declared criterion, scored."""

    name: str
    held: bool | None
    detail: str

    @property
    def verdict(self) -> str:
        if self.held is None:
            return "NOT SCORED"
        return "HELD" if self.held else "NOT HELD"


@dataclass(frozen=True)
class Scorecard:
    """The whole of step 6: the gate, the four criteria, and what they read."""

    signals: tuple[SignalScore, ...]
    arms: tuple[Mapping[str, object], ...]
    gate_passed: bool
    gate_detail: str
    criteria: tuple[Criterion, ...] = field(default_factory=tuple)


# ---------------------------------------------------------------------------
# Reading
# ---------------------------------------------------------------------------


def _delta_points(before: float | None, after: float | None) -> float | None:
    """``before - after`` in percentage points; positive means the rate fell."""
    if before is None or after is None:
        return None
    return 100 * (before - after)


def _mean(values: Sequence[float | None]) -> float | None:
    present = [value for value in values if value is not None]
    return None if not present else sum(present) / len(present)


def _find_arm(report: Mapping[str, object], label: str, *, path: Path) -> Mapping[str, object]:
    models = report.get("models") or []
    matches = [model for model in models if str(model.get("name", "")).split("@")[-1] == label]
    if not matches:
        names = ", ".join(str(model.get("name")) for model in models) or "none"
        raise ThresholdError(
            f"{path}: no arm named {label!r} in this report (arms present: {names}). A "
            "companion comparison holds all three arms; a report missing one was written by a "
            "different command and its numbers do not answer this ticket's question"
        )
    if len(matches) > 1:
        raise ThresholdError(f"{path}: {len(matches)} arms named {label!r}")
    return matches[0]


def _holdout_signal_entry(
    arm: Mapping[str, object], signal: str, *, path: Path
) -> Mapping[str, object] | None:
    """One arm's real-text block for one signal, or ``None`` if unscored.

    ``None`` is what ``--no-holdout`` leaves behind, and it is not an error
    here: it makes the primary criterion unscorable, which is a thing the
    scorecard says out loud rather than a thing this raises over.
    """
    holdout = arm.get("holdout")
    if not holdout:
        return None
    for entry in holdout.get("by_signal") or []:
        if entry.get("signal") == signal:
            return entry
    raise ThresholdError(
        f"{path}: arm {arm.get('name')!r} scored the holdout but carries no {signal!r} row, so "
        "the report's own signal and its holdout disagree about what was measured"
    )


def _real_accuracy(arm: Mapping[str, object]) -> float | None:
    holdout = arm.get("holdout")
    if not holdout:
        return None
    return ((holdout.get("overall") or {}).get("accuracy") or {}).get("mean")


def _synthetic_null_to_true(arm: Mapping[str, object]) -> float | None:
    """The ruled view, because that is the view a deployment would use."""
    pooled = (arm.get("pooled") or {}).get("ruled") or {}
    return (pooled.get("null_to_true") or {}).get("rate")


def _paired_row(report: Mapping[str, object]) -> Mapping[str, object] | None:
    """The Arm 0 / Arm P McNemar row on the 67 submissions, in either order."""
    for row in report.get("holdout_comparisons") or []:
        names = {str(row.get("left", "")).split("@")[-1], str(row.get("right", "")).split("@")[-1]}
        if names == {ARM0, ARMP}:
            return row
    return None


def read_signal(path: Path) -> SignalScore:
    """Score one signal's report."""
    if not path.exists():
        raise ThresholdError(
            f"{path}: no such report. Did the run write to a different --report-dir?"
        )
    try:
        report = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise ThresholdError(f"{path}: not readable as JSON ({error})") from error

    signal = report.get("header", {}).get("signal")
    if not signal:
        raise ThresholdError(f"{path}: the report names no signal")

    arms = {label: _find_arm(report, label, path=path) for label in (ARM0, ARMP, ARMC)}
    real: dict[str, float | None] = {}
    for label, arm in arms.items():
        entry = _holdout_signal_entry(arm, str(signal), path=path)
        real[label] = None if entry is None else (entry.get("null_to_true") or {}).get("mean_rate")

    return SignalScore(
        signal=str(signal),
        real_null_to_true=real,
        real_accuracy={label: _real_accuracy(arm) for label, arm in arms.items()},
        synthetic_null_to_true={label: _synthetic_null_to_true(arm) for label, arm in arms.items()},
        paired=_paired_row(report),
    )


def read_arms(path: Path) -> tuple[Mapping[str, object], ...]:
    """The `companions` header block: what generated each arm's dataset."""
    report = json.loads(path.read_text(encoding="utf-8"))
    return tuple((report.get("companions") or {}).get("arms") or ())


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------


def score_gate(arms: Sequence[Mapping[str, object]]) -> tuple[bool, str]:
    """DD5's leak detector, over both arms' training splits.

    Passing is a statement about the *training* data, not about any model: at
    share 0 there are no companions at all, and at share 0.5 the mean count per
    example must not differ between the `true`, `false` and `null` modes. A run
    that fails this is void.
    """
    if not arms:
        return False, "no `companions` block in the report: the leak detector cannot be read"
    shares = {arm.get("companion_share") for arm in arms}
    if len(shares) < 2:
        return False, (
            f"both arms were generated at companion share {shares.pop()!r}, so this report "
            "compares two seeds rather than two arms"
        )
    worst = 0.0
    unread = []
    for arm in arms:
        spread = arm.get("worst_label_mode_spread")
        if spread is None:
            if arm.get("companion_share"):
                unread.append(str(arm.get("dataset_dir")))
            continue
        worst = max(worst, float(spread))
    if unread:
        return False, (
            "no per-split companion sidecar was found for " + ", ".join(unread) + ", so the "
            "leak detector did not run. It is the one check that decides whether the run is "
            "interpretable at all"
        )
    if worst > LEAK_SPREAD_LIMIT:
        return False, (
            f"worst label-mode spread {worst:.3f} companions/example exceeds the "
            f"{LEAK_SPREAD_LIMIT:.3f} limit: companion count tracks the label, which is the "
            "failure DD5 was written to catch. Prediction 6 has failed and the run is void"
        )
    return (
        True,
        f"worst label-mode spread {worst:.3f} companions/example (limit {LEAK_SPREAD_LIMIT:.3f})",
    )


def score(signals: Sequence[SignalScore], arms: Sequence[Mapping[str, object]]) -> Scorecard:
    """The four declared criteria, in the order they were declared."""
    gate_passed, gate_detail = score_gate(arms)
    if not gate_passed:
        return Scorecard(
            signals=tuple(signals),
            arms=tuple(arms),
            gate_passed=False,
            gate_detail=gate_detail,
            criteria=tuple(
                Criterion(name, None, "the DD5 gate failed: this run is void, not reinterpretable")
                for name in ("Primary", "Guard", "Negative control", "Arm C")
            ),
        )

    cleared = [entry for entry in signals if (entry.primary_delta or 0.0) >= PRIMARY_POINTS]
    unscorable = [entry.signal for entry in signals if entry.primary_delta is None]
    primary = Criterion(
        name="Primary",
        held=None if unscorable else len(cleared) >= PRIMARY_SIGNALS_REQUIRED,
        detail=(
            f"{len(cleared)} of {len(signals)} signals cleared {PRIMARY_POINTS:.0f} points "
            f"(need {PRIMARY_SIGNALS_REQUIRED})"
            if not unscorable
            else "no real-text score for " + ", ".join(unscorable)
        ),
    )

    arm0_accuracy = _mean([entry.real_accuracy[ARM0] for entry in signals])
    armp_accuracy = _mean([entry.real_accuracy[ARMP] for entry in signals])
    guard_delta = _delta_points(armp_accuracy, arm0_accuracy)
    guard = Criterion(
        name="Guard",
        held=None if guard_delta is None else guard_delta >= 0,
        detail=(
            "no real-text accuracy on file"
            if guard_delta is None
            else f"Arm P {100 * (armp_accuracy or 0):.1f}% against Arm 0 "
            f"{100 * (arm0_accuracy or 0):.1f}% ({guard_delta:+.1f} points)"
        ),
    )

    movements = [entry.negative_control_movement for entry in signals]
    worst_movement = max((value for value in movements if value is not None), default=None)
    control = Criterion(
        name="Negative control",
        held=None if worst_movement is None else worst_movement < NEGATIVE_CONTROL_POINTS,
        detail=(
            "no synthetic score on file"
            if worst_movement is None
            else f"largest synthetic movement {worst_movement:.2f} points "
            f"(limit {NEGATIVE_CONTROL_POINTS:.1f}, in either direction)"
        ),
    )

    captures = [entry.armc_capture for entry in signals if entry.armc_capture is not None]
    mean_capture = _mean(captures)
    arm_c = Criterion(
        name="Arm C",
        # Not a pass/fail: the criterion asks how much of Arm P's gain a
        # re-selected margin captured, and a high number is a finding rather
        # than a failure. Scored as `None` so nothing tallies it as a pass.
        held=None,
        detail=(
            "Arm P gained nothing to capture on any signal"
            if mean_capture is None
            else f"margin re-selection alone captured {100 * mean_capture:.0f}% of Arm P's mean "
            f"gain, over {len(captures)} of {len(signals)} signals where Arm P gained"
        ),
    )

    return Scorecard(
        signals=tuple(signals),
        arms=tuple(arms),
        gate_passed=True,
        gate_detail=gate_detail,
        criteria=(primary, guard, control, arm_c),
    )


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------

DASH = "--"


def _pct(value: float | None, digits: int = 1) -> str:
    return DASH if value is None else f"{100 * value:.{digits}f}%"


def _points(value: float | None) -> str:
    return DASH if value is None else f"{value:+.1f}"


def _table(headers: Sequence[str], rows: Sequence[Sequence[str]]) -> list[str]:
    widths = [
        max(len(headers[column]), *(len(row[column]) for row in rows))
        if rows
        else len(headers[column])
        for column in range(len(headers))
    ]

    def line(cells: Sequence[str]) -> str:
        return "  ".join(
            cell.ljust(widths[column]) if column == 0 else cell.rjust(widths[column])
            for column, cell in enumerate(cells)
        )

    return [line(headers), *(line(row) for row in rows)]


def render(card: Scorecard) -> list[str]:
    """The scorecard as plain text: the gate, then the four criteria."""
    lines = ["Companion comparison -- the declared threshold, scored", ""]

    lines.append("Gate -- DD5 leak detector (companion count must not track the label)")
    lines.extend(
        "  " + row
        for row in _table(
            ["arm", "share", "train examples", "companions/example", "label-mode spread"],
            [
                [
                    str(arm.get("dataset_dir")),
                    str(arm.get("companion_share")),
                    str(arm.get("train_examples")),
                    DASH
                    if arm.get("companions_per_example") is None
                    else f"{arm['companions_per_example']:.3f}",
                    DASH
                    if arm.get("worst_label_mode_spread") is None
                    else f"{arm['worst_label_mode_spread']:.3f}",
                ]
                for arm in card.arms
            ],
        )
    )
    lines.append(f"  gate: {'PASSED' if card.gate_passed else 'FAILED'} -- {card.gate_detail}")
    lines.append("")

    if not card.gate_passed:
        lines.append("Every criterion below is VOID. A run whose companion draw correlates with")
        lines.append("the label did not test what it was built to test, and its scores are not")
        lines.append("a weaker version of the answer -- they are not an answer.")
        return lines

    primary, guard, control, arm_c = card.criteria

    lines.append("1. Primary -- real-text `null -> true`, Arm P against Arm 0")
    lines.append("  (`pts lower` is positive when Arm P asserts unmentioned symptoms less often)")
    lines.extend(
        "  " + row
        for row in _table(
            ["signal", "Arm 0", "Arm P", "pts lower", f">={PRIMARY_POINTS:.0f}"],
            [
                [
                    entry.signal,
                    _pct(entry.real_null_to_true[ARM0]),
                    _pct(entry.real_null_to_true[ARMP]),
                    _points(entry.primary_delta),
                    "yes" if (entry.primary_delta or 0.0) >= PRIMARY_POINTS else "no",
                ]
                for entry in card.signals
            ],
        )
    )
    lines.append(f"  {primary.detail}")
    lines.append(f"  PRIMARY: {primary.verdict}")
    lines.append("")

    lines.append("2. Guard -- real-text overall accuracy, Arm P not below Arm 0")
    lines.extend(
        "  " + row
        for row in _table(
            ["arm", "accuracy"],
            [
                [label, _pct(_mean([entry.real_accuracy[label] for entry in card.signals]))]
                for label in (ARM0, ARMC, ARMP)
            ],
        )
    )
    lines.append(f"  {guard.detail}")
    lines.append(f"  GUARD: {guard.verdict}")
    lines.append("  (the 66.7% all-`null` floor is a separate observation and not this criterion)")
    lines.append("")

    lines.append("3. Negative control -- synthetic `null -> true` must barely move")
    lines.extend(
        "  " + row
        for row in _table(
            ["signal", "Arm 0", "Arm P", "pts lower"],
            [
                [
                    entry.signal,
                    _pct(entry.synthetic_null_to_true[ARM0], 2),
                    _pct(entry.synthetic_null_to_true[ARMP], 2),
                    _points(
                        _delta_points(
                            entry.synthetic_null_to_true[ARM0], entry.synthetic_null_to_true[ARMP]
                        )
                    ),
                ]
                for entry in card.signals
            ],
        )
    )
    lines.append(f"  {control.detail}")
    lines.append(f"  NEGATIVE CONTROL: {control.verdict}")
    lines.append(
        "  (read this one backwards: a large synthetic gain is evidence of a new shortcut)"
    )
    lines.append("")

    lines.append("4. Arm C -- how much of Arm P's gain a re-selected margin captured")
    lines.extend(
        "  " + row
        for row in _table(
            ["signal", "Arm 0", "Arm C", "Arm P", "C pts lower", "P pts lower", "captured"],
            [
                [
                    entry.signal,
                    _pct(entry.real_null_to_true[ARM0]),
                    _pct(entry.real_null_to_true[ARMC]),
                    _pct(entry.real_null_to_true[ARMP]),
                    _points(entry.armc_delta),
                    _points(entry.primary_delta),
                    DASH if entry.armc_capture is None else f"{100 * entry.armc_capture:.0f}%",
                ]
                for entry in card.signals
            ],
        )
    )
    lines.append(f"  {arm_c.detail}")
    lines.append(
        "  Not pass/fail. If it captured nearly all of it, the finding is that regenerating"
    )
    lines.append("  the data was not what did the work, and that is the headline.")
    lines.append("")

    lines.extend(_render_paired(card))
    return lines


def _render_paired(card: Scorecard) -> list[str]:
    """The per-fold McNemar counts, with the power warning attached to them."""
    rows = []
    for entry in card.signals:
        if entry.paired is None:
            rows.append([entry.signal, DASH, DASH, DASH, DASH, DASH])
            continue
        folds = entry.paired.get("folds") or []
        discordant = "/".join(
            str(int(fold["left_only_correct"]) + int(fold["right_only_correct"])) for fold in folds
        )
        p_values = "/".join(
            DASH if fold.get("p_value") is None else f"{fold['p_value']:.2f}" for fold in folds
        )
        rows.append(
            [
                entry.signal,
                str(entry.paired.get("n_pairs", DASH)),
                str(entry.paired.get("left_better_folds", DASH)),
                str(entry.paired.get("right_better_folds", DASH)),
                discordant or DASH,
                p_values or DASH,
            ]
        )
    lines = ["Paired real-text McNemar, Arm 0 against Arm P, one test per fold"]
    lines.extend(
        "  " + row
        for row in _table(
            ["signal", "pairs", "Arm 0 better", "Arm P better", "discordant/fold", "p/fold"],
            rows,
        )
    )
    lines.append(
        "  67 submissions per fold, five overlapping models, one cell per submission per signal:"
    )
    lines.append("  these p-values are neither independent of each other nor a statement about new")
    lines.append("  patients. The discordant counts are the honest measure of how little is here.")
    return lines


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def score_directory(report_dir: Path, signals: Sequence[str]) -> Scorecard:
    """Read every signal's companion report under ``report_dir`` and score it."""
    paths = [report_dir / f"{signal}{REPORT_SUFFIX}" for signal in signals]
    scored = [read_signal(path) for path in paths]
    return score(scored, read_arms(paths[0]))


def run(args: argparse.Namespace) -> int:
    card = score_directory(Path(args.report_dir), args.signals)
    if args.json:
        print(json.dumps(_as_dict(card), indent=2))
    else:
        for line in render(card):
            print(line)
    return 0 if card.gate_passed else 1


def _as_dict(card: Scorecard) -> dict:
    return {
        "gate": {"passed": card.gate_passed, "detail": card.gate_detail},
        "arms": [dict(arm) for arm in card.arms],
        "criteria": [
            {"name": item.name, "verdict": item.verdict, "held": item.held, "detail": item.detail}
            for item in card.criteria
        ],
        "signals": [
            {
                "signal": entry.signal,
                "real_null_to_true": entry.real_null_to_true,
                "real_accuracy": entry.real_accuracy,
                "synthetic_null_to_true": entry.synthetic_null_to_true,
                "primary_delta_points": entry.primary_delta,
                "arm_c_delta_points": entry.armc_delta,
                "arm_c_capture": entry.armc_capture,
            }
            for entry in card.signals
        ],
    }

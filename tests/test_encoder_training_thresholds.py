"""Unit tests for the step-6 scorer (multi-symptom ticket, task 7).

Stdlib and pytest only: the scorer reads written reports, so these tests write
reports rather than training anything.

The three failures worth this much machinery are the three that would produce a
*plausible* scorecard while being wrong:

``test_a_large_synthetic_gain_fails_the_negative_control`` is the one a reader
gets backwards without help. The control is a limit on *movement*, so an arm
that halves the synthetic ``null -> true`` cell fails it, and fails it for the
reason the criterion was written: the synthetic set cannot contain the failure
companions fix, so a big move there is a new shortcut.

``test_a_leaked_run_is_void_rather_than_scored`` is the gate. DD5's detector
failing does not make the numbers weaker, it makes them meaningless, and the
scorecard has to refuse to print verdicts rather than print bad ones.

``test_arm_c_capture_is_not_reported_against_a_gain_that_did_not_happen`` is the
divide-by-nothing: a share of Arm P's gain is undefined when Arm P did not gain,
and a ratio printed there would invent a finding out of two failures.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.encoder_training.thresholds import (
    ARM0,
    ARMC,
    ARMP,
    ThresholdError,
    score_directory,
)

SIGNALS = (
    "fever_present",
    "flank_pain_present",
    "haematuria_present",
    "dysuria_present",
    "nocturia_present",
    "urinary_frequency_present",
)

#: The 2026-08-17 baseline cells, which Arm 0 stands in for here.
BASELINE = {
    "fever_present": 0.82,
    "flank_pain_present": 0.89,
    "haematuria_present": 0.79,
    "dysuria_present": 0.67,
    "nocturia_present": 0.58,
    "urinary_frequency_present": 0.47,
}


def _arm(
    label: str,
    signal: str,
    *,
    real_null_to_true: float,
    accuracy: float,
    synthetic_null_to_true: float,
) -> dict:
    return {
        "name": f"arm_b_finetune@{label}",
        "pooled": {"ruled": {"null_to_true": {"rate": synthetic_null_to_true}}},
        "holdout": {
            "overall": {"accuracy": {"mean": accuracy}},
            "by_signal": [
                {
                    "signal": signal,
                    "null_to_true": {
                        "null_support": 40,
                        "counts": [0, 0, 0, 0, 0],
                        "rates": [real_null_to_true] * 5,
                        "mean_rate": real_null_to_true,
                    },
                }
            ],
        },
    }


def _write_reports(
    directory: Path,
    *,
    armp_real: dict[str, float],
    armc_real: dict[str, float] | None = None,
    arm0_accuracy: float = 0.391,
    armp_accuracy: float = 0.421,
    arm0_synthetic: float = 0.012,
    armp_synthetic: float = 0.015,
    label_mode_spread: float = 0.021,
) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    companions = {
        "arms": [
            {
                "dataset_dir": "data/synthetic/generated/arm0",
                "companion_share": 0.0,
                "train_examples": 45000,
                "companions_per_example": 0.0,
                "worst_label_mode_spread": 0.0,
            },
            {
                "dataset_dir": "data/synthetic/generated/armp",
                "companion_share": 0.5,
                "train_examples": 54500,
                "companions_per_example": 0.51,
                "worst_label_mode_spread": label_mode_spread,
            },
        ]
    }
    for signal in SIGNALS:
        arm_c_rate = (armc_real or {}).get(signal, BASELINE[signal])
        report = {
            "header": {"signal": signal},
            "companions": companions,
            "models": [
                _arm(
                    ARM0,
                    signal,
                    real_null_to_true=BASELINE[signal],
                    accuracy=arm0_accuracy,
                    synthetic_null_to_true=arm0_synthetic,
                ),
                _arm(
                    ARMC,
                    signal,
                    real_null_to_true=arm_c_rate,
                    accuracy=arm0_accuracy,
                    synthetic_null_to_true=arm0_synthetic,
                ),
                _arm(
                    ARMP,
                    signal,
                    real_null_to_true=armp_real[signal],
                    accuracy=armp_accuracy,
                    synthetic_null_to_true=armp_synthetic,
                ),
            ],
            "holdout_comparisons": [
                {
                    "left": f"arm_b_finetune@{ARM0}",
                    "right": f"arm_b_finetune@{ARMP}",
                    "signal": signal,
                    "n_pairs": 40,
                    "left_better_folds": 1,
                    "right_better_folds": 4,
                    "folds": [
                        {
                            "fold": index,
                            "n_pairs": 40,
                            "left_only_correct": 2,
                            "right_only_correct": 7,
                            "p_value": 0.09,
                        }
                        for index in range(5)
                    ],
                }
            ],
        }
        (directory / f"{signal}.companion_comparison.json").write_text(
            json.dumps(report), encoding="utf-8"
        )
    return directory


def _verdicts(card) -> dict[str, str]:
    return {item.name: item.verdict for item in card.criteria}


def test_the_primary_criterion_counts_signals_not_average_movement(tmp_path: Path) -> None:
    """Four signals moving 25 points holds; two moving 60 does not.

    The criterion is deliberately a count and not a mean, because a mean is
    passed by one signal collapsing and is exactly what a new shortcut would
    look like.
    """
    four_of_six = {
        "fever_present": 0.57,
        "flank_pain_present": 0.64,
        "haematuria_present": 0.54,
        "dysuria_present": 0.42,
        "nocturia_present": 0.55,
        "urinary_frequency_present": 0.45,
    }
    card = score_directory(_write_reports(tmp_path / "four", armp_real=four_of_six), SIGNALS)
    assert card.gate_passed
    assert _verdicts(card)["Primary"] == "HELD"

    two_huge = dict(BASELINE)
    two_huge["fever_present"] = 0.02
    two_huge["flank_pain_present"] = 0.03
    card = score_directory(_write_reports(tmp_path / "two", armp_real=two_huge), SIGNALS)
    assert _verdicts(card)["Primary"] == "NOT HELD"


def test_the_guard_fails_when_accuracy_falls(tmp_path: Path) -> None:
    """The cheap way to win the primary criterion is to answer `null` to everything."""
    silent = {signal: 0.0 for signal in SIGNALS}
    directory = _write_reports(
        tmp_path / "silent", armp_real=silent, arm0_accuracy=0.391, armp_accuracy=0.310
    )
    card = score_directory(directory, SIGNALS)
    verdicts = _verdicts(card)
    assert verdicts["Primary"] == "HELD"
    assert verdicts["Guard"] == "NOT HELD"


def test_a_large_synthetic_gain_fails_the_negative_control(tmp_path: Path) -> None:
    """Movement is the failure, in either direction, and improvement is movement."""
    modest = {signal: rate - 0.25 for signal, rate in BASELINE.items()}
    held = score_directory(
        _write_reports(
            tmp_path / "held", armp_real=modest, arm0_synthetic=0.012, armp_synthetic=0.017
        ),
        SIGNALS,
    )
    assert _verdicts(held)["Negative control"] == "HELD"

    improved = score_directory(
        _write_reports(
            tmp_path / "improved", armp_real=modest, arm0_synthetic=0.052, armp_synthetic=0.002
        ),
        SIGNALS,
    )
    assert _verdicts(improved)["Negative control"] == "NOT HELD"


def test_a_leaked_run_is_void_rather_than_scored(tmp_path: Path) -> None:
    """DD5's gate: companion count tracking the label voids every number below it."""
    modest = {signal: rate - 0.30 for signal, rate in BASELINE.items()}
    directory = _write_reports(tmp_path / "leaked", armp_real=modest, label_mode_spread=0.4)
    card = score_directory(directory, SIGNALS)
    assert not card.gate_passed
    assert set(_verdicts(card).values()) == {"NOT SCORED"}
    assert "void" in card.gate_detail


def test_arm_c_capture_is_not_reported_against_a_gain_that_did_not_happen(
    tmp_path: Path,
) -> None:
    """A share of a gain Arm P did not make is undefined, not zero and not 100%."""
    worse = {signal: rate + 0.05 for signal, rate in BASELINE.items()}
    card = score_directory(_write_reports(tmp_path / "worse", armp_real=worse), SIGNALS)
    assert all(entry.armc_capture is None for entry in card.signals)
    detail = {item.name: item.detail for item in card.criteria}["Arm C"]
    assert "gained nothing" in detail


def test_arm_c_capture_is_the_fraction_of_arm_p_s_gain(tmp_path: Path) -> None:
    """Half of Arm P's movement, from a re-selected margin and nothing else."""
    armp = {signal: rate - 0.40 for signal, rate in BASELINE.items()}
    armc = {signal: rate - 0.20 for signal, rate in BASELINE.items()}
    card = score_directory(
        _write_reports(tmp_path / "capture", armp_real=armp, armc_real=armc), SIGNALS
    )
    for entry in card.signals:
        assert entry.armc_capture == pytest.approx(0.5)


def test_a_report_missing_an_arm_is_refused(tmp_path: Path) -> None:
    """Two arms in a three-arm report means a different command wrote it."""
    directory = _write_reports(tmp_path / "partial", armp_real={signal: 0.1 for signal in SIGNALS})
    path = directory / "fever_present.companion_comparison.json"
    report = json.loads(path.read_text(encoding="utf-8"))
    report["models"] = [model for model in report["models"] if not model["name"].endswith(ARMC)]
    path.write_text(json.dumps(report), encoding="utf-8")

    with pytest.raises(ThresholdError, match=ARMC):
        score_directory(directory, SIGNALS)

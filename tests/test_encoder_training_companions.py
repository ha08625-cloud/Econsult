"""Unit tests for the three-arm companion comparison (multi-symptom ticket, task 7).

Pure unit tests: no torch, no GPU, no network. The three things covered here are
the three that would produce a *plausible* report while being wrong, which is
the only kind of failure worth this much machinery.

``test_arm_p_cannot_be_paired_on_the_synthetic_test_set`` is the trap. Arm 0 and
Arm P number their examples from zero independently, so their id sets match
exactly while the texts behind them do not. Handed to ``compare_models``
unqualified, the pairing succeeds silently and reports a McNemar test over pairs
that do not exist -- it only raises in the lucky case where the two disagree
about a truth.

``test_the_real_text_comparison_pairs_on_submissions`` is the other half of the
same fact: the 67 submissions *are* the same for every arm, and they are
therefore where the ticket's question is decided.

``test_remargining_scores_the_holdout_last`` is the holdout's own rule (README
rule 2) applied to Arm C. A margin re-selected on another tree's validation
split is still a margin selected before anything is scored, and the recording
fake asserts the order rather than a comment claiming it.
"""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts.encoder_training.__main__ import _as_unpaired, _companion_facts
from scripts.encoder_training.dataset import CLASS_NULL, CLASS_TRUE
from scripts.encoder_training.decision import DecisionRule
from scripts.encoder_training.metrics import Prediction
from scripts.encoder_training.report import (
    FoldRun,
    ModelRun,
    compare_models,
    holdout_comparisons,
)
from scripts.encoder_training.train import (
    FineTuneConfig,
    RemarginedFoldResult,
    TrainError,
    remargin_multi,
    remargined_runs,
)

SIGNAL = "fever_present"


def _prediction(example_id: str, truth: int, predicted: int, *, scores=None) -> Prediction:
    return Prediction(
        example_id=example_id,
        truth=truth,
        predicted=predicted,
        unit=example_id,
        scores=scores,
    )


#: Confident scores in (false, true, null) order, so a prediction can be
#: re-decided under a different margin the way a real one can.
CONFIDENT = {0: (0.9, 0.05, 0.05), 1: (0.05, 0.9, 0.05), 2: (0.05, 0.05, 0.9)}


def _cells(rows) -> dict:
    """A holdout block carrying only what the paired comparison reads."""
    return {
        "path": "data/realistic/uti1_holdout.labels.tsv",
        "n_submissions": len(rows),
        "by_signal": [
            {
                "signal": SIGNAL,
                "null_to_true": {
                    "count": sum(
                        1
                        for _, truth, predicted in rows
                        if truth == CLASS_NULL and predicted == CLASS_TRUE
                    ),
                    "null_support": sum(1 for _, truth, _ in rows if truth == CLASS_NULL),
                },
            }
        ],
        "cells": {
            SIGNAL: [
                {
                    "id": f"{submission}:{SIGNAL}",
                    "unit": submission,
                    "truth": truth,
                    "predicted": predicted,
                }
                for submission, truth, predicted in rows
            ]
        },
    }


def _run(name: str, *, per_fold_rows, test_rows) -> ModelRun:
    return ModelRun(
        name=name,
        kind="finetune",
        description=name,
        folds=tuple(
            FoldRun.build(
                fold_index=index,
                n_train=10,
                n_val=10,
                n_test=len(test_rows),
                rule=DecisionRule(margin=0.0, gated_class=CLASS_TRUE),
                raw=[
                    _prediction(f"test-{position:04d}", truth, predicted)
                    for position, (truth, predicted) in enumerate(test_rows)
                ],
                ruled=[
                    _prediction(f"test-{position:04d}", truth, predicted)
                    for position, (truth, predicted) in enumerate(test_rows)
                ],
                holdout=_cells(rows),
            )
            for index, rows in enumerate(per_fold_rows)
        ),
    )


# --------------------------------------------------------------------------
# What may and may not be paired
# --------------------------------------------------------------------------

RIGHT = [("holdout-0001", CLASS_NULL, CLASS_NULL), ("holdout-0002", CLASS_TRUE, CLASS_TRUE)]
WRONG = [("holdout-0001", CLASS_NULL, CLASS_TRUE), ("holdout-0002", CLASS_TRUE, CLASS_NULL)]


def test_arm_p_cannot_be_paired_on_the_synthetic_test_set():
    """Two arms' recombinations share ids and are different texts.

    The qualification is what turns "these ids happen to match" into a recorded
    skip. Without it the report would carry a McNemar row that looks exactly
    like a real one.
    """
    arm0 = _run("arm0", per_fold_rows=[RIGHT], test_rows=[(CLASS_NULL, CLASS_NULL)])
    armp = _run("armp", per_fold_rows=[RIGHT], test_rows=[(CLASS_NULL, CLASS_NULL)])

    comparisons, skipped = compare_models([arm0, armp])
    assert comparisons, "unqualified ids pair silently -- this is the trap being demonstrated"

    comparisons, skipped = compare_models([arm0, _as_unpaired(armp, prefix="ArmP")])
    assert not comparisons
    assert [entry["reason"] for entry in skipped]
    assert all("example sets differ" in entry["reason"] for entry in skipped)


def test_the_real_text_comparison_pairs_on_submissions():
    arm0 = _run("arm0", per_fold_rows=[WRONG, WRONG], test_rows=[(CLASS_NULL, CLASS_NULL)])
    armp = _run("armp", per_fold_rows=[RIGHT, RIGHT], test_rows=[(CLASS_NULL, CLASS_NULL)])

    comparisons, skipped = holdout_comparisons([arm0, armp], signal=SIGNAL)
    assert not skipped
    (entry,) = comparisons
    assert [row["fold"] for row in entry["folds"]] == [0, 1]
    assert all(row["n_pairs"] == 2 for row in entry["folds"])
    assert entry["right_better_folds"] == 2
    # Arm 0 answers `true` on the one truly-null submission in every fold; the
    # companion arm never does. That is 100 points, and the sign says which way.
    assert entry["null_to_true"]["delta_points"] == pytest.approx(100.0)


def test_a_run_that_did_not_score_the_holdout_is_a_recorded_skip():
    arm0 = _run("arm0", per_fold_rows=[RIGHT], test_rows=[(CLASS_NULL, CLASS_NULL)])
    bare = replace(arm0, name="no_holdout", folds=(replace(arm0.folds[0], holdout=None),))

    comparisons, skipped = holdout_comparisons([arm0, bare], signal=SIGNAL)
    assert not comparisons
    assert "no real-text cells" in skipped[0]["reason"]


def test_a_report_with_no_single_signal_pairs_nothing():
    arm0 = _run("arm0", per_fold_rows=[RIGHT], test_rows=[(CLASS_NULL, CLASS_NULL)])
    assert holdout_comparisons([arm0, arm0], signal=None) == ([], [])


# --------------------------------------------------------------------------
# Arm C: the margin moves and nothing else does
# --------------------------------------------------------------------------


def test_remargining_scores_the_holdout_last():
    """README rule 2, applied to the arm that only changes a threshold."""
    calls: list[str] = []

    def score_realistic(rules):
        calls.append("holdout")
        return {"margin": {SIGNAL: rules[SIGNAL].margin}}

    alt_val = {
        SIGNAL: [
            _prediction(f"val-{index}", truth, truth, scores=CONFIDENT[truth])
            for index, truth in enumerate((CLASS_TRUE, CLASS_NULL, CLASS_NULL, CLASS_TRUE))
        ]
    }
    raw = {SIGNAL: [_prediction("test-0", CLASS_NULL, CLASS_NULL, scores=CONFIDENT[CLASS_NULL])]}

    rules, ruled, realistic = remargin_multi(
        alt_val, raw_by_signal=raw, score_realistic=score_realistic
    )
    assert calls == ["holdout"]
    assert set(rules) == {SIGNAL}
    # The raw predictions are re-decided, not re-scored: same ids, same truths.
    assert [prediction.example_id for prediction in ruled[SIGNAL]] == ["test-0"]
    assert realistic == {"margin": {SIGNAL: rules[SIGNAL].margin}}


def test_remargining_refuses_a_head_with_no_alternate_validation_split():
    raw = {SIGNAL: [_prediction("test-0", CLASS_NULL, CLASS_NULL, scores=CONFIDENT[CLASS_NULL])]}
    with pytest.raises(TrainError, match="no alternate validation predictions"):
        remargin_multi({}, raw_by_signal=raw, score_realistic=lambda rules: None)


def test_arm_c_refuses_to_be_assembled_from_folds_that_were_not_remargined():
    results = [SimpleNamespace(fold_index=0, remargined=None)]
    with pytest.raises(TrainError, match="not run with a re-margining fold"):
        remargined_runs(
            results,
            signals=(SIGNAL,),
            config=FineTuneConfig(base_model="roberta-base"),
            label="ArmC",
            margin_source="ArmP",
        )


def test_arm_c_carries_the_trained_arms_folds_under_its_own_rules():
    fold_run = FoldRun.build(
        fold_index=0,
        n_train=10,
        n_val=10,
        n_test=1,
        rule=DecisionRule(margin=0.4, gated_class=CLASS_TRUE),
        raw=[_prediction("test-0", CLASS_NULL, CLASS_NULL)],
        ruled=[_prediction("test-0", CLASS_NULL, CLASS_NULL)],
    )
    results = [
        SimpleNamespace(
            fold_index=0,
            remargined=RemarginedFoldResult(
                fold_index=0,
                signals=(SIGNAL,),
                margin_source="ArmP",
                fold_runs={SIGNAL: fold_run},
            ),
        )
    ]
    runs = remargined_runs(
        results,
        signals=(SIGNAL,),
        config=FineTuneConfig(base_model="roberta-base"),
        label="ArmC_remargined",
        margin_source="`ArmP_companions`",
    )
    assert runs[SIGNAL].folds == (fold_run,)
    assert "re-selected, not retrained" in runs[SIGNAL].description
    assert not runs[SIGNAL].is_control


# --------------------------------------------------------------------------
# The generator facts the report carries beside the numbers
# --------------------------------------------------------------------------


def _sidecar(path: Path, by_label_mode: dict) -> None:
    path.write_text(
        json.dumps({"companions": {"count_by_label_mode": by_label_mode}}), encoding="utf-8"
    )


class _Split:
    """The two things `_companion_facts` asks a split for: its size and its sidecar."""

    def __init__(self, size: int, stats: dict) -> None:
        self._size = size
        self.stats = stats

    def __len__(self) -> int:
        return self._size


def _folds(train_examples: int, merged: dict):
    return [SimpleNamespace(fold_index=0, train=_Split(train_examples, {"merged_from": merged}))]


def test_companion_facts_report_the_leak_detector(tmp_path):
    """The DD5 check, permanently in the report rather than in a one-off script."""
    _sidecar(
        tmp_path / f"{SIGNAL}.fold0.train.jsonl.stats.json",
        {
            "true": {"0": 50, "1": 50},
            "false": {"0": 50, "1": 50},
            "null_structural": {"0": 40, "1": 60},
            "null_ambiguous": {"0": 50, "1": 50},
        },
    )
    facts = _companion_facts(
        tmp_path,
        (SIGNAL,),
        _folds(400, {"companion_share": 0.5, "filler_only": {"kept": 1118}}),
    )
    assert facts["companion_share"] == 0.5
    assert facts["filler_only_kept"] == 1118
    assert facts["train_splits_read"] == 1
    assert facts["companions_per_example"] == pytest.approx(0.525)
    # structural nulls draw 0.6 against everything else's 0.5: exactly the skew
    # that would make companion count a proxy for the label.
    assert facts["worst_label_mode_spread"] == pytest.approx(0.1)


def test_companion_facts_survive_a_missing_sidecar(tmp_path):
    facts = _companion_facts(tmp_path, (SIGNAL,), _folds(400, {"companion_share": 0.0}))
    assert facts["train_splits_read"] == 0
    assert facts["companions_per_example"] is None
    assert facts["worst_label_mode_spread"] is None


# --------------------------------------------------------------------------
# The three-arm report, end to end
# --------------------------------------------------------------------------

REPO = Path(__file__).resolve().parent.parent
RULESET = REPO / "data" / "uti1.json"
HOLDOUT_LABELS = REPO / "data" / "realistic" / "uti1_holdout.labels.tsv"


def _real_holdout_block(*, invents: bool):
    """A holdout block from the real labels file and a fake forward pass.

    Built through `score_holdout` rather than by hand so that the report is
    rendered against the shape the pipeline actually produces -- including the
    per-submission cells the paired comparison reads, which a hand-written
    fixture would be free to get wrong.
    """
    from scripts.encoder_training.holdout import encoder_signals, load_holdout, score_holdout

    signals = encoder_signals(RULESET)
    holdout = load_holdout(HOLDOUT_LABELS, signals=signals)
    answer = CONFIDENT[CLASS_TRUE] if invents else CONFIDENT[CLASS_NULL]

    def scorer(texts):
        return {signal: [list(answer) for _ in texts] for signal in signals}

    return score_holdout(holdout, scorer, signals=list(signals), resamples=20)


def test_the_three_arm_report_renders(tmp_path):
    """The report the ticket's deliverable is: three arms, one signal, one page."""
    from scripts.encoder_training.report import BootstrapConfig, build_report, render_markdown

    inventing = _real_holdout_block(invents=True)
    quiet = _real_holdout_block(invents=False)
    test_rows = [(CLASS_NULL, CLASS_NULL), (CLASS_TRUE, CLASS_TRUE)]

    def run(name: str, block) -> ModelRun:
        return ModelRun(
            name=name,
            kind="finetune",
            description=name,
            folds=(
                FoldRun.build(
                    fold_index=0,
                    n_train=10,
                    n_val=10,
                    n_test=len(test_rows),
                    rule=DecisionRule(margin=0.0, gated_class=CLASS_TRUE),
                    raw=[
                        _prediction(f"test-{index:04d}", truth, predicted)
                        for index, (truth, predicted) in enumerate(test_rows)
                    ],
                    ruled=[
                        _prediction(f"test-{index:04d}", truth, predicted)
                        for index, (truth, predicted) in enumerate(test_rows)
                    ],
                    holdout=block,
                ),
            ),
        )

    arm0 = run("arm_b_finetune@Arm0_control", inventing)
    armc = run("arm_b_finetune@ArmC_remargined", quiet)
    armp = _as_unpaired(run("arm_b_finetune@ArmP_companions", quiet), prefix="ArmP")

    report = build_report(
        [arm0, armc, armp],
        header={"signal": SIGNAL, "folds": 1},
        boot=BootstrapConfig(resamples=20),
        companions={
            "note": "two arms, one flag apart",
            "arms": [
                {
                    "label": "Arm0_control",
                    "dataset_dir": "data/synthetic/generated/arm0",
                    "companion_share": 0.0,
                    "train_examples": 44680,
                    "filler_only_kept": 3064,
                    "companions_per_example": 0.0,
                    "worst_label_mode_spread": 0.0,
                },
                {
                    "label": "ArmP_companions",
                    "dataset_dir": "data/synthetic/generated/armp",
                    "companion_share": 0.5,
                    "train_examples": 54410,
                    "filler_only_kept": 1118,
                    "companions_per_example": 0.752,
                    "worst_label_mode_spread": 0.0238,
                },
            ],
        },
    )

    assert report["schema_version"] >= 7
    # Arm 0 and Arm C share a test set; Arm P does not, and says so.
    assert report["comparisons"]
    assert report["skipped_comparisons"]
    # All three pair on the 67 submissions, which is where the ticket is decided.
    assert len(report["holdout_comparisons"]) == 3
    assert not report["skipped_holdout_comparisons"]

    delta = {
        (entry["left"], entry["right"]): entry["null_to_true"]["delta_points"]
        for entry in report["holdout_comparisons"]
    }
    assert delta[("arm_b_finetune@Arm0_control", "arm_b_finetune@ArmP_companions")] > 0

    markdown = render_markdown(report)
    assert "`null -> true` on real text -- the headline" in markdown
    assert "## Paired on real text" in markdown
    assert "## The datasets behind these arms" in markdown
    assert "0.0238" in markdown

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

from scripts.encoder_training.__main__ import (
    _as_unpaired,
    _cell_label,
    _cell_shares,
    _companion_facts,
    build_parser,
)
from scripts.encoder_training.dataset import CLASS_NULL, CLASS_TRUE
from scripts.encoder_training.decision import DecisionRule
from scripts.encoder_training.metrics import Prediction
from scripts.encoder_training.report import (
    FoldRun,
    ModelRun,
    _render_holdout_comparisons,
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


def test_the_paired_sentence_names_the_arm_the_gap_actually_favours():
    """The 2026-09-02 declarative sweep read backwards in six reports.

    ``delta_points`` is ``left - right``, so it is negative when the *left*
    arm invents fewer symptoms. The sentence used to append a fixed
    "in favour of `{right}`" to it regardless, which turned every arm that
    made invention worse into one the report appeared to endorse. Only the
    positive direction was covered, which is why it survived. Both directions
    are asserted here on the rendered text, because the sign in the JSON was
    never the thing that misled anyone.
    """
    better = _run("better", per_fold_rows=[RIGHT, RIGHT], test_rows=[(CLASS_NULL, CLASS_NULL)])
    worse = _run("worse", per_fold_rows=[WRONG, WRONG], test_rows=[(CLASS_NULL, CLASS_NULL)])

    def _sentence_for(left, right):
        comparisons, _ = holdout_comparisons([left, right], signal=SIGNAL)
        (entry,) = comparisons
        return entry, _render_holdout_comparisons(
            {"holdout_comparisons": comparisons, "skipped_holdout_comparisons": []}
        )

    # Right-hand arm is the better one: the gap is in its favour.
    entry, lines = _sentence_for(worse, better)
    assert entry["null_to_true"]["delta_points"] == pytest.approx(100.0)
    rendered = "\n".join(lines)
    assert "100.0 points lower** for `better`" in rendered
    assert "higher" not in rendered

    # Swap them. The same gap now runs against the right-hand arm, and the
    # sentence has to say so rather than crediting it with a negative win.
    entry, lines = _sentence_for(better, worse)
    assert entry["null_to_true"]["delta_points"] == pytest.approx(-100.0)
    rendered = "\n".join(lines)
    assert "100.0 points higher** for `worse`" in rendered
    assert "lower" not in rendered

    # Two arms that invent at the same rate are level, not a win for either.
    _, lines = _sentence_for(
        better, _run("same", per_fold_rows=[RIGHT, RIGHT], test_rows=[(CLASS_NULL, CLASS_NULL)])
    )
    assert "**level** between the two." in "\n".join(lines)


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


# --------------------------------------------------------------------------
# The declarative comparison (task 7)
#
# Guards only. What they protect is a sweep that runs for four hours, writes a
# clean report and answers a question nobody asked -- which is the failure mode
# every check here is shaped around, and none of it is visible in the output.
# --------------------------------------------------------------------------


def _cell(directory: Path, *, companion: float, declarative: float, version: int = 4) -> Path:
    """A cell's worth of sidecars: the three fields `_cell_shares` reads."""
    directory.mkdir(parents=True, exist_ok=True)
    (directory / f"{SIGNAL}.fold0.train.jsonl.stats.json").write_text(
        json.dumps(
            {
                "generator_version": version,
                "requested": {
                    "companion_share": companion,
                    "declarative_share": declarative,
                },
            }
        ),
        encoding="utf-8",
    )
    return directory


def _declarative_args(*cells: Path):
    parser = build_parser()
    argv = ["declarative-compare", "--folds", "1", "--signals", SIGNAL]
    for cell in cells:
        argv += ["--cell", str(cell)]
    return parser.parse_args(argv)


def test_cell_shares_are_read_from_the_sidecars_not_the_flags(tmp_path):
    """A directory named after the wrong cell must not be able to mislabel a column.

    The label is the report's column heading and the artefact directory's name,
    so reading it from the tree the numbers came from rather than from the run
    that read the tree is the same argument `_companion_facts` makes.
    """
    directory = _cell(tmp_path / "named-wrong", companion=0.5, declarative=0.3)
    shares = _cell_shares(directory, (SIGNAL,), 1)

    assert shares["companion_share"] == 0.5
    assert shares["declarative_share"] == 0.3
    assert shares["generator_version"] == 4
    assert _cell_label(shares) == "c0.5-d0.3"


def test_cell_shares_survive_a_missing_sidecar(tmp_path):
    shares = _cell_shares(tmp_path, (SIGNAL,), 1)

    assert shares["train_splits_read"] == 0
    assert shares["companion_share"] is None
    assert shares["declarative_share"] is None


def test_one_cell_is_not_a_comparison(tmp_path):
    args = _declarative_args(_cell(tmp_path / "a", companion=0.0, declarative=0.0))

    with pytest.raises(TrainError, match="at least two cells"):
        args.handler(args)


def test_a_repeated_directory_is_refused(tmp_path):
    """Two --cell flags at one tree is one arm trained twice, and the report
    would present the difference between two seeds as the effect of a share."""
    cell = _cell(tmp_path / "a", companion=0.0, declarative=0.3)
    args = _declarative_args(cell, cell)

    with pytest.raises(TrainError, match="repeats a directory"):
        args.handler(args)


def test_two_cells_at_the_same_shares_are_refused(tmp_path):
    """Different directories, same coordinates: still one cell, run twice.

    The directory check above cannot catch this, and this is the shape the
    mistake actually takes -- a second cell generated with a dropdown left where
    it was.
    """
    args = _declarative_args(
        _cell(tmp_path / "a", companion=0.5, declarative=0.3),
        _cell(tmp_path / "b", companion=0.5, declarative=0.3),
    )

    with pytest.raises(TrainError, match="two runs of one cell"):
        args.handler(args)


def test_a_sweep_with_no_declarative_cell_is_refused(tmp_path):
    """Every cell at declarative 0 has nothing to compare, and would report a
    null result more convincingly than a real one."""
    args = _declarative_args(
        _cell(tmp_path / "a", companion=0.0, declarative=0.0),
        _cell(tmp_path / "b", companion=0.5, declarative=0.0),
    )

    with pytest.raises(TrainError, match="nothing here to compare"):
        args.handler(args)


def test_a_path_that_does_not_exist_says_so(tmp_path):
    """Separately from the check below, because the two have different remedies
    and a typo'd path reported as a stale tree sends someone to regenerate a
    cell that was never the problem."""
    args = _declarative_args(
        _cell(tmp_path / "a", companion=0.0, declarative=0.3),
        tmp_path / "typo",
    )

    with pytest.raises(TrainError, match="no such directory"):
        args.handler(args)


def test_a_tree_whose_shares_cannot_be_read_is_refused(tmp_path):
    """A pre-version-4 tree, or one from before generate-folds forwarded the
    shares. Assuming what it was built with is how a cell ends up mislabelled in
    a report that reads as though it were checked."""
    args = _declarative_args(
        _cell(tmp_path / "a", companion=0.0, declarative=0.3),
        (tmp_path / "b").resolve(),
    )
    (tmp_path / "b").mkdir()

    with pytest.raises(TrainError, match="no companion or declarative share"):
        args.handler(args)

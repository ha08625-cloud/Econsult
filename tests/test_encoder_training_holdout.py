"""Unit tests for scripts/encoder_training/holdout.py and the order it is called in.

Pure unit tests: no database, no torch, no GPU, no network, so there is no
``pytestmark``. That is the whole point of ``holdout.py`` taking its forward
pass as a callable -- every line of the logic that decides what a real-text
number *means* runs on CI's unit job, on a runner with no ML wheels.

Three of these carry more weight than the rest.

``test_a_blank_cell_is_not_a_null`` is README rule 4. A signal the labeller
could not judge has its key omitted; ``null`` means the text raises the
territory and does not settle it. Merging them invents a label, which is the
exact failure the label-first design exists to prevent, and it would be
invisible in every number downstream.

``test_the_holdout_is_scored_after_the_margin_and_after_test`` is README rule 2.
The set never selects anything, and running it last is what makes that a
structural property rather than a promise. The test asserts the call sequence
with a recording fake rather than by reading the source.

``test_the_resampling_unit_is_the_submission`` is README rule 5. A submission
contributes up to six cells and they have to resample together; treating them
as six observations would report an interval roughly sqrt(6) too narrow on a
set whose whole limitation is how small it is.
"""

import json
import math
from pathlib import Path

import pytest

from scripts.encoder_training.dataset import CLASS_FALSE, CLASS_NULL, CLASS_TRUE
from scripts.encoder_training.decision import DecisionRule
from scripts.encoder_training.holdout import (
    HoldoutError,
    build_predictions,
    encoder_signals,
    load_holdout,
    score_holdout,
    worst_case_half_width,
)
from scripts.encoder_training.metrics import Prediction
from scripts.encoder_training.report import (
    BootstrapConfig,
    FoldRun,
    ModelRun,
    build_report,
    holdout_summary,
    render_markdown,
)
from scripts.encoder_training.train import describe_holdout, select_then_score

REPO = Path(__file__).resolve().parent.parent
RULESET = REPO / "data" / "uti1.json"
LABELS = REPO / "data" / "realistic" / "uti1_holdout.labels.tsv"
SOURCE = REPO / "data" / "realistic" / "uti1_holdout.source.txt"
README = REPO / "data" / "realistic" / "README.md"

SIGNALS = (
    "dysuria_present",
    "urinary_frequency_present",
    "nocturia_present",
    "fever_present",
    "flank_pain_present",
    "haematuria_present",
    "recent_uti_present",
)

HEADER = "\t".join(("submission_id", *SIGNALS, "text"))


def _tsv(tmp_path: Path, rows, *, header: str = HEADER) -> Path:
    path = tmp_path / "holdout.labels.tsv"
    path.write_text("\n".join([header, *rows]) + "\n", encoding="utf-8")
    return path


def _row(submission_id: str, values, text: str) -> str:
    return "\t".join((submission_id, *values, text))


def _scorer(table):
    """A fake forward pass: signal -> per-submission class scores."""

    def score(texts):
        return {signal: [list(row) for row in rows][: len(texts)] for signal, rows in table.items()}

    return score


CONFIDENT = {CLASS_FALSE: (0.9, 0.05, 0.05), CLASS_TRUE: (0.05, 0.9, 0.05)}
CONFIDENT[CLASS_NULL] = (0.05, 0.05, 0.9)


# --------------------------------------------------------------------------
# The ruleset's signal set
# --------------------------------------------------------------------------


def test_encoder_signals_are_read_from_the_real_ruleset():
    assert set(encoder_signals(RULESET)) == set(SIGNALS)


def test_a_missing_ruleset_is_an_error_rather_than_an_empty_signal_set(tmp_path):
    with pytest.raises(HoldoutError, match="ruleset not found"):
        encoder_signals(tmp_path / "nope.json")


def test_signals_are_only_those_sent_to_the_encoder(tmp_path):
    path = tmp_path / "ruleset.json"
    path.write_text(
        json.dumps(
            {
                "questions": [
                    {"answer_key": "a", "send_to_encoder": True},
                    {"answer_key": "b", "send_to_encoder": False},
                    {"answer_key": "c"},
                ]
            }
        ),
        encoding="utf-8",
    )
    assert encoder_signals(path) == ("a",)


# --------------------------------------------------------------------------
# Loading: the distinction rule 4 exists to protect
# --------------------------------------------------------------------------


def test_a_blank_cell_is_not_a_null(tmp_path):
    """README rule 4, and the reason this module validates rather than reading.

    A signal the labeller could not judge is *omitted*: excluded from the
    numerator and the denominator alike, exactly as `dataset.py` excludes a
    masked signal. A `null` is a claim -- the text raises the territory and does
    not settle it -- and a model is scored on getting it right.
    """
    labels = ["null", "", "true", "false", "null", "", "null"]
    path = _tsv(tmp_path, [_row("holdout-0001", labels, "some text")])
    holdout = load_holdout(path, signals=SIGNALS)

    submission = holdout.submissions[0]
    assert submission.classes["dysuria_present"] == CLASS_NULL
    assert "urinary_frequency_present" not in submission.classes
    assert submission.omitted == ("urinary_frequency_present", "haematuria_present")
    assert not submission.is_judged("urinary_frequency_present")

    distribution = holdout.distribution("urinary_frequency_present")
    assert distribution == {
        "false": 0,
        "true": 0,
        "null": 0,
        "omitted": 1,
        "decisive": 0,
    }


def test_an_omitted_cell_is_scored_in_neither_direction(tmp_path):
    path = _tsv(
        tmp_path,
        [
            _row("holdout-0001", ["true", *(["null"] * 6)], "judged"),
            _row("holdout-0002", ["", *(["null"] * 6)], "not judged"),
        ],
    )
    holdout = load_holdout(path, signals=SIGNALS)
    # The scorer answers `false` on both, which would be wrong on the judged row
    # and wrong on the omitted one too -- if the omitted one were scored at all.
    predictions = build_predictions(
        holdout,
        {"dysuria_present": [CONFIDENT[CLASS_FALSE], CONFIDENT[CLASS_FALSE]]},
        signals=["dysuria_present"],
    )["dysuria_present"]
    assert [prediction.example_id for prediction in predictions] == ["holdout-0001:dysuria_present"]


def test_an_unrecognised_cell_value_is_refused(tmp_path):
    path = _tsv(tmp_path, [_row("holdout-0001", ["maybe", *(["null"] * 6)], "text")])
    with pytest.raises(HoldoutError, match="will not merge them"):
        load_holdout(path, signals=SIGNALS)


def test_a_header_that_does_not_match_the_ruleset_is_refused(tmp_path):
    header = "\t".join(("submission_id", *SIGNALS[:-1], "text"))
    path = _tsv(tmp_path, [_row("holdout-0001", ["null"] * 6, "text")], header=header)
    with pytest.raises(HoldoutError, match="recent_uti_present"):
        load_holdout(path, signals=SIGNALS)


def test_an_extra_signal_column_is_refused(tmp_path):
    header = "\t".join(("submission_id", *SIGNALS, "invented_present", "text"))
    path = _tsv(tmp_path, [_row("holdout-0001", [*(["null"] * 7), "true"], "text")], header=header)
    with pytest.raises(HoldoutError, match="invented_present"):
        load_holdout(path, signals=SIGNALS)


def test_a_repeated_submission_id_is_refused(tmp_path):
    path = _tsv(
        tmp_path,
        [
            _row("holdout-0001", ["null"] * 7, "one"),
            _row("holdout-0001", ["null"] * 7, "two"),
        ],
    )
    with pytest.raises(HoldoutError, match="repeats submission id"):
        load_holdout(path, signals=SIGNALS)


def test_a_missing_labels_file_names_the_way_out(tmp_path):
    with pytest.raises(HoldoutError, match="--no-holdout"):
        load_holdout(tmp_path / "absent.tsv", signals=SIGNALS)


# --------------------------------------------------------------------------
# The real file
# --------------------------------------------------------------------------


def test_the_real_labels_file_loads_and_holds_every_submission():
    holdout = load_holdout(LABELS, signals=encoder_signals(RULESET))
    assert len(holdout) == 67
    assert holdout.submissions[0].submission_id == "holdout-0001"


def test_every_submission_id_matches_its_line_in_the_source_file():
    """Ids are assigned by line order, and the README forbids reordering.

    A shifted id attaches every recorded label to the wrong text, which no
    downstream check could detect: the file would load, the scoring would run,
    and the numbers would be nonsense.
    """
    holdout = load_holdout(LABELS, signals=encoder_signals(RULESET))
    source = SOURCE.read_text(encoding="utf-8").splitlines()
    assert len(source) == len(holdout)
    for position, submission in enumerate(holdout.submissions):
        assert submission.submission_id == f"holdout-{position + 1:04d}"
        assert submission.text.strip() == source[position].strip()


def test_the_readme_distribution_table_matches_the_labels_file():
    """DD10's third item, kept true from here on.

    The README's table was written before two labels were revised and drifted
    by two cells. It is quoted in reports, so it is worth a test rather than a
    correction that can drift again.
    """
    holdout = load_holdout(LABELS, signals=encoder_signals(RULESET))
    readme = README.read_text(encoding="utf-8")
    for signal in holdout.signals:
        distribution = holdout.distribution(signal)
        row = (
            f"| `{signal}` | {distribution['true']} | {distribution['false']} | "
            f"{distribution['null']} | **{distribution['decisive']}** |"
        )
        assert row in readme, f"README distribution row for {signal} is stale; expected {row}"


def test_no_cell_in_the_real_file_is_omitted():
    """The resolution of DD10's open question, pinned so it stays visible.

    Zero blanks is the correct state of this file and not a sign that `null`
    absorbed "cannot say": every submission is a UTI-context text, so every
    signal's territory is either raised or plainly silent, and the README
    defines silence as `null`. A blank is reserved for the labeller being unable
    to decide, which happened nowhere here. If a future submission does produce
    one, this test fails and the README section it points at is the thing to
    re-read -- not the loader, which supports the distinction either way.
    """
    holdout = load_holdout(LABELS, signals=encoder_signals(RULESET))
    blank = [submission.submission_id for submission in holdout.submissions if submission.omitted]
    assert blank == []


def test_dysuria_has_no_false_examples_and_says_so():
    """The set is very nearly a recall-only measurement on three signals."""
    holdout = load_holdout(LABELS, signals=encoder_signals(RULESET))
    scores = {"dysuria_present": [CONFIDENT[CLASS_TRUE]] * len(holdout)}
    block = score_holdout(holdout, _scorer(scores), signals=["dysuria_present"], resamples=50)
    entry = block["by_signal"][0]
    assert entry["distribution"]["false"] == 0
    assert "recall-only" in entry["caveat"]


# --------------------------------------------------------------------------
# Scoring
# --------------------------------------------------------------------------


def _two_signal_set(tmp_path) -> Path:
    return _tsv(
        tmp_path,
        [
            _row("holdout-0001", ["true", "null", "null", "false", "null", "null", "null"], "a"),
            _row("holdout-0002", ["false", "null", "null", "true", "null", "null", "null"], "b"),
            _row("holdout-0003", ["null", "null", "null", "null", "null", "null", "null"], "c"),
        ],
    )


def test_a_model_that_answers_null_everywhere_scores_nothing_on_the_decisive_slice(tmp_path):
    """The trap this block's `decisive` column exists to spring.

    Two thirds of the real set's cells are `null`, so answering "no information"
    unconditionally posts a high `all` figure while getting every cell a patient
    actually spoke about wrong.
    """
    holdout = load_holdout(_two_signal_set(tmp_path), signals=SIGNALS)
    scores = {"fever_present": [CONFIDENT[CLASS_NULL]] * 3}
    block = score_holdout(holdout, _scorer(scores), signals=["fever_present"], resamples=50)

    assert block["overall"]["accuracy"]["point"] == pytest.approx(1 / 3)
    assert block["decisive"]["accuracy"]["point"] == 0.0
    assert block["decisive"]["n_cells"] == 2


def test_the_resampling_unit_is_the_submission(tmp_path):
    """README rule 5: one submission is one observation, whatever it labels.

    Six cells from one submission are not six independent observations, so the
    bootstrap's effective n is the number of submissions and not the number of
    cells.
    """
    holdout = load_holdout(_two_signal_set(tmp_path), signals=SIGNALS)
    scores = {
        "fever_present": [CONFIDENT[CLASS_FALSE], CONFIDENT[CLASS_TRUE], CONFIDENT[CLASS_NULL]],
        "dysuria_present": [CONFIDENT[CLASS_TRUE], CONFIDENT[CLASS_FALSE], CONFIDENT[CLASS_NULL]],
    }
    block = score_holdout(
        holdout, _scorer(scores), signals=["fever_present", "dysuria_present"], resamples=50
    )
    assert block["overall"]["n_cells"] == 6
    assert block["overall"]["n_submissions"] == 3
    assert block["overall"]["accuracy"]["effective_n"] == 3
    assert block["resampling_unit"].startswith("the submission")


def test_the_margin_arrives_already_chosen_and_is_applied(tmp_path):
    """The holdout selects nothing: it is handed one margin and uses it."""
    holdout = load_holdout(_two_signal_set(tmp_path), signals=SIGNALS)
    # `true` wins on argmax by 0.1, so a margin of 0.3 demotes it to the runner-up.
    marginal = (0.1, 0.45, 0.35)
    scores = {"fever_present": [marginal, marginal, marginal]}

    argmax = score_holdout(holdout, _scorer(scores), signals=["fever_present"], resamples=20)
    gated = score_holdout(
        holdout, _scorer(scores), signals=["fever_present"], margin=0.3, resamples=20
    )
    assert argmax["by_signal"][0]["per_class"]["true"]["predicted"] == 3
    assert gated["by_signal"][0]["per_class"]["true"]["predicted"] == 0
    assert gated["margin"] == 0.3


def test_a_joint_model_scores_each_head_under_its_own_margin(tmp_path):
    """A joint model's heads each chose their own margin independently (task 3).

    There is no single number that means "the margin" for a joint model, so
    `score_holdout` also accepts a signal -> margin mapping and applies each
    head's own margin to its own cells, rather than one margin to every column.
    """
    holdout = load_holdout(_two_signal_set(tmp_path), signals=SIGNALS)
    marginal = (0.1, 0.45, 0.35)
    scores = {
        "fever_present": [marginal, marginal, marginal],
        "dysuria_present": [marginal, marginal, marginal],
    }

    block = score_holdout(
        holdout,
        _scorer(scores),
        signals=["fever_present", "dysuria_present"],
        margin={"fever_present": 0.3, "dysuria_present": 0.0},
        resamples=20,
    )
    by_signal = {entry["signal"]: entry for entry in block["by_signal"]}
    # fever_present's own 0.3 margin demotes `true` to the runner-up...
    assert by_signal["fever_present"]["per_class"]["true"]["predicted"] == 0
    assert by_signal["fever_present"]["margin"] == 0.3
    # ...but dysuria_present's own margin is plain argmax, so `true` still wins.
    assert by_signal["dysuria_present"]["per_class"]["true"]["predicted"] == 3
    assert by_signal["dysuria_present"]["margin"] == 0.0


def test_a_joint_model_missing_a_signals_margin_is_refused(tmp_path):
    holdout = load_holdout(_two_signal_set(tmp_path), signals=SIGNALS)
    scores = {"fever_present": [CONFIDENT[CLASS_NULL]] * 3}
    with pytest.raises(HoldoutError, match="no margin given for 'fever_present'"):
        score_holdout(
            holdout, _scorer(scores), signals=["fever_present"], margin={"dysuria_present": 0.1}
        )


def test_a_signal_with_no_head_is_listed_rather_than_scored(tmp_path):
    holdout = load_holdout(_two_signal_set(tmp_path), signals=SIGNALS)
    scores = {"fever_present": [CONFIDENT[CLASS_NULL]] * 3}
    block = score_holdout(holdout, _scorer(scores), signals=["fever_present"], resamples=20)
    assert block["signals_scored"] == ["fever_present"]
    assert "recent_uti_present" in block["signals_not_scored"]


def test_scoring_a_signal_the_holdout_does_not_label_is_an_error(tmp_path):
    holdout = load_holdout(_two_signal_set(tmp_path), signals=SIGNALS)
    with pytest.raises(HoldoutError, match="invented_present"):
        score_holdout(holdout, _scorer({}), signals=["invented_present"])


def test_a_scorer_returning_the_wrong_number_of_rows_is_an_error(tmp_path):
    holdout = load_holdout(_two_signal_set(tmp_path), signals=SIGNALS)

    def short(texts):
        return {"fever_present": [CONFIDENT[CLASS_NULL]]}

    with pytest.raises(HoldoutError, match="1 rows"):
        score_holdout(holdout, short, signals=["fever_present"])


def test_the_provenance_limitation_travels_with_the_number(tmp_path):
    """It is quoted, not cross-referenced. A caveat in an unopened file is none."""
    holdout = load_holdout(_two_signal_set(tmp_path), signals=SIGNALS)
    scores = {"fever_present": [CONFIDENT[CLASS_NULL]] * 3}
    block = score_holdout(holdout, _scorer(scores), signals=["fever_present"], resamples=20)
    assert "proposed by Claude and reviewed by the maintainer" in block["provenance"]
    assert "cannot rank two models" in block["power"]


def test_worst_case_half_width_is_widest_at_a_half_and_shrinks_with_n():
    assert worst_case_half_width(0) is None
    assert worst_case_half_width(67) == pytest.approx(1.96 * math.sqrt(0.25 / 67), rel=1e-3)
    assert worst_case_half_width(18) > worst_case_half_width(67)
    # 67 submissions is roughly +/-12 points, and 18 decisive cells roughly +/-23.
    assert 0.11 < worst_case_half_width(67) < 0.13
    assert 0.22 < worst_case_half_width(18) < 0.24


def test_the_line_printed_during_a_run_carries_the_count_beside_the_percentage(tmp_path):
    """A bare percentage on 18 real cells is the thing this set is misread as."""
    holdout = load_holdout(_two_signal_set(tmp_path), signals=SIGNALS)
    scores = {"fever_present": [CONFIDENT[CLASS_NULL]] * 3}
    block = score_holdout(
        holdout, _scorer(scores), signals=["fever_present"], margin=0.15, resamples=20
    )
    line = describe_holdout(block, "fever_present")
    assert "2 cells" in line
    assert "3 real submissions" in line
    assert "worst-case" in line
    assert "margin 0.15" in line
    assert "not scored" in describe_holdout(block, "nocturia_present")


# --------------------------------------------------------------------------
# The order: README rule 2, asserted by construction
# --------------------------------------------------------------------------


def test_the_holdout_is_scored_after_the_margin_and_after_test(monkeypatch):
    """The holdout can select nothing because there is nothing left to select.

    Asserted with a recording fake rather than by reading `run_finetune_fold`:
    the ordering lives in `select_then_score` precisely so it can be checked
    here, with no torch, no GPU and no encoder.
    """
    calls: list[str] = []
    rule = DecisionRule(margin=0.25)

    def fake_select(predictions):
        calls.append("select_margin")
        return rule

    monkeypatch.setattr("scripts.encoder_training.train.select_margin", fake_select)

    def score_test(chosen):
        calls.append("score_test")
        assert chosen is rule
        return []

    def score_realistic(chosen):
        calls.append("score_holdout")
        assert chosen is rule
        return {"margin": chosen.margin}

    returned, predictions, realistic = select_then_score(
        [], score_test=score_test, score_realistic=score_realistic
    )

    assert calls == ["select_margin", "score_test", "score_holdout"]
    assert returned is rule
    assert predictions == []
    assert realistic == {"margin": 0.25}


def test_the_holdout_sees_the_margin_selected_on_validation(monkeypatch):
    """Not argmax, and not a margin of its own: the fold's chosen one."""
    seen: list[float] = []
    monkeypatch.setattr(
        "scripts.encoder_training.train.select_margin",
        lambda predictions: DecisionRule(margin=0.4),
    )
    select_then_score(
        [],
        score_test=lambda chosen: [],
        score_realistic=lambda chosen: seen.append(chosen.margin),
    )
    assert seen == [0.4]


# --------------------------------------------------------------------------
# The report block
# --------------------------------------------------------------------------


def _prediction(example_id: str, truth: int, predicted: int) -> Prediction:
    return Prediction(
        example_id=example_id,
        truth=truth,
        predicted=predicted,
        unit="cluster-1",
        label_mode="null_ambiguous",
        library="fever_null_hedged",
        subclass="hedged",
        fragment_id="fever_null_hedged:0001",
    )


def _fold_run(fold_index: int, holdout: dict | None) -> FoldRun:
    predictions = [
        _prediction("test-000001", CLASS_TRUE, CLASS_TRUE),
        _prediction("test-000002", CLASS_NULL, CLASS_NULL),
    ]
    return FoldRun.build(
        fold_index=fold_index,
        n_train=10,
        n_val=2,
        n_test=2,
        rule=DecisionRule(margin=0.0),
        raw=predictions,
        ruled=predictions,
        holdout=holdout,
    )


def _holdout_block(accuracy: float) -> dict:
    slice_block = {
        "n_cells": 3,
        "n_submissions": 3,
        "confusion": [[0, 0, 0], [1, 1, 0], [0, 0, 1]],
        "accuracy": {
            "point": accuracy,
            "low": 0.0,
            "high": 1.0,
            "effective_n": 3,
            "resamples_used": 20,
        },
        "macro_f1": accuracy,
        "worst_case_half_width": 0.56,
    }
    return {
        "path": "data/realistic/uti1_holdout.labels.tsv",
        "n_submissions": 3,
        "signals_scored": ["fever_present"],
        "signals_not_scored": ["recent_uti_present"],
        "margin": 0.0,
        "selected_nothing": "scored after the margin was selected",
        "resampling_unit": "the submission",
        "bootstrap": {"resamples": 20, "seed": 0, "alpha": 0.05},
        "overall": slice_block,
        "decisive": slice_block,
        "by_signal": [
            {
                "signal": "fever_present",
                "distribution": {
                    "true": 1,
                    "false": 1,
                    "null": 1,
                    "omitted": 0,
                    "decisive": 2,
                },
                "all": slice_block,
                "decisive": slice_block,
                "per_class": {
                    "false": {"support": 1, "predicted": 1, "recall": 1.0, "precision": 1.0},
                    "true": {"support": 1, "predicted": 1, "recall": accuracy, "precision": 1.0},
                    "null": {"support": 1, "predicted": 1, "recall": 1.0, "precision": 1.0},
                },
                "null_to_true": {"count": 0, "null_support": 1},
            }
        ],
        "provenance": "The labels were proposed by Claude and reviewed by the maintainer.",
        "voice": "67 submissions written by one person share that person's voice.",
        "power": "This set cannot rank two models.",
    }


def _run_with_holdout(*accuracies: float) -> ModelRun:
    return ModelRun(
        name="arm_b_finetune",
        kind="finetune",
        description="a fine-tune",
        folds=tuple(
            _fold_run(index, _holdout_block(accuracy)) for index, accuracy in enumerate(accuracies)
        ),
    )


def test_the_folds_are_averaged_rather_than_pooled():
    """Five folds are five models on one sample of 67, not a sample of 335."""
    summary = holdout_summary(_run_with_holdout(0.4, 0.6))
    assert summary["n_submissions"] == 3
    assert summary["overall"]["n_submissions"] == 3
    assert summary["overall"]["accuracy"]["mean"] == pytest.approx(0.5)
    assert summary["overall"]["accuracy"]["sd"] == pytest.approx(0.1414, rel=1e-2)
    assert summary["overall"]["accuracy"]["values"] == [0.4, 0.6]
    assert "not pooled" in summary["not_pooled"]


def test_a_run_that_did_not_score_the_holdout_carries_no_block():
    run = ModelRun(
        name="baseline",
        kind="baseline",
        description="no holdout here",
        folds=(_fold_run(0, None),),
    )
    assert holdout_summary(run) is None


def test_a_partially_scored_holdout_is_an_error():
    run = ModelRun(
        name="arm_b_finetune",
        kind="finetune",
        description="a fine-tune",
        folds=(_fold_run(0, _holdout_block(0.5)), _fold_run(1, None)),
    )
    with pytest.raises(ValueError, match="1 of 2 folds"):
        holdout_summary(run)


def test_folds_that_scored_different_files_are_an_error():
    first = _holdout_block(0.5)
    second = _holdout_block(0.5)
    second["path"] = "somewhere/else.tsv"
    run = ModelRun(
        name="arm_b_finetune",
        kind="finetune",
        description="a fine-tune",
        folds=(_fold_run(0, first), _fold_run(1, second)),
    )
    with pytest.raises(ValueError, match="different holdout files"):
        holdout_summary(run)


def test_the_report_prints_both_ns_beside_each_other():
    """A holdout number next to a recombination number must print both `n`s."""
    report = build_report(
        [_run_with_holdout(0.4, 0.6)],
        header={"signal": "fever_present"},
        boot=BootstrapConfig(resamples=20),
    )
    assert report["schema_version"] >= 5
    markdown = render_markdown(report)

    assert "## The real-text holdout" in markdown
    assert "Recombination test slice" in markdown
    assert "n 3** submissions" in markdown
    assert "cannot rank two models" in markdown
    assert "proposed by Claude and reviewed by the maintainer" in markdown
    assert "recent_uti_present" in markdown


def test_a_report_without_a_holdout_prints_no_holdout_section():
    """No empty heading: it would read as "the check ran and found nothing"."""
    run = ModelRun(
        name="baseline",
        kind="baseline",
        description="no holdout here",
        folds=(_fold_run(0, None),),
    )
    report = build_report(
        [run], header={"signal": "fever_present"}, boot=BootstrapConfig(resamples=20)
    )
    assert report["models"][0]["holdout"] is None
    assert "## The real-text holdout" not in render_markdown(report)

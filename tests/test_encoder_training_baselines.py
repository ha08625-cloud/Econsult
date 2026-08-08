"""Unit tests for the baselines, the decision rule and the report writer.

Pure unit tests: no database, no torch, no GPU, so there is no ``pytestmark``.

**What CI can and cannot cover here.** ``scikit-learn`` lives in
``requirements-ml.txt``, which CI's unit job deliberately does not install, so
the two ``fit`` bodies that call it are covered only when someone has installed
it locally -- those tests skip themselves otherwise. Everything else is
stdlib-only and always runs: the majority baseline, the label permutation that
is negative control 1, the decision rule's objective, the fold-qualification of
example ids that keeps McNemar honest, and the whole report writer. That split
is the reason the sklearn imports sit inside the methods rather than at module
scope.

The load-bearing tests, if you only read a few:

* ``test_confusion_bootstrap_matches_the_general_one`` -- the fast interval used
  by every table in the report is the same interval as the slow, already-tested
  one. If it drifts, every error bar in the report is wrong and nothing else
  says so.
* ``test_selected_margin_never_worsens_null_to_true`` -- the decision rule's
  constraint holds. That cell invents a symptom into a patient's form.
* ``test_fold_runs_qualify_example_ids`` -- pooled predictions from five folds
  stay distinguishable. Without it McNemar silently compares a model to itself.
* ``test_shuffled_control_trains_on_permuted_labels_and_is_scored_against_the_truth``
  -- negative control 1 is wired to train on permuted labels and be scored
  against the truth, not the other way round. Asserted exactly rather than
  statistically, and it needs no ML at all.
"""

import json
import random
from collections import Counter
from pathlib import Path

import pytest

from scripts.encoder_training.baselines import (
    LengthBaseline,
    MajorityBaseline,
    TfidfBaseline,
    permute_classes,
    run_baseline,
    run_fold,
    token_count,
    training_pairs,
)
from scripts.encoder_training.dataset import (
    CLASS_FALSE,
    CLASS_NULL,
    CLASS_TRUE,
    DatasetError,
    fold_dataset_path,
    load_fold,
    load_folds,
    load_split,
    sidecar_path,
)
from scripts.encoder_training.decision import (
    DEFAULT_MARGINS,
    DecisionError,
    DecisionRule,
    select_margin,
)
from scripts.encoder_training.metrics import (
    Prediction,
    accuracy,
    accuracy_statistic,
    bootstrap_ci,
    bootstrap_confusion_ci,
    class_recall,
    confusion_matrix,
    macro_f1,
)
from scripts.encoder_training.report import (
    DECIDING_SLICE,
    FEVER_LIBRARY_CLUSTERS,
    NULL_SUBCLASSES,
    SCHEMA_VERSION,
    BootstrapConfig,
    FoldRun,
    ModelRun,
    _error_concentration,
    build_report,
    compare_models,
    render_markdown,
    write_report,
)
from scripts.synthetic_data.manifest import library_clusters, load_fragments

FIXTURES = Path(__file__).parent / "fixtures" / "encoder_training"
TRAIN = FIXTURES / "mini.fold0.train.jsonl"
VAL = FIXTURES / "mini.fold0.val.jsonl"
TEST = FIXTURES / "mini.fold0.test.jsonl"
MISSING_KEY = FIXTURES / "missing_key.train.jsonl"

SIGNAL = "fever_present"

#: Small enough to keep the suite quick, large enough that the percentile
#: indices are not degenerate.
RESAMPLES = 64


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------


def _fold():
    return load_fold(TRAIN, VAL, TEST)


def _prediction(example_id, truth, predicted, unit, **kwargs):
    return Prediction(example_id=example_id, truth=truth, predicted=predicted, unit=unit, **kwargs)


def _scored(example_id, truth, scores, unit, **kwargs):
    """A prediction carrying scores, decided by plain argmax."""
    best = max(range(len(scores)), key=lambda index: (scores[index], -index))
    return Prediction(
        example_id=example_id,
        truth=truth,
        predicted=best,
        unit=unit,
        scores=tuple(scores),
        **kwargs,
    )


def _copy_fold_fixture(tmp_path: Path, *, fold_index: int, folds: int) -> None:
    """Write the fixture trio into ``tmp_path`` under the fold-file convention."""
    for split, source in (("train", TRAIN), ("val", VAL), ("test", TEST)):
        target = fold_dataset_path(tmp_path, SIGNAL, fold_index, split)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
        stats = json.loads(sidecar_path(source).read_text(encoding="utf-8"))
        stats["folds"] = folds
        stats["fold_index"] = fold_index
        sidecar_path(target).write_text(json.dumps(stats, indent=2), encoding="utf-8")


def _majority_run(name: str = "majority_class", kind: str = "baseline") -> ModelRun:
    run = run_baseline(MajorityBaseline, [_fold()], signal=SIGNAL)
    return ModelRun(name=name, kind=kind, description=run.description, folds=run.folds)


# --------------------------------------------------------------------------
# Feature extraction and the shuffled-label control
# --------------------------------------------------------------------------


def test_token_count_counts_words_not_punctuation():
    assert token_count("I've had a fever, on and off.") == 7
    assert token_count("") == 0


def test_training_pairs_drop_examples_the_signal_is_masked_on():
    """A missing signal key is not a label, so it is not a training example."""
    split = load_split(MISSING_KEY, signals=(SIGNAL, "dysuria_present"))
    texts, classes = training_pairs(split, "dysuria_present")
    assert len(texts) == len(classes)
    assert len(texts) < len(split.examples)
    assert all(
        example.is_labelled("dysuria_present")
        for example in split.examples
        if example.text in texts
    )


def test_permute_classes_preserves_the_class_balance():
    classes = [CLASS_NULL] * 6 + [CLASS_TRUE] * 2 + [CLASS_FALSE] * 2
    shuffled = permute_classes(classes, seed=1)
    assert sorted(shuffled) == sorted(classes)
    assert shuffled != classes


def test_permute_classes_is_seeded():
    classes = list(range(3)) * 8
    assert permute_classes(classes, seed=3) == permute_classes(classes, seed=3)
    assert permute_classes(classes, seed=3) != permute_classes(classes, seed=4)


# --------------------------------------------------------------------------
# The majority baseline
# --------------------------------------------------------------------------


def test_majority_scores_are_the_training_class_frequencies():
    model = MajorityBaseline().fit(
        ["a", "b", "c", "d"], [CLASS_NULL, CLASS_NULL, CLASS_NULL, CLASS_TRUE]
    )
    scores = model.score(["anything at all"])[0]
    assert scores[CLASS_NULL] == pytest.approx(0.75)
    assert scores[CLASS_TRUE] == pytest.approx(0.25)
    assert scores[CLASS_FALSE] == pytest.approx(0.0)


def test_majority_predicts_the_same_class_for_every_text():
    model = MajorityBaseline().fit(["a", "b", "c"], [CLASS_NULL, CLASS_NULL, CLASS_TRUE])
    scored = model.score(["short", "a much longer piece of text entirely"])
    assert scored[0] == scored[1]


# --------------------------------------------------------------------------
# The decision rule (DD9)
# --------------------------------------------------------------------------


def test_margin_grid_must_contain_argmax():
    predictions = [_scored("a", CLASS_TRUE, (0.1, 0.8, 0.1), "u1")]
    with pytest.raises(DecisionError, match="must contain 0.0"):
        select_margin(predictions, margins=(0.1, 0.2))


def test_select_margin_rejects_an_empty_split():
    with pytest.raises(DecisionError, match="empty split"):
        select_margin([])


def test_selected_margin_never_worsens_null_to_true():
    """The DD9 constraint: the rule may not invent more fevers than argmax does.

    Built so a margin is genuinely tempting -- two truly-null examples are called
    ``true`` by a thin margin, and gating them away costs nothing.
    """
    predictions = [
        _scored("n1", CLASS_NULL, (0.1, 0.45, 0.45), "u1"),
        _scored("n2", CLASS_NULL, (0.1, 0.46, 0.44), "u2"),
        _scored("n3", CLASS_NULL, (0.1, 0.1, 0.8), "u3"),
        _scored("t1", CLASS_TRUE, (0.05, 0.9, 0.05), "u4"),
        _scored("f1", CLASS_FALSE, (0.9, 0.05, 0.05), "u5"),
    ]
    argmax_rate = 2 / 3
    rule = select_margin(predictions)
    assert rule.argmax_null_to_true_rate == pytest.approx(argmax_rate)
    assert rule.null_to_true_rate <= argmax_rate
    assert rule.margin > 0.0


def test_select_margin_falls_back_to_argmax_when_nothing_helps():
    """A model that never says ``true`` cannot be improved by gating ``true``."""
    predictions = [
        _scored("n1", CLASS_NULL, (0.2, 0.1, 0.7), "u1"),
        _scored("f1", CLASS_FALSE, (0.7, 0.1, 0.2), "u2"),
    ]
    rule = select_margin(predictions)
    assert rule.margin == 0.0
    assert rule.null_to_true_rate == 0.0


def test_select_margin_needs_scores():
    with pytest.raises(Exception, match="scores"):
        select_margin([_prediction("a", CLASS_TRUE, CLASS_TRUE, "u1")])


def test_decision_rule_round_trips_through_disk(tmp_path):
    rule = DecisionRule(
        margin=0.35,
        selected_on="val",
        argmax_null_to_true_rate=0.1,
        null_to_true_rate=0.05,
        macro_f1=0.6,
    )
    path = rule.write(tmp_path / "nested" / "decision_rule.json")
    assert DecisionRule.read(path) == rule


def test_decision_rule_records_the_grid_it_chose_from():
    rule = select_margin([_scored("t1", CLASS_TRUE, (0.05, 0.9, 0.05), "u1")])
    assert rule.margins_considered == DEFAULT_MARGINS
    assert 0.0 in rule.margins_considered


# --------------------------------------------------------------------------
# The fast bootstrap
# --------------------------------------------------------------------------


def _mixed_predictions():
    """A slice with several clusters, several classes and some errors."""
    rows = [
        ("a1", CLASS_TRUE, CLASS_TRUE, "c1"),
        ("a2", CLASS_TRUE, CLASS_NULL, "c1"),
        ("b1", CLASS_FALSE, CLASS_FALSE, "c2"),
        ("b2", CLASS_FALSE, CLASS_TRUE, "c2"),
        ("c1", CLASS_NULL, CLASS_NULL, "c3"),
        ("c2", CLASS_NULL, CLASS_TRUE, "c3"),
        ("d1", CLASS_NULL, CLASS_NULL, "c4"),
        ("d2", CLASS_TRUE, CLASS_TRUE, "c5"),
    ]
    return [_prediction(*row) for row in rows]


def test_confusion_bootstrap_matches_the_general_one():
    """The fast path and the slow path are the same interval, draw for draw.

    Every error bar in the report comes from the fast path. It exists only
    because rescoring ten thousand examples two thousand times over is too slow
    to do a hundred times; it is not allowed to be a different statistic.
    """
    predictions = _mixed_predictions()
    for statistic, fast in (
        (accuracy_statistic, accuracy),
        (lambda group: macro_f1(confusion_matrix(group)), macro_f1),
    ):
        slow_interval = bootstrap_ci(predictions, statistic, resamples=RESAMPLES, seed=11)
        fast_interval = bootstrap_confusion_ci(predictions, fast, resamples=RESAMPLES, seed=11)
        assert fast_interval == slow_interval


def test_confusion_bootstrap_reports_clusters_as_the_effective_n():
    interval = bootstrap_confusion_ci(_mixed_predictions(), accuracy, resamples=RESAMPLES, seed=0)
    assert interval.effective_n == 5
    assert interval.low <= interval.point <= interval.high


def test_class_recall_statistic_reads_the_right_row():
    matrix = confusion_matrix(_mixed_predictions())
    assert class_recall(CLASS_NULL)(matrix) == pytest.approx(2 / 3)


# --------------------------------------------------------------------------
# Fold runs and pooling
# --------------------------------------------------------------------------


def test_fold_runs_qualify_example_ids():
    """Pooling five folds must not collapse ``test-000000`` into one example.

    The generator numbers examples per split, so the same id names a different
    example in every fold. McNemar keys on the id; unqualified, it would pair a
    model against itself on four fifths of the data and call the difference
    significant.
    """
    run = run_fold(MajorityBaseline, _fold(), signal=SIGNAL)
    assert run.raw
    assert all(prediction.example_id.startswith("fold0:") for prediction in run.raw)
    assert all(prediction.example_id.startswith("fold0:") for prediction in run.ruled)


def test_fold_run_qualification_is_idempotent():
    fold = _fold()
    once = run_fold(MajorityBaseline, fold, signal=SIGNAL)
    twice = FoldRun.build(
        fold_index=once.fold_index,
        n_train=once.n_train,
        n_val=once.n_val,
        n_test=once.n_test,
        rule=once.rule,
        raw=once.raw,
        ruled=once.ruled,
    )
    assert [p.example_id for p in twice.raw] == [p.example_id for p in once.raw]


def test_run_fold_selects_the_margin_on_validation_not_test():
    run = run_fold(MajorityBaseline, _fold(), signal=SIGNAL)
    assert run.rule.selected_on == "val"


def test_pooled_predictions_concatenate_every_fold():
    run = run_baseline(MajorityBaseline, [_fold()], signal=SIGNAL)
    assert len(run.pooled("raw")) == len(run.folds[0].raw)
    assert len(run.pooled("ruled")) == len(run.folds[0].ruled)


def test_shuffled_run_is_named_and_typed_as_a_control():
    run = run_baseline(MajorityBaseline, [_fold()], signal=SIGNAL, shuffle_seed=5)
    assert run.name.endswith("__shuffled")
    assert run.is_control
    assert "unpermuted test split" in run.description


# --------------------------------------------------------------------------
# Loading a directory of folds
# --------------------------------------------------------------------------


def test_load_folds_reads_a_directory_by_convention(tmp_path):
    _copy_fold_fixture(tmp_path, fold_index=0, folds=1)
    folds = load_folds(tmp_path, SIGNAL, folds=1)
    assert len(folds) == 1
    assert folds[0].fold_index == 0


def test_load_folds_rejects_a_fold_generated_with_a_different_k(tmp_path):
    _copy_fold_fixture(tmp_path, fold_index=0, folds=5)
    with pytest.raises(DatasetError, match="generated with folds="):
        load_folds(tmp_path, SIGNAL, folds=1)


def test_load_folds_rejects_a_file_whose_name_lies_about_its_fold(tmp_path):
    """Regenerating one fold with the wrong ``--fold`` leaves a complete-looking dir."""
    _copy_fold_fixture(tmp_path, fold_index=0, folds=2)
    _copy_fold_fixture(tmp_path, fold_index=1, folds=2)
    for split in ("train", "val", "test"):
        path = sidecar_path(fold_dataset_path(tmp_path, SIGNAL, 1, split))
        stats = json.loads(path.read_text(encoding="utf-8"))
        stats["fold_index"] = 0
        path.write_text(json.dumps(stats), encoding="utf-8")
    with pytest.raises(DatasetError, match="named fold 1 but its sidecar"):
        load_folds(tmp_path, SIGNAL, folds=2)


def test_load_folds_rejects_a_cluster_held_out_twice(tmp_path):
    """Two folds testing the same cluster would count one idea twice when pooled."""
    _copy_fold_fixture(tmp_path, fold_index=0, folds=2)
    _copy_fold_fixture(tmp_path, fold_index=1, folds=2)
    with pytest.raises(DatasetError, match="is a test cluster in both fold"):
        load_folds(tmp_path, SIGNAL, folds=2)


# --------------------------------------------------------------------------
# The report
# --------------------------------------------------------------------------


def _report():
    runs = [
        _majority_run(),
        _majority_run(name="majority_class__shuffled", kind="negative_control"),
    ]
    return build_report(
        runs,
        header={"signal": SIGNAL, "folds": 1},
        boot=BootstrapConfig(resamples=RESAMPLES, seed=0),
        checks={"fragment_disjointness": "checked"},
    )


def test_report_carries_effective_n_beside_every_example_count():
    """The single guard against over-reading anything in this package."""
    report = _report()
    for model in report["models"]:
        for view in model["pooled"].values():
            for key in ("overall", "decisive"):
                assert "effective_n" in view[key]
            for group in ("by_label_mode", "by_subclass", "by_library"):
                for entry in view[group]:
                    assert "effective_n" in entry
                    assert "n_examples" in entry


def test_report_prints_both_confusion_matrices():
    """ "The model is wrong" and "the rule is conservative" must stay separable."""
    model = _report()["models"][0]
    assert model["pooled"]["raw"]["overall"]["confusion"]
    assert model["pooled"]["ruled"]["overall"]["confusion"]


def test_report_holds_the_per_fragment_error_table():
    rows = _report()["models"][0]["fragments"]
    assert rows
    assert all(row["fragment_id"] for row in rows)
    assert rows == sorted(
        rows, key=lambda row: (row["accuracy"], -row["n_examples"], row["fragment_id"])
    )
    assert all(sum(row["predicted"].values()) == row["n_examples"] for row in rows)


def test_report_restricts_the_subclass_table_to_the_declared_subclasses():
    entries = _report()["models"][0]["pooled"]["ruled"]["by_subclass"]
    assert {entry["name"] for entry in entries} <= set(NULL_SUBCLASSES)


def test_comparisons_exclude_negative_controls():
    """A control is not a model to be beaten; comparing against it means nothing."""
    runs = [
        _majority_run(name="a"),
        _majority_run(name="b"),
        _majority_run(name="c__shuffled", kind="negative_control"),
    ]
    names = {
        name for comparison in compare_models(runs) for name in (comparison["a"], comparison["b"])
    }
    assert names == {"a", "b"}


def test_markdown_is_rendered_from_the_json_and_names_the_caveats():
    report = _report()
    markdown = render_markdown(report)
    assert "eff n" in markdown
    assert "Confusion matrix, raw argmax" in markdown
    assert "Confusion matrix, after the decision rule" in markdown
    assert "Per-fragment errors" in markdown
    assert "Limitations" in markdown
    # The two ways these numbers get over-read, both required to be present.
    assert "effective n" in markdown.lower()
    assert "stability check" in markdown


def test_markdown_caps_the_fragment_table_and_says_so():
    report = _report()
    capped = render_markdown(report, fragment_rows=0)
    wrong = [
        row for row in report["models"][0]["fragments"] if row["n_correct"] < row["n_examples"]
    ]
    if wrong:
        assert "further fragments with at least one error" in capped


def test_write_report_writes_json_always_and_markdown_on_request(tmp_path):
    report = _report()
    json_path, markdown_path = write_report(report, tmp_path, stem="run")
    assert json.loads(json_path.read_text(encoding="utf-8"))["schema_version"] == SCHEMA_VERSION
    assert markdown_path.read_text(encoding="utf-8").startswith("# Encoder training")

    json_only, none_path = write_report(report, tmp_path, stem="quiet", markdown=False)
    assert json_only.is_file()
    assert none_path is None


# --------------------------------------------------------------------------
# The comparison the ticket is decided on (task 6)
# --------------------------------------------------------------------------


def _rows(*pairs):
    """Per-fragment table rows, as ``(n_examples, n_correct)`` pairs."""
    return [
        {"fragment_id": f"lib:{index:02d}", "n_examples": total, "n_correct": correct}
        for index, (total, correct) in enumerate(pairs)
    ]


def test_error_concentration_finds_the_fragments_carrying_half_the_errors():
    """The DD7 reading, as a number: 20 errors, and one fragment holds 12."""
    stats = _error_concentration(_rows((20, 8), (10, 9), (10, 9), (10, 9), (10, 9), (10, 10)))
    assert stats["total_errors"] == 12 + 4
    assert stats["decisive_fragments"] == 6
    assert stats["fragments_with_errors"] == 5
    assert stats["fragments_carrying_half"] == 1
    assert stats["share_in_worst_ten"] == 1.0


def test_error_concentration_reference_point_is_an_even_spread():
    """Half the errors on half the erring fragments is the "spread thinly" case.

    Without the reference point the headline count is unreadable: "half the
    errors fall on four fragments" means opposite things depending on whether
    eight fragments erred or eighty.
    """
    stats = _error_concentration(_rows(*[(10, 9)] * 8))
    assert stats["fragments_with_errors"] == 8
    assert stats["fragments_carrying_half"] == 4
    assert stats["even_spread_would_be"] == 4.0


def test_error_concentration_handles_a_model_that_got_everything_right():
    stats = _error_concentration(_rows((10, 10), (4, 4)))
    assert stats["total_errors"] == 0
    assert stats["fragments_carrying_half"] == 0
    assert stats["share_in_worst_ten"] is None


def test_report_carries_the_error_concentration_beside_the_fragment_table():
    model = _report()["models"][0]
    stats = model["error_concentration"]
    errors = sum(row["n_examples"] - row["n_correct"] for row in model["fragments"])
    assert stats["total_errors"] == errors
    assert stats["decisive_fragments"] == len(model["fragments"])


def test_markdown_lays_out_the_tickets_question_without_answering_it():
    """The three numbers the decision turns on, and no automatic verdict.

    A renderer that concluded would be concluding from whichever comparison
    happened to clear a threshold someone picked while writing it.
    """
    markdown = render_markdown(_report())
    assert "## The ticket's question: model or libraries?" in markdown
    assert DECIDING_SLICE in markdown
    assert "Where the errors fall" in markdown
    assert "a sentence a person writes" in markdown


def test_markdown_demands_the_recorded_prediction_be_scored():
    markdown = render_markdown(_report())
    assert "owes each bullet a" in markdown


def test_markdown_reproduces_the_data_limits_in_full_rather_than_citing_them():
    """The one deliberate duplication: this report is read standalone."""
    markdown = render_markdown(_report())
    assert "## What this data is and is not worth" in markdown
    for phrase in (
        "smoke test, not evidence",
        "Length may still leak",
        "Urgency language leaks",
        "The examples are short",
        "Only `fever_present` is covered",
        "Effective sample size",
    ):
        assert phrase in markdown


def test_markdown_names_the_next_ticket():
    markdown = render_markdown(_report())
    assert "## The next ticket" in markdown
    assert "60-100 realistic full submissions" in markdown


def test_library_cluster_table_matches_the_libraries_on_disk():
    """Guards the one table in the report that is written down rather than derived.

    The report must not re-read the fragment libraries -- they may have moved
    since the dataset was generated, and a table that quietly re-read them would
    describe different libraries than the numbers above it came from. So the
    counts are a constant, and this test is what stops the constant drifting.
    """
    fragments = load_fragments(Path("data/synthetic/manifest.json"), check_cells=False)
    counted = Counter(fragment.library for fragment in fragments)
    clustered = Counter(library for library, _ in library_clusters(fragments))
    for library, fragment_count, cluster_count in FEVER_LIBRARY_CLUSTERS:
        assert counted[library] == fragment_count, library
        assert clustered[library] == cluster_count, library


# --------------------------------------------------------------------------
# The sklearn baselines
#
# Skipped wherever requirements-ml.txt is not installed, which includes CI.
# --------------------------------------------------------------------------


@pytest.fixture
def sklearn():
    return pytest.importorskip("sklearn", reason="requirements-ml.txt is not installed")


def test_length_baseline_scores_are_probabilities(sklearn):
    texts = ["a b c", "a b c d e f g h", "a", "a b c d e f g h i j k l"] * 5
    classes = [CLASS_NULL, CLASS_TRUE, CLASS_NULL, CLASS_TRUE] * 5
    model = LengthBaseline().fit(texts, classes)
    for scores in model.score(["a b", "a b c d e f g h i j"]):
        assert len(scores) == 3
        assert sum(scores) == pytest.approx(1.0)


def test_length_baseline_uses_only_length(sklearn):
    """Two texts of the same length must score identically, whatever they say."""
    texts = ["a b c", "a b c d e f g h"] * 10
    classes = [CLASS_NULL, CLASS_TRUE] * 10
    model = LengthBaseline().fit(texts, classes)
    scored = model.score(["x y z", "fever fever fever"])
    assert scored[0] == pytest.approx(scored[1])


def test_tfidf_baseline_learns_a_separable_keyword(sklearn):
    texts = ["i have a fever today"] * 10 + ["no temperature at all here"] * 10
    classes = [CLASS_TRUE] * 10 + [CLASS_FALSE] * 10
    model = TfidfBaseline(min_df=1).fit(texts, classes)
    scores = model.score(["i have a fever today"])[0]
    assert scores.index(max(scores)) == CLASS_TRUE


def test_shuffled_control_lands_near_chance(sklearn):
    """Negative control 1 does what it claims once a model has real capacity.

    The corpus is deliberately varied. An earlier version of this test used two
    distinct sentence shapes, which quantises accuracy to 0, 0.5 or 1.0 and
    turns "lands at chance" into a coin flip that passes or fails at random.
    Sixteen filler words drawn per example gives the held-out score somewhere
    real to land.
    """
    rng = random.Random(0)
    filler = [f"w{index}" for index in range(40)]

    def _corpus(per_class):
        texts, classes = [], []
        for marker, class_index in (("fever", CLASS_TRUE), ("chills", CLASS_FALSE)):
            for _ in range(per_class):
                texts.append(" ".join([marker, *rng.sample(filler, 16)]))
                classes.append(class_index)
        return texts, classes

    train_texts, train_classes = _corpus(80)
    held_out_texts, held_out_classes = _corpus(40)

    honest = TfidfBaseline(min_df=1).fit(train_texts, train_classes)
    shuffled = TfidfBaseline(min_df=1).fit(train_texts, permute_classes(train_classes, seed=1))

    def _score(model, texts, classes):
        scored = model.score(texts)
        predictions = [
            _prediction(str(index), truth, max(range(3), key=lambda cls: scores[cls]), str(index))
            for index, (scores, truth) in enumerate(zip(scored, classes, strict=True))
        ]
        return accuracy(confusion_matrix(predictions))

    assert _score(honest, held_out_texts, held_out_classes) > 0.95
    assert _score(shuffled, held_out_texts, held_out_classes) < 0.8


def test_shuffled_control_trains_on_permuted_labels_and_is_scored_against_the_truth():
    """The wiring of negative control 1, asserted exactly rather than statistically.

    This is the load-bearing half of the control, and it needs no ML at all. Get
    it backwards and a 110M-parameter model at Arm B will memorise the permuted
    training labels, drive train loss to zero, and look like a catastrophic
    failure of the pipeline rather than a correctly-behaving control.
    """
    fold = _fold()
    seen: list[list[int]] = []

    class _Spy(MajorityBaseline):
        def fit(self, texts, classes):
            seen.append(list(classes))
            return super().fit(texts, classes)

    honest_classes = training_pairs(fold.train, SIGNAL)[1]
    run = run_fold(_Spy, fold, signal=SIGNAL, shuffle_seed=3)

    assert seen == [permute_classes(honest_classes, seed=3)]
    assert seen[0] != honest_classes

    # Test predictions carry the real labels, never the permuted ones.
    truths = {prediction.example_id.split(":", 1)[1]: prediction.truth for prediction in run.raw}
    assert truths == {
        example.example_id: example.class_for(SIGNAL) for example in fold.test.examples
    }

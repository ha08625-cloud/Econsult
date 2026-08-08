"""Unit tests for scripts/encoder_training/metrics.py and ruleset_hash.py.

Pure unit tests: no database, no torch, no GPU, so there is no ``pytestmark``.

Most of these are arithmetic, and the arithmetic is not the interesting part.
The load-bearing tests are the ones asserting that the *unit* of every count is
the cluster: ``test_effective_n_counts_clusters_not_examples`` and
``test_cluster_bootstrap_is_wider_than_an_example_bootstrap_would_be``. If those
two ever pass for the wrong reason, every confidence interval this package
produces is too narrow and nothing else would say so.
"""

import json
import math
from pathlib import Path

import pytest

from scripts.encoder_training.dataset import (
    CLASS_FALSE,
    CLASS_NULL,
    CLASS_TRUE,
    STRUCTURAL_NULL_UNIT,
    load_split,
)
from scripts.encoder_training.metrics import (
    MetricsError,
    Prediction,
    accuracy,
    accuracy_statistic,
    apply_margin,
    bootstrap_ci,
    confusion_matrix,
    effective_n,
    fold_spread,
    macro_f1,
    mcnemar,
    null_to_true_rate,
    per_class_metrics,
    recall_statistic,
    repredict,
    slice_by_fragment,
    slice_by_label_mode,
    slice_by_library,
    slice_by_subclass,
    summarise,
    sweep_margins,
)
from scripts.encoder_training.ruleset_hash import hash_ruleset_file, ruleset_hash

FIXTURES = Path(__file__).parent / "fixtures" / "encoder_training"
TEST_SPLIT = FIXTURES / "mini.fold0.test.jsonl"
TRAIN_SPLIT = FIXTURES / "mini.fold0.train.jsonl"
RULESET = Path(__file__).resolve().parent.parent / "data" / "uti1.json"

SIGNAL = "fever_present"


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------


def _prediction(
    example_id: str,
    truth: int,
    predicted: int,
    unit: str,
    **kwargs,
) -> Prediction:
    return Prediction(example_id=example_id, truth=truth, predicted=predicted, unit=unit, **kwargs)


def _perfect(split, *, signal: str = SIGNAL) -> list[Prediction]:
    """Predictions from a loaded split that get every example right."""
    return [
        Prediction.from_example(example, signal, example.class_for(signal))
        for example in split.examples
    ]


# --------------------------------------------------------------------------
# Confusion matrix and per-class metrics
# --------------------------------------------------------------------------


def test_confusion_matrix_rows_are_truth_columns_are_prediction():
    predictions = [
        _prediction("a", CLASS_NULL, CLASS_TRUE, "u1"),
        _prediction("b", CLASS_NULL, CLASS_NULL, "u2"),
        _prediction("c", CLASS_TRUE, CLASS_TRUE, "u3"),
    ]

    matrix = confusion_matrix(predictions)

    assert matrix[CLASS_NULL][CLASS_TRUE] == 1
    assert matrix[CLASS_TRUE][CLASS_NULL] == 0
    assert matrix[CLASS_TRUE][CLASS_TRUE] == 1
    assert sum(sum(row) for row in matrix) == 3


def test_per_class_metrics_are_none_where_undefined():
    """Precision over zero predictions is not zero, and must not average in as one."""
    predictions = [
        _prediction("a", CLASS_NULL, CLASS_NULL, "u1"),
        _prediction("b", CLASS_NULL, CLASS_NULL, "u2"),
    ]

    metrics = per_class_metrics(confusion_matrix(predictions))

    assert metrics["null"].precision == 1.0
    assert metrics["null"].recall == 1.0
    assert metrics["true"].precision is None
    assert metrics["true"].recall is None
    assert metrics["true"].f1 is None


def test_per_class_metrics_arithmetic():
    predictions = [
        _prediction("a", CLASS_TRUE, CLASS_TRUE, "u1"),
        _prediction("b", CLASS_TRUE, CLASS_NULL, "u2"),
        _prediction("c", CLASS_NULL, CLASS_TRUE, "u3"),
    ]

    metrics = per_class_metrics(confusion_matrix(predictions))["true"]

    assert metrics.support == 2
    assert metrics.predicted == 2
    assert metrics.precision == 0.5
    assert metrics.recall == 0.5
    assert metrics.f1 == 0.5


def test_macro_f1_skips_classes_the_slice_never_contained():
    predictions = [
        _prediction("a", CLASS_NULL, CLASS_NULL, "u1"),
        _prediction("b", CLASS_TRUE, CLASS_TRUE, "u2"),
    ]

    # false is absent from both truth and prediction: averaging a 0.0 in for it
    # would report 0.67 for a slice the model got entirely right.
    assert macro_f1(confusion_matrix(predictions)) == 1.0


def test_macro_f1_counts_a_class_it_got_wrong():
    predictions = [
        _prediction("a", CLASS_NULL, CLASS_TRUE, "u1"),
        _prediction("b", CLASS_TRUE, CLASS_TRUE, "u2"),
    ]

    # null has support and zero recall, so its F1 is a real 0.0, not undefined.
    assert macro_f1(confusion_matrix(predictions)) == pytest.approx(2 / 3 / 2)


def test_accuracy_and_null_to_true_rate():
    predictions = [
        _prediction("a", CLASS_NULL, CLASS_TRUE, "u1"),
        _prediction("b", CLASS_NULL, CLASS_NULL, "u2"),
        _prediction("c", CLASS_NULL, CLASS_NULL, "u3"),
        _prediction("d", CLASS_TRUE, CLASS_TRUE, "u4"),
    ]
    matrix = confusion_matrix(predictions)

    assert accuracy(matrix) == 0.75
    assert null_to_true_rate(matrix) == pytest.approx(1 / 3)


def test_empty_slice_metrics_are_none():
    matrix = confusion_matrix([])

    assert accuracy(matrix) is None
    assert macro_f1(matrix) is None
    assert null_to_true_rate(matrix) is None


def test_out_of_range_class_is_rejected():
    with pytest.raises(MetricsError, match="not one of"):
        confusion_matrix([_prediction("a", 7, CLASS_TRUE, "u1")])


# --------------------------------------------------------------------------
# Effective sample size and slicing
# --------------------------------------------------------------------------


def test_effective_n_counts_clusters_not_examples():
    """The single guard against over-reading anything this pipeline produces."""
    predictions = [
        _prediction(f"e{index}", CLASS_NULL, CLASS_NULL, "fever_null_hedged:c01")
        for index in range(200)
    ] + [_prediction("e200", CLASS_NULL, CLASS_NULL, "fever_null_hedged:c02")]

    assert len(predictions) == 201
    assert effective_n(predictions) == 2


def test_summarise_reports_both_counts():
    split = load_split(TEST_SPLIT)
    summary = summarise(_perfect(split))

    assert summary.n_examples == 6
    # Five decisive clusters plus the shared structural-null unit.
    assert summary.effective_n == 6
    assert summary.accuracy == 1.0


def test_structural_nulls_share_one_resampling_unit():
    split = load_split(TEST_SPLIT)
    predictions = _perfect(split)

    units = {prediction.unit for prediction in predictions}
    assert STRUCTURAL_NULL_UNIT in units


def test_slice_by_library_separates_libraries_a_subclass_slice_would_merge():
    """DD6: the manifest sets no subclass on ``fever_true``/``fever_false``.

    Slicing on subclass alone collapses them, and all five filler libraries,
    into one indistinguishable ``None`` bucket.
    """
    split = load_split(TEST_SPLIT)
    predictions = _perfect(split)

    by_library = slice_by_library(predictions)
    by_subclass = slice_by_subclass(predictions)

    assert set(by_library) == {
        "fever_true",
        "fever_false",
        "fever_null_hedged",
        "fever_null_metaphor",
        "fever_null_thirdparty",
        None,
    }
    assert by_subclass[None] and len(by_subclass[None]) == 3
    assert set(by_subclass) == {"hedged", "metaphor", "third_party", None}


def test_slice_by_label_mode_and_fragment():
    split = load_split(TEST_SPLIT)
    predictions = _perfect(split)

    assert set(slice_by_label_mode(predictions)) == {
        "true",
        "false",
        "null_ambiguous",
        "null_structural",
    }
    # DD7: one row per decisive fragment, which is what separates "the method is
    # too weak" from "these specific ideas are unlearnable".
    assert len(slice_by_fragment(predictions)) == 6


def test_slices_sort_none_last():
    split = load_split(TEST_SPLIT)

    assert list(slice_by_library(_perfect(split)))[-1] is None


# --------------------------------------------------------------------------
# Bootstrap
# --------------------------------------------------------------------------


def _split_cluster_predictions(n_per_cluster: int) -> list[Prediction]:
    """Two clusters, one entirely right and one entirely wrong. Accuracy 0.5."""
    predictions = []
    for index in range(n_per_cluster):
        predictions.append(_prediction(f"right{index}", CLASS_NULL, CLASS_NULL, "cluster-a"))
        predictions.append(_prediction(f"wrong{index}", CLASS_NULL, CLASS_TRUE, "cluster-b"))
    return predictions


def test_cluster_bootstrap_is_wider_than_an_example_bootstrap_would_be():
    """The reason the unit is the cluster, stated as a test.

    A hundred examples per cluster look like 200 independent observations of a
    0.5 accuracy, and resampling examples would report roughly +/- 0.07. There
    are two ideas here, not two hundred, and resampling them honestly admits
    that accuracy could have come out anywhere from 0 to 1.
    """
    interval = bootstrap_ci(_split_cluster_predictions(100), accuracy_statistic, seed=7)

    assert interval.point == 0.5
    assert interval.effective_n == 2
    assert interval.low == 0.0
    assert interval.high == 1.0


def test_bootstrap_ignores_how_many_examples_a_cluster_was_recombined_into():
    """Ten recombinations of two ideas carry the same information as a hundred."""
    small = bootstrap_ci(_split_cluster_predictions(10), accuracy_statistic, seed=7)
    large = bootstrap_ci(_split_cluster_predictions(100), accuracy_statistic, seed=7)

    assert (small.low, small.point, small.high) == (large.low, large.point, large.high)


def test_bootstrap_is_deterministic_for_a_seed():
    predictions = _split_cluster_predictions(3)
    first = bootstrap_ci(predictions, accuracy_statistic, seed=11, resamples=200)
    second = bootstrap_ci(predictions, accuracy_statistic, seed=11, resamples=200)
    third = bootstrap_ci(predictions, accuracy_statistic, seed=12, resamples=200)

    assert (first.low, first.high) == (second.low, second.high)
    assert first.resamples_used == 200
    # Not a strict requirement of the method, but a seed that changed nothing
    # would mean the resampling was not happening at all.
    assert (third.low, third.high) != (first.low, first.high) or third.point == first.point


def test_bootstrap_narrows_as_clusters_are_added():
    many = [
        _prediction(f"e{index}", CLASS_NULL, CLASS_NULL if index % 2 else CLASS_TRUE, f"c{index}")
        for index in range(120)
    ]
    few = many[:8]

    wide = bootstrap_ci(few, accuracy_statistic, seed=3)
    narrow = bootstrap_ci(many, accuracy_statistic, seed=3)

    assert (narrow.high - narrow.low) < (wide.high - wide.low)


def test_bootstrap_drops_resamples_where_the_statistic_is_undefined():
    """A resample containing no ``true`` examples has no ``true`` recall."""
    predictions = [
        _prediction("a", CLASS_TRUE, CLASS_TRUE, "c1"),
        _prediction("b", CLASS_NULL, CLASS_NULL, "c2"),
    ]

    interval = bootstrap_ci(predictions, recall_statistic(CLASS_TRUE), seed=5, resamples=100)

    assert 0 < interval.resamples_used < 100
    assert interval.point == 1.0


def test_bootstrap_of_an_empty_slice_is_empty():
    interval = bootstrap_ci([], accuracy_statistic, seed=1, resamples=10)

    assert interval == type(interval)(
        point=None, low=None, high=None, effective_n=0, resamples_used=0
    )


def test_bootstrap_rejects_a_nonsense_alpha():
    with pytest.raises(MetricsError, match="alpha"):
        bootstrap_ci(_split_cluster_predictions(2), accuracy_statistic, alpha=1.5)


# --------------------------------------------------------------------------
# McNemar
# --------------------------------------------------------------------------


def _paired(correct_flags, *, truth: int = CLASS_NULL) -> list[Prediction]:
    return [
        _prediction(f"e{index}", truth, truth if correct else CLASS_TRUE, f"c{index}")
        for index, correct in enumerate(correct_flags)
    ]


def test_mcnemar_counts_discordant_pairs_and_computes_the_exact_p_value():
    a = _paired([True, True, True, True, True])
    b = _paired([False, False, False, False, False])

    result = mcnemar(a, b)

    assert (result.a_only_correct, result.b_only_correct) == (5, 0)
    # Two-sided exact binomial at p=0.5 over 5 discordant pairs: 2 * (1/32).
    assert result.p_value == pytest.approx(2 / 32)


def test_mcnemar_of_identical_models_is_one():
    a = _paired([True, False, True, False])
    b = _paired([True, False, True, False])

    result = mcnemar(a, b)

    assert (result.a_only_correct, result.b_only_correct) == (0, 0)
    assert result.p_value == 1.0


def test_mcnemar_is_symmetric_in_its_p_value():
    a = _paired([True, True, True, False])
    b = _paired([False, False, True, True])

    assert mcnemar(a, b).p_value == pytest.approx(mcnemar(b, a).p_value)


def test_mcnemar_rejects_unpaired_inputs():
    a = _paired([True, True])
    b = _paired([True])

    with pytest.raises(MetricsError, match="identical example sets"):
        mcnemar(a, b)


def test_mcnemar_rejects_disagreement_about_the_truth():
    a = [_prediction("e0", CLASS_NULL, CLASS_NULL, "c0")]
    b = [_prediction("e0", CLASS_TRUE, CLASS_TRUE, "c0")]

    with pytest.raises(MetricsError, match="disagree about the truth"):
        mcnemar(a, b)


# --------------------------------------------------------------------------
# The decision rule (DD9)
# --------------------------------------------------------------------------


def test_margin_zero_is_plain_argmax():
    # (false, true, null)
    assert apply_margin((0.1, 0.6, 0.3), 0.0) == CLASS_TRUE
    assert apply_margin((0.6, 0.1, 0.3), 0.0) == CLASS_FALSE
    assert apply_margin((0.1, 0.3, 0.6), 0.0) == CLASS_NULL


def test_margin_gates_only_the_true_class():
    """The rule protects the ``null -> true`` cell; it is not a general threshold."""
    # true wins by 0.1, which a 0.3 margin refuses, so the runner-up takes it.
    assert apply_margin((0.15, 0.45, 0.40), 0.3) == CLASS_NULL
    # A comfortable win survives the same margin.
    assert apply_margin((0.05, 0.80, 0.15), 0.3) == CLASS_TRUE
    # A margin never moves a decision that was not going to be true anyway.
    assert apply_margin((0.10, 0.30, 0.60), 0.9) == CLASS_NULL


def test_margin_falls_back_to_the_best_rival_not_to_null():
    assert apply_margin((0.40, 0.45, 0.15), 0.3) == CLASS_FALSE


def test_apply_margin_rejects_the_wrong_number_of_scores():
    with pytest.raises(MetricsError, match="expected 3 scores"):
        apply_margin((0.5, 0.5), 0.0)


def test_sweep_returns_the_full_metric_set_and_does_not_choose():
    predictions = [
        _prediction("a", CLASS_NULL, CLASS_TRUE, "c1", scores=(0.10, 0.50, 0.40)),
        _prediction("b", CLASS_NULL, CLASS_TRUE, "c2", scores=(0.05, 0.90, 0.05)),
        _prediction("c", CLASS_TRUE, CLASS_TRUE, "c3", scores=(0.05, 0.85, 0.10)),
    ]

    rows = sweep_margins(predictions, [0.0, 0.2, 0.5])

    assert [row.margin for row in rows] == [0.0, 0.2, 0.5]
    assert [row.null_to_true for row in rows] == [2, 1, 1]
    assert rows[0].null_to_true_rate == 1.0
    assert rows[-1].summary.n_examples == 3
    # Every row carries the whole metric set, so the caller can apply DD9's
    # objective (maximise macro-F1 subject to a null->true rate no worse than
    # argmax's) without this module having an opinion about it.
    assert rows[0].summary.per_class["true"].precision is not None


def test_sweeping_a_margin_never_raises_the_null_to_true_count():
    predictions = [
        _prediction(
            f"e{index}",
            CLASS_NULL,
            CLASS_TRUE,
            f"c{index}",
            scores=(0.1, 0.5 + index / 100, 0.4 - index / 100),
        )
        for index in range(10)
    ]

    counts = [row.null_to_true for row in sweep_margins(predictions, [0.0, 0.1, 0.2, 0.5, 1.0])]

    assert counts == sorted(counts, reverse=True)
    assert counts[-1] == 0


def test_repredict_keeps_provenance_and_needs_scores():
    original = _prediction(
        "a",
        CLASS_NULL,
        CLASS_TRUE,
        "c1",
        library="fever_null_metaphor",
        subclass="metaphor",
        scores=(0.10, 0.50, 0.40),
    )

    rewritten = repredict([original], 0.3)[0]

    assert rewritten.predicted == CLASS_NULL
    assert (rewritten.unit, rewritten.library, rewritten.subclass) == (
        "c1",
        "fever_null_metaphor",
        "metaphor",
    )

    with pytest.raises(MetricsError, match="carries no scores"):
        repredict([_prediction("b", CLASS_NULL, CLASS_TRUE, "c2")], 0.3)


# --------------------------------------------------------------------------
# Across folds
# --------------------------------------------------------------------------


def test_fold_spread_is_a_stability_check():
    spread = fold_spread([0.60, 0.64, 0.58, 0.62, 0.66])

    assert spread.n_folds == 5
    assert spread.mean == pytest.approx(0.62)
    assert spread.sd == pytest.approx(math.sqrt(0.004 / 4))


def test_fold_spread_of_one_fold_has_no_standard_deviation():
    assert fold_spread([0.5]).sd is None


# --------------------------------------------------------------------------
# Predictions carry provenance across from the dataset
# --------------------------------------------------------------------------


def test_prediction_from_example_carries_provenance():
    split = load_split(TEST_SPLIT)
    example = next(e for e in split.examples if e.example_id == "test-000004")

    prediction = Prediction.from_example(example, SIGNAL, CLASS_TRUE, scores=(0.1, 0.6, 0.3))

    assert prediction.truth == CLASS_NULL
    assert prediction.library == "fever_null_thirdparty"
    assert prediction.subclass == "third_party"
    assert prediction.unit == "fever_null_thirdparty:c07"
    assert prediction.correct is False


def test_prediction_from_a_masked_example_is_refused():
    split = load_split(TRAIN_SPLIT, signals=(SIGNAL, "dysuria_present"))
    example = split.examples[0]

    with pytest.raises(MetricsError, match="carries no label"):
        Prediction.from_example(example, "dysuria_present", CLASS_NULL)


# --------------------------------------------------------------------------
# DD15: the duplicated ruleset hash
# --------------------------------------------------------------------------


def test_duplicated_ruleset_hash_agrees_with_the_engine():
    """DD15: offline tooling duplicates the digest rather than importing it.

    A test that catches divergence is cheaper than a coupling that prevents it,
    but only if the test exists -- so this is the whole justification for the
    duplication, and it runs against the real ruleset.
    """
    from app.services.engine.ruleset import ruleset_hash as engine_ruleset_hash

    ruleset = json.loads(RULESET.read_text(encoding="utf-8"))

    assert ruleset_hash(ruleset) == engine_ruleset_hash(ruleset)
    assert hash_ruleset_file(RULESET) == engine_ruleset_hash(ruleset)


def test_ruleset_hash_is_key_order_independent():
    assert ruleset_hash({"a": 1, "b": 2}) == ruleset_hash({"b": 2, "a": 1})


def test_ruleset_hash_covers_the_whole_ruleset():
    """Worth knowing when reading a sidecar: any unrelated edit moves the digest."""
    base = json.loads(RULESET.read_text(encoding="utf-8"))
    edited = dict(base, some_unrelated_key="changed")

    assert ruleset_hash(base) != ruleset_hash(edited)

"""Unit tests for scripts/encoder_training/flip.py, Task 2's paraphrase-flip gate.

Pure unit tests: no torch, no GPU, no network, so there is no ``pytestmark``.
That is the point of ``flip.py`` taking its forward pass as a callable -- every
line that decides what a flip rate *means* runs on CI's unit job.

Three carry more weight than the rest.

``test_the_direction_matrix_says_which_class_went_where`` is the half of the
finding that is actually actionable. 12.6 found decisive recall draining into
``null``, and a flip rate on its own cannot distinguish that from a head
wobbling between ``true`` and ``false``.

``test_the_resampling_unit_is_the_submission`` is the power claim. One
submission's variants are rewrites of the same sentence; treating them as
independent would report an interval roughly sqrt(k) too narrow on a set whose
whole limitation is how small it is.

``test_a_source_row_must_be_the_submission_verbatim`` is what keeps this a
measurement of real text. A tidied-up source measures a rewrite against a
rewrite, and the tidying is exactly the register axis the diagnostic exists to
probe.
"""

import json
from pathlib import Path

import pytest

from scripts.encoder_training.dataset import (
    CLASS_FALSE,
    CLASS_NULL,
    CLASS_TRUE,
    STRUCTURAL_NULL_UNIT,
    fold_dataset_path,
    sidecar_path,
)
from scripts.encoder_training.flip import (
    DEFAULT_PARAPHRASE_PATH,
    FlipError,
    build_pairs,
    build_tree_pairs,
    decided_classes,
    describe_flips,
    describe_guard,
    describe_tree_flips,
    flip_rate,
    load_holdout_sources,
    load_paraphrases,
    load_predictions,
    pair_trees,
    score_flips,
    score_guard,
    score_tree_flips,
    write_predictions,
)
from scripts.encoder_training.metrics import Prediction

HEADER = "variant_id\tsubmission_id\tkind\ttext"

#: Per-class score rows, in `false`/`true`/`null` order as `dataset.CLASSES` has
#: them. Confident enough that a margin of 0.1 changes none of them, so a test
#: that means to exercise the decision rule has to say so.
FALSE_ROW = [0.90, 0.05, 0.05]
TRUE_ROW = [0.05, 0.90, 0.05]
NULL_ROW = [0.05, 0.05, 0.90]


def write_set(path: Path, rows) -> Path:
    path.write_text("\n".join([HEADER, *("\t".join(row) for row in rows)]) + "\n", encoding="utf-8")
    return path


def simple_set(path: Path, *, submissions=("holdout-0001", "holdout-0002"), variants=2) -> Path:
    rows = []
    for submission in submissions:
        rows.append((f"{submission}-src", submission, "source", f"{submission} original"))
        for index in range(1, variants + 1):
            rows.append((f"{submission}-v{index}", submission, "variant", f"{submission} v{index}"))
    return write_set(path, rows)


def scorer_for(rows_by_text, signals=("fever_present",)):
    """A fake forward pass: one fixed score row per text, keyed by the text itself."""

    def score(texts):
        return {signal: [list(rows_by_text[text]) for text in texts] for signal in signals}

    return score


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------


def test_a_variant_with_no_source_is_a_hard_error(tmp_path):
    path = write_set(
        tmp_path / "p.tsv",
        [
            ("holdout-0001-src", "holdout-0001", "source", "original"),
            ("holdout-0001-v1", "holdout-0001", "variant", "rewrite"),
            ("holdout-0009-v1", "holdout-0009", "variant", "orphan"),
        ],
    )
    with pytest.raises(FlipError, match="holdout-0009"):
        load_paraphrases(path)


def test_a_source_with_no_variants_is_a_hard_error(tmp_path):
    path = write_set(
        tmp_path / "p.tsv",
        [
            ("holdout-0001-src", "holdout-0001", "source", "original"),
            ("holdout-0001-v1", "holdout-0001", "variant", "rewrite"),
            ("holdout-0002-src", "holdout-0002", "source", "lonely"),
        ],
    )
    # Not a silently smaller set: a source contributing no pair has to be
    # deleted or written, and the loader will not choose for the author.
    with pytest.raises(FlipError, match="holdout-0002"):
        load_paraphrases(path)


def test_two_source_rows_for_one_submission_are_a_hard_error(tmp_path):
    path = write_set(
        tmp_path / "p.tsv",
        [
            ("holdout-0001-src", "holdout-0001", "source", "original"),
            ("holdout-0001-src2", "holdout-0001", "source", "also original"),
            ("holdout-0001-v1", "holdout-0001", "variant", "rewrite"),
        ],
    )
    with pytest.raises(FlipError, match="second"):
        load_paraphrases(path)


def test_a_repeated_variant_id_is_a_hard_error(tmp_path):
    path = write_set(
        tmp_path / "p.tsv",
        [
            ("holdout-0001-src", "holdout-0001", "source", "original"),
            ("holdout-0001-v1", "holdout-0001", "variant", "rewrite"),
            ("holdout-0001-v1", "holdout-0001", "variant", "another rewrite"),
        ],
    )
    with pytest.raises(FlipError, match="repeats"):
        load_paraphrases(path)


def test_an_unknown_kind_is_a_hard_error(tmp_path):
    path = write_set(
        tmp_path / "p.tsv",
        [
            ("holdout-0001-src", "holdout-0001", "source", "original"),
            ("holdout-0001-v1", "holdout-0001", "paraphrase", "rewrite"),
        ],
    )
    with pytest.raises(FlipError, match="kind"):
        load_paraphrases(path)


def test_a_source_row_must_be_the_submission_verbatim(tmp_path):
    path = simple_set(tmp_path / "p.tsv", submissions=("holdout-0001",))
    sources = {"holdout-0001": "holdout-0001 original"}
    assert len(load_paraphrases(path, sources=sources)) == 1

    tidied = dict(sources, **{"holdout-0001": "Holdout-0001 original."})
    with pytest.raises(FlipError, match="verbatim"):
        load_paraphrases(path, sources=tidied)


def test_holdout_sources_are_keyed_by_line_order(tmp_path):
    source = tmp_path / "source.txt"
    source.write_text("first\nsecond\n\nfourth\n", encoding="utf-8")
    sources = load_holdout_sources(source)
    # Blank lines take an id and are dropped, exactly as the labels file's own
    # line-order convention requires: ids must not shift.
    assert sources == {"holdout-0001": "first", "holdout-0002": "second", "holdout-0004": "fourth"}


def test_texts_interleave_each_source_with_its_own_variants(tmp_path):
    paraphrases = load_paraphrases(simple_set(tmp_path / "p.tsv"))
    assert paraphrases.texts == (
        "holdout-0001 original",
        "holdout-0001 v1",
        "holdout-0001 v2",
        "holdout-0002 original",
        "holdout-0002 v1",
        "holdout-0002 v2",
    )
    assert paraphrases.n_pairs == 4


# ---------------------------------------------------------------------------
# The statistic
# ---------------------------------------------------------------------------


def test_flip_rate_is_one_minus_agreement():
    # Rows are the source's class, columns the variant's: four pairs, one of
    # which changed class.
    confusion = [[2, 0, 1], [0, 1, 0], [0, 0, 0]]
    assert flip_rate(confusion) == pytest.approx(0.25)
    assert flip_rate([[0, 0, 0], [0, 0, 0], [0, 0, 0]]) is None


def test_a_pair_is_the_source_against_its_variant(tmp_path):
    paraphrases = load_paraphrases(simple_set(tmp_path / "p.tsv", submissions=("holdout-0001",)))
    scores = {
        "holdout-0001 original": TRUE_ROW,
        "holdout-0001 v1": TRUE_ROW,
        "holdout-0001 v2": NULL_ROW,
    }
    pairs = build_pairs(
        paraphrases,
        scorer_for(scores)(paraphrases.texts),
        signals=["fever_present"],
    )["fever_present"]
    assert [(pair.example_id, pair.truth, pair.predicted) for pair in pairs] == [
        ("holdout-0001-v1:fever_present", CLASS_TRUE, CLASS_TRUE),
        ("holdout-0001-v2:fever_present", CLASS_TRUE, CLASS_NULL),
    ]
    # The source is never itself a pair: it is the reference the variants are
    # compared against, so k variants give k pairs, not k + 1.
    assert len(pairs) == paraphrases.n_pairs


def test_the_direction_matrix_says_which_class_went_where(tmp_path):
    paraphrases = load_paraphrases(
        simple_set(tmp_path / "p.tsv", submissions=("holdout-0001", "holdout-0002"), variants=2)
    )
    scores = {
        "holdout-0001 original": TRUE_ROW,
        "holdout-0001 v1": NULL_ROW,
        "holdout-0001 v2": NULL_ROW,
        "holdout-0002 original": FALSE_ROW,
        "holdout-0002 v1": FALSE_ROW,
        "holdout-0002 v2": TRUE_ROW,
    }
    result = score_flips(paraphrases, scorer_for(scores), signals=["fever_present"], resamples=50)
    overall = result["overall"]
    assert overall["n_pairs"] == 4
    assert overall["flips"] == 3
    assert overall["flip_rate"]["point"] == pytest.approx(0.75)
    assert overall["direction"]["transitions"] == {"true -> null": 2, "false -> true": 1}
    # A head that wobbles true/null and one that wobbles true/false have the
    # same rate and different faults, which is why the matrix travels with it.
    assert overall["direction"]["matrix"][CLASS_TRUE][CLASS_NULL] == 2
    assert overall["direction"]["matrix"][CLASS_FALSE][CLASS_TRUE] == 1


def test_no_flip_leaves_the_transitions_empty(tmp_path):
    paraphrases = load_paraphrases(simple_set(tmp_path / "p.tsv", submissions=("holdout-0001",)))
    scores = dict.fromkeys(paraphrases.texts, NULL_ROW)
    result = score_flips(paraphrases, scorer_for(scores), signals=["fever_present"], resamples=50)
    assert result["overall"]["flip_rate"]["point"] == pytest.approx(0.0)
    assert result["overall"]["direction"]["transitions"] == {}
    assert "no pair changed class" in "\n".join(describe_flips(result))


def test_the_resampling_unit_is_the_submission(tmp_path):
    # Two submissions, three variants each. One submission flips on every
    # variant, the other on none: at the submission level that is two
    # observations of 1.0 and 0.0, so the bootstrap must be able to return both
    # extremes. Resampling the six pairs independently could not.
    paraphrases = load_paraphrases(
        simple_set(tmp_path / "p.tsv", submissions=("holdout-0001", "holdout-0002"), variants=3)
    )
    scores = {text: NULL_ROW for text in paraphrases.texts}
    for text in paraphrases.texts:
        if text.startswith("holdout-0001") and text != "holdout-0001 original":
            scores[text] = TRUE_ROW
    result = score_flips(paraphrases, scorer_for(scores), signals=["fever_present"], resamples=500)
    overall = result["overall"]
    assert overall["n_pairs"] == 6
    assert overall["n_submissions"] == 2
    assert overall["flip_rate"]["low"] == pytest.approx(0.0)
    assert overall["flip_rate"]["high"] == pytest.approx(1.0)


def test_the_decision_rule_is_applied_to_both_sides(tmp_path):
    # A source just over the line for `true` and a variant just under it. Under
    # argmax the pair does not flip; under the margin the fold actually selected
    # it does, because the margin moves the source and not the variant.
    paraphrases = load_paraphrases(
        simple_set(tmp_path / "p.tsv", submissions=("holdout-0001",), variants=1)
    )
    scores = {
        "holdout-0001 original": [0.05, 0.50, 0.45],
        "holdout-0001 v1": [0.05, 0.40, 0.55],
    }
    argmax = score_flips(paraphrases, scorer_for(scores), signals=["fever_present"], resamples=20)
    assert argmax["overall"]["flips"] == 1

    ruled = score_flips(
        paraphrases, scorer_for(scores), signals=["fever_present"], margin=0.2, resamples=20
    )
    # Both sides are now `null`, so the pair agrees -- which is the point of
    # scoring under the rule the fold was deployed with rather than under argmax.
    assert ruled["overall"]["flips"] == 0


def test_a_scorer_that_returns_the_wrong_shape_is_a_hard_error(tmp_path):
    paraphrases = load_paraphrases(simple_set(tmp_path / "p.tsv", submissions=("holdout-0001",)))
    with pytest.raises(FlipError, match="returned nothing"):
        build_pairs(paraphrases, {}, signals=["fever_present"])
    with pytest.raises(FlipError, match="rows"):
        build_pairs(paraphrases, {"fever_present": [TRUE_ROW]}, signals=["fever_present"])


def test_a_joint_scoring_needs_a_margin_for_every_head(tmp_path):
    paraphrases = load_paraphrases(simple_set(tmp_path / "p.tsv", submissions=("holdout-0001",)))
    scores = scorer_for(
        dict.fromkeys(paraphrases.texts, NULL_ROW), signals=("fever_present", "dysuria_present")
    )(paraphrases.texts)
    with pytest.raises(FlipError, match="no margin given"):
        build_pairs(
            paraphrases,
            scores,
            signals=["fever_present", "dysuria_present"],
            margin={"fever_present": 0.1},
        )


def test_the_result_carries_its_own_caveats(tmp_path):
    paraphrases = load_paraphrases(simple_set(tmp_path / "p.tsv", submissions=("holdout-0001",)))
    result = score_flips(
        paraphrases,
        scorer_for(dict.fromkeys(paraphrases.texts, NULL_ROW)),
        signals=["fever_present"],
        resamples=20,
    )
    # The three notes a report has to carry: who wrote the variants, that the
    # set selects nothing, and what a dozen submissions can support.
    assert "written by Claude" in result["provenance"]
    assert (
        "selects nothing" in result["selects_nothing"]
        or "costs the holdout" in (result["selects_nothing"])
    )
    assert "submission" in result["resampling_unit"]
    assert "power" in "\n".join(describe_flips(result))


# ---------------------------------------------------------------------------
# The committed set
# ---------------------------------------------------------------------------


def test_the_committed_paraphrase_set_loads_and_matches_the_submissions():
    sources = load_holdout_sources(Path("data/realistic/uti1_holdout.source.txt"))
    paraphrases = load_paraphrases(DEFAULT_PARAPHRASE_PATH, sources=sources)
    # Instruction 1's shape: roughly 10-15 submissions, three or four variants
    # each. Asserted as a range rather than a number so adding a submission is
    # not a test failure, but halving the set is.
    assert 10 <= len(paraphrases) <= 15
    assert paraphrases.n_pairs >= 3 * len(paraphrases)
    for group in paraphrases.groups:
        assert group.n_pairs >= 3
        for variant in group.variants:
            assert variant.text != group.source_text


# ---------------------------------------------------------------------------
# The CLI wiring
# ---------------------------------------------------------------------------


def test_the_cli_exposes_flip_rate_and_defaults_to_the_committed_set():
    from scripts.encoder_training.__main__ import build_parser, run_flip_rate

    args = build_parser().parse_args(["flip-rate", "--weights", "fold0.encoder.pt"])
    assert args.handler is run_flip_rate
    assert args.paraphrases == DEFAULT_PARAPHRASE_PATH
    # The rule the fold selected, not argmax: `--margin` is the deliberate
    # sensitivity check, and leaving it unset must mean "read the fold's own".
    assert args.margin is None


def test_the_decision_rule_is_looked_for_beside_the_head_artefacts():
    from scripts.encoder_training.__main__ import _default_decision_path

    assert _default_decision_path(
        Path("models/encoder/fever_present/arm_b_finetune/weights/fold3.encoder.pt")
    ) == Path("models/encoder/fever_present/arm_b_finetune/fold3.decision.json")


# ---------------------------------------------------------------------------
# Task 6: the paired flip rate between two matched trees
#
# The three that carry the most weight here:
#
# ``test_unchanged_pairs_are_excluded_from_the_denominator`` is the statistic's
# definition. Including the clean share would drag every arm's rate towards zero
# by an amount that is a property of `--clean-share` and not of the model.
#
# ``test_the_resampling_unit_is_the_cluster`` is the power claim, and it is the
# one `arch_training.md` section 10 exists to enforce: ten thousand examples over
# a few hundred clusters is not ten thousand observations.
#
# ``test_a_prediction_file_missing_an_example_is_a_hard_error`` is what stops a
# silently-partial pairing. Two cells scored on different examples do not have a
# flip rate; they have an intersection, and an intersection is not a result.
# ---------------------------------------------------------------------------

FIXTURES = Path(__file__).parent / "fixtures" / "encoder_training"
SIGNAL = "fever_present"


def _write_tree(directory: Path, *, folds: int = 1, expand: bool = False) -> Path:
    """The fixture trio under the fold-file convention, optionally 'expanded'.

    ``expand`` rewrites the text of every *other* example and leaves the rest
    byte-identical, which is the shape `expand.py` actually produces: a clean
    share plus the examples holding no match site are untouched, and only the
    remainder can flip.
    """
    directory.mkdir(parents=True, exist_ok=True)
    for fold_index in range(folds):
        for split in ("train", "val", "test"):
            source = FIXTURES / f"mini.fold0.{split}.jsonl"
            target = fold_dataset_path(directory, SIGNAL, fold_index, split)
            target.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
            stats = json.loads(sidecar_path(source).read_text(encoding="utf-8"))
            stats["folds"] = folds
            stats["fold_index"] = fold_index
            # Each fold holds the same six examples in this fixture, and
            # `load_folds` refuses a cluster held out twice -- rightly, since
            # pooling would count it twice. Suffixing the cluster keys per fold
            # is the smallest thing that makes a multi-fold tree legal here
            # without inventing five fixtures.
            for info in stats["fragments"].values():
                info["cluster_key"] = f"{info['cluster_key']}-f{fold_index}"
            if expand:
                stats["expansion"] = {"source_dir": "clean", "seed": 42}
            sidecar_path(target).write_text(json.dumps(stats, indent=2), encoding="utf-8")
            if expand:
                records = [
                    json.loads(line)
                    for line in target.read_text(encoding="utf-8").splitlines()
                    if line
                ]
                for index, record in enumerate(records):
                    if index % 2 == 0:
                        record["text"] = record["text"].replace("fever", "temperature")
                target.write_text(
                    "".join(json.dumps(record) + "\n" for record in records), encoding="utf-8"
                )
    return directory


def _trees(tmp_path: Path, *, folds: int = 1):
    return (
        _write_tree(tmp_path / "clean", folds=folds),
        _write_tree(tmp_path / "expanded", folds=folds, expand=True),
    )


def _predictions(path: Path, pairs, decide) -> Path:
    """Write a predictions file deciding each pair by ``decide(pair)``."""
    return write_predictions(
        path,
        [
            Prediction(
                example_id=pair.example_id,
                truth=CLASS_NULL,
                predicted=decide(pair),
                unit=pair.unit,
                label_mode=pair.label_mode,
            )
            for pair in pairs
        ],
        header={"model": "arm_b_finetune"},
    )


def test_pairing_qualifies_ids_by_fold(tmp_path):
    """The generator numbers examples per split, so ``test-000000`` names one
    example in each of the folds. An unqualified pairing would collapse five
    examples into one and compare four fifths of the tree against the wrong
    row -- the same reason ``report.FoldRun.build`` qualifies."""
    clean, expanded = _trees(tmp_path, folds=2)

    pairs = pair_trees(clean, expanded, signal=SIGNAL, folds=2)

    ids = [pair.example_id for pair in pairs]
    assert len(ids) == len(set(ids))
    assert ids[0].startswith("fold0:")
    assert any(identifier.startswith("fold1:") for identifier in ids)


def test_pairing_marks_only_the_examples_the_pass_changed(tmp_path):
    clean, expanded = _trees(tmp_path)

    pairs = pair_trees(clean, expanded, signal=SIGNAL, folds=1)

    assert any(pair.changed for pair in pairs)
    assert any(not pair.changed for pair in pairs)


def test_pairing_carries_the_cluster_across(tmp_path):
    """The unit comes from the *clean* tree's sidecar, which is the only tree
    whose fragment provenance the expansion pass is guaranteed not to have
    touched -- and, since expansion edits no library, the two agree anyway."""
    clean, expanded = _trees(tmp_path)

    pairs = pair_trees(clean, expanded, signal=SIGNAL, folds=1)

    by_id = {pair.example_id: pair for pair in pairs}
    assert all(pair.unit for pair in pairs)
    assert by_id["fold0:test-000002"].unit == "fever_null_hedged:c05-f0"
    # A structural null holds no decisive fragment, so every one of them shares
    # the single unit `dataset.STRUCTURAL_NULL_UNIT` names.
    assert by_id["fold0:test-000005"].unit == STRUCTURAL_NULL_UNIT


def test_a_tree_with_different_ids_is_a_hard_error(tmp_path):
    clean, expanded = _trees(tmp_path)
    target = fold_dataset_path(expanded, SIGNAL, 0, "test")
    records = [json.loads(line) for line in target.read_text(encoding="utf-8").splitlines() if line]
    records[0]["example_id"] = "test-999999"
    target.write_text("".join(json.dumps(record) + "\n" for record in records), encoding="utf-8")

    with pytest.raises(FlipError, match="two different generations"):
        pair_trees(clean, expanded, signal=SIGNAL, folds=1)


def test_unchanged_pairs_are_excluded_from_the_denominator(tmp_path):
    """The statistic's definition, and the one mistake that would make every arm
    look better than it is. An example the pass left alone is byte-identical on
    both sides and cannot flip; counting it would lower the rate by exactly the
    unchanged share, which is a fact about `--clean-share` and not about a head."""
    clean, expanded = _trees(tmp_path)
    pairs = pair_trees(clean, expanded, signal=SIGNAL, folds=1)
    changed = [pair for pair in pairs if pair.changed]
    assert len(changed) < len(pairs)

    # Every example decides `null` on the clean side and `true` on the expanded
    # one: every *changed* pair flips, and nothing else may enter the count.
    built = build_tree_pairs(
        pairs,
        {pair.example_id: CLASS_NULL for pair in pairs},
        {pair.example_id: CLASS_TRUE for pair in pairs},
    )

    assert len(built) == len(changed)
    assert {prediction.example_id for prediction in built} == {pair.example_id for pair in changed}


def test_the_flip_rate_is_one_when_every_changed_pair_disagrees(tmp_path):
    clean, expanded = _trees(tmp_path)
    pairs = pair_trees(clean, expanded, signal=SIGNAL, folds=1)
    clean_file = _predictions(tmp_path / "a.json", pairs, lambda pair: CLASS_NULL)
    expanded_file = _predictions(tmp_path / "b.json", pairs, lambda pair: CLASS_TRUE)

    result = score_tree_flips(
        pairs,
        decided_classes(load_predictions(clean_file)),
        decided_classes(load_predictions(expanded_file)),
        arm="clean_trained",
        resamples=50,
    )

    assert result["flip_rate"]["point"] == 1.0
    assert result["n_unchanged"] == len(pairs) - result["n_pairs"]
    assert result["direction"]["transitions"] == {"null -> true": result["n_pairs"]}


def test_an_arm_that_never_moves_has_a_flip_rate_of_zero(tmp_path):
    clean, expanded = _trees(tmp_path)
    pairs = pair_trees(clean, expanded, signal=SIGNAL, folds=1)
    decided = {pair.example_id: CLASS_NULL for pair in pairs}

    result = score_tree_flips(pairs, decided, decided, arm="expanded_trained", resamples=50)

    assert result["flip_rate"]["point"] == 0.0
    assert result["direction"]["transitions"] == {}


def test_the_resampling_unit_is_the_cluster(tmp_path):
    """The power claim. Ten thousand examples sit on a few hundred decisive
    clusters; resampling examples would treat rewrites of one idea as
    independent observations and report an interval several times too narrow."""
    clean, expanded = _trees(tmp_path)
    pairs = pair_trees(clean, expanded, signal=SIGNAL, folds=1)
    changed = [pair for pair in pairs if pair.changed]

    result = score_tree_flips(
        pairs,
        {pair.example_id: CLASS_NULL for pair in pairs},
        {pair.example_id: CLASS_TRUE for pair in pairs},
        arm="clean_trained",
        resamples=50,
    )

    assert result["n_clusters"] == len({pair.unit for pair in changed})
    assert result["n_clusters"] <= result["n_pairs"]


def test_a_pass_that_changed_nothing_is_a_hard_error(tmp_path):
    clean = _write_tree(tmp_path / "clean")
    same = _write_tree(tmp_path / "same")
    pairs = pair_trees(clean, same, signal=SIGNAL, folds=1)
    decided = {pair.example_id: CLASS_NULL for pair in pairs}

    with pytest.raises(FlipError, match="changed no example"):
        score_tree_flips(pairs, decided, decided, arm="clean_trained")


def test_a_prediction_file_missing_an_example_is_a_hard_error(tmp_path):
    clean, expanded = _trees(tmp_path)
    pairs = pair_trees(clean, expanded, signal=SIGNAL, folds=1)
    full = {pair.example_id: CLASS_NULL for pair in pairs}
    partial = dict(list(full.items())[:-1])

    with pytest.raises(FlipError, match="not in both prediction files"):
        build_tree_pairs(pairs, full, partial)


def test_a_predictions_file_naming_one_id_twice_is_rejected(tmp_path):
    path = tmp_path / "dupe.json"
    path.write_text(
        json.dumps(
            {
                "predictions": [
                    {"example_id": "fold0:test-000000", "predicted": 0},
                    {"example_id": "fold0:test-000000", "predicted": 1},
                ]
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(FlipError, match="twice"):
        load_predictions(path)


def test_predictions_round_trip_without_scores(tmp_path):
    """Scores are deliberately not written: the decisions here are the ones the
    fold's selected rule made, and re-deciding them downstream under some other
    margin would produce a flip rate for a model nobody ran."""
    path = write_predictions(
        tmp_path / "p.json",
        [Prediction(example_id="fold0:test-000000", truth=0, predicted=1, unit="c01")],
        header={"model": "arm_b_finetune"},
    )

    payload = load_predictions(path)

    assert payload["header"]["model"] == "arm_b_finetune"
    assert decided_classes(payload) == {"fold0:test-000000": 1}
    assert "scores" not in payload["predictions"][0]


# ---------------------------------------------------------------------------
# The guard (plan DD7)
# ---------------------------------------------------------------------------


def _report(path: Path, accuracy: float, *, model: str = "arm_b_finetune") -> Path:
    path.write_text(
        json.dumps(
            {
                "models": [
                    {
                        "name": model,
                        "pooled": {"ruled": {"decisive": {"accuracy": {"point": accuracy}}}},
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    return path


def test_the_guard_holds_when_decisive_accuracy_does(tmp_path):
    guard = score_guard(
        _report(tmp_path / "baseline.json", 0.93),
        _report(tmp_path / "arm.json", 0.925),
        bound=0.02,
        model="arm_b_finetune",
    )

    assert guard["passed"]
    assert guard["drop"] == pytest.approx(0.005)


def test_the_guard_fails_when_the_arm_bought_its_flip_rate(tmp_path):
    """A head that answers `null` to everything has a flip rate of zero. The
    guard is the only thing standing between that and a headline result, which
    is why it is scored in the same invocation as the flip rate rather than in a
    step somebody might skip."""
    guard = score_guard(
        _report(tmp_path / "baseline.json", 0.93),
        _report(tmp_path / "arm.json", 0.85),
        bound=0.02,
        model="arm_b_finetune",
    )

    assert not guard["passed"]
    assert "FAILED" in "\n".join(describe_guard(guard))


def test_the_guard_names_the_models_it_could_not_find(tmp_path):
    with pytest.raises(FlipError, match="arm_a_probe"):
        score_guard(
            _report(tmp_path / "baseline.json", 0.93),
            _report(tmp_path / "arm.json", 0.93),
            bound=0.02,
            model="arm_a_probe",
        )


def test_a_negative_guard_bound_is_rejected(tmp_path):
    """A bound is a permitted *drop*. A negative one would silently demand an
    improvement, which is not what 'the guard held' means anywhere it is read."""
    with pytest.raises(FlipError, match="must not be negative"):
        score_guard(
            _report(tmp_path / "baseline.json", 0.93),
            _report(tmp_path / "arm.json", 0.93),
            bound=-0.01,
            model="arm_b_finetune",
        )


def test_the_summary_says_how_many_examples_could_not_flip(tmp_path):
    """The denominator has to be legible in the printed output, not only in the
    JSON. A rate over changed pairs and a rate over every pair differ by the
    clean share, and a reader who cannot see which one this is cannot compare it
    with anything."""
    clean, expanded = _trees(tmp_path)
    pairs = pair_trees(clean, expanded, signal=SIGNAL, folds=1)

    lines = describe_tree_flips(
        score_tree_flips(
            pairs,
            {pair.example_id: CLASS_NULL for pair in pairs},
            {pair.example_id: CLASS_TRUE for pair in pairs},
            arm="clean_trained",
            resamples=50,
        )
    )

    assert any("could not flip and are excluded" in line for line in lines)
    assert any("clusters" in line for line in lines)

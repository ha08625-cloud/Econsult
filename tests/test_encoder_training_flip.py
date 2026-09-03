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

from pathlib import Path

import pytest

from scripts.encoder_training.dataset import CLASS_FALSE, CLASS_NULL, CLASS_TRUE
from scripts.encoder_training.flip import (
    DEFAULT_PARAPHRASE_PATH,
    FlipError,
    build_pairs,
    describe_flips,
    flip_rate,
    load_holdout_sources,
    load_paraphrases,
    score_flips,
)

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

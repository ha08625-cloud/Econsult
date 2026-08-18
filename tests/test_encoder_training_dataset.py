"""Unit tests for scripts/encoder_training/dataset.py.

Pure unit tests: no database, no torch, no GPU, so there is no ``pytestmark``.
That is the point of the module under test being stdlib-only -- every line of
the logic that decides what an evaluation number *means* is covered by CI's
unit job on an ordinary runner.

The fixtures in ``tests/fixtures/encoder_training/`` are hand-built rather than
generated. A generated fold would be thousands of examples over hundreds of
fragments, and the properties being checked here (which fragment is decisive,
which examples share a cluster, what a missing signal key does) are only legible
at six examples.
"""

import ast
import json
from pathlib import Path

import pytest

from scripts.encoder_training.dataset import (
    CLASS_FALSE,
    CLASS_NULL,
    CLASS_TRUE,
    MASKED_CLASS,
    STRUCTURAL_NULL_UNIT,
    DatasetError,
    label_vector,
    load_fold,
    load_split,
    mask_vector,
    sidecar_path,
)

FIXTURES = Path(__file__).parent / "fixtures" / "encoder_training"
TRAIN = FIXTURES / "mini.fold0.train.jsonl"
VAL = FIXTURES / "mini.fold0.val.jsonl"
TEST = FIXTURES / "mini.fold0.test.jsonl"
MISSING_KEY = FIXTURES / "missing_key.train.jsonl"

SIGNAL = "fever_present"


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------


def _copy_fixture(tmp_path: Path, source: Path, *, name: str | None = None) -> Path:
    """Copy a fixture dataset and its sidecar into ``tmp_path``, returning the JSONL."""
    target = tmp_path / (name or source.name)
    target.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
    sidecar_path(target).write_text(
        sidecar_path(source).read_text(encoding="utf-8"), encoding="utf-8"
    )
    return target


def _edit_stats(path: Path, mutate) -> None:
    """Apply ``mutate`` to a copied sidecar in place."""
    stats_file = sidecar_path(path)
    stats = json.loads(stats_file.read_text(encoding="utf-8"))
    mutate(stats)
    stats_file.write_text(json.dumps(stats, indent=2), encoding="utf-8")


def _edit_records(path: Path, mutate) -> None:
    """Apply ``mutate`` to every record of a copied dataset in place."""
    records = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]
    for record in records:
        mutate(record)
    path.write_text(
        "".join(json.dumps(record) + "\n" for record in records),
        encoding="utf-8",
    )


def _by_id(split):
    return {example.example_id: example for example in split.examples}


# --------------------------------------------------------------------------
# Loading a split
# --------------------------------------------------------------------------


def test_load_split_reads_examples_and_sidecar():
    split = load_split(TRAIN)

    assert split.name == "train"
    assert len(split) == 6
    assert split.signals == (SIGNAL,)
    assert split.generator_version == 2
    assert split.fold_config == (5, 0, "32")
    assert set(split.fragments) >= {"fever_true:11111111", "tangents:66666666"}


def test_sidecar_path_matches_what_the_generator_writes():
    # The generator writes "<out>.stats.json", not "<stem>.stats.json"; getting
    # this wrong would look like a missing sidecar on every real dataset.
    assert sidecar_path(Path("a/b/fever.train.jsonl")).name == "fever.train.jsonl.stats.json"


def test_labels_map_to_class_indices():
    examples = _by_id(load_split(TRAIN))

    assert examples["train-000000"].class_for(SIGNAL) == CLASS_TRUE
    assert examples["train-000001"].class_for(SIGNAL) == CLASS_FALSE
    assert examples["train-000002"].class_for(SIGNAL) == CLASS_NULL


def test_explicit_null_is_labelled_not_masked():
    """DD10: an explicit null trains towards the null class."""
    example = _by_id(load_split(TRAIN))["train-000005"]

    assert example.is_labelled(SIGNAL) is True
    assert example.class_for(SIGNAL) == CLASS_NULL


def test_missing_signal_key_masks_the_head():
    """DD10's other half, and the case the generator can never produce.

    With one signal every example carries the key, so this path gets no
    coverage from real data. Conflating "no label for this head" with "the
    label is null" teaches every head to answer null on every other head's
    data, and is invisible until the model is mysteriously bad.
    """
    split = load_split(MISSING_KEY)
    assert split.signals == ("dysuria_present", "fever_present")
    examples = _by_id(split)

    fever_only = examples["train-000000"]
    assert fever_only.is_labelled("fever_present") is True
    assert fever_only.class_for("fever_present") == CLASS_TRUE
    assert fever_only.is_labelled("dysuria_present") is False
    assert fever_only.class_for("dysuria_present") == MASKED_CLASS

    dysuria_only = examples["train-000001"]
    assert dysuria_only.is_labelled("fever_present") is False
    assert dysuria_only.class_for("dysuria_present") == CLASS_FALSE

    both = examples["train-000002"]
    assert both.mask == {"dysuria_present": True, "fever_present": True}
    assert both.classes == {"dysuria_present": CLASS_NULL, "fever_present": CLASS_NULL}


def test_masked_class_is_not_a_real_class_index():
    """A caller that drops the mask must fail loudly, not read masked as false."""
    assert MASKED_CLASS not in (CLASS_FALSE, CLASS_TRUE, CLASS_NULL)
    assert MASKED_CLASS < 0


def test_label_and_mask_vectors_line_up_with_the_signal_order():
    split = load_split(MISSING_KEY)
    example = _by_id(split)["train-000000"]

    assert label_vector(example, split.signals) == [MASKED_CLASS, CLASS_TRUE]
    assert mask_vector(example, split.signals) == [False, True]


def test_signals_can_be_pinned_so_every_split_has_the_same_width():
    split = load_split(TRAIN, signals=("fever_present", "dysuria_present"))
    example = _by_id(split)["train-000000"]

    assert split.signals == ("fever_present", "dysuria_present")
    assert mask_vector(example, split.signals) == [True, False]


def test_non_boolean_label_is_rejected(tmp_path):
    path = _copy_fixture(tmp_path, TRAIN)
    _edit_records(path, lambda record: record["labels"].update({SIGNAL: 1}))

    with pytest.raises(DatasetError, match="non-Boolean label"):
        load_split(path)


# --------------------------------------------------------------------------
# The decisive fragment (DD6, DD7)
# --------------------------------------------------------------------------


def test_decisive_fragment_is_the_non_filler_one():
    examples = _by_id(load_split(TEST))
    example = examples["test-000004"]

    assert example.fragment_id == "fever_null_thirdparty:30303030"
    assert example.library == "fever_null_thirdparty"
    assert example.subclass == "third_party"


def test_decisive_fragment_is_found_wherever_it_sits():
    """The generator shuffles, so the decisive fragment is not always first."""
    examples = _by_id(load_split(TRAIN))

    assert examples["train-000000"].fragment_ids[0] == "fever_true:11111111"
    assert examples["train-000001"].fragment_ids[1] == "fever_false:22222222"
    assert examples["train-000001"].library == "fever_false"


def test_filler_is_read_from_the_sidecar_not_the_library_name(tmp_path):
    """DD6: ``fever_true`` and ``tangents`` look equally like filler to a regex.

    Retype ``tangents`` as this signal's positive library and the example holds
    two decisive fragments -- which is wrong, but it is wrong *because the
    sidecar says so*, which is what this asserts.
    """
    path = _copy_fixture(tmp_path, TRAIN)
    _edit_stats(
        path,
        lambda stats: stats["fragments"]["tangents:66666666"].update(
            {"fragment_type": "positive", "signal_key": "fever_present"}
        ),
    )

    with pytest.raises(DatasetError, match="2 fragments decisive for"):
        load_split(path)


def test_a_non_filler_fragment_of_another_signal_is_not_decisive(tmp_path):
    """A companion (``--companion-share`` above zero) is clinical and not decisive.

    Retyping ``tangents`` as another signal's positive fragment is exactly what
    a companion looks like from the loader's side: non-filler, and saying
    nothing about the label this example is supervised on. Counting it as
    decisive would make every companion-bearing dataset unloadable, which is
    what happened before the loader was told the difference.
    """
    path = _copy_fixture(tmp_path, TRAIN)
    _edit_stats(
        path,
        lambda stats: stats["fragments"]["tangents:66666666"].update(
            {"fragment_type": "positive", "signal_key": "dysuria_present"}
        ),
    )

    example = _by_id(load_split(path))["train-000000"]
    assert example.decisive is not None
    assert example.decisive.fragment_id == "fever_true:11111111"
    assert example.library == "fever_true"


def test_a_structural_null_may_hold_a_companion(tmp_path):
    """It holds no fragment decisive for *its* signal, which is what the mode means.

    At ``--companion-share`` above zero a structural null stops being
    filler-only and stops being trivially easy, which is the point of it
    (``arch_training.md`` section 5). The label-mode agreement check has to read
    "decisive for this signal" or it would reject every such example.
    """
    path = _copy_fixture(tmp_path, TRAIN)
    _edit_stats(
        path,
        lambda stats: stats["fragments"]["tangents:66666666"].update(
            {"fragment_type": "positive", "signal_key": "dysuria_present"}
        ),
    )

    example = _by_id(load_split(path))["train-000005"]
    assert example.label_mode == "null_structural"
    assert example.decisive is None
    assert example.resampling_unit == STRUCTURAL_NULL_UNIT


def test_structural_null_has_no_decisive_fragment():
    example = _by_id(load_split(TRAIN))["train-000005"]

    assert example.decisive is None
    assert example.library is None
    assert example.subclass is None
    assert example.resampling_unit == STRUCTURAL_NULL_UNIT


def test_label_mode_and_decisive_fragment_must_agree(tmp_path):
    path = _copy_fixture(tmp_path, TRAIN)
    _edit_records(
        path,
        lambda record: record["meta"].update({"label_mode": "null_structural"}),
    )

    with pytest.raises(DatasetError, match="structural null but holds decisive fragment"):
        load_split(path)


def test_fragment_absent_from_the_sidecar_is_an_error(tmp_path):
    path = _copy_fixture(tmp_path, TRAIN)
    _edit_stats(path, lambda stats: stats["fragments"].pop("fever_true:11111111"))

    with pytest.raises(DatasetError, match="absent from the sidecar"):
        load_split(path)


def test_fragment_assigned_to_another_split_is_an_error(tmp_path):
    path = _copy_fixture(tmp_path, TRAIN)
    _edit_stats(
        path,
        lambda stats: stats["fragments"]["fever_true:11111111"].update({"split": "test"}),
    )

    with pytest.raises(DatasetError, match="assigns elsewhere"):
        load_split(path)


# --------------------------------------------------------------------------
# Clusters and the resampling unit (DD5)
# --------------------------------------------------------------------------


def test_clustered_siblings_share_a_resampling_unit():
    """``[c01]`` siblings are one idea written twice, so they are one unit.

    Counting them as two independent observations is exactly what makes a
    confidence interval too narrow.
    """
    examples = _by_id(load_split(TRAIN))

    first = examples["train-000002"]
    sibling = examples["train-000003"]
    assert first.fragment_id != sibling.fragment_id
    assert first.resampling_unit == sibling.resampling_unit == "fever_null_hedged:c01"


def test_unclustered_fragments_get_their_own_unit():
    examples = _by_id(load_split(TRAIN))

    assert examples["train-000000"].resampling_unit == "i had a high temperature all weekend"
    assert examples["train-000004"].resampling_unit == "fever_null_metaphor:c02"


def test_resampling_unit_falls_back_to_the_fragment_id(tmp_path):
    path = _copy_fixture(tmp_path, TRAIN)
    _edit_stats(
        path,
        lambda stats: stats["fragments"]["fever_true:11111111"].update({"cluster_key": ""}),
    )

    example = _by_id(load_split(path))["train-000000"]
    assert example.resampling_unit == "fever_true:11111111"


# --------------------------------------------------------------------------
# The sidecar contract (DD16)
# --------------------------------------------------------------------------


def test_sidecar_without_a_fragments_block_is_a_hard_error(tmp_path):
    """A pre-DD16 sidecar must never fall back to example-level counting.

    That fallback would report effective n as the example count -- for these
    datasets a number one to two orders of magnitude too large -- and every
    confidence interval derived from it would be far too narrow, with nothing
    raised anywhere.
    """
    path = _copy_fixture(tmp_path, TRAIN)
    _edit_stats(path, lambda stats: stats.pop("fragments"))

    with pytest.raises(DatasetError, match="missing required keys: fragments"):
        load_split(path)


def test_empty_fragments_block_is_a_hard_error(tmp_path):
    path = _copy_fixture(tmp_path, TRAIN)
    _edit_stats(path, lambda stats: stats.update({"fragments": {}}))

    with pytest.raises(DatasetError, match="empty or malformed 'fragments' block"):
        load_split(path)


def test_sidecar_missing_the_fold_configuration_is_a_hard_error(tmp_path):
    """``test`` names a different set of clusters under every fold triple."""
    path = _copy_fixture(tmp_path, TRAIN)
    _edit_stats(path, lambda stats: stats.pop("split_salt"))

    with pytest.raises(DatasetError, match="missing required keys: split_salt"):
        load_split(path)


def test_fragment_entry_missing_a_field_is_a_hard_error(tmp_path):
    path = _copy_fixture(tmp_path, TRAIN)
    _edit_stats(
        path,
        lambda stats: stats["fragments"]["fever_true:11111111"].pop("cluster_key"),
    )

    with pytest.raises(DatasetError, match="missing cluster_key"):
        load_split(path)


def test_absent_sidecar_is_a_hard_error(tmp_path):
    path = _copy_fixture(tmp_path, TRAIN)
    sidecar_path(path).unlink()

    with pytest.raises(DatasetError, match="no stats sidecar"):
        load_split(path)


def test_split_mislabelled_in_the_records_is_an_error(tmp_path):
    path = _copy_fixture(tmp_path, TRAIN)
    _edit_records(path, lambda record: record.update({"split": "test"}))

    with pytest.raises(DatasetError, match="labelled split 'test'"):
        load_split(path)


def test_expect_split_catches_mis_ordered_arguments(tmp_path):
    with pytest.raises(DatasetError, match="is split 'train' but was loaded as 'test'"):
        load_split(TRAIN, expect_split="test")


# --------------------------------------------------------------------------
# Loading a fold
# --------------------------------------------------------------------------


def test_load_fold_reads_three_agreeing_splits():
    fold = load_fold(TRAIN, VAL, TEST)

    assert [len(split) for split in fold.splits] == [6, 5, 6]
    assert fold.fold_config == (5, 0, "32")
    assert fold.signals == (SIGNAL,)


def test_load_fold_rejects_disagreeing_generator_versions(tmp_path):
    """Three splits from two generator versions produce an uninterpretable result."""
    train = _copy_fixture(tmp_path, TRAIN)
    val = _copy_fixture(tmp_path, VAL)
    test = _copy_fixture(tmp_path, TEST)
    _edit_stats(test, lambda stats: stats.update({"generator_version": 3}))

    with pytest.raises(DatasetError, match="disagree on 'generator_version'"):
        load_fold(train, val, test)


@pytest.mark.parametrize(
    ("field", "value"),
    [("folds", 10), ("fold_index", 2), ("split_salt", "7"), ("signal", "dysuria_present")],
)
def test_load_fold_rejects_disagreeing_fold_configuration(tmp_path, field, value):
    train = _copy_fixture(tmp_path, TRAIN)
    val = _copy_fixture(tmp_path, VAL)
    test = _copy_fixture(tmp_path, TEST)
    _edit_stats(val, lambda stats: stats.update({field: value}))

    with pytest.raises(DatasetError, match=f"disagree on {field!r}"):
        load_fold(train, val, test)


def test_load_fold_asserts_fragment_level_disjointness(tmp_path):
    """The generator guarantees this; the training code checks it anyway.

    A fragment on both sides of the boundary turns the test score into a
    memorisation score, and the entire meaning of the evaluation rests on it.
    """
    train = _copy_fixture(tmp_path, TRAIN)
    val = _copy_fixture(tmp_path, VAL)
    test = _copy_fixture(tmp_path, TEST)
    leaked = json.loads(sidecar_path(train).read_text())["fragments"]["fever_true:11111111"]
    leaked = dict(leaked, split="test")
    _edit_stats(test, lambda stats: stats["fragments"].update({"fever_true:11111111": leaked}))

    with pytest.raises(DatasetError, match="appear in both the 'train' and 'test' splits"):
        load_fold(train, val, test)


def test_load_fold_asserts_cluster_level_disjointness(tmp_path):
    """Splitting a cluster leaks as effectively as splitting a fragment.

    Only the cluster check catches it: the two fragment ids differ, so
    fragment-level disjointness is satisfied while the same idea sits on both
    sides.
    """
    train = _copy_fixture(tmp_path, TRAIN)
    val = _copy_fixture(tmp_path, VAL)
    test = _copy_fixture(tmp_path, TEST)
    _edit_stats(
        test,
        lambda stats: stats["fragments"]["fever_null_hedged:10101010"].update(
            {"cluster_key": "fever_null_hedged:c01"}
        ),
    )

    with pytest.raises(DatasetError, match="clusters straddle the 'train'/'test' boundary"):
        load_fold(train, val, test)


def test_load_fold_pins_one_signal_set_across_splits(tmp_path):
    train = _copy_fixture(tmp_path, TRAIN)
    val = _copy_fixture(tmp_path, VAL)
    test = _copy_fixture(tmp_path, TEST)

    fold = load_fold(train, val, test, signals=("fever_present", "dysuria_present"))

    assert {split.signals for split in fold.splits} == {("fever_present", "dysuria_present")}


# --------------------------------------------------------------------------
# The offline/runtime boundary
# --------------------------------------------------------------------------


def test_app_never_imports_the_offline_tooling():
    """``app/`` must not import ``scripts/`` -- either package.

    The rule currently lives only in a module docstring
    (``scripts/synthetic_data/ruleset.py``), so nothing enforced it in either
    direction before this test. It covers both offline packages rather than
    just the new one: production must never acquire a dependency on training
    tooling, and a single guard is cheaper to keep honest than two.
    """
    app_root = Path(__file__).resolve().parent.parent / "app"
    offenders: list[str] = []
    for source in sorted(app_root.rglob("*.py")):
        tree = ast.parse(source.read_text(encoding="utf-8"), filename=str(source))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                names = [node.module or ""]
            else:
                continue
            for name in names:
                if name == "scripts" or name.startswith("scripts."):
                    offenders.append(f"{source.relative_to(app_root.parent)}:{node.lineno} {name}")

    assert not offenders, "app/ imports offline tooling: " + ", ".join(offenders)

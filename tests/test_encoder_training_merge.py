"""Unit tests for scripts/encoder_training/merge.py.

Pure unit tests: no database, no torch, no GPU, so there is no ``pytestmark``.
The module under test is stdlib-only for exactly that reason -- the merge decides
what the joint run's numbers mean, so CI's unit job has to cover it.

The fixtures are **built here rather than committed**, unlike
``tests/fixtures/encoder_training/``. A six-signal five-fold tree is forty-five
files, and the properties under test (which structural nulls are shared, which
head is masked where, which fragment entries conflict) are only legible when the
generator's rules are restated as a few lines of Python beside the assertions.
:func:`write_tree` is a miniature of the real generator and follows its two
load-bearing rules: split membership is a pure function of the cluster key, and
structural nulls do not depend on the signal.

The contract test is :func:`test_load_folds_accepts_the_merged_tree`. If the
merged output ever needs a new escape hatch in ``dataset.py`` to load, the merge
is wrong, not the loader.
"""

import json
from pathlib import Path

import pytest

from scripts.encoder_training.dataset import (
    CLASS_NULL,
    CLASS_TRUE,
    MASKED_CLASS,
    STRUCTURAL_NULL_UNIT,
    fold_dataset_path,
    load_folds,
    sidecar_path,
)
from scripts.encoder_training.merge import (
    DEFAULT_SIGNALS,
    MergeError,
    cluster_collisions,
    load_source_split,
    merge_folds,
    merge_split,
)

SIGNALS = ("fever_present", "dysuria_present", "nocturia_present")
FOLDS = 2
SALT = "32"
GENERATOR_VERSION = 3

#: The arm the fixture tree belongs to. Zero, because that is the setting under
#: which every filler-only example is also a ``null_structural`` one and the two
#: sets the merge could key on coincide; the tests that pull them apart set
#: ``meta.filler_only`` themselves.
COMPANION_SHARE = 0.0

#: How many examples of each kind one source split holds. Small enough to read,
#: and asymmetric so an off-by-one in the interleave cannot pass by luck.
OWNED_PER_SPLIT = 3
STRUCTURAL_PER_SPLIT = 2

#: Fragments per library, each its own cluster. Four is the smallest number that
#: leaves every split non-empty in every fold under :func:`_fragment_split`.
PER_LIBRARY = 4

FILLER_LIBRARIES = ("filler_a", "filler_b")


# --------------------------------------------------------------------------
# A miniature of the generator
# --------------------------------------------------------------------------


def _library(signal: str) -> str:
    return f"{signal.removesuffix('_present')}_true"


def _fragment_split(index: int, fold_index: int, folds: int = FOLDS) -> str:
    """Which split a fragment lands in, as a function of its index and the fold.

    Stands in for ``manifest.fold_bucket``, and reproduces the two properties
    the merge actually depends on: the assignment does not depend on the signal,
    so all six trees agree; and every cluster is a *test* cluster in exactly one
    fold, which is what ``_check_test_partition`` asserts over the merged tree.
    """
    if index % folds == fold_index:
        return "test"
    return "train" if (index // folds) % 2 == 0 else "val"


def _library_fragment_ids(library: str, split: str, fold_index: int) -> list[str]:
    return [
        f"{library}:c{index}"
        for index in range(PER_LIBRARY)
        if _fragment_split(index, fold_index) == split
    ]


def _entry(library: str, index: int, split: str) -> dict:
    """One provenance entry, keyed the way the generator keys them.

    ``cluster_key`` is the tagged cluster id where there is one, and the
    normalised text otherwise -- the fallback that is not library-qualified and
    can therefore collide across libraries, which
    :func:`test_cluster_collision_is_reported_not_fatal` exercises.
    """
    return {
        "library": library,
        "cluster_key": f"{library}:c{index}",
        "fragment_type": "filler" if library in FILLER_LIBRARIES else "positive",
        "signal_key": None
        if library in FILLER_LIBRARIES
        else f"{library[: -len('_true')]}_present",
        "subclass": None,
        "split": split,
    }


def _split_fragments(signal: str, split: str, fold_index: int) -> dict[str, dict]:
    """Every fragment this signal's split could draw on.

    The filler entries are byte-identical across signals on purpose: the six
    real trees share the filler libraries entirely, so the merged provenance
    block is mostly a union of things that already agree -- and a conflict there
    is the drift worth failing on.
    """
    fragments: dict[str, dict] = {}
    for library in (_library(signal), *FILLER_LIBRARIES):
        for index in range(PER_LIBRARY):
            if _fragment_split(index, fold_index) == split:
                fragments[f"{library}:c{index}"] = _entry(library, index, split)
    return fragments


def _records(signal: str, split: str, fold_index: int) -> list[dict]:
    """One source split: this signal's own examples, then the shared nulls.

    The filler-only examples carry the same ids, texts and fragment ids for every
    signal, because the real generator's seed derivation does not include the
    signal. That identity is what the union depends on.

    ``meta.filler_only`` is what the merge deduplicates on, so the miniature
    writes it the way the generator does -- true exactly when every fragment is
    filler, which at ``--companion-share 0`` is every structural null.
    """
    decisive = _library_fragment_ids(_library(signal), split, fold_index)
    fillers = [_library_fragment_ids(library, split, fold_index)[0] for library in FILLER_LIBRARIES]

    records = []
    for index in range(OWNED_PER_SPLIT):
        records.append(
            {
                "example_id": f"{split}-{index:06d}",
                "split": split,
                "text": f"{signal} example {index} in {split}.",
                "labels": {signal: True},
                "meta": {
                    "label_mode": "true",
                    "filler_only": False,
                    "fragment_ids": [decisive[index % len(decisive)], fillers[0]],
                    "seed": 42,
                    "generator_version": GENERATOR_VERSION,
                },
            }
        )
    for index in range(STRUCTURAL_PER_SPLIT):
        records.append(
            {
                "example_id": f"{split}-{OWNED_PER_SPLIT + index:06d}",
                "split": split,
                "text": f"shared filler {index} in {split}.",
                "labels": {signal: None},
                "meta": {
                    "label_mode": "null_structural",
                    "filler_only": True,
                    "fragment_ids": list(fillers),
                    "seed": 42,
                    "generator_version": GENERATOR_VERSION,
                },
            }
        )
    return records


def _stats(signal: str, split: str, fold_index: int) -> dict:
    return {
        "generator_version": GENERATOR_VERSION,
        "seed": 42,
        "signal": signal,
        "split": split,
        "folds": FOLDS,
        "fold_index": fold_index,
        "split_salt": SALT,
        "requested": {"companion_share": COMPANION_SHARE},
        "fragments": _split_fragments(signal, split, fold_index),
    }


def write_split(directory: Path, signal: str, fold_index: int, split: str, **edits) -> Path:
    """Write one source split and its sidecar, with optional surgical edits.

    ``records`` and ``stats`` take a callable applied to the built value, which
    is how the failure-path tests introduce exactly one defect into an otherwise
    valid tree.
    """
    records = _records(signal, split, fold_index)
    stats = _stats(signal, split, fold_index)
    if "records" in edits:
        edits["records"](records, signal)
    if "stats" in edits:
        edits["stats"](stats)

    path = fold_dataset_path(directory, signal, fold_index, split)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(record) + "\n" for record in records), encoding="utf-8")
    sidecar_path(path).write_text(json.dumps(stats, indent=2), encoding="utf-8")
    return path


def write_tree(directory: Path, *, signals=SIGNALS, folds=FOLDS, **edits) -> Path:
    """Write a whole per-signal fold tree: every signal, fold and split."""
    for signal in signals:
        for fold_index in range(folds):
            for split in ("train", "val", "test"):
                write_split(directory, signal, fold_index, split, **edits)
    return directory


def _sources(directory: Path, split="train", fold_index=0, signals=SIGNALS):
    return [
        load_source_split(
            fold_dataset_path(directory, signal, fold_index, split), signal=signal, split=split
        )
        for signal in signals
    ]


def _by_id(records):
    return {record["example_id"]: record for record in records}


# --------------------------------------------------------------------------
# The contract: the loader accepts what the merge writes
# --------------------------------------------------------------------------


def test_load_folds_accepts_the_merged_tree(tmp_path):
    """The whole point of the merge: no new escape hatch in dataset.py.

    ``load_folds`` runs ``_check_fold_agreement``, ``_check_disjoint`` and
    ``_check_test_partition`` over the result, which is every check the merge is
    meant to preserve.
    """
    write_tree(tmp_path)
    result = merge_folds(tmp_path, signals=SIGNALS, folds=FOLDS)

    loaded = load_folds(tmp_path, result.name, folds=FOLDS)

    assert len(loaded) == FOLDS
    assert loaded[0].signals == tuple(sorted(SIGNALS))
    assert loaded[0].train.signal == "joint3"
    assert loaded[0].fold_config == (FOLDS, 0, SALT)


def test_merged_tree_keeps_every_head_masked_where_it_had_no_label(tmp_path):
    """DD3: the merge adds no supervision to any head.

    A dysuria example carries a dysuria label and *no fever key*, which
    ``dataset`` reads as "mask this head" rather than "fever is null here".
    Filling those keys with ``null`` is ticket 6, and doing it here would teach
    every head to answer "not mentioned" on every other head's data.
    """
    write_tree(tmp_path)
    merge_folds(tmp_path, signals=SIGNALS, folds=FOLDS)
    train = load_folds(tmp_path, "joint3", folds=FOLDS)[0].train
    examples = {example.example_id: example for example in train.examples}

    owned = examples["fever_present:train-000000"]
    assert owned.class_for("fever_present") == CLASS_TRUE
    assert owned.is_labelled("fever_present") is True
    for other in ("dysuria_present", "nocturia_present"):
        assert owned.class_for(other) == MASKED_CLASS
        assert owned.is_labelled(other) is False

    # Each head keeps exactly the labelled positions it had alone.
    for signal in SIGNALS:
        labelled = [example for example in train.examples if example.is_labelled(signal)]
        assert len(labelled) == OWNED_PER_SPLIT + STRUCTURAL_PER_SPLIT


def test_shared_structural_null_is_null_for_every_signal(tmp_path):
    write_tree(tmp_path)
    merge_folds(tmp_path, signals=SIGNALS, folds=FOLDS)
    train = load_folds(tmp_path, "joint3", folds=FOLDS)[0].train
    shared = {example.example_id: example for example in train.examples}[
        f"shared:train-{OWNED_PER_SPLIT:06d}"
    ]

    assert all(shared.class_for(signal) == CLASS_NULL for signal in SIGNALS)
    assert all(shared.is_labelled(signal) for signal in SIGNALS)
    assert shared.resampling_unit == STRUCTURAL_NULL_UNIT


# --------------------------------------------------------------------------
# Ids, and the pairing that depends on them
# --------------------------------------------------------------------------


def test_ids_are_namespaced_and_source_ids_restore_the_originals(tmp_path):
    """DD4: every merged example keeps the id it had in its own tree.

    The joint run reports signal S's predictions under ``meta.source_ids[S]``,
    which is what makes A1-vs-A3 pairable on example id. Without it, three trees
    that all number from ``train-000000`` would collide on every id.
    """
    write_tree(tmp_path)
    records, _ = merge_split(_sources(tmp_path), name="joint3")
    indexed = _by_id(records)

    assert len(indexed) == len(records)
    owned = indexed["dysuria_present:train-000001"]
    assert owned["meta"]["source_ids"] == {"dysuria_present": "train-000001"}

    shared = indexed[f"shared:train-{OWNED_PER_SPLIT:06d}"]
    assert shared["meta"]["source_ids"] == {
        signal: f"train-{OWNED_PER_SPLIT:06d}" for signal in SIGNALS
    }


def test_meta_is_preserved_verbatim(tmp_path):
    write_tree(tmp_path)
    records, _ = merge_split(_sources(tmp_path), name="joint3")
    owned = _by_id(records)["fever_present:train-000000"]

    assert owned["text"] == "fever_present example 0 in train."
    assert owned["split"] == "train"
    assert owned["meta"]["label_mode"] == "true"
    assert (
        owned["meta"]["fragment_ids"]
        == _records("fever_present", "train", 0)[0]["meta"]["fragment_ids"]
    )
    assert owned["meta"]["seed"] == 42
    assert owned["meta"]["generator_version"] == GENERATOR_VERSION


# --------------------------------------------------------------------------
# Deduplication and volume
# --------------------------------------------------------------------------


def test_structural_nulls_are_kept_once(tmp_path):
    write_tree(tmp_path)
    records, stats = merge_split(_sources(tmp_path), name="joint3")

    expected = len(SIGNALS) * OWNED_PER_SPLIT + STRUCTURAL_PER_SPLIT
    assert len(records) == expected
    assert stats["realised"]["count"] == expected
    assert stats["realised"]["label_modes"]["null_structural"] == STRUCTURAL_PER_SPLIT
    assert stats["merged_from"]["filler_only"] == {
        "kept": STRUCTURAL_PER_SPLIT,
        "dropped_as_duplicates": STRUCTURAL_PER_SPLIT * (len(SIGNALS) - 1),
        "kept_per_signal": 0,
        "note": stats["merged_from"]["filler_only"]["note"],
    }
    assert stats["merged_from"]["companion_share"] == COMPANION_SHARE


def _treated(stats):
    """Mark the fixture tree as the treatment arm, so P > 0 behaviour applies."""
    stats["requested"]["companion_share"] = 0.5


def _companion_in_the_first_structural_null(records, signal):
    """Give every tree's first structural null a companion, the way P > 0 does.

    A companion is drawn from the *primary* signal's eligible pool, so the text
    differs by signal and the example stops being one every tree emitted. The
    generator records that as ``meta.filler_only`` false while the label mode
    stays ``null_structural``: the example still holds no fragment decisive for
    its own signal, which is what the mode has always meant.
    """
    for record in records:
        if record["meta"]["label_mode"] == "null_structural":
            record["meta"]["filler_only"] = False
            record["text"] = f"a {signal} companion sentence."
            return


def test_a_structural_null_carrying_a_companion_is_kept_per_signal(tmp_path):
    """DD11's relaxation: the dedup keys on filler_only, not on the label mode.

    Deduplicating on the mode would assert three trees emitted one example that
    they did not, and would keep whichever arrived first -- the exact silent
    collapse ``check_structural_nulls`` exists to prevent, arriving through the
    door the companion draw opened.
    """
    write_tree(tmp_path, records=_companion_in_the_first_structural_null)
    records, stats = merge_split(_sources(tmp_path), name="joint3")
    indexed = _by_id(records)

    shared_left = STRUCTURAL_PER_SPLIT - 1
    assert stats["merged_from"]["filler_only"]["kept"] == shared_left
    assert len(records) == len(SIGNALS) * (OWNED_PER_SPLIT + 1) + shared_left

    for signal in SIGNALS:
        kept = indexed[f"{signal}:train-{OWNED_PER_SPLIT:06d}"]
        assert kept["text"] == f"a {signal} companion sentence."
        assert kept["meta"]["label_mode"] == "null_structural"
        # Its own head is supervised with null; the others stay masked, exactly
        # as for any other example only one tree holds.
        assert kept["labels"] == {signal: None}

    # The mode is still a null_structural for every copy, so a merged tree at
    # P > 0 is bigger without any head's mix changing shape.
    assert stats["realised"]["label_modes"]["null_structural"] == (len(SIGNALS) * 1 + shared_left)


def test_a_filler_only_example_only_some_sources_emitted_is_kept_per_signal(tmp_path):
    """The case the real libraries produce at P > 0, and the reason for matching by id.

    ``generate`` redraws an example whose normalised text it has already emitted,
    on the same per-example RNG, and the ``seen`` set diverges between trees as
    soon as their companions do -- so one index can come out holding a companion
    in one tree and filler alone in the next. Measured at
    ``--companion-share 0.5``: three such examples in a 10,000-example split.
    Matching by position would call that a hard error; matching by id keeps the
    1118 the sources agree on and lets the three ride as owned examples.
    """

    def only_fever_keeps_it(records, signal):
        if signal == "fever_present":
            return
        for record in records:
            if record["meta"]["label_mode"] == "null_structural":
                record["meta"]["filler_only"] = False
                record["text"] = f"a {signal} companion sentence."
                return

    write_tree(tmp_path, records=only_fever_keeps_it, stats=_treated)
    records, stats = merge_split(_sources(tmp_path), name="joint3")
    indexed = _by_id(records)

    disputed = f"train-{OWNED_PER_SPLIT:06d}"
    assert stats["merged_from"]["filler_only"]["kept"] == STRUCTURAL_PER_SPLIT - 1
    assert stats["merged_from"]["filler_only"]["kept_per_signal"] == 1

    # fever still holds it as filler-only, and it is kept under fever's own id
    # rather than as a shared copy asserting null for heads that never saw it.
    assert f"shared:{disputed}" not in indexed
    assert indexed[f"fever_present:{disputed}"]["labels"] == {"fever_present": None}
    assert indexed[f"fever_present:{disputed}"]["meta"]["filler_only"] is True
    for signal in SIGNALS[1:]:
        assert indexed[f"{signal}:{disputed}"]["text"] == f"a {signal} companion sentence."


def test_records_are_interleaved_so_a_prefix_is_representative(tmp_path):
    write_tree(tmp_path)
    records, _ = merge_split(_sources(tmp_path), name="joint3")

    heads = [record["example_id"].split(":")[0] for record in records[: len(SIGNALS) + 1]]
    assert heads == [*SIGNALS, "shared"]


def test_merged_sidecar_records_the_sources(tmp_path):
    write_tree(tmp_path)
    _, stats = merge_split(_sources(tmp_path), name="joint3")

    assert stats["signal"] == "joint3"
    assert stats["split"] == "train"
    assert stats["folds"] == FOLDS
    assert stats["fold_index"] == 0
    assert stats["split_salt"] == SALT
    assert stats["seed"] == 42
    assert [source["signal"] for source in stats["merged_from"]["sources"]] == list(SIGNALS)
    assert stats["merged_from"]["sources"][0] == {
        "signal": "fever_present",
        "path": str(fold_dataset_path(tmp_path, "fever_present", 0, "train")),
        "examples": OWNED_PER_SPLIT + STRUCTURAL_PER_SPLIT,
        "signal_owned": OWNED_PER_SPLIT,
        "filler_only": STRUCTURAL_PER_SPLIT,
        "companion_share": COMPANION_SHARE,
        "seed": 42,
    }


def test_fragments_are_unioned(tmp_path):
    """Every source's block, with the filler libraries' shared entries kept once."""
    write_tree(tmp_path)
    _, stats = merge_split(_sources(tmp_path), name="joint3")

    expected = set()
    for signal in SIGNALS:
        expected |= set(_split_fragments(signal, "train", 0))
    assert set(stats["fragments"]) == expected
    assert set(stats["fragments"]) >= {
        f"{library}:c1" for library in ("fever_true", "dysuria_true", *FILLER_LIBRARIES)
    }


def test_merge_folds_writes_every_fold_and_split(tmp_path):
    write_tree(tmp_path)
    result = merge_folds(tmp_path, signals=SIGNALS, folds=FOLDS)

    assert result.name == "joint3"
    assert len(result.paths) == FOLDS * 3
    assert all(path.is_file() and sidecar_path(path).is_file() for path in result.paths)
    assert result.examples == FOLDS * 3 * (len(SIGNALS) * OWNED_PER_SPLIT + STRUCTURAL_PER_SPLIT)
    assert result.warnings == ()


def test_merge_folds_writes_to_a_separate_out_dir(tmp_path):
    write_tree(tmp_path / "source")
    result = merge_folds(
        tmp_path / "source", signals=SIGNALS, out_dir=tmp_path / "merged", folds=FOLDS, name="joint"
    )

    assert all(path.parent == tmp_path / "merged" for path in result.paths)
    assert load_folds(tmp_path / "merged", "joint", folds=FOLDS)


def test_default_signals_are_the_six_with_libraries():
    """DD8: six heads, not seven. recent_uti_present has no libraries."""
    assert "recent_uti_present" not in DEFAULT_SIGNALS
    assert len(DEFAULT_SIGNALS) == 6


# --------------------------------------------------------------------------
# The command line
# --------------------------------------------------------------------------


def test_cli_merges_and_the_result_loads(tmp_path):
    from scripts.encoder_training.__main__ import main

    write_tree(tmp_path)
    status = main(
        [
            "merge-folds",
            "--data-dir",
            str(tmp_path),
            "--signals",
            *SIGNALS,
            "--folds",
            str(FOLDS),
        ]
    )

    assert status == 0
    assert load_folds(tmp_path, "joint3", folds=FOLDS)


def test_cli_reports_a_bad_tree_as_a_message_not_a_traceback(tmp_path, capsys):
    from scripts.encoder_training.__main__ import main

    write_tree(tmp_path)
    fold_dataset_path(tmp_path, "fever_present", 0, "train").unlink()

    status = main(
        ["merge-folds", "--data-dir", str(tmp_path), "--signals", *SIGNALS, "--folds", str(FOLDS)]
    )

    assert status == 2
    assert "source dataset not found" in capsys.readouterr().err


# --------------------------------------------------------------------------
# Cluster-key collisions: reported, not fatal
# --------------------------------------------------------------------------


def test_cluster_collision_is_reported_not_fatal(tmp_path):
    """Untagged fragments key on text, which is not library-qualified.

    Identical text in two signals' libraries becomes one resampling unit
    spanning both. That deflates effective n rather than inflating it, so it is
    the safe direction -- but it is invisible, which is the thing worth fixing.
    """

    def collide(stats):
        if stats["signal"] in ("fever_present", "dysuria_present"):
            for entry in stats["fragments"].values():
                if entry["library"] == _library(stats["signal"]):
                    entry["cluster_key"] = "same idea twice"

    write_tree(tmp_path, stats=collide)
    result = merge_folds(tmp_path, signals=SIGNALS, folds=FOLDS)

    assert [collision["cluster_key"] for collision in result.collisions] == ["same idea twice"]
    assert result.collisions[0]["libraries"] == ["dysuria_true", "fever_true"]
    assert len(result.warnings) == 1
    assert "effective sample size" in result.warnings[0]

    stats = json.loads(sidecar_path(result.paths[0]).read_text(encoding="utf-8"))
    collisions = stats["merged_from"]["cluster_key_collisions"]
    assert collisions["count"] == 1
    assert collisions["keys"][0]["cluster_key"] == "same idea twice"


def test_cluster_collisions_ignores_keys_within_one_library():
    """Two fragments of one tagged cluster are the resampling unit working."""
    fragments = {
        "fever_true:a": {"library": "fever_true", "cluster_key": "fever_true:c01"},
        "fever_true:b": {"library": "fever_true", "cluster_key": "fever_true:c01"},
    }

    assert cluster_collisions(fragments) == ()


# --------------------------------------------------------------------------
# Failure paths
# --------------------------------------------------------------------------


def test_divergent_structural_nulls_are_a_hard_error(tmp_path):
    """The identity the union rests on, asserted rather than assumed."""

    def diverge(records, signal):
        if signal != "nocturia_present":
            return
        for record in records:
            if record["meta"]["label_mode"] == "null_structural":
                record["text"] = "a different filler sentence entirely."

    write_tree(tmp_path, records=diverge)

    with pytest.raises(MergeError, match="filler-only example 'train-000003' disagrees on text"):
        merge_folds(tmp_path, signals=SIGNALS, folds=FOLDS)


def test_divergent_structural_null_fragment_ids_are_a_hard_error(tmp_path):
    def relabel(records, signal):
        if signal != "dysuria_present":
            return
        for record in records:
            if record["meta"]["label_mode"] == "null_structural":
                record["meta"]["fragment_ids"] = list(reversed(record["meta"]["fragment_ids"]))

    write_tree(tmp_path, records=relabel)

    with pytest.raises(MergeError, match="disagrees on meta.fragment_ids"):
        merge_folds(tmp_path, signals=SIGNALS, folds=FOLDS)


def test_a_missing_structural_null_is_a_hard_error(tmp_path):
    def drop_one(records, signal):
        if signal != "dysuria_present":
            return
        for index, record in enumerate(records):
            if record["meta"]["label_mode"] == "null_structural":
                del records[index]
                return

    write_tree(tmp_path, records=drop_one)

    with pytest.raises(
        MergeError, match=r"filler-only in some sources and not in others \(train-000003\)"
    ):
        merge_folds(tmp_path, signals=SIGNALS, folds=FOLDS)


def test_conflicting_fragment_entries_are_a_hard_error(tmp_path):
    """A dict union would first-win this, and the two trees would disagree silently."""

    def conflict(stats):
        if stats["signal"] == "nocturia_present":
            for entry in stats["fragments"].values():
                if entry["library"] == "filler_a":
                    entry["fragment_type"] = "positive"

    write_tree(tmp_path, stats=conflict)

    with pytest.raises(MergeError, match="disagrees on 'fragment_type'"):
        merge_folds(tmp_path, signals=SIGNALS, folds=FOLDS)


def test_disagreeing_split_salt_is_a_hard_error(tmp_path):
    def resalt(stats):
        if stats["signal"] == "dysuria_present":
            stats["split_salt"] = "99"

    write_tree(tmp_path, stats=resalt)

    with pytest.raises(MergeError, match="disagree on 'split_salt'"):
        merge_folds(tmp_path, signals=SIGNALS, folds=FOLDS)


def test_disagreeing_generator_version_is_a_hard_error(tmp_path):
    def rewind(stats):
        if stats["signal"] == "dysuria_present":
            stats["generator_version"] = 1

    write_tree(tmp_path, stats=rewind)

    with pytest.raises(MergeError, match="disagree on 'generator_version'"):
        merge_folds(tmp_path, signals=SIGNALS, folds=FOLDS)


def test_disagreeing_companion_share_is_a_hard_error(tmp_path):
    """One arm's examples must not end up in the other arm's tree.

    Same shape and same reasoning as the ``generator_version`` refusal: a merged
    tree that is half Arm 0 and half Arm P loads cleanly, trains cleanly, and
    answers the question the two arms exist to ask with a dataset that is
    neither of them.
    """

    def treat(stats):
        if stats["signal"] == "dysuria_present":
            stats["requested"]["companion_share"] = 0.5

    write_tree(tmp_path, stats=treat)

    with pytest.raises(MergeError, match=r"disagree on 'requested.companion_share'"):
        merge_folds(tmp_path, signals=SIGNALS, folds=FOLDS)


def test_a_sidecar_without_a_companion_share_is_refused(tmp_path):
    """A pre-companion tree is regenerated, not merged on a default of zero."""

    def strip(stats):
        del stats["requested"]

    write_tree(tmp_path, stats=strip)

    with pytest.raises(MergeError, match=r"no 'requested.companion_share'"):
        merge_folds(tmp_path, signals=SIGNALS, folds=FOLDS)


def test_a_record_without_filler_only_is_refused(tmp_path):
    """The key the dedup runs on. Re-deriving it would be right only by luck."""

    def strip(records, signal):
        for record in records:
            del record["meta"]["filler_only"]

    write_tree(tmp_path, records=strip)

    with pytest.raises(MergeError, match="no boolean 'meta.filler_only'"):
        merge_folds(tmp_path, signals=SIGNALS, folds=FOLDS)


def test_a_filler_only_example_that_is_not_a_structural_null_is_refused(tmp_path):
    """Filler everywhere means nothing decisive, so the two cannot disagree."""

    def relabel(records, signal):
        records[0]["meta"]["filler_only"] = True

    write_tree(tmp_path, records=relabel)

    with pytest.raises(MergeError, match="is filler-only but has label mode 'true'"):
        merge_folds(tmp_path, signals=SIGNALS, folds=FOLDS)


def test_a_source_missing_a_fold_is_a_hard_error(tmp_path):
    write_tree(tmp_path)
    fold_dataset_path(tmp_path, "nocturia_present", 1, "val").unlink()

    with pytest.raises(MergeError, match="source dataset not found"):
        merge_folds(tmp_path, signals=SIGNALS, folds=FOLDS)


def test_a_source_missing_its_sidecar_is_a_hard_error(tmp_path):
    write_tree(tmp_path)
    sidecar_path(fold_dataset_path(tmp_path, "fever_present", 0, "test")).unlink()

    with pytest.raises(MergeError, match="no stats sidecar"):
        merge_folds(tmp_path, signals=SIGNALS, folds=FOLDS)


def test_a_multi_signal_source_is_refused(tmp_path):
    """An already-merged tree merged again would build false label vectors."""

    def widen(records, signal):
        for record in records:
            record["labels"]["some_other_signal"] = None

    write_tree(tmp_path, records=widen)

    with pytest.raises(MergeError, match="carries labels for"):
        merge_folds(tmp_path, signals=SIGNALS, folds=FOLDS)


def test_a_structural_null_that_is_not_null_is_refused(tmp_path):
    """The shared copy asserts null six times; each source must assert its own."""

    def falsify(records, signal):
        for record in records:
            if record["meta"]["label_mode"] == "null_structural":
                record["labels"] = dict.fromkeys(record["labels"], False)

    write_tree(tmp_path, records=falsify)

    with pytest.raises(MergeError, match="is a structural null but labels"):
        merge_folds(tmp_path, signals=SIGNALS, folds=FOLDS)


def test_a_sidecar_naming_the_wrong_signal_is_refused(tmp_path):
    write_tree(tmp_path)
    path = fold_dataset_path(tmp_path, "fever_present", 0, "train")
    stats = json.loads(sidecar_path(path).read_text(encoding="utf-8"))
    stats["signal"] = "flank_pain_present"
    sidecar_path(path).write_text(json.dumps(stats), encoding="utf-8")

    with pytest.raises(MergeError, match="records signal"):
        merge_folds(tmp_path, signals=SIGNALS, folds=FOLDS)


def test_merged_name_may_not_shadow_a_source(tmp_path):
    write_tree(tmp_path)

    with pytest.raises(MergeError, match="also one of the source signals"):
        merge_folds(tmp_path, signals=SIGNALS, folds=FOLDS, name="fever_present")


def test_a_merge_needs_at_least_two_signals(tmp_path):
    write_tree(tmp_path)

    with pytest.raises(MergeError, match="at least two signals"):
        merge_folds(tmp_path, signals=("fever_present",), folds=FOLDS)


def test_duplicate_signals_are_refused(tmp_path):
    write_tree(tmp_path)

    with pytest.raises(MergeError, match="must be distinct signals"):
        merge_folds(tmp_path, signals=("fever_present", "fever_present"), folds=FOLDS)


# --------------------------------------------------------------------------
# What the merged provenance does to the report's cluster-tag coverage
# (implementation plan task 4, instruction 5)
# --------------------------------------------------------------------------


def _untag(library: str):
    """A ``stats`` edit that makes one library look as though it carries no markers.

    ``manifest.cluster_key`` hashes ``{library}:{tag}`` for a tagged line and the
    line's own normalised text for an untagged one, so an unqualified key is
    exactly what an untagged library leaves in the sidecar. Kept unique per
    fragment, because two lines sharing a cluster key would be one cluster and
    ``_check_disjoint`` would rightly refuse the tree.
    """

    def edit(stats):
        for fragment_id, entry in stats["fragments"].items():
            if entry["library"] == library:
                entry["cluster_key"] = f"unnamespaced text {fragment_id.rsplit(':', 1)[-1]}"

    return edit


def test_cluster_tag_coverage_reads_one_signal_out_of_a_merged_fragments_block(tmp_path):
    """A merged tree's provenance spans every merged signal, and coverage must not.

    The coverage percentages are what a reader uses to decide whether to trust
    the intervals above them, and after the merge the block they are computed
    from is N times the size it was when a fold tree held one signal. The
    ``signal=`` filter is therefore doing considerably more work than it was
    written for, so it is tested against a real merged tree rather than against
    a hand-built list of fragments.
    """
    from scripts.encoder_training.__main__ import _fragment_provenance
    from scripts.encoder_training.report import cluster_tag_coverage

    write_tree(tmp_path, stats=_untag("dysuria_true"))
    merged = tmp_path / "merged"
    merge_folds(tmp_path, signals=SIGNALS, out_dir=merged, name="joint3", folds=FOLDS)
    fragments = _fragment_provenance(load_folds(merged, "joint3", folds=FOLDS))

    # The merged block really does span every signal's libraries plus the
    # shared filler, or this test would prove nothing.
    assert {fragment.library for fragment in fragments} == {
        *(f"{signal.removesuffix('_present')}_true" for signal in SIGNALS),
        *FILLER_LIBRARIES,
    }

    fever = cluster_tag_coverage(fragments, signal="fever_present")
    assert [row["library"] for row in fever["libraries"]] == ["fever_true"]
    assert fever["untagged_libraries"] == []
    assert fever["libraries"][0]["coverage"] == 1.0

    # The one untagged library shows up under its own signal and nowhere else,
    # so a reader of the fever report is not warned about a dysuria library and
    # a reader of the dysuria report is.
    dysuria = cluster_tag_coverage(fragments, signal="dysuria_present")
    assert dysuria["untagged_libraries"] == ["dysuria_true"]
    assert dysuria["libraries"][0]["coverage"] == 0.0
    assert dysuria["total_fragments"] == PER_LIBRARY

    # Filler carries no signal and is never a decisive fragment, so it must not
    # appear in any signal's coverage table -- five permanently-0% rows above a
    # warning about something else.
    for signal in SIGNALS:
        coverage = cluster_tag_coverage(fragments, signal=signal)
        libraries = {row["library"] for row in coverage["libraries"]}
        assert not libraries & set(FILLER_LIBRARIES)

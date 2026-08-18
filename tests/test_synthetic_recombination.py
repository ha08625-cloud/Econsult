"""Unit tests for the offline synthetic fragment tooling.

These are pure unit tests with no database, so there is no ``pytestmark``.
"""

import hashlib
import json
import math
import re
from collections import Counter
from dataclasses import replace
from pathlib import Path

import pytest

from scripts.synthetic_data.__main__ import DEFAULT_FOLD_SALT
from scripts.synthetic_data.__main__ import main as cli_main
from scripts.synthetic_data.lint import (
    NULL_ON_BLOCK_HEADER,
    SIGNAL_LEXICONS,
    absent_pair_hits,
    cross_signal_cells,
    cross_split_near_duplicates,
    declared_pairs,
    filler_lexicon_hits,
    hedge_marker_hits,
    lexicon_matches,
    policy_pairs,
    render_cross_signal_report,
    render_report,
    signal_language_hits,
    undeclared_pairs,
)
from scripts.synthetic_data.manifest import (
    SPLITS,
    Fragment,
    LibrarySpec,
    ManifestError,
    NullOn,
    assign_split,
    bucket_coverage,
    check_no_empty_cells,
    cluster_key,
    deduplicate,
    find_fold_salts,
    fold_bucket,
    load_fragments,
    parse_line,
    parse_manifest,
    read_library,
)
from scripts.synthetic_data.normalise import normalise
from scripts.synthetic_data.recombine import (
    DEFAULT_FRAGMENT_COUNTS,
    EMIT_SIGNALS_MODES,
    FRAGMENT_TYPE_LABELS,
    LABEL_MODES,
    DistributionError,
    PoolError,
    PoolExhaustedError,
    assemble_text,
    build_pools,
    build_stats,
    generate,
    label_vector,
    labels_for_mode,
    parse_distribution,
    parse_fragment_counts,
    to_record,
)
from scripts.synthetic_data.ruleset import RulesetError, encoder_signals, validate_signal

# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------


def _entry(name: str, **overrides) -> dict:
    entry = {
        "name": name,
        "file": f"{name}.txt",
        "signal_key": None,
        "fragment_type": "filler",
    }
    entry.update(overrides)
    # Filler is only eligible for a signal it has been declared null on, so a
    # fixture filler library needs the declaration the real ones carry or
    # build_pools drops it. Declared here rather than in each fixture so a new
    # fixture cannot forget it; a signal library is skipped because declaring
    # null_on for its own signal is an error.
    if entry["signal_key"] is None:
        entry.setdefault("null_on", {SIGNAL: {"basis": "absent"}})
    return entry


def _write_manifest(base: Path, entries: list[dict], libraries: dict[str, list[str]]) -> Path:
    """Write a manifest plus its library files, returning the manifest path."""
    for filename, lines in libraries.items():
        (base / filename).write_text("\n".join(lines) + "\n", encoding="utf-8")
    manifest_path = base / "manifest.json"
    manifest_path.write_text(json.dumps({"version": 1, "libraries": entries}), encoding="utf-8")
    return manifest_path


def _spread_lines(prefix: str, count: int) -> list[str]:
    """Generate lines that land in all three splits, so the guard stays quiet."""
    return [f"{prefix} fragment number {i}" for i in range(count)]


def _fragment(text: str, **overrides) -> Fragment:
    fields = {
        "fragment_id": f"lib:{text[:8]}",
        "text": text,
        "library": "lib",
        "signal_key": None,
        "fragment_type": "filler",
        "subclass": None,
        "category": None,
        "cluster_id": None,
        "split": "train",
    }
    fields.update(overrides)
    # As _entry: a filler fragment is only eligible for a signal it has been
    # declared null on, so the default filler fragment carries the declaration
    # the real filler libraries carry.
    if fields["signal_key"] is None:
        fields.setdefault("null_on", (NullOn(signal=SIGNAL, basis="absent"),))
    return Fragment(**fields)


# --------------------------------------------------------------------------
# 1. Normalisation (DD5)
# --------------------------------------------------------------------------


def test_curly_and_straight_apostrophes_normalise_identically():
    assert normalise("I’ve had a fever") == normalise("I've had a fever")


def test_typographic_quotes_and_dashes_fold_to_ascii():
    assert normalise("she said “hot” — very") == normalise('she said "hot" - very')


def test_case_whitespace_and_terminal_punctuation_are_folded():
    variants = [
        "I had a fever.",
        "i had a fever",
        "  I  had   a fever!!!  ",
        "I HAD A FEVER?",
        "I had a fever . ",
    ]
    assert len({normalise(v) for v in variants}) == 1


def test_different_sentences_do_not_collide():
    assert normalise("I had a fever") != normalise("I had a headache")


def test_normalisation_does_not_strip_internal_punctuation():
    assert normalise("no. 3 on the list") == "no. 3 on the list"


# --------------------------------------------------------------------------
# 2. Split disjointness (Fine_tuning_plan.md section 6, Rule 4)
# --------------------------------------------------------------------------


def test_no_fragment_id_appears_in_more_than_one_split(tmp_path):
    manifest_path = _write_manifest(
        tmp_path,
        [_entry("alpha"), _entry("beta")],
        {
            "alpha.txt": _spread_lines("alpha", 60),
            "beta.txt": _spread_lines("beta", 60),
        },
    )
    fragments = load_fragments(manifest_path)

    seen: dict[str, str] = {}
    for fragment in fragments:
        if fragment.fragment_id in seen:
            assert seen[fragment.fragment_id] == fragment.split, fragment.fragment_id
        seen[fragment.fragment_id] = fragment.split
    assert len(seen) == len(fragments)


# --------------------------------------------------------------------------
# 3. Cluster cohesion (DD4)
# --------------------------------------------------------------------------


def test_fragments_sharing_a_cluster_id_land_in_the_same_split(tmp_path):
    # Built in-test rather than relying on the real libraries having a twin in
    # an interesting position: the two members hash to different splits on
    # their own text, and must be pulled together by the cluster marker.
    solo_a = "my husband has had a fever since monday and we share a house"
    solo_b = "my boyfriend has had a fever since tuesday and we share a house"
    assert assign_split(normalise(solo_a)) != assign_split(normalise(solo_b))

    manifest_path = _write_manifest(
        tmp_path,
        [_entry("alpha")],
        {"alpha.txt": [f"[c01] {solo_a}", f"[c01] {solo_b}", *_spread_lines("alpha", 60)]},
    )
    fragments = load_fragments(manifest_path)

    clustered = [f for f in fragments if f.cluster_id == "alpha:c01"]
    assert len(clustered) == 2
    assert len({f.split for f in clustered}) == 1


def test_cluster_marker_is_stripped_from_emitted_text_and_namespaced(tmp_path):
    tag, text = parse_line("[c03] My colleague went home with a fever")
    assert tag == "c03"
    assert text == "My colleague went home with a fever"

    manifest_path = _write_manifest(
        tmp_path,
        [_entry("alpha")],
        {"alpha.txt": ["[c03] My colleague went home", *_spread_lines("alpha", 60)]},
    )
    fragment = next(f for f in load_fragments(manifest_path) if f.cluster_id)
    assert fragment.cluster_id == "alpha:c03"
    assert fragment.text == "My colleague went home"


def test_unmarked_lines_have_no_cluster_id():
    assert parse_line("A plain line with [brackets] inside") == (
        None,
        "A plain line with [brackets] inside",
    )


# --------------------------------------------------------------------------
# 4. Split stability under library growth (DD9)
# --------------------------------------------------------------------------


def test_adding_a_fragment_does_not_move_existing_fragments(tmp_path):
    before_dir = tmp_path / "before"
    after_dir = tmp_path / "after"
    before_dir.mkdir()
    after_dir.mkdir()

    lines = _spread_lines("alpha", 60)
    before = _write_manifest(before_dir, [_entry("alpha")], {"alpha.txt": lines})
    after = _write_manifest(
        after_dir, [_entry("alpha")], {"alpha.txt": ["a brand new line about nothing", *lines]}
    )

    before_splits = {f.fragment_id: f.split for f in load_fragments(before)}
    after_splits = {f.fragment_id: f.split for f in load_fragments(after)}

    assert len(after_splits) == len(before_splits) + 1
    for fragment_id, split in before_splits.items():
        assert after_splits[fragment_id] == split


def test_split_assignment_does_not_use_salted_hash():
    # Pinned literals: a per-process salt (Python's hash()) would break these
    # between runs, and every downstream split would silently change.
    assert assign_split("fever_null_hedged:c01") == "train"
    assert assign_split("i had a fever") == "train"
    assert set(assign_split(f"key-{i}") for i in range(200)) == {"train", "val", "test"}


# --------------------------------------------------------------------------
# 5. Manifest validation (C4, DD10)
# --------------------------------------------------------------------------


def test_missing_file_raises(tmp_path):
    manifest_path = _write_manifest(tmp_path, [_entry("ghost")], {})
    with pytest.raises(ManifestError, match="ghost"):
        load_fragments(manifest_path)


def test_unknown_fragment_type_raises():
    with pytest.raises(ManifestError, match="fragment_type"):
        parse_manifest({"libraries": [_entry("alpha", fragment_type="vibes")]})


def test_duplicate_library_name_raises():
    with pytest.raises(ManifestError, match="duplicate library name"):
        parse_manifest({"libraries": [_entry("alpha"), _entry("alpha")]})


def test_filler_library_with_a_signal_key_raises():
    with pytest.raises(ManifestError, match="filler"):
        parse_manifest({"libraries": [_entry("alpha", signal_key="fever_present")]})


def test_signal_library_without_a_signal_key_raises():
    with pytest.raises(ManifestError, match="no signal_key"):
        parse_manifest({"libraries": [_entry("alpha", fragment_type="positive")]})


def test_empty_library_file_raises(tmp_path):
    manifest_path = _write_manifest(tmp_path, [_entry("alpha")], {"alpha.txt": ["", "   ", ""]})
    with pytest.raises(ManifestError, match="zero non-blank lines"):
        load_fragments(manifest_path)


def test_files_on_disk_but_absent_from_the_manifest_are_ignored(tmp_path):
    # fever_synonyms.jsonl (scratch notes) and fever_true.yaml (a generator
    # spec) live alongside the libraries and must never reach training text.
    manifest_path = _write_manifest(
        tmp_path, [_entry("alpha")], {"alpha.txt": _spread_lines("alpha", 60)}
    )
    (tmp_path / "fever_synonyms.jsonl").write_text("1. pyrexia\n\nFever template wrappers\n")
    (tmp_path / "fever_true.yaml").write_text("template: I had a {synonym}\n")

    fragments = load_fragments(manifest_path)
    assert {f.library for f in fragments} == {"alpha"}
    assert not any("pyrexia" in f.text or "template" in f.text for f in fragments)


def test_manifest_metadata_reaches_the_fragment(tmp_path):
    manifest_path = _write_manifest(
        tmp_path,
        [
            _entry(
                "alpha",
                signal_key="fever_present",
                fragment_type="confounder",
                subclass="third_party",
            )
        ],
        {"alpha.txt": _spread_lines("alpha", 60)},
    )
    fragment = load_fragments(manifest_path)[0]
    assert fragment.signal_key == "fever_present"
    assert fragment.fragment_type == "confounder"
    assert fragment.subclass == "third_party"
    assert fragment.library == "alpha"


# --------------------------------------------------------------------------
# 6. Ruleset validation (DD11)
# --------------------------------------------------------------------------


def _ruleset(**overrides) -> dict:
    question = {
        "question_id": "urinary_symptoms_4",
        "answer_key": "fever_present",
        "answer_type": "Boolean",
        "send_to_encoder": True,
    }
    question.update(overrides)
    return {"questions": [{"answer_key": "other_key", "answer_type": "Boolean"}, question]}


def test_valid_signal_returns_its_question():
    question = validate_signal(_ruleset(), "fever_present", source="synthetic")
    assert question["question_id"] == "urinary_symptoms_4"


def test_signal_absent_from_ruleset_raises():
    with pytest.raises(RulesetError, match="dysuria_present"):
        validate_signal(_ruleset(), "dysuria_present", source="synthetic")


def test_signal_not_sent_to_encoder_raises():
    with pytest.raises(RulesetError, match="not sent to the encoder"):
        validate_signal(_ruleset(send_to_encoder=False), "fever_present", source="synthetic")


def test_non_boolean_signal_raises():
    with pytest.raises(RulesetError, match="answer_type"):
        validate_signal(_ruleset(answer_type="Text"), "fever_present", source="synthetic")


# --------------------------------------------------------------------------
# 7. Deduplication (C5)
# --------------------------------------------------------------------------


def test_identical_text_within_a_library_collapses_to_one_fragment(tmp_path):
    manifest_path = _write_manifest(
        tmp_path,
        [_entry("alpha")],
        {"alpha.txt": ["I had a fever.", "i had a fever", *_spread_lines("alpha", 60)]},
    )
    fragments = load_fragments(manifest_path)
    matching = [f for f in fragments if normalise(f.text) == "i had a fever"]
    assert len(matching) == 1
    assert matching[0].text == "I had a fever."  # first occurrence kept, verbatim


def test_same_text_in_two_libraries_with_different_types_raises():
    fragments = [
        _fragment("I had a fever", library="fever_true", fragment_type="positive"),
        _fragment("I had a fever.", library="tangents", fragment_type="filler"),
    ]
    with pytest.raises(ManifestError, match="conflicting labels"):
        deduplicate(fragments)


def test_same_text_in_two_libraries_with_the_same_type_keeps_the_first():
    fragments = [
        _fragment("the weather is awful", library="tangents"),
        _fragment("The weather is awful!", library="emotional"),
    ]
    assert [f.library for f in deduplicate(fragments)] == ["tangents"]


# --------------------------------------------------------------------------
# 8. Empty-cell guard (DD9, C7)
# --------------------------------------------------------------------------


def test_library_too_small_to_fill_every_split_raises():
    spec = LibrarySpec(name="tiny", file="tiny.txt", signal_key=None, fragment_type="filler")
    fragments = [_fragment("only line", library="tiny", split="train")]
    with pytest.raises(ManifestError, match="tiny/val"):
        check_no_empty_cells(fragments, [spec])


def test_empty_cell_error_names_every_empty_cell():
    spec = LibrarySpec(name="tiny", file="tiny.txt", signal_key=None, fragment_type="filler")
    with pytest.raises(ManifestError) as excinfo:
        check_no_empty_cells([_fragment("only line", library="tiny")], [spec])
    assert "tiny/val" in str(excinfo.value)
    assert "tiny/test" in str(excinfo.value)


def test_full_coverage_passes():
    spec = LibrarySpec(name="lib", file="lib.txt", signal_key=None, fragment_type="filler")
    fragments = [_fragment(f"line {s}", split=s) for s in ("train", "val", "test")]
    check_no_empty_cells(fragments, [spec])


# --------------------------------------------------------------------------
# Fragment IDs (DD8)
# --------------------------------------------------------------------------


def test_fragment_id_is_stable_under_reordering(tmp_path):
    forward = tmp_path / "forward"
    reverse = tmp_path / "reverse"
    forward.mkdir()
    reverse.mkdir()

    lines = _spread_lines("alpha", 60)
    a = _write_manifest(forward, [_entry("alpha")], {"alpha.txt": lines})
    b = _write_manifest(reverse, [_entry("alpha")], {"alpha.txt": list(reversed(lines))})

    assert {f.fragment_id for f in load_fragments(a)} == {f.fragment_id for f in load_fragments(b)}


def test_read_library_preserves_text_verbatim(tmp_path):
    (tmp_path / "alpha.txt").write_text("  I’ve had a Fever, honestly!!  \n", encoding="utf-8")
    spec = LibrarySpec(name="alpha", file="alpha.txt", signal_key=None, fragment_type="filler")
    fragment = read_library(spec, tmp_path)[0]
    # Surrounding whitespace goes; casing, the curly apostrophe and the
    # punctuation stay, because the encoder sees raw user input at runtime.
    assert fragment.text == "I’ve had a Fever, honestly!!"


# --------------------------------------------------------------------------
# Recombination fixtures
#
# Tests below run against a small synthetic manifest, never against
# data/synthetic/. Tests that depend on the real libraries break every time
# the user edits a fragment, which is a bad trade for a dataset meant to grow.
# --------------------------------------------------------------------------

SIGNAL = "fever_present"

_RECOMBINE_LIBRARIES = [
    _entry("pos", signal_key=SIGNAL, fragment_type="positive"),
    _entry("neg", signal_key=SIGNAL, fragment_type="negative"),
    _entry("amb", signal_key=SIGNAL, fragment_type="ambiguous", subclass="hedged"),
    _entry("conf", signal_key=SIGNAL, fragment_type="confounder", subclass="third_party"),
    _entry("fill_a"),
    _entry("fill_b"),
    _entry("fill_c"),
]


#: Four filler libraries, so a structural null can be built at count four. Kept
#: separate from the fixture above rather than widening it, so the three-filler
#: pool stays available for the pool-error cases.
_WIDE_LIBRARIES = [*_RECOMBINE_LIBRARIES, _entry("fill_d")]


@pytest.fixture
def libraries(tmp_path) -> Path:
    """A manifest whose every library fills all three splits."""
    return _write_manifest(
        tmp_path,
        _RECOMBINE_LIBRARIES,
        {f"{e['name']}.txt": _spread_lines(e["name"], 60) for e in _RECOMBINE_LIBRARIES},
    )


@pytest.fixture
def wide_libraries(tmp_path) -> Path:
    """As ``libraries``, plus a fourth filler library."""
    return _write_manifest(
        tmp_path,
        _WIDE_LIBRARIES,
        {f"{e['name']}.txt": _spread_lines(e["name"], 60) for e in _WIDE_LIBRARIES},
    )


def _pools(manifest_path: Path, split: str = "train"):
    return build_pools(load_fragments(manifest_path), SIGNAL, split)


def _generate(manifest_path: Path, split: str = "train", count: int = 200, **kwargs):
    examples, _ = generate(_pools(manifest_path, split), count=count, seed=42, **kwargs)
    return examples


def _types_by_id(manifest_path: Path) -> dict[str, str]:
    return {f.fragment_id: f.fragment_type for f in load_fragments(manifest_path)}


def _argv(**flags) -> list[str]:
    """Flatten ``split="train"`` into ``["--split", "train"]``."""
    argv: list[str] = []
    for name, value in flags.items():
        argv += [f"--{name.replace('_', '-')}", str(value)]
    return argv


def _write_ruleset(base: Path, signals: tuple[str, ...] = (SIGNAL,)) -> Path:
    """A minimal ruleset defining ``signals``.

    ``signals`` widens it because a ``null_on`` entry may only name a signal the
    ruleset sends to the encoder, so a manifest declaring foreign pairs needs a
    ruleset that knows those signals exist. The default is the single-signal
    ruleset every test below this used before the parameter existed.
    """
    path = base / "ruleset.json"
    path.write_text(
        json.dumps(
            {
                "questions": [
                    {
                        "question_id": f"urinary_symptoms_{index}",
                        "answer_key": signal,
                        "answer_type": "Boolean",
                        "send_to_encoder": True,
                    }
                    for index, signal in enumerate(signals, start=4)
                ]
            }
        ),
        encoding="utf-8",
    )
    return path


# --------------------------------------------------------------------------
# 9. Distribution parsing (C4)
# --------------------------------------------------------------------------


def test_distribution_parses_and_round_trips():
    assert parse_distribution("null=0.60,false=0.25,true=0.15") == {
        "null": 0.60,
        "false": 0.25,
        "true": 0.15,
    }


def test_distribution_that_does_not_sum_to_one_raises():
    with pytest.raises(DistributionError, match="sum to"):
        parse_distribution("null=0.60,false=0.25,true=0.05")


def test_distribution_with_an_unknown_label_raises():
    with pytest.raises(DistributionError, match="unknown label"):
        parse_distribution("null=0.60,false=0.25,maybe=0.15")


def test_distribution_missing_a_label_raises():
    with pytest.raises(DistributionError, match="missing weights"):
        parse_distribution("null=0.75,false=0.25")


def test_malformed_distribution_term_raises():
    with pytest.raises(DistributionError, match="malformed"):
        parse_distribution("null,false=0.25,true=0.15")


# --------------------------------------------------------------------------
# 9b. Fragment-count parsing
# --------------------------------------------------------------------------


def test_fragment_counts_parse_to_integer_keys():
    assert parse_fragment_counts("2=0.5,3=0.5") == {2: 0.5, 3: 0.5}
    assert parse_fragment_counts("2=0.4,3=0.4,4=0.2") == {2: 0.4, 3: 0.4, 4: 0.2}


def test_fragment_count_below_two_raises():
    # A lone filler is a trivially easy null and a lone decisive fragment
    # removes the noise floor, so two is the floor.
    with pytest.raises(DistributionError, match="below the minimum of 2"):
        parse_fragment_counts("1=0.5,2=0.5")


def test_non_integer_fragment_count_raises():
    with pytest.raises(DistributionError, match="not an integer"):
        parse_fragment_counts("two=1.0")


def test_fragment_counts_that_do_not_sum_to_one_raise():
    with pytest.raises(DistributionError, match="sum to"):
        parse_fragment_counts("2=0.5,3=0.4")


def test_duplicate_fragment_count_raises():
    with pytest.raises(DistributionError, match="appears twice"):
        parse_fragment_counts("2=0.5,2=0.5")


def test_empty_fragment_counts_raise():
    with pytest.raises(DistributionError, match="empty"):
        parse_fragment_counts("")


@pytest.mark.parametrize(
    "text", ["1=1.0", "two=1.0", "2=0.5,3=0.4", "2=0.5,2=0.5", "", "2", "2=nope", "2=-1.0,3=2.0"]
)
def test_fragment_count_errors_name_their_own_flag(text):
    # Sharing the parser with --dist must not make a bad --fragment-counts
    # report itself as a --dist problem.
    with pytest.raises(DistributionError) as excinfo:
        parse_fragment_counts(text)
    assert "--dist" not in str(excinfo.value)


# --------------------------------------------------------------------------
# 10. Determinism (C7.9, C7.10)
# --------------------------------------------------------------------------


def test_same_seed_and_flags_produce_byte_identical_output(tmp_path, libraries):
    ruleset = _write_ruleset(tmp_path)
    outputs = []
    for name in ("first", "second"):
        out = tmp_path / f"{name}.jsonl"
        argv = _argv(
            manifest=libraries,
            ruleset=ruleset,
            signal=SIGNAL,
            split="train",
            count=300,
            seed=42,
            out=out,
        )
        assert cli_main(argv) == 0
        outputs.append(out.read_bytes())
    assert outputs[0] == outputs[1]
    assert outputs[0].count(b"\n") == 300


def test_first_examples_do_not_move_when_count_grows(libraries):
    small = _generate(libraries, count=100)
    large = _generate(libraries, count=1000)
    assert [e.text for e in small] == [e.text for e in large[:100]]
    assert [e.labels for e in small] == [e.labels for e in large[:100]]


def test_changing_the_seed_changes_the_dataset(libraries):
    a, _ = generate(_pools(libraries), count=100, seed=42)
    b, _ = generate(_pools(libraries), count=100, seed=43)
    assert [e.text for e in a] != [e.text for e in b]


# --------------------------------------------------------------------------
# 11. Label/fragment invariants (C3, C7.11-14)
# --------------------------------------------------------------------------


def test_no_positive_fragment_reaches_a_non_true_example(libraries):
    types = _types_by_id(libraries)
    for example in _generate(libraries, count=500):
        used = {types[fid] for fid in example.meta["fragment_ids"]}
        if example.labels[SIGNAL] is not True:
            assert "positive" not in used, example


def test_no_negative_fragment_reaches_a_non_false_example(libraries):
    types = _types_by_id(libraries)
    for example in _generate(libraries, count=500):
        used = {types[fid] for fid in example.meta["fragment_ids"]}
        if example.labels[SIGNAL] is not False:
            assert "negative" not in used, example


def test_no_example_mixes_a_decisive_and_an_ambiguous_fragment(libraries):
    types = _types_by_id(libraries)
    for example in _generate(libraries, count=500):
        used = {types[fid] for fid in example.meta["fragment_ids"]}
        assert not ({"positive", "negative"} & used and {"ambiguous", "confounder"} & used)
        assert not ("positive" in used and "negative" in used)


def test_every_example_holds_one_of_the_requested_fragment_counts(libraries):
    examples = _generate(libraries, count=500)
    seen = set()
    for example in examples:
        size = len(example.meta["fragment_ids"])
        assert size in DEFAULT_FRAGMENT_COUNTS
        assert len(example.meta["fragment_subclasses"]) == size
        seen.add(size)
    # Both requested counts actually occur, or the assertion above is vacuous.
    assert seen == set(DEFAULT_FRAGMENT_COUNTS)


def test_structural_nulls_are_all_filler_from_distinct_libraries(libraries):
    types = _types_by_id(libraries)
    libraries_by_id = {f.fragment_id: f.library for f in load_fragments(libraries)}
    structural = [
        e for e in _generate(libraries, count=500) if e.meta["label_mode"] == "null_structural"
    ]
    assert structural
    for example in structural:
        ids = example.meta["fragment_ids"]
        assert [types[fid] for fid in ids] == ["filler"] * len(ids)
        # Distinct libraries at every count, not just at two: three fillers
        # from one library read as three tangents in the same voice.
        assert len({libraries_by_id[fid] for fid in ids}) == len(ids)


def test_ambiguous_nulls_carry_exactly_one_signal_fragment(libraries):
    types = _types_by_id(libraries)
    ambiguous = [
        e for e in _generate(libraries, count=500) if e.meta["label_mode"] == "null_ambiguous"
    ]
    assert ambiguous
    for example in ambiguous:
        used = Counter(types[fid] for fid in example.meta["fragment_ids"])
        signal = used["ambiguous"] + used["confounder"]
        assert signal == 1
        assert used["filler"] == len(example.meta["fragment_ids"]) - 1


def test_decisive_fragments_appear_in_every_position(libraries):
    # A model that only ever sees the fever claim first can learn position as a
    # shortcut, so the shuffle in select_fragments has to actually shuffle.
    types = _types_by_id(libraries)
    positions = {
        next(i for i, fid in enumerate(e.meta["fragment_ids"]) if types[fid] == "positive")
        for e in _generate(libraries, count=500)
        if e.labels[SIGNAL] is True
    }
    assert positions == set(range(max(DEFAULT_FRAGMENT_COUNTS)))


@pytest.mark.parametrize("split", ["train", "val", "test"])
def test_fragment_pools_are_split_restricted(libraries, split):
    # Filler leakage across splits is exactly as damaging as signal leakage.
    splits_by_id = {f.fragment_id: f.split for f in load_fragments(libraries)}
    for example in _generate(libraries, split=split, count=200):
        assert example.split == split
        for fragment_id in example.meta["fragment_ids"]:
            assert splits_by_id[fragment_id] == split, fragment_id


# --------------------------------------------------------------------------
# 12. Labels and text assembly (DD1, DD7)
# --------------------------------------------------------------------------


def test_labels_are_a_dict_keyed_by_answer_key_with_a_real_none():
    assert labels_for_mode(SIGNAL, "true") == {SIGNAL: True}
    assert labels_for_mode(SIGNAL, "false") == {SIGNAL: False}
    for mode in ("null_structural", "null_ambiguous"):
        labels = labels_for_mode(SIGNAL, mode)
        # None, never a "null" sentinel string: an absent key means "mask this
        # head's loss", a None value means "the label is None".
        assert labels == {SIGNAL: None}
        assert labels[SIGNAL] is None


def test_assembled_text_preserves_fragments_verbatim():
    fragments = [
        _fragment("  I’ve had a Fever since Monday  "),
        _fragment("i'm SO worried about it!"),
    ]
    assert assemble_text(fragments) == "I’ve had a Fever since Monday. i'm SO worried about it!"


def test_assembly_does_not_double_terminal_punctuation():
    fragments = [_fragment("Is it a fever?"), _fragment("I think so...")]
    assert assemble_text(fragments) == "Is it a fever? I think so..."


def test_emitted_text_is_never_normalised(libraries):
    for example in _generate(libraries, count=50):
        assert example.text == example.text.strip()
        assert "  " not in example.text


# --------------------------------------------------------------------------
# 13. Realised distribution (C7.15)
# --------------------------------------------------------------------------


def test_realised_label_counts_are_exactly_these_for_seed_42(libraries):
    # Golden numbers, not a statistical tolerance: the pipeline is
    # deterministic by construction, so a tolerance would be both weaker and
    # flakier. A change here is a real behaviour change.
    #
    # Load-bearing for the variable fragment count: the count is drawn *after*
    # the label mode precisely so that sample_label_mode still consumes exactly
    # the draws it consumed before that feature existed. If these numbers move,
    # the count draw has been placed ahead of the mode draw and the label
    # distribution has silently changed with it.
    examples = _generate(libraries, count=1000)
    counts = Counter(e.meta["label_mode"] for e in examples)
    assert counts == {
        "null_ambiguous": 317,
        "null_structural": 268,
        "false": 259,
        "true": 156,
    }


def test_null_ambiguous_ratio_moves_the_sub_mode_split(libraries):
    examples = _generate(libraries, count=1000, null_ambiguous_ratio=0.0)
    modes = Counter(e.meta["label_mode"] for e in examples)
    assert modes["null_ambiguous"] == 0
    assert modes["null_structural"] > 0


def test_distribution_override_is_honoured(libraries):
    examples = _generate(
        libraries, count=400, distribution={"true": 1.0, "false": 0.0, "null": 0.0}
    )
    assert all(e.labels[SIGNAL] is True for e in examples)


# --------------------------------------------------------------------------
# 13b. Variable fragment count
# --------------------------------------------------------------------------


def test_the_fragment_count_mix_does_not_vary_by_label_mode(libraries):
    # THE test for this feature. Fragment count is allowed to vary; what is not
    # allowed is for it to vary *with the label*, because then text length
    # becomes a usable proxy for the label -- a model would score well on this
    # data having learned nothing about fever, and nothing downstream would
    # show it. If a future change reintroduces that leak, this is what catches
    # it. Do not relax the tolerance to make it pass.
    counts = {2: 0.5, 3: 0.5}
    examples = _generate(libraries, count=4000, fragment_counts=counts)

    by_mode: dict[str, Counter] = {}
    for example in examples:
        tally = by_mode.setdefault(example.meta["label_mode"], Counter())
        tally[len(example.meta["fragment_ids"])] += 1

    assert set(by_mode) == {"true", "false", "null_structural", "null_ambiguous"}
    for mode, tally in by_mode.items():
        total = sum(tally.values())
        assert total >= 200, f"{mode} too small to be evidence of anything"
        for size, weight in counts.items():
            share = tally[size] / total
            assert abs(share - weight) < 0.06, (
                f"{mode} drew {size} fragments {share:.3f} of the time"
            )


def test_a_single_count_mix_produces_only_that_count(libraries):
    for example in _generate(libraries, count=200, fragment_counts={3: 1.0}):
        assert len(example.meta["fragment_ids"]) == 3


def test_the_engine_is_general_over_the_count(wide_libraries):
    # Nothing about the engine is special-cased to two or three: four fillers
    # in the manifest, four fragments per example, still exactly one decisive
    # fragment each.
    types = _types_by_id(wide_libraries)
    libraries_by_id = {f.fragment_id: f.library for f in load_fragments(wide_libraries)}
    examples = _generate(wide_libraries, count=500, fragment_counts={4: 1.0})

    modes = Counter()
    for example in examples:
        ids = example.meta["fragment_ids"]
        used = Counter(types[fid] for fid in ids)
        assert len(ids) == 4
        decisive = used["positive"] + used["negative"] + used["ambiguous"] + used["confounder"]
        assert decisive == (0 if example.meta["label_mode"] == "null_structural" else 1)
        assert used["filler"] == 4 - decisive
        fillers = [fid for fid in ids if types[fid] == "filler"]
        assert len({libraries_by_id[fid] for fid in fillers}) == len(fillers)
        modes[example.meta["label_mode"]] += 1

    # Every mode is exercised, including the structural null that needs all
    # four filler libraries at once.
    assert set(modes) == {"true", "false", "null_structural", "null_ambiguous"}


def test_first_examples_do_not_move_when_count_grows_under_a_mixed_count_mix(libraries):
    # The per-example seeding property, re-verified now that a count draw sits
    # between the label draw and fragment selection.
    counts = {2: 0.3, 3: 0.7}
    small = _generate(libraries, count=100, fragment_counts=counts)
    large = _generate(libraries, count=1000, fragment_counts=counts)
    assert [e.text for e in small] == [e.text for e in large[:100]]
    assert [e.meta["fragment_ids"] for e in small] == [e.meta["fragment_ids"] for e in large[:100]]


# --------------------------------------------------------------------------
# 14. Pool exhaustion (C7.16)
# --------------------------------------------------------------------------


def _tiny_pools():
    fragments = [
        _fragment("i had a fever", library="pos", signal_key=SIGNAL, fragment_type="positive"),
        _fragment("no fever here", library="neg", signal_key=SIGNAL, fragment_type="negative"),
        _fragment("might be warm", library="amb", signal_key=SIGNAL, fragment_type="ambiguous"),
        _fragment("the bus was late", library="fill_a"),
        _fragment("my cat is unwell", library="fill_b"),
    ]
    return build_pools(fragments, SIGNAL, "train")


def test_requesting_more_examples_than_the_pool_holds_raises():
    # One positive x two fillers x two orderings = four unique true examples.
    # Pinned to two-fragment examples: the tiny pool has only two filler
    # libraries, so a three-fragment example could not be built at all.
    with pytest.raises(PoolExhaustedError, match="train"):
        generate(
            _tiny_pools(),
            count=10,
            seed=42,
            distribution={"true": 1.0, "false": 0.0, "null": 0.0},
            fragment_counts={2: 1.0},
        )


def test_a_satisfiable_request_against_the_same_tiny_pool_succeeds():
    examples, telemetry = generate(
        _tiny_pools(),
        count=4,
        seed=42,
        distribution={"true": 1.0, "false": 0.0, "null": 0.0},
        fragment_counts={2: 1.0},
    )
    assert len({e.text for e in examples}) == 4
    assert telemetry["duplicate_rejections"] > 0


def test_a_count_larger_than_the_filler_library_count_raises_before_generating():
    # The ceiling is structural: an N-fragment structural null needs N distinct
    # filler libraries. _tiny_pools has two.
    with pytest.raises(PoolError) as excinfo:
        generate(_tiny_pools(), count=10, seed=42, fragment_counts={2: 0.5, 3: 0.5})
    message = str(excinfo.value)
    assert "up to 3" in message
    assert "has 2" in message
    assert "fill_a, fill_b" in message


def test_the_filler_library_floor_in_build_pools_is_unchanged_by_the_count_check():
    # build_pools cannot know the requested mix, so its own floor stays at the
    # two libraries a structural null has always needed.
    pools = _tiny_pools()
    assert len(pools.filler) == 2
    examples, _ = generate(pools, count=2, seed=42, fragment_counts={2: 1.0})
    assert len(examples) == 2


def test_pool_error_names_the_missing_fragment_type():
    fragments = [
        _fragment("i had a fever", library="pos", signal_key=SIGNAL, fragment_type="positive"),
        _fragment("the bus was late", library="fill_a"),
        _fragment("my cat is unwell", library="fill_b"),
    ]
    with pytest.raises(PoolError, match="negative"):
        build_pools(fragments, SIGNAL, "train")


def test_a_single_filler_library_cannot_serve_structural_nulls():
    fragments = [
        _fragment("i had a fever", library="pos", signal_key=SIGNAL, fragment_type="positive"),
        _fragment("no fever here", library="neg", signal_key=SIGNAL, fragment_type="negative"),
        _fragment("might be warm", library="amb", signal_key=SIGNAL, fragment_type="ambiguous"),
        _fragment("the bus was late", library="fill_a"),
    ]
    with pytest.raises(PoolError, match="two distinct"):
        build_pools(fragments, SIGNAL, "train")


# --------------------------------------------------------------------------
# 15. Output schema and stats sidecar (C5, C6)
# --------------------------------------------------------------------------


def test_jsonl_records_carry_the_training_schema(tmp_path, libraries):
    out = tmp_path / "out.jsonl"
    argv = _argv(
        manifest=libraries,
        ruleset=_write_ruleset(tmp_path),
        split="val",
        count=50,
        out=out,
    )
    assert cli_main(argv) == 0
    records = [json.loads(line) for line in out.read_text(encoding="utf-8").splitlines()]
    assert len(records) == 50
    for record in records:
        assert set(record) == {"example_id", "split", "text", "labels", "meta"}
        assert record["split"] == "val"
        assert set(record["labels"]) == {SIGNAL}
        assert record["labels"][SIGNAL] in (True, False, None)
        # DD8: no fragment_count key. The count is already unambiguously
        # present as len(fragment_ids), and a second copy is one more thing
        # that can disagree with itself.
        assert set(record["meta"]) == {
            "label_mode",
            "filler_only",
            "fragment_ids",
            "fragment_subclasses",
            "seed",
            "generator_version",
        }
        assert len(record["meta"]["fragment_ids"]) in DEFAULT_FRAGMENT_COUNTS
        assert len(record["meta"]["fragment_subclasses"]) == len(record["meta"]["fragment_ids"])
    assert records[0]["example_id"] == "val-000000"


def test_stats_sidecar_records_what_was_asked_for_and_what_came_out(tmp_path, libraries):
    out = tmp_path / "out.jsonl"
    cli_main(
        _argv(
            manifest=libraries,
            ruleset=_write_ruleset(tmp_path),
            split="train",
            count=500,
            out=out,
        )
    )
    stats = json.loads((tmp_path / "out.jsonl.stats.json").read_text(encoding="utf-8"))

    assert stats["requested"]["count"] == 500
    assert stats["requested"]["distribution"] == {"true": 0.15, "false": 0.25, "null": 0.60}
    assert stats["requested"]["fragment_counts"] == {"2": 0.5, "3": 0.5}
    assert stats["realised"]["count"] == 500
    assert sum(stats["realised"]["labels"].values()) == 500
    assert sum(stats["realised"]["label_modes"].values()) == 500
    assert stats["fragment_pool_sizes"]["pos"]["train"] > 0
    assert "duplicate_rejections" in stats
    # DD6: the length confound is reported here or it is invisible.
    for label in ("true", "false", "null"):
        assert stats["token_counts"]["by_label"][label]["median_tokens"] > 0
        assert stats["token_counts"]["by_label"][label]["p90_tokens"] > 0
    # DD7: without this block a skewed count distribution would be invisible.
    for label in ("true", "false", "null"):
        tally = stats["fragment_counts"]["by_label"][label]
        assert set(tally) == {"2", "3"}
        assert sum(tally.values()) == stats["realised"]["labels"][label]
    for mode in ("true", "false", "null_structural", "null_ambiguous"):
        tally = stats["fragment_counts"]["by_label_mode"][mode]
        assert sum(tally.values()) == stats["realised"]["label_modes"][mode]
    assert set(stats["token_counts"]["by_fragment_count"]) == {"2", "3"}
    assert (
        sum(entry["count"] for entry in stats["token_counts"]["by_fragment_count"].values()) == 500
    )


def test_stats_fragment_count_keys_survive_the_json_round_trip(tmp_path, libraries):
    # json.dump coerces int keys to strings silently, so the in-memory dict is
    # built string-keyed to match what anyone reading the sidecar back will
    # find. This checks the two agree rather than assuming it.
    out = tmp_path / "out.jsonl"
    cli_main(
        _argv(
            manifest=libraries,
            ruleset=_write_ruleset(tmp_path),
            split="train",
            count=100,
            fragment_counts="2=0.5,3=0.5",
            out=out,
        )
    )
    written = json.loads((tmp_path / "out.jsonl.stats.json").read_text(encoding="utf-8"))
    pools = _pools(libraries)
    examples, telemetry = generate(pools, count=100, seed=42)
    in_memory = build_stats(
        examples,
        telemetry=telemetry,
        fragments=load_fragments(libraries),
        pools=pools,
        count=100,
        seed=42,
        distribution={"true": 0.15, "false": 0.25, "null": 0.60},
        null_ambiguous_ratio=0.5,
        fragment_counts={2: 0.5, 3: 0.5},
        manifest_path=str(libraries),
        ruleset_path=str(tmp_path / "ruleset.json"),
    )
    assert in_memory["fragment_counts"] == written["fragment_counts"]
    assert in_memory["requested"]["fragment_counts"] == written["requested"]["fragment_counts"]


def test_stats_length_summary_matches_the_examples(libraries):
    pools = _pools(libraries)
    examples, telemetry = generate(pools, count=200, seed=42)
    stats = build_stats(
        examples,
        telemetry=telemetry,
        fragments=load_fragments(libraries),
        pools=pools,
        count=200,
        seed=42,
        distribution={"true": 0.15, "false": 0.25, "null": 0.60},
        null_ambiguous_ratio=0.5,
        fragment_counts={2: 0.5, 3: 0.5},
        manifest_path=str(libraries),
        ruleset_path="ruleset.json",
    )
    true_lengths = sorted(len(e.text.split()) for e in examples if e.labels[SIGNAL] is True)
    assert stats["token_counts"]["by_label"]["true"]["count"] == len(true_lengths)
    assert stats["token_counts"]["by_label"]["true"]["p90_tokens"] == float(
        true_lengths[max(0, math.ceil(0.9 * len(true_lengths)) - 1)]
    )


# --------------------------------------------------------------------------
# 16. CLI failure modes
# --------------------------------------------------------------------------


def test_cli_rejects_a_signal_absent_from_the_ruleset(tmp_path, libraries, capsys):
    out = tmp_path / "out.jsonl"
    code = cli_main(
        _argv(
            manifest=libraries,
            ruleset=_write_ruleset(tmp_path),
            signal="dysuria_present",
            split="train",
            count=10,
            out=out,
        )
    )
    assert code == 2
    assert "dysuria_present" in capsys.readouterr().err
    assert not out.exists()


def test_cli_rejects_a_bad_distribution_before_writing_anything(tmp_path, libraries, capsys):
    out = tmp_path / "out.jsonl"
    code = cli_main(
        _argv(
            manifest=libraries,
            ruleset=_write_ruleset(tmp_path),
            split="train",
            count=10,
            dist="null=0.6,false=0.2,true=0.1",
            out=out,
        )
    )
    assert code == 2
    assert "sum to" in capsys.readouterr().err
    assert not out.exists()


def test_cli_rejects_bad_fragment_counts_before_reading_any_library(tmp_path, capsys):
    # The manifest path is deliberately nonexistent: a malformed flag must fail
    # before a single file is opened, so this can only pass if the parse
    # happens first.
    out = tmp_path / "out.jsonl"
    code = cli_main(
        _argv(
            manifest=tmp_path / "no-such-manifest.json",
            ruleset=_write_ruleset(tmp_path),
            split="train",
            count=10,
            fragment_counts="1=1.0",
            out=out,
        )
    )
    assert code == 2
    error = capsys.readouterr().err
    assert "--fragment-counts" in error
    assert "--dist" not in error
    assert not out.exists()


def test_cli_rejects_a_count_the_filler_libraries_cannot_serve(tmp_path, libraries, capsys):
    # Three filler libraries in the fixture, four requested.
    out = tmp_path / "out.jsonl"
    code = cli_main(
        _argv(
            manifest=libraries,
            ruleset=_write_ruleset(tmp_path),
            split="train",
            count=10,
            fragment_counts="4=1.0",
            out=out,
        )
    )
    assert code == 2
    assert "up to 4" in capsys.readouterr().err
    assert not out.exists()


def test_cli_honours_a_fragment_count_override(tmp_path, libraries):
    out = tmp_path / "out.jsonl"
    assert (
        cli_main(
            _argv(
                manifest=libraries,
                ruleset=_write_ruleset(tmp_path),
                split="train",
                count=50,
                fragment_counts="3=1.0",
                out=out,
            )
        )
        == 0
    )
    records = [json.loads(line) for line in out.read_text(encoding="utf-8").splitlines()]
    assert {len(r["meta"]["fragment_ids"]) for r in records} == {3}


# --------------------------------------------------------------------------
# 17. Lint reports (C1, C2, C3)
#
# Everything except the filler-purity tests below runs against synthetic
# fragments. The filler-purity tests deliberately read the real
# data/synthetic/ tree: their entire purpose is to fail when someone edits a
# filler library and introduces symptom language, which no fixture can catch.
# --------------------------------------------------------------------------

REAL_MANIFEST = Path(__file__).resolve().parents[1] / "data" / "synthetic" / "manifest.json"
REAL_RULESET = Path(__file__).resolve().parents[1] / "data" / "uti1.json"

#: Filler fragments permitted to match a signal's lexicon, per signal. All six
#: are empty: the filler libraries are silent about every signal that has
#: libraries, and the near misses are excluded by the lexicons themselves
#: rather than by an allowlist -- see test_the_known_lexicon_traps_are_not_flagged.
#:
#: An entry here is a claim that a line reads as signal language, is staying in
#: filler anyway, and that somebody decided that on purpose. Adding one to make
#: a failure go away is the failure.
FILLER_PURITY_BASELINE: dict[str, set[str]] = {signal: set() for signal in SIGNAL_LEXICONS}

#: Hand-written text that each lexicon must match. This is the guard against
#: the empty baseline above passing against a lexicon narrowed into matching
#: nothing at all -- which is the easy way to "fix" a filler-purity failure and
#: the one that leaves the check dead.
LEXICON_SELF_TEST: dict[str, tuple[str, ...]] = {
    "fever_present": (
        "I've had a fever since Monday",
        "my temperature was 38.5 this morning",
        "I keep getting chills and sweats",
    ),
    "dysuria_present": (
        "it burns when I pee",
        "passing urine is really painful",
        "there's a stinging feeling every time I go for a wee",
    ),
    "urinary_frequency_present": (
        "I'm weeing far more often than normal",
        "I need the toilet constantly",
        "I'm up and down to the loo all day",
    ),
    "nocturia_present": (
        "I'm getting up two or three times a night for a wee",
        "I woke up needing the toilet twice last night",
        "my sleep is broken because I keep needing to empty my bladder",
    ),
    "flank_pain_present": (
        "I've got a dull ache in my left side, just under my ribs",
        "there's a sharp pain in my back on the right side",
        "my kidneys feel really tender",
    ),
    "haematuria_present": (
        "there is bright red blood in my wee",
        "my urine has turned red today",
        "the toilet bowl was dark red when I went earlier",
    ),
    "recent_uti_present": (
        "I finished a course of nitrofurantoin for a water infection ten days ago",
        "I was diagnosed with a UTI a fortnight ago",
        "the surgery treated me for cystitis earlier this month",
    ),
}

#: The floor each lexicon must clear against its own ``positive`` library, and
#: what it actually clears today. Well below the measured figures because the
#: point is to catch a lexicon that has been gutted, not to freeze recall: a
#: library that grows in a new register will move these, and moving them is
#: normal. Measured on the committed tree: fever 90%, dysuria 91%,
#: urinary_frequency 59%, nocturia 70%, flank_pain 83%, haematuria 87%.
#:
#: Positive libraries only. The negatives run 25 to 45 points lower across
#: every signal, because negating a symptom drops the detail that names it
#: ("no change in how often I'm weeing" keeps the anchor and loses nothing
#: else; "no blood at all" keeps neither half). That asymmetry is real and
#: worth knowing about, but averaging it in would leave the floor too low to
#: catch anything.
#:
#: urinary_frequency is the low one by a distance, and it is a property of the
#: library rather than of the lexicon: "I'm going every twenty minutes" names
#: no urinary word at all, and the lexicon deliberately does not treat a bare
#: "go" as one. See the Lexicon docstring.
LEXICON_RECALL_FLOOR = 0.45


def _real_fragments():
    # check_cells=False: the real fever_null sub-classes are small enough that
    # some (library, split) cells are empty, which aborts generation by design.
    # This test is about filler text, not about split balance.
    return load_fragments(REAL_MANIFEST, check_cells=False)


def test_no_filler_fragment_contains_signal_language():
    hits = filler_lexicon_hits(_real_fragments())
    found: dict[str, set[str]] = {signal: set() for signal in SIGNAL_LEXICONS}
    for hit in hits:
        found[hit.signal].add(hit.fragment_id)
    assert found == FILLER_PURITY_BASELINE, (
        "a filler library has acquired symptom language, so examples labelled "
        "null on the strength of their structure would contain text asserting "
        "that symptom: "
        + "; ".join(f"{hit.signal} {hit.fragment_id} {hit.terms} {hit.text}" for hit in hits)
    )


@pytest.mark.parametrize("signal", sorted(SIGNAL_LEXICONS))
def test_every_lexicon_actually_matches_its_own_signal_text(signal):
    fragments = [_fragment(t, fragment_type="filler") for t in LEXICON_SELF_TEST[signal]]
    matched = {hit.fragment_id for hit in filler_lexicon_hits(fragments) if hit.signal == signal}
    assert len(matched) == len(fragments), (
        f"the {signal} lexicon no longer matches text that plainly asserts it, "
        "so its empty filler-purity baseline is meaningless"
    )


def _signals_with_a_positive_library():
    """Signals the recall guard can be asked about, read from the live manifest.

    ``recent_uti_present`` has a lexicon and no libraries yet, and measuring
    recall against a library that does not exist is a ZeroDivisionError rather
    than a finding. Derived from the manifest rather than from an exemption
    list, so the signal joins the guard the moment its libraries land and
    nobody has to remember to remove anything.
    """
    return sorted(
        {f.signal_key for f in _real_fragments() if f.fragment_type == "positive" and f.signal_key}
    )


@pytest.mark.parametrize("signal", _signals_with_a_positive_library())
def test_every_lexicon_reaches_most_of_its_own_library(signal):
    # The hand-written sentences above are written to match. This runs the same
    # question against the real positive library, where nobody was aiming.
    library = [
        f for f in _real_fragments() if f.signal_key == signal and f.fragment_type == "positive"
    ]
    matched = sum(1 for f in library if lexicon_matches(f.text, signal))
    assert matched / len(library) >= LEXICON_RECALL_FLOOR, (
        f"the {signal} lexicon matches only {matched}/{len(library)} of its own "
        "positive fragments, which is too few for its filler-purity baseline to "
        "mean anything"
    )


def test_the_known_lexicon_traps_are_not_flagged():
    # Real filler lines, each one half of a signal's language and no more.
    # Every one of them was flagged by a draft of these lexicons, and each is
    # why the lexicon it tripped is shaped the way it is. Substring matching or
    # a one-sided lexicon puts all of them back.
    traps = [
        # "hot" inside lithotripsy / photos / shot: word boundaries only.
        "could I be referred for lithotripsy to break it up",
        "My sister texted saying she's worried about me from the photos I sent",
        "I've been unemployed for 8 months and this is my best shot at getting back to work",
        # Blood, but not in urine.
        "I think a blood test would help figure out what's wrong",
        "My dad's been on those blood pressure tablets for about two years now",
        # Urine, but no symptom attached to it.
        "I think I should get a urine culture done to identify the bug",
        "could I get an urgent ultrasound of my bladder to check if it's emptying properly",
        # Kidneys and backs, but nothing hurting.
        "I'm worried I might need a scan to check my kidneys aren't damaged",
        "I need to get back to normal because I've got loads on at the moment",
        "My mum's been complaining about her back again, says the physio isn't helping much",
        # Broken sleep with nothing urinary in it.
        "I've been sleeping badly the last few weeks because my neighbour's dog barks all night",
        "The stress from my mortgage application has been keeping me up at night",
        "My wife's working nights all next week so I need to be able to look after the kids",
        # Frequency and pain words about something other than the body.
        "I've got stress going on at the moment with family issues that have been dragging on",
        "I've been drinking a lot more water than usual because I'm trying to cut back on coffee",
        "Probably just another water infection, happens quite often",
        # An infection named, but nothing putting one inside the 30-day window:
        # a suspicion about now, a recurrence with no marker, and an episode
        # explicitly outside it. All three are null under section 9's policy,
        # and all three are how uti_speculation talks.
        "I reckon it's another UTI, I'm prone to them",
        "I think it's likely to be a water infection like last time",
        "I reckon it's a kidney infection, I had one last year",
        # Treatment named, but no infection to attach it to.
        "I think I might need antibiotics to clear this up",
        "I think I need stronger antibiotics this time as the last lot didn't clear it properly",
        "I had trimethoprim last time and it didn't touch it so I'm hoping for something stronger",
    ]
    assert filler_lexicon_hits([_fragment(t, fragment_type="filler") for t in traps]) == []


def test_signal_language_in_a_signal_library_is_not_a_filler_leak():
    fragments = [
        _fragment("I've had a fever", fragment_type="positive", signal_key=SIGNAL),
        _fragment(
            "it stings when I wee",
            fragment_type="positive",
            signal_key="dysuria_present",
        ),
    ]
    assert filler_lexicon_hits(fragments) == []


# --------------------------------------------------------------------------
# 17b. The cross-signal report (ticket 6, task 1)
#
# The same lexicons as above, asked about every library rather than only
# filler. Unlike filler purity this report has no right answer to assert
# against: a hit is a decision to be made (leave the pair undeclared, declare
# null_on with basis "policy", or rewrite the line), so the tests are about the
# report covering what it claims to cover rather than about the count.
# --------------------------------------------------------------------------


def test_a_fragment_is_never_checked_against_its_own_signal():
    # The dysuria lexicon matches this line by design; that is the lexicon
    # working, and test_every_lexicon_reaches_most_of_its_own_library is where
    # it is measured. Reporting it here would bury the foreign hits under it.
    own = _fragment("it burns when I pee", fragment_type="positive", signal_key="dysuria_present")
    assert [hit.signal for hit in signal_language_hits([own])] == []

    foreign = _fragment("it burns when I pee", fragment_type="positive", signal_key="fever_present")
    assert [hit.signal for hit in signal_language_hits([foreign])] == ["dysuria_present"]


def test_filler_purity_is_the_cross_signal_check_restricted_to_filler():
    # Not an equivalence for its own sake: if the generalisation had changed
    # what filler purity reports, the empty baseline in the test above would be
    # measuring something new while looking untouched.
    fragments = _real_fragments()
    filler_names = {f.library for f in fragments if f.fragment_type == "filler"}
    from_grid = {
        (cell.library, cell.signal, hit.fragment_id)
        for cell in cross_signal_cells(fragments)
        if cell.library in filler_names
        for hit in cell.hits
    }
    from_report = {
        (hit.library, hit.signal, hit.fragment_id) for hit in filler_lexicon_hits(fragments)
    }
    assert from_grid == from_report


def test_the_grid_covers_every_library_against_every_foreign_signal():
    fragments = _real_fragments()
    libraries = {f.library: f.signal_key for f in fragments}
    expected = {
        (library, signal)
        for library, own in libraries.items()
        for signal in SIGNAL_LEXICONS
        if own != signal
    }
    cells = cross_signal_cells(fragments)
    assert {(cell.library, cell.signal) for cell in cells} == expected
    assert len(cells) == len(expected), "a pair is reported twice"


def test_the_grid_is_sorted_worst_first():
    cells = cross_signal_cells(_real_fragments())
    keys = [(-cell.matched, cell.library, cell.signal) for cell in cells]
    assert keys == sorted(keys)


def test_every_line_count_is_the_whole_library():
    fragments = _real_fragments()
    sizes = Counter(f.library for f in fragments)
    for cell in cross_signal_cells(fragments):
        assert cell.lines == sizes[cell.library], (
            f"{cell.library} reports {cell.lines} lines against {cell.signal} but holds "
            f"{sizes[cell.library]}"
        )


def _parse_null_on_block(report):
    """Read the paste-ready block back as ``{library: {signal: declaration}}``.

    Parses it as JSON rather than by string matching, because "can this be
    pasted into the manifest" is the only property the block has to have and a
    trailing comma on a last entry is the way to lose it.
    """
    block = report.split(NULL_ON_BLOCK_HEADER)[1]
    declared = {}
    library, body = None, []
    for raw in block.splitlines():
        line = raw.strip()
        if not line:
            continue
        if line == '"null_on": {':
            body = []
        elif line == "}":
            declared[library] = json.loads("{" + "\n".join(body) + "}")
        elif line.startswith('"'):
            body.append(line)
        else:
            library = line
    return declared


def test_the_paste_ready_block_declares_exactly_the_silent_pairs():
    fragments = _real_fragments()
    cells = cross_signal_cells(fragments)
    declared = _parse_null_on_block("\n".join(render_cross_signal_report(fragments)))

    pairs = {(library, signal) for library, entry in declared.items() for signal in entry}
    assert pairs == {(cell.library, cell.signal) for cell in cells if cell.silent}
    assert all(
        value == {"basis": "absent"} for entry in declared.values() for value in entry.values()
    ), "only the machine-checkable basis may be proposed automatically"


def test_the_report_says_a_zero_is_evidence_and_not_proof():
    # The whole block below it is about to be pasted into the manifest as a
    # guarantee, so the caveat travels with the output rather than living only
    # in arch_training.md.
    report = "\n".join(render_cross_signal_report(_real_fragments()))
    assert "NOT proof" in report


# --------------------------------------------------------------------------
# 17b. The null_on declaration (DD1, DD2, DD3)
#
# Schema tests run against fixtures; the four pinned-set tests below run
# against the real manifest, because the declaration *is* the real manifest and
# a fixture cannot say whether somebody read a library before claiming it was
# silent.
# --------------------------------------------------------------------------


def _spec(**overrides) -> LibrarySpec:
    payload = {
        "name": "lib",
        "file": "lib.txt",
        "signal_key": None,
        "fragment_type": "filler",
    }
    payload.update(overrides)
    return parse_manifest({"libraries": [payload]})[0]


def test_null_on_parses_into_sorted_entries():
    spec = _spec(
        null_on={
            "nocturia_present": {"basis": "absent"},
            "fever_present": {"basis": "policy", "note": "past tense throughout"},
        }
    )
    # Sorted by signal, so two manifests declaring the same pairs in a different
    # order are the same manifest.
    assert spec.null_on == (
        NullOn(signal="fever_present", basis="policy", note="past tense throughout"),
        NullOn(signal="nocturia_present", basis="absent", note=""),
    )


def test_a_library_with_no_null_on_is_undeclared_rather_than_null():
    # The default is silence about the decision, not the decision. A closed-world
    # default would mean adding an eighth signal silently asserted that every
    # existing library was null on it.
    spec = _spec()
    assert spec.null_on == ()


def test_an_unknown_basis_raises():
    with pytest.raises(ManifestError, match="unknown basis"):
        _spec(null_on={"fever_present": {"basis": "silent"}})


def test_a_policy_entry_without_a_note_raises():
    # The whole of DD2: policy is the half no lexicon can check, so the rule that
    # makes the label null has to be written down or the claim is invisible.
    with pytest.raises(ManifestError, match="no note"):
        _spec(null_on={"fever_present": {"basis": "policy"}})


def test_a_policy_entry_whose_note_is_only_whitespace_raises():
    with pytest.raises(ManifestError, match="no note"):
        _spec(null_on={"fever_present": {"basis": "policy", "note": "   "}})


def test_an_absent_entry_needs_no_note_but_may_carry_one():
    spec = _spec(null_on={"fever_present": {"basis": "absent", "note": "flushed toilets"}})
    assert spec.null_on[0].note == "flushed toilets"


def test_declaring_null_on_for_the_librarys_own_signal_raises():
    # That value comes from fragment_type, and two sources for one value is one
    # that can disagree with itself.
    with pytest.raises(ManifestError, match="its own signal"):
        _spec(
            signal_key="fever_present",
            fragment_type="positive",
            null_on={"fever_present": {"basis": "absent"}},
        )


def test_a_signal_the_ruleset_does_not_send_to_the_encoder_raises():
    with pytest.raises(ManifestError, match="does not send to the encoder"):
        parse_manifest(
            {
                "libraries": [
                    {
                        "name": "lib",
                        "file": "lib.txt",
                        "signal_key": None,
                        "fragment_type": "filler",
                        "null_on": {"fever_presnt": {"basis": "absent"}},
                    }
                ]
            },
            signals={"fever_present"},
        )


def test_without_a_ruleset_the_signal_name_is_not_checked():
    # The reporting tools load the manifest with no ruleset in hand, and a lint
    # that refuses to run because the manifest is wrong is useless exactly when
    # it is needed.
    assert _spec(null_on={"anything_at_all": {"basis": "absent"}}).null_on[0].signal == (
        "anything_at_all"
    )


def test_an_unknown_key_inside_a_null_on_entry_raises():
    # "notes" would otherwise be a note that silently does not exist.
    with pytest.raises(ManifestError, match="unknown key"):
        _spec(null_on={"fever_present": {"basis": "policy", "notes": "typo"}})


def test_a_null_on_that_is_not_an_object_raises():
    with pytest.raises(ManifestError, match="not an object keyed by signal"):
        _spec(null_on=["fever_present"])


def test_a_null_on_entry_that_is_not_an_object_raises():
    with pytest.raises(ManifestError, match="is not an object"):
        _spec(null_on={"fever_present": "absent"})


def test_the_declaration_reaches_the_fragment(tmp_path):
    # DD3's instruction 3: resolved once at load time, so build_pools and the
    # companion draw never read the manifest a second time.
    (tmp_path / "lib.txt").write_text("the parking here is impossible\n", encoding="utf-8")
    manifest = _write_manifest(
        tmp_path,
        [
            _entry(
                "lib",
                null_on={
                    "fever_present": {"basis": "absent"},
                    "dysuria_present": {"basis": "policy", "note": "all past tense"},
                },
            )
        ],
        {"lib.txt": _spread_lines("lib", 60)},
    )
    fragment = load_fragments(manifest, check_cells=False)[0]
    assert fragment.null_on_basis("fever_present") == "absent"
    assert fragment.null_on_basis("dysuria_present") == "policy"
    assert fragment.null_on_basis("nocturia_present") is None
    assert fragment.declares_null_on("fever_present")
    assert not fragment.declares_null_on("nocturia_present")


# --------------------------------------------------------------------------
# 17c. The declaration against the real manifest (the CI baseline)
# --------------------------------------------------------------------------

#: Every (library, signal) pair declared ``absent`` in which a lexicon
#: nevertheless finds the signal's language. An entry here is a claim that a
#: line reads as another signal's language, is staying where it is anyway, and
#: somebody decided that on purpose -- exactly as for ``FILLER_PURITY_BASELINE``.
#:
#: All 28 are lexicon over-reach, and they cluster in three families that are
#: worth naming because each is the lexicon working as designed rather than
#: failing: a **flushed toilet** where the fever lexicon wants a flushed face
#: (6 lines, all haematuria); a **counting word** ("times", "more",
#: "constantly", "all day") that qualifies the pain or the colour rather than
#: how often the patient goes (13 lines); and a **pain word** that belongs to
#: another clause than the urinary anchor it was paired with (7 lines). Each
#: pair's ``note`` in the manifest says which.
#:
#: Narrowing the lexicons to clear these would cost real recall -- "flushed" is
#: how patients describe a fever, and "more" is how they describe frequency --
#: which is the trade ``FILLER_PURITY_HEADER`` describes and why baselining is
#: the third resolution rather than the last resort.
ABSENT_PAIR_BASELINE: dict[tuple[str, str], set[str]] = {
    ("dysuria_false", "urinary_frequency_present"): {
        "dysuria_false:64f15eeb",
    },
    ("dysuria_null_hedged", "urinary_frequency_present"): {
        "dysuria_null_hedged:464ee4f6",
        "dysuria_null_hedged:58a8b3c4",
        "dysuria_null_hedged:8e93e0ff",
        "dysuria_null_hedged:cae59b3c",
        "dysuria_null_hedged:ec574b54",
    },
    ("dysuria_null_historical", "flank_pain_present"): {
        "dysuria_null_historical:15e236ea",
    },
    ("dysuria_null_thirdparty", "nocturia_present"): {
        "dysuria_null_thirdparty:4365dff9",
    },
    ("dysuria_true", "urinary_frequency_present"): {
        "dysuria_true:a28e78a6",
    },
    ("flank_pain_null_historical", "dysuria_present"): {
        "flank_pain_null_historical:124d71ca",
    },
    ("haematuria_false", "fever_present"): {
        "haematuria_false:b692c4ce",
    },
    ("haematuria_null_hedged", "fever_present"): {
        "haematuria_null_hedged:b46c1780",
        "haematuria_null_hedged:d9bf40cb",
        "haematuria_null_hedged:e2b503fc",
    },
    ("haematuria_null_hedged", "urinary_frequency_present"): {
        "haematuria_null_hedged:f5ac0bee",
    },
    ("haematuria_null_historical", "dysuria_present"): {
        "haematuria_null_historical:d046cb69",
    },
    ("haematuria_null_historical", "urinary_frequency_present"): {
        "haematuria_null_historical:3823ca1c",
    },
    ("haematuria_null_thirdparty", "nocturia_present"): {
        "haematuria_null_thirdparty:ed75fa0d",
    },
    ("haematuria_true", "fever_present"): {
        "haematuria_true:7ea098d1",
        "haematuria_true:a2e5d4cc",
    },
    ("haematuria_true", "urinary_frequency_present"): {
        "haematuria_true:5cf89fbc",
        "haematuria_true:b54f9151",
    },
    ("nocturia_null_attribution", "dysuria_present"): {
        "nocturia_null_attribution:3b2e43f2",
        "nocturia_null_attribution:7d2de3ba",
        "nocturia_null_attribution:e51cceef",
    },
    ("nocturia_null_attribution", "haematuria_present"): {
        "nocturia_null_attribution:dd528c2a",
    },
    ("nocturia_null_metaphor", "dysuria_present"): {
        "nocturia_null_metaphor:be836a5b",
    },
    ("recent_uti_null_hedged", "urinary_frequency_present"): {
        #: The pairs declared ``null_on`` with basis ``policy`` -- the half of the
        #: guarantee no lexicon can check. Pinned so that adding one is a deliberate
        #: edit to this list rather than a line in a 1000-line manifest diff, because an
        #: unchecked claim that nobody notices arriving is the failure mode DD2 exists to
        #: prevent. Nineteen of the twenty-three are on ``recent_uti_present``, which is
        #: the expected shape: its lexicon deliberately matches the infection nouns
        #: every one of these libraries uses while its recency modifiers stop short of
        #: "last time", "again" and "I'm prone to them".
        "recent_uti_null_hedged:effd92b2",
    },
}

POLICY_PAIRS: frozenset[tuple[str, str]] = frozenset(
    {
        ("dysuria_false", "recent_uti_present"),
        ("dysuria_null_historical", "recent_uti_present"),
        ("dysuria_null_thirdparty", "recent_uti_present"),
        ("expectations", "recent_uti_present"),
        ("fever_false", "recent_uti_present"),
        ("fever_null_historical", "recent_uti_present"),
        ("fever_true", "recent_uti_present"),
        ("flank_pain_null_hedged", "recent_uti_present"),
        ("flank_pain_null_historical", "recent_uti_present"),
        ("flank_pain_null_thirdparty", "recent_uti_present"),
        ("haematuria_null_hedged", "recent_uti_present"),
        ("haematuria_null_historical", "flank_pain_present"),
        ("haematuria_null_historical", "recent_uti_present"),
        ("haematuria_null_thirdparty", "recent_uti_present"),
        ("nocturia_false", "recent_uti_present"),
        ("nocturia_null_historical", "recent_uti_present"),
        ("nocturia_null_thirdparty", "recent_uti_present"),
        ("recent_uti_null_hedged", "dysuria_present"),
        ("recent_uti_true", "dysuria_present"),
        ("urinary_frequency_null_adjacent", "haematuria_present"),
        ("urinary_frequency_null_historical", "recent_uti_present"),
        ("urinary_frequency_null_thirdparty", "recent_uti_present"),
        ("uti_speculation", "recent_uti_present"),
    }
)

#: The pairs deliberately left undeclared, and therefore ineligible as
#: companions. Fourteen of the sixteen are the nocturia / urinary-frequency
#: pair in both directions: "up three times in the night for a wee" genuinely
#: asserts both signals, the assertion is a per-*line* fact over libraries whose
#: lines disagree, and DD1 has no state that can express that. The other two are
#: the same fault in single lines -- ``dysuria_true`` carries "I've been waking
#: up at night because weeing is so painful" and ``flank_pain_false`` carries
#: "My sides feel fine, it's just uncomfortable when I wee".
#:
#: Undeclared is not a workaround here, it is the honest state: a smaller
#: companion pool is a smaller dataset, not a wrong one, and the alternative is
#: a declaration that is false on some lines. Per-line label vectors (12.3)
#: are what would let these pairs be declared, and they are out of scope.
UNDECLARED_PAIRS: frozenset[tuple[str, str]] = frozenset(
    {
        ("dysuria_true", "nocturia_present"),
        ("flank_pain_false", "dysuria_present"),
        ("nocturia_false", "urinary_frequency_present"),
        ("nocturia_null_attribution", "urinary_frequency_present"),
        ("nocturia_null_hedged", "urinary_frequency_present"),
        ("nocturia_null_historical", "urinary_frequency_present"),
        ("nocturia_null_metaphor", "urinary_frequency_present"),
        ("nocturia_null_thirdparty", "urinary_frequency_present"),
        ("nocturia_true", "urinary_frequency_present"),
        ("urinary_frequency_false", "nocturia_present"),
        ("urinary_frequency_null_adjacent", "nocturia_present"),
        ("urinary_frequency_null_hedged", "nocturia_present"),
        ("urinary_frequency_null_historical", "nocturia_present"),
        ("urinary_frequency_null_metaphor", "nocturia_present"),
        ("urinary_frequency_null_thirdparty", "nocturia_present"),
        ("urinary_frequency_true", "nocturia_present"),
    }
)


def test_no_absent_pair_contains_the_signals_language():
    hits: dict[tuple[str, str], set[str]] = {}
    for hit in absent_pair_hits(_real_fragments()):
        hits.setdefault((hit.library, hit.signal), set()).add(hit.fragment_id)
    assert hits == ABSENT_PAIR_BASELINE, (
        "a library declared 'absent' on a signal has acquired that signal's "
        "language, so every companion drawn from it would make its example's "
        "label a lie about that signal (DD3). Either the line moved, the lexicon "
        "widened, or the declaration was wrong: "
        + "; ".join(
            f"{hit.library}->{hit.signal} {hit.fragment_id} {hit.terms} {hit.text}"
            for hit in absent_pair_hits(_real_fragments())
        )
    )


def test_the_policy_pairs_are_exactly_the_pinned_ones():
    found = {(pair.library, pair.signal) for pair in policy_pairs(_real_fragments())}
    assert found == POLICY_PAIRS, (
        "the set of unverifiable null_on claims has changed. Every policy pair is "
        "a decision no lexicon can check, so it arrives here or it arrives "
        f"unnoticed: added={sorted(found - POLICY_PAIRS)} "
        f"removed={sorted(POLICY_PAIRS - found)}"
    )


def test_every_policy_pair_carries_a_note():
    # Enforced by the schema too; asserted here against the real manifest so a
    # note that is present but empty of content is at least visible.
    thin = [
        (pair.library, pair.signal, pair.note)
        for pair in policy_pairs(_real_fragments())
        if len(pair.note) < 40
    ]
    assert not thin, f"a policy claim is too short to be a reason: {thin}"


def test_the_undeclared_pairs_are_exactly_the_pinned_ones():
    found = set(undeclared_pairs(_real_fragments()))
    assert found == UNDECLARED_PAIRS, (
        "the set of pairs left undeclared has changed. This list is the cost of "
        "every decision deliberately unmade, so it shrinks by a declaration "
        f"being written rather than by accident: added={sorted(found - UNDECLARED_PAIRS)} "
        f"removed={sorted(UNDECLARED_PAIRS - found)}"
    )


def test_every_foreign_pair_is_either_declared_or_deliberately_undeclared():
    # The deliverable: no pair is in an unconsidered state. 293 = 43 signal
    # libraries x 6 foreign signals + 5 filler libraries x 7.
    fragments = _real_fragments()
    declared = {
        (pair.library, pair.signal)
        for basis in ("absent", "policy")
        for pair in declared_pairs(fragments, basis)
    }
    assert len(declared) + len(UNDECLARED_PAIRS) == len(cross_signal_cells(fragments))
    assert declared & UNDECLARED_PAIRS == set()


def test_the_real_manifest_declares_only_signals_the_ruleset_sends_to_the_encoder():
    # Catches a typo'd signal name, which is otherwise indistinguishable from a
    # pair nobody declared.
    signals = encoder_signals(json.loads(REAL_RULESET.read_text(encoding="utf-8")))
    load_fragments(REAL_MANIFEST, check_cells=False, signals=signals)


def test_filler_purity_stays_stricter_than_the_declaration():
    # filler_lexicon_hits is deliberately not replaced by absent_pair_hits: the
    # two filler libraries declared 'policy' on recent_uti_present would stop
    # being checked, and filler is paired with examples of every label, so a
    # filler line that acquires signal language is worth catching even where the
    # declaration would tolerate it.
    fragments = _real_fragments()
    filler_policy = {
        (pair.library, pair.signal)
        for pair in policy_pairs(fragments)
        if pair.library in {"expectations", "uti_speculation"}
    }
    assert filler_policy == {
        ("expectations", "recent_uti_present"),
        ("uti_speculation", "recent_uti_present"),
    }
    assert filler_lexicon_hits(fragments) == []


# --------------------------------------------------------------------------
# 17d. What the declaration does to the pools (DD4, DD6, DD17)
# --------------------------------------------------------------------------


@pytest.mark.parametrize("signal", sorted(SIGNAL_LEXICONS))
def test_every_filler_library_is_eligible_for_every_signal(signal):
    # Instruction 10, and DD4's byte-identity argument: the filler filter removes
    # nothing today, so no generated byte moves. It stops being free the moment a
    # filler library goes undeclared on one of the seven, which is a reason to
    # keep that from happening quietly rather than to skip the filter.
    fragments = load_fragments(REAL_MANIFEST, check_cells=False)
    filler = {f.library for f in fragments if f.fragment_type == "filler"}
    pools = build_pools(fragments, signal, "train")
    assert set(pools.filler_libraries) == filler
    assert pools.undeclared_filler == ()


def test_an_undeclared_filler_library_is_excluded_and_named(tmp_path):
    # DD17's downward branch: the ceiling drops rather than the run failing,
    # right up to the point where fewer than two filler libraries are left.
    entries = [
        _entry("pos", signal_key=SIGNAL, fragment_type="positive"),
        _entry("neg", signal_key=SIGNAL, fragment_type="negative"),
        _entry("amb", signal_key=SIGNAL, fragment_type="ambiguous"),
        _entry("fill_a"),
        _entry("fill_b"),
        _entry("fill_c", null_on={}),
    ]
    manifest = _write_manifest(
        tmp_path, entries, {f"{e['name']}.txt": _spread_lines(e["name"], 60) for e in entries}
    )
    pools = build_pools(load_fragments(manifest), SIGNAL, "train")
    assert pools.undeclared_filler == ("fill_c",)
    assert set(pools.filler_libraries) == {"fill_a", "fill_b"}


def test_the_count_ceiling_error_names_the_undeclared_filler_and_the_way_out(tmp_path):
    entries = [
        _entry("pos", signal_key=SIGNAL, fragment_type="positive"),
        _entry("neg", signal_key=SIGNAL, fragment_type="negative"),
        _entry("amb", signal_key=SIGNAL, fragment_type="ambiguous"),
        _entry("fill_a"),
        _entry("fill_b"),
        _entry("fill_c", null_on={}),
    ]
    manifest = _write_manifest(
        tmp_path, entries, {f"{e['name']}.txt": _spread_lines(e["name"], 60) for e in entries}
    )
    pools = build_pools(load_fragments(manifest), SIGNAL, "train")
    with pytest.raises(PoolError) as excinfo:
        generate(pools, count=10, seed=42, fragment_counts={3: 1.0})
    message = str(excinfo.value)
    # A pool error whose real cause is three lines of missing JSON must not read
    # as a library-size problem.
    assert "fill_c" in message
    assert 'basis "policy"' in message


def test_a_run_left_with_one_filler_library_raises_and_names_the_declaration(tmp_path):
    entries = [
        _entry("pos", signal_key=SIGNAL, fragment_type="positive"),
        _entry("neg", signal_key=SIGNAL, fragment_type="negative"),
        _entry("amb", signal_key=SIGNAL, fragment_type="ambiguous"),
        _entry("fill_a"),
        _entry("fill_b", null_on={}),
        _entry("fill_c", null_on={}),
    ]
    manifest = _write_manifest(
        tmp_path, entries, {f"{e['name']}.txt": _spread_lines(e["name"], 60) for e in entries}
    )
    with pytest.raises(PoolError) as excinfo:
        build_pools(load_fragments(manifest), SIGNAL, "train")
    assert "fill_b, fill_c" in str(excinfo.value)


def test_the_companion_pool_holds_declared_foreign_libraries_only():
    fragments = load_fragments(REAL_MANIFEST, check_cells=False)
    pools = build_pools(fragments, "fever_present", "train")
    pairs = {(signal, library) for signal, library, _ in pools.companion}

    # No filler, and nothing of the primary signal: the primary signal enters an
    # example through the decisive slot alone, or null_structural and
    # null_ambiguous collapse into each other (DD6).
    assert all(signal != "fever_present" for signal, _ in pairs)
    assert not any(library in {"tangents", "expectations"} for _, library in pairs)

    # Declared pairs are in; undeclared ones are out.
    assert ("dysuria_present", "dysuria_true") in pairs
    assert ("nocturia_present", "nocturia_true") in pairs
    assert pools.companion_signals == (
        "dysuria_present",
        "flank_pain_present",
        "haematuria_present",
        "nocturia_present",
        "recent_uti_present",
        "urinary_frequency_present",
    )


def test_an_undeclared_pair_keeps_its_library_out_of_the_companion_pool():
    # The two pairs the declaration pass deliberately left undeclared, seen from
    # the pool that consumes them.
    fragments = load_fragments(REAL_MANIFEST, check_cells=False)
    nocturia = build_pools(fragments, "nocturia_present", "train")
    assert "dysuria_true" not in {library for _, library, _ in nocturia.companion}
    assert "urinary_frequency_true" not in {library for _, library, _ in nocturia.companion}

    dysuria = build_pools(fragments, "dysuria_present", "train")
    assert "flank_pain_false" not in {library for _, library, _ in dysuria.companion}


def test_the_companion_pool_is_split_restricted():
    # DD9: a companion comes from the same split as the example. fold_bucket is a
    # pure hash of the cluster key, with no knowledge of which signal's run is
    # generating, so this is free -- but a fever *test* example holding a dysuria
    # *train* fragment would be training text inside the test set.
    fragments = load_fragments(REAL_MANIFEST, check_cells=False)
    for split in SPLITS:
        pools = build_pools(fragments, "fever_present", split)
        assert all(f.split == split for _, _, members in pools.companion for f in members), (
            f"a companion fragment from outside {split} reached the {split} pool"
        )


def test_nothing_draws_from_the_companion_pool_at_share_zero():
    # The default is not "a small share", it is off: build_pools may carry other
    # signals' fragments and no draw touches them. The golden content digest is
    # the other half of this; this half says so against the real libraries.
    fragments = load_fragments(REAL_MANIFEST, check_cells=False)
    pools = build_pools(fragments, "fever_present", "train")
    assert pools.companion
    companion_ids = {f.fragment_id for _, _, members in pools.companion for f in members}
    examples, _ = generate(pools, count=400, seed=42)
    used = {fid for example in examples for fid in example.meta["fragment_ids"]}
    assert used & companion_ids == set()


def test_the_real_libraries_put_other_symptoms_into_fever_nulls():
    # The deliverable, stated against the tree as committed rather than against a
    # fixture: a fever_present null example whose text is dense with another
    # symptom's clinical language. Every null example ever generated before this
    # paired the absence of fever language with bland filler, which made
    # "clinical-sounding text -> not null" a perfect rule on our data and a
    # catastrophic one on real submissions.
    fragments = load_fragments(REAL_MANIFEST, check_cells=False)
    pools = build_pools(fragments, "fever_present", "train")
    examples, _ = generate(pools, count=400, seed=42, companion_share=0.5)
    origin = {f.fragment_id: f.signal_key for f in fragments}

    with_companions = [
        example
        for example in examples
        if example.labels["fever_present"] is None
        and any(origin[fid] not in (None, "fever_present") for fid in example.meta["fragment_ids"])
    ]
    assert len(with_companions) > 50
    assert all(example.meta["filler_only"] is False for example in with_companions)


# --------------------------------------------------------------------------
# The merge guards.
#
# Four library tickets landed in quick succession and their merges concatenated
# conflicting edits instead of merging them. The manifest ended up as invalid
# JSON with two pairs of entries fused into one object, and one library
# disappeared entirely because duplicate JSON keys are last-wins. The
# architecture doc ended up listing flank_pain twice, once with pre-expansion
# counts.
#
# None of the tests above fire on any of that: they load the manifest through
# ``json.load``, which accepts duplicate keys silently, and they never read the
# doc. These four do, and they are deliberately about the *tree as committed*
# rather than about any fixture.
# --------------------------------------------------------------------------

DOC = Path(__file__).resolve().parents[1] / "documentation" / "arch_training.md"

#: Directories under data/synthetic/ whose .txt files are not libraries.
_NON_LIBRARY_DIRS = ("drafts", "generated")

#: A section 3 table row: ``| `conditions/uti/symptoms/fever/fever_true.txt` | 96 | ... |``
_DOC_ROW = re.compile(r"^\| `([^`]+\.txt)` \| (\d+) \|", re.M)


def _doc_rows() -> list[tuple[str, int]]:
    return [(path, int(count)) for path, count in _DOC_ROW.findall(DOC.read_text())]


def _library_line_count(relative_path: str) -> int:
    text = (REAL_MANIFEST.parent / relative_path).read_text()
    return sum(1 for line in text.splitlines() if line.strip())


def test_the_manifest_has_no_duplicate_json_keys():
    # The fault that made the manifest invalid: a merge fused two entries into
    # one object. json.load resolves duplicate keys last-wins, so the first
    # library silently vanishes rather than raising. Only object_pairs_hook
    # sees it.
    offenders: list[str] = []

    def reject_duplicates(pairs):
        keys = [key for key, _ in pairs]
        offenders.extend(key for key in keys if keys.count(key) > 1)
        return dict(pairs)

    json.loads(REAL_MANIFEST.read_text(), object_pairs_hook=reject_duplicates)
    assert not offenders, (
        "the manifest has duplicate keys within one object, which means a merge "
        f"fused two library entries and one of them has been lost: {sorted(set(offenders))}"
    )


def test_every_library_file_on_disk_is_declared_in_the_manifest():
    # The other half of the same fault. A library the manifest no longer names
    # is not an error anywhere -- load_fragments only checks the reverse
    # direction -- so it would quietly stop being training data.
    declared = {entry["file"] for entry in json.loads(REAL_MANIFEST.read_text())["libraries"]}
    root = REAL_MANIFEST.parent
    on_disk = {
        str(path.relative_to(root))
        for path in root.rglob("*.txt")
        if not any(part in _NON_LIBRARY_DIRS for part in path.relative_to(root).parts)
    }
    assert on_disk == declared, (
        "a fragment library on disk is missing from the manifest (or vice versa): "
        f"undeclared={sorted(on_disk - declared)} missing_from_disk={sorted(declared - on_disk)}"
    )


def test_the_architecture_doc_lists_every_library_exactly_once():
    # Catches the duplicated table: flank_pain appeared twice, once with its
    # current counts and once with the pre-expansion seed numbers, and a reader
    # has no way to tell which block is live.
    rows = _doc_rows()
    paths = [path for path, _ in rows]
    duplicated = sorted({path for path in paths if paths.count(path) > 1})
    assert not duplicated, f"arch_training.md lists these libraries more than once: {duplicated}"

    declared = {entry["file"] for entry in json.loads(REAL_MANIFEST.read_text())["libraries"]}
    assert set(paths) == declared, (
        "arch_training.md's library table has drifted from the manifest: "
        f"undocumented={sorted(declared - set(paths))} stale_rows={sorted(set(paths) - declared)}"
    )


def test_the_architecture_doc_fragment_counts_match_the_libraries():
    # The counts are per-library totals that only a merged tree can compute, so
    # they go stale on merge rather than in the PR that moved them. Growing a
    # library and not updating the table is the common case.
    wrong = [
        f"{path}: doc says {count}, file has {_library_line_count(path)}"
        for path, count in _doc_rows()
        if count != _library_line_count(path)
    ]
    assert not wrong, "arch_training.md's fragment counts are out of date: " + "; ".join(wrong)


def test_hedge_markers_are_reported_for_decisive_libraries_only():
    fragments = [
        _fragment("I think I might have a fever", fragment_type="positive", signal_key="s"),
        _fragment("probably no fever", fragment_type="negative", signal_key="s"),
        _fragment("maybe warm, hard to tell", fragment_type="ambiguous", signal_key="s"),
        _fragment("my neighbour might be unwell", fragment_type="confounder", signal_key="s"),
        _fragment("the bus was probably late"),
    ]
    # Ambiguous and confounder fragments are supposed to hedge, and filler is
    # not this report's business, so only the decisive two are reported.
    assert {hit.text for hit in hedge_marker_hits(fragments)} == {
        "I think I might have a fever",
        "probably no fever",
    }


def test_hedge_report_lists_every_marker_it_matched():
    fragment = _fragment("I'm not sure, could be a fever", fragment_type="positive", signal_key="s")
    (hit,) = hedge_marker_hits([fragment])
    assert hit.terms == ("could be", "not sure")


def test_hedge_markers_match_on_word_boundaries():
    fragment = _fragment("the mighty river", fragment_type="positive", signal_key="s")
    assert hedge_marker_hits([fragment]) == []


def test_hedge_report_does_not_change_any_fragment():
    fragments = [_fragment("I think I have a fever", fragment_type="positive", signal_key="s")]
    before = list(fragments)
    hedge_marker_hits(fragments)
    assert fragments == before


def _near_duplicate_pair(split_a: str, split_b: str) -> list[Fragment]:
    return [
        _fragment(
            "My colleague went home with a fever on Monday and we share an office",
            fragment_id="lib:aaaaaaaa",
            split=split_a,
        ),
        _fragment(
            "My colleague went home with a fever on Tuesday and we share an office",
            fragment_id="lib:bbbbbbbb",
            split=split_b,
        ),
    ]


def test_near_duplicates_in_different_splits_are_reported():
    (pair,) = cross_split_near_duplicates(_near_duplicate_pair("train", "val"))
    assert pair.ratio >= 0.6
    assert {pair.left.split, pair.right.split} == {"train", "val"}


def test_near_duplicates_within_one_split_are_not_reported():
    # Same-split twins cost a little diversity; they do not let a validation
    # example borrow lexical content from a training example.
    assert cross_split_near_duplicates(_near_duplicate_pair("train", "train")) == []


def test_near_duplicates_are_not_compared_across_libraries():
    left, right = _near_duplicate_pair("train", "val")
    assert cross_split_near_duplicates([left, replace(right, library="other")]) == []


def test_unrelated_fragments_are_not_near_duplicates():
    fragments = [
        _fragment("I had a fever on Monday", fragment_id="lib:a", split="train"),
        _fragment("the parking at the surgery is impossible", fragment_id="lib:b", split="val"),
    ]
    assert cross_split_near_duplicates(fragments) == []


def test_cluster_markers_keep_twins_out_of_the_near_duplicate_report(tmp_path):
    # The report is the feedback loop on Task 1's manual clustering pass: a
    # tagged twin pair cannot straddle a split, so it cannot be reported.
    twins = ["[c01] my husband has had a fever for three days now"]
    twins += ["[c01] my boyfriend has had a fever for about three days now"]
    manifest_path = _write_manifest(
        tmp_path,
        [_entry("nulls", signal_key=SIGNAL, fragment_type="confounder")],
        {"nulls.txt": twins + _spread_lines("nulls", 40)},
    )
    fragments = load_fragments(manifest_path, check_cells=False)
    tagged = {f.fragment_id for f in fragments if f.cluster_id == "nulls:c01"}
    assert len(tagged) == 2
    assert len({f.split for f in fragments if f.fragment_id in tagged}) == 1
    reported = {
        fragment_id
        for pair in cross_split_near_duplicates(fragments)
        for fragment_id in (pair.left.fragment_id, pair.right.fragment_id)
    }
    assert not (tagged & reported)


def test_lint_reports_empty_split_cells_instead_of_aborting(tmp_path):
    # Generation aborts on an empty cell (DD9). The lint must not: it is the
    # tool you reach for when the generator refuses.
    manifest_path = _write_manifest(
        tmp_path,
        [_entry("tiny")],
        {"tiny.txt": ["only one line here"]},
    )
    with pytest.raises(ManifestError):
        load_fragments(manifest_path)
    report = "\n".join(render_report(load_fragments(manifest_path, check_cells=False)))
    assert "empty cell" in report
    assert "empty cells: 2" in report


def test_cli_lint_needs_no_split_count_or_out(capsys):
    assert cli_main(["--lint", "--manifest", str(REAL_MANIFEST)]) == 0
    out = capsys.readouterr().out
    assert "Hedge markers in decisive libraries:" in out
    assert "Cross-split near-duplicates" in out
    assert "Signal language in filler libraries:" in out
    assert "Cross-signal language (every library, every foreign signal)" in out
    # Grouped by signal: a bare total would not say which label a hit falsifies.
    for signal in SIGNAL_LEXICONS:
        assert f"  {signal}: " in out


def test_cli_still_requires_the_generation_flags_without_lint(tmp_path, libraries):
    with pytest.raises(SystemExit) as excinfo:
        cli_main(_argv(manifest=libraries, ruleset=_write_ruleset(tmp_path)))
    assert excinfo.value.code == 2


# --------------------------------------------------------------------------
# 18. Fold mode (DD4) and sidecar fragment provenance (DD16)
#
# Fold mode is opt-in, so the first test here is the one that matters most:
# nothing about the default path may move. Every dataset generated so far and
# every split-coverage number in arch_training.md section 10 depends on it.
# --------------------------------------------------------------------------

#: sha256 of the JSONL produced by the default invocation against the
#: ``libraries`` fixture at seed 42, count 300. Pinned so that any change to
#: banding, hashing, sampling order or the record shape has to be deliberate.
#: There is no historical reference for this digest -- it was recorded from the
#: pre-fold-mode code while adding fold mode, and byte-identity against that
#: code was verified separately at the time.
#:
#: Re-recorded once, when ``meta`` gained ``filler_only`` and the generator
#: version went to 3. That moved every byte of every record without moving a
#: single *choice*, which is why the constant below exists: it is the half of
#: this test that a metadata addition is not allowed to move, and it was carried
#: across the companion commit unchanged.
GOLDEN_DEFAULT_SPLIT_SHA256 = "03e78fe3c47118a17ca5a22c31ce190c9c9066fc7bb329c80ac24064e5f882f8"

#: sha256 of the same dataset projected onto everything the generator *chose* --
#: the text, the labels, the mode and the fragments, with the bookkeeping keys
#: dropped. Recorded from the pre-companion code at ``GENERATOR_VERSION`` 2 and
#: unchanged since: ``--companion-share 0`` draws exactly the sequence it drew
#: before companions existed, which is the claim DD4 makes and the one that
#: makes Arm 0 a control rather than a second treatment.
GOLDEN_DEFAULT_SPLIT_CONTENT_SHA256 = (
    "ad1bdeb647314967dc6cb96c3f6fe3b3ca895531415c78c6dc335e914be66b22"
)


def _content_digest(path: Path) -> str:
    """Hash the choices in a dataset, ignoring the bookkeeping around them."""
    projection = [
        [
            record["example_id"],
            record["split"],
            record["text"],
            record["labels"],
            record["meta"]["label_mode"],
            record["meta"]["fragment_ids"],
            record["meta"]["fragment_subclasses"],
        ]
        for record in (json.loads(line) for line in path.read_text(encoding="utf-8").splitlines())
    ]
    blob = json.dumps(projection, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()


FOLDS = 5


def test_default_invocation_still_produces_the_golden_dataset(tmp_path, libraries):
    out = tmp_path / "out.jsonl"
    assert (
        cli_main(
            _argv(
                manifest=libraries,
                ruleset=_write_ruleset(tmp_path),
                split="train",
                count=300,
                seed=42,
                out=out,
            )
        )
        == 0
    )
    assert hashlib.sha256(out.read_bytes()).hexdigest() == GOLDEN_DEFAULT_SPLIT_SHA256
    assert _content_digest(out) == GOLDEN_DEFAULT_SPLIT_CONTENT_SHA256


def test_an_empty_salt_reproduces_the_unsalted_digest():
    # The salt is threaded through the same hash the default path uses, so an
    # empty salt has to be a no-op rather than merely "close enough".
    assert assign_split("fever_null_hedged:c01", salt="") == "train"
    assert assign_split("i had a fever", salt="") == "train"


def test_a_salt_changes_the_split_assignment():
    keys = [f"key-{i}" for i in range(200)]
    unsalted = [assign_split(key) for key in keys]
    salted = [assign_split(key, salt="32") for key in keys]
    assert unsalted != salted


def _fold_splits(key: str, folds: int = FOLDS, salt: str = "") -> list[str]:
    return [assign_split(key, folds=folds, fold_index=i, salt=salt) for i in range(folds)]


def test_every_cluster_is_a_test_cluster_in_exactly_one_fold():
    for i in range(200):
        splits = _fold_splits(f"key-{i}")
        assert splits.count("test") == 1
        assert splits.count("val") == 1
        assert splits.count("train") == FOLDS - 2


def test_fold_bands_are_60_20_20_at_five_folds():
    counts = Counter(assign_split(f"key-{i}", folds=FOLDS, fold_index=0) for i in range(5000))
    assert counts["test"] == pytest.approx(1000, abs=120)
    assert counts["val"] == pytest.approx(1000, abs=120)
    assert counts["train"] == pytest.approx(3000, abs=180)


def test_fold_index_outside_the_fold_range_raises():
    with pytest.raises(ManifestError, match="outside"):
        assign_split("some key", folds=FOLDS, fold_index=FOLDS)


def test_fold_bucket_below_two_folds_raises():
    with pytest.raises(ManifestError, match="at least 2"):
        fold_bucket("some key", folds=1)


def test_cluster_key_is_the_cluster_when_tagged_and_the_text_otherwise():
    assert cluster_key("alpha:c01", "My son has a fever") == "alpha:c01"
    assert cluster_key(None, "  My son has a FEVER.  ") == normalise("My son has a fever")


@pytest.fixture
def fold_libraries(tmp_path) -> Path:
    """As ``libraries``, but every library large enough to populate five buckets."""
    return _write_manifest(
        tmp_path,
        _RECOMBINE_LIBRARIES,
        {f"{e['name']}.txt": _spread_lines(e["name"], 60) for e in _RECOMBINE_LIBRARIES},
    )


def test_every_fragments_cluster_is_a_test_cluster_in_exactly_one_fold(fold_libraries):
    tested: Counter[str] = Counter()
    every_cluster: set[str] = set()
    for fold in range(FOLDS):
        fragments = load_fragments(fold_libraries, folds=FOLDS, fold_index=fold)
        for fragment in fragments:
            key = cluster_key(fragment.cluster_id, fragment.text)
            every_cluster.add(key)
            if fragment.split == "test":
                tested[key] += 1
    assert every_cluster
    assert {tested[key] for key in every_cluster} == {1}


def test_the_three_splits_are_disjoint_within_every_fold(fold_libraries):
    for fold in range(FOLDS):
        fragments = load_fragments(fold_libraries, folds=FOLDS, fold_index=fold)
        by_split: dict[str, set[str]] = {"train": set(), "val": set(), "test": set()}
        for fragment in fragments:
            by_split[fragment.split].add(fragment.fragment_id)
        assert by_split["train"] & by_split["val"] == set()
        assert by_split["train"] & by_split["test"] == set()
        assert by_split["val"] & by_split["test"] == set()
        assert all(by_split.values()), f"fold {fold} has an empty split"


def test_fold_mode_does_not_move_fragments_between_folds_when_a_library_grows(tmp_path):
    # The same stability guarantee the default bands have. Without it, adding a
    # fragment would silently reshuffle every fold's test set.
    before_dir = tmp_path / "before"
    after_dir = tmp_path / "after"
    before_dir.mkdir()
    after_dir.mkdir()

    lines = _spread_lines("alpha", 60)
    before = _write_manifest(before_dir, [_entry("alpha")], {"alpha.txt": lines})
    after = _write_manifest(
        after_dir, [_entry("alpha")], {"alpha.txt": ["a brand new line about nothing", *lines]}
    )

    kwargs = {"check_cells": False, "folds": FOLDS, "fold_index": 2, "salt": "32"}
    before_splits = {f.fragment_id: f.split for f in load_fragments(before, **kwargs)}
    after_splits = {f.fragment_id: f.split for f in load_fragments(after, **kwargs)}
    assert len(after_splits) == len(before_splits) + 1
    for fragment_id, split in before_splits.items():
        assert after_splits[fragment_id] == split


# --------------------------------------------------------------------------
# The empty-cell guard under fold mode, and the salt search that serves it.
#
# ``fill_d`` holds seven fragments, too few to reliably cover five buckets, so
# it stands in for the real binding constraint: dysuria_null_thirdparty's seven
# clusters. The guard covers the whole manifest, so this blocks a fever run.
# --------------------------------------------------------------------------

_UNBALANCED_LIBRARIES = [*_RECOMBINE_LIBRARIES, _entry("fill_d")]


@pytest.fixture
def unbalanced_fold_libraries(tmp_path) -> Path:
    return _write_manifest(
        tmp_path,
        _UNBALANCED_LIBRARIES,
        {
            f"{e['name']}.txt": _spread_lines(e["name"], 7 if e["name"] == "fill_d" else 60)
            for e in _UNBALANCED_LIBRARIES
        },
    )


def test_a_salt_that_empties_a_cell_still_raises(unbalanced_fold_libraries):
    # Salt "0" leaves fill_d with nothing in bucket 0, so fold 0 has no test
    # fragments for it. Fold mode must not weaken the guard: an empty cell makes
    # a sub-class invisible to evaluation whichever mode produced it.
    with pytest.raises(ManifestError, match="fill_d/test"):
        load_fragments(unbalanced_fold_libraries, folds=FOLDS, fold_index=0, salt="0")


def test_the_fold_empty_cell_error_points_at_the_salt_search(unbalanced_fold_libraries):
    with pytest.raises(ManifestError) as excinfo:
        load_fragments(unbalanced_fold_libraries, folds=FOLDS, fold_index=0, salt="0")
    assert "--find-fold-salt" in str(excinfo.value)
    assert "salt '0'" in str(excinfo.value)


def test_find_fold_salts_returns_only_salts_that_populate_every_bucket(
    unbalanced_fold_libraries,
):
    fragments = load_fragments(unbalanced_fold_libraries, check_cells=False)
    salts = find_fold_salts(fragments, folds=FOLDS, limit=50)
    assert salts and "0" not in salts
    for salt in salts:
        coverage = bucket_coverage(fragments, folds=FOLDS, salt=salt)
        assert all(len(buckets) == FOLDS for buckets in coverage.values())


def test_every_salt_find_fold_salts_returns_generates_every_fold(unbalanced_fold_libraries):
    # The search's whole claim: a salt it returns clears the empty-cell guard
    # for all five folds, not just the one someone happened to try.
    fragments = load_fragments(unbalanced_fold_libraries, check_cells=False)
    salt = find_fold_salts(fragments, folds=FOLDS, limit=50)[0]
    for fold in range(FOLDS):
        load_fragments(unbalanced_fold_libraries, folds=FOLDS, fold_index=fold, salt=salt)


def test_the_agreed_salt_still_clears_the_real_libraries():
    # DD4 pins DEFAULT_FOLD_SALT and every downstream fold uses it. If a
    # library grows past the point where it still works, this fails here
    # rather than halfway through a five-fold training run.
    for fold in range(FOLDS):
        load_fragments(REAL_MANIFEST, folds=FOLDS, fold_index=fold, salt=DEFAULT_FOLD_SALT)


# --------------------------------------------------------------------------
# Fold flags on the CLI
# --------------------------------------------------------------------------


def test_cli_rejects_fold_without_folds(tmp_path, libraries):
    with pytest.raises(SystemExit) as excinfo:
        cli_main(
            _argv(
                manifest=libraries,
                ruleset=_write_ruleset(tmp_path),
                fold=2,
                split="train",
                count=10,
                out=tmp_path / "out.jsonl",
            )
        )
    assert excinfo.value.code == 2
    assert not (tmp_path / "out.jsonl").exists()


def test_cli_rejects_a_split_salt_without_folds(tmp_path, libraries):
    # Salting the default bands would silently move the split of every dataset
    # generated so far, so it is refused rather than quietly honoured.
    with pytest.raises(SystemExit) as excinfo:
        cli_main(
            _argv(
                manifest=libraries,
                ruleset=_write_ruleset(tmp_path),
                split_salt="32",
                split="train",
                count=10,
                out=tmp_path / "out.jsonl",
            )
        )
    assert excinfo.value.code == 2


def test_cli_rejects_a_fold_outside_the_fold_range(tmp_path, fold_libraries):
    with pytest.raises(SystemExit) as excinfo:
        cli_main(
            _argv(
                manifest=fold_libraries,
                ruleset=_write_ruleset(tmp_path),
                folds=FOLDS,
                fold=FOLDS,
                split="train",
                count=10,
                out=tmp_path / "out.jsonl",
            )
        )
    assert excinfo.value.code == 2


def test_cli_rejects_fewer_than_three_folds(tmp_path, fold_libraries):
    # At K=2 the test and validation buckets consume everything, leaving no
    # training data at all.
    with pytest.raises(SystemExit) as excinfo:
        cli_main(
            _argv(
                manifest=fold_libraries,
                ruleset=_write_ruleset(tmp_path),
                folds=2,
                split="train",
                count=10,
                out=tmp_path / "out.jsonl",
            )
        )
    assert excinfo.value.code == 2


def test_cli_find_fold_salt_needs_no_split_count_or_out(capsys):
    argv = ["--folds", str(FOLDS), "--find-fold-salt", "--manifest", str(REAL_MANIFEST)]
    assert cli_main(argv) == 0
    printed = capsys.readouterr().out.splitlines()
    assert printed[0].startswith(f"salts below {1000} populating all {FOLDS} buckets")
    assert DEFAULT_FOLD_SALT in printed[1:]


def test_cli_find_fold_salt_requires_folds():
    with pytest.raises(SystemExit) as excinfo:
        cli_main(["--find-fold-salt", "--manifest", str(REAL_MANIFEST)])
    assert excinfo.value.code == 2


def _generate_fold(tmp_path: Path, manifest: Path, split: str, fold: int, **extra) -> dict:
    """Run one fold's generation and return its parsed sidecar."""
    out = tmp_path / f"{split}-{fold}.jsonl"
    assert (
        cli_main(
            _argv(
                manifest=manifest,
                ruleset=_write_ruleset(tmp_path),
                folds=FOLDS,
                fold=fold,
                split=split,
                count=200,
                out=out,
                **extra,
            )
        )
        == 0
    )
    sidecar = json.loads((tmp_path / f"{out.name}.stats.json").read_text(encoding="utf-8"))
    lines = out.read_text(encoding="utf-8").splitlines()
    sidecar["_records"] = [json.loads(line) for line in lines]
    return sidecar


def test_sidecar_records_the_fold_configuration(tmp_path, fold_libraries):
    sidecar = _generate_fold(tmp_path, fold_libraries, "test", 3)
    assert sidecar["folds"] == FOLDS
    assert sidecar["fold_index"] == 3
    assert sidecar["split_salt"] == DEFAULT_FOLD_SALT


def test_sidecar_records_an_explicit_split_salt(tmp_path, fold_libraries):
    sidecar = _generate_fold(tmp_path, fold_libraries, "test", 0, split_salt="7")
    assert sidecar["split_salt"] == "7"


def test_default_mode_sidecar_records_no_fold_configuration(tmp_path, libraries):
    out = tmp_path / "out.jsonl"
    cli_main(
        _argv(
            manifest=libraries,
            ruleset=_write_ruleset(tmp_path),
            split="train",
            count=100,
            out=out,
        )
    )
    sidecar = json.loads((tmp_path / "out.jsonl.stats.json").read_text(encoding="utf-8"))
    assert sidecar["folds"] is None
    assert sidecar["fold_index"] is None
    assert sidecar["split_salt"] == ""


def test_every_fragment_id_in_the_jsonl_has_sidecar_provenance(tmp_path, fold_libraries):
    # Without this the training code cannot compute effective sample size at
    # all: nothing else in a generated dataset says which fragments are the
    # same idea, or which libraries are filler.
    sidecar = _generate_fold(tmp_path, fold_libraries, "test", 1)
    used = {
        fragment_id
        for record in sidecar["_records"]
        for fragment_id in record["meta"]["fragment_ids"]
    }
    assert used
    assert used <= set(sidecar["fragments"])


def test_sidecar_cluster_keys_agree_with_the_manifest_loader(tmp_path, fold_libraries):
    sidecar = _generate_fold(tmp_path, fold_libraries, "test", 1)
    expected = {
        f.fragment_id: cluster_key(f.cluster_id, f.text)
        for f in load_fragments(fold_libraries, folds=FOLDS, fold_index=1, salt=DEFAULT_FOLD_SALT)
    }
    assert sidecar["fragments"]
    for fragment_id, entry in sidecar["fragments"].items():
        assert entry["cluster_key"] == expected[fragment_id]


def test_sidecar_provenance_carries_every_field_slicing_needs(tmp_path, fold_libraries):
    # DD6: meta.fragment_subclasses is not enough to slice on, because the
    # manifest only sets subclass for the ambiguous and confounder libraries.
    # The library and fragment_type are what make filler distinguishable.
    sidecar = _generate_fold(tmp_path, fold_libraries, "test", 0)
    entries = sidecar["fragments"]
    assert all(entry["split"] == "test" for entry in entries.values())
    assert {entry["library"] for entry in entries.values()} == {
        "pos",
        "neg",
        "amb",
        "conf",
        "fill_a",
        "fill_b",
        "fill_c",
    }

    confounder = entries[next(key for key in sorted(entries) if key.startswith("conf:"))]
    assert confounder["library"] == "conf"
    assert confounder["fragment_type"] == "confounder"
    assert confounder["signal_key"] == SIGNAL
    assert confounder["subclass"] == "third_party"
    assert confounder["cluster_key"]

    filler = entries[next(key for key in sorted(entries) if key.startswith("fill_a:"))]
    assert filler["fragment_type"] == "filler"
    assert filler["signal_key"] is None
    assert filler["subclass"] is None


def test_sidecar_provenance_holds_only_the_generated_split(tmp_path, fold_libraries):
    # One sidecar describes one split; merging a fold's three sidecars gives the
    # whole library, which is why every entry keeps its own split.
    test_sidecar = _generate_fold(tmp_path, fold_libraries, "test", 2)
    train_sidecar = _generate_fold(tmp_path, fold_libraries, "train", 2)
    assert set(test_sidecar["fragments"]) & set(train_sidecar["fragments"]) == set()
    assert all(entry["split"] == "train" for entry in train_sidecar["fragments"].values())


# --------------------------------------------------------------------------
# 20. The companion draw (6a, DD5-DD10, DD17)
#
# The fixtures below carry a second signal so that companion behaviour can be
# tested without depending on the real libraries. Everything that must hold
# *numerically* -- the blindness of the count and of the choice -- is asserted
# over thousands of examples rather than over a code path: DD5's hole is
# arithmetic, and a test that only walks the branch would not have caught it.
# --------------------------------------------------------------------------

OTHER_SIGNAL = "dysuria_present"
THIRD_SIGNAL = "nocturia_present"

_COMPANION_LIBRARIES = [
    *_RECOMBINE_LIBRARIES,
    _entry(
        "dys_pos",
        signal_key=OTHER_SIGNAL,
        fragment_type="positive",
        null_on={SIGNAL: {"basis": "absent"}},
    ),
    _entry(
        "dys_neg",
        signal_key=OTHER_SIGNAL,
        fragment_type="negative",
        null_on={SIGNAL: {"basis": "absent"}},
    ),
    _entry(
        "noc_pos",
        signal_key=THIRD_SIGNAL,
        fragment_type="positive",
        null_on={SIGNAL: {"basis": "absent"}},
    ),
    #: Undeclared on fever, so it may not companion a fever run however much
    #: fever text it is sitting next to.
    _entry("noc_neg", signal_key=THIRD_SIGNAL, fragment_type="negative"),
]


@pytest.fixture
def companion_libraries(tmp_path) -> Path:
    """``libraries`` plus two foreign signals, one of them partly undeclared."""
    return _write_manifest(
        tmp_path,
        _COMPANION_LIBRARIES,
        {f"{e['name']}.txt": _spread_lines(e["name"], 60) for e in _COMPANION_LIBRARIES},
    )


def _companion_pools(manifest_path: Path, split: str = "train"):
    return build_pools(load_fragments(manifest_path), SIGNAL, split)


def _origin(manifest_path: Path) -> dict[str, str | None]:
    return {f.fragment_id: f.signal_key for f in load_fragments(manifest_path)}


def _companions(example, origin: dict[str, str | None]) -> list[str]:
    """The foreign signals this example drew, one entry per companion fragment."""
    return [
        str(origin[fid])
        for fid in example.meta["fragment_ids"]
        if origin[fid] not in (None, SIGNAL)
    ]


def test_companion_share_zero_is_inert_against_a_pool_that_could_serve_it(companion_libraries):
    # Not the same test as the golden digest, which runs against a manifest with
    # no companion pool at all. Here the pool is populated and the flag is off.
    pools = _companion_pools(companion_libraries)
    assert pools.companion_signals == (OTHER_SIGNAL, THIRD_SIGNAL)
    off, _ = generate(pools, count=300, seed=42)
    explicit, _ = generate(pools, count=300, seed=42, companion_share=0.0)
    assert [e.text for e in off] == [e.text for e in explicit]
    origin = _origin(companion_libraries)
    assert not any(_companions(example, origin) for example in off)
    assert all(
        example.meta["filler_only"] is (example.meta["label_mode"] == "null_structural")
        for example in off
    )


def test_a_non_zero_share_puts_foreign_signals_into_every_label_mode(companion_libraries):
    pools = _companion_pools(companion_libraries)
    examples, _ = generate(pools, count=2000, seed=42, companion_share=0.5)
    origin = _origin(companion_libraries)
    modes_with_companions = {
        example.meta["label_mode"] for example in examples if _companions(example, origin)
    }
    assert modes_with_companions == set(LABEL_MODES)


def test_the_companion_count_does_not_vary_by_label_mode(companion_libraries):
    # DD5, and the single easiest thing in this feature to get subtly wrong. A
    # structural null has one more non-decisive slot than every other mode at the
    # same fragment count, so a per-slot draw over *those* slots would give
    # structural nulls twice the companions at the default count of two -- and
    # companion count would become a proxy for the label pointing the wrong way:
    # more clinical text -> more likely null. A model can learn that without
    # reading anything, and it would flatter this feature for the wrong reason.
    pools = _companion_pools(companion_libraries)
    examples, _ = generate(pools, count=8000, seed=11, companion_share=0.5)
    origin = _origin(companion_libraries)

    totals: dict[str, list[int]] = {mode: [] for mode in LABEL_MODES}
    for example in examples:
        totals[example.meta["label_mode"]].append(len(_companions(example, origin)))

    means = {mode: sum(values) / len(values) for mode, values in totals.items()}
    assert all(len(values) > 500 for values in totals.values())
    # Expected 0.75 at the default 2=0.5,3=0.5 mix: (0.5 x 1 + 0.5 x 2) x 0.5.
    assert max(means.values()) - min(means.values()) < 0.08, means


def test_which_companion_is_drawn_does_not_vary_by_label_mode(companion_libraries):
    # DD6, the same question asked of *which* rather than *how many*. If true
    # examples drew positive companions more often than null examples did, we
    # would have replaced "clinical language -> not null" with "clinical language
    # -> true", which is the same failure wearing a different hat.
    pools = _companion_pools(companion_libraries)
    examples, _ = generate(pools, count=8000, seed=11, companion_share=0.5)
    fragments = load_fragments(companion_libraries)
    types = {f.fragment_id: f.fragment_type for f in fragments}
    origin = {f.fragment_id: f.signal_key for f in fragments}

    shares: dict[str, float] = {}
    for mode in LABEL_MODES:
        # Companions only. The decisive fragment is positive in every true
        # example and negative in every false one by construction, and counting
        # it here would measure that instead of the companion draw.
        drawn = [
            types[fid]
            for example in examples
            if example.meta["label_mode"] == mode
            for fid in example.meta["fragment_ids"]
            if origin[fid] not in (None, SIGNAL)
        ]
        assert len(drawn) > 300
        shares[mode] = sum(1 for t in drawn if t == "positive") / len(drawn)
    assert max(shares.values()) - min(shares.values()) < 0.1, shares


def test_the_primary_signal_never_reaches_a_non_decisive_slot(companion_libraries):
    # DD6: without this, a fever_null_hedged fragment could land in a fever
    # structural null, null_structural and null_ambiguous would collapse into
    # each other, and --null-ambiguous-ratio would stop meaning anything.
    pools = _companion_pools(companion_libraries)
    examples, _ = generate(pools, count=2000, seed=42, companion_share=0.8)
    types = {f.fragment_id: f.fragment_type for f in load_fragments(companion_libraries)}
    origin = _origin(companion_libraries)

    for example in examples:
        own = [types[fid] for fid in example.meta["fragment_ids"] if origin[fid] == SIGNAL]
        expected = 0 if example.meta["label_mode"] == "null_structural" else 1
        assert len(own) == expected, example.meta


def test_no_example_holds_two_fragments_from_one_signal(companion_libraries):
    # DD8. Two would either agree, doubling the evidence for one claim and
    # teaching nothing, or disagree, which no single emitted label could describe.
    pools = _companion_pools(companion_libraries)
    examples, _ = generate(pools, count=2000, seed=42, companion_share=1.0)
    origin = _origin(companion_libraries)
    for example in examples:
        drawn = _companions(example, origin)
        assert len(drawn) == len(set(drawn)), example.meta


def test_an_undeclared_foreign_library_never_companions(companion_libraries):
    pools = _companion_pools(companion_libraries)
    examples, _ = generate(pools, count=2000, seed=42, companion_share=1.0)
    libraries = {f.fragment_id: f.library for f in load_fragments(companion_libraries)}
    used = {libraries[fid] for example in examples for fid in example.meta["fragment_ids"]}
    assert "noc_pos" in used
    assert "noc_neg" not in used


def test_companions_come_from_the_examples_own_split(companion_libraries):
    # DD9: free today, because build_pools is already split-restricted and
    # fold_bucket knows nothing about signals. Asserted anyway, because it is
    # what would silently stop holding if pools were ever built per signal -- and
    # a fever *test* example holding a dysuria *train* fragment is training text
    # inside the test set.
    fragments = load_fragments(companion_libraries)
    splits = {f.fragment_id: f.split for f in fragments}
    for split in SPLITS:
        pools = build_pools(fragments, SIGNAL, split)
        examples, _ = generate(pools, count=200, seed=42, companion_share=0.8)
        assert all(
            splits[fid] == split for example in examples for fid in example.meta["fragment_ids"]
        )


def test_a_structural_null_keeps_at_least_one_filler(companion_libraries):
    # DD5's other half: the draw runs over fragment_count - 1 slots in every
    # mode, so a structural null's remaining slot is always filler.
    pools = _companion_pools(companion_libraries)
    examples, _ = generate(pools, count=2000, seed=42, companion_share=1.0)
    types = {f.fragment_id: f.fragment_type for f in load_fragments(companion_libraries)}
    structural = [e for e in examples if e.meta["label_mode"] == "null_structural"]
    assert structural
    for example in structural:
        assert any(types[fid] == "filler" for fid in example.meta["fragment_ids"])


def test_filler_only_marks_the_examples_the_merge_may_still_deduplicate(companion_libraries):
    # DD10: at share > 0 a structural null is no longer filler-only, so the
    # merge's structural-null dedup stops firing and the merged tree grows. That
    # is the compute bill, and this is the fact the merge reads to see it.
    pools = _companion_pools(companion_libraries)
    types = {f.fragment_id: f.fragment_type for f in load_fragments(companion_libraries)}
    for share in (0.0, 0.5):
        examples, _ = generate(pools, count=1000, seed=42, companion_share=share)
        for example in examples:
            derived = all(types[fid] == "filler" for fid in example.meta["fragment_ids"])
            assert example.meta["filler_only"] is derived
    structural = [
        e
        for e in generate(pools, count=1000, seed=42, companion_share=0.9)[0]
        if e.meta["label_mode"] == "null_structural"
    ]
    assert sum(1 for e in structural if e.meta["filler_only"]) < len(structural) / 4


def test_companions_raise_the_fragment_count_ceiling(companion_libraries):
    # DD17, upward. Three filler libraries in the fixture and two eligible
    # companion signals, so a four-fragment example is now reachable where it was
    # not. The lower bound on the companion count is what makes it reachable, and
    # it is a function of the count and the pool sizes alone -- never of the mode.
    pools = _companion_pools(companion_libraries)
    assert len(pools.filler) == 3
    with pytest.raises(PoolError, match="up to 4"):
        generate(pools, count=10, seed=42, fragment_counts={4: 1.0})
    examples, _ = generate(pools, count=200, seed=42, fragment_counts={4: 1.0}, companion_share=0.5)
    origin = _origin(companion_libraries)
    assert all(len(e.meta["fragment_ids"]) == 4 for e in examples)
    assert all(_companions(e, origin) for e in examples)


def test_the_ceiling_is_still_a_ceiling(companion_libraries):
    # Three filler libraries plus two companion signals is five distinct sources,
    # and one fragment per signal means six fragments cannot be built.
    pools = _companion_pools(companion_libraries)
    with pytest.raises(PoolError, match="up to 6"):
        generate(pools, count=10, seed=42, fragment_counts={6: 1.0}, companion_share=0.5)


def test_a_share_above_zero_without_an_eligible_pool_is_an_error(libraries):
    # Falling back to filler would produce the control arm's dataset under the
    # treatment arm's flags, and nothing downstream could tell the two apart.
    pools = _pools(libraries)
    assert pools.companion == ()
    with pytest.raises(PoolError, match="companion-share"):
        generate(pools, count=10, seed=42, companion_share=0.5)


def test_a_share_outside_the_unit_interval_is_rejected(companion_libraries):
    pools = _companion_pools(companion_libraries)
    with pytest.raises(DistributionError, match="companion-share"):
        generate(pools, count=10, seed=42, companion_share=1.5)


def test_the_cli_threads_the_share_and_the_sidecar_records_it(tmp_path, companion_libraries):
    out = tmp_path / "out.jsonl"
    assert (
        cli_main(
            _argv(
                manifest=companion_libraries,
                ruleset=_write_ruleset(tmp_path),
                split="train",
                count=600,
                companion_share=0.5,
                out=out,
            )
        )
        == 0
    )
    stats = json.loads((tmp_path / "out.jsonl.stats.json").read_text(encoding="utf-8"))
    assert stats["requested"]["companion_share"] == 0.5
    assert stats["generator_version"] == 3

    companions = stats["companions"]
    # String-keyed like every other tally in build_stats: json.dump coerces int
    # keys silently, and a dict written string-keyed but built int-keyed bites
    # whoever reads the sidecar back.
    assert all(isinstance(key, str) for row in companions["count_by_label"].values() for key in row)
    assert set(companions["signals"]) == {OTHER_SIGNAL, THIRD_SIGNAL}
    assert set(companions["count_by_label_mode"]) == set(LABEL_MODES)

    # The leak detector, read the way a human would read it: the mean companion
    # count per example must agree across the four modes.
    means = {}
    for mode, row in companions["count_by_label_mode"].items():
        total = sum(row.values())
        means[mode] = sum(int(key) * value for key, value in row.items()) / total
    assert max(means.values()) - min(means.values()) < 0.15, means

    drawn = sum(companions["signals"].values())
    assert drawn == sum(
        int(key) * value
        for row in companions["count_by_label"].values()
        for key, value in row.items()
    )
    assert sum(sum(row.values()) for row in companions["label_mix_by_label"].values()) == drawn


# --------------------------------------------------------------------------
# 21. Label vectors and multi-key emission (6b, DD7, DD13)
#
# Built and not measured: no trained arm uses --emit-signals all, and merge-folds
# refuses a multi-key tree. What is tested is the rule, row by row, because the
# masked row is the one whose failure is invisible -- emitting null where a key
# should have been absent teaches every head to answer "not mentioned" to every
# question it was not trained on, and nothing downstream would say so.
# --------------------------------------------------------------------------

_VECTOR_SIGNALS = (SIGNAL, OTHER_SIGNAL, THIRD_SIGNAL)


def _declares(*signals: str) -> dict:
    return {signal: {"basis": "absent"} for signal in signals}


#: Every library declares every foreign signal except ``fill_c``, which is
#: deliberately undeclared on the third signal. That one omission is what makes
#: the masked row reachable in *generated* data rather than only in a unit test:
#: an example holding fill_c emits no third-signal key at all.
_VECTOR_LIBRARIES = [
    _entry(
        "pos",
        signal_key=SIGNAL,
        fragment_type="positive",
        null_on=_declares(OTHER_SIGNAL, THIRD_SIGNAL),
    ),
    _entry(
        "neg",
        signal_key=SIGNAL,
        fragment_type="negative",
        null_on=_declares(OTHER_SIGNAL, THIRD_SIGNAL),
    ),
    _entry(
        "amb",
        signal_key=SIGNAL,
        fragment_type="ambiguous",
        subclass="hedged",
        null_on=_declares(OTHER_SIGNAL, THIRD_SIGNAL),
    ),
    _entry(
        "conf",
        signal_key=SIGNAL,
        fragment_type="confounder",
        subclass="third_party",
        null_on=_declares(OTHER_SIGNAL, THIRD_SIGNAL),
    ),
    _entry("fill_a", null_on=_declares(*_VECTOR_SIGNALS)),
    _entry("fill_b", null_on=_declares(*_VECTOR_SIGNALS)),
    _entry("fill_c", null_on=_declares(SIGNAL, OTHER_SIGNAL)),
    _entry(
        "dys_pos",
        signal_key=OTHER_SIGNAL,
        fragment_type="positive",
        null_on=_declares(SIGNAL, THIRD_SIGNAL),
    ),
    _entry(
        "dys_neg",
        signal_key=OTHER_SIGNAL,
        fragment_type="negative",
        null_on=_declares(SIGNAL, THIRD_SIGNAL),
    ),
    _entry(
        "noc_conf",
        signal_key=THIRD_SIGNAL,
        fragment_type="confounder",
        subclass="third_party",
        null_on=_declares(SIGNAL, OTHER_SIGNAL),
    ),
]


@pytest.fixture
def vector_libraries(tmp_path) -> Path:
    """Three signals whose libraries declare each other, bar one omission."""
    return _write_manifest(
        tmp_path,
        _VECTOR_LIBRARIES,
        {f"{e['name']}.txt": _spread_lines(e["name"], 60) for e in _VECTOR_LIBRARIES},
    )


def _vector_pools(manifest_path: Path, split: str = "train"):
    return build_pools(load_fragments(manifest_path), SIGNAL, split)


# --- The table, row by row -------------------------------------------------


@pytest.mark.parametrize(("fragment_type", "expected"), sorted(FRAGMENT_TYPE_LABELS.items()))
def test_an_asserting_fragment_gives_the_signal_its_own_polarity(fragment_type, expected):
    # Row 2. A confounder asserts null rather than declining to say, which is
    # the whole difference between null_ambiguous and a missing key.
    mode = {True: "true", False: "false"}.get(expected, "null_ambiguous")
    decisive = _fragment(
        "the decisive claim",
        signal_key=SIGNAL,
        fragment_type=fragment_type,
        null_on=(NullOn(signal=OTHER_SIGNAL, basis="absent"),),
    )
    companion = _fragment("some filler", fragment_id="fill:1")
    vector = label_vector([decisive, companion], signal_key=SIGNAL, label_mode=mode)
    assert vector[SIGNAL] is expected


def test_the_signal_is_null_when_every_fragment_only_declares_it():
    # Row 3. No fragment asserts the signal and all of them declare it null_on,
    # so the key is present and its value is null -- a supervised "not
    # mentioned", not a mask.
    fragments = [_fragment(f"filler {i}", fragment_id=f"fill:{i}") for i in range(2)]
    vector = label_vector(fragments, signal_key=SIGNAL, label_mode="null_structural")
    assert vector == {SIGNAL: None}


def test_an_undeclared_fragment_masks_the_signal_rather_than_nulling_it():
    # Row 1, and the row that must not be got backwards. The other fragment
    # declares the foreign signal null_on; this one says nothing about it, so
    # the example is not entitled to a key at all.
    declared = _fragment(
        "declared filler",
        fragment_id="fill:a",
        null_on=(
            NullOn(signal=SIGNAL, basis="absent"),
            NullOn(signal=OTHER_SIGNAL, basis="absent"),
        ),
    )
    silent = _fragment(
        "undeclared filler",
        fragment_id="fill:b",
        null_on=(NullOn(signal=SIGNAL, basis="absent"),),
    )
    vector = label_vector([declared, silent], signal_key=SIGNAL, label_mode="null_structural")
    assert OTHER_SIGNAL not in vector
    assert vector == {SIGNAL: None}


def test_a_signal_no_fragment_names_is_simply_absent():
    # The candidate set needs no ruleset: a signal nothing asserts and nothing
    # declares is one every fragment is undeclared on, so the table masks it.
    fragments = [_fragment(f"filler {i}", fragment_id=f"fill:{i}") for i in range(2)]
    vector = label_vector(fragments, signal_key=SIGNAL, label_mode="null_structural")
    assert "haematuria_present" not in vector


def test_two_fragments_asserting_one_signal_raise_rather_than_resolve():
    # Row 4, verified rather than assumed. Two assertions are either redundant
    # or contradictory, and silently keeping one of them is how a dataset
    # acquires a wrong label.
    first = _fragment(
        "first claim", fragment_id="pos:1", signal_key=SIGNAL, fragment_type="positive", null_on=()
    )
    second = _fragment(
        "second claim", fragment_id="neg:1", signal_key=SIGNAL, fragment_type="negative", null_on=()
    )
    with pytest.raises(AssertionError, match="two fragments assert"):
        label_vector([first, second], signal_key=SIGNAL, label_mode="true")


def test_a_vector_that_disagrees_with_the_spec_is_refused():
    # The primary key is cross-checked against the spec rather than trusted. It
    # cannot differ while every non-decisive slot is drawn from a pool filtered
    # on null_on, so a disagreement means that filter was bypassed -- which
    # would put a wrong label on real training text.
    decisive = _fragment(
        "i had a fever",
        fragment_id="pos:1",
        signal_key=SIGNAL,
        fragment_type="positive",
        null_on=(),
    )
    undeclared = _fragment("filler", fragment_id="fill:x", null_on=())
    with pytest.raises(AssertionError, match="primary signal"):
        label_vector([decisive, undeclared], signal_key=SIGNAL, label_mode="true")


# --- The flag --------------------------------------------------------------


def test_emit_signals_primary_is_the_default_and_changes_nothing(vector_libraries):
    pools = _vector_pools(vector_libraries)
    for share in (0.0, 0.5):
        default, _ = generate(pools, count=400, seed=42, companion_share=share)
        explicit, _ = generate(
            pools, count=400, seed=42, companion_share=share, emit_signals="primary"
        )
        assert [to_record(e) for e in default] == [to_record(e) for e in explicit]
        assert all(set(e.labels) == {SIGNAL} for e in default)


def test_emit_signals_all_changes_only_the_labels(vector_libraries):
    # The DD4 fixture-digest shape: same seed, same draws, same fragments. The
    # flag decides how much of what was already decided gets written down, and
    # nothing else.
    pools = _vector_pools(vector_libraries)
    primary, _ = generate(pools, count=400, seed=42, companion_share=0.5)
    every, _ = generate(pools, count=400, seed=42, companion_share=0.5, emit_signals="all")
    assert [(e.example_id, e.text, e.meta) for e in primary] == [
        (e.example_id, e.text, e.meta) for e in every
    ]
    assert [e.labels for e in primary] != [e.labels for e in every]


def test_the_primary_key_still_holds_what_the_spec_decided(vector_libraries):
    pools = _vector_pools(vector_libraries)
    primary, _ = generate(pools, count=800, seed=7, companion_share=0.5)
    every, _ = generate(pools, count=800, seed=7, companion_share=0.5, emit_signals="all")
    for one, many in zip(primary, every, strict=True):
        assert SIGNAL in many.labels
        assert many.labels[SIGNAL] == one.labels[SIGNAL]


def test_every_emitted_companion_key_matches_that_fragments_own_polarity(vector_libraries):
    pools = _vector_pools(vector_libraries)
    examples, _ = generate(pools, count=1500, seed=7, companion_share=0.6, emit_signals="all")
    fragments = load_fragments(vector_libraries)
    origin = {f.fragment_id: (f.signal_key, f.fragment_type) for f in fragments}

    asserted_keys = 0
    masked_assertions = 0
    for example in examples:
        drawn = {
            signal: FRAGMENT_TYPE_LABELS[fragment_type]
            for signal, fragment_type in (origin[fid] for fid in example.meta["fragment_ids"])
            if signal is not None and signal != SIGNAL
        }
        for signal, value in drawn.items():
            if signal not in example.labels:
                # An assertion is masked by an *unrelated* fragment being
                # undeclared on that signal: fill_c says nothing about the third
                # signal, so an example holding it is not entitled to a key even
                # when a third-signal fragment is sitting right there. The table
                # is read over the whole example, never over one fragment.
                masked_assertions += 1
                continue
            assert example.labels[signal] is value, example.meta
            asserted_keys += 1
        # Everything else the example is entitled to a key for is null.
        for signal, value in example.labels.items():
            if signal != SIGNAL and signal not in drawn:
                assert value is None
    assert asserted_keys > 200
    assert masked_assertions > 20


def test_the_undeclared_pair_masks_its_key_in_generated_data(vector_libraries):
    # fill_c is undeclared on the third signal, so an example holding it emits
    # no key for that signal -- and an example without it does. Both cells have
    # to occur, or the test is asserting nothing.
    pools = _vector_pools(vector_libraries)
    examples, _ = generate(pools, count=1500, seed=7, companion_share=0.5, emit_signals="all")
    libraries = {f.fragment_id: f.library for f in load_fragments(vector_libraries)}

    with_fill_c = [
        e for e in examples if any(libraries[fid] == "fill_c" for fid in e.meta["fragment_ids"])
    ]
    without = [
        e for e in examples if all(libraries[fid] != "fill_c" for fid in e.meta["fragment_ids"])
    ]
    assert len(with_fill_c) > 100 and len(without) > 100
    assert all(THIRD_SIGNAL not in e.labels for e in with_fill_c)
    assert all(THIRD_SIGNAL in e.labels for e in without)
    # The other foreign signal is declared everywhere, so it is never masked.
    assert all(OTHER_SIGNAL in e.labels for e in examples)


def test_no_two_assertion_example_is_ever_built(vector_libraries):
    # DD8 verified rather than assumed: label_vector raises on a second
    # assertion for one signal, so generating at share 1.0 across every label
    # mode passes only because no such example can be assembled.
    pools = _vector_pools(vector_libraries)
    examples, _ = generate(pools, count=2000, seed=11, companion_share=1.0, emit_signals="all")
    assert {e.meta["label_mode"] for e in examples} == set(LABEL_MODES)


def test_an_unknown_emit_signals_mode_is_rejected(vector_libraries):
    pools = _vector_pools(vector_libraries)
    with pytest.raises(DistributionError, match="emit-signals"):
        generate(pools, count=10, seed=42, emit_signals="both")


# --- The sidecar and the CLI ----------------------------------------------


def _vector_stats(tmp_path: Path, manifest: Path, **flags) -> dict:
    out = tmp_path / "out.jsonl"
    assert (
        cli_main(
            _argv(
                manifest=manifest,
                ruleset=_write_ruleset(tmp_path, _VECTOR_SIGNALS),
                split="train",
                count=1200,
                out=out,
                **flags,
            )
        )
        == 0
    )
    return json.loads((tmp_path / "out.jsonl.stats.json").read_text(encoding="utf-8"))


def test_the_sidecar_reports_the_realised_prior_of_every_head(tmp_path, vector_libraries):
    # DD12 made a fact in the file rather than a claim in a document: the
    # decision rule's constraint is stated relative to argmax, and argmax moves
    # with the prior, so a head's prior has to be readable per head.
    stats = _vector_stats(tmp_path, vector_libraries, companion_share=0.5, emit_signals="all")
    assert stats["requested"]["emit_signals"] == "all"
    rows = stats["realised"]["labels_by_signal"]
    assert set(rows) == set(_VECTOR_SIGNALS)
    assert rows[SIGNAL] == {**stats["realised"]["labels"], "absent": 0}

    for signal in (OTHER_SIGNAL, THIRD_SIGNAL):
        row = rows[signal]
        assert sum(row.values()) == stats["realised"]["count"]
        emitted = sum(row[label] for label in ("true", "false", "null"))
        # A companion head is overwhelmingly null, which is DD13's point: its
        # prior is nothing like the primary head's, so the two arms are not
        # comparable on a metric whose constraint is stated relative to argmax.
        # The real six-signal tree lands near 92% because a companion draw is
        # spread over five foreign signals; this fixture spreads it over two, so
        # it is the weaker version of the same shape rather than that number.
        assert row["null"] / emitted > 0.5
    # Only the deliberately undeclared pair is ever masked.
    assert rows[OTHER_SIGNAL]["absent"] == 0
    assert rows[THIRD_SIGNAL]["absent"] > 0


def test_the_sidecar_reports_one_head_at_emit_signals_primary(tmp_path, vector_libraries):
    stats = _vector_stats(tmp_path, vector_libraries, companion_share=0.5)
    assert stats["requested"]["emit_signals"] == "primary"
    rows = stats["realised"]["labels_by_signal"]
    assert set(rows) == {SIGNAL}
    assert rows[SIGNAL] == {**stats["realised"]["labels"], "absent": 0}


def test_the_cli_writes_multi_key_records(tmp_path, vector_libraries):
    out = tmp_path / "out.jsonl"
    assert (
        cli_main(
            _argv(
                manifest=vector_libraries,
                ruleset=_write_ruleset(tmp_path, _VECTOR_SIGNALS),
                split="train",
                count=400,
                companion_share=0.5,
                emit_signals="all",
                out=out,
            )
        )
        == 0
    )
    records = [json.loads(line) for line in out.read_text(encoding="utf-8").splitlines()]
    assert all(SIGNAL in record["labels"] for record in records)
    assert any(len(record["labels"]) == 3 for record in records)


def test_the_cli_rejects_an_unknown_emit_signals_choice(tmp_path, vector_libraries):
    with pytest.raises(SystemExit) as excinfo:
        cli_main(
            _argv(
                manifest=vector_libraries,
                ruleset=_write_ruleset(tmp_path, _VECTOR_SIGNALS),
                split="train",
                count=10,
                emit_signals="everything",
                out=tmp_path / "out.jsonl",
            )
        )
    assert excinfo.value.code == 2
    assert set(EMIT_SIGNALS_MODES) == {"primary", "all"}

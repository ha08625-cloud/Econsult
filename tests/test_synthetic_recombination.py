"""Unit tests for the offline synthetic fragment tooling.

These are pure unit tests with no database, so there is no ``pytestmark``.
"""

import hashlib
import json
import math
from collections import Counter
from dataclasses import replace
from pathlib import Path

import pytest

from scripts.synthetic_data.__main__ import DEFAULT_FOLD_SALT
from scripts.synthetic_data.__main__ import main as cli_main
from scripts.synthetic_data.lint import (
    FEVER_LEXICON,
    cross_split_near_duplicates,
    filler_lexicon_hits,
    hedge_marker_hits,
    render_report,
)
from scripts.synthetic_data.manifest import (
    Fragment,
    LibrarySpec,
    ManifestError,
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
    DistributionError,
    PoolError,
    PoolExhaustedError,
    assemble_text,
    build_pools,
    build_stats,
    generate,
    labels_for_mode,
    parse_distribution,
    parse_fragment_counts,
)
from scripts.synthetic_data.ruleset import RulesetError, validate_signal

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


def _write_ruleset(base: Path) -> Path:
    path = base / "ruleset.json"
    path.write_text(
        json.dumps(
            {
                "questions": [
                    {
                        "question_id": "urinary_symptoms_4",
                        "answer_key": SIGNAL,
                        "answer_type": "Boolean",
                        "send_to_encoder": True,
                    }
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
# Everything except the filler-purity test below runs against synthetic
# fragments. The filler-purity test deliberately reads the real
# data/synthetic/ tree: its entire purpose is to fail when someone edits a
# filler library and reintroduces fever language, which no fixture can catch.
# --------------------------------------------------------------------------

REAL_MANIFEST = Path(__file__).resolve().parents[1] / "data" / "synthetic" / "manifest.json"

#: Filler fragments permitted to match the fever lexicon. Empty, because the
#: current filler libraries are clean under word-boundary matching. The three
#: known incidental hits ("lithotripsy", "photos", "months" all containing the
#: substring "hot") are excluded by \b, not by an allowlist -- see
#: test_the_known_substring_traps_are_not_flagged.
FILLER_PURITY_BASELINE: set[str] = set()


def _real_fragments():
    # check_cells=False: the real fever_null sub-classes are small enough that
    # some (library, split) cells are empty, which aborts generation by design.
    # This test is about filler text, not about split balance.
    return load_fragments(REAL_MANIFEST, check_cells=False)


def test_no_filler_fragment_contains_fever_language():
    hits = filler_lexicon_hits(_real_fragments())
    assert {hit.fragment_id for hit in hits} == FILLER_PURITY_BASELINE, (
        "a filler library has acquired fever language, so examples labelled null "
        "on the strength of their structure would contain fever text: "
        + "; ".join(f"{hit.fragment_id} {hit.terms} {hit.text}" for hit in hits)
    )


def test_the_fever_lexicon_actually_matches_fever_text():
    # Without this, the empty baseline above would pass just as happily against
    # a lexicon that had been broken into matching nothing at all.
    fragments = [
        _fragment("I've had a fever since Monday", fragment_type="filler"),
        _fragment("my temperature was 38.5 this morning", fragment_type="filler"),
        _fragment("I keep getting chills and sweats", fragment_type="filler"),
    ]
    assert len(filler_lexicon_hits(fragments)) == 3


def test_the_known_substring_traps_are_not_flagged():
    # These are the three real filler lines that naive substring matching
    # flags, all on "hot" inside lithotripsy / photos / shot. Word boundaries
    # are the only thing standing between them and a check that fails on day
    # one against clean data.
    traps = [
        "could I be referred for lithotripsy to break it up",
        "My sister texted saying she's worried about me from the photos I sent",
        "I've been unemployed for 8 months and this is my best shot at getting back to work",
    ]
    assert "hot" in FEVER_LEXICON
    assert all("hot" in trap.lower() for trap in traps)
    assert filler_lexicon_hits([_fragment(t, fragment_type="filler") for t in traps]) == []


def test_fever_language_in_a_signal_library_is_not_a_filler_leak():
    fragment = _fragment("I've had a fever", fragment_type="positive", signal_key=SIGNAL)
    assert filler_lexicon_hits([fragment]) == []


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
    assert "Fever language in filler libraries:" in out


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
GOLDEN_DEFAULT_SPLIT_SHA256 = "5844bc1399fdd7af5526935a9c0301cc6f1d577390708a580c43637427ca686a"

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

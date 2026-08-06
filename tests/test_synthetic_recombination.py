"""Unit tests for the offline synthetic fragment tooling.

These are pure unit tests with no database, so there is no ``pytestmark``.
"""

import json
from pathlib import Path

import pytest

from scripts.synthetic_data.manifest import (
    Fragment,
    LibrarySpec,
    ManifestError,
    assign_split,
    check_no_empty_cells,
    deduplicate,
    load_fragments,
    parse_line,
    parse_manifest,
    read_library,
)
from scripts.synthetic_data.normalise import normalise
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

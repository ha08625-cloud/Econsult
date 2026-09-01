"""Unit tests for the procedural declarative fragment generator.

These are pure unit tests with no database, so there is no ``pytestmark``.

Two of them are guards on the committed artefact rather than on the code:
``test_the_committed_library_is_what_the_inventory_generates`` is the
regeneration check CI runs, and
``test_the_committed_library_loads_as_a_library`` is the statement that the
generator's output and the engine's reader agree about the format.
"""

import json
import random
from pathlib import Path

import pytest

from scripts.synthetic_data.__main__ import main as cli_main
from scripts.synthetic_data.declarative import (
    ARITY_CEILING,
    DEFAULT_ARITY_WEIGHTS,
    DEFAULT_INVENTORY,
    DEFAULT_OUT,
    DEFAULT_TARGET_COUNT,
    DeclarativeError,
    Phrase,
    allocate,
    build,
    cluster_for,
    draw_line,
    generate_lines,
    join_items,
    line_labels,
    load_inventory,
    parse_arity_weights,
    render,
    render_jsonl,
)
from scripts.synthetic_data.manifest import DECLARATIVE_TYPE, load_fragments
from scripts.synthetic_data.normalise import normalise

REPO_ROOT = Path(__file__).resolve().parents[1]
REAL_MANIFEST = REPO_ROOT / "data" / "synthetic" / "manifest.json"
REAL_INVENTORY = REPO_ROOT / DEFAULT_INVENTORY
REAL_LIBRARY = REPO_ROOT / DEFAULT_OUT

#: A two-signal stand-in inventory, so the unit tests do not move when a phrase
#: is authored. Four signals, because the arity ceiling is four.
FIXTURE_INVENTORY = {
    "fever_present": (Phrase("a fever", "any fever"),),
    "dysuria_present": (Phrase("pain when I pee", "any pain when I pee"),),
    "nocturia_present": (Phrase("night trips to wee", "any night trips to wee"),),
    "urinary_frequency_present": (Phrase("extra toilet trips", "any extra toilet trips"),),
}


# --------------------------------------------------------------------------
# 1. The conjunction engine (instruction 1)
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("items", "is_positive", "oxford", "expected"),
    [
        (["A"], True, True, "A"),
        (["A"], False, False, "A"),
        (["A", "B"], True, True, "A and B"),
        (["A", "B"], False, True, "A or B"),
        (["A", "B", "C"], True, True, "A, B, and C"),
        (["A", "B", "C"], True, False, "A, B and C"),
        (["A", "B", "C"], False, True, "A, B, or C"),
        (["A", "B", "C"], False, False, "A, B or C"),
        (["A", "B", "C", "D"], True, True, "A, B, C, and D"),
        (["A", "B", "C", "D"], False, False, "A, B, C or D"),
    ],
)
def test_the_conjunction_engine_on_every_length_and_polarity(items, is_positive, oxford, expected):
    assert join_items(items, is_positive=is_positive, oxford=oxford) == expected


def test_a_two_item_list_never_takes_an_oxford_comma():
    # The flag governs the comma before the conjunction in a list of three or
    # more, and nothing else: "A, and B" is not English.
    for oxford in (True, False):
        assert join_items(["A", "B"], is_positive=True, oxford=oxford) == "A and B"


def test_the_negative_conjunction_is_or():
    # "I have not had A and B" denies the conjunction rather than each of them,
    # which is a different claim from the one the label records.
    assert join_items(["A", "B"], is_positive=False, oxford=True) == "A or B"


def test_an_empty_clause_is_an_error_rather_than_an_empty_string():
    with pytest.raises(DeclarativeError):
        join_items([], is_positive=True, oxford=True)


# --------------------------------------------------------------------------
# 2. The frames (instruction 2, DD7)
# --------------------------------------------------------------------------


def test_the_four_frames_and_what_each_renders():
    assert render(["a fever"], [], lead_true=True, oxford=True) == (
        "I have had a fever.",
        "pos_base",
    )
    assert render([], ["any fever"], lead_true=False, oxford=True) == (
        "I have not had any fever.",
        "neg_base",
    )
    assert render(["a fever"], ["any pain when I pee"], lead_true=True, oxford=True) == (
        "I have had a fever, but not any pain when I pee.",
        "pos_base_mixed",
    )
    assert render(["a fever"], ["any pain when I pee"], lead_true=False, oxford=True) == (
        "I have not had any pain when I pee, but I have had a fever.",
        "neg_base_mixed",
    )


def test_the_base_is_chosen_by_the_leading_block_not_the_larger_one():
    # Instruction 2. If the larger block chose the base, a long false block
    # would drag the sentence onto the negative base and the frame would start
    # correlating with the label -- which is exactly what DD7 forbids.
    text, frame = render(["a fever"], ["any A", "any B", "any C"], lead_true=True, oxford=False)
    assert frame == "pos_base_mixed"
    assert text.startswith("I have had a fever, but not")


def test_a_single_polarity_block_ignores_the_leading_coin():
    # An all-true sentence has no false block to lead with, so the coin cannot
    # change the frame. It is still drawn (see the determinism test): a decision
    # that is sometimes skipped would move every subsequent draw.
    for lead_true in (True, False):
        assert render(["a fever"], [], lead_true=lead_true, oxford=True)[1] == "pos_base"


def test_rendering_nothing_is_an_error():
    with pytest.raises(DeclarativeError):
        render([], [], lead_true=True, oxford=True)


# --------------------------------------------------------------------------
# 3. Labels and clusters (instructions 4 and 5, DD2, DD6, DD14)
# --------------------------------------------------------------------------


def test_an_asserted_signal_takes_its_polarity_and_the_rest_are_declared_silent():
    labels = line_labels(
        {"fever_present": True, "dysuria_present": False},
        ["fever_present", "dysuria_present", "flank_pain_present", "haematuria_present"],
    )
    assert labels == {
        "dysuria_present": False,
        "fever_present": True,
        "flank_pain_present": None,
        "haematuria_present": None,
    }


def test_the_nocturia_frequency_partner_is_omitted_rather_than_nulled():
    # DD14. "Up three times in the night for a wee" genuinely asserts both, the
    # overlap is a per-line fact and nobody has decided the general rule -- so a
    # line asserting one and not mentioning the other says *nothing* about the
    # other. Omitted is ineligible for that signal's run; null would be a claim.
    signals = ["fever_present", "nocturia_present", "urinary_frequency_present"]
    assert "urinary_frequency_present" not in line_labels({"nocturia_present": True}, signals)
    assert "nocturia_present" not in line_labels({"urinary_frequency_present": False}, signals)


def test_the_pair_is_declared_silent_when_the_line_asserts_neither():
    # The omission is about the *partner of an assertion*, not about the pair in
    # general: a line that mentions neither is silent on both, like any other
    # signal it does not name.
    labels = line_labels(
        {"fever_present": True},
        ["fever_present", "nocturia_present", "urinary_frequency_present"],
    )
    assert labels["nocturia_present"] is None
    assert labels["urinary_frequency_present"] is None


def test_both_of_the_pair_are_labelled_when_both_are_asserted():
    labels = line_labels(
        {"nocturia_present": True, "urinary_frequency_present": False},
        ["fever_present", "nocturia_present", "urinary_frequency_present"],
    )
    assert labels["nocturia_present"] is True
    assert labels["urinary_frequency_present"] is False


def test_the_cluster_key_is_the_asserted_label_content():
    # DD6's worked example. Polarity is part of the key: two lines naming the
    # same symptoms with opposite polarities make different claims, and that is
    # the discrimination we want measured rather than leaked across the split.
    assert (
        cluster_for({"dysuria_present": False, "fever_present": True, "haematuria_present": True})
        == "decl:dysuria-fever+haematuria+"
    )


def test_clusters_differ_by_polarity_and_not_by_frame():
    positive = cluster_for({"fever_present": True, "dysuria_present": True})
    mixed = cluster_for({"fever_present": True, "dysuria_present": False})
    assert positive != mixed


# --------------------------------------------------------------------------
# 4. Flags and the budget (DD15)
# --------------------------------------------------------------------------


def test_the_arity_weights_parse_and_sort():
    assert parse_arity_weights("2=0.5,3=0.35,4=0.15") == {2: 0.5, 3: 0.35, 4: 0.15}


@pytest.mark.parametrize(
    "raw",
    [
        "1=1.0",  # arity 1 is what the hand-written libraries already are
        "5=1.0",  # five- and six-symptom sentences are out of scope for v1
        "2=0.5,3=0.4",  # does not sum to one
        "2=0.5,2=0.5",  # the same arity twice
        "2",  # not arity=weight
        "two=1.0",
        "2=lots",
        "",
    ],
)
def test_a_malformed_arity_mix_is_rejected(raw):
    with pytest.raises(DeclarativeError):
        parse_arity_weights(raw)


def test_the_budget_is_allocated_exactly_and_deterministically():
    # Largest remainder: the realised arity mix is the declared mix, so it does
    # not wobble with the seed and a run's counts can be read off the flags.
    assert allocate(1000, {2: 0.5, 3: 0.35, 4: 0.15}) == {2: 500, 3: 350, 4: 150}
    assert sum(allocate(7, {2: 0.5, 3: 0.35, 4: 0.15}).values()) == 7
    assert allocate(0, {2: 1.0}) == {2: 0}


def test_a_budget_too_large_for_the_inventory_fails_loudly():
    # Instruction 5: a duplicate is redrawn rather than emitted, because
    # deduplicate() downstream would drop it and the realised count would then
    # silently not be the count asked for. When redrawing cannot find anything
    # new, that has to be an error rather than a short file.
    with pytest.raises(DeclarativeError) as excinfo:
        generate_lines(FIXTURE_INVENTORY, target_count=5000, arity_weights={4: 1.0}, seed=42)
    assert "--target-count" in str(excinfo.value)


def test_an_arity_above_the_signals_available_is_an_error():
    with pytest.raises(DeclarativeError):
        generate_lines(
            {"fever_present": FIXTURE_INVENTORY["fever_present"]},
            target_count=1,
            arity_weights={2: 1.0},
            seed=42,
        )


# --------------------------------------------------------------------------
# 5. Determinism (DD1, and what --check rests on)
# --------------------------------------------------------------------------


def test_the_same_seed_gives_the_same_library():
    first = generate_lines(FIXTURE_INVENTORY, target_count=40, arity_weights={2: 1.0}, seed=42)
    second = generate_lines(FIXTURE_INVENTORY, target_count=40, arity_weights={2: 1.0}, seed=42)
    assert render_jsonl(first) == render_jsonl(second)


def test_a_different_seed_gives_a_different_library():
    first = generate_lines(FIXTURE_INVENTORY, target_count=20, arity_weights={2: 1.0}, seed=42)
    second = generate_lines(FIXTURE_INVENTORY, target_count=20, arity_weights={2: 1.0}, seed=43)
    assert render_jsonl(first) != render_jsonl(second)


def test_every_decision_is_drawn_on_every_line():
    # The order of draws is the contract that makes --check meaningful, and a
    # decision skipped when its outcome does not matter would shift every later
    # draw. Two lines of the same arity therefore consume the same number of
    # values from the RNG, whatever they render.
    for _ in range(20):
        rng = random.Random(7)
        draw_line(rng, FIXTURE_INVENTORY, 2)
        consumed = rng.random()
        rng = random.Random(7)
        draw_line(rng, FIXTURE_INVENTORY, 2)
        assert rng.random() == consumed


def test_the_output_is_sorted_by_cluster_then_text():
    lines = generate_lines(FIXTURE_INVENTORY, target_count=30, arity_weights={2: 1.0}, seed=1)
    assert lines == sorted(lines, key=lambda line: (line.cluster, line.text))


def test_every_generated_line_is_distinct_after_normalisation():
    lines = generate_lines(FIXTURE_INVENTORY, target_count=30, arity_weights={2: 1.0}, seed=3)
    assert len({normalise(line.text) for line in lines}) == len(lines)


def test_the_rendered_file_is_newline_terminated_with_no_trailing_whitespace():
    content = render_jsonl(
        generate_lines(FIXTURE_INVENTORY, target_count=10, arity_weights={2: 1.0}, seed=5)
    )
    assert content.endswith("\n")
    assert all(line == line.rstrip() for line in content.splitlines())
    assert "\r" not in content


# --------------------------------------------------------------------------
# 6. The authored inventory (DD10, DD11)
# --------------------------------------------------------------------------


def test_the_real_inventory_loads_and_covers_the_arity_ceiling():
    inventory = load_inventory(REAL_INVENTORY)
    assert len(inventory) >= ARITY_CEILING
    assert "recent_uti_present" not in inventory


def test_an_inventory_naming_recent_uti_is_refused(tmp_path):
    # DD9. Its label turns on a 30-day window and the section 9 policy rules, so
    # a declarative frame cannot state it -- and a phrase that looked like it
    # could would put a policy judgement into a procedurally labelled line.
    path = tmp_path / "phrases.json"
    path.write_text(
        json.dumps({"recent_uti_present": {"phrases": [{"text": "a UTI", "negated": "any UTI"}]}})
    )
    with pytest.raises(DeclarativeError) as excinfo:
        load_inventory(path)
    assert "recent_uti_present" in str(excinfo.value)


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"fever_present": {}},
        {"fever_present": {"phrases": []}},
        {"fever_present": {"phrases": [{"text": "a fever"}]}},
        {"fever_present": {"phrases": [{"text": "", "negated": "any fever"}]}},
        {"fever_present": {"phrases": [{"text": "a b c d e", "negated": "any a b c d e"}]}},
    ],
)
def test_a_malformed_inventory_is_refused(tmp_path, payload):
    path = tmp_path / "phrases.json"
    path.write_text(json.dumps(payload))
    with pytest.raises(DeclarativeError):
        load_inventory(path)


def test_the_negated_form_is_used_after_a_negative_base_and_never_after_a_positive_one():
    # DD11, seen end to end: "I have not had burning when I pee" is broken
    # English and "I have not had any burning when I pee" is not, so the surface
    # form is authored per phrase rather than derived.
    inventory = {"dysuria_present": (Phrase("burning when I pee", "any burning when I pee"),)}
    inventory["fever_present"] = (Phrase("a fever", "any fever"),)
    lines = generate_lines(inventory, target_count=6, arity_weights={2: 1.0}, seed=11)
    for line in lines:
        if line.labels["dysuria_present"] is False:
            assert "any burning when I pee" in line.text
        elif line.labels["dysuria_present"] is True:
            assert "burning when I pee" in line.text
            assert "any burning when I pee" not in line.text


# --------------------------------------------------------------------------
# 7. The committed artefact (instructions 6, 7 and 8)
# --------------------------------------------------------------------------


def test_the_committed_library_is_what_the_inventory_generates():
    # The regeneration check, as a test as well as a CI step: this is the only
    # thing that stops the committed library and the inventory drifting apart
    # silently, and a drift means the sentences a human read are not the
    # sentences being trained on.
    _, content = build(
        inventory_path=REAL_INVENTORY,
        target_count=DEFAULT_TARGET_COUNT,
        arity_weights=DEFAULT_ARITY_WEIGHTS,
        seed=42,
    )
    assert REAL_LIBRARY.read_text(encoding="utf-8") == content, (
        "data/synthetic/conditions/uti/declarative/declarative_v1.jsonl is not what the "
        "inventory generates. Rerun: python -m scripts.synthetic_data --build-declarative"
    )


def test_the_cli_check_mode_agrees_with_the_committed_file(capsys):
    assert cli_main(["--build-declarative", "--check"]) == 0
    assert "matches the inventory" in capsys.readouterr().out


def test_the_cli_check_mode_fails_on_a_file_that_is_not_the_generated_one(tmp_path, capsys):
    stale = tmp_path / "declarative_v1.jsonl"
    stale.write_text('{"text": "I have had a fever.", "labels": {}, "cluster": "x"}\n')
    assert cli_main(["--build-declarative", "--check", "--out", str(stale)]) == 1
    assert "Rerun --build-declarative" in capsys.readouterr().err


def test_check_without_build_declarative_is_refused():
    # --check reads as "check something" and would otherwise silently generate a
    # dataset, which is the quiet mismatch check_fold_args exists for.
    with pytest.raises(SystemExit):
        cli_main(["--check", "--split", "train", "--count", "1", "--out", "/dev/null"])


def test_building_writes_the_library_and_reports_its_shape(tmp_path, capsys):
    out = tmp_path / "declarative_v1.jsonl"
    assert cli_main(["--build-declarative", "--out", str(out), "--target-count", "50"]) == 0
    printed = capsys.readouterr().out
    assert "50 lines across" in printed
    assert len(out.read_text(encoding="utf-8").splitlines()) == 50


def test_the_committed_library_loads_as_a_library():
    # The generator's output and the engine's reader have to agree about the
    # format, and this is where that is stated. It also pins the shape of what
    # was committed: every line asserts between two and four signals, and every
    # line carries a cluster.
    fragments = [
        fragment
        for fragment in load_fragments(REAL_MANIFEST, check_cells=False)
        if fragment.fragment_type == DECLARATIVE_TYPE
    ]
    assert len(fragments) == DEFAULT_TARGET_COUNT
    for fragment in fragments:
        assert fragment.signal_key is None
        assert fragment.null_on == ()
        assert fragment.cluster_id is not None and fragment.cluster_id.startswith(
            "declarative_v1:decl:"
        )
        asserted = [value for value in fragment.labels.values() if value is not None]
        assert 2 <= len(asserted) <= ARITY_CEILING
        assert fragment.meta["frame"] in {
            "pos_base",
            "pos_base_mixed",
            "neg_base",
            "neg_base_mixed",
        }


def test_the_committed_library_never_labels_recent_uti():
    # DD9 against the artefact rather than the code: nothing in the file may
    # carry a key for the one signal a declarative frame cannot state.
    for raw in REAL_LIBRARY.read_text(encoding="utf-8").splitlines():
        assert "recent_uti_present" not in json.loads(raw)["labels"]


def test_the_committed_library_populates_every_split():
    # A generated library is not exempt from the empty-cell guard, and a split
    # holding none of it would make every declarative line invisible to that
    # split's evaluation.
    fragments = [
        fragment
        for fragment in load_fragments(REAL_MANIFEST)
        if fragment.fragment_type == DECLARATIVE_TYPE
    ]
    assert {fragment.split for fragment in fragments} == {"train", "val", "test"}


def test_no_generated_line_reproduces_a_hand_written_one():
    # deduplicate() is global and would drop such a line anyway; this says so
    # before it happens, because a silent drop makes the realised count wrong
    # and the collision itself is the interesting fact.
    fragments = load_fragments(REAL_MANIFEST, check_cells=False)
    generated = {normalise(f.text) for f in fragments if f.fragment_type == DECLARATIVE_TYPE}
    hand_written = {normalise(f.text) for f in fragments if f.fragment_type != DECLARATIVE_TYPE}
    assert generated & hand_written == set()

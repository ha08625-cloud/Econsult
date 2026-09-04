"""Unit tests for the lexical variant expansion pass.

Pure unit tests on fixed strings for everything above the directory pass -- no
manifest, no ruleset, no fold tree, no database -- so there is no
``pytestmark``. That the pass is testable this way is the point of it being
post-processing over the JSONL rather than a rewrite of the fragment libraries
(``arch_training.md`` 12.10, DD1).

The directory-pass tests at the bottom touch the filesystem, but only a tmp
tree they build by hand, reusing the fixture helpers from the noise suite: the
two passes consume the same tree shape, and two fixtures for one shape drifting
apart is worse than the import.
"""

import json
import random
from pathlib import Path

import pytest

from scripts.encoder_training import dataset
from scripts.synthetic_data import expand, noise
from scripts.synthetic_data.expand import (
    DEFAULT_CLEAN_SHARE,
    RULES_ROOT,
    ExpansionError,
    expand_example,
    expand_text,
    fold_haystack,
    load_rules,
    match_sites,
    parse_rules,
    structural_sequence,
)
from tests.test_synthetic_noise import SIGNAL, read_records, write_tree

#: Enough draws that a one-in-a-thousand hole in a "never" would show.
VOLUME = 2_000


def rule(**overrides):
    """A valid Tier B rule, with whatever the caller wants changed."""
    base = {
        "id": "fever-to-temperature",
        "tier": "B",
        "find": "a fever",
        "replace": "a temperature",
        "invariant": "Both are bare noun phrases naming the same state.",
    }
    base.update(overrides)
    return base


def load(*raw_rules, signal=SIGNAL):
    """Validate a rule document built from ``raw_rules`` and return the rules."""
    _, rules = parse_rules({"signal": signal, "rules": list(raw_rules)}, source="<test>")
    return rules


RULES = load(
    rule(),
    rule(id="temperature-to-fever", find="a temperature", replace="a fever"),
    rule(id="high-temperature-to-fever", find="a high temperature", replace="a fever"),
    rule(id="ive", tier="A", find="I've", replace="I have"),
    rule(id="havent", tier="A", find="haven't", replace="have not"),
)


# ---------------------------------------------------------------------------
# The rule format and its three layers (DD6)
# ---------------------------------------------------------------------------


def test_a_well_formed_rule_file_loads():
    rules = load(rule())
    assert [one.id for one in rules] == ["fever-to-temperature"]
    assert rules[0].weight == 1.0
    assert rules[0].tier == "B"


@pytest.mark.parametrize(
    ("overrides", "fragment"),
    [
        ({"note": "a comment"}, "unknown key"),
        ({"tier": "C"}, "not one of A, B"),
        ({"weight": 0}, "positive number"),
        ({"weight": "1.0"}, "positive number"),
        ({"invariant": "   "}, "non-empty string"),
    ],
)
def test_the_rule_key_set_is_closed_and_typed(overrides, fragment):
    with pytest.raises(ExpansionError, match=fragment):
        load(rule(**overrides))


def test_a_missing_invariant_is_refused():
    raw = rule()
    del raw["invariant"]
    with pytest.raises(ExpansionError, match="missing required key"):
        load(raw)


def test_duplicate_ids_are_refused():
    with pytest.raises(ExpansionError, match="duplicate id"):
        load(rule(), rule(find="a temperature", replace="a fever"))


def test_an_unknown_top_level_key_is_refused():
    with pytest.raises(ExpansionError, match="unknown top-level key"):
        parse_rules(
            {"signal": SIGNAL, "rules": [rule()], "notes": "hello"},
            source="<test>",
        )


def test_a_signal_with_no_lexicon_is_refused():
    with pytest.raises(ExpansionError, match="'signal' must be one of"):
        load(rule(), signal="made_up_signal")


def test_layer_one_refuses_a_find_that_cannot_be_matched_whole_word():
    with pytest.raises(ExpansionError, match="leading or trailing whitespace"):
        load(rule(find="fever "))
    with pytest.raises(ExpansionError, match="start and end on a word character"):
        load(rule(find="(fever)", replace="temperature"))


def test_layer_one_refuses_a_swap_that_only_changes_case():
    with pytest.raises(ExpansionError, match="differ only in case"):
        load(rule(find="a fever", replace="A Fever"))


@pytest.mark.parametrize(
    ("find", "replace"),
    [
        ("a fever", "no fever"),  # inserts a negation
        ("my temperature", "a temperature"),  # drops the person marker
        ("had a fever", "have a fever"),  # moves the tense
        ("a fever", "maybe a fever"),  # adds modality
    ],
)
def test_layer_two_refuses_a_swap_that_moves_a_structural_token(find, replace):
    with pytest.raises(ExpansionError, match="structural-token invariance"):
        load(rule(find=find, replace=replace))


def test_layer_two_survives_contraction_expansion():
    """The Tier A rules the pass exists to carry are not falsely flagged."""
    rules = load(
        rule(id="ive", tier="A", find="I've", replace="I have"),
        rule(id="havent", tier="A", find="haven't", replace="have not"),
    )
    assert [one.id for one in rules] == ["ive", "havent"]
    assert structural_sequence("haven't") == structural_sequence("have not")
    assert structural_sequence("I've") == structural_sequence("I have")


def test_layer_three_refuses_a_swap_that_moves_its_own_signal_out_of_view():
    with pytest.raises(ExpansionError, match="signal-lexicon invariance"):
        load(rule(replace="a headache"))


def test_layer_three_refuses_a_swap_that_introduces_another_signals_language():
    with pytest.raises(ExpansionError, match="introduces dysuria_present language"):
        load(rule(replace="a fever and burning when peeing"))


def test_each_layer_names_the_rule_and_why():
    with pytest.raises(ExpansionError) as error:
        load(rule(id="my-rule", replace="no fever"))
    message = str(error.value)
    assert "my-rule" in message
    assert "DD6 layer 2" in message


def test_load_rules_reports_the_path_and_a_digest(tmp_path):
    path = tmp_path / f"{SIGNAL}.rules.json"
    path.write_text(json.dumps({"signal": SIGNAL, "rules": [rule()]}), encoding="utf-8")
    loaded = load_rules(path)
    assert loaded.signal == SIGNAL
    assert loaded.path == path
    assert len(loaded.digest) == 64
    assert [one.id for one in loaded.rules] == ["fever-to-temperature"]


def test_a_missing_rule_file_is_refused(tmp_path):
    with pytest.raises(ExpansionError, match="no rule file at"):
        load_rules(tmp_path / "absent.rules.json")


def test_rule_files_live_outside_the_library_tree():
    """DD11. ``data/synthetic/`` is guarded as libraries and manifest only."""
    assert not RULES_ROOT.is_relative_to("data/synthetic")


# ---------------------------------------------------------------------------
# Matching
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("word", ["lithotripsy", "photos", "shot", "hotel"])
def test_matching_never_fires_inside_a_longer_word(word):
    rules = load(rule(id="hot", find="hot", replace="warm"))
    assert match_sites(f"I felt {word} all evening", rules) == []


def test_matching_is_case_insensitive_and_apostrophe_folding():
    rules = load(rule(id="ive", tier="A", find="I've", replace="I have"))
    assert len(match_sites("I’ve had it", rules)) == 1
    assert len(match_sites("i've had it", rules)) == 1


def test_folding_preserves_every_offset():
    text = "I’VE had A Fever."
    assert len(fold_haystack(text)) == len(text)


def test_the_longest_match_at_a_position_wins():
    text = "I had a high temperature last night"
    (site,) = match_sites(text, RULES)
    assert text[site.start : site.end] == "a high temperature"
    assert [one.id for one in site.rules] == ["high-temperature-to-fever"]


def test_sites_do_not_overlap_and_run_left_to_right():
    text = "A fever on Monday and a fever on Tuesday"
    sites = match_sites(text, RULES)
    assert [text[site.start : site.end] for site in sites] == ["A fever", "a fever"]
    assert sites[0].end <= sites[1].start


def test_a_replacement_is_never_rematched():
    """Sites are found once, on the source text, so a swap cannot compound."""
    text = "I had a fever"
    result = expand_example(text, RULES, random.Random(0), rate=1.0)
    assert result.text == "I had a temperature"


def test_leading_capitalisation_is_preserved():
    rules = load(rule())
    assert expand_text("A fever.", rules, random.Random(0), rate=1.0)[0] == "A temperature."
    assert expand_text("a fever.", rules, random.Random(0), rate=1.0)[0] == "a temperature."


def test_rate_zero_leaves_the_text_alone():
    text = "I had a fever and a temperature"
    for seed in range(50):
        assert expand_text(text, RULES, random.Random(seed), rate=0.0)[0] == text


def test_a_rule_fires_per_site_rather_than_per_example():
    """DD3: three mentions can move one, two, three or none of them."""
    text = "a fever on Monday, a fever on Tuesday, a fever on Wednesday"
    counts = {
        expand_example(text, RULES, random.Random(seed), rate=0.5).applied for seed in range(VOLUME)
    }
    assert counts == {0, 1, 2, 3}


def test_the_weighted_choice_reaches_every_rule_matching_a_site():
    rules = load(
        rule(id="to-temperature", find="a fever", replace="a temperature"),
        rule(id="to-high-temperature", find="a fever", replace="a high temperature"),
    )
    fired = set()
    for seed in range(VOLUME):
        _, applications = expand_text("a fever", rules, random.Random(seed), rate=1.0)
        fired.update(applications)
    assert fired == {"to-temperature", "to-high-temperature"}


def test_weight_zero_is_refused_rather_than_silently_disabling_a_rule():
    with pytest.raises(ExpansionError, match="positive number"):
        load(rule(weight=0.0))


# ---------------------------------------------------------------------------
# Label blindness (DD5), the whole safety argument for section 2
# ---------------------------------------------------------------------------


def test_the_substitution_path_takes_no_label_argument():
    """Mechanical half of DD5: a label cannot reach the decision even by
    accident, because no function on the path accepts one."""
    for function in (expand_text, expand_example, match_sites):
        parameters = set(function.__code__.co_varnames[: function.__code__.co_argcount])
        assert not parameters & {"labels", "label", "meta", "label_mode"}


def test_expansion_depends_only_on_the_text_the_rules_and_the_draw():
    """Behavioural half: the same id and text expand identically whatever the
    record around them says, so a rule cannot be applied to ``true`` examples
    and not to ``null`` ones."""
    text = "I had a fever last night"
    expected = expand_text(text, RULES, noise.example_rng(7, "e-1"), rate=0.6)
    for _ in range(20):
        assert expand_text(text, RULES, noise.example_rng(7, "e-1"), rate=0.6) == expected


# ---------------------------------------------------------------------------
# The directory pass
# ---------------------------------------------------------------------------


RULE_DOCUMENT = {
    "signal": SIGNAL,
    "rules": [
        rule(id="temperature-to-fever", find="temperature", replace="fever"),
        rule(id="neighbour-spelling", tier="A", find="neighbour", replace="neighbor"),
    ],
}


@pytest.fixture
def rules_dir(tmp_path):
    directory = tmp_path / "expansion-rules"
    directory.mkdir()
    (directory / f"{SIGNAL}.rules.json").write_text(
        json.dumps(RULE_DOCUMENT, indent=2), encoding="utf-8"
    )
    return directory


@pytest.fixture
def tree(tmp_path):
    source = tmp_path / "clean"
    write_tree(source)
    return source


def run_tree(source, target, rules_dir, **kwargs):
    kwargs.setdefault("rate", 0.5)
    kwargs.setdefault("root", source.parent)
    return expand.expand_tree(source, target, rules_dir=rules_dir, **kwargs)


def test_the_output_tree_keeps_every_filename_and_every_field_but_text(tree, rules_dir, tmp_path):
    target = tmp_path / "expanded"
    run_tree(tree, target, rules_dir)

    assert sorted(path.name for path in target.iterdir()) == sorted(
        path.name for path in tree.iterdir()
    )
    for path in sorted(tree.glob("*.jsonl")):
        clean = read_records(path)
        expanded = read_records(target / path.name)
        assert len(clean) == len(expanded)
        for before, after in zip(clean, expanded, strict=True):
            assert before["example_id"] == after["example_id"]
            assert before["split"] == after["split"]
            assert before["labels"] == after["labels"]
            assert before["meta"] == after["meta"]
            assert list(after) == list(noise.RECORD_KEYS)


def test_something_actually_changed(tree, rules_dir, tmp_path):
    target = tmp_path / "expanded"
    tally = run_tree(tree, target, rules_dir, rate=1.0, clean_share=0.0)
    assert tally.total_applied > 0
    assert tally.changed > 0


def test_files_that_are_neither_dataset_nor_sidecar_are_copied_through(tree, rules_dir, tmp_path):
    (tree / "notes.txt").write_text("keep me\n", encoding="utf-8")
    target = tmp_path / "expanded"
    run_tree(tree, target, rules_dir)
    assert (target / "notes.txt").read_text(encoding="utf-8") == "keep me\n"


def test_the_expanded_tree_loads_through_load_fold(tree, rules_dir, tmp_path):
    target = tmp_path / "expanded"
    run_tree(tree, target, rules_dir)
    paths = [target / f"{SIGNAL}.fold0.{split}.jsonl" for split in ("train", "val", "test")]
    fold = dataset.load_fold(*paths)
    assert fold.fold_index == 0
    assert fold.train.stats["expansion"]["requested"]["rate"] == 0.5


def test_two_runs_write_byte_identical_files(tree, rules_dir, tmp_path):
    first, second = tmp_path / "one", tmp_path / "two"
    run_tree(tree, first, rules_dir)
    run_tree(tree, second, rules_dir)
    for path in sorted(first.rglob("*")):
        if path.is_file():
            assert path.read_bytes() == (second / path.relative_to(first)).read_bytes()


def test_the_expansion_block_is_the_marker_that_a_tree_is_expanded(tree, rules_dir, tmp_path):
    target = tmp_path / "expanded"
    run_tree(tree, target, rules_dir)

    path = next(target.glob("*.jsonl"))
    stats = json.loads(noise.sidecar_path(path).read_text(encoding="utf-8"))
    block = stats["expansion"]
    assert block["requested"]["rules"]["signal"] == SIGNAL
    assert len(block["requested"]["rules"]["sha256"]) == 64
    assert block["requested"]["rules"]["count"] == 2
    assert set(block["realised"]["substitutions_per_hundred_words"]["by_label"]) == set(
        noise.LABELS
    )
    assert set(block["realised"]["substitutions_per_hundred_words"]["by_label_mode"]) == set(
        noise.LABEL_MODES
    )
    assert "fragments" in stats
    assert stats["generator_version"] == "7"

    with pytest.raises(ExpansionError, match="already carries an 'expansion' block"):
        expand.expand_tree(
            target,
            tmp_path / "again",
            rate=0.5,
            rules_dir=rules_dir,
            root=tmp_path,
        )


def test_a_noisy_tree_is_refused(tree, rules_dir, tmp_path):
    """DD9: two passes that both multiply surface forms are unattributable."""
    for path in tree.glob("*.jsonl"):
        sidecar = noise.sidecar_path(path)
        stats = json.loads(sidecar.read_text(encoding="utf-8"))
        stats["noise"] = {"seed": 1}
        sidecar.write_text(json.dumps(stats), encoding="utf-8")
    with pytest.raises(ExpansionError, match="carries a 'noise' block"):
        run_tree(tree, tmp_path / "expanded", rules_dir)


def test_a_signal_with_no_rule_file_is_refused(tree, tmp_path):
    empty = tmp_path / "no-rules"
    empty.mkdir()
    with pytest.raises(ExpansionError, match="no rule file at"):
        run_tree(tree, tmp_path / "expanded", empty)


def test_sidecars_that_disagree_on_the_fold_configuration_are_refused(rules_dir, tmp_path):
    source = tmp_path / "clean"
    write_tree(source, splits=("train", "val"))
    write_tree(source, splits=("test",), split_salt="9")
    with pytest.raises(ExpansionError, match="disagree on 'split_salt'"):
        run_tree(source, tmp_path / "expanded", rules_dir)


def test_an_empty_input_tree_is_refused(rules_dir, tmp_path):
    source = tmp_path / "clean"
    source.mkdir()
    with pytest.raises(ExpansionError, match="no \\*.jsonl files"):
        run_tree(source, tmp_path / "expanded", rules_dir)


def test_a_dataset_with_no_sidecar_is_refused(rules_dir, tmp_path):
    source = tmp_path / "clean"
    write_tree(source, with_sidecar=False)
    with pytest.raises(ExpansionError, match="no stats sidecar"):
        run_tree(source, tmp_path / "expanded", rules_dir)


def test_an_output_dir_that_is_the_input_dir_is_refused(tree, rules_dir):
    with pytest.raises(ExpansionError, match="never .* in place"):
        run_tree(tree, tree, rules_dir)


@pytest.mark.parametrize("nested", ["inside", "outside"])
def test_nested_input_and_output_directories_are_refused(tree, rules_dir, tmp_path, nested):
    target = tree / "child" if nested == "inside" else tree.parent
    with pytest.raises(ExpansionError, match="nested|outside"):
        run_tree(tree, target, rules_dir)


def test_a_directory_outside_the_generated_root_is_refused(tree, rules_dir, tmp_path):
    with pytest.raises(ExpansionError, match="resolves outside"):
        run_tree(tree, tmp_path / "expanded", rules_dir, root=tmp_path / "elsewhere")


def test_a_non_empty_output_dir_needs_force(tree, rules_dir, tmp_path):
    target = tmp_path / "expanded"
    target.mkdir()
    (target / "already-here.txt").write_text("x", encoding="utf-8")
    with pytest.raises(ExpansionError, match="not empty"):
        run_tree(tree, target, rules_dir)
    run_tree(tree, target, rules_dir, force=True)


def test_the_clean_share_leaves_examples_untouched(tree, rules_dir, tmp_path):
    target = tmp_path / "expanded"
    tally = run_tree(tree, target, rules_dir, rate=1.0, clean_share=DEFAULT_CLEAN_SHARE)
    assert 0 < tally.overall_clean_share < 1
    assert tally.changed < sum(tally.examples.values())


# ---------------------------------------------------------------------------
# The dry run against the library lint (Task 4)
# ---------------------------------------------------------------------------

#: A filler line carrying a flank-pain *anchor* and no modifier, so it is silent
#: on flank pain as committed. It is the whole of the aggregate case: a rule can
#: supply the missing modifier without carrying an anchor itself, which means it
#: passes the per-rule load check (DD6 layer 3) and manufactures the hit anyway.
BACK_LINE = "My back has been playing up since the weekend"

FILLER_LINES = [
    BACK_LINE,
    "I have been meaning to call about the appointment",
    "Work has been busy and I have not had a moment",
    "The pharmacy said to ring you instead",
    "I am usually fit and well otherwise",
    "Nothing else has changed at home",
]


def write_manifest(base, lines=None):
    """Write a one-filler-library manifest and return its path."""
    library = FILLER_LINES if lines is None else lines
    (base / "filler_admin.txt").write_text("\n".join(library) + "\n", encoding="utf-8")
    path = base / "manifest.json"
    path.write_text(
        json.dumps(
            {
                "version": 1,
                "libraries": [
                    {
                        "name": "filler_admin",
                        "file": "filler_admin.txt",
                        "signal_key": None,
                        "fragment_type": "filler",
                        "null_on": {SIGNAL: {"basis": "absent"}},
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    return path


def ruleset(*raw_rules, signal=SIGNAL):
    """A :class:`RuleSet` built in memory, so the dry run needs no rule file."""
    _, rules = parse_rules({"signal": signal, "rules": list(raw_rules)}, source="<test>")
    return expand.RuleSet(signal=signal, path=Path("<test>"), digest="0" * 64, rules=rules)


HARMLESS = rule(
    id="playing-up-to-grumbling",
    tier="A",
    find="playing up",
    replace="grumbling on",
    invariant="Both say the complaint continues; neither names a symptom.",
)

MANUFACTURES_A_HIT = rule(
    id="playing-up-to-aching",
    tier="A",
    find="playing up",
    replace="aching",
    invariant="Wrong, and that is the point: 'aching' is a flank-pain modifier.",
)


def test_a_rule_that_manufactures_a_foreign_signal_hit_fails(tmp_path):
    """The aggregate fault no per-rule check can see (DD6 layer 3's supplement).

    ``playing up -> aching`` passes the load check, because "aching" on its own
    carries a modifier and no anchor and so matches no lexicon. Applied to a
    line that already says "back", it completes the co-occurrence.
    """
    assert load(MANUFACTURES_A_HIT), "the rule must pass the per-rule load check"

    diff = expand.dry_run_lint(write_manifest(tmp_path), [ruleset(MANUFACTURES_A_HIT)])

    assert diff.failed
    assert len(diff.introduced) == 2, "once for filler purity, once for the cross-signal grid"
    reports = {change.report for change in diff.introduced}
    assert reports == {"filler", "cross-signal"}
    for change in diff.introduced:
        assert change.variant == "playing-up-to-aching"
        assert change.library == "filler_admin"
        assert change.signal == "flank_pain_present"
        assert "aching" in change.after
    assert not diff.removed

    rendered = "\n".join(expand.render_dry_run(diff))
    assert "FAIL" in rendered
    assert "playing-up-to-aching" in rendered
    assert "flank_pain_present" in rendered
    assert BACK_LINE in rendered


def test_a_rule_set_that_changes_nothing_passes_with_an_empty_diff(tmp_path):
    diff = expand.dry_run_lint(write_manifest(tmp_path), [ruleset(HARMLESS)])

    assert not diff.failed
    assert diff.introduced == ()
    assert diff.removed == ()
    assert diff.fragments == len(FILLER_LINES)
    assert diff.rewritten == 1
    assert "PASS" in "\n".join(expand.render_dry_run(diff))


def test_a_rule_that_removes_an_existing_hit_is_reported_and_is_not_a_failure(tmp_path):
    """An existing hit is a labelling decision somebody made (instruction 5)."""
    manifest = write_manifest(tmp_path, [*FILLER_LINES, "My side has been aching all week"])
    diff = expand.dry_run_lint(
        manifest,
        [
            ruleset(
                rule(
                    id="aching-to-quiet",
                    tier="A",
                    find="aching",
                    replace="carrying on",
                    invariant="Test-only.",
                )
            )
        ],
    )

    assert not diff.failed
    assert {change.signal for change in diff.removed} == {"flank_pain_present"}
    assert "REMOVED hits (2)" in "\n".join(expand.render_dry_run(diff))


def test_the_combined_variant_catches_what_no_single_rule_does(tmp_path):
    """Two individually harmless rules that together complete a lexicon."""
    manifest = write_manifest(tmp_path, [*FILLER_LINES, "My shoulder is settling down nicely"])
    rules = ruleset(
        rule(
            id="shoulder-to-loin",
            tier="B",
            find="shoulder",
            replace="loin",
            invariant="Test-only: supplies a flank-pain anchor and no modifier.",
        ),
        rule(
            id="settling-to-sore",
            tier="A",
            find="settling down",
            replace="sore",
            invariant="Test-only: supplies a pain modifier and no anchor.",
        ),
    )

    diff = expand.dry_run_lint(manifest, [rules])

    assert diff.failed
    assert {change.variant for change in diff.introduced} == {expand.COMBINED}


def test_the_dry_run_writes_nothing(tmp_path):
    manifest = write_manifest(tmp_path)
    before = {path: path.stat().st_mtime_ns for path in sorted(tmp_path.rglob("*"))}

    expand.dry_run_lint(manifest, [ruleset(MANUFACTURES_A_HIT)])

    assert {path: path.stat().st_mtime_ns for path in sorted(tmp_path.rglob("*"))} == before


def test_every_rule_is_applied_unconditionally_rather_than_at_a_rate(tmp_path):
    """Instruction 2: the worst case is what a dry run wants to check."""
    text = "a fever, a fever, a fever"
    assert expand.rewrite_exhaustively(text, load(rule())) == (
        "a temperature, a temperature, a temperature"
    )


def test_the_dry_run_exits_nonzero_on_a_manufactured_hit(tmp_path, capsys):
    manifest = write_manifest(tmp_path)
    rules_dir = tmp_path / "rules"
    rules_dir.mkdir()
    (rules_dir / f"{SIGNAL}.rules.json").write_text(
        json.dumps({"signal": SIGNAL, "rules": [MANUFACTURES_A_HIT]}), encoding="utf-8"
    )

    code = expand.main(
        ["--dry-run-lint", "--manifest", str(manifest), "--rules-dir", str(rules_dir)]
    )

    assert code == 1
    assert "FAIL" in capsys.readouterr().out


def test_the_dry_run_needs_no_tree_but_expanding_still_does(capsys):
    with pytest.raises(SystemExit):
        expand.main([])
    assert "--in-dir" in capsys.readouterr().err

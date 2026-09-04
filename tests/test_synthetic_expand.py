"""Unit tests for the lexical variant expansion pass.

Pure unit tests on fixed strings and hand-built trees -- no manifest, no
ruleset, no fold tree from the generator, no database -- so there is no
``pytestmark``. That the pass is testable this way is the point of it being
post-processing rather than a generator flag (``arch_training.md`` 12.6 and
12.10, DD1).

The rule-validation tests are the important half. Every one of them describes a
rule that would otherwise produce a tree that looks fine, trains fine, and
carries text that no longer matches its label -- the failure section 2 exists to
prevent, arriving through the one pass that edits text after the label is fixed.
"""

import json
import random

import pytest

from scripts.synthetic_data import expand
from scripts.synthetic_data.expand import (
    DEFAULT_CLEAN_SHARE,
    ExpandError,
    apply_case,
    compile_rule,
    expand_text,
    find_sites,
    load_rules,
    parse_rules,
    structural_sequence,
)

SIGNAL = "fever_present"


def rule(**overrides):
    """One valid Tier B rule, with ``overrides`` applied."""
    payload = {
        "id": "fever-to-temperature",
        "tier": "B",
        "find": "a fever",
        "replace": "a temperature",
        "invariant": "Both are bare noun phrases naming the same state; changes neither "
        "tense, person, certainty nor polarity.",
    }
    payload.update(overrides)
    return payload


def compiled(**overrides):
    return compile_rule(rule(**overrides), signal=SIGNAL)


def rewrite(text, rules, *, rate=1.0, seed=0):
    return expand_text(text, rules, random.Random(seed), rate)[0]


# ---------------------------------------------------------------------------
# The rule format
# ---------------------------------------------------------------------------


def test_a_valid_rule_compiles():
    compiled_rule = compiled()
    assert compiled_rule.find == "a fever"
    assert compiled_rule.replace == "a temperature"
    assert compiled_rule.weight == expand.DEFAULT_WEIGHT


def test_an_unknown_key_is_an_error_not_a_comment():
    """The key set is closed for the reason ``_NULL_ON_KEYS`` is.

    A typo in an optional key is otherwise a silently ignored instruction, and
    here the ignored instruction could be the one bounding a substitution.
    """
    with pytest.raises(ExpandError, match="unknown key"):
        compiled(note="this is a comment")


@pytest.mark.parametrize("missing", sorted(expand.REQUIRED_RULE_KEYS - {"id"}))
def test_a_missing_required_key_is_an_error(missing):
    payload = rule()
    del payload[missing]
    with pytest.raises(ExpandError, match="missing required key"):
        compile_rule(payload, signal=SIGNAL)


def test_an_empty_invariant_is_refused():
    """The invariant is the only layer catching a referent change, so it is
    required to actually say something."""
    with pytest.raises(ExpandError, match="'invariant' is empty"):
        compiled(invariant="   ")


def test_an_unknown_tier_is_refused():
    with pytest.raises(ExpandError, match="tier 'C' is not one of"):
        compiled(tier="C")


@pytest.mark.parametrize("weight", [0, -1, "1.0", True])
def test_a_bad_weight_is_refused(weight):
    with pytest.raises(ExpandError, match="'weight'"):
        compiled(weight=weight)


def test_a_rule_that_changes_nothing_is_refused():
    with pytest.raises(ExpandError, match="identical"):
        compiled(replace="a fever")


def test_duplicate_rule_ids_are_refused():
    with pytest.raises(ExpandError, match="twice"):
        parse_rules(
            {
                "signal": SIGNAL,
                "rules": [rule(), rule(find="the fever", replace="the temperature")],
            },
            source="<test>",
            digest="d",
        )


def test_an_unknown_signal_is_refused():
    with pytest.raises(ExpandError, match="no lexicon"):
        parse_rules({"signal": "not_a_signal", "rules": [rule()]}, source="<test>", digest="d")


def test_a_file_with_no_rules_is_refused():
    with pytest.raises(ExpandError, match="declares no rules"):
        parse_rules({"signal": SIGNAL, "rules": []}, source="<test>", digest="d")


def test_load_rules_digests_the_file(tmp_path):
    path = tmp_path / f"{SIGNAL}.rules.json"
    path.write_text(json.dumps({"signal": SIGNAL, "rules": [rule()]}), encoding="utf-8")
    loaded = load_rules(path)
    assert loaded.signal == SIGNAL
    assert len(loaded) == 1
    assert len(loaded.digest) == 64

    path.write_text(json.dumps({"signal": SIGNAL, "rules": [rule(weight=2.0)]}), encoding="utf-8")
    assert load_rules(path).digest != loaded.digest


# ---------------------------------------------------------------------------
# DD6: the three layers, each with its own message
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "find, replace",
    [
        ("", "a temperature"),
        ("a fever", ""),
        (" a fever", "a temperature"),
        ("a fever ", "a temperature"),
        ("-fever", "a temperature"),
        ("a fever,", "a temperature"),
    ],
)
def test_a_rule_that_cannot_be_anchored_whole_word_is_refused(find, replace):
    """Section 8 records why whole-word matters: "hot" is inside ``photos``."""
    with pytest.raises(ExpandError, match="whole-word matchability"):
        compiled(find=find, replace=replace)


@pytest.mark.parametrize(
    "find, replace, why",
    [
        ("no fever", "a fever", "drops a negation"),
        ("a fever", "no fever", "inserts a negation"),
        ("my fever", "a fever", "drops a person marker"),
        ("I had a fever", "I have a fever", "changes tense"),
        ("maybe a fever", "a fever", "drops a hedge"),
    ],
)
def test_layer_2_refuses_a_rule_that_moves_a_structural_token(find, replace, why):
    with pytest.raises(ExpandError, match="DD6 layer 2"):
        compiled(find=find, replace=replace)


def test_layer_2_allows_a_contraction_pair():
    """Tier A's whole purpose. ``haven't`` folds to one frozen token and
    ``have not`` to two, so without contraction normalisation the layer that
    catches a *dropped* negation would reject the pass's safest rule."""
    assert structural_sequence("haven't") == structural_sequence("have not")
    assert compiled(tier="A", find="I've", replace="I have").tier == "A"


def test_layer_3_refuses_a_rule_that_changes_its_own_signals_match_status():
    with pytest.raises(ExpandError, match=r"DD6 layer 3.*fever_present"):
        compiled(replace="a headache")


def test_layer_3_refuses_a_rule_that_introduces_another_signals_language():
    """The one thing the provisional plan's "re-run the lint over the expanded
    tree" was for, caught per-rule instead."""
    with pytest.raises(ExpandError, match=r"DD6 layer 3.*dysuria_present"):
        compiled(replace="a fever and burning when passing urine")


def test_the_three_layers_give_distinguishable_messages():
    """A rule file is authored by hand and these messages are the whole of that
    person's feedback loop, so each layer has to name itself."""
    messages = []
    for overrides in (
        {"find": "-fever"},
        {"find": "no fever", "replace": "a fever"},
        {"replace": "a headache"},
    ):
        with pytest.raises(ExpandError) as caught:
            compiled(**overrides)
        messages.append(str(caught.value))
    assert len({message.split(":")[0] for message in messages}) == 3
    assert all("fever-to-temperature" in message for message in messages)


# ---------------------------------------------------------------------------
# The pass
# ---------------------------------------------------------------------------


def test_matching_is_whole_word_only():
    """Section 8 records the trap: "hot" is inside ``lithotripsy``, ``photos``, ``shot``."""
    rules = [compiled(id="hot", find="hot", replace="burning up")]
    text = "Photos after lithotripsy, one shot, and I feel hot."
    assert rewrite(text, rules) == "Photos after lithotripsy, one shot, and I feel burning up."


def test_the_longest_match_at_a_position_wins():
    """So an author can write the specific rule and the general one, and get the
    specific one where it applies (DD3)."""
    rules = [
        compiled(id="long", find="a high temperature", replace="a fever"),
        compiled(id="short", find="temperature", replace="fever"),
    ]
    sites, overlapping = find_sites("I had a high temperature", rules)
    assert [site.candidates[0].id for site in sites] == ["long"]
    assert overlapping == 1
    assert rewrite("I had a high temperature", rules) == "I had a fever"


def test_sites_do_not_overlap_and_are_taken_left_to_right():
    rules = [compiled(id="t", find="temperature", replace="fever")]
    text = "my temperature and her temperature"
    sites, _ = find_sites(text, rules)
    assert [(site.start, site.end) for site in sites] == [(3, 14), (23, 34)]
    assert rewrite(text, rules) == "my fever and her fever"


def test_matching_is_case_insensitive_and_output_is_not():
    """A rule written lower-case must not lowercase a sentence opener."""
    rules = [compiled()]
    assert rewrite("A fever since Tuesday.", rules) == "A temperature since Tuesday."
    assert rewrite("I had a fever.", rules) == "I had a temperature."


@pytest.mark.parametrize(
    "source, replacement, expected",
    [("A fever", "a temperature", "A temperature"), ("a fever", "a temperature", "a temperature")],
)
def test_apply_case_carries_only_the_leading_capital(source, replacement, expected):
    assert apply_case(source, replacement) == expected


def test_the_rate_is_drawn_per_site():
    """At rate 1 every site fires; at rate 0-ish none does. The point of a
    per-site draw is that one example can be partly rewritten."""
    rules = [compiled(id="t", find="temperature", replace="fever")]
    text = " ".join(["my temperature"] * 40)
    assert rewrite(text, rules, rate=1.0).count("fever") == 40
    assert rewrite(text, rules, rate=0.01).count("fever") <= 3


def test_a_weighted_choice_among_rules_matching_the_same_span():
    rules = [
        compiled(id="to-temperature", find="a fever", replace="a temperature"),
        compiled(id="to-hot", find="a fever", replace="a hot spell", weight=3.0),
    ]
    outputs = {rewrite("I had a fever", rules, seed=seed) for seed in range(60)}
    assert outputs == {"I had a temperature", "I had a hot spell"}


def test_the_same_text_rules_and_seed_give_the_same_bytes():
    rules = [compiled(id="t", find="temperature", replace="fever")]
    text = " ".join(["a high temperature"] * 20)
    first = rewrite(text, rules, rate=0.5, seed=7)
    assert first == rewrite(text, rules, rate=0.5, seed=7)
    assert first != rewrite(text, rules, rate=0.5, seed=8)


def test_text_with_no_match_is_returned_unchanged():
    text = "Nothing here about the symptom at all."
    assert rewrite(text, [compiled()]) == text


# ---------------------------------------------------------------------------
# The directory pass
# ---------------------------------------------------------------------------

MODE_LABELS = {
    "true": True,
    "false": False,
    "null_structural": None,
    "null_ambiguous": None,
}

MODE_TEXTS = {
    "true": "I had a fever since Tuesday and it has not settled.",
    "false": "I had a fever check and it was normal, so no fever at all.",
    "null_structural": "I had a fever last year but nothing since then.",
    "null_ambiguous": "My son had a fever, though I have been fine myself.",
}


def write_split(
    directory,
    *,
    split="train",
    count=12,
    signal=SIGNAL,
    fold_index=0,
    folds=5,
    split_salt="0",
    stats_overrides=None,
    with_sidecar=True,
    label_shift=0,
):
    """Write one split's JSONL and sidecar into ``directory``.

    ``label_shift`` rotates which label each text is written beside, without
    touching the text: the lever the label-blindness test pulls.
    """
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{signal}.fold{fold_index}.{split}.jsonl"
    modes = list(MODE_TEXTS)
    records = []
    for index in range(count):
        mode = modes[index % len(modes)]
        labelled = modes[(index + label_shift) % len(modes)]
        records.append(
            {
                "example_id": f"{signal}-{split}-{index:05d}",
                "split": split,
                "text": MODE_TEXTS[mode],
                "labels": {signal: MODE_LABELS[labelled]},
                "meta": {
                    "label_mode": labelled,
                    "filler_only": labelled == "null_structural",
                    "fragment_ids": [f"{split}-{index}-a", f"{split}-{index}-b"],
                    "seed": 1,
                    "generator_version": "7",
                },
            }
        )
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")

    if with_sidecar:
        stats = {
            "generator_version": "7",
            "seed": 1,
            "signal": signal,
            "split": split,
            "folds": folds,
            "fold_index": fold_index,
            "split_salt": split_salt,
            "requested": {"count": count},
            "realised": {"count": len(records)},
            "token_counts": {
                "by_label": {label: {"count": 0} for label in ("true", "false", "null")},
                "by_label_mode": {mode: {"count": 0} for mode in MODE_TEXTS},
                "by_fragment_count": {"2": {"count": len(records)}},
            },
        }
        stats.update(stats_overrides or {})
        expand.sidecar_path(path).write_text(
            json.dumps(stats, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
    return path


def write_rules(directory, *, signal=SIGNAL, rules=None):
    directory.mkdir(parents=True, exist_ok=True)
    payload = {
        "signal": signal,
        "rules": rules
        if rules is not None
        else [
            rule(),
            rule(id="fever-to-hot", find="a fever", replace="a hot spell"),
            rule(id="contraction", tier="A", find="I have", replace="I've"),
        ],
    }
    path = directory / f"{signal}.rules.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return directory


@pytest.fixture
def tree(tmp_path):
    source = tmp_path / "generated" / "clean"
    write_split(source, split="train")
    write_split(source, split="val", count=8)
    return source


@pytest.fixture
def rules_dir(tmp_path):
    return write_rules(tmp_path / "expansion")


def run_tree(source, target, *, rules_dir, rate=1.0, root=None, **kwargs):
    """``expand_tree`` with the generated-root guard pointed at the tmp tree."""
    return expand.expand_tree(
        source,
        target,
        rate=rate,
        rules_dir=rules_dir,
        root=source.parent if root is None else root,
        **kwargs,
    )


def read_records(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def test_only_text_changes_between_the_clean_and_expanded_trees(tree, rules_dir, tmp_path):
    """The pairing the whole architecture rests on: same ids, same labels, same
    provenance, so the decision metric is a paired statistic (DD1)."""
    target = tmp_path / "generated" / "expanded"
    run_tree(tree, target, rules_dir=rules_dir, clean_share=0.0)

    for source_path in sorted(tree.glob("*.jsonl")):
        before = read_records(source_path)
        after = read_records(target / source_path.name)
        assert len(before) == len(after)
        for old, new in zip(before, after, strict=True):
            for key in ("example_id", "split", "labels", "meta"):
                assert old[key] == new[key]
            assert list(new) == list(expand.RECORD_KEYS)
        assert [record["text"] for record in before] != [record["text"] for record in after]


def test_the_tree_is_deterministic(tree, rules_dir, tmp_path):
    first = tmp_path / "generated" / "one"
    second = tmp_path / "generated" / "two"
    run_tree(tree, first, rules_dir=rules_dir, rate=0.5, seed=11)
    run_tree(tree, second, rules_dir=rules_dir, rate=0.5, seed=11)
    for path in sorted(first.glob("*.jsonl")):
        assert path.read_bytes() == (second / path.name).read_bytes()

    third = tmp_path / "generated" / "three"
    run_tree(tree, third, rules_dir=rules_dir, rate=0.5, seed=12)
    assert any(
        path.read_bytes() != (third / path.name).read_bytes()
        for path in sorted(first.glob("*.jsonl"))
    )


def test_the_pass_cannot_see_the_label(tree, rules_dir, tmp_path):
    """DD5 as a property rather than a discipline.

    Two trees carrying identical text under rotated labels must produce
    identical text out. If the selection path ever learned to read ``labels`` or
    ``meta`` this is the test that fails.
    """
    shifted = tmp_path / "generated" / "shifted"
    write_split(shifted, split="train", label_shift=2)
    write_split(shifted, split="val", count=8, label_shift=2)

    straight_out = tmp_path / "generated" / "straight-out"
    shifted_out = tmp_path / "generated" / "shifted-out"
    run_tree(tree, straight_out, rules_dir=rules_dir, rate=0.5, clean_share=DEFAULT_CLEAN_SHARE)
    run_tree(shifted, shifted_out, rules_dir=rules_dir, rate=0.5, clean_share=DEFAULT_CLEAN_SHARE)

    for path in sorted(straight_out.glob("*.jsonl")):
        straight = [record["text"] for record in read_records(path)]
        rotated = [record["text"] for record in read_records(shifted_out / path.name)]
        assert straight == rotated


def test_the_sidecar_reports_substitutions_by_label_and_label_mode(tree, rules_dir, tmp_path):
    target = tmp_path / "generated" / "expanded"
    run_tree(tree, target, rules_dir=rules_dir, clean_share=0.0)

    stats = json.loads(
        expand.sidecar_path(target / f"{SIGNAL}.fold0.train.jsonl").read_text(encoding="utf-8")
    )
    block = stats["expansion"]
    assert block["requested"]["rate"] == 1.0
    assert block["requested"]["rules"]["signal"] == SIGNAL
    assert len(block["requested"]["rules"]["digest"]) == 64

    realised = block["realised"]["substitutions_per_hundred_words"]
    assert set(realised["by_label"]) == {"true", "false", "null"}
    assert set(realised["by_label_mode"]) == set(MODE_TEXTS)
    assert realised["overall"] > 0
    assert block["realised"]["clean_share"]["overall"] == 0.0
    assert sum(block["realised"]["rules"].values()) == block["realised"]["sites"]["applied"]
    # Passed through untouched: the fragments were not edited.
    assert stats["generator_version"] == "7"
    assert stats["fold_index"] == 0


def test_the_clean_share_leaves_examples_untouched(tree, rules_dir, tmp_path):
    target = tmp_path / "generated" / "expanded"
    tally = run_tree(tree, target, rules_dir=rules_dir, clean_share=0.5)
    assert 0 < tally.overall_clean_share < 1


def test_files_that_are_neither_dataset_nor_sidecar_are_copied_through(tree, rules_dir, tmp_path):
    (tree / "notes.txt").write_text("keep me\n", encoding="utf-8")
    target = tmp_path / "generated" / "expanded"
    run_tree(tree, target, rules_dir=rules_dir)
    assert (target / "notes.txt").read_text(encoding="utf-8") == "keep me\n"


# ---------------------------------------------------------------------------
# The guards. Every one of these fails silently if it is not a startup error.
# ---------------------------------------------------------------------------


def test_an_output_dir_that_is_the_input_dir_is_refused(tree, rules_dir):
    with pytest.raises(ExpandError, match="in place"):
        run_tree(tree, tree, rules_dir=rules_dir)


@pytest.mark.parametrize("nested", ["child", "parent"])
def test_nested_input_and_output_directories_are_refused(tree, rules_dir, nested):
    target = tree / "inside" if nested == "child" else tree.parent
    with pytest.raises(ExpandError, match="nested"):
        run_tree(tree, target, rules_dir=rules_dir)


def test_a_directory_outside_the_generated_root_is_refused(tree, rules_dir, tmp_path):
    with pytest.raises(ExpandError, match="resolves outside"):
        # The real root, which no tmp path can be inside.
        expand.expand_tree(tree, tmp_path / "elsewhere", rate=1.0, rules_dir=rules_dir)


def test_a_non_empty_output_dir_needs_force(tree, rules_dir, tmp_path):
    target = tmp_path / "generated" / "expanded"
    target.mkdir(parents=True)
    (target / "leftover.jsonl").write_text("{}\n", encoding="utf-8")
    with pytest.raises(ExpandError, match="is not empty"):
        run_tree(tree, target, rules_dir=rules_dir)
    run_tree(tree, target, rules_dir=rules_dir, force=True)
    assert (target / f"{SIGNAL}.fold0.train.jsonl").is_file()


def test_an_already_expanded_tree_is_refused(tree, rules_dir, tmp_path):
    """Expanding twice compounds the substitutions in a way no rate describes."""
    target = tmp_path / "generated" / "expanded"
    run_tree(tree, target, rules_dir=rules_dir)
    again = tmp_path / "generated" / "again"
    with pytest.raises(ExpandError, match="already carries an 'expansion' block"):
        run_tree(target, again, rules_dir=rules_dir, root=tree.parent)


def test_a_noised_tree_is_refused(tree, rules_dir, tmp_path):
    """DD9: both passes multiply surface forms, so one experiment carrying both
    is unattributable."""
    source = tmp_path / "generated" / "noisy"
    write_split(source, split="train", stats_overrides={"noise": {"seed": 1}})
    with pytest.raises(ExpandError, match="carries a 'noise' block"):
        run_tree(source, tmp_path / "generated" / "out", rules_dir=rules_dir, root=source.parent)


def test_a_signal_with_no_rule_file_is_refused(tree, tmp_path):
    """The dangerous one: the pass would run, write an identical tree, and the
    experiment would compare a tree against itself."""
    empty = tmp_path / "no-rules"
    empty.mkdir()
    with pytest.raises(ExpandError, match="no rule file"):
        run_tree(tree, tmp_path / "generated" / "out", rules_dir=empty)


def test_sidecars_that_disagree_on_the_fold_configuration_are_refused(tree, rules_dir, tmp_path):
    write_split(tree, split="train", fold_index=1, split_salt="9")
    with pytest.raises(ExpandError, match="disagree on 'split_salt'"):
        run_tree(tree, tmp_path / "generated" / "out", rules_dir=rules_dir)


def test_a_dataset_with_no_sidecar_is_refused(tree, rules_dir, tmp_path):
    write_split(tree, split="train", fold_index=2, with_sidecar=False)
    with pytest.raises(ExpandError, match="no stats sidecar"):
        run_tree(tree, tmp_path / "generated" / "out", rules_dir=rules_dir)


def test_an_empty_tree_is_refused(rules_dir, tmp_path):
    source = tmp_path / "generated" / "empty"
    source.mkdir(parents=True)
    with pytest.raises(ExpandError, match="no \\*.jsonl files"):
        run_tree(source, tmp_path / "generated" / "out", rules_dir=rules_dir)


# ---------------------------------------------------------------------------
# The CLI
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("rate", ["0", "1.5", "-0.1"])
def test_the_cli_refuses_a_rate_outside_the_open_unit_interval(rate):
    with pytest.raises(SystemExit):
        expand.build_parser().parse_args(["--in-dir", "a", "--out-dir", "b", "--rate", rate])


def test_the_cli_reports_a_refused_tree_as_an_error(tree, rules_dir, capsys):
    code = expand.main(
        [
            "--in-dir",
            str(tree),
            "--out-dir",
            str(tree),
            "--rate",
            "1.0",
            "--rules-dir",
            str(rules_dir),
        ]
    )
    assert code == 2
    assert "error:" in capsys.readouterr().err

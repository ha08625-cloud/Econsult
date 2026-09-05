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

import hashlib
import json
import random
import re
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
    load_classes,
    load_rules,
    match_sites,
    parse_classes,
    parse_rules,
    structural_sequence,
)
from scripts.synthetic_data.manifest import load_fragments
from scripts.synthetic_data.normalise import normalise
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


# ---------------------------------------------------------------------------
# Layer 2's person-class relaxation, and the fact that it is gated (DD6a, F3)
# ---------------------------------------------------------------------------


def generated(find, replace, origin="referent/adult_female"):
    """A rule as the swap-class loader would build it: ``origin`` set."""
    return expand.Rule(
        id=f"{origin}:{find}->{replace}",
        tier="B",
        find=find,
        replace=replace,
        invariant="Both members name a third party, and the class declares it.",
        origin=origin,
    )


@pytest.mark.parametrize(
    ("find", "replace"),
    [
        ("mum", "sister"),  # both frozen today; both <third-party> now
        ("partner", "flatmate"),  # frozen -> unfrozen, the 57% DD6a unlocks
        ("son", "boy"),  # the gendered child sub-classes, empty before DD6a
        ("daughter", "girl"),
        ("my wife", "my sister"),  # the possessive survives on both sides
        ("kid", "little one"),  # a multi-word member is one marker, not two
    ],
)
def test_layer_two_allows_a_person_class_swap_for_a_generated_rule(find, replace):
    expand._check_structural(generated(find, replace))


@pytest.mark.parametrize(
    ("find", "replace"),
    [
        ("mum", "I"),  # third party -> speaker: the null axis moves
        ("my wife", "I"),
        ("sister", "my sister"),  # gains a person marker
        ("mum", "my mum"),
        ("sister", "nurse"),  # a clinician is not whose symptom this is
        ("sister", "tomorrow"),  # and neither is a day
    ],
)
def test_layer_two_still_refuses_a_generated_rule_that_moves_the_person(find, replace):
    with pytest.raises(ExpansionError, match="structural-token invariance"):
        expand._check_structural(generated(find, replace))


def test_an_unmapped_member_fails_closed():
    """DD6a's whole argument for a *total* map.

    A referent normalises to a marker, so a word that is not in
    :data:`PERSON_CLASSES` normalises to nothing and every pair touching it is
    refused. With a partial map both sides would be ``()`` and the pair would
    load.
    """
    assert structural_sequence("sister", person_classes=True) == (noise.THIRD_PARTY,)
    assert structural_sequence("plumber", person_classes=True) == ()
    with pytest.raises(ExpansionError, match="structural-token invariance"):
        expand._check_structural(generated("sister", "plumber"))


def test_a_generated_rules_refusal_names_its_class():
    with pytest.raises(ExpansionError) as error:
        expand._check_structural(generated("mum", "I", origin="referent/adult_female"))
    assert "referent/adult_female" in str(error.value)


def test_the_relaxation_does_not_reach_a_hand_written_rule_file():
    """F3, and the whole reason DD6a is carried on the rule rather than in the check.

    ``_check_structural`` runs from ``parse_rules`` for every rule, so a
    relaxation written into the check itself would relax the signal rule files
    too. A ``*.rules.json`` file loads with ``origin is None``, so ``my mum ->
    my daughter`` -- two members of *different* referent classes, which DD4
    forbids and no class file could generate -- is still refused there.
    """
    with pytest.raises(ExpansionError, match="structural-token invariance"):
        load(rule(find="my mum", replace="my daughter"))
    assert all(one.origin is None for one in RULES)


@pytest.mark.parametrize("find,replace", [("mum", "sister"), ("partner", "flatmate")])
def test_the_pairs_dd6a_unlocks_are_refused_from_a_rule_file(find, replace):
    with pytest.raises(ExpansionError, match="structural-token invariance"):
        load(rule(find=find, replace=replace))


def test_the_default_sequence_is_unchanged():
    """The v1 arm has to reproduce 2026-09-04 byte for byte, so the default is."""
    for phrase in ("my mum", "I've had a fever", "no fever", "my son had a temperature"):
        assert structural_sequence(phrase) == structural_sequence(phrase, person_classes=False)
    assert structural_sequence("my mum") == ("my", "mum")
    assert structural_sequence("my mum", person_classes=True) == (
        noise.FIRST_PERSON,
        noise.THIRD_PARTY,
    )


def test_contractions_expand_before_the_person_map():
    """Order matters: the Tier A rules layer 2 exists to carry stay loadable."""
    assert structural_sequence("I've", person_classes=True) == (noise.FIRST_PERSON, "have")
    assert structural_sequence("I have", person_classes=True) == (noise.FIRST_PERSON, "have")
    expand._check_structural(generated("I've", "I have", origin="tier-a"))


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
# The swap-class format and its loader (DD3, DD11)
# ---------------------------------------------------------------------------

#: Long enough to clear the class floor, which is twice the rule floor.
CLASS_INVARIANT = (
    "Every member names an adult female third party, so the third-party null axis does not "
    "move whichever way the pair runs; read against 'my X was up all night with it'."
)


def swap_class(**overrides):
    """A valid class, with whatever the caller wants changed."""
    base = {
        "id": "referent.adult_female",
        "gender": "female",
        "life_stage": "adult",
        "number": "singular",
        "person": "third-party",
        "tier": "B",
        "members": ["mum", "mother", "sister"],
        "invariant": CLASS_INVARIANT,
    }
    base.update(overrides)
    return base


def load_class(*raw_classes, group="referent"):
    """Validate a class document built from ``raw_classes`` and return the set."""
    return parse_classes({"group": group, "classes": list(raw_classes)}, source="<test>")


def test_a_well_formed_class_file_loads():
    loaded = load_class(swap_class())
    assert loaded.group == "referent"
    assert [one.id for one in loaded.classes] == ["referent.adult_female"]
    assert loaded.classes[0].members == ("mum", "mother", "sister")
    assert loaded.path is None and loaded.digest is None


def test_a_class_expands_to_every_ordered_pair():
    """DD3's arithmetic: n members are n*(n-1) rules from one review."""
    rules = load_class(swap_class()).rules
    assert len(rules) == 6
    assert {(one.find, one.replace) for one in rules} == {
        (find, replace)
        for find in ("mum", "mother", "sister")
        for replace in ("mum", "mother", "sister")
        if find != replace
    }
    assert all(one.origin == "referent.adult_female" for one in rules)
    assert all(one.tier == "B" for one in rules)
    assert all(one.invariant == CLASS_INVARIANT for one in rules)
    assert all(one.weight == 1.0 for one in rules)


def test_generated_ids_are_deterministic_and_survive_a_reordered_list():
    """Two loads produce byte-identical rule order, and so do two orderings."""
    first = [one.id for one in load_class(swap_class()).rules]
    again = [one.id for one in load_class(swap_class()).rules]
    shuffled = [one.id for one in load_class(swap_class(members=["sister", "mum", "mother"])).rules]
    assert first == again == shuffled
    assert first == sorted(first)
    assert "referent.adult_female:mum->sister" in first


def test_a_multi_word_member_leaves_an_id_with_no_spaces():
    loaded = load_class(
        swap_class(
            id="referent.child_neutral_singular",
            gender="neutral",
            life_stage="child",
            members=["kid", "little one"],
            invariant=CLASS_INVARIANT,
        )
    )
    assert {one.id for one in loaded.rules} == {
        "referent.child_neutral_singular:kid->little_one",
        "referent.child_neutral_singular:little_one->kid",
    }


@pytest.mark.parametrize(
    ("overrides", "fragment"),
    [
        ({"note": "a comment"}, "unknown key"),
        ({"gender": "woman"}, "not one of female, male, neutral, none"),
        ({"life_stage": "grown"}, "not one of adult, elder, child, none"),
        ({"number": "many"}, "not one of singular, plural"),
        ({"person": "second-person"}, "not one of first-person, third-party, none"),
        ({"tier": "C"}, "not one of A, B"),
        ({"invariant": "   "}, "non-empty string"),
        ({"members": "mum"}, "must be a list"),
        ({"members": ["mum", ""]}, "non-empty string"),
        ({"members": ["mum", " sister"]}, "leading or trailing whitespace"),
        ({"members": ["mum", "(sister)"]}, "start and end on a word character"),
        ({"id": "adult_female"}, "must start with 'referent.'"),
    ],
)
def test_the_class_key_set_is_closed_and_typed(overrides, fragment):
    with pytest.raises(ExpansionError, match=re.escape(fragment)):
        load_class(swap_class(**overrides))


def test_a_missing_class_key_is_refused():
    raw = swap_class()
    del raw["person"]
    with pytest.raises(ExpansionError, match="missing required key"):
        load_class(raw)


def test_an_unknown_top_level_key_in_a_class_file_is_refused():
    with pytest.raises(ExpansionError, match="unknown top-level key"):
        parse_classes(
            {"group": "referent", "classes": [swap_class()], "notes": "hello"},
            source="<test>",
        )


def test_a_class_file_carries_no_signal():
    """DD2. A class belongs to no signal, so 'signal' is not a key it may carry."""
    assert "signal" not in expand.CLASS_KEYS
    with pytest.raises(ExpansionError, match="unknown top-level key"):
        parse_classes(
            {"group": "referent", "classes": [swap_class()], "signal": SIGNAL},
            source="<test>",
        )


def test_duplicate_class_ids_are_refused():
    with pytest.raises(ExpansionError, match="duplicate id"):
        load_class(swap_class(), swap_class(members=["aunt", "auntie"]))


def test_a_member_in_two_classes_of_a_group_is_refused():
    """DD11. A word in two classes is a swap that escapes its declared gender."""
    with pytest.raises(ExpansionError, match="already in class 'referent.adult_female'"):
        load_class(
            swap_class(),
            swap_class(
                id="referent.adult_neutral",
                gender="neutral",
                members=["partner", "sister"],
            ),
        )


def test_a_member_repeated_within_a_class_is_refused():
    with pytest.raises(ExpansionError, match="listed more than once"):
        load_class(swap_class(members=["mum", "mother", "Mum"]))


@pytest.mark.parametrize("count", [1, 13])
def test_a_class_that_is_too_small_or_too_large_is_refused(count):
    members = [f"mum{index}" for index in range(count)]
    with pytest.raises(ExpansionError, match="a class holds between 2 and 12"):
        load_class(swap_class(members=members))


def test_a_thin_invariant_is_refused():
    """One class invariant stands for dozens of rules, so the floor is doubled."""
    with pytest.raises(ExpansionError, match="the floor is 120"):
        load_class(swap_class(invariant="Both name a third party."))
    assert expand.MIN_CLASS_INVARIANT == 120


def test_a_vowel_initial_multi_word_member_is_refused():
    """Review F6: 'a other half', and no mechanical layer sees it."""
    with pytest.raises(ExpansionError, match="vowel-initial and multi-word"):
        load_class(
            swap_class(
                id="referent.adult_neutral",
                gender="neutral",
                members=["partner", "other half"],
            )
        )


def test_a_vowel_initial_single_word_member_still_loads():
    assert len(load_class(swap_class(members=["mum", "aunt"])).rules) == 2


def test_every_generated_rule_runs_layer_one():
    with pytest.raises(ExpansionError, match="start and end on a word character"):
        load_class(swap_class(members=["mum", "sister-"]))


def test_a_member_missing_from_the_person_map_is_refused_by_layer_two():
    """DD6a's total map, seen from the loader: the message names the class."""
    with pytest.raises(ExpansionError) as error:
        load_class(swap_class(members=["mum", "matriarch"]))
    message = str(error.value)
    assert "structural-token invariance" in message
    assert "referent.adult_female" in message


def test_layer_two_still_refuses_a_class_that_crosses_the_person_axis():
    with pytest.raises(ExpansionError, match="structural-token invariance"):
        load_class(swap_class(members=["mum", "my mum"]))


def test_layer_three_is_signal_agnostic_for_a_class():
    """A class belongs to no signal, so it may not move *any* signal's language.

    Neither member is a person, so layer 2 passes both as ``()`` and layer 3 is
    the only thing standing between the class and a swap that walks a decisive
    fever line into saying nothing about fever.
    """
    with pytest.raises(ExpansionError, match="moves fever_present language"):
        load_class(
            swap_class(
                id="affect.worried",
                gender="none",
                life_stage="none",
                person="none",
                members=["worried", "feverish"],
            ),
            group="affect",
        )


def test_load_classes_reports_the_path_and_a_digest(tmp_path):
    path = tmp_path / "referent.classes.json"
    path.write_text(json.dumps({"group": "referent", "classes": [swap_class()]}), encoding="utf-8")
    loaded = load_classes(path)
    assert loaded.group == "referent"
    assert loaded.path == path
    assert len(loaded.digest) == 64
    assert len(loaded.rules) == 6


def test_a_class_file_named_for_another_group_is_refused(tmp_path):
    path = tmp_path / "weekday.classes.json"
    path.write_text(json.dumps({"group": "referent", "classes": [swap_class()]}), encoding="utf-8")
    with pytest.raises(ExpansionError, match="declares group 'referent' but is named for"):
        load_classes(path)


def test_a_missing_class_file_is_refused(tmp_path):
    with pytest.raises(ExpansionError, match="no class file at"):
        load_classes(tmp_path / "absent.classes.json")


def _write_group(directory, group, *raw_classes):
    path = directory / f"{group}.classes.json"
    path.write_text(json.dumps({"group": group, "classes": list(raw_classes)}), encoding="utf-8")
    return path


def test_load_class_groups_loads_several(tmp_path):
    _write_group(tmp_path, "referent", swap_class())
    _write_group(
        tmp_path,
        "weekday",
        swap_class(
            id="weekday.working",
            gender="none",
            life_stage="none",
            person="none",
            members=["Monday", "Tuesday", "Friday"],
        ),
    )
    loaded = expand.load_class_groups(["referent", "weekday"], tmp_path)
    assert [one.group for one in loaded] == ["referent", "weekday"]
    assert sum(len(one.rules) for one in loaded) == 12


def test_a_class_id_shared_between_two_files_is_refused(tmp_path):
    """Reachable only by naming a group twice: the id prefix rule closes the rest.

    A class id must start with its file's group and a file's group must match
    its name, so two *different* groups cannot collide. The same group asked
    for twice can, and it is the mistake a hand-typed ``--class-groups`` makes.
    """
    _write_group(tmp_path, "referent", swap_class())
    with pytest.raises(ExpansionError, match="declared in both"):
        expand.load_class_groups(["referent", "referent"], tmp_path)


def test_a_member_shared_between_two_files_is_refused(tmp_path):
    _write_group(tmp_path, "referent", swap_class())
    _write_group(
        tmp_path,
        "kin",
        swap_class(id="kin.adults", members=["sister", "cousin"]),
    )
    with pytest.raises(ExpansionError, match="already in class 'referent.adult_female'"):
        expand.load_class_groups(["referent", "kin"], tmp_path)


def test_classes_live_under_the_rules_root_and_outside_the_library_tree():
    """DD11, and a glob over one format must never pick up the other."""
    assert expand.CLASSES_ROOT.is_relative_to(RULES_ROOT)
    assert not expand.CLASSES_ROOT.is_relative_to("data/synthetic")
    assert expand.classes_path("referent") == expand.CLASSES_ROOT / "referent.classes.json"


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
# Per-example memoisation and per-class injectivity (DD12, v2 review F7)
# ---------------------------------------------------------------------------

#: Four adult-female members, which is the smallest class that leaves a *choice*
#: after injectivity has excluded the two words already standing in "my wife and
#: my sister". A three-member class would make every assertion below true by
#: arithmetic rather than by the code under test.
REFERENT_CLASS = swap_class(members=["wife", "sister", "mum", "mother"])
REFERENT_RULES = load_class(REFERENT_CLASS).rules

#: The two members of one class, which is the *only* way to force a collision:
#: with one candidate per site and that candidate already spoken for, the
#: candidate list empties and the site has to be skipped.
PAIR_RULES = load_class(swap_class(members=["wife", "sister"])).rules

#: Every folded word any of the classes above could put into a text.
MEMBERS = ("wife", "sister", "mum", "mother")


def members_in(text):
    """The class members present in ``text``, in order, folded."""
    return re.findall(rf"\b(?:{'|'.join(MEMBERS)})\b", text.lower())


def test_a_repeated_referent_takes_one_decision_at_every_site():
    """DD12's first half. The rate coin fires per site and *before* the
    substitution, so memoising only the target would still let the second site
    lose its coin and leave "my sister ... my wife" in the line. The decision is
    what is memoised: three mentions of one person move together or not at all,
    and the two repeats spend no coin."""
    text = "My sister rang, my sister was up all night, and my sister is still poorly"
    for seed in range(VOLUME):
        result = expand_example(text, REFERENT_RULES, random.Random(seed), rate=0.5)
        assert len(set(members_in(result.text))) == 1
        assert result.applied in (0, 3)
        assert result.memoised == 2
        assert result.skipped["memo"] == (2 if not result.applied else 0)


def test_two_referents_never_collapse_onto_one_person():
    """DD12's second half. Keying the memo on the *source* does not stop two
    sources landing on one target: "my wife and my sister" with ``wife ->
    sister`` firing gives "my sister and my sister", which is one person where
    the line had two."""
    text = "My wife and my sister"
    seen = set()
    for seed in range(VOLUME):
        result = expand_example(text, REFERENT_RULES, random.Random(seed), rate=1.0)
        present = members_in(result.text)
        assert len(present) == 2
        assert len(set(present)) == 2
        seen.add(result.text)
    #: Not one frozen answer: injectivity narrows the draw, it does not replace it.
    assert len(seen) > 1


def test_a_member_already_in_the_source_text_is_excluded_as_a_target():
    """The half of injectivity the committed set cannot cover. Nothing has been
    substituted yet at the first site, so only the *source text* says that
    "sister" is taken."""
    text = "My wife and my sister"
    for seed in range(VOLUME):
        result = expand_example(text, REFERENT_RULES, random.Random(seed), rate=1.0)
        assert not result.text.lower().startswith("my sister ")


def test_an_emptied_candidate_list_skips_the_site_and_says_why():
    """A skipped site is telemetry, not silence: ``class_collision`` is what
    distinguishes "injectivity had nowhere to go" from "the coin came up short",
    and the two would otherwise be indistinguishable in the sidecar."""
    text = "My wife and my sister"
    for seed in range(VOLUME // 20):
        result = expand_example(text, PAIR_RULES, random.Random(seed), rate=1.0)
        assert result.text == text
        assert result.applied == 0
        assert result.skipped["class_collision"] == 2


def test_injectivity_is_scoped_to_the_class_and_not_to_the_rule_set():
    """Repeating ``temperature`` in a line is correct English and correct data;
    repeating a person is not. A hand-written rule firing twice onto the same
    replacement is therefore untouched by any of this."""
    text = "I had a fever on Monday and a fever on Tuesday"
    counts = {
        expand_example(text, RULES, random.Random(seed), rate=1.0).applied
        for seed in range(VOLUME // 20)
    }
    assert counts == {2}


def test_a_class_rule_and_a_hand_written_rule_in_one_example_do_not_share_a_memo():
    """The gate is ``origin``, so the two paths coexist inside one example: the
    referent moves as one person, and the two mentions of "a fever" still draw
    independently as DD3 requires."""
    text = "I had a fever, my sister had a fever, and my sister was fine"
    combined = (*RULES, *REFERENT_RULES)
    hand_counts = set()
    for seed in range(VOLUME):
        result = expand_example(text, combined, random.Random(seed), rate=0.5)
        hand = sum(
            count for rule_id, count in result.applications.items() if not rule_id.startswith("ref")
        )
        hand_counts.add(hand)
        assert len(set(members_in(result.text))) == 1
        assert result.memoised == 1
    assert hand_counts == {0, 1, 2}


def test_a_fever_only_rule_set_reproduces_the_pre_memo_output_byte_for_byte():
    """DD5's ``v1`` arm is the anchor against 2026-09-04, and an anchor that
    does not reproduce is not an anchor.

    The expected string below was produced by the committed rule file under the
    code as it stood *before* the memo, and is inline rather than computed so
    that a change to the substitution path has to edit it deliberately. The
    accounting either side of it matters as much as the text: no rule in a
    ``*.rules.json`` file carries an ``origin``, so every site spends its own
    coin, ``memoised`` stays at zero and no site is ever refused for a
    collision. Memoising a repeat would move the RNG stream, and the stream
    position is what makes the arm reproducible at all.
    """
    rules = load_rules(RULES_ROOT / "fever_present.rules.json").rules
    text = (
        "I've had a fever since Tuesday and I didn't sleep; my son had a temperature too, "
        "and I'm still running a temperature this morning."
    )
    result = expand_example(text, rules, random.Random(7), rate=0.6)
    assert result.text == (
        "I have had a fever since Tuesday and I did not sleep; my son had a fever too, "
        "and I am still running a fever this morning."
    )
    assert (result.sites, result.applied) == (6, 5)
    assert dict(result.skipped) == {"rate_coin": 1}
    assert result.memoised == 0

    for seed in range(VOLUME // 4):
        other = expand_example(text, rules, random.Random(seed), rate=0.6)
        assert other.memoised == 0
        assert "class_collision" not in other.skipped
        assert "memo" not in other.skipped


def test_every_site_lands_in_exactly_one_of_applied_and_skipped():
    """The three skip reasons and the applications have to add to the sites, or
    the sidecar's ``sites`` block is describing a different run."""
    text = "My wife rang about my sister, and my sister rang about my wife"
    for seed in range(VOLUME // 20):
        result = expand_example(text, REFERENT_RULES, random.Random(seed), rate=0.5)
        assert result.applied + sum(result.skipped.values()) == result.sites


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
    # Hermetic unless the caller says otherwise. An arm that names no class
    # group falls back to ``discover_class_groups()`` over the committed
    # ``data/expansion/classes``, so from Task 6 onwards a directory-pass test
    # built on a tmp tree would silently run the shipped swap classes against
    # a two-rule tmp rule file. The tests that are *about* class selection pass
    # their own ``classes_dir`` and are unaffected.
    if "classes_dir" not in kwargs and "class_groups" not in kwargs:
        empty = source.parent / "expansion-classes-empty"
        empty.mkdir(exist_ok=True)
        kwargs["classes_dir"] = empty
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
    assert block["requested"]["class_groups"] == []
    assert len(block["requested"]["rule_sources"]) == 1
    (source,) = block["requested"]["rule_sources"]
    assert source["kind"] == "rules"
    assert source["signal"] == SIGNAL
    assert len(source["sha256"]) == 64
    assert source["count"] == 2
    assert set(block["realised"]["substitutions_per_hundred_words"]["by_label"]) == set(
        noise.LABELS
    )
    assert set(block["realised"]["substitutions_per_hundred_words"]["by_label_mode"]) == set(
        noise.LABEL_MODES
    )
    # DD12. Zero here is the assertion, not a placeholder: a hand-written rule
    # file carries no ``origin``, so nothing on this run could be memoised.
    assert block["realised"]["sites"]["memoised"] == 0
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
# Arm selection: --rules and --class-groups (DD2, DD5)
# ---------------------------------------------------------------------------

#: A class whose members are neither persons nor any signal's vocabulary, so
#: every layer passes and the only thing under test is the *selection*. "kitchen"
#: is in the fixture tree's word pool, so the class actually fires.
SETTING_CLASS = swap_class(
    id="setting.rooms",
    gender="none",
    life_stage="none",
    number="singular",
    person="none",
    members=["kitchen", "hallway", "landing"],
    invariant=(
        "Every member names a room of the same house, so no member says anything about a "
        "symptom, a person or a time; read against 'I was in the X when it started'."
    ),
)


@pytest.fixture
def classes_dir(tmp_path):
    directory = tmp_path / "expansion-classes"
    directory.mkdir()
    _write_group(directory, "setting", SETTING_CLASS)
    return directory


def sidecar_expansion(target):
    """The ``expansion.requested`` block of the first sidecar in ``target``."""
    path = next(target.glob("*.jsonl"))
    stats = json.loads(noise.sidecar_path(path).read_text(encoding="utf-8"))
    return stats["expansion"]["requested"]


@pytest.mark.parametrize(
    ("rule_kinds", "class_groups", "kinds"),
    [
        ("signal", None, ["rules"]),
        ("classes", None, ["classes"]),
        ("classes", ("setting",), ["classes"]),
        ("both", None, ["rules", "classes"]),
        ("both", ("setting",), ["rules", "classes"]),
    ],
)
def test_each_arm_loads_exactly_the_rule_files_it_names(
    tree, rules_dir, classes_dir, tmp_path, rule_kinds, class_groups, kinds
):
    """DD5's five arms are a selection over files, and the sidecar says which."""
    target = tmp_path / "expanded"
    run_tree(
        tree,
        target,
        rules_dir,
        classes_dir=classes_dir,
        rule_kinds=rule_kinds,
        class_groups=class_groups,
    )

    requested = sidecar_expansion(target)
    assert [source["kind"] for source in requested["rule_sources"]] == kinds
    assert requested["class_groups"] == (["setting"] if "classes" in kinds else [])


def test_a_classes_only_arm_needs_no_rule_file_for_the_signal(tree, classes_dir, tmp_path):
    """DD2: the classes belong to no signal, so requiring one signal's rule file
    would tie a signal-agnostic pass back to the only signal that has one."""
    empty = tmp_path / "no-rules"
    empty.mkdir()
    target = tmp_path / "expanded"
    tally = run_tree(tree, target, empty, classes_dir=classes_dir, rule_kinds="classes", rate=1.0)

    assert tally.total_applied > 0
    (source,) = sidecar_expansion(target)["rule_sources"]
    assert source["kind"] == "classes" and source["signal"] is None


def test_a_selection_that_leaves_a_signal_with_no_rules_is_refused(tree, tmp_path):
    """Writing an untouched copy under a name that says "expanded" is the one
    silent no-op an arm comparison cannot see."""
    empty_rules = tmp_path / "no-rules"
    empty_rules.mkdir()
    empty_classes = tmp_path / "no-classes"
    empty_classes.mkdir()
    with pytest.raises(ExpansionError, match="no rules at all"):
        run_tree(
            tree,
            tmp_path / "expanded",
            empty_rules,
            classes_dir=empty_classes,
            rule_kinds="classes",
        )


def test_a_missing_rule_file_is_fatal_only_when_the_arm_asks_for_one(tree, classes_dir, tmp_path):
    empty = tmp_path / "no-rules"
    empty.mkdir()
    with pytest.raises(ExpansionError, match="no rule file at"):
        run_tree(tree, tmp_path / "signal-arm", empty, classes_dir=classes_dir, rule_kinds="both")
    run_tree(tree, tmp_path / "classes-arm", empty, classes_dir=classes_dir, rule_kinds="classes")


def test_a_named_class_group_with_no_file_is_refused(tree, rules_dir, classes_dir, tmp_path):
    """A named group that is not on disk is a typo, never an empty selection."""
    with pytest.raises(ExpansionError, match="no class file at"):
        run_tree(
            tree,
            tmp_path / "expanded",
            rules_dir,
            classes_dir=classes_dir,
            class_groups=("referent",),
        )


def test_the_sidecar_carries_one_entry_per_file_with_its_own_digest(
    tree, rules_dir, classes_dir, tmp_path
):
    """The digests are the only provenance that survives the concatenation."""
    target = tmp_path / "expanded"
    run_tree(tree, target, rules_dir, classes_dir=classes_dir, rule_kinds="both")

    sources = sidecar_expansion(target)["rule_sources"]
    on_disk = {
        str(rules_dir / f"{SIGNAL}.rules.json"): (rules_dir / f"{SIGNAL}.rules.json"),
        str(classes_dir / "setting.classes.json"): (classes_dir / "setting.classes.json"),
    }
    assert {source["path"] for source in sources} == set(on_disk)
    for source in sources:
        digest = hashlib.sha256(on_disk[source["path"]].read_bytes()).hexdigest()
        assert source["sha256"] == digest
        assert source["count"] > 0
    assert [source["signal"] for source in sources] == [SIGNAL, None]


def test_the_signal_arm_is_byte_identical_to_a_run_with_no_classes_on_disk(
    tree, rules_dir, classes_dir, tmp_path
):
    """DD5's ``v1`` arm is the 2026-09-04 anchor, and an anchor that does not
    reproduce is not an anchor."""
    empty = tmp_path / "no-classes"
    empty.mkdir()
    first = tmp_path / "with-classes-on-disk"
    second = tmp_path / "without"
    run_tree(tree, first, rules_dir, classes_dir=classes_dir, rule_kinds="signal")
    run_tree(tree, second, rules_dir, classes_dir=empty, rule_kinds="signal")

    for path in sorted(first.rglob("*.jsonl")):
        assert path.read_bytes() == (second / path.relative_to(first)).read_bytes()


def test_a_hand_written_rule_and_a_class_rule_compete_on_length_at_one_site():
    """Newly reachable in the ``combined`` arm, so it is worth saying explicitly:
    the two rule sources are concatenated and ``match_sites`` prefers the longest
    needle, exactly as it does between two hand-written rules."""
    hand = load(
        rule(
            id="the-kitchen",
            tier="A",
            find="the kitchen",
            replace="the hallway",
            invariant="Both name a room of the same house.",
        )
    )
    class_rules = load_class(SETTING_CLASS, group="setting").rules
    text = "I was in the kitchen"
    (site,) = match_sites(text, (*hand, *class_rules))

    assert text[site.start : site.end] == "the kitchen"
    assert {one.id for one in site.rules} == {"the-kitchen"}


def test_an_unknown_rule_kind_is_refused():
    with pytest.raises(ExpansionError, match="--rules must be one of"):
        expand.check_tree([], [], rule_kinds="everything")


def test_the_cli_parses_the_arm_flags():
    parser = expand.build_parser()
    assert parser.parse_args([]).rule_kinds == "both"
    assert parser.parse_args([]).class_groups is None
    args = parser.parse_args(["--rules", "classes", "--class-groups", "referent, calendar"])
    assert args.rule_kinds == "classes"
    assert args.class_groups == ("referent", "calendar")


@pytest.mark.parametrize("raw", ["", "referent,", "referent,referent"])
def test_an_ill_formed_class_group_list_is_refused(raw):
    parser = expand.build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["--class-groups", raw])


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
    """A :class:`RuleSource` built in memory, so the dry run needs no rule file."""
    _, rules = parse_rules({"signal": signal, "rules": list(raw_rules)}, source="<test>")
    return expand.RuleSet(signal=signal, path=Path("<test>"), digest="0" * 64, rules=rules).source


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
        [
            "--dry-run-lint",
            "--manifest",
            str(manifest),
            "--rules-dir",
            str(rules_dir),
            "--classes-dir",
            str(tmp_path / "no-classes"),
        ]
    )

    assert code == 1
    assert "FAIL" in capsys.readouterr().out


def test_the_dry_run_needs_no_tree_but_expanding_still_does(capsys):
    with pytest.raises(SystemExit):
        expand.main([])
    assert "--in-dir" in capsys.readouterr().err


def test_the_dry_run_defaults_to_every_rule_file_and_every_class_file(rules_dir, classes_dir):
    """What CI runs (Task 7): no flags, everything committed, both formats."""
    sources = expand.load_rulesets(None, rules_dir, classes_dir=classes_dir)

    assert [source.label for source in sources] == [f"{SIGNAL} (rules)", "setting (classes)"]
    assert [source.kind for source in sources] == ["rules", "classes"]


@pytest.mark.parametrize(
    ("rule_kinds", "labels"),
    [
        ("signal", [f"{SIGNAL} (rules)"]),
        ("classes", ["setting (classes)"]),
        ("both", [f"{SIGNAL} (rules)", "setting (classes)"]),
    ],
)
def test_the_dry_run_checks_only_the_kinds_it_was_asked_for(
    rules_dir, classes_dir, rule_kinds, labels
):
    sources = expand.load_rulesets(None, rules_dir, classes_dir=classes_dir, rule_kinds=rule_kinds)
    assert [source.label for source in sources] == labels


def test_an_empty_classes_directory_is_a_true_answer_for_the_dry_run(rules_dir, tmp_path):
    """The dry run lints what is committed and writes nothing, so "no class
    files" is a state rather than a mistake -- and the header says so."""
    sources = expand.load_rulesets(None, rules_dir, classes_dir=tmp_path / "no-classes")

    assert [source.kind for source in sources] == ["rules"]


def test_a_dry_run_that_selects_nothing_at_all_is_refused(rules_dir, tmp_path):
    with pytest.raises(ExpansionError, match="selected no rule files at all"):
        expand.load_rulesets(
            None, rules_dir, classes_dir=tmp_path / "no-classes", rule_kinds="classes"
        )


def test_the_dry_run_header_names_every_source_it_checked(tmp_path):
    diff = expand.dry_run_lint(write_manifest(tmp_path), [ruleset(HARMLESS)])

    assert diff.sources == (f"{SIGNAL} (rules)",)
    assert f"sources:  {SIGNAL} (rules)" in "\n".join(expand.render_dry_run(diff))


def test_the_dry_run_covers_class_rules_too(tmp_path, classes_dir):
    """A class file is a rule file for this mode's purposes, and the pairs it
    generates are exactly what nothing else lints in aggregate (DD10)."""
    source = expand.load_classes(classes_dir / "setting.classes.json").source
    diff = expand.dry_run_lint(write_manifest(tmp_path), [source])

    assert diff.sources == ("setting (classes)",)
    assert diff.rules == 6
    assert not diff.failed


# ---------------------------------------------------------------------------
# The committed fever_present rule set (Task 5)
# ---------------------------------------------------------------------------

#: The pilot signal Task 1 recommended, and the only rule file that exists.
PILOT = "fever_present"

#: The libraries a Tier B fever rule must leave alone. Both talk about heat
#: without asserting the signal -- "burning up with anger", "hay fever",
#: "the menopause gives me hot flushes" -- and both are where a swap is most
#: likely to change what a line means (Task 5 instruction 5).
FIGURATIVE_LIBRARIES = ("fever_null_metaphor", "fever_null_attribution")


@pytest.fixture(scope="module")
def committed():
    """The committed rule set, loaded through all three validation layers.

    Loading *is* the assertion: :func:`load_rules` raises on any layer, so a
    rule file that reaches the fixture body has passed all of them. The guard
    this test exists to be is against a later library edit or a later rule
    edit, either of which can invalidate a rule that was sound when authored.
    """
    return expand.load_rules(expand.rules_path(PILOT))


@pytest.fixture(scope="module")
def library_fragments():
    return load_fragments(Path("data/synthetic/manifest.json"), check_cells=False)


def test_the_committed_rule_file_loads_and_declares_the_pilot_signal(committed):
    assert committed.signal == PILOT
    assert committed.rules
    assert {rule.tier for rule in committed.rules} == {"A", "B"}


def test_every_committed_rule_declares_an_invariant_worth_reading(committed):
    """The one layer no check can recover, so the check is that it is there.

    Nothing mechanical can read an invariant, and a placeholder is worse than
    none: it looks like the review happened. A length floor is a crude proxy
    and is the only one available -- "same thing, different word" fits in
    thirty characters and is what the plan names as not an invariant.
    """
    for rule in committed.rules:
        assert len(rule.invariant) >= 60, rule.id


def test_every_committed_rule_fires_somewhere_in_the_libraries(committed, library_fragments):
    """A rule matching nothing is authoring cost for nothing (instruction 1).

    It is also a quiet failure mode: a rule written against a phrase the
    libraries do not use reads as coverage in the rule file and buys none.
    """
    firing = {
        rule.id
        for fragment in library_fragments
        for site in expand.match_sites(fragment.text, committed.rules)
        for rule in site.rules
    }
    assert {rule.id for rule in committed.rules} - firing == set()


def test_no_committed_rule_rewrites_the_figurative_fever_libraries(committed, library_fragments):
    """Tier B must not touch "burning up with anger" or "hay fever".

    Checked at the worst case rather than at a rate: a rule that is harmless
    at ``--rate`` is harmless because of the sampling, not because of the rule.
    Tier A is excluded because register repair is safe everywhere and firing
    there is the point of it.
    """
    tier_b = [rule for rule in committed.rules if rule.tier == "B"]
    for fragment in library_fragments:
        if fragment.library in FIGURATIVE_LIBRARIES:
            assert expand.rewrite_exhaustively(fragment.text, tier_b) == fragment.text, (
                fragment.fragment_id
            )


def test_no_committed_rule_rewrites_a_line_into_another_librarys_line(committed, library_fragments):
    """A rewrite that lands on a line from a differently-labelled library.

    Not a lexicon fault, so the dry run cannot see it, and worse than one: the
    two libraries carry different labels, so the rewritten line asserts what
    its own label denies. Compared under :func:`normalise` because that is the
    key the manifest clusters and splits on.
    """
    by_text: dict[str, set[str]] = {}
    for fragment in library_fragments:
        by_text.setdefault(normalise(fragment.text), set()).add(fragment.library)
    for fragment in library_fragments:
        rewritten = expand.rewrite_exhaustively(fragment.text, committed.rules)
        if rewritten == fragment.text:
            continue
        landed = by_text.get(normalise(rewritten), set())
        assert landed <= {fragment.library}, f"{fragment.fragment_id} -> {sorted(landed)}"


def test_the_committed_rules_pass_the_dry_run_against_the_real_libraries(committed):
    """Task 4's aggregate check, run against the committed libraries.

    This is the test that fails when somebody edits a *library* rather than a
    rule: a lexicon match needing an anchor and a modifier can be completed by
    a swap that carries neither on its own, and that fault appears in library
    text the rule's author never saw.
    """
    diff = expand.dry_run_lint(expand.DEFAULT_MANIFEST, [committed.source])

    assert not diff.failed, "\n".join(expand.render_dry_run(diff))
    assert diff.rewritten, "no library line is rewritten at all"


# ---------------------------------------------------------------------------
# The committed swap classes (Task 6)
# ---------------------------------------------------------------------------

#: Members whose class is a referent class, and therefore must be reachable by
#: :data:`~scripts.synthetic_data.noise.PERSON_CLASSES`. Everything else --
#: weekdays, affect adjectives, clinicians -- must *not* be, and the second
#: half of that is the load-bearing one: mapping a clinician onto
#: ``<third-party>`` would let a swap pass a check whose whole subject is
#: whose symptom is being described.
REFERENT_GROUP = "referent"


@pytest.fixture(scope="module")
def committed_classes():
    """Every committed class file, loaded through every validation layer.

    Loading *is* the assertion, exactly as for the committed rule file: the
    loader runs layer 1, layer 2 on person class (because these rules carry an
    ``origin``) and layer 3 in its signal-agnostic form on every generated
    pair, so a set that reaches the fixture body has passed all three.
    """
    groups = expand.discover_class_groups()
    assert groups, "no committed class files"
    return tuple(expand.load_classes(expand.classes_path(group)) for group in groups)


@pytest.fixture(scope="module")
def committed_class_rules(committed_classes):
    return tuple(rule for class_set in committed_classes for rule in class_set.rules)


def _members(class_sets):
    """``(group, class id, member)`` for every member of every committed class."""
    return [
        (class_set.group, swap_class.id, member)
        for class_set in class_sets
        for swap_class in class_set.classes
        for member in swap_class.members
    ]


def test_the_committed_class_files_load_and_expand(committed_classes, committed_class_rules):
    assert {class_set.group for class_set in committed_classes} == {
        "affect",
        "calendar",
        "referent",
        "setting",
    }
    # Ordered pairs, so a class of n members is n*(n-1) rules and the total is
    # a function of the committed lists alone.
    assert len(committed_class_rules) == sum(
        len(swap_class.members) * (len(swap_class.members) - 1)
        for class_set in committed_classes
        for swap_class in class_set.classes
    )
    assert {rule.origin for rule in committed_class_rules} == {
        swap_class.id for class_set in committed_classes for swap_class in class_set.classes
    }


def test_every_referent_member_is_reachable_by_the_person_map(committed_classes):
    """DD6a's fail-closed property, asserted on the committed lists.

    Checked as "does layer 2 see a person here" rather than as literal
    membership of :data:`~scripts.synthetic_data.noise.PERSON_CLASSES`, because
    that is the property that matters and the map reaches more than its keys:
    an unhyphenated "mother in law" is normalised through its head noun, and a
    hyphenated "mother-in-law" is one token and needs its own key. A member
    that produced an empty sequence would compare equal to any other empty one,
    which is the failure the map is total to prevent.
    """
    for group, class_id, member in _members(committed_classes):
        sequence = structural_sequence(member, person_classes=True)
        if group == REFERENT_GROUP:
            assert sequence == (noise.THIRD_PARTY,), f"{class_id}: {member!r}"
        else:
            assert sequence == (), f"{class_id}: {member!r} must not read as a person"


def test_every_member_that_occurs_fires_as_a_find_and_every_member_is_a_target(
    committed_classes, committed_class_rules, library_fragments
):
    """DD14's replacement for "every committed rule fires somewhere".

    A generated pair whose ``find`` names a member the libraries never use
    fires nowhere, and that is the mechanism working rather than a fault: such
    a member exists to widen the *target* vocabulary. So the guard splits in
    two. A member the libraries *do* use must be reachable as a ``find`` --
    if it is not, a longer member is shadowing every one of its sites and the
    lists want looking at. And every member must be some rule's ``replace``,
    which is what makes an unreachable member worth its authoring cost.
    """
    fired = {
        fold_haystack(rule.find)
        for fragment in library_fragments
        for site in expand.match_sites(fragment.text, committed_class_rules)
        for rule in site.rules
    }
    targets = {fold_haystack(rule.replace) for rule in committed_class_rules}
    for _, class_id, member in _members(committed_classes):
        folded = fold_haystack(member)
        assert folded in targets, f"{class_id}: {member!r} is never a replacement"
        occurs = any(
            re.search(rf"(?<!\w){re.escape(member.lower())}(?!\w)", fragment.text.lower())
            for fragment in library_fragments
        )
        if occurs:
            assert folded in fired, f"{class_id}: {member!r} occurs but fires nowhere"


def test_the_in_law_classes_shadow_the_bare_referent_nouns(committed_class_rules):
    """The one property the referent lists are built on, guarded directly.

    Without the compound classes the longest match at "my mother in law" is the
    bare "mother", and referent.adult_female rewrites the line to "my wife in
    law": broken English that introduces no lexicon hit, so ``--dry-run-lint``
    exits 0 on it. Longest-match-wins is what fixes it, and this is the test
    that notices if a compound is ever dropped from a list.
    """
    for text in (
        "My mother-in-law lives with us",
        "my mother in law's falls",
        "My brother-in-law is off work",
        "It's been months of my brother in law waking needing a wee",
        "My mum-in-law phoned earlier",
    ):
        for rotation in range(8):
            rewritten = expand.rewrite_exhaustively(text, committed_class_rules, rotation=rotation)
            assert re.search(r"(?<!\w)\w+[- ]in[- ]law", rewritten, re.I), rewritten
            # "mum-in-law" is absent from this list on purpose: it is an
            # authored member of referent.in_law_female_hyphenated, because the
            # libraries spell one site that way and it is a real British form.
            assert not re.search(
                r"(?<!\w)(wife|husband|dad|girlfriend|boyfriend|missus|aunt|auntie)"
                r"[- ]in[- ]law",
                rewritten,
                re.I,
            ), f"rotation {rotation}: {rewritten}"


def test_no_committed_class_rewrites_a_line_into_another_librarys_line(
    committed_class_rules, library_fragments
):
    """The rule-file guard, extended to classes, and the one most likely to fire.

    A referent swap is exactly the edit that can land a ``*_null_thirdparty``
    line on a line from a library carrying a different label. Run at every
    rotation, because a single exhaustive pass only ever picks the target whose
    id sorts first and would check one of n-1 (v2 review F9).
    """
    by_text: dict[str, set[str]] = {}
    for fragment in library_fragments:
        by_text.setdefault(normalise(fragment.text), set()).add(fragment.library)
    rotations = expand.combined_rotations(committed_class_rules)
    for rotation in range(rotations):
        for fragment in library_fragments:
            rewritten = expand.rewrite_exhaustively(
                fragment.text, committed_class_rules, rotation=rotation
            )
            if rewritten == fragment.text:
                continue
            landed = by_text.get(normalise(rewritten), set())
            assert landed <= {fragment.library}, (
                f"rotation {rotation}: {fragment.fragment_id} -> {sorted(landed)}"
            )


def test_the_committed_classes_pass_the_dry_run_against_every_signals_libraries(
    committed_classes,
):
    """Task 4's aggregate check over the classes, for all seven signals at once.

    A swap class belongs to no signal, so this is not seven runs but one: every
    class rule is applied to every library line of every signal, and the diff is
    over all seven lexicon reports. Slow -- it is the whole corpus times every
    rule -- and the plan budgets for it rather than skipping it, because a
    lexicon hit completed by a swap is invisible to every per-rule layer.
    """
    diff = expand.dry_run_lint(
        expand.DEFAULT_MANIFEST, [class_set.source for class_set in committed_classes]
    )

    assert not diff.failed, "\n".join(expand.render_dry_run(diff))
    assert diff.rewritten, "no library line is rewritten at all"

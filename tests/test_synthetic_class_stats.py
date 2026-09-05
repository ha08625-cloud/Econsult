"""Unit tests for the swap-class library measurement.

Pure unit tests on hand-built corpora -- no manifest, no ruleset, no database
-- so there is no ``pytestmark``. The module is an instrument and prints rather
than asserts, so what is worth testing is the *counting rule*: that it is
whole-word and case-insensitive, that it does not fire inside a longer word,
and that the two derived columns agree with the functions they claim to report
rather than restating them from a local copy that can drift.
"""

import json
import re

import pytest

from scripts.synthetic_data import class_stats
from scripts.synthetic_data.class_stats import (
    CANDIDATE_CLASSES,
    CandidateClass,
    ClassStatsError,
    Corpus,
    frozen_tokens,
    lexicon_hits,
    load_candidates,
    load_corpus,
    measure_class,
    measure_member,
    render,
)
from scripts.synthetic_data.lint import SIGNAL_LEXICONS, lexicon_matches
from scripts.synthetic_data.noise import STRUCTURAL_FROZEN, fold_token


def corpus(*lines: str) -> Corpus:
    """A corpus of exactly these lines, lowercased the way the reader does."""
    return Corpus(files=(), lines=tuple(line.lower() for line in lines))


def candidate(*members: str, group: str = "referent", class_id: str = "test") -> CandidateClass:
    return CandidateClass(group=group, class_id=class_id, members=members)


# ---------------------------------------------------------------------------
# The counting rule
# ---------------------------------------------------------------------------


def test_counting_is_case_insensitive():
    stats = measure_member("mum", corpus("My Mum called.", "MUM again.", "mum."))
    assert (stats.occurrences, stats.lines) == (3, 3)


def test_repeated_member_on_one_line_counts_once_per_occurrence():
    stats = measure_member("mum", corpus("my mum rang and then mum rang again"))
    assert (stats.occurrences, stats.lines) == (2, 1)


@pytest.mark.parametrize(
    "line",
    [
        "the climate is awful",  # mate inside a longer word
        "my flatmate is away",  # mate as a suffix
        "checkmate",
        "matey",
    ],
)
def test_a_member_inside_a_longer_word_is_not_counted(line):
    assert measure_member("mate", corpus(line)).occurrences == 0


def test_a_member_is_counted_when_it_stands_alone():
    assert (
        measure_member("mate", corpus("my mate has it too", "(mate)", "mate, honestly")).occurrences
        == 3
    )


def test_gran_does_not_match_grandad():
    assert measure_member("gran", corpus("my grandad rang")).occurrences == 0
    assert measure_member("gran", corpus("my gran rang")).occurrences == 1


def test_a_hyphenated_member_is_bounded_on_both_sides():
    stats = measure_member("call-back", corpus("waiting on a call-back", "call-backs are slow"))
    assert stats.occurrences == 1


def test_multi_word_members_are_matched_as_a_phrase():
    stats = measure_member("little one", corpus("my little one is hot", "little ones are hot"))
    assert stats.occurrences == 1


# ---------------------------------------------------------------------------
# The derived columns, checked against their sources
# ---------------------------------------------------------------------------


def test_the_frozen_column_agrees_with_structural_frozen():
    for _group, _class_id, members in CANDIDATE_CLASSES:
        for member in members:
            expected = tuple(
                folded
                for token in member.split()
                if (folded := fold_token(token)) in STRUCTURAL_FROZEN
            )
            assert frozen_tokens(member) == expected


def test_a_frozen_member_reports_the_token_that_froze_it():
    assert frozen_tokens("mum") == ("mum",)
    assert frozen_tokens("sister") == ()


def test_the_lexicon_column_agrees_with_lexicon_matches():
    for _group, _class_id, members in CANDIDATE_CLASSES:
        for member in members:
            expected = tuple(
                f"{signal}:{'/'.join(matched)}"
                for signal in SIGNAL_LEXICONS
                if (matched := lexicon_matches(member, signal))
            )
            assert lexicon_hits(member) == expected


def test_no_candidate_member_reads_as_a_signal():
    """DD10/F4: layer 3 passes trivially for every class, and that is why the
    invariant and the dry run are the whole safety argument. A new member that
    breaks this is a member whose swap can move a label."""
    offenders = {
        member
        for _group, _class_id, members in CANDIDATE_CLASSES
        for member in members
        if lexicon_hits(member)
    }
    assert offenders == set()


# ---------------------------------------------------------------------------
# Class-level aggregation
# ---------------------------------------------------------------------------


def test_lines_with_multiple_counts_collision_opportunity():
    stats = measure_class(
        candidate("wife", "sister"),
        corpus("my wife and my sister", "my wife only", "nobody here"),
    )
    assert (stats.lines_with_any, stats.lines_with_multiple) == (2, 1)
    assert stats.occurrences == 3


def test_absent_and_frozen_rollups():
    stats = measure_class(candidate("mum", "sister", "missus"), corpus("my mum and my sister"))
    assert stats.absent == ("missus",)
    assert stats.frozen == ("mum",)
    assert stats.frozen_occurrences == 1


def test_ordered_pairs_is_n_times_n_minus_one():
    assert candidate("a", "b", "c").pairs == 6


def test_determiner_context_is_the_word_directly_before():
    stats = measure_member(
        "friend", corpus("a friend of mine", "my friend", "the friend", "friend of a friend")
    )
    assert dict(stats.determiners) == {"a": 2, "the": 1, "my": 1, "bare": 1}


def test_group_rollup_counts_a_line_once_across_classes():
    candidates = (candidate("wife", class_id="female"), candidate("son", class_id="male"))
    any_line, multi_line = class_stats.group_lines(
        candidates, "referent", corpus("my wife and my son", "my son only")
    )
    assert (any_line, multi_line) == (2, 1)


# ---------------------------------------------------------------------------
# Reading the corpus and the candidate lists
# ---------------------------------------------------------------------------


def test_load_corpus_drops_blank_and_comment_lines(tmp_path):
    (tmp_path / "one.txt").write_text("# a comment\n\nmy mum called.\n   \n  # indented comment\n")
    (tmp_path / "nested").mkdir()
    (tmp_path / "nested" / "two.txt").write_text("my son called.\n")
    loaded = load_corpus(tmp_path)
    # Sorted path order, so the nested file comes first. Deterministic is the
    # only property that matters: nothing downstream reads the line order.
    assert loaded.lines == ("my son called.", "my mum called.")
    assert len(loaded.files) == 2


def test_load_corpus_lowercases_once(tmp_path):
    (tmp_path / "one.txt").write_text("My Mum Called.\n")
    assert load_corpus(tmp_path).lines == ("my mum called.",)


def test_load_corpus_refuses_an_empty_root(tmp_path):
    with pytest.raises(ClassStatsError, match="no '\\*.txt' libraries"):
        load_corpus(tmp_path)


def test_candidates_fall_back_to_the_hard_coded_lists(tmp_path):
    candidates, source = load_candidates(tmp_path / "absent")
    assert len(candidates) == len(CANDIDATE_CLASSES)
    assert "hard-coded" in source


def test_authored_class_files_win_when_they_exist(tmp_path):
    (tmp_path / "referent.classes.json").write_text(
        json.dumps(
            {
                "group": "referent",
                "classes": [
                    {
                        "id": "adult_female",
                        "members": ["mum", "mother"],
                        "invariant": "ignored by this module",
                    }
                ],
            }
        )
    )
    candidates, source = load_candidates(tmp_path)
    assert candidates == (CandidateClass("referent", "adult_female", ("mum", "mother")),)
    assert "1 class file" in source


@pytest.mark.parametrize(
    "payload",
    [
        "[]",
        '{"group": "referent"}',
        '{"classes": [["adult_female", ["mum"]]]}',
        '{"classes": [{"id": "adult_female"}]}',
        '{"classes": [{"id": "adult_female", "members": [1]}]}',
        "{not json",
    ],
)
def test_a_class_file_this_module_would_have_to_guess_at_is_refused(tmp_path, payload):
    (tmp_path / "referent.classes.json").write_text(payload)
    with pytest.raises(ClassStatsError):
        load_candidates(tmp_path)


# ---------------------------------------------------------------------------
# The report
# ---------------------------------------------------------------------------


def test_the_report_names_every_class_and_member():
    library = corpus("my mum and my sister", "my son is hot")
    candidates = (candidate("mum", "sister", class_id="adult_female"),)
    text = "\n".join(render(tuple(measure_class(c, library) for c in candidates), library, "test"))
    assert "adult_female" in text
    assert "mum" in text and "sister" in text
    assert "Section 1" in text and "Section 2" in text and "Section 3" in text


def test_the_report_prints_and_does_not_fail_on_the_committed_libraries(capsys):
    """A smoke test, deliberately not a gate on the corpus.

    The counts are not pinned: this module prints so that a class that measures
    badly is dropped in review, and a test that failed every time a library
    gained a line would make the instrument a reason not to write fragments.
    """
    assert class_stats.main([]) == 0
    printed = capsys.readouterr().out
    assert re.search(r"corpus: \d+ files, \d+ non-blank non-comment lines", printed)
    assert "adult_female" in printed


def test_main_reports_a_missing_library_root_without_a_traceback(tmp_path, capsys):
    assert class_stats.main(["--library-root", str(tmp_path)]) == 2
    assert "error:" in capsys.readouterr().err

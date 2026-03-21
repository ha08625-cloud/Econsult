"""
Repository-level tests for signposting methods in PracticeRepository.

These tests exercise the database layer using an in-memory SQLite database.
They do not re-test HTML sanitisation behaviour — that is covered by
test_sanitise_signposting.py. These tests verify:

- Valid HTML is written to and read back from the database correctly
- The column stores a plain string, not JSON-encoded content
- Empty/whitespace input to set_signposting deletes any existing row
- Quill empty output to set_signposting deletes any existing row
- PracticeNotFound is raised when the practice does not exist
- get_signposting returns None when no row exists
- delete_signposting removes the row; subsequent get returns None
- Overwriting existing signposting replaces the content
- HTML that would be malformed JSON does not cause errors on read

Run from the project root:
    python -m pytest tests/test_practice_repository_signposting.py -v

Requires nh3 to be installed:
    pip install nh3
"""

import pytest
from app.repositories.practice_repository import (
    PracticeRepository,
    PracticeNotFound,
    QUILL_EMPTY_OUTPUT,
)


PRACTICE_ID = "test-practice"
CONDITION_ID = "test-condition"


@pytest.fixture
def repo(tmp_path):
    """
    Create a PracticeRepository backed by a temporary on-disk SQLite file.
    A practice row is seeded so signposting operations have a valid foreign key.
    """
    db_path = str(tmp_path / "test.db")
    r = PracticeRepository(db_path)
    r.create_practice(PRACTICE_ID, "Test Practice", "test@example.com")
    return r


# ---------------------------------------------------------------------------
# get_signposting — no row exists
# ---------------------------------------------------------------------------

def test_get_returns_none_when_no_row(repo):
    result = repo.get_signposting(PRACTICE_ID, CONDITION_ID)
    assert result is None


def test_get_returns_none_for_unknown_practice(repo):
    # Does not raise — graceful degradation is intentional.
    result = repo.get_signposting("nonexistent-practice", CONDITION_ID)
    assert result is None


# ---------------------------------------------------------------------------
# set_signposting — valid content is written and read back
# ---------------------------------------------------------------------------

def test_valid_html_is_stored_and_returned(repo):
    html = "<p>Call us on <strong>0800 123 456</strong> for more information.</p>"
    repo.set_signposting(PRACTICE_ID, CONDITION_ID, html)
    result = repo.get_signposting(PRACTICE_ID, CONDITION_ID)
    assert result is not None
    assert isinstance(result, str)
    # The stored value is a plain string, not JSON — verify it is not
    # double-encoded by checking the angle bracket survives unescaped.
    assert "<p>" in result
    assert "<strong>" in result


def test_stored_value_is_not_json_encoded(repo):
    """
    Regression guard: the column must store raw HTML, not json.dumps(html).
    If the value were JSON-encoded, it would be surrounded by double-quotes
    and angle brackets would be escaped.
    """
    html = "<p>some content</p>"
    repo.set_signposting(PRACTICE_ID, CONDITION_ID, html)
    result = repo.get_signposting(PRACTICE_ID, CONDITION_ID)
    assert result is not None
    # A JSON-encoded string would start with '"' and contain '\\u003c' or '"<p>'
    assert not result.startswith('"')
    assert "\\u003c" not in result
    assert result.startswith("<")


def test_html_that_would_break_json_parsing_survives(repo):
    """
    Content containing characters that are special in JSON (quotes, backslashes)
    must survive the round-trip without corruption. This guards against any
    accidental re-introduction of JSON encoding.
    """
    html = '<p>Visit <a href="https://example.com">example.com</a> for details.</p>'
    repo.set_signposting(PRACTICE_ID, CONDITION_ID, html)
    result = repo.get_signposting(PRACTICE_ID, CONDITION_ID)
    assert result is not None
    assert 'href="https://example.com"' in result


# ---------------------------------------------------------------------------
# set_signposting — empty content deletes the row
# ---------------------------------------------------------------------------

def test_empty_string_deletes_existing_row(repo):
    repo.set_signposting(PRACTICE_ID, CONDITION_ID, "<p>content</p>")
    assert repo.get_signposting(PRACTICE_ID, CONDITION_ID) is not None

    repo.set_signposting(PRACTICE_ID, CONDITION_ID, "")
    assert repo.get_signposting(PRACTICE_ID, CONDITION_ID) is None


def test_whitespace_only_deletes_existing_row(repo):
    repo.set_signposting(PRACTICE_ID, CONDITION_ID, "<p>content</p>")
    repo.set_signposting(PRACTICE_ID, CONDITION_ID, "   ")
    assert repo.get_signposting(PRACTICE_ID, CONDITION_ID) is None


def test_quill_empty_output_deletes_existing_row(repo):
    repo.set_signposting(PRACTICE_ID, CONDITION_ID, "<p>content</p>")
    repo.set_signposting(PRACTICE_ID, CONDITION_ID, QUILL_EMPTY_OUTPUT)
    assert repo.get_signposting(PRACTICE_ID, CONDITION_ID) is None


def test_empty_write_on_nonexistent_row_does_not_raise(repo):
    """
    set_signposting with empty content when no row exists should be a no-op,
    not raise an error.
    """
    repo.set_signposting(PRACTICE_ID, CONDITION_ID, "")
    assert repo.get_signposting(PRACTICE_ID, CONDITION_ID) is None


# ---------------------------------------------------------------------------
# set_signposting — error cases
# ---------------------------------------------------------------------------

def test_set_raises_practice_not_found(repo):
    with pytest.raises(PracticeNotFound):
        repo.set_signposting("nonexistent-practice", CONDITION_ID, "<p>text</p>")


# ---------------------------------------------------------------------------
# set_signposting — overwrite behaviour
# ---------------------------------------------------------------------------

def test_overwrite_replaces_content(repo):
    repo.set_signposting(PRACTICE_ID, CONDITION_ID, "<p>first</p>")
    repo.set_signposting(PRACTICE_ID, CONDITION_ID, "<p>second</p>")
    result = repo.get_signposting(PRACTICE_ID, CONDITION_ID)
    assert result is not None
    assert "second" in result
    assert "first" not in result


# ---------------------------------------------------------------------------
# delete_signposting
# ---------------------------------------------------------------------------

def test_delete_removes_row(repo):
    repo.set_signposting(PRACTICE_ID, CONDITION_ID, "<p>content</p>")
    repo.delete_signposting(PRACTICE_ID, CONDITION_ID)
    assert repo.get_signposting(PRACTICE_ID, CONDITION_ID) is None


def test_delete_is_idempotent(repo):
    """Deleting a non-existent row must not raise."""
    repo.delete_signposting(PRACTICE_ID, CONDITION_ID)
    repo.delete_signposting(PRACTICE_ID, CONDITION_ID)


def test_set_after_delete_restores_content(repo):
    repo.set_signposting(PRACTICE_ID, CONDITION_ID, "<p>content</p>")
    repo.delete_signposting(PRACTICE_ID, CONDITION_ID)
    repo.set_signposting(PRACTICE_ID, CONDITION_ID, "<p>restored</p>")
    result = repo.get_signposting(PRACTICE_ID, CONDITION_ID)
    assert result is not None
    assert "restored" in result


# ---------------------------------------------------------------------------
# Condition isolation
# ---------------------------------------------------------------------------

def test_different_conditions_are_independent(repo):
    repo.set_signposting(PRACTICE_ID, "condition-a", "<p>for A</p>")
    repo.set_signposting(PRACTICE_ID, "condition-b", "<p>for B</p>")

    result_a = repo.get_signposting(PRACTICE_ID, "condition-a")
    result_b = repo.get_signposting(PRACTICE_ID, "condition-b")

    assert result_a is not None and "for A" in result_a
    assert result_b is not None and "for B" in result_b

    repo.delete_signposting(PRACTICE_ID, "condition-a")
    assert repo.get_signposting(PRACTICE_ID, "condition-a") is None
    assert repo.get_signposting(PRACTICE_ID, "condition-b") is not None
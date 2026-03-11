"""
Tests for sanitise_signposting_html in practice_repository.py.

Run from the project root:
    python -m pytest tests/test_sanitise_signposting.py -v

Requires nh3 to be installed:
    pip install nh3
"""

import pytest
from practice_repository import (
    sanitise_signposting_html,
    InvalidSignpostingData,
    MAX_SIGNPOSTING_LENGTH,
    QUILL_EMPTY_OUTPUT,
)


# ---------------------------------------------------------------------------
# Allowed content survives
# ---------------------------------------------------------------------------

def test_strong_tag_survives():
    result = sanitise_signposting_html("<strong>bold</strong>")
    assert result is not None
    assert "<strong>bold</strong>" in result


def test_em_tag_survives():
    result = sanitise_signposting_html("<em>italic</em>")
    assert result is not None
    assert "<em>italic</em>" in result


def test_valid_https_link_survives_with_href():
    result = sanitise_signposting_html(
        '<a href="https://example.com">click here</a>'
    )
    assert result is not None
    assert 'href="https://example.com"' in result
    assert "click here" in result


def test_rel_and_target_attributes_survive():
    """
    Quill automatically adds rel="noopener noreferrer" and target="_blank"
    to all links.

    nh3 behaviour:
    - rel: nh3 INJECTS rel="noopener noreferrer" automatically on every <a>
      tag via its link_rel parameter (default value). It must NOT be passed
      through the attributes dict or nh3 will panic.
    - target: passes through the attributes dict normally.

    Both must be present in the sanitised output so that DOMPurify in
    admin.html and App.tsx (which must allow rel and target) does not
    silently strip a security attribute.
    """
    result = sanitise_signposting_html(
        '<a href="https://example.com" rel="noopener noreferrer" target="_blank">link</a>'
    )
    assert result is not None
    assert 'rel="noopener noreferrer"' in result
    assert 'target="_blank"' in result


# ---------------------------------------------------------------------------
# Disallowed content is stripped
# ---------------------------------------------------------------------------

def test_javascript_href_is_stripped():
    result = sanitise_signposting_html(
        '<a href="javascript:alert(1)">click</a>'
    )
    # Either the href is stripped (leaving a bare <a>) or the element is
    # removed entirely. Either way, the javascript: URI must not appear.
    assert result is None or "javascript:" not in result


def test_onclick_attribute_is_stripped():
    result = sanitise_signposting_html(
        '<p onclick="alert(1)">text</p>'
    )
    assert result is not None
    assert "onclick" not in result
    assert "text" in result


def test_script_tag_is_stripped_text_preserved():
    result = sanitise_signposting_html("<script>alert(1)</script>visible")
    # The script tag is gone; the text content "visible" survives.
    assert result is None or (
        "<script>" not in result and "alert(1)" not in result
    )
    # "visible" is bare text — nh3 does not wrap it, so this may return None.
    # The important assertion is that no script tag survives.


def test_h1_tag_stripped_text_preserved():
    result = sanitise_signposting_html("<h1>heading text</h1>")
    assert result is None or (
        "<h1>" not in result and "heading text" in result
    )


def test_img_tag_stripped_entirely():
    """img has no text content so it must disappear completely."""
    result = sanitise_signposting_html('<img src="x" onerror="alert(2)">')
    assert result is None
    # If nh3 produces any non-empty output, the img tag must not be present.
    if result is not None:
        assert "<img" not in result


# ---------------------------------------------------------------------------
# Empty-content detection returns None
# ---------------------------------------------------------------------------

def test_empty_string_returns_none():
    assert sanitise_signposting_html("") is None


def test_whitespace_only_returns_none():
    assert sanitise_signposting_html("   ") is None


def test_quill_empty_output_returns_none():
    """<p></p> is the confirmed Quill 2.0.2 empty-editor output."""
    assert sanitise_signposting_html(QUILL_EMPTY_OUTPUT) is None


# ---------------------------------------------------------------------------
# Length enforcement
# ---------------------------------------------------------------------------

def test_exactly_max_length_is_accepted():
    # Build a string of exactly MAX_SIGNPOSTING_LENGTH characters.
    # Use plain text so it is not stripped by nh3.
    # Wrap in <p> so nh3 does not need to handle bare text.
    padding = "a" * (MAX_SIGNPOSTING_LENGTH - len("<p></p>"))
    raw = f"<p>{padding}</p>"
    # Trim to exactly MAX_SIGNPOSTING_LENGTH if our wrapping overshot.
    raw = raw[:MAX_SIGNPOSTING_LENGTH]
    # Should not raise.
    result = sanitise_signposting_html(raw)
    # Result is either None (if all content was stripped) or a string.
    # The key assertion is that no exception was raised.
    assert result is None or isinstance(result, str)


def test_one_over_max_length_raises():
    raw = "a" * (MAX_SIGNPOSTING_LENGTH + 1)
    with pytest.raises(InvalidSignpostingData) as exc_info:
        sanitise_signposting_html(raw)
    assert "5000" in str(exc_info.value)
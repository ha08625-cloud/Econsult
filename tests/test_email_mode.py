"""
Unit tests for app/core/email_mode.py.

Pure unit tests: no database, no integration marker, no environment
variables. email_mode.py's functions take their inputs as plain
arguments, so these tests call them directly rather than monkeypatching
os.environ -- there is no env-sourcing path to exercise here, unlike
app/core/settings.py, which is a separate, already-covered concern (see
test_settings.py).
"""

from app.core.email_mode import (
    has_complete_mailgun,
    has_partial_mailgun,
    select_email_delivery_mode,
)


# ---------------------------------------------------------------------------
# has_complete_mailgun
# ---------------------------------------------------------------------------

def test_complete_pair_is_complete():
    assert has_complete_mailgun("key-123", "mg.example.com") is True


def test_key_only_is_not_complete():
    assert has_complete_mailgun("key-123", None) is False


def test_domain_only_is_not_complete():
    assert has_complete_mailgun(None, "mg.example.com") is False


def test_neither_set_is_not_complete():
    assert has_complete_mailgun(None, None) is False


def test_blank_key_is_not_complete():
    assert has_complete_mailgun("", "mg.example.com") is False


def test_whitespace_only_domain_is_not_complete():
    # Matches the os.environ.get(...) truthiness semantics used
    # elsewhere in this codebase: a whitespace-only value is treated
    # as unset, not as a real configured value.
    assert has_complete_mailgun("key-123", "   ") is False


# ---------------------------------------------------------------------------
# has_partial_mailgun
# ---------------------------------------------------------------------------

def test_key_only_is_partial():
    assert has_partial_mailgun("key-123", None) is True


def test_domain_only_is_partial():
    assert has_partial_mailgun(None, "mg.example.com") is True


def test_complete_pair_is_not_partial():
    assert has_partial_mailgun("key-123", "mg.example.com") is False


def test_neither_set_is_not_partial():
    assert has_partial_mailgun(None, None) is False


def test_whitespace_only_key_with_real_domain_is_partial():
    assert has_partial_mailgun("   ", "mg.example.com") is True


def test_blank_domain_with_real_key_is_partial():
    assert has_partial_mailgun("key-123", "") is True


# ---------------------------------------------------------------------------
# select_email_delivery_mode
# ---------------------------------------------------------------------------

def test_complete_mailgun_selects_mailgun():
    assert select_email_delivery_mode("key-123", "mg.example.com") == "mailgun"


def test_key_only_selects_smtp():
    # The exact case worker_main.py used to get wrong: key set, domain
    # missing must NOT select Mailgun.
    assert select_email_delivery_mode("key-123", None) == "smtp"


def test_domain_only_selects_smtp():
    assert select_email_delivery_mode(None, "mg.example.com") == "smtp"


def test_neither_set_selects_smtp():
    assert select_email_delivery_mode(None, None) == "smtp"


def test_blank_values_select_smtp():
    assert select_email_delivery_mode("", "") == "smtp"


def test_whitespace_only_values_select_smtp():
    # The case that changes worker behaviour: previously a whitespace-
    # only MAILGUN_API_KEY was truthy to a raw os.environ.get(...) check
    # and would have selected Mailgun; the shared predicate treats it
    # as unset.
    assert select_email_delivery_mode("   ", "\t") == "smtp"
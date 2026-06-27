"""
Single-sourced predicate for which email delivery path is configured.

This is a leaf module by design: it imports nothing (not stdlib, not
pydantic, not any project module) -- mirroring app/core/state_keys.py --
so that both app/core/settings.py (the web path, via EmailSettings) and
worker_main.py (the delivery worker, which reads os.environ directly
and never constructs a settings object) can depend on it without either
one pulling in the other's import closure.

Why this module exists
-----------------------
Before this module existed, "is Mailgun configured" was decided in two
places that could drift out of sync:
  - app/core/settings.py (EmailSettings) required BOTH MAILGUN_API_KEY
    and MAILGUN_DOMAIN to be set before selecting Mailgun.
  - worker_main.py required only MAILGUN_API_KEY.

A deployment with MAILGUN_API_KEY set but MAILGUN_DOMAIN missing (or
blank) started successfully on the web -- which correctly fell through
to SMTP -- and then crash-looped on the delivery worker, which selected
Mailgun and then failed inside MailgunHttpDeliveryService.__init__
because MAILGUN_DOMAIN is a required constructor argument. Defining the
predicate once, here, removes that drift at its source rather than
re-deriving it in each entry point.

Blank-versus-unset
-------------------
Callers may pass raw os.environ.get(...) results directly. An empty
string or a whitespace-only string is treated identically to an unset
(None) value, matching the long-standing truthiness semantics of the
os.environ.get(...) checks used elsewhere in this codebase (see
app/core/settings.py's _blank_to_none). That one helper is
re-implemented below rather than imported, to preserve the "imports
nothing" leaf constraint -- this module must remain importable by
worker_main.py without dragging in pydantic or any other dependency.

Scope
-----
This module makes one decision -- which mode applies -- and nothing
else. It does not log, raise, or otherwise have side effects.
Diagnostics (e.g. the partial-Mailgun warning) remain each caller's
responsibility, since the web (a pydantic model validator) and the
worker (a plain log statement before branching) have different
logging conventions and different failure semantics.
"""


def _is_set(value: str | None) -> bool:
    """True if value is present and not blank/whitespace-only."""
    return value is not None and value.strip() != ""


def has_complete_mailgun(api_key: str | None, domain: str | None) -> bool:
    """True only if both MAILGUN_API_KEY and MAILGUN_DOMAIN are set."""
    return _is_set(api_key) and _is_set(domain)


def has_partial_mailgun(api_key: str | None, domain: str | None) -> bool:
    """True if exactly one of the Mailgun pair is set, but not both."""
    return (
        _is_set(api_key) or _is_set(domain)
    ) and not has_complete_mailgun(api_key, domain)


def select_email_delivery_mode(api_key: str | None, domain: str | None) -> str:
    """
    The single definition of which email path is configured.

    Returns "mailgun" only for a COMPLETE Mailgun configuration (both
    api_key and domain set and non-blank); otherwise "smtp".

    This function does not validate that the SMTP path is itself
    complete. A caller that needs a fail-fast startup guarantee (the
    web's EmailSettings model validator) must enforce that separately.
    The delivery worker instead relies on EmailDeliveryService's own
    constructor to fail fast if SMTP is incomplete.
    """
    return "mailgun" if has_complete_mailgun(api_key, domain) else "smtp"
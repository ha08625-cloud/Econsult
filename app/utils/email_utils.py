"""
app/utils/email_utils.py

Shared email utility functions.

Kept deliberately minimal — only validation logic that is needed in more than
one place belongs here. Domain allowlist checking lives in auth_service.py
because it depends on application configuration (ALLOWED_ADMIN_DOMAINS), not
just the email string itself.
"""


def is_valid_email_format(email: str) -> bool:
    """
    Return True if email has a structurally valid format.

    Checks:
    - Contains exactly one '@'
    - Local part (before '@') is non-empty
    - Domain part (after '@') is non-empty

    This is intentionally minimal — it catches obvious malformed inputs
    (empty string, missing '@', bare '@') without reimplementing a full
    RFC 5321 parser. Domain-level validation (allowed domains) is a
    separate concern handled by validate_admin_domain in auth_service.py.

    Does NOT check:
    - Whether the domain exists or resolves
    - Whether the TLD is valid
    - Length limits beyond what the above rules imply
    """
    if not isinstance(email, str):
        return False
    parts = email.split("@")
    if len(parts) != 2:
        return False
    local, domain = parts
    return bool(local) and bool(domain)

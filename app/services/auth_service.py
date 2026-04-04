"""
app/services/auth_service.py

Business logic for admin MFA authentication.

Responsibilities:
- Domain validation (allowed email domains)
- Code generation and hashing
- request_mfa_code flow (cooldown check, generate, upsert, send)
- verify_mfa_code flow (verification pipeline with fixed-delay timing)

This module sits between the router and the repository. It never touches
the database directly — all DB access goes through AuthRepository.

Timing attack mitigation:
_fixed_delay() ensures every verification attempt takes at least 300ms,
regardless of which gate failed. This prevents an attacker from learning
information about the user's existence or code validity from response time.

bcrypt note:
bcrypt.hashpw and bcrypt.checkpw are blocking CPU-bound operations.
At current scale (single admin user, infrequent logins) this is acceptable.
If this ever becomes a performance concern, wrap calls in
asyncio.get_event_loop().run_in_executor(None, ...) from the async router.
"""

import secrets
import time
import logging
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING

import bcrypt

from app.core.errors import INVALID_PAYLOAD, INVALID_AUTH_CODE, RATE_LIMIT_EXCEEDED

if TYPE_CHECKING:
    from app.repositories.auth_repository import AuthRepository
    from app.services.delivery.admin_delivery_service import AdminDeliveryService

logger = logging.getLogger(__name__)

# Code validity window.
_CODE_TTL_MINUTES = 10

# Minimum time (seconds) for any verification attempt, regardless of outcome.
# Prevents timing-based enumeration of which gate failed.
_MIN_RESPONSE_SECONDS = 0.3

# Rate-limit cooldown window.
_COOLDOWN_SECONDS = 60

# Maximum failed attempts before the code is deleted and locked out.
_MAX_ATTEMPTS = 3


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _fixed_delay(start: float) -> None:
    """
    Block until at least _MIN_RESPONSE_SECONDS have elapsed since start.

    Uses time.sleep (not asyncio.sleep) because the repository calls in
    verify_mfa_code are synchronous psycopg2 calls. Mixing asyncio.sleep
    with synchronous code would require run_in_executor for the entire
    function. At current scale this is acceptable — revisit if the admin
    portal ever handles concurrent login attempts under load.
    """
    elapsed = time.monotonic() - start
    remaining = _MIN_RESPONSE_SECONDS - elapsed
    if remaining > 0:
        time.sleep(remaining)


# ---------------------------------------------------------------------------
# Domain validation
# ---------------------------------------------------------------------------

def validate_admin_domain(email: str, allowed_domains: str) -> bool:
    """
    Return True if the email's domain is in the allowed_domains list.

    allowed_domains is a comma-separated string (e.g. "nhs.net,gov.uk").
    Each entry is stripped of whitespace before comparison.

    Uses exact match on the domain part — does NOT use endswith().
    Example: "user@nhs.net" passes for "nhs.net" but not for "notnhs.net".

    Returns False if:
    - The email contains no '@' or more than one '@'
    - The domain is not in the allowed list
    - allowed_domains is empty or blank
    """
    parts = email.split("@")
    if len(parts) != 2:
        return False
    domain = parts[1]
    allowed = [d.strip() for d in allowed_domains.split(",") if d.strip()]
    return domain in allowed


# ---------------------------------------------------------------------------
# Code generation and hashing
# ---------------------------------------------------------------------------

def generate_code() -> str:
    """
    Return a cryptographically random 6-digit zero-padded string.

    Uses secrets.randbelow for cryptographic randomness.
    Output range: "000000" to "999999".
    """
    return str(secrets.randbelow(1_000_000)).zfill(6)


def hash_code(code: str) -> str:
    """
    Return the bcrypt hash of the given code string.

    Uses bcrypt.hashpw with a freshly generated salt. The result is a
    bytes object decoded to str for storage in the TEXT column.
    """
    return bcrypt.hashpw(code.encode(), bcrypt.gensalt()).decode()


def verify_code(code: str, hashed: str) -> bool:
    """
    Return True if code matches the bcrypt hash.
    """
    return bcrypt.checkpw(code.encode(), hashed.encode())


# ---------------------------------------------------------------------------
# Request-code flow
# ---------------------------------------------------------------------------

def request_mfa_code(
    email: str,
    auth_repo: "AuthRepository",
    delivery_service: "AdminDeliveryService",
    allowed_domains: str,
    practice_id: str,
) -> None:
    """
    Validate the request, generate a code, persist it, and send it.

    Steps:
    1. Validate domain — raise INVALID_PAYLOAD if not in allowed list.
       Generic message; does not reveal whether the email is registered.
    2. Look up user by email — return silently if not found.
       Silence prevents user enumeration at this endpoint.
    3. Check last_requested_at — raise RATE_LIMIT_EXCEEDED if within
       the 60-second cooldown window.
    4. Generate code, hash it, upsert the record.
    5. Send the code via delivery_service.

    practice_id is accepted but not used for filtering here — user lookup
    is by email only, and the email domain check is the scope guard.
    It is retained in the signature for potential future multi-tenant use
    and to make the dependency explicit at the call site in the router.
    """
    if not validate_admin_domain(email, allowed_domains):
        raise INVALID_PAYLOAD("Email domain is not permitted for admin access.")

    user = auth_repo.get_user_by_email(email)
    if user is None:
        # Silent return — do not reveal that the email is not registered.
        logger.info("MFA code requested for unknown email (suppressed): %s", email)
        return

    now = datetime.now(tz=timezone.utc)
    record = auth_repo.get_auth_code_record(email)
    if record is not None:
        last_requested = record["last_requested_at"]
        # Normalise to UTC-aware for comparison if psycopg2 returns aware datetime.
        if last_requested.tzinfo is None:
            last_requested = last_requested.replace(tzinfo=timezone.utc)
        elapsed = (now - last_requested).total_seconds()
        if elapsed < _COOLDOWN_SECONDS:
            raise RATE_LIMIT_EXCEEDED()

    code = generate_code()
    hashed = hash_code(code)
    expires_at = now + timedelta(minutes=_CODE_TTL_MINUTES)

    auth_repo.upsert_auth_code(
        email=email,
        hashed_code=hashed,
        expires_at=expires_at,
        last_requested_at=now,
    )

    delivery_service.send_mfa_code(email, code)
    logger.info("MFA code sent to %s", email)


# ---------------------------------------------------------------------------
# Verify-code flow
# ---------------------------------------------------------------------------

def verify_mfa_code(
    email: str,
    code: str,
    auth_repo: "AuthRepository",
    session_ttl_minutes: int,
) -> str:
    """
    Run the verification pipeline and return a session_id on success.

    Every failure path calls _fixed_delay() before raising to ensure a
    consistent minimum response time regardless of which gate failed.

    Raises INVALID_AUTH_CODE (APIError -> 422) on any failure.
    Returns the session_id string on success.

    Pipeline:
    1. User lookup — fail if not found.
    2. Auth code record lookup — fail if not found.
    3. Lockout check — fail and delete code if attempts >= _MAX_ATTEMPTS.
    4. Expiry check — fail and delete code if expired.
    5. bcrypt verification — fail and increment attempts if wrong.
    6. Success — delete code, create session, return session_id.
    """
    start = time.monotonic()

    # Stage 1: user lookup.
    user = auth_repo.get_user_by_email(email)
    if user is None:
        _fixed_delay(start)
        raise INVALID_AUTH_CODE()

    # Stage 2: auth code record.
    record = auth_repo.get_auth_code_record(email)
    if record is None:
        _fixed_delay(start)
        raise INVALID_AUTH_CODE()

    # Stage 3: lockout check.
    if record["attempts_count"] >= _MAX_ATTEMPTS:
        auth_repo.delete_auth_code(email)
        _fixed_delay(start)
        raise INVALID_AUTH_CODE()

    # Stage 4: expiry check.
    expires_at = record["expires_at"]
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if expires_at < datetime.now(tz=timezone.utc):
        auth_repo.delete_auth_code(email)
        _fixed_delay(start)
        raise INVALID_AUTH_CODE()

    # Stage 5: bcrypt verification.
    if not verify_code(code, record["hashed_code"]):
        auth_repo.increment_code_attempts(email)
        _fixed_delay(start)
        raise INVALID_AUTH_CODE()

    # Stage 6: success.
    auth_repo.delete_auth_code(email)
    session_expires_at = datetime.now(tz=timezone.utc) + timedelta(minutes=session_ttl_minutes)
    session_id = auth_repo.create_session(user["id"], session_expires_at)

    logger.info("MFA verification successful for %s — session created", email)
    return session_id
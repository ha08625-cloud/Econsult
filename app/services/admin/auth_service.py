"""
app/services/admin/auth_service.py

Business logic for admin MFA and password authentication.

Responsibilities:
- Domain validation (allowed email domains)
- Code generation and hashing
- request_mfa_code flow (cooldown check, generate, upsert, send)
- verify_mfa_code flow (verification pipeline with fixed-delay timing)
- verify_login_credentials flow (password check with timing-safe execution)
- Password reset token generation and verification
- set_new_password (strength enforcement via zxcvbn, bcrypt hashing)

This module sits between the router and the repository. It never touches
the database directly — all DB access goes through AuthRepository.

Timing attack mitigation:
_fixed_delay() ensures every verification attempt takes at least 300ms,
regardless of which gate failed. This prevents an attacker from learning
information about the user's existence or code validity from response time.

Password timing mitigation (verify_login_credentials):
All fast checks (user lookup, cooldown, lockout, no-password guard) are
evaluated first without running bcrypt. A boolean flag records whether
the real hash should be used. A single bcrypt.checkpw() call is then
executed unconditionally — against the real hash on the happy path, or
against a static dummy hash on all failure paths. _fixed_delay(start) is
called immediately after bcrypt, before any branching on the outcome.
This means bcrypt's CPU cost is always accounted for within the minimum
response window, regardless of which path was taken.

bcrypt note:
bcrypt.hashpw and bcrypt.checkpw are blocking CPU-bound operations.
At current scale (single admin user, infrequent logins) this is acceptable.
If this ever becomes a performance concern, wrap calls in
asyncio.get_event_loop().run_in_executor(None, ...) from the async router.
"""

import hashlib
import secrets
import time
import logging
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, Optional

import bcrypt

from app.core.errors import (
    INVALID_PAYLOAD,
    INVALID_AUTH_CODE,
    RATE_LIMIT_EXCEEDED,
    INVALID_CREDENTIALS,
    INVALID_RESET_TOKEN,
    WEAK_PASSWORD,
)
from app.utils.email_utils import is_valid_email_format

if TYPE_CHECKING:
    from app.repositories.auth_repository import AuthRepository
    from app.services.delivery.admin_delivery_service import AdminDeliveryService

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Code validity window.
_CODE_TTL_MINUTES = 10

# Minimum time (seconds) for any verification attempt, regardless of outcome.
# Prevents timing-based enumeration of which gate failed.
_MIN_RESPONSE_SECONDS = 0.3

# Rate-limit cooldown window (shared between MFA and password step 1).
_COOLDOWN_SECONDS = 60

# Maximum failed attempts before the code is deleted and locked out (MFA).
_MAX_ATTEMPTS = 3

# Password lockout configuration.
_PASSWORD_MAX_FAILED_ATTEMPTS = 3
_PASSWORD_LOCKOUT_MINUTES = 15

# Password length constraints.
_PASSWORD_MIN_LENGTH = 12
_PASSWORD_MAX_LENGTH = 128

# Minimum zxcvbn score (0–4). Score 3 = "good", score 4 = "very strong".
_PASSWORD_MIN_ZXCVBN_SCORE = 3

# Reset/setup token validity window.
_RESET_TOKEN_EXPIRY_HOURS = 1

# A bcrypt hash of a static string, computed once at module load.
# Used in the dummy-execution path of verify_login_credentials to ensure
# bcrypt always runs regardless of which failure gate was triggered.
# The specific string hashed is arbitrary — it must never appear in any
# real code or password path.
_DUMMY_HASH: str = bcrypt.hashpw(b"__dummy_hash_input__", bcrypt.gensalt()).decode()


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _fixed_delay(start: float) -> None:
    """
    Block until at least _MIN_RESPONSE_SECONDS have elapsed since start.

    Uses time.sleep (not asyncio.sleep) because the repository calls in
    verify_mfa_code and verify_login_credentials are synchronous psycopg2
    calls. Mixing asyncio.sleep with synchronous code would require
    run_in_executor for the entire function. At current scale this is
    acceptable — revisit if the admin portal ever handles concurrent login
    attempts under load.
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
    - The email does not have a valid format (delegated to is_valid_email_format)
    - The domain is not in the allowed list
    - allowed_domains is empty or blank
    """
    if not is_valid_email_format(email):
        return False
    domain = email.split("@")[1]
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
        logger.warning("auth.verify.user_not_found: %s", email)
        _fixed_delay(start)
        raise INVALID_AUTH_CODE()

    # Stage 2: auth code record.
    record = auth_repo.get_auth_code_record(email)
    if record is None:
        logger.warning("auth.verify.no_code_record: %s", email)
        _fixed_delay(start)
        raise INVALID_AUTH_CODE()

    # Stage 3: lockout check.
    if record["attempts_count"] >= _MAX_ATTEMPTS:
        logger.warning(
            "auth.verify.locked_out: %s — %d failed attempts",
            email,
            record["attempts_count"],
        )
        auth_repo.delete_auth_code(email)
        _fixed_delay(start)
        raise INVALID_AUTH_CODE()

    # Stage 4: expiry check.
    expires_at = record["expires_at"]
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if expires_at < datetime.now(tz=timezone.utc):
        logger.warning("auth.verify.code_expired: %s", email)
        auth_repo.delete_auth_code(email)
        _fixed_delay(start)
        raise INVALID_AUTH_CODE()

    # Stage 5: bcrypt verification.
    if not verify_code(code, record["hashed_code"]):
        new_attempts = record["attempts_count"] + 1
        logger.warning(
            "auth.verify.wrong_code: %s — attempt %d of %d",
            email,
            new_attempts,
            _MAX_ATTEMPTS,
        )
        auth_repo.increment_code_attempts(email)
        _fixed_delay(start)
        raise INVALID_AUTH_CODE()

    # Stage 6: success.
    auth_repo.delete_auth_code(email)
    session_expires_at = datetime.now(tz=timezone.utc) + timedelta(minutes=session_ttl_minutes)
    session_id = auth_repo.create_session(user["id"], session_expires_at)

    logger.info("MFA verification successful for %s — session created", email)
    return session_id


# ---------------------------------------------------------------------------
# Password verification flow
# ---------------------------------------------------------------------------

def verify_login_credentials(
    email: str,
    password: str,
    auth_repo: "AuthRepository",
) -> dict:
    """
    Verify email/password and return the user dict on success.

    Timing-safe design: all fast checks are evaluated first and recorded
    in a flag. A single bcrypt.checkpw() call is then executed against
    either the real hash or a static dummy hash. _fixed_delay(start) is
    called immediately after bcrypt, before any branching on the result.
    This ensures the total response time is always >= _MIN_RESPONSE_SECONDS
    regardless of which gate was hit, and that bcrypt's CPU cost is always
    incurred within that window.

    Raises INVALID_CREDENTIALS (APIError -> 422) on any failure.
    All failure paths raise the same generic error to prevent an attacker
    from learning which gate failed (user not found, wrong password, locked,
    no password set, cooldown).

    Returns the user dict on success.
    """
    start = time.monotonic()
    now = datetime.now(tz=timezone.utc)

    # ------------------------------------------------------------------
    # Fast checks — evaluated before bcrypt, recorded as a flag.
    # ------------------------------------------------------------------
    user = auth_repo.get_user_by_email(email)
    should_use_real_hash = True
    failure_reason: Optional[str] = None

    if user is None:
        should_use_real_hash = False
        failure_reason = "user_not_found"
    else:
        # Cooldown check: re-use the admin_auth_codes table's
        # last_requested_at field. A code requested within the cooldown
        # window means step 1 is already in-flight; block further attempts.
        record = auth_repo.get_auth_code_record(email)
        if record is not None:
            last_requested = record["last_requested_at"]
            if last_requested.tzinfo is None:
                last_requested = last_requested.replace(tzinfo=timezone.utc)
            elapsed = (now - last_requested).total_seconds()
            if elapsed < _COOLDOWN_SECONDS:
                should_use_real_hash = False
                failure_reason = "cooldown"

        # Lockout check.
        if should_use_real_hash:
            locked_until = user.get("password_locked_until")
            if locked_until is not None:
                if locked_until.tzinfo is None:
                    locked_until = locked_until.replace(tzinfo=timezone.utc)
                if locked_until > now:
                    should_use_real_hash = False
                    failure_reason = "locked"

        # No password set yet (invited but not yet set up).
        if should_use_real_hash and user.get("hashed_password") is None:
            should_use_real_hash = False
            failure_reason = "no_password"

    # ------------------------------------------------------------------
    # Single bcrypt call — always executes, against real or dummy hash.
    # ------------------------------------------------------------------
    candidate_hash = user["hashed_password"] if should_use_real_hash else _DUMMY_HASH
    password_correct = bcrypt.checkpw(password.encode(), candidate_hash.encode())

    # ------------------------------------------------------------------
    # Fixed delay — applied immediately after bcrypt, before branching.
    # ------------------------------------------------------------------
    _fixed_delay(start)

    # ------------------------------------------------------------------
    # Outcome handling — after the timing window is closed.
    # ------------------------------------------------------------------
    if not should_use_real_hash:
        logger.warning(
            "auth.login.step1_fast_fail: %s — reason: %s",
            email,
            failure_reason,
        )
        raise INVALID_CREDENTIALS()

    if not password_correct:
        new_attempts = user["failed_password_attempts"] + 1
        lock_until: Optional[datetime] = None
        if new_attempts >= _PASSWORD_MAX_FAILED_ATTEMPTS:
            lock_until = now + timedelta(minutes=_PASSWORD_LOCKOUT_MINUTES)
            logger.warning(
                "auth.login.password_locked: %s — %d failed attempts, "
                "locked until %s",
                email,
                new_attempts,
                lock_until.isoformat(),
            )
        else:
            logger.warning(
                "auth.login.wrong_password: %s — attempt %d of %d",
                email,
                new_attempts,
                _PASSWORD_MAX_FAILED_ATTEMPTS,
            )
        auth_repo.record_failed_password_attempt(user["id"], lock_until=lock_until)
        raise INVALID_CREDENTIALS()

    # Success — reset the attempt counter.
    auth_repo.reset_password_attempts(user["id"])
    logger.info("auth.login.step1_success: %s", email)
    return user


# ---------------------------------------------------------------------------
# Password reset token flow
# ---------------------------------------------------------------------------

def generate_reset_token(
    user_id: str,
    auth_repo: "AuthRepository",
    conn=None,
) -> str:
    """
    Generate a cryptographically random reset/setup token for the given user.

    The raw token is returned to the caller for inclusion in the email link.
    Only the SHA-256 hex digest is stored in the database — raw tokens are
    never persisted.

    Uses upsert (ON CONFLICT DO UPDATE) so that generating a new token for
    a user who already has a pending token atomically replaces the old one.
    There is never a window where two valid tokens exist for the same user.

    conn: passed through to upsert_reset_token for transactional atomicity
    when called from within a POST /users transaction block.
    """
    raw_token = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
    expires_at = datetime.now(tz=timezone.utc) + timedelta(hours=_RESET_TOKEN_EXPIRY_HOURS)

    auth_repo.upsert_reset_token(
        user_id=user_id,
        token_hash=token_hash,
        expires_at=expires_at,
        conn=conn,
    )

    return raw_token


def verify_reset_token(raw_token: str, auth_repo: "AuthRepository") -> str:
    """
    Verify a reset token and return the associated user_id on success.

    Hashes the raw token with SHA-256 and looks up the record. The token
    is deleted immediately on lookup (consumed), ensuring each token can
    only be used once regardless of outcome.

    Raises INVALID_RESET_TOKEN (APIError -> 422) if:
    - No record exists for this token hash (never issued or already used).
    - The token has expired.
    """
    token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
    record = auth_repo.get_reset_token_record(token_hash)

    if record is None:
        raise INVALID_RESET_TOKEN()

    # Delete immediately — consumed tokens cannot be reused even if
    # the expiry check below subsequently fails.
    auth_repo.delete_reset_token(token_hash)

    expires_at = record["expires_at"]
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if expires_at < datetime.now(tz=timezone.utc):
        raise INVALID_RESET_TOKEN()

    return record["user_id"]


# ---------------------------------------------------------------------------
# Password setting flow
# ---------------------------------------------------------------------------

def set_new_password(
    user_id: str,
    password: str,
    auth_repo: "AuthRepository",
) -> None:
    """
    Validate password strength and store a new bcrypt hash for the user.

    The password is validated and hashed exactly as submitted — it is never
    stripped or otherwise normalised. verify_login_credentials does not
    strip the typed password at login either, so normalising it here would
    let a user set a password they could never successfully retype.

    Validation steps:
    1. Enforce length constraints (12–128 characters).
    2. Run zxcvbn strength check — require score >= _PASSWORD_MIN_ZXCVBN_SCORE.
       If the score is too low, raise WEAK_PASSWORD with the first actionable
       suggestion zxcvbn provides.
    3. Hash with bcrypt and persist via auth_repo.set_password, which also
       sets password_changed_at and resets the lockout state atomically.

    Raises INVALID_PAYLOAD if the password is outside the length bounds.
    Raises WEAK_PASSWORD if the zxcvbn score is below the threshold.
    """
    # Import here to keep the module-level import surface minimal.
    # zxcvbn is only used in this function.
    from zxcvbn import zxcvbn  # type: ignore[import]

    if len(password) < _PASSWORD_MIN_LENGTH:
        raise INVALID_PAYLOAD(
            f"Password must be at least {_PASSWORD_MIN_LENGTH} characters."
        )
    if len(password) > _PASSWORD_MAX_LENGTH:
        raise INVALID_PAYLOAD(
            f"Password must not exceed {_PASSWORD_MAX_LENGTH} characters."
        )

    result = zxcvbn(password)
    if result["score"] < _PASSWORD_MIN_ZXCVBN_SCORE:
        # Extract the most actionable feedback string available.
        feedback = result.get("feedback", {})
        suggestions = feedback.get("suggestions", [])
        warning = feedback.get("warning", "")
        if suggestions:
            message = suggestions[0]
        elif warning:
            message = warning
        else:
            message = "Password is too weak. Try a longer or less predictable password."
        raise WEAK_PASSWORD(message)

    hashed = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
    auth_repo.set_password(user_id=user_id, hashed_password=hashed)
    logger.info("auth.password_set: user_id=%s", user_id)
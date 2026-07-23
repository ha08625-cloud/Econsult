"""
Availability evaluation logic.

No database access. No imports from any project module except
app.models.availability_models. Fully testable without a database.

Uses stdlib `logging` only, to warn on malformed exception rows in
evaluate_availability — this is a deliberate, minimal loosening of the
"pure logic" contract (stdlib logging is not IO in the app's sense: no
project module, no database, no network). See the fallback comment in
evaluate_availability for why the warning exists.

Functions:
- validate_availability_config: raises ValueError on invalid config input
- validate_override: raises ValueError on invalid override input
- validate_exception: raises ValueError on invalid exception input
- deactivation_clears_override: returns True if override should be cleared
- evaluate_availability: returns AvailabilityResult from config + current time
"""

import datetime
import logging
from datetime import timedelta

from app.models.availability_models import (
    LONDON_TZ,
    AvailabilityConfig,
    AvailabilityException,
    AvailabilityResult,
)

logger = logging.getLogger(__name__)

VALID_DAYS = {"mon", "tue", "wed", "thu", "fri", "sat", "sun"}

# Day abbreviation mapping: Python weekday() returns 0=Monday..6=Sunday.
_WEEKDAY_TO_ABBR = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]

# Maximum length for admin-authored patient-facing messages (closed_message,
# override_message). Applies equally to both — they serve the same purpose
# and are surfaced through the same UI.
MAX_AVAILABILITY_MESSAGE_LENGTH = 500


def validate_availability_config(
    weekly_open_days: list,
    open_time: datetime.time,
    close_time: datetime.time,
    closed_message: str | None,
) -> None:
    """
    Validate availability configuration values.

    Raises ValueError with a clear message if:
    - weekly_open_days contains any value not in the valid set
    - open_time == close_time
    - open_time >= close_time (overnight hours not supported)
    - closed_message exceeds MAX_AVAILABILITY_MESSAGE_LENGTH characters

    Does not validate weekly_open_days being empty (UI concern only).
    """
    invalid = set(weekly_open_days) - VALID_DAYS
    if invalid:
        raise ValueError(
            f"Invalid day(s) in weekly_open_days: {sorted(invalid)}. "
            f"Valid values are: {sorted(VALID_DAYS)}"
        )

    if open_time == close_time:
        raise ValueError(f"open_time and close_time must not be equal (both are {open_time})")

    if open_time >= close_time:
        raise ValueError(
            f"open_time ({open_time}) must be before close_time ({close_time}). "
            "Overnight hours are not supported."
        )

    if closed_message is not None and len(closed_message) > MAX_AVAILABILITY_MESSAGE_LENGTH:
        raise ValueError(
            f"closed_message must not exceed {MAX_AVAILABILITY_MESSAGE_LENGTH} characters "
            f"(got {len(closed_message)})"
        )


def validate_override(
    status: str,
    expires_at: datetime.datetime | None,
    now_utc: datetime.datetime,
    message: str | None = None,
) -> None:
    """
    Validate override parameters.

    Raises ValueError if:
    - status is not "open" or "closed"
    - expires_at is None
    - expires_at is timezone-naive (no tzinfo)
    - expires_at <= now_utc (must be in the future)
    - expires_at > now_utc + 24 hours (must not exceed 24 hours ahead)
    - message exceeds MAX_AVAILABILITY_MESSAGE_LENGTH characters

    The valid window is: now_utc < expires_at <= now_utc + 24 hours.
    """
    if status not in ("open", "closed"):
        raise ValueError(f"override status must be 'open' or 'closed', got '{status}'")

    if expires_at is None:
        raise ValueError("override expires_at is required")

    if expires_at.tzinfo is None:
        raise ValueError(
            "override expires_at must be timezone-aware. "
            "Submit as a UTC timestamp or with an explicit timezone offset."
        )

    if expires_at <= now_utc:
        raise ValueError("override expires_at must be in the future")

    max_expiry = now_utc + timedelta(hours=24)
    if expires_at > max_expiry:
        raise ValueError("override expires_at must not exceed 24 hours from now")

    if message is not None and len(message) > MAX_AVAILABILITY_MESSAGE_LENGTH:
        raise ValueError(
            f"override message must not exceed {MAX_AVAILABILITY_MESSAGE_LENGTH} characters "
            f"(got {len(message)})"
        )


def validate_exception(
    exception_type: str,
    open_time: datetime.time | None,
    close_time: datetime.time | None,
) -> None:
    """
    Validate exception parameters.

    Raises ValueError if:
    - exception_type is not "closed" or "custom_hours"
    - exception_type is "custom_hours" and either open_time or close_time is None
    - exception_type is "closed" and either open_time or close_time is not None
    - open_time == close_time when both are present
    - open_time >= close_time when both are present (overnight hours not supported)
    """
    if exception_type not in ("closed", "custom_hours"):
        raise ValueError(
            f"exception_type must be 'closed' or 'custom_hours', got '{exception_type}'"
        )

    if exception_type == "custom_hours":
        if open_time is None or close_time is None:
            raise ValueError("custom_hours exception requires both open_time and close_time")
        if open_time == close_time:
            raise ValueError(f"open_time and close_time must not be equal (both are {open_time})")
        if open_time >= close_time:
            raise ValueError(
                f"open_time ({open_time}) must be before close_time ({close_time}). "
                "Overnight hours are not supported."
            )

    if exception_type == "closed" and (open_time is not None or close_time is not None):
        raise ValueError("closed exception must not have open_time or close_time")


def deactivation_clears_override(is_active: bool) -> bool:
    """
    Return True if the override should be cleared.

    When is_active is set to false, any existing override is cleared to
    prevent stale override data from silently taking effect if the admin
    later re-enables is_active.
    """
    return not is_active


def evaluate_availability(
    config: AvailabilityConfig,
    now_utc: datetime.datetime,
    exceptions: list[AvailabilityException] | None = None,
) -> AvailabilityResult:
    """
    Evaluate whether the practice is currently open.

    Takes a typed AvailabilityConfig and the current UTC datetime.
    Optionally takes a list of AvailabilityException entries.
    Returns an AvailabilityResult.

    Evaluation order:
    1. If is_active is false: always open, no messages.
    2. If an active override exists (override_status not null, expires_at > now):
       - "open": return open with after-hours notice from config close_time.
       - "closed": return closed with override_message (or fallback to closed_message).
    3. If a per-date exception exists for today (Europe/London):
       - "closed": return closed with config closed_message.
       - "custom_hours": evaluate exception open_time/close_time against London time.
    4. Otherwise: evaluate weekly schedule.
    """
    if not config.is_active:
        return AvailabilityResult(
            is_open=True,
            closed_message=None,
            after_hours_notice=None,
        )

    # --- Override check ---
    if (
        config.override_status is not None
        and config.override_expires_at is not None
        and config.override_expires_at > now_utc
    ):
        if config.override_status == "open":
            # Override forces open. After-hours notice is still constructed
            # from the config's close time because the override is temporary
            # and the patient should still be aware of the normal schedule.
            after_hours_notice = _build_after_hours_notice(config.close_time)
            return AvailabilityResult(
                is_open=True,
                closed_message=None,
                after_hours_notice=after_hours_notice,
            )
        else:
            # Override forces closed. Use override_message if not None,
            # fall back to closed_message. Explicit `is not None` check —
            # an empty string "" is a valid configured message.
            if config.override_message is not None:
                message = config.override_message
            else:
                message = config.closed_message
            return AvailabilityResult(
                is_open=False,
                closed_message=message,
                after_hours_notice=None,
            )

    # --- Per-date exception check ---
    if exceptions is None:
        exceptions = []

    now_london = now_utc.astimezone(LONDON_TZ)
    today_london = now_london.date()
    current_time = now_london.time()

    for exc in exceptions:
        if exc.exception_date == today_london:
            if exc.exception_type == "closed":
                return AvailabilityResult(
                    is_open=False,
                    closed_message=config.closed_message,
                    after_hours_notice=None,
                )
            # custom_hours
            # Defensive guard: the DB CHECK constraint on
            # practice_availability_exceptions (see migration 0006) should
            # make this unreachable, but a malformed row (e.g. a manual DB
            # edit predating that constraint) must not crash evaluation.
            # Treat it as if no exception exists for today and fall through
            # to the weekly schedule below — this matches the system's
            # existing fail-open philosophy (a data problem must not lock
            # patients out) without inventing a new failure mode.
            if exc.open_time is None or exc.close_time is None:
                logger.warning(
                    "Malformed availability exception for practice_id=%s "
                    "exception_date=%s: exception_type='custom_hours' but "
                    "open_time=%r close_time=%r. Falling through to weekly "
                    "schedule.",
                    config.practice_id,
                    exc.exception_date,
                    exc.open_time,
                    exc.close_time,
                )
                break
            time_open = exc.open_time <= current_time < exc.close_time
            if time_open:
                after_hours_notice = _build_after_hours_notice(exc.close_time)
                return AvailabilityResult(
                    is_open=True,
                    closed_message=None,
                    after_hours_notice=after_hours_notice,
                )
            return AvailabilityResult(
                is_open=False,
                closed_message=config.closed_message,
                after_hours_notice=None,
            )

    # --- Weekly schedule ---
    current_day = _WEEKDAY_TO_ABBR[now_london.weekday()]

    day_open = current_day in config.weekly_open_days
    time_open = config.open_time <= current_time < config.close_time

    if day_open and time_open:
        after_hours_notice = _build_after_hours_notice(config.close_time)
        return AvailabilityResult(
            is_open=True,
            closed_message=None,
            after_hours_notice=after_hours_notice,
        )

    return AvailabilityResult(
        is_open=False,
        closed_message=config.closed_message,
        after_hours_notice=None,
    )


def _build_after_hours_notice(close_time: datetime.time) -> str:
    """
    Construct the after-hours notice string.

    Formats close_time in 24-hour time (e.g. "18:30"), the standard
    convention for UK NHS systems.
    """
    formatted = close_time.strftime("%H:%M")
    return (
        f"Please note: forms submitted after {formatted} will be reviewed on the next working day."
    )

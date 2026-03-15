"""
app/services/availability_service.py — Availability evaluation logic.

No database access. No imports from any project module except
app.models.availability_models. Fully testable without a database.

Functions:
- validate_availability_config: raises ValueError on invalid input
- evaluate_availability: returns AvailabilityResult from config + current time
"""

import datetime
from zoneinfo import ZoneInfo

from app.models.availability_models import AvailabilityConfig, AvailabilityResult

LONDON_TZ = ZoneInfo("Europe/London")

VALID_DAYS = {"mon", "tue", "wed", "thu", "fri", "sat", "sun"}

# Day abbreviation mapping: Python weekday() returns 0=Monday..6=Sunday.
_WEEKDAY_TO_ABBR = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]


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

    Does not validate open_time < close_time (domain constraint against
    overnight hours makes reversed times a self-evident data entry error).
    Does not validate weekly_open_days being empty (UI concern only).
    """
    invalid = set(weekly_open_days) - VALID_DAYS
    if invalid:
        raise ValueError(
            f"Invalid day(s) in weekly_open_days: {sorted(invalid)}. "
            f"Valid values are: {sorted(VALID_DAYS)}"
        )

    if open_time == close_time:
        raise ValueError(
            f"open_time and close_time must not be equal (both are {open_time})"
        )


def evaluate_availability(
    config: AvailabilityConfig,
    now_utc: datetime.datetime,
) -> AvailabilityResult:
    """
    Evaluate whether the practice is currently open.

    Takes a typed AvailabilityConfig and the current UTC datetime.
    Returns an AvailabilityResult.

    Logic:
    1. If is_active is false: always open, no messages.
    2. Convert now_utc to Europe/London time.
    3. Check day is in weekly_open_days.
    4. Check time is >= open_time and < close_time.
    5. If both pass: open with after-hours notice.
    6. Otherwise: closed with closed_message.
    """
    if not config.is_active:
        return AvailabilityResult(
            is_open=True,
            closed_message=None,
            after_hours_notice=None,
        )

    now_london = now_utc.astimezone(LONDON_TZ)
    current_day = _WEEKDAY_TO_ABBR[now_london.weekday()]
    current_time = now_london.time()

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
        f"Please note: forms submitted after {formatted} "
        f"will be reviewed on the next working day."
    )

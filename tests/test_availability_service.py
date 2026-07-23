"""
Unit tests for app.services.admin.availability_service validators and
evaluate_availability.

Pure unit tests — no database, no FastAPI — so this module carries no
integration marker.

Scope: covers the MAX_AVAILABILITY_MESSAGE_LENGTH checks added to
validate_availability_config (closed_message) and validate_override
(message), plus evaluate_availability's fallback behaviour for malformed
custom_hours exception rows (see migration 0006 and the guard comment in
evaluate_availability). Does not re-test the pre-existing day/time
validation rules or the well-formed exception evaluation paths, which are
already covered indirectly via test_admin_availability_router.py.
"""

import datetime
import logging

import pytest

from app.models.availability_models import AvailabilityConfig, AvailabilityException
from app.services.admin.availability_service import (
    MAX_AVAILABILITY_MESSAGE_LENGTH,
    evaluate_availability,
    validate_availability_config,
    validate_override,
)

VALID_DAYS = ["mon", "tue", "wed"]
VALID_OPEN = datetime.time(8, 0)
VALID_CLOSE = datetime.time(18, 0)


# ---------------------------------------------------------------------------
# validate_availability_config: closed_message length
# ---------------------------------------------------------------------------


def test_closed_message_none_passes():
    validate_availability_config(
        weekly_open_days=VALID_DAYS,
        open_time=VALID_OPEN,
        close_time=VALID_CLOSE,
        closed_message=None,
    )


def test_closed_message_at_max_length_passes():
    message = "x" * MAX_AVAILABILITY_MESSAGE_LENGTH
    validate_availability_config(
        weekly_open_days=VALID_DAYS,
        open_time=VALID_OPEN,
        close_time=VALID_CLOSE,
        closed_message=message,
    )


def test_closed_message_over_max_length_raises():
    message = "x" * (MAX_AVAILABILITY_MESSAGE_LENGTH + 1)
    with pytest.raises(ValueError, match="closed_message must not exceed"):
        validate_availability_config(
            weekly_open_days=VALID_DAYS,
            open_time=VALID_OPEN,
            close_time=VALID_CLOSE,
            closed_message=message,
        )


# ---------------------------------------------------------------------------
# validate_override: message length
# ---------------------------------------------------------------------------


def _valid_override_kwargs(message=None):
    now_utc = datetime.datetime.now(datetime.UTC)
    return {
        "status": "closed",
        "expires_at": now_utc + datetime.timedelta(hours=1),
        "now_utc": now_utc,
        "message": message,
    }


def test_override_message_none_passes():
    validate_override(**_valid_override_kwargs(message=None))


def test_override_message_defaults_to_none_when_omitted():
    # message is an optional keyword argument — existing callers that don't
    # pass it at all must continue to work.
    now_utc = datetime.datetime.now(datetime.UTC)
    validate_override(
        status="closed",
        expires_at=now_utc + datetime.timedelta(hours=1),
        now_utc=now_utc,
    )


def test_override_message_at_max_length_passes():
    message = "x" * MAX_AVAILABILITY_MESSAGE_LENGTH
    validate_override(**_valid_override_kwargs(message=message))


def test_override_message_over_max_length_raises():
    message = "x" * (MAX_AVAILABILITY_MESSAGE_LENGTH + 1)
    with pytest.raises(ValueError, match="override message must not exceed"):
        validate_override(**_valid_override_kwargs(message=message))


# ---------------------------------------------------------------------------
# evaluate_availability: malformed custom_hours exception fallback
#
# The DB CHECK constraint added in migration 0006 should make these rows
# unreachable in production, but evaluate_availability must not crash if
# one ever occurs (a bad manual DB edit, a pre-migration row, etc). These
# tests exercise the defensive guard directly, bypassing validate_exception
# entirely — the guard exists precisely for input that never went through
# that validator.
# ---------------------------------------------------------------------------

# Fixed date outside BST (January) so UTC == Europe/London local time and
# the test is not sensitive to daylight-saving offset rules.
_MONDAY = datetime.date(2026, 1, 5)  # weekly_open_days below includes "mon"
_TUESDAY = datetime.date(2026, 1, 6)  # not in weekly_open_days below

_BASE_CONFIG_KWARGS = dict(
    practice_id="test_practice",
    is_active=True,
    weekly_open_days=["mon"],
    open_time=datetime.time(8, 0),
    close_time=datetime.time(18, 0),
    closed_message="We are currently closed.",
    override_status=None,
    override_expires_at=None,
    override_message=None,
)


def _malformed_exception(exception_date, open_time, close_time):
    return AvailabilityException(
        practice_id="test_practice",
        exception_date=exception_date,
        exception_type="custom_hours",
        open_time=open_time,
        close_time=close_time,
        note=None,
    )


@pytest.mark.parametrize(
    "open_time,close_time",
    [
        (None, datetime.time(12, 0)),
        (datetime.time(9, 0), None),
        (None, None),
    ],
    ids=["open_time_none", "close_time_none", "both_none"],
)
def test_malformed_exception_falls_through_to_weekly_open(open_time, close_time):
    # Monday, 12:00 UTC == 12:00 London (outside BST) — within the weekly
    # 08:00-18:00 window on a day the practice is open.
    now_utc = datetime.datetime(2026, 1, 5, 12, 0, tzinfo=datetime.UTC)
    config = AvailabilityConfig(**_BASE_CONFIG_KWARGS)
    exceptions = [_malformed_exception(_MONDAY, open_time, close_time)]

    result = evaluate_availability(config, now_utc, exceptions)

    assert result.is_open is True


@pytest.mark.parametrize(
    "open_time,close_time",
    [
        (None, datetime.time(12, 0)),
        (datetime.time(9, 0), None),
        (None, None),
    ],
    ids=["open_time_none", "close_time_none", "both_none"],
)
def test_malformed_exception_falls_through_to_weekly_closed(open_time, close_time):
    # Tuesday — not in weekly_open_days, so the weekly schedule says closed
    # regardless of time of day.
    now_utc = datetime.datetime(2026, 1, 6, 12, 0, tzinfo=datetime.UTC)
    config = AvailabilityConfig(**_BASE_CONFIG_KWARGS)
    exceptions = [_malformed_exception(_TUESDAY, open_time, close_time)]

    result = evaluate_availability(config, now_utc, exceptions)

    assert result.is_open is False
    assert result.closed_message == "We are currently closed."


def test_malformed_exception_logs_warning(caplog):
    now_utc = datetime.datetime(2026, 1, 5, 12, 0, tzinfo=datetime.UTC)
    config = AvailabilityConfig(**_BASE_CONFIG_KWARGS)
    exceptions = [_malformed_exception(_MONDAY, None, None)]

    with caplog.at_level(logging.WARNING, logger="app.services.admin.availability_service"):
        evaluate_availability(config, now_utc, exceptions)

    assert any("Malformed availability exception" in record.message for record in caplog.records)

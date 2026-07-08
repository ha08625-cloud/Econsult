"""
Unit tests for app.services.admin.availability_service validators.

Pure unit tests — no database, no FastAPI — so this module carries no
integration marker.

Scope: covers the MAX_AVAILABILITY_MESSAGE_LENGTH checks added to
validate_availability_config (closed_message) and validate_override
(message). Does not re-test the pre-existing day/time validation rules,
which are already covered indirectly via test_admin_availability_router.py.
"""

import datetime

import pytest

from app.services.admin.availability_service import (
    MAX_AVAILABILITY_MESSAGE_LENGTH,
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
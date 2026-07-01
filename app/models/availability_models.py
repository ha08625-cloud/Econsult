"""
app/models/availability_models.py — Availability data shapes.

Data shapes only. No logic, no IO, no imports from service modules.

AvailabilityConfig: represents the stored configuration from the
practice_availability table. Includes override fields.

AvailabilityResult: the return type of evaluate_availability(). Consumed
by GET /availability and the availability check inside POST /form/init.

AvailabilityException: represents a single row from the
practice_availability_exceptions table.
"""

import datetime
from dataclasses import dataclass
from zoneinfo import ZoneInfo

# Canonical timezone constant. All availability evaluation uses Europe/London
# local time for schedule matching and date boundary logic. Imported by
# availability_service.py, main.py, and admin_router.py.
LONDON_TZ = ZoneInfo("Europe/London")


@dataclass
class AvailabilityConfig:
    practice_id: str
    is_active: bool
    weekly_open_days: list[str]
    open_time: datetime.time
    close_time: datetime.time
    closed_message: str | None
    # Override fields. All nullable — null means no override.
    override_status: str | None = None
    override_expires_at: datetime.datetime | None = None
    override_message: str | None = None

    @classmethod
    def from_row(cls, row: dict) -> "AvailabilityConfig":
        return cls(
            practice_id=row["practice_id"],
            is_active=row["is_active"],
            weekly_open_days=row["weekly_open_days"],
            open_time=row["open_time"],
            close_time=row["close_time"],
            closed_message=row["closed_message"],
            override_status=row.get("override_status"),
            override_expires_at=row.get("override_expires_at"),
            override_message=row.get("override_message"),
        )


@dataclass
class AvailabilityResult:
    is_open: bool
    closed_message: str | None
    after_hours_notice: str | None


@dataclass
class AvailabilityException:
    practice_id: str
    exception_date: datetime.date
    exception_type: str  # "closed" or "custom_hours"
    open_time: datetime.time | None
    close_time: datetime.time | None
    note: str | None

    @classmethod
    def from_row(cls, row: dict) -> "AvailabilityException":
        return cls(
            practice_id=row["practice_id"],
            exception_date=row["exception_date"],
            exception_type=row["exception_type"],
            open_time=row.get("open_time"),
            close_time=row.get("close_time"),
            note=row.get("note"),
        )

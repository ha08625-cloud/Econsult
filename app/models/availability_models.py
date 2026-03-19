"""
Availability data shapes.

Data shapes only. No logic, no IO, no imports from service modules.

AvailabilityConfig: represents the stored configuration from the
practice_availability table. Includes override fields (Stage 3).

AvailabilityResult: the return type of evaluate_availability(). Consumed
by GET /availability and the availability check inside POST /form/init.

AvailabilityException: represents a single row from the
practice_availability_exceptions table (Stage 4).
"""

from dataclasses import dataclass, field
import datetime
from typing import Optional
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
    closed_message: Optional[str]
    # Override fields (Stage 3). All nullable — null means no override.
    override_status: Optional[str] = None
    override_expires_at: Optional[datetime.datetime] = None
    override_message: Optional[str] = None

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
    closed_message: Optional[str]
    after_hours_notice: Optional[str]


@dataclass
class AvailabilityException:
    practice_id: str
    exception_date: datetime.date
    exception_type: str  # "closed" or "custom_hours"
    open_time: Optional[datetime.time]
    close_time: Optional[datetime.time]
    note: Optional[str]

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

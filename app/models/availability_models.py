"""
app/models/availability_models.py — Availability data shapes.

Data shapes only. No logic, no IO, no imports from service modules.

AvailabilityConfig: represents the stored configuration from the
practice_availability table. Extended in Stage 3 with override fields.

AvailabilityResult: the return type of evaluate_availability(). Consumed
by GET /availability and the availability check inside POST /form/init.
"""

from dataclasses import dataclass
import datetime
from typing import Optional


@dataclass
class AvailabilityConfig:
    practice_id: str
    is_active: bool
    weekly_open_days: list[str]
    open_time: datetime.time
    close_time: datetime.time
    closed_message: Optional[str]

    @classmethod
    def from_row(cls, row: dict) -> "AvailabilityConfig":
        return cls(
            practice_id=row["practice_id"],
            is_active=row["is_active"],
            weekly_open_days=row["weekly_open_days"],
            open_time=row["open_time"],
            close_time=row["close_time"],
            closed_message=row["closed_message"],
        )


@dataclass
class AvailabilityResult:
    is_open: bool
    closed_message: Optional[str]
    after_hours_notice: Optional[str]

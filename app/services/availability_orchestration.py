"""
Availability orchestration.

Wires AvailabilityRepository and availability_service together.
No HTTP logic. No clinical logic.

This module exists because availability_service.py is pure logic (no database
access), and the repository layer has no awareness of the service. Something
must fetch the data and call the service. That something is this module.

This is the same pattern as engine_adapters.py: services contain pure logic,
orchestration lives in a dedicated calling layer.

Fail-open rule: callers are responsible for catching exceptions from
check_availability and treating any failure as "open". This module does not
swallow exceptions — it lets them propagate so callers can log them with
appropriate context.

Imported by:
- app/routers/public_router.py  (GET /availability)
- main.py                       (POST /form/init, POST /form/finish)
"""

from datetime import datetime

from app.models.availability_models import (
    AvailabilityConfig,
    AvailabilityException,
    LONDON_TZ,
)
from app.repositories.availability_repository import AvailabilityRepository
from app.services import availability_service


def check_availability(
    availability_repo: AvailabilityRepository,
    practice_id: str,
    now_utc: datetime,
) -> availability_service.AvailabilityResult:
    """
    Fetch availability config and exceptions, then evaluate current availability.

    Steps:
    1. Fetch config from availability_repo and construct AvailabilityConfig.
    2. Compute today's date in Europe/London time.
    3. Fetch exceptions from today onwards and construct AvailabilityException list.
    4. Call evaluate_availability with config, now_utc, and exceptions.
    5. Return the AvailabilityResult.

    Raises any exception from the repository or service layer — callers must
    catch and apply fail-open logic with appropriate log context.
    """
    row = availability_repo.get_availability(practice_id)
    config = AvailabilityConfig.from_row(row)

    today_london = now_utc.astimezone(LONDON_TZ).date()
    exception_rows = availability_repo.get_exceptions(practice_id, today_london)
    exceptions = [AvailabilityException.from_row(r) for r in exception_rows]

    return availability_service.evaluate_availability(config, now_utc, exceptions)
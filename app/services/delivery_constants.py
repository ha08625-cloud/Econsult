"""
Delivery retry constants.

Defines the backoff schedule and maximum attempt count for delivery retry.
This module has no imports from any other application module.

MAX_ATTEMPTS is derived from the schedule length. It represents the total
number of delivery attempts (first attempt plus all retries). This is the
single canonical expression of the exhaustion threshold. No other module
may define its own maximum.

The backoff schedule is deliberately short (total window ~71 minutes) for
clinical safety. If delivery cannot succeed within this window, alternative
mechanisms (deferred, separate ticket) are required.
"""

RETRY_BACKOFF_MINUTES: list[int] = [1, 10, 60]

MAX_ATTEMPTS: int = len(RETRY_BACKOFF_MINUTES) + 1  # 4
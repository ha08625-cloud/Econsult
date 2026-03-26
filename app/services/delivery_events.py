"""
Structured delivery event constants.

Used by the delivery orchestration layer for consistent logging of delivery
lifecycle events. Each constant is a plain string used as the `event` field
in structured log entries.

This module has no dependencies on any other application module.
"""

DELIVERY_SENT = "delivery_sent"
DELIVERY_FAILED = "delivery_failed"
DELIVERY_EXHAUSTED = "delivery_exhausted"
DELIVERY_RETRY_TOO_EARLY = "delivery_retry_too_early"
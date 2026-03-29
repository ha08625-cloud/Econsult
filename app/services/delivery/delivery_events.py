"""
Delivery lifecycle event constants.

Used by delivery_orchestration.py for structured logging of delivery
attempts, failures, and retry state transitions.

This module has no imports from any other application module.
"""

DELIVERY_SENT = "delivery_sent"
DELIVERY_FAILED = "delivery_failed"
DELIVERY_EXHAUSTED = "delivery_exhausted"
DELIVERY_RETRY_TOO_EARLY = "delivery_retry_too_early"

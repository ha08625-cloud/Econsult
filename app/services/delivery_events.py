"""
Delivery lifecycle event constants.

Used by delivery_orchestration.py for structured logging of delivery
attempts, failures, and retry state transitions.

This module has no imports from any other application module.
"""

DELIVERY_SENT = "delivery.sent"
DELIVERY_FAILED = "delivery.failed"
DELIVERY_EXHAUSTED = "delivery.exhausted"
DELIVERY_RETRY_TOO_EARLY = "delivery.retry_too_early"
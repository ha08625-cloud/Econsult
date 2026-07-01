"""
Telemetry initialisation.

Single entry point for Sentry observability. Called at the top of each
process entry point (main.py, worker_main.py, pdf_worker_main.py,
deletion_job.py) before any other internal application imports.

Design rules:
- This module must NOT import any application repositories, registries,
  service modules, or database configuration. Any such import would create
  a circular dependency or trigger database activity before Sentry is ready.
- All sentry_sdk imports are deferred (inside the function body) so that
  missing or broken sentry-sdk installation never crashes a process that
  has not set SENTRY_DSN.
- Sentry is always disabled in test environments.
  This prevents test-suite HTTP requests and pipeline pollution.
"""

import logging
import os
import sys

logger = logging.getLogger(__name__)


def init_telemetry(app_context: str) -> None:
    """
    Initialise Sentry for the given process context.

    app_context is a short label used to tag events by process type,
    e.g. "http-api", "pdf-worker", "delivery-worker", "deletion-cron".

    Returns immediately (no-op) if:
    - pytest is loaded in sys.modules (test environment)
    - TEST_DATABASE_URL is set (integration test environment)
    - SENTRY_DSN is absent (graceful fallback — logs a warning)

    FastAPIIntegration is included only when app_context == "http-api".
    Workers must not use it — they run infinite loops, not request/response
    cycles, and the ASGI integration is not meaningful for them.

    traces_sample_rate is set to 0.0 for all contexts. The while True
    worker loops would otherwise be treated as a single hanging transaction.
    """
    # --- Test environment bypass ---
    if "pytest" in sys.modules or os.environ.get("TEST_DATABASE_URL"):
        return

    # --- Graceful fallback if DSN is absent ---
    dsn = os.environ.get("SENTRY_DSN")
    if not dsn:
        logger.warning(
            "SENTRY_DSN not set — telemetry disabled for context '%s'",
            app_context,
        )
        return

    try:
        import sentry_sdk  # noqa: PLC0415

        integrations = []

        if app_context == "http-api":
            from sentry_sdk.integrations.fastapi import FastAPIIntegration  # noqa: PLC0415
            from sentry_sdk.integrations.logging import LoggingIntegration  # noqa: PLC0415
            from slowapi.errors import RateLimitExceeded  # noqa: PLC0415

            from app.core.errors import APIError, ConditionNotFound, RateLimitError  # noqa: PLC0415

            integrations = [
                FastAPIIntegration(
                    transaction_style="endpoint",
                    failed_request_status_codes=[500, 502, 503],
                ),
                LoggingIntegration(
                    level=logging.ERROR,
                    event_level=logging.CRITICAL,
                ),
            ]
            ignore_errors = [APIError, ConditionNotFound, RateLimitError, RateLimitExceeded]
        else:
            from sentry_sdk.integrations.logging import LoggingIntegration  # noqa: PLC0415

            integrations = [
                LoggingIntegration(
                    level=logging.ERROR,
                    event_level=logging.CRITICAL,
                ),
            ]
            ignore_errors = []

        sentry_sdk.init(
            dsn=dsn,
            integrations=integrations,
            ignore_errors=ignore_errors,
            # PII lockdown — multipart payloads containing clinical JSON and
            # patient photos must never reach Sentry.
            send_default_pii=False,
            request_bodies="never",
            with_locals=False,
            # Disable tracing. Workers run infinite loops which would be
            # treated as a single hanging transaction. HTTP tracing is also
            # not needed at this stage.
            traces_sample_rate=0.0,
            # Tag every event with the originating process type.
            release=os.environ.get("RAILWAY_DEPLOYMENT_ID"),
            environment=os.environ.get("RAILWAY_ENVIRONMENT_NAME", "production"),
            server_name=app_context,
        )

        logger.info(
            "Sentry initialised for context '%s'",
            app_context,
        )

    except Exception as exc:
        # A broken Sentry configuration must never crash the application.
        logger.error(
            "Failed to initialise Sentry for context '%s': %s",
            app_context,
            exc,
        )

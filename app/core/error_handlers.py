"""
Centralised exception handler registration for the FastAPI app.

Stage 3 of the configuration refactor: a pure relocation. The four
handlers below were moved verbatim from main.py. register_error_handlers
attaches them to the app in place of the previous @app.exception_handler
decorators; behaviour, status codes, and response envelopes are unchanged.

The error envelope contract (status code primary, body shape secondary)
is described per-handler below and is unchanged from the original.
"""

from fastapi import FastAPI, HTTPException
from fastapi.exception_handlers import http_exception_handler as _default_http_handler
from fastapi.responses import JSONResponse
from slowapi.errors import RateLimitExceeded

from app.core.errors import APIError, RateLimitError, ConditionNotFound


def register_error_handlers(app: FastAPI) -> None:
    """Attach all application exception handlers to the given app."""

    @app.exception_handler(APIError)
    async def api_error_handler(_, exc: APIError):
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": {"code": exc.code, "message": exc.message}},
        )

    @app.exception_handler(ConditionNotFound)
    async def condition_not_found_handler(_, exc: ConditionNotFound):
        return JSONResponse(
            status_code=404,
            content={"error": {"code": "CONDITION_NOT_FOUND", "message": f"Unknown condition: {exc}"}},
        )

    @app.exception_handler(RateLimitError)
    async def rate_limit_handler(_, exc: RateLimitError):
        return JSONResponse(
            status_code=429,
            content={"error": {"code": "RATE_LIMIT_EXCEEDED", "message": str(exc)}},
        )

    @app.exception_handler(RateLimitExceeded)
    async def slowapi_rate_limit_handler(_, exc: RateLimitExceeded):
        # Catches requests rejected by @limiter.limit() decorators (slowapi).
        # Returns the same error envelope as the service-layer RateLimitError handler
        # above so the frontend always receives a consistent 429 response shape.
        return JSONResponse(
            status_code=429,
            content={
                "error": {
                    "code": "RATE_LIMIT_EXCEEDED",
                    "message": "Too many requests. Please try again later.",
                }
            },
        )

    @app.exception_handler(HTTPException)
    async def http_exception_envelope_handler(request, exc: HTTPException):
        # Reshape 401 responses into the standard error envelope so the frontend
        # has a consistent body shape across all error types. The HTTP status code
        # is the primary contract for session expiry — this handler is the single
        # place that enforces the secondary (body) contract for 401s.
        # All other HTTP exceptions pass through to FastAPI's default handler
        # unchanged — we do not want to interfere with 404s, 422s from Pydantic, etc.
        if exc.status_code == 401:
            return JSONResponse(
                status_code=401,
                content={"error": {"code": "UNAUTHORIZED", "message": exc.detail}},
            )
        return await _default_http_handler(request, exc)
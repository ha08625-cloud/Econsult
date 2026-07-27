"""
app/core/body_capture.py

BodyCapturingRoute and read_json_body are a pair (D9,
documentation/planned_updates/ticket_event_loop_body_handlers.md).

A plain `def` handler is dispatched by FastAPI onto the anyio threadpool,
which is how blocking database/bcrypt/network calls inside it get off the
event loop — but a plain `def` cannot `await request.json()` to read its own
body. BodyCapturingRoute reads the raw body once, in the async route wrapper
that runs before the handler, and stashes it on `request.state.raw_body`.
The handler then reconstructs it synchronously via read_json_body.

A router only gets this behaviour if it is constructed with
`APIRouter(route_class=BodyCapturingRoute)`. A plain `def` handler on a
router without it has no `raw_body` to read; read_json_body raises
BodyNotCaptured with an explicit message instead of a bare AttributeError.
"""

import json
from collections.abc import Callable

from fastapi import Request, Response
from fastapi.routing import APIRoute

from app.core.errors import INVALID_PAYLOAD


class BodyNotCaptured(Exception):
    """Raised when read_json_body is called on a request whose router was
    not constructed with route_class=BodyCapturingRoute."""


class BodyCapturingRoute(APIRoute):
    def get_route_handler(self) -> Callable:
        original = super().get_route_handler()

        async def custom_handler(request: Request) -> Response:
            request.state.raw_body = await request.body()
            return await original(request)

        return custom_handler


def read_json_body(request: Request, parse_float=None):
    """
    Return the parsed JSON body captured by BodyCapturingRoute.

    Raises BodyNotCaptured if the route this request matched was not
    constructed with route_class=BodyCapturingRoute.
    Raises INVALID_PAYLOAD("Invalid JSON body") if the captured bytes are
    not valid JSON, matching the error the old `await request.json()` +
    try/except sites raised.
    """
    raw_body = getattr(request.state, "raw_body", None)
    if raw_body is None:
        raise BodyNotCaptured(
            "request.state.raw_body is not set. The router for this handler "
            "must be constructed with APIRouter(route_class=BodyCapturingRoute)."
        )

    try:
        return json.loads(raw_body, parse_float=parse_float)
    except Exception as exc:
        raise INVALID_PAYLOAD("Invalid JSON body") from exc

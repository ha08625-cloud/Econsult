"""
Tests for app/core/max_body_size_route.py.

Pins the DoS-hardening fix: a request whose Content-Length header exceeds
MAX_FINISH_REQUEST_BYTES must be rejected with 413 before the wrapped
handler ever runs -- proving the check happens in the route wrapper, ahead
of dependency resolution / body parsing, not inside the handler body.

No database required. Run with: make test
"""

import unittest

from fastapi import APIRouter, FastAPI
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

from app.core.errors import APIError
from app.core.max_body_size_route import MaxBodySizeRoute
from app.core.upload_constants import MAX_FINISH_REQUEST_BYTES


def _register_error_handlers(app: FastAPI):
    @app.exception_handler(APIError)
    async def api_error_handler(_, exc: APIError):
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": {"code": exc.code, "message": exc.message}},
        )


class TestMaxBodySizeRoute(unittest.TestCase):
    def _client(self, handler_calls: list):
        app = FastAPI()
        _register_error_handlers(app)
        router = APIRouter(route_class=MaxBodySizeRoute)

        @router.post("/echo")
        def echo():
            handler_calls.append(True)
            return {"ok": True}

        app.include_router(router)
        return TestClient(app, raise_server_exceptions=True)

    def test_request_at_the_limit_is_accepted(self):
        handler_calls: list = []
        client = self._client(handler_calls)
        body = b"x" * MAX_FINISH_REQUEST_BYTES
        res = client.post("/echo", content=body)
        self.assertEqual(res.status_code, 200)
        self.assertEqual(handler_calls, [True])

    def test_request_over_the_limit_is_rejected_with_413(self):
        handler_calls: list = []
        client = self._client(handler_calls)
        body = b"x" * (MAX_FINISH_REQUEST_BYTES + 1)
        res = client.post("/echo", content=body)
        self.assertEqual(res.status_code, 413)
        self.assertEqual(res.json()["error"]["code"], "PAYLOAD_TOO_LARGE")

    def test_handler_never_runs_when_content_length_exceeds_limit(self):
        # The point of the check: reject before the wrapped handler --
        # and by extension, before dependency resolution / body parsing --
        # ever executes.
        handler_calls: list = []
        client = self._client(handler_calls)
        body = b"x" * (MAX_FINISH_REQUEST_BYTES + 1)
        client.post("/echo", content=body)
        self.assertEqual(handler_calls, [])

    def test_missing_content_length_is_not_rejected_by_this_check(self):
        # Chunked transfer-encoding (no Content-Length) is documented as an
        # explicit gap: this header check cannot catch it, so it must not
        # raise on a request the header is simply absent from.
        handler_calls: list = []
        client = self._client(handler_calls)

        def _chunks():
            yield b"small body"

        res = client.post("/echo", content=_chunks())
        self.assertEqual(res.status_code, 200)
        self.assertEqual(handler_calls, [True])

    def test_non_integer_content_length_is_not_rejected_by_this_check(self):
        handler_calls: list = []
        client = self._client(handler_calls)
        res = client.post("/echo", content=b"small", headers={"content-length": "not-a-number"})
        self.assertEqual(res.status_code, 200)
        self.assertEqual(handler_calls, [True])


if __name__ == "__main__":
    unittest.main()

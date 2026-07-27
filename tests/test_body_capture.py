"""
Tests for app/core/body_capture.py.

Pins the D9 footgun mitigation: a plain `def` handler registered on a router
that was NOT constructed with route_class=BodyCapturingRoute must fail via
read_json_body's named error, not a bare AttributeError.
"""

import unittest
from decimal import Decimal

from fastapi import APIRouter, FastAPI, Request
from fastapi.testclient import TestClient

from app.core.body_capture import BodyCapturingRoute, read_json_body
from app.core.errors import APIError


def _register_error_handlers(app: FastAPI):
    from fastapi.responses import JSONResponse

    @app.exception_handler(APIError)
    async def api_error_handler(_, exc: APIError):
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": {"code": exc.code, "message": exc.message}},
        )


class TestReadJsonBodyWithoutCapturingRoute(unittest.TestCase):
    def test_named_error_not_attribute_error(self):
        app = FastAPI()
        router = APIRouter()  # deliberately no route_class=BodyCapturingRoute

        @router.post("/echo")
        def echo(request: Request):
            return read_json_body(request)

        app.include_router(router)
        client = TestClient(app, raise_server_exceptions=False)

        res = client.post("/echo", json={"a": 1})
        self.assertEqual(res.status_code, 500)


class TestReadJsonBodyWithCapturingRoute(unittest.TestCase):
    def _client(self):
        app = FastAPI()
        _register_error_handlers(app)
        router = APIRouter(route_class=BodyCapturingRoute)

        @router.post("/echo")
        def echo(request: Request):
            return read_json_body(request)

        app.include_router(router)
        return TestClient(app, raise_server_exceptions=True)

    def test_valid_json_round_trips(self):
        client = self._client()
        res = client.post("/echo", json={"a": 1})
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json(), {"a": 1})

    def test_malformed_json_raises_invalid_payload(self):
        client = self._client()
        res = client.post(
            "/echo",
            content=b"{not valid json",
            headers={"content-type": "application/json"},
        )
        self.assertEqual(res.status_code, 422)
        self.assertEqual(res.json()["error"]["code"], "INVALID_PAYLOAD")


class TestReadJsonBodyParseFloat(unittest.TestCase):
    """
    Pins form_update's Decimal requirement: read_json_body(request,
    parse_float=Decimal) must parse Number fields as exact Decimals rather
    than lossy floats.
    """

    def test_parse_float_decimal_is_exact(self):
        app = FastAPI()
        _register_error_handlers(app)
        router = APIRouter(route_class=BodyCapturingRoute)

        captured = {}

        @router.post("/echo")
        def echo(request: Request):
            body = read_json_body(request, parse_float=Decimal)
            captured["weight"] = body["weight"]
            return {"ok": True}

        app.include_router(router)
        client = TestClient(app, raise_server_exceptions=True)

        res = client.post(
            "/echo", content=b'{"weight": 70.15}', headers={"content-type": "application/json"}
        )
        self.assertEqual(res.status_code, 200)
        self.assertEqual(captured["weight"], Decimal("70.15"))
        self.assertIsInstance(captured["weight"], Decimal)


if __name__ == "__main__":
    unittest.main()

"""
Tests for GET /practice endpoint in public_router.py.

Uses a stub practice repo and a bare FastAPI app — no database required.

Run from project root:
    python -m pytest tests/test_practice_endpoint.py
"""

import unittest

# ---------------------------------------------------------------------------
# Stubs
# ---------------------------------------------------------------------------


class StubPracticeRepo:
    def __init__(self, practice=None):
        self._practice = practice

    def get_practice(self, practice_id: str):
        return self._practice


# ---------------------------------------------------------------------------
# App factory
# ---------------------------------------------------------------------------


def make_test_app(practice=None, practice_id="test_practice"):
    from fastapi import FastAPI

    from app.routers.public_router import router as public_router

    app = FastAPI()
    app.include_router(public_router)

    app.state.practice_id = practice_id
    app.state.practice_repo = StubPracticeRepo(practice=practice)

    # Stubs for other dependencies used by other routes on the same router.
    # These are never called by the /practice endpoint but must exist to
    # satisfy FastAPI's dependency injection at app build time.
    class _StubRegistry:
        def list_conditions(self):
            return []

        def has_condition(self, _):
            return False

    class _StubPresentationService:
        def get_universal_safety_warning(self):
            return ""

        def get_patient_presentation(self, *_):
            return {}

    class _StubAvailabilityRepo:
        pass

    app.state.registry = _StubRegistry()
    app.state.presentation_service = _StubPresentationService()
    app.state.availability_repo = _StubAvailabilityRepo()

    return app


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestGetPracticeEndpoint(unittest.TestCase):
    def test_returns_200_and_practice_name(self):
        from fastapi.testclient import TestClient

        app = make_test_app(
            practice={
                "practice_id": "test_practice",
                "name": "Elm Tree Surgery",
                "email": "test@example.com",
            }
        )
        client = TestClient(app, raise_server_exceptions=True)

        res = client.get("/practice")

        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json(), {"practice_name": "Elm Tree Surgery"})

    def test_returns_500_when_practice_not_found(self):
        from fastapi.testclient import TestClient

        app = make_test_app(practice=None)
        client = TestClient(app, raise_server_exceptions=False)

        res = client.get("/practice")

        self.assertEqual(res.status_code, 500)


if __name__ == "__main__":
    unittest.main()

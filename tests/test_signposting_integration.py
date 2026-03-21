"""
Step 6 — Backend integration tests for the signposting feature.

These tests exercise the complete backend stack:
    HTTP request -> admin_router -> practice_repository -> SQLite -> response

They use a minimal FastAPI app with the real admin_router, real
PracticeRepository, and a stub ConditionRegistry. The presentation
endpoint is also tested to confirm the patient-facing response
reflects the new str | None type rather than list | None.

These tests do NOT test HTML sanitisation behaviour (test_sanitise_signposting.py)
or database-layer behaviour in isolation (test_practice_repository_signposting.py).
They test the HTTP contract: status codes, response shapes, and the
end-to-end round-trip through the full request/response cycle.

Run from the project root:
    python -m pytest tests/test_signposting_integration.py -v

Requires nh3 and httpx:
    pip install nh3 httpx
"""

import pytest
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

from app.routers.admin_router import router as admin_router
from app.core.admin_context import AdminContext, require_admin
from app.repositories.practice_repository import PracticeRepository, MAX_SIGNPOSTING_LENGTH
from app.services.presentation_service import PresentationService
from app.core.condition_registry import ConditionNotFound


PRACTICE_ID = "test-practice"
CONDITION_ID = "uti1"


# ---------------------------------------------------------------------------
# Minimal condition registry stub
# ---------------------------------------------------------------------------

class _StubRegistry:
    def has_condition(self, cid: str) -> bool:
        return cid == CONDITION_ID

    def list_conditions(self):
        return [{"id": CONDITION_ID, "label": "Urinary symptoms"}]

    def get_presentation(self, cid: str) -> dict:
        if cid != CONDITION_ID:
            raise ConditionNotFound(cid)
        return {"label": "Urinary symptoms", "free_text_prompt": "Describe your symptoms"}

    def get_ruleset_path(self, cid: str) -> str:
        raise ConditionNotFound(cid)


# ---------------------------------------------------------------------------
# App factory
# ---------------------------------------------------------------------------

def _make_app(tmp_path):
    app = FastAPI()
    app.include_router(admin_router, prefix="/admin")

    repo = PracticeRepository(str(tmp_path / "test.db"))
    repo.create_practice(PRACTICE_ID, "Test Practice", "test@example.com")

    registry = _StubRegistry()
    presentation_svc = PresentationService(registry, repo)

    app.state.practice_repo = repo
    app.state.registry = registry
    app.state.practice_id = PRACTICE_ID

    app.dependency_overrides[require_admin] = lambda: AdminContext(
        practice_id=PRACTICE_ID,
        auth_method="dev_any",
    )

    # Patient-facing presentation endpoint — mirrors main.py
    @app.get("/conditions/{condition_id}/presentation")
    async def get_presentation(condition_id: str):
        try:
            return presentation_svc.get_patient_presentation(
                condition_id,
                app.state.practice_id,
            )
        except ConditionNotFound:
            return JSONResponse(status_code=404, content={"error": "not found"})

    return app


@pytest.fixture
def client(tmp_path):
    return TestClient(_make_app(tmp_path))


# ---------------------------------------------------------------------------
# PUT valid HTML -> GET returns same HTML
# ---------------------------------------------------------------------------

def test_put_valid_html_then_get_returns_html(client):
    html = "<p>Call us on <strong>0800 123 456</strong> for an appointment.</p>"
    r = client.put(
        f"/admin/conditions/{CONDITION_ID}/signposting",
        json={"signposting": html},
    )
    assert r.status_code == 200

    r2 = client.get(f"/admin/conditions/{CONDITION_ID}/signposting")
    assert r2.status_code == 200
    saved = r2.json()["signposting"]
    assert saved is not None
    assert "0800 123 456" in saved
    assert "<strong>" in saved


# ---------------------------------------------------------------------------
# PUT empty content -> row deleted -> GET returns null
# ---------------------------------------------------------------------------

def test_put_empty_string_returns_null_signposting(client):
    client.put(
        f"/admin/conditions/{CONDITION_ID}/signposting",
        json={"signposting": "<p>content</p>"},
    )
    r = client.put(
        f"/admin/conditions/{CONDITION_ID}/signposting",
        json={"signposting": ""},
    )
    assert r.status_code == 200
    assert r.json()["signposting"] is None

    r2 = client.get(f"/admin/conditions/{CONDITION_ID}/signposting")
    assert r2.json()["signposting"] is None


def test_put_quill_empty_output_returns_null(client):
    client.put(
        f"/admin/conditions/{CONDITION_ID}/signposting",
        json={"signposting": "<p>content</p>"},
    )
    r = client.put(
        f"/admin/conditions/{CONDITION_ID}/signposting",
        json={"signposting": "<p></p>"},
    )
    assert r.status_code == 200
    assert r.json()["signposting"] is None


# ---------------------------------------------------------------------------
# PUT with javascript: href — accepted at HTTP level, href stripped silently
# ---------------------------------------------------------------------------

def test_put_javascript_href_accepted_href_stripped(client):
    """
    A javascript: href is a sanitisation concern, not a validation error.
    The request is accepted (HTTP 200). The stored HTML has the href removed.
    The router must not return HTTP 400 for this input.
    """
    r = client.put(
        f"/admin/conditions/{CONDITION_ID}/signposting",
        json={"signposting": '<p><a href="javascript:alert(1)">click here</a></p>'},
    )
    assert r.status_code == 200
    saved = r.json()["signposting"]
    if saved is not None:
        assert "javascript:" not in saved


# ---------------------------------------------------------------------------
# PUT with script tag — accepted, tag stripped silently
# ---------------------------------------------------------------------------

def test_put_script_tag_accepted_tag_stripped(client):
    r = client.put(
        f"/admin/conditions/{CONDITION_ID}/signposting",
        json={"signposting": "<p>visible</p><script>alert(1)</script>"},
    )
    assert r.status_code == 200
    saved = r.json()["signposting"]
    assert saved is not None
    assert "<script>" not in saved
    assert "alert(1)" not in saved
    assert "visible" in saved


# ---------------------------------------------------------------------------
# PUT overlength -> HTTP 400
# ---------------------------------------------------------------------------

def test_put_overlength_returns_400(client):
    r = client.put(
        f"/admin/conditions/{CONDITION_ID}/signposting",
        json={"signposting": "a" * (MAX_SIGNPOSTING_LENGTH + 1)},
    )
    assert r.status_code == 400
    assert "5000" in r.json()["detail"]


def test_put_exactly_max_length_returns_200(client):
    padding = "a" * (MAX_SIGNPOSTING_LENGTH - len("<p></p>"))
    raw = f"<p>{padding}</p>"
    raw = raw[:MAX_SIGNPOSTING_LENGTH]
    r = client.put(
        f"/admin/conditions/{CONDITION_ID}/signposting",
        json={"signposting": raw},
    )
    assert r.status_code == 200


# ---------------------------------------------------------------------------
# PUT wrong types -> HTTP 400
# ---------------------------------------------------------------------------

def test_put_missing_key_returns_400(client):
    r = client.put(
        f"/admin/conditions/{CONDITION_ID}/signposting",
        json={"other": "value"},
    )
    assert r.status_code == 400


def test_put_signposting_as_list_returns_400(client):
    r = client.put(
        f"/admin/conditions/{CONDITION_ID}/signposting",
        json={"signposting": ["item one", "item two"]},
    )
    assert r.status_code == 400


# ---------------------------------------------------------------------------
# DELETE -> GET returns null
# ---------------------------------------------------------------------------

def test_delete_then_get_returns_null(client):
    client.put(
        f"/admin/conditions/{CONDITION_ID}/signposting",
        json={"signposting": "<p>content</p>"},
    )
    r = client.delete(f"/admin/conditions/{CONDITION_ID}/signposting")
    assert r.status_code == 204

    r2 = client.get(f"/admin/conditions/{CONDITION_ID}/signposting")
    assert r2.json()["signposting"] is None


# ---------------------------------------------------------------------------
# PUT after DELETE -> restores content
# ---------------------------------------------------------------------------

def test_put_after_delete_restores_content(client):
    client.put(
        f"/admin/conditions/{CONDITION_ID}/signposting",
        json={"signposting": "<p>original</p>"},
    )
    client.delete(f"/admin/conditions/{CONDITION_ID}/signposting")
    client.put(
        f"/admin/conditions/{CONDITION_ID}/signposting",
        json={"signposting": "<p>restored</p>"},
    )
    r = client.get(f"/admin/conditions/{CONDITION_ID}/signposting")
    assert "restored" in r.json()["signposting"]


# ---------------------------------------------------------------------------
# Patient-facing presentation endpoint reflects new str | None type
# ---------------------------------------------------------------------------

def test_presentation_returns_null_signposting_when_none_configured(client):
    r = client.get(f"/conditions/{CONDITION_ID}/presentation")
    assert r.status_code == 200
    data = r.json()
    assert "practice_signposting" in data
    assert data["practice_signposting"] is None


def test_presentation_returns_html_string_after_put(client):
    client.put(
        f"/admin/conditions/{CONDITION_ID}/signposting",
        json={"signposting": "<p>Information from your practice.</p>"},
    )
    r = client.get(f"/conditions/{CONDITION_ID}/presentation")
    assert r.status_code == 200
    data = r.json()
    signposting = data["practice_signposting"]
    assert signposting is not None
    assert isinstance(signposting, str)
    # Must be a string, not a list — this is the key type change
    assert not isinstance(signposting, list)
    assert "Information from your practice" in signposting


def test_presentation_returns_null_after_content_cleared(client):
    client.put(
        f"/admin/conditions/{CONDITION_ID}/signposting",
        json={"signposting": "<p>content</p>"},
    )
    client.put(
        f"/admin/conditions/{CONDITION_ID}/signposting",
        json={"signposting": ""},
    )
    r = client.get(f"/conditions/{CONDITION_ID}/presentation")
    assert r.json()["practice_signposting"] is None
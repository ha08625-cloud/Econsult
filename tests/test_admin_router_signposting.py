"""
Tests for admin_router.py signposting endpoints.

Uses FastAPI's TestClient with a minimal app state. The condition registry
and practice repository are real objects backed by an in-memory / tmp SQLite
database. The admin auth dependency is bypassed by overriding require_admin.

Run from the project root:
    python -m pytest tests/test_admin_router_signposting.py -v

Requires nh3 and fastapi[testclient] (starlette):
    pip install nh3 httpx
"""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from admin_router import router
from admin_context import AdminContext, require_admin
from practice_repository import PracticeRepository, MAX_SIGNPOSTING_LENGTH


PRACTICE_ID = "test-practice"
CONDITION_ID = "uti1"          # must match a condition in the registry


# ---------------------------------------------------------------------------
# Minimal condition registry stub
# ---------------------------------------------------------------------------

class _StubRegistry:
    """Minimal registry that only answers has_condition."""
    def has_condition(self, condition_id: str) -> bool:
        return condition_id == CONDITION_ID

    def list_conditions(self):
        return [{"id": CONDITION_ID, "label": "Urinary symptoms"}]


# ---------------------------------------------------------------------------
# App factory
# ---------------------------------------------------------------------------

def _make_app(tmp_path):
    app = FastAPI()
    app.include_router(router, prefix="/admin")

    repo = PracticeRepository(str(tmp_path / "test.db"))
    repo.create_practice(PRACTICE_ID, "Test Practice", "test@example.com")

    app.state.practice_repo = repo
    app.state.registry = _StubRegistry()
    app.state.practice_id = PRACTICE_ID

    # Override auth so tests do not need a real token
    app.dependency_overrides[require_admin] = lambda: AdminContext(
        practice_id=PRACTICE_ID,
        auth_method="dev_any",
    )

    return app


@pytest.fixture
def client(tmp_path):
    app = _make_app(tmp_path)
    return TestClient(app)


# ---------------------------------------------------------------------------
# GET — no content configured
# ---------------------------------------------------------------------------

def test_get_returns_null_when_nothing_configured(client):
    r = client.get(f"/admin/conditions/{CONDITION_ID}/signposting")
    assert r.status_code == 200
    data = r.json()
    assert data["condition_id"] == CONDITION_ID
    assert data["signposting"] is None


def test_get_unknown_condition_returns_404(client):
    r = client.get("/admin/conditions/unknown-condition/signposting")
    assert r.status_code == 404


# ---------------------------------------------------------------------------
# PUT — valid content
# ---------------------------------------------------------------------------

def test_put_valid_html_returns_200_with_content(client):
    r = client.put(
        f"/admin/conditions/{CONDITION_ID}/signposting",
        json={"signposting": "<p>Call us on <strong>0800 123 456</strong>.</p>"},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["condition_id"] == CONDITION_ID
    assert data["signposting"] is not None
    assert isinstance(data["signposting"], str)


def test_put_then_get_returns_same_content(client):
    html = "<p>Refer yourself to physio via <a href=\"https://example.com\">this link</a>.</p>"
    client.put(
        f"/admin/conditions/{CONDITION_ID}/signposting",
        json={"signposting": html},
    )
    r = client.get(f"/admin/conditions/{CONDITION_ID}/signposting")
    assert r.status_code == 200
    saved = r.json()["signposting"]
    assert saved is not None
    assert "Refer yourself" in saved


def test_put_response_reflects_sanitised_content_not_raw_input(client):
    """
    The PUT response must show what was stored after sanitisation,
    not the raw input. A javascript: href should be stripped.
    """
    r = client.put(
        f"/admin/conditions/{CONDITION_ID}/signposting",
        json={"signposting": '<p><a href="javascript:alert(1)">click</a></p>'},
    )
    assert r.status_code == 200
    saved = r.json()["signposting"]
    # The response reflects what is in the database: javascript: is gone.
    if saved is not None:
        assert "javascript:" not in saved


# ---------------------------------------------------------------------------
# PUT — empty content clears signposting
# ---------------------------------------------------------------------------

def test_put_empty_string_clears_signposting(client):
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


def test_put_quill_empty_output_clears_signposting(client):
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


def test_put_empty_on_empty_database_returns_null(client):
    r = client.put(
        f"/admin/conditions/{CONDITION_ID}/signposting",
        json={"signposting": ""},
    )
    assert r.status_code == 200
    assert r.json()["signposting"] is None


# ---------------------------------------------------------------------------
# PUT — input validation errors
# ---------------------------------------------------------------------------

def test_put_missing_signposting_key_returns_400(client):
    r = client.put(
        f"/admin/conditions/{CONDITION_ID}/signposting",
        json={"other_key": "value"},
    )
    assert r.status_code == 400


def test_put_signposting_as_list_returns_400(client):
    r = client.put(
        f"/admin/conditions/{CONDITION_ID}/signposting",
        json={"signposting": ["item one", "item two"]},
    )
    assert r.status_code == 400


def test_put_signposting_as_integer_returns_400(client):
    r = client.put(
        f"/admin/conditions/{CONDITION_ID}/signposting",
        json={"signposting": 42},
    )
    assert r.status_code == 400


def test_put_overlength_returns_400(client):
    r = client.put(
        f"/admin/conditions/{CONDITION_ID}/signposting",
        json={"signposting": "a" * (MAX_SIGNPOSTING_LENGTH + 1)},
    )
    assert r.status_code == 400
    assert "5000" in r.json()["detail"]


def test_put_exactly_max_length_returns_200(client):
    # Build a string of exactly MAX_SIGNPOSTING_LENGTH characters that
    # contains real content so nh3 does not strip it to empty.
    padding = "a" * (MAX_SIGNPOSTING_LENGTH - len("<p></p>"))
    raw = f"<p>{padding}</p>"
    raw = raw[:MAX_SIGNPOSTING_LENGTH]
    r = client.put(
        f"/admin/conditions/{CONDITION_ID}/signposting",
        json={"signposting": raw},
    )
    assert r.status_code == 200


def test_put_unknown_condition_returns_404(client):
    r = client.put(
        "/admin/conditions/unknown-condition/signposting",
        json={"signposting": "<p>text</p>"},
    )
    assert r.status_code == 404


# ---------------------------------------------------------------------------
# DELETE
# ---------------------------------------------------------------------------

def test_delete_returns_204(client):
    client.put(
        f"/admin/conditions/{CONDITION_ID}/signposting",
        json={"signposting": "<p>content</p>"},
    )
    r = client.delete(f"/admin/conditions/{CONDITION_ID}/signposting")
    assert r.status_code == 204


def test_delete_then_get_returns_null(client):
    client.put(
        f"/admin/conditions/{CONDITION_ID}/signposting",
        json={"signposting": "<p>content</p>"},
    )
    client.delete(f"/admin/conditions/{CONDITION_ID}/signposting")
    r = client.get(f"/admin/conditions/{CONDITION_ID}/signposting")
    assert r.json()["signposting"] is None


def test_delete_is_idempotent(client):
    client.delete(f"/admin/conditions/{CONDITION_ID}/signposting")
    r = client.delete(f"/admin/conditions/{CONDITION_ID}/signposting")
    assert r.status_code == 204


def test_put_after_delete_restores_content(client):
    client.put(
        f"/admin/conditions/{CONDITION_ID}/signposting",
        json={"signposting": "<p>content</p>"},
    )
    client.delete(f"/admin/conditions/{CONDITION_ID}/signposting")
    client.put(
        f"/admin/conditions/{CONDITION_ID}/signposting",
        json={"signposting": "<p>restored</p>"},
    )
    r = client.get(f"/admin/conditions/{CONDITION_ID}/signposting")
    assert r.json()["signposting"] is not None
    assert "restored" in r.json()["signposting"]


def test_delete_unknown_condition_returns_404(client):
    r = client.delete("/admin/conditions/unknown-condition/signposting")
    assert r.status_code == 404
"""
Import-surface regression guard for app/core/admin_context.py.

admin_context is a security boundary that deliberately depends on the
AuthProvider abstraction rather than the concrete repository/wiring
modules (dependency inversion), so that importing it does not pull in the
heavy repository-and-service closure that app/core/dependencies.py and
app/core/wiring.py load at module import time. See app/core/state_keys.py
and the admin_context module docstring.

This must run in a SUBPROCESS. An in-process check
(assert "app.repositories..." not in sys.modules) is unreliable under
pytest: other tests import main, which imports everything, so by the time
this test runs those modules are already in the shared sys.modules
regardless of what admin_context imports. The assertion would then pass or
fail on test ordering, not on admin_context's actual import surface. A
clean interpreter is the only robust form.

The subprocess's importability of `app` is hardened explicitly via cwd and
PYTHONPATH derived from this file's location (tests/ -> repo root), rather
than relying on `python -m pytest` happening to prepend the cwd. This
keeps the test correct if pytest is invoked from another directory or with
PYTHONSAFEPATH set.
"""

import os
import subprocess
import sys

from fastapi.testclient import TestClient

from tests.helpers.admin_test_helpers import StubAuthRepo, make_test_app


def test_admin_context_import_surface_stays_minimal():
    # tests/test_admin_context.py -> tests/ -> repo root
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    code = (
        "import app.core.admin_context, sys; "
        "leaked = sorted(m for m in sys.modules "
        "if m.startswith(('app.repositories', 'app.services')) "
        "or m in ('app.core.dependencies', 'app.core.wiring')); "
        "assert not leaked, leaked"
    )
    env = dict(os.environ)
    env["PYTHONPATH"] = repo_root + os.pathsep + env.get("PYTHONPATH", "")
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=repo_root,
        env=env,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr


# ---------------------------------------------------------------------------
# require_admin — sliding-window session refresh
# ---------------------------------------------------------------------------


class RefreshSpyAuthRepo(StubAuthRepo):
    """StubAuthRepo that records update_session_expiry calls, and can be
    made to raise to exercise the best-effort refresh failure path."""

    def __init__(self, raise_on_refresh=False):
        super().__init__()
        self.raise_on_refresh = raise_on_refresh
        self.refresh_calls = []

    def update_session_expiry(self, session_id, ttl_minutes):
        self.refresh_calls.append((session_id, ttl_minutes))
        if self.raise_on_refresh:
            raise RuntimeError("simulated DB failure")


def test_require_admin_refreshes_session_and_resets_cookie():
    from app.core.admin_context import SESSION_COOKIE_MAX_AGE, SESSION_TTL_MINUTES

    auth_repo = RefreshSpyAuthRepo()
    app = make_test_app(auth_repo=auth_repo)
    client = TestClient(app)

    response = client.get(
        "/admin/audit-log",
        cookies={"session_id": "test-session-id"},
    )

    assert response.status_code == 200
    assert auth_repo.refresh_calls == [("test-session-id", SESSION_TTL_MINUTES)]

    set_cookie = response.headers.get("set-cookie")
    assert set_cookie is not None
    assert "session_id=test-session-id" in set_cookie
    assert f"Max-Age={SESSION_COOKIE_MAX_AGE}" in set_cookie
    assert "HttpOnly" in set_cookie
    assert "samesite=strict" in set_cookie.lower()


def test_require_admin_refresh_failure_does_not_break_request():
    auth_repo = RefreshSpyAuthRepo(raise_on_refresh=True)
    app = make_test_app(auth_repo=auth_repo)
    client = TestClient(app)

    response = client.get(
        "/admin/audit-log",
        cookies={"session_id": "test-session-id"},
    )

    # The request still succeeds even though the refresh raised.
    assert response.status_code == 200
    assert auth_repo.refresh_calls  # refresh was attempted


def test_require_admin_still_401s_without_refresh_attempt():
    auth_repo = RefreshSpyAuthRepo()
    app = make_test_app(auth_repo=auth_repo)
    client = TestClient(app)

    response = client.get(
        "/admin/audit-log",
        cookies={"session_id": "wrong-session-id"},
    )

    assert response.status_code == 401
    assert auth_repo.refresh_calls == []

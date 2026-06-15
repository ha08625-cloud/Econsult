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

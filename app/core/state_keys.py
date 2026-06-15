"""
Canonical names of attributes stored on app.state at startup.

This is a leaf module by design: it imports nothing (not stdlib, not
FastAPI, not any project module) so that import-light modules can depend
on it without pulling in a heavy import closure.

Why this module exists
-----------------------
app.state attributes are populated by app/core/wiring.py (via
unpack_container, keyed on AppContainer's dataclass field names) and read
back by the getters in app/core/dependencies.py. For attributes read ONLY
inside dependencies.py, the getter <-> field-name contract is pinned by
tests/test_wiring.py, so a literal string in a getter is safe: a rename
that desyncs the getter from the container field fails CI.

The exception is any attribute that must also be read by a module which
deliberately does NOT import the wiring closure. app/core/admin_context.py
is such a module: it is a security boundary that depends on the
AuthProvider abstraction rather than the concrete repository/wiring
modules (dependency inversion), keeping its import surface minimal because
it may be imported early in the startup chain. admin_context cannot import
the get_auth_repo getter without dragging in the entire repository-and-
service closure that dependencies.py loads at import time.

That leaves exactly one fragility: the app.state key for the auth
repository is referenced in two places that share no import path
(dependencies.get_auth_repo and admin_context.require_admin). Defining it
once here, and having both reference it, removes the silent-drift risk (a
wiring rename would otherwise break admin_context at runtime with an
AttributeError that masquerades as a 401) without coupling admin_context
to the wiring closure.

Only keys read across that import boundary belong here. Keys read solely
within dependencies.py stay as literals there, guarded by the wiring
contract test.

The value MUST equal the corresponding AppContainer field name in
app/core/wiring.py. tests/test_wiring.py enforces this for AUTH_REPO via
get_auth_repo, which routes through this constant.
"""

# Must equal AppContainer.auth_repo's field name in app/core/wiring.py.
AUTH_REPO = "auth_repo"

"""
Unit tests for app/core/wiring.py.

Pure unit tests: no database, no integration marker.

The getter-contract test is the load-bearing one. dependencies.py getters
read flat attributes from app.state; main.py populates app.state by
unpacking an AppContainer via dataclasses.fields(). The contract that
makes this safe is: every getter named get_X in dependencies.py must have
a container field named X. This test enumerates the getters dynamically,
so adding a getter to dependencies.py without adding the matching
container field fails CI -- nobody has to remember to update this file.

build_container itself is not unit-tested here: it constructs real
repositories and runs DB-backed checks, and is exercised end-to-end by
the existing integration tests that import main (test_public_routes.py,
test_form_routes.py).
"""

import dataclasses
import inspect
from types import SimpleNamespace

from fastapi import FastAPI

import app.core.dependencies as dependencies
from app.core.wiring import AppContainer, unpack_container


def _stub_container() -> AppContainer:
    """
    An AppContainer with a unique sentinel object in every field.

    Field types are not enforced at runtime by dataclasses, so plain
    object() sentinels are sufficient and keep this test free of stubs
    for eleven repositories.
    """
    kwargs = {field.name: object() for field in dataclasses.fields(AppContainer)}
    return AppContainer(**kwargs)


def _getters():
    """All functions named get_* defined in dependencies.py itself."""
    return [
        (name, func)
        for name, func in inspect.getmembers(dependencies, inspect.isfunction)
        if name.startswith("get_") and func.__module__ == dependencies.__name__
    ]


def test_dependencies_module_has_getters():
    # Guard against the enumeration silently matching nothing (e.g. after
    # a module rename), which would make the contract test vacuous.
    assert len(_getters()) >= 17


def test_every_getter_has_a_matching_container_field_and_returns_it():
    container = _stub_container()
    app = FastAPI()
    unpack_container(app, container)
    request = SimpleNamespace(app=app)

    field_names = {field.name for field in dataclasses.fields(AppContainer)}

    for name, getter in _getters():
        expected_field = name[len("get_"):]
        assert expected_field in field_names, (
            f"dependencies.{name} has no matching AppContainer field "
            f"'{expected_field}'. Add the field to AppContainer in "
            "app/core/wiring.py (and populate it in build_container), or "
            "rename the getter to follow the get_<field> convention."
        )
        result = getter(request)
        assert result is getattr(container, expected_field), (
            f"dependencies.{name} did not return the container's "
            f"'{expected_field}' object."
        )


def test_unpack_container_copies_every_field():
    container = _stub_container()
    app = FastAPI()
    unpack_container(app, container)
    for field in dataclasses.fields(AppContainer):
        assert getattr(app.state, field.name) is getattr(container, field.name)


def test_container_is_frozen():
    container = _stub_container()
    try:
        container.practice_id = "mutated"  # type: ignore[misc]
    except dataclasses.FrozenInstanceError:
        return
    raise AssertionError("AppContainer must be frozen")

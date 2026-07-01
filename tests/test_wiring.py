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

build_container's DB phase is not unit-tested here: it constructs real
repositories and runs DB-backed checks, and is exercised end-to-end by
the existing integration tests that import main (test_public_routes.py,
test_form_routes.py). Its ruleset-validation phase, however, runs before
any repository is constructed, so it IS unit-tested below without a
database.
"""

import dataclasses
import inspect
import json
from types import SimpleNamespace

import pytest
from fastapi import FastAPI

import app.core.dependencies as dependencies
from app.core.wiring import AppContainer, build_container, unpack_container


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
        expected_field = name[len("get_") :]
        assert expected_field in field_names, (
            f"dependencies.{name} has no matching AppContainer field "
            f"'{expected_field}'. Add the field to AppContainer in "
            "app/core/wiring.py (and populate it in build_container), or "
            "rename the getter to follow the get_<field> convention."
        )
        result = getter(request)
        assert result is getattr(container, expected_field), (
            f"dependencies.{name} did not return the container's '{expected_field}' object."
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


# ---------------------------------------------------------------------------
# Startup ruleset validation
# ---------------------------------------------------------------------------
#
# These tests prove that build_container validates the full clinical ruleset
# at startup, before any repository is constructed. The invalid-ruleset case
# must abort startup; the valid case must get past validation and only then
# fail later when it reaches the database (which these unit tests do not
# provide). Both assertions rely on the validation running in the config-file
# phase, ahead of DB access.


# A ruleset whose presentation block is valid (so ConditionRegistry accepts it
# at construction) but whose clinical body is invalid: the safety rule points
# at an answer_key that no question declares. validate_ruleset rejects this.
_CLINICALLY_INVALID_RULESET = {
    "condition_id": "broken_demo",
    "presentation": {"label": "Broken Demo"},
    "questions": [
        {
            "question_id": "q1",
            "question": "Do you have a fever?",
            "answer_key": "has_fever",
            "answer_type": "Boolean",
            "send_to_encoder": False,
            "encoder_prompt": None,
        }
    ],
    "safety": {
        "rules": {
            "r1": {
                "any": [{"is_true": "key_that_does_not_exist"}],
                "message": "unreachable",
            }
        }
    },
}

_VALID_RULESET = {
    "condition_id": "valid_demo",
    "presentation": {"label": "Valid Demo"},
    "questions": [
        {
            "question_id": "q1",
            "question": "Do you have a fever?",
            "answer_key": "has_fever",
            "answer_type": "Boolean",
            "send_to_encoder": False,
            "encoder_prompt": None,
        }
    ],
    "safety": {"rules": {}},
}


def _write_ruleset(directory, ruleset: dict) -> None:
    path = directory / f"{ruleset['condition_id']}.json"
    path.write_text(json.dumps(ruleset))


def _settings_for(data_dir) -> SimpleNamespace:
    # build_container reads DATABASE_URL and PRACTICE_ID before constructing
    # the registry, and data_dir when constructing it. Nothing else is touched
    # before ruleset validation runs, so a lightweight stub is sufficient and
    # keeps these tests free of a real WebSettings and its environment.
    return SimpleNamespace(
        DATABASE_URL="postgresql://unused/unused",
        PRACTICE_ID="test_practice",
        data_dir=str(data_dir),
    )


def test_build_container_aborts_on_clinically_invalid_ruleset(tmp_path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    _write_ruleset(data_dir, _CLINICALLY_INVALID_RULESET)

    with pytest.raises(RuntimeError) as excinfo:
        build_container(_settings_for(data_dir))

    message = str(excinfo.value)
    # The condition is named so an operator can find the offending file, and
    # the underlying validate_ruleset reason is preserved.
    assert "broken_demo" in message
    assert "key_that_does_not_exist" in message


def test_build_container_passes_ruleset_validation_for_valid_rulesets(tmp_path):
    # A valid ruleset must survive the validation phase. We cannot assert a
    # successful build here (that needs a database), so we assert that the
    # failure, if any, is NOT a ruleset validation failure -- i.e. execution
    # got past validate_rulesets and only stumbled later, at repository or
    # DB-backed construction.
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    _write_ruleset(data_dir, _VALID_RULESET)

    with pytest.raises(Exception) as excinfo:
        build_container(_settings_for(data_dir))

    assert "Ruleset validation failed" not in str(excinfo.value)

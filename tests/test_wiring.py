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

The quantity_kind registry-parity section below is a different kind of
wiring test: ruleset.QUANTITY_KINDS, form_logic._NON_CANONICAL_CONVERTERS,
and pdf_formatter._QUANTITY_FORMATTERS are three tables, in three layers,
that must agree on the same set of quantity kinds. They cannot import each
other to enforce this directly -- pdf_formatter.py is presentation and must
not import the core engine -- so a cross-module test is the only place the
contract can be checked at all. It lives here, alongside the other
startup-adjacent contract checks, rather than in test_ruleset.py or
test_pdf_formatter.py, because it is about agreement between modules, not
about the behaviour of any one of them.
"""

import dataclasses
import inspect
import json
from types import SimpleNamespace

import pytest
from fastapi import FastAPI

import app.core.dependencies as dependencies
import app.services.engine.ruleset as ruleset
import app.utils.pdf_formatter as pdf_formatter
from app.core.wiring import AppContainer, build_container, unpack_container
from app.services.engine.form_logic import _NON_CANONICAL_CONVERTERS


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


# ---------------------------------------------------------------------------
# quantity_kind registry parity
#
# ruleset.QUANTITY_KINDS is the single source of truth for which quantity
# kinds exist. form_logic._NON_CANONICAL_CONVERTERS and
# pdf_formatter._QUANTITY_FORMATTERS are parallel tables in other layers that
# must stay in step with it. Neither can import ruleset.py to enforce this
# directly (form_logic.py already does; pdf_formatter.py must not, since
# presentation must not import the core engine), so this is the only place
# the three-way contract can be checked. Pulling in pdf_formatter here pulls
# fpdf into an otherwise dependency-light file, which is acceptable since
# fpdf is already a hard dependency of the project.
# ---------------------------------------------------------------------------


def test_quantity_kinds_registry_is_non_empty():
    # Guards against the assertions below becoming vacuous if the registry
    # were ever emptied.
    assert len(ruleset.QUANTITY_KINDS) > 0


def test_pdf_formatter_table_matches_quantity_kinds_registry():
    assert set(ruleset.QUANTITY_KINDS) == set(pdf_formatter._QUANTITY_FORMATTERS)


def test_every_quantity_kind_canonical_system_is_a_declared_system():
    for kind in ruleset.QUANTITY_KINDS:
        canonical = ruleset.canonical_system(kind)
        assert canonical in ruleset.QUANTITY_KINDS[kind]["systems"], (
            f"quantity_kind '{kind}' has canonical_system '{canonical}', which "
            "is not a key of its own systems map."
        )


def test_every_quantity_kind_canonical_system_has_exactly_one_component():
    # The direct (no-conversion) storage path assumes the canonical system's
    # value is a single scalar. A compound kind (e.g. blood pressure) needs a
    # different seam, per design decision 2 in the implementation plan; this
    # assertion is a tripwire so such a kind cannot be added to the registry
    # without that seam being built first.
    for kind in ruleset.QUANTITY_KINDS:
        canonical = ruleset.canonical_system(kind)
        components = ruleset.component_keys(kind, canonical)
        assert len(components) == 1, (
            f"quantity_kind '{kind}' has canonical system '{canonical}' with "
            f"{len(components)} components {components}; the canonical system "
            "must map to exactly one component key."
        )


def test_non_canonical_converters_match_registry_exactly():
    # Every (kind, system) pair other than the canonical one must have a
    # converter, and the converter table must contain no pair the registry
    # does not declare (a stale converter left behind after a kind or system
    # is removed).
    expected_pairs = {
        (kind, system)
        for kind, spec in ruleset.QUANTITY_KINDS.items()
        for system in spec["systems"]
        if system != spec["canonical_system"]
    }
    assert set(_NON_CANONICAL_CONVERTERS) == expected_pairs

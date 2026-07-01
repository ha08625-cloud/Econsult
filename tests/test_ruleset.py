"""
Unit tests for Number-question and answer_type validation in ruleset.py.

These assert the fail-fast startup contract: a malformed Number question or an
unknown/missing answer_type must raise. Pure unit tests — no integration marker.
"""

import copy
import json

import pytest

from app.services.engine.ruleset import load_ruleset, validate_ruleset


def _base_ruleset():
    return {
        "condition_id": "demo",
        "presentation": {"label": "Demo", "free_text_prompt": "x"},
        "questions": [
            {
                "question_id": "q1",
                "question": "What is your weight in kg?",
                "answer_key": "weight",
                "answer_type": "Number",
                "decimal_places": 1,
                "min": 2,
                "max": 400,
                "send_to_encoder": False,
                "encoder_prompt": None,
            }
        ],
        "safety": {"rules": {}},
    }


def _with(**overrides):
    rs = copy.deepcopy(_base_ruleset())
    rs["questions"][0].update(overrides)
    return rs


def _without(key):
    rs = copy.deepcopy(_base_ruleset())
    del rs["questions"][0][key]
    return rs


# ---------------------------------------------------------------------------
# Accept
# ---------------------------------------------------------------------------


def test_accepts_valid_number_question():
    validate_ruleset(_base_ruleset())


def test_accepts_authored_range_warning_text():
    validate_ruleset(_with(range_warning_text="That value is unusual, please check."))


def test_accepts_decimal_places_zero():
    validate_ruleset(_with(decimal_places=0, min=2, max=400))


# ---------------------------------------------------------------------------
# answer_type allow-list
# ---------------------------------------------------------------------------


def test_rejects_unknown_answer_type():
    with pytest.raises(ValueError):
        validate_ruleset(_with(answer_type="Integer"))


def test_rejects_missing_answer_type():
    with pytest.raises(ValueError):
        validate_ruleset(_without("answer_type"))


# ---------------------------------------------------------------------------
# Number field validation
# ---------------------------------------------------------------------------


def test_rejects_missing_decimal_places():
    with pytest.raises(ValueError):
        validate_ruleset(_without("decimal_places"))


def test_rejects_negative_decimal_places():
    with pytest.raises(ValueError):
        validate_ruleset(_with(decimal_places=-1))


def test_rejects_bool_decimal_places():
    with pytest.raises(ValueError):
        validate_ruleset(_with(decimal_places=True))


def test_rejects_missing_min():
    with pytest.raises(ValueError):
        validate_ruleset(_without("min"))


def test_rejects_missing_max():
    with pytest.raises(ValueError):
        validate_ruleset(_without("max"))


def test_rejects_non_numeric_max():
    with pytest.raises(ValueError):
        validate_ruleset(_with(max="big"))


def test_rejects_min_not_less_than_max():
    with pytest.raises(ValueError):
        validate_ruleset(_with(min=400, max=2))


def test_rejects_bound_finer_than_decimal_places():
    with pytest.raises(ValueError):
        validate_ruleset(_with(decimal_places=0, min=2.5, max=400))


def test_rejects_non_string_range_warning_text():
    with pytest.raises(ValueError):
        validate_ruleset(_with(range_warning_text=123))


# ---------------------------------------------------------------------------
# Quantity (unit-toggle) field validation
# ---------------------------------------------------------------------------


def test_accepts_valid_quantity_question():
    validate_ruleset(
        _with(
            quantity=True,
            allowed_systems=["metric", "imperial"],
            default_system="metric",
        )
    )


def test_accepts_quantity_with_single_system():
    validate_ruleset(_with(quantity=True, allowed_systems=["metric"], default_system="metric"))


def test_accepts_quantity_false_without_unit_fields():
    # Explicit quantity=False is fine as long as the unit fields are absent.
    validate_ruleset(_with(quantity=False))


def test_rejects_non_boolean_quantity():
    with pytest.raises(ValueError, match="non-boolean quantity"):
        validate_ruleset(_with(quantity="yes"))


def test_rejects_quantity_on_non_number_question():
    with pytest.raises(ValueError, match="not a Number question"):
        validate_ruleset(
            _with(
                answer_type="text",
                quantity=True,
                allowed_systems=["metric"],
                default_system="metric",
            )
        )


def test_rejects_quantity_missing_allowed_systems():
    with pytest.raises(ValueError, match="non-empty allowed_systems"):
        validate_ruleset(_with(quantity=True, default_system="metric"))


def test_rejects_quantity_empty_allowed_systems():
    with pytest.raises(ValueError, match="non-empty allowed_systems"):
        validate_ruleset(_with(quantity=True, allowed_systems=[], default_system="metric"))


def test_rejects_unknown_allowed_system():
    with pytest.raises(ValueError, match="unknown allowed_systems"):
        validate_ruleset(
            _with(quantity=True, allowed_systems=["metric", "nautical"], default_system="metric")
        )


def test_rejects_duplicate_allowed_systems():
    with pytest.raises(ValueError, match="duplicate allowed_systems"):
        validate_ruleset(
            _with(quantity=True, allowed_systems=["metric", "metric"], default_system="metric")
        )


def test_rejects_default_system_not_in_allowed():
    with pytest.raises(ValueError, match="default_system"):
        validate_ruleset(
            _with(quantity=True, allowed_systems=["metric"], default_system="imperial")
        )


def test_rejects_missing_default_system():
    with pytest.raises(ValueError, match="default_system"):
        validate_ruleset(_with(quantity=True, allowed_systems=["metric"]))


def test_rejects_allowed_systems_on_non_quantity_question():
    # Unit fields set without the quantity flag would be silently ignored, so
    # they are rejected outright.
    with pytest.raises(ValueError, match="must not set allowed_systems"):
        validate_ruleset(_with(allowed_systems=["metric"]))


def test_rejects_default_system_on_non_quantity_question():
    with pytest.raises(ValueError, match="must not set default_system"):
        validate_ruleset(_with(default_system="metric"))


# ---------------------------------------------------------------------------
# Caching
# ---------------------------------------------------------------------------


def test_load_ruleset_caches_by_path(tmp_path):
    """
    Two loads of the same path must return the same object, not just an
    equal one -- this is what proves the file was read from disk once,
    not re-parsed on the second call.
    """
    path = tmp_path / "demo.json"
    path.write_text(json.dumps(_base_ruleset()))

    first = load_ruleset(str(path))
    second = load_ruleset(str(path))

    assert first is second

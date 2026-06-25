"""
Unit tests for Number-question and answer_type validation in ruleset.py.

These assert the fail-fast startup contract: a malformed Number question or an
unknown/missing answer_type must raise. Pure unit tests — no integration marker.
"""

import copy

import pytest

from app.services.engine.ruleset import validate_ruleset


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
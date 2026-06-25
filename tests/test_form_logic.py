"""
Unit tests for the Number answer type in form_logic.

Covers validate_required_answers (accept and reject tiers) and
normalise_number_answers. Pure unit tests — no database, no FastAPI — so this
module carries no integration marker.
"""

from decimal import Decimal

import pytest

from app.models.runtime_state import RuntimeState, AnswerState, SafetyEvaluation
from app.services.engine.form_logic import (
    validate_required_answers,
    normalise_number_answers,
    AnswerValidationError,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _number_ruleset(decimal_places: int = 1):
    return {
        "condition_id": "demo",
        "questions": [
            {
                "question_id": "q1",
                "question": "What is your weight in kg?",
                "answer_key": "weight",
                "answer_type": "Number",
                "decimal_places": decimal_places,
                "min": 2,
                "max": 400,
                "send_to_encoder": False,
                "encoder_prompt": None,
            }
        ],
        "safety": {"rules": {}},
    }


def _runtime(value):
    return RuntimeState(
        condition_id="demo",
        ruleset_version="hash",
        free_text="",
        additional_text=None,
        answers={
            "weight": AnswerState(
                value=value,
                source="patient",
                encoder_value=None,
                answer_type="number",
            )
        },
        safety_evaluation=SafetyEvaluation(),
        metadata={},
    )


# ---------------------------------------------------------------------------
# validate_required_answers — accept
# ---------------------------------------------------------------------------

def test_accepts_decimal_at_exact_precision():
    validate_required_answers(_runtime(Decimal("70.5")), _number_ruleset(1))


def test_accepts_decimal_below_allowed_precision():
    validate_required_answers(_runtime(Decimal("70.5")), _number_ruleset(2))


def test_accepts_integer_when_decimal_places_zero():
    validate_required_answers(_runtime(7), _number_ruleset(0))


def test_accepts_integer_when_decimals_allowed():
    validate_required_answers(_runtime(70), _number_ruleset(1))


def test_range_is_not_enforced_here():
    # min/max are a non-blocking client warning; validation must not reject
    # an out-of-range value.
    validate_required_answers(_runtime(Decimal("999.9")), _number_ruleset(1))


# ---------------------------------------------------------------------------
# validate_required_answers — reject
# ---------------------------------------------------------------------------

def test_rejects_missing_number():
    with pytest.raises(AnswerValidationError):
        validate_required_answers(_runtime(None), _number_ruleset(1))


def test_rejects_string_value():
    with pytest.raises(AnswerValidationError):
        validate_required_answers(_runtime("70.5"), _number_ruleset(1))


def test_rejects_bool_value():
    # isinstance(True, int) is True in Python; the bool exclusion must be
    # explicit, so this is asserted directly.
    with pytest.raises(AnswerValidationError):
        validate_required_answers(_runtime(True), _number_ruleset(1))


def test_rejects_list_value():
    with pytest.raises(AnswerValidationError):
        validate_required_answers(_runtime([70.5]), _number_ruleset(1))


def test_rejects_dict_value():
    with pytest.raises(AnswerValidationError):
        validate_required_answers(_runtime({"v": 70.5}), _number_ruleset(1))


def test_rejects_too_many_decimals():
    with pytest.raises(AnswerValidationError):
        validate_required_answers(_runtime(Decimal("70.55")), _number_ruleset(1))


def test_rejects_decimal_when_whole_numbers_required():
    with pytest.raises(AnswerValidationError):
        validate_required_answers(_runtime(Decimal("70.5")), _number_ruleset(0))


def test_rejects_non_finite_decimal():
    with pytest.raises(AnswerValidationError):
        validate_required_answers(_runtime(Decimal("NaN")), _number_ruleset(1))


def test_answer_validation_error_is_a_value_error():
    # Subclassing ValueError keeps existing `pytest.raises(ValueError)` green.
    with pytest.raises(ValueError):
        validate_required_answers(_runtime(None), _number_ruleset(1))


# ---------------------------------------------------------------------------
# normalise_number_answers
# ---------------------------------------------------------------------------

def _normalised(value):
    rt = _runtime(value)
    normalise_number_answers(rt)
    return rt.answers["weight"].value


def test_normalise_decimal_to_plain_string():
    assert _normalised(Decimal("70.5")) == "70.5"


def test_normalise_preserves_trailing_zero():
    assert _normalised(Decimal("70.50")) == "70.50"


def test_normalise_integer_to_string():
    assert _normalised(70) == "70"


def test_normalise_canonicalises_exponential_notation():
    assert _normalised(Decimal("7e1")) == "70"


def test_normalise_leaves_none_untouched():
    assert _normalised(None) is None


def test_normalise_ignores_non_number_answers():
    rt = RuntimeState(
        condition_id="demo",
        ruleset_version="hash",
        free_text="",
        additional_text=None,
        answers={
            "has_pain": AnswerState(True, "patient", None, "boolean"),
            "notes": AnswerState("hello", "patient", None, "text"),
        },
        safety_evaluation=SafetyEvaluation(),
        metadata={},
    )
    normalise_number_answers(rt)
    assert rt.answers["has_pain"].value is True
    assert rt.answers["notes"].value == "hello"
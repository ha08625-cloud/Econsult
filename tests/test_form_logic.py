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
    apply_patient_answers,
    normalise_encoder_provenance,
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
# validate_required_answers — unknown answer_type (corrupted persisted state)
#
# answer_type is only a Literal type *hint* on the AnswerState dataclass; it
# is never enforced at runtime. RuntimeState.from_dict will happily rebuild a
# state from a legacy or corrupted JSONB row carrying any string here. The
# else branch must raise rather than silently skip the check.
# ---------------------------------------------------------------------------

def test_rejects_unknown_answer_type():
    rt = RuntimeState(
        condition_id="demo",
        ruleset_version="hash",
        free_text="",
        additional_text=None,
        answers={
            "weight": AnswerState(
                value=70,
                source="patient",
                encoder_value=None,
                answer_type="decimal",  # not "boolean"/"text"/"number"
            )
        },
        safety_evaluation=SafetyEvaluation(),
        metadata={},
    )
    with pytest.raises(AnswerValidationError):
        validate_required_answers(rt, _number_ruleset(1))


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


# ---------------------------------------------------------------------------
# apply_patient_answers / normalise_encoder_provenance — provenance
#
# source is a pure function of (value, encoder_value):
#   encoder_value is None        -> "patient"
#   value == encoder_value       -> "encoder_correct"
#   value != encoder_value       -> "encoder_incorrect"
# ---------------------------------------------------------------------------

def _bool_runtime(source, encoder_value, value=None):
    """Single-boolean RuntimeState for provenance tests."""
    return RuntimeState(
        condition_id="demo",
        ruleset_version="hash",
        free_text="",
        additional_text=None,
        answers={
            "flag": AnswerState(
                value=value,
                source=source,
                encoder_value=encoder_value,
                answer_type="boolean",
            )
        },
        safety_evaluation=SafetyEvaluation(),
        metadata={},
    )


def _apply(source, encoder_value, value):
    rt = _bool_runtime(source=source, encoder_value=encoder_value)
    apply_patient_answers(rt, {"flag": value})
    return rt.answers["flag"]


def test_apply_no_encoder_suggestion_is_patient():
    # encoder_value None: answer is patient-owned regardless of value.
    assert _apply(source="unanswered", encoder_value=None, value=True).source == "patient"


def test_apply_value_matches_true_suggestion_is_correct():
    assert _apply(source="encoder", encoder_value=True, value=True).source == "encoder_correct"


def test_apply_value_differs_from_true_suggestion_is_incorrect():
    assert _apply(source="encoder", encoder_value=True, value=False).source == "encoder_incorrect"


def test_apply_value_matches_false_suggestion_is_correct():
    assert _apply(source="encoder", encoder_value=False, value=False).source == "encoder_correct"


def test_apply_value_differs_from_false_suggestion_is_incorrect():
    assert _apply(source="encoder", encoder_value=False, value=True).source == "encoder_incorrect"


def test_apply_revert_to_matching_value_returns_to_correct():
    # Headline behaviour this ticket adds: an answer previously recorded as
    # encoder_incorrect, re-set to match the encoder's suggestion, becomes
    # encoder_correct. Under the old event model this transition was impossible.
    rt = _bool_runtime(source="encoder_incorrect", encoder_value=True)
    apply_patient_answers(rt, {"flag": True})
    assert rt.answers["flag"].source == "encoder_correct"


def test_apply_is_idempotent():
    # Re-applying the same value yields the same source. This is what makes the
    # client round-tripping the whole answers map every update safe.
    rt = _bool_runtime(source="encoder", encoder_value=True)
    apply_patient_answers(rt, {"flag": False})
    first = rt.answers["flag"].source
    apply_patient_answers(rt, {"flag": False})
    assert rt.answers["flag"].source == first == "encoder_incorrect"


def test_apply_does_not_mutate_encoder_value():
    # The surviving invariant: a patient answer can never become encoder-derived,
    # which holds only because apply_patient_answers never writes encoder_value.
    rt = _bool_runtime(source="encoder", encoder_value=True)
    apply_patient_answers(rt, {"flag": False})
    assert rt.answers["flag"].encoder_value is True


def test_apply_unknown_answer_key_raises_keyerror():
    rt = _bool_runtime(source="unanswered", encoder_value=None)
    with pytest.raises(KeyError):
        apply_patient_answers(rt, {"does_not_exist": True})


def test_normalise_promotes_raw_encoder_to_correct():
    rt = _bool_runtime(source="encoder", encoder_value=True, value=True)
    normalise_encoder_provenance(rt)
    assert rt.answers["flag"].source == "encoder_correct"


def test_normalise_leaves_patient_untouched():
    rt = _bool_runtime(source="patient", encoder_value=None, value=True)
    normalise_encoder_provenance(rt)
    assert rt.answers["flag"].source == "patient"


def test_normalise_leaves_encoder_incorrect_untouched():
    rt = _bool_runtime(source="encoder_incorrect", encoder_value=True, value=False)
    normalise_encoder_provenance(rt)
    assert rt.answers["flag"].source == "encoder_incorrect"
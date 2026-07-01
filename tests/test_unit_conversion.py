"""
Unit tests for unit_conversion.imperial_weight_to_kg.

Pure arithmetic — no database, no FastAPI — so no integration marker. Asserts
exactness of the conversion and the whole/non-negative component guards,
including that the function raises ValueError (the domain translation to
AnswerValidationError happens in form_logic, not here).
"""

from decimal import Decimal

import pytest

from app.services.engine.unit_conversion import imperial_weight_to_kg

# ---------------------------------------------------------------------------
# Exact conversion
# ---------------------------------------------------------------------------


def test_zero_is_zero():
    assert imperial_weight_to_kg(0, 0) == Decimal("0")


def test_known_value_is_exact():
    # 11 st 11 lb = 165 lb; 165 * 0.45359237 = 74.84274105 exactly.
    assert imperial_weight_to_kg(11, 11) == Decimal("74.84274105")


def test_whole_stones_only():
    # 10 st = 140 lb; 140 * 0.45359237 = 63.5029318 exactly.
    assert imperial_weight_to_kg(10, 0) == Decimal("63.5029318")


def test_pounds_only():
    assert imperial_weight_to_kg(0, 1) == Decimal("0.45359237")


def test_result_is_decimal_and_unrounded():
    result = imperial_weight_to_kg(11, 11)
    assert isinstance(result, Decimal)
    # Deliberately not rounded to the question's decimal_places here.
    assert result.as_tuple().exponent == -8


def test_int_and_decimal_inputs_agree():
    assert imperial_weight_to_kg(11, 11) == imperial_weight_to_kg(Decimal("11"), Decimal("11"))


# ---------------------------------------------------------------------------
# Component guards
# ---------------------------------------------------------------------------


def test_rejects_bool_stones():
    with pytest.raises(ValueError, match="stones"):
        imperial_weight_to_kg(True, 5)


def test_rejects_bool_pounds():
    with pytest.raises(ValueError, match="pounds"):
        imperial_weight_to_kg(5, True)


def test_rejects_string():
    with pytest.raises(ValueError, match="stones"):
        imperial_weight_to_kg("11", 11)


def test_rejects_float():
    # A bare Python float should never arrive (parse_float=Decimal), but guard.
    with pytest.raises(ValueError, match="pounds"):
        imperial_weight_to_kg(11, 11.0)


def test_rejects_negative_stones():
    with pytest.raises(ValueError, match="negative"):
        imperial_weight_to_kg(-1, 0)


def test_rejects_negative_pounds():
    with pytest.raises(ValueError, match="negative"):
        imperial_weight_to_kg(0, -3)


def test_rejects_fractional_pounds():
    with pytest.raises(ValueError, match="pounds"):
        imperial_weight_to_kg(11, Decimal("11.5"))


def test_rejects_numerically_whole_but_fractional_notation():
    # Decimal("11.0") is numerically whole but its exponent is -1; rejected as
    # non-canonical. Documents the strict "exponent < 0" rule.
    with pytest.raises(ValueError, match="stones"):
        imperial_weight_to_kg(Decimal("11.0"), 0)


def test_rejects_non_finite_as_valueerror_not_typeerror():
    # Must surface as ValueError so convert_unit_answers can translate it; a
    # leaked TypeError from comparing/inspecting a non-finite Decimal would
    # become a 500 instead of a 422.
    with pytest.raises(ValueError):
        imperial_weight_to_kg(Decimal("NaN"), 0)
    with pytest.raises(ValueError):
        imperial_weight_to_kg(0, Decimal("Infinity"))

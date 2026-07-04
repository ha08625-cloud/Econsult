"""
Pure unit-conversion arithmetic.

No RuntimeState, no ruleset, no AnswerValidationError, no IO. This module knows
only numbers. Callers (form_logic.convert_unit_answers) are responsible for
translating the plain ValueError raised here into the domain's
AnswerValidationError, and for any rounding of the result.

Everything on the wire is a JSON number parsed with parse_float=Decimal, so a
component arrives as a Python int (whole) or Decimal (only if a direct-API
client sent a fractional literal). Both are accepted for the type check; a
genuine fractional part is then rejected, because stones and pounds must be
whole numbers.
"""

from decimal import Decimal

Number = int | Decimal

# Exact, internationally-defined pound-to-kilogram factor. Decimal so the
# multiplication is exact and finite with no binary-float rounding.
_LB_TO_KG = Decimal("0.45359237")

_LB_PER_STONE = 14


def _require_whole_nonneg(value: object, name: str) -> None:
    """
    Reject anything that is not a whole, non-negative number.

    Order matters: bool is excluded before the int/Decimal check (isinstance(
    True, int) is True); the finite guard runs before any comparison or exponent
    inspection, because Decimal("NaN") < 0 raises and as_tuple().exponent is a
    string for non-finite values. A whole number is an int, or a Decimal whose
    exponent is >= 0 (a negative exponent is a genuine fractional part, so even
    a numerically-whole "11.0" -- exponent -1 -- is rejected as non-canonical).
    """
    if isinstance(value, bool):
        raise ValueError(f"{name} must be a whole number, not a boolean")

    if not isinstance(value, (int, Decimal)):
        raise ValueError(f"{name} must be a whole number")

    if isinstance(value, Decimal) and not value.is_finite():
        raise ValueError(f"{name} must be a finite whole number")

    if value < 0:
        raise ValueError(f"{name} must not be negative")

    if isinstance(value, Decimal) and value.as_tuple().exponent < 0:
        raise ValueError(f"{name} must be a whole number")


def imperial_weight_to_kg(stones: Number, pounds: Number) -> Decimal:
    """
    Convert a stones-and-pounds weight to an exact, unrounded kilogram Decimal.

    Each component is validated as a whole, non-negative number first. The result
    is intentionally not rounded -- rounding to the question's decimal_places is a
    form-logic concern, kept out of this pure arithmetic. For example 11 st 11 lb
    -> Decimal("74.84274105"), which the caller rounds for the canonical value
    while raw_components preserves the exact "11 st 11 lb" input.

    Raises ValueError (not AnswerValidationError) on any invalid component.
    """
    _require_whole_nonneg(stones, "stones")
    _require_whole_nonneg(pounds, "pounds")

    total_pounds = stones * _LB_PER_STONE + pounds
    return total_pounds * _LB_TO_KG

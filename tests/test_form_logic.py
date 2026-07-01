"""
Unit tests for the Number answer type in form_logic.

Covers validate_required_answers (accept and reject tiers) and
normalise_number_answers. Pure unit tests — no database, no FastAPI — so this
module carries no integration marker.
"""

from decimal import Decimal

import pytest

from app.models.runtime_state import AnswerState, RuntimeState, SafetyEvaluation
from app.services.engine.form_logic import (
    AnswerValidationError,
    _validate_number_value,
    apply_patient_answers,
    convert_unit_answers,
    normalise_encoder_provenance,
    normalise_number_answers,
    validate_required_answers,
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
    with pytest.raises(ValueError):
        validate_required_answers(_runtime(None), _number_ruleset(1))


# ---------------------------------------------------------------------------
# _validate_number_value — direct
#
# The shared number-acceptance ladder, pinned independently of its callers
# because the unit-conversion metric branch calls it directly. It is NOT
# None-aware by design: a None reaches the int/Decimal check and is rejected as
# "must be a number". That is exactly why every caller checks for None first
# and raises its own context-specific message ("Missing ...", or a malformed
# component error) before delegating here.
# ---------------------------------------------------------------------------


def test_helper_accepts_int():
    _validate_number_value(70, 1, "weight")


def test_helper_accepts_decimal_within_precision():
    _validate_number_value(Decimal("70.5"), 1, "weight")
    _validate_number_value(Decimal("70"), 1, "weight")


def test_helper_rejects_bool():
    with pytest.raises(AnswerValidationError, match="not a boolean"):
        _validate_number_value(True, 1, "weight")


def test_helper_rejects_non_number():
    with pytest.raises(AnswerValidationError, match="must be a number"):
        _validate_number_value("70.5", 1, "weight")


def test_helper_rejects_non_finite():
    with pytest.raises(AnswerValidationError, match="finite"):
        _validate_number_value(Decimal("Infinity"), 1, "weight")


def test_helper_rejects_over_precision():
    with pytest.raises(AnswerValidationError, match="more than 1 decimal"):
        _validate_number_value(Decimal("70.55"), 1, "weight")


def test_helper_zero_decimal_places_rejects_fraction():
    with pytest.raises(AnswerValidationError, match="more than 0 decimal"):
        _validate_number_value(Decimal("70.5"), 0, "weight")


def test_helper_is_not_none_aware():
    # Documents the contract that justifies the caller-side None pre-check.
    with pytest.raises(AnswerValidationError, match="must be a number"):
        _validate_number_value(None, 1, "weight")


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
# ---------------------------------------------------------------------------


def _bool_runtime(source, encoder_value, value=None):
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
    rt = _bool_runtime(source="encoder_incorrect", encoder_value=True)
    apply_patient_answers(rt, {"flag": True})
    assert rt.answers["flag"].source == "encoder_correct"


def test_apply_is_idempotent():
    rt = _bool_runtime(source="encoder", encoder_value=True)
    apply_patient_answers(rt, {"flag": False})
    first = rt.answers["flag"].source
    apply_patient_answers(rt, {"flag": False})
    assert rt.answers["flag"].source == first == "encoder_incorrect"


def test_apply_does_not_mutate_encoder_value():
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


# ---------------------------------------------------------------------------
# apply_patient_answers — change_count auditing
# ---------------------------------------------------------------------------


def _encoder_runtime(encoder_value=True):
    return _bool_runtime(source="encoder", encoder_value=encoder_value, value=encoder_value)


def _submit(rt, value):
    apply_patient_answers(rt, {"flag": value})
    return rt.answers["flag"]


def test_change_count_kept_answer_does_not_increment():
    rt = _encoder_runtime(encoder_value=True)
    _submit(rt, True)
    assert rt.answers["flag"].change_count == 0


def test_change_count_override_increments_once():
    rt = _encoder_runtime(encoder_value=True)
    _submit(rt, False)
    assert rt.answers["flag"].change_count == 1


def test_change_count_accumulates_across_submits_ignoring_noops():
    rt = _encoder_runtime(encoder_value=True)
    _submit(rt, True)
    _submit(rt, False)
    _submit(rt, False)
    _submit(rt, True)
    assert rt.answers["flag"].change_count == 2


def test_change_count_parity_matches_source():
    rt = _encoder_runtime(encoder_value=True)
    for value in (False, True, False):
        _submit(rt, value)
    a = rt.answers["flag"]
    assert a.change_count == 3
    assert a.source == "encoder_incorrect"
    assert (a.change_count % 2 == 0) == (a.source == "encoder_correct")


def test_change_count_ignores_non_encoder_boolean():
    rt = _bool_runtime(source="patient", encoder_value=None, value=True)
    _submit(rt, False)
    assert rt.answers["flag"].change_count == 0


def test_change_count_ignores_number_answer():
    rt = _runtime(Decimal("70.5"))
    apply_patient_answers(rt, {"weight": Decimal("80.5")})
    assert rt.answers["weight"].change_count == 0


def test_change_count_multi_key_submit_counts_each_changed_encoder_answer():
    rt = RuntimeState(
        condition_id="demo",
        ruleset_version="hash",
        free_text="",
        additional_text=None,
        answers={
            "a": AnswerState(
                value=True, source="encoder", encoder_value=True, answer_type="boolean"
            ),
            "b": AnswerState(
                value=False, source="encoder", encoder_value=False, answer_type="boolean"
            ),
            "c": AnswerState(value="hi", source="patient", encoder_value=None, answer_type="text"),
        },
        safety_evaluation=SafetyEvaluation(),
        metadata={},
    )
    apply_patient_answers(rt, {"a": False, "b": False, "c": "bye"})
    assert rt.answers["a"].change_count == 1
    assert rt.answers["b"].change_count == 0
    assert rt.answers["c"].change_count == 0


# ---------------------------------------------------------------------------
# AnswerState.change_count — serialisation
# ---------------------------------------------------------------------------


def test_answerstate_roundtrip_preserves_change_count():
    a = AnswerState(
        value=True,
        source="encoder_incorrect",
        encoder_value=True,
        answer_type="boolean",
        change_count=3,
    )
    restored = AnswerState.from_dict(a.to_dict())
    assert restored.change_count == 3


def test_answerstate_from_dict_defaults_missing_change_count_to_zero():
    legacy = {
        "value": True,
        "source": "encoder_correct",
        "encoder_value": True,
        "answer_type": "boolean",
    }
    assert AnswerState.from_dict(legacy).change_count == 0


# ---------------------------------------------------------------------------
# convert_unit_answers
#
# Resolves a quantity-bearing Number answer from the transient client dict
# {"system", "components"} into a canonical kg Decimal, recording raw_components
# and runtime.unit_system. Metric rejects over-precision; imperial rounds.
# ---------------------------------------------------------------------------


def _quantity_ruleset(decimal_places=1, allowed=("metric", "imperial")):
    return {
        "condition_id": "demo",
        "questions": [
            {
                "question_id": "q1",
                "question": "What is your weight?",
                "answer_key": "weight",
                "answer_type": "Number",
                "decimal_places": decimal_places,
                "min": 2,
                "max": 400,
                "send_to_encoder": False,
                "encoder_prompt": None,
                "quantity": True,
                "allowed_systems": list(allowed),
                "default_system": "metric",
            }
        ],
        "safety": {"rules": {}},
    }


def _convert(value, ruleset=None):
    rt = _runtime(value)
    convert_unit_answers(rt, ruleset or _quantity_ruleset())
    return rt


# --- metric ---


def test_convert_metric_decimal():
    rt = _convert({"system": "metric", "components": {"kg": Decimal("70.5")}})
    a = rt.answers["weight"]
    assert a.value == Decimal("70.5")
    assert a.raw_components == {"kg": "70.5"}
    assert rt.unit_system == "metric"


def test_convert_metric_whole_int_kg():
    rt = _convert({"system": "metric", "components": {"kg": 70}})
    a = rt.answers["weight"]
    assert a.value == Decimal("70")
    assert a.raw_components == {"kg": "70"}


def test_convert_metric_rejects_over_precision():
    with pytest.raises(AnswerValidationError, match="more than 1 decimal"):
        _convert({"system": "metric", "components": {"kg": Decimal("70.55")}})


def test_convert_metric_rejects_string_component():
    with pytest.raises(AnswerValidationError, match="must be a number"):
        _convert({"system": "metric", "components": {"kg": "70.5"}})


def test_convert_metric_rejects_bool_component():
    with pytest.raises(AnswerValidationError, match="not a boolean"):
        _convert({"system": "metric", "components": {"kg": True}})


# --- imperial ---


def test_convert_imperial_rounds_to_decimal_places():
    rt = _convert({"system": "imperial", "components": {"st": 11, "lb": 11}})
    a = rt.answers["weight"]
    assert a.value == Decimal("74.8")  # 74.84274105 rounded to 1 dp
    assert a.raw_components == {"st": 11, "lb": 11}
    assert rt.unit_system == "imperial"


def test_convert_imperial_rounds_half_up_to_whole():
    rt = _convert(
        {"system": "imperial", "components": {"st": 11, "lb": 11}},
        ruleset=_quantity_ruleset(decimal_places=0),
    )
    assert rt.answers["weight"].value == Decimal("75")  # 74.84 -> 75


def test_convert_imperial_accepts_decimal_whole_components():
    rt = _convert({"system": "imperial", "components": {"st": Decimal("11"), "lb": Decimal("0")}})
    # 11 st = 154 lb; 154 * 0.45359237 = 69.85322498 -> 69.9 at 1 dp
    assert rt.answers["weight"].value == Decimal("69.9")
    assert rt.answers["weight"].raw_components == {"st": 11, "lb": 0}


def test_convert_imperial_rejects_fractional_pounds():
    with pytest.raises(AnswerValidationError, match="whole number"):
        _convert({"system": "imperial", "components": {"st": 11, "lb": Decimal("11.5")}})


def test_convert_imperial_rejects_negative():
    with pytest.raises(AnswerValidationError, match="negative"):
        _convert({"system": "imperial", "components": {"st": -1, "lb": 0}})


# --- shape / system guards ---


def test_convert_skips_unanswered():
    rt = _convert(None)
    assert rt.answers["weight"].value is None
    assert rt.answers["weight"].raw_components is None
    assert rt.unit_system is None


def test_convert_rejects_bare_number_for_quantity_question():
    with pytest.raises(AnswerValidationError, match="system, components"):
        _convert(Decimal("70"))


def test_convert_rejects_unknown_system():
    with pytest.raises(AnswerValidationError, match="unsupported unit system"):
        _convert({"system": "nautical", "components": {"kg": Decimal("70")}})


def test_convert_rejects_system_not_in_allowed():
    with pytest.raises(AnswerValidationError, match="unsupported unit system"):
        _convert(
            {"system": "imperial", "components": {"st": 11, "lb": 0}},
            ruleset=_quantity_ruleset(allowed=("metric",)),
        )


def test_convert_rejects_wrong_component_keys():
    with pytest.raises(AnswerValidationError, match="requires exactly"):
        _convert({"system": "metric", "components": {"st": 11, "lb": 11}})


def test_convert_rejects_extra_component_key():
    with pytest.raises(AnswerValidationError, match="requires exactly"):
        _convert({"system": "metric", "components": {"kg": Decimal("70"), "x": 1}})


def test_convert_rejects_missing_components():
    with pytest.raises(AnswerValidationError, match="missing its components"):
        _convert({"system": "metric"})


def test_convert_rejects_non_dict_components():
    with pytest.raises(AnswerValidationError, match="missing its components"):
        _convert({"system": "metric", "components": "nope"})


def test_convert_ignores_non_quantity_number_question():
    # A plain number question (no quantity flag) is left untouched by convert.
    rt = _runtime(Decimal("70.5"))
    convert_unit_answers(rt, _number_ruleset(1))
    assert rt.answers["weight"].value == Decimal("70.5")
    assert rt.answers["weight"].raw_components is None
    assert rt.unit_system is None


# ---------------------------------------------------------------------------
# Pure pipeline sequence: apply -> convert -> provenance -> validate -> normalise
# Proves the ordering and the final persisted shape, without a database.
# ---------------------------------------------------------------------------


def _run_sequence(submitted_value, ruleset):
    rt = _runtime(None)  # starts unanswered
    rt.answers["weight"].source = "unanswered"
    apply_patient_answers(rt, {"weight": submitted_value})
    convert_unit_answers(rt, ruleset)
    normalise_encoder_provenance(rt)
    validate_required_answers(rt, ruleset)
    normalise_number_answers(rt)
    return rt


def test_sequence_imperial_end_state():
    rt = _run_sequence(
        {"system": "imperial", "components": {"st": 11, "lb": 11}},
        _quantity_ruleset(1),
    )
    a = rt.answers["weight"]
    assert a.value == "74.8"  # canonical kg string, persisted
    assert a.raw_components == {"st": 11, "lb": 11}
    assert a.source == "patient"
    assert a.change_count == 0
    assert rt.unit_system == "imperial"


def test_sequence_metric_end_state():
    rt = _run_sequence(
        {"system": "metric", "components": {"kg": Decimal("70.5")}},
        _quantity_ruleset(1),
    )
    a = rt.answers["weight"]
    assert a.value == "70.5"
    assert a.raw_components == {"kg": "70.5"}
    assert a.source == "patient"
    assert rt.unit_system == "metric"


def test_sequence_metric_whole_number_persists_cleanly():
    rt = _run_sequence(
        {"system": "metric", "components": {"kg": 70}},
        _quantity_ruleset(1),
    )
    assert rt.answers["weight"].value == "70"


# ---------------------------------------------------------------------------
# normalise_number_answers defensive guard
# ---------------------------------------------------------------------------


def test_normalise_raises_on_unresolved_dict():
    # A dict reaching normalise means convert was skipped / ran out of order.
    # This is an internal error (RuntimeError -> 500), not bad client input.
    rt = _runtime({"system": "metric", "components": {"kg": Decimal("70")}})
    with pytest.raises(RuntimeError, match="Unresolved quantity components"):
        normalise_number_answers(rt)

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
# Safety clause shape (is_true / is_false)
# ---------------------------------------------------------------------------


def _safety_base_ruleset():
    """
    A ruleset with one Boolean question and one text question, so tests can
    check both "valid clause" and "clause references a non-Boolean question"
    cases.
    """
    return {
        "condition_id": "demo",
        "presentation": {"label": "Demo", "free_text_prompt": "x"},
        "questions": [
            {
                "question_id": "q1",
                "question": "Do you have diarrhoea?",
                "answer_key": "diarrhoea",
                "answer_type": "Boolean",
                "send_to_encoder": False,
                "encoder_prompt": None,
            },
            {
                "question_id": "q2",
                "question": "Describe your symptoms",
                "answer_key": "symptom_text",
                "answer_type": "text",
                "send_to_encoder": False,
                "encoder_prompt": None,
            },
        ],
        "safety": {"rules": {}},
    }


def _with_safety_rule(clauses):
    rs = copy.deepcopy(_safety_base_ruleset())
    rs["safety"]["rules"]["r1"] = {"any": clauses, "message": "Seek urgent advice"}
    return rs


def test_accepts_is_true_clause():
    validate_ruleset(_with_safety_rule([{"is_true": "diarrhoea"}]))


def test_accepts_is_false_clause():
    validate_ruleset(_with_safety_rule([{"is_false": "diarrhoea"}]))


def test_accepts_mixed_is_true_and_is_false_clauses():
    validate_ruleset(
        _with_safety_rule([{"is_true": "diarrhoea"}, {"is_false": "diarrhoea"}])
    )


def test_rejects_clause_with_both_keys():
    with pytest.raises(ValueError, match="exactly one"):
        validate_ruleset(
            _with_safety_rule([{"is_true": "diarrhoea", "is_false": "diarrhoea"}])
        )


def test_rejects_clause_with_neither_key():
    with pytest.raises(ValueError, match="exactly one"):
        validate_ruleset(_with_safety_rule([{}]))


def test_rejects_clause_with_unexpected_key():
    with pytest.raises(ValueError, match="unexpected keys"):
        validate_ruleset(_with_safety_rule([{"is_true": "diarrhoea", "note": "x"}]))


def test_rejects_non_string_clause_value():
    with pytest.raises(ValueError, match="must be a string"):
        validate_ruleset(_with_safety_rule([{"is_true": 123}]))


def test_rejects_clause_referencing_unknown_answer_key():
    with pytest.raises(ValueError, match="unknown answer_key"):
        validate_ruleset(_with_safety_rule([{"is_true": "nonexistent"}]))


def test_rejects_clause_referencing_text_question():
    # A text answer can never be True or False. Without this check the rule
    # would validate cleanly and then silently never fire.
    with pytest.raises(ValueError, match="not 'Boolean'"):
        validate_ruleset(_with_safety_rule([{"is_true": "symptom_text"}]))


def test_rejects_non_dict_clause():
    with pytest.raises(ValueError, match="not an object"):
        validate_ruleset(_with_safety_rule(["is_true"]))


def test_rejects_rule_missing_message():
    rs = _with_safety_rule([{"is_true": "diarrhoea"}])
    del rs["safety"]["rules"]["r1"]["message"]
    with pytest.raises(ValueError, match="message"):
        validate_ruleset(rs)


def test_rejects_rule_missing_any():
    rs = _with_safety_rule([{"is_true": "diarrhoea"}])
    del rs["safety"]["rules"]["r1"]["any"]
    with pytest.raises(ValueError, match="'any'"):
        validate_ruleset(rs)


def test_rejects_rule_with_typo_key_instead_of_any():
    rs = _with_safety_rule([{"is_true": "diarrhoea"}])
    rs["safety"]["rules"]["r1"]["all"] = rs["safety"]["rules"]["r1"].pop("any")
    with pytest.raises(ValueError, match="'any'"):
        validate_ruleset(rs)


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

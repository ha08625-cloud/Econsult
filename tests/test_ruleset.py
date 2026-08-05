"""
Unit tests for Number-question and answer_type validation in ruleset.py.

These assert the fail-fast startup contract: a malformed Number question or an
unknown/missing answer_type must raise. Pure unit tests — no integration marker.
"""

import copy
import json

import pytest

from app.services.engine import ruleset
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
            quantity_kind="weight",
            allowed_systems=["metric", "imperial"],
            default_system="metric",
        )
    )


def test_accepts_quantity_with_single_system():
    validate_ruleset(
        _with(
            quantity=True,
            quantity_kind="weight",
            allowed_systems=["metric"],
            default_system="metric",
        )
    )


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
                quantity_kind="weight",
                allowed_systems=["metric"],
                default_system="metric",
            )
        )


def test_rejects_quantity_missing_allowed_systems():
    with pytest.raises(ValueError, match="non-empty allowed_systems"):
        validate_ruleset(_with(quantity=True, quantity_kind="weight", default_system="metric"))


def test_rejects_quantity_empty_allowed_systems():
    with pytest.raises(ValueError, match="non-empty allowed_systems"):
        validate_ruleset(
            _with(
                quantity=True,
                quantity_kind="weight",
                allowed_systems=[],
                default_system="metric",
            )
        )


def test_rejects_allowed_system_outside_kind_vocabulary():
    # "nautical" is not in weight's systems map ({"metric", "imperial"}), even
    # though it is a plausible-looking unit system name in the abstract.
    with pytest.raises(ValueError, match="unknown allowed_systems"):
        validate_ruleset(
            _with(
                quantity=True,
                quantity_kind="weight",
                allowed_systems=["metric", "nautical"],
                default_system="metric",
            )
        )


def test_rejects_duplicate_allowed_systems():
    with pytest.raises(ValueError, match="duplicate allowed_systems"):
        validate_ruleset(
            _with(
                quantity=True,
                quantity_kind="weight",
                allowed_systems=["metric", "metric"],
                default_system="metric",
            )
        )


def test_rejects_default_system_not_in_allowed():
    with pytest.raises(ValueError, match="default_system"):
        validate_ruleset(
            _with(
                quantity=True,
                quantity_kind="weight",
                allowed_systems=["metric"],
                default_system="imperial",
            )
        )


def test_rejects_missing_default_system():
    with pytest.raises(ValueError, match="default_system"):
        validate_ruleset(_with(quantity=True, quantity_kind="weight", allowed_systems=["metric"]))


def test_rejects_allowed_systems_on_non_quantity_question():
    # Unit fields set without the quantity flag would be silently ignored, so
    # they are rejected outright.
    with pytest.raises(ValueError, match="must not set allowed_systems"):
        validate_ruleset(_with(allowed_systems=["metric"]))


def test_rejects_default_system_on_non_quantity_question():
    with pytest.raises(ValueError, match="must not set default_system"):
        validate_ruleset(_with(default_system="metric"))


# ---------------------------------------------------------------------------
# quantity_kind validation
# ---------------------------------------------------------------------------


def test_rejects_quantity_missing_kind():
    with pytest.raises(ValueError, match="quantity_kind"):
        validate_ruleset(_with(quantity=True, allowed_systems=["metric"], default_system="metric"))


def test_rejects_unknown_quantity_kind():
    with pytest.raises(ValueError, match="quantity_kind"):
        validate_ruleset(
            _with(
                quantity=True,
                quantity_kind="mass",
                allowed_systems=["metric"],
                default_system="metric",
            )
        )


def test_rejects_quantity_kind_on_non_quantity_question():
    with pytest.raises(ValueError, match="must not set quantity_kind"):
        validate_ruleset(_with(quantity_kind="weight"))


# ---------------------------------------------------------------------------
# Shared-toggle consistency across multi-system quantity questions
# ---------------------------------------------------------------------------


def _two_question_ruleset(first_overrides, second_overrides):
    """
    A ruleset with two Number questions, each independently overridable, for
    the shared-toggle consistency tests -- _base_ruleset() only has one
    question and reshaping it would obscure the single-question tests above.
    """
    base_question = {
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
    q1 = {**base_question, **first_overrides}
    q2 = {
        **base_question,
        "question_id": "q2",
        "question": "What is your height?",
        "answer_key": "height",
        **second_overrides,
    }
    return {
        "condition_id": "demo",
        "presentation": {"label": "Demo", "free_text_prompt": "x"},
        "questions": [q1, q2],
        "safety": {"rules": {}},
    }


def test_accepts_agreeing_multi_system_quantity_questions():
    validate_ruleset(
        _two_question_ruleset(
            {
                "quantity": True,
                "quantity_kind": "weight",
                "allowed_systems": ["metric", "imperial"],
                "default_system": "metric",
            },
            {
                "quantity": True,
                "quantity_kind": "weight",
                "allowed_systems": ["metric", "imperial"],
                "default_system": "metric",
            },
        )
    )


def test_rejects_multi_system_quantity_questions_with_differing_allowed_systems(monkeypatch):
    # weight's registered systems map has only two entries (metric, imperial),
    # so any multi-system question drawn from it must select exactly that
    # pair -- there is no way to construct two multi-system questions that
    # disagree on allowed_systems using the real registry alone until a
    # second quantity_kind exists (Ticket 2). Temporarily widen weight's
    # systems map for this test only, so the disagreement path in
    # _validate_shared_toggle_consistency can be exercised now.
    monkeypatch.setitem(ruleset.QUANTITY_KINDS["weight"]["systems"], "extra", ("x",))

    with pytest.raises(ValueError, match="must share the same allowed_systems"):
        validate_ruleset(
            _two_question_ruleset(
                {
                    "quantity": True,
                    "quantity_kind": "weight",
                    "allowed_systems": ["metric", "imperial"],
                    "default_system": "metric",
                },
                {
                    "quantity": True,
                    "quantity_kind": "weight",
                    "allowed_systems": ["metric", "extra"],
                    "default_system": "metric",
                },
            )
        )


def test_rejects_multi_system_quantity_questions_with_differing_default_system():
    with pytest.raises(ValueError, match="must share the same allowed_systems"):
        validate_ruleset(
            _two_question_ruleset(
                {
                    "quantity": True,
                    "quantity_kind": "weight",
                    "allowed_systems": ["metric", "imperial"],
                    "default_system": "metric",
                },
                {
                    "quantity": True,
                    "quantity_kind": "weight",
                    "allowed_systems": ["metric", "imperial"],
                    "default_system": "imperial",
                },
            )
        )


def test_accepts_single_system_question_alongside_multi_system_question():
    # Single-system quantity questions are exempt from shared-toggle
    # agreement -- there is nothing for them to toggle between.
    validate_ruleset(
        _two_question_ruleset(
            {
                "quantity": True,
                "quantity_kind": "weight",
                "allowed_systems": ["metric", "imperial"],
                "default_system": "metric",
            },
            {
                "quantity": True,
                "quantity_kind": "weight",
                "allowed_systems": ["metric"],
                "default_system": "metric",
            },
        )
    )


# ---------------------------------------------------------------------------
# pdf_label
# ---------------------------------------------------------------------------


def test_accepts_absent_pdf_label():
    validate_ruleset(_base_ruleset())


def test_accepts_null_pdf_label():
    validate_ruleset(_with(pdf_label=None))


def test_accepts_pdf_label_on_number_question():
    validate_ruleset(_with(pdf_label="Weight"))


def test_accepts_pdf_label_on_boolean_question():
    rs = _with(answer_type="Boolean", pdf_label="Fever")
    for field_name in ("decimal_places", "min", "max"):
        del rs["questions"][0][field_name]
    validate_ruleset(rs)


def test_rejects_empty_pdf_label():
    with pytest.raises(ValueError, match="pdf_label"):
        validate_ruleset(_with(pdf_label=""))


def test_rejects_whitespace_only_pdf_label():
    with pytest.raises(ValueError, match="pdf_label"):
        validate_ruleset(_with(pdf_label="   "))


def test_rejects_non_string_pdf_label():
    with pytest.raises(ValueError, match="pdf_label"):
        validate_ruleset(_with(pdf_label=42))


def test_rejects_pdf_label_on_text_question():
    rs = _with(answer_type="text", pdf_label="Onset")
    for field_name in ("decimal_places", "min", "max"):
        del rs["questions"][0][field_name]
    with pytest.raises(ValueError, match="must not set pdf_label"):
        validate_ruleset(rs)


def test_rejects_duplicate_pdf_label():
    rs = _with(pdf_label="Weight")
    second = copy.deepcopy(rs["questions"][0])
    second["question_id"] = "q2"
    second["answer_key"] = "weight_again"
    rs["questions"].append(second)
    with pytest.raises(ValueError, match="Duplicate pdf_label"):
        validate_ruleset(rs)


# ---------------------------------------------------------------------------
# Safety clause shape (is_true / is_false / any / all)
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
    validate_ruleset(_with_safety_rule([{"is_true": "diarrhoea"}, {"is_false": "diarrhoea"}]))


def test_rejects_clause_with_both_keys():
    with pytest.raises(ValueError, match="exactly one"):
        validate_ruleset(_with_safety_rule([{"is_true": "diarrhoea", "is_false": "diarrhoea"}]))


def test_rejects_clause_with_neither_key():
    # A clause must carry exactly one of the four clause keys
    # (is_true / is_false / any / all); an empty object carries none.
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


def test_rejects_all_at_rule_top_level():
    # "all" is legal as a nested group but deliberately not at the top level of
    # a rule: a rule is a list of independent triggers, and OR is the clinically
    # correct default for a red-flag list. An author who wants a whole-rule AND
    # writes {"any": [{"all": [...]}]}, which makes the intent explicit at the
    # point of authoring and keeps every rule readable the same way. This is a
    # deliberate restriction, not obsolete typo protection -- do not relax it.
    rs = _with_safety_rule([{"is_true": "diarrhoea"}])
    rs["safety"]["rules"]["r1"]["all"] = rs["safety"]["rules"]["r1"].pop("any")
    with pytest.raises(ValueError, match="'any'"):
        validate_ruleset(rs)


# ---------------------------------------------------------------------------
# Nested safety clause groups (any / all)
# ---------------------------------------------------------------------------


def test_accepts_all_group_nested_in_rule_any():
    validate_ruleset(
        _with_safety_rule([{"all": [{"is_true": "diarrhoea"}, {"is_false": "diarrhoea"}]}])
    )


def test_accepts_any_group_nested_in_all_group():
    validate_ruleset(
        _with_safety_rule(
            [
                {
                    "all": [
                        {"is_true": "diarrhoea"},
                        {"any": [{"is_false": "diarrhoea"}, {"is_true": "diarrhoea"}]},
                    ]
                }
            ]
        )
    )


def test_accepts_three_group_levels():
    # The rule's own "any" is level 1, the "all" is level 2, the inner "any" is
    # level 3 -- exactly at MAX_SAFETY_CLAUSE_DEPTH.
    validate_ruleset(_with_safety_rule([{"all": [{"any": [{"is_true": "diarrhoea"}]}]}]))


def test_rejects_four_group_levels():
    # A fourth level is past what a clinician can reasonably review in one
    # rule; the rule should be split instead.
    with pytest.raises(ValueError, match="group levels deep"):
        validate_ruleset(
            _with_safety_rule([{"all": [{"any": [{"all": [{"is_true": "diarrhoea"}]}]}]}])
        )


def test_rejects_empty_nested_all_group():
    # The dangerous one: Python evaluates all([]) to True, so {"all": []} is
    # satisfied unconditionally. It would fire its rule for every patient and
    # block every submission on this condition with a message no answer can
    # clear. It must never reach a running deployment.
    with pytest.raises(ValueError, match="empty 'all' group"):
        validate_ruleset(_with_safety_rule([{"all": []}]))


def test_rejects_empty_nested_any_group():
    # The mirror of the above, and the harmless direction: any([]) is False, so
    # this clause silently never fires. Still an authoring mistake, still
    # rejected -- a clause that can never match has no meaning.
    with pytest.raises(ValueError, match="empty 'any' group"):
        validate_ruleset(_with_safety_rule([{"any": []}]))


def test_rejects_group_whose_value_is_not_a_list():
    with pytest.raises(ValueError, match="not a list"):
        validate_ruleset(_with_safety_rule([{"all": {"is_true": "diarrhoea"}}]))


def test_rejects_clause_mixing_leaf_and_group():
    # Without the "exactly one key" rule the engine's key-dispatch order would
    # silently decide what this clause means clinically.
    with pytest.raises(ValueError, match="exactly one"):
        validate_ruleset(
            _with_safety_rule([{"is_true": "diarrhoea", "all": [{"is_false": "diarrhoea"}]}])
        )


def test_rejects_clause_with_both_group_keys():
    with pytest.raises(ValueError, match="exactly one"):
        validate_ruleset(
            _with_safety_rule(
                [{"any": [{"is_true": "diarrhoea"}], "all": [{"is_false": "diarrhoea"}]}]
            )
        )


def test_rejects_nested_clause_referencing_unknown_answer_key():
    # Proves the declared-key check reaches into the recursion.
    with pytest.raises(ValueError, match="unknown answer_key"):
        validate_ruleset(
            _with_safety_rule([{"all": [{"is_true": "diarrhoea"}, {"is_true": "nonexistent"}]}])
        )


def test_rejects_nested_clause_referencing_text_question():
    # Proves the Boolean check reaches into the recursion.
    with pytest.raises(ValueError, match="not 'Boolean'"):
        validate_ruleset(_with_safety_rule([{"all": [{"is_true": "symptom_text"}]}]))


def test_rejects_non_dict_nested_clause():
    with pytest.raises(ValueError, match="not an object"):
        validate_ruleset(_with_safety_rule([{"any": ["is_true"]}]))


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

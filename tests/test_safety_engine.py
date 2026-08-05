"""
Unit tests for safety_engine.py's evaluate_safety.

evaluate_safety is a pure function with no DB or IO dependency, so these are
plain unit tests -- no integration marker.

Covers:
- is_true fires only on explicit True; never on None or False
- is_false fires only on explicit False; never on None or True
- a missing answer_key behaves the same as None (unknown, never satisfies)
- ANY logic: a rule with multiple clauses fires if any one clause is satisfied
- a rule with no satisfied clauses does not fire, and produces no message
- multiple rules can fire independently in the same evaluation
- the returned message payload carries the rule id and its authored text
- nested any/all groups evaluate recursively, to arbitrary depth
- None inside an "all" group leaves that group unsatisfied
- empty groups behave as Python any([])/all([]) do -- see the section comment
"""

from app.models.explicit_answers import ExplicitAnswers
from app.services.engine.safety_engine import evaluate_safety


def _answers(**values):
    return ExplicitAnswers(values=values)


def _rules(**rules):
    """
    Each kwarg value is a list of clause dicts, e.g.
    _rules(r1=[{"is_true": "diarrhoea"}])
    """
    return {
        rule_id: {"any": clauses, "message": f"message for {rule_id}"}
        for rule_id, clauses in rules.items()
    }


# ---------------------------------------------------------------------------
# is_true
# ---------------------------------------------------------------------------


def test_is_true_fires_on_explicit_true():
    result = evaluate_safety(_answers(diarrhoea=True), _rules(r1=[{"is_true": "diarrhoea"}]))
    assert result.triggered_rules == ["r1"]


def test_is_true_does_not_fire_on_false():
    result = evaluate_safety(_answers(diarrhoea=False), _rules(r1=[{"is_true": "diarrhoea"}]))
    assert result.triggered_rules == []


def test_is_true_does_not_fire_on_none():
    result = evaluate_safety(_answers(diarrhoea=None), _rules(r1=[{"is_true": "diarrhoea"}]))
    assert result.triggered_rules == []


def test_is_true_does_not_fire_on_missing_key():
    result = evaluate_safety(_answers(), _rules(r1=[{"is_true": "diarrhoea"}]))
    assert result.triggered_rules == []


# ---------------------------------------------------------------------------
# is_false
# ---------------------------------------------------------------------------


def test_is_false_fires_on_explicit_false():
    result = evaluate_safety(_answers(diarrhoea=False), _rules(r1=[{"is_false": "diarrhoea"}]))
    assert result.triggered_rules == ["r1"]


def test_is_false_does_not_fire_on_true():
    result = evaluate_safety(_answers(diarrhoea=True), _rules(r1=[{"is_false": "diarrhoea"}]))
    assert result.triggered_rules == []


def test_is_false_does_not_fire_on_none():
    result = evaluate_safety(_answers(diarrhoea=None), _rules(r1=[{"is_false": "diarrhoea"}]))
    assert result.triggered_rules == []


def test_is_false_does_not_fire_on_missing_key():
    result = evaluate_safety(_answers(), _rules(r1=[{"is_false": "diarrhoea"}]))
    assert result.triggered_rules == []


# ---------------------------------------------------------------------------
# ANY logic across clauses and rules
# ---------------------------------------------------------------------------


def test_rule_fires_if_any_clause_satisfied():
    rules = _rules(r1=[{"is_true": "a"}, {"is_false": "b"}])
    result = evaluate_safety(_answers(a=False, b=False), rules)
    assert result.triggered_rules == ["r1"]


def test_rule_does_not_fire_if_no_clause_satisfied():
    rules = _rules(r1=[{"is_true": "a"}, {"is_false": "b"}])
    result = evaluate_safety(_answers(a=False, b=True), rules)
    assert result.triggered_rules == []
    assert result.messages == []


def test_multiple_rules_fire_independently():
    rules = _rules(
        r1=[{"is_true": "a"}],
        r2=[{"is_false": "b"}],
        r3=[{"is_true": "c"}],
    )
    result = evaluate_safety(_answers(a=True, b=False, c=None), rules)
    assert set(result.triggered_rules) == {"r1", "r2"}


# ---------------------------------------------------------------------------
# Message payload
# ---------------------------------------------------------------------------


def test_triggered_rule_produces_message_with_id_and_text():
    rules = {"r1": {"any": [{"is_true": "a"}], "message": "See a doctor urgently"}}
    result = evaluate_safety(_answers(a=True), rules)
    assert result.messages == [{"id": "r1", "text": "See a doctor urgently"}]


def test_no_rules_no_evaluation():
    result = evaluate_safety(_answers(a=True), {})
    assert result.triggered_rules == []
    assert result.messages == []


# ---------------------------------------------------------------------------
# Nested any / all groups
# ---------------------------------------------------------------------------


def test_all_group_fires_only_when_every_leaf_satisfied():
    rules = _rules(r1=[{"all": [{"is_true": "fever"}, {"is_true": "flank_pain"}]}])
    assert evaluate_safety(_answers(fever=True, flank_pain=True), rules).triggered_rules == ["r1"]
    assert evaluate_safety(_answers(fever=True, flank_pain=False), rules).triggered_rules == []
    assert evaluate_safety(_answers(fever=False, flank_pain=False), rules).triggered_rules == []


def test_all_group_mixes_is_true_and_is_false_leaves():
    rules = _rules(r1=[{"all": [{"is_true": "fever"}, {"is_false": "improving"}]}])
    assert evaluate_safety(_answers(fever=True, improving=False), rules).triggered_rules == ["r1"]
    assert evaluate_safety(_answers(fever=True, improving=True), rules).triggered_rules == []


def test_any_group_nested_inside_all_group():
    # fever AND (flank_pain OR vomiting)
    rules = _rules(
        r1=[
            {
                "all": [
                    {"is_true": "fever"},
                    {"any": [{"is_true": "flank_pain"}, {"is_true": "vomiting"}]},
                ]
            }
        ]
    )
    assert evaluate_safety(_answers(fever=True, vomiting=True), rules).triggered_rules == ["r1"]
    assert evaluate_safety(_answers(fever=True, flank_pain=True), rules).triggered_rules == ["r1"]
    assert evaluate_safety(_answers(fever=True), rules).triggered_rules == []
    assert evaluate_safety(_answers(vomiting=True), rules).triggered_rules == []


def test_three_levels_of_nesting():
    # rule "any" (level 1) > "all" (level 2) > "any" (level 3)
    rules = _rules(
        r1=[
            {
                "all": [
                    {"any": [{"is_true": "fever"}, {"is_true": "rigors"}]},
                    {"any": [{"is_true": "flank_pain"}, {"is_false": "passing_urine"}]},
                ]
            }
        ]
    )
    assert evaluate_safety(_answers(rigors=True, passing_urine=False), rules).triggered_rules == [
        "r1"
    ]
    assert evaluate_safety(_answers(fever=True, flank_pain=True), rules).triggered_rules == ["r1"]
    # first inner group satisfied, second not
    assert evaluate_safety(_answers(fever=True, passing_urine=True), rules).triggered_rules == []


def test_group_clause_alongside_leaf_clauses_in_the_same_rule():
    rules = _rules(
        r1=[
            {"is_true": "sepsis_signs"},
            {"all": [{"is_true": "fever"}, {"is_true": "flank_pain"}]},
        ]
    )
    assert evaluate_safety(_answers(sepsis_signs=True), rules).triggered_rules == ["r1"]
    assert evaluate_safety(_answers(fever=True, flank_pain=True), rules).triggered_rules == ["r1"]
    assert evaluate_safety(_answers(fever=True), rules).triggered_rules == []


# ---------------------------------------------------------------------------
# Unknown (None) answers inside groups
# ---------------------------------------------------------------------------


def test_none_inside_all_group_leaves_it_unsatisfied():
    # An unanswered question defeats an AND group even when every other leaf
    # is satisfied -- "unknown" is not "true".
    rules = _rules(r1=[{"all": [{"is_true": "fever"}, {"is_true": "flank_pain"}]}])
    assert evaluate_safety(_answers(fever=True, flank_pain=None), rules).triggered_rules == []


def test_none_inside_all_group_defeats_an_is_false_leaf_too():
    rules = _rules(r1=[{"all": [{"is_true": "fever"}, {"is_false": "improving"}]}])
    assert evaluate_safety(_answers(fever=True, improving=None), rules).triggered_rules == []


def test_none_inside_nested_any_group_is_ignored():
    rules = _rules(r1=[{"any": [{"is_true": "fever"}, {"is_true": "rigors"}]}])
    assert evaluate_safety(_answers(fever=None, rigors=True), rules).triggered_rules == ["r1"]
    assert evaluate_safety(_answers(fever=None, rigors=None), rules).triggered_rules == []


# ---------------------------------------------------------------------------
# Malformed and empty clauses
#
# These pin current engine behaviour only. None of these shapes can reach
# production: ruleset.py rejects them at startup (task 2 of this plan), which
# is what actually protects patients here. The engine returns a plain bool so
# a bug elsewhere cannot raise mid-request.
# ---------------------------------------------------------------------------


def test_clause_with_no_recognised_key_does_not_fire():
    rules = _rules(r1=[{"is_missing": "fever"}])
    assert evaluate_safety(_answers(fever=True), rules).triggered_rules == []


def test_empty_any_group_does_not_fire():
    rules = _rules(r1=[{"any": []}])
    assert evaluate_safety(_answers(fever=True), rules).triggered_rules == []


def test_empty_all_group_fires_vacuously():
    # all([]) is True in Python, so an empty "all" satisfies its rule
    # unconditionally -- and a triggered rule blocks submission. This is the
    # exact hazard the recursive validator in task 2 closes; the assertion
    # documents it rather than endorsing it.
    rules = _rules(r1=[{"all": []}])
    assert evaluate_safety(_answers(), rules).triggered_rules == ["r1"]


def test_group_with_non_list_value_does_not_fire():
    answers = _answers(fever=True)
    assert evaluate_safety(answers, _rules(r1=[{"all": "fever"}])).triggered_rules == []
    assert evaluate_safety(answers, _rules(r1=[{"any": "fever"}])).triggered_rules == []

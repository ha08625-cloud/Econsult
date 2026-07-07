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
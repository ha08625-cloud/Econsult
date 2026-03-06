from typing import Dict
from explicit_answers import ExplicitAnswers
from runtime_state import SafetyEvaluation


def evaluate_safety(
    explicit_answers: ExplicitAnswers,
    safety_rules: Dict,
) -> SafetyEvaluation:
    """
    Inputs:
    - explicit_answers: immutable, projected answers only
    - safety_rules: ruleset["safety"]["rules"]
    Output:
    - SafetyEvaluation with triggered rule IDs and messages
    Semantics:
    - None means unknown and never satisfies a condition
    - Safety rules use ANY logic: a rule fires if any condition is true
    """

    evaluation = SafetyEvaluation()

    answers = explicit_answers.values

    for rule_id, rule in safety_rules.items():
        conditions = rule.get("any", [])

        satisfied = False
        for cond in conditions:
            key = cond.get("is_true")
            if key is None:
                continue

            if answers.get(key) is True:
                satisfied = True
                break

        if satisfied:
            evaluation.triggered_rules.append(rule_id)
            evaluation.messages.append(
                {
                    "id": rule_id,
                    "text": rule["message"],
                }
            )

    return evaluation
from app.models.explicit_answers import ExplicitAnswers
from app.models.runtime_state import SafetyEvaluation


def evaluate_safety(
    explicit_answers: ExplicitAnswers,
    safety_rules: dict,
) -> SafetyEvaluation:
    """
    Inputs:
    - explicit_answers: immutable, projected answers only
    - safety_rules: ruleset["safety"]["rules"]
    Output:
    - SafetyEvaluation with triggered rule IDs and messages
    Semantics:
    - None means unknown and never satisfies a condition
    - Safety rules use ANY logic: a rule fires if any condition is satisfied
    - is_true: satisfied when the answer is explicitly True
    - is_false: satisfied when the answer is explicitly False
    - Neither is satisfied by None (unknown/unanswered)
    """

    evaluation = SafetyEvaluation()

    answers = explicit_answers.values

    for rule_id, rule in safety_rules.items():
        conditions = rule.get("any", [])

        satisfied = False
        for cond in conditions:
            is_true_key = cond.get("is_true")
            is_false_key = cond.get("is_false")

            if is_true_key is not None:
                if answers.get(is_true_key) is True:
                    satisfied = True
                    break

            if is_false_key is not None:
                if answers.get(is_false_key) is False:
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

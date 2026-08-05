from app.models.explicit_answers import ExplicitAnswers
from app.models.runtime_state import SafetyEvaluation


def _clause_satisfied(clause: dict, answers: dict) -> bool:
    """
    Evaluate a single safety clause against projected answers.

    A clause is either a leaf (is_true / is_false) or a group (any / all)
    whose value is a list of further clauses, evaluated recursively.

    A clause matching none of the four keys returns False. That is a backstop
    against a bug elsewhere raising mid-request, not a safety mechanism -- a
    rule that does not fire leaves the patient unwarned, which is the unsafe
    direction. ruleset.py rejects malformed clauses at startup so this path
    is unreachable in a booted deployment.
    """

    is_true_key = clause.get("is_true")
    is_false_key = clause.get("is_false")

    if is_true_key is not None and answers.get(is_true_key) is True:
        return True

    if is_false_key is not None and answers.get(is_false_key) is False:
        return True

    if "any" in clause:
        group = clause["any"]
        if not isinstance(group, list):
            return False
        return any(_clause_satisfied(c, answers) for c in group)

    if "all" in clause:
        group = clause["all"]
        if not isinstance(group, list):
            return False
        return all(_clause_satisfied(c, answers) for c in group)

    return False


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
    - Safety rules use ANY logic: a rule fires if any clause is satisfied
    - A clause is either a leaf or a group, evaluated recursively:
      - is_true: satisfied when the answer is explicitly True
      - is_false: satisfied when the answer is explicitly False
      - any: satisfied when at least one nested clause is satisfied
      - all: satisfied when every nested clause is satisfied
    - No leaf is satisfied by None (unknown/unanswered), so a single unknown
      leaf leaves an enclosing "all" group unsatisfied
    """

    evaluation = SafetyEvaluation()

    answers = explicit_answers.values

    for rule_id, rule in safety_rules.items():
        satisfied = any(_clause_satisfied(c, answers) for c in rule.get("any", []))

        if satisfied:
            evaluation.triggered_rules.append(rule_id)
            evaluation.messages.append(
                {
                    "id": rule_id,
                    "text": rule["message"],
                }
            )

    return evaluation

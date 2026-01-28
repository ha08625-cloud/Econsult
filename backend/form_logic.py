from typing import Any
from runtime_state import RuntimeState, AnswerState, SafetyEvaluation
from ruleset import ruleset_hash

"""
creates blank runtime state at initialisation
"""

def initialise_runtime_state(
    ruleset: dict,
    free_text: str,
    engine_version: str = "0.1",
) -> RuntimeState:
    answers = {
        q["answer_key"]: AnswerState(
            value=None,
            source="unanswered",
            encoder_value=None,
        )
        for q in ruleset["questions"]
    }

    return RuntimeState(
        condition_id=ruleset["condition_id"],
        ruleset_version=ruleset_hash(ruleset),
        free_text=free_text,
        answers=answers,
        safety_evaluation=SafetyEvaluation(),
        metadata={
            "engine_version": engine_version,
            "timestamp": datetime.utcnow().isoformat() + "Z",
        },
    )

"""
reloads partially filled form on returns
fail loud if incompatible with ruleset version
"""
def hydrate_runtime_state(
    incoming: RuntimeState,
    ruleset: dict,
) -> RuntimeState:
    assert incoming.ruleset_version == ruleset_hash(ruleset)

    rule_keys = {q["answer_key"] for q in ruleset["questions"]}
    state_keys = set(incoming.answers.keys())

    assert rule_keys == state_keys

    for a in incoming.answers.values():
        assert a.source in {
            "unanswered",
            "encoder",
            "encoder_confirmed",
            "encoder_corrected",
            "patient",
        }

    return incoming

"""
changes source if patient clicks box
"""

def patient_update(runtime: RuntimeState, answer_key: str, value: Any) -> None:
    a = runtime.answers[answer_key]

    a.value = value

    if a.source == "encoder":
        a.source = "encoder_corrected"
    else:
        a.source = "patient"

"""
changes all encoders to encoder_confirmed on submit
"""

def normalise_on_submit(runtime: RuntimeState) -> None:
    for a in runtime.answers.values():
        if a.source == "encoder":
            a.source = "encoder_confirmed"

"""
checks for safety netting instructions needed
"""

def evaluate_safety(runtime: RuntimeState, ruleset: dict) -> None:
    runtime.safety_evaluation = SafetyEvaluation()

    answers_view = {
        k: v.value for k, v in runtime.answers.items()
    }

    for rule_id, rule in ruleset.get("safety", {}).get("rules", {}).items():
        satisfied = all(
            answers_view.get(cond["is_true"]) is True
            for cond in rule.get("all", [])
        )

        if satisfied:
            runtime.safety_evaluation.triggered_rules.append(rule_id)
            runtime.safety_evaluation.messages.append(rule["message"])

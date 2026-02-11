"""
Deterministic functional core.

No encoder access. No IO. No serialization. No sequencing.
Can be fully unit tested without the pipeline or encoder.
"""

from datetime import datetime
from typing import Any, Dict
from runtime_state import RuntimeState, AnswerState, SafetyEvaluation
from ruleset import ruleset_hash


def initialise_runtime_state(
    ruleset: dict,
    free_text: str,
    engine_version: str = "0.1",
) -> RuntimeState:
    """Create blank RuntimeState at initialisation."""

    answers = {
        q["answer_key"]: AnswerState(
            value=None,
            source="unanswered",
            encoder_value=None,
            answer_type=q["answer_type"].lower(),
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


def hydrate_runtime_state(
    incoming: RuntimeState,
    ruleset: dict,
) -> RuntimeState:
    """
    Reload partially filled form on return.
    Fail loud if incompatible with ruleset version.
    """

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


def apply_patient_answers(
    runtime: RuntimeState,
    answers: Dict[str, Any],
) -> None:
    """
    Apply a dict of patient answers to RuntimeState.
    Each answer updates the value and sets provenance:
    - If previously encoder-filled, source becomes encoder_corrected
    - Otherwise source becomes patient
    """

    for answer_key, value in answers.items():
        if answer_key not in runtime.answers:
            raise KeyError(f"Unknown answer_key: {answer_key}")

        a = runtime.answers[answer_key]
        a.value = value

        if a.source == "encoder":
            a.source = "encoder_corrected"
        else:
            a.source = "patient"


def normalise_encoder_provenance(runtime: RuntimeState) -> None:
    """
    On submit, any remaining encoder-derived answers that were not
    explicitly corrected by the patient are treated as confirmed.
    """

    for a in runtime.answers.values():
        if a.source == "encoder":
            a.source = "encoder_confirmed"


def validate_required_answers(runtime: RuntimeState) -> None:
    """
    Validate that all answers are complete.
    For MVP all questions are required.
    - Boolean answers: value must not be None
    - Text answers: value must be a non-empty string
    """

    for answer_key, a in runtime.answers.items():
        if a.answer_type == "boolean":
            if a.value is None:
                raise ValueError(
                    f"Required boolean answer not provided: {answer_key}"
                )
        elif a.answer_type == "text":
            if not isinstance(a.value, str) or a.value.strip() == "":
                raise ValueError(
                    f"Required text answer not provided: {answer_key}"
                )
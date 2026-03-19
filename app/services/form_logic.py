"""
Deterministic functional core.

No encoder access. No IO. No serialization. No sequencing.
Can be fully unit tested without the pipeline or encoder.
"""

from datetime import datetime
from typing import Any, Dict, Optional
from app.models.runtime_state import RuntimeState, AnswerState, SafetyEvaluation
from app.services.ruleset import ruleset_hash

VALID_ANSWER_SOURCES = {
    "unanswered",
    "encoder",
    "encoder_confirmed",
    "encoder_corrected",
    "patient",
}


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
        additional_text=None,
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

    expected_hash = ruleset_hash(ruleset)
    if incoming.ruleset_version != expected_hash:
        raise ValueError(
            f"Ruleset version mismatch: state has {incoming.ruleset_version}, "
            f"ruleset has {expected_hash}"
        )

    rule_keys = {q["answer_key"] for q in ruleset["questions"]}
    state_keys = set(incoming.answers.keys())

    if rule_keys != state_keys:
        missing = rule_keys - state_keys
        extra = state_keys - rule_keys
        raise ValueError(
            f"Answer key mismatch between ruleset and state. "
            f"Missing from state: {missing}, Extra in state: {extra}"
        )

    for key, a in incoming.answers.items():
        if a.source not in VALID_ANSWER_SOURCES:
            raise ValueError(
                f"Invalid answer source '{a.source}' for answer_key '{key}'"
            )

    return incoming


def apply_additional_text(
    runtime: RuntimeState,
    additional_text: Optional[str],
) -> None:
    """
    Store the patient's optional additional free text on RuntimeState.
    Converts empty string to None so downstream code can treat None as absent.
    Never passed to encoder, safety engine, or validation.
    """
    if additional_text and additional_text.strip():
        runtime.additional_text = additional_text.strip()
    else:
        runtime.additional_text = None


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
    additional_text is never validated here — it is always optional.
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

from datetime import datetime, timezone
from typing import Any, Dict, Optional
from app.models.runtime_state import RuntimeState, AnswerState, SafetyEvaluation
from app.services.engine.ruleset import ruleset_hash

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
    """Creates the initial RuntimeState for a new clinical session."""
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
            "timestamp": datetime.now(timezone.utc).isoformat(),
        },
    )

def hydrate_runtime_state(
    incoming: RuntimeState,
    ruleset: dict,
) -> RuntimeState:
    """Validates that existing state is compatible with the current ruleset."""
    expected_hash = ruleset_hash(ruleset)
    if incoming.ruleset_version != expected_hash:
        raise ValueError(f"Ruleset mismatch: state={incoming.ruleset_version}, ruleset={expected_hash}")

    rule_keys = {q["answer_key"] for q in ruleset["questions"]}
    state_keys = set(incoming.answers.keys())

    if rule_keys != state_keys:
        raise ValueError(f"Key mismatch. Missing: {rule_keys - state_keys}, Extra: {state_keys - rule_keys}")

    for key, a in incoming.answers.items():
        if a.source not in VALID_ANSWER_SOURCES:
            raise ValueError(f"Invalid source '{a.source}' for key '{key}'")

    return incoming

def apply_additional_text(runtime: RuntimeState, additional_text: Optional[str]) -> None:
    """Updates the optional patient narrative, normalizing empty strings to None."""
    runtime.additional_text = additional_text.strip() if additional_text and additional_text.strip() else None

def apply_patient_answers(runtime: RuntimeState, answers: Dict[str, Any]) -> None:
    """
    Applies patient-provided answers and updates provenance.
    If an answer was previously provided by an encoder, it is marked as 'corrected'.
    """
    for answer_key, value in answers.items():
        if answer_key not in runtime.answers:
            raise KeyError(f"Unknown answer_key: {answer_key}")

        a = runtime.answers[answer_key]
        a.value = value
        a.source = "encoder_corrected" if a.source == "encoder" else "patient"

def normalise_encoder_provenance(runtime: RuntimeState) -> None:
    """Promotes uncorrected encoder answers to 'confirmed' status upon submission."""
    for a in runtime.answers.values():
        if a.source == "encoder":
            a.source = "encoder_confirmed"

def validate_required_answers(runtime: RuntimeState) -> None:
    """Ensures all questions have been answered based on their type requirements."""
    for answer_key, a in runtime.answers.items():
        if a.answer_type == "boolean":
            if a.value is None:
                raise ValueError(f"Missing boolean answer: {answer_key}")
        elif a.answer_type == "text":
            if not isinstance(a.value, str) or not a.value.strip():
                raise ValueError(f"Missing text answer: {answer_key}")
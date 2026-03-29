from typing import Dict
from app.models.runtime_state import RuntimeState
from app.models.explicit_answers import ExplicitAnswers

EXPLICIT_SOURCES = {
    "patient",
    "encoder_confirmed",
    "encoder_corrected",
}


def project_explicit_answers(runtime: RuntimeState) -> ExplicitAnswers:
    """
    Strict allow-list projection.
    Only patient and encoder_confirmed answers are included and sent to safety_engine.py for evaluation
    """

    projected: Dict[str, bool | None] = {}

    for key, answer in runtime.answers.items():
        if answer.source in EXPLICIT_SOURCES:
            projected[key] = answer.value
        else:
            projected[key] = None

    return ExplicitAnswers(values=projected)

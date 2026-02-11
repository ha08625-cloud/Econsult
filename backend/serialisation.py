"""
Serialisation layer.

Produces three views:
- ClientStateView (for frontend rendering)
- ClinicalOutput (lossy, portable, for clinician use)
- AuditOutput (lossless, for debugging and regulation)

Serialisation never mutates state.
"""

from runtime_state import RuntimeState
from serialisation_contracts import ClinicalOutput, AuditOutput


def serialize_client_state(runtime: RuntimeState, ruleset: dict) -> dict:
    """
    Project RuntimeState + ruleset into the ClientStateView dict
    expected by the frontend.

    The ruleset is needed because RuntimeState does not store
    question text -- only answer_key and values.

    Output shape matches frontend types.ts ClientStateView:
    {
        condition_label: str,
        free_text: str | null,
        questions: [
            {
                answer_key: str,
                question_text: str,
                answer_type: "boolean" | "text",
                current_value: bool | str | null,
                required: true,
                suggested: bool,
            }
        ]
    }
    """

    questions = []
    for q in ruleset["questions"]:
        answer_key = q["answer_key"]
        answer = runtime.answers[answer_key]

        questions.append({
            "answer_key": answer_key,
            "question_text": q["question"],
            "answer_type": answer.answer_type,
            "current_value": answer.value,
            "required": True,  # MVP: all questions required
            "suggested": answer.source == "encoder",
        })

    return {
        "condition_label": ruleset.get("presentation", {}).get("label", ruleset["condition_id"]),
        "free_text": runtime.free_text or None,
        "questions": questions,
    }


def clinical_output(runtime: RuntimeState) -> ClinicalOutput:
    """Lossy output safe for clinical and patient use."""
    return ClinicalOutput(
        condition_id=runtime.condition_id,
        free_text=runtime.free_text,
        answers={k: v.value for k, v in runtime.answers.items()},
        safety_messages=runtime.safety_evaluation.messages,
    )


def audit_output(runtime: RuntimeState) -> AuditOutput:
    """Lossless output for debugging, safety review, and regulation."""
    return AuditOutput(
        runtime_state=runtime.to_dict(),
        safety_evaluation=runtime.safety_evaluation.to_dict(),
        ruleset_version=runtime.ruleset_version,
    )
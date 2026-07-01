"""
Serialisation layer.

Produces three views:
- ClientStateView (for frontend rendering)
- ClinicalOutput (lossy, portable, for clinician use)
- AuditOutput (lossless, for debugging and regulation)

Serialisation never mutates state.

Architectural guarantee:
    This module never accesses presentation metadata directly.
    The condition_label for ClientStateView is passed in explicitly
    by the calling layer. The ruleset parameter contains only clinical
    data (questions, safety rules, encoder definitions).
"""

from app.models.runtime_state import RuntimeState
from app.models.serialisation_contracts import AuditOutput, ClinicalOutput, PatientDetails


def serialize_client_state(runtime: RuntimeState, ruleset: dict, condition_label: str) -> dict:
    """
    Project RuntimeState + ruleset into the ClientStateView dict
    expected by the frontend.

    Output shape matches frontend types.ts ClientStateView.
    additional_text is included so the frontend can pre-populate
    the field if the patient navigates back to EDIT.

    Number questions additionally carry decimal_places, min, max and an
    optional range_warning_text so the client can set the input step/min/max,
    perform its own precision check, and render a non-blocking out-of-range
    notice. No range computation happens here: the value passes through as the
    stored string and the client decides when to warn.

    A quantity (unit-toggle) Number question additionally carries quantity,
    allowed_systems and default_system. Its current_value is overridden to
    {"system", "components"} when answered (else null). Components are emitted as
    strings -- the same convention as a scalar Number's string current_value --
    so the client holds them verbatim while editing and converts to JSON numbers
    only at payload-build time.
    """

    questions = []
    for q in ruleset["questions"]:
        answer_key = q["answer_key"]
        answer = runtime.answers[answer_key]

        question_dict = {
            "answer_key": answer_key,
            "question_text": q["question"],
            "answer_type": answer.answer_type,
            "current_value": answer.value,
            "required": True,  # MVP: all questions required
            "suggested": answer.source == "encoder",
        }

        if q["answer_type"] == "Number":
            question_dict["decimal_places"] = q["decimal_places"]
            question_dict["min"] = q["min"]
            question_dict["max"] = q["max"]
            question_dict["range_warning_text"] = q.get("range_warning_text")

            if q.get("quantity"):
                question_dict["quantity"] = True
                question_dict["allowed_systems"] = q["allowed_systems"]
                question_dict["default_system"] = q["default_system"]
                if answer.raw_components is not None:
                    question_dict["current_value"] = {
                        "system": runtime.unit_system,
                        "components": {k: str(v) for k, v in answer.raw_components.items()},
                    }
                else:
                    question_dict["current_value"] = None

        questions.append(question_dict)

    return {
        "condition_label": condition_label,
        "free_text": runtime.free_text or None,
        "additional_text": runtime.additional_text,
        "questions": questions,
    }


def clinical_output(
    runtime: RuntimeState,
    ruleset: dict,
    patient_details: PatientDetails,
    contact_preferences: dict | None = None,
) -> ClinicalOutput:
    """
    Lossy output safe for clinical and patient use.
    """
    question_labels = {q["answer_key"]: q["question"] for q in ruleset["questions"]}

    # Sidecar for quantity (unit-toggle) answers: the lossless raw input plus a
    # snapshot of decimal_places, so the PDF formatter (which has no ruleset) can
    # render "11 st 11 lb (74.8 kg)". answers[key] still holds the canonical kg
    # string for these keys, unchanged.
    quantity_answers = {}
    for q in ruleset["questions"]:
        if not q.get("quantity"):
            continue
        key = q["answer_key"]
        a = runtime.answers[key]
        if a.raw_components is not None:
            quantity_answers[key] = {
                "raw_components": a.raw_components,
                "decimal_places": q["decimal_places"],
            }

    return ClinicalOutput(
        condition_id=runtime.condition_id,
        free_text=runtime.free_text,
        additional_text=runtime.additional_text,
        answers={k: v.value for k, v in runtime.answers.items()},
        safety_messages=runtime.safety_evaluation.messages,
        question_labels=question_labels,
        patient_details=patient_details,
        contact_preferences=contact_preferences,
        unit_system=runtime.unit_system,
        quantity_answers=quantity_answers,
    )


def audit_output(runtime: RuntimeState) -> AuditOutput:
    """Lossless output for debugging, safety review, and regulation."""
    return AuditOutput(
        runtime_state=runtime.to_dict(),
        safety_evaluation=runtime.safety_evaluation.to_dict(),
        ruleset_version=runtime.ruleset_version,
    )

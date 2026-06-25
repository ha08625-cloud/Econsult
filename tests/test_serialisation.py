"""
Unit tests for Number-field passthrough in serialize_client_state.

Asserts the client view carries decimal_places/min/max/range_warning_text for
Number questions, omits them for other types, and exposes the stored string as
current_value. No range computation happens server-side. Pure unit tests.
"""

from app.models.runtime_state import RuntimeState, AnswerState, SafetyEvaluation
from app.services.engine.serialisation import serialize_client_state


def _ruleset(range_warning_text="Please check this value."):
    q = {
        "question_id": "q1",
        "question": "What is your weight in kg?",
        "answer_key": "weight",
        "answer_type": "Number",
        "decimal_places": 1,
        "min": 2,
        "max": 400,
        "send_to_encoder": False,
        "encoder_prompt": None,
    }
    if range_warning_text is not None:
        q["range_warning_text"] = range_warning_text
    return {
        "condition_id": "demo",
        "questions": [
            q,
            {
                "question_id": "q2",
                "question": "Any other notes?",
                "answer_key": "notes",
                "answer_type": "text",
                "send_to_encoder": False,
                "encoder_prompt": None,
            },
        ],
        "safety": {"rules": {}},
    }


def _runtime(weight_value):
    return RuntimeState(
        condition_id="demo",
        ruleset_version="hash",
        free_text="",
        additional_text=None,
        answers={
            "weight": AnswerState(weight_value, "patient", None, "number"),
            "notes": AnswerState("hi", "patient", None, "text"),
        },
        safety_evaluation=SafetyEvaluation(),
        metadata={},
    )


def _weight_question(view):
    return next(q for q in view["questions"] if q["answer_key"] == "weight")


def _notes_question(view):
    return next(q for q in view["questions"] if q["answer_key"] == "notes")


def test_number_question_passes_through_bounds_and_precision():
    view = serialize_client_state(_runtime("70.5"), _ruleset(), "Demo")
    q = _weight_question(view)
    assert q["decimal_places"] == 1
    assert q["min"] == 2
    assert q["max"] == 400


def test_number_question_passes_through_range_warning_text():
    view = serialize_client_state(_runtime("70.5"), _ruleset("Check this."), "Demo")
    assert _weight_question(view)["range_warning_text"] == "Check this."


def test_range_warning_text_is_none_when_unauthored():
    view = serialize_client_state(_runtime("70.5"), _ruleset(range_warning_text=None), "Demo")
    assert _weight_question(view)["range_warning_text"] is None


def test_current_value_is_the_stored_string():
    view = serialize_client_state(_runtime("70.5"), _ruleset(), "Demo")
    assert _weight_question(view)["current_value"] == "70.5"


def test_number_answer_type_is_lowercased():
    view = serialize_client_state(_runtime("70.5"), _ruleset(), "Demo")
    assert _weight_question(view)["answer_type"] == "number"


def test_non_number_question_omits_number_fields():
    view = serialize_client_state(_runtime("70.5"), _ruleset(), "Demo")
    notes = _notes_question(view)
    assert "decimal_places" not in notes
    assert "min" not in notes
    assert "max" not in notes
    assert "range_warning_text" not in notes
"""
Unit tests for Number-field passthrough in serialize_client_state.

Asserts the client view carries decimal_places/min/max/range_warning_text for
Number questions, omits them for other types, and exposes the stored string as
current_value. No range computation happens server-side. Pure unit tests.

Also asserts the change_count audit counter surfaces in the lossless
AuditOutput (and only there).
"""

from app.models.runtime_state import AnswerState, RuntimeState, SafetyEvaluation
from app.models.serialisation_contracts import ClinicalOutput, PatientDetails
from app.services.engine.serialisation import (
    audit_output,
    clinical_output,
    serialize_client_state,
)


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


# ---------------------------------------------------------------------------
# change_count exposure
#
# change_count lives only in the lossless AuditOutput, reached via
# runtime.to_dict(). It does not appear in ClientStateView (serialize_client_state
# exposes only value/source) or ClinicalOutput (which keeps only value). This is
# the real exposure path, so it is the one guarded here.
# ---------------------------------------------------------------------------


def test_audit_output_exposes_change_count():
    rt = RuntimeState(
        condition_id="demo",
        ruleset_version="hash",
        free_text="",
        additional_text=None,
        answers={
            "flag": AnswerState(
                value=False,
                source="encoder_incorrect",
                encoder_value=True,
                answer_type="boolean",
                change_count=2,
            ),
        },
        safety_evaluation=SafetyEvaluation(),
        metadata={},
    )
    audit = audit_output(rt)
    assert audit.runtime_state["answers"]["flag"]["change_count"] == 2


# ---------------------------------------------------------------------------
# Quantity (unit-toggle) questions — client view
# ---------------------------------------------------------------------------


def _quantity_ruleset(allowed=("metric", "imperial"), default="metric", decimal_places=1):
    return {
        "condition_id": "demo",
        "questions": [
            {
                "question_id": "q1",
                "question": "What is your current weight?",
                "answer_key": "weight",
                "answer_type": "Number",
                "decimal_places": decimal_places,
                "min": 2,
                "max": 400,
                "range_warning_text": "Please check this value.",
                "send_to_encoder": False,
                "encoder_prompt": None,
                "quantity": True,
                "quantity_kind": "weight",
                "allowed_systems": list(allowed),
                "default_system": default,
            }
        ],
        "safety": {"rules": {}},
    }


def _quantity_runtime(value, raw_components, unit_system):
    return RuntimeState(
        condition_id="demo",
        ruleset_version="hash",
        free_text="",
        additional_text=None,
        answers={
            "weight": AnswerState(
                value=value,
                source="patient",
                encoder_value=None,
                answer_type="number",
                raw_components=raw_components,
                unit_system=unit_system,
            ),
        },
        safety_evaluation=SafetyEvaluation(),
        metadata={},
    )


def test_quantity_question_emits_toggle_fields():
    view = serialize_client_state(
        _quantity_runtime("74.8", {"st": 11, "lb": 11}, "imperial"),
        _quantity_ruleset(),
        "Demo",
    )
    q = _weight_question(view)
    assert q["quantity"] is True
    assert q["quantity_kind"] == "weight"
    assert q["allowed_systems"] == ["metric", "imperial"]
    assert q["default_system"] == "metric"


def test_quantity_answered_imperial_current_value():
    view = serialize_client_state(
        _quantity_runtime("74.8", {"st": 11, "lb": 11}, "imperial"),
        _quantity_ruleset(),
        "Demo",
    )
    cv = _weight_question(view)["current_value"]
    assert cv == {"system": "imperial", "components": {"st": "11", "lb": "11"}}


def test_quantity_answered_metric_current_value():
    view = serialize_client_state(
        _quantity_runtime("70.5", {"kg": "70.5"}, "metric"),
        _quantity_ruleset(),
        "Demo",
    )
    cv = _weight_question(view)["current_value"]
    assert cv == {"system": "metric", "components": {"kg": "70.5"}}


def test_quantity_components_are_strings_on_the_wire():
    # Components travel as strings outbound (same convention as a scalar Number's
    # string current_value), even though they persist as ints for st/lb.
    view = serialize_client_state(
        _quantity_runtime("74.8", {"st": 11, "lb": 11}, "imperial"),
        _quantity_ruleset(),
        "Demo",
    )
    comps = _weight_question(view)["current_value"]["components"]
    assert all(isinstance(v, str) for v in comps.values())


def test_quantity_unanswered_current_value_is_null_but_fields_present():
    view = serialize_client_state(
        _quantity_runtime(None, None, None),
        _quantity_ruleset(),
        "Demo",
    )
    q = _weight_question(view)
    assert q["current_value"] is None
    assert q["quantity"] is True
    assert q["default_system"] == "metric"


# ---------------------------------------------------------------------------
# Quantity questions — clinical output
# ---------------------------------------------------------------------------


def _patient_details():
    return PatientDetails(
        patient_for="me",
        first_name="Joe",
        last_name="Bloggs",
        date_of_birth="1990-03-15",
        postcode="SW1A 1AA",
        gender="male",
    )


def test_clinical_output_records_unit_system():
    # The form-level ClinicalOutput.unit_system field is gone; the patient's
    # chosen system now lives in the per-answer sidecar entry.
    out = clinical_output(
        _quantity_runtime("74.8", {"st": 11, "lb": 11}, "imperial"),
        _quantity_ruleset(),
        _patient_details(),
    )
    assert out.quantity_answers["weight"]["unit_system"] == "imperial"


def test_clinical_output_quantity_answers_sidecar():
    out = clinical_output(
        _quantity_runtime("74.8", {"st": 11, "lb": 11}, "imperial"),
        _quantity_ruleset(),
        _patient_details(),
    )
    assert out.quantity_answers == {
        "weight": {
            "quantity_kind": "weight",
            "raw_components": {"st": 11, "lb": 11},
            "unit_system": "imperial",
            "decimal_places": 1,
        }
    }


def test_clinical_output_answer_is_canonical_kg_string():
    out = clinical_output(
        _quantity_runtime("74.8", {"st": 11, "lb": 11}, "imperial"),
        _quantity_ruleset(),
        _patient_details(),
    )
    # answers[key] stays the canonical kg string; raw input lives in the sidecar.
    assert out.answers["weight"] == "74.8"


def test_clinical_output_from_dict_roundtrip_preserves_quantity_fields():
    out = clinical_output(
        _quantity_runtime("70.5", {"kg": "70.5"}, "metric"),
        _quantity_ruleset(),
        _patient_details(),
    )
    # Simulate JSONB round-trip via the dataclass dict form.
    from dataclasses import asdict

    restored = ClinicalOutput.from_dict(asdict(out))
    assert restored.quantity_answers == {
        "weight": {
            "quantity_kind": "weight",
            "raw_components": {"kg": "70.5"},
            "unit_system": "metric",
            "decimal_places": 1,
        }
    }


def test_clinical_output_from_dict_defaults_for_legacy_record():
    # A record predating quantity support has neither key.
    legacy = {
        "condition_id": "demo",
        "free_text": "",
        "additional_text": None,
        "answers": {"has_pain": True},
        "safety_messages": [],
        "question_labels": {"has_pain": "Pain?"},
        "patient_details": {
            "patient_for": "me",
            "first_name": "Joe",
            "last_name": "Bloggs",
            "date_of_birth": "1990-03-15",
            "postcode": "SW1A 1AA",
            "gender": "male",
        },
    }
    restored = ClinicalOutput.from_dict(legacy)
    assert restored.quantity_answers == {}
    assert restored.pdf_labels == {}


# ---------------------------------------------------------------------------
# pdf_labels -- CLINICAL SUMMARY snapshot
# ---------------------------------------------------------------------------


def _pdf_label_ruleset():
    rs = _ruleset()
    rs["questions"][0]["pdf_label"] = "Weight"
    return rs


def test_clinical_output_collects_authored_pdf_labels():
    out = clinical_output(_runtime("70.5"), _pdf_label_ruleset(), _patient_details())
    assert out.pdf_labels == {"weight": "Weight"}


def test_clinical_output_pdf_labels_empty_when_none_authored():
    out = clinical_output(_runtime("70.5"), _ruleset(), _patient_details())
    assert out.pdf_labels == {}


def test_clinical_output_pdf_labels_round_trip():
    from dataclasses import asdict

    out = clinical_output(_runtime("70.5"), _pdf_label_ruleset(), _patient_details())
    restored = ClinicalOutput.from_dict(asdict(out))
    assert restored.pdf_labels == {"weight": "Weight"}

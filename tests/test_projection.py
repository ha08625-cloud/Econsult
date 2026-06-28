"""
Unit tests for the projection allow-list.

project_explicit_answers is the single choke point deciding which answers reach
the safety engine. These tests lock the membership of EXPLICIT_SOURCES and the
None-projection of every excluded source. Pure unit tests — no database, no
FastAPI — so this module carries no integration marker.
"""

from app.models.runtime_state import RuntimeState, AnswerState, SafetyEvaluation
from app.services.engine.projection import EXPLICIT_SOURCES, project_explicit_answers


def _runtime(source, value):
    return RuntimeState(
        condition_id="demo",
        ruleset_version="hash",
        free_text="",
        additional_text=None,
        answers={
            "flag": AnswerState(
                value=value,
                source=source,
                encoder_value=None,
                answer_type="boolean",
            )
        },
        safety_evaluation=SafetyEvaluation(),
        metadata={},
    )


def test_explicit_sources_is_exactly_the_three_explicit_states():
    # Exact equality, not membership: catches an accidental future addition
    # (e.g. raw "encoder") leaking unconfirmed signals into safety.
    assert EXPLICIT_SOURCES == {"patient", "encoder_correct", "encoder_incorrect"}


def test_patient_value_is_projected():
    projected = project_explicit_answers(_runtime("patient", True))
    assert projected.values["flag"] is True


def test_encoder_correct_value_is_projected():
    projected = project_explicit_answers(_runtime("encoder_correct", True))
    assert projected.values["flag"] is True


def test_encoder_incorrect_value_is_projected():
    projected = project_explicit_answers(_runtime("encoder_incorrect", False))
    assert projected.values["flag"] is False


def test_raw_encoder_is_projected_as_none_even_with_a_value():
    # An unconfirmed encoder suggestion must read as unknown to safety, never
    # as its stored value.
    projected = project_explicit_answers(_runtime("encoder", True))
    assert projected.values["flag"] is None


def test_unanswered_is_projected_as_none():
    projected = project_explicit_answers(_runtime("unanswered", None))
    assert projected.values["flag"] is None
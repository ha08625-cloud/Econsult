from typing import Dict, Any, List
from dataclasses import dataclass

from runtime_state import RuntimeState
from projection import project_to_explicit_answers
from safety_engine import evaluate_safety
from serialization import serialize_client_state, serialize_clinical_output, serialize_audit_output
from ruleset import load_ruleset, compute_ruleset_hash
from encoder_mapping import apply_encoder_mapping
from form_logic import (
    initialise_runtime_state,
    apply_patient_answers,
    normalise_encoder_provenance,
    validate_required_answers,
)


@dataclass
class SafetyMessage:
    rule_id: str
    message: str


def init_runtime_state(condition_id: str, free_text: str | None):
    ruleset = load_ruleset(condition_id)
    ruleset_hash = compute_ruleset_hash(ruleset)

    runtime_state = initialise_runtime_state(ruleset)

    if free_text:
        runtime_state.free_text = free_text
        apply_encoder_mapping(runtime_state, ruleset, free_text)

    client_state = serialize_client_state(runtime_state, ruleset)

    return runtime_state, ruleset_hash, client_state


def apply_update_and_evaluate(
    runtime_state: RuntimeState,
    answers: Dict[str, Any],
):
    apply_patient_answers(runtime_state, answers)

    validate_required_answers(runtime_state)

    normalise_encoder_provenance(runtime_state)

    explicit_answers = project_to_explicit_answers(runtime_state)

    safety_eval = evaluate_safety(explicit_answers)

    safety_messages: List[SafetyMessage] = [
        SafetyMessage(rule_id=r.rule_id, message=r.message)
        for r in safety_eval.triggered_rules
    ]

    client_state = serialize_client_state(runtime_state)

    return runtime_state, client_state, safety_messages


def finish_runtime_state(runtime_state: RuntimeState) -> str:
    clinical = serialize_clinical_output(runtime_state)
    audit = serialize_audit_output(runtime_state)

    # out of scope persistence / handoff
    submission_id = audit.submission_id

    return submission_id

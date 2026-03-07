"""
Orchestration layer.

Wires together: ruleset loading, encoder, form logic, projection,
safety evaluation, and serialisation.

This is the only module permitted to coordinate across engine boundaries.
main.py calls these entry points; they return API-ready data.

Architectural guarantee:
    This module never imports or accesses condition_registry or presentation
    metadata. The condition_label needed for ClientStateView is passed in
    explicitly by the HTTP layer.
"""

from typing import Dict, Any, List, Optional, Tuple

from contracts.runtime_state import RuntimeState
from contracts.encoder_contracts import EncoderOutput, EncoderSignalDefinition
from projection import project_explicit_answers
from safety_engine import evaluate_safety
from serialisation import serialize_client_state, clinical_output, audit_output
from contracts.serialisation_contracts import ClinicalOutput, AuditOutput
from ruleset import load_ruleset, ruleset_hash, extract_encoder_definitions
from encoder_stub import extract_signals
from encoder_mapping import apply_encoder_output
from form_logic import (
    initialise_runtime_state,
    apply_additional_text,
    apply_patient_answers,
    normalise_encoder_provenance,
    validate_required_answers,
)
from api_models import SafetyMessage


def init_runtime_state(
    condition_id: str,
    free_text: str | None,
    ruleset_path: str,
    condition_label: str,
):
    """Entry point for /form/init."""

    ruleset = load_ruleset(ruleset_path)
    rh = ruleset_hash(ruleset)

    runtime_state = initialise_runtime_state(ruleset, free_text or "")

    if free_text:
        encoder_defs_raw = extract_encoder_definitions(ruleset)
        encoder_defs = [
            EncoderSignalDefinition(
                answer_key=d["answer_key"],
                encoder_prompt=d["encoder_prompt"],
            )
            for d in encoder_defs_raw
        ]

        raw_signals = extract_signals(free_text, encoder_defs_raw)

        encoder_output = EncoderOutput(
            model_name="stub",
            model_version="0.1",
            ruleset_hash=rh,
            signals=raw_signals,
        )

        apply_encoder_output(runtime_state, encoder_output, encoder_defs)

    client_state = serialize_client_state(runtime_state, ruleset, condition_label)

    return runtime_state, rh, client_state


def apply_update_and_evaluate(
    runtime_state: RuntimeState,
    answers: Dict[str, Any],
    additional_text: Optional[str],
    ruleset_path: str,
    condition_label: str,
):
    """Entry point for /form/update."""

    ruleset = load_ruleset(ruleset_path)

    apply_additional_text(runtime_state, additional_text)

    apply_patient_answers(runtime_state, answers)

    normalise_encoder_provenance(runtime_state)

    validate_required_answers(runtime_state)

    explicit_answers = project_explicit_answers(runtime_state)
    safety_rules = ruleset.get("safety", {}).get("rules", {})
    safety_eval = evaluate_safety(explicit_answers, safety_rules)

    runtime_state.safety_evaluation = safety_eval

    safety_messages: List[SafetyMessage] = [
        SafetyMessage(
            rule_id=m["id"],
            message=m["text"],
        )
        for m in safety_eval.messages
    ]

    client_state = serialize_client_state(runtime_state, ruleset, condition_label)

    return runtime_state, client_state, safety_messages


def finish_runtime_state(
    runtime_state: RuntimeState,
    ruleset_path: str,
) -> Tuple[ClinicalOutput, AuditOutput]:
    """Entry point for /form/finish."""

    ruleset = load_ruleset(ruleset_path)

    clinical = clinical_output(runtime_state, ruleset)
    audit = audit_output(runtime_state)

    return clinical, audit
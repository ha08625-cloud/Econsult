"""
Orchestration layer.

Wires together: ruleset loading, encoder, form logic, projection,
safety evaluation, and serialisation.

This is the only module permitted to coordinate across engine boundaries.
main.py calls these entry points; they return API-ready data.

Architectural guarantee:
    This module never imports or accesses condition_registry or presentation
    metadata. The condition_label needed for ClientStateView is passed in
    explicitly by the HTTP layer. The clinical engine operates exactly as
    if presentation metadata never existed.
"""

import uuid
from typing import Dict, Any, List

from contracts.runtime_state import RuntimeState
from contracts.encoder_contracts import EncoderOutput, EncoderSignalDefinition
from projection import project_explicit_answers
from safety_engine import evaluate_safety
from serialisation import serialize_client_state, clinical_output, audit_output
from ruleset import load_ruleset, ruleset_hash, extract_encoder_definitions
from encoder_stub import extract_signals
from encoder_mapping import apply_encoder_output
from form_logic import (
    initialise_runtime_state,
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
    """
    Entry point for /form/init.

    Loads ruleset, creates blank RuntimeState, runs encoder if free text
    is provided, and returns the state + hash + client view.
    """

    ruleset = load_ruleset(ruleset_path)
    rh = ruleset_hash(ruleset)

    runtime_state = initialise_runtime_state(ruleset, free_text or "")

    if free_text:
        # Extract encoder definitions from ruleset
        encoder_defs_raw = extract_encoder_definitions(ruleset)
        encoder_defs = [
            EncoderSignalDefinition(
                answer_key=d["answer_key"],
                encoder_prompt=d["encoder_prompt"],
            )
            for d in encoder_defs_raw
        ]

        # Run stub encoder (returns plain dict)
        raw_signals = extract_signals(free_text, encoder_defs_raw)

        # Wrap in EncoderOutput contract
        encoder_output = EncoderOutput(
            model_name="stub",
            model_version="0.1",
            ruleset_hash=rh,
            signals=raw_signals,
        )

        # Apply to RuntimeState (validates + maps)
        apply_encoder_output(runtime_state, encoder_output, encoder_defs)

    client_state = serialize_client_state(runtime_state, ruleset, condition_label)

    return runtime_state, rh, client_state


def apply_update_and_evaluate(
    runtime_state: RuntimeState,
    answers: Dict[str, Any],
    ruleset_path: str,
    condition_label: str,
):
    """
    Entry point for /form/update.

    Applies patient answers, normalises encoder provenance,
    validates completeness, projects to explicit answers,
    evaluates safety, and returns updated state + client view + safety messages.
    """

    ruleset = load_ruleset(ruleset_path)

    apply_patient_answers(runtime_state, answers)

    normalise_encoder_provenance(runtime_state)

    validate_required_answers(runtime_state)

    # Project to explicit answers then evaluate safety
    explicit_answers = project_explicit_answers(runtime_state)
    safety_rules = ruleset.get("safety", {}).get("rules", {})
    safety_eval = evaluate_safety(explicit_answers, safety_rules)

    # Store safety evaluation on runtime state
    runtime_state.safety_evaluation = safety_eval

    # Build safety messages for API response
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
) -> str:
    """
    Entry point for /form/finish.

    Generates clinical and audit outputs.
    Returns a submission_id.
    """

    clinical = clinical_output(runtime_state)
    audit = audit_output(runtime_state)

    # TODO: persist clinical + audit outputs to storage
    # For MVP, just generate a submission ID
    submission_id = str(uuid.uuid4())

    return submission_id
"""
Apply encoder output to RuntimeState.

This module is the containment boundary between probabilistic inference
(encoder) and clinical state.

Encoder output may only populate unanswered fields.
Encoder may never overwrite patient input.
Encoder influence is fully contained in this module.
"""

from app.models.runtime_state import RuntimeState
from app.services.encoder_contracts import EncoderOutput, EncoderSignalDefinition
from typing import Iterable


def apply_encoder_output(
    runtime: RuntimeState,
    encoder_output: EncoderOutput,
    encoder_definitions: Iterable[EncoderSignalDefinition],
) -> None:
    """
    Apply validated encoder output to RuntimeState.

    Rules:
    - encoder_output is validated against definitions before any mutation
    - Only unanswered fields are populated
    - Encoder never overwrites patient or previously set values
    - Raw encoder output is stored in metadata for audit
    """

    encoder_output.validate_against(encoder_definitions)

    # Store raw encoder output for audit trail (as plain dict for JSON serialisation)
    from dataclasses import asdict
    runtime.metadata.setdefault("audit", {})
    runtime.metadata["audit"]["encoder_output"] = asdict(encoder_output)

    for defn in encoder_definitions:
        answer_key = defn.answer_key
        inferred_value = encoder_output.signals[answer_key]

        answer = runtime.answers[answer_key]

        # Encoder may never overwrite explicit input
        if answer.source != "unanswered":
            continue

        if inferred_value is None:
            continue

        # Apply encoder suggestion
        answer.value = inferred_value
        answer.encoder_value = inferred_value
        answer.source = "encoder"

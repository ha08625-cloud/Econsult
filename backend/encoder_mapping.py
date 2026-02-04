"""
Apply encoder output to RuntimeState.  This module is the containment boundary between probabilistic inference
(encoder) and clinical state
"""

from runtime_state import RuntimeState
from contracts.encoder_contracts import EncoderOutput, EncoderSignalDefinition
from typing import Dict, Iterable


def apply_encoder_output(
    runtime: RuntimeState,
    encoder_output: EncoderOutput,
    signal_definitions: Iterable[EncoderSignalDefinition],
) -> None:

    encoder_output.validate_against(signal_definitions)

    runtime.metadata.setdefault("audit", {})
    runtime.metadata["audit"]["encoder_output"] = encoder_output

    for signal_def in signal_definitions:
        answer_key = signal_def.answer_key
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

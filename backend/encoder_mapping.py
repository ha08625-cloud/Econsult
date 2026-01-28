"""
takes encoder signals and inteprets them into answers
"""

from typing import Dict, Optional
from runtime_state import RuntimeState


def apply_encoder_signals(
    runtime: RuntimeState,
    signal_to_answer_key: Dict[str, str],
    encoder_output: Dict[str, Optional[bool]],
) -> None:
    """
    Apply encoder output to RuntimeState.

    Rules:
    - Encoder never overwrites user input
    - Encoder only populates unanswered fields
    - Mapping failures are fatal
    """

    # Fail loud: unknown signal
    for signal_id in encoder_output:
        if signal_id not in signal_to_answer_key:
            raise ValueError(f"Unknown signal_id: {signal_id}")

    # Preserve raw encoder output for audit
    runtime.metadata.setdefault("audit", {})
    runtime.metadata["audit"]["encoder_raw"] = encoder_output.copy()

    for signal_id, value in encoder_output.items():
        answer_key = signal_to_answer_key[signal_id]
        answer = runtime.answers[answer_key]

        if answer.source != "unanswered":
            continue

        if value is None:
            continue

        answer.value = value
        answer.encoder_value = value
        answer.source = "encoder"

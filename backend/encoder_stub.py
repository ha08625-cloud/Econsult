"""
encoder stub
will be replaced in entirety by real stub
only purpose is to test output signals are received and interpreted
"""

from typing import Dict, Optional, List

def extract_signals(
    free_text: Optional[str],
    encoder_definitions: List[dict],
) -> Dict[str, Optional[bool]]:
    """
    Stub encoder.
    Non-goals:
    - accuracy
    - NLP
    - negation
    - confidence
    - realism
    """

    # Fail soft
    if not free_text:
        return {d["signal_id"]: None for d in encoder_definitions}

    text = free_text.lower()
    output: Dict[str, Optional[bool]] = {}

    for d in encoder_definitions:
        signal_id = d["signal_id"]

        if "no" in text:
            output[signal_id] = False
        elif signal_id == "fever_present" and "fever" in text:
            output[signal_id] = True
        elif signal_id == "dysuria_present" and "burn" in text:
            output[signal_id] = True
        elif signal_id == "frequency_present" and "frequency" in text:
            output[signal_id] = True
        else:
            output[signal_id] = None

    return output

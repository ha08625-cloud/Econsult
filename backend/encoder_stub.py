"""
encoder stub
will be replaced in entirety by real encoder
only purpose is to test output signals are received and interpreted
"""

from typing import Dict, Optional, List


def extract_signals(
    free_text: Optional[str],
    encoder_definitions: List[dict],
) -> Dict[str, Optional[bool]]:
    """
    Stub encoder.
    Input: free text + encoder definitions (answer_key + encoder_prompt pairs)
    Output: {answer_key: True | False | None}

    Non-goals:
    - accuracy
    - NLP
    - negation
    - confidence
    - realism
    """

    if not free_text:
        return {d["answer_key"]: None for d in encoder_definitions}

    text = free_text.lower()
    output: Dict[str, Optional[bool]] = {}

    for d in encoder_definitions:
        answer_key = d["answer_key"]

        if "no" in text:
            output[answer_key] = False
        elif answer_key == "fever_present" and "fever" in text:
            output[answer_key] = True
        elif answer_key == "dysuria_present" and "burn" in text:
            output[answer_key] = True
        elif answer_key == "frequency_present" and "frequency" in text:
            output[answer_key] = True
        else:
            output[answer_key] = None

    return output
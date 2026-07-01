"""
encoder stub
will be replaced in entirety by real stub
only purpose is to test output signals are received and interpreted
"""


def extract_signals(
    free_text: str | None,
    encoder_definitions: list[dict],
) -> dict[str, bool | None]:
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
        return {d["answer_key"]: None for d in encoder_definitions}

    text = free_text.lower()
    output: dict[str, bool | None] = {}

    for d in encoder_definitions:
        answer_key = d["answer_key"]

        if "no" in text:
            output[answer_key] = False
        elif (
            answer_key == "fever_present"
            and "fever" in text
            or answer_key == "dysuria_present"
            and "burn" in text
            or answer_key == "frequency_present"
            and "frequency" in text
        ):
            output[answer_key] = True
        else:
            output[answer_key] = None

    return output

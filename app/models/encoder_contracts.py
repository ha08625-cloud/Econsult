"""
This module defines the only data structures that may cross the boundary
between an encoder implementation (stub or ML-backed) and the rest of the
form engine
encoder_stub.py
encoder_mapping.py
"""

from collections.abc import Iterable
from dataclasses import dataclass


@dataclass(frozen=True)
class EncoderSignalDefinition:
    """
    This is a projection derived from the ruleset and is the *only* semantic
    information the encoder is allowed to see about a signal.
    """

    answer_key: str
    encoder_prompt: str


@dataclass(frozen=True)
class EncoderOutput:
    """
    This object is the sole permissible output of an encoder and the sole
    permissible input to encoder_mapping.
    """

    model_name: str
    model_version: str
    ruleset_hash: str
    signals: dict[str, bool | None]

    def validate_against(self, definitions: Iterable[EncoderSignalDefinition]) -> None:
        """
        Validate that this output exactly matches the provided signal definitions.
        """

        expected_keys = {d.answer_key for d in definitions}
        output_keys = set(self.signals.keys())

        if output_keys != expected_keys:
            missing = expected_keys - output_keys
            extra = output_keys - expected_keys
            raise ValueError(
                "EncoderOutput keys do not match signal definitions. "
                f"Missing={missing}, Extra={extra}"
            )

        for key, value in self.signals.items():
            if value not in (True, False, None):
                raise TypeError(
                    f"Invalid encoder value for {key}: {value!r}. Expected True, False, or None."
                )

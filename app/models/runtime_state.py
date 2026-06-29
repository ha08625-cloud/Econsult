"""
The data contract for canonical runtime state.

This module defines what state can exist, not how it is used.
No business logic. No IO. No encoder awareness. No safety logic.
"""

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Dict, Any, Optional, Literal

AnswerSource = Literal[
    "unanswered",
    "encoder",
    "encoder_correct",
    "encoder_incorrect",
    "patient",
]


@dataclass
class AnswerState:
    """
    encoder_value:
        populated only if encoder ran
        may differ from value if user corrected
        never authoritative

    value:
        For "boolean" answers this is a bool; for "text" answers a str.
        For "number" answers the *persisted* form is always a str (e.g. "70.5"),
        which keeps the value exact through JSONB round-trips. int and Decimal
        appear only transiently inside a single /form/update request, between
        apply_patient_answers (which receives them from the parsed body) and
        normalise_number_answers (which stringifies them before persistence).
        Numbers never reach the encoder, so encoder_value stays bool-or-None.

    change_count:
        Net change events recorded for this answer, accumulated across submits.
        Maintained only for encoder-suggested answers (encoder_value is not
        None); it stays 0 for text and number answers and for encoder-null
        booleans. The baseline is the encoder prefill (count starts at 0, since
        the prefill is not a patient change), and it increments by at most one
        per submit, only when the submitted value differs from the currently
        committed value (see form_logic.apply_patient_answers). It rides in the
        state_json JSONB blob (no migration) and surfaces only in the lossless
        AuditOutput. Because each increment on a boolean is a flip, parity is an
        invariant: even count <-> encoder_correct, odd count <-> encoder_incorrect.
    """
    value: bool | str | int | float | Decimal | None
    source: AnswerSource
    encoder_value: Optional[bool]
    answer_type: Literal["boolean", "text", "number"]
    change_count: int = 0

    def to_dict(self) -> dict:
        return {
            "value": self.value,
            "source": self.source,
            "encoder_value": self.encoder_value,
            "answer_type": self.answer_type,
            "change_count": self.change_count,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "AnswerState":
        return cls(
            value=d["value"],
            source=d["source"],
            encoder_value=d["encoder_value"],
            answer_type=d["answer_type"],
            # Default to 0 so already-persisted states that predate the field
            # deserialise cleanly.
            change_count=d.get("change_count", 0),
        )


@dataclass
class SafetyEvaluation:
    triggered_rules: list[str] = field(default_factory=list)
    messages: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "triggered_rules": list(self.triggered_rules),
            "messages": list(self.messages),
        }

    @classmethod
    def from_dict(cls, d: dict) -> "SafetyEvaluation":
        return cls(
            triggered_rules=list(d["triggered_rules"]),
            messages=list(d["messages"]),
        )


@dataclass
class RuntimeState:
    condition_id: str
    ruleset_version: str
    free_text: str
    additional_text: Optional[str]
    answers: Dict[str, AnswerState]
    safety_evaluation: SafetyEvaluation
    metadata: Dict[str, Any]

    def to_dict(self) -> dict:
        return {
            "condition_id": self.condition_id,
            "ruleset_version": self.ruleset_version,
            "free_text": self.free_text,
            "additional_text": self.additional_text,
            "answers": {k: v.to_dict() for k, v in self.answers.items()},
            "safety_evaluation": self.safety_evaluation.to_dict(),
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "RuntimeState":
        if isinstance(d, str):
            import json
            d = json.loads(d)
        return cls(
            condition_id=d["condition_id"],
            ruleset_version=d["ruleset_version"],
            free_text=d["free_text"],
            additional_text=d.get("additional_text"),
            answers={k: AnswerState.from_dict(v) for k, v in d["answers"].items()},
            safety_evaluation=SafetyEvaluation.from_dict(d["safety_evaluation"]),
            metadata=d["metadata"],
        )
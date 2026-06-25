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
    "encoder_confirmed",
    "encoder_corrected",
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
    """
    value: bool | str | int | float | Decimal | None
    source: AnswerSource
    encoder_value: Optional[bool]
    answer_type: Literal["boolean", "text", "number"]

    def to_dict(self) -> dict:
        return {
            "value": self.value,
            "source": self.source,
            "encoder_value": self.encoder_value,
            "answer_type": self.answer_type,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "AnswerState":
        return cls(
            value=d["value"],
            source=d["source"],
            encoder_value=d["encoder_value"],
            answer_type=d["answer_type"],
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
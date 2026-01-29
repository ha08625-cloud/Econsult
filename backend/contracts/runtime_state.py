"""
The data contract for canonical runtime state
"""

from dataclasses import dataclass, field
from typing import Dict, Any, Optional, Literal

AnswerSource = Literal[
    "unanswered",
    "encoder",
    "encoder_confirmed",
    "encoder_corrected",
    "patient",
]
"""
encoder_value:
populated only if encoder ran
may differ from value if user corrected
never authoritative
"""
@dataclass
class AnswerState:
    value: Optional[Any]
    source: AnswerSource
    encoder_value: Optional[bool]


@dataclass
class SafetyEvaluation:
    triggered_rules: list[str] = field(default_factory=list)
    messages: list[str] = field(default_factory=list)


@dataclass
class RuntimeState:
    condition_id: str
    ruleset_version: str
    free_text: str
    answers: Dict[str, AnswerState]
    safety_evaluation: SafetyEvaluation
    metadata: Dict[str, Any]

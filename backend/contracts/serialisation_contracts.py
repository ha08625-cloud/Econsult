from dataclasses import dataclass
from typing import Dict, Any, List


@dataclass(frozen=True)
class ClinicalOutput:
    condition_id: str
    free_text: str
    answers: Dict[str, Any]
    safety_messages: List[dict]


@dataclass(frozen=True)
class AuditOutput:
    runtime_state: Dict[str, Any]
    safety_evaluation: Dict[str, Any]
    ruleset_version: str
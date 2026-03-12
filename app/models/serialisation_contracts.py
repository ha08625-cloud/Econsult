from dataclasses import dataclass
from typing import Dict, Any, List, Optional


@dataclass(frozen=True)
class ClinicalOutput:
    condition_id: str
    free_text: str
    additional_text: Optional[str]
    answers: Dict[str, Any]
    safety_messages: List[dict]
    question_labels: Dict[str, str]  # answer_key -> question text at submission time


@dataclass(frozen=True)
class AuditOutput:
    runtime_state: Dict[str, Any]
    safety_evaluation: Dict[str, Any]
    ruleset_version: str

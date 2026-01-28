"""
export for clinicians
"""

from typing import Dict, Any
from runtime_state import RuntimeState

def clinical_output(runtime: RuntimeState) -> dict:
    return {
        "condition_id": runtime.condition_id,
        "free_text": runtime.free_text,
        "answers": {
            k: v.value for k, v in runtime.answers.items()
        },
        "safety_messages": runtime.safety_evaluation.messages,
    }

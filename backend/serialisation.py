"""
Serialization layer.
- ClinicalOutput (lossy, portable)
- AuditOutput (lossless, internal)
"""

from runtime_state import RuntimeState
from serialization_contracts import ClinicalOutput, AuditOutput


def clinical_output(runtime: RuntimeState) -> ClinicalOutput:
    return ClinicalOutput(
        condition_id=runtime.condition_id,
        free_text=runtime.free_text,
        answers={k: v.value for k, v in runtime.answers.items()},
        safety_messages=runtime.safety_evaluation.messages,
    )


def audit_output(runtime: RuntimeState) -> AuditOutput:
    return AuditOutput(
        runtime_state=runtime.to_dict(),
        safety_evaluation=runtime.safety_evaluation.to_dict(),
        ruleset_version=runtime.ruleset_version,
    )

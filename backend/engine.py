from dataclasses import dataclass, field
from typing import Dict, Any, Optional, Literal
from datetime import datetime
import hashlib
import json

AnswerSource = Literal[
    "unanswered",
    "encoder",
    "encoder_confirmed",
    "encoder_corrected",
    "patient",
]

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

def load_ruleset(path: str) -> dict:
    with open(path, "r") as f:
        ruleset = json.load(f)
    validate_ruleset(ruleset)
    return ruleset


def ruleset_hash(ruleset: dict) -> str:
    payload = json.dumps(ruleset, sort_keys=True).encode()
    return hashlib.sha256(payload).hexdigest()

def validate_ruleset(ruleset: dict) -> None:
    assert "condition_id" in ruleset
    assert "questions" in ruleset and ruleset["questions"]

    seen_keys = set()

    for q in ruleset["questions"]:
        assert "answer_key" in q
        assert q["answer_key"] not in seen_keys
        seen_keys.add(q["answer_key"])

        if q["send_to_encoder"]:
            assert q["answer_type"] == "Boolean"
            assert q["encoder_prompt"] is not None
        else:
            assert q["encoder_prompt"] is None

    if "safety" in ruleset:
        for rule in ruleset["safety"]["rules"].values():
            for clause in rule.get("all", []):
                key = clause.get("is_true") or clause.get("is_false")
                assert key in seen_keys

def initialise_runtime_state(
    ruleset: dict,
    free_text: str,
    engine_version: str = "0.1",
) -> RuntimeState:
    answers = {
        q["answer_key"]: AnswerState(
            value=None,
            source="unanswered",
            encoder_value=None,
        )
        for q in ruleset["questions"]
    }

    return RuntimeState(
        condition_id=ruleset["condition_id"],
        ruleset_version=ruleset_hash(ruleset),
        free_text=free_text,
        answers=answers,
        safety_evaluation=SafetyEvaluation(),
        metadata={
            "engine_version": engine_version,
            "timestamp": datetime.utcnow().isoformat() + "Z",
        },
    )

def hydrate_runtime_state(
    incoming: RuntimeState,
    ruleset: dict,
) -> RuntimeState:
    assert incoming.ruleset_version == ruleset_hash(ruleset)

    rule_keys = {q["answer_key"] for q in ruleset["questions"]}
    state_keys = set(incoming.answers.keys())

    assert rule_keys == state_keys

    for a in incoming.answers.values():
        assert a.source in {
            "unanswered",
            "encoder",
            "encoder_confirmed",
            "encoder_corrected",
            "patient",
        }

    return incoming

def run_encoder_stub(free_text: str, ruleset: dict) -> Dict[str, bool]:
    text = free_text.lower()
    output = {}

    for q in ruleset["questions"]:
        if not q["send_to_encoder"]:
            continue

        key = q["answer_key"]
        if key == "fever_present":
            output[key] = "fever" in text or "hot" in text
        if key == "dysuria_present":
            output[key] = "burn" in text or "pain" in text

    return output

def apply_encoder(runtime: RuntimeState, ruleset: dict) -> None:
    eligible = (
        runtime.free_text.strip() != ""
        and any(
            q["send_to_encoder"]
            and runtime.answers[q["answer_key"]].source == "unanswered"
            for q in ruleset["questions"]
        )
    )

    if not eligible:
        return

    encoder_output = run_encoder_stub(runtime.free_text, ruleset)

    for key, value in encoder_output.items():
        a = runtime.answers[key]
        if a.source == "unanswered" and a.encoder_value is None:
            a.encoder_value = value
            a.value = value
            a.source = "encoder"

def patient_update(runtime: RuntimeState, answer_key: str, value: Any) -> None:
    a = runtime.answers[answer_key]

    a.value = value

    if a.source == "encoder":
        a.source = "encoder_corrected"
    else:
        a.source = "patient"

def normalise_on_submit(runtime: RuntimeState) -> None:
    for a in runtime.answers.values():
        if a.source == "encoder":
            a.source = "encoder_confirmed"

def evaluate_safety(runtime: RuntimeState, ruleset: dict) -> None:
    runtime.safety_evaluation = SafetyEvaluation()

    answers_view = {
        k: v.value for k, v in runtime.answers.items()
    }

    for rule_id, rule in ruleset.get("safety", {}).get("rules", {}).items():
        satisfied = all(
            answers_view.get(cond["is_true"]) is True
            for cond in rule.get("all", [])
        )

        if satisfied:
            runtime.safety_evaluation.triggered_rules.append(rule_id)
            runtime.safety_evaluation.messages.append(rule["message"])

def clinical_output(runtime: RuntimeState) -> dict:
    return {
        "condition_id": runtime.condition_id,
        "free_text": runtime.free_text,
        "answers": {
            k: v.value for k, v in runtime.answers.items()
        },
        "safety_messages": runtime.safety_evaluation.messages,
    }

ruleset = load_ruleset("uti1_revised.json")

state = initialise_runtime_state(
    ruleset,
    free_text="Burning when peeing and feel hot",
)

apply_encoder(state, ruleset)

patient_update(state, "fever_present", False)
patient_update(state, "symptom_onset_text", "2 days ago")

normalise_on_submit(state)
evaluate_safety(state, ruleset)

print(clinical_output(state))
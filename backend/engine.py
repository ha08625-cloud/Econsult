from dataclasses import dataclass, field
from typing import Dict, Any, Optional, Literal
from datetime import datetime
import hashlib
import json

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

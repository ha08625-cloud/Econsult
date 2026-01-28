from dataclasses import dataclass, field
from typing import Dict, Any, Optional, Literal
from datetime import datetime
import hashlib
import json

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

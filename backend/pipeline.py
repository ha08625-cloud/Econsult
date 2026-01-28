# thin orchestrator

from typing import Optional, Dict, Any

from ruleset import (
    load_ruleset,
    ruleset_hash,
    extract_encoder_definitions,
    extract_signal_to_answer_key_map,
)

from runtime_state import RuntimeState
from form_logic import (
    initialise_runtime_state,
    hydrate_runtime_state,
    normalise_on_submit,
    evaluate_safety,
)

from encoder_stub import extract_signals
from encoder_mapping import apply_encoder_signals
from serialization import clinical_output


def init_form(
    ruleset_path: str,
    free_text: Optional[str],
) -> RuntimeState:
    ruleset = load_ruleset(ruleset_path)

    runtime = initialise_runtime_state(
        ruleset=ruleset,
        free_text=free_text or "",
    )

    encoder_definitions = extract_encoder_definitions(ruleset)
    signal_map = extract_signal_to_answer_key_map(ruleset)

    encoder_output = extract_signals(free_text, encoder_definitions)

    apply_encoder_signals(
        runtime=runtime,
        signal_to_answer_key=signal_map,
        encoder_output=encoder_output,
    )

    return runtime


def submit_form(
    runtime: RuntimeState,
    ruleset_path: str,
) -> Dict[str, Any]:
    ruleset = load_ruleset(ruleset_path)

    hydrate_runtime_state(runtime, ruleset)

    normalise_on_submit(runtime)
    evaluate_safety(runtime, ruleset)

    return clinical_output(runtime)
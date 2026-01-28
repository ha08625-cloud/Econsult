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

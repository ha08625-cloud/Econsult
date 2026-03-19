# ruleset IO and validation

import json
import hashlib
from typing import Dict, Any, List


def load_ruleset(path: str) -> Dict[str, Any]:
    with open(path, "r") as f:
        ruleset = json.load(f)
    validate_ruleset(ruleset)
    return ruleset


def ruleset_hash(ruleset: Dict[str, Any]) -> str:
    payload = json.dumps(ruleset, sort_keys=True).encode()
    return hashlib.sha256(payload).hexdigest()


def validate_ruleset(ruleset: Dict[str, Any]) -> None:
    if "condition_id" not in ruleset:
        raise ValueError("Ruleset missing required field: condition_id")

    if "questions" not in ruleset or not ruleset["questions"]:
        raise ValueError("Ruleset missing or empty: questions")

    seen_answer_keys = set()

    for q in ruleset["questions"]:
        if "answer_key" not in q:
            raise ValueError("Question missing required field: answer_key")

        if q["answer_key"] in seen_answer_keys:
            raise ValueError(f"Duplicate answer_key: {q['answer_key']}")
        seen_answer_keys.add(q["answer_key"])

        if q.get("send_to_encoder"):
            if q.get("encoder_prompt") is None:
                raise ValueError(
                    f"Encoder question missing encoder_prompt: {q['answer_key']}"
                )
            if q.get("answer_type") != "Boolean":
                raise ValueError(
                    f"Encoder questions must be Boolean, got {q.get('answer_type')} "
                    f"for {q['answer_key']}"
                )
        else:
            if q.get("encoder_prompt") is not None:
                raise ValueError(
                    f"Non-encoder question must not have encoder_prompt: {q['answer_key']}"
                )

    if "safety" in ruleset:
        for rule_id, rule in ruleset["safety"]["rules"].items():
            for clause in rule.get("all", []):
                key = clause.get("is_true") or clause.get("is_false")
                if key not in seen_answer_keys:
                    raise ValueError(
                        f"Safety rule '{rule_id}' references unknown answer_key: {key}"
                    )


def extract_encoder_definitions(ruleset: Dict[str, Any]) -> List[Dict[str, str]]:
    """
    Returns the encoder-facing contract.
    Each definition contains answer_key + encoder_prompt.
    answer_key is the universal identifier -- no separate signal_id exists.
    """
    return [
        {
            "answer_key": q["answer_key"],
            "encoder_prompt": q["encoder_prompt"],
        }
        for q in ruleset["questions"]
        if q.get("send_to_encoder")
    ]

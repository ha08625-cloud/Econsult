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
    assert "condition_id" in ruleset
    assert "questions" in ruleset and ruleset["questions"]

    seen_answer_keys = set()

    for q in ruleset["questions"]:
        assert "answer_key" in q
        assert q["answer_key"] not in seen_answer_keys
        seen_answer_keys.add(q["answer_key"])

        if q.get("send_to_encoder"):
            assert q.get("encoder_prompt") is not None
            assert q.get("answer_type") == "Boolean", (
                f"Encoder questions must be Boolean, got {q.get('answer_type')} "
                f"for {q['answer_key']}"
            )
        else:
            assert q.get("encoder_prompt") is None

    if "safety" in ruleset:
        for rule in ruleset["safety"]["rules"].values():
            for clause in rule.get("any", []):
                key = clause.get("is_true")
                assert key in seen_answer_keys


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
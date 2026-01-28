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
    assert "condition_id" in ruleset
    assert "questions" in ruleset and ruleset["questions"]

    seen_answer_keys = set()
    seen_signal_ids = set()

    for q in ruleset["questions"]:
        assert "answer_key" in q
        assert q["answer_key"] not in seen_answer_keys
        seen_answer_keys.add(q["answer_key"])

        if q.get("send_to_encoder"):
            assert q.get("encoder_prompt") is not None
            assert q.get("signal_id") is not None
            assert q["signal_id"] not in seen_signal_ids
            seen_signal_ids.add(q["signal_id"])
        else:
            assert q.get("encoder_prompt") is None
            assert q.get("signal_id") is None

    if "safety" in ruleset:
        for rule in ruleset["safety"]["rules"].values():
            for clause in rule.get("all", []):
                key = clause.get("is_true") or clause.get("is_false")
                assert key in seen_answer_keys


def extract_encoder_definitions(ruleset: Dict[str, Any]) -> List[Dict[str, str]]:
    """
    Returns the encoder-facing contract
    """
    return [
        {
            "signal_id": q["signal_id"],
            "encoder_prompt": q["encoder_prompt"],
        }
        for q in ruleset["questions"]
        if q.get("send_to_encoder")
    ]


def extract_signal_to_answer_key_map(ruleset: Dict[str, Any]) -> Dict[str, str]:
    """
    Defines the only allowed mapping from encoder signals to answers
    """
    return {
        q["signal_id"]: q["answer_key"]
        for q in ruleset["questions"]
        if q.get("send_to_encoder")
    }
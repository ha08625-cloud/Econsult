"""
ruleset IO and validation
"""

import json
import hashlib
from typing import Dict, Any

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

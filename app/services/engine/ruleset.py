# ruleset IO and validation

import json
import hashlib
from decimal import Decimal
from functools import lru_cache
from typing import Dict, Any, List


# The complete set of answer types the engine understands. Authored in the
# ruleset's original (capitalised-Boolean) casing; runtime lowercases it.
VALID_ANSWER_TYPES = {"Boolean", "text", "Number"}


@lru_cache(maxsize=None)
def load_ruleset(path: str) -> Dict[str, Any]:
    """
    Loads, validates, and caches a ruleset by its file path.

    Cached for the lifetime of the process: rulesets only change via a
    redeploy (which starts a fresh process), never via a live edit while
    sessions are open, so re-reading and re-validating the same file on
    every request has no benefit. The first call for a given path does the
    real work (this is what wiring.py's startup validation exercises);
    every call after that returns the same cached dict. A failed load is
    not cached -- a path that raises will be retried on the next call.
    """
    with open(path, "r") as f:
        ruleset = json.load(f)
    validate_ruleset(ruleset)
    return ruleset


def ruleset_hash(ruleset: Dict[str, Any]) -> str:
    payload = json.dumps(ruleset, sort_keys=True).encode()
    return hashlib.sha256(payload).hexdigest()


def _is_number(x: Any) -> bool:
    """True for JSON numbers (int or float) but not bool."""
    return isinstance(x, (int, float)) and not isinstance(x, bool)


def _decimal_places(x: float) -> int:
    """
    Authoring-time decimal-place count for a bound (min/max). Uses
    Decimal(str(x)) so the shortest round-trippable repr is measured rather
    than the raw binary float, which keeps this exact for the small, authored
    values that appear in a ruleset. Startup-only; never on the request path.
    """
    exponent = Decimal(str(x)).as_tuple().exponent
    return -exponent if isinstance(exponent, int) and exponent < 0 else 0


def _validate_number_question(q: Dict[str, Any]) -> None:
    """Validate the Number-specific fields. Raises ValueError on any violation."""
    key = q["answer_key"]

    dp = q.get("decimal_places")
    if isinstance(dp, bool) or not isinstance(dp, int) or dp < 0:
        raise ValueError(
            f"Number question '{key}' requires decimal_places to be a "
            f"non-negative integer, got {dp!r}"
        )

    lo = q.get("min")
    hi = q.get("max")
    if not _is_number(lo) or not _is_number(hi):
        raise ValueError(
            f"Number question '{key}' requires numeric min and max, "
            f"got min={lo!r}, max={hi!r}"
        )
    if lo >= hi:
        raise ValueError(
            f"Number question '{key}' requires min < max, got min={lo}, max={hi}"
        )

    # A bound finer than the question's own precision is an authoring mistake:
    # it can never be entered or matched. Reject it fail-fast.
    if _decimal_places(lo) > dp or _decimal_places(hi) > dp:
        raise ValueError(
            f"Number question '{key}' has a min/max with more decimal places "
            f"than decimal_places={dp}"
        )

    rwt = q.get("range_warning_text")
    if rwt is not None and not isinstance(rwt, str):
        raise ValueError(
            f"Number question '{key}' range_warning_text must be a string or null, "
            f"got {rwt!r}"
        )


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

        # answer_type must be present and one of the known types. Previously only
        # encoder questions had their type checked; an unknown or missing type on
        # a non-encoder question slipped through to a runtime KeyError at init.
        answer_type = q.get("answer_type")
        if answer_type not in VALID_ANSWER_TYPES:
            raise ValueError(
                f"Question '{q['answer_key']}' has invalid or missing answer_type: "
                f"{answer_type!r}. Allowed: {sorted(VALID_ANSWER_TYPES)}"
            )

        if answer_type == "Number":
            _validate_number_question(q)

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
            for clause in rule.get("any", []):
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
"""Startup validation of the signal being generated against a clinical ruleset.

Every ``answer_key`` used by the generator must exist in the ruleset, and the
project treats configuration drift as a fail-fast error rather than something
to tolerate. A signal that is absent, non-Boolean, or not sent to the encoder
would produce a dataset that no encoder head consumes.

This deliberately reads the ruleset JSON directly rather than importing from
``app/``: the generator is an offline tool and must not couple to runtime
wiring, even though ``app/services/engine/ruleset.py`` also parses these files.
"""

from __future__ import annotations

import json
from pathlib import Path


class RulesetError(ValueError):
    """Raised when the requested signal is missing or unusable in the ruleset."""


def validate_signal(ruleset: dict, signal_key: str, *, source: str) -> dict:
    """Return the ruleset question defining ``signal_key``, or raise.

    ``source`` names the ruleset in error messages -- a path when the ruleset
    came from disk.
    """
    questions = ruleset.get("questions")
    if not isinstance(questions, list):
        raise RulesetError(f"ruleset {source} has no 'questions' list")

    matches = [q for q in questions if isinstance(q, dict) and q.get("answer_key") == signal_key]
    if not matches:
        raise RulesetError(f"signal {signal_key!r} has no question in ruleset {source}")
    if len(matches) > 1:
        raise RulesetError(
            f"signal {signal_key!r} is defined by {len(matches)} questions in ruleset {source}"
        )

    question = matches[0]
    answer_type = question.get("answer_type")
    if answer_type != "Boolean":
        raise RulesetError(
            f"signal {signal_key!r} in ruleset {source} has answer_type {answer_type!r}, "
            "but only Boolean signals can be generated"
        )
    if question.get("send_to_encoder") is not True:
        raise RulesetError(
            f"signal {signal_key!r} in ruleset {source} is not sent to the encoder, "
            "so training data for it would never be consumed"
        )
    return question


def load_and_validate(ruleset_path: Path, signal_key: str) -> dict:
    """Load a ruleset from disk and validate ``signal_key`` within it."""
    ruleset_path = Path(ruleset_path)
    if not ruleset_path.is_file():
        raise RulesetError(f"ruleset not found: {ruleset_path}")
    ruleset = json.loads(ruleset_path.read_text(encoding="utf-8"))
    return validate_signal(ruleset, signal_key, source=str(ruleset_path))


def encoder_signals(ruleset: dict) -> set[str]:
    """Return every Boolean ``answer_key`` the ruleset sends to the encoder.

    The set a ``null_on`` declaration may name. Read from the ruleset rather
    than from the manifest so a declaration for a signal that has no libraries
    yet is still legal -- that is the normal state while a signal is being
    written, and it is how ``recent_uti_present`` was declared ahead of its own
    libraries landing.
    """
    questions = ruleset.get("questions")
    if not isinstance(questions, list):
        raise RulesetError("ruleset has no 'questions' list")
    return {
        question["answer_key"]
        for question in questions
        if isinstance(question, dict)
        and question.get("send_to_encoder") is True
        and question.get("answer_type") == "Boolean"
        and isinstance(question.get("answer_key"), str)
    }

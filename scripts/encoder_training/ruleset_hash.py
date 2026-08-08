"""The ruleset digest recorded in a trained model's metadata sidecar.

This is a deliberate duplicate of ``app/services/engine/ruleset.py``'s
``ruleset_hash``, for the same reason ``scripts/synthetic_data/ruleset.py``
re-parses rulesets rather than importing the engine's loader: offline tooling
must not couple to runtime wiring. Importing the engine's version would pull the
application's ruleset *validation* and its module-level caching into a training
script that has no business depending on either.

Three lines duplicated is a small cost. The guard against the two drifting apart
is ``tests/test_encoder_training_metrics.py``, which asserts both
implementations produce the same digest for the real ``data/uti1.json`` -- a
test that catches divergence is cheaper than a coupling that prevents it.

One thing to know when reading a sidecar: this hashes the **whole** ruleset
dict, so editing any unrelated question changes the recorded hash. That is the
right conservative default -- the hash's job is to say "this model was trained
against exactly this configuration" -- but a changed hash is not evidence that
the signal's own definition moved.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


def ruleset_hash(ruleset: dict[str, Any]) -> str:
    """Return the SHA-256 of the ruleset, key-order independent."""
    payload = json.dumps(ruleset, sort_keys=True).encode()
    return hashlib.sha256(payload).hexdigest()


def hash_ruleset_file(path: Path | str) -> str:
    """Load a ruleset from disk and return its digest.

    No validation: an offline tool recording what it trained against should not
    be the thing that decides whether a ruleset is deployable.
    """
    return ruleset_hash(json.loads(Path(path).read_text(encoding="utf-8")))

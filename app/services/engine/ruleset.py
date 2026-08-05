# ruleset IO and validation

import hashlib
import json
from decimal import Decimal
from functools import cache
from typing import Any

# The complete set of answer types the engine understands. Authored in the
# ruleset's original (capitalised-Boolean) casing; runtime lowercases it.
VALID_ANSWER_TYPES = {"Boolean", "text", "Number"}

# Registry of quantity kinds the engine can fully handle. For each kind:
# canonical_system is the system whose single component is the value stored
# as-is (every other system needs a converter), and systems maps each
# offered system to its ordered component keys (e.g. imperial weight is
# entered as stone + pounds, in that order).
#
# This is the single source of truth for which kinds exist. ruleset.py uses
# it to validate quantity_kind and allowed_systems at startup. form_logic.py
# (conversion) and pdf_formatter.py (formatting) hold their own parallel
# tables keyed by the same kind names -- pdf_formatter.py is presentation
# and must not import the core engine, so it cannot import this registry
# directly. test_wiring.py asserts the three tables agree; a ruleset can
# never declare a quantity_kind the engine cannot fully handle, because
# quantity_kind is validated against VALID_QUANTITY_KINDS below.
QUANTITY_KINDS: dict[str, dict[str, Any]] = {
    "weight": {
        "canonical_system": "metric",
        "systems": {
            "metric": ("kg",),
            "imperial": ("st", "lb"),
        },
    },
}

VALID_QUANTITY_KINDS = frozenset(QUANTITY_KINDS)

# The keys a safety clause may carry. Exactly one of these must be present at
# every depth: is_true/is_false are leaves, any/all are groups holding a list
# of further clauses.
SAFETY_LEAF_KEYS = ("is_true", "is_false")
SAFETY_GROUP_KEYS = ("any", "all")
SAFETY_CLAUSE_KEYS = SAFETY_LEAF_KEYS + SAFETY_GROUP_KEYS

# Maximum number of nested group levels in a safety rule, where the rule's own
# "any" list is level 1. This is not about stack safety -- a ruleset is finite
# authored JSON. The cap exists so a clinician reviewing a rule can hold it in
# their head: three levels expresses anything realistic (an "any" of "all"s of
# "any"s), and needing more is a sign the rule should be split in two.
MAX_SAFETY_CLAUSE_DEPTH = 3


def canonical_system(kind: str) -> str:
    """The system whose single component is the value stored as-is (no conversion)."""
    return QUANTITY_KINDS[kind]["canonical_system"]


def component_keys(kind: str, system: str) -> tuple[str, ...]:
    """The ordered component keys a given quantity_kind/system pair is entered as."""
    return QUANTITY_KINDS[kind]["systems"][system]


@cache
def load_ruleset(path: str) -> dict[str, Any]:
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
    with open(path) as f:
        ruleset = json.load(f)
    validate_ruleset(ruleset)
    return ruleset


def ruleset_hash(ruleset: dict[str, Any]) -> str:
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


def _validate_number_question(q: dict[str, Any]) -> None:
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
            f"Number question '{key}' requires numeric min and max, got min={lo!r}, max={hi!r}"
        )
    if lo >= hi:
        raise ValueError(f"Number question '{key}' requires min < max, got min={lo}, max={hi}")

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
            f"Number question '{key}' range_warning_text must be a string or null, got {rwt!r}"
        )


def _validate_quantity_fields(q: dict[str, Any]) -> None:
    """
    Validate the unit-toggle fields (quantity / quantity_kind / allowed_systems /
    default_system).

    These fields are only meaningful together and only on a Number question, so
    they are enforced fail-fast at startup:

      - quantity, if present, must be a bool.
      - When quantity is True: answer_type must be "Number"; quantity_kind must
        be present and a member of VALID_QUANTITY_KINDS (the closed set of kinds
        the engine has complete wiring for); allowed_systems must be a non-empty
        list drawn from that kind's own systems vocabulary with no duplicates;
        and default_system must be present and one of allowed_systems.
      - When quantity is not True: allowed_systems, default_system, and
        quantity_kind must all be absent, so an author who sets them but forgets
        the quantity flag (which would otherwise be silently ignored) fails
        loudly instead. This mirrors the existing "non-encoder question must not
        have encoder_prompt" rule.

    Note: min/max on a quantity question are expressed in the canonical unit
    for that quantity_kind and are validated by _validate_number_question like
    any other Number bound; nothing unit-specific is checked here.
    """
    key = q["answer_key"]
    quantity = q.get("quantity")

    if quantity is not None and not isinstance(quantity, bool):
        raise ValueError(f"Question '{key}' has a non-boolean quantity: {quantity!r}")

    if quantity is True:
        if q.get("answer_type") != "Number":
            raise ValueError(f"Question '{key}' sets quantity but is not a Number question")

        kind = q.get("quantity_kind")
        if not isinstance(kind, str) or kind not in VALID_QUANTITY_KINDS:
            raise ValueError(
                f"Quantity question '{key}' has invalid or missing quantity_kind: "
                f"{kind!r}. Allowed: {sorted(VALID_QUANTITY_KINDS)}"
            )
        kind_systems = QUANTITY_KINDS[kind]["systems"]

        allowed = q.get("allowed_systems")
        if not isinstance(allowed, list) or not allowed:
            raise ValueError(f"Quantity question '{key}' requires a non-empty allowed_systems list")
        unknown = [s for s in allowed if s not in kind_systems]
        if unknown:
            raise ValueError(
                f"Quantity question '{key}' has unknown allowed_systems {unknown} for "
                f"quantity_kind '{kind}'; allowed: {sorted(kind_systems)}"
            )
        if len(set(allowed)) != len(allowed):
            raise ValueError(f"Quantity question '{key}' has duplicate allowed_systems: {allowed}")

        default_system = q.get("default_system")
        if default_system not in allowed:
            raise ValueError(
                f"Quantity question '{key}' default_system {default_system!r} must "
                f"be one of allowed_systems {allowed}"
            )
    else:
        for unit_field in ("allowed_systems", "default_system", "quantity_kind"):
            if q.get(unit_field) is not None:
                raise ValueError(f"Non-quantity question '{key}' must not set {unit_field}")


def _validate_pdf_label(q: dict[str, Any]) -> None:
    """
    Validate the optional pdf_label field.

    pdf_label is a PDF display concern only: it names a question in the
    CLINICAL SUMMARY block (see arch_submission.md) and has no effect on form
    logic, encoder behaviour, or safety rules. It is optional, so absence is
    always valid, but a label that is present must be usable:

      - a non-empty string, since an empty label renders a bare colon
      - not on a text question, because a free-text answer cannot render
        usefully in the summary's fixed-width value column

    Uniqueness within the ruleset is enforced by the caller, which is the only
    place with a view across questions.
    """
    key = q["answer_key"]
    label = q.get("pdf_label")

    if label is None:
        return

    if not isinstance(label, str) or not label.strip():
        raise ValueError(
            f"Question '{key}' pdf_label must be a non-empty string or null, got {label!r}"
        )

    if q.get("answer_type") == "text":
        raise ValueError(
            f"Text question '{key}' must not set pdf_label: a free-text answer "
            f"cannot render usefully in the CLINICAL SUMMARY block"
        )


def _validate_shared_toggle_consistency(ruleset: dict[str, Any]) -> None:
    """
    All multi-system quantity questions in a ruleset must agree on
    allowed_systems (compared as sets) and on default_system.

    The client renders a single, form-wide unit toggle that drives every
    quantity question at once -- there is no per-question toggle (see
    arch_frontend.md). If two multi-system quantity questions disagreed --
    say weight offered metric and imperial while height offered metric
    only -- the shared toggle would render at least one of them in a
    system it does not accept, giving the patient an unclearable 422.
    That is a broken deployment and must abort at startup, per the
    fail-fast invariant, rather than surface at request time.

    Single-system quantity questions are exempt: they sit outside the
    shared toggle by definition, since there is nothing to toggle.
    """
    multi_system_questions = [
        q
        for q in ruleset["questions"]
        if q.get("quantity") is True and len(q.get("allowed_systems") or []) > 1
    ]

    if len(multi_system_questions) < 2:
        return

    first = multi_system_questions[0]
    first_systems = set(first["allowed_systems"])
    first_default = first["default_system"]

    disagreeing = [
        q["answer_key"]
        for q in multi_system_questions[1:]
        if set(q["allowed_systems"]) != first_systems or q["default_system"] != first_default
    ]

    if disagreeing:
        raise ValueError(
            "Multi-system quantity questions must share the same allowed_systems "
            "and default_system, since the client renders a single form-wide unit "
            f"toggle: '{first['answer_key']}' disagrees with {disagreeing}"
        )


def _validate_safety_clause(
    clause: Any,
    rule_id: str,
    path: str,
    seen_answer_keys: set[str],
    answer_key_types: dict[str, str],
    depth: int,
) -> None:
    """
    Validate one safety clause, recursing into nested any/all groups.

    A clause is either a leaf (is_true / is_false naming a declared Boolean
    answer_key) or a group (any / all holding a non-empty list of further
    clauses). Exactly one of the four keys must be present, and nothing else:
    without that, a clause like {"is_true": "x", "all": [...]} would let the
    engine's key-dispatch order silently decide clinical meaning.

    `depth` is the group level containing this clause -- the rule's own "any"
    list is level 1. `path` names the clause's position (e.g. "any[0].all[2]")
    so an author can find it in a deep rule. `seen_answer_keys` and
    `answer_key_types` are threaded through the recursion so a nested leaf gets
    exactly the same declared-key and Boolean checks as a top-level one.
    """
    if not isinstance(clause, dict):
        raise ValueError(
            f"Safety rule '{rule_id}' has a clause at {path} that is not an object: {clause!r}"
        )

    present = [k for k in SAFETY_CLAUSE_KEYS if k in clause]
    if len(present) != 1:
        raise ValueError(
            f"Safety rule '{rule_id}' has a clause at {path} that must contain exactly "
            f"one of {list(SAFETY_CLAUSE_KEYS)}, got keys {list(clause.keys())}"
        )

    extra_keys = set(clause.keys()) - set(SAFETY_CLAUSE_KEYS)
    if extra_keys:
        raise ValueError(
            f"Safety rule '{rule_id}' has a clause at {path} with unexpected keys: "
            f"{sorted(extra_keys)}"
        )

    clause_kind = present[0]
    value = clause[clause_kind]

    if clause_kind in SAFETY_LEAF_KEYS:
        # A leaf compares one Boolean answer to True/False. A clause pointing at
        # a text or Number answer can never match, so it would validate cleanly
        # and then silently never fire in safety_engine.py.
        if not isinstance(value, str):
            raise ValueError(
                f"Safety rule '{rule_id}' clause at {path} '{clause_kind}' must be a "
                f"string answer_key, got {value!r}"
            )
        if value not in seen_answer_keys:
            raise ValueError(
                f"Safety rule '{rule_id}' clause at {path} references unknown answer_key: {value}"
            )
        if answer_key_types[value] != "Boolean":
            raise ValueError(
                f"Safety rule '{rule_id}' clause at {path} '{clause_kind}' references "
                f"answer_key '{value}' which is answer_type "
                f"'{answer_key_types[value]}', not 'Boolean'; a safety clause can "
                f"only compare Boolean answers to True/False"
            )
        return

    if not isinstance(value, list):
        raise ValueError(
            f"Safety rule '{rule_id}' has a '{clause_kind}' group at {path} that is "
            f"not a list: {value!r}"
        )

    # An empty group is the sharpest trap in the whole feature, because Python
    # evaluates all([]) to True: a clause of {"all": []} is satisfied
    # unconditionally, fires its rule for every patient, and blocks every
    # submission on that condition with a message no answer can clear. The
    # mirror, {"any": []}, is False and so silently never fires. Both are
    # authoring mistakes; neither may reach a running deployment.
    if not value:
        raise ValueError(f"Safety rule '{rule_id}' has an empty '{clause_kind}' group at {path}")

    child_depth = depth + 1
    if child_depth > MAX_SAFETY_CLAUSE_DEPTH:
        raise ValueError(
            f"Safety rule '{rule_id}' nests safety clauses more than "
            f"{MAX_SAFETY_CLAUSE_DEPTH} group levels deep at {path}; split the rule "
            f"instead so it stays reviewable"
        )

    for index, child in enumerate(value):
        _validate_safety_clause(
            child,
            rule_id,
            f"{path}.{clause_kind}[{index}]",
            seen_answer_keys,
            answer_key_types,
            child_depth,
        )


def validate_ruleset(ruleset: dict[str, Any]) -> None:
    if "condition_id" not in ruleset:
        raise ValueError("Ruleset missing required field: condition_id")

    if "questions" not in ruleset or not ruleset["questions"]:
        raise ValueError("Ruleset missing or empty: questions")

    seen_answer_keys = set()
    seen_pdf_labels: set[str] = set()
    answer_key_types: dict[str, str] = {}

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
        answer_key_types[q["answer_key"]] = answer_type

        if answer_type == "Number":
            _validate_number_question(q)

        _validate_quantity_fields(q)

        _validate_pdf_label(q)
        pdf_label = q.get("pdf_label")
        if pdf_label is not None:
            if pdf_label in seen_pdf_labels:
                raise ValueError(
                    f"Duplicate pdf_label {pdf_label!r} on question '{q['answer_key']}': "
                    f"summary rows must be unambiguous"
                )
            seen_pdf_labels.add(pdf_label)

        if q.get("send_to_encoder"):
            if q.get("encoder_prompt") is None:
                raise ValueError(f"Encoder question missing encoder_prompt: {q['answer_key']}")
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

    _validate_shared_toggle_consistency(ruleset)

    if "safety" in ruleset:
        for rule_id, rule in ruleset["safety"]["rules"].items():
            # "any" must be present, a list, and non-empty. Previously a missing
            # key, a typo'd key (e.g. "all"), or an empty list all fell through
            # rule.get("any", []) unnoticed -- the rule validated cleanly and
            # then silently never fired in safety_engine.py.
            if "any" not in rule:
                raise ValueError(f"Safety rule '{rule_id}' missing required 'any' key")
            if not isinstance(rule["any"], list):
                raise ValueError(f"Safety rule '{rule_id}' has 'any' that is not a list")
            if not rule["any"]:
                raise ValueError(f"Safety rule '{rule_id}' has an empty 'any' list")

            # "message" is read with a direct dict access (rule["message"]) in
            # safety_engine.py once a rule fires -- without this check, a rule
            # authored without it validates fine at startup and then raises
            # KeyError mid-request the first time a patient actually triggers it.
            if "message" not in rule:
                raise ValueError(f"Safety rule '{rule_id}' missing required 'message' key")
            if not isinstance(rule["message"], str) or not rule["message"].strip():
                raise ValueError(f"Safety rule '{rule_id}' has an empty or non-string 'message'")

            # Every clause, at every depth, must be a dict containing exactly
            # one of is_true / is_false / any / all and nothing else, with a
            # leaf naming a declared Boolean answer_key and a group holding a
            # non-empty list of further clauses. See _validate_safety_clause
            # for why each of those checks exists; the short version is that a
            # malformed clause validates cleanly and then silently never fires
            # (or, for {"all": []}, always fires) in safety_engine.py.
            # The rule's own "any" list is group level 1.
            for index, clause in enumerate(rule["any"]):
                _validate_safety_clause(
                    clause,
                    rule_id,
                    f"any[{index}]",
                    seen_answer_keys,
                    answer_key_types,
                    depth=1,
                )


def extract_encoder_definitions(ruleset: dict[str, Any]) -> list[dict[str, str]]:
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

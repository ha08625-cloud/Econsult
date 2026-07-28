from collections.abc import Callable
from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from app.models.runtime_state import AnswerState, RuntimeState, SafetyEvaluation
from app.services.engine.ruleset import canonical_system, component_keys, ruleset_hash
from app.services.engine.unit_conversion import imperial_weight_to_kg


class AnswerValidationError(ValueError):
    """
    A submitted answer failed validation (missing, wrong type, or precision).

    Subclasses ValueError so existing `pytest.raises(ValueError)` tests stay
    green. The HTTP boundary (form_router) catches this specific subclass and
    translates it to a 422, while a plain ValueError raised elsewhere in the
    pipeline (e.g. a ruleset load failure) still surfaces as a logged 500.
    """


# Conversion functions for every non-canonical (quantity_kind, system) pair.
# The canonical system for a kind never appears here -- its value is stored
# as-is (see convert_unit_answers). A new kind registers its conversion
# function here and its arithmetic in unit_conversion.py; test_wiring.py
# asserts every non-canonical pair the ruleset registry declares has an entry.
_NON_CANONICAL_CONVERTERS: dict[tuple[str, str], Callable[[dict], Decimal]] = {
    ("weight", "imperial"): lambda c: imperial_weight_to_kg(c["st"], c["lb"]),
}


def _validate_number_value(value: Any, decimal_places: int, answer_key: str) -> None:
    """
    Validate that `value` is a finite number (int or Decimal) carrying no more
    than `decimal_places` decimal places. Raises AnswerValidationError on any
    violation, with answer_key in the message.

    This is the number-acceptance ladder shared by every place that accepts a
    numeric quantity from the wire. It deliberately does NOT handle None: a
    missing value means different things to different callers (an unanswered
    question vs a malformed component of a compound answer), so each caller
    checks for None first and raises its own context-specific message.

    The checks run most-specific-true first:
      - bool is excluded before the int/Decimal check because isinstance(True,
        int) is True, so True/False would otherwise be read as 1/0.
      - Decimal NaN/Infinity never arise from the wire (json parses those
        constants as float, which fails the int/Decimal check), but the finite
        guard ensures a non-finite value can never reach the exponent check.
      - An int has no fractional part and is always acceptable. A Decimal's
        negative exponent is its number of decimal places.
    """
    if isinstance(value, bool):
        raise AnswerValidationError(f"Answer must be a number, not a boolean: {answer_key}")

    if not isinstance(value, (int, Decimal)):
        raise AnswerValidationError(f"Answer must be a number: {answer_key}")

    if isinstance(value, Decimal) and not value.is_finite():
        raise AnswerValidationError(f"Answer must be a finite number: {answer_key}")

    if isinstance(value, Decimal) and value.as_tuple().exponent < -decimal_places:
        raise AnswerValidationError(
            f"Answer for {answer_key} has more than {decimal_places} decimal place(s)"
        )


def initialise_runtime_state(
    ruleset: dict,
    free_text: str,
    engine_version: str = "0.1",
) -> RuntimeState:
    """Creates the initial RuntimeState for a new clinical session."""
    answers = {
        q["answer_key"]: AnswerState(
            value=None,
            source="unanswered",
            encoder_value=None,
            answer_type=q["answer_type"].lower(),
        )
        for q in ruleset["questions"]
    }

    return RuntimeState(
        condition_id=ruleset["condition_id"],
        ruleset_version=ruleset_hash(ruleset),
        free_text=free_text,
        additional_text=None,
        answers=answers,
        safety_evaluation=SafetyEvaluation(),
        metadata={
            "engine_version": engine_version,
            "timestamp": datetime.now(UTC).isoformat(),
        },
    )


def apply_additional_text(runtime: RuntimeState, additional_text: str | None) -> None:
    """Updates the optional patient narrative, normalizing empty strings to None."""
    runtime.additional_text = (
        additional_text.strip() if additional_text and additional_text.strip() else None
    )


def apply_patient_answers(runtime: RuntimeState, answers: dict[str, Any]) -> None:
    """
    Applies patient-provided answers, recomputes provenance, and records churn.

    `source` is a pure function of the current value relative to the encoder's
    suggestion (`encoder_value`), so it is idempotent: re-applying the same value
    yields the same source. This is what lets the client round-trip the whole
    answers map on every update without provenance drifting.

    - encoder_value is None (encoder never suggested this answer, e.g. number/text
      questions or an encoder that returned null): the answer is patient-owned.
    - value matches encoder_value: the encoder's suggestion currently stands
      ("encoder_correct").
    - value differs from encoder_value: the current answer departs from the
      encoder's suggestion ("encoder_incorrect").

    encoder_value is never written here; it is set once in encoder_mapping and is
    the reason a patient-owned answer can never become encoder-derived.

    Change auditing (change_count):
        Before the value is overwritten, an encoder-suggested answer
        (encoder_value is not None) whose submitted value differs from the
        currently committed value has its change_count incremented by one. The
        read-before-write happens in this same loop iteration, immediately ahead
        of the assignment below, so the "read the old value first" requirement is
        structural and cannot be broken by reordering elsewhere. Text and number
        answers (encoder_value None) and encoder-null booleans are out of audit
        scope and never increment. Re-applying the same value does not increment,
        so the idempotency property above extends to change_count: a no-op submit
        leaves it untouched.
    """
    for answer_key, value in answers.items():
        if answer_key not in runtime.answers:
            raise KeyError(f"Unknown answer_key: {answer_key}")

        a = runtime.answers[answer_key]

        # Record churn BEFORE overwriting a.value. Encoder-suggested answers
        # only; a.value here is still the previously committed value.
        if a.encoder_value is not None and value != a.value:
            a.change_count += 1

        a.value = value
        if a.encoder_value is None:
            a.source = "patient"
        elif value == a.encoder_value:
            a.source = "encoder_correct"
        else:
            a.source = "encoder_incorrect"


def convert_unit_answers(runtime: RuntimeState, ruleset: dict) -> None:
    """
    Resolve quantity-bearing Number answers (those with a unit toggle) from the
    transient client dict {"system", "components"} into a canonical Decimal in
    the question's quantity_kind's canonical unit, recording the patient's raw
    input in raw_components and the chosen system in the answer's own
    unit_system.

    Ordering (enforced by pipeline.apply_update_and_evaluate): runs after
    apply_patient_answers, which placed the dict in a.value, and before
    validate_required_answers and normalise_number_answers. It MUST precede
    validate_required_answers, which would otherwise see a dict and reject it as
    "not a number"; it leaves a.value as a Decimal that normalise_number_answers
    then stringifies like any other Number. normalise_encoder_provenance is
    unaffected: a quantity question is a Number, so it is never send_to_encoder
    (ruleset validation enforces encoder questions are Boolean) and its source is
    always "patient".

    Per-question behaviour:
      - Unanswered (a.value is None): skipped, left to validate_required_answers'
        missing-answer check.
      - Canonical system (e.g. metric for weight): the patient typed the
        canonical unit directly, so over-precision is a real input error -- the
        value goes through the shared number-acceptance ladder and is rejected
        if it exceeds decimal_places. The canonical value is the typed amount.
      - Non-canonical system (e.g. imperial for weight): components are
        converted to an exact canonical Decimal via the kind's registered
        converter, then ROUND_HALF_UP to decimal_places. The exact-but-long
        conversion artifact never persists; raw_components keeps the patient's
        input (e.g. "11 st 11 lb") as the lossless record.

    A malformed payload (wrong dict shape, unknown system, bad component) raises
    AnswerValidationError so the HTTP boundary returns 422.

    The chosen system is recorded on the answer itself (a.unit_system), not on
    the form. Cross-question agreement that every multi-system quantity
    question offers the same systems is a client convention, enforced once at
    startup in ruleset.py -- not a runtime check here.
    """
    questions_by_key = {q["answer_key"]: q for q in ruleset["questions"]}

    for q in ruleset["questions"]:
        if not q.get("quantity"):
            continue

        answer_key = q["answer_key"]
        a = runtime.answers[answer_key]

        if a.value is None:
            continue  # unanswered; validate_required_answers handles it

        if not isinstance(a.value, dict):
            raise AnswerValidationError(
                f"Quantity answer {answer_key} must be a {{system, components}} object"
            )

        kind = q["quantity_kind"]
        allowed_systems = q.get("allowed_systems", [])
        system = a.value.get("system")
        if system not in allowed_systems:
            raise AnswerValidationError(
                f"Quantity answer {answer_key} has an unsupported unit system: {system!r}"
            )

        components = a.value.get("components")
        if not isinstance(components, dict):
            raise AnswerValidationError(f"Quantity answer {answer_key} is missing its components")

        # system is guaranteed to have known component keys: ruleset validation
        # restricts allowed_systems to the kind's own systems vocabulary, and
        # system is in allowed_systems by the check above.
        expected_keys = set(component_keys(kind, system))
        if set(components.keys()) != expected_keys:
            raise AnswerValidationError(
                f"Quantity answer {answer_key} for system {system!r} requires "
                f"exactly the components {sorted(expected_keys)}"
            )

        decimal_places = questions_by_key[answer_key]["decimal_places"]

        if system == canonical_system(kind):
            (canonical_key,) = component_keys(kind, system)
            raw_value = components[canonical_key]
            _validate_number_value(raw_value, decimal_places, answer_key)
            canonical = Decimal(raw_value)
            # Persisted as a string for the same exactness reason as value.
            a.raw_components = {canonical_key: format(canonical, "f")}
        else:
            try:
                exact = _NON_CANONICAL_CONVERTERS[(kind, system)](components)
            except ValueError as exc:
                raise AnswerValidationError(f"Quantity answer {answer_key}: {exc}") from exc
            quantum = Decimal(1).scaleb(-decimal_places)
            canonical = exact.quantize(quantum, rounding=ROUND_HALF_UP)
            # Non-canonical components are whole numbers; persist as ints.
            a.raw_components = {key: int(components[key]) for key in expected_keys}

        a.value = canonical
        a.unit_system = system


def normalise_encoder_provenance(runtime: RuntimeState) -> None:
    """
    Promotes any still-raw encoder answer to 'encoder_correct' on submission.

    A raw "encoder" answer is one the patient never touched, so its value still
    equals encoder_value by construction; recording it as encoder_correct keeps
    source consistent with the value-vs-encoder_value rule used everywhere else.
    Acts only on raw "encoder"; all other sources are left unchanged.
    """
    for a in runtime.answers.values():
        if a.source == "encoder":
            a.source = "encoder_correct"


def validate_required_answers(runtime: RuntimeState, ruleset: dict) -> None:
    """
    Ensures every question has been answered acceptably for its type.

    Raises AnswerValidationError on the first failure. For Number answers the
    tiers are checked most-specific-true first: missing, then the shared
    number-acceptance ladder (wrong type, non-finite, precision) in
    _validate_number_value. Range (min/max) is deliberately NOT enforced here --
    it is a non-blocking warning surfaced in the client, never a submission
    blocker.

    Quantity-bearing Number answers have already been resolved to a canonical kg
    Decimal by convert_unit_answers (metric values are <= decimal_places by the
    same ladder; imperial values were rounded to decimal_places), so they pass
    this check with no special-casing.

    `ruleset` is required because Number precision validation needs each
    question's decimal_places.
    """
    questions_by_key = {q["answer_key"]: q for q in ruleset["questions"]}

    for answer_key, a in runtime.answers.items():
        if a.answer_type == "boolean":
            if a.value is None:
                raise AnswerValidationError(f"Missing boolean answer: {answer_key}")

        elif a.answer_type == "text":
            if not isinstance(a.value, str) or not a.value.strip():
                raise AnswerValidationError(f"Missing text answer: {answer_key}")

        elif a.answer_type == "number":
            decimal_places = questions_by_key[answer_key]["decimal_places"]
            value = a.value

            if value is None:
                raise AnswerValidationError(f"Missing number answer: {answer_key}")

            _validate_number_value(value, decimal_places, answer_key)


def normalise_number_answers(runtime: RuntimeState) -> None:
    """
    Convert validated Number answers to their canonical string form for
    persistence. Runs AFTER validate_required_answers so the exact int/Decimal
    type is still available to that check, and BEFORE the state is serialised
    or persisted (Decimal is not JSON-serialisable, and storing a string keeps
    the value exact across JSONB round-trips).

    format(value, "f") renders a Decimal in plain (non-exponential) notation,
    so a value entered as "7e1" by a direct API client is stored as "70" rather
    than "7E+1". Whole numbers arrive as int and stringify directly.
    """
    for answer_key, a in runtime.answers.items():
        if a.answer_type != "number" or a.value is None:
            continue
        if isinstance(a.value, dict):
            # A quantity dict must have been resolved by convert_unit_answers
            # before this point. A dict here means the pipeline ran out of order
            # or convert skipped a question it should have handled; fail loud as
            # an internal error (500) rather than persist "{'kg': ...}" into a
            # clinical record. This is not an AnswerValidationError (not a 422):
            # it is a programming/ordering bug, not bad client input.
            raise RuntimeError(
                f"Unresolved quantity components for answer {answer_key}: "
                f"convert_unit_answers must run before normalise_number_answers"
            )
        if isinstance(a.value, Decimal):
            a.value = format(a.value, "f")
        else:
            a.value = str(a.value)

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, Optional
from app.models.runtime_state import RuntimeState, AnswerState, SafetyEvaluation
from app.services.engine.ruleset import ruleset_hash


class AnswerValidationError(ValueError):
    """
    A submitted answer failed validation (missing, wrong type, or precision).

    Subclasses ValueError so existing `pytest.raises(ValueError)` tests stay
    green. The HTTP boundary (form_router) catches this specific subclass and
    translates it to a 422, while a plain ValueError raised elsewhere in the
    pipeline (e.g. a ruleset load failure) still surfaces as a logged 500.
    """


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
            "timestamp": datetime.now(timezone.utc).isoformat(),
        },
    )

def apply_additional_text(runtime: RuntimeState, additional_text: Optional[str]) -> None:
    """Updates the optional patient narrative, normalizing empty strings to None."""
    runtime.additional_text = additional_text.strip() if additional_text and additional_text.strip() else None

def apply_patient_answers(runtime: RuntimeState, answers: Dict[str, Any]) -> None:
    """
    Applies patient-provided answers and recomputes provenance.

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
    """
    for answer_key, value in answers.items():
        if answer_key not in runtime.answers:
            raise KeyError(f"Unknown answer_key: {answer_key}")

        a = runtime.answers[answer_key]
        a.value = value
        if a.encoder_value is None:
            a.source = "patient"
        elif value == a.encoder_value:
            a.source = "encoder_correct"
        else:
            a.source = "encoder_incorrect"

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
    tiers are checked most-specific-true first: missing, then wrong type
    (the bool exclusion is explicit because isinstance(True, int) is True),
    then precision. Range (min/max) is deliberately NOT enforced here — it is
    a non-blocking warning surfaced in the client, never a submission blocker.

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

            # bool is a subclass of int, so exclude it before the int/Decimal
            # acceptance check, or True/False would be read as 1/0.
            if isinstance(value, bool):
                raise AnswerValidationError(
                    f"Answer must be a number, not a boolean: {answer_key}"
                )

            if not isinstance(value, (int, Decimal)):
                raise AnswerValidationError(
                    f"Answer must be a number: {answer_key}"
                )

            # Decimal NaN/Infinity never arise from the wire (json parses those
            # constants as float, which fails the int/Decimal check above), but
            # guard anyway so a non-finite value can never reach the exponent check.
            if isinstance(value, Decimal) and not value.is_finite():
                raise AnswerValidationError(
                    f"Answer must be a finite number: {answer_key}"
                )

            # Precision: an int has no fractional part and is always acceptable.
            # A Decimal's negative exponent is its number of decimal places.
            if isinstance(value, Decimal) and value.as_tuple().exponent < -decimal_places:
                raise AnswerValidationError(
                    f"Answer for {answer_key} has more than {decimal_places} "
                    f"decimal place(s)"
                )

        else:
            # Not unreachable: validate_ruleset only constrains answer_type at
            # startup. AnswerState is a plain dataclass, so its Literal type
            # hint is not enforced at runtime, and RuntimeState.from_dict will
            # accept any string straight out of persisted JSONB. Without this
            # branch, a corrupted or legacy answer_type would silently skip
            # required-answer checking instead of failing loudly.
            raise AnswerValidationError(
                f"Unknown answer_type '{a.answer_type}' for {answer_key}"
            )

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
    for a in runtime.answers.values():
        if a.answer_type != "number" or a.value is None:
            continue
        if isinstance(a.value, Decimal):
            a.value = format(a.value, "f")
        else:
            a.value = str(a.value)
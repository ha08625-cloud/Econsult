from dataclasses import dataclass


@dataclass(frozen=True)
class ExplicitAnswers:
    """
    Immutable projection of answers that are allowed to influence
    safety or other post-submit rule engines.

    Semantics:
    - True / False: explicitly answered
    - None: unknown / unanswered (never treated as False)
    """

    values: dict[str, bool | None]

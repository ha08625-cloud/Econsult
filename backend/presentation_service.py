"""
Presentation service.

Composes patient-facing presentation from multiple sources:
- Universal safety warning (constant)
- Practice-specific signposting (database)
- Condition-specific presentation (condition_registry)

This module is responsible for:
- Defining the universal safety warning
- Composing the complete patient-facing presentation
- Providing a single access point for all presentation data

This module must never:
- Access clinical data (rulesets, RuntimeState, answers, safety rules)
- Modify any data (read-only composition)
- Handle authentication (that belongs in practice_context, Phase 1B)

Architectural note:
This module performs COMPOSITION, not MERGING. Each data source
populates a distinct field in the output. There is no field-level
override logic - practice data and condition data occupy separate slots.

Single-tenant contract:
practice_id is always required. This service is deployed once per
practice. The practice_id is resolved from app.state at the HTTP layer
and passed in explicitly. There is no concept of a missing or optional
practice in this deployment model.
"""

from condition_registry import ConditionRegistry, ConditionNotFound
from practice_repository import PracticeRepository


# Universal safety warning shown to all patients before all conditions.
# This is intentionally hardcoded - it should not be editable by practices.
UNIVERSAL_SAFETY_WARNING = (
    "If you are experiencing any of the following, do not use this service. "
    "Call 999 or go to A&E immediately: chest pain, difficulty breathing, "
    "signs of a stroke (face drooping, arm weakness, speech difficulty), "
    "severe bleeding, or loss of consciousness."
)


class PresentationService:
    """
    Composes patient-facing presentation from multiple sources.

    Thread-safe for read operations (all writes go through PracticeRepository).
    """

    def __init__(
        self,
        condition_registry: ConditionRegistry,
        practice_repository: PracticeRepository,
    ):
        self._condition_registry = condition_registry
        self._practice_repository = practice_repository

    def get_patient_presentation(
        self,
        condition_id: str,
        practice_id: str,
    ) -> dict:
        """
        Get the complete patient-facing presentation for a condition.

        Args:
            condition_id: The condition to get presentation for
            practice_id: The practice ID for practice-specific signposting.
                         Always required in single-tenant deployments.

        Returns:
            dict with keys:
                - label: str (condition label)
                - free_text_prompt: str | None
                - universal_safety_warning: str
                - practice_signposting: list[str] | None

        Raises:
            ConditionNotFound: If condition_id does not exist

        Behaviour:
            - If no signposting is configured for this practice and condition,
              practice_signposting is None
            - If signposting is configured, practice_signposting is the list of strings
            - Empty list from database is returned as None (nothing to display)
        """
        # Get condition presentation (raises ConditionNotFound if invalid)
        condition_presentation = self._condition_registry.get_presentation(condition_id)

        # Get practice-specific signposting
        signposting = self._practice_repository.get_signposting(practice_id, condition_id)
        # Convert empty list to None (nothing to display)
        practice_signposting = signposting if signposting else None

        return {
            "label": condition_presentation["label"],
            "free_text_prompt": condition_presentation.get("free_text_prompt"),
            "universal_safety_warning": UNIVERSAL_SAFETY_WARNING,
            "practice_signposting": practice_signposting,
        }
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

from app.core.condition_registry import ConditionRegistry, ConditionNotFound
from app.repositories.practice_repository import PracticeRepository


# Universal safety warning shown to all patients before all conditions.
# This is intentionally hardcoded - it should not be editable by practices.
# Displayed on the first screen the patient sees, before condition selection.
# Also included in get_patient_presentation() for backwards compatibility.
UNIVERSAL_SAFETY_WARNING = (
    "If you or someone else is experiencing any of the following, do not use this service. "
    "Call 999 or go to A&E immediately. "
    "Chest pain or heart attack signs: central chest pain, often heavy, tight, or crushing. "
    "Breathing difficulties: struggling to breathe, gasping, or unable to speak in full sentences. "
    "Stroke signs (FAST): face drooping, arm weakness, or slurred speech. "
    "Severe bleeding: bleeding that is spraying, pouring, or will not stop with pressure. "
    "Loss of consciousness: the person is unconscious or has collapsed. "
    "Fits or seizures: especially a first-time fit, or if the person is not waking up. "
    "Severe allergic reaction (anaphylaxis): sudden swelling of the lips, mouth, throat, or tongue. "
    "Acute confusion: sudden onset of confusion, agitation, or odd behaviour. "
    "Major trauma: serious injuries from a high-speed accident or fall from height. "
    "Suicide attempt or self-harm: immediate risk of harm to self."
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

    def get_universal_safety_warning(self) -> str:
        """
        Return the universal safety warning text.

        This is a module-level constant, not practice- or condition-specific.
        Called by the GET /safety-warning endpoint to serve the pre-condition
        safety gate screen. No condition ID or practice ID required.
        """
        return UNIVERSAL_SAFETY_WARNING

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
                - practice_signposting: str | None

        Raises:
            ConditionNotFound: If condition_id does not exist

        Behaviour:
            - If no signposting is configured for this practice and condition,
              practice_signposting is None
            - If signposting is configured, practice_signposting is a sanitised
              HTML string. The repository guarantees it is never an empty string —
              empty content is stored as a deleted row, not as an empty value.
        """
        # Get condition presentation (raises ConditionNotFound if invalid)
        condition_presentation = self._condition_registry.get_presentation(condition_id)

        # Get practice-specific signposting.
        # get_signposting returns either a non-empty HTML string or None —
        # the repository never stores an empty string, so no further
        # normalisation is needed here.
        practice_signposting = self._practice_repository.get_signposting(
            practice_id, condition_id
        )

        return {
            "label": condition_presentation["label"],
            "free_text_prompt": condition_presentation.get("free_text_prompt"),
            "universal_safety_warning": UNIVERSAL_SAFETY_WARNING,
            "practice_signposting": practice_signposting,
        }

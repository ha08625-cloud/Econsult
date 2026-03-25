"""
Shared FastAPI dependency providers.

All routers import from here rather than reading request.app.state directly.
This makes dependencies visible at the function signature, keeps handler
bodies free of infrastructure lookups, and makes handlers independently
testable by injecting fakes via Depends overrides.

Rules:
- These are thin wrappers only. No logic, no error handling.
- app.state is populated by main.py at startup before any request is served.
- All values stored in app.state are immutable after startup.
"""

from fastapi import Request

from app.core.condition_registry import ConditionRegistry
from app.repositories.practice_repository import PracticeRepository
from app.repositories.availability_repository import AvailabilityRepository
from app.repositories.runtime_state_repository import RuntimeStateRepository
from app.repositories.submission_repository import SubmissionRepository
from app.repositories.attachment_repository import AttachmentRepository
from app.services.delivery_service import DeliveryService
from app.services.presentation_service import PresentationService


def get_registry(request: Request) -> ConditionRegistry:
    return request.app.state.registry


def get_practice_repo(request: Request) -> PracticeRepository:
    return request.app.state.practice_repo


def get_availability_repo(request: Request) -> AvailabilityRepository:
    return request.app.state.availability_repo


def get_practice_id(request: Request) -> str:
    return request.app.state.practice_id


def get_presentation_service(request: Request) -> PresentationService:
    return request.app.state.presentation_service


def get_runtime_repo(request: Request) -> RuntimeStateRepository:
    return request.app.state.runtime_repo


def get_submission_repo(request: Request) -> SubmissionRepository:
    return request.app.state.submission_repo


def get_delivery_service(request: Request) -> DeliveryService:
    return request.app.state.delivery_service


def get_attachment_repo(request: Request) -> AttachmentRepository:
    return request.app.state.attachment_repo


def get_practice_name(request: Request) -> str:
    return request.app.state.practice_name
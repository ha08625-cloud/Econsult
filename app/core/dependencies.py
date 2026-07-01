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
from app.core.state_keys import AUTH_REPO
from app.repositories.attachment_repository import AttachmentRepository
from app.repositories.audit_repository import AuditRepository
from app.repositories.auth_repository import AuthRepository
from app.repositories.availability_repository import AvailabilityRepository
from app.repositories.delivery_repository import DeliveryRepository
from app.repositories.pdf_repository import PDFRepository
from app.repositories.photo_repository import PhotoRepository
from app.repositories.practice_repository import PracticeRepository
from app.repositories.runtime_state_repository import RuntimeStateRepository
from app.repositories.submission_repository import SubmissionRepository
from app.services.delivery.admin_delivery_service import AdminDeliveryService
from app.services.delivery.delivery_service import DeliveryService
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


def get_attachment_repo(request: Request) -> AttachmentRepository:
    return request.app.state.attachment_repo


def get_pdf_repo(request: Request) -> PDFRepository:
    return request.app.state.pdf_repo


def get_photo_repo(request: Request) -> PhotoRepository:
    return request.app.state.photo_repo


def get_delivery_repo(request: Request) -> DeliveryRepository:
    return request.app.state.delivery_repo


def get_delivery_service(request: Request) -> DeliveryService:
    return request.app.state.delivery_service


def get_practice_name(request: Request) -> str:
    return request.app.state.practice_name


def get_auth_repo(request: Request) -> AuthRepository:
    # Reads via the shared AUTH_REPO constant rather than a literal because
    # this attribute name is also referenced by app/core/admin_context.py,
    # which cannot import this module. See app/core/state_keys.py.
    return getattr(request.app.state, AUTH_REPO)


def get_audit_repo(request: Request) -> AuditRepository:
    return request.app.state.audit_repo


def get_admin_delivery_service(request: Request) -> AdminDeliveryService:
    return request.app.state.admin_delivery_service


def get_allowed_admin_domains(request: Request) -> str:
    return request.app.state.allowed_admin_domains


def get_database_url(request: Request) -> str:
    return request.app.state.database_url


def get_mailgun_signing_key(request: Request) -> str | None:
    # Optional by design: None on the SMTP delivery path. Uses getattr with a
    # None default so a deployment that never set the attribute resolves to
    # None (and the webhook returns 403) rather than raising AttributeError,
    # preserving the webhook's misconfiguration-is-403 behaviour.
    return getattr(request.app.state, "mailgun_signing_key", None)

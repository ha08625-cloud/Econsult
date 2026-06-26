"""
Application wiring: container construction and startup deployment checks.

Constructs every long-lived object the web service needs (repositories,
services, registry) plus the startup-derived scalars, and runs the
DB-backed deployment checks. For the full startup sequence, the
app.state field table, and the delivery service selection rules, see
docs/arch_http_boundary.md -- this docstring covers only what isn't
already there.

Design:

- AppContainer is a frozen dataclass: constructing it IS the startup-time
  completeness check, so a wiring bug that forgets a repository fails at
  startup, not at first request. See the AppContainer docstring below for
  the field-name contract with app/core/dependencies.py.

- build_container's construction order is load-bearing for error
  precedence: repositories, then the DB-backed deployment checks, then
  the practice name lookup, then the delivery services (whose
  constructors validate their own environment variables, e.g. ADMIN_URL).
  This keeps "practice not found" surfacing before "ADMIN_URL missing".
"""

import logging
from dataclasses import dataclass, fields
from typing import Optional

from fastapi import FastAPI

from app.core.condition_registry import ConditionRegistry
from app.core.settings import WebSettings
from app.repositories.practice_repository import PracticeRepository
from app.repositories.availability_repository import AvailabilityRepository
from app.repositories.runtime_state_repository import RuntimeStateRepository
from app.repositories.submission_repository import SubmissionRepository
from app.repositories.attachment_repository import AttachmentRepository
from app.repositories.pdf_repository import PDFRepository
from app.repositories.photo_repository import PhotoRepository
from app.repositories.delivery_repository import DeliveryRepository
from app.repositories.auth_repository import AuthRepository
from app.repositories.audit_repository import AuditRepository
from app.services.presentation_service import PresentationService
from app.services.delivery.delivery_service import (
    DeliveryService,
    EmailDeliveryService,
    MailgunHttpDeliveryService,
)
from app.services.delivery.admin_delivery_service import (
    AdminDeliveryService,
    MailgunHttpAdminDeliveryService,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Container
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class AppContainer:
    """
    Everything the web service holds for its lifetime.

    Field names must match the app.state attribute names read by the
    getters in app/core/dependencies.py. Do not rename a field without
    renaming the corresponding getter target -- tests/test_wiring.py
    enforces this.
    """

    registry: ConditionRegistry
    practice_repo: PracticeRepository
    availability_repo: AvailabilityRepository
    runtime_repo: RuntimeStateRepository
    submission_repo: SubmissionRepository
    attachment_repo: AttachmentRepository
    pdf_repo: PDFRepository
    photo_repo: PhotoRepository
    delivery_repo: DeliveryRepository
    auth_repo: AuthRepository
    audit_repo: AuditRepository

    presentation_service: PresentationService
    delivery_service: DeliveryService
    admin_delivery_service: AdminDeliveryService

    practice_id: str
    practice_name: Optional[str]
    allowed_admin_domains: str
    mailgun_signing_key: Optional[str]
    database_url: str


# ---------------------------------------------------------------------------
# DB-backed deployment checks (logic unchanged from the legacy
# _validate_startup; the environment-variable checks it used to perform
# now live in app/core/settings.py)
# ---------------------------------------------------------------------------

def run_deployment_checks(
    practice_repo: PracticeRepository,
    auth_repo: AuthRepository,
    practice_id: str,
) -> None:
    """
    Validate the deployed database state. Raises RuntimeError on failure.

    Checks (unchanged messages):
    - the practice record exists (no automatic seeding)
    - the practice record has an email configured
    - the database contains exactly one practice (single-tenant invariant)
    - at least one admin user exists for the practice
    """
    practice = practice_repo.get_practice(practice_id)
    if practice is None:
        raise RuntimeError(
            f"Practice '{practice_id}' not found in database. "
            "Insert the practice record before starting the application. "
            "See docs/deployment_checklist.md."
        )

    if not practice.get("email", "").strip():
        raise RuntimeError(
            f"Practice '{practice_id}' has no email address configured. "
            "Update the practice record with a valid email before starting."
        )

    count = practice_repo.count_practices()
    if count > 1:
        raise RuntimeError(
            f"Database contains {count} practices. "
            "This is a single-tenant deployment. "
            "Multiple practices is a clinically unsafe configuration. "
            "Aborting startup."
        )

    user_count = auth_repo.count_users_for_practice(practice_id)
    if user_count == 0:
        raise RuntimeError(
            f"No admin users found for practice '{practice_id}'. "
            "Use scripts/create_admin_user.py to add an admin user before starting. "
            "See docs/deployment_checklist.md."
        )


# ---------------------------------------------------------------------------
# Construction
# ---------------------------------------------------------------------------

def build_container(settings: WebSettings) -> AppContainer:
    """
    Instantiate every long-lived object and return the completed container.

    Runs the DB-backed deployment checks after repository construction and
    before delivery service construction, preserving the legacy startup
    error precedence. Raises RuntimeError on any deployment check failure;
    delivery service constructors raise RuntimeError on their own missing
    environment variables (e.g. ADMIN_URL).
    """
    database_url = settings.DATABASE_URL
    practice_id = settings.PRACTICE_ID

    registry = ConditionRegistry(settings.data_dir)

    practice_repo = PracticeRepository(database_url)
    availability_repo = AvailabilityRepository(database_url)
    runtime_repo = RuntimeStateRepository(database_url)
    submission_repo = SubmissionRepository(database_url)
    attachment_repo = AttachmentRepository(database_url)
    pdf_repo = PDFRepository(database_url)
    photo_repo = PhotoRepository(database_url)
    delivery_repo = DeliveryRepository(database_url)
    auth_repo = AuthRepository(database_url)
    audit_repo = AuditRepository(database_url)

    presentation_service = PresentationService(registry, practice_repo)

    run_deployment_checks(practice_repo, auth_repo, practice_id)

    # Practice name for generated PDFs. Captured once at startup; a name
    # change via the admin interface takes effect at the next restart.
    # run_deployment_checks has just confirmed the record exists; the
    # defensive None handling is kept for parity with the legacy code.
    practice_record = practice_repo.get_practice(practice_id)
    practice_name = practice_record.get("name") if practice_record else None

    if settings.email.delivery_mode == "mailgun":
        delivery_service: DeliveryService = MailgunHttpDeliveryService()
        admin_delivery_service: AdminDeliveryService = MailgunHttpAdminDeliveryService()
    else:
        delivery_service = EmailDeliveryService()
        admin_delivery_service = AdminDeliveryService()

    return AppContainer(
        registry=registry,
        practice_repo=practice_repo,
        availability_repo=availability_repo,
        runtime_repo=runtime_repo,
        submission_repo=submission_repo,
        attachment_repo=attachment_repo,
        pdf_repo=pdf_repo,
        photo_repo=photo_repo,
        delivery_repo=delivery_repo,
        auth_repo=auth_repo,
        audit_repo=audit_repo,
        presentation_service=presentation_service,
        delivery_service=delivery_service,
        admin_delivery_service=admin_delivery_service,
        practice_id=practice_id,
        practice_name=practice_name,
        allowed_admin_domains=settings.ALLOWED_ADMIN_DOMAINS,
        mailgun_signing_key=settings.email.MAILGUN_SIGNING_KEY,
        database_url=database_url,
    )


# ---------------------------------------------------------------------------
# Unpacking onto app.state
# ---------------------------------------------------------------------------

def unpack_container(app: FastAPI, container: AppContainer) -> None:
    """
    Copy every container field onto app.state under the same name.

    Iterating dataclasses.fields() rather than hand-writing assignments
    means a field added to AppContainer is automatically exposed on
    app.state, and names cannot drift between this module and the
    dependencies.py getters.
    """
    for field in fields(container):
        setattr(app.state, field.name, getattr(container, field.name))

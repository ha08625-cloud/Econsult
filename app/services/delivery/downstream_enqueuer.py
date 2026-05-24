"""
Downstream enqueuer.

Defines the polymorphic seam between the PDF worker and whatever queue
consumes its output. In the email-only configuration (MESH_DELIVERY=0),
the seam dispatches to delivery_jobs via DeliveryEnqueuer. Future phases
will add a second implementation (PdsEnqueuer) for the MESH delivery path.

Architecture rules:
- The Protocol owns the contract: enqueue(submission_id).
- Implementations are responsible for reading any further data they need
  from repositories. The PDF worker never threads enqueuer-specific
  values through its own call signature.
- This module must never:
    - Generate PDFs.
    - Send emails.
    - Touch the database directly (uses repositories).
    - Import clinical engine modules.

Why the slim Protocol signature:
Different downstream queues need different inputs. Forcing a fat
interface (to_email, condition_label, submitted_at) onto every adapter
encodes the email path's assumptions onto paths that don't need them.
The slim signature trades one extra SELECT on the email path for an
honest interface. At current scale (~5 submissions/day) the cost is
negligible.
"""

from typing import Protocol

from app.repositories.delivery_repository import DeliveryRepository
from app.repositories.pdf_repository import PDFRepository
from app.repositories.submission_repository import SubmissionRepository


class DownstreamEnqueuer(Protocol):
    """
    Uniform interface for the PDF worker's post-attachment queue write.

    Implementations are selected at worker startup by pdf_worker_main.py
    based on the MESH_DELIVERY environment variable. The PDF worker
    itself is downstream-agnostic.
    """

    def enqueue(self, *, submission_id: str) -> None:
        ...


class DeliveryEnqueuer:
    """
    Downstream enqueuer for the email delivery path.

    Reads the delivery email from pdf_jobs and the condition label and
    submitted_at timestamp from submission_records, then enqueues a
    delivery_jobs row via DeliveryRepository.create_job.

    The two reads are deliberate: the PDF worker no longer threads these
    values through its own call signature, so this adapter is
    self-sufficient. At ~5 submissions/day the extra SELECTs are not
    measurable. If this changes, cache locally before changing the seam.

    Idempotency: DeliveryRepository.create_job uses ON CONFLICT DO
    NOTHING on submission_id, so calling enqueue twice for the same
    submission is safe. This is required by the PDF worker's ordering
    invariant (see arch_submission.md).
    """

    def __init__(
        self,
        pdf_repo: PDFRepository,
        submission_repo: SubmissionRepository,
        delivery_repo: DeliveryRepository,
    ) -> None:
        self._pdf_repo = pdf_repo
        self._submission_repo = submission_repo
        self._delivery_repo = delivery_repo

    def enqueue(self, *, submission_id: str) -> None:
        to_email = self._pdf_repo.get_delivery_email(submission_id)
        submission = self._submission_repo.get_submission(submission_id)
        self._delivery_repo.create_job(
            submission_id=submission_id,
            to_email=to_email,
            condition_label=submission["condition_label"],
            submitted_at=submission["submitted_at"],
        )
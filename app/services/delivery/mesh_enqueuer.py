"""
MESH enqueuer.

The MESH-path implementation of the DownstreamEnqueuer Protocol (defined in
downstream_enqueuer.py). Selected at PDF worker startup by pdf_worker_main.py
when MESH_DELIVERY=1. The PDF worker itself stays downstream-agnostic.

Where DeliveryEnqueuer reads the delivery email and submission metadata before
writing a delivery_jobs row, MeshEnqueuer needs almost nothing at enqueue time:
the destination is a single deployment-wide value (the recipient mailbox,
resolved once at worker startup from MESH_RECIPIENT_MAILBOX_ID and passed into
the constructor), and the payload is built later by the dispatcher (Phase 3)
when it reads the attachment and submission metadata. So this adapter is a thin
forwarder to MeshRepository.create_job.

Idempotency: MeshRepository.create_job uses ON CONFLICT DO NOTHING on
submission_id, so calling enqueue twice for the same submission is safe. This
is required by the PDF worker's ordering invariant (see arch_submission.md):
save_attachment -> downstream.enqueue -> mark_done, where enqueue may run more
than once across worker retries.

Architecture rules (shared with downstream_enqueuer.py):
- This module must never generate PDFs, send messages, touch the database
  directly (it uses a repository), or import clinical engine modules.
"""

from app.repositories.mesh_repository import MeshRepository


class MeshEnqueuer:
    """
    Downstream enqueuer for the MESH delivery path.

    Writes a mesh_jobs row via MeshRepository.create_job, stamping the
    deployment-wide recipient mailbox ID onto the row so a later configuration
    change cannot misroute an already-queued referral.
    """

    def __init__(
        self,
        mesh_repo: MeshRepository,
        recipient_mailbox_id: str,
    ) -> None:
        self._mesh_repo = mesh_repo
        self._recipient_mailbox_id = recipient_mailbox_id

    def enqueue(self, *, submission_id: str) -> None:
        self._mesh_repo.create_job(
            submission_id=submission_id,
            recipient_mailbox_id=self._recipient_mailbox_id,
        )
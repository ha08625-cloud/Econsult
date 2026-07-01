"""
Attachment repository.

Database access for submission PDF attachments.
Handles the submission_attachments table.

This module is responsible for:
- Storing pre-rendered PDF bytes at PDF generation time (UPSERT — safe on retry)
- Retrieving PDF bytes for delivery (first attempt or retry)
- Deleting PDF bytes (exclusively used by deletion_job.py)

The PDF stored here is the canonical delivery artifact. It must never be
regenerated at retry time. Whatever was in the PDF at submission time is
what gets sent on every delivery attempt.

This module must never:
- Generate or modify PDF content (that belongs in pdf_formatter.py)
- Send emails (that belongs in delivery_service)
- Make decisions about retry logic (that belongs in the calling layer)
- Import clinical engine modules

save_attachment uses INSERT ... ON CONFLICT DO UPDATE (UPSERT) so that
a PDF worker retry that has already written the attachment does not raise
on the second write. PDF generation from the same inputs is deterministic,
so overwriting with the same bytes is safe.
"""

from app.core.db import get_conn


class AttachmentNotFound(Exception):
    """
    Raised when a submission's PDF attachment does not exist.

    This is an error, not a normal empty state. A missing attachment at
    delivery time means the ordering invariant has been broken and must
    be investigated. See arch_submission.md.
    """

    pass


class AttachmentRepository:
    def __init__(self, database_url: str):
        self.database_url = database_url

    def save_attachment(self, submission_id: str, pdf_bytes: bytes) -> None:
        """
        Store PDF bytes for a submission (UPSERT).

        Uses INSERT ... ON CONFLICT (submission_id) DO UPDATE so that a
        PDF worker retry that already wrote the attachment does not raise.
        PDF generation from the same inputs is deterministic, so overwriting
        is safe. The updated_at column is not present on this table; the
        SET clause updates pdf_bytes only.

        Called by the PDF worker as step 1 of its ordered sequence
        (save_attachment -> create_job -> mark_done). This ordering is the
        invariant that guarantees the delivery worker always finds the
        attachment when it claims a delivery job. Do not break this ordering.
        """
        with get_conn(self.database_url) as conn, conn.cursor() as cur:
            cur.execute(
                """
                    INSERT INTO submission_attachments (submission_id, pdf_bytes)
                    VALUES (%s, %s)
                    ON CONFLICT (submission_id) DO UPDATE
                        SET pdf_bytes = EXCLUDED.pdf_bytes
                    """,
                (submission_id, pdf_bytes),
            )

    def get_attachment(self, submission_id: str) -> bytes:
        """
        Retrieve PDF bytes for a submission.

        Raises AttachmentNotFound if the row does not exist. This is
        always an error condition — the ordering invariant guarantees
        a delivery job cannot exist unless save_attachment has already
        completed successfully. If the attachment is absent, the invariant
        has been broken and the error must propagate loudly.
        """
        with get_conn(self.database_url) as conn, conn.cursor() as cur:
            cur.execute(
                """
                    SELECT pdf_bytes
                    FROM submission_attachments
                    WHERE submission_id = %s
                    """,
                (submission_id,),
            )
            row = cur.fetchone()

        if row is None:
            raise AttachmentNotFound(
                f"No attachment found for submission {submission_id}. "
                "The ordering invariant has been violated — investigate immediately."
            )
        return bytes(row[0])

    def delete_attachment(self, submission_id: str) -> None:
        """
        Delete PDF bytes for a submission.

        Idempotent — does not raise if the row does not exist.
        Called exclusively by deletion_job.py for fully delivered submissions.
        """
        with get_conn(self.database_url) as conn, conn.cursor() as cur:
            cur.execute(
                """
                    DELETE FROM submission_attachments
                    WHERE submission_id = %s
                    """,
                (submission_id,),
            )

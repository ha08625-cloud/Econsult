"""
Attachment repository.

Database access for submission PDF attachments.
Handles the submission_attachments table.

This module is responsible for:
- Storing pre-rendered PDF bytes at submission time
- Retrieving PDF bytes for delivery (first attempt or retry)
- Deleting PDF bytes after successful delivery

The PDF stored here is the canonical delivery artifact. It must never be
regenerated at retry time. Whatever was in the PDF at submission time is
what gets sent on every delivery attempt.

This module must never:
- Generate or modify PDF content (that belongs in pdf_formatter.py)
- Send emails (that belongs in delivery_service)
- Make decisions about retry logic (that belongs in the calling layer)
- Import clinical engine modules
"""

from app.core.db import get_conn


class AttachmentNotFound(Exception):
    """
    Raised when a submission's PDF attachment does not exist.

    This is an error, not a normal empty state. A missing attachment at
    retry time means the submission was created in a broken state and
    must be investigated.
    """
    pass


class AttachmentRepository:
    def __init__(self, database_url: str):
        self.database_url = database_url

    def save_attachment(self, submission_id: str, pdf_bytes: bytes) -> None:
        """
        Store PDF bytes for a submission.

        Must be called exactly once per submission, immediately after
        create_submission and before any delivery attempt. Raises
        psycopg2.errors.UniqueViolation if the row already exists.
        """
        with get_conn(self.database_url) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO submission_attachments (submission_id, pdf_bytes)
                    VALUES (%s, %s)
                    """,
                    (submission_id, pdf_bytes),
                )

    def get_attachment(self, submission_id: str) -> bytes:
        """
        Retrieve PDF bytes for a submission.

        Raises AttachmentNotFound if the row does not exist. This is
        always an error condition — every submission should have an
        attachment until it is successfully delivered.
        """
        with get_conn(self.database_url) as conn:
            with conn.cursor() as cur:
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
                "The submission may have been created in a broken state."
            )
        return bytes(row[0])

    def delete_attachment(self, submission_id: str) -> None:
        """
        Delete PDF bytes after successful delivery.

        Idempotent — does not raise if the row does not exist.
        This allows safe repeated calls during retry cleanup.
        """
        with get_conn(self.database_url) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    DELETE FROM submission_attachments
                    WHERE submission_id = %s
                    """,
                    (submission_id,),
                )
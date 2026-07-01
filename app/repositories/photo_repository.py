"""
Photo repository.

Database access for the submission_photos table.

Responsibilities:
- Storing raw photo bytes at form submission time, one row per photo.
- Retrieving photos ordered by photo_index for PDF generation.

Architecture rules:
- This module must never import clinical engine modules.
- This module must never generate PDFs or send emails.
- Photo deletion is exclusively the responsibility of deletion_job.py.
  No delete method is provided here.
- save_photos is not idempotent by default. Callers must not call it twice
  for the same submission_id unless they first delete the existing rows
  (which only the deletion cron does, and only for fully delivered
  submissions). In practice the form router calls it exactly once.
"""

from app.core.db import get_conn


class PhotoRepository:
    def __init__(self, database_url: str):
        self.database_url = database_url

    def save_photos(self, submission_id: str, photo_bytes_list: list[bytes]) -> None:
        """
        Insert one row per photo into submission_photos.

        photo_index is assigned from enumeration (0-based) to preserve the
        order in which photos were uploaded. The PDF worker reads them in
        this order when embedding images.

        If photo_bytes_list is empty, no rows are inserted and the call
        returns silently. This is correct — a submission with no photos
        simply has no rows in this table.

        Raises psycopg2.errors.UniqueViolation if rows already exist for
        this submission_id (the primary key is (submission_id, photo_index)).
        The form router must call this exactly once per submission.
        """
        if not photo_bytes_list:
            return

        with get_conn(self.database_url) as conn, conn.cursor() as cur:
            for index, photo in enumerate(photo_bytes_list):
                cur.execute(
                    """
                        INSERT INTO submission_photos (submission_id, photo_index, photo_bytes)
                        VALUES (%s, %s, %s)
                        """,
                    (submission_id, index, photo),
                )

    def get_photos(self, submission_id: str) -> list[bytes]:
        """
        Retrieve photo bytes for a submission, ordered by photo_index.

        Returns an empty list if no photos exist for this submission.
        The PDF worker uses the returned list directly — an empty list
        means no PHOTOS section is rendered in the PDF.

        The caller (PDF worker) is responsible for comparing the length
        of this list against job.attachment_count as a defensive check.
        """
        with get_conn(self.database_url) as conn, conn.cursor() as cur:
            cur.execute(
                """
                    SELECT photo_bytes
                    FROM submission_photos
                    WHERE submission_id = %s
                    ORDER BY photo_index ASC
                    """,
                (submission_id,),
            )
            rows = cur.fetchall()

        return [bytes(row[0]) for row in rows]

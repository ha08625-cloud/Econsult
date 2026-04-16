"""
Submission repository.

Database access for submission records.
Handles the submission_records table.

This module is responsible for:
- Creating submission records at the point of form completion
- Retrieving submissions by ID

This module must never:
- Access clinical engine modules (form_logic, safety_engine, etc.)
- Send emails (that belongs in delivery_service)
- Make decisions about retry logic (that belongs in the orchestration layer)
"""

from dataclasses import asdict
from datetime import datetime

import psycopg2.extras
from psycopg2.extras import RealDictCursor

from app.core.db import get_conn
from app.models.serialisation_contracts import ClinicalOutput, AuditOutput


# Explicit column list for SELECT queries against submission_records.
# Must be updated whenever a migration adds or removes a column.
# Do not use SELECT * — new columns would appear silently in returned dicts
# and make schema changes harder to track.

_SUBMISSION_COLUMNS = """
    submission_id,
    practice_id,
    condition_id,
    condition_label,
    clinical_output_json,
    audit_output_json,
    submitted_at
"""


class SubmissionNotFound(Exception):
    """Raised when a submission_id does not exist."""
    pass


class SubmissionRepository:
    def __init__(self, database_url: str):
        self.database_url = database_url

    def create_submission(
        self,
        submission_id: str,
        practice_id: str,
        condition_id: str,
        condition_label: str,
        clinical_output: ClinicalOutput,
        audit_output: AuditOutput,
        submitted_at: datetime,
    ) -> None:
        """
        Create a new submission record.

        condition_label is the human-readable condition name at submission time.
        It is stored denormalised for historical fidelity — if the condition
        label is later changed in the ruleset, historical records retain the
        label that was active when the patient submitted.

        clinical_output and audit_output are stored as JSONB. psycopg2 does not
        automatically serialise dataclasses, so we convert to dict with asdict()
        first and wrap in psycopg2.extras.Json so psycopg2 serialises correctly
        for JSONB columns.

        Named parameters (%(name)s) are used throughout the INSERT rather than
        positional %s placeholders. This makes the column-to-value mapping
        explicit and prevents silent data corruption if columns are reordered.

        Raises psycopg2.errors.UniqueViolation if submission_id already exists.
        """
        clinical_dict = asdict(clinical_output)
        audit_dict = asdict(audit_output)

        with get_conn(self.database_url) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO submission_records (
                        submission_id,
                        practice_id,
                        condition_id,
                        condition_label,
                        clinical_output_json,
                        audit_output_json,
                        submitted_at
                    ) VALUES (
                        %(submission_id)s,
                        %(practice_id)s,
                        %(condition_id)s,
                        %(condition_label)s,
                        %(clinical_output_json)s,
                        %(audit_output_json)s,
                        %(submitted_at)s
                    )
                    """,
                    {
                        "submission_id": submission_id,
                        "practice_id": practice_id,
                        "condition_id": condition_id,
                        "condition_label": condition_label,
                        "clinical_output_json": psycopg2.extras.Json(clinical_dict),
                        "audit_output_json": psycopg2.extras.Json(audit_dict),
                        "submitted_at": submitted_at,
                    },
                )

    def get_submission(self, submission_id: str) -> dict:
        """
        Get a submission record by ID.

        Returns a dict with the columns listed in _SUBMISSION_COLUMNS.
        clinical_output_json and audit_output_json are returned as Python
        dicts (psycopg2 deserialises JSONB columns automatically) — callers
        do not need to call json.loads() on these fields.

        Raises SubmissionNotFound if submission_id does not exist.
        """
        with get_conn(self.database_url) as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    f"""
                    SELECT {_SUBMISSION_COLUMNS}
                    FROM submission_records
                    WHERE submission_id = %s
                    """,
                    (submission_id,),
                )
                row = cur.fetchone()

        if row is None:
            raise SubmissionNotFound(submission_id)
        return dict(row)

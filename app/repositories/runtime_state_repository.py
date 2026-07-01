"""
app/repositories/runtime_state_repository.py

Replaces app/core/persistence.py.

Database access for versioned runtime session state.
Handles the runtime_state_versions table.

Error classes live here because they are raised only by this repository,
following the same pattern as PracticeNotFound in practice_repository.py
and SubmissionNotFound in submission_repository.py.

This module must never:
- Import clinical engine modules
- Perform business logic
- Manage table creation (handled by Alembic migrations)
"""

from psycopg2.extras import Json, RealDictCursor

from app.core.db import get_conn


class RuntimeStateNotFound(Exception):
    pass


class VersionConflict(Exception):
    pass


class SessionClosed(Exception):
    pass


class RuntimeStateRepository:
    def __init__(self, database_url: str):
        self.database_url = database_url

    def get_latest(self, runtime_id: str) -> dict:
        """
        Return the most recent version row for runtime_id.

        Raises RuntimeStateNotFound if no row exists.
        Raises SessionClosed if the session has been closed.
        """
        with get_conn(self.database_url) as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT *
                    FROM runtime_state_versions
                    WHERE runtime_id = %s
                    ORDER BY version DESC
                    LIMIT 1
                    """,
                    (runtime_id,),
                )
                row = cur.fetchone()

        if row is None:
            raise RuntimeStateNotFound(runtime_id)

        if row["is_closed"]:
            raise SessionClosed(runtime_id)

        return dict(row)

    def insert_new_version(
        self,
        runtime_id: str,
        base_version: int,
        ruleset_hash: str,
        state_dict: dict,
    ) -> int:
        """
        Insert a new version row, incrementing base_version by 1.

        Raises RuntimeStateNotFound if runtime_id does not exist.
        Raises SessionClosed if the session is already closed.
        Raises VersionConflict if the current version does not match base_version
        (indicates a concurrent update).

        Returns the new version number.

        Note: state_dict is wrapped in psycopg2.extras.Json() before being passed
        to the query. psycopg2 does not automatically adapt plain dicts to JSONB —
        explicit wrapping is required.
        """
        with get_conn(self.database_url) as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT version, is_closed
                    FROM runtime_state_versions
                    WHERE runtime_id = %s
                    ORDER BY version DESC
                    LIMIT 1
                    """,
                    (runtime_id,),
                )
                latest = cur.fetchone()

                if latest is None:
                    raise RuntimeStateNotFound(runtime_id)

                if latest["is_closed"]:
                    raise SessionClosed(runtime_id)

                if latest["version"] != base_version:
                    raise VersionConflict()

                new_version = base_version + 1

                cur.execute(
                    """
                    INSERT INTO runtime_state_versions
                        (runtime_id, version, ruleset_hash, state_json, is_closed)
                    VALUES (%s, %s, %s, %s, FALSE)
                    """,
                    (runtime_id, new_version, ruleset_hash, Json(state_dict)),
                )

        return new_version

    def create_initial(
        self,
        runtime_id: str,
        ruleset_hash: str,
        state_dict: dict,
    ) -> None:
        """
        Insert version 1 row for a new session.

        Raises psycopg2.errors.UniqueViolation if runtime_id already exists.
        Unlike the old SQLite implementation, this does not use ON CONFLICT DO NOTHING —
        a duplicate runtime_id is a programming error and should propagate.

        Note: state_dict is wrapped in psycopg2.extras.Json() before being passed
        to the query. psycopg2 does not automatically adapt plain dicts to JSONB —
        explicit wrapping is required.
        """
        with get_conn(self.database_url) as conn, conn.cursor() as cur:
            cur.execute(
                """
                    INSERT INTO runtime_state_versions
                        (runtime_id, version, ruleset_hash, state_json, is_closed)
                    VALUES (%s, 1, %s, %s, FALSE)
                    """,
                (runtime_id, ruleset_hash, Json(state_dict)),
            )

    def close_session(self, runtime_id: str, version: int) -> None:
        """
        Mark the session as closed by setting is_closed = TRUE on the latest row.

        Raises RuntimeStateNotFound if runtime_id does not exist.
        Raises VersionConflict if version does not match the current latest version.
        """
        with get_conn(self.database_url) as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT version
                    FROM runtime_state_versions
                    WHERE runtime_id = %s
                    ORDER BY version DESC
                    LIMIT 1
                    """,
                    (runtime_id,),
                )
                row = cur.fetchone()

                if row is None:
                    raise RuntimeStateNotFound(runtime_id)

                if row["version"] != version:
                    raise VersionConflict()

                cur.execute(
                    """
                    UPDATE runtime_state_versions
                    SET is_closed = TRUE
                    WHERE runtime_id = %s AND version = %s
                    """,
                    (runtime_id, version),
                )

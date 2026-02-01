import sqlite3
import json
from contextlib import contextmanager
from typing import Optional


class RuntimeStateNotFound(Exception):
    pass


class VersionConflict(Exception):
    pass


class SessionClosed(Exception):
    pass


class RuntimeStateRepository:
    def __init__(self, db_path: str):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        with self._conn() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS runtime_state_versions (
                    runtime_id TEXT NOT NULL,
                    version INTEGER NOT NULL,
                    ruleset_hash TEXT NOT NULL,
                    state_json TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    is_closed BOOLEAN NOT NULL DEFAULT 0,
                    PRIMARY KEY (runtime_id, version)
                )
                """
            )

    @contextmanager
    def _conn(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def get_latest(self, runtime_id: str) -> dict:
        with self._conn() as conn:
            row = conn.execute(
                """
                SELECT * FROM runtime_state_versions
                WHERE runtime_id = ?
                ORDER BY version DESC
                LIMIT 1
                """,
                (runtime_id,),
            ).fetchone()

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
        with self._conn() as conn:
            latest = conn.execute(
                """
                SELECT version, is_closed FROM runtime_state_versions
                WHERE runtime_id = ?
                ORDER BY version DESC
                LIMIT 1
                """,
                (runtime_id,),
            ).fetchone()

            if latest is None:
                raise RuntimeStateNotFound(runtime_id)

            if latest["is_closed"]:
                raise SessionClosed(runtime_id)

            if latest["version"] != base_version:
                raise VersionConflict()

            new_version = base_version + 1

            conn.execute(
                """
                INSERT INTO runtime_state_versions
                (runtime_id, version, ruleset_hash, state_json, is_closed)
                VALUES (?, ?, ?, ?, 0)
                """,
                (
                    runtime_id,
                    new_version,
                    ruleset_hash,
                    json.dumps(state_dict),
                ),
            )

            return new_version

    def create_initial(
        self,
        runtime_id: str,
        ruleset_hash: str,
        state_dict: dict,
    ):
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO runtime_state_versions
                (runtime_id, version, ruleset_hash, state_json, is_closed)
                VALUES (?, 1, ?, ?, 0)
                """,
                (runtime_id, ruleset_hash, json.dumps(state_dict)),
            )

    def close_session(self, runtime_id: str, version: int):
        with self._conn() as conn:
            row = conn.execute(
                """
                SELECT version FROM runtime_state_versions
                WHERE runtime_id = ?
                ORDER BY version DESC
                LIMIT 1
                """,
                (runtime_id,),
            ).fetchone()

            if row is None:
                raise RuntimeStateNotFound(runtime_id)

            if row["version"] != version:
                raise VersionConflict()

            conn.execute(
                """
                UPDATE runtime_state_versions
                SET is_closed = 1
                WHERE runtime_id = ? AND version = ?
                """,
                (runtime_id, version),
            )

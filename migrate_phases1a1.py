"""
Migration: Phase 1A.1

Changes:
- Recreates practices table with required email column
- Creates submission_records table

Run from project root:
    python -m migrate_phase1a1

WARNING: This drops and recreates the practices table.
Any existing practice rows will be lost.
This is safe in development. Do not run against production data.
"""

import sqlite3
import os
import sys


def run(db_path: str) -> None:
    print(f"Running Phase 1A.1 migration on: {db_path}")

    conn = sqlite3.connect(db_path)
    try:
        cursor = conn.cursor()

        # --- practices table ---

        # Check for existing rows so we can warn before dropping
        try:
            existing = cursor.execute("SELECT COUNT(*) FROM practices").fetchone()[0]
            if existing > 0:
                print(
                    f"WARNING: practices table contains {existing} row(s). "
                    "These will be lost. Press Enter to continue or Ctrl+C to abort."
                )
                input()
        except sqlite3.OperationalError:
            # Table does not exist yet — nothing to warn about
            pass

        print("Dropping practices table if it exists...")
        cursor.execute("DROP TABLE IF EXISTS practices")

        print("Creating practices table with email column...")
        cursor.execute(
            """
            CREATE TABLE practices (
                practice_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                email TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )

        # --- submission_records table ---

        print("Creating submission_records table if it does not exist...")
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS submission_records (
                submission_id TEXT PRIMARY KEY,
                practice_id TEXT NOT NULL,
                condition_id TEXT NOT NULL,
                clinical_output_json TEXT NOT NULL,
                audit_output_json TEXT NOT NULL,
                submitted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                delivery_status TEXT NOT NULL DEFAULT 'pending',
                delivery_email TEXT NOT NULL,
                delivered_at TIMESTAMP,
                delivery_error TEXT
            )
            """
        )

        conn.commit()
        print("Migration complete.")

    except Exception as e:
        conn.rollback()
        print(f"Migration failed: {e}")
        sys.exit(1)
    finally:
        conn.close()


if __name__ == "__main__":
    db_path = os.environ.get("DB_PATH", "runtime.db")
    run(db_path)
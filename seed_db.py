"""
Database seed script.

Creates the practice record if it does not already exist.
Safe to run multiple times - skips creation if the record is present.

Required environment variables:
    PRACTICE_ID   - practice identifier (e.g. summertown_health_centre)
    DATABASE_URL  - Postgres connection string (set by Railway)

Optional environment variables:
    PRACTICE_NAME  - human-readable name (defaults to PRACTICE_ID if not set)
    PRACTICE_EMAIL - email address for clinical output delivery
                     (defaults to demo@demo.net if not set)

Usage:
    PYTHONPATH=. python seed_db.py
"""

import os
import sys

from app.repositories.practice_repository import PracticeRepository


def seed():
    practice_id = os.environ.get("PRACTICE_ID")
    if not practice_id:
        print("ERROR: PRACTICE_ID environment variable is not set.")
        sys.exit(1)

    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        print("ERROR: DATABASE_URL environment variable is not set.")
        sys.exit(1)

    practice_name = os.environ.get("PRACTICE_NAME", practice_id)
    practice_email = os.environ.get("PRACTICE_EMAIL", "demo@demo.net")

    print(f"Practice ID:    {practice_id}")
    print(f"Practice name:  {practice_name}")
    print(f"Practice email: {practice_email}")

    repo = PracticeRepository(database_url)

    if repo.practice_exists(practice_id):
        print(f"Practice '{practice_id}' already exists. Nothing to do.")
        return

    repo.create_practice(
        practice_id=practice_id,
        name=practice_name,
        email=practice_email,
    )
    print(f"Practice '{practice_id}' created successfully.")


if __name__ == "__main__":
    seed()

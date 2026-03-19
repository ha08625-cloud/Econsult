"""
conftest.py — pytest configuration for the test suite.

Loads .env from the project root before any test module is imported.
This ensures DATABASE_URL and other required env vars are available
when test modules check for them at import time.

dotenv is a dev dependency only. If python-dotenv is not installed,
tests will still run — they will just rely on env vars being set manually.
"""

import os
from pathlib import Path


def _load_dotenv():
    try:
        from dotenv import load_dotenv
    except ImportError:
        return

    env_path = Path(__file__).parent.parent / ".env"
    if env_path.exists():
        load_dotenv(env_path, override=False)


_load_dotenv()
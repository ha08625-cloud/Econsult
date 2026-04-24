"""
scripts/create_admin_user.py

One-time management command for inserting an admin user before first boot.

Usage:
    DATABASE_URL=... PRACTICE_ID=... ALLOWED_ADMIN_DOMAINS=... ADMIN_URL=... \\
        python scripts/create_admin_user.py <email>

Optional flag:
    --create-practice   Also insert the practice row if it does not exist.
                        Requires PRACTICE_NAME and PRACTICE_EMAIL env vars.
                        Intended for CI environments only. Production operators
                        should insert the practice record manually — see
                        docs/deployment_checklist.md.

After inserting the user, the script generates a one-time password setup token
and prints a setup URL to stdout. The operator must visit this URL (or forward
it to the user) to complete account setup.

If ADMIN_URL is not set, the raw token is printed so that the setup URL can
be constructed manually. The token expires in 1 hour.

This script does not start the application and does not run Alembic migrations.
Migrations must have been run before this script is called.

Exit codes:
    0 — success, or user already exists (idempotent)
    1 — error (missing env var, domain not permitted, practice not found, etc.)
"""

import os
import sys

# ---------------------------------------------------------------------------
# Locate the project root so app.* imports resolve regardless of where the
# script is called from.
# ---------------------------------------------------------------------------
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_SCRIPT_DIR)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)


def _require_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        print(f"ERROR: Required environment variable not set: {name}", file=sys.stderr)
        sys.exit(1)
    return value


def main() -> None:
    # Parse arguments before importing app modules so that --help works
    # without a database connection.
    args = sys.argv[1:]
    create_practice_flag = "--create-practice" in args
    positional = [a for a in args if not a.startswith("--")]

    if not positional:
        print(
            "Usage: python scripts/create_admin_user.py <email> [--create-practice]",
            file=sys.stderr,
        )
        print(
            "  --create-practice   Insert the practice row if absent (CI use only).",
            file=sys.stderr,
        )
        sys.exit(1)

    email = positional[0].strip()

    # ---------------------------------------------------------------------------
    # Read required environment variables.
    # ---------------------------------------------------------------------------
    database_url = _require_env("DATABASE_URL")
    practice_id = _require_env("PRACTICE_ID")
    allowed_admin_domains = _require_env("ALLOWED_ADMIN_DOMAINS")
    admin_url = os.environ.get("ADMIN_URL", "").strip()

    # ---------------------------------------------------------------------------
    # Import app modules only after path setup and env checks.
    # ---------------------------------------------------------------------------
    from app.repositories.practice_repository import PracticeRepository
    from app.repositories.auth_repository import AuthRepository
    from app.services.admin.auth_service import validate_admin_domain, generate_reset_token

    practice_repo = PracticeRepository(database_url)
    auth_repo = AuthRepository(database_url)

    # ---------------------------------------------------------------------------
    # Validate email domain.
    # ---------------------------------------------------------------------------
    if not validate_admin_domain(email, allowed_admin_domains):
        print(
            f"ERROR: Email domain is not permitted.\n"
            f"  Email:           {email}\n"
            f"  Allowed domains: {allowed_admin_domains}",
            file=sys.stderr,
        )
        sys.exit(1)

    # ---------------------------------------------------------------------------
    # Ensure the practice row exists.
    # ---------------------------------------------------------------------------
    practice = practice_repo.get_practice(practice_id)

    if practice is None:
        if create_practice_flag:
            practice_name = os.environ.get("PRACTICE_NAME", "").strip() or practice_id
            practice_email = os.environ.get("PRACTICE_EMAIL", "").strip()
            if not practice_email:
                print(
                    "ERROR: PRACTICE_EMAIL must be set when using --create-practice.",
                    file=sys.stderr,
                )
                sys.exit(1)
            practice_repo.create_practice(
                practice_id=practice_id,
                name=practice_name,
                email=practice_email,
            )
            print(f"Practice '{practice_id}' created.")
        else:
            print(
                f"ERROR: Practice '{practice_id}' not found in database.\n"
                "Insert the practice record before creating users.\n"
                "See docs/deployment_checklist.md.",
                file=sys.stderr,
            )
            sys.exit(1)

    # ---------------------------------------------------------------------------
    # Check whether the user already exists — idempotent.
    # ---------------------------------------------------------------------------
    existing = auth_repo.get_user_by_email(email)
    if existing is not None:
        print(f"User '{email}' already exists for practice '{practice_id}'.")
        print("Generating a fresh setup token for this user.")
        raw_token = generate_reset_token(existing["id"], auth_repo)
        _print_setup_instructions(email, raw_token, admin_url)
        sys.exit(0)

    # ---------------------------------------------------------------------------
    # Insert the user.
    # ---------------------------------------------------------------------------
    auth_repo.insert_user(email=email, practice_id=practice_id, role="admin")
    print(f"Admin user '{email}' created for practice '{practice_id}'.")

    # ---------------------------------------------------------------------------
    # Generate a setup token.
    # ---------------------------------------------------------------------------
    # Re-fetch to get the id assigned by Postgres.
    new_user = auth_repo.get_user_by_email(email)
    if new_user is None:
        print(
            "ERROR: User was inserted but could not be re-fetched. "
            "Cannot generate setup token.",
            file=sys.stderr,
        )
        sys.exit(1)

    raw_token = generate_reset_token(new_user["id"], auth_repo)
    _print_setup_instructions(email, raw_token, admin_url)


def _print_setup_instructions(email: str, raw_token: str, admin_url: str) -> None:
    """Print setup URL or raw token depending on whether ADMIN_URL is set."""
    if admin_url:
        setup_url = f"{admin_url}#reset:{raw_token}"
        print(f"\nSetup URL for '{email}' (expires in 1 hour):")
        print(f"  {setup_url}")
        print("\nForward this URL to the user so they can set their password.")
    else:
        print(
            "\nWARNING: ADMIN_URL is not set. Cannot construct a full setup URL."
        )
        print(f"Raw token for '{email}' (expires in 1 hour): {raw_token}")
        print(
            "Construct the setup URL manually: "
            "<ADMIN_URL>#reset:<token>"
        )


if __name__ == "__main__":
    main()
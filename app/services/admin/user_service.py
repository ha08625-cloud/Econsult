"""
app/services/admin/user_service.py

Business logic for admin user management.

Responsibilities:
- Validating email format and domain policy before adding a user.
- Enforcing tenant safety rules before removing a user (self-delete guard,
  last-user guard).
- Looking up a user for invitation resend.

This module must never:
- Touch the database directly (all DB access goes through repositories).
- Send emails (that is the router's responsibility, after the transaction commits).
- Import from routers.

All methods that mutate state accept a conn parameter. The caller (the router)
owns the transaction lifecycle — it opens get_conn, calls this service, calls
audit_repo.log_event, then the with block commits. This ensures that the
mutation and the audit log write are atomic.

resend_invitation performs no writes and accepts no conn parameter.
"""

import logging
from typing import TYPE_CHECKING

import psycopg2.errors

from app.core.errors import (
    INVALID_PAYLOAD,
    ACTION_NOT_PERMITTED,
    USER_ALREADY_EXISTS,
    USER_NOT_FOUND,
)
from app.services.admin.auth_service import validate_admin_domain

if TYPE_CHECKING:
    from app.repositories.auth_repository import AuthRepository
    from app.repositories.practice_repository import PracticeRepository
    from app.core.admin_context import AdminContext

logger = logging.getLogger(__name__)


def _validate_email_format(email: str) -> None:
    """
    Check that email has exactly one '@', a non-empty local part, and a
    non-empty domain part.

    This is a deliberately minimal check — we do not attempt full RFC 5322
    parsing. The domain policy check (validate_admin_domain) is separate.

    Raises INVALID_PAYLOAD if the format check fails.
    """
    if (
        "@" not in email
        or email.count("@") != 1
        or len(email.split("@")[0]) == 0
        or len(email.split("@")[1]) == 0
    ):
        raise INVALID_PAYLOAD("Invalid email address format.")


def add_user(
    email: str,
    allowed_domains: str,
    admin_context: "AdminContext",
    practice_repo: "PracticeRepository",
    auth_repo: "AuthRepository",
    conn,
) -> None:
    """
    Add a new admin user for the current practice.

    Steps:
    1. Normalise email to lowercase.
    2. Validate basic email format — raise INVALID_PAYLOAD on failure.
    3. Validate domain against allowed_domains — raise ACTION_NOT_PERMITTED
       if the domain is not permitted.
    4. Acquire a row-level lock on the practice row to serialise concurrent
       add/remove operations for this tenant.
    5. Insert the user — raise USER_ALREADY_EXISTS on duplicate email.

    Returns nothing. The router has the email from the request body and
    passes it directly to send_admin_invitation after the transaction commits.

    conn is required — the caller owns the transaction.
    """
    email = email.lower()

    _validate_email_format(email)

    if not validate_admin_domain(email, allowed_domains):
        raise ACTION_NOT_PERMITTED("Admin email must use an approved domain.")

    practice_repo.lock_practice(admin_context.practice_id, conn=conn)

    try:
        auth_repo.insert_user(email, admin_context.practice_id, role="admin", conn=conn)
    except psycopg2.errors.UniqueViolation:
        raise USER_ALREADY_EXISTS()


def remove_user(
    target_user_id: str,
    admin_context: "AdminContext",
    practice_repo: "PracticeRepository",
    auth_repo: "AuthRepository",
    conn,
) -> None:
    """
    Remove an admin user from the current practice.

    Guards:
    - An admin cannot delete their own account.
    - The practice must retain at least one admin user.
    - The target user must exist within this practice (tenant boundary).

    The practice lock is acquired before reading the user list so that two
    concurrent remove requests cannot both pass the minimum-user check and
    both delete, leaving the practice with no admins.

    conn is required — the caller owns the transaction.
    """
    if target_user_id == admin_context.user_id:
        raise ACTION_NOT_PERMITTED("You cannot delete your own account.")

    practice_repo.lock_practice(admin_context.practice_id, conn=conn)

    # Read the user list inside the locked transaction so this read is
    # consistent with the lock — no concurrent transaction can add or
    # remove users between the lock acquisition and this read.
    users = auth_repo.get_users_by_practice(admin_context.practice_id, conn=conn)
    user_ids = {u["id"] for u in users}

    if target_user_id not in user_ids:
        raise USER_NOT_FOUND()

    if len(users) <= 1:
        raise ACTION_NOT_PERMITTED("You cannot delete the last admin user.")

    auth_repo.delete_user(target_user_id, admin_context.practice_id, conn=conn)


def resend_invitation(
    target_user_id: str,
    admin_context: "AdminContext",
    auth_repo: "AuthRepository",
) -> str:
    """
    Look up the email address for a user so the router can resend their
    invitation.

    Returns the user's email string on success.
    Raises USER_NOT_FOUND if the user does not exist within this practice.

    No conn parameter — this method performs no writes. The router opens a
    transaction separately, solely to write the audit log.
    """
    user = auth_repo.get_user_by_id(target_user_id, admin_context.practice_id)
    if user is None:
        raise USER_NOT_FOUND()
    return user["email"]
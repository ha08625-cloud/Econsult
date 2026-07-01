"""
app/services/admin/user_service.py

Business logic for admin user management.

Responsibilities:
- add_user: validate, lock, insert, handle duplicate
- remove_user: validate, lock, list, guard, delete
- resend_invitation: look up user by id, return email

This module sits between the router and the repositories. It never touches
the database directly — all DB access goes through the repository arguments.
Email delivery is handled entirely by the router after these functions return.

The conn parameter is required by all write operations because:
- The practice row lock must be held for the full duration of the operation.
- The audit log insert must be atomic with the user write.
Both are opened once in the router and passed in here.

resend_invitation has no conn parameter — it performs no writes and has no
transaction to join.
"""

import logging
from typing import TYPE_CHECKING

import psycopg2.errors

from app.core.errors import (
    ACTION_NOT_PERMITTED,
    INVALID_PAYLOAD,
    USER_ALREADY_EXISTS,
    USER_NOT_FOUND,
)
from app.services.admin.auth_service import validate_admin_domain
from app.utils.email_utils import is_valid_email_format

if TYPE_CHECKING:
    from app.core.admin_context import AdminContext
    from app.repositories.auth_repository import AuthRepository
    from app.repositories.practice_repository import PracticeRepository

logger = logging.getLogger(__name__)


def add_user(
    email: str,
    allowed_domains: str,
    admin_context: "AdminContext",
    practice_repo: "PracticeRepository",
    auth_repo: "AuthRepository",
    conn,
) -> None:
    """
    Validate, lock, and insert a new admin user.

    Steps:
    1. Normalise email to lowercase.
    2. Validate basic email format — raise INVALID_PAYLOAD if malformed.
    3. Validate email domain against allowed_domains — raise ACTION_NOT_PERMITTED
       if the domain is not on the allowlist.
    4. Acquire a row-level lock on the practice row to serialise concurrent
       add/remove operations for this tenant.
    5. Insert the user — raise USER_ALREADY_EXISTS if the email is taken.

    Returns nothing. The router already has the email from the request body
    and calls send_admin_invitation directly after this function returns.

    conn is required — the insert must be atomic with the audit log write
    and must happen inside the transaction that holds the practice lock.
    """
    email = email.lower()

    if not is_valid_email_format(email):
        raise INVALID_PAYLOAD("Invalid email address format.")

    if not validate_admin_domain(email, allowed_domains):
        raise ACTION_NOT_PERMITTED("Admin email must use an approved domain.")

    practice_repo.lock_practice(admin_context.practice_id, conn=conn)

    try:
        auth_repo.insert_user(
            email=email,
            practice_id=admin_context.practice_id,
            role="admin",
            conn=conn,
        )
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
    Validate and delete an admin user.

    Steps:
    1. Reject self-deletion — raise ACTION_NOT_PERMITTED if target is the
       authenticated user.
    2. Acquire a row-level lock on the practice row.
    3. Read all users for this practice inside the same transaction (conn is
       passed through so the read is consistent with the lock — two concurrent
       deletes cannot both pass the minimum-user check).
    4. Verify the target user exists in this practice — raise USER_NOT_FOUND
       if not.
    5. Reject deletion if only one user remains — raise ACTION_NOT_PERMITTED.
    6. Delete the user. Postgres cascades the delete to admin_sessions via
       the ON DELETE CASCADE FK added in migration 0002.

    conn is required — the delete must be atomic with the audit log write
    and must happen inside the transaction that holds the practice lock.
    """
    if target_user_id == admin_context.user_id:
        raise ACTION_NOT_PERMITTED("You cannot delete your own account.")

    practice_repo.lock_practice(admin_context.practice_id, conn=conn)

    users = auth_repo.get_users_by_practice(admin_context.practice_id, conn=conn)

    user_ids = {u["id"] for u in users}
    if target_user_id not in user_ids:
        raise USER_NOT_FOUND()

    if len(users) <= 1:
        raise ACTION_NOT_PERMITTED("You cannot delete the last admin user.")

    auth_repo.delete_user(
        user_id=target_user_id,
        practice_id=admin_context.practice_id,
        conn=conn,
    )


def resend_invitation(
    target_user_id: str,
    admin_context: "AdminContext",
    auth_repo: "AuthRepository",
) -> str:
    """
    Look up a user by id and return their email for re-sending an invitation.

    Raises USER_NOT_FOUND if the user does not exist in this practice.
    Returns the user's email address. The router handles delivery.

    No conn parameter — this function performs no writes.
    """
    user = auth_repo.get_user_by_id(target_user_id, admin_context.practice_id)
    if user is None:
        raise USER_NOT_FOUND()
    return user["email"]

"""
Admin API master router.

This file orchestrates the sub-routers for the admin domain.
Prefix /admin and tag "admin" are applied when registered in main.py.

This module enforces strict domain boundaries: it must never import clinical
engine modules, presentation_service, or patient-facing runtime states.
"""

from fastapi import APIRouter

from app.routers.admin import (
    admin_auth_router,
    admin_availability_router,
    admin_practice_router,
    admin_audit_router,
)

router = APIRouter()

# ---------------------------------------------------------------------------
# Admin Sub-Routers
# ---------------------------------------------------------------------------
# The `require_admin` dependency is applied individually within the route
# definitions of the sub-routers (except auth, which is unauthenticated).

router.include_router(admin_auth_router.router, tags=["admin-auth"])
router.include_router(admin_practice_router.router, tags=["admin-practice"])
router.include_router(admin_availability_router.router, tags=["admin-availability"])
router.include_router(admin_audit_router.router, tags=["admin-audit"])
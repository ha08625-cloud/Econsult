### Admin portal sliding window Plan
**1. Adjust Constants (admin_context.py)**
 * Update the TTL constant to 30 minutes: SESSION_TTL_MINUTES = 30.
 * SESSION_COOKIE_MAX_AGE will automatically compute to 1800 seconds.
**2. Add Repository Method (auth_repository.py)**
 * Add update_session_expiry(self, session_id: str, new_expires_at: datetime) -> None.
 * This will execute a simple UPDATE admin_sessions SET expires_at = %s WHERE session_id = %s::uuid.
**3. Update Protocol & Dependency (admin_context.py)**
 * Add update_session_expiry to the AuthProvider Protocol so require_admin can use it while maintaining the strict dependency boundary.
 * Modify require_admin to accept response: Response.
 * Inside require_admin, after successfully validating the session:
   * Calculate new_expires_at = datetime.now(tz=timezone.utc) + timedelta(minutes=SESSION_TTL_MINUTES).
   * Call auth_repo.update_session_expiry(session_id, new_expires_at).
   * Update the cookie using response.set_cookie(key=SESSION_COOKIE_NAME, value=session_id, max_age=SESSION_COOKIE_MAX_AGE, httponly=True, secure=True, samesite="lax").

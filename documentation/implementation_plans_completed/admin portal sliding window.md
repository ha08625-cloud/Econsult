## Implementation plan: 60-minute sliding admin sessions

### Backend

**1. `app/core/admin_context.py`**
- `SESSION_TTL_MINUTES = 60`; `SESSION_COOKIE_MAX_AGE` derives automatically. Rewrite the stale comment ("24 hours is appropriate...") to explain the sliding-window design instead.
- Add `update_session_expiry(session_id: str, ttl_minutes: int) -> None` to the `AuthProvider` Protocol.
- `require_admin` gains a `response: Response` parameter. After successful validation: call `auth_repo.update_session_expiry(session_id, SESSION_TTL_MINUTES)` and re-issue the cookie with `httponly=True, secure=True, samesite="strict", max_age=SESSION_COOKIE_MAX_AGE` — matching the login cookie exactly.
- The refresh is best-effort: wrapped in try/except, logged on failure, request proceeds. A dead DB would fail the validation step anyway, so this only covers transient refresh failures.
- Update the module docstring (cookie is now re-set by `require_admin`, not only by `/auth/verify`).

**2. `app/repositories/auth_repository.py`**
- New method `update_session_expiry(session_id, ttl_minutes)` executing `UPDATE admin_sessions SET expires_at = NOW() + make_interval(mins => %s) WHERE session_id = %s::uuid`. All time arithmetic on the DB clock, consistent with `get_session_context`. No `conn` parameter — it never joins another transaction. Idempotent, no-ops on missing rows.

### Frontend (admin UI)

**3. `frontend/admin-ui/src/App.tsx`** — preserve state on mid-session expiry
- Current behaviour tears down `EditorView` on `AuthError`, discarding unsaved work (the comments even document this as acceptable "given the 24-hour TTL" — no longer true).
- Change: add a `sessionExpired` boolean alongside `authState`. `handleAuthError` sets it to true instead of switching to `login` — `EditorView` stays mounted, so `SignpostingEditor` text, `AvailabilityEditor` state, active tab, and selected condition all survive.
- While `sessionExpired` is true, render `LoginView` in a modal overlay above the (inert) editor, with a note like "Your session expired. Log in again to continue — your unsaved changes are kept." On success, simply clear the flag; no `fetchConditions` refetch, no remount. The user re-clicks Save on whatever action failed — no automatic retry of the failed request.
- The startup probe and explicit logout paths are unchanged (full-page `LoginView`, state discarded — correct for logout).
- Re-login requires the full password + OTP flow. That is inherent to the auth design and correct; the overlay does not shortcut 2FA.
- Include an explicit "Log out and discard changes" escape hatch in the overlay.
- Update the now-inaccurate docstrings in `App.tsx` and `EditorView.tsx`.

**4. Minor CSS** in `index.css` for the modal overlay (backdrop, centered panel). `LoginView` itself should need no logic changes — it already takes an `onSuccess` callback.

### Tests

- `test_admin_context.py`: add `update_session_expiry` to the fake providers; new tests — refresh called on valid session, refresh failure does not 500, Set-Cookie present with `strict`/`max_age=3600` on protected responses.
- Repository integration test for `update_session_expiry` (extends expiry; no-ops on unknown id), marked `pytestmark = pytest.mark.integration`.
- `EditorView`/`App` vitest coverage: `AuthError` shows overlay with editor still mounted; successful re-login dismisses overlay and preserves state.
- I will check `test_admin_auth_router.py` for any hardcoded 24-hour assertions while editing.

### Afterwards
Once coded and approved, I will prompt you with a git commit message and offer updates to `arch_admin.md` and `arch_security.md` (both describe the 24-hour fixed TTL and the intentional-data-loss behaviour, which this change reverses).

One caveat to accept explicitly: with sliding expiry there is still no absolute session cap — an active admin can stay logged in indefinitely

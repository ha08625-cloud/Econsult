# Admin Portal & Configuration

**LLM INSTRUCTIONS:** This document covers design decisions and strict boundaries for the admin domain. Read the actual source files for function signatures, field names, and endpoint details.

---

## Scope

Admin authentication, editing per-condition signposting, configuring availability (schedule, overrides, per-date exceptions), managing practice email and doctor list, managing admin users, and the admin-portal frontend.

**Key files:** `app/routers/admin_router.py` (orchestrator), `app/routers/admin/admin_auth_router.py`, `app/routers/admin/admin_practice_router.py`, `app/routers/admin/admin_availability_router.py`, `app/routers/admin/admin_audit_router.py`, `app/routers/admin/admin_user_router.py`, `admin_context.py`, `app/services/admin/auth_service.py`, `app/services/admin/user_service.py`, `app/repositories/auth_repository.py`, `app/repositories/audit_repository.py`, `app/repositories/practice_repository.py`, `app/services/delivery/admin_delivery_service.py`, `availability_repository.py`, `availability_service.py`, `app/utils/http_utils.py`, `app/utils/email_utils.py`, `frontend/admin-ui/src/*`

---

## Design Decisions & Invariants

### Router Structure

The admin domain uses a thin orchestrator (`admin_router.py`) that registers five sub-routers from the `app/routers/admin/` package. Each sub-router owns a single domain boundary and mirrors its corresponding repository or service:

- `admin_auth_router.py` — password+OTP login (two steps), password reset/setup, logout (all unauthenticated)
- `admin_practice_router.py` — conditions list, practice settings, signposting, doctor list
- `admin_availability_router.py` — weekly config, manual overrides, per-date exceptions
- `admin_audit_router.py` — audit log read endpoint
- `admin_user_router.py` — list, add, delete, and resend-invitation for admin users

The `require_admin` dependency is applied within each sub-router's route definitions, not in the orchestrator. Auth endpoints are deliberately excluded.

The domain boundary invariant applies to all sub-routers: **no sub-router may import clinical engine modules, `presentation_service`, `serialisation`, `projection`, or `runtime_state`.**

---

### Authentication (`admin_context.py`, `auth_service.py`, `auth_repository.py`)

Authentication is two-factor: password (factor 1) followed by a one-time email code (factor 2). Sessions are issued only after both factors pass. All session management uses HttpOnly cookies.

**Login flow:**

1. `POST /admin/auth/login` — verifies email and password. On success: synchronously generates a 6-digit OTP, hashes it with bcrypt, and upserts it to `admin_auth_codes`. Then dispatches email delivery as a FastAPI `BackgroundTask` so the network call does not block the response. Returns `{"ok": true}` — the client transitions to the OTP entry screen. On failure: returns `INVALID_CREDENTIALS` (HTTP 422). The same generic error is returned regardless of which gate failed (user not found, wrong password, account locked, no password set, OTP cooldown active). See the timing attack mitigation section.

2. `POST /admin/auth/verify` — runs the OTP verification pipeline: user lookup, code record lookup, lockout check (3 attempts), expiry check (10 minutes), bcrypt comparison. On success: deletes the code, creates a session, sets an HttpOnly session cookie (`session_id`), and updates `admin_users.last_login` atomically. All failure paths raise `INVALID_AUTH_CODE` (HTTP 422). Route unchanged from the previous single-factor flow.

3. `POST /admin/auth/logout` — deletes the session if a cookie is present, clears the cookie with `Max-Age=0`. No auth required — logout must succeed even for expired sessions.

**Background task OTP delivery:**
The OTP is written to the database synchronously before the 200 response is returned. This guarantees the DB write succeeded before the client transitions to the OTP screen. Email delivery is then dispatched as a background task (`_send_mfa_code_background`) to avoid blocking on the SMTP/HTTP network call. If the background delivery fails, the task catches the exception, reports it to Sentry, and **deletes the OTP record from the database**. Cleanup on failure is important: without it, the 60-second cooldown would block an immediate retry even though the code was never delivered.

**Password reset / setup flow:**

- `POST /admin/auth/request-reset` — accepts an email address. Always returns 200 to prevent user enumeration. A `_fixed_delay()` is applied before acting on the user-lookup result to prevent distinguishing a DB hit from a miss via response time. If the user exists, generates a reset token synchronously and dispatches the setup email as a FastAPI `BackgroundTask` (`_send_reset_email_background`) — the Mailgun HTTP round trip happens after the response is sent, so it cannot reintroduce the timing leak the fixed delay is meant to prevent (mirrors the `POST /auth/login` OTP pattern below). No audit log is written — recording hit/miss here would enumerate registered addresses in the audit trail.

- `POST /admin/auth/set-password` — accepts the raw token (from the `#reset:{token}` URL hash fragment) and a new password. Verifies the token by SHA-256 hashing and DB lookup. Tokens are single-use: they are deleted immediately on lookup regardless of whether the expiry check passes. Validates password strength with zxcvbn (score >= 3, length 12–128 characters). On success, stores the bcrypt hash and sets `password_changed_at` atomically. Returns `INVALID_RESET_TOKEN` (422) for absent/expired/consumed tokens; `WEAK_PASSWORD` (422) with the zxcvbn feedback string for weak passwords.

**Reset token design:**
- Raw tokens are generated with `secrets.token_urlsafe(32)`. Only the SHA-256 hex digest is stored in `admin_password_reset_tokens` — raw tokens are never persisted.
- One active token per user is enforced structurally by a `UNIQUE (user_id)` constraint and an upsert (ON CONFLICT DO UPDATE). Generating a new token atomically replaces any existing pending token for the same user.
- Token expiry is 1 hour. Expiry is checked in the service layer, not in SQL.
- Token URLs use the `#reset:{token}` URL fragment. Fragments are never sent to the server and do not appear in server access logs.

**Password lockout:**
Three consecutive wrong passwords lock the account for 15 minutes (`password_locked_until` on `admin_users`). The lockout timestamp is set atomically with the third failed attempt in a single UPDATE. `reset_password_attempts` is called on successful password verification to clear the counter. `set_password` also resets the counter atomically.

**Session behaviour:**
- Sessions use a sliding 60-minute TTL (`SESSION_TTL_MINUTES = 60` in `admin_context.py`), not a fixed absolute expiry. Every successful `require_admin` validation extends `expires_at` by another 60 minutes (`AuthRepository.update_session_expiry`, DB-clock arithmetic via `make_interval`) and re-issues the session cookie with the same attributes as login (`httponly=True, secure=True, samesite="strict"`, `max_age=SESSION_COOKIE_MAX_AGE`). An actively-used session therefore never lapses; only 60+ minutes of inactivity expires it. The refresh is best-effort — wrapped in try/except and logged on failure, since a dead DB would already have failed the validation step. There is still no absolute session cap: an actively-used session can remain valid indefinitely.
- Single-session enforcement: `AuthRepository.create_session` deletes all existing sessions for the user before inserting the new one, in a single transaction.
- `require_admin` reads the session cookie, calls `auth_repo.get_session_context(session_id)`, and raises HTTP 401 if the cookie is absent, not found, or expired. The expiry check is done in SQL (`expires_at > NOW()`) to avoid clock-skew.

**`admin_context.py` constraints:**
- `require_admin` is the **sole authentication boundary** for all admin endpoints. Every admin endpoint that requires auth declares `Depends(require_admin)`. Auth endpoints are deliberately unauthenticated.
- **This module must never import any project module other than `app.core.db`.** Only stdlib, FastAPI, and psycopg2. The `AuthProvider` Protocol in this module documents the subset of `AuthRepository` used here without importing it directly.

**`AdminContext` fields:** `practice_id`, `user_id`, `role`, `actor_email`, and `session_id` are all populated by `require_admin` from the session record. All fields are always present.

**Timing attack mitigation:**
Both `verify_mfa_code` and `verify_login_credentials` in `auth_service.py` use `_fixed_delay()` to ensure every attempt takes at least 300ms regardless of outcome.

`verify_login_credentials` uses a specific pattern to prevent CPU-timing leaks from bcrypt: all fast checks (user lookup, cooldown, lockout, no-password guard) are evaluated first and recorded in a boolean flag. A single `bcrypt.checkpw()` call is then executed unconditionally — against the real hash on the happy path, or against a static module-level dummy hash (`_DUMMY_HASH`) on all failure paths. `_fixed_delay(start)` is called immediately after bcrypt, before any branching on the result. This ensures bcrypt's CPU cost is always incurred within the minimum response window regardless of which path was taken.

**Domain validation:**
`ALLOWED_ADMIN_DOMAINS` is a comma-separated list of permitted email domains. Validation uses exact domain match — `endswith` is not used. The same domain check applies when adding a new admin user.

**Email normalisation:**
All email addresses are normalised to lowercase at the point of entry in routers and services. Stored emails are always lowercase.

**`last_login` field:**
`admin_users.last_login` is `NULL` until the user first completes OTP verification — the frontend displays `NULL` as "Pending". Set to `NOW()` atomically inside `AuthRepository.create_session`.

**`password_changed_at` field:**
Set to `NOW()` by `AuthRepository.set_password` whenever a new password is stored. Required for Cyber Essentials Plus compliance auditing. Never updated by any other method.

**Session expiry mid-session:**
If a session expires while an admin is mid-edit (60+ minutes of inactivity), the next API request returns 401. The frontend detects `AuthError` and shows `LoginView` in a modal overlay above the still-mounted `EditorView`, rather than tearing it down — unsaved signposting/availability edits, the active tab, and the selected condition all survive. On successful re-login the overlay is dismissed with no refetch or remount; the user re-clicks whatever action failed. An explicit "Log out and discard changes" escape hatch in the overlay, and the separate full-page logout button, both discard state as before.

**401 response contract (HTTP-first):**
HTTP `401 Unauthorized` is the primary contract for session expiry. `admin_context.py` raises `HTTPException(status_code=401)`. `main.py` reshapes any 401 into `{"error": {"code": "UNAUTHORIZED", "message": "..."}}`. `api.ts` throws `AuthError` on `res.status === 401`.

---

### Signposting (`admin_practice_router.py`, `practice_repository.py`)

- The admin `GET /admin/conditions` endpoint is a **raw administrative view** deliberately separate from the patient-facing `GET /conditions`.
- `GET /admin/conditions/{id}/signposting` returns `null` (not 404) when no signposting is configured.
- `PUT` with empty/whitespace content is treated as "clear" — the repository deletes the row.
- **Validation responsibility split:** The router validates HTTP input. The repository acts as a backstop only.
- `condition_id` is validated against the registry before any database operation. The registry is immutable after startup.
- HTML sanitisation of signposting content is performed by `practice_repository.py` via `nh3`. The router does not sanitise; it delegates entirely.

---

### Availability (`admin_availability_router.py`, `availability_service.py`, `availability_repository.py`)

- `GET /admin/availability` returns the raw config. It does **not** call `evaluate_availability`.
- Setting `is_active = false` auto-clears any existing override.
- Availability and exception validation is delegated to the service layer.
- Override expiry must be timezone-aware.

---

### Audit Trail (`admin_audit_router.py`, `audit_repository.py`, `http_utils.py`)

Every mutating admin action and all authentication events are recorded in the `admin_audit_log` table. The audit log is append-only and has no foreign keys.

**What is recorded:**
- Auth events: `auth.login.step1_succeeded`, `auth.login.step1_failed`, `auth.login.succeeded`, `auth.login.failed`, `auth.logout`
- User management events: `auth.user_added`, `auth.user_deleted`, `auth.invitation_resent`
- Mutating admin endpoints: practice email, signposting, doctor list, availability config, override, per-date exceptions

`POST /admin/auth/request-reset` and `POST /admin/auth/set-password` are not audited. Recording outcomes for these endpoints would reveal whether a given email is registered (`request-reset`) or confirm token validity (`set-password`), which would undermine their anti-enumeration design.

**Transaction pattern for mutating endpoints:**
Each mutating endpoint wraps the repository mutation and `audit_repo.log_event` in a single shared `get_conn` transaction. Auth events (no paired mutation) use standalone inserts (`conn=None`).

**IP address extraction** is centralised in `app/utils/http_utils.py` (`extract_ip`).

**Read endpoint:** `GET /admin/audit-log` accepts `cursor`, `from_date`, `to_date`, `actor`, `action` (prefix match), `limit` (default 50, max 200). Pagination uses an opaque base64 cursor.

---

### User Management (`admin_user_router.py`, `user_service.py`, `auth_repository.py`, `practice_repository.py`)

Admin users are managed per-practice. Each practice is an isolated tenant.

**Endpoints:**
- `GET /admin/users` — plain read, no lock. Returns all users ordered by `created_at` ascending. Each row includes `is_current_user: bool`.
- `POST /admin/users` — add a new admin user. Rate-limited to 10/minute.
- `DELETE /admin/users/{id}` — delete an admin user.
- `POST /admin/users/{id}/resend-invitation` — regenerate a setup token and resend the invitation email. Rate-limited to 10/minute.

**Service layer (`user_service.py`):**
`add_user`: normalise email → validate format → validate domain → acquire practice lock → insert user → catch `UniqueViolation` and raise `USER_ALREADY_EXISTS`.

`remove_user`: reject self-deletion → acquire practice lock → read all users inside the same transaction → verify target exists → reject if only one user remains → delete user. Postgres cascades the delete to `admin_sessions` and `admin_password_reset_tokens` via `ON DELETE CASCADE`.

`resend_invitation`: look up user by id and practice, return email. No writes.

**Transaction boundary for `POST /admin/users`:**
The user insert, reset token upsert (`auth_service.generate_reset_token(..., conn=conn)`), and audit log write all share a single `get_conn` transaction. If any step fails, all roll back. This guarantees no orphaned token exists for a user whose insert was rolled back. Email delivery is outside the transaction — a delivery failure does not roll back the user insert.

The user's id is looked up within the same transaction (via a direct cursor query on the shared `conn`) immediately after insert, since `insert_user` does not return the id and `get_user_by_email` opens its own connection.

**Token generation for `resend-invitation`:**
`generate_reset_token` opens its own connection (upsert is idempotent — no larger transaction needed). The fresh token replaces any existing pending token via the `UNIQUE (user_id)` constraint.

**Invitation email:**
`send_admin_invitation(email, token)` sends a plain-text email containing the setup URL `{ADMIN_URL}#reset:{token}`. The token is in the URL fragment, which is never sent to the server and does not appear in server logs. Token expiry is 1 hour.

---

### Admin Frontend (`frontend/admin-ui/src/`)

The admin UI is a Vite + React app (TypeScript).

**Component structure:**
- `App.tsx` — root. On mount, checks `window.location.hash` before probing the session. If the hash matches `#reset:{token}`, bypasses the session probe and sets state to `set_password`. Otherwise, probes by calling `GET /admin/conditions`. Auth states: `"checking" | "login" | "editor" | "set_password"`, plus a separate `sessionExpired` boolean that overlays `LoginView` on top of a still-mounted `EditorView` on mid-session `AuthError`, instead of transitioning `authState` away from `"editor"`.
- `LoginView.tsx` — two-step 2FA login. Step 1 ("login" state): email and password inputs; calls `POST /admin/auth/login`. Step 2 ("code" state): 6-digit OTP input; calls `POST /admin/auth/verify`. Also renders a "Forgot / Set up password?" button that calls `POST /admin/auth/request-reset` and shows a generic confirmation message regardless of outcome. On OTP success, calls `onSuccess()`.
- `SetPasswordView.tsx` — rendered when `authState === "set_password"`. On mount: extracts the raw token from the URL hash and calls `history.replaceState` to clear it — this happens unconditionally (success, error, or no token) to prevent the token from persisting in browser history. Renders a password input with a real-time zxcvbn strength meter (4 colour-coded segments, score labels, actionable suggestions) and a confirm-password input. Submit is disabled until: length >= 12, zxcvbn score >= 3, and passwords match. On success, transitions to login via `onComplete()`. On `INVALID_RESET_TOKEN`, shows an expired-link message.
- `EditorView.tsx` — five-tab container (Signposting, Availability, Practice settings, Audit log, Manage users).
- All other components unchanged.

**URL hash routing:**
The `#reset:{token}` pattern is detected by `App.tsx` on mount using `/^#reset:/.test(window.location.hash)`. The hash check runs before the session probe to avoid an unnecessary authenticated API call. `SetPasswordView` clears the hash on its own mount via `history.replaceState(null, "", location.pathname)`.

**zxcvbn integration:**
`@zxcvbn-ts/core` with `@zxcvbn-ts/language-en` and `@zxcvbn-ts/language-common`. Options are initialised once at module load in `SetPasswordView.tsx`. Strength evaluation runs on every keystroke in the component (no debounce needed — zxcvbn is CPU-bound but fast for typical password lengths). The same minimum score threshold (3) is enforced on both frontend and backend.

**Key boundaries:**
- No token is held in React state or any browser storage. Authentication is entirely cookie-based.
- `api.ts` adds `X-Requested-With: XMLHttpRequest` and `credentials: "same-origin"` to every request.
- `AuthError` is thrown by `apiFetch` on any 401. Child components catch it and call `onAuthError()`.
- `requestPasswordReset` in `api.ts` always resolves without throwing — the server always returns 200. Network errors are silently swallowed at the API layer.
- The frontend makes requests to `/admin/*` endpoints only.
- The frontend contains no clinical logic.

**Types and API functions:** See `frontend/admin-ui/src/types.ts` and `frontend/admin-ui/src/api.ts` directly.

---

## What Admin Must Never Do

- `admin_context.py`: import any project module other than `app.core.db`
- Any admin sub-router: import clinical engine modules, `presentation_service`, `serialisation`, `projection`, or `runtime_state`
- `auth_service.py`: access the database directly — all DB access goes through `AuthRepository`
- `auth_repository.py`: contain business logic (cooldown checks, code generation, hashing, lockout decisions)
- `user_service.py`: touch the database directly; handle email delivery (belongs in the router)
- `admin_delivery_service.py`: check cooldowns or access any repository — it is a pure transport layer
- `practice_repository.py`: access clinical data, perform composition logic, or handle authentication
- `audit_repository.py`: contain business logic or validation; import from service modules or routers; be called from the patient-facing request path
- `http_utils.py`: import any application module — stdlib only
- `email_utils.py`: import any application module — stdlib only; perform domain allowlist checks (that belongs in `auth_service.py`)
- Admin frontend: store session data in `localStorage` or `sessionStorage`; contain clinical logic; call non-`/admin/*` endpoints; bypass `onAuthError` on 401; render HTML content from `detail` fields; store raw reset tokens in state beyond the immediate submission
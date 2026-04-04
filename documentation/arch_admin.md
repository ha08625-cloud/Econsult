# Admin Portal & Configuration

**LLM INSTRUCTIONS:** This document covers design decisions and strict boundaries for the admin domain. Read the actual source files for function signatures, field names, and endpoint details.

---

## Scope

Admin authentication, editing per-condition signposting, configuring availability (schedule, overrides, per-date exceptions), managing practice email and doctor list, and the admin-portal frontend.

**Key files:** `admin_router.py`, `admin_context.py`, `app/services/auth_service.py`, `app/repositories/auth_repository.py`, `app/services/delivery/admin_delivery_service.py`, `practice_repository.py`, `availability_repository.py`, `availability_service.py`, `frontend/admin-ui/src/*`

---

## Design Decisions & Invariants

### Authentication (`admin_context.py`, `auth_service.py`, `auth_repository.py`)

Authentication is email-based MFA using time-limited one-time codes and HttpOnly session cookies.

**MFA flow:**
1. `POST /admin/auth/request-code` — validates email domain, looks up the user, checks the 60-second rate-limit cooldown, generates a 6-digit cryptographic code, hashes it with bcrypt, upserts it to `admin_auth_codes`, and sends it via `AdminDeliveryService`. If the email is not registered, returns 200 silently to prevent user enumeration.
2. `POST /admin/auth/verify` — runs the verification pipeline: user lookup, code record lookup, lockout check (3 attempts), expiry check (10 minutes), bcrypt comparison. On success: deletes the code, creates a session, sets an HttpOnly session cookie (`session_id`). All failure paths raise `INVALID_AUTH_CODE` (HTTP 422) regardless of which gate failed — a single generic error deliberately conceals which check failed.
3. `POST /admin/auth/logout` — deletes the session if a cookie is present, clears the cookie with `Max-Age=0`. No auth required — logout must succeed even for expired sessions.

**Session behaviour:**
- Session TTL is 24 hours (`SESSION_TTL_MINUTES = 60 * 24` in `admin_context.py`).
- Single-session enforcement: `AuthRepository.create_session` deletes all existing sessions for the user before inserting the new one, in a single transaction. This means a new login invalidates any existing session from another browser.
- `require_admin` reads the session cookie, calls `auth_repo.get_session_context(session_id)`, and raises HTTP 401 if the session is absent, not found, or expired. The expiry check is done in SQL (`expires_at > NOW()`) to avoid clock-skew.

**DEV_MODE bearer-token fallback:**
- When `DEV_MODE=1` and no session cookie is present, `require_admin` falls back to the original bearer-token path for backward compatibility. This keeps existing admin endpoint tests passing during the transition.
- If `ADMIN_TOKEN` is set in production alongside MFA, a startup warning is logged (both auth methods active). `ADMIN_TOKEN` is no longer required in production — MFA replaces it.
- The bearer fallback will be removed in a future cleanup pass once MFA is fully deployed.

**`admin_context.py` constraints:**
- `require_admin` is the **sole authentication boundary** for all admin endpoints. Every admin endpoint that requires auth declares `Depends(require_admin)`. The three auth endpoints (`request-code`, `verify`, `logout`) are deliberately unauthenticated.
- `auth_method` is a plain string (`"session_cookie"` | `"bearer_token"` | `"dev_any"`), not an enum.
- **This module must never import any project module other than `app.core.db`.** Only stdlib, FastAPI, and psycopg2. The `AuthProvider` Protocol in this module documents the subset of `AuthRepository` used here without importing it directly.

**Timing attack mitigation:**
`verify_mfa_code` in `auth_service.py` uses `_fixed_delay()` to ensure every verification attempt takes at least 300ms regardless of outcome. This prevents an attacker from learning which gate failed from response time. Uses `time.sleep` (not `asyncio.sleep`) because all repository calls are synchronous psycopg2. Revisit with `run_in_executor` if concurrent load ever becomes a concern.

**Domain validation:**
`ALLOWED_ADMIN_DOMAINS` is a comma-separated list of permitted email domains (e.g. `nhs.net,gov.uk`). Validation uses exact domain match — `endswith` is not used. Email must have exactly one `@`. Set at startup and stored in `app.state.allowed_admin_domains`.

**Session expiry mid-session:**
If a session expires while an admin is mid-edit, the next mutating API request returns 401. The frontend detects `AuthError` and redirects to `LoginView`. Any unsaved data is lost. This is acceptable given the 24-hour TTL and infrequent use pattern. No re-auth modal is provided — complexity is not justified.

---

### Signposting (`admin_router.py`, `practice_repository.py`)

- The admin `GET /admin/conditions` endpoint is a **raw administrative view** deliberately separate from the patient-facing `GET /conditions`. A change to one cannot accidentally affect the other.
- `GET /admin/conditions/{id}/signposting` returns `null` (not 404) when no signposting is configured. Absence of signposting is a valid configured state, not an error.
- `PUT` with empty/whitespace content is treated as "clear" — the repository deletes the row. `DELETE` also deletes the row. Both are semantically distinct at the database level (preserves audit distinctions) but both return `null` to current consumers via the normalisation rule.
- **Validation responsibility split:** The router validates HTTP input (types, whitespace, empty strings, condition ID existence). The repository acts as a backstop only. The condition registry is authoritative for valid condition IDs; the repository has no knowledge of them.
- `condition_id` is validated against the registry before any database operation. The registry is immutable after startup — new condition JSON files require a server restart to be visible in admin endpoints. This is intentional.
- HTML sanitisation of signposting content is performed by `practice_repository.py` via `nh3`. The router does not sanitise; it delegates entirely.
- `practice_repository.py` must never: access clinical data (rulesets, RuntimeState, answers), perform composition logic (belongs in `presentation_service`), or handle authentication.

---

### Availability (`admin_router.py`, `availability_service.py`, `availability_repository.py`)

- `GET /admin/availability` returns the raw config. It does **not** call `evaluate_availability` — that is the patient-facing logic. Admin reads and writes raw config only.
- Setting `is_active = false` auto-clears any existing override. This is handled in the router before persisting.
- Availability and exception validation (equal times, override expiry window, exception type constraints) is delegated to the service layer, not the router.
- Override expiry must be timezone-aware. Timezone-naive `expires_at` is rejected with HTTP 400.

---

### Admin Frontend (`frontend/admin-ui/src/`)

The admin UI is a Vite + React app (TypeScript). It is **not** the no-build CDN/Babel frontend — see `frontend_admin-ui_index.html` for the entry point.

**Component structure:**
- `App.tsx` — root; probes session on mount by calling `GET /admin/conditions`; shows `LoginView` on 401, `EditorView` on success. No token state. Owns `conditions` state and `handleAuthError` callback.
- `LoginView.tsx` — two-step MFA login: step 1 email input calls `POST /admin/auth/request-code`; step 2 code input calls `POST /admin/auth/verify`. On success calls `onSuccess()` so App re-fetches conditions and transitions to `EditorView`.
- `EditorView.tsx` — condition selector + editor container; owns unsaved-change tracking via refs; passes `onAuthError` down to all children.
- `SignpostingEditor.tsx` — rich text editor for one condition; calls `onAuthError` on `AuthError`.
- `AvailabilityEditor.tsx` — schedule, override, and exceptions card; calls `onAuthError` on `AuthError`.
- `PracticeSettingsTab.tsx` — practice email and doctor list; calls `onAuthError` on `AuthError`.
- `TokenView.tsx` — **deleted**. Replaced by `LoginView.tsx`.

**Key boundaries:**
- No token is held in React state or any browser storage. Authentication is entirely cookie-based — the browser attaches the `session_id` HttpOnly cookie automatically.
- `api.ts` adds `X-Requested-With: XMLHttpRequest` and `credentials: "same-origin"` to every request. This satisfies the CSRF requirement given a strict same-origin CORS policy.
- `AuthError` is thrown by `apiFetch` on any 401 response. Child components catch it and call `onAuthError()`, which transitions App back to `LoginView`. Unsaved data is lost on session expiry — no modal, no retry queue.
- All fetch calls are wrapped in try/catch; network errors produce inline messages, not browser error dialogs.
- The frontend makes requests to `/admin/*` endpoints only.
- The frontend contains no clinical logic or safety rule evaluation.

**Unsaved change tracking:** `SignpostingEditor` and `AvailabilityEditor` report unsaved state to `EditorView` via `onUnsavedChange` callbacks. `EditorView` stores these in refs so `confirm()` dialogs can read them synchronously.

**Types and API functions:** See `frontend/admin-ui/src/types.ts` and `frontend/admin-ui/src/api.ts` directly.

---

## What Admin Must Never Do

- `admin_context.py`: import any project module other than `app.core.db`
- `admin_router.py`: import clinical engine modules, `presentation_service`, `serialisation`, `projection`, or `runtime_state`
- `auth_service.py`: access the database directly — all DB access goes through `AuthRepository`
- `auth_repository.py`: contain business logic (cooldown checks, code generation, hashing)
- `admin_delivery_service.py`: check cooldowns or access any repository — it is a pure transport layer
- `practice_repository.py`: access clinical data, perform composition logic, or handle authentication
- Admin frontend: store session data in `localStorage` or `sessionStorage`; contain clinical logic; call non-`/admin/*` endpoints; bypass `onAuthError` on 401
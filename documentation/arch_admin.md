# Admin Portal & Configuration

**LLM INSTRUCTIONS:** This document covers design decisions and strict boundaries for the admin domain. Read the actual source files for function signatures, field names, and endpoint details.

---

## Scope

Admin authentication, editing per-condition signposting, configuring availability (schedule, overrides, per-date exceptions), managing practice email and doctor list, and the admin-portal frontend.

**Key files:** `app/routers/admin_router.py` (orchestrator), `app/routers/admin/admin_auth_router.py`, `app/routers/admin/admin_practice_router.py`, `app/routers/admin/admin_availability_router.py`, `app/routers/admin/admin_audit_router.py`, `admin_context.py`, `app/services/auth_service.py`, `app/repositories/auth_repository.py`, `app/repositories/audit_repository.py`, `app/services/delivery/admin_delivery_service.py`, `practice_repository.py`, `availability_repository.py`, `availability_service.py`, `app/utils/http_utils.py`, `frontend/admin-ui/src/*`

---

## Design Decisions & Invariants

### Router Structure

The admin domain uses a thin orchestrator (`admin_router.py`) that registers four sub-routers from the `app/routers/admin/` package. Each sub-router owns a single domain boundary and mirrors its corresponding repository:

- `admin_auth_router.py` — MFA request, verify, logout (all unauthenticated)
- `admin_practice_router.py` — conditions list, practice settings, signposting, doctor list
- `admin_availability_router.py` — weekly config, manual overrides, per-date exceptions
- `admin_audit_router.py` — audit log read endpoint

The `require_admin` dependency is applied within each sub-router's route definitions, not in the orchestrator. Auth endpoints are deliberately excluded.

The domain boundary invariant from the original router is inherited by all sub-routers: **no sub-router may import clinical engine modules, `presentation_service`, `serialisation`, `projection`, or `runtime_state`.**

---

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

**401 response contract (HTTP-first):**
HTTP `401 Unauthorized` is the primary contract for session expiry. The JSON body is secondary. This separation exists because `admin_context.py` cannot import project modules, so no Python constant can be shared across that boundary. The design is:
- `admin_context.py` raises `HTTPException(status_code=401, detail="...")` with a plain human-readable detail string.
- `main.py` registers an `HTTPException` handler that reshapes any 401 into the standard envelope: `{"error": {"code": "UNAUTHORIZED", "message": "..."}}`. This is the single place the secondary contract is enforced.
- `api.ts` throws `AuthError` on `res.status === 401`. Callers catch `AuthError` to trigger a login redirect. The JSON body is not inspected for 401 responses.
- No `SESSION_EXPIRED` constant exists in `errors.py` — the HTTP status code makes it unnecessary.

---

### Signposting (`admin_practice_router.py`, `practice_repository.py`)

- The admin `GET /admin/conditions` endpoint is a **raw administrative view** deliberately separate from the patient-facing `GET /conditions`. A change to one cannot accidentally affect the other.
- `GET /admin/conditions/{id}/signposting` returns `null` (not 404) when no signposting is configured. Absence of signposting is a valid configured state, not an error.
- `PUT` with empty/whitespace content is treated as "clear" — the repository deletes the row. `DELETE` also deletes the row. Both are semantically distinct at the database level (preserves audit distinctions) but both return `null` to current consumers via the normalisation rule.
- **Validation responsibility split:** The router validates HTTP input (types, whitespace, empty strings, condition ID existence). The repository acts as a backstop only. The condition registry is authoritative for valid condition IDs; the repository has no knowledge of them.
- `condition_id` is validated against the registry before any database operation. The registry is immutable after startup — new condition JSON files require a server restart to be visible in admin endpoints. This is intentional.
- HTML sanitisation of signposting content is performed by `practice_repository.py` via `nh3`. The router does not sanitise; it delegates entirely.
- `practice_repository.py` must never: access clinical data (rulesets, RuntimeState, answers), perform composition logic (belongs in `presentation_service`), or handle authentication.

---

### Availability (`admin_availability_router.py`, `availability_service.py`, `availability_repository.py`)

- `GET /admin/availability` returns the raw config. It does **not** call `evaluate_availability` — that is the patient-facing logic. Admin reads and writes raw config only.
- Setting `is_active = false` auto-clears any existing override. This is handled in the router before persisting.
- Availability and exception validation (equal times, override expiry window, exception type constraints) is delegated to the service layer, not the router.
- Override expiry must be timezone-aware. Timezone-naive `expires_at` is rejected with HTTP 400.

---

### Audit Trail (`admin_audit_router.py`, `audit_repository.py`, `http_utils.py`)

Every mutating admin action and all authentication events are recorded in the `admin_audit_log` table (created by migration 0015). The audit log is append-only and has no foreign keys — it remains readable even if a user or practice record is later deleted.

**What is recorded:**
- Auth events: `auth.code_requested`, `auth.login.succeeded`, `auth.login.failed`, `auth.logout`
- Mutating admin endpoints: practice email, signposting (per condition), doctor list, availability config, override, and per-date exceptions

Each event records: `practice_id`, `actor_email`, `action`, `resource` (optional), `detail` (JSONB, action-specific shape), `ip_address`, `session_id`, `occurred_at`. The per-action `detail` shapes are documented in `audit_repository.py`.

**Transaction pattern for mutating endpoints:**
Each mutating endpoint reads the "before" state, then wraps both the repository mutation and the `audit_repo.log_event` call in a single shared `get_conn` transaction. If either operation fails, both roll back. The before state is read outside the transaction (clean read, no lock held). This pattern applies uniformly across all three mutating sub-routers.

**Auth events** (which have no paired mutation) use standalone inserts — `log_event` opens and commits its own connection when `conn=None`.

**IP address extraction** is centralised in `app/utils/http_utils.py` (`extract_ip`). It reads `X-Forwarded-For` first (taking the first value, the original client), then `X-Real-IP`, then `request.client.host`. This logic lives in one place only — not repeated at each call site.

**`AdminContext` fields:** `actor_email` and `session_id` are populated by `require_admin` from the session record. For the DEV_MODE bearer fallback, `session_id` is `None` and `actor_email` is `"dev@local"`.

**Read endpoint:** `GET /admin/audit-log` accepts query parameters `cursor`, `from_date`, `to_date`, `actor`, `action` (prefix match), `limit` (default 50, max 200). Pagination uses an opaque base64 cursor encoding `last_id` and `last_occurred_at`. The cursor and filters are independent — discarding the cursor and re-querying when a filter changes is correct behaviour.

**`AuditRepository` design decisions:**
- `list_events` fetches `limit + 1` rows to detect whether a next page exists, avoiding a separate `COUNT(*)` query.
- The `action_prefix` parameter is validated against `^[a-z0-9_.]+$` before building the `LIKE` clause — this prevents wildcard injection.
- Date boundaries are converted to midnight-start and end-of-day datetimes in Python before being passed to the query, making the boundary logic explicit and testable.
- Cursor decoding raises `ValueError` on malformed input; the endpoint converts this to HTTP 400.

---

### Admin Frontend (`frontend/admin-ui/src/`)

The admin UI is a Vite + React app (TypeScript). It is **not** the no-build CDN/Babel frontend — see `frontend_admin-ui_index.html` for the entry point.

**Component structure:**
- `App.tsx` — root; probes session on mount by calling `GET /admin/conditions`; shows `LoginView` on 401, `EditorView` on success. No token state. Owns `conditions` state and `handleAuthError` callback.
- `LoginView.tsx` — two-step MFA login: step 1 email input calls `POST /admin/auth/request-code`; step 2 code input calls `POST /admin/auth/verify`. On success calls `onSuccess()` so App re-fetches conditions and transitions to `EditorView`.
- `EditorView.tsx` — four-tab container (Signposting, Availability, Practice settings, Audit log); owns unsaved-change tracking via refs; passes `onAuthError` down to all children. `AvailabilityEditor` is always mounted (display:none when inactive) to preserve state. All other tabs are conditionally rendered and perform a fresh fetch on mount.
- `SignpostingEditor.tsx` — rich text editor for one condition; calls `onAuthError` on `AuthError`.
- `AvailabilityEditor.tsx` — schedule, override, and exceptions card; calls `onAuthError` on `AuthError`.
- `PracticeSettingsTab.tsx` — practice email and doctor list; calls `onAuthError` on `AuthError`.
- `AuditLogTab.tsx` — read-only audit event viewer. Filter inputs (date range, actor, action prefix) with 400 ms debounce on text fields. Paginated table with "Load more" cursor-based pagination. Each row has a collapsible detail cell showing a structured diff: changed keys side-by-side for object before/after, labelled blocks for string/list/single-side values, key-value pairs for flat auth events. Values rendered as plain text — HTML is never rendered.
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
- Any admin sub-router: import clinical engine modules, `presentation_service`, `serialisation`, `projection`, or `runtime_state`
- `auth_service.py`: access the database directly — all DB access goes through `AuthRepository`
- `auth_repository.py`: contain business logic (cooldown checks, code generation, hashing)
- `admin_delivery_service.py`: check cooldowns or access any repository — it is a pure transport layer
- `practice_repository.py`: access clinical data, perform composition logic, or handle authentication
- `audit_repository.py`: contain business logic or validation; import from service modules or routers; be called from the patient-facing request path
- `http_utils.py`: import any application module — stdlib only
- Admin frontend: store session data in `localStorage` or `sessionStorage`; contain clinical logic; call non-`/admin/*` endpoints; bypass `onAuthError` on 401; render HTML content from `detail` fields

# Admin Portal & Configuration

**LLM INSTRUCTIONS:** This document covers design decisions and strict boundaries for the admin domain. Read the actual source files for function signatures, field names, and endpoint details.

---

## Scope

Admin authentication, editing per-condition signposting, configuring availability (schedule, overrides, per-date exceptions), and the admin-portal frontend.

**Key files:** `admin_router.py`, `admin_context.py`, `practice_repository.py`, `availability_repository.py`, `availability_service.py`, `frontend/admin-ui/src/*`

---

## Design Decisions & Invariants

### Authentication (`admin_context.py`)

- The `require_admin` FastAPI dependency is the **sole authentication boundary** for all admin endpoints. Every admin endpoint declares `Depends(require_admin)`.
- The Authorization header is **always required**, even in DEV_MODE. This keeps the auth code path live in development so a broken check cannot be shipped silently.
- `auth_method` is a plain string (`"bearer_token"` | `"dev_any"`), not an enum. This allows Phase 1B (session-based MFA) to introduce new values without modifying the dataclass.
- **This module must never import any project module** — only stdlib and FastAPI. It is designed to be replaced in its entirety in Phase 1B without touching anything else.

### Signposting (`admin_router.py`, `practice_repository.py`)

- The admin `GET /admin/conditions` endpoint is a **raw administrative view** deliberately separate from the patient-facing `GET /conditions`. A change to one cannot accidentally affect the other.
- `GET /admin/conditions/{id}/signposting` returns `null` (not 404) when no signposting is configured. Absence of signposting is a valid configured state, not an error.
- `PUT` with empty/whitespace content is treated as "clear" — the repository deletes the row. `DELETE` also deletes the row. Both are semantically distinct at the database level (preserves audit distinctions) but both return `null` to current consumers via the normalisation rule.
- **Validation responsibility split:** The router validates HTTP input (types, whitespace, empty strings, condition ID existence). The repository acts as a backstop only. The condition registry is authoritative for valid condition IDs; the repository has no knowledge of them.
- `condition_id` is validated against the registry before any database operation. The registry is immutable after startup — new condition JSON files require a server restart to be visible in admin endpoints. This is intentional.
- HTML sanitisation of signposting content is performed by `practice_repository.py` via `nh3`. The router does not sanitise; it delegates entirely.
- `practice_repository.py` must never: access clinical data (rulesets, RuntimeState, answers), perform composition logic (belongs in `presentation_service`), or handle authentication.

### Availability (`admin_router.py`, `availability_service.py`, `availability_repository.py`)

- `GET /admin/availability` returns the raw config. It does **not** call `evaluate_availability` — that is the patient-facing logic. Admin reads and writes raw config only.
- Setting `is_active = false` auto-clears any existing override. This is handled in the router before persisting.
- Availability and exception validation (equal times, override expiry window, exception type constraints) is delegated to the service layer, not the router.
- Override expiry must be timezone-aware. Timezone-naive `expires_at` is rejected with HTTP 400.

### Admin Frontend (`frontend/admin-ui/src/`)

The admin UI is a Vite + React app (TypeScript). It is **not** the no-build CDN/Babel frontend — see `frontend_admin-ui_index.html` for the entry point.

**Component structure:**
- `App.tsx` — root; owns `token` and `conditions` state; gates on `TokenView` vs `EditorView`
- `TokenView.tsx` — token entry; calls `GET /admin/conditions` as auth check; valid token stored in React state only
- `EditorView.tsx` — condition selector + editor container; owns unsaved-change tracking via a `ref` (not state, so it's readable synchronously inside `confirm()` without re-renders)
- `SignpostingEditor.tsx` — full list editor for one condition (load, add, delete, reorder, save)
- `AvailabilityEditor.tsx` — schedule, override, and exceptions card

**Key boundaries:**
- The admin token is **never written to `localStorage` or `sessionStorage`** — only React component state for the duration of the browser session.
- All fetch calls are wrapped in try/catch; network errors produce inline messages, not browser error dialogs.
- The frontend makes requests to `/admin/*` endpoints only.
- The frontend contains no clinical logic or safety rule evaluation.

**Unsaved change tracking:** `SignpostingEditor` reports unsaved state to `EditorView` via an `onUnsavedChange` callback. `EditorView` stores this in a `ref` so the condition-switch `confirm()` dialog can read it synchronously.

**Types and API functions:** See `frontend/admin-ui/src/types.ts` and `frontend/admin-ui/src/api.ts` directly.

---

## What Admin Must Never Do

- `admin_context.py`: import any project module
- `admin_router.py`: import clinical engine modules, `presentation_service`, `serialisation`, `projection`, or `runtime_state`
- `practice_repository.py`: access clinical data, perform composition logic, or handle authentication
- Admin frontend: store token in persistent browser storage; contain clinical logic; call non-`/admin/*` endpoints

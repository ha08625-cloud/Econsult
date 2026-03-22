# Admin Portal & Configuration

**LLM INSTRUCTIONS:** This document covers design decisions and strict boundaries for the admin domain. Read the actual source files for function signatures, field names, and endpoint details.

---

## Scope

Admin authentication, editing per-condition signposting, configuring availability (schedule, overrides, per-date exceptions), and the admin-portal frontend.

**Key files:** `admin_router.py`, `admin_context.py`, `practice_repository.py`, `availability_repository.py`, `availability_service.py`, `frontend/admin-ui/src/api.ts`, `frontend/admin-ui/src/types.ts`, `frontend/admin-ui/src/App.tsx`, `frontend/admin-ui/src/TokenView.tsx`, `frontend/admin-ui/src/EditorView.tsx`, `frontend/admin-ui/src/SignpostingEditor.tsx`, `frontend/admin-ui/src/AvailabilityEditor.tsx`

**Error constructors:** Admin-specific errors (`CONDITION_NOT_FOUND`, `INVALID_DATE_FORMAT`, `INVALID_FIELD_TYPE`) live in `errors.py` alongside the form engine errors.

---

## Design Decisions & Invariants

### Authentication (`admin_context.py`)

- The `require_admin` FastAPI dependency is the **sole authentication boundary** for all admin endpoints. Every admin endpoint declares `Depends(require_admin)`.
- The Authorization header is **always required**, even in DEV_MODE. This keeps the auth code path live in development so a broken check cannot be shipped silently.
- `auth_method` is a plain string (`"bearer_token"` | `"dev_any"`), not an enum. This allows Phase 1B (session-based MFA) to introduce new values without modifying the dataclass.
- **This module must never import any project module** — only stdlib and FastAPI. It is designed to be replaced in its entirety in Phase 1B without touching anything else.
- `require_admin` raises `HTTPException(401)` directly. This is the **only** place in the admin domain that raises `HTTPException`. All other error paths in `admin_router.py` use `APIError` constructors from `errors.py`.

### Dependency Injection (`admin_router.py`)

- `registry`, `practice_repo`, and `availability_repo` are accessed via three module-level dependency provider functions (`get_registry`, `get_practice_repo`, `get_availability_repo`) and injected with `Depends`. Handler bodies contain no `request.app.state.*` calls.
- Handlers that do not parse a request body do not declare `request: Request` in their signature at all.

### Error Handling (`admin_router.py`, `errors.py`)

- All errors in `admin_router.py` use named `APIError` constructors — never `HTTPException`. These are translated to HTTP 422 by the `api_error_handler` registered in `main.py`.
- Three admin-specific constructors exist in `errors.py`: `CONDITION_NOT_FOUND(cid)`, `INVALID_DATE_FORMAT(field, value)`, `INVALID_FIELD_TYPE(field, expected)`. Generic payload errors use the existing `INVALID_PAYLOAD(msg)`.
- The admin frontend reads both error shapes: `body.detail` (legacy HTTPException format) and `body.error.message` (APIError format). See `extractErrorDetail` in `frontend/admin-ui/src/api.ts`.
- The 404 vs 422 semantic distinction for missing condition IDs is a known trade-off. The current `APIError` handler always returns 422. The admin frontend does not branch on HTTP status codes.

### Signposting (`admin_router.py`, `practice_repository.py`)

- The admin `GET /admin/conditions` endpoint is a **raw administrative view** deliberately separate from the patient-facing `GET /conditions`. A change to one cannot accidentally affect the other.
- `GET /admin/conditions/{id}/signposting` returns `null` (not an error) when no signposting is configured. Absence of signposting is a valid configured state.
- `PUT` with empty/whitespace content is treated as "clear" — the repository deletes the row. `DELETE` also deletes the row. Both return `null` to current consumers via the normalisation helper.
- **Validation responsibility split:** The router validates HTTP input (types, whitespace, empty strings, condition ID existence). The repository acts as a backstop only. The condition registry is authoritative for valid condition IDs; the repository has no knowledge of them.
- `condition_id` is validated against the registry before any database operation. The registry is immutable after startup — new condition JSON files require a server restart.
- HTML sanitisation of signposting content is performed by `practice_repository.py` via `nh3`. The router does not sanitise.
- `practice_repository.py` must never: access clinical data, perform composition logic, or handle authentication.

### Availability (`admin_router.py`, `availability_service.py`, `availability_repository.py`)

- `GET /admin/availability` returns the raw config. It does **not** call `evaluate_availability` — that is the patient-facing logic.
- Setting `is_active = false` auto-clears any existing override. This is handled in the router before persisting.
- Availability and exception validation (equal times, override expiry window, exception type constraints) is delegated to the service layer, not the router.
- Override expiry must be timezone-aware. Timezone-naive `expires_at` is rejected.

### Admin Frontend (`frontend/admin-ui/src/`)

The admin UI is a Vite + React app (TypeScript). It is **not** the no-build CDN/Babel frontend — see `frontend_admin-ui_index.html` for the entry point.

**Component structure:**
- `App.tsx` — root; owns `token` and `conditions` state; gates on `TokenView` vs `EditorView`
- `TokenView.tsx` — token entry; calls `GET /admin/conditions` as auth check; valid token stored in React state only
- EditorView.tsx — three-tab layout (Signposting, Availability, Practice settings); owns unsaved-change tracking via two refs. AvailabilityEditor is always mounted and shown/hidden via display:none to preserve state. Signposting content and Practice settings are conditionally rendered.
- `SignpostingEditor.tsx` — full list editor for one condition (load, add, delete, reorder, save)
- AvailabilityEditor.tsx — schedule, override, and exceptions card; accepts optional onUnsavedChange prop to report dirty state to EditorView

**Key boundaries:**
- The admin token is **never written to `localStorage` or `sessionStorage`** — only React component state for the duration of the browser session.
- All fetch calls go through `apiFetch` and error handling goes through `extractErrorDetail` in `api.ts`. Components do not call `fetch` directly.
- The frontend makes requests to `/admin/*` endpoints only.
- The frontend contains no clinical logic or safety rule evaluation.

**Unsaved change tracking:** Both SignpostingEditor and AvailabilityEditor report unsaved state to EditorView via onUnsavedChange callbacks. EditorView stores these in signpostingUnsavedRef and availabilityUnsavedRef. Both refs are reset explicitly on confirm — availabilityUnsavedRef in particular must be reset manually because AvailabilityEditor stays mounted and will not re-fetch after a discarded tab switch.

---

## What Admin Must Never Do

- `admin_context.py`: import any project module
- `admin_router.py`: import clinical engine modules, `presentation_service`, `serialisation`, `projection`, or `runtime_state`; access `request.app.state` outside the three dependency provider functions; raise `HTTPException`
- `practice_repository.py`: access clinical data, perform composition logic, or handle authentication
- Admin frontend: store token in persistent browser storage; contain clinical logic; call non-`/admin/*` endpoints

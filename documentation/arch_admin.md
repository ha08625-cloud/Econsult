### Admin Portal & Configuration
* **Scope:** Admin authentication, editing signposting, configuring availability (schedule, overrides, per-date exceptions) and frontend for the Admin portal
* **Key Files:** `admin_router.py`, `admin_context.py`, `practice_repository.py`, `availability_repository.py`, `availability_service.py`, `frontend/admin-ui/src/*`

### practice_repository.py — Practice database access

Responsibilities:
- Initialise practices and practice_signposting tables on startup
- CRUD operations for practices (practice_id, name, email)
- CRUD operations for practice-specific signposting per condition
- Email format validation
- HTML sanitisation for signposting content via nh3

Public interface:
- create_practice(practice_id, name, email) → None
- get_practice(practice_id) → dict | None
- get_email(practice_id) → str (raises PracticeNotFound if absent)
- practice_exists(practice_id) → bool
- count_practices() → int
- get_signposting(practice_id, condition_id) → str | None
- set_signposting(practice_id, condition_id, html) → None
- sanitise_signposting_html(raw) → str | None  (module-level function)
- delete_signposting(practice_id, condition_id) → None

Email validation rules:
- Must be a string
- Must not have leading or trailing whitespace
- Must contain exactly one '@' with non-empty parts either side

This module must never:
- Access clinical data (rulesets, RuntimeState, answers)
- Perform composition logic (that belongs in presentation_service)
- Handle authentication (Phase 1B)

### Admin portal — AvailabilityEditor.tsx
Location: frontend/admin-ui/src/AvailabilityEditor.tsx
A self-contained React component rendered as a card above the signposting
editor in EditorView.tsx. Contains three panels: schedule configuration,
temporary override, and per-date exceptions. All three panels are only
visible when is_active is true.

Fetches GET /admin/availability on mount. Displays:

Enable/disable checkbox (is_active). When unchecked, schedule fields
are hidden and a description reads "The form is available at all times."
When active: day toggle buttons (Mon–Sun), open/close time inputs
(HTML type="time"), closed message textarea.
Save button calling PUT /admin/availability.

Empty-days confirmation:
If is_active is true and no days are selected when Save is clicked, a
window.confirm dialog is shown: "No days are selected. Saving this
configuration will close the form to patients on every day of the week.
Are you sure?" The admin must confirm before the request is sent.
Validation errors from the API are displayed inline via the SaveStatus
pattern used by SignpostingEditor.
After a successful save, form state is synced to the server's response
to ensure the UI reflects exactly what was stored.

Override panel (Stage 3):
Displayed below the Save button when is_active is true. Shows the
current override status if active. Provides Force open / Force closed
buttons that open an inline form with expiry datetime picker and optional
message. Clear override button removes the override. Override active
check uses UTC comparison (Date.now() is UTC-safe). Override expiry
display uses Europe/London formatting via Intl.DateTimeFormat.

Exceptions panel (Stage 4):
Displayed below the override panel when is_active is true. Fetches
GET /admin/availability/exceptions when is_active becomes true.
Displays a list of upcoming exceptions ordered by date ascending.
Each row shows: formatted date (e.g. "Mon 14 Jul 2025"), type
(Closed / custom hours time range), optional note, and a Delete button.
"Add exception" button opens an inline form with: date picker (min =
today), type dropdown (Closed all day / Custom hours), conditional
open/close time inputs for custom hours, optional note field, and
Save/Cancel buttons. The form calls PUT /admin/availability/exceptions/{date}.
After a successful save or delete, the exceptions list is refreshed.
Delete calls DELETE /admin/availability/exceptions/{date} and is
idempotent. Delete errors are shown via alert() — simple and appropriate
for a rare action on an internal tool.

Admin api.ts functions:

fetchAvailability(token) → AvailabilityConfig
putAvailability(token, config) → AvailabilityConfig
postOverride(token, override) → AvailabilityConfig
deleteOverride(token) → AvailabilityConfig
fetchExceptions(token) → AvailabilityException[]
putException(token, date, exception) → AvailabilityException
deleteException(token, date) → void

Admin types.ts:

ConditionSummary interface (id, label)
SaveStatus type (type: "success" | "error", text)
AvailabilityConfig interface (practice_id, is_active, weekly_open_days,
open_time, close_time, closed_message, override_status,
override_expires_at, override_message)
AvailabilityException interface (exception_date, exception_type,
open_time, close_time, note)

EditorView.tsx changes:

Imports and renders AvailabilityEditor above the signposting card.
Component renders a fragment (<>) instead of a single card div to
accommodate both cards.

---

### admin_context.py — Admin authentication boundary
Responsibilities:
* Define the AdminContext frozen dataclass
* Provide the require_admin FastAPI dependency, which is the sole authentication boundary for all admin endpoints

AdminContext fields:

practice_id: str — resolved from request.app.state.practice_id
auth_method: str — "bearer_token" when validated against ADMIN_TOKEN; "dev_any" in DEV_MODE without a set token

Authentication rules:
* Authorization header is always required, even in DEV_MODE
* Missing or empty bearer value → 401
* If ADMIN_TOKEN is set: token must match exactly → 401 on mismatch
* If DEV_MODE=1 and ADMIN_TOKEN is not set: any non-empty bearer token is accepted
* If neither condition holds (production mode, no ADMIN_TOKEN): 401 always — fail closed

The reason the header is required even in DEV_MODE is that omitting it entirely would mean the auth code path is never exercised in development or tests. A broken auth check could be shipped without being noticed. Requiring a header but accepting any value keeps the code path live.
This module is designed to be replaced in its entirety in Phase 1B when session-based MFA is introduced. Nothing else changes when it is replaced. auth_method is a string rather than an enum so Phase 1B can introduce new values without modifying the dataclass.
This module must never import any project module. Only stdlib and FastAPI.

---

### admin_router.py — Admin API endpoints
Responsibilities:
* Provide all admin HTTP endpoints as a FastAPI APIRouter
* Validate condition_id against the condition registry before any database operation
* Validate and sanitise signposting input before calling the repository
* Normalise empty signposting lists to null in all responses
* Validate and persist availability configuration, overrides, and per-date exceptions

The router is registered in main.py with prefix /admin and tag admin. The prefix and tag are not defined in this module so that the router stays decoupled from its mount point.
All endpoints declare Depends(require_admin) and receive an AdminContext. Resources (registry, practice_repo, availability_repo) are read from request.app.state — never imported from main.py.

Signposting endpoints:
* GET /admin/conditions — returns all condition IDs and labels from the registry. This is a raw administrative view separate from the patient-facing GET /conditions, which composes full presentation data. Keeping them separate means a change to either cannot accidentally affect the other.
* GET /admin/conditions/{condition_id}/signposting — returns current signposting or null. Returns null (not 404) when no signposting is configured; absence of signposting is a valid configured state, not an error.
* PUT /admin/conditions/{condition_id}/signposting — sets signposting for a condition. Body must be {"signposting": "..."} where the value is a string. Empty or whitespace-only content is treated as an instruction to clear — the repository deletes the row and returns {"signposting": null}. Length is pre-checked against MAX_SIGNPOSTING_LENGTH before the repository call. InvalidSignpostingData from the repository is caught and converted to HTTP 400.
* DELETE /admin/conditions/{condition_id}/signposting — removes the database row entirely. Idempotent. Returns 204 no body. Semantically distinct from PUT []: the row is deleted rather than updated, which preserves the distinction at the database level and in any future audit log, even though GET normalises both to null for current consumers.

Availability endpoints:
* GET /admin/availability — returns the raw config dict with times formatted as HH:MM strings and override_expires_at as ISO string. Requires admin auth. Does not call evaluate_availability.
* PUT /admin/availability — accepts the schedule config, validates via the service layer, persists via the repository, and returns the updated config. If is_active is set to false, auto-clears any existing override. Logs a warning if is_active is true and weekly_open_days is empty. Returns HTTP 400 if validation fails.
* POST /admin/availability/override — sets a manual force-open or force-closed override. Validates via validate_override in the service layer. Rejects timezone-naive expires_at with HTTP 400. Returns the updated raw config.
* DELETE /admin/availability/override — clears any active override. Idempotent. Returns the updated raw config.

Exception endpoints (Stage 4):
* GET /admin/availability/exceptions — returns all exceptions on or after today's date (Europe/London time), ordered by date ascending. Includes today's exception if one exists.
* PUT /admin/availability/exceptions/{date} — creates or updates an exception for a specific date. Date is parsed from the URL path as YYYY-MM-DD. Body contains exception_type, open_time, close_time, and note. Validates via validate_exception in the service layer. Returns the stored exception with times formatted as HH:MM strings.
* DELETE /admin/availability/exceptions/{date} — deletes an exception for a specific date. Idempotent. Returns 204.

Response normalisation rule: None and empty/whitespace-only strings are both returned as null in all responses.

Validation responsibility split:
* The router is the primary validation layer for HTTP input (types, whitespace, empty strings)
* The repository's own validation acts as a backstop but the router validates first
* condition_id is validated against the registry in the router; the repository has no knowledge of valid condition IDs and does not raise on unknown ones
* Availability and exception validation (equal times, override expiry window, exception type constraints) is delegated to the service layer

Known limitation: the condition registry is immutable after startup. A new condition JSON file added to data/ while the server is running will return 404 from admin endpoints until the server is restarted. This is intentional.
This module must never import: clinical engine modules, presentation_service, serialisation, projection, runtime_state.

---

### frontend/admin-ui/src/index.html — Admin frontend

A single self-contained HTML file serving the practice admin UI.
No build step. React 18 and JSX loaded via CDN. Babel-standalone
performs in-browser JSX transpilation at load time.

Babel-standalone is approximately 800KB. This is acceptable for an
internal tool on a local network. It would not be acceptable for a
patient-facing or high-traffic interface.

Served at /admin-portal/ via StaticFiles mount in main.py.

Component structure:
- App: root component, owns token and conditions state, switches between views
- TokenView: token entry form, calls GET /admin/conditions as connectivity
  and auth check, stores valid token in React state (never localStorage)
- EditorView: condition dropdown and editor container, owns unsaved-change
  tracking via a ref updated by a callback prop from the editor
- SignpostingEditorWithRef: manages the full list editor for one condition —
  load, add, delete, reorder, per-item validation, save, status messages
- AvailabilityEditor: schedule, override, and exceptions management card

State ownership:
- token and conditions: App
- selectedConditionId: EditorView
- items, savedItems, isSaving, saveStatus, validationError: SignpostingEditorWithRef
- config, isActive, weeklyOpenDays, openTime, closeTime, closedMessage, override state, exceptions state: AvailabilityEditor

Unsaved change tracking:
SignpostingEditorWithRef reports its unsaved state to EditorView via an
onUnsavedChange callback prop. EditorView stores this in a ref (not state)
so the value is readable synchronously inside the confirm() dialog handler
without triggering a re-render. When the condition dropdown changes and
unsaved changes exist, window.confirm() is shown before the switch proceeds.

Key behaviours:
- Token entry calls GET /admin/conditions; 200 means valid, 401 shows error
- Condition switch with unsaved changes triggers a confirm() dialog
- Each item is validated as non-empty (after trim) before save is permitted
- Save always sends the full list via PUT (no partial update)
- Empty list save sends [] which the backend stores; subsequent GET returns null;
  UI shows an empty editor
- Try/catch on all fetch calls; network errors produce inline error messages,
  not browser error dialogs
- Saving spinner and "Saved" / "Save failed: ..." status messages inline

Authentication note:
The token field is a temporary placeholder. It will be replaced entirely in
Phase 5 when session-based MFA is introduced. The token is never written to
localStorage or any persistent browser storage — it exists only in React
component state for the duration of the browser session.

This module must never:
- Store the admin token in localStorage or sessionStorage
- Contain clinical logic or safety rule evaluation
- Make requests to any endpoint other than /admin/*

# Frontend (Patient UI)

**LLM INSTRUCTIONS:** This document covers design decisions and strict boundaries for the patient-facing frontend. Read the actual source files for component internals, prop signatures, type definitions, and function names. The frontend is a stateless renderer — all clinical intelligence lives on the server.

---

## Scope

Stateless React rendering of a six-screen patient form flow, condition search, and API communication.

**Key files:** `App.tsx`, `helpers.ts`, `layout.tsx`, `api.ts`, `types.ts`, `search.ts`, `ConditionCombobox.tsx`, `constants.ts`, `screens/DoneScreen.tsx`, `screens/SafetyWarningScreen.tsx`

**Screen components (frontend/src/screens/):** Individual screens extracted from `App.tsx` during Phase 2. See file_structure.md for the current list. Each screen component owns only its own UI state; session state lives in `App.tsx` and is passed down as props.

---

## Core Invariants

- **No clinical logic in the frontend.** No branching decisions, no safety evaluation, no encoder awareness. The UI renders what the server returns.
- **Patient input must never be destroyed by a recoverable error.** This is the most important frontend invariant. See Error Handling below.
- **No state round-trips.** Session state is never sent back to pre-session screens. Pre-session state is discarded after `/form/init` succeeds.
- **Availability fails open.** If `GET /availability` fails for any reason, the frontend must set `practiceIsOpen = true` and allow the patient to proceed. A fetch failure must never lock patients out.

---

## Screen Flow

Six screens in sequence: `SAFETY_WARNING` → `SELECT_CONDITION` → `FREE_TEXT` → `EDIT` → `REVIEW` → `CONTACT` → `DONE`.

- Screen 0 (`SAFETY_WARNING`) is a hard block. The Continue button must remain disabled until the patient acknowledges. It also fetches `GET /availability` in parallel — see Availability below.
- Screen 3 (`EDIT`) collects `additionalText` alongside question answers. This is included in the submission payload and shown on REVIEW only when non-empty.
- Screen 4 (`REVIEW`) transitions to Screen 5 on submit — it does not call the API.
- Screen 5 (`CONTACT`) calls `POST /form/finish` with the full `ContactPreferences` payload.

The `SAFETY_WARNING` screen still receives `universal_safety_warning` inside the `GET /conditions/{id}/presentation` payload for backend compatibility. **The frontend must ignore it and never display it on Screen 2.** This is an intentional API quirk — do not remove it.

---

## Error Handling (Enforced Architecture)

Two error states — the classification decision must be made at the API boundary, not in component logic:

- **`fatalError`:** Replaces the screen entirely. Use only for genuinely unrecoverable situations (e.g. the condition list fails to load, missing `runtime_id`).
- **`screenError`:** Displays an inline message and preserves user answers. Use for all recoverable failures — network errors, 5xx, 4xx on submission endpoints, 503 from `/form/init` (practice closed mid-session).

`screenError` must be cleared on every screen transition or when the patient resumes editing.

`ApiError` (defined in `api.ts`) must be thrown by all fetch wrappers. It carries the HTTP `status` (number) or `null` for network failures. Component logic must never hardcode error messages — it delegates to `friendlyErrorMessage(e)`. A 409 indicates a session version conflict (multiple tabs).

---

## Module Responsibilities

### `App.tsx`
Owns all screen state and transitions. The only file that knows the screen order. Contains no clinical logic. Renders the active screen component — there is no inline JSX for screens that have been extracted to `frontend/src/screens/`.

The reset function (triggered on fatal error) manually clears every `useState` in the file. It carries an explicit per-variable checklist comment directly above the reset block — if a new `useState` is added to `App.tsx`, it must also appear in that list. `presentationFetchTrigger` resets to `0`, not `null` — this is noted in the checklist comment.

`App.tsx` imports layout wrappers from `layout.tsx`, helper functions from `helpers.ts`, and screen components from `./screens/`. It must not redefine anything that belongs in those modules.

### Screen components (`frontend/src/screens/`)
Each extracted screen is a single default export. It receives session state as props from `App.tsx` and owns only its own UI state (e.g. `isSubmitting`, `screenError`, form-local preferences). Screen components must not call `setScreen` directly — they communicate outcomes to `App.tsx` via callbacks. See file_structure.md for the current list of extracted screens and their prop interfaces.

### `helpers.ts`
Pure functions with no React dependency: state initialisers and client-side validation. Nothing in this file should have side effects, make API calls, or import from any other local module except `types.ts`.

### `layout.tsx`
Structural React wrappers (`PageShell`, `InlineError`) with no knowledge of application state. References global CSS class names from `index.css` — that coupling is intentional. Must not import from `api.ts`, `helpers.ts`, or any screen component.

### `api.ts`
Typed fetch wrappers for all backend endpoints. No business logic, no data transformation beyond JSON serialisation. Payload field names must match backend expectations exactly. All type imports must use `import type` syntax (required by `verbatimModuleSyntax` in tsconfig).

### `types.ts`
TypeScript interfaces for all data the frontend receives or sends. These are projections of server-side state, not mirrors of it. Read this file directly for the current contract.

### `search.ts`
All condition filtering logic lives here and nowhere else. Three-layer matching: substring on label, substring on search tags, then Levenshtein fuzzy match on tag tokens. Fuzzy matching is disabled for queries under 4 characters to prevent false positives. `filterConditions` always filters from the full canonical list passed in — never incrementally from a previous result. Returns the full list as a fallback when nothing matches (never returns empty).

### `ConditionCombobox.tsx`
Self-contained combobox for condition selection. `filteredConditions` is a derived value computed on every render — never stored in state — which guarantees filtering is always from the canonical list. The 150ms blur delay on the input is intentional: `mousedown` on a suggestion fires `blur` before `click`, so without the delay the list closes before the selection registers.

### `constants.ts`
`GENERAL_CONSULTATION_ID` must match the `condition_id` in `general.json` exactly. If the general consultation ruleset is renamed, update this constant only — it must not be hardcoded elsewhere.

---

## Availability (Screen 0)

`GET /availability` is fetched in a separate `useEffect` on Screen 0, parallel to the safety warning fetch.

- Fail open: any failure (network, non-200) sets `practiceIsOpen = true`. No error is shown to the patient.
- If the practice is closed: a warning banner is shown above the safety text; the Continue button is disabled. The safety warning must remain visible even when closed — a patient arriving out of hours still needs emergency information.
- If `afterHoursNotice` is non-null and the practice is open: an informational notice is shown below the safety warning.
- If `POST /form/init` returns 503 (closed between availability check and submission), `friendlyErrorMessage` extracts the `detail` field from the response body and displays it as a `screenError` on Screen 2.

The safety warning fetch writes errors to a dedicated `safetyFetchError` state variable in `App.tsx`, not to `screenError`. The fetch state is passed to `SafetyWarningScreen` as a `SafetyWarningFetchState` discriminated union.

---

## Presentation Fetch (Screen 2)

`GET /conditions/{id}/presentation` is fetched via a `useEffect` in `App.tsx`. The result is held in a `PresentationState` discriminated union (defined in `types.ts`):

```typescript
type PresentationState =
  | { status: "loading" }
  | { status: "success"; data: ConditionPresentation }
  | { status: "error"; message: string }
```

There is no `idle` state. `presentationState` is only rendered inside the `FREE_TEXT` screen block, and both transitions into `FREE_TEXT` reset it to `loading` before navigating. If a future developer adds a third path to `FREE_TEXT`, they must do the same — failing to reset guarantees the patient will see stale data from a previous condition.

The `useEffect` depends on `[selectedConditionId, presentationFetchTrigger]`. `presentationFetchTrigger` is an integer counter in `App.tsx` whose only purpose is to signal "please re-fetch even though `selectedConditionId` has not changed." It is incremented at both navigation boundaries and by `retryPresentation`. This solves two problems that a dependency on `selectedConditionId` alone cannot handle:

- **Same-condition re-entry after error:** the patient selects condition A, advances, gets a fetch error, goes back, and clicks Continue again without changing their selection. `selectedConditionId` has not changed, so the effect would not re-fire without the trigger increment.
- **Retry:** the error screen offers a "Try again" button. Incrementing the trigger causes the effect to re-run; the retry does not call any fetch function directly.

The `useEffect` uses a `cancelled` boolean flag for cleanup. In development with React StrictMode, the effect fires twice on every `FREE_TEXT` entry — the flag ensures only the second result is used. Two network requests per entry in the browser dev tools during development is expected and not a bug.

The `FREE_TEXT` render block branches on `presentationState.status`:

- `"loading"` — spinner only
- `"error"` — error message with Back and Try again buttons; Back returns to `SELECT_CONDITION`, Try again calls `retryPresentation`
- `"success"` — the full presentation form; `presentation` is narrowed from `presentationState.data`

The `screenError` state variable is not used for presentation fetch errors. It remains in use on the `FREE_TEXT` success render for `initForm` submission errors only.

---

## Search Tags (Ruleset Schema)

`search_tags` is an optional field inside the `presentation` block of each ruleset JSON. It provides synonyms and colloquial terms for `search.ts` to match against.

Placed in `presentation` (not the clinical schema) because tags are presentation-layer metadata — keeping them out of the clinical schema prevents search concerns from polluting it.

Validated by `condition_registry.py` at startup — see that file for current limits (max count, max length per tag). Case-insensitive duplicates are silently de-duplicated with a logged warning.

Tags are the only synonym mechanism. There is no automatic or ML-based expansion. If a condition is renamed or new colloquial terms become common, the JSON must be updated manually.

---

## Development

Vite dev server on port 5173. Vite proxy forwards `/conditions` and `/form` requests to FastAPI on port 8000.

```
cd frontend && npm run dev   # in one terminal
uvicorn main:app --reload    # in another terminal
```

For production: `npm run build`, then the `dist/` output is served as `StaticFiles` in `main.py`.

---

## What the Frontend Must Never Do

- Contain clinical logic, safety rule evaluation, or encoder awareness
- Store admin tokens or session data in `localStorage` / `sessionStorage`
- Hardcode error messages in component logic (delegate to `friendlyErrorMessage`)
- Destroy patient input on a recoverable error
- Lock patients out due to an availability fetch failure

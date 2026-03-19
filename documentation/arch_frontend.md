# Frontend (Patient UI)

**LLM INSTRUCTIONS:** This document covers design decisions, enforced constraints, and non-obvious architectural choices for the patient-facing frontend. Read the actual source files for component internals, prop signatures, type definitions, and function names. The frontend is a stateless renderer — all clinical intelligence lives on the server.

---

## Scope

Stateless React rendering of a seven-screen patient form flow, condition search, and API communication.

**Key files:** `App.tsx`, `helpers.ts`, `layout.tsx`, `api.ts`, `types.ts`, `search.ts`, `ConditionCombobox.tsx`, `constants.ts`

**Screen components:** `frontend/src/screens/` — individual screens extracted from `App.tsx`. See `file_structure.md` for the current list. Each screen owns only its own UI state; session state lives in `App.tsx` and is passed down as props.

---

## Core Invariants

- **No clinical logic in the frontend.** No branching decisions, no safety evaluation, no encoder awareness. The UI renders what the server returns.
- **Patient input must never be destroyed by a recoverable error.** See Error Handling below.
- **No state round-trips.** Session state is never sent back to pre-session screens. Pre-session state is discarded after `/form/init` succeeds.
- **Availability fails open.** If `GET /availability` fails for any reason, the frontend must set `practiceIsOpen = true` and allow the patient to proceed. A fetch failure must never lock patients out.

---

## Screen Flow

Seven screens in sequence: `SAFETY_WARNING` → `SELECT_CONDITION` → `FREE_TEXT` → `EDIT` → `REVIEW` → `CONTACT` → `DONE`.

- Screen 0 (`SAFETY_WARNING`) is a hard block. Continue stays disabled until the patient acknowledges the safety warning. Availability is fetched in parallel — see Availability below.
- Screen 4 (`REVIEW`) transitions to Screen 5 without an API call.
- Screen 5 (`CONTACT`) calls `POST /form/finish`.

The `SAFETY_WARNING` screen receives `universal_safety_warning` inside the `GET /conditions/{id}/presentation` payload for backend compatibility. **The frontend must ignore this field and never display it on Screen 2.** This is an intentional API quirk — do not remove it.

---

## State Ownership

`App.tsx` owns all session state (`runtimeId`, `version`, `clientState`, `editableAnswers`, `safetyMessages`) and all screen transition logic. It is the only file that knows the screen order.

Screen components own only UI state internal to that screen (`isSubmitting`, `screenError`, `contactPreferences`, etc.). They must not call `setScreen` directly — they communicate outcomes to `App.tsx` via typed callbacks. `onContinue` callbacks on screens that make API calls receive the result as a parameter so `App.tsx` can update session state before navigating.

The reset function in `App.tsx` manually clears every `useState` in the file. A checklist comment directly above the reset block names every variable — if a new `useState` is added, it must appear in the list. This is the only mechanism enforcing completeness.

---

## Error Handling

Two error classifications — the decision is made at the API boundary, not in component logic:

- **`fatalError`:** Replaces the screen entirely. Use only for genuinely unrecoverable situations (missing `runtime_id`, condition list fails to load). Lives in `App.tsx`.
- **Screen-local error state:** Displays an inline message and preserves user answers. Use for all recoverable failures. Each screen component that makes API calls declares its own error state locally — it is not shared through `App.tsx`.

Screen-local error state clears automatically on navigation because extracted screen components mount fresh.

`ApiError` (defined in `api.ts`) is thrown by all fetch wrappers and carries the HTTP `status` or `null` for network failures. Component logic must never hardcode error messages — delegate to `friendlyErrorMessage(e)`. A 409 indicates a session version conflict (multiple tabs).

---

## Fetch State Pattern

Both the safety warning fetch (Screen 0) and the presentation fetch (Screen 2) use a discriminated union with `status: "loading" | "success" | "error"`. This pattern eliminates nullable cross-references in components. If either is changed, keep them consistent.

For Screen 0: `App.tsx` holds the raw fetch result as two separate state variables and derives the discriminated union inline before passing it to `SafetyWarningScreen` as a single prop. The type is exported from `SafetyWarningScreen.tsx`.

For Screen 2: `PresentationState` is defined in `types.ts`. There is no `idle` status — both transitions into `FREE_TEXT` reset it to `loading` before navigating. A third transition path added in future must do the same.

The `presentationFetchTrigger` counter in `App.tsx` exists solely to force a re-fetch when `selectedConditionId` has not changed (same-condition re-entry after error, or explicit retry). Incrementing it is the only correct way to trigger a retry — the retry callback must not call the fetch function directly.

---

## Availability (Screen 0)

`GET /availability` is fetched in a separate `useEffect` on Screen 0, parallel to the safety warning fetch. Fail open: any failure sets `practiceIsOpen = true` silently. If closed: warning banner shown, Continue disabled. The safety warning remains visible even when closed — patients arriving out of hours still need emergency information. If `POST /form/init` returns 503, `friendlyErrorMessage` extracts the `detail` field and displays it as a screen-local error.

---

## ConditionCombobox

The input `id` is generated dynamically via React's `useId()` hook — do not target it by a stable string in tests. Use label text or role queries instead.

`filteredConditions` is computed on every render from the full canonical list — never stored in state. The 150ms blur delay is intentional: `mousedown` on a suggestion fires before `click`, so without the delay the list closes before selection registers.

---

## Search Tags

`search_tags` lives in the `presentation` block of each ruleset JSON (not the clinical schema) because tags are presentation-layer metadata. See `search.ts` for the matching algorithm and `condition_registry.py` for validation rules applied at startup.

---

## Development

```
cd frontend && npm run dev   # Vite on port 5173, proxies /conditions and /form to FastAPI
uvicorn main:app --reload    # FastAPI on port 8000
```

For production: `npm run build` — output is served as `StaticFiles` in `main.py`.

---

## What the Frontend Must Never Do

- Contain clinical logic, safety rule evaluation, or encoder awareness
- Store admin tokens or session data in `localStorage` / `sessionStorage`
- Hardcode error messages in component logic (delegate to `friendlyErrorMessage`)
- Destroy patient input on a recoverable error
- Lock patients out due to an availability fetch failure
# Frontend (Patient UI)

**LLM INSTRUCTIONS:** Design decisions, enforced constraints, and non-obvious architectural choices for the patient-facing frontend. Read source files for component internals, prop signatures, type definitions, and function names — do not expect this document to duplicate them.

---

## Scope

Stateless React rendering of a seven-screen patient form flow. All clinical intelligence lives on the server — the frontend renders what the server returns and never makes branching clinical decisions.

Screen components live in `frontend/src/screens/`. Session state and screen transition logic live in `App.tsx`. See `file_structure.md` for the full file list.

---

## Core Invariants

- **No clinical logic in the frontend.** No branching decisions, no safety evaluation, no encoder awareness.
- **Patient input must never be destroyed by a recoverable error.** Screen-local error state preserves answers; only fatal errors replace the screen.
- **Availability fails open.** If `GET /availability` fails for any reason, the frontend treats the practice as open and allows the patient to proceed. A fetch failure must never lock patients out.

---

## Screen Flow

`SAFETY_WARNING` → `PATIENT DETAILS` → `SELECT_CONDITION` → `FREE_TEXT` → `EDIT` → `REVIEW` → `CONTACT` → `DONE`

- `SAFETY_WARNING` (Screen 0) is a hard block — Continue is disabled until the patient acknowledges the warning. Availability is fetched in parallel on this screen.
- `REVIEW` (Screen 4) transitions to `CONTACT` without an API call.
- `CONTACT` (Screen 5) calls `POST /form/finish`.

**API quirk:** The `GET /conditions/{id}/presentation` response includes `universal_safety_warning` for backend compatibility. The frontend must ignore this field and never display it on Screen 2. Do not remove this field from the API response.

---

## State Ownership

`App.tsx` owns all session state and is the only file that knows screen order. Screen components receive session data as props and communicate outcomes to `App.tsx` via typed callbacks. Screen components own only their own transient UI state (`isSubmitting`, `screenError`, form field state).

`onContinue` callbacks on screens that make API calls receive the full API result as a typed parameter — the component does not call any `App.tsx` state setters directly. `App.tsx` updates session state and navigates.

**Exception — `ContactScreen`:** Its `onSubmit` is `() => void` with no result parameter. `POST /form/finish` returns only a `submission_id` which `App.tsx` does not need, so nothing is passed up. This is the only screen where the callback carries no data.

The reset function in `App.tsx` manually clears every `useState` in the file. A checklist comment directly above the reset block names every variable. If a new `useState` is added to `App.tsx`, it must appear in the checklist.

**Dedicated error variable:** `App.tsx` uses `safetyFetchError` for safety warning fetch failures. This is the only fetch that lives in `App.tsx` rather than inside a screen component, so it needs its own error variable. All other fetch errors are owned locally by the screen component that makes the call.

---

## Error Handling

Two error classifications — the decision is made at the API boundary:

- **`fatalError`:** Replaces the screen entirely. Use only for genuinely unrecoverable situations (missing `runtime_id`, condition list fails to load). Lives in `App.tsx`.
- **Screen-local `screenError`:** Displays an inline message and preserves user answers. Each screen component that makes API calls declares its own `screenError` locally. Clears automatically on navigation because screen components mount fresh.

Component logic must never hardcode error messages — delegate to `friendlyErrorMessage(e)`. A 409 from the API indicates a session version conflict (multiple tabs).

---

## Fetch State Pattern

Both the safety warning fetch (Screen 0) and the presentation fetch (Screen 2) use a discriminated union `status: "loading" | "success" | "error"`. Keep these consistent with each other if either is changed.

Screen 0: `App.tsx` derives the union inline from raw state variables before passing it to `SafetyWarningScreen` as a single prop. The type `SafetyWarningFetchState` is exported from `SafetyWarningScreen.tsx`.

Screen 2: `PresentationState` is defined in `types.ts`. There is no `idle` status — both transitions into `FREE_TEXT` reset it to `loading` before navigating. Any future third entry path must do the same.

The `presentationFetchTrigger` counter in `App.tsx` exists solely to force a re-fetch when `selectedConditionId` has not changed (retry, or same-condition re-entry). Incrementing the counter is the only correct retry mechanism. **The retry callback must only call `setPresentationFetchTrigger(k => k + 1)` — not `setPresentationState({ status: "loading" })`.** The fetch effect sets loading state itself at the top of its body.

---

## ConditionCombobox

The input `id` is generated dynamically via React's `useId()` — do not target it by a stable string in tests. Query by label text instead.

---

## What the Frontend Must Never Do

- Contain clinical logic, safety rule evaluation, or encoder awareness
- Store admin tokens or session data in `localStorage` / `sessionStorage`
- Hardcode error messages in component logic
- Destroy patient input on a recoverable error
- Lock patients out due to an availability fetch failure

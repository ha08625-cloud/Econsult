# Frontend (Patient UI)

**LLM INSTRUCTIONS:** Design decisions, enforced constraints, and non-obvious architectural choices for the patient-facing frontend. Read source files for component internals, prop signatures, type definitions, and function names — do not expect this document to duplicate them.

---

## Scope

Stateless React rendering of an eight-screen patient form flow. All clinical intelligence lives on the server — the frontend renders what the server returns and never makes branching clinical decisions.

Screen components live in `frontend/src/screens/`. Session state and screen transition logic live in `App.tsx`. See `file_structure.md` for the full file list.

---

## Core Invariants

- **No clinical logic in the frontend.** No branching decisions, no safety evaluation, no encoder awareness.
- **Patient input must never be destroyed by a recoverable error.** Screen-local error state preserves answers; only fatal errors replace the screen.
- **Availability fails open.** If `GET /availability` fails for any reason, the frontend treats the practice as open and allows the patient to proceed. A fetch failure must never lock patients out.

---

## Screen Flow

`SAFETY_WARNING` → `PATIENT_DETAILS` → `OUTCOME` → `SELECT_CONDITION` → `FREE_TEXT` → `EDIT` → `REVIEW` → `CONTACT` → `DONE`

- `SAFETY_WARNING` (Screen 0) is a hard block — Continue is disabled until the patient acknowledges the warning. Availability is fetched in parallel on this screen.
- `PATIENT_DETAILS` (Screen 1) captures patient identity before condition selection.
- `OUTCOME` (Screen 2) captures the patient's desired consultation outcome before condition selection. No API call. A selection is required to proceed — `not_sure` is the explicit "I don't know" option.
- `REVIEW` (Screen 6) transitions to `CONTACT` without an API call.
- `CONTACT` (Screen 7) calls `POST /form/finish`.

**Back navigation:** `SELECT_CONDITION` navigates back to `OUTCOME`. `OUTCOME` navigates back to `PATIENT_DETAILS`.

**API quirk:** The `GET /conditions/{id}/presentation` response includes `universal_safety_warning` for backend compatibility. The frontend must ignore this field and never display it on Screen 4. Do not remove this field from the API response.

---

## Consultation Outcome Constants (`consultation_outcomes.json`)

The list of selectable outcomes is defined in `consultation_outcomes.json` at the project root. Each entry has a `value` (machine-readable, stored in the database and printed in the PDF) and a `label` (human-readable, shown to the patient).

This file is the single source of truth. It is consumed by:
- `OutcomeScreen.tsx` — imported directly via `resolveJsonModule` to render the radio list
- `consultation_outcomes.py` — loaded at import time; exposes `CONSULTATION_OUTCOMES` and `VALID_OUTCOME_VALUES`
- `pdf_formatter.py` — derives its label lookup dict from `CONSULTATION_OUTCOMES` at module load time
- `request_validation.py` — uses `VALID_OUTCOME_VALUES` to validate incoming submissions

**SYNC OBLIGATION:** The `ConsultationOutcome` union type in `frontend/src/types.ts` is defined manually and must be kept in sync with the `value` strings in `consultation_outcomes.json`. TypeScript's `resolveJsonModule` cannot derive a discriminated union automatically. When adding a new outcome:
1. Add the entry to `consultation_outcomes.json`
2. Add the value string to the `ConsultationOutcome` union in `types.ts`
3. `VALID_OUTCOME_VALUES` in `consultation_outcomes.py` is derived automatically from the JSON — no manual update needed there

**IMMUTABILITY:** The value strings are stored verbatim in the database and in PDFs. Adding new entries is safe. Renaming or removing existing values is a breaking change against stored submissions.

---

## State Ownership

`App.tsx` owns all session state and is the only file that knows screen order. Screen components receive session data as props and communicate outcomes to `App.tsx` via typed callbacks. Screen components own only their own transient UI state (`isSubmitting`, `screenError`, form field state).

`onContinue` callbacks on screens that make API calls receive the full API result as a typed parameter — the component does not call any `App.tsx` state setters directly. `App.tsx` updates session state and navigates.

**Exception — `ContactScreen`:** Its `onSubmit` is `() => void` with no result parameter. `POST /form/finish` returns only a `submission_id` which `App.tsx` does not need, so nothing is passed up. This is the only screen where the callback carries no data.

The reset function in `App.tsx` manually clears every `useState` in the file. A checklist comment directly above the reset block names every variable. If a new `useState` is added to `App.tsx`, it must appear in the checklist.

**Dedicated error variable:** `App.tsx` uses `safetyWarningFetchState` for safety warning fetch failures. This is the only fetch that lives in `App.tsx` rather than inside a screen component, so it needs its own error variable. All other fetch errors are owned locally by the screen component that makes the call.

---

## Photo Attachments

`photos: PhotoAttachment[]` is owned by `App.tsx` and threaded as props to `EditScreen` (read/write via `onPhotosChange`), `ReviewScreen` (read-only thumbnails), and `ContactScreen` (as `File[]` extracted from the attachment objects).

**Object URL lifecycle:** Each `PhotoAttachment` holds a `previewUrl` created with `URL.createObjectURL`. These must be explicitly revoked to avoid browser memory leaks. The rules are:

- **On remove:** revoke the URL immediately in the remove handler before updating state. Implemented in `EditScreen`.
- **On back navigation from EDIT to FREE_TEXT:** `App.tsx` revokes all URLs and clears `photos` before navigating. Photos do not persist across a condition change.
- **On fatal error reset:** `App.tsx` revokes all URLs before calling `setPhotos([])`. Revocation must happen before the state clear, while references are still available.
- **On unmount:** a `useEffect` with an empty dependency array in `App.tsx` revokes all remaining URLs via a `photosRef`. A ref is required here because the cleanup closure would otherwise capture the initial empty array.

**Client-side validation in EditScreen:** The `onChange` handler on the file input performs synchronous checks using the constants from `upload_constants.ts`: MIME type against `ALLOWED_MIME_TYPES`, per-file size against `MAX_FILE_SIZE_BYTES`, total count against `MAX_FILE_COUNT`, and combined size against `MAX_TOTAL_SIZE_BYTES`. These checks run against the existing `photos` prop plus the newly selected files, so the total size and count limits account for photos already in state. The server enforces the same limits independently — the client checks are a usability guard, not a security boundary. No magic bytes validation is performed; MIME type is checked via `file.type` (browser-supplied, not cryptographically verified).

**ReviewScreen thumbnail display:** `ReviewScreen` renders a read-only `Photos (n)` section when `photos.length > 0`, positioned after `additional_text` and before the safety alert. Thumbnails are 80px tall with descriptive alt text (`Photo 1`, `Photo 2`, etc.). There is no remove affordance on this screen — a plain instruction directs the patient to go back if they need to remove a photo. Photos persist when navigating back from REVIEW to EDIT, so the instruction is always actionable.

**Photos persist** when navigating back from REVIEW to EDIT — this is intentional. The patient has not changed their condition and their photos remain valid.

**Photos do not persist** when navigating back from EDIT to FREE_TEXT. A warning dialog is shown before this navigation regardless of whether any photos are attached (simpler logic, consistent behaviour). The dialog message is: "If you have attached photos, they will be lost and may need to be re-uploaded." The dialog renders as an overlay on top of the EDIT screen so answers are not lost.

---

## Error Handling

Two error classifications — the decision is made at the API boundary:

- **`fatalError`:** Replaces the screen entirely. Use only for genuinely unrecoverable situations (missing `runtime_id`, condition list fails to load). Lives in `App.tsx`.
- **Screen-local `screenError`:** Displays an inline message and preserves user answers. Each screen component that makes API calls declares its own `screenError` locally. Clears automatically on navigation because screen components mount fresh.

Component logic must never hardcode error messages — delegate to `friendlyErrorMessage(e)`. A 409 from the API indicates a session version conflict (multiple tabs).

**422 photo error translation:** `POST /form/finish` can return a 422 with a technical server detail string describing a photo validation failure. `friendlyErrorMessage` has a 422 branch that calls `friendlyPhotoErrorMessage` (in `helpers.ts`) to convert these strings into patient-facing instructions (e.g. "One of your photos is too large to send. Please go back and remove it, then try again."). Unrecognised 422 detail strings fall back to the generic error message rather than exposing raw server text. The server strings being matched are defined in `app/routers/form_router.py` — if those strings change, update `friendlyPhotoErrorMessage` to match.

---

## Fetch State Pattern

Both the safety warning fetch (Screen 0) and the presentation fetch (Screen 4) use a discriminated union `status: "loading" | "success" | "error"`. Keep these consistent with each other if either is changed.

Screen 0: `App.tsx` derives the union inline from raw state variables before passing it to `SafetyWarningScreen` as a single prop. The type `SafetyWarningFetchState` is exported from `SafetyWarningScreen.tsx`.

Screen 4: `PresentationState` is defined in `types.ts`. There is no `idle` status — both transitions into `FREE_TEXT` reset it to `loading` before navigating. Any future third entry path must do the same.

The `presentationFetchTrigger` counter in `App.tsx` exists solely to force a re-fetch when `selectedConditionId` has not changed (retry, or same-condition re-entry). Incrementing the counter is the only correct retry mechanism. **The retry callback must only call `setPresentationFetchTrigger(k => k + 1)` — not `setPresentationState({ status: "loading" })`.** The fetch effect sets loading state itself at the top of its body.

---

## Types

Wire-format types (server contracts) live in `frontend/src/types.ts`. UI-only types that are never serialised or sent to the server live in `frontend/src/uiTypes.ts`. Keep these files separate — do not add UI concerns to `types.ts`.

`PhotoAttachment` (in `uiTypes.ts`) holds a `File` object and a `previewUrl` object URL. The `previewUrl` must be revoked with `URL.revokeObjectURL` when the photo is removed or the session ends — failure to do so leaks browser memory.

---

## API Layer (`api.ts`)

`finishForm` uses `fetch` directly with a `FormData` body rather than the `postJson` helper. This is intentional — `postJson` sets `Content-Type: application/json`, which prevents the browser from setting the multipart boundary the server requires to parse the body. Do not refactor `finishForm` to use `postJson`. Do not set `Content-Type` manually on this call.

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
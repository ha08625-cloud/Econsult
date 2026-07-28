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

The list of selectable outcomes is defined in `app/core/consultation_outcomes.json`. Each entry has a `value` (machine-readable, stored in the database and printed in the PDF) and a `label` (human-readable, shown to the patient).

This file is the single source of truth. It lives at `app/core/` alongside `consultation_outcomes.py`. The Dockerfile frontend build stage copies it explicitly into the frontend workdir so Vite can resolve the import in `OutcomeScreen.tsx`.

It is consumed by:
- `OutcomeScreen.tsx` — imported directly via `resolveJsonModule` to render the radio list
- `consultation_outcomes.py` — loaded at import time; exposes `CONSULTATION_OUTCOMES` and `VALID_OUTCOME_VALUES`
- `pdf_formatter.py` — derives its label lookup dict from `CONSULTATION_OUTCOMES` at module load time
- `request_validation.py` — uses `VALID_OUTCOME_VALUES` to validate incoming submissions

**SYNC OBLIGATION:** The `ConsultationOutcome` union type in `frontend/src/types.ts` is defined manually and must be kept in sync with the `value` strings in the JSON. TypeScript's `resolveJsonModule` cannot derive a discriminated union automatically. When adding a new outcome:
1. Add the entry to `app/core/consultation_outcomes.json`
2. Add the value string to the `ConsultationOutcome` union in `types.ts`
3. `VALID_OUTCOME_VALUES` in `consultation_outcomes.py` is derived automatically from the JSON — no manual update needed there

**IMMUTABILITY:** The value strings are stored verbatim in the database and in PDFs. Adding new entries is safe. Renaming or removing existing values is a breaking change against stored submissions.

---

## State Ownership

`App.tsx` owns all session state and is the only file that knows screen order. Screen components receive session data as props and communicate outcomes to `App.tsx` via typed callbacks. Screen components own only their own transient UI state (`isSubmitting`, `screenError`, form field state).

`onContinue` callbacks on screens that make API calls receive the full API result as a typed parameter — the component does not call any `App.tsx` state setters directly. `App.tsx` updates session state and navigates.

**Exception — `ContactScreen`:** Its `onSubmit` is `() => void` with no result parameter. `POST /form/finish` returns only a `submission_id` which `App.tsx` does not need, so nothing is passed up. This is the only screen where the callback carries no data.

**`photoTier` state:** `photoTier: PhotoTier | null` follows the same ownership pattern as `photos` — owned by `App.tsx`, passed as a prop to `EditScreen` (read/write) and `ContactScreen` (read-only, forwarded to `finishForm`). The `PhotoTier` type is exported from `EditScreen.tsx` and imported by `App.tsx` and `ContactScreen.tsx`. It is reset to `null` alongside `photos` on back navigation from EDIT to FREE_TEXT.

**Condition selection state:** `selectedConditionId` and `confirmedConditionId` are deliberately separate state, not one value doing two jobs. `selectedConditionId` gates the `SELECT_CONDITION` screen's Continue button and drives the `FREE_TEXT` presentation fetch; `ConditionCombobox` nulls it transiently on every keystroke while the patient is mid-search (see the `ConditionCombobox` section below). `confirmedConditionId` records which condition the patient's current `freeText` was actually written against, and is only ever set at the point free text starts being written for a condition — `SELECT_CONDITION`'s `onContinue`, `onBlankForm`, and the "Switch condition" confirmation in "Condition Change Warning" below. Conflating these two into one value was the root cause of free text being silently wiped by the act of touching the search box on back navigation — see "Condition Change Warning".

The `triggerFatalError` function in `App.tsx` is the single entry point for fatal errors. It fires `Sentry.captureMessage` before calling `setFatalError`, ensuring the event is captured even if the component subsequently unmounts. Direct calls to `setFatalError` from the render path are banned — all five render-guard fatal paths use `triggerFatalError`. The conditions fetch failure in the `useEffect` is the one exception: it calls `setFatalError` directly because the underlying server error has already been captured by `api.ts`, and double-reporting must be avoided.

The fatal error reset button uses `window.location.reload()` rather than a manual enumeration of state setters. This guarantees object URL revocation (the browser destroys the JS context), eliminates the need to keep a reset list in sync with new `useState` declarations, and provides the cleanest possible slate after a React tree collapse. The state checklist comment in `App.tsx` no longer requires a parallel reset block entry — it is a record of state variables only.

**Dedicated error variable:** `App.tsx` uses `safetyWarningFetchState` for safety warning fetch failures. This is the only fetch that lives in `App.tsx` rather than inside a screen component, so it needs its own error variable. All other fetch errors are owned locally by the screen component that makes the call.

---

## Quantity (Unit-Toggle) Questions

A Number question flagged `quantity` in the ruleset lets the patient enter the value in metric or imperial. Each such question also carries `quantity_kind` (only `"weight"` exists today) identifying which clinical quantity it represents; this selects the component-key set and display formatter to use. Frontend design decisions:

- **Kind-first component map.** `helpers.ts` exports `QUANTITY_KINDS`, a `Record<QuantityKind, {canonicalSystem, systems}>` mirroring the backend's `ruleset.QUANTITY_KINDS` registry. `emptyComponents(kind, system)` and the component-input loop in `EditScreen` both read from it. **Parity between this table and the backend registry is a manual obligation — no automated check spans the language boundary.** Adding a kind means extending both together.
- **One form-wide toggle.** A single `unitSystem` state on `EditScreen` drives every quantity question, seeded from the first quantity question that offers **more than one** system — single-system questions are skipped by definition — via `initialUnitSystem` in `helpers.ts`. There is no per-question unit selector and no tie-break logic: the backend's startup authoring check guarantees all multi-system quantity questions agree on `allowed_systems` and `default_system`, so the first one found simply reflects the already-agreed shared choice.
- **Edit as strings, submit as numbers.** A quantity answer is held in `editableAnswers` as `{system, components}` with **string** components (e.g. `{kg: "70.5"}` or `{st: "11", lb: "11"}`) — the same verbatim-string convention scalar Numbers use, so trailing-zero precision errors are detectable. They are converted to JSON numbers only when the `/form/update` payload is built. This mirrors the server's outbound-string / inbound-number asymmetry (see `arch_submission.md`).
- **Toggling clears, never converts.** Switching units blanks every quantity question's component inputs, using each question's own `quantity_kind` to determine its blank shape. There is no automatic conversion between systems — a deliberate v1 choice.
- **Client-side gates.** The completeness gate requires every component non-empty (a seeded-but-blank quantity is not "answered"). Precision is enforced per system: metric flags kg over-`decimal_places`; imperial flags any fractional stones/pounds — this logic is still weight-specific (it is not generalised by kind) since no other kind exists yet. The advisory out-of-range notice is shown only when `unitSystem` equals the kind's `canonicalSystem` — suppressed otherwise (a recorded limitation, matching the backend, since `min`/`max` are expressed in canonical units).
- **Rendering.** `EditScreen` renders a metric/imperial toggle plus compound inputs (kg, or st + lb) driven by `QUANTITY_KINDS[kind].systems[unitSystem]`. `ReviewScreen` looks up `QUANTITY_DISPLAY_FORMATTERS[quantity_kind ?? "weight"]` to render the patient's chosen unit as `"11 st 11 lb"` or `"70.5 kg"` — never the raw object. The canonical-unit conversion for a non-canonical system appears on the clinical PDF, not the Review screen.
- **No single-system render path.** No registered kind offers only one system, so `EditScreen` has no fixed-unit (non-toggle) rendering branch. This cannot be exercised by any current ruleset or test other than a synthetic fixture. **Known limitation:** deferred to whichever ticket introduces a single-system kind.
- **`UNIT_SYSTEM_LABELS` and `COMPONENT_LABELS` stay flat, unnested by kind.** Component keys are unique across kinds in practice, and `UNIT_SYSTEM_LABELS` is exactly what a future relabelling ticket touches — restructuring it now while forbidding a text change would be churn.
- **Pure helpers.** Seeding, the kind-keyed component map, the display formatter table, and the string→number payload conversion live as pure functions in `helpers.ts` (unit-tested in `helpers.test.ts`), keeping `EditScreen` wiring thin.

---

## Condition Change Warning

Switching condition on `SELECT_CONDITION` after free text has already been written against the previous condition would silently destroy that text. This is the scenario the `selectedConditionId` / `confirmedConditionId` split above exists to prevent.

`onConditionChange` in `App.tsx` distinguishes three cases for an incoming id from `ConditionCombobox`:

- **`null` (mid-typing), or matches `confirmedConditionId`** (the patient re-selected the condition their free text already belongs to): commit directly, no warning.
- **Genuinely different and `freeText` is non-empty:** hold it as `pendingConditionId` and show the warning modal rather than committing immediately.
- **Genuinely different but `freeText` is empty:** nothing to lose, commit directly.

The modal text is: "Switching conditions will clear the answer you've already typed." It offers two choices:

- **"Keep my answer"** — discards the pending id, restores `selectedConditionId` to `confirmedConditionId` (it may already have been nulled by typing before the switch was proposed, so this restoration is not a no-op), and bumps `comboboxResetKey`. That counter is passed to `SelectConditionScreen` as a prop and used as `ConditionCombobox`'s `key`, forcing it to remount so its displayed text re-syncs to the restored id — the same remount-to-resync mechanism the `ConditionCombobox` section below documents.
- **"Switch condition"** — clears `freeText`, then commits the pending id to both `selectedConditionId` and `confirmedConditionId`. No remount is needed here: `ConditionCombobox`'s own local input state already shows the new condition's label from the moment it was picked, before `App.tsx` decided what to do with it.

**`onBlankForm`** sets `confirmedConditionId` to `GENERAL_CONSULTATION_ID` alongside `selectedConditionId`, for the same reason `onContinue` does. It does **not** clear `freeText` — "Use blank form" has never been wired to do so, and that is intentional: it is a fallback path with its own looser semantics, not a condition switch.

---

## Photo Attachments

`photos: PhotoAttachment[]` and `photoTier: PhotoTier | null` are both owned by `App.tsx`. They are threaded as props to `EditScreen` (read/write), `ReviewScreen` (`photos` read-only for thumbnails), and `ContactScreen` (`photos` as `File[]`, `photoTier` passed through to `finishForm`).

`photoTier` is reset to `null` when the patient navigates back from EDIT to FREE_TEXT, alongside the photo array being cleared. They are always reset together.

**Two-tier upload model:**

The patient must select a photo quality tier before the file input is shown. Two tiers are available:

- `"high"` — 1 photo maximum. Intended for clinical close-ups (skin lesions, moles). The backend CDR targets 4K (3840px long edge) at quality 85.
- `"standard"` — up to 5 photos. Intended for documents, letters, or general photos. The backend CDR targets 1080p (1920px long edge) at quality 80.

The `multiple` attribute on the file input is set conditionally based on the selected tier (`multiple={photoTier === "standard"}`). This prevents the OS file picker from allowing multi-select in high tier at the point of selection, rather than only after the fact.

Switching tier after photos have already been added clears the existing photos and resets the photo error. A patient selecting a different tier is changing their intent and re-uploading is the correct behaviour.

**Photo guide modal:**

A "How to take a good photo" button appears below the tier selection once a tier has been chosen. It opens a modal overlay with guidance text and a reference image (`/photo-guide.jpg` served from `frontend/public/`). Whether the guide is open (`isGuideOpen`) is self-contained local state in `EditScreen` — nothing outside the screen needs to know about it — but the dialog itself is rendered via the shared `ConfirmDialog` component (see "Shared Dialog Primitive (`ConfirmDialog`)" below).

Modal accessibility requirements: focus moves to the close button on open (the first focusable element in the panel), Escape closes the modal, focus is trapped inside the panel while open, clicking the backdrop closes the modal, clicking inside the panel does not, and focus returns to the "How to take a good photo" button on close.

**Object URL lifecycle:** Each `PhotoAttachment` holds a `previewUrl` created with `URL.createObjectURL`. These must be explicitly revoked to avoid browser memory leaks. The rules are:

- **On remove:** revoke the URL immediately in the remove handler before updating state. Implemented in `EditScreen`.
- **On tier change:** `EditScreen` revokes all existing URLs and calls `onPhotosChange([])` before calling `onPhotoTierChange`.
- **On back navigation from EDIT to FREE_TEXT:** `App.tsx` revokes all URLs and clears `photos` before navigating. Photos do not persist across a condition change.
- **On fatal error:** `App.tsx` renders the fatal error screen and the reset button triggers `window.location.reload()`. The browser destroys the JS context on reload, which revokes all object URLs automatically. No manual revocation is needed in this path.
- **On unmount:** a `useEffect` with an empty dependency array in `App.tsx` revokes all remaining URLs via a `photosRef`. A ref is required here because the cleanup closure would otherwise capture the initial empty array.

**Client-side validation in EditScreen:** The `onChange` handler on the file input performs synchronous checks: MIME type against `ALLOWED_MIME_TYPES`, per-file size against `MAX_FILE_SIZE_BYTES`, photo count against the per-tier limit (`TIER_MAX_COUNT`), and combined size against `MAX_TOTAL_SIZE_BYTES`. These checks run against the existing `photos` prop plus the newly selected files. The server enforces the same limits independently — the client checks are a usability guard, not a security boundary. No magic bytes validation is performed; MIME type is checked via `file.type` (browser-supplied, not cryptographically verified).

**ReviewScreen thumbnail display:** `ReviewScreen` renders a read-only `Photos (n)` section when `photos.length > 0`, positioned after `additional_text` and before the safety alert. Thumbnails are 80px tall with descriptive alt text (`Photo 1`, `Photo 2`, etc.). There is no remove affordance on this screen — a plain instruction directs the patient to go back if they need to remove a photo. Photos persist when navigating back from REVIEW to EDIT, so the instruction is always actionable.

**Photos persist** when navigating back from REVIEW to EDIT — this is intentional. The patient has not changed their condition and their photos remain valid.

**Photos do not persist** when navigating back from EDIT to FREE_TEXT. A warning dialog is shown before this navigation regardless of whether any photos are attached (simpler logic, consistent behaviour). The dialog message is: "If you have attached photos, they will be lost and may need to be re-uploaded." The dialog renders as an overlay on top of the EDIT screen so answers are not lost.

---

## Shared Dialog Primitive (`ConfirmDialog`)

`ConfirmDialog` (`frontend/src/ConfirmDialog.tsx`) is the single implementation of an accessible modal overlay, used by all three modal dialogs in the patient flow: the condition-change warning and back-navigation warning in `App.tsx`, and the photo guide modal in `EditScreen`. It replaces three previously-duplicated `<div className="modal-overlay">` implementations, two of which (the `App.tsx` warnings) were plain overlays with none of the dialog behaviour below.

It implements, in one place:
- `role="dialog"` and `aria-modal="true"` on the overlay.
- An accessible name via `aria-labelledby` (when a visible `title` is given, rendered as the panel's `<h2 className="modal-title">`) or `aria-label` (when the dialog has no visible heading — the two `App.tsx` warnings use this, since their text is a single paragraph rather than a titled dialog).
- Focus moved to the first focusable element inside the panel on open. Callers control which element that is purely through DOM order — the safe/non-destructive button (or the close button, for the photo guide) must be first in the panel's markup.
- A Tab/Shift+Tab focus trap confined to the panel while the dialog is open.
- Escape closes the dialog via the caller-supplied `onEscape`, which **must** map to the same safe/non-destructive action as the first-focused button — there is no separate "cancel" concept, Escape and the first button are the same action.
- Focus returned to whatever element triggered the dialog (captured via `document.activeElement` on mount) when the dialog closes.
- Backdrop click is opt-in via `onOverlayClick` — the two `App.tsx` warnings omit it (clicking outside does nothing, matching their pre-existing behaviour); the photo guide passes it to close on backdrop click, matching its pre-existing behaviour.

`ConfirmDialog` renders the overlay and panel only — buttons, body text, and any panel class override (`className`, e.g. `"modal-panel modal-panel--narrow"` for the two warning dialogs, which are narrower than the default `.modal-panel`) are supplied by the caller as `children`. It does not own any open/closed state itself; callers keep their own boolean and conditionally render `<ConfirmDialog>`, same as before this component existed.

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

On mount, the input's displayed text is initialised from `selectedId` via a one-time lookup against the `conditions` list (a lazy `useState` initialiser) — if the patient returns to this screen with a condition already selected, the label is shown immediately rather than starting blank. This is a one-time lookup, not a live sync: if `selectedId` changes after mount without the component remounting, the displayed text does not follow it. The only consumer of this today is the "Keep my answer" path in "Condition Change Warning" above, which forces a resync by remounting via a changing `key` rather than by making this component fully controlled.

All visual styles live in `index.css` under the `/* Condition Combobox */` section. The class names are: `.combobox-wrapper`, `.combobox-input`, `.combobox-listbox`, `.combobox-info-item`, `.combobox-option`, `.combobox-option--active`, `.combobox-option--selected`. Do not add inline styles to this component — the CSS section is the single source of truth.

The `maxHeight` of the listbox is the one permitted exception: it is set as an inline style because it is derived from the `SUGGESTION_LIST_MAX_HEIGHT` constant in the component. If the constant changes, the style updates automatically. Duplicating the value in CSS would create silent drift.

Active and selected option states use `outline: 2px solid` in addition to a background colour. This is intentional — background colour alone is invisible in Windows High Contrast / forced-colors mode. Do not remove the outline rules.

The informational rows inside the listbox (no-match notice, filtered count) use `--text-muted` (`#5a6a7a`), which passes the WCAG 2.1 AA 4.5:1 contrast threshold on a white background. Do not substitute a lighter colour.

A `useEffect` keyed on the computed `activeDescendant` id calls `scrollIntoView({ block: "nearest" })` on the active option's DOM element whenever arrow-key navigation changes it. Without this, the fixed 300px `maxHeight` scroll area can move the active option out of view during keyboard navigation, leaving no visible indication of position. `scrollIntoView` is called via optional chaining (`?.scrollIntoView?.(...)`) since it is unimplemented in jsdom, the test environment.

---

## Doctor Preference (`ContactScreen`)

`ContactScreen` has two doctor-preference UIs, chosen by whether the practice has configured a doctor list (`doctors` from `GET /doctors`):

- **List path** (`doctors` non-empty): a dropdown of "Soonest available doctor" (`any`), "Someone not on this list" (`other`), and one option per configured doctor, plus a free text box that is **always visible**. The dropdown value is held in local state (`doctorSelection`) separate from `contactPreferences` and mapped onto the wire fields on submit.
- **Legacy path** (`doctors` empty, including when the fetch failed): the original two-option dropdown (`any` / `usual`) with the free text box shown only when `usual` is selected. It writes `doctor_preference` / `usual_doctor_name` directly.

**Mapping rules for the list path (submit-time precedence, highest first):**

1. A named doctor selected from the list wins — free text is ignored. The explicit selection is the stronger signal, and the free text box is labelled for doctors *not* on the list.
2. Otherwise, non-empty (trimmed) free text produces `doctor_preference: "usual"` with that name. This holds for `other` **and** for `any`: a name typed while the dropdown is left at its default is an **implicit `other` selection**. Never submit `any` while discarding a name the patient has typed — the practice would never see the preference and the patient gets no warning that it was dropped.
3. Otherwise `doctor_preference: "any"`, `usual_doctor_name: null`. Whitespace-only free text falls here.

Validation on the list path only requires a name when `other` is explicitly selected. The `any` + free text combination is valid, not an error — the dropdown is deliberately *not* auto-changed to `other` when the patient types, since silently rewriting one control from another is the change-of-context antipattern this codebase avoids elsewhere (WCAG 3.2.2).

---

## Accessibility (WCAG 2.1 AA / NHS Digital)

The patient frontend must comply with WCAG 2.1 Level AA and follow NHS Digital Service Manual patterns. This section records decisions made during the accessibility pass so they are applied consistently across all screens.

---

### Focus Management on Screen Load

Every screen focuses its `<h1>` on mount (or, for the two screens with an async loading -> ready transition, once that content is ready) so screen reader users are notified of every Continue/Back screen transition. This generalises what used to be a two-screen-only pattern to all nine screens plus the `App.tsx` fatal error view.

The shared implementation is `useFocusHeading` (`frontend/src/useFocusHeading.ts`):
- It returns a `ref` to attach to the screen's `<h1>`, alongside `tabIndex={-1}` (allows programmatic focus without inserting the heading into the natural tab order).
- Called with no argument, it focuses on mount — the correct behaviour for any screen that renders synchronously.
- Called with a value that starts falsy and becomes truthy once async data has loaded (e.g. `useFocusHeading(conditions)` in `SelectConditionScreen`, `useFocusHeading(presentationState.status === "success")` in `FreeTextScreen`), it defers focus until the heading's final content is in place — preserving the original loading-transition behaviour for those two screens.

Any new screen must call `useFocusHeading` and wire its return value to the `<h1>`. Do not focus the body or an arbitrary container — the heading is the correct target per the NHS Service Manual.

---

### Visually Hidden Text (`sr-only`)

The `.sr-only` CSS class is the standard visually hidden pattern (1px clipped box). It must be used — not `display:none` or `visibility:hidden`, both of which hide content from screen readers entirely.

Two mandatory uses established during the accessibility pass, which must be replicated on every equivalent element across all screens:

- **Warning callouts:** A `<span className="sr-only">Important: </span>` must appear immediately before the visible heading text inside any NHS warning callout box. The visible heading should not contain the word "Important" — it belongs only in the hidden span.
- **Error messages (`InlineError`):** The `InlineError` component in `layout.tsx` already prepends `<span className="sr-only">Error: </span>` to every message. Any new error display component that is not `InlineError` must follow the same pattern. Do not add a second "Error:" prefix on top of `InlineError`.

---

### Error Summary Links

`PatientDetailsScreen` and `ContactScreen` render a per-field error summary (`.error-summary`) above the form on failed validation. Each list item is a link (`<a href="#field-id">`) to the offending field, per the NHS/GOV.UK error summary pattern — a `preventDefault` click handler calls `document.getElementById(id)?.focus()` so activating the link moves focus to the field, not just scrolls to it. The target id for each error key lives in that screen's `ERROR_FIELD_IDS` map, parallel to its existing `ERROR_LABELS` map. An error key with no entry in `ERROR_FIELD_IDS` renders as plain text (no known single field to link to).

These two summaries deliberately omit `role="alert"`. Focus is already moved onto the summary container (`summaryRef.current.focus()`) on failed submission, and that focus move alone causes screen readers to announce the container's content — adding `role="alert"` on top produces a double announcement on some screen reader/browser pairs. `EditScreen`'s error summary (generic `screenError`/`photoError` messages, not per-field) still uses `role="alert"` and is out of scope for this pattern; do not assume the two are equivalent.

---

### Hint Text, Not Placeholders

Field instructions and examples (date formats, "e.g." examples) must be a `.field-hint` paragraph wired via `aria-describedby`, never an input `placeholder`. Placeholders vanish on input, are skipped by some screen readers, and default placeholder grey is borderline against WCAG 1.4.3 in some browsers — NHS guidance is not to use them.

The established convention (originally the phone-number hint in `ContactScreen`, now applied throughout `PatientDetailsScreen`, `ContactScreen`, and `ConditionCombobox`): give the hint paragraph a stable `id`, and set the input's `aria-describedby` to that id normally, switching to the field's error id when one is present (mutually exclusive — not both ids at once). Any new field with placeholder-style instructional text must follow this pattern rather than introducing a `placeholder` attribute.

---

### Alert Colour Semantics

The `.alert-danger` (red) and `.alert-warning` (yellow) CSS classes are not interchangeable. The distinction matters both visually and semantically:

- `.alert-danger` — error states only (fetch failures, validation errors). This is what `InlineError` uses.
- `.alert-warning` — clinical or contextual warnings that are not errors (the safety warning callout, the practice-closed message). Yellow per the NHS Warning Callout pattern.
- `.alert-info` — supplementary notices (after-hours notice).

Using red for a clinical warning callout is wrong: it implies the page is in an error state, which confuses both sighted users and screen readers.

---

### `InlineError` — shared component behaviour

`InlineError` in `layout.tsx` carries `role="alert"`. This causes screen readers to announce the error immediately when it mounts. Do not add a second `role="alert"` wrapper around `InlineError`.

---

### Loading States

Loading containers must carry `role="status"`. This causes screen readers to announce the loading message when the container mounts. The `.status-container` / `.status-text` CSS classes are the standard pattern — use them for all loading states, and always pair them with `role="status"`.

---

### Number Questions Use `type="text"` + `inputMode`, Not `type="number"`

`EditScreen`'s Number question inputs (both scalar and quantity-component) use `type="text"` with `inputMode="decimal"` (or `"numeric"` for imperial stones/pounds, which must be whole numbers) and a `pattern` attribute. GOV.UK moved away from `type="number"`: the scroll-wheel and arrow keys can silently change the value, some screen readers misreport the control, and letters are silently swallowed rather than rejected. Precision validation already operates on the raw string value in `editableAnswers`, so this was a low-risk swap. The native `step`/`min`/`max` attributes were dropped along with `type="number"` — they never did any blocking validation in this flow (the precision/range gates are the client-side JS logic above), so nothing was lost by removing them.

---

### Touch Target Size

The photo thumbnail remove button in `EditScreen` is visually 28x28px (unchanged, to avoid disturbing the photo grid layout) but its hit area is enlarged to 44x44px per NHS/Apple/Google touch guidance via the `.photo-remove-btn` CSS class — a transparent `::before` pseudo-element with `inset: -8px` extends the clickable/tappable area without affecting appearance.

---

### Focus Indicators (1.4.11)

A single global rule in `index.css` gives every interactive element a consistent 3px `var(--border-focus)` outline on `:focus-visible`, declared after the element-specific focus rules so it wins by source order without removing them (e.g. it strengthens, rather than replaces, the border-colour change on `input[type="text"]:focus`). This is what makes `<select>` elements (styled via `.combobox-input`, which the text-input focus rule never reached) and buttons (previously the unstyled browser default) get a visible focus ring. Generalises the pattern already used by `.error-summary:focus` and `.guide-link:focus`.

---

### Gated Continue Buttons — Always Enabled, Never `disabled`

None of the five screens with a Continue gate condition (`SafetyWarningScreen`, `OutcomeScreen`, `SelectConditionScreen`, `EditScreen`, `ReviewScreen`) use the `disabled` attribute on the Continue button. A `disabled` button is removed from the tab order, so a keyboard or screen reader user who misses the unmet condition tabs past it with no explanation.

Instead, per the GOV.UK error-summary pattern already used by `PatientDetailsScreen` and `ContactScreen`, the button is always enabled and its `onClick` checks the gate condition itself:
- If the gate is unmet, it moves focus to the existing hint/error text explaining why (a `ref`ed element with `tabIndex={-1}`) and does not call `onContinue`.
- If met, it calls `onContinue` as normal.

`EditScreen` reuses its existing `screenError` / `error-summary` / `summaryRef` mechanism for this — `handleContinue` sets `screenError` for the unmet-gate case before the async submit path, so the same focus-on-error `useEffect` handles it. `ReviewScreen`'s gate (`hasSafetyBlock`) is a genuine clinical block rather than a fixable field; clicking focuses the safety alert box rather than a fix-it hint, since the only remedy is going Back. The Continue button also carries `aria-describedby="review-safety-alert"` while blocked, so a screen reader user tabbing to the button (rather than clicking it) still hears the blocking reason attached to the control itself.

---

### Contextual Button Descriptions

When a button's purpose is explained by adjacent prose that is not its visible label, link them explicitly with `aria-describedby`. Set an `id` on the explanatory paragraph and set `aria-describedby` to that `id` on the button. This ensures screen reader users navigating by interactive elements hear the explanation, not just the button label.

Established example: the "Use blank form" button in `SelectConditionScreen` is described by `id="blank-form-hint"`.

---

### Text Formatting Rules

These must be observed on all screens; they are not enforced by the CSS and require authorial discipline:

- **Left-align all text.** No `text-align: justify` anywhere.
- **No italics** in patient-facing content.
- **No all-caps** (BLOCK CAPITALS). Use sentence case for all headings and labels.
- **Underlining is reserved for hyperlinks only.** Do not underline text for emphasis.
- **Do not set font sizes with inline styles** on screen components — add or reuse a CSS class.

---

### Reduced Motion (2.3.3)

A `@media (prefers-reduced-motion: reduce)` block in `index.css` zeroes the `border-color`/`all` transitions on text inputs and `.selection-card`, and the `.btn-primary:active` press transform. Any new transition or transform added to an interactive element must get a corresponding reduced-motion override in this block.

**Known gap:** the Google Font (`Source Sans 3`) is still fetched at runtime from `fonts.googleapis.com` via `@import` in `index.css`. This is not an accessibility issue, but it is a render-blocking third-party dependency and a GDPR/NHS data-flow consideration (the font request leaks the patient's IP to Google). Self-hosting the font file is deferred to a future ticket.

---

### Testing Accessibility Changes

When writing or updating tests for screens that have been through the accessibility pass:

- Use `getByLabelText` to assert checkbox/input associations — this verifies the label association is working, not just that the element exists.
- Use a `textContent` matcher function (not `getByText` with a plain string) when asserting on elements that contain both an `sr-only` span and visible text, since the full `textContent` includes the hidden text. Constrain the matcher to a specific `tagName` when multiple ancestor elements share the same `textContent`.
- Do not test that `sr-only` text is visually hidden — that is a CSS concern, not a component concern. Test only that the text is present in the DOM.
- For focus management tests, use `waitFor` and assert on `document.activeElement`.

---

## What the Frontend Must Never Do

- Contain clinical logic, safety rule evaluation, or encoder awareness
- Store admin tokens or session data in `localStorage` / `sessionStorage`
- Hardcode error messages in component logic
- Destroy patient input on a recoverable error
- Lock patients out due to an availability fetch failure

---

## Observability

`@sentry/react` is initialised in `main.tsx` before `<App />` mounts.

**Test and dev isolation.** Sentry is only initialised when `!import.meta.env.DEV && import.meta.env.MODE !== 'test'`. The `DEV` guard covers the Vite dev server. The `MODE !== 'test'` guard covers Vitest, which sets `MODE="test"` in jsdom. Without both guards Sentry would intercept console errors and attempt outbound network requests during CI.

**PII lockdown.** The following integrations are explicitly removed from the defaults: `BrowserTracing` (would leak sensitive URL parameters into transaction names), `Breadcrumbs` (tracks DOM clicks and navigation), `GlobalHandlers`, `LinkedErrors`, `HttpContext`, `Dedupe`. Performance tracing is disabled (`tracesSampleRate: 0`). A `beforeBreadcrumb` hook drops the request body size field for POST requests to `/form/update` and `/form/finish`, which carry raw clinical JSON and `FormData` payloads.

**Error capture strategy.** Errors are captured at two layers:

- `api.ts` captures 5xx responses and online network failures before throwing `ApiError`. This is the correct interception point because `ApiError` stores only the status code and a generic message — the request body is never retained. The `ErrorBoundary` in `main.tsx` catches synchronous render-phase crashes that `App.tsx`'s `fatalError` state cannot reach.
- `App.tsx`'s `triggerFatalError` captures unrecoverable state invariant violations (missing runtime IDs, invalid screen transitions). These are bugs, not server errors, and are reported at `"fatal"` level.

**Safety isolation invariant.** Triggered safety rules are successful, deterministic clinical operations. They must never be reported to Sentry. `triggerFatalError` must never be called from safety message handling paths. This invariant is enforced by convention — there is no runtime guard.

**DSN configuration.** The frontend DSN is supplied via `VITE_SENTRY_DSN` (a Vite build-time environment variable). If absent, `Sentry.init` receives `undefined` as the DSN and initialises silently without sending events. No error is thrown.
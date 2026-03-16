* **Scope:** Stateless React rendering, condition search, combobox, fetching APIs.  This document covers frontend
* **Key Files:** `App.tsx`, `api.ts`, `types.ts`, `search.ts`, `ConditionCombobox.tsx`

## Screen 0: Pre-Session Safety Gate (Strict Constraints)

**CRITICAL RULE:** The Safety Gate is a HARD BLOCK, not an advisory. A patient must actively acknowledge the warning before accessing any form logic.

* **API Contract:** Frontend calls `GET /safety-warning` on mount.
    * No authentication, condition ID, or session is required.
    * Returns the `UNIVERSAL_SAFETY_WARNING` constant defined in `presentation_service.py`.
* **UI Enforcement:** The "Continue" button MUST remain disabled until the "I confirm..." checkbox is ticked.
* **Validation UX:** While unticked, display the red hint: *"If any of the above apply to you, please call 999 or go to A&E immediately. Do not use this form."*.
* **Error Handling:** Fetch failures show an inline error with a "Try again" button. (Note: No state is lost because no session exists yet).
* **API Quirk (Do not "fix"):** `GET /conditions/{id}/presentation` still returns `universal_safety_warning` in its payload for backend compatibility, but the frontend MUST ignore it and never display it on Screen 2.

## Frontend Error Handling Constraints

**CORE INVARIANT:** Patient input MUST NEVER be destroyed by a recoverable error. Error classification happens at the API boundary, never in component logic.

### Error States (Enforced via React State)
* **`fatalError`:** Replaces the current screen entirely. 
  * *Constraint:* ONLY use this for genuinely unrecoverable situations (e.g., the condition list fails to load on Screen 1, or an invalid internal state like missing `runtime_id`).
* **`screenError`:** Displays an inline message and preserves user answers. 
  * *Constraint:* Use for ALL recoverable failures (network errors, 5xx, and 4xx on submission endpoints). 
  * *Behavior:* Automatically clear this state on every screen transition or when the patient resumes editing.

### API Boundary Rules (`api.ts`)
* **`ApiError`:** All fetch calls MUST be wrapped to throw `ApiError` rather than a standard `Error`.
* **Payload:** `ApiError` must carry the HTTP `status` (number) or `null` for network-level failures.
* **User Messages:** Component logic MUST NOT hardcode error messages. It must delegate to `friendlyErrorMessage(e)` to generate patient-facing text based on the status code. 
* **Special Case (409):** A 409 status on a form endpoint indicates a session version conflict (optimistic concurrency failure, e.g., multiple tabs open).

## Frontend modules

The frontend is a stateless renderer. It contains no clinical logic,
no branching decisions, and no safety evaluation. All intelligence
lives on the server.

### types.ts — Frontend-visible contracts

Defines TypeScript interfaces for all data the frontend may receive or send.

Contains:
* ClientQuestion — individual question with current value and suggested flag
* ClientStateView — full form state for rendering
* ClientAnswerReturn — payload sent back on update (runtime_id, base_version, answers)
* SafetyMessage — rule_id + message text
* ConditionSummary — id + label for condition list
* ConditionPresentation — label, free_text_prompt, universal_safety_warning, practice_signposting (string | undefined — sanitised HTML rendered via DOMPurify)
*  ContactMethod — union type: "email" | "text" | "phone"
* DoctorPreference — union type: "any" | "usual"
* ContactPreferences — contact method selection, contact details,
  and doctor preference collected on Screen 5 (CONTACT)
* AvailabilityResult — is_open (boolean), closed_message (string | null),
after_hours_notice (string | null). Used by Screen 0 availability fetch.

Rules:
* No clinical logic
* No encoder awareness
* No safety evaluation
* These types are projections of server-side state, not mirrors of it

### api.ts — HTTP client

Provides typed fetch wrappers for all backend endpoints.

Functions:
* getConditions() — GET /conditions
* getConditionPresentation(conditionId) — GET /conditions/{id}/presentation
* initForm(conditionId, freeText) — POST /form/init
* updateForm(payload) — POST /form/update
* finishForm(runtimeId, version, contactPreferences) — POST /form/finish
  Accepts a ContactPreferences object and includes it as contact_preferences
  in the POST body.
* getSafetyWarning() — GET /safety-warning (already existed, document here for completeness alongside availability)
* getAvailability() — GET /availability. Returns AvailabilityResult
* ApiError now carries a detail field. postJson extracts detail from 503 responses. friendlyErrorMessage returns the server's closed message for 503 errors.

Rules:
* No business logic
* No data transformation beyond JSON serialisation
* Payload field names must match backend expectations exactly
  (e.g. condition_id, free_text, runtime_id, base_version)
* All type imports must use `import type` syntax. TypeScript interfaces
  do not exist at runtime; using a plain import causes bundler errors
  when verbatimModuleSyntax is enabled in tsconfig

### App.tsx — React UI

Stateless renderer implementing a six-screen flow.

* Screen 0 (SAFETY_WARNING): displays universal safety warning, requires
  confirmation before continuing
* Screen 1 (SELECT_CONDITION): fetches GET /conditions, renders combobox
* Screen 2 (FREE_TEXT): fetches GET /conditions/{id}/presentation,
  renders framing text + free text input, submits to POST /form/init
* Screen 3 (EDIT): renders questions from ClientStateView, collects answers.
  additionalText state is collected here, included in the ClientAnswerReturn
  payload, and shown on the REVIEW screen only when non-empty.
  Submits to POST /form/update.
* Screen 4 (REVIEW): displays answers + safety messages.
  Submit button transitions to Screen 5 (CONTACT) rather than calling
  the API directly. Returns to EDIT via Back.
* Screen 5 (CONTACT): collects contact preferences (method, contact details,
  doctor preference). Submits to POST /form/finish with the complete
  ContactPreferences payload. Returns to REVIEW via Back without losing
  REVIEW state.
* Screen 6 (DONE): confirmation

Contact screen behaviour:
* At least one contact method must be selected before submission
* Phone number field is shown when "text" or "phone" is selected
* Email address field is shown when "email" is selected
* Best time to call field is shown when "phone" is selected
* Doctor name field is shown when "usual doctor" is selected in the dropdown
* UK phone validation: strips spaces, checks for 07 or +44 prefix,
  enforces length 10–13 digits. International numbers are rejected.
* Validation fires on Submit with inline per-field error messages.
  No alert boxes.
* contactPreferences state is reset to defaults each time the patient
  enters the CONTACT screen from REVIEW.

State management:
* Pre-session state: selectedConditionId, presentation, freeText
* Session state: runtimeId, version, clientState, editableAnswers,
  safetyMessages, additionalText
* Contact state: contactPreferences, contactErrors
* Pre-session state is discarded after /form/init succeeds
* Session state is never round-tripped back to pre-session screens
* contactPreferences is not persisted to the server until final submission

Development:
* Served via Vite dev server on port 5173 during development
* Vite proxy forwards /conditions and /form requests to FastAPI on port 8000
* For production, run npm run build and serve the dist/ output as StaticFiles
* Start command from project root:
    cd frontend && npm run dev
  FastAPI must also be running on port 8000 in a separate terminal

Screen 0 (SAFETY_WARNING) now fetches GET /availability alongside the
safety warning. Three new state variables: practiceIsOpen,
availabilityClosedMessage, afterHoursNotice.
Availability fetch behaviour:

Runs in a separate useEffect, parallel to the safety warning fetch.
If the fetch fails for any reason (network error, any non-200 response),
fails open: practiceIsOpen is set to true. No closed message banner,
no after-hours notice. A fetch failure must never lock patients out.

Screen 0 rendering changes:

When practice is closed (practiceIsOpen === false): a yellow warning
banner appears above the safety warning text. The safety warning remains
visible — a patient arriving out of hours must still see emergency safety
information. The Continue button is disabled.
When practice is open and afterHoursNotice is non-null: an informational
blue notice appears below the safety warning, above the checkbox.

initForm 503 handling:

If POST /form/init returns 503 (practice closed between availability
check and form submission), the detail field from the response body is
displayed as the screen error on Screen 2 (FREE_TEXT). This is handled
transparently via the updated friendlyErrorMessage in api.ts.

### search.ts — Condition search and filtering
A single-purpose frontend module containing all condition filtering logic for the combobox. Nothing else in the frontend contains matching logic.

Location: frontend/src/search.ts

Exported functions:
* normalise(text): string — lowercases and trims a string. Applied to both query and all strings being compared.
* matchesQuery(condition, query): boolean — returns true if the condition should appear for a given query string.
* filterConditions(conditions, query): ConditionSummary[] — filters a canonical condition list by query. Always filters from the full list passed in, never incrementally from a previous result.

Three-layer matching strategy (applied in order):
* Layer 1 — substring match on the condition label. Case-insensitive. Handles the common case of a patient typing part of a plain English label.
* Layer 2 — substring match on any search_tags entry. Case-insensitive. Handles synonyms, abbreviations, and medical terms that differ from the label (e.g. "UTI" finding "Urinary symptoms").
* Layer 3 — Levenshtein (edit distance) fuzzy match on individual tokens of each tag. The tag is split on whitespace into tokens. The query is kept as a single string and compared against each token. Handles common misspellings (e.g. "cistitis" finding "cystitis").
* Layer 3 only runs if layers 1 and 2 both return false. This avoids unnecessary computation and prevents short correct queries from triggering fuzzy noise.

Fuzzy matching thresholds:
* Query lengthBehaviourLess than 4Fuzzy disabled entirely4 to 5Threshold 1 (one edit)6 or moreThreshold 2 (two edits)
* Short queries disable fuzzy matching to prevent false positives. For example, "ut" would otherwise match almost everything.
* Fallback behaviour:
* filterConditions returns the full canonical list when the query is empty or when no conditions match. It never returns an empty list.  The caller (ConditionCombobox) is responsible for detecting the no-match fallback and showing the appropriate message.

Constants (named, not magic numbers):
* FUZZY_MIN_QUERY_LENGTH = 4
* FUZZY_THRESHOLD_SHORT = 1
* FUZZY_THRESHOLD_LONG = 2

Dependencies: types.ts (ConditionSummary type only). No backend dependency. No external library.

### 3.19.5 ConditionCombobox.tsx — Condition selection combobox
A self-contained React component that replaces the separate search input and select dropdown on Screen 0. Renders a text input that shows a floating suggestion list, filtered in real time as the patient types.
Location: frontend/src/ConditionCombobox.tsx
Props:
typescriptinterface ConditionComboboxProps {
  conditions: ConditionSummary[];   // full canonical list, never mutated
  selectedId: string | null;        // currently selected condition id
  onChange: (id: string | null) => void;
}
Internal state:
* inputValue: string — text currently shown in the input
* isOpen: boolean — whether the suggestion list is visible
* activeIndex: number | null — which suggestion is keyboard-highlighted

filteredConditions is a derived value computed on every render from filterConditions(conditions, inputValue). It is never stored in state, which guarantees filtering is always from the canonical list and never incremental.
Behaviour:
* On focus: opens the suggestion list showing all conditions (input is empty, full list returned).
* On typing: updates inputValue, reopens the list, clears activeIndex, and calls onChange(null) to invalidate any previous selection.
* On suggestion click: sets inputValue to the condition label, closes the list, calls onChange(condition.id).
* On selection via keyboard Enter: same outcome as click.
* On blur: closes the list after a 150ms delay. The delay is necessary because mousedown on a suggestion fires the input blur event before the click registers. Without the delay the list closes before the selection is applied. The blur timeout is cancelled if the user refocuses the input or clicks a suggestion.
* Escape closes the list without clearing the input or selection. Tab closes the list and allows natural focus movement.

Keyboard navigation:
* ArrowDown — moves highlight down, wraps from last to first
* ArrowUp — moves highlight up, wraps from first to last
* Enter — selects the highlighted condition if one exists
* Escape — closes the list
* Tab — closes the list, does not prevent default

Suggestion list:
* Rendered as an absolutely-positioned <ul> below the input. position: relative on the container ensures correct positioning. max-height: 300px with overflow-y: auto prevents the list extending off screen. z-index: 100 ensures it overlays subsequent page content.
* When the filtered list is shorter than the full list, a count label is shown at the top of the list: "Showing X of Y conditions."
* When inputValue is non-empty but no tags or labels matched and filterConditions fell back to the full list, a message is shown instead of the count: "No matching conditions — try different words, or scroll below."

ARIA:
* Follows the ARIA combobox pattern. The input has role="combobox", aria-expanded, aria-autocomplete="list", aria-controls pointing to the listbox, and aria-activedescendant pointing to the active option when keyboard-highlighted. The list has role="listbox". Each item has role="option" and aria-selected. IDs are generated with useId() to prevent collisions.
Dependencies: search.ts (filterConditions), types.ts (ConditionSummary). No external library.

Condition search_tags — ruleset schema
search_tags is an optional field in the presentation block of each ruleset JSON file. It provides synonyms, abbreviations, and colloquial terms that patients might type when searching for a condition.
Location in ruleset: inside presentation, alongside label and free_text_prompt.
Example:
json"presentation": {
  "label": "Urinary symptoms",
  "free_text_prompt": "Tell us about your symptoms and when they started.",
  "search_tags": ["UTI", "cystitis", "bladder infection", "burning urine"]
}


**Design rationale:** search tags are presentation-layer metadata, not clinical content. Placing them inside the `presentation` block keeps clinical schema (questions, safety rules, encoder definitions) free of search concerns. Tags are written and maintained by whoever edits the ruleset JSON — there is no automatic synonym generation.

**Validation** (enforced by `condition_registry.py` at startup — any failure aborts startup):

- `search_tags` is optional. Absent means empty list, not an error.
- If present, must be a list.
- Each item must be a non-empty string after stripping whitespace.
- Each item must not exceed `SEARCH_TAGS_MAX_TAG_LENGTH` (60) characters.
- Total count must not exceed `SEARCH_TAGS_MAX_COUNT` (20) tags.
- Case-insensitive duplicates are silently removed with a logged warning. First occurrence is kept.
- `search_tags` is added to the presentation allow-list in `condition_registry.py`. Any other unexpected key in `presentation` still aborts startup.

**Exposure:** `condition_registry.list_conditions()` returns `search_tags` alongside `id` and `label`. Search tags are never exposed in the clinical engine, safety engine, or any backend module other than the registry.

**Maintenance note:** tags are the only mechanism for synonym matching. There is no automatic or ML-based synonym expansion. If a condition is renamed or new colloquial terms become common, the JSON file must be updated manually.

### constants.ts — Frontend application constants
Single file for frontend-wide constants that must be kept in one place.
Contains:

GENERAL_CONSULTATION_ID: string — the condition_id of the general consultation
(blank form) ruleset. Must match the condition_id field in general.json exactly.
Used in App.tsx to filter this condition from the combobox and to set
selectedConditionId when the blank form button is clicked.

If the general consultation ruleset is ever renamed, update this constant and
this constant only. Do not hardcode the string elsewhere in the frontend.

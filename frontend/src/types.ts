// Frontend-visible contracts only

export type AnswerType = "boolean" | "text" | "number";

export type UnitSystem = "metric" | "imperial";

// The clinical quantity a unit-toggle question represents. Only "weight" is
// registered today (mirrors ruleset.QUANTITY_KINDS on the backend). UnitSystem
// stays "metric" | "imperial" because that is the system vocabulary of every
// registered kind today; a kind with its own systems (e.g. a temperature kind
// using "celsius" | "fahrenheit") would widen UnitSystem rather than replace it.
export type QuantityKind = "weight";

// Server -> client shape for a quantity (unit-toggle) question's current value.
// Components are strings, matching the scalar-Number convention: the value is
// held verbatim in the edit form so trailing-zero precision errors can be
// detected, and converted to JSON numbers only when the /form/update payload is
// built. Keys depend on the system ("kg" for metric; "st" and "lb" for imperial).
export interface QuantityValueView {
  system: UnitSystem;
  components: Record<string, string>;
}

// Client -> server shape for a quantity answer in the /form/update payload.
// Components are JSON numbers; the backend parses them with Decimal precision.
export interface QuantityAnswerPayload {
  system: UnitSystem;
  components: Record<string, number>;
}

export interface ClientQuestion {
  answer_key: string;
  question_text: string;
  answer_type: AnswerType;
  // For "number" questions the server sends the value as its canonical string
  // (e.g. "70.5"), which is why this stays string-or-null rather than widening
  // to number. The string is held verbatim in the edit form so trailing-zero
  // precision errors can be detected; it is converted to a number only when the
  // /form/update payload is built.
  //
  // For a quantity (unit-toggle) Number question, current_value is instead a
  // QuantityValueView ({system, components}) when answered, or null when not.
  current_value: boolean | string | QuantityValueView | null;
  required: boolean;
  suggested: boolean;
  // Number questions only. Absent for boolean and text questions.
  decimal_places?: number;
  min?: number;
  max?: number;
  range_warning_text?: string | null;
  // Quantity (unit-toggle) Number questions only. Absent otherwise.
  // allowed_systems lists the systems the patient may choose between;
  // default_system seeds the toggle before any answer is given.
  // quantity_kind identifies which clinical quantity this is (e.g. "weight"),
  // which selects the component-key set and formatter to use.
  quantity?: boolean;
  quantity_kind?: QuantityKind;
  allowed_systems?: UnitSystem[];
  default_system?: UnitSystem;
}

export interface ClientStateView {
  condition_label: string;
  free_text: string | null;
  additional_text: string | null;
  questions: ClientQuestion[];
}

export interface ClientAnswerReturn {
  runtime_id: string;
  base_version: number;
  // Number answers travel on the wire as JSON numbers; the backend parses them
  // with Decimal precision. boolean and text answers travel as before. A
  // quantity answer travels as a QuantityAnswerPayload ({system, components}).
  answers: Record<string, boolean | string | number | QuantityAnswerPayload | null>;
  additional_text: string | null;
}

export interface SafetyMessage {
  rule_id: string;
  message: string;
}

// --- Pre-session safety gate (Screen 0) ---

export interface SafetyWarning {
  universal_safety_warning: string;
}

// Discriminated union for the safety warning fetch lifecycle.
// Stored as a single state variable in App.tsx.
// Guard: if (safetyWarningFetchState.status === "success") return — prevents re-fetch.
// Retry: reset to { status: "loading" } to trigger a new fetch.
export type SafetyWarningFetchState =
  | { status: "loading" }
  | { status: "success"; text: string }
  | { status: "error"; message: string };

// --- Availability (Screen 0) ---

export interface AvailabilityResult {
  is_open: boolean;
  closed_message: string | null;
  after_hours_notice: string | null;
}

// --- Condition discovery and presentation (Screens 1-2) ---

export interface ConditionSummary {
  id: string;
  label: string;
  search_tags: string[];
}

export interface ConditionPresentation {
  label: string;
  free_text_prompt?: string;
  universal_safety_warning: string;
  practice_signposting?: string;
}

// Discriminated union for the presentation fetch lifecycle.
// No idle state — this value is only rendered inside the FREE_TEXT screen block,
// and both transitions into FREE_TEXT reset it to "loading" before navigating.
// If a future developer adds a third path to FREE_TEXT, they must do the same.
export type PresentationState =
  | { status: "loading" }
  | { status: "success"; data: ConditionPresentation }
  | { status: "error"; message: string };

// --- Form finish response ---

export interface FinishFormResult {
  submission_id: string;
}

// --- Consultation outcome (Screen 2, OUTCOME) ---

// SYNC OBLIGATION: This type must exactly match the "value" strings in
// consultation_outcomes.json. It cannot be derived automatically from the JSON
// because JSON imports do not produce discriminated union types.
//
// When adding a new outcome:
//   1. Add the entry to consultation_outcomes.json
//   2. Add the value string to this union type
//   3. Add the value string to VALID_OUTCOME_VALUES in consultation_outcomes.py
//
// Renaming or removing existing values is a breaking change — stored submissions
// contain these strings verbatim.
export type ConsultationOutcome =
  | "admin_task"
  | "face_to_face"
  | "phone_appointment"
  | "advice_only"
  | "medication"
  | "not_sure";

// --- Contact preferences (Screen 5) ---

export type ContactMethod = "email" | "text" | "phone";

export type DoctorPreference = "any" | "usual";

export interface ContactPreferences {
  contact_methods: ContactMethod[];          // min length 1
  email_address: string | null;             // required if "email" in contact_methods
  phone_number: string | null;              // required if "text" or "phone" in contact_methods
  best_time_to_call: string | null;         // required if "phone" in contact_methods
  doctor_preference: DoctorPreference;
  usual_doctor_name: string | null;         // required if doctor_preference === "usual"
  // consultation_outcome is optional here because ContactPreferences is also used as
  // the local form state type inside ContactScreen (via initialiseContactPreferences),
  // where the outcome is not yet known. The value is always set on the wire payload
  // in ContactScreen.validateAndSubmit before calling finishForm. The backend will
  // reject a missing value with a 422.
  consultation_outcome?: ConsultationOutcome;
}

// --- Patient details (Screen 1, immediately after safety warning) ---

// Wire format sent from frontend to backend.
// Each field is a string containing only digits — validated client-side before
// submission. The backend validates numeric content and assembles into a date.
export interface DateOfBirth {
  day: string;
  month: string;
  year: string;
}

// SYNC OBLIGATION: Gender values must exactly match VALID_GENDER_VALUES in
// request_validation.py. If values are added or renamed, update both.
export type Gender = "male" | "female" | "other" | "prefer_not_to_say";

export interface PatientDetails {
  patient_for: "me" | "someone_else";
  first_name: string;
  last_name: string;
  date_of_birth: DateOfBirth;
  postcode: string;
  gender: Gender;                  // required
  preferred_name?: string;         // optional — only sent if non-empty
  nhs_number?: string;             // optional — only sent if non-empty; digits only, spaces stripped
  submitter_name?: string;         // required when patient_for === "someone_else"
  submitter_relationship?: string; // required when patient_for === "someone_else"
}
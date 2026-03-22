// Frontend-visible contracts only

export type AnswerType = "boolean" | "text";

export interface ClientQuestion {
  answer_key: string;
  question_text: string;
  answer_type: AnswerType;
  current_value: boolean | string | null;
  required: boolean;
  suggested: boolean;
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
  answers: Record<string, boolean | string | null>;
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

// Discriminated union for the practice name fetch lifecycle.
// Stored as a single state variable in App.tsx.
// Guard: if (practiceNameFetchState.status === "success") return — prevents re-fetch.
// Retry: reset to { status: "loading" } to trigger a new fetch.
// The practice name fetch is fail-closed: the Continue button on SafetyWarningScreen
// is disabled until this reaches "success".
export type PracticeNameFetchState =
  | { status: "loading" }
  | { status: "success"; name: string }
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

export interface PatientDetails {
  patient_for: "me" | "someone_else";
  first_name: string;
  last_name: string;
  date_of_birth: DateOfBirth;
  postcode: string;
  submitter_name?: string;       // required when patient_for === "someone_else"
  submitter_relationship?: string; // required when patient_for === "someone_else"
}
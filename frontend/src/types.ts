// Wire-format types. These are serialised and sent to / received from the server.
// UI-only types live in uiTypes.ts.

// ---------------------------------------------------------------------------
// Consultation outcome
// ---------------------------------------------------------------------------
//
// ConsultationOutcome is a union of the value strings defined in
// consultation_outcomes.json. This type must be kept in sync with that file
// manually — TypeScript cannot derive a discriminated union from a JSON import.
//
// VALUE STRINGS ARE IMMUTABLE once the system has live data. Adding new values
// requires updating both this type and consultation_outcomes.json. Renaming or
// removing values is a breaking change against stored database records.
//
// The backend validates incoming values against the same JSON file via
// app/core/consultation_outcomes.py.

export type ConsultationOutcome =
  | "admin_task"
  | "face_to_face"
  | "phone_appointment"
  | "advice_only"
  | "medication"
  | "not_sure";

// ---------------------------------------------------------------------------
// Contact preferences
// ---------------------------------------------------------------------------

export type ContactMethod = "email" | "text" | "phone";

export interface ContactPreferences {
  contact_methods: ContactMethod[];
  email_address: string | null;
  phone_number: string | null;
  best_time_to_call: string | null;
  doctor_preference: "any" | "usual";
  usual_doctor_name: string | null;
  consultation_outcome: ConsultationOutcome;
}

// ---------------------------------------------------------------------------
// Patient details
// ---------------------------------------------------------------------------

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
  submitter_name?: string | null;
  submitter_relationship?: string | null;
}

// ---------------------------------------------------------------------------
// API response shapes
// ---------------------------------------------------------------------------

export interface SafetyWarning {
  universal_safety_warning: string;
}

export interface AvailabilityResult {
  is_open: boolean;
  closed_message: string | null;
  after_hours_notice: string | null;
}

export interface ConditionSummary {
  id: string;
  label: string;
}

export interface QuestionView {
  answer_key: string;
  question_text: string;
  answer_type: string;
  current_value: boolean | string | null;
  is_required: boolean;
  options?: string[];
}

export interface ClientStateView {
  condition_id: string;
  condition_label: string;
  questions: QuestionView[];
  additional_text: string | null;
}

export interface SafetyMessage {
  id: string;
  text: string;
}

export interface ConditionPresentation {
  condition_id: string;
  condition_label: string;
  framing_text: string | null;
  universal_safety_warning: string;
}

export interface ClientAnswerReturn {
  runtime_id: string;
  base_version: number;
  answers: Record<string, boolean | string | null>;
  additional_text: string | null;
}

export interface FinishFormResult {
  submission_id: string;
}

// ---------------------------------------------------------------------------
// Fetch state discriminated unions (Screen 0)
// ---------------------------------------------------------------------------

export type SafetyWarningFetchState =
  | { status: "loading" }
  | { status: "success"; text: string }
  | { status: "error"; message: string };

export type PracticeNameFetchState =
  | { status: "loading" }
  | { status: "success"; name: string }
  | { status: "error"; message: string };

// ---------------------------------------------------------------------------
// Presentation state discriminated union (Screen 3)
// ---------------------------------------------------------------------------

export type PresentationState =
  | { status: "loading" }
  | { status: "success"; data: ConditionPresentation }
  | { status: "error"; message: string };
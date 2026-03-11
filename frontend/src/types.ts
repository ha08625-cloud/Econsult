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

// --- Contact preferences (Screen 4) ---

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

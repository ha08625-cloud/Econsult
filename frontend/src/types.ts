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
  practice_signposting?: string[];
}

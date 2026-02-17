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
  questions: ClientQuestion[];
}

export interface ClientAnswerReturn {
  runtime_id: string;
  base_version: number;
  answers: Record<string, boolean | string | null>;
}

export interface SafetyMessage {
  rule_id: string;
  message: string;
}

// --- Condition discovery and presentation (Screens 0-1 only) ---

export interface ConditionSummary {
  id: string;
  label: string;
}

export interface ConditionPresentation {
  label: string;
  free_text_prompt?: string;
  universal_safety_warning: string;
  practice_signposting?: string[];
}

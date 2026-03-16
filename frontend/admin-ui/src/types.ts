/**
 * types.ts — admin portal type definitions.
 */
export interface ConditionSummary {
  id: string;
  label: string;
}
export type SaveStatus = {
  type: "success" | "error";
  text: string;
};
export interface AvailabilityConfig {
  practice_id: string;
  is_active: boolean;
  weekly_open_days: string[];
  open_time: string;
  close_time: string;
  closed_message: string | null;
  override_status: string | null;
  override_expires_at: string | null;
  override_message: string | null;
}
export interface AvailabilityException {
  exception_date: string;   // YYYY-MM-DD
  exception_type: "closed" | "custom_hours";
  open_time: string | null; // HH:MM or null
  close_time: string | null; // HH:MM or null
  note: string | null;
}

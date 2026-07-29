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

// ---------------------------------------------------------------------------
// Audit log
// ---------------------------------------------------------------------------

/**
 * A single audit log event as returned by GET /admin/audit-log.
 *
 * detail shape varies by action type — see AuditRepository module docstring
 * for the per-action contract. The frontend treats detail as an opaque object
 * and renders it structurally without interpreting action-specific semantics.
 *
 * There is no session_id field. The server records one per event but never
 * returns it: the stored value is the raw session cookie, so exposing it
 * would let one admin impersonate another.
 */
export interface AuditEvent {
  id: number;
  occurred_at: string;                        // ISO 8601 string
  actor_email: string;
  action: string;
  resource: string | null;
  detail: Record<string, unknown> | null;
  ip_address: string | null;
}

export interface AuditLogPage {
  events: AuditEvent[];
  next_cursor: string | null;
}

// ---------------------------------------------------------------------------
// Admin users
// ---------------------------------------------------------------------------

export interface AdminUser {
  id: string;
  email: string;
  is_current_user: boolean;
  last_login: string | null; // ISO 8601 string or null
  created_at: string;        // ISO 8601 string
}

export interface AddUserResponse {
  ok: boolean;
  email_sent: boolean;
}
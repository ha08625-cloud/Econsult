/**
 * api.ts — admin portal API helpers.
 *
 * Authentication is handled via an HttpOnly session cookie set by
 * POST /admin/auth/verify. No token is passed by callers — the browser
 * attaches the cookie automatically on every same-origin request.
 *
 * CSRF protection: X-Requested-With: XMLHttpRequest is sent on every
 * request. Browsers do not send custom headers cross-origin without a
 * CORS preflight, so this header is sufficient given a strict CORS policy.
 *
 * 401 handling: apiFetch throws AuthError on any 401 response. Callers
 * that need to handle session expiry catch AuthError specifically and
 * redirect to the login view.
 */

import type { ConditionSummary, AvailabilityConfig, AvailabilityException, AuditLogPage, AdminUser, AddUserResponse } from "./types";

// ---------------------------------------------------------------------------
// AuthError — thrown by apiFetch on any 401 response.
// Callers distinguish this from other errors to trigger a login redirect.
// ---------------------------------------------------------------------------

export class AuthError extends Error {
  constructor() {
    super("Session expired or not authenticated.");
    this.name = "AuthError";
  }
}

// ---------------------------------------------------------------------------
// Internal helpers
// ---------------------------------------------------------------------------

async function apiFetch(
  path: string,
  options: RequestInit = {}
): Promise<Response> {
  const res = await fetch(path, {
    ...options,
    credentials: "same-origin",
    headers: {
      "Content-Type": "application/json",
      "X-Requested-With": "XMLHttpRequest",
      ...(options.headers ?? {}),
    },
  });

  if (res.status === 401) {
    throw new AuthError();
  }

  return res;
}

/**
 * Extract a detail message from a non-ok response, or fall back to
 * a generic "Server error: {status}" string.
 *
 * All backend error responses use the standard envelope:
 *   {"error": {"code": "...", "message": "..."}}
 */
async function extractErrorDetail(res: Response): Promise<string> {
  let detail = `Server error: ${res.status}`;
  try {
    const body = await res.json();
    if (body.error?.message) detail = body.error.message;
  } catch (_) {
    // ignore parse errors
  }
  return detail;
}

// ---------------------------------------------------------------------------
// Auth endpoints (no session required)
// ---------------------------------------------------------------------------

/**
 * Step 1 of 2-factor login: submit email and password.
 *
 * On success, the server has generated an OTP and queued its delivery.
 * The caller should transition to the OTP entry screen.
 *
 * Throws an Error on any failure (422 INVALID_CREDENTIALS, 429 rate limit).
 * The error message is safe to display to the user.
 */
export async function login(email: string, password: string): Promise<void> {
  const res = await fetch("/admin/auth/login", {
    method: "POST",
    credentials: "same-origin",
    headers: {
      "Content-Type": "application/json",
      "X-Requested-With": "XMLHttpRequest",
    },
    body: JSON.stringify({ email, password }),
  });

  if (!res.ok) {
    throw new Error(await extractErrorDetail(res));
  }
}

/**
 * Verify a 6-digit MFA code. On success the server sets an HttpOnly
 * session cookie — no further action is needed by the caller.
 *
 * Throws an Error with a descriptive message on failure (422).
 */
export async function verifyMfaCode(email: string, code: string): Promise<void> {
  const res = await fetch("/admin/auth/verify", {
    method: "POST",
    credentials: "same-origin",
    headers: {
      "Content-Type": "application/json",
      "X-Requested-With": "XMLHttpRequest",
    },
    body: JSON.stringify({ email, code }),
  });

  if (!res.ok) {
    throw new Error(await extractErrorDetail(res));
  }
}

/**
 * Request a password reset/setup link for the given email address.
 *
 * Always resolves without throwing — the server always returns 200
 * regardless of whether the email is registered, to prevent enumeration.
 * Errors (network, 429) are silently swallowed; the UI displays a
 * generic confirmation message in all cases.
 */
export async function requestPasswordReset(email: string): Promise<void> {
  try {
    await fetch("/admin/auth/request-reset", {
      method: "POST",
      credentials: "same-origin",
      headers: {
        "Content-Type": "application/json",
        "X-Requested-With": "XMLHttpRequest",
      },
      body: JSON.stringify({ email }),
    });
  } catch (_) {
    // Network failure is silently ignored — the UI shows the same generic
    // message regardless.
  }
}

/**
 * Set a new password using a password reset/setup token.
 *
 * token is the raw value extracted from the #reset:{token} URL hash fragment.
 *
 * Throws an Error on failure:
 * - 422 INVALID_RESET_TOKEN: link has expired or was already used.
 * - 422 WEAK_PASSWORD: password does not meet strength requirements.
 *   The error message contains specific guidance from zxcvbn.
 * - 422 INVALID_PAYLOAD: validation error (length, format).
 */
export async function setPassword(token: string, password: string): Promise<void> {
  const res = await fetch("/admin/auth/set-password", {
    method: "POST",
    credentials: "same-origin",
    headers: {
      "Content-Type": "application/json",
      "X-Requested-With": "XMLHttpRequest",
    },
    body: JSON.stringify({ token, password }),
  });

  if (!res.ok) {
    throw new Error(await extractErrorDetail(res));
  }
}

/**
 * Log out by asking the server to delete the session and clear the cookie.
 * Always resolves — logout errors are non-fatal.
 */
export async function logout(): Promise<void> {
  try {
    await fetch("/admin/auth/logout", {
      method: "POST",
      credentials: "same-origin",
      headers: { "X-Requested-With": "XMLHttpRequest" },
    });
  } catch (_) {
    // Network failure during logout is silently ignored.
    // The session will expire naturally on the server.
  }
}

// ---------------------------------------------------------------------------
// Conditions
// ---------------------------------------------------------------------------

/**
 * Fetches the list of conditions.
 * Throws AuthError if the session has expired.
 * Throws a descriptive error string for other failures.
 */
export async function fetchConditions(): Promise<ConditionSummary[]> {
  const res = await apiFetch("/admin/conditions");
  if (!res.ok) throw new Error(`Server error: ${res.status}`);
  const data = await res.json();
  return data.conditions as ConditionSummary[];
}

// ---------------------------------------------------------------------------
// Signposting
// ---------------------------------------------------------------------------

/**
 * Fetches the signposting HTML for a condition.
 * Returns null if none is configured.
 */
export async function fetchSignposting(
  conditionId: string
): Promise<string | null> {
  const res = await apiFetch(
    `/admin/conditions/${encodeURIComponent(conditionId)}/signposting`
  );
  if (!res.ok) throw new Error(await extractErrorDetail(res));
  const data = await res.json();
  return data.signposting ?? null;
}

/**
 * Sends signposting HTML to the PUT endpoint.
 * Returns the sanitised HTML the server actually stored, or null if cleared.
 */
export async function putSignposting(
  conditionId: string,
  htmlString: string
): Promise<string | null> {
  const res = await apiFetch(
    `/admin/conditions/${encodeURIComponent(conditionId)}/signposting`,
    {
      method: "PUT",
      body: JSON.stringify({ signposting: htmlString }),
    }
  );
  if (!res.ok) {
    throw new Error(await extractErrorDetail(res));
  }
  const data = await res.json();
  return data.signposting ?? null;
}

// ---------------------------------------------------------------------------
// Practice
// ---------------------------------------------------------------------------

export interface PracticeDetails {
  practice_id: string;
  name: string;
  email: string;
}

/**
 * Fetches current practice details (practice_id, name, email).
 */
export async function getPractice(): Promise<PracticeDetails> {
  const res = await apiFetch("/admin/practice");
  if (!res.ok) throw new Error(await extractErrorDetail(res));
  return (await res.json()) as PracticeDetails;
}

/**
 * Updates the practice email address.
 * Returns the updated practice details on success.
 */
export async function updatePracticeEmail(email: string): Promise<PracticeDetails> {
  const res = await apiFetch("/admin/practice/email", {
    method: "PUT",
    body: JSON.stringify({ email }),
  });
  if (!res.ok) {
    throw new Error(await extractErrorDetail(res));
  }
  return (await res.json()) as PracticeDetails;
}

// ---------------------------------------------------------------------------
// Doctor list
// ---------------------------------------------------------------------------

/**
 * Fetches the current doctor list for the practice.
 * Returns an empty array if no doctors are configured.
 */
export async function getDoctors(): Promise<string[]> {
  const res = await apiFetch("/admin/doctors");
  if (!res.ok) throw new Error(await extractErrorDetail(res));
  const data = await res.json();
  return data.doctors as string[];
}

/**
 * Replaces the doctor list for the practice.
 * An empty array is valid — it clears the list entirely.
 * Returns the saved list as confirmed by the server.
 */
export async function putDoctors(doctors: string[]): Promise<string[]> {
  const res = await apiFetch("/admin/doctors", {
    method: "PUT",
    body: JSON.stringify({ doctors }),
  });
  if (!res.ok) {
    throw new Error(await extractErrorDetail(res));
  }
  const data = await res.json();
  return data.doctors as string[];
}

// ---------------------------------------------------------------------------
// Availability
// ---------------------------------------------------------------------------

/**
 * Fetches the current availability configuration.
 */
export async function fetchAvailability(): Promise<AvailabilityConfig> {
  const res = await apiFetch("/admin/availability");
  if (!res.ok) throw new Error(await extractErrorDetail(res));
  return (await res.json()) as AvailabilityConfig;
}

/**
 * Updates the availability configuration.
 * Returns the updated config as stored by the server.
 */
export async function putAvailability(config: {
  is_active: boolean;
  weekly_open_days: string[];
  open_time: string;
  close_time: string;
  closed_message: string | null;
}): Promise<AvailabilityConfig> {
  const res = await apiFetch("/admin/availability", {
    method: "PUT",
    body: JSON.stringify(config),
  });
  if (!res.ok) {
    throw new Error(await extractErrorDetail(res));
  }
  return (await res.json()) as AvailabilityConfig;
}

// ---------------------------------------------------------------------------
// Override
// ---------------------------------------------------------------------------

/**
 * Set a manual override (force-open or force-closed).
 * expires_at must be a UTC ISO datetime string.
 * Returns the updated raw config.
 */
export async function postOverride(override: {
  status: string;
  expires_at: string;
  message: string | null;
}): Promise<AvailabilityConfig> {
  const res = await apiFetch("/admin/availability/override", {
    method: "POST",
    body: JSON.stringify(override),
  });
  if (!res.ok) {
    throw new Error(await extractErrorDetail(res));
  }
  return (await res.json()) as AvailabilityConfig;
}

/**
 * Clear any active override. Idempotent.
 * Returns the updated raw config.
 */
export async function deleteOverride(): Promise<AvailabilityConfig> {
  const res = await apiFetch("/admin/availability/override", {
    method: "DELETE",
  });
  if (!res.ok) {
    throw new Error(await extractErrorDetail(res));
  }
  return (await res.json()) as AvailabilityConfig;
}

// ---------------------------------------------------------------------------
// Per-date exceptions
// ---------------------------------------------------------------------------

/**
 * Fetches all exceptions on or after today.
 */
export async function fetchExceptions(): Promise<AvailabilityException[]> {
  const res = await apiFetch("/admin/availability/exceptions");
  if (!res.ok) throw new Error(await extractErrorDetail(res));
  const data = await res.json();
  return data.exceptions as AvailabilityException[];
}

/**
 * Create or update an exception for a specific date.
 */
export async function putException(
  date: string,
  exception: {
    exception_type: string;
    open_time: string | null;
    close_time: string | null;
    note: string | null;
  }
): Promise<AvailabilityException> {
  const res = await apiFetch(
    `/admin/availability/exceptions/${encodeURIComponent(date)}`,
    {
      method: "PUT",
      body: JSON.stringify(exception),
    }
  );
  if (!res.ok) {
    throw new Error(await extractErrorDetail(res));
  }
  return (await res.json()) as AvailabilityException;
}

/**
 * Delete an exception for a specific date. Idempotent.
 */
export async function deleteException(date: string): Promise<void> {
  const res = await apiFetch(
    `/admin/availability/exceptions/${encodeURIComponent(date)}`,
    { method: "DELETE" }
  );
  if (!res.ok) {
    throw new Error(await extractErrorDetail(res));
  }
}

// ---------------------------------------------------------------------------
// Audit log
// ---------------------------------------------------------------------------

export interface FetchAuditLogParams {
  cursor?: string;
  from_date?: string;
  to_date?: string;
  actor?: string;
  action?: string;
  limit?: number;
}

/**
 * Fetch a page of audit log events.
 *
 * All parameters are optional. Omitting cursor starts from the most recent
 * event. Pass the next_cursor from a previous response to load the next page.
 *
 * Throws AuthError on 401. Throws a descriptive Error on other failures.
 */
export async function fetchAuditLog(
  params: FetchAuditLogParams = {}
): Promise<AuditLogPage> {
  const qs = new URLSearchParams();
  if (params.cursor   !== undefined) qs.set("cursor",    params.cursor);
  if (params.from_date !== undefined) qs.set("from_date", params.from_date);
  if (params.to_date   !== undefined) qs.set("to_date",   params.to_date);
  if (params.actor     !== undefined) qs.set("actor",     params.actor);
  if (params.action    !== undefined) qs.set("action",    params.action);
  if (params.limit     !== undefined) qs.set("limit",     String(params.limit));

  const path = `/admin/audit-log${qs.toString() ? `?${qs.toString()}` : ""}`;
  const res = await apiFetch(path);
  if (!res.ok) throw new Error(await extractErrorDetail(res));
  return (await res.json()) as AuditLogPage;
}

// ---------------------------------------------------------------------------
// Admin users
// ---------------------------------------------------------------------------

/**
 * Fetches the list of admin users for the current practice.
 * Throws AuthError on 401. Throws a descriptive Error on other failures.
 */
export async function fetchUsers(): Promise<AdminUser[]> {
  const res = await apiFetch("/admin/users");
  if (!res.ok) throw new Error(await extractErrorDetail(res));
  return (await res.json()) as AdminUser[];
}

/**
 * Adds a new admin user with the given email address.
 * Returns ok: true on success. email_sent indicates whether the invitation
 * email was delivered — callers should warn the user if false.
 * Throws the server error message string on failure (covers domain rejection,
 * duplicate email, and any other APIError from the envelope).
 */
export async function addUser(email: string): Promise<AddUserResponse> {
  const res = await apiFetch("/admin/users", {
    method: "POST",
    body: JSON.stringify({ email }),
  });
  if (!res.ok) throw new Error(await extractErrorDetail(res));
  return (await res.json()) as AddUserResponse;
}

/**
 * Deletes the admin user with the given id.
 * Throws the server error message string on failure (covers self-deletion
 * attempt, last-user guard, and not-found).
 */
export async function removeUser(id: string): Promise<void> {
  const res = await apiFetch(`/admin/users/${encodeURIComponent(id)}`, {
    method: "DELETE",
  });
  if (!res.ok) throw new Error(await extractErrorDetail(res));
}

/**
 * Resends the invitation email for the user with the given id.
 * Returns ok: true on success. email_sent indicates whether delivery succeeded.
 * Throws the server error message string on failure (covers not-found).
 */
export async function resendInvitation(id: string): Promise<AddUserResponse> {
  const res = await apiFetch(
    `/admin/users/${encodeURIComponent(id)}/resend-invitation`,
    { method: "POST" }
  );
  if (!res.ok) throw new Error(await extractErrorDetail(res));
  return (await res.json()) as AddUserResponse;
}
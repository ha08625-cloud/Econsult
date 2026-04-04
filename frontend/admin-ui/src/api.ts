/**
 * api.ts — admin portal API helpers.
 *
 * Authentication is now handled via an HttpOnly session cookie set by
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

import type { ConditionSummary, AvailabilityConfig, AvailabilityException } from "./types";

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
 * The body.detail path has been removed — FastAPI HTTPExceptions are now
 * reshaped into the standard envelope by the handler in main.py.
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
 * Request an MFA code to be sent to the given email address.
 *
 * Returns normally on success (including when the email is unregistered —
 * the server always returns 200 to prevent enumeration).
 * Throws on domain rejection (422) or rate limit (429).
 */
export async function requestMfaCode(email: string): Promise<void> {
  const res = await fetch("/admin/auth/request-code", {
    method: "POST",
    credentials: "same-origin",
    headers: {
      "Content-Type": "application/json",
      "X-Requested-With": "XMLHttpRequest",
    },
    body: JSON.stringify({ email }),
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
/**
 * api.ts — admin portal API helpers.
 *
 * All requests include a Bearer token in the Authorization header.
 * The server validates this token via admin_context.py.
 */

import type { ConditionSummary, AvailabilityConfig, AvailabilityException } from "./types";

async function apiFetch(
  path: string,
  token: string,
  options: RequestInit = {}
): Promise<Response> {
  return fetch(path, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${token}`,
      ...(options.headers ?? {}),
    },
  });
}

/**
 * Extract a detail message from a non-ok response, or fall back to
 * a generic "Server error: {status}" string.
 *
 * Handles two error shapes:
 * - HTTPException format: {"detail": "..."}
 * - APIError format:      {"error": {"code": "...", "message": "..."}}
 */
async function extractErrorDetail(res: Response): Promise<string> {
  let detail = `Server error: ${res.status}`;
  try {
    const body = await res.json();
    if (body.detail) detail = body.detail;
    else if (body.error?.message) detail = body.error.message;
  } catch (_) {
    // ignore parse errors
  }
  return detail;
}

/**
 * Fetches the list of conditions.
 * Throws "UNAUTHORIZED" if the token is rejected.
 * Throws a descriptive error string for other failures.
 */
export async function fetchConditions(token: string): Promise<ConditionSummary[]> {
  const res = await apiFetch("/admin/conditions", token);
  if (res.status === 401) throw new Error("UNAUTHORIZED");
  if (!res.ok) throw new Error(`Server error: ${res.status}`);
  const data = await res.json();
  return data.conditions as ConditionSummary[];
}

/**
 * Fetches the signposting HTML for a condition.
 * Returns null if none is configured.
 */
export async function fetchSignposting(
  conditionId: string,
  token: string
): Promise<string | null> {
  const res = await apiFetch(
    `/admin/conditions/${encodeURIComponent(conditionId)}/signposting`,
    token
  );
  if (!res.ok) throw new Error(await extractErrorDetail(res));
  const data = await res.json();
  return data.signposting ?? null;
}

/**
 * Sends signposting HTML to the PUT endpoint.
 * Empty content is handled server-side: the repository deletes the row
 * and returns {"signposting": null}. The router never returns an error for
 * empty content.
 * Returns the sanitised HTML the server actually stored, or null if cleared.
 */
export async function putSignposting(
  conditionId: string,
  token: string,
  htmlString: string
): Promise<string | null> {
  const res = await apiFetch(
    `/admin/conditions/${encodeURIComponent(conditionId)}/signposting`,
    token,
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
export async function getPractice(token: string): Promise<PracticeDetails> {
  const res = await apiFetch("/admin/practice", token);
  if (!res.ok) throw new Error(await extractErrorDetail(res));
  return (await res.json()) as PracticeDetails;
}

/**
 * Updates the practice email address.
 * Throws a descriptive error string on validation failure (422) or other
 * server errors. Returns the updated practice details on success.
 */
export async function updatePracticeEmail(
  token: string,
  email: string
): Promise<PracticeDetails> {
  const res = await apiFetch("/admin/practice/email", token, {
    method: "PUT",
    body: JSON.stringify({ email }),
  });
  if (!res.ok) {
    throw new Error(await extractErrorDetail(res));
  }
  return (await res.json()) as PracticeDetails;
}

// ---------------------------------------------------------------------------
// Availability
// ---------------------------------------------------------------------------

/**
 * Fetches the current availability configuration.
 */
export async function fetchAvailability(
  token: string
): Promise<AvailabilityConfig> {
  const res = await apiFetch("/admin/availability", token);
  if (!res.ok) throw new Error(await extractErrorDetail(res));
  return (await res.json()) as AvailabilityConfig;
}

/**
 * Updates the availability configuration.
 * Returns the updated config as stored by the server.
 */
export async function putAvailability(
  token: string,
  config: {
    is_active: boolean;
    weekly_open_days: string[];
    open_time: string;
    close_time: string;
    closed_message: string | null;
  }
): Promise<AvailabilityConfig> {
  const res = await apiFetch("/admin/availability", token, {
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
export async function postOverride(
  token: string,
  override: {
    status: string;
    expires_at: string;
    message: string | null;
  }
): Promise<AvailabilityConfig> {
  const res = await apiFetch("/admin/availability/override", token, {
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
export async function deleteOverride(
  token: string
): Promise<AvailabilityConfig> {
  const res = await apiFetch("/admin/availability/override", token, {
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
 * Fetches all exceptions on or after today (server determines today
 * in Europe/London time). Ordered by date ascending.
 */
export async function fetchExceptions(
  token: string
): Promise<AvailabilityException[]> {
  const res = await apiFetch("/admin/availability/exceptions", token);
  if (!res.ok) throw new Error(await extractErrorDetail(res));
  const data = await res.json();
  return data.exceptions as AvailabilityException[];
}

/**
 * Create or update an exception for a specific date.
 * Returns the stored exception.
 */
export async function putException(
  token: string,
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
    token,
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
export async function deleteException(
  token: string,
  date: string
): Promise<void> {
  const res = await apiFetch(
    `/admin/availability/exceptions/${encodeURIComponent(date)}`,
    token,
    { method: "DELETE" }
  );
  if (!res.ok) {
    throw new Error(await extractErrorDetail(res));
  }
}
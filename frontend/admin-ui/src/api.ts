/**
 * api.ts — admin portal API helpers.
 *
 * All requests include a Bearer token in the Authorization header.
 * The server validates this token via admin_context.py.
 */

import type { ConditionSummary } from "./types";

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
  if (!res.ok) throw new Error(`Server error: ${res.status}`);
  const data = await res.json();
  return data.signposting ?? null;
}

/**
 * Sends signposting HTML to the PUT endpoint.
 * Empty content is handled server-side: the repository deletes the row
 * and returns {"signposting": null}. The router never returns 400 for
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
    let detail = `Server error: ${res.status}`;
    try {
      const body = await res.json();
      if (body.detail) detail = body.detail;
    } catch (_) {
      // ignore parse errors
    }
    throw new Error(detail);
  }
  const data = await res.json();
  return data.signposting ?? null;
}

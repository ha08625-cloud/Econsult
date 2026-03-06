import type {
  ClientAnswerReturn,
  ClientStateView,
  ConditionSummary,
  ConditionPresentation,
  SafetyMessage,
} from "./types";

const API_BASE = ""; // same-origin

async function postJson<T>(url: string, body: unknown): Promise<T> {
  const res = await fetch(API_BASE + url, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(body),
  });

  if (!res.ok) {
    throw new Error(`HTTP ${res.status}`);
  }

  return (await res.json()) as T;
}

async function getJson<T>(url: string): Promise<T> {
  const res = await fetch(API_BASE + url, {
    method: "GET",
    headers: {
      Accept: "application/json",
    },
  });

  if (!res.ok) {
    throw new Error(`HTTP ${res.status}`);
  }

  return (await res.json()) as T;
}

// -------------------------------
// Condition discovery (Screens 0-1)
// -------------------------------

export async function getConditions(): Promise<{
  conditions: ConditionSummary[];
}> {
  return getJson("/conditions");
}

export async function getConditionPresentation(
  conditionId: string
): Promise<ConditionPresentation> {
  return getJson(`/conditions/${encodeURIComponent(conditionId)}/presentation`);
}

// -------------------------------
// Form session endpoints
// -------------------------------

export async function initForm(conditionId: string, freeText: string | null): Promise<{
  runtime_id: string;
  version: number;
  client_state: ClientStateView;
}> {
  return postJson("/form/init", {
    condition_id: conditionId,
    free_text: freeText,
  });
}

export async function updateForm(payload: ClientAnswerReturn): Promise<{
  runtime_id: string;
  version: number;
  client_state: ClientStateView;
  safety_messages: SafetyMessage[];
}> {
  return postJson("/form/update", payload);
}

export async function finishForm(runtimeId: string, version: number): Promise<{
  submission_id: string;
}> {
  return postJson("/form/finish", {
    runtime_id: runtimeId,
    version: version,
  });
}
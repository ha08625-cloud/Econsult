import { ClientAnswerReturn, ClientStateView, SafetyMessage } from "./types";

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

// -------------------------------
// API endpoints
// -------------------------------

export async function initForm(condition: string, freeText: string | null): Promise<{
  runtime_id: string;
  version: number;
  client_state: ClientStateView;
}> {
  return postJson("/form/init", {
    condition,
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

export async function finishForm(payload: ClientAnswerReturn): Promise<{
  submission_id: string;
}> {
  return postJson("/form/finish", payload);
}

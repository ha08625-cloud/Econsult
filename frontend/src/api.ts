import type {
  ClientAnswerReturn,
  ClientStateView,
  ConditionSummary,
  ConditionPresentation,
  SafetyMessage,
  SafetyWarning,
  AvailabilityResult,
  ContactPreferences,
  FinishFormResult,
} from "./types";

const API_BASE = "BROKEN"; // same-origin

// ---------------------------------
// Typed error
// ---------------------------------

export class ApiError extends Error {
  status: number | null;
  detail: string | null;

  constructor(message: string, status: number | null, detail: string | null = null) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
  }
}

export function friendlyErrorMessage(e: unknown): string {
  if (e instanceof ApiError) {
    if (e.status === 503 && e.detail) {
      // 503 from POST /form/init — practice is closed.
      // detail contains the closed_message from the server.
      return e.detail;
    }
    if (e.status === 409) {
      return "Please check you do not have this form open in another tab. If you do, close the other tab and try again.";
    }
    if (e.status !== null && e.status >= 500) {
      return "The server encountered a problem. Please try again in a moment.";
    }
    return "Something went wrong. Please try again.";
  }
  // fetch() itself threw — likely a network failure
  return "Could not reach the server. Please check your internet connection and try again.";
}

// ---------------------------------
// Internal helpers
// ---------------------------------

async function postJson<T>(url: string, body: unknown): Promise<T> {
  let res: Response;
  try {
    res = await fetch(API_BASE + url, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(body),
    });
  } catch {
    throw new ApiError("Network failure", null);
  }

  if (!res.ok) {
    // For 503 responses, extract the detail field for the closed message.
    if (res.status === 503) {
      let detail: string | null = null;
      try {
        const body = await res.json();
        detail = body.detail ?? null;
      } catch {
        // If we can't parse the body, proceed with null detail.
      }
      throw new ApiError(`HTTP ${res.status}`, res.status, detail);
    }
    throw new ApiError(`HTTP ${res.status}`, res.status);
  }

  return (await res.json()) as T;
}

async function getJson<T>(url: string): Promise<T> {
  let res: Response;
  try {
    res = await fetch(API_BASE + url, {
      method: "GET",
      headers: {
        Accept: "application/json",
      },
    });
  } catch {
    throw new ApiError("Network failure", null);
  }

  if (!res.ok) {
    throw new ApiError(`HTTP ${res.status}`, res.status);
  }

  return (await res.json()) as T;
}

// ---------------------------------
// Pre-session safety gate (Screen 0)
// ---------------------------------

export async function getSafetyWarning(): Promise<SafetyWarning> {
  return getJson("/safety-warning");
}

// ---------------------------------
// Availability (Screen 0)
// ---------------------------------

export async function getAvailability(): Promise<AvailabilityResult> {
  return getJson("/availability");
}

// ---------------------------------
// Condition discovery (Screens 1-2)
// ---------------------------------

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

// ---------------------------------
// Form session endpoints
// ---------------------------------

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

export async function finishForm(
  runtimeId: string,
  version: number,
  contactPreferences: ContactPreferences,
): Promise<FinishFormResult> {
  return postJson("/form/finish", {
    runtime_id: runtimeId,
    version: version,
    contact_preferences: contactPreferences,
  });
}

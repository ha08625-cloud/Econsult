import type {
  ClientAnswerReturn,
  ClientStateView,
  ConditionSummary,
  ConditionPresentation,
  SafetyMessage,
  SafetyWarning,
  AvailabilityResult,
  ContactPreferences,
  PatientDetails,
  FinishFormResult,
} from "./types";
import { friendlyPhotoErrorMessage } from "./helpers";

const API_BASE = ""; // same-origin

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
    if (e.status === 422 && e.detail) {
      // 422 from POST /form/finish — server-side photo validation failure.
      // Attempt to convert the technical server string into patient-friendly
      // instructions. Falls back to the generic message for unrecognised strings.
      const photoMessage = friendlyPhotoErrorMessage(e.detail);
      if (photoMessage !== null) {
        return photoMessage;
      }
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
// Practice identity (Screen 0)
// ---------------------------------

export async function getPractice(): Promise<{ practice_name: string }> {
  return getJson("/practice");
}

// ---------------------------------
// Availability (Screen 0)
// ---------------------------------

export async function getAvailability(): Promise<AvailabilityResult> {
  return getJson("/availability");
}

// ---------------------------------
// Doctor list (Screen 0 — fetched at session start)
// ---------------------------------

/**
 * Fetches the doctor list from GET /doctors.
 * Returns an empty array if the request fails for any reason — the caller
 * must treat failure as "no list configured" and fall back to free text.
 * This function never throws; errors are silently swallowed.
 */
export async function getDoctors(): Promise<string[]> {
  try {
    const data = await getJson<{ doctors: string[] }>("/doctors");
    return data.doctors;
  } catch {
    return [];
  }
}

// ---------------------------------
// Condition discovery (Screens 2-3)
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

/**
 * Submits the completed form as multipart/form-data.
 *
 * Do NOT use postJson here — postJson sets Content-Type: application/json,
 * which prevents the browser from setting the multipart boundary that the
 * server requires to parse the body. Pass a FormData object to fetch directly
 * and let the browser set Content-Type automatically.
 *
 * The JSON payload is sent as a plain string in the `payload` field.
 * Each photo File is appended as a separate `photos` field.
 * The server reads these in app/routers/form_router.py → form_finish.
 */
export async function finishForm(
  runtimeId: string,
  version: number,
  contactPreferences: ContactPreferences,
  patientDetails: PatientDetails,
  photos: File[],
): Promise<FinishFormResult> {
  const form = new FormData();

  form.append(
    "payload",
    JSON.stringify({
      runtime_id: runtimeId,
      version: version,
      contact_preferences: contactPreferences,
      patient_details: patientDetails,
    }),
  );

  for (const photo of photos) {
    form.append("photos", photo);
  }

  let res: Response;
  try {
    res = await fetch(API_BASE + "/form/finish", {
      method: "POST",
      body: form,
      // Do not set Content-Type — the browser sets it automatically with the
      // correct multipart boundary when a FormData object is passed as body.
    });
  } catch {
    throw new ApiError("Network failure", null);
  }

  if (!res.ok) {
    // For 422 responses, extract the detail field so friendlyErrorMessage can
    // convert photo validation errors into patient-friendly instructions.
    if (res.status === 422) {
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

  return (await res.json()) as FinishFormResult;
}
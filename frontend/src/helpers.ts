// Pure functions only. No React. No API calls. No side effects.

import type { ClientStateView, ContactPreferences } from "./types";

export function initialiseEditableAnswers(
  clientState: ClientStateView
): Record<string, boolean | string | null> {
  return clientState.questions.reduce((acc, q) => {
    acc[q.answer_key] = q.current_value ?? null;
    return acc;
  }, {} as Record<string, boolean | string | null>);
}

// Returns the contact-preference fields that belong to this screen's local
// form state. consultation_outcome is excluded because it is captured earlier
// on the OUTCOME screen and passed in as a prop to ContactScreen.
export function initialiseContactPreferences(): Omit<ContactPreferences, "consultation_outcome"> {
  return {
    contact_methods: [],
    email_address: null,
    phone_number: null,
    best_time_to_call: null,
    doctor_preference: "any",
    usual_doctor_name: null,
  };
}

/**
 * UK phone number client-side validation.
 * Strips spaces, checks starts with 07 or +44, length 10-13 digits.
 */
export function isValidUkPhone(value: string): boolean {
  const stripped = value.replace(/\s+/g, "");
  if (!/^\+?[\d]+$/.test(stripped)) return false;
  const digitsOnly = stripped.replace(/^\+44/, "0");
  return /^07\d{8,11}$/.test(digitsOnly) || /^0[1-9]\d{8,9}$/.test(digitsOnly);
}

/**
 * Converts a server-supplied 422 detail string from POST /form/finish into a
 * plain-English message suitable for display to patients.
 *
 * The server strings are defined in app/routers/form_router.py. If those
 * strings change, update the patterns here to match.
 *
 * Unrecognised strings — including 422s unrelated to photos — return null,
 * which signals the caller to fall back to the generic error message.
 */
export function friendlyPhotoErrorMessage(detail: string): string | null {
  if (detail.startsWith("Photo") && detail.includes("exceeds")) {
    return "One of your photos is too large to send. Please go back and remove it, then try again.";
  }
  if (detail.startsWith("Combined photo size")) {
    return "Your photos together are too large to send. Please go back and remove one or more, then try again.";
  }
  if (detail.startsWith("Too many photos")) {
    return "You have attached too many photos. Please go back and remove some, then try again.";
  }
  return null;
}
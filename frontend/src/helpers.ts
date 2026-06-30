// Pure functions only. No React. No API calls. No side effects.

import type {
  ClientStateView,
  ContactPreferences,
  QuantityValueView,
  UnitSystem,
} from "./types";

/**
 * One entry in the EditScreen's editable answers map. A quantity (unit-toggle)
 * question holds a QuantityValueView (system + string components) so the form
 * edits strings, exactly as the server sends them; every other question holds
 * its scalar value as before.
 */
export type EditableAnswerValue = boolean | string | QuantityValueView | null;
export type EditableAnswers = Record<string, EditableAnswerValue>;

/**
 * Component input keys per unit system. Mirrors the backend's _COMPONENT_KEYS
 * (weight only today): metric -> kg; imperial -> st, lb. A second quantity kind
 * would extend this together with the backend; that is the deferred epic.
 */
export const UNIT_COMPONENTS: Record<UnitSystem, readonly string[]> = {
  metric: ["kg"],
  imperial: ["st", "lb"],
};

/** Blank string components for a system, e.g. {st: "", lb: ""} for imperial. */
export function emptyComponents(system: UnitSystem): Record<string, string> {
  return UNIT_COMPONENTS[system].reduce(
    (acc, key) => {
      acc[key] = "";
      return acc;
    },
    {} as Record<string, string>
  );
}

export function initialiseEditableAnswers(
  clientState: ClientStateView
): EditableAnswers {
  return clientState.questions.reduce((acc, q) => {
    if (q.quantity) {
      const cv = q.current_value;
      if (cv && typeof cv === "object") {
        // Answered: current_value is a QuantityValueView with string components.
        // Copy the components so edits don't mutate the server-supplied object.
        acc[q.answer_key] = { system: cv.system, components: { ...cv.components } };
      } else {
        // Unanswered: seed from default_system (metric fallback) with blanks.
        const system: UnitSystem = q.default_system ?? "metric";
        acc[q.answer_key] = { system, components: emptyComponents(system) };
      }
    } else {
      acc[q.answer_key] = q.current_value ?? null;
    }
    return acc;
  }, {} as EditableAnswers);
}

/**
 * Seed the single shared unit toggle from the first quantity question: its
 * answered system if present, otherwise its default_system. Returns "metric"
 * when the form has no quantity question (the value is then unused).
 *
 * TODO(multi-quantity): with more than one quantity question whose defaults
 * could disagree there is no defined tie-break yet; the first question wins.
 * Revisit when a second quantity question is introduced.
 */
export function initialUnitSystem(clientState: ClientStateView): UnitSystem {
  const q = clientState.questions.find((x) => x.quantity);
  if (!q) return "metric";
  const cv = q.current_value;
  if (cv && typeof cv === "object") return cv.system;
  return q.default_system ?? "metric";
}

/**
 * Convert a quantity question's string components to the JSON-number payload
 * shape sent on /form/update. The caller must ensure components are non-empty
 * (the Continue gate enforces this); Number("") would otherwise become 0.
 */
export function quantityComponentsToNumbers(
  components: Record<string, string>
): Record<string, number> {
  return Object.fromEntries(
    Object.entries(components).map(([key, value]) => [key, Number(value)])
  );
}

export function initialiseContactPreferences(): ContactPreferences {
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
 * The server strings are defined in app/routers/form_router.py and
 * app/utils/image_sanitizer.py. If those strings change, update the patterns
 * here to match.
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
  // ImageTooLargeError from the high-tier CDR quality iteration fallback.
  // The server message already contains patient-facing instructions; pass it
  // through directly rather than replacing it with a generic string.
  if (detail.startsWith("Image could not be reduced")) {
    return detail;
  }
  return null;
}
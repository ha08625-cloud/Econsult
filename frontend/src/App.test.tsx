// File path: frontend/src/App_test.tsx
//
// New test file — App.tsx previously had no dedicated tests.
//
// Scope note: this file is deliberately scoped to the condition-selection /
// free-text-preservation feature covered in this piece of work (the
// ConditionCombobox mount-sync bug fix, confirmedConditionId, and the new
// condition-change warning modal). It drives the patient through
// SAFETY_WARNING -> PATIENT_DETAILS -> OUTCOME -> SELECT_CONDITION -> FREE_TEXT
// and back, but does not exercise EDIT / REVIEW / CONTACT / submission, photo
// upload, or error-path behaviour. Those would need their own test file(s)
// if and when that coverage is wanted.

import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi } from "vitest";
import App from "./App";
import type { ConditionSummary } from "./types";

vi.mock("./api", () => ({
  getSafetyWarning: vi.fn(),
  getPractice: vi.fn(),
  getAvailability: vi.fn(),
  getDoctors: vi.fn(),
  getConditions: vi.fn(),
  getConditionPresentation: vi.fn(),
  friendlyErrorMessage: (e: unknown) =>
    e instanceof Error ? e.message : "Unknown error",
}));

import {
  getSafetyWarning,
  getPractice,
  getAvailability,
  getDoctors,
  getConditions,
  getConditionPresentation,
} from "./api";

const mockGetSafetyWarning = vi.mocked(getSafetyWarning);
const mockGetPractice = vi.mocked(getPractice);
const mockGetAvailability = vi.mocked(getAvailability);
const mockGetDoctors = vi.mocked(getDoctors);
const mockGetConditions = vi.mocked(getConditions);
const mockGetConditionPresentation = vi.mocked(getConditionPresentation);

const sampleConditions: ConditionSummary[] = [
  { id: "uti1", label: "Urinary symptoms", search_tags: ["uti", "urine"] },
  { id: "back1", label: "Back pain", search_tags: ["back", "spine"] },
  { id: "skin1", label: "Skin rash", search_tags: ["rash", "skin"] },
];

function mockHappyApi() {
  mockGetSafetyWarning.mockResolvedValue({
    universal_safety_warning: "Call 999 if you have chest pain.\nSevere bleeding.",
  });
  mockGetPractice.mockResolvedValue({ practice_name: "Test Practice" });
  mockGetAvailability.mockResolvedValue({
    is_open: true,
    closed_message: null,
    after_hours_notice: null,
  });
  mockGetDoctors.mockResolvedValue({ doctors: [] });
  mockGetConditions.mockResolvedValue({ conditions: sampleConditions });
  mockGetConditionPresentation.mockImplementation(async (id: string) => {
    const cond = sampleConditions.find((c) => c.id === id);
    return {
      label: cond ? cond.label : "Tell us about your symptoms",
      universal_safety_warning: "ignored by the frontend",
    };
  });
}

// --- Navigation helpers ---
// Each drives one screen transition via real user interaction, matching the
// minimum required fields so PatientDetailsScreen's validation passes.

async function navigateToSelectCondition() {
  render(<App />);

  const checkbox = await screen.findByRole("checkbox");
  await userEvent.click(checkbox);
  const safetyContinue = await screen.findByRole("button", { name: /^continue$/i });
  await waitFor(() => expect(safetyContinue).not.toBeDisabled());
  await userEvent.click(safetyContinue);

  await screen.findByText(/about the patient/i);
  await userEvent.type(screen.getByLabelText(/^first name$/i), "Jane");
  await userEvent.type(screen.getByLabelText(/^last name$/i), "Doe");
  await userEvent.type(screen.getByLabelText(/^day$/i), "15");
  await userEvent.type(screen.getByLabelText(/^month$/i), "06");
  await userEvent.type(screen.getByLabelText(/^year$/i), "1990");
  await userEvent.type(screen.getByLabelText(/^postcode$/i), "SW1A 1AA");
  await userEvent.click(screen.getByRole("radio", { name: /^male$/i }));
  await userEvent.click(screen.getByRole("button", { name: /^continue$/i }));

  await screen.findByText(/what do you need today/i);
  await userEvent.click(screen.getByRole("radio", { name: /not sure/i }));
  await userEvent.click(screen.getByRole("button", { name: /^continue$/i }));

  await screen.findByText(/what is your consultation about/i);
}

async function openComboboxAndPick(label: string) {
  await userEvent.click(screen.getByRole("combobox"));
  await userEvent.click(screen.getByRole("option", { name: label }));
}

async function continueToFreeText() {
  await userEvent.click(screen.getByRole("button", { name: /^continue$/i }));
  return screen.findByRole("textbox", { name: /describe your symptoms/i });
}

async function backToSelectCondition() {
  await userEvent.click(screen.getByRole("button", { name: /^back$/i }));
  await screen.findByText(/what is your consultation about/i);
}

describe("App — condition selection and free text", () => {
  beforeEach(() => {
    vi.resetAllMocks();
    mockHappyApi();
  });

  it("shows the previously selected condition's label and an enabled Continue button after going back from FREE_TEXT", async () => {
    await navigateToSelectCondition();
    await openComboboxAndPick("Back pain");
    const textarea = await continueToFreeText();
    await userEvent.type(textarea, "My back hurts");

    await backToSelectCondition();

    expect((screen.getByRole("combobox") as HTMLInputElement).value).toBe("Back pain");
    expect(screen.getByRole("button", { name: /^continue$/i })).not.toBeDisabled();
  });

  it("typing in the box disables Continue but does not touch the free text or show a warning until a different condition is actually chosen", async () => {
    await navigateToSelectCondition();
    await openComboboxAndPick("Back pain");
    const textarea = await continueToFreeText();
    await userEvent.type(textarea, "My back hurts");
    await backToSelectCondition();

    // Mid-typing: Continue should disable, no modal should appear.
    await userEvent.click(screen.getByRole("combobox"));
    await userEvent.clear(screen.getByRole("combobox"));
    await userEvent.type(screen.getByRole("combobox"), "x");
    expect(screen.getByRole("button", { name: /^continue$/i })).toBeDisabled();
    expect(screen.queryByText(/switching conditions will clear/i)).toBeNull();

    // Re-selecting the same condition the free text already belongs to:
    // commits directly, no warning.
    await userEvent.click(screen.getByRole("option", { name: "Back pain" }));
    expect(screen.queryByText(/switching conditions will clear/i)).toBeNull();
    expect(screen.getByRole("button", { name: /^continue$/i })).not.toBeDisabled();

    const textareaAgain = await continueToFreeText();
    expect((textareaAgain as HTMLTextAreaElement).value).toBe("My back hurts");
  });

  it("warns before switching to a different condition with existing free text, and 'Keep my answer' restores the original selection without losing the text", async () => {
    await navigateToSelectCondition();
    await openComboboxAndPick("Back pain");
    const textarea = await continueToFreeText();
    await userEvent.type(textarea, "My back hurts");
    await backToSelectCondition();

    await openComboboxAndPick("Skin rash");
    expect(screen.getByText(/switching conditions will clear/i)).toBeTruthy();

    await userEvent.click(screen.getByRole("button", { name: /keep my answer/i }));

    expect(screen.queryByText(/switching conditions will clear/i)).toBeNull();
    expect((screen.getByRole("combobox") as HTMLInputElement).value).toBe("Back pain");
    expect(screen.getByRole("button", { name: /^continue$/i })).not.toBeDisabled();

    const textareaAgain = await continueToFreeText();
    expect((textareaAgain as HTMLTextAreaElement).value).toBe("My back hurts");
  });

  it("'Switch condition' clears the free text and commits the new selection", async () => {
    await navigateToSelectCondition();
    await openComboboxAndPick("Back pain");
    const textarea = await continueToFreeText();
    await userEvent.type(textarea, "My back hurts");
    await backToSelectCondition();

    await openComboboxAndPick("Skin rash");
    await userEvent.click(screen.getByRole("button", { name: /switch condition/i }));

    expect(screen.queryByText(/switching conditions will clear/i)).toBeNull();
    expect((screen.getByRole("combobox") as HTMLInputElement).value).toBe("Skin rash");

    const newTextarea = await continueToFreeText();
    expect((newTextarea as HTMLTextAreaElement).value).toBe("");
  });

  it("switching condition before any free text exists requires no warning", async () => {
    await navigateToSelectCondition();
    await openComboboxAndPick("Back pain");
    await openComboboxAndPick("Skin rash");

    expect(screen.queryByText(/switching conditions will clear/i)).toBeNull();
    expect((screen.getByRole("combobox") as HTMLInputElement).value).toBe("Skin rash");
  });

  it("'Use blank form' never shows the condition-change warning and does not clear existing free text", async () => {
    await navigateToSelectCondition();
    await openComboboxAndPick("Back pain");
    const textarea = await continueToFreeText();
    await userEvent.type(textarea, "My back hurts");
    await backToSelectCondition();

    await userEvent.click(screen.getByRole("button", { name: /use blank form/i }));

    expect(screen.queryByText(/switching conditions will clear/i)).toBeNull();
    const blankFormTextarea = await screen.findByRole("textbox", {
      name: /describe your symptoms/i,
    });
    expect((blankFormTextarea as HTMLTextAreaElement).value).toBe("My back hurts");
  });
});
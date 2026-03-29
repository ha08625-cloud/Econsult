import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi } from "vitest";
import EditScreen from "./EditScreen";
import type { ClientStateView } from "../types";

// Mock the api module so tests never make real HTTP calls
vi.mock("../api", () => ({
  updateForm: vi.fn(),
  friendlyErrorMessage: (e: unknown) =>
    e instanceof Error ? e.message : "Unknown error",
}));

import { updateForm } from "../api";
const mockUpdateForm = vi.mocked(updateForm);

const noop = () => {};

const booleanQuestion = {
  answer_key: "has_pain",
  question_text: "Do you have pain?",
  answer_type: "boolean" as const,
  current_value: null,
  required: true,
  suggested: false,
};

const textQuestion = {
  answer_key: "duration",
  question_text: "How long have you had symptoms?",
  answer_type: "text" as const,
  current_value: null,
  required: true,
  suggested: false,
};

const suggestedQuestion = {
  answer_key: "frequency",
  question_text: "How often do you experience this?",
  answer_type: "text" as const,
  current_value: "Daily",
  required: false,
  suggested: true,
};

const baseClientState: ClientStateView = {
  condition_label: "Urinary symptoms",
  free_text: null,
  additional_text: null,
  questions: [booleanQuestion, textQuestion],
};

const baseAnswers: Record<string, boolean | string | null> = {
  has_pain: null,
  duration: null,
};

const defaultProps = {
  practiceName: null,
  clientState: baseClientState,
  editableAnswers: baseAnswers,
  additionalText: "",
  onAnswersChange: noop,
  onAdditionalTextChange: noop,
  onContinue: noop,
  onBack: noop,
  runtimeId: "runtime-123",
  version: 1,
  photos: [],
  onPhotosChange: noop,
};

describe("EditScreen", () => {
  beforeEach(() => {
    mockUpdateForm.mockReset();
  });

  it("renders all questions from clientState", () => {
    render(<EditScreen {...defaultProps} />);
    expect(screen.getByText("Do you have pain?")).toBeTruthy();
    expect(screen.getByText("How long have you had symptoms?")).toBeTruthy();
  });

  it("boolean questions render Yes and No radio buttons", () => {
    render(<EditScreen {...defaultProps} />);
    const radios = screen.getAllByRole("radio");
    const labels = radios.map((r) => r.parentElement?.textContent?.trim());
    expect(labels).toContain("Yes");
    expect(labels).toContain("No");
  });

  it("text questions render a text input", () => {
    render(
      <EditScreen
        {...defaultProps}
        clientState={{ ...baseClientState, questions: [textQuestion] }}
        editableAnswers={{ duration: "" }}
      />
    );
    // The additional-text textarea is always present, so there are two textboxes:
    // one for the question input and one for additional information.
    expect(screen.getAllByRole("textbox")).toHaveLength(2);
    expect(screen.getByText("How long have you had symptoms?")).toBeTruthy();
  });

  it("suggested questions render the suggested badge", () => {
    render(
      <EditScreen
        {...defaultProps}
        clientState={{ ...baseClientState, questions: [suggestedQuestion] }}
        editableAnswers={{ frequency: "Daily" }}
      />
    );
    expect(screen.getByText(/pre-filled from your description/i)).toBeTruthy();
  });

  it("Continue button is disabled when a required answer is missing", () => {
    render(
      <EditScreen
        {...defaultProps}
        editableAnswers={{ has_pain: null, duration: null }}
      />
    );
    expect(
      screen.getByRole("button", { name: /review answers/i }).hasAttribute("disabled")
    ).toBe(true);
  });

  it("Continue button is enabled when all required answers are filled", () => {
    render(
      <EditScreen
        {...defaultProps}
        editableAnswers={{ has_pain: true, duration: "Three days" }}
      />
    );
    expect(
      screen.getByRole("button", { name: /review answers/i }).hasAttribute("disabled")
    ).toBe(false);
  });

  it("does not crash when editableAnswers has no keys matching clientState questions", () => {
    // Defensive: prop mismatch should not throw
    expect(() =>
      render(<EditScreen {...defaultProps} editableAnswers={{}} />)
    ).not.toThrow();
  });

  it("calls onContinue with API result on successful submit", async () => {
    const onContinue = vi.fn();
    const mockResult = {
      runtime_id: "runtime-123",
      version: 2,
      client_state: { ...baseClientState, questions: [] },
      safety_messages: [],
    };
    mockUpdateForm.mockResolvedValueOnce(mockResult);

    render(
      <EditScreen
        {...defaultProps}
        editableAnswers={{ has_pain: true, duration: "Two days" }}
        onContinue={onContinue}
      />
    );

    await userEvent.click(screen.getByRole("button", { name: /review answers/i }));

    expect(onContinue).toHaveBeenCalledWith({
      version: 2,
      clientState: mockResult.client_state,
      safetyMessages: [],
    });
  });

  it("displays an inline error when the API call fails", async () => {
    mockUpdateForm.mockRejectedValueOnce(new Error("Network error"));

    render(
      <EditScreen
        {...defaultProps}
        editableAnswers={{ has_pain: true, duration: "Two days" }}
      />
    );

    await userEvent.click(screen.getByRole("button", { name: /review answers/i }));

    expect(screen.getByText(/network error/i)).toBeTruthy();
  });
});

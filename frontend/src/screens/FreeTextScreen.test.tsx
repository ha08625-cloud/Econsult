import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi } from "vitest";
import FreeTextScreen from "./FreeTextScreen";
import type { PresentationState } from "../types";

vi.mock("../api", () => ({
  initForm: vi.fn(),
  friendlyErrorMessage: (e: unknown) =>
    e instanceof Error ? e.message : "Unknown error",
}));

vi.mock("../helpers", () => ({
  initialiseEditableAnswers: vi.fn(() => ({})),
}));

import { initForm } from "../api";
const mockInitForm = vi.mocked(initForm);

const noop = () => {};

const successState: PresentationState = {
  status: "success",
  data: {
    label: "Urinary symptoms",
    free_text_prompt: "Please describe your symptoms",
    universal_safety_warning: "Call 999 in an emergency.",
    practice_signposting: undefined,
  },
};

const defaultProps = {
  presentationState: successState,
  freeText: "",
  selectedConditionId: "uti1",
  onFreeTextChange: noop,
  onContinue: noop,
  onBack: noop,
  onRetry: noop,
};

describe("FreeTextScreen", () => {
  beforeEach(() => {
    mockInitForm.mockReset();
  });

it("renders loading state with correct ARIA role when presentationState.status is loading", () => {
    render(
      <FreeTextScreen
        {...defaultProps}
        presentationState={{ status: "loading" }}
      />
    );
    const statusContainer = screen.getByRole("status");
    expect(statusContainer).toBeTruthy();
    expect(statusContainer).toHaveAttribute("aria-live", "polite");
    expect(statusContainer).toHaveTextContent(/loading/i);
  });

  it("renders error state when presentationState.status is error", () => {
    render(
      <FreeTextScreen
        {...defaultProps}
        presentationState={{ status: "error", message: "Could not load form." }}
      />
    );
    expect(screen.getByText(/could not load form/i)).toBeTruthy();
    expect(screen.getByText(/something went wrong/i)).toBeTruthy();
  });

  it("Try again button in error state calls onRetry", async () => {
    const onRetry = vi.fn();
    render(
      <FreeTextScreen
        {...defaultProps}
        presentationState={{ status: "error", message: "Error." }}
        onRetry={onRetry}
      />
    );
    await userEvent.click(screen.getByRole("button", { name: /try again/i }));
    expect(onRetry).toHaveBeenCalledTimes(1);
  });

  it("Back button in error state calls onBack", async () => {
    const onBack = vi.fn();
    render(
      <FreeTextScreen
        {...defaultProps}
        presentationState={{ status: "error", message: "Error." }}
        onBack={onBack}
      />
    );
    await userEvent.click(screen.getByRole("button", { name: /back/i }));
    expect(onBack).toHaveBeenCalledTimes(1);
  });

  it("renders condition label and free text prompt when loaded", () => {
    render(<FreeTextScreen {...defaultProps} />);
    expect(screen.getByText("Urinary symptoms")).toBeTruthy();
    expect(screen.getByText("Please describe your symptoms")).toBeTruthy();
  });

  it("renders signposting HTML when practice_signposting is present", () => {
    render(
      <FreeTextScreen
        {...defaultProps}
        presentationState={{
          status: "success",
          data: {
            ...successState.data,
            practice_signposting: "<p>Contact us first.</p>",
          },
        }}
      />
    );
    expect(screen.getByText(/contact us first/i)).toBeTruthy();
  });

  it("Continue button is present when loaded", () => {
    render(<FreeTextScreen {...defaultProps} />);
    expect(screen.getByRole("button", { name: /continue/i })).toBeTruthy();
  });

  it("calls onContinue with mapped result on successful submit", async () => {
    const onContinue = vi.fn();
    const mockClientState = {
      condition_label: "Urinary symptoms",
      free_text: "Some text",
      additional_text: null,
      questions: [],
    };
    mockInitForm.mockResolvedValueOnce({
      runtime_id: "runtime-abc",
      version: 1,
      client_state: mockClientState,
    });

    render(<FreeTextScreen {...defaultProps} onContinue={onContinue} />);
    await userEvent.click(screen.getByRole("button", { name: /continue/i }));

    expect(onContinue).toHaveBeenCalledWith(
      expect.objectContaining({
        runtimeId: "runtime-abc",
        version: 1,
        clientState: mockClientState,
        additionalText: "",
      })
    );
  });

  it("displays an inline error when the API call fails", async () => {
    mockInitForm.mockRejectedValueOnce(new Error("Server error"));

    render(<FreeTextScreen {...defaultProps} />);
    await userEvent.click(screen.getByRole("button", { name: /continue/i }));

    expect(screen.getByText(/server error/i)).toBeTruthy();
  });
});

it("marks the textarea as invalid when a submission error occurs", async () => {
    mockInitForm.mockRejectedValueOnce(new Error("Server error"));

    render(<FreeTextScreen {...defaultProps} />);
    
    const textarea = screen.getByRole("textbox", { name: /describe your symptoms/i });
    expect(textarea.hasAttribute("aria-invalid")).toBe(false); // Valid initially

    await userEvent.click(screen.getByRole("button", { name: /continue/i }));

    // Wait for the inline error to appear, which indicates state has updated
    expect(await screen.findByText(/server error/i)).toBeTruthy();
    
    // Now check the textarea
    expect(textarea.getAttribute("aria-invalid")).toBe("true");
  });
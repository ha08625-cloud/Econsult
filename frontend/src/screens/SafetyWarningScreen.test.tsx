import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import SafetyWarningScreen from "./SafetyWarningScreen";
import type { SafetyWarningFetchState } from "./SafetyWarningScreen";

// Default no-op callbacks used in most tests — override only what the test cares about.
const noop = () => {};

const defaultProps = {
  safetyConfirmed: false,
  practiceIsOpen: true,
  availabilityClosedMessage: null,
  afterHoursNotice: null,
  onConfirmChange: noop,
  onRetry: noop,
  onContinue: noop,
};

function renderScreen(
  fetchState: SafetyWarningFetchState,
  overrides: Partial<typeof defaultProps> = {}
) {
  return render(
    <SafetyWarningScreen
      safetyWarningFetchState={fetchState}
      {...defaultProps}
      {...overrides}
    />
  );
}

describe("SafetyWarningScreen", () => {
  it("renders loading state", () => {
    renderScreen({ status: "loading" });
    expect(screen.getByText(/loading/i)).toBeTruthy();
  });

  it("renders warning text when loaded", () => {
    renderScreen({ status: "success", text: "Call 999 if you have chest pain." });
    expect(screen.getByText(/call 999 if you have chest pain/i)).toBeTruthy();
  });

  it("renders closed banner when practiceIsOpen is false", () => {
    renderScreen(
      { status: "success", text: "Some warning." },
      { practiceIsOpen: false, availabilityClosedMessage: "We are closed today." }
    );
    expect(screen.getByText(/this service is currently closed/i)).toBeTruthy();
    expect(screen.getByText(/we are closed today/i)).toBeTruthy();
  });

  it("renders closed banner without message when practiceIsOpen is false and no message provided", () => {
    renderScreen(
      { status: "success", text: "Some warning." },
      { practiceIsOpen: false, availabilityClosedMessage: null }
    );
    expect(screen.getByText(/this service is currently closed/i)).toBeTruthy();
  });

  it("Continue button is disabled until checkbox is ticked", () => {
    renderScreen(
      { status: "success", text: "Some warning." },
      { safetyConfirmed: false }
    );
    const btn = screen.getByRole("button", { name: /continue/i });
    expect(btn.hasAttribute("disabled")).toBe(true);
  });

  it("Continue button is enabled when checkbox is ticked and practice is open", () => {
    renderScreen(
      { status: "success", text: "Some warning." },
      { safetyConfirmed: true, practiceIsOpen: true }
    );
    const btn = screen.getByRole("button", { name: /continue/i });
    expect(btn.hasAttribute("disabled")).toBe(false);
  });

  it("Continue button is disabled when practice is closed even if checkbox is ticked", () => {
    renderScreen(
      { status: "success", text: "Some warning." },
      { safetyConfirmed: true, practiceIsOpen: false }
    );
    const btn = screen.getByRole("button", { name: /continue/i });
    expect(btn.hasAttribute("disabled")).toBe(true);
  });

  it("renders error message and retry button when in error state", () => {
    renderScreen({ status: "error", message: "Could not load warning." });
    expect(screen.getByText(/could not load warning/i)).toBeTruthy();
    expect(screen.getByRole("button", { name: /try again/i })).toBeTruthy();
  });

  it("retry button calls onRetry", async () => {
    const onRetry = vi.fn();
    renderScreen({ status: "error", message: "Error." }, { onRetry });
    await userEvent.click(screen.getByRole("button", { name: /try again/i }));
    expect(onRetry).toHaveBeenCalledTimes(1);
  });
});

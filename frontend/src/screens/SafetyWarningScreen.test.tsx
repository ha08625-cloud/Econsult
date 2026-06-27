import { render, screen } from "@testing-library/react";
import SafetyWarningScreen from "./SafetyWarningScreen";

const baseProps = {
  safetyWarningFetchState: { status: "success" as const, text: "Call 999 if...\nSymptom A\nSymptom B" },
  practiceName: "Elm Tree Surgery" as string | null,
  safetyConfirmed: false,
  practiceIsOpen: true,
  availabilityClosedMessage: null,
  afterHoursNotice: null,
  onConfirmChange: () => {},
  onRetry: () => {},
  onContinue: () => {},
};

test("Checkbox is correctly associated with its label for screen readers", () => {
  render(<SafetyWarningScreen {...baseProps} />);
  // getByLabelText finds inputs wrapped inside a <label> element
  const checkbox = screen.getByLabelText(/I confirm that none of the above apply to me/i);
  expect(checkbox).toBeInTheDocument();
  expect(checkbox).toHaveAttribute("type", "checkbox");
});

test("Continue is disabled when safetyConfirmed is false", () => {
  render(<SafetyWarningScreen {...baseProps} safetyConfirmed={false} />);
  expect(screen.getByRole("button", { name: /continue/i })).toBeDisabled();
});

test("Continue is enabled when safetyConfirmed is true and practice name loaded", () => {
  render(<SafetyWarningScreen {...baseProps} safetyConfirmed={true} />);
  expect(screen.getByRole("button", { name: /continue/i })).not.toBeDisabled();
});

test("Continue is enabled when safetyConfirmed is true even though practice name failed to load", () => {
  // practiceName fails open: a cosmetic header value must never block the patient.
  render(<SafetyWarningScreen {...baseProps} safetyConfirmed={true} practiceName={null} />);
  expect(screen.getByRole("button", { name: /continue/i })).not.toBeDisabled();
});

test("No practice name error or retry control is shown when practice name is unavailable", () => {
  // There is no separate error/retry UI for practice name — it fails open silently,
  // the same way availability and doctors do.
  render(<SafetyWarningScreen {...baseProps} practiceName={null} />);
  expect(screen.queryByText(/retry loading practice name/i)).not.toBeInTheDocument();
});

test("Safety gate hint renders as a plain paragraph with warning text when not confirmed", () => {
  render(<SafetyWarningScreen {...baseProps} safetyConfirmed={false} />);
  // The hint is a plain <p>, not an InlineError — it is a warning instruction, not an error message
  expect(screen.getByText(/please call 999 or go to A&E immediately/i)).toBeInTheDocument();
});

test("Safety warning includes visually hidden 'Important:' prefix", () => {
  render(<SafetyWarningScreen {...baseProps} />);
  // textContent check spans the sr-only span and visible heading text
  expect(screen.getByText((_, element) => {
    return element?.textContent === "Important: Read before continuing";
  })).toBeInTheDocument();
});

test("Renders 'closed' message when practiceIsOpen is false", () => {
  render(
    <SafetyWarningScreen
      {...baseProps}
      practiceIsOpen={false}
      availabilityClosedMessage="Custom closed message"
    />
  );
  expect(screen.getByText(/This service is currently closed/i)).toBeInTheDocument();
  expect(screen.getByText(/Custom closed message/i)).toBeInTheDocument();
});
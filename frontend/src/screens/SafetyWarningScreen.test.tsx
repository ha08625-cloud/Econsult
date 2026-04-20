import { render, screen } from "@testing-library/react";
import SafetyWarningScreen from "./SafetyWarningScreen";

const baseProps = {
  safetyWarningFetchState: { status: "success" as const, text: "Call 999 if...\nSymptom A\nSymptom B" },
  practiceNameFetchState: { status: "success" as const, name: "Elm Tree Surgery" },
  safetyConfirmed: false,
  practiceIsOpen: true,
  availabilityClosedMessage: null,
  afterHoursNotice: null,
  onConfirmChange: () => {},
  onRetry: () => {},
  onPracticeRetry: () => {},
  onContinue: () => {},
};

test("Checkbox is correctly associated with its label for screen readers", () => {
  render(<SafetyWarningScreen {...baseProps} />);
  // getByLabelText verifies the 'for'/'id' association is working
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

test("Practice error block renders with 'Error:' prefix for screen readers", () => {
  render(
    <SafetyWarningScreen
      {...baseProps}
      practiceNameFetchState={{ status: "error", message: "Could not load practice" }}
    />
  );
  
  // Use a function matcher to find text across multiple elements
  expect(screen.getByText((content, element) => {
    return element?.textContent === "Error: Could not load practice";
  })).toBeInTheDocument();
});

test("Safety gate hint renders as an InlineError when not confirmed", () => {
  render(<SafetyWarningScreen {...baseProps} safetyConfirmed={false} />);
  
  const expectedText = "Error: If any of the above apply to you, please call 999 or go to A&E immediately. Do not use this form.";
  
  expect(screen.getByText((content, element) => {
    return element?.textContent === expectedText;
  })).toBeInTheDocument();
});

test("Safety warning includes visually hidden 'Important:' prefix", () => {
  render(<SafetyWarningScreen {...baseProps} />);
  
  // Also update this one to be safe
  expect(screen.getByText((content, element) => {
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

// Tests for SafetyWarningScreen
// Run with: make test (or npx vitest)

import { render, screen } from "@testing-library/react";
import SafetyWarningScreen from "./SafetyWarningScreen";

const baseProps = {
  safetyWarningFetchState: { status: "success" as const, text: "Call 999 if..." },
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

test("Continue is disabled when safetyConfirmed is false", () => {
  render(<SafetyWarningScreen {...baseProps} safetyConfirmed={false} />);
  expect(screen.getByRole("button", { name: /continue/i })).toBeDisabled();
});

test("Continue is enabled when safetyConfirmed is true and practice name loaded", () => {
  render(<SafetyWarningScreen {...baseProps} safetyConfirmed={true} />);
  expect(screen.getByRole("button", { name: /continue/i })).not.toBeDisabled();
});

test("Continue is disabled when practiceNameFetchState is loading", () => {
  render(
    <SafetyWarningScreen
      {...baseProps}
      safetyConfirmed={true}
      practiceNameFetchState={{ status: "loading" }}
    />
  );
  expect(screen.getByRole("button", { name: /continue/i })).toBeDisabled();
});

test("Continue is disabled when practiceNameFetchState is error", () => {
  render(
    <SafetyWarningScreen
      {...baseProps}
      safetyConfirmed={true}
      practiceNameFetchState={{ status: "error", message: "Server error" }}
    />
  );
  expect(screen.getByRole("button", { name: /continue/i })).toBeDisabled();
});

test("Practice error block renders when practiceNameFetchState is error", () => {
  render(
    <SafetyWarningScreen
      {...baseProps}
      practiceNameFetchState={{ status: "error", message: "Could not load practice" }}
    />
  );
  expect(screen.getByText("Could not load practice")).toBeInTheDocument();
});

test("Practice error block not rendered when practiceNameFetchState is success", () => {
  render(<SafetyWarningScreen {...baseProps} />);
  expect(screen.queryByText("Could not load practice")).not.toBeInTheDocument();
});

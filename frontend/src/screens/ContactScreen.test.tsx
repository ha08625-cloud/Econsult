import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi } from "vitest";
import ContactScreen from "./ContactScreen";

vi.mock("../api", () => ({
  finishForm: vi.fn(),
  friendlyErrorMessage: (e: unknown) =>
    e instanceof Error ? e.message : "Unknown error",
}));

import { finishForm } from "../api";
const mockFinishForm = vi.mocked(finishForm);

const noop = () => {};

const defaultProps = {
  runtimeId: "runtime-abc",
  version: 2,
  onSubmit: noop,
  onBack: noop,
};

describe("ContactScreen", () => {
  beforeEach(() => {
    mockFinishForm.mockReset();
  });

  it("phone field appears when phone is selected", async () => {
    render(<ContactScreen {...defaultProps} />);
    await userEvent.click(screen.getByRole("checkbox", { name: /phone call/i }));
    expect(document.getElementById("contact-phone")).not.toBeNull();
  });

  it("phone field appears when text message is selected", async () => {
    render(<ContactScreen {...defaultProps} />);
    await userEvent.click(screen.getByRole("checkbox", { name: /text message/i }));
    expect(document.getElementById("contact-phone")).not.toBeNull();
  });

  it("phone field does not appear when only email is selected", async () => {
    render(<ContactScreen {...defaultProps} />);
    await userEvent.click(screen.getByRole("checkbox", { name: /email/i }));
    expect(document.getElementById("contact-phone")).toBeNull();
  });

  it("email field appears when email is selected", async () => {
    render(<ContactScreen {...defaultProps} />);
    await userEvent.click(screen.getByRole("checkbox", { name: /email/i }));
    expect(document.getElementById("contact-email")).not.toBeNull();
  });

  it("usual doctor name field appears when doctor preference is usual", async () => {
    render(<ContactScreen {...defaultProps} />);
    const select = document.getElementById("doctor-preference") as HTMLSelectElement;
    await userEvent.selectOptions(select, "usual");
    expect(document.getElementById("usual-doctor-name")).not.toBeNull();
  });

  it("validates and shows error when no contact method is selected", async () => {
    render(<ContactScreen {...defaultProps} />);
    await userEvent.click(screen.getByRole("button", { name: /submit/i }));
    expect(
      screen.getByText(/please select at least one contact method/i)
    ).toBeTruthy();
  });

  it("validates and shows error for invalid UK phone number", async () => {
    render(<ContactScreen {...defaultProps} />);
    await userEvent.click(screen.getByRole("checkbox", { name: /phone call/i }));
    const phoneInput = document.getElementById("contact-phone") as HTMLInputElement;
    await userEvent.type(phoneInput, "00000000000");
    await userEvent.click(screen.getByRole("button", { name: /submit/i }));
    expect(
      screen.getByText(/please enter a valid uk mobile or landline number/i)
    ).toBeTruthy();
  });

  it("Submit button is disabled while submitting", async () => {
    // Make finishForm hang so we can inspect the in-flight state
    mockFinishForm.mockImplementation(() => new Promise(() => {}));

    render(<ContactScreen {...defaultProps} />);
    await userEvent.click(screen.getByRole("checkbox", { name: /email/i }));
    const emailInput = document.getElementById("contact-email") as HTMLInputElement;
    await userEvent.type(emailInput, "test@example.com");
    await userEvent.click(screen.getByRole("button", { name: /submit/i }));

    expect(
      screen.getByRole("button", { name: /submitting/i }).hasAttribute("disabled")
    ).toBe(true);
  });
});
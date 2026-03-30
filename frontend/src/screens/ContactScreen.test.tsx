import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi } from "vitest";
import ContactScreen from "./ContactScreen";
import type { PatientDetails } from "../types";

vi.mock("../api", () => ({
  finishForm: vi.fn(),
  friendlyErrorMessage: (e: unknown) =>
    e instanceof Error ? e.message : "Unknown error",
}));

import { finishForm } from "../api";
const mockFinishForm = vi.mocked(finishForm);

const noop = () => {};

const defaultPatientDetails: PatientDetails = {
  first_name: "Jane",
  last_name: "Smith",
  date_of_birth: "1990-01-01",
};

const defaultProps = {
  practiceName: null,
  runtimeId: "runtime-abc",
  version: 2,
  patientDetails: defaultPatientDetails,
  photos: [] as File[],
  doctors: [] as string[],
  onSubmit: noop,
  onBack: noop,
};

// Helper: fill a valid email submission and click Submit.
async function submitWithEmail() {
  await userEvent.click(screen.getByRole("checkbox", { name: /email/i }));
  const emailInput = document.getElementById("contact-email") as HTMLInputElement;
  await userEvent.type(emailInput, "test@example.com");
  await userEvent.click(screen.getByRole("button", { name: /submit/i }));
}

describe("ContactScreen", () => {
  beforeEach(() => {
    mockFinishForm.mockReset();
    mockFinishForm.mockResolvedValue({ submission_id: "sub-1" });
  });

  // ---------------------------------
  // Contact method UI
  // ---------------------------------

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

  // ---------------------------------
  // Legacy path (no doctor list)
  // ---------------------------------

  it("shows two-option select and no free text box by default when no doctor list is provided", () => {
    render(<ContactScreen {...defaultProps} doctors={[]} />);
    const select = document.getElementById("doctor-preference") as HTMLSelectElement;
    expect(select).not.toBeNull();
    expect(select.options.length).toBe(2);
    expect(document.getElementById("usual-doctor-name")).toBeNull();
  });

  it("usual doctor name field appears when doctor preference is usual (legacy path)", async () => {
    render(<ContactScreen {...defaultProps} doctors={[]} />);
    const select = document.getElementById("doctor-preference") as HTMLSelectElement;
    await userEvent.selectOptions(select, "usual");
    expect(document.getElementById("usual-doctor-name")).not.toBeNull();
  });

  it("validates missing doctor name on legacy path", async () => {
    render(<ContactScreen {...defaultProps} doctors={[]} />);
    const select = document.getElementById("doctor-preference") as HTMLSelectElement;
    await userEvent.selectOptions(select, "usual");
    await userEvent.click(screen.getByRole("checkbox", { name: /email/i }));
    const emailInput = document.getElementById("contact-email") as HTMLInputElement;
    await userEvent.type(emailInput, "test@example.com");
    await userEvent.click(screen.getByRole("button", { name: /submit/i }));
    expect(screen.getByText(/please enter your doctor's name/i)).toBeTruthy();
  });

  // ---------------------------------
  // List path (doctor list provided)
  // ---------------------------------

  it("shows the doctor list dropdown with correct options when doctors prop is non-empty", () => {
    render(<ContactScreen {...defaultProps} doctors={["Dr Smith", "Dr Jones"]} />);
    const select = document.getElementById("doctor-preference") as HTMLSelectElement;
    expect(select).not.toBeNull();
    // Should have: "Soonest available", "Someone not on this list", Dr Smith, Dr Jones
    expect(select.options.length).toBe(4);
    const optionValues = Array.from(select.options).map((o) => o.value);
    expect(optionValues).toContain("any");
    expect(optionValues).toContain("other");
    expect(optionValues).toContain("Dr Smith");
    expect(optionValues).toContain("Dr Jones");
  });

  it("free text box is always visible when doctor list is shown", () => {
    render(<ContactScreen {...defaultProps} doctors={["Dr Smith"]} />);
    expect(document.getElementById("usual-doctor-name")).not.toBeNull();
  });

  it("submits doctor_preference=any and usual_doctor_name=null when soonest available is selected", async () => {
    render(<ContactScreen {...defaultProps} doctors={["Dr Smith"]} />);
    // Default selection is "any" — no change needed.
    await submitWithEmail();
    expect(mockFinishForm).toHaveBeenCalledOnce();
    const prefs = mockFinishForm.mock.calls[0][2];
    expect(prefs.doctor_preference).toBe("any");
    expect(prefs.usual_doctor_name).toBeNull();
  });

  it("submits usual_doctor_name as the selected doctor name when a named doctor is chosen", async () => {
    render(<ContactScreen {...defaultProps} doctors={["Dr Smith", "Dr Jones"]} />);
    const select = document.getElementById("doctor-preference") as HTMLSelectElement;
    await userEvent.selectOptions(select, "Dr Jones");
    await submitWithEmail();
    expect(mockFinishForm).toHaveBeenCalledOnce();
    const prefs = mockFinishForm.mock.calls[0][2];
    expect(prefs.doctor_preference).toBe("usual");
    expect(prefs.usual_doctor_name).toBe("Dr Jones");
  });

  it("named doctor takes precedence over free text when both are filled", async () => {
    render(<ContactScreen {...defaultProps} doctors={["Dr Smith"]} />);
    const select = document.getElementById("doctor-preference") as HTMLSelectElement;
    await userEvent.selectOptions(select, "Dr Smith");
    const freeText = document.getElementById("usual-doctor-name") as HTMLInputElement;
    await userEvent.type(freeText, "Dr Other");
    await submitWithEmail();
    expect(mockFinishForm).toHaveBeenCalledOnce();
    const prefs = mockFinishForm.mock.calls[0][2];
    expect(prefs.usual_doctor_name).toBe("Dr Smith");
  });

  it("submits free text value when 'Someone not on this list' is selected", async () => {
    render(<ContactScreen {...defaultProps} doctors={["Dr Smith"]} />);
    const select = document.getElementById("doctor-preference") as HTMLSelectElement;
    await userEvent.selectOptions(select, "other");
    const freeText = document.getElementById("usual-doctor-name") as HTMLInputElement;
    await userEvent.type(freeText, "Dr Patel");
    await submitWithEmail();
    expect(mockFinishForm).toHaveBeenCalledOnce();
    const prefs = mockFinishForm.mock.calls[0][2];
    expect(prefs.doctor_preference).toBe("usual");
    expect(prefs.usual_doctor_name).toBe("Dr Patel");
  });

  it("shows validation error when 'Someone not on this list' is selected but free text is empty", async () => {
    render(<ContactScreen {...defaultProps} doctors={["Dr Smith"]} />);
    const select = document.getElementById("doctor-preference") as HTMLSelectElement;
    await userEvent.selectOptions(select, "other");
    await userEvent.click(screen.getByRole("checkbox", { name: /email/i }));
    const emailInput = document.getElementById("contact-email") as HTMLInputElement;
    await userEvent.type(emailInput, "test@example.com");
    await userEvent.click(screen.getByRole("button", { name: /submit/i }));
    expect(screen.getByText(/please enter your doctor's name/i)).toBeTruthy();
  });

  it("does not require free text when a named doctor is selected from the list", async () => {
    render(<ContactScreen {...defaultProps} doctors={["Dr Smith"]} />);
    const select = document.getElementById("doctor-preference") as HTMLSelectElement;
    await userEvent.selectOptions(select, "Dr Smith");
    // Do not fill the free text box.
    await submitWithEmail();
    expect(mockFinishForm).toHaveBeenCalledOnce();
  });

  it("falls back to legacy free text UI when doctors prop is empty", () => {
    render(<ContactScreen {...defaultProps} doctors={[]} />);
    const select = document.getElementById("doctor-preference") as HTMLSelectElement;
    expect(select).not.toBeNull();
    expect(select.options.length).toBe(2);
  });

  // ---------------------------------
  // Contact method validation
  // ---------------------------------

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

  // ---------------------------------
  // Submission state
  // ---------------------------------

  it("Submit button is disabled while submitting", async () => {
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

  // ---------------------------------
  // Photo passthrough
  // ---------------------------------

  it("calls finishForm with an empty photos array when no photos are provided", async () => {
    render(<ContactScreen {...defaultProps} photos={[]} />);
    await submitWithEmail();

    expect(mockFinishForm).toHaveBeenCalledOnce();
    const photosArg = mockFinishForm.mock.calls[0][4];
    expect(photosArg).toEqual([]);
  });

  it("calls finishForm with the correct photos array when photos are provided", async () => {
    const file1 = new File([new Uint8Array([0xff, 0xd8, 0xff])], "photo1.jpg", {
      type: "image/jpeg",
    });
    const file2 = new File([new Uint8Array([0xff, 0xd8, 0xff])], "photo2.jpg", {
      type: "image/jpeg",
    });

    render(<ContactScreen {...defaultProps} photos={[file1, file2]} />);
    await submitWithEmail();

    expect(mockFinishForm).toHaveBeenCalledOnce();
    const photosArg = mockFinishForm.mock.calls[0][4];
    expect(photosArg).toHaveLength(2);
    expect((photosArg as File[])[0].name).toBe("photo1.jpg");
    expect((photosArg as File[])[1].name).toBe("photo2.jpg");
  });
});
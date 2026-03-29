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
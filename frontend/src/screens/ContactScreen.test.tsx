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
  doctors: [],
};

// Helper: submit the form with a valid email so we can reach finishForm.
async function submitWithEmail() {
  await userEvent.click(screen.getByRole("checkbox", { name: /email/i }));
  const emailInput = document.getElementById("contact-email") as HTMLInputElement;
  await userEvent.type(emailInput, "test@example.com");
  await userEvent.click(screen.getByRole("button", { name: /submit/i }));
}

describe("ContactScreen", () => {
  beforeEach(() => {
    mockFinishForm.mockReset();
  });

  // -------------------------------------------------------------------------
  // Existing behaviour (no doctor list — doctors prop is empty)
  // -------------------------------------------------------------------------

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

  it("usual doctor name field appears when doctor preference is usual (no list)", async () => {
    // When doctors is empty, the legacy two-option select is shown.
    // Selecting "usual" shows the free text input.
    render(<ContactScreen {...defaultProps} doctors={[]} />);
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

  // -------------------------------------------------------------------------
  // Doctor list path (doctors prop is non-empty)
  // -------------------------------------------------------------------------

  it("doctor dropdown is shown when doctors prop is non-empty", () => {
    render(
      <ContactScreen
        {...defaultProps}
        doctors={["Dr Smith", "Dr Jones"]}
      />
    );
    const select = document.getElementById("doctor-preference") as HTMLSelectElement;
    expect(select).not.toBeNull();
    // Confirm the list options are present
    const options = Array.from(select.options).map((o) => o.value);
    expect(options).toContain("any");
    expect(options).toContain("other");
    expect(options).toContain("Dr Smith");
    expect(options).toContain("Dr Jones");
  });

  it("soonest available and someone not on list options appear at the top of the dropdown", () => {
    render(
      <ContactScreen
        {...defaultProps}
        doctors={["Dr Smith", "Dr Jones"]}
      />
    );
    const select = document.getElementById("doctor-preference") as HTMLSelectElement;
    const options = Array.from(select.options);
    expect(options[0].value).toBe("any");
    expect(options[1].value).toBe("other");
  });

  it("free text box is always visible when doctor list is shown", () => {
    render(
      <ContactScreen
        {...defaultProps}
        doctors={["Dr Smith"]}
      />
    );
    // The free text input is present even though "any" (soonest available) is selected
    expect(document.getElementById("usual-doctor-name")).not.toBeNull();
  });

  it("free text box is visible even when a named doctor is selected from the list", async () => {
    render(
      <ContactScreen
        {...defaultProps}
        doctors={["Dr Smith", "Dr Jones"]}
      />
    );
    const select = document.getElementById("doctor-preference") as HTMLSelectElement;
    await userEvent.selectOptions(select, "Dr Smith");
    expect(document.getElementById("usual-doctor-name")).not.toBeNull();
  });

  it("submits doctor_preference: usual and usual_doctor_name from dropdown when named doctor is selected", async () => {
    mockFinishForm.mockResolvedValue({ submission_id: "x" });

    render(
      <ContactScreen
        {...defaultProps}
        doctors={["Dr Smith", "Dr Jones"]}
      />
    );

    await userEvent.click(screen.getByRole("checkbox", { name: /email/i }));
    const emailInput = document.getElementById("contact-email") as HTMLInputElement;
    await userEvent.type(emailInput, "test@example.com");

    const select = document.getElementById("doctor-preference") as HTMLSelectElement;
    await userEvent.selectOptions(select, "Dr Smith");

    await userEvent.click(screen.getByRole("button", { name: /submit/i }));

    expect(mockFinishForm).toHaveBeenCalledOnce();
    const prefs = mockFinishForm.mock.calls[0][2];
    expect(prefs.doctor_preference).toBe("usual");
    expect(prefs.usual_doctor_name).toBe("Dr Smith");
  });

  it("submits doctor_preference: usual and usual_doctor_name from free text when 'someone not on list' is selected", async () => {
    mockFinishForm.mockResolvedValue({ submission_id: "x" });

    render(
      <ContactScreen
        {...defaultProps}
        doctors={["Dr Smith"]}
      />
    );

    await userEvent.click(screen.getByRole("checkbox", { name: /email/i }));
    const emailInput = document.getElementById("contact-email") as HTMLInputElement;
    await userEvent.type(emailInput, "test@example.com");

    const select = document.getElementById("doctor-preference") as HTMLSelectElement;
    await userEvent.selectOptions(select, "other");

    const freeText = document.getElementById("usual-doctor-name") as HTMLInputElement;
    await userEvent.type(freeText, "Dr Brown");

    await userEvent.click(screen.getByRole("button", { name: /submit/i }));

    expect(mockFinishForm).toHaveBeenCalledOnce();
    const prefs = mockFinishForm.mock.calls[0][2];
    expect(prefs.doctor_preference).toBe("usual");
    expect(prefs.usual_doctor_name).toBe("Dr Brown");
  });

  it("submits doctor_preference: any when soonest available is selected", async () => {
    mockFinishForm.mockResolvedValue({ submission_id: "x" });

    render(
      <ContactScreen
        {...defaultProps}
        doctors={["Dr Smith"]}
      />
    );

    await userEvent.click(screen.getByRole("checkbox", { name: /email/i }));
    const emailInput = document.getElementById("contact-email") as HTMLInputElement;
    await userEvent.type(emailInput, "test@example.com");

    // "any" is already selected by default — no need to change it

    await userEvent.click(screen.getByRole("button", { name: /submit/i }));

    expect(mockFinishForm).toHaveBeenCalledOnce();
    const prefs = mockFinishForm.mock.calls[0][2];
    expect(prefs.doctor_preference).toBe("any");
    expect(prefs.usual_doctor_name).toBeNull();
  });

  it("named doctor takes precedence over free text when both are filled in", async () => {
    mockFinishForm.mockResolvedValue({ submission_id: "x" });

    render(
      <ContactScreen
        {...defaultProps}
        doctors={["Dr Smith"]}
      />
    );

    await userEvent.click(screen.getByRole("checkbox", { name: /email/i }));
    const emailInput = document.getElementById("contact-email") as HTMLInputElement;
    await userEvent.type(emailInput, "test@example.com");

    const select = document.getElementById("doctor-preference") as HTMLSelectElement;
    await userEvent.selectOptions(select, "Dr Smith");

    // Patient also fills in the free text box (should be ignored)
    const freeText = document.getElementById("usual-doctor-name") as HTMLInputElement;
    await userEvent.type(freeText, "Dr Someone Else");

    await userEvent.click(screen.getByRole("button", { name: /submit/i }));

    expect(mockFinishForm).toHaveBeenCalledOnce();
    const prefs = mockFinishForm.mock.calls[0][2];
    expect(prefs.usual_doctor_name).toBe("Dr Smith");
  });

  it("shows validation error when 'someone not on list' is selected but free text is empty", async () => {
    render(
      <ContactScreen
        {...defaultProps}
        doctors={["Dr Smith"]}
      />
    );

    await userEvent.click(screen.getByRole("checkbox", { name: /email/i }));
    const emailInput = document.getElementById("contact-email") as HTMLInputElement;
    await userEvent.type(emailInput, "test@example.com");

    const select = document.getElementById("doctor-preference") as HTMLSelectElement;
    await userEvent.selectOptions(select, "other");

    // Do not fill in the free text box

    await userEvent.click(screen.getByRole("button", { name: /submit/i }));

    expect(screen.getByText(/please enter your doctor's name/i)).toBeTruthy();
    expect(mockFinishForm).not.toHaveBeenCalled();
  });

  it("does not show validation error when named doctor is selected and free text is empty", async () => {
    mockFinishForm.mockResolvedValue({ submission_id: "x" });

    render(
      <ContactScreen
        {...defaultProps}
        doctors={["Dr Smith"]}
      />
    );

    await userEvent.click(screen.getByRole("checkbox", { name: /email/i }));
    const emailInput = document.getElementById("contact-email") as HTMLInputElement;
    await userEvent.type(emailInput, "test@example.com");

    const select = document.getElementById("doctor-preference") as HTMLSelectElement;
    await userEvent.selectOptions(select, "Dr Smith");

    // Free text box is intentionally left empty

    await userEvent.click(screen.getByRole("button", { name: /submit/i }));

    // Should not show error — named doctor was selected
    expect(screen.queryByText(/please enter your doctor's name/i)).toBeNull();
    expect(mockFinishForm).toHaveBeenCalledOnce();
  });

  it("falls back to free text path when doctors prop is empty", () => {
    render(<ContactScreen {...defaultProps} doctors={[]} />);
    const select = document.getElementById("doctor-preference") as HTMLSelectElement;
    const options = Array.from(select.options).map((o) => o.value);
    // Legacy path: only "any" and "usual" options, no "other"
    expect(options).toContain("any");
    expect(options).toContain("usual");
    expect(options).not.toContain("other");
  });
});
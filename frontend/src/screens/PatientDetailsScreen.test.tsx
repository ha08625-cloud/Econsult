import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi } from "vitest";
import PatientDetailsScreen from "./PatientDetailsScreen";

const noop = () => {};

const defaultProps = {
  practiceName: null,
  onContinue: noop,
  onBack: noop,
};

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

// Fill in the minimum fields required to pass validation for a "myself" submission.
// Gender (female) is included because it is required.
async function fillValidMyselfForm() {
  await userEvent.type(screen.getByLabelText(/first name/i), "Jane");
  await userEvent.type(screen.getByLabelText(/last name/i), "Smith");
  await userEvent.click(screen.getByLabelText(/^female$/i));
  await userEvent.type(screen.getByLabelText(/^day$/i), "15");
  await userEvent.type(screen.getByLabelText(/^month$/i), "03");
  await userEvent.type(screen.getByLabelText(/^year$/i), "1990");
  await userEvent.type(screen.getByLabelText(/postcode/i), "SW1A 1AA");
}

// ---------------------------------------------------------------------------
// Rendering
// ---------------------------------------------------------------------------

describe("PatientDetailsScreen", () => {
  it("renders the page heading", () => {
    render(<PatientDetailsScreen {...defaultProps} />);
    expect(screen.getByRole("heading", { name: /about the patient/i })).toBeTruthy();
  });

  it("renders the who-is-this-for radio group with two options", () => {
    render(<PatientDetailsScreen {...defaultProps} />);
    expect(screen.getByLabelText(/myself/i)).toBeTruthy();
    expect(screen.getByLabelText(/someone else/i)).toBeTruthy();
  });

  it("defaults to the Myself radio being selected", () => {
    render(<PatientDetailsScreen {...defaultProps} />);
    const myself = screen.getByLabelText(/myself/i) as HTMLInputElement;
    expect(myself.checked).toBe(true);
  });

  it("renders first name, last name, DOB, and postcode fields", () => {
    render(<PatientDetailsScreen {...defaultProps} />);
    expect(screen.getByLabelText(/first name/i)).toBeTruthy();
    expect(screen.getByLabelText(/last name/i)).toBeTruthy();
    expect(screen.getByLabelText(/^day$/i)).toBeTruthy();
    expect(screen.getByLabelText(/^month$/i)).toBeTruthy();
    expect(screen.getByLabelText(/^year$/i)).toBeTruthy();
    expect(screen.getByLabelText(/postcode/i)).toBeTruthy();
  });

  it("renders gender radio buttons", () => {
    render(<PatientDetailsScreen {...defaultProps} />);
    expect(screen.getByLabelText(/^male$/i)).toBeTruthy();
    expect(screen.getByLabelText(/^female$/i)).toBeTruthy();
    expect(screen.getByLabelText(/^other$/i)).toBeTruthy();
    expect(screen.getByLabelText(/i'd rather not say/i)).toBeTruthy();
  });

  it("renders preferred name and NHS number fields", () => {
    render(<PatientDetailsScreen {...defaultProps} />);
    expect(screen.getByLabelText(/preferred name/i)).toBeTruthy();
    expect(screen.getByLabelText(/nhs number/i)).toBeTruthy();
  });

  it("does not render submitter fields when Myself is selected", () => {
    render(<PatientDetailsScreen {...defaultProps} />);
    expect(screen.queryByLabelText(/your name/i)).toBeNull();
    expect(screen.queryByLabelText(/your relationship/i)).toBeNull();
  });

  it("renders submitter fields when Someone else is selected", async () => {
    render(<PatientDetailsScreen {...defaultProps} />);
    await userEvent.click(screen.getByLabelText(/someone else/i));
    expect(screen.getByLabelText(/your name/i)).toBeTruthy();
    expect(screen.getByLabelText(/relationship to patient/i)).toBeTruthy();
  });

  it("renders Continue and Back buttons", () => {
    render(<PatientDetailsScreen {...defaultProps} />);
    expect(screen.getByRole("button", { name: /continue/i })).toBeTruthy();
    expect(screen.getByRole("button", { name: /back/i })).toBeTruthy();
  });

  // ---------------------------------------------------------------------------
  // Validation — required fields
  // ---------------------------------------------------------------------------

  it("shows first name error when first name is empty on submit", async () => {
    render(<PatientDetailsScreen {...defaultProps} />);
    await userEvent.click(screen.getByRole("button", { name: /continue/i }));
    const fields = screen.getByTestId("form-fields");
    expect(within(fields).getByText(/enter first name/i)).toBeInTheDocument();
  });

  it("shows last name error when last name is empty on submit", async () => {
    render(<PatientDetailsScreen {...defaultProps} />);
    await userEvent.type(screen.getByLabelText(/first name/i), "Jane");
    await userEvent.click(screen.getByRole("button", { name: /continue/i }));
    const fields = screen.getByTestId("form-fields");
    expect(within(fields).getByText(/enter last name/i)).toBeInTheDocument();
  });

  it("shows DOB error when DOB fields are empty on submit", async () => {
    render(<PatientDetailsScreen {...defaultProps} />);
    await userEvent.type(screen.getByLabelText(/first name/i), "Jane");
    await userEvent.type(screen.getByLabelText(/last name/i), "Smith");
    await userEvent.click(screen.getByRole("button", { name: /continue/i }));
    const fields = screen.getByTestId("form-fields");
    expect(within(fields).getByText(/enter a complete date of birth/i)).toBeInTheDocument();
  });

  it("shows DOB error when DOB is not a real calendar date", async () => {
    render(<PatientDetailsScreen {...defaultProps} />);
    await userEvent.type(screen.getByLabelText(/first name/i), "Jane");
    await userEvent.type(screen.getByLabelText(/last name/i), "Smith");
    await userEvent.type(screen.getByLabelText(/^day$/i), "31");
    await userEvent.type(screen.getByLabelText(/^month$/i), "02");
    await userEvent.type(screen.getByLabelText(/^year$/i), "1990");
    await userEvent.click(screen.getByRole("button", { name: /continue/i }));
    const fields = screen.getByTestId("form-fields");
    expect(within(fields).getByText(/enter a valid date/i)).toBeInTheDocument();
  });

  it("shows DOB error when DOB is in the future", async () => {
    render(<PatientDetailsScreen {...defaultProps} />);
    await userEvent.type(screen.getByLabelText(/first name/i), "Jane");
    await userEvent.type(screen.getByLabelText(/last name/i), "Smith");
    await userEvent.type(screen.getByLabelText(/^day$/i), "01");
    await userEvent.type(screen.getByLabelText(/^month$/i), "01");
    await userEvent.type(screen.getByLabelText(/^year$/i), "2099");
    await userEvent.click(screen.getByRole("button", { name: /continue/i }));
    const fields = screen.getByTestId("form-fields");
    expect(within(fields).getByText(/cannot be in the future/i)).toBeInTheDocument();
  });

  it("shows postcode error when postcode is empty on submit", async () => {
    render(<PatientDetailsScreen {...defaultProps} />);
    await userEvent.type(screen.getByLabelText(/first name/i), "Jane");
    await userEvent.type(screen.getByLabelText(/last name/i), "Smith");
    await userEvent.type(screen.getByLabelText(/^day$/i), "15");
    await userEvent.type(screen.getByLabelText(/^month$/i), "03");
    await userEvent.type(screen.getByLabelText(/^year$/i), "1990");
    await userEvent.click(screen.getByRole("button", { name: /continue/i }));
    const fields = screen.getByTestId("form-fields");
    expect(within(fields).getByText(/enter a postcode/i)).toBeInTheDocument();
  });

  it("shows postcode format error for an invalid postcode", async () => {
    render(<PatientDetailsScreen {...defaultProps} />);
    await userEvent.type(screen.getByLabelText(/first name/i), "Jane");
    await userEvent.type(screen.getByLabelText(/last name/i), "Smith");
    await userEvent.type(screen.getByLabelText(/^day$/i), "15");
    await userEvent.type(screen.getByLabelText(/^month$/i), "03");
    await userEvent.type(screen.getByLabelText(/^year$/i), "1990");
    await userEvent.type(screen.getByLabelText(/postcode/i), "NOTAPOSTCODE");
    await userEvent.click(screen.getByRole("button", { name: /continue/i }));
    const fields = screen.getByTestId("form-fields");
    expect(within(fields).getByText(/enter a valid uk postcode/i)).toBeInTheDocument();
  });

  it("shows submitter name and relationship errors when someone-else fields are empty", async () => {
    render(<PatientDetailsScreen {...defaultProps} />);
    await userEvent.click(screen.getByLabelText(/someone else/i));
    await fillValidMyselfForm();
    await userEvent.click(screen.getByRole("button", { name: /continue/i }));
    const fields = screen.getByTestId("form-fields");
    expect(within(fields).getByText(/enter your name/i)).toBeInTheDocument();
    expect(within(fields).getByText(/enter relationship/i)).toBeInTheDocument();
  });

  // ---------------------------------------------------------------------------
  // Validation — gender
  // ---------------------------------------------------------------------------

  it("shows gender error when no gender is selected on submit", async () => {
    render(<PatientDetailsScreen {...defaultProps} />);
    await userEvent.type(screen.getByLabelText(/first name/i), "Jane");
    await userEvent.type(screen.getByLabelText(/last name/i), "Smith");
    await userEvent.type(screen.getByLabelText(/^day$/i), "15");
    await userEvent.type(screen.getByLabelText(/^month$/i), "03");
    await userEvent.type(screen.getByLabelText(/^year$/i), "1990");
    await userEvent.type(screen.getByLabelText(/postcode/i), "SW1A 1AA");
    await userEvent.click(screen.getByRole("button", { name: /continue/i }));
    const fields = screen.getByTestId("form-fields");
    expect(within(fields).getByText(/select a gender/i)).toBeInTheDocument();
  });

  it("clears gender error once a gender is selected", async () => {
    render(<PatientDetailsScreen {...defaultProps} />);
    await userEvent.click(screen.getByRole("button", { name: /continue/i }));
    const fields = screen.getByTestId("form-fields");
    expect(within(fields).getByText(/select a gender/i)).toBeInTheDocument();
    await userEvent.click(screen.getByLabelText(/^female$/i));
    expect(within(fields).queryByText(/select a gender/i)).toBeNull();
  });

  // ---------------------------------------------------------------------------
  // Validation — NHS number
  // ---------------------------------------------------------------------------

  it("shows NHS number error for an entry with wrong digit count", async () => {
    render(<PatientDetailsScreen {...defaultProps} />);
    await userEvent.type(screen.getByLabelText(/nhs number/i), "12345");
    await userEvent.click(screen.getByRole("button", { name: /continue/i }));
    const fields = screen.getByTestId("form-fields");
    expect(within(fields).getByText(/valid 10-digit nhs number/i)).toBeInTheDocument();
  });

  it("input guard silently drops non-digit characters typed into the NHS number field", async () => {
    // The formatNhsNumber helper strips non-digits on change, so typing letters
    // results in an empty field rather than an error. An empty NHS number is
    // valid (the field is optional), so no error should appear.
    render(<PatientDetailsScreen {...defaultProps} />);
    const nhsInput = screen.getByLabelText(/nhs number/i) as HTMLInputElement;
    await userEvent.type(nhsInput, "ABCDEFGHIJ");
    expect(nhsInput.value).toBe("");
    await userEvent.click(screen.getByRole("button", { name: /continue/i }));
    expect(screen.queryByText(/valid 10-digit nhs number/i)).toBeNull();
  });

  it("accepts a 10-digit NHS number with standard spaces", async () => {
    const onContinue = vi.fn();
    render(<PatientDetailsScreen {...defaultProps} onContinue={onContinue} />);
    await fillValidMyselfForm();
    await userEvent.type(screen.getByLabelText(/nhs number/i), "485 777 3456");
    await userEvent.click(screen.getByRole("button", { name: /continue/i }));
    expect(screen.queryByText(/valid 10-digit nhs number/i)).toBeNull();
    expect(onContinue).toHaveBeenCalledOnce();
    const payload = onContinue.mock.calls[0][0];
    expect(payload.nhs_number).toBe("4857773456");
  });

  it("accepts a 10-digit NHS number with no spaces", async () => {
    const onContinue = vi.fn();
    render(<PatientDetailsScreen {...defaultProps} onContinue={onContinue} />);
    await fillValidMyselfForm();
    await userEvent.type(screen.getByLabelText(/nhs number/i), "4857773456");
    await userEvent.click(screen.getByRole("button", { name: /continue/i }));
    expect(onContinue).toHaveBeenCalledOnce();
    const payload = onContinue.mock.calls[0][0];
    expect(payload.nhs_number).toBe("4857773456");
  });

  it("omits nhs_number from payload when field is left empty", async () => {
    const onContinue = vi.fn();
    render(<PatientDetailsScreen {...defaultProps} onContinue={onContinue} />);
    await fillValidMyselfForm();
    await userEvent.click(screen.getByRole("button", { name: /continue/i }));
    expect(onContinue).toHaveBeenCalledOnce();
    const payload = onContinue.mock.calls[0][0];
    expect(payload.nhs_number).toBeUndefined();
  });

  // ---------------------------------------------------------------------------
  // Validation — preferred name (optional)
  // ---------------------------------------------------------------------------

  it("form submits successfully without a preferred name", async () => {
    const onContinue = vi.fn();
    render(<PatientDetailsScreen {...defaultProps} onContinue={onContinue} />);
    await fillValidMyselfForm();
    await userEvent.click(screen.getByRole("button", { name: /continue/i }));
    expect(onContinue).toHaveBeenCalledOnce();
    const payload = onContinue.mock.calls[0][0];
    expect(payload.preferred_name).toBeUndefined();
  });

  it("includes preferred_name in payload when provided", async () => {
    const onContinue = vi.fn();
    render(<PatientDetailsScreen {...defaultProps} onContinue={onContinue} />);
    await fillValidMyselfForm();
    await userEvent.type(screen.getByLabelText(/preferred name/i), "Jo");
    await userEvent.click(screen.getByRole("button", { name: /continue/i }));
    expect(onContinue).toHaveBeenCalledOnce();
    const payload = onContinue.mock.calls[0][0];
    expect(payload.preferred_name).toBe("Jo");
  });

  // ---------------------------------------------------------------------------
  // Input guards
  // ---------------------------------------------------------------------------

  it("DOB input guard prevents non-numeric characters from being entered", async () => {
    render(<PatientDetailsScreen {...defaultProps} />);
    const dayInput = screen.getByLabelText(/^day$/i) as HTMLInputElement;
    await userEvent.type(dayInput, "AB");
    expect(dayInput.value).toBe("");
  });

  it("postcode field forces input to uppercase", async () => {
    render(<PatientDetailsScreen {...defaultProps} />);
    const postcodeInput = screen.getByLabelText(/postcode/i) as HTMLInputElement;
    await userEvent.type(postcodeInput, "sw1a 1aa");
    expect(postcodeInput.value).toBe("SW1A 1AA");
  });

  // ---------------------------------------------------------------------------
  // Accessibility — error summary and ARIA attributes
  // ---------------------------------------------------------------------------

  it("shows the error summary with 'There is a problem' heading on failed submission", async () => {
    render(<PatientDetailsScreen {...defaultProps} />);
    await userEvent.click(screen.getByRole("button", { name: /continue/i }));
    expect(screen.getByRole("heading", { name: /there is a problem/i })).toBeInTheDocument();
  });

  it("error summary lists each field error on failed submission", async () => {
    render(<PatientDetailsScreen {...defaultProps} />);
    await userEvent.click(screen.getByRole("button", { name: /continue/i }));
    const summary = screen
      .getByRole("heading", { name: /there is a problem/i })
      .closest(".error-summary") as HTMLElement;
    // First name and last name errors should appear inside the summary
    expect(summary).toHaveTextContent(/first name/i);
    expect(summary).toHaveTextContent(/last name/i);
  });

  it("error summary is not present before any submission attempt", () => {
    render(<PatientDetailsScreen {...defaultProps} />);
    expect(screen.queryByRole("heading", { name: /there is a problem/i })).toBeNull();
  });

  it("error summary items are links that move focus to the offending field", async () => {
    render(<PatientDetailsScreen {...defaultProps} />);
    await userEvent.click(screen.getByRole("button", { name: /continue/i }));
    const link = screen.getByRole("link", { name: /first name/i });
    await userEvent.click(link);
    expect(document.activeElement).toBe(screen.getByLabelText(/first name/i));
  });

  it("sets aria-invalid on first name input when that field has an error", async () => {
    render(<PatientDetailsScreen {...defaultProps} />);
    await userEvent.click(screen.getByRole("button", { name: /continue/i }));
    const firstNameInput = screen.getByLabelText(/first name/i);
    expect(firstNameInput).toHaveAttribute("aria-invalid", "true");
  });

  it("clears aria-invalid on first name input once a value is entered", async () => {
    render(<PatientDetailsScreen {...defaultProps} />);
    await userEvent.click(screen.getByRole("button", { name: /continue/i }));
    const firstNameInput = screen.getByLabelText(/first name/i);
    expect(firstNameInput).toHaveAttribute("aria-invalid", "true");
    await userEvent.type(firstNameInput, "Jane");
    expect(firstNameInput).toHaveAttribute("aria-invalid", "false");
  });

  // ---------------------------------------------------------------------------
  // Happy path
  // ---------------------------------------------------------------------------

  it("calls onContinue with correct payload for a myself submission", async () => {
    const onContinue = vi.fn();
    render(<PatientDetailsScreen {...defaultProps} onContinue={onContinue} />);

    await fillValidMyselfForm();
    await userEvent.click(screen.getByRole("button", { name: /continue/i }));

    expect(onContinue).toHaveBeenCalledOnce();
    const payload = onContinue.mock.calls[0][0];
    expect(payload.patient_for).toBe("me");
    expect(payload.first_name).toBe("Jane");
    expect(payload.last_name).toBe("Smith");
    expect(payload.gender).toBe("female");
    expect(payload.date_of_birth).toEqual({ day: "15", month: "03", year: "1990" });
    expect(payload.postcode).toBe("SW1A 1AA");
    expect(payload.submitter_name).toBeUndefined();
    expect(payload.submitter_relationship).toBeUndefined();
  });

  it("calls onContinue with submitter fields included for a someone-else submission", async () => {
    const onContinue = vi.fn();
    render(<PatientDetailsScreen {...defaultProps} onContinue={onContinue} />);

    await userEvent.click(screen.getByLabelText(/someone else/i));
    await fillValidMyselfForm();
    await userEvent.type(screen.getByLabelText(/your name/i), "Bob Smith");
    await userEvent.type(screen.getByLabelText(/relationship to patient/i), "Parent");
    await userEvent.click(screen.getByRole("button", { name: /continue/i }));

    expect(onContinue).toHaveBeenCalledOnce();
    const payload = onContinue.mock.calls[0][0];
    expect(payload.patient_for).toBe("someone_else");
    expect(payload.submitter_name).toBe("Bob Smith");
    expect(payload.submitter_relationship).toBe("Parent");
  });

  it("does not call onContinue when validation fails", async () => {
    const onContinue = vi.fn();
    render(<PatientDetailsScreen {...defaultProps} onContinue={onContinue} />);
    await userEvent.click(screen.getByRole("button", { name: /continue/i }));
    expect(onContinue).not.toHaveBeenCalled();
  });

  it("calls onBack when Back is clicked", async () => {
    const onBack = vi.fn();
    render(<PatientDetailsScreen {...defaultProps} onBack={onBack} />);
    await userEvent.click(screen.getByRole("button", { name: /back/i }));
    expect(onBack).toHaveBeenCalledOnce();
  });
});
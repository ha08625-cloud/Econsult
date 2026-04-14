import { render, screen } from "@testing-library/react";
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
    expect(screen.getByLabelText(/your relationship to the patient/i)).toBeTruthy();
  });

  it("renders Continue and Back buttons", () => {
    render(<PatientDetailsScreen {...defaultProps} />);
    expect(screen.getByRole("button", { name: /continue/i })).toBeTruthy();
    expect(screen.getByRole("button", { name: /back/i })).toBeTruthy();
  });

  // ---------------------------------------------------------------------------
  // Validation — existing fields
  // ---------------------------------------------------------------------------

  it("shows first name error when first name is empty on submit", async () => {
    render(<PatientDetailsScreen {...defaultProps} />);
    await userEvent.click(screen.getByRole("button", { name: /continue/i }));
    expect(screen.getByText(/please enter the patient's first name/i)).toBeTruthy();
  });

  it("shows last name error when last name is empty on submit", async () => {
    render(<PatientDetailsScreen {...defaultProps} />);
    await userEvent.type(screen.getByLabelText(/first name/i), "Jane");
    await userEvent.click(screen.getByRole("button", { name: /continue/i }));
    expect(screen.getByText(/please enter the patient's last name/i)).toBeTruthy();
  });

  it("shows DOB error when DOB fields are empty on submit", async () => {
    render(<PatientDetailsScreen {...defaultProps} />);
    await userEvent.type(screen.getByLabelText(/first name/i), "Jane");
    await userEvent.type(screen.getByLabelText(/last name/i), "Smith");
    await userEvent.click(screen.getByRole("button", { name: /continue/i }));
    expect(screen.getByText(/please enter a complete date of birth/i)).toBeTruthy();
  });

  it("shows DOB error when DOB is not a real calendar date", async () => {
    render(<PatientDetailsScreen {...defaultProps} />);
    await userEvent.type(screen.getByLabelText(/first name/i), "Jane");
    await userEvent.type(screen.getByLabelText(/last name/i), "Smith");
    await userEvent.type(screen.getByLabelText(/^day$/i), "31");
    await userEvent.type(screen.getByLabelText(/^month$/i), "02");
    await userEvent.type(screen.getByLabelText(/^year$/i), "1990");
    await userEvent.click(screen.getByRole("button", { name: /continue/i }));
    expect(screen.getByText(/please enter a valid date of birth/i)).toBeTruthy();
  });

  it("shows postcode error when postcode is empty on submit", async () => {
    render(<PatientDetailsScreen {...defaultProps} />);
    await userEvent.type(screen.getByLabelText(/first name/i), "Jane");
    await userEvent.type(screen.getByLabelText(/last name/i), "Smith");
    await userEvent.type(screen.getByLabelText(/^day$/i), "15");
    await userEvent.type(screen.getByLabelText(/^month$/i), "03");
    await userEvent.type(screen.getByLabelText(/^year$/i), "1990");
    await userEvent.click(screen.getByRole("button", { name: /continue/i }));
    expect(screen.getByText(/please enter a postcode/i)).toBeTruthy();
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
    expect(screen.getByText(/please enter a valid uk postcode/i)).toBeTruthy();
  });

  it("shows submitter name and relationship errors when someone-else fields are empty", async () => {
    render(<PatientDetailsScreen {...defaultProps} />);
    await userEvent.click(screen.getByLabelText(/someone else/i));
    await fillValidMyselfForm();
    await userEvent.click(screen.getByRole("button", { name: /continue/i }));
    expect(screen.getByText(/please enter your name/i)).toBeTruthy();
    expect(screen.getByText(/please enter your relationship to the patient/i)).toBeTruthy();
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
    expect(screen.getByText(/please select a gender/i)).toBeTruthy();
  });

  it("clears gender error once a gender is selected", async () => {
    render(<PatientDetailsScreen {...defaultProps} />);
    await userEvent.click(screen.getByRole("button", { name: /continue/i }));
    // Error is visible
    expect(screen.queryByText(/please select a gender/i)).toBeTruthy();
    await userEvent.click(screen.getByLabelText(/^female$/i));
    expect(screen.queryByText(/please select a gender/i)).toBeNull();
  });

  // ---------------------------------------------------------------------------
  // Validation — NHS number
  // ---------------------------------------------------------------------------

  it("shows NHS number error for an entry with wrong digit count", async () => {
    render(<PatientDetailsScreen {...defaultProps} />);
    await userEvent.type(screen.getByLabelText(/nhs number/i), "12345");
    await userEvent.click(screen.getByRole("button", { name: /continue/i }));
    expect(screen.getByText(/valid 10-digit nhs number/i)).toBeTruthy();
  });

  it("shows NHS number error for non-digit characters", async () => {
    render(<PatientDetailsScreen {...defaultProps} />);
    await userEvent.type(screen.getByLabelText(/nhs number/i), "ABCDEFGHIJ");
    await userEvent.click(screen.getByRole("button", { name: /continue/i }));
    expect(screen.getByText(/valid 10-digit nhs number/i)).toBeTruthy();
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
    // Spaces stripped before sending
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
    await userEvent.type(screen.getByLabelText(/your relationship to the patient/i), "Parent");
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
/**
 * LoginView.test.tsx
 *
 * Tests for the two-step 2FA login component.
 *
 * The component has two distinct render states driven by internal step state:
 *   Step 1 ("login"): email + password inputs + Sign in button + forgot link
 *   Step 2 ("code"):  6-digit code input + Verify button + back link
 *
 * Mocking strategy: the entire ../api module is replaced with vi.mock so no
 * real HTTP calls are made.
 *
 * Sections:
 *   1. Step 1 rendering
 *   2. Step 1 behaviour (login submission)
 *   3. Forgot / Set up password link
 *   4. Step 2 rendering
 *   5. Step 2 behaviour
 *   6. Navigation between steps
 */

import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi } from "vitest";
import LoginView from "./LoginView";

// ---------------------------------------------------------------------------
// Mock the api module
// ---------------------------------------------------------------------------

vi.mock("../api", () => ({
  login: vi.fn(),
  verifyMfaCode: vi.fn(),
  requestPasswordReset: vi.fn(),
}));

import { login, verifyMfaCode, requestPasswordReset } from "../api";

const mockLogin = vi.mocked(login);
const mockVerifyMfaCode = vi.mocked(verifyMfaCode);
const mockRequestPasswordReset = vi.mocked(requestPasswordReset);

const noop = () => {};

// Helper: render the component and advance to step 2 by submitting valid credentials.
async function renderAtStepTwo(email = "admin@example.nhs.net") {
  mockLogin.mockResolvedValue(undefined);
  render(<LoginView onSuccess={noop} />);
  await userEvent.type(screen.getByLabelText(/email address/i), email);
  await userEvent.type(screen.getByLabelText(/^password$/i), "SomePassword1!");
  await userEvent.click(screen.getByRole("button", { name: /sign in/i }));
  await waitFor(() =>
    expect(screen.getByLabelText(/security code/i)).toBeTruthy()
  );
}

// ---------------------------------------------------------------------------
// Section 1: Step 1 rendering
// ---------------------------------------------------------------------------

describe("LoginView — step 1 rendering", () => {
  beforeEach(() => {
    vi.resetAllMocks();
  });

  it("renders the Admin login heading", () => {
    render(<LoginView onSuccess={noop} />);
    expect(screen.getByText(/admin login/i)).toBeTruthy();
  });

  it("renders an email input", () => {
    render(<LoginView onSuccess={noop} />);
    expect(screen.getByLabelText(/email address/i)).toBeTruthy();
  });

  it("renders a password input", () => {
    render(<LoginView onSuccess={noop} />);
    expect(screen.getByLabelText(/^password$/i)).toBeTruthy();
  });

  it("renders the Sign in button", () => {
    render(<LoginView onSuccess={noop} />);
    expect(screen.getByRole("button", { name: /sign in/i })).toBeTruthy();
  });

  it("Sign in button is disabled when both fields are empty", () => {
    render(<LoginView onSuccess={noop} />);
    expect(
      (screen.getByRole("button", { name: /sign in/i }) as HTMLButtonElement).disabled
    ).toBe(true);
  });

  it("Sign in button is disabled when only email is filled", async () => {
    render(<LoginView onSuccess={noop} />);
    await userEvent.type(screen.getByLabelText(/email address/i), "admin@nhs.net");
    expect(
      (screen.getByRole("button", { name: /sign in/i }) as HTMLButtonElement).disabled
    ).toBe(true);
  });

  it("Sign in button is disabled when only password is filled", async () => {
    render(<LoginView onSuccess={noop} />);
    await userEvent.type(screen.getByLabelText(/^password$/i), "SomePassword1!");
    expect(
      (screen.getByRole("button", { name: /sign in/i }) as HTMLButtonElement).disabled
    ).toBe(true);
  });

  it("Sign in button is enabled once both email and password are filled", async () => {
    render(<LoginView onSuccess={noop} />);
    await userEvent.type(screen.getByLabelText(/email address/i), "admin@nhs.net");
    await userEvent.type(screen.getByLabelText(/^password$/i), "SomePassword1!");
    expect(
      (screen.getByRole("button", { name: /sign in/i }) as HTMLButtonElement).disabled
    ).toBe(false);
  });

  it("does not render the code input on step 1", () => {
    render(<LoginView onSuccess={noop} />);
    expect(screen.queryByLabelText(/security code/i)).toBeNull();
  });

  it("renders the forgot/set up password link", () => {
    render(<LoginView onSuccess={noop} />);
    expect(
      screen.getByRole("button", { name: /forgot \/ set up password/i })
    ).toBeTruthy();
  });
});

// ---------------------------------------------------------------------------
// Section 2: Step 1 behaviour (login submission)
// ---------------------------------------------------------------------------

describe("LoginView — step 1 behaviour", () => {
  beforeEach(() => {
    vi.resetAllMocks();
  });

  it("calls login with the trimmed, lowercased email and password on submit", async () => {
    mockLogin.mockResolvedValue(undefined);
    render(<LoginView onSuccess={noop} />);
    await userEvent.type(
      screen.getByLabelText(/email address/i),
      "  Admin@Example.NHS.net  "
    );
    await userEvent.type(screen.getByLabelText(/^password$/i), "SomePassword1!");
    await userEvent.click(screen.getByRole("button", { name: /sign in/i }));
    await waitFor(() =>
      expect(mockLogin).toHaveBeenCalledWith("admin@example.nhs.net", "SomePassword1!")
    );
  });

  it("advances to step 2 after a successful login", async () => {
    mockLogin.mockResolvedValue(undefined);
    render(<LoginView onSuccess={noop} />);
    await userEvent.type(screen.getByLabelText(/email address/i), "admin@example.nhs.net");
    await userEvent.type(screen.getByLabelText(/^password$/i), "SomePassword1!");
    await userEvent.click(screen.getByRole("button", { name: /sign in/i }));
    await waitFor(() =>
      expect(screen.getByLabelText(/security code/i)).toBeTruthy()
    );
  });

  it("shows an error message when login fails", async () => {
    mockLogin.mockRejectedValue(new Error("Invalid email or password."));
    render(<LoginView onSuccess={noop} />);
    await userEvent.type(screen.getByLabelText(/email address/i), "admin@nhs.net");
    await userEvent.type(screen.getByLabelText(/^password$/i), "WrongPass1!");
    await userEvent.click(screen.getByRole("button", { name: /sign in/i }));
    await waitFor(() =>
      expect(screen.getByText(/invalid email or password/i)).toBeTruthy()
    );
  });

  it("stays on step 1 when login fails", async () => {
    mockLogin.mockRejectedValue(new Error("Invalid email or password."));
    render(<LoginView onSuccess={noop} />);
    await userEvent.type(screen.getByLabelText(/email address/i), "admin@nhs.net");
    await userEvent.type(screen.getByLabelText(/^password$/i), "WrongPass1!");
    await userEvent.click(screen.getByRole("button", { name: /sign in/i }));
    await waitFor(() =>
      expect(screen.getByText(/invalid email or password/i)).toBeTruthy()
    );
    // Email input should still be present — not on step 2.
    expect(screen.getByLabelText(/email address/i)).toBeTruthy();
  });

  it("submitting with Enter key in the password field calls login", async () => {
    mockLogin.mockResolvedValue(undefined);
    render(<LoginView onSuccess={noop} />);
    await userEvent.type(screen.getByLabelText(/email address/i), "admin@example.nhs.net");
    await userEvent.type(
      screen.getByLabelText(/^password$/i),
      "SomePassword1!{Enter}"
    );
    await waitFor(() => expect(mockLogin).toHaveBeenCalledOnce());
  });

  it("does not call login when both fields are empty on Enter", async () => {
    render(<LoginView onSuccess={noop} />);
    screen.getByLabelText(/email address/i).focus();
    await userEvent.keyboard("{Enter}");
    expect(mockLogin).not.toHaveBeenCalled();
  });
});

// ---------------------------------------------------------------------------
// Section 3: Forgot / Set up password link
// ---------------------------------------------------------------------------

describe("LoginView — forgot/set up password link", () => {
  beforeEach(() => {
    vi.resetAllMocks();
    // requestPasswordReset always resolves (server always returns 200).
    mockRequestPasswordReset.mockResolvedValue(undefined);
  });

  it("clicking the link with a filled email calls requestPasswordReset", async () => {
    render(<LoginView onSuccess={noop} />);
    await userEvent.type(screen.getByLabelText(/email address/i), "admin@nhs.net");
    await userEvent.click(
      screen.getByRole("button", { name: /forgot \/ set up password/i })
    );
    await waitFor(() =>
      expect(mockRequestPasswordReset).toHaveBeenCalledWith("admin@nhs.net")
    );
  });

  it("shows a confirmation message after clicking the link with a filled email", async () => {
    render(<LoginView onSuccess={noop} />);
    await userEvent.type(screen.getByLabelText(/email address/i), "admin@nhs.net");
    await userEvent.click(
      screen.getByRole("button", { name: /forgot \/ set up password/i })
    );
    await waitFor(() =>
      expect(
        screen.getByText(/if this email is registered/i)
      ).toBeTruthy()
    );
  });

  it("shows an error prompt when the link is clicked with an empty email", async () => {
    render(<LoginView onSuccess={noop} />);
    await userEvent.click(
      screen.getByRole("button", { name: /forgot \/ set up password/i })
    );
    expect(mockRequestPasswordReset).not.toHaveBeenCalled();
    expect(screen.getByText(/enter your email address above first/i)).toBeTruthy();
  });

  it("does not advance to step 2 after clicking the forgot link", async () => {
    render(<LoginView onSuccess={noop} />);
    await userEvent.type(screen.getByLabelText(/email address/i), "admin@nhs.net");
    await userEvent.click(
      screen.getByRole("button", { name: /forgot \/ set up password/i })
    );
    await waitFor(() =>
      expect(screen.getByText(/if this email is registered/i)).toBeTruthy()
    );
    // Still on step 1 — code input should not exist.
    expect(screen.queryByLabelText(/security code/i)).toBeNull();
  });
});

// ---------------------------------------------------------------------------
// Section 4: Step 2 rendering
// ---------------------------------------------------------------------------

describe("LoginView — step 2 rendering", () => {
  beforeEach(() => {
    vi.resetAllMocks();
  });

  it("renders the Enter your code heading on step 2", async () => {
    await renderAtStepTwo();
    expect(screen.getByText(/enter your code/i)).toBeTruthy();
  });

  it("displays the submitted email address in the step 2 subtitle", async () => {
    await renderAtStepTwo("admin@example.nhs.net");
    expect(screen.getByText(/admin@example\.nhs\.net/)).toBeTruthy();
  });

  it("renders the security code input", async () => {
    await renderAtStepTwo();
    expect(screen.getByLabelText(/security code/i)).toBeTruthy();
  });

  it("renders the Verify button", async () => {
    await renderAtStepTwo();
    expect(screen.getByRole("button", { name: /^verify$/i })).toBeTruthy();
  });

  it("Verify button is disabled when fewer than 6 digits are entered", async () => {
    await renderAtStepTwo();
    await userEvent.type(screen.getByLabelText(/security code/i), "12345");
    expect(
      (screen.getByRole("button", { name: /^verify$/i }) as HTMLButtonElement).disabled
    ).toBe(true);
  });

  it("Verify button is enabled once 6 digits are entered", async () => {
    await renderAtStepTwo();
    await userEvent.type(screen.getByLabelText(/security code/i), "123456");
    expect(
      (screen.getByRole("button", { name: /^verify$/i }) as HTMLButtonElement).disabled
    ).toBe(false);
  });

  it("renders the back to login button", async () => {
    await renderAtStepTwo();
    expect(
      screen.getByRole("button", { name: /back to login/i })
    ).toBeTruthy();
  });

  it("does not render the email input on step 2", async () => {
    await renderAtStepTwo();
    expect(screen.queryByLabelText(/email address/i)).toBeNull();
  });

  it("does not render the password input on step 2", async () => {
    await renderAtStepTwo();
    expect(screen.queryByLabelText(/^password$/i)).toBeNull();
  });
});

// ---------------------------------------------------------------------------
// Section 5: Step 2 behaviour
// ---------------------------------------------------------------------------

describe("LoginView — step 2 behaviour", () => {
  beforeEach(() => {
    vi.resetAllMocks();
  });

  it("calls verifyMfaCode with the email and code on submit", async () => {
    mockVerifyMfaCode.mockResolvedValue(undefined);
    await renderAtStepTwo("admin@example.nhs.net");
    await userEvent.type(screen.getByLabelText(/security code/i), "123456");
    await userEvent.click(screen.getByRole("button", { name: /^verify$/i }));
    await waitFor(() =>
      expect(mockVerifyMfaCode).toHaveBeenCalledWith("admin@example.nhs.net", "123456")
    );
  });

  it("calls onSuccess after a successful verify", async () => {
    const onSuccess = vi.fn();
    mockLogin.mockResolvedValue(undefined);
    mockVerifyMfaCode.mockResolvedValue(undefined);
    render(<LoginView onSuccess={onSuccess} />);
    await userEvent.type(screen.getByLabelText(/email address/i), "admin@example.nhs.net");
    await userEvent.type(screen.getByLabelText(/^password$/i), "SomePassword1!");
    await userEvent.click(screen.getByRole("button", { name: /sign in/i }));
    await waitFor(() => expect(screen.getByLabelText(/security code/i)).toBeTruthy());
    await userEvent.type(screen.getByLabelText(/security code/i), "123456");
    await userEvent.click(screen.getByRole("button", { name: /^verify$/i }));
    await waitFor(() => expect(onSuccess).toHaveBeenCalledOnce());
  });

  it("shows an error message when verifyMfaCode fails", async () => {
    mockVerifyMfaCode.mockRejectedValue(new Error("Invalid or expired code"));
    await renderAtStepTwo();
    await userEvent.type(screen.getByLabelText(/security code/i), "000000");
    await userEvent.click(screen.getByRole("button", { name: /^verify$/i }));
    await waitFor(() =>
      expect(screen.getByText(/invalid or expired code/i)).toBeTruthy()
    );
  });

  it("does not call onSuccess when verifyMfaCode fails", async () => {
    const onSuccess = vi.fn();
    mockLogin.mockResolvedValue(undefined);
    mockVerifyMfaCode.mockRejectedValue(new Error("Bad code"));
    render(<LoginView onSuccess={onSuccess} />);
    await userEvent.type(screen.getByLabelText(/email address/i), "admin@example.nhs.net");
    await userEvent.type(screen.getByLabelText(/^password$/i), "SomePassword1!");
    await userEvent.click(screen.getByRole("button", { name: /sign in/i }));
    await waitFor(() => expect(screen.getByLabelText(/security code/i)).toBeTruthy());
    await userEvent.type(screen.getByLabelText(/security code/i), "000000");
    await userEvent.click(screen.getByRole("button", { name: /^verify$/i }));
    await waitFor(() => expect(screen.getByText(/bad code/i)).toBeTruthy());
    expect(onSuccess).not.toHaveBeenCalled();
  });

  it("strips non-digit characters from the code input", async () => {
    mockVerifyMfaCode.mockResolvedValue(undefined);
    await renderAtStepTwo();
    await userEvent.type(screen.getByLabelText(/security code/i), "1a2b3c4d5e6f");
    await userEvent.click(screen.getByRole("button", { name: /^verify$/i }));
    await waitFor(() =>
      expect(mockVerifyMfaCode).toHaveBeenCalledWith(expect.any(String), "123456")
    );
  });

  it("submitting with Enter key on the code input calls verifyMfaCode", async () => {
    mockVerifyMfaCode.mockResolvedValue(undefined);
    await renderAtStepTwo();
    await userEvent.type(
      screen.getByLabelText(/security code/i),
      "123456{Enter}"
    );
    await waitFor(() => expect(mockVerifyMfaCode).toHaveBeenCalledOnce());
  });
});

// ---------------------------------------------------------------------------
// Section 6: Navigation between steps
// ---------------------------------------------------------------------------

describe("LoginView — navigation between steps", () => {
  beforeEach(() => {
    vi.resetAllMocks();
  });

  it("clicking Back to login returns to step 1", async () => {
    await renderAtStepTwo();
    await userEvent.click(
      screen.getByRole("button", { name: /back to login/i })
    );
    expect(screen.getByLabelText(/email address/i)).toBeTruthy();
    expect(screen.queryByLabelText(/security code/i)).toBeNull();
  });

  it("the email field is retained when returning to step 1", async () => {
    await renderAtStepTwo("admin@example.nhs.net");
    await userEvent.click(
      screen.getByRole("button", { name: /back to login/i })
    );
    const emailInput = screen.getByLabelText(/email address/i) as HTMLInputElement;
    expect(emailInput.value).toBe("admin@example.nhs.net");
  });

  it("any step 2 error is cleared when returning to step 1", async () => {
    mockVerifyMfaCode.mockRejectedValue(new Error("Bad code"));
    await renderAtStepTwo();
    await userEvent.type(screen.getByLabelText(/security code/i), "000000");
    await userEvent.click(screen.getByRole("button", { name: /^verify$/i }));
    await waitFor(() => expect(screen.getByText(/bad code/i)).toBeTruthy());
    await userEvent.click(
      screen.getByRole("button", { name: /back to login/i })
    );
    expect(screen.queryByText(/bad code/i)).toBeNull();
  });
});
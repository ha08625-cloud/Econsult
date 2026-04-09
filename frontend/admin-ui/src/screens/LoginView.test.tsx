/**
 * LoginView.test.tsx
 *
 * Tests for the two-step MFA login component.
 *
 * The component has two distinct render states driven by internal step state:
 *   Step 1 (email): email input + Send code button
 *   Step 2 (code):  code input + Verify button + back link
 *
 * Mocking strategy: the entire ../api module is replaced with vi.mock so no
 * real HTTP calls are made.
 *
 * Sections:
 *   1. Step 1 rendering
 *   2. Step 1 behaviour
 *   3. Step 2 rendering
 *   4. Step 2 behaviour
 *   5. Navigation between steps
 */

import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi } from "vitest";
import LoginView from "./LoginView";

// ---------------------------------------------------------------------------
// Mock the api module
// ---------------------------------------------------------------------------

vi.mock("../api", () => ({
  requestMfaCode: vi.fn(),
  verifyMfaCode: vi.fn(),
}));

import { requestMfaCode, verifyMfaCode } from "../api";

const mockRequestMfaCode = vi.mocked(requestMfaCode);
const mockVerifyMfaCode = vi.mocked(verifyMfaCode);

const noop = () => {};

// Helper: render the component and advance to step 2 by submitting a valid email.
async function renderAtStepTwo(email = "admin@example.nhs.net") {
  mockRequestMfaCode.mockResolvedValue(undefined);
  render(<LoginView onSuccess={noop} />);
  await userEvent.type(screen.getByLabelText(/email address/i), email);
  await userEvent.click(screen.getByRole("button", { name: /send code/i }));
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

  it("renders the Send code button", () => {
    render(<LoginView onSuccess={noop} />);
    expect(screen.getByRole("button", { name: /send code/i })).toBeTruthy();
  });

  it("Send code button is disabled when the email field is empty", () => {
    render(<LoginView onSuccess={noop} />);
    expect(
      (screen.getByRole("button", { name: /send code/i }) as HTMLButtonElement).disabled
    ).toBe(true);
  });

  it("Send code button is enabled once an email is typed", async () => {
    render(<LoginView onSuccess={noop} />);
    await userEvent.type(screen.getByLabelText(/email address/i), "a@b.com");
    expect(
      (screen.getByRole("button", { name: /send code/i }) as HTMLButtonElement).disabled
    ).toBe(false);
  });

  it("does not render the code input on step 1", () => {
    render(<LoginView onSuccess={noop} />);
    expect(screen.queryByLabelText(/security code/i)).toBeNull();
  });
});

// ---------------------------------------------------------------------------
// Section 2: Step 1 behaviour
// ---------------------------------------------------------------------------

describe("LoginView — step 1 behaviour", () => {
  beforeEach(() => {
    vi.resetAllMocks();
  });

  it("calls requestMfaCode with the trimmed, lowercased email on submit", async () => {
    mockRequestMfaCode.mockResolvedValue(undefined);
    render(<LoginView onSuccess={noop} />);
    await userEvent.type(
      screen.getByLabelText(/email address/i),
      "  Admin@Example.NHS.net  "
    );
    await userEvent.click(screen.getByRole("button", { name: /send code/i }));
    await waitFor(() =>
      expect(mockRequestMfaCode).toHaveBeenCalledWith("admin@example.nhs.net")
    );
  });

  it("advances to step 2 after a successful requestMfaCode", async () => {
    mockRequestMfaCode.mockResolvedValue(undefined);
    render(<LoginView onSuccess={noop} />);
    await userEvent.type(screen.getByLabelText(/email address/i), "admin@example.nhs.net");
    await userEvent.click(screen.getByRole("button", { name: /send code/i }));
    await waitFor(() =>
      expect(screen.getByLabelText(/security code/i)).toBeTruthy()
    );
  });

  it("shows an error message when requestMfaCode fails", async () => {
    mockRequestMfaCode.mockRejectedValue(new Error("Domain not allowed"));
    render(<LoginView onSuccess={noop} />);
    await userEvent.type(screen.getByLabelText(/email address/i), "admin@other.com");
    await userEvent.click(screen.getByRole("button", { name: /send code/i }));
    await waitFor(() =>
      expect(screen.getByText(/domain not allowed/i)).toBeTruthy()
    );
  });

  it("stays on step 1 when requestMfaCode fails", async () => {
    mockRequestMfaCode.mockRejectedValue(new Error("Rate limited"));
    render(<LoginView onSuccess={noop} />);
    await userEvent.type(screen.getByLabelText(/email address/i), "admin@example.nhs.net");
    await userEvent.click(screen.getByRole("button", { name: /send code/i }));
    await waitFor(() => expect(screen.getByText(/rate limited/i)).toBeTruthy());
    // Email input should still be present — not on step 2
    expect(screen.getByLabelText(/email address/i)).toBeTruthy();
  });

  it("submitting with Enter key calls requestMfaCode", async () => {
    mockRequestMfaCode.mockResolvedValue(undefined);
    render(<LoginView onSuccess={noop} />);
    await userEvent.type(
      screen.getByLabelText(/email address/i),
      "admin@example.nhs.net{Enter}"
    );
    await waitFor(() =>
      expect(mockRequestMfaCode).toHaveBeenCalledOnce()
    );
  });

  it("does not call requestMfaCode when email is blank on Enter", async () => {
    render(<LoginView onSuccess={noop} />);
    // Focus the input and press Enter without typing anything
    screen.getByLabelText(/email address/i).focus();
    await userEvent.keyboard("{Enter}");
    expect(mockRequestMfaCode).not.toHaveBeenCalled();
  });
});

// ---------------------------------------------------------------------------
// Section 3: Step 2 rendering
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

  it("renders the Use a different email address back link", async () => {
    await renderAtStepTwo();
    expect(screen.getByRole("button", { name: /use a different email address/i })).toBeTruthy();
  });

  it("does not render the email input on step 2", async () => {
    await renderAtStepTwo();
    expect(screen.queryByLabelText(/email address/i)).toBeNull();
  });
});

// ---------------------------------------------------------------------------
// Section 4: Step 2 behaviour
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
    mockRequestMfaCode.mockResolvedValue(undefined);
    mockVerifyMfaCode.mockResolvedValue(undefined);
    render(<LoginView onSuccess={onSuccess} />);
    await userEvent.type(screen.getByLabelText(/email address/i), "admin@example.nhs.net");
    await userEvent.click(screen.getByRole("button", { name: /send code/i }));
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
    mockRequestMfaCode.mockResolvedValue(undefined);
    mockVerifyMfaCode.mockRejectedValue(new Error("Bad code"));
    render(<LoginView onSuccess={onSuccess} />);
    await userEvent.type(screen.getByLabelText(/email address/i), "admin@example.nhs.net");
    await userEvent.click(screen.getByRole("button", { name: /send code/i }));
    await waitFor(() => expect(screen.getByLabelText(/security code/i)).toBeTruthy());
    await userEvent.type(screen.getByLabelText(/security code/i), "000000");
    await userEvent.click(screen.getByRole("button", { name: /^verify$/i }));
    await waitFor(() => expect(screen.getByText(/bad code/i)).toBeTruthy());
    expect(onSuccess).not.toHaveBeenCalled();
  });

  it("strips non-digit characters from the code input", async () => {
    mockVerifyMfaCode.mockResolvedValue(undefined);
    await renderAtStepTwo();
    // Type digits mixed with letters — only digits should be kept
    await userEvent.type(screen.getByLabelText(/security code/i), "1a2b3c4d5e6f");
    await userEvent.click(screen.getByRole("button", { name: /^verify$/i }));
    await waitFor(() =>
      expect(mockVerifyMfaCode).toHaveBeenCalledWith(
        expect.any(String),
        "123456"
      )
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
// Section 5: Navigation between steps
// ---------------------------------------------------------------------------

describe("LoginView — navigation between steps", () => {
  beforeEach(() => {
    vi.resetAllMocks();
  });

  it("clicking Use a different email address returns to step 1", async () => {
    await renderAtStepTwo();
    await userEvent.click(
      screen.getByRole("button", { name: /use a different email address/i })
    );
    expect(screen.getByLabelText(/email address/i)).toBeTruthy();
    expect(screen.queryByLabelText(/security code/i)).toBeNull();
  });

  it("the email field is retained when returning to step 1", async () => {
    await renderAtStepTwo("admin@example.nhs.net");
    await userEvent.click(
      screen.getByRole("button", { name: /use a different email address/i })
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
      screen.getByRole("button", { name: /use a different email address/i })
    );
    expect(screen.queryByText(/bad code/i)).toBeNull();
  });
});
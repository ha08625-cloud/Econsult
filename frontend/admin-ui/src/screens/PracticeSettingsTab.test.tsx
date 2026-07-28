/**
 * PracticeSettingsTab.test.tsx
 *
 * Tests for the practice settings component.
 *
 * The component has two independent sections loaded in parallel on mount:
 *   1. Contact email — display, edit, and save the practice email address.
 *   2. Doctor list   — display, add, reorder, delete, and save doctor names.
 *
 * Both sections share a single load state. If either fetch fails the whole
 * component shows an error. Each section has its own independent save state.
 *
 * Mocking strategy: the entire ../api module is replaced with vi.mock so no
 * real HTTP calls are made.
 *
 * Sections:
 *   1. Initial load
 *   2. Contact email
 *   3. Doctor list — display and editing
 *   4. Doctor list — saving
 */

import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi } from "vitest";
import PracticeSettingsTab from "./PracticeSettingsTab";

// ---------------------------------------------------------------------------
// Mock the api module
// ---------------------------------------------------------------------------

vi.mock("../api", () => ({
  getPractice: vi.fn(),
  updatePracticeEmail: vi.fn(),
  getDoctors: vi.fn(),
  putDoctors: vi.fn(),
  AuthError: class AuthError extends Error {
    constructor() {
      super("Session expired or not authenticated.");
      this.name = "AuthError";
    }
  },
}));

import {
  getPractice,
  updatePracticeEmail,
  getDoctors,
  putDoctors,
  AuthError,
} from "../api";

const mockGetPractice = vi.mocked(getPractice);
const mockUpdatePracticeEmail = vi.mocked(updatePracticeEmail);
const mockGetDoctors = vi.mocked(getDoctors);
const mockPutDoctors = vi.mocked(putDoctors);

// ---------------------------------------------------------------------------
// Shared fixtures
// ---------------------------------------------------------------------------

const PRACTICE = {
  practice_id: "test-practice",
  name: "Test Surgery",
  email: "test@surgery.nhs.net",
};

function setupSuccessfulLoad(doctors: string[] = []) {
  mockGetPractice.mockResolvedValue(PRACTICE);
  mockGetDoctors.mockResolvedValue(doctors);
}

const noop = () => {};

// ---------------------------------------------------------------------------
// Section 1: Initial load
// ---------------------------------------------------------------------------

describe("PracticeSettingsTab — initial load", () => {
  beforeEach(() => {
    vi.resetAllMocks();
  });

  it("shows a loading indicator before the fetches resolve", () => {
    mockGetPractice.mockReturnValue(new Promise(() => {}));
    mockGetDoctors.mockReturnValue(new Promise(() => {}));
    render(<PracticeSettingsTab onAuthError={noop} />);
    expect(screen.getByText(/loading practice details/i)).toBeTruthy();
  });

  it("renders the practice name after a successful load", async () => {
    setupSuccessfulLoad();
    render(<PracticeSettingsTab onAuthError={noop} />);
    await waitFor(() =>
      expect(screen.getByText("Test Surgery")).toBeTruthy()
    );
  });

  it("renders the practice ID after a successful load", async () => {
    setupSuccessfulLoad();
    render(<PracticeSettingsTab onAuthError={noop} />);
    await waitFor(() =>
      expect(screen.getByText("test-practice")).toBeTruthy()
    );
  });

  it("shows an error message when getPractice fails", async () => {
    mockGetPractice.mockRejectedValue(new Error("Network error"));
    mockGetDoctors.mockResolvedValue([]);
    render(<PracticeSettingsTab onAuthError={noop} />);
    await waitFor(() =>
      expect(screen.getByText(/network error/i)).toBeTruthy()
    );
  });

  it("shows an error message when getDoctors fails", async () => {
    mockGetPractice.mockResolvedValue(PRACTICE);
    mockGetDoctors.mockRejectedValue(new Error("Failed to load doctors"));
    render(<PracticeSettingsTab onAuthError={noop} />);
    await waitFor(() =>
      expect(screen.getByText(/failed to load doctors/i)).toBeTruthy()
    );
  });

  it("calls onAuthError when getPractice returns a 401", async () => {
    const onAuthError = vi.fn();
    mockGetPractice.mockRejectedValue(new AuthError());
    mockGetDoctors.mockResolvedValue([]);
    render(<PracticeSettingsTab onAuthError={onAuthError} />);
    await waitFor(() => expect(onAuthError).toHaveBeenCalledOnce());
  });
});

// ---------------------------------------------------------------------------
// Section 2: Contact email
// ---------------------------------------------------------------------------

describe("PracticeSettingsTab — contact email", () => {
  beforeEach(() => {
    vi.resetAllMocks();
  });

  it("pre-populates the email input with the fetched address", async () => {
    setupSuccessfulLoad();
    render(<PracticeSettingsTab onAuthError={noop} />);
    await waitFor(() => {
      const input = screen.getByRole("textbox", {
        name: /contact email address/i,
      }) as HTMLInputElement;
      expect(input.value).toBe("test@surgery.nhs.net");
    });
  });

  it("the email Save button is disabled when the input is empty", async () => {
    setupSuccessfulLoad();
    render(<PracticeSettingsTab onAuthError={noop} />);
    await waitFor(() =>
      expect(screen.getByRole("textbox", { name: /contact email address/i })).toBeTruthy()
    );
    // Clear the pre-populated value
    await userEvent.clear(
      screen.getByRole("textbox", { name: /contact email address/i })
    );
    // The email save button is the first Save button in the document
    const saveButtons = screen.getAllByRole("button", { name: /^save$/i });
    expect((saveButtons[0] as HTMLButtonElement).disabled).toBe(true);
  });

  it("a successful email save shows a confirmation message", async () => {
    setupSuccessfulLoad();
    mockUpdatePracticeEmail.mockResolvedValue({
      ...PRACTICE,
      email: "new@surgery.nhs.net",
    });
    render(<PracticeSettingsTab onAuthError={noop} />);
    await waitFor(() =>
      expect(screen.getByRole("textbox", { name: /contact email address/i })).toBeTruthy()
    );
    await userEvent.click(screen.getAllByRole("button", { name: /^save$/i })[0]);
    await waitFor(() =>
      expect(screen.getByText(/email address updated/i)).toBeTruthy()
    );
  });

  it("calls updatePracticeEmail with the current input value", async () => {
    setupSuccessfulLoad();
    mockUpdatePracticeEmail.mockResolvedValue(PRACTICE);
    render(<PracticeSettingsTab onAuthError={noop} />);
    await waitFor(() =>
      expect(screen.getByRole("textbox", { name: /contact email address/i })).toBeTruthy()
    );
    await userEvent.clear(
      screen.getByRole("textbox", { name: /contact email address/i })
    );
    await userEvent.type(
      screen.getByRole("textbox", { name: /contact email address/i }),
      "new@surgery.nhs.net"
    );
    await userEvent.click(screen.getAllByRole("button", { name: /^save$/i })[0]);
    await waitFor(() =>
      expect(mockUpdatePracticeEmail).toHaveBeenCalledWith("new@surgery.nhs.net")
    );
  });

  it("shows an error message when updatePracticeEmail fails", async () => {
    setupSuccessfulLoad();
    mockUpdatePracticeEmail.mockRejectedValue(new Error("Invalid email format"));
    render(<PracticeSettingsTab onAuthError={noop} />);
    await waitFor(() =>
      expect(screen.getByRole("textbox", { name: /contact email address/i })).toBeTruthy()
    );
    await userEvent.click(screen.getAllByRole("button", { name: /^save$/i })[0]);
    await waitFor(() =>
      expect(screen.getByText(/invalid email format/i)).toBeTruthy()
    );
  });

  it("calls onAuthError when updatePracticeEmail returns a 401", async () => {
    const onAuthError = vi.fn();
    setupSuccessfulLoad();
    mockUpdatePracticeEmail.mockRejectedValue(new AuthError());
    render(<PracticeSettingsTab onAuthError={onAuthError} />);
    await waitFor(() =>
      expect(screen.getByRole("textbox", { name: /contact email address/i })).toBeTruthy()
    );
    await userEvent.click(screen.getAllByRole("button", { name: /^save$/i })[0]);
    await waitFor(() => expect(onAuthError).toHaveBeenCalledOnce());
  });
});

// ---------------------------------------------------------------------------
// Section 3: Doctor list — display and editing
// ---------------------------------------------------------------------------

describe("PracticeSettingsTab — doctor list display and editing", () => {
  beforeEach(() => {
    vi.resetAllMocks();
  });

  it("shows the empty state message when no doctors are configured", async () => {
    setupSuccessfulLoad([]);
    render(<PracticeSettingsTab onAuthError={noop} />);
    await waitFor(() =>
      expect(screen.getByText(/no doctors configured/i)).toBeTruthy()
    );
  });

  it("renders each doctor name from the fetched list", async () => {
    setupSuccessfulLoad(["Dr Smith", "Dr Jones"]);
    render(<PracticeSettingsTab onAuthError={noop} />);
    await waitFor(() => {
      expect(screen.getByText("Dr Smith")).toBeTruthy();
      expect(screen.getByText("Dr Jones")).toBeTruthy();
    });
  });

  it("adds a doctor to the list when Add is clicked", async () => {
    setupSuccessfulLoad([]);
    render(<PracticeSettingsTab onAuthError={noop} />);
    await waitFor(() =>
      expect(screen.getByRole("textbox", { name: /new doctor name/i })).toBeTruthy()
    );
    await userEvent.type(
      screen.getByRole("textbox", { name: /new doctor name/i }),
      "Dr Patel"
    );
    await userEvent.click(screen.getByRole("button", { name: /^add$/i }));
    expect(screen.getByText("Dr Patel")).toBeTruthy();
  });

  it("clears the add input after a doctor is added", async () => {
    setupSuccessfulLoad([]);
    render(<PracticeSettingsTab onAuthError={noop} />);
    await waitFor(() =>
      expect(screen.getByRole("textbox", { name: /new doctor name/i })).toBeTruthy()
    );
    await userEvent.type(
      screen.getByRole("textbox", { name: /new doctor name/i }),
      "Dr Patel"
    );
    await userEvent.click(screen.getByRole("button", { name: /^add$/i }));
    expect(
      (screen.getByRole("textbox", { name: /new doctor name/i }) as HTMLInputElement).value
    ).toBe("");
  });

  it("pressing Enter in the add input adds the doctor", async () => {
    setupSuccessfulLoad([]);
    render(<PracticeSettingsTab onAuthError={noop} />);
    await waitFor(() =>
      expect(screen.getByRole("textbox", { name: /new doctor name/i })).toBeTruthy()
    );
    await userEvent.type(
      screen.getByRole("textbox", { name: /new doctor name/i }),
      "Dr Patel{Enter}"
    );
    expect(screen.getByText("Dr Patel")).toBeTruthy();
  });

  it("rejects adding a duplicate doctor name and does not add it to the list", async () => {
    setupSuccessfulLoad(["Dr Smith"]);
    render(<PracticeSettingsTab onAuthError={noop} />);
    await waitFor(() =>
      expect(screen.getByRole("textbox", { name: /new doctor name/i })).toBeTruthy()
    );
    await userEvent.type(
      screen.getByRole("textbox", { name: /new doctor name/i }),
      "dr smith"
    );
    await userEvent.click(screen.getByRole("button", { name: /^add$/i }));
    expect(screen.getByText(/already on the list/i)).toBeTruthy();
    expect(screen.queryAllByLabelText(/remove/i)).toHaveLength(1);
  });

  it("Add button is disabled when the input is empty", async () => {
    setupSuccessfulLoad([]);
    render(<PracticeSettingsTab onAuthError={noop} />);
    await waitFor(() =>
      expect(screen.getByRole("button", { name: /^add$/i })).toBeTruthy()
    );
    expect(
      (screen.getByRole("button", { name: /^add$/i }) as HTMLButtonElement).disabled
    ).toBe(true);
  });

  it("removes a doctor when their Remove button is clicked", async () => {
    setupSuccessfulLoad(["Dr Smith", "Dr Jones"]);
    render(<PracticeSettingsTab onAuthError={noop} />);
    await waitFor(() => expect(screen.getByText("Dr Smith")).toBeTruthy());
    await userEvent.click(screen.getByRole("button", { name: /remove dr smith/i }));
    expect(screen.queryByText("Dr Smith")).toBeNull();
    expect(screen.getByText("Dr Jones")).toBeTruthy();
  });

  it("moves a doctor up when their Move up button is clicked", async () => {
    setupSuccessfulLoad(["Dr Smith", "Dr Jones"]);
    render(<PracticeSettingsTab onAuthError={noop} />);
    await waitFor(() => expect(screen.getByText("Dr Jones")).toBeTruthy());
    await userEvent.click(screen.getByRole("button", { name: /move dr jones up/i }));
    // After moving up, Dr Jones should appear before Dr Smith in the list items
    const items = screen.getAllByRole("listitem");
    expect(items[0].textContent).toContain("Dr Jones");
    expect(items[1].textContent).toContain("Dr Smith");
  });

  it("moves a doctor down when their Move down button is clicked", async () => {
    setupSuccessfulLoad(["Dr Smith", "Dr Jones"]);
    render(<PracticeSettingsTab onAuthError={noop} />);
    await waitFor(() => expect(screen.getByText("Dr Smith")).toBeTruthy());
    await userEvent.click(screen.getByRole("button", { name: /move dr smith down/i }));
    const items = screen.getAllByRole("listitem");
    expect(items[0].textContent).toContain("Dr Jones");
    expect(items[1].textContent).toContain("Dr Smith");
  });

  it("Move up button is disabled for the first doctor in the list", async () => {
    setupSuccessfulLoad(["Dr Smith", "Dr Jones"]);
    render(<PracticeSettingsTab onAuthError={noop} />);
    await waitFor(() => expect(screen.getByText("Dr Smith")).toBeTruthy());
    expect(
      (screen.getByRole("button", { name: /move dr smith up/i }) as HTMLButtonElement).disabled
    ).toBe(true);
  });

  it("Move down button is disabled for the last doctor in the list", async () => {
    setupSuccessfulLoad(["Dr Smith", "Dr Jones"]);
    render(<PracticeSettingsTab onAuthError={noop} />);
    await waitFor(() => expect(screen.getByText("Dr Jones")).toBeTruthy());
    expect(
      (screen.getByRole("button", { name: /move dr jones down/i }) as HTMLButtonElement).disabled
    ).toBe(true);
  });
});

// ---------------------------------------------------------------------------
// Section 4: Doctor list — saving
// ---------------------------------------------------------------------------

describe("PracticeSettingsTab — doctor list saving", () => {
  beforeEach(() => {
    vi.resetAllMocks();
  });

  it("clicking Save doctor list calls putDoctors with the current list", async () => {
    setupSuccessfulLoad(["Dr Smith"]);
    mockPutDoctors.mockResolvedValue(["Dr Smith"]);
    render(<PracticeSettingsTab onAuthError={noop} />);
    await waitFor(() =>
      expect(screen.getByRole("button", { name: /save doctor list/i })).toBeTruthy()
    );
    await userEvent.click(screen.getByRole("button", { name: /save doctor list/i }));
    await waitFor(() =>
      expect(mockPutDoctors).toHaveBeenCalledWith(["Dr Smith"])
    );
  });

  it("a successful save shows a confirmation message", async () => {
    setupSuccessfulLoad(["Dr Smith"]);
    mockPutDoctors.mockResolvedValue(["Dr Smith"]);
    render(<PracticeSettingsTab onAuthError={noop} />);
    await waitFor(() =>
      expect(screen.getByRole("button", { name: /save doctor list/i })).toBeTruthy()
    );
    await userEvent.click(screen.getByRole("button", { name: /save doctor list/i }));
    await waitFor(() =>
      expect(screen.getByText(/doctor list saved/i)).toBeTruthy()
    );
  });

  it("shows an error message when putDoctors fails", async () => {
    setupSuccessfulLoad(["Dr Smith"]);
    mockPutDoctors.mockRejectedValue(new Error("Server error"));
    render(<PracticeSettingsTab onAuthError={noop} />);
    await waitFor(() =>
      expect(screen.getByRole("button", { name: /save doctor list/i })).toBeTruthy()
    );
    await userEvent.click(screen.getByRole("button", { name: /save doctor list/i }));
    await waitFor(() =>
      expect(screen.getByText(/server error/i)).toBeTruthy()
    );
  });

  it("calls onAuthError when putDoctors returns a 401", async () => {
    const onAuthError = vi.fn();
    setupSuccessfulLoad(["Dr Smith"]);
    mockPutDoctors.mockRejectedValue(new AuthError());
    render(<PracticeSettingsTab onAuthError={onAuthError} />);
    await waitFor(() =>
      expect(screen.getByRole("button", { name: /save doctor list/i })).toBeTruthy()
    );
    await userEvent.click(screen.getByRole("button", { name: /save doctor list/i }));
    await waitFor(() => expect(onAuthError).toHaveBeenCalledOnce());
  });

  it("putDoctors is called with the list after local edits, not the original fetched list", async () => {
    setupSuccessfulLoad(["Dr Smith"]);
    mockPutDoctors.mockResolvedValue(["Dr Smith", "Dr Patel"]);
    render(<PracticeSettingsTab onAuthError={noop} />);
    await waitFor(() =>
      expect(screen.getByRole("textbox", { name: /new doctor name/i })).toBeTruthy()
    );
    await userEvent.type(
      screen.getByRole("textbox", { name: /new doctor name/i }),
      "Dr Patel"
    );
    await userEvent.click(screen.getByRole("button", { name: /^add$/i }));
    await userEvent.click(screen.getByRole("button", { name: /save doctor list/i }));
    await waitFor(() =>
      expect(mockPutDoctors).toHaveBeenCalledWith(["Dr Smith", "Dr Patel"])
    );
  });
});
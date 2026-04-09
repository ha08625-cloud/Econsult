/**
 * AvailabilityEditor.test.tsx
 *
 * Tests for the AvailabilityEditor screen component.
 *
 * Mocking strategy: the entire ../api module is replaced with vi.mock so no
 * real HTTP calls are made. Each test that exercises an API interaction
 * overrides the relevant mock return value directly.
 *
 * window.confirm (used when saving with no days selected) is not tested here
 * because it requires mocking a browser global. Add a test for it if the
 * confirmation behaviour becomes a source of bugs.
 *
 * Sections:
 *   1. Initial load
 *   2. Schedule editing
 *   3. Override panel
 *   4. Exception panel
 */

import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi } from "vitest";
import AvailabilityEditor from "./AvailabilityEditor";
import type { AvailabilityConfig, AvailabilityException } from "../types";

// ---------------------------------------------------------------------------
// Mock the api module
// ---------------------------------------------------------------------------

vi.mock("../api", () => ({
  fetchAvailability: vi.fn(),
  putAvailability: vi.fn(),
  postOverride: vi.fn(),
  deleteOverride: vi.fn(),
  fetchExceptions: vi.fn(),
  putException: vi.fn(),
  deleteException: vi.fn(),
  AuthError: class AuthError extends Error {
    constructor() {
      super("Session expired or not authenticated.");
      this.name = "AuthError";
    }
  },
}));

import {
  fetchAvailability,
  putAvailability,
  postOverride,
  deleteOverride,
  fetchExceptions,
  putException,
  deleteException,
  AuthError,
} from "../api";

const mockFetchAvailability = vi.mocked(fetchAvailability);
const mockPutAvailability = vi.mocked(putAvailability);
const mockPostOverride = vi.mocked(postOverride);
const mockDeleteOverride = vi.mocked(deleteOverride);
const mockFetchExceptions = vi.mocked(fetchExceptions);
const mockPutException = vi.mocked(putException);
const mockDeleteException = vi.mocked(deleteException);

// ---------------------------------------------------------------------------
// Shared fixtures
// ---------------------------------------------------------------------------

function makeConfig(overrides: Partial<AvailabilityConfig> = {}): AvailabilityConfig {
  return {
    practice_id: "test-practice",
    is_active: false,
    weekly_open_days: [],
    open_time: "08:00",
    close_time: "18:30",
    closed_message: null,
    override_status: null,
    override_expires_at: null,
    override_message: null,
    ...overrides,
  };
}

function makeException(overrides: Partial<AvailabilityException> = {}): AvailabilityException {
  return {
    exception_date: "2099-12-25",
    exception_type: "closed",
    open_time: null,
    close_time: null,
    note: null,
    ...overrides,
  };
}

const noop = () => {};

// ---------------------------------------------------------------------------
// Section 1: Initial load
// ---------------------------------------------------------------------------

describe("AvailabilityEditor — initial load", () => {
  beforeEach(() => {
    vi.resetAllMocks();
  });

  it("shows a loading indicator before the fetch resolves", () => {
    // Never resolves — component stays in loading state
    mockFetchAvailability.mockReturnValue(new Promise(() => {}));
    render(<AvailabilityEditor onAuthError={noop} />);
    expect(screen.getByText(/loading/i)).toBeTruthy();
  });

  it("renders the card title after a successful fetch", async () => {
    mockFetchAvailability.mockResolvedValue(makeConfig());
    mockFetchExceptions.mockResolvedValue([]);
    render(<AvailabilityEditor onAuthError={noop} />);
    await waitFor(() =>
      expect(screen.getByText(/opening hours/i)).toBeTruthy()
    );
  });

  it("renders the enable availability checkbox after load", async () => {
    mockFetchAvailability.mockResolvedValue(makeConfig());
    mockFetchExceptions.mockResolvedValue([]);
    render(<AvailabilityEditor onAuthError={noop} />);
    await waitFor(() =>
      expect(screen.getByRole("checkbox", { name: /enable availability checking/i })).toBeTruthy()
    );
  });

  it("checkbox reflects is_active=false from fetched config", async () => {
    mockFetchAvailability.mockResolvedValue(makeConfig({ is_active: false }));
    mockFetchExceptions.mockResolvedValue([]);
    render(<AvailabilityEditor onAuthError={noop} />);
    await waitFor(() => {
      const checkbox = screen.getByRole("checkbox", {
        name: /enable availability checking/i,
      }) as HTMLInputElement;
      expect(checkbox.checked).toBe(false);
    });
  });

  it("checkbox reflects is_active=true from fetched config", async () => {
    mockFetchAvailability.mockResolvedValue(
      makeConfig({ is_active: true, weekly_open_days: ["mon"] })
    );
    mockFetchExceptions.mockResolvedValue([]);
    render(<AvailabilityEditor onAuthError={noop} />);
    await waitFor(() => {
      const checkbox = screen.getByRole("checkbox", {
        name: /enable availability checking/i,
      }) as HTMLInputElement;
      expect(checkbox.checked).toBe(true);
    });
  });

  it("shows an error message when the fetch fails", async () => {
    mockFetchAvailability.mockRejectedValue(new Error("Server unavailable"));
    render(<AvailabilityEditor onAuthError={noop} />);
    await waitFor(() =>
      expect(screen.getByText(/could not load availability settings/i)).toBeTruthy()
    );
  });

  it("calls onAuthError when fetch returns a 401", async () => {
    const onAuthError = vi.fn();
    mockFetchAvailability.mockRejectedValue(new AuthError());
    render(<AvailabilityEditor onAuthError={onAuthError} />);
    await waitFor(() => expect(onAuthError).toHaveBeenCalledOnce());
  });
});

// ---------------------------------------------------------------------------
// Section 2: Schedule editing
// ---------------------------------------------------------------------------

describe("AvailabilityEditor — schedule editing", () => {
  beforeEach(() => {
    vi.resetAllMocks();
  });

  it("does not render day checkboxes when is_active is false", async () => {
    mockFetchAvailability.mockResolvedValue(makeConfig({ is_active: false }));
    mockFetchExceptions.mockResolvedValue([]);
    render(<AvailabilityEditor onAuthError={noop} />);
    await waitFor(() =>
      // Wait for loading to finish
      expect(screen.queryByText(/loading/i)).toBeNull()
    );
    expect(screen.queryByText("Mon")).toBeNull();
  });

  it("renders day checkboxes when is_active is true", async () => {
    mockFetchAvailability.mockResolvedValue(
      makeConfig({ is_active: true, weekly_open_days: ["mon", "tue"] })
    );
    mockFetchExceptions.mockResolvedValue([]);
    render(<AvailabilityEditor onAuthError={noop} />);
    await waitFor(() => expect(screen.getByText("Mon")).toBeTruthy());
    expect(screen.getByText("Tue")).toBeTruthy();
    expect(screen.getByText("Sat")).toBeTruthy();
    expect(screen.getByText("Sun")).toBeTruthy();
  });

  it("toggling the enable checkbox calls onUnsavedChange(true)", async () => {
    const onUnsavedChange = vi.fn();
    mockFetchAvailability.mockResolvedValue(makeConfig({ is_active: false }));
    mockFetchExceptions.mockResolvedValue([]);
    render(<AvailabilityEditor onAuthError={noop} onUnsavedChange={onUnsavedChange} />);
    await waitFor(() =>
      expect(screen.getByRole("checkbox", { name: /enable availability checking/i })).toBeTruthy()
    );
    await userEvent.click(
      screen.getByRole("checkbox", { name: /enable availability checking/i })
    );
    expect(onUnsavedChange).toHaveBeenLastCalledWith(true);
  });

  it("a successful save shows a Saved status message", async () => {
    const savedConfig = makeConfig({ is_active: false });
    mockFetchAvailability.mockResolvedValue(savedConfig);
    mockPutAvailability.mockResolvedValue(savedConfig);
    mockFetchExceptions.mockResolvedValue([]);
    render(<AvailabilityEditor onAuthError={noop} />);
    await waitFor(() =>
      expect(screen.getByRole("button", { name: /^save$/i })).toBeTruthy()
    );
    await userEvent.click(screen.getByRole("button", { name: /^save$/i }));
    await waitFor(() => expect(screen.getByText(/saved/i)).toBeTruthy());
  });

  it("a successful save calls onUnsavedChange(false)", async () => {
    const onUnsavedChange = vi.fn();
    const savedConfig = makeConfig({ is_active: false });
    mockFetchAvailability.mockResolvedValue(savedConfig);
    mockPutAvailability.mockResolvedValue(savedConfig);
    mockFetchExceptions.mockResolvedValue([]);
    render(<AvailabilityEditor onAuthError={noop} onUnsavedChange={onUnsavedChange} />);
    await waitFor(() =>
      expect(screen.getByRole("button", { name: /^save$/i })).toBeTruthy()
    );
    await userEvent.click(screen.getByRole("button", { name: /^save$/i }));
    await waitFor(() =>
      expect(onUnsavedChange).toHaveBeenLastCalledWith(false)
    );
  });

  it("a failed save shows an error status message", async () => {
    mockFetchAvailability.mockResolvedValue(makeConfig());
    mockPutAvailability.mockRejectedValue(new Error("Save failed"));
    mockFetchExceptions.mockResolvedValue([]);
    render(<AvailabilityEditor onAuthError={noop} />);
    await waitFor(() =>
      expect(screen.getByRole("button", { name: /^save$/i })).toBeTruthy()
    );
    await userEvent.click(screen.getByRole("button", { name: /^save$/i }));
    await waitFor(() => expect(screen.getByText(/save failed/i)).toBeTruthy());
  });

  it("calls onAuthError when save returns a 401", async () => {
    const onAuthError = vi.fn();
    mockFetchAvailability.mockResolvedValue(makeConfig());
    mockPutAvailability.mockRejectedValue(new AuthError());
    mockFetchExceptions.mockResolvedValue([]);
    render(<AvailabilityEditor onAuthError={onAuthError} />);
    await waitFor(() =>
      expect(screen.getByRole("button", { name: /^save$/i })).toBeTruthy()
    );
    await userEvent.click(screen.getByRole("button", { name: /^save$/i }));
    await waitFor(() => expect(onAuthError).toHaveBeenCalledOnce());
  });
});

// ---------------------------------------------------------------------------
// Section 3: Override panel
// ---------------------------------------------------------------------------

describe("AvailabilityEditor — override panel", () => {
  beforeEach(() => {
    vi.resetAllMocks();
  });

  it("does not render the override panel when is_active is false", async () => {
    mockFetchAvailability.mockResolvedValue(makeConfig({ is_active: false }));
    mockFetchExceptions.mockResolvedValue([]);
    render(<AvailabilityEditor onAuthError={noop} />);
    await waitFor(() => expect(screen.queryByText(/loading/i)).toBeNull());
    expect(screen.queryByText(/temporary override/i)).toBeNull();
  });

  it("renders the override panel when is_active is true", async () => {
    mockFetchAvailability.mockResolvedValue(
      makeConfig({ is_active: true, weekly_open_days: ["mon"] })
    );
    mockFetchExceptions.mockResolvedValue([]);
    render(<AvailabilityEditor onAuthError={noop} />);
    await waitFor(() =>
      expect(screen.getByText(/temporary override/i)).toBeTruthy()
    );
  });

  it("renders Force open and Force closed buttons when no override is active", async () => {
    mockFetchAvailability.mockResolvedValue(
      makeConfig({ is_active: true, weekly_open_days: ["mon"] })
    );
    mockFetchExceptions.mockResolvedValue([]);
    render(<AvailabilityEditor onAuthError={noop} />);
    await waitFor(() =>
      expect(screen.getByRole("button", { name: /force open/i })).toBeTruthy()
    );
    expect(screen.getByRole("button", { name: /force closed/i })).toBeTruthy();
  });

  it("clicking Force open opens the override form", async () => {
    mockFetchAvailability.mockResolvedValue(
      makeConfig({ is_active: true, weekly_open_days: ["mon"] })
    );
    mockFetchExceptions.mockResolvedValue([]);
    render(<AvailabilityEditor onAuthError={noop} />);
    await waitFor(() =>
      expect(screen.getByRole("button", { name: /force open/i })).toBeTruthy()
    );
    await userEvent.click(screen.getByRole("button", { name: /force open/i }));
    expect(screen.getByRole("button", { name: /set override/i })).toBeTruthy();
  });

  it("submitting the override form calls postOverride", async () => {
    const config = makeConfig({ is_active: true, weekly_open_days: ["mon"] });
    mockFetchAvailability.mockResolvedValue(config);
    mockFetchExceptions.mockResolvedValue([]);
    mockPostOverride.mockResolvedValue(config);
    render(<AvailabilityEditor onAuthError={noop} />);
    await waitFor(() =>
      expect(screen.getByRole("button", { name: /force open/i })).toBeTruthy()
    );
    await userEvent.click(screen.getByRole("button", { name: /force open/i }));
    await userEvent.click(screen.getByRole("button", { name: /set override/i }));
    await waitFor(() => expect(mockPostOverride).toHaveBeenCalledOnce());
  });

  it("cancelling the override form hides it", async () => {
    mockFetchAvailability.mockResolvedValue(
      makeConfig({ is_active: true, weekly_open_days: ["mon"] })
    );
    mockFetchExceptions.mockResolvedValue([]);
    render(<AvailabilityEditor onAuthError={noop} />);
    await waitFor(() =>
      expect(screen.getByRole("button", { name: /force open/i })).toBeTruthy()
    );
    await userEvent.click(screen.getByRole("button", { name: /force open/i }));
    await userEvent.click(screen.getByRole("button", { name: /^cancel$/i }));
    expect(screen.queryByRole("button", { name: /set override/i })).toBeNull();
  });

  it("shows a Clear override button when an active override exists", async () => {
    // expires_at is set far in the future so isOverrideActive returns true
    mockFetchAvailability.mockResolvedValue(
      makeConfig({
        is_active: true,
        weekly_open_days: ["mon"],
        override_status: "closed",
        override_expires_at: "2099-01-01T00:00:00Z",
      })
    );
    mockFetchExceptions.mockResolvedValue([]);
    render(<AvailabilityEditor onAuthError={noop} />);
    await waitFor(() =>
      expect(screen.getByRole("button", { name: /clear override/i })).toBeTruthy()
    );
  });

  it("clicking Clear override calls deleteOverride", async () => {
    const config = makeConfig({
      is_active: true,
      weekly_open_days: ["mon"],
      override_status: "closed",
      override_expires_at: "2099-01-01T00:00:00Z",
    });
    mockFetchAvailability.mockResolvedValue(config);
    mockFetchExceptions.mockResolvedValue([]);
    mockDeleteOverride.mockResolvedValue(
      makeConfig({ is_active: true, weekly_open_days: ["mon"] })
    );
    render(<AvailabilityEditor onAuthError={noop} />);
    await waitFor(() =>
      expect(screen.getByRole("button", { name: /clear override/i })).toBeTruthy()
    );
    await userEvent.click(screen.getByRole("button", { name: /clear override/i }));
    await waitFor(() => expect(mockDeleteOverride).toHaveBeenCalledOnce());
  });

  it("calls onAuthError when postOverride returns a 401", async () => {
    const onAuthError = vi.fn();
    const config = makeConfig({ is_active: true, weekly_open_days: ["mon"] });
    mockFetchAvailability.mockResolvedValue(config);
    mockFetchExceptions.mockResolvedValue([]);
    mockPostOverride.mockRejectedValue(new AuthError());
    render(<AvailabilityEditor onAuthError={onAuthError} />);
    await waitFor(() =>
      expect(screen.getByRole("button", { name: /force open/i })).toBeTruthy()
    );
    await userEvent.click(screen.getByRole("button", { name: /force open/i }));
    await userEvent.click(screen.getByRole("button", { name: /set override/i }));
    await waitFor(() => expect(onAuthError).toHaveBeenCalledOnce());
  });
});

// ---------------------------------------------------------------------------
// Section 4: Exception panel
// ---------------------------------------------------------------------------

describe("AvailabilityEditor — exception panel", () => {
  beforeEach(() => {
    vi.resetAllMocks();
  });

  it("does not render the exception panel when is_active is false", async () => {
    mockFetchAvailability.mockResolvedValue(makeConfig({ is_active: false }));
    mockFetchExceptions.mockResolvedValue([]);
    render(<AvailabilityEditor onAuthError={noop} />);
    await waitFor(() => expect(screen.queryByText(/loading/i)).toBeNull());
    expect(screen.queryByText(/date exceptions/i)).toBeNull();
  });

  it("renders the exception panel when is_active is true", async () => {
    mockFetchAvailability.mockResolvedValue(
      makeConfig({ is_active: true, weekly_open_days: ["mon"] })
    );
    mockFetchExceptions.mockResolvedValue([]);
    render(<AvailabilityEditor onAuthError={noop} />);
    await waitFor(() =>
      expect(screen.getByText(/date exceptions/i)).toBeTruthy()
    );
  });

  it("renders existing exceptions returned by fetchExceptions", async () => {
    mockFetchAvailability.mockResolvedValue(
      makeConfig({ is_active: true, weekly_open_days: ["mon"] })
    );
    mockFetchExceptions.mockResolvedValue([
      makeException({ exception_date: "2099-12-25", note: "Christmas" }),
    ]);
    render(<AvailabilityEditor onAuthError={noop} />);
    await waitFor(() =>
      expect(screen.getByText(/christmas/i)).toBeTruthy()
    );
  });

  it("shows 'No upcoming exceptions' when the list is empty", async () => {
    mockFetchAvailability.mockResolvedValue(
      makeConfig({ is_active: true, weekly_open_days: ["mon"] })
    );
    mockFetchExceptions.mockResolvedValue([]);
    render(<AvailabilityEditor onAuthError={noop} />);
    await waitFor(() =>
      expect(screen.getByText(/no upcoming exceptions/i)).toBeTruthy()
    );
  });

  it("clicking Add exception opens the exception form", async () => {
    mockFetchAvailability.mockResolvedValue(
      makeConfig({ is_active: true, weekly_open_days: ["mon"] })
    );
    mockFetchExceptions.mockResolvedValue([]);
    render(<AvailabilityEditor onAuthError={noop} />);
    await waitFor(() =>
      expect(screen.getByRole("button", { name: /add exception/i })).toBeTruthy()
    );
    await userEvent.click(screen.getByRole("button", { name: /add exception/i }));
    expect(screen.getByRole("button", { name: /save exception/i })).toBeTruthy();
  });

  it("submitting the exception form without a date shows a validation error", async () => {
    mockFetchAvailability.mockResolvedValue(
      makeConfig({ is_active: true, weekly_open_days: ["mon"] })
    );
    mockFetchExceptions.mockResolvedValue([]);
    render(<AvailabilityEditor onAuthError={noop} />);
    await waitFor(() =>
      expect(screen.getByRole("button", { name: /add exception/i })).toBeTruthy()
    );
    await userEvent.click(screen.getByRole("button", { name: /add exception/i }));
    await userEvent.click(screen.getByRole("button", { name: /save exception/i }));
    expect(screen.getByText(/please select a date/i)).toBeTruthy();
    expect(mockPutException).not.toHaveBeenCalled();
  });

  it("cancelling the exception form hides it", async () => {
    mockFetchAvailability.mockResolvedValue(
      makeConfig({ is_active: true, weekly_open_days: ["mon"] })
    );
    mockFetchExceptions.mockResolvedValue([]);
    render(<AvailabilityEditor onAuthError={noop} />);
    await waitFor(() =>
      expect(screen.getByRole("button", { name: /add exception/i })).toBeTruthy()
    );
    await userEvent.click(screen.getByRole("button", { name: /add exception/i }));
    await userEvent.click(screen.getByRole("button", { name: /^cancel$/i }));
    expect(screen.queryByRole("button", { name: /save exception/i })).toBeNull();
  });

  it("a successful exception submission calls putException then re-fetches the list", async () => {
    const config = makeConfig({ is_active: true, weekly_open_days: ["mon"] });
    mockFetchAvailability.mockResolvedValue(config);
    mockFetchExceptions.mockResolvedValue([]);
    mockPutException.mockResolvedValue(undefined);
    render(<AvailabilityEditor onAuthError={noop} />);
    await waitFor(() =>
      expect(screen.getByRole("button", { name: /add exception/i })).toBeTruthy()
    );
    await userEvent.click(screen.getByRole("button", { name: /add exception/i }));
    // Fill in the date field
    await userEvent.type(screen.getByLabelText(/^date$/i), "2099-12-26");
    await userEvent.click(screen.getByRole("button", { name: /save exception/i }));
    await waitFor(() => expect(mockPutException).toHaveBeenCalledOnce());
    // fetchExceptions is called once on load and once after a successful save
    expect(mockFetchExceptions).toHaveBeenCalledTimes(2);
  });

  it("clicking Delete on an exception calls deleteException with the correct date", async () => {
    mockFetchAvailability.mockResolvedValue(
      makeConfig({ is_active: true, weekly_open_days: ["mon"] })
    );
    mockFetchExceptions.mockResolvedValue([
      makeException({ exception_date: "2099-12-25", note: "Christmas" }),
    ]);
    mockDeleteException.mockResolvedValue(undefined);
    render(<AvailabilityEditor onAuthError={noop} />);
    await waitFor(() =>
      expect(screen.getByRole("button", { name: /^delete$/i })).toBeTruthy()
    );
    await userEvent.click(screen.getByRole("button", { name: /^delete$/i }));
    await waitFor(() =>
      expect(mockDeleteException).toHaveBeenCalledWith("2099-12-25")
    );
  });

  it("calls onAuthError when fetchExceptions returns a 401", async () => {
    const onAuthError = vi.fn();
    mockFetchAvailability.mockResolvedValue(
      makeConfig({ is_active: true, weekly_open_days: ["mon"] })
    );
    mockFetchExceptions.mockRejectedValue(new AuthError());
    render(<AvailabilityEditor onAuthError={onAuthError} />);
    await waitFor(() => expect(onAuthError).toHaveBeenCalledOnce());
  });
});